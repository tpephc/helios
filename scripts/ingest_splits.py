#!/usr/bin/env python3
# scripts/ingest_splits.py
"""偵測 & 抓 stock splits 進 corporate_actions (v0.2.0 自動偵測版).

# v0.1.0 (yfinance) 的失敗教訓 (2026-05-16 驗證):
#   - yfinance 對台股的 .splits 屬性把「無償配股」(stock dividend) 也算 split
#     → 跟 FinMind dividend_result 重複計算 (FinMind after/before 已含股票股利)
#     → 2881 從 0 abnormal 變 1 abnormal (worse)
#   - yfinance 對 0050 真實 1:4 split (2025-06-18) **完全沒抓到**
#   → yfinance 對台股 split 既誤報又漏報

# v0.2.0 改用「raw price 跳水偵測」：
#   - 從 daily_price 算 close[T] / close[T-1]，若 < 0.55 (45%+ 單日跌幅) → 必然是 split
#   - 台股 ±10% 漲跌停 → -10% 永遠不會觸發
#   - 無償配股 factor 通常 0.85-0.95 → 不會被誤抓
#   - ETF 雖無漲跌停但 -45% 級單日跌 = 系統性崩盤 (5 年內無此事件)
#   - factor = 實際 ratio (e.g., 0.2522 for 0050 1:4)，比理論 0.25 更精準對齊實價

# 設計:
#   1. DELETE 舊的 split records (kind='split') — 包括 v0.1.10.1 yfinance 來源
#   2. 對每個 symbol 掃 daily_price，偵測 ratio < SPLIT_THRESHOLD 的日子
#   3. 寫進 corporate_actions, kind='split', source='auto_detected_price_drop'

# Sanity warning: 若偵測到的 split date 同時也是 FinMind dividend date,
# 印 warning (理論上不該發生，台股 split 跟 ex-dividend 是不同事件)

# 使用：
#   uv run python scripts/ingest_splits.py                 # universe symbols
#   uv run python scripts/ingest_splits.py --symbols 0050  # 限定範圍
#   uv run python scripts/ingest_splits.py --threshold 0.60  # 調整偵測閾值

Version: v0.2.0 (2026-05-16)
Changelog:
  v0.2.0 (2026-05-16): 完全改寫 — 從 raw price 自動偵測，丟棄 yfinance source
                       (yfinance 對台股的 .splits 不可靠，見上方註解)
  v0.1.0 (2026-05-16): Initial — yfinance.splits source [DEPRECATED, 對台股不可用]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from typing import Any

import polars as pl

from data.database import connect, init_schema
from utils.logger import get_logger

logger = get_logger(__name__)

# 45%+ 單日跌幅 = 一定是 split (or 重大停牌復牌跳空，極罕見)
SPLIT_THRESHOLD = 0.55


# ─────────────────────────────────────────────────────────────
# Detection
# ─────────────────────────────────────────────────────────────


def detect_splits_from_prices(
    stock_id: str, threshold: float = SPLIT_THRESHOLD
) -> list[dict[str, Any]]:
    """從 daily_price 掃 close[T]/close[T-1] < threshold 的事件.

    Returns:
        list of {date, ratio, prev_close, curr_close}
    """
    with connect(read_only=True) as conn:
        arrow = conn.execute(
            "SELECT date, close FROM daily_price "
            "WHERE stock_id = ? AND close > 0 ORDER BY date",
            [stock_id],
        ).to_arrow_table()
    df = pl.from_arrow(arrow)
    if df.is_empty() or df.height < 2:
        return []

    df = df.with_columns(
        prev_close=pl.col("close").shift(1),
        prev_date=pl.col("date").shift(1),
    )
    df = df.with_columns(
        ratio=(pl.col("close") / pl.col("prev_close")),
    ).filter(pl.col("prev_close").is_not_null())

    splits = df.filter(pl.col("ratio") < threshold)

    return [
        {
            "date": r["date"],
            "ratio": r["ratio"],
            "prev_close": r["prev_close"],
            "curr_close": r["close"],
            "prev_date": r["prev_date"],
        }
        for r in splits.iter_rows(named=True)
    ]


def cross_check_against_dividends(
    stock_id: str, split_date: Any
) -> dict | None:
    """若 split 日期同時也是 dividend 日期，回傳該 dividend 資訊（warning 用）."""
    with connect(read_only=True) as conn:
        row = conn.execute(
            """
            SELECT date, kind, adjustment_factor, source
            FROM corporate_actions
            WHERE stock_id = ? AND date = ? AND kind != 'split'
            """,
            [stock_id, split_date],
        ).fetchone()
    if row is None:
        return None
    return {"date": row[0], "kind": row[1], "factor": row[2], "source": row[3]}


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Auto-detect & ingest stock splits from daily_price (Taiwan-aware)"
    )
    parser.add_argument(
        "--symbols", type=str,
        help="逗號分隔；不給就掃 daily_price 全部 (排除 TAIEX)",
    )
    parser.add_argument(
        "--threshold", type=float, default=SPLIT_THRESHOLD,
        help=f"偵測閾值 (close[T]/close[T-1] < threshold)，預設 {SPLIT_THRESHOLD}",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="只列出偵測結果，不寫 DB",
    )
    args = parser.parse_args()

    init_schema()
    print(f"Helios ingest_splits — {datetime.now().isoformat(timespec='seconds')}")
    print(f"Method: auto-detect from raw price (close[T]/close[T-1] < {args.threshold})")
    print()

    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        with connect(read_only=True) as conn:
            rows = conn.execute(
                "SELECT DISTINCT stock_id FROM daily_price "
                "WHERE stock_id != 'TAIEX' ORDER BY stock_id"
            ).fetchall()
        symbols = [r[0] for r in rows]

    if not symbols:
        print("❌ daily_price 內沒任何 symbol，請先跑 download_daily.py")
        return 1

    # 偵測
    print(f"Scanning {len(symbols)} symbol(s)...")
    all_detections: list[dict[str, Any]] = []
    coincidence_warnings: list[str] = []

    for i, sid in enumerate(symbols, 1):
        events = detect_splits_from_prices(sid, args.threshold)
        if not events:
            print(f"  [{i:2d}/{len(symbols)}] ○ {sid:8s}")
            continue

        for ev in events:
            # Sanity: 跟 dividend 重疊?
            coincidence = cross_check_against_dividends(sid, ev["date"])
            warning_str = ""
            if coincidence:
                warning_str = (
                    f" ⚠ ALSO dividend ({coincidence['kind']}, "
                    f"factor={coincidence['factor']:.5f}) — 雙重事件，請手動 audit"
                )
                coincidence_warnings.append(
                    f"{sid} @ {ev['date']}: both split(ratio={ev['ratio']:.4f}) "
                    f"and {coincidence['kind']}(factor={coincidence['factor']:.5f})"
                )

            print(
                f"  [{i:2d}/{len(symbols)}] ✓ {sid:8s}  "
                f"{ev['date']} ratio={ev['ratio']:.4f} "
                f"({ev['prev_close']:.2f} → {ev['curr_close']:.2f}){warning_str}"
            )
            all_detections.append({
                "date": ev["date"],
                "stock_id": sid,
                "kind": "split",
                "before_price": ev["prev_close"],
                "after_price": ev["curr_close"],
                "adjustment_factor": ev["ratio"],  # ratio < 1, 拿來往下調
                "cash_dividend": None,
                "stock_div_ratio": None,
                "confirmed": True,
                "source": "auto_detected_price_drop",
                "notes": (
                    f"detected_ratio={ev['ratio']:.5f} "
                    f"prev={ev['prev_close']:.2f} curr={ev['curr_close']:.2f}"
                ),
            })

    if not all_detections:
        print("\n(no splits detected across all symbols)")

    # Cleanup 舊 split records (確保 idempotent + 清掉 v0.1.10.1 yfinance 殘留)
    if not args.dry_run:
        with connect() as conn:
            res = conn.execute(
                "SELECT COUNT(*) FROM corporate_actions WHERE kind = 'split'"
            ).fetchone()
            n_old = res[0] if res else 0
            if n_old > 0:
                conn.execute("DELETE FROM corporate_actions WHERE kind = 'split'")
                print(f"\nCleaned {n_old} old split records (including v0.1.10.1 yfinance)")

        # 寫入新偵測結果
        if all_detections:
            ingest_at = datetime.now()
            df_write = pl.DataFrame(all_detections).with_columns(
                ingested_at=ingest_at,
            )
            with connect() as conn:
                conn.register("inp", df_write.to_arrow())
                try:
                    conn.execute("""
                        INSERT INTO corporate_actions
                        (date, stock_id, kind, before_price, after_price, adjustment_factor,
                         cash_dividend, stock_div_ratio, confirmed, source, notes, ingested_at)
                        SELECT date, stock_id, kind, before_price, after_price, adjustment_factor,
                               cash_dividend, stock_div_ratio, confirmed, source, notes, ingested_at
                        FROM inp
                    """)
                finally:
                    conn.unregister("inp")
            print(f"✓ Wrote {len(all_detections)} split event(s)")
    else:
        print("\n(--dry-run: not writing DB)")

    if coincidence_warnings:
        print()
        print("⚠ Coincidence warnings (split 跟 dividend 同日 — 通常是異常):")
        for w in coincidence_warnings:
            print(f"   {w}")

    # 摘要
    if not args.dry_run:
        print(f"\n{'='*60}\ncorporate_actions summary\n{'='*60}")
        with connect(read_only=True) as conn:
            dividends_n = conn.execute(
                "SELECT COUNT(*) FROM corporate_actions WHERE kind != 'split'"
            ).fetchone()[0]
            splits_n = conn.execute(
                "SELECT COUNT(*) FROM corporate_actions WHERE kind = 'split'"
            ).fetchone()[0]
        print(f"  Dividends:  {dividends_n}")
        print(f"  Splits:     {splits_n}")
        print()
        print("💡 下一步:")
        print("   uv run python scripts/build_adjusted_prices.py --force")
        print("   uv run python scripts/validate_adjustments.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())
