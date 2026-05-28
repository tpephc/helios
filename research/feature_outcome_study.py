#!/usr/bin/env python3
# research/feature_outcome_study.py
"""Feature outcome baseline study — Phase 0 v2.

Computes forward return distributions per feature bucket to establish
baseline measurement before any feature engineering changes.

Methodology:
  - Forward return: adj_close[t+N] / adj_close[t] - 1 (vectorized shift)
  - MAE/MFE: close-based only (close_mae, close_mfe)
  - Continuous features: expanding window quantile (boundary from < t only)
  - Integer/count features: fixed semantic grouping
  - Sample spacing: per-stock sequence index, default = max(horizons)
  - Cost: gross + simple_net (round_trip_cost_bps = 58.5)
  - Universe: all + point-in-time universe_snapshot membership
  - Output: CSV dump + console summary

v2 fixes (per review):
  P0-1: is_top200 uses universe_snapshot point-in-time, not config/universe.yaml
  P0-2: continuous bucket boundaries use expanding window (shift(1), < t data only)
  P0-3: sample_every_n_days uses per-stock sequence index
  P0-4: forward return uses Polars vectorized join + shift
  P1-1: MIN_BUCKET_N = 30 with is_underpowered flag
  P1-2: winsorized_mean_return_5pct added

Version: v0.1.0-p0v2 (2026-05-28)
"""
from __future__ import annotations

import argparse
import sys
from datetime import date as date_type
from pathlib import Path

import polars as pl

from data.database import connect
from utils.logger import get_logger

logger = get_logger(__name__)


# ── Cost model ────────────────────────────────────────────────────────────

COMMISSION_BPS: float = 14.25 * 2  # buy + sell
TAX_BPS: float = 30.0              # sell-side
ROUND_TRIP_COST_BPS: float = COMMISSION_BPS + TAX_BPS  # 58.5 bps

# ── Bucket config ─────────────────────────────────────────────────────────

N_QUANTILE_BUCKETS = 5
MIN_BUCKET_N = 30
WINSORIZE_PCT = 0.05  # 5% each tail

_STREAK_BUCKETS = [
    ("0",     lambda v: v == 0),
    ("1-2",   lambda v: 1 <= v <= 2),
    ("3-5",   lambda v: 3 <= v <= 5),
    ("6-10",  lambda v: 6 <= v <= 10),
    ("10+",   lambda v: v > 10),
]

_COUNT_BUCKETS = [
    ("0",  lambda v: v == 0),
    ("1",  lambda v: v == 1),
    ("2",  lambda v: v == 2),
    ("3+", lambda v: v >= 3),
]

_BINARY_SPARSE_BUCKETS = [
    ("0",  lambda v: v == 0),
    ("1",  lambda v: v == 1),
    ("2+", lambda v: v >= 2),
]

_INTEGER_BUCKET_MAP: dict[str, list] = {
    "above_ma20_streak": _STREAK_BUCKETS,
    "above_ma50_streak": _STREAK_BUCKETS,
    "below_ma20_streak": _STREAK_BUCKETS,
    "below_ma50_streak": _STREAK_BUCKETS,
    "below_ma200_streak": _STREAK_BUCKETS,
    "ma20_reclaim_confirmed": _STREAK_BUCKETS,
    "ma50_reclaim_confirmed": _STREAK_BUCKETS,
    "volume_contraction_days_10d": _COUNT_BUCKETS,
    "tight_range_days_10d": _COUNT_BUCKETS,
    "volume_breakout_days_5d": _BINARY_SPARSE_BUCKETS,
    "failed_breakdown_count_10d": _BINARY_SPARSE_BUCKETS,
    "failed_ma20_reclaim_5d": _BINARY_SPARSE_BUCKETS,
    "failed_ma50_reclaim_10d": _BINARY_SPARSE_BUCKETS,
    "high_vol_down_days_5d": _BINARY_SPARSE_BUCKETS,
    "weak_rebound_days_10d": _COUNT_BUCKETS,
    "new_low_after_rebound_5d": _BINARY_SPARSE_BUCKETS,
    "atr_compression_days_10d": _COUNT_BUCKETS,
    "atr_expansion_days_5d": _BINARY_SPARSE_BUCKETS,
}


# ── Data loading ──────────────────────────────────────────────────────────


