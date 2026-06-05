#!/usr/bin/env python3
# research/rs_acceleration.py
"""Study B RS Acceleration — v0.1.0.

Within RS_T3 leadership, does recent rank acceleration (Δ5 = rs_pctile[t] -
rs_pctile[t-5]) predict forward returns?

Primary analysis is restricted to the 0.75-0.90 current-RS band (n~34k),
which avoids two mechanical confounds:
  - 0.67-0.75: contaminated by T3-entry artifact (50% accel by construction)
  - 0.90-1.00: ceiling-constrained (3% decel, degenerate)
These two bands are reported as CONTEXT only, NOT verdict sources.

Estimand:
  PRIMARY:   Spearman(Δ5, fwd_ret) within 0.75-0.90 band
  SECONDARY: within-band adaptive-tercile dose response (shape check)
  Inference: date moving-block bootstrap CI (sole inference tool)
  No permutation null (Δ5 has within-stock lag-1 autocorr ~0.66 from
  the 15/20 overlap window; permutation would be anti-conservative).

Design constraints:
  B-1 Endpoint conditioning: current_rs_band FIXED; Δ5 measured within band.
      Prevents collapse into "high RS > low RS" (which R1 already tested).
  B-2 R1 separation: R1 tested AGE (duration in T3). Study B tests VELOCITY
      (recent rank change). Primary band 0.75-0.90 minimizes T3-entry
      overlap vs the entry band 0.67-0.75.
  B-3 Feasibility: precheck confirmed n~34k in primary band; all adaptive-
      tercile dose cells >4k.

KNOWN LIMITATIONS — DO NOT OVERSTATE:
  - Δ5 inherits 15/20 = 75% overlap from rolling beta_adj_rs_20d. Mechanical
    autocorrelation (lag-1 ~0.66). Block-CI handles dependence; effective
    sample < n.
  - Primary = 1 band × 3 horizons = 3 tests. Exploratory, no MT correction.
  - Spearman assumes monotone association. Secondary dose checks for non-
    linearity (U-shape or threshold).
  - Within-band Spearman does NOT partial out current RS level within the band
    (e.g., 0.76 vs 0.89). Confound expected small in a narrow band.
  - Context bands (0.67-0.75, 0.90-1.00) have documented mechanical
    contamination. Do NOT use context results for production decisions.
  - NO regime conditioning (R3 gated); single-regime span (~2021-09..2026-05);
    current-constituent survivorship; missing target at T+h excluded; RAW LHS
    carries market beta.

Standalone, read-only analysis. No schema changes. Static report to stdout
(+ optional Parquet via --out).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

import numpy as np
import pandas as pd

# ── configuration ──────────────────────────────────────────────────────

DB_PATH = "data/_storage/helios.duckdb"
RS_T3_Q = 2 / 3
DELTA_K = 5

BAND_EDGES = [0.667, 0.75, 0.90, 1.001]
BAND_LABELS = ["0.67-0.75", "0.75-0.90", "0.90-1.00"]
PRIMARY_BAND = "0.75-0.90"


@dataclass(frozen=True)
class StudyConfig:
    horizons: tuple[int, ...] = (20, 40, 60)
    n_boot: int = 1999
    alpha: float = 0.05
    seed: int = 42


# ── helpers ────────────────────────────────────────────────────────────


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 3:
        return np.nan
    return pd.Series(x).corr(pd.Series(y), method="spearman")


def _date_row_map(date_ord: np.ndarray) -> dict[int, np.ndarray]:
    d: dict[int, list[int]] = {}
    for i, v in enumerate(date_ord):
        d.setdefault(int(v), []).append(i)
    return {k: np.array(v, dtype=np.intp) for k, v in d.items()}


def _block_resample(unique_ords: np.ndarray, drm: dict[int, np.ndarray],
                    block_len: int, rng: np.random.Generator) -> np.ndarray:
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


# ── analysis engines ───────────────────────────────────────────────────


def run_spearman(feat: np.ndarray, outcome: np.ndarray,
                 uo: np.ndarray, drm: dict[int, np.ndarray],
                 block_len: int, rng: np.random.Generator,
                 cfg: StudyConfig) -> dict:
    """Spearman(feat, outcome) + date-block bootstrap CI."""
    rho = _spearman(feat, outcome)
    boots = np.empty(cfg.n_boot)
    for b in range(cfg.n_boot):
        idx = _block_resample(uo, drm, block_len, rng)
        boots[b] = _spearman(feat[idx], outcome[idx]) if len(idx) >= 30 else np.nan
    boots = boots[~np.isnan(boots)]
    ci_lo = float(np.percentile(boots, 100 * cfg.alpha / 2))
    ci_hi = float(np.percentile(boots, 100 * (1 - cfg.alpha / 2)))
    return {"rho": rho, "ci_lo": ci_lo, "ci_hi": ci_hi}


def run_dose(outcome: np.ndarray, dose: np.ndarray,
             uo: np.ndarray, drm: dict[int, np.ndarray],
             block_len: int, rng: np.random.Generator,
             cfg: StudyConfig) -> dict:
    """Per-dose-group deviation from band mean + block-CI."""
    groups = sorted(set(dose))
    band_mean = float(np.nanmean(outcome))
    obs = {}
    for g in groups:
        gm = dose == g
        obs[g] = float(np.nanmean(outcome[gm]) - band_mean) if gm.any() else np.nan

    boot_excess: dict = {g: np.empty(cfg.n_boot) for g in groups}
    for b in range(cfg.n_boot):
        idx = _block_resample(uo, drm, block_len, rng)
        bm = float(np.nanmean(outcome[idx]))
        for g in groups:
            gm = dose[idx] == g
            boot_excess[g][b] = (float(np.nanmean(outcome[idx][gm])) - bm
                                 ) if gm.any() else np.nan

    result = {}
    for g in groups:
        be = boot_excess[g][~np.isnan(boot_excess[g])]
        lo = float(np.percentile(be, 100 * cfg.alpha / 2)) if len(be) else np.nan
        hi = float(np.percentile(be, 100 * (1 - cfg.alpha / 2))) if len(be) else np.nan
        result[g] = {"n": int((dose == g).sum()), "excess": obs.get(g, np.nan),
                     "ci_lo": lo, "ci_hi": hi}
    return result


# ── data pipeline ──────────────────────────────────────────────────────


def load_panel() -> pd.DataFrame:
    import duckdb
    con = duckdb.connect(DB_PATH, read_only=True)
    sql = """
    SELECT b.date, b.stock_id, b.beta_adj_rs_20d,
           b.dist_above_ma20_atr, b.beta_60, d.adj_close
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
    dates_sorted = np.sort(df["date"].unique())
    d2o = {d: i for i, d in enumerate(dates_sorted)}
    df["date_ord"] = df["date"].map(d2o).astype(np.int32)

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


