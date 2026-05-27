#!/usr/bin/env python3
# scripts/shioaji_download_daily.py
"""下載日 K 資料到 DuckDB — Shioaji daily_quotes 版本 — v0.1.0.

取代 download_daily.py 的 FinMind raw OHLCV 下載。
設計與 download_daily.py 完全相同（watermark、incremental、schema）。

驗證記錄 (2026-05-26):
  - daily_quotes(date) 回傳全市場 1975 筆，一次 call 完成
  - Shioaji close == FinMind raw close，5/5 symbols on 2026-05-25 ✅
  - snapshots() ts = 13:30 CST，收盤後立刻可取 ✅
  - 資料為未還原 raw price，與 FinMind 語意一致 ✅

使用時機：
  - 每個交易日 13:45（收盤後 15 分鐘）
  - 取代 16:00 的 download_daily.py

差異：
  - 不需要 FinMind token
  - 需要 Shioaji API key + CA（simulation=True 即可）
  - 一次取全市場，不逐 symbol 迴圈（速度快很多）
  - 只抓「今天」，歷史補抓仍需 download_daily.py

使用：
  uv run python scripts/shioaji_download_daily.py
  uv run python scripts/shioaji_download_daily.py --date 2026-05-23
  uv run python scripts/shioaji_download_daily.py --dry-run

Remaining verification needed (see backlog #21):
  - Ex-dividend date: Shioaji raw close on ex-date == FinMind raw close
  - OTC symbols: confirm daily_quotes includes OTC (not TSE only)

Version: v0.1.0 (2026-05-26)
Changelog:
  v0.1.0 (2026-05-26): Initial — replaces FinMind daily OHLCV download.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime

import polars as pl

from data.database import connect, init_schema
from market.trading_calendar import is_trading_day, previous_trading_day
from utils.logger import get_logger

logger = get_logger(__name__)

DATASET = "daily_price"

# daily_price 表的標準欄位順序（與 download_daily.py 對齊）
_PRICE_COLS = [
    "stock_id", "date",
    "open", "high", "low", "close", "volume",
]


# ── Watermark helpers (identical to download_daily.py) ────────────────

def get_watermark(stock_id: str) -> date | None:
    with connect(read_only=True) as conn:
        row = conn.execute(
            "SELECT last_date FROM ingest_watermark WHERE stock_id = ? AND dataset = ?",
            [stock_id, DATASET],
        ).fetchone()
    return row[0] if row else None


def insert_daily_prices(df: pl.DataFrame) -> int:
    """把 daily_price DataFrame 寫入 DuckDB（DELETE + INSERT + watermark）。

    P0-2: watermark update is transactionally coupled with data write.
    All three operations (DELETE, INSERT, watermark) happen in a single
    connection transaction so there is no split-brain between data state
    and watermark state on partial failure.
    """
    if df.is_empty():
        return 0

    stock_id = df["stock_id"][0]
    min_date = df["date"].min()
    max_date = df["date"].max()

    with connect() as conn:
        conn.execute("BEGIN")
        try:
            conn.execute(
                "DELETE FROM daily_price WHERE stock_id = ? AND date BETWEEN ? AND ?",
                [stock_id, min_date, max_date],
            )
            conn.register("df_in", df.select(_PRICE_COLS).to_arrow())
            conn.execute(
            "INSERT INTO daily_price"
            " (stock_id, date, open, high, low, close, volume,"
            "  turnover, transactions, spread)"
            " SELECT stock_id, date, open, high, low, close, volume,"
            "        NULL, NULL, NULL FROM df_in"
        )
            conn.unregister("df_in")
            # Watermark update inside the same transaction
            conn.execute(
                "DELETE FROM ingest_watermark WHERE stock_id = ? AND dataset = ?",
                [stock_id, DATASET],
            )
            conn.execute(
                "INSERT INTO ingest_watermark (stock_id, dataset, last_date) "
                "VALUES (?, ?, ?)",
                [stock_id, DATASET, max_date],
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    return len(df)


# ── Shioaji data fetch ─────────────────────────────────────────────────

def fetch_daily_quotes(target_date: date) -> pl.DataFrame:
    """Fetch full-market daily quotes from Shioaji for target_date.

    Returns Polars DataFrame with columns matching daily_price schema.
    Empty DataFrame if no data available (e.g. non-trading day or
    data not yet published).

    Uses daily_quotes() — one API call for all ~1975 stocks.
    fetch_contract=False to avoid the 30-second contract download.

    [ASSUMED]: simulation=True daily_quotes returns identical data to
    live. Verified for 5/5 symbols on 2026-05-25 (spot check only).
    Full verification required before using as sole production source.
    See scripts/verify_shioaji_vs_finmind.py (backlog #21).
    """
    try:
        import shioaji as sj
    except ImportError:
        logger.error("shioaji_not_installed",
                     hint="uv add shioaji or pip install shioaji")
        raise

    from config.settings import get_settings
    cfg = get_settings()

    # P0-1: simulation semantics are not fully verified
    # daily_quotes in simulation may diverge from live market data
    # on ex-dividend dates, OTC symbols, halted stocks, etc.
    logger.warning(
        "simulation_data_semantics_unverified",
        risk="daily_quotes in simulation=True mode — verified for 5 TSE "
             "symbols only. OTC, ETF, ex-dividend, halt semantics unverified. "
             "Do not use as sole production truth source until "
             "verify_shioaji_vs_finmind.py validation is complete.",
    )

    logger.info("shioaji_login_start", simulation=True)
    api = sj.Shioaji(simulation=True)
    api.login(
        api_key=cfg.shioaji_api_key.get_secret_value(),
        secret_key=cfg.shioaji_secret_key.get_secret_value(),
        fetch_contract=False,
    )

    # P1-1: bounded retry instead of fixed sleep
    # daily_quotes needs login session to be ready; poll with backoff
    _max_attempts = 5
    _base_sleep = 1.0
    dq = None
    for attempt in range(1, _max_attempts + 1):
        try:
            dq = api.daily_quotes(date=target_date)
            break
        except Exception as exc:
            if attempt == _max_attempts:
                logger.error("shioaji_daily_quotes_failed",
                             attempts=_max_attempts, error=str(exc))
                api.logout()
                raise
            sleep_sec = _base_sleep * (2 ** (attempt - 1))
            logger.warning("shioaji_daily_quotes_retry",
                           attempt=attempt, sleep_sec=sleep_sec, error=str(exc))
            time.sleep(sleep_sec)

    try:
        import pandas as pd
        df_pd = pd.DataFrame({**dq})

        if df_pd.empty:
            logger.warning(
                "shioaji_daily_quotes_empty",
                date=str(target_date),
                hint="Data may not be published yet (try after 14:30 TST) "
                     "or this is a non-trading day.",
            )
            return pl.DataFrame()

        # P1-5: partial-day sanity guard
        # Full TWSE market is ~1700+ symbols; significantly fewer suggests
        # incomplete data (API stale, exchange delay, half-day trading).
        _MIN_EXPECTED_ROWS = 1500
        if len(df_pd) < _MIN_EXPECTED_ROWS:
            logger.warning(
                "shioaji_daily_quotes_partial",
                rows=len(df_pd),
                min_expected=_MIN_EXPECTED_ROWS,
                date=str(target_date),
                risk="Ingestion aborted — row count below threshold. "
                     "Possible exchange delay or half-day trading.",
            )
            return pl.DataFrame()

        logger.info(
            "shioaji_daily_quotes_received",
            date=str(target_date),
            rows=len(df_pd),
            fetch_contract=False,
            otc_note="fetch_contract=False — OTC symbols may have missing/null "
                     "Volume or Close in some Shioaji versions. Verify OTC "
                     "coverage in verify_shioaji_vs_finmind.py (backlog #21). "
                     "If OTC data is incomplete, set fetch_contract=True "
                     "(adds ~30s startup latency).",
        )

        # Normalise to daily_price schema
        df = pl.from_pandas(df_pd).select([
            pl.col("Code").alias("stock_id"),
            pl.lit(target_date).alias("date"),
            pl.col("Open").cast(pl.Float64).alias("open"),
            pl.col("High").cast(pl.Float64).alias("high"),
            pl.col("Low").cast(pl.Float64).alias("low"),
            pl.col("Close").cast(pl.Float64).alias("close"),
            pl.col("Volume").cast(pl.Int64).alias("volume"),
        ]).filter(
            pl.col("close").is_not_null() & (pl.col("close") > 0)
        )

        return df

    finally:
        api.logout()
        logger.info("shioaji_logout")


# ── Universe ──────────────────────────────────────────────────────────

def get_universe_symbols() -> list[str]:
    """Return all stock_ids currently tracked in daily_price (excl. TAIEX).

    TAIEX is excluded because Shioaji daily_quotes does not include index
    data. TAIEX ingestion remains via download_daily.py (FinMind).
    """
    with connect(read_only=True) as conn:
        rows = conn.execute(
            "SELECT DISTINCT stock_id FROM daily_price "
            "WHERE stock_id != 'TAIEX' ORDER BY stock_id"
        ).fetchall()
    return [r[0] for r in rows]


# ── Main ──────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download daily OHLCV from Shioaji daily_quotes"
    )
    parser.add_argument(
        "--date", type=str, default=None,
        help="Target date (YYYY-MM-DD). Default: today if trading day, "
             "else previous_trading_day.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Fetch data but do not write to DB.",
    )
    args = parser.parse_args()

    init_schema()

    # Resolve target date
    if args.date:
        target = date.fromisoformat(args.date)
    else:
        today = date.today()
        if is_trading_day(today):
            target = today
        else:
            target = previous_trading_day(today)
            if target is None:
                print("ERROR: cannot determine target trading day")
                return 1

    print(
        f"Helios shioaji_download_daily — "
        f"{datetime.now().isoformat(timespec='seconds')}  "
        f"target={target}"
    )

    if not is_trading_day(target):
        print(f"WARNING: {target} is not a trading day — skipping")
        logger.warning("shioaji_download_skipped_non_trading_day",
                       date=str(target))
        return 0

    # Fetch
    df_all = fetch_daily_quotes(target)

    if df_all.is_empty():
        print(f"No data returned for {target}. "
              f"If market is open, try again after 14:30 TST.")
        return 1

    if args.dry_run:
        print(f"[DRY RUN] Would write {len(df_all)} rows for {target}")
        print(df_all.head(5))
        return 0

    # Filter to universe (only update symbols we already track)
    # New symbols must be added via download_daily.py --full first
    universe = set(get_universe_symbols())
    df_universe = df_all.filter(pl.col("stock_id").is_in(universe))
    df_new = df_all.filter(~pl.col("stock_id").is_in(universe))

    if len(df_new) > 0:
        logger.info(
            "shioaji_download_new_symbols_skipped",
            count=len(df_new),
            hint="New symbols must be initialised via download_daily.py --full",
        )

    print(f"  Writing {len(df_universe)} symbols for {target} ...")

    # Write per-symbol (DELETE + INSERT + watermark)
    n_ok = n_skip = n_err = 0
    for stock_id, group in df_universe.group_by("stock_id"):
        sid = stock_id[0] if isinstance(stock_id, tuple) else stock_id
        try:
            # Skip if watermark already at target date
            wm = get_watermark(sid)
            if wm is not None and wm >= target:
                n_skip += 1
                continue

            insert_daily_prices(group)  # watermark updated inside transaction
            n_ok += 1
        except Exception:
            logger.exception("shioaji_download_write_failed", stock_id=sid)
            n_err += 1

    print(f"\n  ok={n_ok}  skipped={n_skip}  errors={n_err}")
    logger.info(
        "shioaji_download_complete",
        date=str(target),
        n_ok=n_ok,
        n_skip=n_skip,
        n_err=n_err,
    )

    if n_err > 0:
        print(f"WARNING: {n_err} symbols failed — check logs")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