def _load_feature_table(
    table: str,
    start: date_type | None,
    end: date_type | None,
) -> pl.DataFrame:
    """Load feature table joined with adj_close."""
    where_parts = ["p.adj_close IS NOT NULL", "p.adj_close > 0"]
    params: list = []

    if start:
        where_parts.append("f.date >= ?")
        params.append(str(start))
    if end:
        where_parts.append("f.date <= ?")
        params.append(str(end))

    where_sql = " AND ".join(where_parts)

    query = f"""
        SELECT f.*, p.adj_close
        FROM {table} f
        JOIN daily_price_adj p
          ON f.stock_id = p.stock_id AND f.date = p.date
        WHERE {where_sql}
        ORDER BY f.stock_id, f.date
    """

    with connect(read_only=True) as conn:
        result = conn.execute(query, params).fetchall()
        columns = [desc[0] for desc in conn.description]

    return pl.DataFrame(
        {col: [row[i] for row in result] for i, col in enumerate(columns)}
    )


def _load_price_series() -> pl.DataFrame:
    """Load full adj_close series for forward return lookups."""
    with connect(read_only=True) as conn:
        result = conn.execute(
            "SELECT stock_id, date, adj_close "
            "FROM daily_price_adj "
            "WHERE adj_close IS NOT NULL AND adj_close > 0 "
            "ORDER BY stock_id, date"
        ).fetchall()

    return pl.DataFrame({
        "stock_id": [r[0] for r in result],
        "date": [r[1] for r in result],
        "adj_close": [r[2] for r in result],
    })


def _load_pit_universe() -> pl.DataFrame:
    """Load point-in-time universe membership from universe_snapshot.

    Returns DataFrame with (stock_id, date, passed) for rows where
    universe_name = 'dynamic_top200' and passed = true.

    P0-1 fix: replaces config/universe.yaml (which is current-state,
    not point-in-time). Using universe_snapshot ensures the membership
    is as-of the feature date, preventing survivorship bias.
    """
    with connect(read_only=True) as conn:
        result = conn.execute(
            """
            SELECT stock_id, snapshot_date AS date
            FROM universe_snapshot
            WHERE universe_name = 'dynamic_top200'
              AND passed = TRUE
            ORDER BY snapshot_date, stock_id
            """
        ).fetchall()

    return pl.DataFrame({
        "stock_id": [r[0] for r in result],
        "pit_date": [r[1] for r in result],
    })


# ── Forward return (vectorized) ───────────────────────────────────────────


def _compute_forward_metrics(
    features_df: pl.DataFrame,
    price_df: pl.DataFrame,
    horizons: list[int],
) -> pl.DataFrame:
    """Compute forward return, close_mae, close_mfe per horizon.

    P0-4: fully vectorized using Polars shift within per-stock groups.
    No Python per-row loops.

    For each horizon N:
      forward_return_{N}d = adj_close[t+N] / adj_close[t] - 1
      close_mae_{N}d = min(adj_close[t+1..t+N]) / adj_close[t] - 1
      close_mfe_{N}d = max(adj_close[t+1..t+N]) / adj_close[t] - 1
      simple_net_return_{N}d = forward_return_{N}d - round_trip_cost
    """
    # Add row_index within each stock for shift operations
    price_indexed = price_df.with_columns(
        pl.col("date").rank("ordinal").over("stock_id").alias("_seq_idx")
    )

    # For each horizon, compute forward close and rolling min/max
    fwd_cols = []
    for h in horizons:
        # Forward close at t+h
        fwd_close = (
            price_indexed
            .with_columns(
                pl.col("adj_close").shift(-h).over("stock_id").alias(f"_fwd_close_{h}"),
            )
            .select(["stock_id", "date", f"_fwd_close_{h}"])
        )
        fwd_cols.append(fwd_close)

        # Rolling min/max over [t+1, t+h] for MAE/MFE
        # Build by shifting each offset and taking min/max
        shift_exprs = []
        for offset in range(1, h + 1):
            shift_exprs.append(
                pl.col("adj_close").shift(-offset).over("stock_id").alias(f"_s{offset}")
            )

        if shift_exprs:
            shifted = price_indexed.with_columns(shift_exprs)
            shift_col_names = [f"_s{offset}" for offset in range(1, h + 1)]

            shifted = shifted.with_columns([
                pl.min_horizontal(*shift_col_names).alias(f"_fwd_min_{h}"),
                pl.max_horizontal(*shift_col_names).alias(f"_fwd_max_{h}"),
            ])

            mae_mfe = shifted.select([
                "stock_id", "date",
                f"_fwd_min_{h}", f"_fwd_max_{h}",
            ])
            fwd_cols.append(mae_mfe)

    # Join all forward columns back to features
    result = features_df.clone()
    for fc in fwd_cols:
        result = result.join(fc, on=["stock_id", "date"], how="left")

    # Compute return metrics
    cost_pct = ROUND_TRIP_COST_BPS / 10000.0
    for h in horizons:
        fwd_col = f"_fwd_close_{h}"
        min_col = f"_fwd_min_{h}"
        max_col = f"_fwd_max_{h}"

        result = result.with_columns([
            (pl.col(fwd_col) / pl.col("adj_close") - 1.0)
                .alias(f"forward_return_{h}d"),
            (pl.col(min_col) / pl.col("adj_close") - 1.0)
                .alias(f"close_mae_{h}d"),
            (pl.col(max_col) / pl.col("adj_close") - 1.0)
                .alias(f"close_mfe_{h}d"),
            (pl.col(fwd_col) / pl.col("adj_close") - 1.0 - cost_pct)
                .alias(f"simple_net_return_{h}d"),
        ])

    # Drop temp columns
    drop_cols = [c for c in result.columns if c.startswith("_fwd_") or c.startswith("_s")]
    result = result.drop(drop_cols)

    return result


