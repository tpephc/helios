#!/usr/bin/env python3
# scripts/compute_bullish_features.py
"""Bullish temporal feature computation pipeline — v0.1.0.

Reads from daily_features + daily_price_adj + market_regime,
computes multi-bar bullish accumulation/markup features via
features/bullish_features.py, and writes to the bullish_features table.

Design mirrors compute_bearish_features.py exactly:
  - Standalone: does not depend on compute_features.py
  - Full rewrite per symbol: DELETE + INSERT
  - TAIEX loaded once for all symbols
  - Graceful degradation on insufficient history

Usage:
  uv run python scripts/compute_bullish_features.py
  uv run python scripts/compute_bullish_features.py --symbols 2330,2454
  uv run python scripts/compute_bullish_features.py --symbols 2330

Version: v0.1.0 (2026-05-26)
Changelog:
  v0.1.0 (2026-05-26): Initial — mirrors compute_bearish_features.py
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime

import polars as pl

from data.database import connect
from features.bullish_features import (
    BULLISH_FEATURE_COLUMN_NAMES,
    compute_all_bullish_features,
)
from utils.logger import get_logger

logger = get_logger(__name__)

_MIN_ROWS_FOR_FEATURES = 80

_KEY_COLS = ["stock_id", "date"]
_ALL_OUTPUT_COLS = _KEY_COLS + BULLISH_FEATURE_COLUMN_NAMES + ["computed_at"]

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS bullish_features (
    stock_id    VARCHAR  NOT NULL,
    date        DATE     NOT NULL,
    -- Family 1: Persistence
    above_ma20_streak              INTEGER,
    above_ma50_streak              INTEGER,
    -- Family 2: Reclaim quality
    ma20_reclaim_confirmed         INTEGER,
    ma50_reclaim_confirmed         INTEGER,
    -- Family 3: Accumulation (base formation)
    volume_contraction_days_10d    INTEGER,
    tight_range_days_10d           INTEGER,
    -- Family 4: Breakout quality
    volume_breakout_days_5d        INTEGER,
    failed_breakdown_count_10d     INTEGER,
    -- Family 5: Relative strength (nullable — requires TAIEX)
    beta_60                        DOUBLE,
    beta_adj_rs_20d                DOUBLE,
    beta_adj_rs_60d                DOUBLE,
    -- Family 6: Volatility compression
    atr_compression_ratio          DOUBLE,
    atr_compression_days_10d       INTEGER,
    -- Metadata
    computed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (stock_id, date)
)
"""


def ensure_schema() -> None:
    with connect() as conn:
        conn.execute(_CREATE_TABLE_SQL)
    logger.info("bullish_features_schema_ready")


def get_all_symbols() -> list[str]:
    with connect(read_only=True) as conn:
        rows = conn.execute(
            "SELECT DISTINCT stock_id FROM daily_features ORDER BY stock_id"
        ).fetchall()
    return [r[0] for r in rows]


def load_symbol_data(stock_id: str) -> pl.DataFrame:
    with connect(read_only=True) as conn:
        arrow = conn.execute(
            """
            SELECT f.stock_id, f.date,
                   p.adj_close,
                   f.sma_20, f.sma_50, f.sma_200,
                   f.rsi_14, f.roc_20,
                   f.atr_14,
                   f.rel_volume_20
            FROM   daily_features f
            JOIN   daily_price_adj p
                   ON f.stock_id = p.stock_id AND f.date = p.date
            WHERE  f.stock_id = ?
              AND  f.sma_20   IS NOT NULL
            ORDER BY f.date
            """,
            [stock_id],
        ).to_arrow_table()
    return pl.from_arrow(arrow)


def load_taiex_series() -> pl.DataFrame:
    with connect(read_only=True) as conn:
        arrow = conn.execute(
            """
            SELECT date, taiex_close
            FROM   market_regime
            WHERE  taiex_close IS NOT NULL
            ORDER BY date
            """
        ).to_arrow_table()
    df = pl.from_arrow(arrow)
    if df.is_empty():
        logger.warning("taiex_series_empty",
                       hint="Run compute_features.py --regime-only first")
    return df


