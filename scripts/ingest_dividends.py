#!/usr/bin/env python3
# scripts/ingest_dividends.py
"""填 corporate_actions 表 — 歷史除權息 (FinMind) + 未來預告 (TWSE TWT48U)。

兩階段：

Phase 1 (歷史)：FinMind TaiwanStockDividendResult
  - 每個 universe symbol 抓 5 年歷史除權息
  - confirmed=true
  - 提供 adjustment_factor (after / before)
  - v0.1.10 features/dividend_adjustment.py 用這個算 adjusted close

Phase 2 (預告)：TWSE TWT48U
  - 一次抓全市場「尚未發生」的除權息事件
  - confirmed=false
  - 主要用於 trading-time 警告 (你今天買的股，明天會除息)

策略：
- DELETE + INSERT (對 confirmed=true 鎖 stock_id 範圍；對 confirmed=false 全量重寫)
- Phase 1 對 universe 跑，Phase 2 全市場一次抓

使用：
  uv run python scripts/ingest_dividends.py                    # 兩個 phase 都跑
  uv run python scripts/ingest_dividends.py --historical-only   # 只跑 phase 1
  uv run python scripts/ingest_dividends.py --forecast-only     # 只跑 phase 2
  uv run python scripts/ingest_dividends.py --symbols 2330,0050 # 限定 universe

Version: v0.1.0 (2026-05-16)
Changelog:
  v0.1.0 (2026-05-16): Initial — FinMind historical + TWSE forecast
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timedelta
from typing import Any

import polars as pl

from config import load_universe
from data.database import connect, init_schema
from data.sources.finmind_client import FinMindClient
from data.sources.twse_client import TwseClient
from utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_HISTORY_DAYS = 365 * 5


# ─────────────────────────────────────────────────────────────
# Universe
# ─────────────────────────────────────────────────────────────


def get_universe_symbols() -> list[str]:
    """從 universe.yaml 取 symbols (不加 TAIEX, TAIEX 沒有 dividend)。"""
    universe = load_universe()
    symbols: set[str] = set()
    for _, u_def in universe.get("universes", {}).items():
        for sym in u_def.get("include_specific", []):
            symbols.add(str(sym))
    return sorted(symbols)


# ─────────────────────────────────────────────────────────────
# Phase 1: Historical dividends from FinMind
# ─────────────────────────────────────────────────────────────


def ingest_historical(symbols: list[str], years_back: int = 5) -> dict[str, Any]:
    """跑 FinMind TaiwanStockDividendResult，寫 confirmed=true 進 corporate_actions。"""
    print(f"\n{'='*60}\nPhase 1: Historical dividends (FinMind, last {years_back}yr)")
    print(f"{'='*60}")
    print(f"Symbols: {len(symbols)}")

    end = date.today()
    start = end - timedelta(days=years_back * 365)

    all_records: list[dict[str, Any]] = []
    failed: list[str] = []
    t0 = time.time()

    with FinMindClient() as fm:
        for i, sid in enumerate(symbols, 1):
            try:
                df = fm.dividend_result(sid, start, end)
                if df.is_empty():
                    print(f"  [{i:2d}/{len(symbols)}] ○ {sid:8s} (no dividends in range)")
                    continue
                n = df.height
                # 加 ingestion metadata
                df_dict = df.with_columns(
                    confirmed=pl.lit(True),
                    source=pl.lit("finmind_dividend_result"),
                    notes=pl.lit(None).cast(pl.Utf8),
                    cash_dividend=pl.lit(None).cast(pl.Float64),  # FinMind 不分現金/股票，混在一起
                    stock_div_ratio=pl.lit(None).cast(pl.Float64),
                ).to_dicts()
                all_records.extend(df_dict)
                print(f"  [{i:2d}/{len(symbols)}] ✓ {sid:8s} {n} events")
            except Exception as e:
                logger.exception("dividend_fetch_failed", stock_id=sid)
                failed.append(sid)
                print(f"  [{i:2d}/{len(symbols)}] ✗ {sid:8s} ERROR: {e}")

    elapsed = time.time() - t0

    # 寫入 (對涉及的 symbol 範圍先 DELETE)
    if all_records:
        # 清 confirmed=true + 在 symbol 範圍內的舊資料
        with connect() as conn:
            placeholders = ",".join(["?"] * len(symbols))
            conn.execute(
                f"""
                DELETE FROM corporate_actions
                WHERE confirmed = TRUE AND stock_id IN ({placeholders})
                """,
                symbols,
            )

        # 寫新資料
        ingest_at = datetime.now()
        df_write = pl.DataFrame(all_records).with_columns(
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

    print(f"\nPhase 1 complete: {len(all_records)} events from {len(symbols) - len(failed)}/{len(symbols)} symbols ({elapsed:.1f}s)")
    if failed:
        print(f"  Failed: {failed}")

    return {
        "phase": "historical",
        "symbols_total": len(symbols),
        "symbols_ok": len(symbols) - len(failed),
        "events_written": len(all_records),
        "failed_symbols": failed,
        "elapsed_seconds": elapsed,
    }


# ─────────────────────────────────────────────────────────────
# Phase 2: Forecast from TWSE TWT48U
# ─────────────────────────────────────────────────────────────


def ingest_forecast() -> dict[str, Any]:
    """跑 TWSE TWT48U，寫 confirmed=false 進 corporate_actions。"""
    print(f"\n{'='*60}\nPhase 2: Forecast dividends (TWSE TWT48U)")
    print(f"{'='*60}")

    t0 = time.time()
    with TwseClient(sleep_between_calls=1.0) as twse:
        df = twse.dividend_forecast()
    elapsed = time.time() - t0

    if df.is_empty():
        print("(no upcoming dividends in TWSE forecast)")
        return {"phase": "forecast", "events_written": 0, "elapsed_seconds": elapsed}

    n = df.height
    print(f"TWSE returned {n} upcoming ex-dividend events")

    # 全量重寫 confirmed=false (預告會隨時更新)
    ingest_at = datetime.now()
    df_write = df.rename({"ex_date": "date"}).with_columns(
        kind=pl.col("ex_kind"),
        before_price=pl.lit(None).cast(pl.Float64),
        after_price=pl.lit(None).cast(pl.Float64),
        adjustment_factor=pl.lit(None).cast(pl.Float64),
        confirmed=pl.lit(False),
        source=pl.lit("twse_twt48u"),
        notes=pl.col("name"),
        ingested_at=ingest_at,
    ).select([
        "date", "stock_id", "kind", "before_price", "after_price", "adjustment_factor",
        "cash_dividend", "stock_div_ratio", "confirmed", "source", "notes", "ingested_at",
    ])

    with connect() as conn:
        # 清舊 forecast
        conn.execute("DELETE FROM corporate_actions WHERE confirmed = FALSE")
        # 寫新 forecast
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

    # 摘要：近 7 天內的預告
    soon = date.today() + timedelta(days=7)
    with connect(read_only=True) as conn:
        upcoming = conn.execute(
            """
            SELECT date, stock_id, kind, cash_dividend, notes
            FROM corporate_actions
            WHERE confirmed = FALSE AND date BETWEEN ? AND ?
            ORDER BY date, stock_id
            LIMIT 10
            """,
            [date.today(), soon],
        ).fetchall()

    if upcoming:
        print("\nUpcoming ex-dividend in next 7 days (preview):")
        for r in upcoming:
            cash = f"${r[3]}" if r[3] else "—"
            print(f"  {r[0]} {r[1]:8s} {r[2]}  cash={cash}  {r[4] or ''}")

    print(f"\nPhase 2 complete: {n} forecast events ({elapsed:.1f}s)")
    return {"phase": "forecast", "events_written": n, "elapsed_seconds": elapsed}


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingest dividend events into corporate_actions"
    )
    parser.add_argument("--historical-only", action="store_true",
                        help="只跑 FinMind 歷史 (跳過 TWSE forecast)")
    parser.add_argument("--forecast-only", action="store_true",
                        help="只跑 TWSE forecast (跳過 FinMind 歷史)")
    parser.add_argument("--symbols", type=str,
                        help="逗號分隔，覆蓋 universe.yaml")
    parser.add_argument("--years-back", type=int, default=5,
                        help="歷史回填年數 (預設 5)")
    args = parser.parse_args()

    if args.historical_only and args.forecast_only:
        print("❌ --historical-only and --forecast-only mutually exclusive")
        return 2

    init_schema()
    print(f"Helios ingest_dividends — {datetime.now().isoformat(timespec='seconds')}")

    summary: list[dict[str, Any]] = []

    if not args.forecast_only:
        if args.symbols:
            symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
        else:
            symbols = get_universe_symbols()
        if not symbols:
            print("❌ universe.yaml 沒任何 symbol")
            return 1
        summary.append(ingest_historical(symbols, years_back=args.years_back))

    if not args.historical_only:
        summary.append(ingest_forecast())

    # 全表摘要
    print(f"\n{'='*60}\nOverall corporate_actions summary\n{'='*60}")
    with connect(read_only=True) as conn:
        confirmed = conn.execute(
            "SELECT COUNT(*) FROM corporate_actions WHERE confirmed = TRUE"
        ).fetchone()[0]
        forecast = conn.execute(
            "SELECT COUNT(*) FROM corporate_actions WHERE confirmed = FALSE"
        ).fetchone()[0]
        n_symbols = conn.execute(
            "SELECT COUNT(DISTINCT stock_id) FROM corporate_actions"
        ).fetchone()[0]
    print(f"  Confirmed (historical): {confirmed}")
    print(f"  Forecast (upcoming):    {forecast}")
    print(f"  Distinct symbols:       {n_symbols}")
    print()
    print("💡 v0.1.10 features/dividend_adjustment.py 將用此表算 adjusted close")

    return 0


if __name__ == "__main__":
    sys.exit(main())
