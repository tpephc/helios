#!/usr/bin/env python3
# scripts/run_phase2a_analysis.py
"""R8 Phase 2A Stability Validation — v0.1.3.

Temporal robustness analysis of the Phase 1 Tier 1 finding:
    Δ_A3 | bull, nlu=0, 10td / 20td

Analyses (all mandatory per r8_phase2a_spec.md v0.3.0):
    P2A-1  Sub-period analysis (4 bull-support-balanced segments)
    P2A-2  Rolling-window analysis (24-month, monthly step, half-open [start, end))
    P2A-3  Influence diagnostics (top-5 individual + top-5 collective appendix)
    P2A-4  Concentration diagnostic (top-1 / top-2 contribution share)

Locked constants (D1–D7 per SPEC v0.3.0):
    N_SEGMENTS              = 4
    TREATMENT_DATES_MIN     = 60      (ADEQUACY_ELIGIBLE floor, segments)
    N_EFF_MIN               = 20      (ADEQUACY_ELIGIBLE floor, all units)
    ROLLING_MONTHS          = 24
    ROLLING_STEP_MONTHS     = 1
    ROLLING_TREATMENT_MIN   = 30      (window eligibility floor)
    ROLLING_N_EFF_MIN       = 20      (DIRECTIONAL_ONLY threshold)
    INFLUENCE_TOP_N         = 5
    G1_MATERIAL_ADVERSE_PCT = -0.01   (-1.0%)
    G1_HARD_FAIL_PCT        = -0.02   (-2.0%)
    G2_STREAK_LENGTH        = 6
    G2_STREAK_MEAN_FAIL_PCT = -0.005  (-0.5%)
    G5_TOP1_THRESHOLD       = 0.60
    G5_TOP2_THRESHOLD       = 0.80
    BOOTSTRAP_REPLICATIONS  = 5000
    BLOCK_LENGTH_PRIMARY    = 20
    SEED                    = 42
    HORIZONS_TD             = [10, 20]

Bootstrap: reuses Phase 1 A-3 run_bootstrap() and _stationary_bootstrap_dates()
           verbatim via import — no reimplementation.
n_eff:     reuses Phase 1 n_eff = n_raw_dates / vif (VIF method, ADR-R8P1-001 D6).

Panel: data/_storage/r8_phase1_remediated/  (Phase 1 clean-panel, commit 4a307e6)
Output: data/_storage/r8_phase2a/v0.1.0/

Usage:
    uv run python scripts/run_phase2a_analysis.py                     # dry-run (default)
    uv run python scripts/run_phase2a_analysis.py --allow-write       # persist artifacts
    uv run python scripts/run_phase2a_analysis.py --analysis p2a1   # single analysis
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from calendar import monthrange
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path bootstrap — must happen before importing Phase 1 helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ---------------------------------------------------------------------------
# Phase 1 helper imports (frozen; do not reimplement)
# Source: scripts/run_r8_phase1_a3.py
# Any changes to the bootstrap method require a Phase 1 SPEC amendment.
# ---------------------------------------------------------------------------

from scripts.run_r8_phase1_a3 import (  # noqa: E402
    BootstrapResult,
    load_panel,
    load_price_series,
    compute_forward_returns,
    run_bootstrap,
)

import duckdb  # noqa: E402  (after path setup)

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------

DB_PATH = _REPO_ROOT / "data/_storage/helios.duckdb"
OUTPUT_DIR = _REPO_ROOT / "data/_storage/r8_phase2a/v0.1.0"
SPEC_PATH = _REPO_ROOT / "research/r8_phase2a_spec.md"

# ---------------------------------------------------------------------------
# Locked SPEC constants (D1–D7 — do not modify without SPEC amendment)
# ---------------------------------------------------------------------------

N_SEGMENTS: int = 4
TREATMENT_DATES_MIN: int = 60
N_EFF_MIN: int = 20
ROLLING_MONTHS: int = 24
ROLLING_STEP_MONTHS: int = 1
ROLLING_TREATMENT_MIN: int = 30
ROLLING_N_EFF_MIN: int = 20
INFLUENCE_TOP_N: int = 5
G1_MATERIAL_ADVERSE_PCT: float = -0.01
G1_HARD_FAIL_PCT: float = -0.02
G2_STREAK_LENGTH: int = 6
G2_STREAK_MEAN_FAIL_PCT: float = -0.005
G5_TOP1_THRESHOLD: float = 0.60
G5_TOP2_THRESHOLD: float = 0.80

BOOTSTRAP_REPLICATIONS: int = 5000
BLOCK_LENGTH_PRIMARY: int = 20
SEED: int = 42
HORIZONS_TD: list[int] = [10, 20]

# Phase 1 Tier 1 fingerprint bounds (bull/nlu=0, full-sample)
# Anchor: Phase 1 artifact a3_primary_inference.parquet v0.2.0 (commit 4a307e6)
#   10td delta_obs = 0.012123, 20td delta_obs = 0.019197
# Tolerance: ±0.002 (= 0.20pp = 20 bps) — allows for panel reconstruction variance
# Source: data/_storage/r8_phase1_a3/v0.2.0/a3_primary_inference.parquet
_FINGERPRINT_BOUNDS: dict[int, tuple[float, float]] = {
    10: (0.010123, 0.014123),
    20: (0.017197, 0.021197),
}

# Target cell (Phase 1 Tier 1)
TARGET_REGIME: str = "bull"
TARGET_NLU: int = 0

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("r8_phase2a")


# ---------------------------------------------------------------------------
# Adequacy classification (Phase 2A three-tier system, SPEC §5)
# n_eff is computed via Phase 1 VIF method (run_bootstrap → n_eff field)
# ---------------------------------------------------------------------------


class AdequacyClass:
    ELIGIBLE = "ADEQUACY_ELIGIBLE"
    DIRECTIONAL_ONLY = "DIRECTIONAL_ONLY"
    INSUFFICIENT = "INSUFFICIENT"


def classify_adequacy(treatment_dates: int, n_eff: float | None) -> str:
    """Classify an analysis unit by Phase 2A adequacy rules (D2).

    ADEQUACY_ELIGIBLE : treatment_dates >= 60 AND n_eff >= 20
    DIRECTIONAL_ONLY  : treatment_dates >= 60 AND n_eff < 20
    INSUFFICIENT      : treatment_dates < 60

    n_eff must be the VIF-based estimate from run_bootstrap(), not an
    approximation. Pass None when bootstrap has not been run (maps to
    INSUFFICIENT regardless of treatment_dates).
    """
    if treatment_dates < TREATMENT_DATES_MIN:
        return AdequacyClass.INSUFFICIENT
    if n_eff is None or n_eff < N_EFF_MIN:
        return AdequacyClass.DIRECTIONAL_ONLY
    return AdequacyClass.ELIGIBLE


def classify_rolling_adequacy(treatment_dates: int, n_eff: float | None) -> str:
    """Classify a rolling window (lower 30-date floor per D3)."""
    if treatment_dates < ROLLING_TREATMENT_MIN:
        return AdequacyClass.INSUFFICIENT
    if n_eff is None or n_eff < ROLLING_N_EFF_MIN:
        return AdequacyClass.DIRECTIONAL_ONLY
    return AdequacyClass.ELIGIBLE


# ---------------------------------------------------------------------------
# Panel filtering helpers
# ---------------------------------------------------------------------------


def filter_target_cell(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (treatment, baseline) filtered to target cell.

    Target cell: regime=bull, near_limit_up=0 (Phase 1 Tier 1).
    Both treatment and baseline are filtered together to preserve the
    date-anchored estimand: baseline rows are RS_T3 non-R8 on R8 event dates.
    """
    mask = (panel["regime"] == TARGET_REGIME) & (panel["near_limit_up"] == TARGET_NLU)
    cell = panel[mask].copy()
    treat = cell[cell["universe"] == "treatment_1"].copy()
    base = cell[cell["universe"] == "baseline_1"].copy()
    log.info(
        "Target cell (bull/nlu=0): %d treatment rows (%d dates), "
        "%d baseline rows (%d dates)",
        len(treat), treat["date"].nunique(),
        len(base), base["date"].nunique(),
    )
    return treat, base