# ── Sample spacing ────────────────────────────────────────────────────────


def _apply_sample_spacing(
    df: pl.DataFrame,
    spacing: int,
) -> pl.DataFrame:
    """Subsample rows with per-stock sequence spacing.

    P0-3: uses per-stock sequence index (not global date index) to ensure
    consistent spacing even with missing data days.

    Every `spacing`-th row per stock is kept. This prevents forward return
    overlap from inflating statistical significance.
    """
    if spacing <= 1:
        return df

    return (
        df
        .with_columns(
            (pl.arange(0, pl.count()).over("stock_id") % spacing)
            .alias("_spacing_mod")
        )
        .filter(pl.col("_spacing_mod") == 0)
        .drop("_spacing_mod")
    )


# ── Point-in-time universe flag ───────────────────────────────────────────


def _add_pit_universe_flag(
    df: pl.DataFrame,
    pit_universe: pl.DataFrame,
) -> pl.DataFrame:
    """Add is_top200 flag using point-in-time universe_snapshot.

    P0-1: join on (stock_id, date) to get as-of membership.
    If universe_snapshot is sparse (e.g. weekly), use join_asof
    to find the most recent snapshot <= feature date.
    """
    if pit_universe.is_empty():
        return df.with_columns(pl.lit(False).alias("is_top200"))

    # Check if snapshot is daily or sparse
    pit_dates = pit_universe["pit_date"].n_unique()
    feature_dates = df["date"].n_unique()

    if pit_dates >= feature_dates * 0.8:
        # Dense enough for exact join
        pit_flag = pit_universe.with_columns(
            pl.lit(True).alias("is_top200")
        ).rename({"pit_date": "date"})

        return (
            df
            .join(pit_flag, on=["stock_id", "date"], how="left")
            .with_columns(
                pl.col("is_top200").fill_null(False)
            )
        )
    else:
        # Sparse: use join_asof (most recent snapshot <= feature date)
        pit_sorted = (
            pit_universe
            .with_columns(pl.lit(True).alias("_pit_member"))
            .sort("pit_date")
        )

        df_sorted = df.sort("date")

        # join_asof per stock: feature.date >= pit.pit_date
        joined = df_sorted.join_asof(
            pit_sorted,
            left_on="date",
            right_on="pit_date",
            by="stock_id",
            strategy="backward",
        )

        return joined.with_columns(
            pl.col("_pit_member").fill_null(False).alias("is_top200")
        ).drop("_pit_member", "pit_date")


# ── Expanding window quantile buckets ─────────────────────────────────────


