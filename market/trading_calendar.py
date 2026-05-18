# market/trading_calendar.py
"""台股交易日曆。

Hybrid 設計：
- 歷史日期：查詢 DuckDB 的 TAIEX 資料，有 row 就是交易日（天然處理颱風假、補班日、特殊休市）
- 未來日期：規則版 fallback（週末 + 已知國定假日）

註：未來日期的假日表需每年人工維護。Step 9 後可改成從 TWSE API 抓。

Version: v0.1.1 (2026-05-16)
Changelog:
  v0.1.1 (2026-05-16): DB 缺 TAIEX 資料時 log warning 提醒 (避免颱風假誤判為交易日)
  v0.1.0 (2026-05-16): Initial implementation
"""
from __future__ import annotations

from datetime import date, timedelta

from data.database import connect
from utils.logger import get_logger

logger = get_logger(__name__)


# ────────────────────────────────────────────────────────────
# Fallback holidays (僅用於未來日期判斷)
# 來源：TWSE 公告之國定假日。每年需更新。
# 不包含補班日（補班日是交易日）。
# ────────────────────────────────────────────────────────────
TW_HOLIDAYS_FALLBACK: set[date] = {
    # 2026 (預估，正式公告以 TWSE 為準)
    date(2026, 1, 1),    # 元旦
    date(2026, 2, 16),   # 春節
    date(2026, 2, 17),
    date(2026, 2, 18),
    date(2026, 2, 19),
    date(2026, 2, 20),
    date(2026, 2, 27),   # 228 連假
    date(2026, 4, 3),    # 兒童清明
    date(2026, 4, 6),
    date(2026, 5, 1),    # 勞動節
    date(2026, 6, 19),   # 端午節
    date(2026, 9, 25),   # 中秋節
    date(2026, 10, 9),   # 雙十連假
    date(2026, 10, 12),
    # 2027 起需另外加入
}


def is_trading_day(d: date) -> bool:
    """判斷某日是否為交易日。

    歷史日期 (≤ 今日)：查 DuckDB 是否有 TAIEX 資料
    未來日期：週末 + holiday 表

    注意：若 DB 沒抓 TAIEX 資料 (新裝環境)，歷史日期會 fall through 到規則 fallback，
    此時無法區分颱風假/特殊休市。會 log 一次 warning 提醒使用者執行 init_db.py + 補抓 TAIEX。
    """
    # 週末必非交易日
    if d.weekday() >= 5:  # Sat=5, Sun=6
        return False

    today = date.today()

    if d <= today:
        # 歷史：以 DB 為準
        try:
            with connect(read_only=True) as conn:
                n = conn.execute(
                    "SELECT COUNT(*) FROM daily_price WHERE stock_id = 'TAIEX' AND date = ?",
                    [d],
                ).fetchone()
            if n is not None and n[0] > 0:
                return True
            # DB 沒這天的 TAIEX 資料 → fall through 到 fallback 規則
            # log warning 提醒可能不準
            _warn_calendar_fallback_once(d)
        except Exception as e:
            logger.warning("trading_day_db_check_failed", date=str(d), error=str(e))

    # 未來日期 (或 DB 沒資料時 fallback)
    return d not in TW_HOLIDAYS_FALLBACK


# 用 module-level set 避免重複 warning 洗 log
_WARNED_DATES: set[date] = set()


def _warn_calendar_fallback_once(d: date) -> None:
    """同一個日期只 warn 一次，避免回測時瘋狂洗 log。"""
    if d not in _WARNED_DATES:
        _WARNED_DATES.add(d)
        if len(_WARNED_DATES) <= 5:  # 也限制總警告數量
            logger.warning(
                "calendar_fallback_no_taiex_data",
                date=str(d),
                hint="Run scripts/init_db.py and ensure TAIEX daily_price is loaded "
                     "for accurate historical trading-day detection.",
            )
        elif len(_WARNED_DATES) == 6:
            logger.warning(
                "calendar_fallback_warnings_suppressed",
                hint="Further fallback warnings will be suppressed this session.",
            )


def previous_trading_day(d: date, max_back_days: int = 30) -> date | None:
    """找到 d 之前最近的一個交易日（不含 d）。"""
    for i in range(1, max_back_days + 1):
        candidate = d - timedelta(days=i)
        if is_trading_day(candidate):
            return candidate
    logger.error("no_previous_trading_day_found", date=str(d), max_back=max_back_days)
    return None


def next_trading_day(d: date, max_forward_days: int = 30) -> date | None:
    """找到 d 之後最近的一個交易日（不含 d）。

    Calendar truth: returns whether a date IS a trading day per the market calendar.
    Does NOT verify whether daily_price_adj data has been ingested for that date.
    For T+1 fill use case, use `next_fillable_day` instead.
    """
    for i in range(1, max_forward_days + 1):
        candidate = d + timedelta(days=i)
        if is_trading_day(candidate):
            return candidate
    logger.error("no_next_trading_day_found", date=str(d), max_forward=max_forward_days)
    return None


def next_fillable_day(d: date, max_forward_days: int = 30) -> date | None:
    """找到 d 之後最近、且 daily_price_adj 已有資料的交易日。

    v0.1.14.2-c3: explicit split from `next_trading_day` to separate two
    concerns previously conflated in execution.shutdown.next_trading_day:

      - next_trading_day(d): calendar truth ("is 5/18 a trading day?")
      - next_fillable_day(d): calendar + data availability
                               ("is 5/18 a trading day AND do we have data?")

    For T+1 fill semantics (signal on day T, fill at T+1 close as proxy), we
    need the FILLABLE variant: the next trading day with data ingested. If the
    calendar says 5/18 is a trading day but data isn't there yet, return None
    so the operator knows to wait for data ingestion before running.

    Returns None if no fillable day found within max_forward_days.
    """
    cal_next = next_trading_day(d, max_forward_days=max_forward_days)
    if cal_next is None:
        return None
    # Check data availability for the calendar's next trading day
    try:
        with connect(read_only=True) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM daily_price_adj WHERE date = ?", [cal_next]
            ).fetchone()
        return cal_next if row and row[0] > 0 else None
    except Exception as e:
        logger.warning("next_fillable_day_db_check_failed", date=str(cal_next), error=str(e))
        return None


def get_trading_days(start: date, end: date) -> list[date]:
    """回傳 [start, end] 區間的所有交易日（含端點）。"""
    result = []
    cur = start
    while cur <= end:
        if is_trading_day(cur):
            result.append(cur)
        cur += timedelta(days=1)
    return result


def trading_days_between(start: date, end: date) -> int:
    """計算 [start, end] 區間的交易日數量。"""
    return len(get_trading_days(start, end))


# ────────────────────────────────────────────────────────────
# Smoke test
# ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    today = date.today()
    print(f"Today ({today}) is trading day: {is_trading_day(today)}")

    prev = previous_trading_day(today)
    nxt = next_trading_day(today)
    print(f"Previous trading day: {prev}")
    print(f"Next trading day:     {nxt}")

    # 2026 春節期間應為休市
    cny = date(2026, 2, 17)
    print(f"CNY {cny} is trading day: {is_trading_day(cny)}")

    # 過去 7 天
    week_ago = today - timedelta(days=7)
    days = get_trading_days(week_ago, today)
    print(f"Trading days {week_ago} → {today}: {len(days)} days")
    for d in days:
        print(f"  {d}")