# ---------------------------------------------------------------------------
# Phase 1 fingerprint assertion
# ---------------------------------------------------------------------------


def assert_phase1_fingerprint(
    treat: pd.DataFrame,
    base: pd.DataFrame,
) -> None:
    """Assert full-sample Δ_A3 reproduces Phase 1 v1.0.0 Tier 1 finding.

    This is a lineage check, not an inferential test. It guards against
    silent panel drift between Phase 1 and Phase 2A execution.

    Raises RuntimeError if any horizon falls outside the expected bounds.
    Bounds (±0.002 = 0.20pp = 20 bps): 10td [+1.01%, +1.41%], 20td [+1.72%, +2.12%]
    Source: r8_phase1_interim_findings.md v1.0.0 §6 Tier 1
    """
    log.info("Asserting Phase 1 fingerprint (lineage check) ...")
    failed = []
    for h, (lo, hi) in _FINGERPRINT_BOUNDS.items():
        col = f"fwd_{h}td"
        t_valid = treat[col].dropna()
        b_valid = base[col].dropna()
        if len(t_valid) == 0 or len(b_valid) == 0:
            raise RuntimeError(f"Fingerprint FAIL at {h}td: no valid returns")
        delta = float(t_valid.mean()) - float(b_valid.mean())
        log.info(
            "Fingerprint %dtd: observed=%.4f, expected=[%.4f, %.4f], "
            "diff_bps=%.1f, n_treat=%d, n_base=%d",
            h, delta, lo, hi, (delta - (lo + hi) / 2) * 10000,
            len(t_valid), len(b_valid),
        )
        if not (lo <= delta <= hi):
            failed.append(
                f"{h}td: observed={delta:.4f} outside [{lo:.4f}, {hi:.4f}]"
            )
    if failed:
        raise RuntimeError(
            "Phase 1 fingerprint FAILED — panel has drifted from Phase 1 v1.0.0.\n"
            + "\n".join(failed)
            + "\nDo not proceed with Phase 2A until panel lineage is resolved."
        )
    log.info("Phase 1 fingerprint PASSED — panel lineage confirmed.")