def _assign_expanding_quantile_bucket(
    col_name: str,
    df: pl.DataFrame,
) -> pl.Series:
    """Assign quantile bucket using expanding window (< t data only).

    P0-2: boundary at row t uses only data from rows < t (shift(1)).
    This prevents future feature distribution from leaking into
    current bucket assignment.

    Implementation: for each stock, compute expanding quantile boundaries
    using all prior rows, then classify current row's value.
    """
    values = df[col_name].to_list()
    stock_ids = df["stock_id"].to_list()
    n = len(values)

    labels: list[str | None] = [None] * n

    # Group by stock for expanding window
    stock_history: dict[str, list[float]] = {}

    for i in range(n):
        sid = stock_ids[i]
        v = values[i]

        if sid not in stock_history:
            stock_history[sid] = []

        history = stock_history[sid]

        # Bucket assignment uses history BEFORE adding current value
        if v is not None and len(history) >= N_QUANTILE_BUCKETS * 2:
            # Compute boundaries from history (< t, not <= t)
            sorted_hist = sorted(history)
            nh = len(sorted_hist)
            boundaries = []
            for q in range(1, N_QUANTILE_BUCKETS):
                idx = int(q / N_QUANTILE_BUCKETS * nh)
                idx = min(idx, nh - 1)
                boundaries.append(sorted_hist[idx])

            bucket_idx = 0
            for b in boundaries:
                if v > b:
                    bucket_idx += 1
            labels[i] = f"Q{bucket_idx + 1}"

        # Add current value to history AFTER bucket assignment
        if v is not None:
            history.append(v)

    return pl.Series(f"{col_name}_bucket", labels, dtype=pl.Utf8)


def _assign_integer_bucket(
    col_name: str,
    values: pl.Series,
) -> pl.Series:
    """Assign fixed semantic bucket for integer features (no leakage risk)."""
    buckets = _INTEGER_BUCKET_MAP.get(col_name, _COUNT_BUCKETS)
    labels = []
    for v in values.to_list():
        if v is None:
            labels.append(None)
            continue
        matched = False
        for label, pred in buckets:
            if pred(v):
                labels.append(label)
                matched = True
                break
        if not matched:
            labels.append(buckets[-1][0])
    return pl.Series(f"{col_name}_bucket", labels, dtype=pl.Utf8)


# ── Winsorized mean ───────────────────────────────────────────────────────


def _winsorized_mean(series: pl.Series, pct: float = WINSORIZE_PCT) -> float | None:
    """Compute winsorized mean (trim pct from each tail)."""
    vals = series.drop_nulls().sort()
    n = len(vals)
    if n < 4:
        return None
    trim = max(1, int(n * pct))
    trimmed = vals[trim:n - trim]
    if len(trimmed) == 0:
        return None
    return trimmed.mean()


# ── Aggregation ───────────────────────────────────────────────────────────


def _get_feature_columns(df: pl.DataFrame) -> list[str]:
    """Identify feature columns (exclude metadata and computed columns)."""
    exclude = {
        "stock_id", "date", "adj_close", "computed_at",
        "is_top200", "_seq_idx",
    }
    exclude.update(c for c in df.columns if c.startswith("forward_return_"))
    exclude.update(c for c in df.columns if c.startswith("close_mae_"))
    exclude.update(c for c in df.columns if c.startswith("close_mfe_"))
    exclude.update(c for c in df.columns if c.startswith("simple_net_return_"))
    exclude.update(c for c in df.columns if c.endswith("_bucket"))

    return [c for c in df.columns if c not in exclude]


def _compute_bucket_stats(
    df: pl.DataFrame,
    feature_col: str,
    horizons: list[int],
    top200_only: bool = False,
) -> list[dict]:
    """Compute per-bucket statistics for one feature column."""
    bucket_col = f"{feature_col}_bucket"
    if bucket_col not in df.columns:
        return []

    work = df.filter(pl.col("is_top200") == True) if top200_only else df

    results = []
    for h in horizons:
        ret_col = f"forward_return_{h}d"
        net_col = f"simple_net_return_{h}d"
        mae_col = f"close_mae_{h}d"
        mfe_col = f"close_mfe_{h}d"

        if ret_col not in work.columns:
            continue

        valid = work.filter(
            pl.col(bucket_col).is_not_null()
            & pl.col(ret_col).is_not_null()
        )
        if valid.is_empty():
            continue

        for bucket_val in sorted(
            valid[bucket_col].unique().to_list(),
            key=lambda x: x if x is not None else "",
        ):
            if bucket_val is None:
                continue

            subset = valid.filter(pl.col(bucket_col) == bucket_val)
            n = subset.height
            if n == 0:
                continue

            rets = subset[ret_col].drop_nulls()
            nets = subset[net_col].drop_nulls() if net_col in subset.columns else rets
            maes = subset[mae_col].drop_nulls() if mae_col in subset.columns else pl.Series([])
            mfes = subset[mfe_col].drop_nulls() if mfe_col in subset.columns else pl.Series([])

            results.append({
                "feature": feature_col,
                "bucket": bucket_val,
                "horizon_d": h,
                "sample_count": n,
                "is_underpowered": n < MIN_BUCKET_N,
                "mean_return": rets.mean() if len(rets) > 0 else None,
                "median_return": rets.median() if len(rets) > 0 else None,
                "winsorized_mean_return_5pct": _winsorized_mean(rets),
                "std_return": rets.std() if len(rets) > 1 else None,
                "hit_rate": (
                    (rets > 0).sum() / len(rets) if len(rets) > 0 else None
                ),
                "p10_return": (
                    rets.quantile(0.10, interpolation="linear")
                    if len(rets) >= 10 else None
                ),
                "p90_return": (
                    rets.quantile(0.90, interpolation="linear")
                    if len(rets) >= 10 else None
                ),
                "mean_simple_net_return": nets.mean() if len(nets) > 0 else None,
                "mean_close_mae": maes.mean() if len(maes) > 0 else None,
                "mean_close_mfe": mfes.mean() if len(mfes) > 0 else None,
                "universe": "top200" if top200_only else "all",
            })

    return results


