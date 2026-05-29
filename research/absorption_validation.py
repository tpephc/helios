#!/usr/bin/env python3
# research/absorption_validation.py
"""Absorption validation pack — Phase 0 follow-up.

Phase 0 finding: RS_T3 + failed_breakdown (bear regime) has +0.94%
interaction lift. This script validates that finding with:

1. Absorption count granularity (0 / 1 / 2+) per RS tercile
2. Beta × absorption cross (within RS_T3 only) WITH interaction lift
3. Volume × absorption cross (within RS_T3 only)
4. RS_T3 absorption baseline distribution diagnostics

Pre-filter: analyses 2-4 are RS_T3 only (conditional study).

REGIME SEMANTICS: --regime filters by entry-date regime only.
A sample with entry-date in bear regime may have its forward return
span partially or entirely in a bull regime. This measures "what
happens to positions OPENED during bear regime", NOT "returns while
market stays bearish". This is intentional: it matches the operational
decision point (enter or not on day T).

Sample spacing: per-horizon (5d→5, 10d→10, 20d→20) applied inside
stats computation. Bucket assignment runs on full data for better
quantile estimation. This gives ~4x more samples for 5d horizon
compared to the previous global spacing=20 approach.

Usage:
  uv run python research/absorption_validation.py
  uv run python research/absorption_validation.py --regime bear
  uv run python research/absorption_validation.py --regime bull

Version: v0.1.0 (2026-05-29)
"""
from __future__ import annotations

import argparse
import bisect
import sys
from collections import defaultdict
from datetime import date as date_type, timedelta
from math import isnan
from pathlib import Path

import polars as pl

from data.database import connect
from utils.logger import get_logger

logger = get_logger(__name__)

# Commission: 0.1425% per side × 2 sides = 0.285%
# Tax: 0.3% on sell side only
# Round-trip: 0.285% + 0.3% = 0.585% = 58.5 bps
ROUND_TRIP_COST_BPS = 58.5

TRIM_PCT = 0.05
# Target ~252 trading days. Implemented as calendar-day approximation
# (×1.5 ≈ 378 calendar days). Holiday density / market halts cause
# ±10% variation in actual trading sessions covered.
RS_LOOKBACK_CALENDAR_DAYS = 378
MIN_CELL_N = 30
HORIZONS = [5, 10, 20]


# ── Data loading ──────────────────────────────────────────────────────────


def _load_features_with_prices(
    start: date_type | None, end: date_type | None,
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
        FROM bullish_features f
        JOIN daily_price_adj p ON f.stock_id = p.stock_id AND f.date = p.date
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
            "SELECT stock_id, date, adj_close FROM daily_price_adj "
            "WHERE adj_close IS NOT NULL AND adj_close > 0 "
            "ORDER BY stock_id, date"
        ).fetchall()
    return pl.DataFrame({
        "stock_id": [r[0] for r in result],
        "date": [r[1] for r in result],
        "adj_close": [r[2] for r in result],
    })


def _load_market_regime() -> pl.DataFrame:
    with connect(read_only=True) as conn:
        result = conn.execute(
            "SELECT date, regime FROM market_regime ORDER BY date"
        ).fetchall()
    return pl.DataFrame({
        "date": [r[0] for r in result],
        "market_regime": [r[1] for r in result],
    })


# ── Forward return (vectorized) ───────────────────────────────────────────


def _compute_forward_metrics(
    df: pl.DataFrame, price_df: pl.DataFrame,
) -> pl.DataFrame:
    fwd_cols = []
    for h in HORIZONS:
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
    for h in HORIZONS:
        result = result.with_columns([
            (pl.col(f"_fwd_close_{h}") / pl.col("adj_close") - 1.0).alias(f"fwd_{h}d"),
            (pl.col(f"_fwd_min_{h}") / pl.col("adj_close") - 1.0).alias(f"mae_{h}d"),
            (pl.col(f"_fwd_max_{h}") / pl.col("adj_close") - 1.0).alias(f"mfe_{h}d"),
            (pl.col(f"_fwd_close_{h}") / pl.col("adj_close") - 1.0 - cost_pct).alias(f"net_{h}d"),
        ])

    drop_cols = [c for c in result.columns if c.startswith("_fwd_") or c.startswith("_s")]
    return result.drop(drop_cols)


# ── Generic rolling percentile tercile ────────────────────────────────────