# ---------------------------------------------------------------------------
# Bootstrap wrapper (thin, to provide Phase 2A logging context)
# ---------------------------------------------------------------------------


def _run_bootstrap_cell(
    treat_sub: pd.DataFrame,
    base_sub: pd.DataFrame,
    fwd_col: str,
    context: str,
) -> BootstrapResult | None:
    """Run Phase 1 run_bootstrap() on a sub-panel with logging.

    Returns None if either side has fewer than 5 valid rows.
    """
    t_valid = treat_sub[treat_sub[fwd_col].notna()]
    b_valid = base_sub[base_sub[fwd_col].notna()]
    if len(t_valid) < 5 or len(b_valid) < 5:
        log.warning("%s: insufficient rows (treat=%d, base=%d), skipping bootstrap",
                    context, len(t_valid), len(b_valid))
        return None
    return run_bootstrap(
        treatment_df=t_valid,
        baseline_df=b_valid,
        fwd_col=fwd_col,
        block_length=BLOCK_LENGTH_PRIMARY,
        n_replications=BOOTSTRAP_REPLICATIONS,
        seed=SEED,
    )


# ---------------------------------------------------------------------------
# P2A-1: Sub-period analysis
# ---------------------------------------------------------------------------


def construct_segments(
    treat: pd.DataFrame,
    n_segments: int = N_SEGMENTS,
) -> list[tuple[date, date]]:
    """Construct N bull-support-balanced segments by quantile cut.

    Segments are temporally contiguous. Boundaries are set at treatment
    date quantiles so each segment has approximately equal treatment_dates.
    The last segment absorbs any remainder from integer division.
    """
    treat_dates = sorted(treat["date"].unique())
    n_dates = len(treat_dates)
    segment_size = n_dates // n_segments
    boundaries: list[tuple[date, date]] = []
    for i in range(n_segments):
        start_idx = i * segment_size
        end_idx = (i + 1) * segment_size - 1 if i < n_segments - 1 else n_dates - 1
        boundaries.append((treat_dates[start_idx], treat_dates[end_idx]))
        log.info(
            "Segment %d: %s to %s (%d treatment dates)",
            i + 1, treat_dates[start_idx], treat_dates[end_idx],
            end_idx - start_idx + 1,
        )
    return boundaries


