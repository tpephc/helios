#!/usr/bin/env python3
# scripts/backfill_taiex.py
"""Backfill TAIEX daily_price from Shioaji index kbars.

Fetches minute-level kbars for TAIEX (TSE001), aggregates to daily
OHLCV, and writes to daily_price table with stock_id='TAIEX'.

Also exports `fetch_taiex_daily()` for use by shioaji_download_daily.py.

Usage:
  uv run python scripts/backfill_taiex.py
  uv run python scripts/backfill_taiex.py --start 2026-05-26 --end 2026-05-29
  uv run python scripts/backfill_taiex.py --dry-run
"""
from __future__ import annotations

import argparse
import sys
from datetime import date as date_type, datetime
from zoneinfo import ZoneInfo

import polars as pl

from data.database import connect, init_schema
from utils.logger import get_logger

logger = get_logger(__name__)

TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def fetch_taiex_daily(
    api,
    start: str,
    end: str,
) -> pl.DataFrame:
    """Fetch TAIEX kbars and aggregate to daily OHLCV.

    Args:
        api: logged-in Shioaji API instance
        start: start date 'YYYY-MM-DD'
        end: end date 'YYYY-MM-DD'

    Returns:
        Polars DataFrame with columns:
          stock_id, date, open, high, low, close, volume
        One row per trading day.
    """
    contract = api.Contracts.Indexs.TSE.TSE001
    kbars = api.kbars(contract, start=start, end=end)

    if not kbars.ts:
        logger.warning("taiex_kbars_empty", start=start, end=end)
        return pl.DataFrame()

    # Build DataFrame from kbars
    df = pl.DataFrame({
        "ts": kbars.ts,
        "open": kbars.Open,
        "high": kbars.High,
        "low": kbars.Low,
        "close": kbars.Close,
        "volume": kbars.Volume,
    })

    # Convert nanosecond timestamps to Taipei date
    df = df.with_columns(
        pl.col("ts")
        .cast(pl.Int64)
        .truediv(1_000_000_000)
        .cast(pl.Int64)
        .map_elements(
            lambda s: datetime.fromtimestamp(s, tz=TAIPEI_TZ).date(),
            return_dtype=pl.Date,
        )
        .alias("date")
    )

    # Filter out zero-volume bars (closing auction artifacts)
    df = df.filter(pl.col("volume") > 0)

    if df.is_empty():
        return pl.DataFrame()

    # Aggregate to daily OHLCV
    daily = df.group_by("date").agg([
        pl.col("open").first().alias("open"),
        pl.col("high").max().alias("high"),
        pl.col("low").min().alias("low"),
        pl.col("close").last().alias("close"),
        pl.col("volume").sum().alias("volume"),
    ]).sort("date")

    # Add stock_id column
    daily = daily.with_columns(pl.lit("TAIEX").alias("stock_id"))

    return daily.select(["stock_id", "date", "open", "high", "low", "close", "volume"])


def write_taiex_daily(df: pl.DataFrame) -> int:
    """Write TAIEX daily rows to daily_price (upsert by date)."""
    if df.is_empty():
        return 0

    written = 0
    with connect() as conn:
        for row in df.iter_rows(named=True):
            # Delete existing row for this date (if any)
            conn.execute(
                "DELETE FROM daily_price WHERE stock_id = 'TAIEX' AND date = ?",
                [row["date"]],
            )
            conn.execute(
                """
                INSERT INTO daily_price (stock_id, date, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [row["stock_id"], row["date"], row["open"], row["high"],
                 row["low"], row["close"], row["volume"]],
            )
            written += 1

    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill TAIEX from Shioaji kbars")
    parser.add_argument("--start", type=str, default=None,
                        help="Start date (default: day after latest TAIEX in DB)")
    parser.add_argument("--end", type=str, default=None,
                        help="End date (default: today)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    init_schema()

    # Determine date range
    if args.start:
        start = args.start
    else:
        with connect(read_only=True) as conn:
            row = conn.execute(
                "SELECT MAX(date) FROM daily_price WHERE stock_id = 'TAIEX'"
            ).fetchone()
        if row and row[0]:
            from datetime import timedelta
            last_date = row[0] if isinstance(row[0], date_type) else date_type.fromisoformat(str(row[0]))
            start = str(last_date + timedelta(days=1))
        else:
            start = "2021-01-01"

    end = args.end or str(date_type.today())

    print(f"TAIEX backfill: {start} → {end}")

    # Login
    from config.settings import get_settings
    import shioaji as sj

    cfg = get_settings()
    api = sj.Shioaji(simulation=True)
    api.login(
        api_key=cfg.shioaji_api_key.get_secret_value(),
        secret_key=cfg.shioaji_secret_key.get_secret_value(),
        fetch_contract=True,
    )

    try:
        df = fetch_taiex_daily(api, start, end)

        if df.is_empty():
            print("No TAIEX data returned for this range.")
            return 0

        print(f"Fetched {df.height} trading days:")
        for row in df.iter_rows(named=True):
            print(f"  {row['date']}  O={row['open']:.2f}  H={row['high']:.2f}  "
                  f"L={row['low']:.2f}  C={row['close']:.2f}  V={row['volume']}")

        if args.dry_run:
            print("(dry-run, not writing)")
            return 0

        n = write_taiex_daily(df)
        print(f"Wrote {n} rows to daily_price")

        # Verify
        with connect(read_only=True) as conn:
            latest = conn.execute(
                "SELECT MAX(date) FROM daily_price WHERE stock_id = 'TAIEX'"
            ).fetchone()
            print(f"TAIEX latest in DB: {latest[0]}")

    finally:
        try:
            api.logout()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
