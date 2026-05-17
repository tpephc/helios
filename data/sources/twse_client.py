# data/sources/twse_client.py
"""TWSE 官方 API client。

依 docs/data_sources_catalog.md 的「TWSE primary for daily ops」架構，覆蓋四個 endpoint：

1. `STOCK_DAY_ALL` (openapi)   — 全市場最新交易日 OHLC，daily 增量主力
2. `STOCK_DAY`     (www.twse)  — 個股某月日 K (historical per-month, 慢)
3. `MI_INDEX`      (openapi)   — 50+ 指數含 30+ 產業類股，sector rotation 用
4. `MI_5MINS_HIST` (openapi)   — TAIEX 過去 10 個交易日 OHLC，TAIEX 增量用

設計原則：
- 無 token，自律 rate limit (預設 1 秒間隔)
- 兩個 base URL：openapi (新, JSON 直丟) + www.twse (舊, response=json 參數)
- 統一 Polars 輸出 + 民國年 / 千分號 parser 全集中
- 不負責 cache (上層 fetcher 處理)

Version: v0.1.1 (2026-05-16)
Changelog:
  v0.1.1 (2026-05-16): _get_json 加 tenacity retry (3 次 exp backoff);
                       stock_month 當 stat ≠ OK 時 log warning;
                       新增 company_info() (t187ap03_L) + dividend_forecast() (TWT48U)
  v0.1.0 (2026-05-16): Initial — 4 endpoints + 民國年 / 千分號 parser
"""
from __future__ import annotations

import time
from datetime import date
from typing import Any

import httpx
import polars as pl
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from utils.logger import get_logger

logger = get_logger(__name__)


class TwseError(Exception):
    """TWSE API 呼叫失敗。"""


# ─────────────────────────────────────────────────────────────
# Parsers — 統一處理 TWSE 三種 quirks
# ─────────────────────────────────────────────────────────────


def parse_roc_compact(s: str) -> date | None:
    """民國年連月日 → date。

    Examples:
      "1150508" → date(2026, 5, 8)
      "1150410" → date(2026, 4, 10)
      "990101"  → date(2010, 1, 1)   (民國 99)
    """
    if not s or not s.isdigit():
        return None
    # 民國年部分可能是 2 或 3 位
    if len(s) == 6:  # 99年/月/日 → 990101
        roc_year = int(s[:2])
        month = int(s[2:4])
        day = int(s[4:6])
    elif len(s) == 7:  # 115年/月/日 → 1150508
        roc_year = int(s[:3])
        month = int(s[3:5])
        day = int(s[5:7])
    else:
        return None
    try:
        return date(roc_year + 1911, month, day)
    except ValueError:
        return None


def parse_roc_slashed(s: str) -> date | None:
    """民國年/月/日 → date。

    Examples:
      "114/01/02" → date(2025, 1, 2)
    """
    if not s or "/" not in s:
        return None
    try:
        parts = s.split("/")
        if len(parts) != 3:
            return None
        roc_year = int(parts[0])
        month = int(parts[1])
        day = int(parts[2])
        return date(roc_year + 1911, month, day)
    except (ValueError, IndexError):
        return None


def parse_twse_num(s: Any) -> float | None:
    """TWSE 數字 string → float。

    處理：
    - 千分號:  "45,045,125" → 45045125.0
    - null:    "--", "", "X" → None
    - 帶符號:  "+10.00" / "-25.00" → ±10.0 / -25.0
    - 已是數字: 原樣返回
    """
    if s is None:
        return None
    if isinstance(s, int | float):
        return float(s)
    s = str(s).strip()
    if not s or s in ("--", "X", "x", "N/A"):
        return None
    # 去千分號 + 空白
    cleaned = s.replace(",", "").replace(" ", "")
    if not cleaned or cleaned == "-":
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_western_compact(s: Any) -> date | None:
    """西元年連月日 YYYYMMDD → date。

    不同於 parse_roc_compact (民國年)，這裡的「上市日期」、「成立日期」是西元年。

    Examples:
      "19940905" → date(1994, 9, 5)   (台積電上市)
      "20220715" → date(2022, 7, 15)
    """
    if s is None:
        return None
    s = str(s).strip()
    if len(s) != 8 or not s.isdigit():
        return None
    try:
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except ValueError:
        return None


# ─────────────────────────────────────────────────────────────
# Client
# ─────────────────────────────────────────────────────────────


