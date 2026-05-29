#!/usr/bin/env python3
# research/feature_interaction_study.py
"""Feature interaction study — Phase 0 v2.

Tests whether feature combinations reveal edge that single features miss.

Core question: does feature B ADD edge when conditioned on feature A,
beyond what A alone provides? Measured via interaction_lift:
  lift = cell_return - marginal_A - marginal_B + grand_mean

v2 fixes:
  P0-1: RS bucket uses rolling 252d percentile tercile (regime-invariant)
  P0-2: interaction_lift metric (additive interaction effect)
  P1-7: renamed winsorized_mean → trimmed_mean_5pct (honest naming)

Interaction pairs:
  1. RS × Compression       — "coiled leader"
  2. RS × Failed Breakdown  — "strong absorption"
  3. RS × Volume Breakout   — "continuation"
  4. RS(low) × New Low After Rebound — "bearish continuation"

CAVEAT: sample spacing = max(horizon) reduces but does not eliminate
forward return overlap. Do not interpret these results as statistically
independent. Purged walk-forward / clustered bootstrap deferred to Phase B.

Usage:
  uv run python research/feature_interaction_study.py
  uv run python research/feature_interaction_study.py --horizons 5,10,20

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

COMMISSION_BPS: float = 14.25 * 2
TAX_BPS: float = 30.0
ROUND_TRIP_COST_BPS: float = COMMISSION_BPS + TAX_BPS

MIN_CELL_N = 30
TRIM_PCT = 0.05
# Rolling percentile lookback: target ~252 trading days, implemented as
# calendar-day approximation (×1.5 ≈ 378 calendar days). Not exact.
RS_LOOKBACK_TRADING_DAYS = 252


# ── Interaction definitions ───────────────────────────────────────────────
# feature_b buckets are fixed semantic (interpretable, no leakage risk).
# feature_a (RS) uses rolling percentile tercile assigned at runtime.

INTERACTIONS = [
    {
        "name": "rs_x_compression",
        "hypothesis": "Coiled leader: high RS + ATR compression → breakout edge",
        "table": "bullish_features",
        "feature_a": "beta_adj_rs_20d",
        "feature_b": "atr_compression_ratio",
        "buckets_b": [
            ("comp_yes", lambda v: v is not None and v < 0.85),
            ("comp_no",  lambda v: v is not None and v >= 0.85),
        ],
    },
    {
        "name": "rs_x_failed_breakdown",
        "hypothesis": "Strong absorption: high RS + failed breakdown → demand defense",
        "table": "bullish_features",
        "feature_a": "beta_adj_rs_20d",
        "feature_b": "failed_breakdown_count_10d",
        "buckets_b": [
            ("no_absorption",  lambda v: v is not None and v == 0),
            ("has_absorption", lambda v: v is not None and v >= 1),
        ],
    },
    {
        "name": "rs_x_volume_breakout",
        "hypothesis": "Continuation: high RS + volume breakout → momentum persistence",
        "table": "bullish_features",
        "feature_a": "beta_adj_rs_20d",
        "feature_b": "volume_breakout_days_5d",
        "buckets_b": [
            ("no_vol_break",  lambda v: v is not None and v == 0),
            ("has_vol_break", lambda v: v is not None and v >= 1),
        ],
    },
    {
        "name": "rs_x_new_low_rebound",
        "hypothesis": "Bearish continuation: low RS + new low after rebound → downside cluster",
        "table": "bearish_features",
        "feature_a": "beta_adj_rs_20d",
        "feature_b": "new_low_after_rebound_5d",
        "buckets_b": [
            ("no_new_low",  lambda v: v is not None and v == 0),
            ("has_new_low", lambda v: v is not None and v >= 1),
        ],
    },
    {
        "name": "beta_x_rs",
        "hypothesis": "Convexity: high beta + high RS → momentum persistence with leverage",
        "table": "bullish_features",
        "feature_a": "beta_60",
        "feature_b": "beta_adj_rs_20d",
        "buckets_b": "rolling_percentile",  # special marker: use rolling tercile
    },
    # ── Phase A: Trend Quality × RS ────────────────────────
    {
        "name": "rs_x_distance",
        "hypothesis": "Does distance from MA20 add info beyond RS? Or is it redundant?",
        "table": "bullish_features",
        "feature_a": "beta_adj_rs_20d",
        "feature_b": "dist_above_ma20_atr",
        "buckets_b": "rolling_percentile",
    },
    {
        "name": "rs_x_slope",
        "hypothesis": "RS = who is strong. Slope = accelerating? Independent info source?",
        "table": "bullish_features",
        "feature_a": "beta_adj_rs_20d",
        "feature_b": "sma20_slope_10d",
        "buckets_b": "rolling_percentile",
    },
    {
        "name": "rs_x_spread",
        "hypothesis": "Do strong stocks need trend structure (MA separation) to continue?",
        "table": "bullish_features",
        "feature_a": "beta_adj_rs_20d",
        "feature_b": "ma20_ma50_spread_atr",
        "buckets_b": "rolling_percentile",
    },
]


# ── Data loading ──────────────────────────────────────────────────────────


def _load_table_with_prices(
    table: str,
    start: date_type | None,
    end: date_type | None,
) -> pl.DataFrame:
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


def _load_market_regime() -> pl.DataFrame:
    """Load market_regime table for regime-conditioned analysis."""
    with connect(read_only=True) as conn:
        result = conn.execute(
            "SELECT date, regime FROM market_regime ORDER BY date"
        ).fetchall()
    return pl.DataFrame({
        "date": [r[0] for r in result],
        "market_regime": [r[1] for r in result],
    })


def _apply_regime_filter(
    df: pl.DataFrame,
    regime_df: pl.DataFrame,
    regime: str,
) -> pl.DataFrame:
    """Filter df to rows where market_regime matches.

    Join on date, then filter. Rows without regime data are dropped.
    """
    joined = df.join(regime_df, on="date", how="left")
    return joined.filter(pl.col("market_regime") == regime)


# ── Forward return (vectorized) ───────────────────────────────────────────


def _compute_forward_metrics(
    df: pl.DataFrame,
    price_df: pl.DataFrame,
    horizons: list[int],
) -> pl.DataFrame:
    fwd_cols = []
    for h in horizons:
        fwd_close = (
            price_df
            .with_columns(
                pl.col("adj_close").shift(-h).over("stock_id").alias(f"_fwd_close_{h}")
            )
            .select(["stock_id", "date", f"_fwd_close_{h}"])
        )
        fwd_cols.append(fwd_close)

        shift_exprs = [
            pl.col("adj_close").shift(-offset).over("stock_id").alias(f"_s{offset}")
            for offset in range(1, h + 1)
        ]
        if shift_exprs:
            shifted = price_df.with_columns(shift_exprs)
            shift_names = [f"_s{offset}" for offset in range(1, h + 1)]
            shifted = shifted.with_columns([
                pl.min_horizontal(*shift_names).alias(f"_fwd_min_{h}"),
                pl.max_horizontal(*shift_names).alias(f"_fwd_max_{h}"),
            ])
            fwd_cols.append(shifted.select(["stock_id", "date", f"_fwd_min_{h}", f"_fwd_max_{h}"]))

    result = df.clone()
    for fc in fwd_cols:
        result = result.join(fc, on=["stock_id", "date"], how="left")

    cost_pct = ROUND_TRIP_COST_BPS / 10000.0
    for h in horizons:
        result = result.with_columns([
            (pl.col(f"_fwd_close_{h}") / pl.col("adj_close") - 1.0)
                .alias(f"forward_return_{h}d"),
            (pl.col(f"_fwd_min_{h}") / pl.col("adj_close") - 1.0)
                .alias(f"close_mae_{h}d"),
            (pl.col(f"_fwd_max_{h}") / pl.col("adj_close") - 1.0)
                .alias(f"close_mfe_{h}d"),
            (pl.col(f"_fwd_close_{h}") / pl.col("adj_close") - 1.0 - cost_pct)
                .alias(f"simple_net_return_{h}d"),
        ])

    drop_cols = [c for c in result.columns if c.startswith("_fwd_") or c.startswith("_s")]
    return result.drop(drop_cols)


# ── Sample spacing ────────────────────────────────────────────────────────


def _apply_sample_spacing(df: pl.DataFrame, spacing: int) -> pl.DataFrame:
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


# ── Rolling percentile RS bucket (P0-1 fix) ──────────────────────────────


def _assign_rolling_percentile_tercile(
    df: pl.DataFrame,
    feature: str,
    window: int = RS_LOOKBACK_TRADING_DAYS,
) -> pl.Series:
    """Assign RS tercile using rolling percentile (regime-invariant).

    For each (stock_id, date) row:
      1. Collect all values of `feature` across ALL stocks on dates < t
         within a rolling window of `window` trading days.
      2. Compute the value's percentile rank within that cross-sectional
         + temporal window.
      3. Assign tercile: T1 (bottom 33%), T2 (middle), T3 (top 33%).

    This is regime-invariant: RS=5 in a bull market may be T2,
    while RS=5 in a bear market may be T3.

    Implementation: per-stock expanding/rolling approach.
    For computational efficiency, we use a per-date cross-sectional
    percentile with a lookback filter, not a true per-observation
    rolling window over all stocks × dates.
    """
    dates = df["date"].to_list()
    values = df[feature].to_list()
    n = len(values)

    from collections import defaultdict
    from datetime import timedelta

    # Collect all (date, value) pairs sorted by date
    date_value_pairs = sorted(
        [(dates[i], values[i]) for i in range(n) if values[i] is not None],
        key=lambda x: x[0],
    )

    unique_dates = sorted(set(dates))

    # Lookback: ~252 trading days ≈ 378 calendar days.
    # This is a calendar-day approximation, not exact trading sessions.
    # Holiday density / market halts cause ±10% variation in actual
    # trading sessions covered. Acceptable for cross-sectional tercile.
    lookback_days = timedelta(days=int(window * 1.5))

    # Accumulate values by date
    values_by_date: dict = defaultdict(list)
    for d, v in date_value_pairs:
        values_by_date[d].append(v)

    # For each row, compute percentile rank against lookback pool
    labels: list[str | None] = [None] * n

    # Cache: sorted pool per date (reuse across stocks on same date)
    pool_cache: dict = {}

    for i in range(n):
        v = values[i]
        if v is None:
            continue

        d = dates[i]
        if d not in pool_cache:
            # Build pool: all values from dates in [d - lookback, d)
            pool = []
            for ud in unique_dates:
                if ud >= d:
                    break
                if (d - ud).days <= lookback_days.days:
                    pool.extend(values_by_date.get(ud, []))
            pool_cache[d] = sorted(pool) if pool else None

        sorted_pool = pool_cache[d]
        if sorted_pool is None or len(sorted_pool) < 30:
            continue

        # Percentile rank: fraction of pool values <= v
        # Binary search for efficiency
        import bisect
        rank = bisect.bisect_right(sorted_pool, v)
        pctile = rank / len(sorted_pool)

        # Short prefix for labels (e.g. "RS" for beta_adj_rs_20d, "Beta" for beta_60)
        _prefix_map = {
            "beta_adj_rs_20d": "RS",
            "beta_adj_rs_60d": "RS60",
            "beta_60": "Beta",
            "dist_above_ma20_atr": "Dist",
            "sma20_slope_10d": "Slope",
            "ma20_ma50_spread_atr": "Spread",
        }
        prefix = _prefix_map.get(feature, feature[:8])

        if pctile < 1 / 3:
            labels[i] = f"{prefix}_T1_low"
        elif pctile < 2 / 3:
            labels[i] = f"{prefix}_T2_mid"
        else:
            labels[i] = f"{prefix}_T3_high"

    return pl.Series(f"{feature}_bucket", labels, dtype=pl.Utf8)


# ── Feature B bucket assignment ───────────────────────────────────────────


def _assign_semantic_buckets(
    df: pl.DataFrame,
    feature: str,
    bucket_defs: list[tuple[str, object]],
) -> pl.Series:
    values = df[feature].to_list()
    labels = []
    for v in values:
        matched = False
        for label, pred in bucket_defs:
            if pred(v):
                labels.append(label)
                matched = True
                break
        if not matched:
            labels.append(None)
    return pl.Series(f"{feature}_bucket", labels, dtype=pl.Utf8)


# ── Trimmed mean ──────────────────────────────────────────────────────────


def _trimmed_mean(series: pl.Series, pct: float = TRIM_PCT) -> float | None:
    """Trimmed mean (remove pct from each tail). NOT winsorization."""
    vals = series.drop_nulls().sort()
    n = len(vals)
    if n < 4:
        return None
    trim = max(1, int(n * pct))
    trimmed = vals[trim:n - trim]
    if len(trimmed) == 0:
        return None
    return trimmed.mean()


# ── Cell statistics + marginal uplift ─────────────────────────────────────


def _compute_interaction_stats(
    df: pl.DataFrame,
    bucket_a_col: str,
    bucket_b_col: str,
    horizons: list[int],
    interaction_name: str,
) -> list[dict]:
    """Compute stats for each cross-cell, plus marginal baselines and lift.

    interaction_lift = cell_mean - marginal_a_mean - marginal_b_mean + grand_mean

    If lift > 0: the combination adds value beyond what each feature
    contributes independently (genuine interaction effect).
    If lift ≈ 0: the cell return is explained by additive single-feature effects.
    """
    results = []

    valid = df.filter(
        pl.col(bucket_a_col).is_not_null()
        & pl.col(bucket_b_col).is_not_null()
    )
    if valid.is_empty():
        return results

    a_vals = sorted([v for v in valid[bucket_a_col].unique().to_list() if v is not None])
    b_vals = sorted([v for v in valid[bucket_b_col].unique().to_list() if v is not None])

    for h in horizons:
        ret_col = f"forward_return_{h}d"
        net_col = f"simple_net_return_{h}d"
        mae_col = f"close_mae_{h}d"
        mfe_col = f"close_mfe_{h}d"

        if ret_col not in valid.columns:
            continue

        h_valid = valid.filter(pl.col(ret_col).is_not_null())
        if h_valid.is_empty():
            continue

        # Grand mean
        grand_rets = h_valid[ret_col].drop_nulls()
        grand_mean = grand_rets.mean() if len(grand_rets) > 0 else 0.0

        # Marginal means (for lift calculation)
        marginal_a: dict[str, float] = {}
        for a_val in a_vals:
            subset = h_valid.filter(pl.col(bucket_a_col) == a_val)
            rets = subset[ret_col].drop_nulls()
            marginal_a[a_val] = rets.mean() if len(rets) > 0 else grand_mean

        marginal_b: dict[str, float] = {}
        for b_val in b_vals:
            subset = h_valid.filter(pl.col(bucket_b_col) == b_val)
            rets = subset[ret_col].drop_nulls()
            marginal_b[b_val] = rets.mean() if len(rets) > 0 else grand_mean

        # Add marginal rows for comparison
        for a_val in a_vals:
            results.append({
                "interaction": interaction_name,
                "bucket_a": a_val,
                "bucket_b": "_MARGINAL_A_",
                "cell": f"{a_val}|_marginal_",
                "horizon_d": h,
                "sample_count": h_valid.filter(pl.col(bucket_a_col) == a_val).height,
                "is_underpowered": False,
                "mean_return": marginal_a[a_val],
                "trimmed_mean_5pct": None,
                "median_return": None,
                "std_return": None,
                "hit_rate": None,
                "p10_return": None,
                "p90_return": None,
                "mean_simple_net_return": None,
                "mean_close_mae": None,
                "mean_close_mfe": None,
                "interaction_lift": 0.0,  # marginal has no lift by definition
            })

        # Cell stats
        for a_val in a_vals:
            for b_val in b_vals:
                cell = h_valid.filter(
                    (pl.col(bucket_a_col) == a_val)
                    & (pl.col(bucket_b_col) == b_val)
                )
                n = cell.height
                if n == 0:
                    continue

                rets = cell[ret_col].drop_nulls()
                nets = cell[net_col].drop_nulls() if net_col in cell.columns else rets
                maes = cell[mae_col].drop_nulls() if mae_col in cell.columns else pl.Series([])
                mfes = cell[mfe_col].drop_nulls() if mfe_col in cell.columns else pl.Series([])

                cell_mean = rets.mean() if len(rets) > 0 else None

                # Interaction lift: cell - marginal_a - marginal_b + grand
                lift = None
                if cell_mean is not None:
                    lift = (
                        cell_mean
                        - marginal_a.get(a_val, grand_mean)
                        - marginal_b.get(b_val, grand_mean)
                        + grand_mean
                    )

                results.append({
                    "interaction": interaction_name,
                    "bucket_a": a_val,
                    "bucket_b": b_val,
                    "cell": f"{a_val}|{b_val}",
                    "horizon_d": h,
                    "sample_count": n,
                    "is_underpowered": n < MIN_CELL_N,
                    "mean_return": cell_mean,
                    "trimmed_mean_5pct": _trimmed_mean(rets),
                    "median_return": rets.median() if len(rets) > 0 else None,
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
                    "interaction_lift": lift,
                })

    return results


# ── Console output ────────────────────────────────────────────────────────


def _print_interaction(
    stats: list[dict],
    interaction: dict,
) -> None:
    name = interaction["name"]
    rows = [s for s in stats if s["interaction"] == name]
    if not rows:
        return

    print(f"\n{'═' * 95}")
    print(f"  {name}")
    print(f"  Hypothesis: {interaction['hypothesis']}")
    print(f"  Features: {interaction['feature_a']} × {interaction['feature_b']}")
    print(f"  RS buckets: rolling {RS_LOOKBACK_TRADING_DAYS}d percentile tercile")
    print(f"{'═' * 95}")

    print(f"  {'cell':<30} {'hz':>4} {'n':>6} {'⚡':>2} "
          f"{'mean':>8} {'t.mean':>8} {'med':>8} {'hit%':>6} "
          f"{'MAE':>8} {'MFE':>8} {'LIFT':>8}")
    print(f"  {'─' * 93}")

    for r in sorted(rows, key=lambda x: (x["horizon_d"], x["bucket_a"], x["bucket_b"])):
        def _f(v):
            if v is None:
                return "    N/A"
            return f"{v * 100:>+7.2f}%"

        hit = f"{r['hit_rate'] * 100:>5.1f}%" if r["hit_rate"] is not None else "  N/A"
        flag = "⚠" if r["is_underpowered"] else " "
        is_marginal = r["bucket_b"] == "_MARGINAL_A_"
        cell_display = r["cell"]
        if is_marginal:
            cell_display = f"  → {r['bucket_a']} (marginal)"

        lift_str = _f(r["interaction_lift"])
        if is_marginal:
            lift_str = "     ---"

        print(
            f"  {cell_display:<30} {r['horizon_d']:>3}d {r['sample_count']:>6} {flag:>2} "
            f"{_f(r['mean_return'])} {_f(r['trimmed_mean_5pct'])} "
            f"{_f(r['median_return'])} {hit} "
            f"{_f(r['mean_close_mae'])} {_f(r['mean_close_mfe'])} "
            f"{lift_str}"
        )


# ── Main ──────────────────────────────────────────────────────────────────


def run_interaction_study(
    horizons: list[int],
    start: date_type | None = None,
    end: date_type | None = None,
    sample_spacing: int | None = None,
    output_dir: Path | None = None,
    regime: str | None = None,
) -> list[dict]:
    """Run all interaction studies.

    IMPORTANT — `end` semantics:
      `end` filters feature observation dates, NOT price availability.
      Forward returns for observations near `end` use post-end prices
      from the full price series. This is correct for computing forward
      returns but means `end` is NOT a hard information boundary.

      For train/test split: set end = actual_cutoff - max(horizon) to
      ensure no observation's forward return reaches into the test period.
    """
    if output_dir is None:
        output_dir = Path("research/outputs")
    output_dir.mkdir(parents=True, exist_ok=True)

    if sample_spacing is None:
        sample_spacing = max(horizons)

    table_cache: dict[str, pl.DataFrame] = {}

    print("Loading price series...")
    price_df = _load_price_series()
    print(f"  price rows: {price_df.height}")

    # Regime filter (optional)
    regime_df = None
    if regime:
        regime_df = _load_market_regime()
        n_regime = regime_df.filter(pl.col("market_regime") == regime).height
        print(f"  regime filter: '{regime}' ({n_regime} trading days)")

    all_stats: list[dict] = []

    for interaction in INTERACTIONS:
        name = interaction["name"]
        table = interaction["table"]
        fa = interaction["feature_a"]
        fb = interaction["feature_b"]

        print(f"\n{'=' * 95}")
        print(f"Interaction: {name}")
        print(f"  table: {table}, features: {fa} × {fb}")

        if table not in table_cache:
            print(f"  Loading {table}...")
            df = _load_table_with_prices(table, start, end)
            print(f"    rows: {df.height}, stocks: {df['stock_id'].n_unique()}")

            print(f"    Computing forward returns...")
            df = _compute_forward_metrics(df, price_df, horizons)

            pre = df.height
            df = _apply_sample_spacing(df, sample_spacing)
            print(f"    Spacing: {pre} → {df.height}")

            # Regime filter (apply after spacing, before bucket computation)
            if regime and regime_df is not None:
                pre_regime = df.height
                df = _apply_regime_filter(df, regime_df, regime)
                print(f"    Regime filter '{regime}': {pre_regime} → {df.height}")

            table_cache[table] = df
        else:
            print(f"  Using cached {table}")

        df = table_cache[table]

        if fa not in df.columns:
            print(f"  ⚠ {fa} not in table, skipping")
            continue
        if fb not in df.columns:
            print(f"  ⚠ {fb} not in table, skipping")
            continue

        # Feature A: rolling percentile tercile (computed once per feature, cached)
        if f"{fa}_bucket" not in df.columns:
            print(f"    Computing rolling {RS_LOOKBACK_TRADING_DAYS}d percentile for {fa}...")
            bucket_a = _assign_rolling_percentile_tercile(df, fa)
            df = df.with_columns(bucket_a)
            table_cache[table] = df

            counts = df[f"{fa}_bucket"].value_counts().sort("count", descending=True)
            print(f"    {fa} tercile distribution:")
            for row in counts.iter_rows(named=True):
                print(f"      {row[f'{fa}_bucket']}: {row['count']}")

        # Feature B: semantic bucket or rolling percentile
        if interaction["buckets_b"] == "rolling_percentile":
            # Both features use rolling percentile (e.g. beta × RS)
            if f"{fb}_bucket" not in df.columns:
                print(f"    Computing rolling {RS_LOOKBACK_TRADING_DAYS}d percentile for {fb}...")
                bucket_b = _assign_rolling_percentile_tercile(df, fb)
                df = df.with_columns(bucket_b)
                table_cache[table] = df  # update cache
            df_work = df
        else:
            bucket_b = _assign_semantic_buckets(df, fb, interaction["buckets_b"])
            df_work = df.with_columns(bucket_b)

        # Log B distribution
        counts_b = df_work[f"{fb}_bucket"].value_counts().sort("count", descending=True)
        print(f"  {fb} buckets:")
        for row in counts_b.iter_rows(named=True):
            print(f"    {row[f'{fb}_bucket']}: {row['count']}")

        # Compute cell stats with marginal lift
        stats = _compute_interaction_stats(
            df_work,
            f"{fa}_bucket",
            f"{fb}_bucket",
            horizons,
            name,
        )
        all_stats.extend(stats)
        _print_interaction(stats, interaction)

    if all_stats:
        stats_df = pl.DataFrame(all_stats)
        suffix = f"_{regime}" if regime else ""
        csv_path = output_dir / f"feature_interaction_baseline{suffix}.csv"
        stats_df.write_csv(csv_path)
        print(f"\nCSV written: {csv_path} ({len(all_stats)} rows)")

        underpowered = sum(1 for s in all_stats if s.get("is_underpowered"))
        print(f"Underpowered cells (n < {MIN_CELL_N}): {underpowered} / {len(all_stats)}")

        # Summary: strongest interaction lifts
        real_cells = [s for s in all_stats if s["bucket_b"] != "_MARGINAL_A_" and s["interaction_lift"] is not None]
        if real_cells:
            print(f"\nTop 10 interaction lifts (20d horizon):")
            top_lifts = sorted(
                [s for s in real_cells if s["horizon_d"] == max(horizons) and not s["is_underpowered"]],
                key=lambda x: abs(x["interaction_lift"] or 0),
                reverse=True,
            )[:10]
            for s in top_lifts:
                print(f"  {s['cell']:<30} lift={s['interaction_lift']*100:>+6.2f}%  "
                      f"mean={s['mean_return']*100:>+6.2f}%  n={s['sample_count']}")

    return all_stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Phase 0 v2: Feature interaction study"
    )
    parser.add_argument("--horizons", type=str, default="5,10,20")
    parser.add_argument("--start", type=str, default=None)
    parser.add_argument("--end", type=str, default=None)
    parser.add_argument("--sample-spacing", type=int, default=None)
    parser.add_argument("--output-dir", type=str, default=None)
    parser.add_argument(
        "--regime", type=str, default=None,
        choices=["bull", "bear", "crisis", "neutral"],
        help="Filter to specific market regime (from market_regime table)",
    )
    args = parser.parse_args()

    horizons = [int(h.strip()) for h in args.horizons.split(",")]
    start = date_type.fromisoformat(args.start) if args.start else None
    end = date_type.fromisoformat(args.end) if args.end else None

    print(f"Feature Interaction Study — Phase 0 v3")
    print(f"  horizons:        {horizons}")
    print(f"  RS bucket:       rolling {RS_LOOKBACK_TRADING_DAYS}d percentile tercile")
    print(f"  sample_spacing:  {args.sample_spacing or f'auto ({max(horizons)})'}")
    print(f"  regime:          {args.regime or 'all (no filter)'}")
    print(f"  cost:            {ROUND_TRIP_COST_BPS:.1f} bps")
    print(f"  min_cell_n:      {MIN_CELL_N}")
    print(f"  trim_pct:        {TRIM_PCT * 100:.0f}%")
    print(f"  interactions:    {len(INTERACTIONS)}")
    print(f"  CAVEAT: spacing={args.sample_spacing or max(horizons)} does not eliminate overlap.")
    print()

    stats = run_interaction_study(
        horizons=horizons,
        start=start,
        end=end,
        sample_spacing=args.sample_spacing,
        output_dir=Path(args.output_dir) if args.output_dir else None,
        regime=args.regime,
    )

    print(f"\nTotal rows: {len(stats)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