def run_p2a1(
    treat: pd.DataFrame,
    base: pd.DataFrame,
    horizons: list[int] = HORIZONS_TD,
) -> list[dict]:
    """P2A-1: Sub-period analysis.

    Each segment uses date-anchored filtering: baseline rows are those
    on treatment dates within the segment (preserving the A-3 estimand).
    """
    segments = construct_segments(treat)
    results: list[dict] = []

    for seg_id, (seg_start, seg_end) in enumerate(segments, start=1):
        log.info("=== Segment %d: %s – %s ===", seg_id, seg_start, seg_end)

        # Date-anchored filter: treatment defines the date window;
        # baseline is restricted to the same date window.
        t_seg = treat[(treat["date"] >= seg_start) & (treat["date"] <= seg_end)].copy()
        b_seg = base[(base["date"] >= seg_start) & (base["date"] <= seg_end)].copy()

        t_dates_count = t_seg["date"].nunique()

        for h in horizons:
            col = f"fwd_{h}td"
            context = f"P2A-1 seg={seg_id} h={h}td"

            boot = _run_bootstrap_cell(t_seg, b_seg, col, context)

            n_eff = boot.n_eff if boot is not None else None
            adequacy = classify_adequacy(t_dates_count, n_eff)

            row: dict = {
                "segment_id": seg_id,
                "date_start": seg_start,
                "date_end": seg_end,
                "horizon_td": h,
                "treatment_dates": t_dates_count,
                "treatment_events": len(t_seg),
                "baseline_events": len(b_seg),
                "adequacy_class": adequacy,
                "delta_obs": boot.delta_obs if boot else (
                    float(t_seg[col].dropna().mean() - b_seg[col].dropna().mean())
                    if t_seg[col].notna().any() and b_seg[col].notna().any() else None
                ),
                "n_eff": n_eff,
                # CI and p-value only for ADEQUACY_ELIGIBLE
                "ci_lo": boot.ci_lo if (boot and adequacy == AdequacyClass.ELIGIBLE) else None,
                "ci_hi": boot.ci_hi if (boot and adequacy == AdequacyClass.ELIGIBLE) else None,
                "p_value": boot.p_value if (boot and adequacy == AdequacyClass.ELIGIBLE) else None,
                "se_bootstrap": boot.se_bootstrap if boot else None,
                "vif": boot.vif if boot else None,
                "n_bootstrap_used": boot.n_bootstrap_used if boot else None,
            }

            if boot:
                log.info(
                    "%s: delta=%.4f, n_eff=%.1f, CI=[%.4f, %.4f], p=%.4f [%s]",
                    context, boot.delta_obs, boot.n_eff,
                    boot.ci_lo, boot.ci_hi, boot.p_value, adequacy,
                )
            results.append(row)

    return results


# ---------------------------------------------------------------------------
# P2A-2: Rolling-window analysis
# ---------------------------------------------------------------------------


def _month_offset(d: date, months: int) -> date:
    """Return date offset by N calendar months (day clamped to month end)."""
    month = (d.month - 1 + months) % 12 + 1
    year = d.year + (d.month - 1 + months) // 12
    day = min(d.day, monthrange(year, month)[1])
    return date(year, month, day)


def run_p2a2(
    treat: pd.DataFrame,
    base: pd.DataFrame,
    horizons: list[int] = HORIZONS_TD,
) -> list[dict]:
    """P2A-2: Rolling-window analysis (24-month, monthly step).

    Windows are half-open intervals [start, end) to avoid off-by-one
    at monthly boundaries. end = _month_offset(start, ROLLING_MONTHS).
    """
    treat_dates_sorted = sorted(treat["date"].unique())
    first_date = treat_dates_sorted[0]
    last_date = treat_dates_sorted[-1]

    window_starts: list[date] = []
    cursor = first_date
    while True:
        win_end = _month_offset(cursor, ROLLING_MONTHS)
        if win_end > last_date:
            break
        window_starts.append(cursor)
        cursor = _month_offset(cursor, ROLLING_STEP_MONTHS)

    log.info("P2A-2: %d rolling windows to evaluate", len(window_starts))
    results: list[dict] = []

    for win_start in window_starts:
        win_end = _month_offset(win_start, ROLLING_MONTHS)

        # Half-open interval [start, end)
        t_win = treat[(treat["date"] >= win_start) & (treat["date"] < win_end)].copy()
        b_win = base[(base["date"] >= win_start) & (base["date"] < win_end)].copy()

        t_dates_count = t_win["date"].nunique()

        for h in horizons:
            col = f"fwd_{h}td"
            context = f"P2A-2 win={win_start} h={h}td"

            boot = _run_bootstrap_cell(t_win, b_win, col, context)
            n_eff = boot.n_eff if boot else None
            adequacy = classify_rolling_adequacy(t_dates_count, n_eff)

            row: dict = {
                "window_start": win_start,
                "window_end": win_end,
                "horizon_td": h,
                "treatment_dates": t_dates_count,
                "adequacy_class": adequacy,
                "delta_obs": boot.delta_obs if boot else (
                    float(t_win[col].dropna().mean() - b_win[col].dropna().mean())
                    if t_win[col].notna().any() and b_win[col].notna().any() else None
                ),
                "n_eff": n_eff,
                "ci_lo": boot.ci_lo if boot else None,
                "ci_hi": boot.ci_hi if boot else None,
                "p_value": boot.p_value if boot else None,
            }
            results.append(row)

    return results


