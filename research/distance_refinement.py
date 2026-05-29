#!/usr/bin/env python3
# research/distance_refinement.py
"""RS_T3 × Distance pullback entry — deep refinement.

Phase A confirmed finding: RS_T3 + Dist_T1 (close to MA20) has the
strongest interaction lift (+1.66%, 20d) and highest hit rate (62.3%).

This script validates and refines with:
1. Regime split (bull/bear) — does pullback entry work in both?
2. Beta cross — which beta bucket benefits most from pullback?
3. Distance threshold analysis — optimal ATR distance for entry
4. Holding period stability (5d/10d/20d consistency)
5. Distribution diagnostics (MAE/MFE/p10/p90)

Pre-filter: RS_T3 only (rolling percentile top tercile).

REGIME SEMANTICS: --regime filters by entry-date regime only.

Version: v0.1.0 (2026-05-29)
"""
from __future__ import annotations

import argparse
import bisect
import sys
from collections import defaultdict
from datetime import date as date_type, timedelta
from pathlib import Path

import polars as pl

from data.database import connect
from utils.logger import get_logger

logger = get_logger(__name__)

# Commission: 0.1425% per side × 2 = 0.285% + Tax: 0.3% sell only = 0.585%
ROUND_TRIP_COST_BPS = 58.5
TRIM_PCT = 0.05
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


# ── Forward return ────────────────────────────────────────────────────────


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

    for h in HORIZONS:
        result = result.with_columns([
            (pl.col(f"_fwd_close_{h}") / pl.col("adj_close") - 1.0).alias(f"fwd_{h}d"),
            (pl.col(f"_fwd_min_{h}") / pl.col("adj_close") - 1.0).alias(f"mae_{h}d"),
            (pl.col(f"_fwd_max_{h}") / pl.col("adj_close") - 1.0).alias(f"mfe_{h}d"),
        ])

    drop_cols = [c for c in result.columns if c.startswith("_fwd_") or c.startswith("_s")]
    return result.drop(drop_cols)


# ── Rolling percentile tercile ────────────────────────────────────────────


def _assign_rolling_tercile(
    df: pl.DataFrame, feature: str, prefix: str,
) -> pl.Series:
    dates = df["date"].to_list()
    values = df[feature].to_list()
    n = len(values)
    lookback = timedelta(days=RS_LOOKBACK_CALENDAR_DAYS)

    date_value_pairs = sorted(
        [(dates[i], values[i]) for i in range(n) if values[i] is not None],
        key=lambda x: x[0],
    )
    unique_dates = sorted(set(dates))
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


# ── Per-horizon spacing ──────────────────────────────────────────────────


def _subsample(df: pl.DataFrame, h: int) -> pl.DataFrame:
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


# ── Stats helpers ─────────────────────────────────────────────────────────


def _trimmed_mean(s: pl.Series) -> float | None:
    vals = s.drop_nulls().sort()
    n = len(vals)
    if n < 4:
        return None
    trim = max(1, int(n * TRIM_PCT))
    return vals[trim:n - trim].mean()


def _cell_stats(df: pl.DataFrame, label: str) -> list[dict]:
    results = []
    for h in HORIZONS:
        ret_col = f"fwd_{h}d"
        mae_col = f"mae_{h}d"
        mfe_col = f"mfe_{h}d"
        spaced = _subsample(df, h)
        valid = spaced.filter(pl.col(ret_col).is_not_null())
        n = valid.height
        if n == 0:
            continue
        rets = valid[ret_col].drop_nulls()
        maes = valid[mae_col].drop_nulls() if mae_col in valid.columns else pl.Series([])
        mfes = valid[mfe_col].drop_nulls() if mfe_col in valid.columns else pl.Series([])
        cost_pct = ROUND_TRIP_COST_BPS / 10000.0

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
            "net_mean": (rets.mean() - cost_pct) if len(rets) > 0 else None,
        })
    return results


def _print_table(rows: list[dict], title: str) -> None:
    if not rows:
        print(f"  (no data for {title})")
        return
    print(f"\n{'─' * 110}")
    print(f"  {title}")
    print(f"{'─' * 110}")
    print(f"  {'cell':<40} {'hz':>4} {'n':>6} {'⚡':>2} "
          f"{'mean':>8} {'t.mean':>8} {'med':>8} {'hit%':>6} "
          f"{'p10':>8} {'p90':>8} {'MAE':>8} {'MFE':>8} {'net':>8}")
    print(f"  {'─' * 108}")
    for r in rows:
        def _f(v):
            return f"{v * 100:>+7.2f}%" if v is not None else "    N/A"
        flag = "⚠" if r["underpowered"] else " "
        hit = f"{r['hit_pct']:>5.1f}%" if r["hit_pct"] is not None else "  N/A"
        print(
            f"  {r['cell']:<40} {r['horizon']:>4} {r['n']:>6} {flag:>2} "
            f"{_f(r['mean'])} {_f(r['trimmed_mean'])} {_f(r['median'])} {hit} "
            f"{_f(r['p10'])} {_f(r['p90'])} {_f(r['mae'])} {_f(r['mfe'])} {_f(r['net_mean'])}"
        )


# ── Main analysis ─────────────────────────────────────────────────────────


