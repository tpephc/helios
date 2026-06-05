#!/usr/bin/env python3
# research/r5_precheck.py
"""R5 Pullback Quality — Pre-check Audit — v0.1.0.

Feature distribution and collinearity within the primary pullback universe
(RS_T3 ∩ dist_above_ma20_atr < 0).  Determines which candidate features
have sufficient variance for the main R5 study, and maps the correlation
structure to guide axis-level vs per-feature interpretation.

Standalone, read-only analysis.  No schema changes.  Outputs to stdout.
"""

from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

# ── configuration ──────────────────────────────────────────────────────
DB_PATH = "data/_storage/helios.duckdb"
RS_T3_Q = 2 / 3  # 0.6667 — numpy-linear quantile, matching live screener

CANDIDATE_FEATURES: list[str] = [
    # consolidation axis (primary hypothesis)
    "atr_compression_ratio",
    "tight_range_days_10d",
    "volume_contraction_days_10d",
    # trend structure axis
    "ma20_ma50_spread_atr",
    "sma20_slope_10d",
    "above_ma50_streak",        # shallow-pullback quality; may not exist
    # context-only (expect degenerate in primary)
    "above_ma20_streak",
]

COLLINEARITY_THRESHOLDS = {"SAME AXIS": 0.80, "RELATED": 0.50}


# ── helpers ────────────────────────────────────────────────────────────
def _weak_ecdf(vals: np.ndarray) -> np.ndarray:
    """count(v <= val) / N  for each val — weak ECDF, matching live screener."""
    n = len(vals)
    # Broadcast: (n,1) <= (1,n) → boolean matrix, sum columns
    return (vals[:, None] <= vals[None, :]).sum(axis=0) / n