def _assign_rolling_tercile(
    df: pl.DataFrame,
    feature: str,
    prefix: str,
) -> pl.Series:
    """Rolling cross-sectional percentile tercile.

    For each row, computes the feature's percentile rank against all
    values of that feature across ALL stocks on dates strictly < t,
    within a lookback window of RS_LOOKBACK_CALENDAR_DAYS.

    Returns Series with labels: {prefix}_T1, {prefix}_T2, {prefix}_T3.
    """
    dates = df["date"].to_list()
    values = df[feature].to_list()
    n = len(values)

    date_value_pairs = sorted(
        [(dates[i], values[i]) for i in range(n) if values[i] is not None],
        key=lambda x: x[0],
    )
    unique_dates = sorted(set(dates))
    lookback = timedelta(days=RS_LOOKBACK_CALENDAR_DAYS)

    values_by_date: dict = defaultdict(list)
    for d, v in date_value_pairs:
        values_by_date[d].append(v)

    pool_cache: dict = {}
    labels: list[str | None] = [None] * n

    for i in range(n):
        v = values[i]
        if v is None:
            continue
        d = dates[i]
        if d not in pool_cache:
            pool = []
            for ud in unique_dates:
                if ud >= d:
                    break
                if (d - ud).days <= lookback.days:
                    pool.extend(values_by_date.get(ud, []))
            pool_cache[d] = sorted(pool) if pool else None

        sorted_pool = pool_cache[d]
        if sorted_pool is None or len(sorted_pool) < 30:
            continue
        rank = bisect.bisect_right(sorted_pool, v)
        pctile = rank / len(sorted_pool)
        if pctile < 1 / 3:
            labels[i] = f"{prefix}_T1"
        elif pctile < 2 / 3:
            labels[i] = f"{prefix}_T2"
        else:
            labels[i] = f"{prefix}_T3"

    return pl.Series(f"{feature}_tercile", labels, dtype=pl.Utf8)


# ── Trimmed mean ──────────────────────────────────────────────────────────


def _trimmed_mean(s: pl.Series) -> float | None:
    vals = s.drop_nulls().sort()
    n = len(vals)
    if n < 4:
        return None
    trim = max(1, int(n * TRIM_PCT))
    return vals[trim:n - trim].mean()


# ── Per-horizon spacing helper ────────────────────────────────────────────


def _subsample_for_horizon(df: pl.DataFrame, h: int) -> pl.DataFrame:
    """Per-stock spacing = h for non-overlapping forward returns."""
    if h <= 1:
        return df
    return (
        df
        .with_columns(
            (pl.arange(0, pl.len()).over("stock_id") % h).alias("_h_mod")
        )
        .filter(pl.col("_h_mod") == 0)
        .drop("_h_mod")
    )


# ── Cell statistics ───────────────────────────────────────────────────────


def _cell_stats(df: pl.DataFrame, label: str) -> list[dict]:
    results = []
    for h in HORIZONS:
        ret_col = f"fwd_{h}d"
        mae_col = f"mae_{h}d"
        mfe_col = f"mfe_{h}d"
        net_col = f"net_{h}d"
        if ret_col not in df.columns:
            continue
        # Per-horizon spacing: 5d→5, 10d→10, 20d→20
        spaced = _subsample_for_horizon(df, h)
        valid = spaced.filter(pl.col(ret_col).is_not_null())
        n = valid.height
        if n == 0:
            continue
        rets = valid[ret_col].drop_nulls()
        maes = valid[mae_col].drop_nulls() if mae_col in valid.columns else pl.Series([])
        mfes = valid[mfe_col].drop_nulls() if mfe_col in valid.columns else pl.Series([])

        # Net return: gross - cost (deterministic, no sampling difference)
        cost_pct = ROUND_TRIP_COST_BPS / 10000.0
        net_mean = (rets.mean() - cost_pct) if len(rets) > 0 else None

        results.append({
            "cell": label,
            "horizon": f"{h}d",
            "n": n,
            "underpowered": n < MIN_CELL_N,
            "mean": rets.mean(),
            "trimmed_mean": _trimmed_mean(rets),
            "median": rets.median(),
            "std": rets.std() if n > 1 else None,
            "hit_pct": (rets > 0).sum() / len(rets) * 100 if len(rets) > 0 else None,
            "p10": rets.quantile(0.10) if n >= 10 else None,
            "p90": rets.quantile(0.90) if n >= 10 else None,
            "mae": maes.mean() if len(maes) > 0 else None,
            "mfe": mfes.mean() if len(mfes) > 0 else None,
            "net_mean": net_mean,
        })
    return results