# ---------------------------------------------------------------------------
# P2A-3: Influence diagnostics
# ---------------------------------------------------------------------------


def compute_date_contributions(
    treat: pd.DataFrame,
    base: pd.DataFrame,
    horizon: int,
) -> pd.Series:
    """Jackknife LOO: contribution of each treatment date to delta_obs.

    Contribution_d = delta_full - delta_loo_d

    For each treatment date d, both treatment AND baseline rows on date d
    are removed (date-anchored estimand). This preserves the A-3 counterfactual:
    baseline is RS_T3 non-R8 on R8 event dates; removing an R8 date removes
    it from both sides.

    Positive contribution: date inflates delta.
    Negative contribution: date deflates delta.
    """
    col = f"fwd_{horizon}td"
    t_full = treat[col].dropna()
    b_full = base[col].dropna()
    delta_full = float(t_full.mean()) - float(b_full.mean())

    contributions: dict[date, float] = {}
    for d in sorted(treat["date"].unique()):
        t_loo = treat[treat["date"] != d][col].dropna()
        b_loo = base[base["date"] != d][col].dropna()  # date-anchored removal
        if len(t_loo) == 0:
            continue
        delta_loo = (float(t_loo.mean()) - float(b_loo.mean())) if len(b_loo) > 0 else float("nan")
        if not np.isnan(delta_loo):
            contributions[d] = delta_full - delta_loo

    return pd.Series(contributions).sort_values(ascending=False)