class TwseClient:
    """TWSE 官方 API client (無 token, 自律 rate limit)。"""

    OPENAPI_BASE = "https://openapi.twse.com.tw/v1"
    HISTORICAL_BASE = "https://www.twse.com.tw/exchangeReport"

    def __init__(
        self,
        sleep_between_calls: float = 1.0,
        timeout: float = 30.0,
    ) -> None:
        self._http = httpx.Client(timeout=timeout)
        self._min_interval = sleep_between_calls
        self._last_call_time = 0.0

    def _rate_limit_wait(self) -> None:
        """確保兩次 call 之間至少 `_min_interval` 秒。"""
        elapsed = time.time() - self._last_call_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call_time = time.time()

    @retry(
        retry=retry_if_exception_type(httpx.HTTPError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _http_get(self, url: str, params: dict | None = None) -> httpx.Response:
        """HTTP GET 一次嘗試 (tenacity 包裝重試)。"""
        return self._http.get(url, params=params)

    def _get_json(self, url: str, params: dict | None = None) -> Any:
        """執行 GET + rate limit + parse json，失敗丟 TwseError。

        v0.1.1: 加 tenacity retry (3 次, exp backoff 1-8s) 處理 TWSE 偶發
        connection reset / timeout / 5xx。JSON decode 失敗不重試 (response 格式錯)。
        """
        self._rate_limit_wait()
        try:
            r = self._http_get(url, params)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            raise TwseError(f"HTTP error for {url} (after retries): {e}") from e
        except ValueError as e:
            raise TwseError(f"JSON decode failed for {url}: {e}") from e

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> TwseClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # ─────────────────────────────────────────────────────────
    # Endpoint 1: STOCK_DAY_ALL — 全市場最新交易日 OHLC
    # ─────────────────────────────────────────────────────────

    def daily_all(self) -> pl.DataFrame:
        """全市場最新交易日 OHLC (~1700 檔)。

        每天執行一次即可，跟 FinMind 比對「昨天那筆」做 cross-source spot check。
        不接 date 參數 — 永遠回最新一天。

        Returns:
            Columns: stock_id, name, date, open, high, low, close, volume, turnover, transactions, spread
        """
        rows = self._get_json(f"{self.OPENAPI_BASE}/exchangeReport/STOCK_DAY_ALL")
        if not rows:
            return pl.DataFrame()

        df = pl.from_dicts(rows)

        return df.select(
            pl.col("Code").alias("stock_id"),
            pl.col("Name").alias("name"),
            pl.col("Date").map_elements(parse_roc_compact, return_dtype=pl.Date).alias("date"),
            pl.col("OpeningPrice").map_elements(parse_twse_num, return_dtype=pl.Float64).alias("open"),
            pl.col("HighestPrice").map_elements(parse_twse_num, return_dtype=pl.Float64).alias("high"),
            pl.col("LowestPrice").map_elements(parse_twse_num, return_dtype=pl.Float64).alias("low"),
            pl.col("ClosingPrice").map_elements(parse_twse_num, return_dtype=pl.Float64).alias("close"),
            pl.col("TradeVolume").map_elements(parse_twse_num, return_dtype=pl.Float64).cast(pl.Int64, strict=False).alias("volume"),
            pl.col("TradeValue").map_elements(parse_twse_num, return_dtype=pl.Float64).alias("turnover"),
            pl.col("Transaction").map_elements(parse_twse_num, return_dtype=pl.Float64).cast(pl.Int64, strict=False).alias("transactions"),
            pl.col("Change").map_elements(parse_twse_num, return_dtype=pl.Float64).alias("spread"),
        ).filter(pl.col("close").is_not_null())

    # ─────────────────────────────────────────────────────────
    # Endpoint 2: STOCK_DAY — 個股某月日 K (historical)
    # ─────────────────────────────────────────────────────────

    def stock_month(self, stock_id: str, year_month: date) -> pl.DataFrame:
        """個股某月日 K (一次回該月所有交易日)。

        Args:
            stock_id: 證券代號
            year_month: 該月任一天 (內部取 YYYYMM)

        Returns:
            Columns: stock_id, date, open, high, low, close, volume, turnover,
                     transactions, spread, twse_note (拆分標記用)
            空 DataFrame 若 TWSE 回 stat ≠ "OK" 或無資料 (會 log warning 留 trace)
        """
        date_param = year_month.strftime("%Y%m") + "01"
        data = self._get_json(
            f"{self.HISTORICAL_BASE}/STOCK_DAY",
            params={"response": "json", "date": date_param, "stockNo": stock_id},
        )
        stat = data.get("stat", "<no stat field>")
        if stat != "OK":
            # v0.1.1: 留 audit trail (上次 cross_source_audit 撞到的 silent fail)
            logger.warning(
                "twse_stock_month_non_ok",
                stock_id=stock_id,
                year_month=year_month.strftime("%Y%m"),
                stat=stat,
            )
            return pl.DataFrame()
        if not data.get("data"):
            logger.info(
                "twse_stock_month_empty",
                stock_id=stock_id,
                year_month=year_month.strftime("%Y%m"),
            )
            return pl.DataFrame()

        # data["data"] 是 list of list；對應 fields ["日期","成交股數","成交金額","開盤價","最高價","最低價","收盤價","漲跌價差","成交筆數","註記"]
        records: list[dict[str, Any]] = []
        for row in data["data"]:
            if len(row) < 9:
                continue
            d = parse_roc_slashed(row[0])
            if d is None:
                continue
            records.append({
                "stock_id": stock_id,
                "date": d,
                "volume": parse_twse_num(row[1]),
                "turnover": parse_twse_num(row[2]),
                "open": parse_twse_num(row[3]),
                "high": parse_twse_num(row[4]),
                "low": parse_twse_num(row[5]),
                "close": parse_twse_num(row[6]),
                "spread": parse_twse_num(row[7]),
                "transactions": parse_twse_num(row[8]),
                "twse_note": row[9] if len(row) > 9 else "",
            })

        if not records:
            return pl.DataFrame()

        df = pl.DataFrame(records)
        return df.unique(subset=["stock_id", "date"]).sort("date")

    # ─────────────────────────────────────────────────────────
    # Endpoint 3: MI_INDEX — 50+ 指數 (今日，含產業類股)
    # ─────────────────────────────────────────────────────────

    def indices_today(self) -> pl.DataFrame:
        """50+ 指數今日收盤 (含 30+ 產業類股 + 大盤)。

        Returns:
            Columns: date, index_name, close, change_pct
            change_pct 已合併「漲跌方向」+「漲跌百分比」為含正負號的單一欄位
        """
        rows = self._get_json(f"{self.OPENAPI_BASE}/exchangeReport/MI_INDEX")
        if not rows:
            return pl.DataFrame()

        df = pl.from_dicts(rows)

        # 漲跌欄位是 "+" / "-" / "" ；漲跌百分比可能是 "--" (平盤)
        df = df.with_columns(
            pl.col("日期").map_elements(parse_roc_compact, return_dtype=pl.Date).alias("date"),
            pl.col("指數").alias("index_name"),
            pl.col("收盤指數").map_elements(parse_twse_num, return_dtype=pl.Float64).alias("close"),
            pl.col("漲跌百分比").map_elements(parse_twse_num, return_dtype=pl.Float64).alias("abs_pct"),
            pl.col("漲跌").alias("direction"),
        )
        # 合併方向 + 絕對百分比
        df = df.with_columns(
            pl.when(pl.col("direction") == "-")
            .then(-pl.col("abs_pct"))
            .otherwise(pl.col("abs_pct"))
            .alias("change_pct"),
        )

        return df.select(["date", "index_name", "close", "change_pct"]).filter(
            pl.col("close").is_not_null()
        )

    # ─────────────────────────────────────────────────────────
    # Endpoint 4: MI_5MINS_HIST — TAIEX 過去 ~10 日 OHLC
    # ─────────────────────────────────────────────────────────

    def taiex_recent(self) -> pl.DataFrame:
        """TAIEX 加權指數過去 ~10 個交易日 OHLC。

        Returns:
            Columns: stock_id (="TAIEX"), date, open, high, low, close
            volume/turnover 不適用（指數無成交量）→ None
        """
        rows = self._get_json(f"{self.OPENAPI_BASE}/indicesReport/MI_5MINS_HIST")
        if not rows:
            return pl.DataFrame()

        df = pl.from_dicts(rows)

        return df.select(
            pl.lit("TAIEX").alias("stock_id"),
            pl.col("Date").map_elements(parse_roc_compact, return_dtype=pl.Date).alias("date"),
            pl.col("OpeningIndex").map_elements(parse_twse_num, return_dtype=pl.Float64).alias("open"),
            pl.col("HighestIndex").map_elements(parse_twse_num, return_dtype=pl.Float64).alias("high"),
            pl.col("LowestIndex").map_elements(parse_twse_num, return_dtype=pl.Float64).alias("low"),
            pl.col("ClosingIndex").map_elements(parse_twse_num, return_dtype=pl.Float64).alias("close"),
        ).filter(pl.col("close").is_not_null()).sort("date")

    # ─────────────────────────────────────────────────────────
    # Endpoint 5: t187ap03_L — 上市公司基本資訊
    # ─────────────────────────────────────────────────────────

    def company_info(self) -> pl.DataFrame:
        """t187ap03_L → 全市場上市公司基本資訊 (~1000+ 家)。

        中文 keys → 英文欄位標準化：
        - 公司代號 → stock_id
        - 公司名稱 → company_name
        - 公司簡稱 → short_name
        - 產業別 → industry_code (數字代碼，如 "24"=半導體)
        - 上市日期 → listing_date (西元 YYYYMMDD 格式)
        - 出表日期 → report_date (民國年連月日格式)
        - 實收資本額 → paid_in_capital
        - 已發行普通股數或TDR原股發行股數 → issued_shares

        Returns:
            Columns: stock_id, company_name, short_name, industry_code,
                     listing_date, report_date, paid_in_capital, issued_shares
        """
        rows = self._get_json(f"{self.OPENAPI_BASE}/opendata/t187ap03_L")
        if not rows:
            return pl.DataFrame()

        df = pl.from_dicts(rows)
        return df.select(
            pl.col("公司代號").alias("stock_id"),
            pl.col("公司名稱").alias("company_name"),
            pl.col("公司簡稱").alias("short_name"),
            pl.col("產業別").alias("industry_code"),
            pl.col("上市日期").map_elements(
                _parse_western_compact, return_dtype=pl.Date
            ).alias("listing_date"),
            pl.col("出表日期").map_elements(
                parse_roc_compact, return_dtype=pl.Date
            ).alias("report_date"),
            pl.col("實收資本額").map_elements(
                parse_twse_num, return_dtype=pl.Float64
            ).cast(pl.Int64, strict=False).alias("paid_in_capital"),
            pl.col("已發行普通股數或TDR原股發行股數").map_elements(
                parse_twse_num, return_dtype=pl.Float64
            ).cast(pl.Int64, strict=False).alias("issued_shares"),
        )

    # ─────────────────────────────────────────────────────────
    # Endpoint 6: TWT48U — 除權除息預告表 (未來事件)
    # ─────────────────────────────────────────────────────────

    def dividend_forecast(self) -> pl.DataFrame:
        """TWT48U → 除權除息預告表 (尚未發生的除權息事件)。

        Schema (fields):
          除權除息日期 / 股票代號 / 名稱 / 除權息 / 無償配股率 /
          現金增資配股率 / 現金增資認購價 / 現金股利 / ...

        Returns:
            Columns: ex_date, stock_id, name, ex_kind,
                     stock_div_ratio (無償配股率, 配 X 股),
                     cash_increase_ratio (現金增資配股率),
                     cash_increase_price (現金增資認購價),
                     cash_dividend (現金股利)
        """
        data = self._get_json(
            f"{self.HISTORICAL_BASE}/TWT48U",
            params={"response": "json"},
        )
        if data.get("stat") != "OK" or not data.get("data"):
            logger.warning(
                "twse_dividend_forecast_non_ok",
                stat=data.get("stat", "<missing>"),
            )
            return pl.DataFrame()

        records: list[dict[str, Any]] = []
        for row in data["data"]:
            if len(row) < 8:
                continue
            records.append({
                "ex_date": parse_roc_slashed(row[0]),
                "stock_id": str(row[1]).strip(),
                "name": str(row[2]).strip() if row[2] else None,
                "ex_kind": str(row[3]).strip() if row[3] else None,  # 權/息/權息
                "stock_div_ratio": parse_twse_num(row[4]),
                "cash_increase_ratio": parse_twse_num(row[5]),
                "cash_increase_price": parse_twse_num(row[6]),
                "cash_dividend": parse_twse_num(row[7]),
            })

        if not records:
            return pl.DataFrame()
        return (
            pl.DataFrame(records)
            .filter(pl.col("ex_date").is_not_null())
            .sort(["ex_date", "stock_id"])
        )

    # ─────────────────────────────────────────────────────────
    # Convenience: stock_range — 跨多月歷史抓取 (慢)
    # ─────────────────────────────────────────────────────────

    def stock_range(
        self, stock_id: str, start: date, end: date
    ) -> pl.DataFrame:
        """個股某區間日 K (內部用 month loop 呼叫 stock_month)。

        ⚠ 慢：每個月一個 HTTP call + 1 秒 rate limit。
        5 年 = 60 個月 ≈ 60+ 秒/股。只用於 historical spot-check，不要 bulk backfill。
        """
        if start > end:
            return pl.DataFrame()

        dfs: list[pl.DataFrame] = []
        # iterate by month
        cursor = date(start.year, start.month, 1)
        while cursor <= end:
            try:
                df_m = self.stock_month(stock_id, cursor)
                if not df_m.is_empty():
                    dfs.append(df_m)
            except TwseError as e:
                logger.warning("twse_stock_month_failed",
                               stock_id=stock_id, year_month=cursor.strftime("%Y%m"),
                               error=str(e))
            # next month
            if cursor.month == 12:
                cursor = date(cursor.year + 1, 1, 1)
            else:
                cursor = date(cursor.year, cursor.month + 1, 1)

        if not dfs:
            return pl.DataFrame()

        return (
            pl.concat(dfs)
            .filter((pl.col("date") >= start) & (pl.col("date") <= end))
            .unique(subset=["stock_id", "date"])
            .sort("date")
        )
