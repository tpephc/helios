#!/usr/bin/env python3
# research/pullback_quality.py
"""R5 Pullback Quality Transfer Study — v0.1.1.

Among RS_T3 pullback candidates (dist_above_ma20_atr < 0), do the
consolidation and trend-structure features used by find_bullish_setups
(above-MA20 base/breakout universe) transfer as forward-return predictors
to the below-MA20 pullback universe?

This is a TRANSFER / VALIDATION study, not new-alpha discovery.  The features
are already deployed in find_bullish_setups.py as heuristic filter gates and
sort keys in the above-MA20 universe (above_ma20_streak >= 3, vol_contraction
>= 4, tight_range >= 4, atr_compression <= 0.85).  R5 tests whether the same
quality concept predicts in the opposite-geometry pullback universe.

Output = per-feature directional evidence for soft entry-priority adjustment,
NOT hard filter.  Three semi-independent axes (precheck collinearity confirmed):

  Axis 1  ATR compression        atr_compression_ratio         (Spearman)
  Axis 2  Volume contraction     volume_contraction_days_10d   (dose = primary)
  Axis 3  Trend structure        ma20_ma50_spread_atr          (Spearman, VERDICT)
          robustness              sma20_slope_10d               (same-axis check)
          robustness              above_ma50_streak             (binary >0, same-axis)

  Axis 3 verdict is based on the primary feature ONLY (ma20_ma50_spread_atr).
  Robustness features confirm directional consistency; they are NOT independent
  evidence (|rho| 0.65-0.83 with primary → same latent factor).

Dropped (degenerate in primary universe, dist<0):
  tight_range_days_10d    96.8% zero — ATR expands during pullback
  above_ma20_streak       100% zero — by definition below MA20

Context: above_ma20_streak validates find_bullish_setups sort key (production
audit, NOT pullback-study evidence).

v0.1.1 changes from v0.1.0:
  - Removed permutation null entirely (anti-conservative for rolling-count
    features with time-clustering; R5 has no R1-style artifact question that
    justifies it).  Block-CI is the SOLE inference tool.
  - Axis 2: dose response is PRIMARY estimand; Spearman demoted to secondary
    monotonicity check (count variable with known threshold, not necessarily
    monotone).
  - Axis 3: output clearly separates PRIMARY (verdict) from ROBUSTNESS
    (same-axis consistency check, not independent evidence).
  - Section C renamed "Production Audit" (validates find_bullish_setups,
    not pullback evidence).

KNOWN LIMITATIONS — DO NOT OVERSTATE:
  - MULTI-FEATURE STUDY (3 axes x 3 horizons = 9 primary tests): NO multiple-
    testing correction.  All results are EXPLORATORY.  Report all, no cherry-pick.
  - Cohort-excess controls RS sub-band x dist-depth strata, NOT date-level
    market return; date handled through block bootstrap, not demeaning.  Adding
    date to the cell rejected (thin -> degenerate, same as R1/R2).
  - NO regime conditioning (R3 gated on resolved n>=30); single-regime span
    (~2021-09..2026-05, largely bull/recovery); current-constituent survivorship;
    missing target at T+h excluded (can bias); RAW LHS carries market beta.
  - above_ma50_streak analyzed as binary (0 vs >0) due to 46.7% zero mass +
    heavy right tail making raw Spearman unreliable (massive tied ranks).
  - Consolidation trio does NOT cohere in the pullback universe: tight_range
    degenerate, atr_compression vs vol_contraction only |rho|=0.42 (semi-
    independent).  Do not interpret them as one bundle.
  - Axis 3 robustness features (sma20_slope_10d, above_ma50_streak) are NOT
    independent of the primary (|rho| 0.65-0.83).  Treat as same-axis
    consistency checks, not additional axes.

Standalone, read-only analysis.  No schema changes.  Static report to stdout
(+ optional Parquet via --out).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

import numpy as np
import pandas as pd

# ── live threshold import ──────────────────────────────────────────────

try:
    from strategies.trend_pullback.screener import (  # type: ignore[import-not-found]
        _compute_tercile_thresholds as _live_tercile_thresholds,
    )
except Exception:  # noqa: BLE001
    _live_tercile_thresholds = None

# ── configuration ──────────────────────────────────────────────────────

DB_PATH = "data/_storage/helios.duckdb"
RS_T3_Q = 2 / 3


@dataclass(frozen=True)
class StudyConfig:
    horizons: tuple[int, ...] = (20, 40, 60)
    n_boot: int = 1999
    alpha: float = 0.05
    seed: int = 42
    dist_deep: float = -1.0
    min_cell: int = 20


# ── feature metadata ──────────────────────────────────────────────────

FEAT_META: dict[str, dict] = {
    "atr_compression_ratio": dict(
        axis=1, role="primary", kind="continuous",
        label="Axis 1 — ATR compression",
        desc="atr_14[t] / mean(atr_14 baseline); <1=compressed, >1=expanded",
    ),
    "volume_contraction_days_10d": dict(
        axis=2, role="primary", kind="count",
        label="Axis 2 — Volume contraction",
        desc="trailing-10d count of days with vol < 0.7x baseline",
        # Pre-registered from distribution audit (precheck v0.1.0, 2026-05).
        # NOT optimized from outcomes.
        dose_edges=(-0.5, 0.5, 3.5, 6.5, 10.5),
        dose_labels=("0", "1-3", "4-6", "7+"),
    ),
    "ma20_ma50_spread_atr": dict(
        axis=3, role="primary", kind="continuous",
        label="Axis 3 — Trend structure [PRIMARY / VERDICT]",
        desc="(sma_20 - sma_50) / atr_14; >0 = MA20 above MA50",
    ),
    "sma20_slope_10d": dict(
        axis=3, role="robustness", kind="continuous",
        label="Axis 3 — Trend structure [ROBUSTNESS: MA20 slope, |rho|=0.76]",
        desc="sma_20[t] / sma_20[t-10] - 1; >0 = rising MA20",
    ),
    "above_ma50_streak": dict(
        axis=3, role="robustness", kind="binary",
        label="Axis 3 — Trend structure [ROBUSTNESS: MA50 intact, |rho|=0.83]",
        desc="consecutive days close > sma_50; binary 0 vs >0",
    ),
}

CONTEXT_FEAT = "above_ma20_streak"
ALL_DB_FEATS = list(FEAT_META.keys()) + [CONTEXT_FEAT]

# ── low-level helpers ──────────────────────────────────────────────────


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    """Spearman rho with average-rank tie handling (via pandas)."""
    if len(x) < 3:
        return np.nan
    return pd.Series(x).corr(pd.Series(y), method="spearman")


def _cohort_resid(vals: np.ndarray, cell_codes: np.ndarray) -> np.ndarray:
    """Within-cell demean: val - mean(val in cell)."""
    means = pd.Series(vals).groupby(pd.Series(cell_codes)).transform("mean")
    return (vals - means.values).astype(np.float64)


def _date_row_map(date_ord: np.ndarray) -> dict[int, np.ndarray]:
    """date_ord value -> array of row indices."""
    d: dict[int, list[int]] = {}
    for i, v in enumerate(date_ord):
        d.setdefault(int(v), []).append(i)
    return {k: np.array(v, dtype=np.intp) for k, v in d.items()}


def _block_resample(unique_ords: np.ndarray, drm: dict[int, np.ndarray],
                    block_len: int, rng: np.random.Generator) -> np.ndarray:
    """Circular moving-block bootstrap -> row indices with draw-multiplicity."""
    n = len(unique_ords)
    n_blocks = max(1, int(np.ceil(n / block_len)))
    starts = rng.integers(0, n, size=n_blocks)
    parts: list[np.ndarray] = []
    count = 0
    for s in starts:
        for j in range(block_len):
            if count >= n:
                break
            d = int(unique_ords[(s + j) % n])
            rows = drm.get(d)
            if rows is not None:
                parts.append(rows)
            count += 1
        if count >= n:
            break
    return np.concatenate(parts) if parts else np.array([], dtype=np.intp)


# ── analysis engines (block-CI only, no permutation null) ─────────────


def run_spearman(feat: np.ndarray, resid: np.ndarray,
                 uo: np.ndarray, drm: dict[int, np.ndarray],
                 block_len: int, rng: np.random.Generator,
                 cfg: StudyConfig) -> dict:
    """Spearman(feature, cohort_resid) + date-block bootstrap CI."""
    rho = _spearman(feat, resid)

    boots = np.empty(cfg.n_boot)
    for b in range(cfg.n_boot):
        idx = _block_resample(uo, drm, block_len, rng)
        boots[b] = _spearman(feat[idx], resid[idx]) if len(idx) >= 30 else np.nan
    boots = boots[~np.isnan(boots)]
    ci_lo = float(np.percentile(boots, 100 * cfg.alpha / 2))
    ci_hi = float(np.percentile(boots, 100 * (1 - cfg.alpha / 2)))

    return {"rho": rho, "ci_lo": ci_lo, "ci_hi": ci_hi}


def run_binary(resid: np.ndarray, flag: np.ndarray,
               uo: np.ndarray, drm: dict[int, np.ndarray],
               block_len: int, rng: np.random.Generator,
               cfg: StudyConfig) -> dict:
    """Binary cohort-excess + date-block bootstrap CI."""
    t = flag.astype(bool)
    excess = float(resid[t].mean() - resid[~t].mean()) if t.any() and (~t).any() else np.nan

    boots = np.empty(cfg.n_boot)
    for b in range(cfg.n_boot):
        idx = _block_resample(uo, drm, block_len, rng)
        r, f = resid[idx], t[idx]
        boots[b] = (r[f].mean() - r[~f].mean()) if f.any() and (~f).any() else np.nan
    boots = boots[~np.isnan(boots)]
    ci_lo = float(np.percentile(boots, 100 * cfg.alpha / 2))
    ci_hi = float(np.percentile(boots, 100 * (1 - cfg.alpha / 2)))

    return {"excess": excess, "ci_lo": ci_lo, "ci_hi": ci_hi,
            "n_treated": int(t.sum()), "n_control": int((~t).sum())}


def run_dose(resid: np.ndarray, dose: np.ndarray,
             uo: np.ndarray, drm: dict[int, np.ndarray],
             block_len: int, rng: np.random.Generator,
             cfg: StudyConfig) -> dict:
    """Per-dose-group cohort-excess with block-bootstrap CI."""
    groups = sorted(set(dose))
    obs = {}
    for g in groups:
        gm = dose == g
        obs[g] = float(resid[gm].mean()) if gm.any() else np.nan

    boot_means: dict[str, np.ndarray] = {g: np.empty(cfg.n_boot) for g in groups}
    for b in range(cfg.n_boot):
        idx = _block_resample(uo, drm, block_len, rng)
        for g in groups:
            gm = dose[idx] == g
            boot_means[g][b] = resid[idx][gm].mean() if gm.any() else np.nan

    result = {}
    for g in groups:
        bm = boot_means[g][~np.isnan(boot_means[g])]
        lo = float(np.percentile(bm, 100 * cfg.alpha / 2)) if len(bm) else np.nan
        hi = float(np.percentile(bm, 100 * (1 - cfg.alpha / 2))) if len(bm) else np.nan
        result[g] = {"n": int((dose == g).sum()), "excess": obs.get(g, np.nan),
                     "ci_lo": lo, "ci_hi": hi}
    return result


# ── data pipeline ──────────────────────────────────────────────────────


def load_panel() -> pd.DataFrame:
    """Load Step-2 universe with R5 features, read-only."""
    import duckdb

    con = duckdb.connect(DB_PATH, read_only=True)
    schema = con.execute("PRAGMA table_info('bullish_features')").fetchdf()
    avail = set(schema["name"])
    feat_cols = [c for c in ALL_DB_FEATS if c in avail]
    missing = [c for c in ALL_DB_FEATS if c not in avail]
    if missing:
        print(f"⚠️  Missing columns: {missing}")

    feat_sql = ", ".join(f"b.{c}" for c in feat_cols)
    sql = f"""
    SELECT b.date, b.stock_id, b.beta_adj_rs_20d,
           b.dist_above_ma20_atr, b.beta_60,
           d.adj_close, {feat_sql}
    FROM bullish_features b
    JOIN daily_price_adj d ON b.stock_id = d.stock_id AND b.date = d.date
    WHERE b.beta_adj_rs_20d IS NOT NULL
      AND b.dist_above_ma20_atr IS NOT NULL
      AND b.beta_60 IS NOT NULL
      AND d.adj_close > 0
    ORDER BY b.date, b.stock_id
    """
    df = con.execute(sql).fetchdf()
    con.close()
    return df


def assign_membership(df: pd.DataFrame) -> pd.DataFrame:
    """Per-day weak-ECDF rs_pctile + RS_T3 flag."""
    parts: list[pd.DataFrame] = []
    for _, g in df.groupby("date"):
        vals = g["beta_adj_rs_20d"].values
        n = len(vals)
        g = g.copy()
        g["rs_pctile"] = np.array([(vals <= v).sum() / n for v in vals])
        thresh = float(np.quantile(vals, RS_T3_Q))
        g["rs_t3"] = vals >= thresh
        parts.append(g)
    return pd.concat(parts, ignore_index=True)


def add_forward_returns(df: pd.DataFrame, cfg: StudyConfig) -> pd.DataFrame:
    """Forward returns via global trading-day ordinal, with always-on invariant."""
    dates_sorted = np.sort(df["date"].unique())
    d2o = {d: i for i, d in enumerate(dates_sorted)}
    df["date_ord"] = df["date"].map(d2o).astype(np.int32)

    cl = df.set_index(["stock_id", "date_ord"])["adj_close"]
    for h in cfg.horizons:
        target = df["date_ord"].values + h
        keys = list(zip(df["stock_id"].values, target))
        fc = cl.reindex(keys).values
        df[f"fwd_ret_{h}"] = fc / df["adj_close"].values - 1.0
        valid = df[f"fwd_ret_{h}"].notna()
        if valid.any():
            gap = target[valid.values] - df["date_ord"].values[valid.values]
            assert (gap == h).all(), f"invariant failed h={h}"
        print(f"    h={h:3d}: non-null = {valid.sum():,d}  "
              f"(invariant target==source+{h} verified)")
    return df


def assign_primary_strata(df: pd.DataFrame, cfg: StudyConfig) -> pd.DataFrame:
    """RS sub-bands (pooled tercile within T3 primary) x dist depth."""
    df["rs_sub"] = pd.qcut(
        df["rs_pctile"], 3, labels=["rs_lo", "rs_mid", "rs_hi"],
        duplicates="drop",
    )
    df["dist_band"] = np.where(
        df["dist_above_ma20_atr"] < cfg.dist_deep, "deep", "shallow",
    )
    df["cell_code"] = df["rs_sub"].astype(str) + "_" + df["dist_band"]
    return df


# ── print helpers ──────────────────────────────────────────────────────


def _pr_spearman(label: str, res: dict, n: int) -> None:
    print(f"     {label}")
    print(f"       n={n}  rho={res['rho']:+.4f}  "
          f"[95% block-CI: {res['ci_lo']:+.4f}, {res['ci_hi']:+.4f}]")


def _pr_binary(label: str, res: dict) -> None:
    print(f"     {label}")
    print(f"       n_treated={res['n_treated']}  n_control={res['n_control']}")
    print(f"       cohort-excess={res['excess']:+.4f}  "
          f"[95% block-CI: {res['ci_lo']:+.4f}, {res['ci_hi']:+.4f}]")


def _pr_dose(label: str, dr: dict) -> None:
    print(f"     {label}")
    parts = []
    for g in sorted(dr.keys()):
        d = dr[g]
        parts.append(f"{g}:{d['excess']:+.4f}[{d['ci_lo']:+.4f},{d['ci_hi']:+.4f}]"
                     f"(n={d['n']})")
    print(f"       " + "  ".join(parts))


# ── main ───────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="R5 Pullback Quality Transfer Study (v0.1.1)")
    parser.add_argument("--out", type=str, default="",
                        help="path to write analysis frame (parquet)")
    args = parser.parse_args()

    cfg = StudyConfig()
    rng = np.random.default_rng(cfg.seed)

    # ── load ──
    print("📥  Loading Step-2 universe (read-only) ...")
    df = load_panel()
    n_all = len(df)
    print(f"    rows={n_all:,d}  stocks={df['stock_id'].nunique()}  "
          f"dates={df['date'].nunique()}  "
          f"span={df['date'].min()}..{df['date'].max()}")

    print("🧮  Per-day RS_T3 thresholds + percentile ...")
    df = assign_membership(df)
    print(f"    T3 member-rows={int(df['rs_t3'].sum())} / {n_all}")

    print(f"🧮  Forward returns for horizons {cfg.horizons} ...")
    df = add_forward_returns(df, cfg)

    # ── universes ──
    primary = df[df["rs_t3"] & (df["dist_above_ma20_atr"] < 0)].copy()
    primary = assign_primary_strata(primary, cfg)
    n_prim = len(primary)
    n_deep = int((primary["dist_above_ma20_atr"] < cfg.dist_deep).sum())

    df["rs_tercile"] = pd.qcut(
        df["rs_pctile"], 3, labels=["T1", "T2", "T3"], duplicates="drop",
    )

    # ================================================================
    # SECTION A — feature definitions (pre-registered, report all)
    # ================================================================
    print(f"\n{'=' * 78}")
    print("📊  SECTION A — feature definitions (pre-registered, report all)")
    print(f"{'=' * 78}")
    for feat, meta in FEAT_META.items():
        tag = meta["role"].upper()
        if meta.get("role") == "robustness":
            tag = "ROBUSTNESS"
        print(f"    [{tag}] {meta['label']}")
        print(f"      {feat}: {meta['desc']}")
    print(f"    [CONTEXT / PRODUCTION AUDIT] {CONTEXT_FEAT}:")
    print(f"      consecutive days close > sma_20 — validates find_bullish_setups"
          f" sort key")

    # ================================================================
    # SECTION B — feasibility
    # ================================================================
    print(f"\n{'=' * 78}")
    print("📊  SECTION B — feasibility (primary universe)")
    print(f"{'=' * 78}")
    print(f"    n={n_prim}  (deep dist<{cfg.dist_deep}: {n_deep}, "
          f"shallow: {n_prim - n_deep})")

    cell_cts = primary["cell_code"].value_counts()
    print(f"    cells={len(cell_cts)}  median={int(cell_cts.median())}  "
          f"min={int(cell_cts.min())}")
    if cell_cts.min() < cfg.min_cell:
        print(f"    ⚠️  min cell < {cfg.min_cell} — interpret with caution")

    print(f"\n    feature {'median':>8s} {'mean':>8s} {'std':>8s} "
          f"{'zero%':>6s} {'null%':>6s}")
    print(f"    {'-' * 60}")
    for feat in FEAT_META:
        if feat not in primary.columns:
            print(f"    {feat:<36s} (not available)")
            continue
        col = primary[feat]
        nn = col.dropna()
        z_pct = float((nn == 0).sum()) / len(nn) * 100 if len(nn) else 0.0
        n_pct = float(col.isna().sum()) / len(col) * 100
        print(f"    {feat:<36s} {nn.median():>8.4f} {nn.mean():>8.4f} "
              f"{nn.std():>8.4f} {z_pct:>5.1f}% {n_pct:>5.1f}%")

    # ================================================================
    # SECTION C — PRODUCTION AUDIT: above_ma20_streak
    # ================================================================
    print(f"\n{'=' * 78}")
    print("📊  SECTION C — PRODUCTION AUDIT: above_ma20_streak")
    print("    Full universe, RS-tercile stratified.")
    print("    Validates whether find_bullish_setups sort key has")
    print("    forward-return support.  NOT pullback-study evidence.")
    print(f"{'=' * 78}")

    if CONTEXT_FEAT in df.columns:
        ctx_vals = df[CONTEXT_FEAT].values.astype(float)
        nn_ctx = ctx_vals[~np.isnan(ctx_vals)]
        print(f"    n={len(nn_ctx):,d}  median={np.median(nn_ctx):.0f}  "
              f"mean={np.mean(nn_ctx):.1f}  "
              f"zero%={(nn_ctx == 0).sum() / len(nn_ctx) * 100:.1f}%")

        for h in cfg.horizons:
            col = f"fwd_ret_{h}"
            mask = df[col].notna() & df[CONTEXT_FEAT].notna()
            sub = df[mask]
            resid = _cohort_resid(sub[col].values, sub["rs_tercile"].values)
            feat_v = sub[CONTEXT_FEAT].values.astype(float)
            date_ord = sub["date_ord"].values
            uo = np.sort(np.unique(date_ord))
            drm = _date_row_map(date_ord)

            print(f"\n  ── horizon = {h}d ──")
            print(f"     n={len(sub):,d}")

            res = run_spearman(feat_v, resid, uo, drm, h, rng, cfg)
            _pr_spearman("Spearman(above_ma20_streak, cohort_resid)", res, len(sub))

            dose_arr = pd.cut(
                feat_v, bins=[-0.5, 0.5, 5.5, 20.5, 9999],
                labels=["0", "1-5", "6-20", "21+"],
            ).astype(str).to_numpy()
            dose_res = run_dose(resid, dose_arr, uo, drm, h, rng, cfg)
            _pr_dose("dose cohort-excess", dose_res)
    else:
        print(f"    ⚠️  {CONTEXT_FEAT} not available, skipping.")

    # ================================================================
    # SECTION D — PRIMARY: per-axis results
    # ================================================================
    print(f"\n{'=' * 78}")
    print("📊  SECTION D — PRIMARY: pullback universe (RS_T3 ∩ dist<0)")
    print("    cohort-excess within (RS sub-band × dist depth); "
          "date = bootstrap cluster.")
    print("    Block-CI is the SOLE inference tool (no permutation null).")
    print("    3 axes × 3 horizons = 9 primary tests.  "
          "NO multiple-testing correction.")
    print(f"{'=' * 78}")
    print(f"    primary rows={n_prim}  "
          f"(deep: {n_deep}, shallow: {n_prim - n_deep})")

    for h in cfg.horizons:
        col = f"fwd_ret_{h}"
        mask = primary[col].notna()
        sub = primary[mask].copy()
        n_sub = len(sub)

        resid = _cohort_resid(sub[col].values, sub["cell_code"].values)
        date_ord = sub["date_ord"].values
        uo = np.sort(np.unique(date_ord))
        drm = _date_row_map(date_ord)

        cell_cts_h = pd.Series(sub["cell_code"].values).value_counts()

        print(f"\n  ── horizon = {h}d ──")
        print(f"     n={n_sub}  cells={len(cell_cts_h)} "
              f"(median {int(cell_cts_h.median())}, min {int(cell_cts_h.min())})")

        # ── Axis 1 — ATR compression (Spearman) ──
        fname = "atr_compression_ratio"
        if fname in sub.columns:
            fv = sub[fname].values.astype(float)
            res = run_spearman(fv, resid, uo, drm, h, rng, cfg)
            _pr_spearman(FEAT_META[fname]["label"], res, n_sub)

        # ── Axis 2 — Volume contraction (dose = PRIMARY, Spearman = secondary) ──
        fname = "volume_contraction_days_10d"
        if fname in sub.columns:
            fv = sub[fname].values.astype(float)
            meta = FEAT_META[fname]

            # PRIMARY: dose response
            dose_arr = pd.cut(
                fv, bins=list(meta["dose_edges"]),
                labels=list(meta["dose_labels"]),
            ).astype(str).to_numpy()
            dose_res = run_dose(resid, dose_arr, uo, drm, h, rng, cfg)
            _pr_dose(f"{meta['label']} [PRIMARY: dose response]", dose_res)

            # SECONDARY: Spearman monotonicity check
            res = run_spearman(fv, resid, uo, drm, h, rng, cfg)
            _pr_spearman(f"{meta['label']} [SECONDARY: monotonicity]", res, n_sub)

        # ── Axis 3 — Trend structure ──
        # PRIMARY (verdict based on this feature only)
        fname = "ma20_ma50_spread_atr"
        if fname in sub.columns:
            fv = sub[fname].values.astype(float)
            res = run_spearman(fv, resid, uo, drm, h, rng, cfg)
            _pr_spearman(FEAT_META[fname]["label"], res, n_sub)

        # ROBUSTNESS: MA20 slope (same axis, |rho|=0.76 with primary)
        fname = "sma20_slope_10d"
        if fname in sub.columns:
            fv = sub[fname].values.astype(float)
            res = run_spearman(fv, resid, uo, drm, h, rng, cfg)
            _pr_spearman(FEAT_META[fname]["label"], res, n_sub)

        # ROBUSTNESS: MA50 intact (same axis, |rho|=0.83, binary)
        fname = "above_ma50_streak"
        if fname in sub.columns:
            flag = (sub[fname].values > 0).astype(float)
            res = run_binary(resid, flag, uo, drm, h, rng, cfg)
            _pr_binary(FEAT_META[fname]["label"] + " (>0 vs =0)", res)

    # ================================================================
    # SECTION E — limitations
    # ================================================================
    print(f"\n{'=' * 78}")
    print("📊  SECTION E — limitations")
    print(f"{'=' * 78}")
    for lim in (
        "MULTI-FEATURE: 3 axes × 3 horizons = 9 primary tests; NO MT "
        "correction; all results exploratory; report all, no cherry-pick",
        "transfer study: features deployed in find_bullish_setups (above-MA20 "
        "base); R5 tests transfer to below-MA20 pullback — different geometry",
        "Axis 3 verdict = ma20_ma50_spread_atr ONLY; robustness features are "
        "NOT independent evidence (|rho| 0.65-0.83 with primary)",
        "Axis 2 primary estimand = dose response (count variable with known "
        "threshold); Spearman is secondary monotonicity check",
        "cohort-excess controls RS/dist strata, not date-level market return; "
        "date handled through block bootstrap, not demeaning",
        "consolidation trio does NOT cohere: tight_range degenerate, "
        "atr_compression vs vol_contraction |rho|=0.42 (semi-independent)",
        "no regime conditioning (R3 gated); single-regime span; "
        "current-constituent survivorship",
        "missing target at T+h excluded (can bias); RAW LHS carries market beta",
        "above_ma50_streak binary (0 vs >0) due to 46.7% zero + right tail",
        "block-CI is sole inference tool; no permutation null (anti-conservative "
        "for rolling-count features with time-clustering)",
    ):
        print(f"    - {lim}")

    # ── optional output ──
    if args.out:
        primary.to_parquet(args.out, index=False)
        print(f"\n📥  Analysis frame written to {args.out}")

    print(f"\n✅  Done (pass --out <path> to persist the analysis frame).")


if __name__ == "__main__":
    main()
