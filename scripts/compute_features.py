#!/usr/bin/env python3
# scripts/compute_features.py
"""Daily feature computation pipeline (v0.1.11).

兩個階段:
  Phase 1: 每個 symbol 從 daily_price_adj 算 9 個 indicator → 寫 daily_features
  Phase 2: TAIEX 從 daily_price 算 regime → 寫 market_regime

設計:
- 全量重寫 (DELETE + INSERT per symbol)
- 大盤 regime 一次算完整 series
- 對 symbol 跑 < 200 天資料的會有 SMA200 = null，這是預期的

使用:
  uv run python scripts/compute_features.py             # 全部
  uv run python scripts/compute_features.py --symbols 2330,0050
  uv run python scripts/compute_features.py --regime-only
  uv run python scripts/compute_features.py --indicators-only

Version: v0.1.0 (2026-05-17)
Changelog:
  v0.1.0 (2026-05-17): Initial — 2-phase pipeline
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from typing import Any

import polars as pl

from data.database import connect, init_schema
from features.regime import compute_regime
from features.technical import compute_indicators
from utils.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────
# Phase 1: per-symbol indicators
# ─────────────────────────────────────────────────────────────


def get_symbols_with_adj() -> list[str]:
    with connect(read_only=True) as conn:
        rows = conn.execute(
            "SELECT DISTINCT stock_id FROM daily_price_adj ORDER BY stock_id"
        ).fetchall()
    return [r[0] for r in rows]


def load_adj_for_symbol(stock_id: str) -> pl.DataFrame:
    with connect(read_only=True) as conn:
        arrow = conn.execute(
            """
            SELECT stock_id, date, adj_open, adj_high, adj_low, adj_close,
                   raw_close, cum_factor, volume
            FROM daily_price_adj
            WHERE stock_id = ?
            ORDER BY date
            """,
            [stock_id],
        ).to_arrow_table()
    return pl.from_arrow(arrow)


FEATURE_COLUMNS = [
    "stock_id", "date",
    "sma_20", "sma_50", "sma_200", "ema_20",
    "rsi_14", "roc_20",
    "atr_14",
    "donchian_20_high", "donchian_20_low",
    "volume_ma_20", "rel_volume_20",
    "computed_at",
]


def write_features(stock_id: str, df: pl.DataFrame, ingest_at: datetime) -> int:
    """Write daily_features rows for one symbol (DELETE + INSERT)."""
    # Keep only feature columns + meta
    df_out = df.with_columns(computed_at=ingest_at).select(FEATURE_COLUMNS)
    with connect() as conn:
        conn.execute(
            "DELETE FROM daily_features WHERE stock_id = ?", [stock_id]
        )
        conn.register("inp", df_out.to_arrow())
        try:
            conn.execute(f"""
                INSERT INTO daily_features ({','.join(FEATURE_COLUMNS)})
                SELECT {','.join(FEATURE_COLUMNS)} FROM inp
            """)
        finally:
            conn.unregister("inp")
    return df_out.height


def compute_phase_indicators(symbols: list[str]) -> dict[str, Any]:
    print(f"\n{'='*60}\nPhase 1: Per-symbol indicators\n{'='*60}")
    print(f"Symbols: {len(symbols)}")

    ingest_at = datetime.now()
    n_ok, n_err = 0, 0
    t0 = time.time()

    for i, sid in enumerate(symbols, 1):
        try:
            df_adj = load_adj_for_symbol(sid)
            if df_adj.is_empty():
                print(f"  [{i:2d}/{len(symbols)}] ○ {sid:8s} (no adj data)")
                continue

            df_features = compute_indicators(df_adj)
            n_written = write_features(sid, df_features, ingest_at)

            # 顯示 latest 一筆做 sanity check
            latest = df_features.tail(1).row(0, named=True)
            sma_str = f"{latest['sma_20']:.2f}" if latest['sma_20'] is not None else "null"
            rsi_str = f"{latest['rsi_14']:.1f}" if latest['rsi_14'] is not None else "null"
            print(
                f"  [{i:2d}/{len(symbols)}] ✓ {sid:8s}  "
                f"rows={n_written}  "
                f"close={latest['adj_close']:.2f}  "
                f"sma_20={sma_str}  rsi_14={rsi_str}"
            )
            n_ok += 1
        except Exception as e:
            logger.exception("feature_compute_failed", stock_id=sid)
            print(f"  [{i:2d}/{len(symbols)}] ✗ {sid:8s}  ERROR: {e}")
            n_err += 1

    elapsed = time.time() - t0
    return {"n_ok": n_ok, "n_err": n_err, "elapsed": elapsed}


# ─────────────────────────────────────────────────────────────
# Phase 2: market regime
# ─────────────────────────────────────────────────────────────


def compute_phase_regime() -> dict[str, Any]:
    print(f"\n{'='*60}\nPhase 2: Market regime (TAIEX)\n{'='*60}")

    with connect(read_only=True) as conn:
        arrow = conn.execute(
            "SELECT date, close FROM daily_price WHERE stock_id = 'TAIEX' ORDER BY date"
        ).to_arrow_table()
    taiex_df = pl.from_arrow(arrow)

    if taiex_df.is_empty():
        print("❌ daily_price 內沒 TAIEX 資料")
        return {"n_ok": 0, "n_err": 1, "elapsed": 0.0}

    print(f"TAIEX rows: {taiex_df.height}")

    t0 = time.time()
    regime_df = compute_regime(taiex_df)
    ingest_at = datetime.now()
    regime_df = regime_df.with_columns(computed_at=ingest_at)

    with connect() as conn:
        conn.execute("DELETE FROM market_regime")
        conn.register("inp", regime_df.to_arrow())
        try:
            conn.execute("""
                INSERT INTO market_regime
                (date, taiex_close, sma_200, vol_20, regime, computed_at)
                SELECT date, taiex_close, sma_200, vol_20, regime, computed_at
                FROM inp
            """)
        finally:
            conn.unregister("inp")

    elapsed = time.time() - t0

    # Regime distribution
    print()
    print("Regime distribution (over full history):")
    dist = (
        regime_df.filter(pl.col("regime").is_not_null())
        .group_by("regime")
        .len()
        .sort("len", descending=True)
    )
    total = dist["len"].sum() if dist.height > 0 else 0
    for r in dist.iter_rows(named=True):
        pct = r["len"] / total * 100 if total else 0
        print(f"  {r['regime']:8s} {r['len']:5d} ({pct:5.1f}%)")

    # Latest regime
    latest = regime_df.tail(1).row(0, named=True) if regime_df.height > 0 else None
    if latest:
        print(f"\nLatest ({latest['date']}):")
        print(f"  TAIEX close = {latest['taiex_close']:.2f}")
        if latest['sma_200'] is not None:
            print(f"  SMA_200     = {latest['sma_200']:.2f} "
                  f"({'above' if latest['taiex_close'] > latest['sma_200'] else 'below'})")
        if latest['vol_20'] is not None:
            print(f"  vol_20      = {latest['vol_20']*100:.2f}%")
        print(f"  regime      = {latest['regime']}")

    return {"n_ok": regime_df.height, "n_err": 0, "elapsed": elapsed}


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute daily_features (indicators) + market_regime"
    )
    parser.add_argument(
        "--symbols", type=str,
        help="逗號分隔；不給就用 daily_price_adj 全部 symbol",
    )
    parser.add_argument(
        "--indicators-only", action="store_true",
        help="只跑 Phase 1 (跳過 regime)",
    )
    parser.add_argument(
        "--regime-only", action="store_true",
        help="只跑 Phase 2 (跳過 indicators)",
    )
    args = parser.parse_args()

    if args.indicators_only and args.regime_only:
        print("❌ --indicators-only 跟 --regime-only 不能同時用")
        return 2

    init_schema()
    print(f"Helios compute_features — {datetime.now().isoformat(timespec='seconds')}")

    summary: dict[str, Any] = {}

    if not args.regime_only:
        if args.symbols:
            symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
        else:
            symbols = get_symbols_with_adj()
        if not symbols:
            print("❌ daily_price_adj 為空，請先跑 build_adjusted_prices.py")
            return 1
        summary["phase1"] = compute_phase_indicators(symbols)

    if not args.indicators_only:
        summary["phase2"] = compute_phase_regime()

    # 全表摘要
    print(f"\n{'='*60}\nOverall summary\n{'='*60}")
    with connect(read_only=True) as conn:
        f_rows = conn.execute("SELECT COUNT(*) FROM daily_features").fetchone()[0]
        f_syms = conn.execute(
            "SELECT COUNT(DISTINCT stock_id) FROM daily_features"
        ).fetchone()[0]
        r_rows = conn.execute("SELECT COUNT(*) FROM market_regime").fetchone()[0]
    print(f"  daily_features: {f_rows} rows × {f_syms} symbols")
    print(f"  market_regime:  {r_rows} rows")
    if "phase1" in summary:
        print(f"  Phase 1 time: {summary['phase1']['elapsed']:.1f}s")
    if "phase2" in summary:
        print(f"  Phase 2 time: {summary['phase2']['elapsed']:.2f}s")
    print()
    print("💡 跑 scripts/feature_inspect.py 看 5 個 strategy-readiness 問題")

    return 0


if __name__ == "__main__":
    sys.exit(main())