def run_p2a3(
    treat: pd.DataFrame,
    base: pd.DataFrame,
    horizon: int = 20,
) -> dict:
    """P2A-3: Influence diagnostics.

    Individual removal runs: remove ONLY date_i from both treatment and
    baseline (not cumulative). Each run is independent.

    Collective removal appendix: remove all top-N dates simultaneously.
    This is the mandatory appendix per SPEC §12; it is not a gate input.

    G3 gate applies to: top-1 individual removal only.
    """
    log.info("P2A-3: Computing jackknife contributions at %dtd ...", horizon)
    contributions = compute_date_contributions(treat, base, horizon)

    top_dates = contributions.abs().nlargest(INFLUENCE_TOP_N).index.tolist()
    log.info("Top-%d influential dates (by abs contribution): %s",
             INFLUENCE_TOP_N, top_dates)

    col = f"fwd_{horizon}td"
    removal_results: list[dict] = []

    # --- Baseline (no removal) ---
    boot_full = _run_bootstrap_cell(treat, base, col, "P2A-3 baseline")
    if boot_full is None:
        raise RuntimeError("P2A-3: full-sample bootstrap failed — cannot proceed")

    removal_results.append({
        "run": "baseline",
        "removal_type": "none",
        "dates_removed": [],
        "n_dates_removed": 0,
        "treatment_dates_remaining": treat["date"].nunique(),
        "delta_obs": boot_full.delta_obs,
        "ci_lo": boot_full.ci_lo,
        "ci_hi": boot_full.ci_hi,
        "p_value": boot_full.p_value,
        "n_eff": boot_full.n_eff,
        "delta_vs_baseline": 0.0,
        "ci_lo_crossed_zero": False,
        "sign_reversal": False,
        "is_gate_input": False,
        "is_appendix": False,
    })

    # --- Individual removal (top-1 through top-N, each independent) ---
    # G3 gate applies to top-1 only; top-2 through top-N are diagnostics.
    for k, d in enumerate(top_dates, start=1):
        t_sub = treat[treat["date"] != d].copy()
        b_sub = base[base["date"] != d].copy()  # date-anchored removal

        context = f"P2A-3 individual remove_date_{k}"
        boot = _run_bootstrap_cell(t_sub, b_sub, col, context)
        if boot is None:
            log.warning("P2A-3 individual removal %d: bootstrap failed, skipping", k)
            continue

        delta_vs_base = boot.delta_obs - boot_full.delta_obs
        ci_lo_crossed = boot.ci_lo < 0.0
        sign_reversal = (boot_full.delta_obs > 0) and (boot.delta_obs < 0)
        is_gate_input = (k == 1)  # G3 gate applies to top-1 only

        removal_results.append({
            "run": f"individual_remove_date_{k}",
            "removal_type": "individual",
            "dates_removed": [str(d)],
            "n_dates_removed": 1,
            "treatment_dates_remaining": t_sub["date"].nunique(),
            "delta_obs": boot.delta_obs,
            "ci_lo": boot.ci_lo,
            "ci_hi": boot.ci_hi,
            "p_value": boot.p_value,
            "n_eff": boot.n_eff,
            "delta_vs_baseline": delta_vs_base,
            "ci_lo_crossed_zero": ci_lo_crossed,
            "sign_reversal": sign_reversal,
            "is_gate_input": is_gate_input,
            "is_appendix": not is_gate_input,
        })

        log.info(
            "%s: date=%s delta=%.4f (Δ=%.4f), CI=[%.4f, %.4f], "
            "ci_lo_crossed=%s, sign_reversal=%s [G3=%s]",
            context, d, boot.delta_obs, delta_vs_base,
            boot.ci_lo, boot.ci_hi,
            ci_lo_crossed, sign_reversal,
            "GATE" if is_gate_input else "diagnostic",
        )

    # --- Collective removal appendix (all top-N simultaneously) ---
    t_coll = treat[~treat["date"].isin(top_dates)].copy()
    b_coll = base[~base["date"].isin(top_dates)].copy()

    boot_coll = _run_bootstrap_cell(t_coll, b_coll, col, "P2A-3 collective_appendix")
    if boot_coll is not None:
        delta_vs_base = boot_coll.delta_obs - boot_full.delta_obs
        sign_reversal = (boot_full.delta_obs > 0) and (boot_coll.delta_obs < 0)
        removal_results.append({
            "run": f"collective_remove_top_{INFLUENCE_TOP_N}_appendix",
            "removal_type": "collective",
            "dates_removed": [str(d) for d in top_dates],
            "n_dates_removed": len(top_dates),
            "treatment_dates_remaining": t_coll["date"].nunique(),
            "delta_obs": boot_coll.delta_obs,
            "ci_lo": boot_coll.ci_lo,
            "ci_hi": boot_coll.ci_hi,
            "p_value": boot_coll.p_value,
            "n_eff": boot_coll.n_eff,
            "delta_vs_baseline": delta_vs_base,
            "ci_lo_crossed_zero": boot_coll.ci_lo < 0.0,
            "sign_reversal": sign_reversal,
            "is_gate_input": False,
            "is_appendix": True,
        })
        log.info(
            "P2A-3 collective appendix (top-%d removed): "
            "delta=%.4f (Δ=%.4f), CI=[%.4f, %.4f], sign_reversal=%s",
            INFLUENCE_TOP_N, boot_coll.delta_obs, delta_vs_base,
            boot_coll.ci_lo, boot_coll.ci_hi, sign_reversal,
        )

    return {
        "contributions": contributions,
        "top_dates": top_dates,
        "removal_results": removal_results,
    }


# ---------------------------------------------------------------------------
# P2A-4: Concentration diagnostic
# ---------------------------------------------------------------------------