def write_bullish_features(
    stock_id: str,
    df: pl.DataFrame,
    computed_at: datetime,
) -> int:
    df_out = df.with_columns(pl.lit(computed_at).alias("computed_at"))

    for col_name in _ALL_OUTPUT_COLS:
        if col_name not in df_out.columns:
            df_out = df_out.with_columns(pl.lit(None).alias(col_name))
    df_out = df_out.select(_ALL_OUTPUT_COLS)

    with connect() as conn:
        conn.execute(
            "DELETE FROM bullish_features WHERE stock_id = ?", [stock_id]
        )
        conn.register("inp", df_out.to_arrow())
        try:
            conn.execute(f"""
                INSERT INTO bullish_features ({','.join(_ALL_OUTPUT_COLS)})
                SELECT {','.join(_ALL_OUTPUT_COLS)} FROM inp
            """)
        finally:
            conn.unregister("inp")

    return df_out.height


def compute_phase_bullish(
    symbols: list[str],
    taiex_df: pl.DataFrame,
    computed_at: datetime,
) -> dict:
    print(f"\n{'=' * 60}")
    print("Bullish temporal feature computation")
    print(f"{'=' * 60}")
    print(f"Symbols:       {len(symbols)}")
    print(f"TAIEX rows:    {taiex_df.height}")
    print(f"Computed at:   {computed_at.isoformat()}")

    n_ok = n_skip = n_err = 0
    t0 = time.time()

    for i, sid in enumerate(symbols, 1):
        try:
            df = load_symbol_data(sid)

            if df.height < _MIN_ROWS_FOR_FEATURES:
                print(
                    f"  [{i:3d}/{len(symbols)}] ○ {sid:8s}"
                    f"  skip (rows={df.height} < {_MIN_ROWS_FOR_FEATURES})"
                )
                n_skip += 1
                continue

            df_feat = compute_all_bullish_features(
                df,
                taiex_df=taiex_df if not taiex_df.is_empty() else None,
            )

            n_written = write_bullish_features(sid, df_feat, computed_at)

            latest = df_feat.tail(1).row(0, named=True)
            a20  = latest.get("above_ma20_streak", "?")
            vb5  = latest.get("volume_breakout_days_5d", "?")
            cmp  = latest.get("atr_compression_ratio")
            cmp_str = f"{cmp:.2f}x" if cmp is not None else "null"

            print(
                f"  [{i:3d}/{len(symbols)}] ✓ {sid:8s}"
                f"  rows={n_written}"
                f"  above_ma20={a20}"
                f"  vbkout5d={vb5}"
                f"  atr_cmp={cmp_str}"
            )
            n_ok += 1

        except Exception:
            logger.exception("bullish_feature_compute_failed", stock_id=sid)
            print(f"  [{i:3d}/{len(symbols)}] ✗ {sid:8s}  ERROR (see log)")
            n_err += 1

    elapsed = time.time() - t0
    return {"n_ok": n_ok, "n_skip": n_skip, "n_err": n_err, "elapsed": elapsed}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute bullish temporal features (Phase 3)"
    )
    parser.add_argument(
        "--symbols", type=str, default=None,
        help="Comma-separated stock_ids (default: all in daily_features)",
    )
    args = parser.parse_args()

    ensure_schema()

    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = get_all_symbols()

    if not symbols:
        print("No symbols found in daily_features. Run compute_features.py first.")
        return 1

    taiex_df = load_taiex_series()
    computed_at = datetime.now()
    result = compute_phase_bullish(symbols, taiex_df, computed_at)

    elapsed = result["elapsed"]
    print(f"\n{'=' * 60}")
    print("Summary")
    print(f"{'=' * 60}")
    print(f"  ok:      {result['n_ok']}")
    print(f"  skipped: {result['n_skip']}  (< {_MIN_ROWS_FOR_FEATURES} rows)")
    print(f"  errors:  {result['n_err']}")
    print(f"  elapsed: {elapsed:.1f}s")
    print()

    logger.info(
        "bullish_features_complete",
        n_ok=result["n_ok"],
        n_skip=result["n_skip"],
        n_err=result["n_err"],
        elapsed_s=round(elapsed, 1),
    )

    return 0 if result["n_err"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
