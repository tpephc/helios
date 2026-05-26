#!/usr/bin/env python3
# scripts/compute_bearish_features.py
"""Bearish temporal feature computation pipeline — v0.1.0.

Reads from daily_features + daily_price_adj + market_regime,
computes multi-bar bearish regime features via features/bearish_regime.py,
and writes to the bearish_features table.

Design:
  - Standalone: does not depend on or modify compute_features.py.
  - Full rewrite per symbol: DELETE + INSERT (same pattern as compute_features.py).
  - TAIEX loaded once, passed to all symbols (not per-symbol DB call).
  - Graceful degradation: symbols with insufficient history are skipped,
    not errored. Relative weakness features are skipped if TAIEX missing.

Usage:
  uv run python scripts/compute_bearish_features.py
  uv run python scripts/compute_bearish_features.py --symbols 2330,2454
  uv run python scripts/compute_bearish_features.py --as-of 2026-05-22

Version: v0.1.0 (2026-05-26)
Changelog:
  v0.1.0 (2026-05-26): Initial — Phase 2 bearish temporal feature layer.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date as date_type
from datetime import datetime

import polars as pl

from data.database import connect, init_schema
from features.bearish_regime import (
    BEARISH_FEATURE_COLUMN_NAMES,
    compute_all_bearish_features,
)
from utils.logger import get_logger

logger = get_logger(__name__)

# Minimum rows required to compute any meaningful temporal feature.
# ATR baseline needs 20 bars, beta_adj_rs_60d needs 61 bars.
# Set conservatively at 80 to ensure all features are computable.
_MIN_ROWS_FOR_FEATURES = 80

# Output columns written to bearish_features table (key + feature columns)
_KEY_COLS = ["stock_id", "date"]
_ALL_OUTPUT_COLS = _KEY_COLS + BEARISH_FEATURE_COLUMN_NAMES + ["computed_at"]


# ── Schema ────────────────────────────────────────────────────────────

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS bearish_features (
    stock_id    VARCHAR  NOT NULL,
    date        DATE     NOT NULL,
    -- Family 1: Persistence (consecutive trading day streak, resets on close >= MA)
    below_ma20_streak              INTEGER,
    below_ma50_streak              INTEGER,
    below_ma200_streak             INTEGER,
    -- Family 2: Failed reclaim
    failed_ma20_reclaim_5d         INTEGER,
    failed_ma50_reclaim_10d        INTEGER,
    -- Family 3: Distribution sequence (primitives)
    high_vol_down_days_5d          INTEGER,
    weak_rebound_days_10d          INTEGER,
    new_low_after_rebound_5d       INTEGER,
    -- Family 4: Relative weakness (nullable — requires TAIEX data)
    beta_60                        DOUBLE,
    beta_adj_rs_20d                DOUBLE,
    beta_adj_rs_60d                DOUBLE,
    -- Family 5: Volatility clustering
    atr_expansion_ratio            DOUBLE,
    atr_expansion_days_5d          INTEGER,
    -- Metadata
    computed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (stock_id, date)
)
"""


def ensure_schema() -> None:
    """Create bearish_features table if it does not exist."""
    with connect() as conn:
        conn.execute(_CREATE_TABLE_SQL)
    logger.info("bearish_features_schema_ready")


# ── Data loading ──────────────────────────────────────────────────────

def get_all_symbols() -> list[str]:
    """Return all symbols present in daily_features."""
    with connect(read_only=True) as conn:
        rows = conn.execute(
            "SELECT DISTINCT stock_id FROM daily_features ORDER BY stock_id"
        ).fetchall()
    return [r[0] for r in rows]


def load_symbol_data(stock_id: str) -> pl.DataFrame:
    """Load daily_features + adj_close for one symbol, sorted by date ASC."""
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
    """Load TAIEX close price series from market_regime."""
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


# ── Write ─────────────────────────────────────────────────────────────

def write_bearish_features(
    stock_id: str,
    df: pl.DataFrame,
    computed_at: datetime,
) -> int:
    """Write bearish_features rows for one symbol (DELETE + INSERT)."""
    df_out = df.with_columns(
        pl.lit(computed_at).alias("computed_at")
    )

    # Select only output columns that exist in df (beta_adj_rs may be absent
    # if TAIEX data was unavailable)
    available_cols = [c for c in _ALL_OUTPUT_COLS if c in df_out.columns]
    # Fill missing feature columns with null
    for col_name in _ALL_OUTPUT_COLS:
        if col_name not in df_out.columns:
            df_out = df_out.with_columns(pl.lit(None).alias(col_name))
    df_out = df_out.select(_ALL_OUTPUT_COLS)

    with connect() as conn:
        conn.execute(
            "DELETE FROM bearish_features WHERE stock_id = ?", [stock_id]
        )
        conn.register("inp", df_out.to_arrow())
        try:
            conn.execute(f"""
                INSERT INTO bearish_features ({','.join(_ALL_OUTPUT_COLS)})
                SELECT {','.join(_ALL_OUTPUT_COLS)} FROM inp
            """)
        finally:
            conn.unregister("inp")

    return df_out.height


# ── Main pipeline ─────────────────────────────────────────────────────

def compute_phase_bearish(
    symbols: list[str],
    taiex_df: pl.DataFrame,
    computed_at: datetime,
) -> dict:
    """Compute and write bearish features for all symbols."""
    print(f"\n{'=' * 60}")
    print("Bearish temporal feature computation")
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

            df_feat = compute_all_bearish_features(
                df,
                taiex_df=taiex_df if not taiex_df.is_empty() else None,
            )

            n_written = write_bearish_features(sid, df_feat, computed_at)

            # Spot-check latest row
            latest = df_feat.tail(1).row(0, named=True)
            b20  = latest.get("below_ma20_streak", "?")
            hvd  = latest.get("high_vol_down_days_5d", "?")
            atr  = latest.get("atr_expansion_ratio")
            atr_str = f"{atr:.2f}x" if atr is not None else "null"

            print(
                f"  [{i:3d}/{len(symbols)}] ✓ {sid:8s}"
                f"  rows={n_written}"
                f"  below_ma20={b20}"
                f"  hvd5d={hvd}"
                f"  atr_ratio={atr_str}"
            )
            n_ok += 1

        except Exception:
            logger.exception("bearish_feature_compute_failed", stock_id=sid)
            print(f"  [{i:3d}/{len(symbols)}] ✗ {sid:8s}  ERROR (see log)")
            n_err += 1

    elapsed = time.time() - t0
    return {
        "n_ok": n_ok, "n_skip": n_skip, "n_err": n_err,
        "elapsed": elapsed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute bearish temporal features (Phase 2)"
    )
    parser.add_argument(
        "--symbols", type=str, default=None,
        help="Comma-separated stock_ids (default: all symbols in daily_features)",
    )
    parser.add_argument(
        "--as-of", type=str, default=None,
        help="Not yet implemented — currently always computes full history",
    )
    args = parser.parse_args()

    # Ensure table exists
    ensure_schema()

    # Resolve symbols
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = get_all_symbols()

    if not symbols:
        print("No symbols found in daily_features. Run compute_features.py first.")
        return 1

    # Load TAIEX once for all symbols
    taiex_df = load_taiex_series()

    computed_at = datetime.now()
    result = compute_phase_bearish(symbols, taiex_df, computed_at)

    # Summary
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
        "bearish_features_complete",
        n_ok=result["n_ok"],
        n_skip=result["n_skip"],
        n_err=result["n_err"],
        elapsed_s=round(elapsed, 1),
    )

    return 0 if result["n_err"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