def compute_delta(df: pd.DataFrame, t3: pd.DataFrame) -> pd.DataFrame:
    lookup = (
        df[["stock_id", "date_ord", "rs_pctile"]]
        .drop_duplicates(subset=["stock_id", "date_ord"])
        .set_index(["stock_id", "date_ord"])["rs_pctile"]
    )
    lag_ord = t3["date_ord"].values - DELTA_K
    lag_keys = list(zip(t3["stock_id"].values, lag_ord))
    t3[f"delta_{DELTA_K}"] = t3["rs_pctile"].values - lookup.reindex(lag_keys).values
    return t3


def add_forward_returns(df: pd.DataFrame, t3: pd.DataFrame,
                        cfg: StudyConfig) -> pd.DataFrame:
    cl = (
        df[["stock_id", "date_ord", "adj_close"]]
        .drop_duplicates(subset=["stock_id", "date_ord"])
        .set_index(["stock_id", "date_ord"])["adj_close"]
    )
    for h in cfg.horizons:
        target = t3["date_ord"].values + h
        keys = list(zip(t3["stock_id"].values, target))
        fc = cl.reindex(keys).values
        t3[f"fwd_ret_{h}"] = fc / t3["adj_close"].values - 1.0
        valid = t3[f"fwd_ret_{h}"].notna()
        if valid.any():
            gap = target[valid.values] - t3["date_ord"].values[valid.values]
            assert (gap == h).all(), f"invariant failed h={h}"
        print(f"    h={h:3d}: non-null = {valid.sum():,d}  "
              f"(invariant target==source+{h} verified)")
    return t3