def _print_table(rows: list[dict], title: str) -> None:
    if not rows:
        print(f"  (no data for {title})")
        return
    print(f"\n{'─' * 105}")
    print(f"  {title}")
    print(f"{'─' * 105}")
    print(f"  {'cell':<35} {'hz':>4} {'n':>6} {'⚡':>2} "
          f"{'mean':>8} {'t.mean':>8} {'med':>8} {'hit%':>6} "
          f"{'p10':>8} {'p90':>8} {'MAE':>8} {'MFE':>8}")
    print(f"  {'─' * 103}")
    for r in rows:
        def _f(v):
            if v is None:
                return "    N/A"
            return f"{v * 100:>+7.2f}%"
        flag = "⚠" if r["underpowered"] else " "
        hit = f"{r['hit_pct']:>5.1f}%" if r["hit_pct"] is not None else "  N/A"
        print(
            f"  {r['cell']:<35} {r['horizon']:>4} {r['n']:>6} {flag:>2} "
            f"{_f(r['mean'])} {_f(r['trimmed_mean'])} {_f(r['median'])} {hit} "
            f"{_f(r['p10'])} {_f(r['p90'])} {_f(r['mae'])} {_f(r['mfe'])}"
        )


def _print_lift_table(rows: list[dict], title: str) -> None:
    """Print table with interaction lift column."""
    if not rows:
        print(f"  (no data for {title})")
        return
    print(f"\n{'─' * 115}")
    print(f"  {title}")
    print(f"{'─' * 115}")
    print(f"  {'cell':<35} {'hz':>4} {'n':>6} {'⚡':>2} "
          f"{'mean':>8} {'t.mean':>8} {'med':>8} {'hit%':>6} "
          f"{'MAE':>8} {'MFE':>8} {'LIFT':>8}")
    print(f"  {'─' * 113}")
    for r in rows:
        def _f(v):
            if v is None:
                return "    N/A"
            return f"{v * 100:>+7.2f}%"
        flag = "⚠" if r.get("underpowered") else " "
        hit = f"{r['hit_pct']:>5.1f}%" if r.get("hit_pct") is not None else "  N/A"
        lift = _f(r.get("lift"))
        if r.get("is_marginal"):
            lift = "     ---"
        print(
            f"  {r['cell']:<35} {r['horizon']:>4} {r['n']:>6} {flag:>2} "
            f"{_f(r['mean'])} {_f(r.get('trimmed_mean'))} {_f(r.get('median'))} {hit} "
            f"{_f(r.get('mae'))} {_f(r.get('mfe'))} {lift}"
        )


# ── Interaction lift computation ──────────────────────────────────────────


def _compute_cells_with_lift(
    df: pl.DataFrame,
    feature_a_col: str,
    feature_a_vals: list[str],
    feature_b_col: str,
    feature_b_vals: list[str],
    label_fn,
) -> list[dict]:
    """Compute cell stats with marginal interaction lift.

    lift = cell_mean - marginal_A - marginal_B + grand_mean
    """
    all_rows = []

    for h in HORIZONS:
        ret_col = f"fwd_{h}d"
        mae_col = f"mae_{h}d"
        mfe_col = f"mfe_{h}d"
        if ret_col not in df.columns:
            continue

        h_valid = df.filter(pl.col(ret_col).is_not_null())
        # Per-horizon spacing
        h_valid = _subsample_for_horizon(h_valid, h)
        if h_valid.is_empty():
            continue

        grand_mean = h_valid[ret_col].mean()

        # Marginal A
        marginal_a: dict[str, float] = {}
        for a_val in feature_a_vals:
            sub = h_valid.filter(pl.col(feature_a_col) == a_val)
            rets = sub[ret_col].drop_nulls()
            marginal_a[a_val] = rets.mean() if len(rets) > 0 else grand_mean

        # Marginal B
        marginal_b: dict[str, float] = {}
        for b_val in feature_b_vals:
            sub = h_valid.filter(pl.col(feature_b_col) == b_val)
            rets = sub[ret_col].drop_nulls()
            marginal_b[b_val] = rets.mean() if len(rets) > 0 else grand_mean

        # Marginal rows
        for a_val in feature_a_vals:
            sub = h_valid.filter(pl.col(feature_a_col) == a_val)
            all_rows.append({
                "cell": f"  → {a_val} (marginal)",
                "horizon": f"{h}d",
                "n": sub.height,
                "mean": marginal_a[a_val],
                "hit_pct": None,
                "is_marginal": True,
                "lift": None,
            })

        # Cell rows
        for a_val in feature_a_vals:
            for b_val in feature_b_vals:
                cell = h_valid.filter(
                    (pl.col(feature_a_col) == a_val)
                    & (pl.col(feature_b_col) == b_val)
                )
                n = cell.height
                if n == 0:
                    continue
                rets = cell[ret_col].drop_nulls()
                maes = cell[mae_col].drop_nulls() if mae_col in cell.columns else pl.Series([])
                mfes = cell[mfe_col].drop_nulls() if mfe_col in cell.columns else pl.Series([])

                cell_mean = rets.mean() if len(rets) > 0 else None
                lift = None
                if cell_mean is not None:
                    lift = cell_mean - marginal_a[a_val] - marginal_b[b_val] + grand_mean

                all_rows.append({
                    "cell": label_fn(a_val, b_val),
                    "horizon": f"{h}d",
                    "n": n,
                    "underpowered": n < MIN_CELL_N,
                    "mean": cell_mean,
                    "trimmed_mean": _trimmed_mean(rets),
                    "median": rets.median() if len(rets) > 0 else None,
                    "hit_pct": (rets > 0).sum() / len(rets) * 100 if len(rets) > 0 else None,
                    "p10": rets.quantile(0.10) if n >= 10 else None,
                    "p90": rets.quantile(0.90) if n >= 10 else None,
                    "mae": maes.mean() if len(maes) > 0 else None,
                    "mfe": mfes.mean() if len(mfes) > 0 else None,
                    "lift": lift,
                    "is_marginal": False,
                })

    return all_rows