# ── Console summary ───────────────────────────────────────────────────────


def _print_summary(stats: list[dict], table: str) -> None:
    """Print concise console summary."""
    if not stats:
        print("No statistics computed.")
        return

    by_feature: dict[str, list[dict]] = {}
    for s in stats:
        by_feature.setdefault(s["feature"], []).append(s)

    print(f"\n{'=' * 90}")
    print(f"Feature Outcome Baseline — {table}")
    print(f"{'=' * 90}")

    for feature, rows in sorted(by_feature.items()):
        print(f"\n  {feature}")
        print(f"  {'bucket':<8} {'hz':>4} {'n':>6} {'⚡':>2} "
              f"{'mean':>8} {'w.mean':>8} {'med':>8} {'hit%':>6} "
              f"{'p10':>8} {'p90':>8} {'MAE':>8} {'MFE':>8}")
        print(f"  {'─' * 88}")

        for r in sorted(rows, key=lambda x: (x["horizon_d"], x["bucket"])):
            def _f(v):
                if v is None:
                    return "    N/A"
                return f"{v * 100:>+7.2f}%"

            hit = f"{r['hit_rate'] * 100:>5.1f}%" if r["hit_rate"] is not None else "  N/A"
            flag = "⚠" if r["is_underpowered"] else " "

            print(
                f"  {r['bucket']:<8} {r['horizon_d']:>3}d {r['sample_count']:>6} {flag:>2} "
                f"{_f(r['mean_return'])} {_f(r['winsorized_mean_return_5pct'])} "
                f"{_f(r['median_return'])} {hit} "
                f"{_f(r['p10_return'])} {_f(r['p90_return'])} "
                f"{_f(r['mean_close_mae'])} {_f(r['mean_close_mfe'])}"
            )


# ── Main ──────────────────────────────────────────────────────────────────