def run_p2a4(segment_results: list[dict], horizon: int = 20) -> dict:
    """P2A-4: Concentration diagnostic (G5, mandatory, not a hard gate).

    Contribution shares computed over positive-delta ADEQUACY_ELIGIBLE and
    DIRECTIONAL_ONLY segments (INSUFFICIENT excluded).
    """
    eligible = [
        r for r in segment_results
        if r["horizon_td"] == horizon
        and r["adequacy_class"] != AdequacyClass.INSUFFICIENT
        and r["delta_obs"] is not None
    ]

    if not eligible:
        log.warning("P2A-4: No eligible segments for concentration diagnostic")
        return {
            "eligible_segments": 0,
            "top1_share": None,
            "top2_share": None,
            "material_concentration": False,
            "concentration_note": "No eligible segments",
        }

    deltas = {r["segment_id"]: r["delta_obs"] for r in eligible}
    positive_deltas = {sid: d for sid, d in deltas.items() if d > 0}

    if not positive_deltas:
        return {
            "eligible_segments": len(eligible),
            "deltas_by_segment": deltas,
            "top1_share": None,
            "top2_share": None,
            "material_concentration": False,
            "concentration_note": "No positive-delta segments; shares undefined",
        }

    total_positive = sum(positive_deltas.values())
    # Sort by delta descending, preserving segment identity (SPEC: identity must be disclosed)
    sorted_items = sorted(positive_deltas.items(), key=lambda kv: kv[1], reverse=True)
    sorted_positive = [v for _, v in sorted_items]

    top1_segment_id = sorted_items[0][0]
    top2_segment_ids = [sid for sid, _ in sorted_items[:2]]

    top1_share = sorted_positive[0] / total_positive
    top2_share = (
        sum(sorted_positive[:2]) / total_positive
        if len(sorted_positive) >= 2 else top1_share
    )
    material = (top1_share > G5_TOP1_THRESHOLD) or (top2_share > G5_TOP2_THRESHOLD)

    log.info(
        "P2A-4 (%dtd): top1_share=%.3f (seg %s), top2_share=%.3f (segs %s), material=%s",
        horizon, top1_share, top1_segment_id, top2_share, top2_segment_ids, material,
    )

    return {
        "eligible_segments": len(eligible),
        "deltas_by_segment": deltas,
        "top1_segment_id": top1_segment_id,
        "top2_segment_ids": top2_segment_ids,
        "top1_share": top1_share,
        "top2_share": top2_share,
        "material_concentration": material,
        "concentration_note": (
            f"Material concentration: top-1={top1_share:.1%} (seg {top1_segment_id}), "
            f"top-2={top2_share:.1%} (segs {top2_segment_ids}). "
            "Phase 2B must incorporate into capacity assumptions."
            if material else
            f"Distributed effect: top-1={top1_share:.1%} (seg {top1_segment_id}), "
            f"top-2={top2_share:.1%} (segs {top2_segment_ids})."
        ),
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _sha256_file(path: Path) -> str:
    if not path.exists():
        return "missing"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_artifacts(
    p2a1_results: list[dict],
    p2a2_results: list[dict],
    p2a3_results: dict,
    p2a4_results: dict,
    started_at: datetime,
) -> None:
    """Write all Phase 2A artifacts. Called only after fingerprint PASS."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    segments_dir = OUTPUT_DIR / "segments"
    rolling_dir = OUTPUT_DIR / "rolling"
    influence_dir = OUTPUT_DIR / "influence"
    concentration_dir = OUTPUT_DIR / "concentration"
    for d in [segments_dir, rolling_dir, influence_dir, concentration_dir]:
        d.mkdir(exist_ok=True)

    seg_path = segments_dir / "p2a1_segment_results.parquet"
    pd.DataFrame(p2a1_results).to_parquet(seg_path, index=False)

    roll_path = rolling_dir / "p2a2_rolling_results.parquet"
    pd.DataFrame(p2a2_results).to_parquet(roll_path, index=False)

    removal_path = influence_dir / "p2a3_removal_results.parquet"
    pd.DataFrame(p2a3_results["removal_results"]).to_parquet(removal_path, index=False)

    contrib_df = p2a3_results["contributions"].reset_index()
    contrib_df.columns = ["date", "contribution"]
    contrib_path = influence_dir / "p2a3_contributions.parquet"
    contrib_df.to_parquet(contrib_path, index=False)

    p2a4_serial = {
        k: (
            {str(kk): float(vv) for kk, vv in v.items()}
            if isinstance(v, dict) else v
        )
        for k, v in p2a4_results.items()
    }
    conc_path = concentration_dir / "p2a4_concentration.json"
    conc_path.write_text(json.dumps(p2a4_serial, indent=2))

    manifest = {
        "spec_version": "r8_phase2a_spec.md v0.3.0",
        "script_version": "v0.1.3",
        "artifact_namespace": "v0.1.0",
        "artifact_namespace_note": (
            "Artifact namespace frozen at first executable SPEC version (v0.1.0). "
            "SPEC version (v0.3.0) reflects governance revisions only; "
            "no D1–D7 parameters were modified."
        ),
        "phase1_panel_commit": "4a307e6",
        "bootstrap_source": "scripts/run_r8_phase1_a3.py (imported, not reimplemented)",
        "bootstrap_method": "stationary",
        "resampling_unit": "trading_date",
        "block_length_primary": BLOCK_LENGTH_PRIMARY,
        "replications": BOOTSTRAP_REPLICATIONS,
        "ci_method": "percentile",
        "p_value_method": "null_shifted_two_tailed",
        "n_eff_method": "vif_based (n_raw_dates / vif), ADR-R8P1-001 D6",
        "seed": SEED,
        "target_regime": TARGET_REGIME,
        "target_nlu": TARGET_NLU,
        "horizons_td": HORIZONS_TD,
        "n_segments": N_SEGMENTS,
        "treatment_dates_min": TREATMENT_DATES_MIN,
        "n_eff_min": N_EFF_MIN,
        "rolling_months": ROLLING_MONTHS,
        "rolling_window_interval": "half-open [start, end)",
        "rolling_treatment_min": ROLLING_TREATMENT_MIN,
        "influence_top_n": INFLUENCE_TOP_N,
        "p2a3_individual_removal": "independent per date (not cumulative)",
        "p2a3_collective_removal": "top-5 simultaneously (mandatory appendix, not gate input)",
        "fingerprint_bounds": {
            str(h): {"lo": lo, "hi": hi}
            for h, (lo, hi) in _FINGERPRINT_BOUNDS.items()
        },
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "outputs": {
            "p2a1_segments": str(seg_path),
            "p2a2_rolling": str(roll_path),
            "p2a3_removal": str(removal_path),
            "p2a3_contributions": str(contrib_path),
            "p2a4_concentration": str(conc_path),
        },
        "output_hashes": {
            "p2a1_segments": _sha256_file(seg_path),
            "p2a2_rolling": _sha256_file(roll_path),
            "p2a3_removal": _sha256_file(removal_path),
            "p2a4_concentration": _sha256_file(conc_path),
        },
    }
    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    log.info("Artifacts written to: %s", OUTPUT_DIR)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="R8 Phase 2A stability validation v0.1.3")
    p.add_argument("--allow-write", action="store_true",
                   help="Write artifacts to output directory (default: dry-run only)")
    p.add_argument(
        "--analysis",
        choices=["p2a1", "p2a2", "p2a3", "p2a4", "all"],
        default="all",
        help="Which analysis to run (default: all)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    started_at = datetime.now(timezone.utc)

    log.info(
        "R8 Phase 2A v0.1.3 starting — spec=r8_phase2a_spec.md v0.3.0, "
        "analysis=%s, allow_write=%s",
        args.analysis, args.allow_write,
    )

    if not SPEC_PATH.exists():
        log.error("SPEC not found: %s — governance chain broken", SPEC_PATH)
        sys.exit(1)

    # Load panel (reuses Phase 1 helpers verbatim)
    log.info("Connecting to DuckDB (read-only): %s", DB_PATH)
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        panel = load_panel(con)
        prices = load_price_series(con)
    finally:
        con.close()

    panel = compute_forward_returns(panel, prices, horizons=[1, 5, 10, 20])
    treat, base = filter_target_cell(panel)

    # Fingerprint assertion — must pass before any analysis proceeds
    try:
        assert_phase1_fingerprint(treat, base)
    except RuntimeError as exc:
        log.error("FINGERPRINT FAILED: %s", exc)
        log.error("Phase 2A ABORTED — resolve panel lineage before proceeding.")
        sys.exit(1)

    # Run analyses
    p2a1_results: list[dict] = []
    p2a2_results: list[dict] = []
    p2a3_results: dict = {}
    p2a4_results: dict = {}

    if args.analysis in ("p2a1", "all"):
        log.info("--- P2A-1: Sub-period analysis ---")
        p2a1_results = run_p2a1(treat, base)

    if args.analysis in ("p2a2", "all"):
        log.info("--- P2A-2: Rolling-window analysis ---")
        p2a2_results = run_p2a2(treat, base)

    if args.analysis in ("p2a3", "all"):
        log.info("--- P2A-3: Influence diagnostics ---")
        p2a3_results = run_p2a3(treat, base, horizon=20)

    if args.analysis in ("p2a4", "all") and p2a1_results:
        log.info("--- P2A-4: Concentration diagnostic ---")
        p2a4_results = run_p2a4(p2a1_results, horizon=20)

    if args.allow_write:
        save_artifacts(
            p2a1_results, p2a2_results,
            p2a3_results, p2a4_results,
            started_at,
        )
    else:
        log.info("Dry-run mode (default) — no files written. Use --allow-write to persist artifacts.")

    log.info("Phase 2A complete.")


if __name__ == "__main__":
    main()