# ── Main analysis ─────────────────────────────────────────────────────────


def run_validation(
    regime: str | None = None,
    start: date_type | None = None,
    end: date_type | None = None,
    output_dir: Path | None = None,
) -> list[dict]:
    if output_dir is None:
        output_dir = Path(__file__).parent / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Loading data...")
    df = _load_features_with_prices(start, end)
    price_df = _load_price_series()
    print(f"  features: {df.height} rows, {df['stock_id'].n_unique()} stocks")

    print("Computing forward returns...")
    df = _compute_forward_metrics(df, price_df)

    # Per-horizon spacing (5d→5, 10d→10, 20d→20) applied in stats, not here.
    # Bucket assignment runs on full data for better quantile estimation.
    print(f"  rows after forward returns: {df.height}")

    # Regime filter
    if regime:
        regime_df = _load_market_regime()
        df = df.join(regime_df, on="date", how="left")
        pre_r = df.height
        df = df.filter(pl.col("market_regime") == regime)
        print(f"  regime '{regime}' (entry-date only): {pre_r} → {df.height}")

    # Assign terciles (generic function)
    print("Computing terciles...")
    df = df.with_columns(_assign_rolling_tercile(df, "beta_adj_rs_20d", "RS"))
    df = df.with_columns(_assign_rolling_tercile(df, "beta_60", "Beta"))

    rs_counts = df["beta_adj_rs_20d_tercile"].value_counts().sort("count", descending=True)
    print(f"  RS: {dict(zip(rs_counts['beta_adj_rs_20d_tercile'].to_list(), rs_counts['count'].to_list()))}")

    # Absorption bucket column for lift computation
    df = df.with_columns(
        pl.when(pl.col("failed_breakdown_count_10d") >= 1)
        .then(pl.lit("has_abs"))
        .otherwise(pl.lit("no_abs"))
        .alias("abs_bucket")
    )

    all_stats: list[dict] = []

    # ══════════════════════════════════════════════════════════
    # Analysis 1: Absorption count granularity per RS tercile
    # ══════════════════════════════════════════════════════════
    print("\n" + "=" * 105)
    print("  ANALYSIS 1: Absorption count granularity per RS tercile")

    for rs in ["RS_T1", "RS_T2", "RS_T3"]:
        rs_df = df.filter(pl.col("beta_adj_rs_20d_tercile") == rs)
        if rs_df.is_empty():
            continue
        rows = []
        for label, pred_val, pred_op in [("abs=0", 0, "eq"), ("abs=1", 1, "eq"), ("abs=2+", 2, "ge")]:
            if pred_op == "eq":
                cell_df = rs_df.filter(pl.col("failed_breakdown_count_10d") == pred_val)
            else:
                cell_df = rs_df.filter(pl.col("failed_breakdown_count_10d") >= pred_val)
            rows.extend(_cell_stats(cell_df, f"{rs}|{label}"))
        all_stats.extend(rows)
        _print_table(rows, f"Absorption count — {rs}")

    # ══════════════════════════════════════════════════════════
    # Analysis 2: Beta × absorption (RS_T3 only) WITH LIFT
    # ══════════════════════════════════════════════════════════
    print("\n" + "=" * 115)
    print("  ANALYSIS 2: Beta × Absorption (RS_T3 only) — with interaction lift")

    rs3_df = df.filter(pl.col("beta_adj_rs_20d_tercile") == "RS_T3")
    if not rs3_df.is_empty():
        beta_vals = sorted([
            v for v in rs3_df["beta_60_tercile"].unique().to_list()
            if v is not None
        ])
        abs_vals = ["no_abs", "has_abs"]

        rows = _compute_cells_with_lift(
            rs3_df,
            "beta_60_tercile", beta_vals,
            "abs_bucket", abs_vals,
            label_fn=lambda a, b: f"RS_T3|{a}|{b}",
        )
        all_stats.extend(rows)
        _print_lift_table(rows, "Beta × Absorption (RS_T3 filtered) — interaction lift")

    # ══════════════════════════════════════════════════════════
    # Analysis 3: Absorption × volume (RS_T3 only)
    # ══════════════════════════════════════════════════════════
    print("\n" + "=" * 105)
    print("  ANALYSIS 3: Absorption × Volume breakout (RS_T3 only)")

    if not rs3_df.is_empty():
        rows = []
        for abs_label, abs_val in [("no_abs", 0), ("has_abs", 1)]:
            for vol_label, vol_val in [("no_vol", 0), ("has_vol", 1)]:
                abs_cond = (
                    pl.col("failed_breakdown_count_10d") == 0 if abs_val == 0
                    else pl.col("failed_breakdown_count_10d") >= 1
                )
                vol_cond = (
                    pl.col("volume_breakout_days_5d") == 0 if vol_val == 0
                    else pl.col("volume_breakout_days_5d") >= 1
                )
                cell_df = rs3_df.filter(abs_cond & vol_cond)
                rows.extend(_cell_stats(cell_df, f"RS_T3|{abs_label}|{vol_label}"))
        all_stats.extend(rows)
        _print_table(rows, "Absorption × Volume (RS_T3 filtered)")

    # ══════════════════════════════════════════════════════════
    # Analysis 4: RS_T3 absorption baseline comparison
    # ══════════════════════════════════════════════════════════
    print("\n" + "=" * 105)
    print("  ANALYSIS 4: RS_T3 baseline distribution comparison")

    if not rs3_df.is_empty():
        rows = []
        rows.extend(_cell_stats(rs3_df, "RS_T3 (all)"))
        rows.extend(_cell_stats(
            rs3_df.filter(pl.col("failed_breakdown_count_10d") >= 1),
            "RS_T3 + has_absorption",
        ))
        rows.extend(_cell_stats(
            rs3_df.filter(pl.col("failed_breakdown_count_10d") == 0),
            "RS_T3 + no_absorption",
        ))
        all_stats.extend(rows)
        _print_table(rows, "RS_T3 absorption vs no-absorption baseline")

    # ── Write CSV ─────────────────────────────────────────────
    if all_stats:
        suffix = f"_{regime}" if regime else ""
        stats_df = pl.DataFrame(all_stats)
        csv_path = output_dir / f"absorption_validation{suffix}.csv"
        stats_df.write_csv(csv_path)
        print(f"\nCSV: {csv_path} ({len(all_stats)} rows)")

    return all_stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Absorption validation pack (Phase 0 follow-up)"
    )
    parser.add_argument("--regime", type=str, default=None,
                        choices=["bull", "bear", "crisis", "neutral"])
    parser.add_argument("--start", type=str, default=None)
    parser.add_argument("--end", type=str, default=None)
    parser.add_argument("--output-dir", type=str, default=None)
    args = parser.parse_args()

    start = date_type.fromisoformat(args.start) if args.start else None
    end = date_type.fromisoformat(args.end) if args.end else None

    print(f"Absorption Validation Pack v3")
    print(f"  regime:  {args.regime or 'all (entry-date filter only)'}")
    print(f"  cost:    {ROUND_TRIP_COST_BPS:.1f} bps")
    print(f"  spacing: per-horizon (5d→5, 10d→10, 20d→20)")
    print()

    run_validation(
        regime=args.regime,
        start=start, end=end,
        output_dir=Path(args.output_dir) if args.output_dir else None,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