def run_study(
    table: str,
    horizons: list[int],
    start: date_type | None = None,
    end: date_type | None = None,
    sample_spacing: int | None = None,
    output_dir: Path | None = None,
) -> list[dict]:
    """Run the full feature outcome study."""
    if output_dir is None:
        output_dir = Path("research/outputs")
    output_dir.mkdir(parents=True, exist_ok=True)

    if sample_spacing is None:
        sample_spacing = max(horizons)

    # ── Load data ─────────────────────────────────────────────
    print(f"Loading {table}...")
    features_df = _load_feature_table(table, start, end)
    print(f"  rows: {features_df.height}")
    print(f"  stocks: {features_df['stock_id'].n_unique()}")

    if features_df.is_empty():
        print("No data found. Exiting.")
        return []

    dates = features_df["date"]
    print(f"  min_date: {dates.min()}")
    print(f"  max_date: {dates.max()}")

    print("Loading price series...")
    price_df = _load_price_series()
    print(f"  price rows: {price_df.height}")

    # ── Point-in-time universe flag (P0-1) ────────────────────
    print("Loading point-in-time universe membership...")
    pit_universe = _load_pit_universe()
    print(f"  universe_snapshot rows: {pit_universe.height}")
    features_df = _add_pit_universe_flag(features_df, pit_universe)
    n_top200 = features_df.filter(pl.col("is_top200")).height
    print(f"  point-in-time top200 matches: {n_top200} / {features_df.height}")

    # ── Forward metrics (P0-4 vectorized) ─────────────────────
    print(f"Computing forward returns (vectorized) for horizons {horizons}...")
    features_df = _compute_forward_metrics(features_df, price_df, horizons)

    for h in horizons:
        col = f"forward_return_{h}d"
        n_valid = len(features_df[col].drop_nulls())
        print(f"  horizon {h}d: {n_valid} usable samples "
              f"({n_valid / features_df.height * 100:.1f}%)")

    # ── Sample spacing (P0-3 per-stock) ───────────────────────
    pre_spacing = features_df.height
    features_df = _apply_sample_spacing(features_df, sample_spacing)
    print(f"Sample spacing: every {sample_spacing} rows per stock "
          f"({pre_spacing} → {features_df.height})")

    # ── Bucketing (P0-2 expanding quantile) ───────────────────
    feature_cols = _get_feature_columns(features_df)
    print(f"Feature columns: {len(feature_cols)}")

    for col in feature_cols:
        dtype = features_df[col].dtype
        if dtype in (pl.Int32, pl.Int64, pl.UInt32, pl.UInt64, pl.Int16):
            bucket_series = _assign_integer_bucket(col, features_df[col])
        else:
            bucket_series = _assign_expanding_quantile_bucket(col, features_df)
        features_df = features_df.with_columns(bucket_series)

    # ── Aggregation ───────────────────────────────────────────
    print("Computing bucket statistics...")
    all_stats: list[dict] = []

    for col in feature_cols:
        stats = _compute_bucket_stats(features_df, col, horizons, top200_only=False)
        all_stats.extend(stats)
        stats_200 = _compute_bucket_stats(features_df, col, horizons, top200_only=True)
        all_stats.extend(stats_200)

    # ── Output ────────────────────────────────────────────────
    if all_stats:
        stats_df = pl.DataFrame(all_stats)
        csv_path = output_dir / f"{table}_outcome_baseline.csv"
        stats_df.write_csv(csv_path)
        print(f"\nCSV written: {csv_path} ({len(all_stats)} rows)")

        underpowered = sum(1 for s in all_stats if s["is_underpowered"])
        print(f"Underpowered buckets (n < {MIN_BUCKET_N}): "
              f"{underpowered} / {len(all_stats)}")

        _print_summary(
            [s for s in all_stats if s["universe"] == "all"],
            table,
        )
    else:
        print("No statistics generated.")

    return all_stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Phase 0: Feature outcome baseline study (v2)"
    )
    parser.add_argument(
        "--table", type=str, required=True,
        choices=["bullish_features", "bearish_features"],
    )
    parser.add_argument(
        "--horizons", type=str, default="5,10,20",
        help="Comma-separated horizons in trading days (default: 5,10,20)",
    )
    parser.add_argument("--start", type=str, default=None)
    parser.add_argument("--end", type=str, default=None)
    parser.add_argument(
        "--sample-spacing", type=int, default=None,
        help="Per-stock sample spacing in rows (default: max horizon)",
    )
    parser.add_argument("--output-dir", type=str, default=None)
    args = parser.parse_args()

    horizons = [int(h.strip()) for h in args.horizons.split(",")]
    start = date_type.fromisoformat(args.start) if args.start else None
    end = date_type.fromisoformat(args.end) if args.end else None
    output_dir = Path(args.output_dir) if args.output_dir else None
    spacing = args.sample_spacing

    print(f"Feature Outcome Study — Phase 0 Baseline v2")
    print(f"  table:          {args.table}")
    print(f"  horizons:       {horizons}")
    print(f"  start:          {start or '(all)'}")
    print(f"  end:            {end or '(all)'}")
    print(f"  sample_spacing: {spacing or f'auto (max horizon = {max(horizons)})'}")
    print(f"  cost:           {ROUND_TRIP_COST_BPS:.1f} bps "
          f"(commission {COMMISSION_BPS:.1f} + tax {TAX_BPS:.1f})")
    print(f"  min_bucket_n:   {MIN_BUCKET_N}")
    print(f"  winsorize:      {WINSORIZE_PCT * 100:.0f}% each tail")
    print()

    stats = run_study(
        table=args.table,
        horizons=horizons,
        start=start,
        end=end,
        sample_spacing=spacing,
        output_dir=output_dir,
    )

    print(f"\nTotal bucket-horizon combinations: {len(stats)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