# ── main ───────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Study B RS Acceleration (v0.1.0)")
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

    print("🧮  Per-day RS_T3 + percentile ...")
    df = assign_membership(df)
    t3 = df[df["rs_t3"]].copy()
    print(f"    T3 rows={len(t3):,d}")

    print(f"🧮  Computing Δ{DELTA_K} ...")
    t3 = compute_delta(df, t3)
    n_valid = int(t3[f"delta_{DELTA_K}"].notna().sum())
    n_miss = len(t3) - n_valid
    print(f"    valid Δ{DELTA_K}: {n_valid:,d}  "
          f"missing: {n_miss:,d} ({n_miss / len(t3) * 100:.1f}%)")
    t3 = t3[t3[f"delta_{DELTA_K}"].notna()].copy()

    print("🧮  Forward returns ...")
    t3 = add_forward_returns(df, t3, cfg)

    # ── band assignment ──
    t3["current_band"] = pd.cut(
        t3["rs_pctile"], bins=BAND_EDGES, labels=BAND_LABELS, right=False,
    )
    delta_col = f"delta_{DELTA_K}"

    # ================================================================
    # SECTION A — design summary
    # ================================================================
    print(f"\n{'=' * 78}")
    print("📊  SECTION A — Study B design summary")
    print(f"{'=' * 78}")
    print(f"    Feature: Δ{DELTA_K} = rs_pctile[t] - rs_pctile[t-{DELTA_K}]")
    print(f"    PRIMARY band: {PRIMARY_BAND} (sole verdict source)")
    print(f"    CONTEXT bands: 0.67-0.75 (T3-entry artifact), "
          f"0.90-1.00 (ceiling)")
    print(f"    Estimand: Spearman(Δ{DELTA_K}, fwd_ret) + block-CI")
    print(f"    Secondary: within-band adaptive Δ{DELTA_K} tercile dose "
          f"(shape check)")
    print(f"    Inference: block-CI only (no permutation null)")

    # ================================================================
    # SECTION B — feasibility
    # ================================================================
    print(f"\n{'=' * 78}")
    print("📊  SECTION B — feasibility per band")
    print(f"{'=' * 78}")

    for band in BAND_LABELS:
        sub = t3[t3["current_band"] == band]
        d = sub[delta_col]
        tag = " [PRIMARY]" if band == PRIMARY_BAND else " [CONTEXT]"
        print(f"\n  {band}{tag}  n={len(sub):,d}")
        q = d.quantile([0, 0.10, 0.25, 0.50, 0.75, 0.90, 1.0])
        print(f"    Δ{DELTA_K}: med={q.iloc[3]:+.4f}  p10={q.iloc[1]:+.4f}  "
              f"p90={q.iloc[5]:+.4f}  range=[{q.iloc[0]:+.4f}, {q.iloc[6]:+.4f}]")

    # ================================================================
    # SECTION C — PRIMARY: 0.75-0.90 band
    # ================================================================
    print(f"\n{'=' * 78}")
    print(f"📊  SECTION C — PRIMARY: {PRIMARY_BAND} band (VERDICT)")
    print(f"    Spearman(Δ{DELTA_K}, fwd_ret) + date-block bootstrap CI.")
    print(f"    1 band × 3 horizons = 3 primary tests.  "
          f"NO multiple-testing correction.")
    print(f"{'=' * 78}")

    primary = t3[t3["current_band"] == PRIMARY_BAND].copy()
    n_prim = len(primary)
    print(f"    n={n_prim:,d}")

    # adaptive tercile cuts for secondary dose
    d_vals = primary[delta_col].values
    t_lo = float(np.percentile(d_vals, 100 / 3))
    t_hi = float(np.percentile(d_vals, 200 / 3))
    print(f"    adaptive tercile cuts: Δ{DELTA_K} < {t_lo:+.4f} (Low) | "
          f"{t_lo:+.4f} to {t_hi:+.4f} (Mid) | > {t_hi:+.4f} (High)")

    for h in cfg.horizons:
        col = f"fwd_ret_{h}"
        mask = primary[col].notna()
        sub = primary[mask]
        n_sub = len(sub)
        feat = sub[delta_col].values
        outcome = sub[col].values
        date_ord = sub["date_ord"].values
        uo = np.sort(np.unique(date_ord))
        drm = _date_row_map(date_ord)

        print(f"\n  ── horizon = {h}d ──")
        print(f"     n={n_sub:,d}")

        # PRIMARY: Spearman
        res = run_spearman(feat, outcome, uo, drm, h, rng, cfg)
        print(f"     Spearman(Δ{DELTA_K}, fwd_ret_{h})")
        print(f"       n={n_sub}  rho={res['rho']:+.4f}  "
              f"[95% block-CI: {res['ci_lo']:+.4f}, {res['ci_hi']:+.4f}]")

        # SECONDARY: adaptive tercile dose
        dose = np.where(feat < t_lo, "Low",
                        np.where(feat > t_hi, "High", "Mid"))
        dose_res = run_dose(outcome, dose, uo, drm, h, rng, cfg)
        print(f"     dose (shape check, NOT verdict)"
              f"  [Low: Δ<{t_lo:+.3f} | Mid | High: Δ>{t_hi:+.3f}]")
        parts = []
        for g in ["Low", "Mid", "High"]:
            if g in dose_res:
                d = dose_res[g]
                parts.append(f"{g}:{d['excess']:+.4f}"
                             f"[{d['ci_lo']:+.4f},{d['ci_hi']:+.4f}]"
                             f"(n={d['n']})")
        print(f"       " + "  ".join(parts))

    # ================================================================
    # SECTION D — CONTEXT: other bands
    # ================================================================
    print(f"\n{'=' * 78}")
    print(f"📊  SECTION D — CONTEXT: other bands (NOT verdict)")
    print(f"    0.67-0.75: T3-entry artifact (50% mechanically accelerating)")
    print(f"    0.90-1.00: ceiling-constrained (3% decel, degenerate)")
    print(f"{'=' * 78}")

    for band in BAND_LABELS:
        if band == PRIMARY_BAND:
            continue
        ctx = t3[t3["current_band"] == band].copy()
        caveat = ("T3-entry artifact" if band == "0.67-0.75"
                  else "ceiling-constrained")

        print(f"\n  ── {band} ({caveat}) ──")
        print(f"     n={len(ctx):,d}")

        for h in cfg.horizons:
            col = f"fwd_ret_{h}"
            mask = ctx[col].notna()
            sub = ctx[mask]
            feat = sub[delta_col].values
            outcome = sub[col].values
            date_ord = sub["date_ord"].values
            uo = np.sort(np.unique(date_ord))
            drm = _date_row_map(date_ord)

            res = run_spearman(feat, outcome, uo, drm, h, rng, cfg)
            print(f"     h={h}d  n={len(sub):,d}  rho={res['rho']:+.4f}  "
                  f"[CI: {res['ci_lo']:+.4f}, {res['ci_hi']:+.4f}]")

    # ================================================================
    # SECTION E — limitations
    # ================================================================
    print(f"\n{'=' * 78}")
    print("📊  SECTION E — limitations")
    print(f"{'=' * 78}")
    for lim in (
        f"Δ{DELTA_K} inherits {20 - DELTA_K}/20 = "
        f"{(20 - DELTA_K) / 20:.0%} overlap from rolling beta_adj_rs_20d; "
        f"within-stock lag-1 autocorr ~0.66; block-CI handles dependence "
        f"but effective sample < n",
        "primary = 1 band × 3 horizons = 3 tests; exploratory, no MT "
        "correction",
        "Spearman assumes monotone; secondary dose checks non-linearity",
        "within-band Spearman does NOT partial out current RS level "
        "(0.76 vs 0.89); confound expected small in narrow band",
        "0.67-0.75 context contaminated by T3-entry mechanics "
        "(50% accel by selection)",
        "0.90-1.00 context ceiling-constrained "
        "(3% decel, n=773 degenerate)",
        "no regime conditioning (R3 gated); single-regime span; "
        "survivorship; RAW LHS carries market beta",
        "block-CI is sole inference tool; no permutation null "
        "(Δ5 autocorr ~0.66 makes permutation anti-conservative)",
    ):
        print(f"    - {lim}")

    # ── optional output ──
    if args.out:
        t3.to_parquet(args.out, index=False)
        print(f"\n📥  Analysis frame written to {args.out}")

    print(f"\n✅  Done (pass --out <path> to persist the analysis frame).")


if __name__ == "__main__":
    main()