# ── main ───────────────────────────────────────────────────────────────
def main() -> None:
    # ── load Step-2 universe ──
    print("📥  Loading Step-2 universe (read-only) ...")
    con = duckdb.connect(DB_PATH, read_only=True)

    schema = con.execute("PRAGMA table_info('bullish_features')").fetchdf()
    avail = set(schema["name"])

    present = [f for f in CANDIDATE_FEATURES if f in avail]
    missing = [f for f in CANDIDATE_FEATURES if f not in avail]
    if missing:
        print(f"⚠️  NOT in bullish_features table: {missing}")
    if not present:
        print("❌  No candidate features found.  Exiting.")
        return

    feat_sql = ", ".join(f"b.{c}" for c in present)
    sql = f"""
    SELECT
        b.date,
        b.stock_id,
        b.beta_adj_rs_20d,
        b.dist_above_ma20_atr,
        b.beta_60,
        d.adj_close,
        {feat_sql}
    FROM bullish_features b
    JOIN daily_price_adj d
        ON b.stock_id = d.stock_id AND b.date = d.date
    WHERE b.beta_adj_rs_20d IS NOT NULL
      AND b.dist_above_ma20_atr IS NOT NULL
      AND b.beta_60 IS NOT NULL
      AND d.adj_close > 0
    ORDER BY b.date, b.stock_id
    """
    df = con.execute(sql).fetchdf()
    con.close()

    n_rows = len(df)
    n_stocks = df["stock_id"].nunique()
    n_dates = df["date"].nunique()
    d_min, d_max = df["date"].min(), df["date"].max()
    print(f"    rows={n_rows}  stocks={n_stocks}  dates={n_dates}"
          f"  span={d_min}..{d_max}")

    # ── per-day RS_T3 + percentile ──
    print("🧮  Per-day RS_T3 thresholds + percentile ...")
    parts: list[pd.DataFrame] = []
    for _date, g in df.groupby("date"):
        rs_vals = g["beta_adj_rs_20d"].values
        g = g.copy()
        g["rs_pctile"] = _weak_ecdf(rs_vals)
        thresh = float(np.quantile(rs_vals, RS_T3_Q))
        g["rs_t3"] = rs_vals >= thresh
        parts.append(g)
    df = pd.concat(parts, ignore_index=True)
    t3_n = int(df["rs_t3"].sum())
    print(f"    T3 member-rows={t3_n} / {n_rows}")

    # ── primary universe ──
    primary = df[df["rs_t3"] & (df["dist_above_ma20_atr"] < 0)].copy()
    n_primary = len(primary)
    n_deep = int((primary["dist_above_ma20_atr"] < -1.0).sum())
    n_shallow = n_primary - n_deep

    print(f"\n{'=' * 74}")
    print("📊  PRIMARY UNIVERSE: RS_T3 ∩ dist_above_ma20_atr < 0")
    print(f"{'=' * 74}")
    print(f"    n={n_primary}  (deep dist<-1.0: {n_deep}, shallow: {n_shallow})")

    # ── PRECHECK 2: per-feature distribution ──
    print(f"\n{'=' * 74}")
    print("📊  PRECHECK 2 — Per-feature distribution (primary universe)")
    print(f"{'=' * 74}")

    header = (f"  {'feature':<32s} {'n_ok':>6s} {'null%':>6s} {'zero%':>6s}"
              f" {'min':>10s} {'p25':>10s} {'med':>10s} {'p75':>10s} {'max':>10s}")
    print(header)
    print(f"  {'-' * (len(header) - 2)}")

    for feat in present:
        col = primary[feat]
        n_tot = len(col)
        n_null = int(col.isna().sum())
        nn = col.dropna()
        n_ok = len(nn)
        null_pct = n_null / n_tot * 100 if n_tot > 0 else 0.0
        zero_pct = float((nn == 0).sum()) / n_ok * 100 if n_ok > 0 else 0.0

        if n_ok > 0:
            q = nn.quantile([0.0, 0.25, 0.5, 0.75, 1.0])
            mn, p25, med, p75, mx = q.values
        else:
            mn = p25 = med = p75 = mx = float("nan")

        tag = ""
        if null_pct > 50:
            tag = " ← MOSTLY NULL"
        elif zero_pct > 90:
            tag = " ← DEGENERATE (>90% zero)"
        elif zero_pct > 70:
            tag = " ← LOW VARIANCE (>70% zero)"

        print(f"  {feat:<32s} {n_ok:>6d} {null_pct:>5.1f}% {zero_pct:>5.1f}%"
              f" {mn:>10.4f} {p25:>10.4f} {med:>10.4f} {p75:>10.4f} {mx:>10.4f}{tag}")

    # ── PRECHECK 3: Spearman correlation ──
    print(f"\n{'=' * 74}")
    print("📊  PRECHECK 3 — Spearman correlation matrix (primary universe)")
    print(f"{'=' * 74}")

    corr_cols = [f for f in present if f in primary.columns]
    corr_cols += ["rs_pctile", "dist_above_ma20_atr"]
    corr_frame = primary[corr_cols].dropna()
    n_complete = len(corr_frame)
    print(f"    complete cases = {n_complete}")

    if n_complete < 30:
        print("    ⚠️  Too few complete cases for reliable correlation.  Skipping.")
        return

    rho = corr_frame.corr(method="spearman")

    short = {
        "atr_compression_ratio": "atr_comp",
        "tight_range_days_10d": "tight_rng",
        "volume_contraction_days_10d": "vol_contr",
        "ma20_ma50_spread_atr": "ma_sprd",
        "sma20_slope_10d": "sma_slp",
        "above_ma50_streak": "ma50_str",
        "above_ma20_streak": "ma20_str",
        "rs_pctile": "rs_pctl",
        "dist_above_ma20_atr": "dist",
    }
    labels = [short.get(c, c[:8]) for c in rho.columns]

    # header row
    print(f"\n    {'':>10s}  " + "  ".join(f"{lb:>9s}" for lb in labels))
    for i, (_, row) in enumerate(rho.iterrows()):
        vals_str = "  ".join(f"{v:>9.3f}" for v in row.values)
        print(f"    {labels[i]:>10s}  {vals_str}")

    # flag notable pairs
    print(f"\n    Notable pairs (|rho| >= 0.50):")
    flagged: list[tuple[str, str, float, str]] = []
    for i in range(len(rho)):
        for j in range(i + 1, len(rho)):
            r = rho.iloc[i, j]
            if abs(r) >= COLLINEARITY_THRESHOLDS["RELATED"]:
                level = ("SAME AXIS" if abs(r) >= COLLINEARITY_THRESHOLDS["SAME AXIS"]
                         else "RELATED")
                flagged.append((labels[i], labels[j], r, level))
    flagged.sort(key=lambda x: -abs(x[2]))
    for a, b, r, level in flagged:
        print(f"      {a:>10s} × {b:<10s}  rho={r:+.3f}  [{level}]")
    if not flagged:
        print("      (none)")

    print(f"\n✅  Pre-check complete.")


if __name__ == "__main__":
    main()