def run_refinement(
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

    # Regime join (before filter, for regime column availability)
    regime_df = _load_market_regime()
    df = df.join(regime_df, on="date", how="left")

    if regime:
        pre = df.height
        df = df.filter(pl.col("market_regime") == regime)
        print(f"  regime '{regime}' (entry-date): {pre} → {df.height}")

    print("Computing terciles...")
    df = df.with_columns(_assign_rolling_tercile(df, "beta_adj_rs_20d", "RS"))
    df = df.with_columns(_assign_rolling_tercile(df, "beta_60", "Beta"))
    df = df.with_columns(_assign_rolling_tercile(df, "dist_above_ma20_atr", "Dist"))

    # Filter to RS_T3 only
    rs3 = df.filter(pl.col("beta_adj_rs_20d_tercile") == "RS_T3")
    print(f"  RS_T3 filtered: {rs3.height} rows")

    all_stats: list[dict] = []

    # ══════════════════════════════════════════════════════════
    # Analysis 1: Distance tercile baseline (RS_T3 only)
    # ══════════════════════════════════════════════════════════
    print("\n" + "=" * 110)
    print("  ANALYSIS 1: RS_T3 Distance tercile baseline")
    rows = []
    rows.extend(_cell_stats(rs3, "RS_T3 (all)"))
    for dt in ["Dist_T1", "Dist_T2", "Dist_T3"]:
        rows.extend(_cell_stats(
            rs3.filter(pl.col("dist_above_ma20_atr_tercile") == dt),
            f"RS_T3|{dt}",
        ))
    all_stats.extend(rows)
    _print_table(rows, "RS_T3 by distance tercile")

    # ══════════════════════════════════════════════════════════
    # Analysis 2: Distance × Beta cross (RS_T3 only)
    # ══════════════════════════════════════════════════════════
    print("\n" + "=" * 110)
    print("  ANALYSIS 2: Distance × Beta cross (RS_T3 only)")
    rows = []
    for dt in ["Dist_T1", "Dist_T2", "Dist_T3"]:
        for bt in ["Beta_T1", "Beta_T2", "Beta_T3"]:
            cell = rs3.filter(
                (pl.col("dist_above_ma20_atr_tercile") == dt)
                & (pl.col("beta_60_tercile") == bt)
            )
            rows.extend(_cell_stats(cell, f"RS_T3|{dt}|{bt}"))
    all_stats.extend(rows)
    _print_table(rows, "Distance × Beta (RS_T3 filtered)")

    # ══════════════════════════════════════════════════════════
    # Analysis 3: Distance granularity (quintile-like ATR thresholds)
    # ══════════════════════════════════════════════════════════
    print("\n" + "=" * 110)
    print("  ANALYSIS 3: Distance granularity (ATR thresholds, RS_T3)")
    rows = []
    # Define fixed ATR distance buckets
    thresholds = [
        ("dist<-1 (below MA20)", lambda d: d < -1.0),
        ("-1≤dist<0 (just below)", lambda d: (d >= -1.0) & (d < 0.0)),
        ("0≤dist<0.5 (on MA20)", lambda d: (d >= 0.0) & (d < 0.5)),
        ("0.5≤dist<1 (slightly above)", lambda d: (d >= 0.5) & (d < 1.0)),
        ("1≤dist<2 (above)", lambda d: (d >= 1.0) & (d < 2.0)),
        ("2≤dist<3 (extended)", lambda d: (d >= 2.0) & (d < 3.0)),
        ("dist≥3 (far extended)", lambda d: d >= 3.0),
    ]
    for label, pred in thresholds:
        cell = rs3.filter(pred(pl.col("dist_above_ma20_atr")))
        rows.extend(_cell_stats(cell, f"RS_T3|{label}"))
    all_stats.extend(rows)
    _print_table(rows, "Distance ATR thresholds (RS_T3 filtered)")

    # ══════════════════════════════════════════════════════════
    # Analysis 4: Regime comparison (RS_T3+Dist_T1 in bull vs bear)
    # ══════════════════════════════════════════════════════════
    if not regime:
        print("\n" + "=" * 110)
        print("  ANALYSIS 4: RS_T3+Dist_T1 by regime")
        rows = []
        dist_t1 = rs3.filter(pl.col("dist_above_ma20_atr_tercile") == "Dist_T1")
        for r_name in ["bull", "bear", "neutral", "crisis"]:
            r_df = dist_t1.filter(pl.col("market_regime") == r_name)
            if r_df.height > 0:
                rows.extend(_cell_stats(r_df, f"RS_T3|Dist_T1|{r_name}"))
        rows.extend(_cell_stats(dist_t1, "RS_T3|Dist_T1 (all regimes)"))
        all_stats.extend(rows)
        _print_table(rows, "RS_T3+Dist_T1 pullback entry by regime")

    # ── Write CSV ─────────────────────────────────────────────
    if all_stats:
        suffix = f"_{regime}" if regime else ""
        stats_df = pl.DataFrame(all_stats)
        csv_path = output_dir / f"distance_refinement{suffix}.csv"
        stats_df.write_csv(csv_path)
        print(f"\nCSV: {csv_path} ({len(all_stats)} rows)")

    return all_stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="RS_T3 × Distance pullback entry refinement"
    )
    parser.add_argument("--regime", type=str, default=None,
                        choices=["bull", "bear", "crisis", "neutral"])
    parser.add_argument("--start", type=str, default=None)
    parser.add_argument("--end", type=str, default=None)
    parser.add_argument("--output-dir", type=str, default=None)
    args = parser.parse_args()

    start = date_type.fromisoformat(args.start) if args.start else None
    end = date_type.fromisoformat(args.end) if args.end else None

    print(f"Distance Refinement Study v1")
    print(f"  regime:  {args.regime or 'all (entry-date filter only)'}")
    print(f"  cost:    {ROUND_TRIP_COST_BPS:.1f} bps")
    print(f"  spacing: per-horizon (5d→5, 10d→10, 20d→20)")
    print()

    run_refinement(
        regime=args.regime,
        start=start, end=end,
        output_dir=Path(args.output_dir) if args.output_dir else None,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
