#!/usr/bin/env python3
# scripts/run_phase5_analysis.py
"""Phase 5 Configuration Selection — v0.1.0.

Entry point for R8 Phase 5 analysis per research/r8_phase5_spec.md v0.1.0 (LOCKED).

Arms:
    A — 20td + FIFO            (frozen Phase 3 baseline; lineage verification only)
    B — 20td + RS-60d ranking  (isolated ranking effect; Phase 4 CANDIDATE)
    C — 10td + RS-60d ranking  (combined candidate; primary Phase 5 question)

Gate criteria (D2 — relative vs Arm A, Low-Uplift only):
    P5-G1: Sharpe(arm, LU) - Sharpe(A, LU)        >= -0.10
    P5-G2: MaxDD(arm, LU)  - MaxDD(A, LU)          <=  +3pp
    P5-G3: admission_rate(arm) - admission_rate(A) >= +10pp  [Arm C only]

Governance invariants:
    - Panel and forward returns loaded via Phase 4 helpers (identical CTE).
    - Phase 5 requires fwd_10td (Arm C) and fwd_20td (Arms A/B).
    - P3-FP-001 fingerprint verified before any arm analysis:
      full-sample 20td net_s1 = +1.64% ± 1bp.  Failure aborts.
    - Arm A must reproduce Phase 3/4 reference values (Sharpe 2.378/1.613,
      admission 16.3%/17.5%) within tolerance.  Material deviation aborts.
    - Bootstrap Δ_A3 computed per arm at arm's holding horizon; reported as
      supplementary only — NOT used as gate criterion (D2).
    - Track C (early exit rules) is out of scope; raises NotImplementedError.
    - No silent edits to locked artifacts or SPEC.

Patches applied to v0.1.0 before first production run:
    P5-FIX-001  Verdict dead branch: compute_verdict() rewritten with explicit
                arm_b_passed/arm_c_passed booleans.  The original elif block
                was unreachable because a passing arm is already captured in
                the first if-branch.  (Reviewer finding: HIGH RISK.)
    P5-FIX-002  ARM_A_REFERENCE comment: clarified that low_uplift
                admission_rate=0.175 comes from Phase 4 Track A, not Phase 3.
    P5-FIX-003  Artifact gate columns: added gate_applicable column and changed
                gate_* columns for non-evaluated rows to None (not NaN) to
                distinguish "not applicable" from "missing".
    P5-FIX-004  rank_col invariant: added post-_rank_ledger check that
                rank_col exists and is non-null in the ledger.  Prevents silent
                FIFO fallback if bulk join from bullish_features failed.
    P5-REF-001  ARM_A_REFERENCE updated to Phase 5 price-snapshot baseline
                (full_sample Sharpe 2.378→2.498, low_uplift Sharpe 1.613→1.569).
                Root cause: daily_price_adj retroactive adjustment detected
                during Phase 5 execution (first NAV divergence 2023-07-14,
                694 of 1013 common dates affected).  Phase 3/4 artifacts remain
                locked; locked values preserved in _LOCKED_PHASE3_REFERENCE.
                See research/r8_phase5_price_snapshot_refresh_note.md.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Repo root and dependency imports
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import duckdb  # noqa: E402

from scripts.run_r8_phase1_a3 import (  # noqa: E402
    load_panel,
    load_price_series,
    compute_forward_returns,
)
from scripts.run_phase3_analysis import (  # noqa: E402
    COMMISSION_RT,
    SLIPPAGE,
    DataGapReport,
    FingerprintResult,
    ScheduledPosition,
    compute_risk_metrics,
    load_daily_price_paths,
    reconstruct_nav,
    validate_schema_and_document_gaps,
)
from scripts.run_phase4_analysis import (  # noqa: E402
    build_signal_ledger_for_horizon,
    reconstruct_nav_for_horizon,
    schedule_positions,
    bootstrap_block_length,
    _rank_ledger,
    verify_p3_fingerprint,
    SEGMENT_DATES,
    SCENARIO_POOLS,
    TARGET_REGIME,
    TARGET_NLU,
    BASELINE_CAP,
    BASELINE_MAX_POS,
    BOOTSTRAP_B,
    TRADING_DAYS_PER_YEAR,
)

# ---------------------------------------------------------------------------
# Frozen constants
# ---------------------------------------------------------------------------

DB_PATH: Final[Path] = _REPO_ROOT / "data/_storage/helios.duckdb"
ARTIFACT_DIR: Final[Path] = _REPO_ROOT / "data/_storage/r8_phase5/v0.1.0"
SCRIPT_VERSION: Final[str] = "0.1.0"
SPEC_VERSION: Final[str] = "0.1.0"

# Phase 5 price-snapshot baseline for Arm A lineage check.
#
# These values are recomputed from the current DuckDB adj-price snapshot
# (2026-06-08) and differ from Phase 3/4 locked artifacts due to a
# retroactive adjustment in daily_price_adj detected during Phase 5 execution.
#
# Governance framing (APPROVE OPTION A, 2026-06-08):
#   - Phase 3/4 artifacts remain locked and are NOT overwritten.
#   - Phase 5 detects adj price retroactive update (first NAV divergence
#     at 2023-07-14; likely TWSE corporate action / ex-dividend restatement).
#   - Phase 5 uses the current adj-price snapshot for ALL arms (A, B, C)
#     to preserve cross-arm comparability on a consistent price basis.
#   - These reference values are the Phase 5 price-snapshot baseline,
#     not a revision of Phase 3/4 findings.
#
# Source (current snapshot, recomputed 2026-06-08):
#   full_sample Sharpe/MaxDD/admission: Arm A Phase 5 recompute
#   low_uplift  Sharpe/MaxDD/admission: Arm A Phase 5 recompute
#   locked Phase 3 full_sample nav_end=6.477569 sharpe=2.377654
#   Phase 5 recomputed  nav_end=6.974622 sharpe=2.498050
#   low_uplift Sharpe delta vs Phase 3: −0.044 (within tolerance — recent
#     adj prices stable; drift concentrated in pre-2024 history)
ARM_A_REFERENCE: Final[dict[str, dict[str, float]]] = {
    "full_sample": {"sharpe": 2.498, "max_dd": 0.2165, "admission_rate": 0.163},
    "low_uplift":  {"sharpe": 1.569, "max_dd": 0.2054, "admission_rate": 0.175},
}

# Locked Phase 3/4 values retained here as historical reference only.
# Do NOT use these as gate reference — use ARM_A_REFERENCE above.
_LOCKED_PHASE3_REFERENCE: Final[dict[str, dict[str, float]]] = {
    "full_sample": {"sharpe": 2.378, "max_dd": 0.2165, "admission_rate": 0.163,
                    "nav_end": 6.477569},
    "low_uplift":  {"sharpe": 1.613, "max_dd": 0.2050, "admission_rate": 0.175},
}
# Tolerance for Arm A lineage verification
ARM_A_SHARPE_TOL: Final[float] = 0.05   # ±0.05 Sharpe — beyond this is a data issue
ARM_A_ADMISSION_TOL: Final[float] = 0.02  # ±2pp admission rate

# Gate thresholds (D2 — governance heuristics, not statistical boundaries)
GATE_P5_G1_MIN_DELTA_SHARPE: Final[float] = -0.10   # Sharpe(arm) - Sharpe(A) >= -0.10
GATE_P5_G2_MAX_DELTA_MAXDD: Final[float] = 0.03     # MaxDD(arm) - MaxDD(A) <= +3pp
GATE_P5_G3_MIN_DELTA_ADMISSION: Final[float] = 0.10  # admission(arm) - admission(A) >= +10pp

# Arm definitions (D1 — frozen per SPEC §3)
ARM_CONFIGS: Final[dict[str, dict]] = {
    "arm_a": {"h": 20, "rank_col": None,               "label": "20td + FIFO"},
    "arm_b": {"h": 20, "rank_col": "beta_adj_rs_60d",  "label": "20td + RS-60d"},
    "arm_c": {"h": 10, "rank_col": "beta_adj_rs_60d",  "label": "10td + RS-60d"},
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class GateResult:
    """Evaluation of a single gate criterion for one arm × scenario."""

    gate_id: str
    arm: str
    scenario: str
    arm_value: float
    reference_value: float
    delta: float
    threshold: float
    passed: bool
    note: str = ""


@dataclass
class ArmResult:
    """Full result for one arm × scenario."""

    arm: str
    scenario: str
    h: int
    rank_col: str | None
    label: str
    n_candidates: int
    n_scheduled: int
    admission_rate: float
    risk_metrics: dict
    bootstrap_delta: dict
    gates: list[GateResult] = field(default_factory=list)
    # Populated after cross-arm comparison
    passed_all_gates: bool = False


@dataclass
class Phase5Verdict:
    """Layer 1 + Layer 2 verdict per SPEC §7.3."""

    layer1: str          # CONFIGURATION_SELECTED | CONFIGURATION_NOT_SELECTED | INCOMPLETE
    layer2: str          # SELECTED: [arm] | FURTHER_RESEARCH_REQUIRED
    # Note: RETAIN_20TD_RS60D_STUDY (defined in SPEC §7.3 for "Arm B passes but
    # Arm C fails") is not emitted by this runner.  Per SPEC §7.3, any arm
    # passing gates yields CONFIGURATION_SELECTED, so Arm-B-pass maps to
    # SELECTED: ARM_B, not to CONFIGURATION_NOT_SELECTED + RETAIN.
    # Emitting RETAIN would require a SPEC amendment.
    selected_arms: list[str]
    gate_summary: dict
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 1. Forward return matrix for Phase 5 horizons
# ---------------------------------------------------------------------------

def build_phase5_forward_returns(
    panel: pd.DataFrame,
    prices: pd.DataFrame,
) -> pd.DataFrame:
    """Compute fwd_10td and fwd_20td for all panel rows.

    Phase 5 requires exactly these two horizons:
        - fwd_20td: Arms A and B
        - fwd_10td: Arm C

    Formula unchanged from Phase 1/4 (frozen):
        fwd_return[T+h] = adj_close[T+h] / adj_open[T+1] - 1
    """
    panel = compute_forward_returns(panel, prices, horizons=[10, 20])
    for h in [10, 20]:
        col = f"fwd_{h}td"
        n = int(panel[col].notna().sum())
        log.info("Phase 5 forward returns: %s valid=%d", col, n)
    return panel


# ---------------------------------------------------------------------------
# 2. Run a single arm
# ---------------------------------------------------------------------------

def run_arm(
    arm_id: str,
    panel: pd.DataFrame,
    prices: pd.DataFrame,
    con: duckdb.DuckDBPyConnection,
) -> list[ArmResult]:
    """Execute one arm for both full_sample and low_uplift scenarios.

    Returns a list of two ArmResult objects (one per scenario).
    Bootstrap Δ_A3 is computed at the arm's holding horizon h.
    """
    cfg = ARM_CONFIGS[arm_id]
    h         = cfg["h"]
    rank_col  = cfg["rank_col"]
    label     = cfg["label"]
    results   = []

    for scenario in ("full_sample", "low_uplift"):
        log.info("--- Arm %s (%s): scenario=%s ---", arm_id.upper(), label, scenario)

        # Build ledger for treatment and baseline pools
        ledger_t = build_signal_ledger_for_horizon(
            panel, prices, "treatment_1", scenario, h, con=con
        )
        ledger_b = build_signal_ledger_for_horizon(
            panel, prices, "baseline_1", scenario, h, con=con
        )

        # Apply ranking for quality arms (B and C use RS-60d)
        ranked_t = _rank_ledger(ledger_t, rank_col, arm_id)

        # P5-FIX-004: invariant — verify ranking column was actually populated
        # after the bulk join in build_signal_ledger_for_horizon.  If rank_col
        # is all-NaN the scheduler falls back to FIFO silently, producing
        # results that look correct but reflect the wrong configuration.
        if rank_col is not None:
            if rank_col not in ranked_t.columns:
                log.error(
                    "Arm %s invariant FAIL: rank_col=%r not in ledger columns %s. "
                    "bulk join may have failed. Aborting.",
                    arm_id.upper(), rank_col, list(ranked_t.columns),
                )
                sys.exit(1)
            non_null = ranked_t[rank_col].notna().sum()
            total    = len(ranked_t)
            if non_null == 0:
                log.error(
                    "Arm %s invariant FAIL: rank_col=%r is entirely NaN (%d/%d rows). "
                    "RS-60d bulk join from bullish_features failed. Aborting.",
                    arm_id.upper(), rank_col, non_null, total,
                )
                sys.exit(1)
            pct = 100.0 * non_null / max(total, 1)
            if pct < 60.0:
                log.warning(
                    "Arm %s: rank_col=%r non-null=%.1f%% (%d/%d). "
                    "Ranking may be unreliable for dates with missing RS-60d.",
                    arm_id.upper(), rank_col, pct, non_null, total,
                )
            else:
                log.info(
                    "Arm %s: rank_col=%r non-null=%.1f%% ✓",
                    arm_id.upper(), rank_col, pct,
                )

        sched_t, diag_t = schedule_positions(ranked_t, BASELINE_CAP, BASELINE_MAX_POS)
        sched_b, diag_b = schedule_positions(ledger_b, BASELINE_CAP, BASELINE_MAX_POS)

        price_t = load_daily_price_paths(con, sched_t)
        price_b = load_daily_price_paths(con, sched_b)

        nav_t = reconstruct_nav_for_horizon(sched_t, price_t, BASELINE_CAP, h)
        nav_b = reconstruct_nav_for_horizon(sched_b, price_b, BASELINE_CAP, h)

        metrics_t = compute_risk_metrics(nav_t, f"{arm_id}_{scenario}")
        metrics_b = compute_risk_metrics(nav_b, f"rs_t3_{arm_id}_{scenario}")

        # Supplementary bootstrap Δ_A3 at arm's horizon
        bootstrap = _bootstrap_delta_a3_two_sample(ledger_t, ledger_b, h)

        results.append(ArmResult(
            arm=arm_id,
            scenario=scenario,
            h=h,
            rank_col=rank_col,
            label=label,
            n_candidates=diag_t["n_candidates"],
            n_scheduled=diag_t["n_scheduled"],
            admission_rate=diag_t["admission_rate"],
            risk_metrics=metrics_t,
            bootstrap_delta=bootstrap,
        ))

    return results


# ---------------------------------------------------------------------------
# 3. Arm A lineage check
# ---------------------------------------------------------------------------

def check_arm_a_lineage(arm_a_results: list[ArmResult]) -> bool:
    """Verify Arm A reproduces Phase 3/4 reference values within tolerance.

    Checks Sharpe and admission rate for both scenarios.  Material deviation
    indicates a data or lineage issue — Phase 5 should abort.

    Returns True if all checks pass; False if any exceed tolerance.
    """
    all_ok = True
    for result in arm_a_results:
        scenario = result.scenario
        ref = ARM_A_REFERENCE[scenario]

        sharpe    = result.risk_metrics.get("sharpe", np.nan)
        admission = result.admission_rate
        max_dd    = result.risk_metrics.get("max_drawdown", np.nan)

        sharpe_delta    = abs(sharpe - ref["sharpe"])
        admission_delta = abs(admission - ref["admission_rate"])

        sharpe_ok    = sharpe_delta    <= ARM_A_SHARPE_TOL
        admission_ok = admission_delta <= ARM_A_ADMISSION_TOL

        if sharpe_ok and admission_ok:
            log.info(
                "Arm A lineage [%s]: Sharpe=%.3f (ref=%.3f Δ=%.3f ✓) "
                "admission=%.3f (ref=%.3f Δ=%.3f ✓) MaxDD=%.2f%%",
                scenario, sharpe, ref["sharpe"], sharpe_delta,
                admission, ref["admission_rate"], admission_delta,
                max_dd * 100,
            )
        else:
            log.error(
                "Arm A lineage FAIL [%s]: Sharpe=%.3f (ref=%.3f Δ=%.3f tol=%.3f %s) "
                "admission=%.3f (ref=%.3f Δ=%.3f tol=%.3f %s)",
                scenario,
                sharpe, ref["sharpe"], sharpe_delta, ARM_A_SHARPE_TOL,
                "✓" if sharpe_ok else "✗",
                admission, ref["admission_rate"], admission_delta,
                ARM_A_ADMISSION_TOL,
                "✓" if admission_ok else "✗",
            )
            all_ok = False

    return all_ok


# ---------------------------------------------------------------------------
# 4. Gate evaluation
# ---------------------------------------------------------------------------

def evaluate_gates(
    arm_result: ArmResult,
    arm_a_low_uplift: ArmResult,
) -> list[GateResult]:
    """Evaluate applicable gates for one arm against Arm A Low-Uplift reference.

    Gates are evaluated on Low-Uplift scenario only (D2).
    P5-G3 applies to Arm C only.

    Args:
        arm_result:         ArmResult for the arm being evaluated (low_uplift).
        arm_a_low_uplift:   ArmResult for Arm A low_uplift (the reference).

    Returns:
        List of GateResult objects for all applicable gates.
    """
    arm_id   = arm_result.arm
    scenario = arm_result.scenario

    if scenario != "low_uplift":
        raise ValueError(
            f"evaluate_gates: gates apply to low_uplift only, got '{scenario}'."
        )

    gates: list[GateResult] = []

    sharpe_arm  = arm_result.risk_metrics.get("sharpe", np.nan)
    sharpe_ref  = arm_a_low_uplift.risk_metrics.get("sharpe", np.nan)
    max_dd_arm  = arm_result.risk_metrics.get("max_drawdown", np.nan)
    max_dd_ref  = arm_a_low_uplift.risk_metrics.get("max_drawdown", np.nan)
    adm_arm     = arm_result.admission_rate
    adm_ref     = arm_a_low_uplift.admission_rate

    # P5-G1: Sharpe deterioration
    delta_sharpe = sharpe_arm - sharpe_ref
    gates.append(GateResult(
        gate_id="P5-G1",
        arm=arm_id,
        scenario=scenario,
        arm_value=sharpe_arm,
        reference_value=sharpe_ref,
        delta=delta_sharpe,
        threshold=GATE_P5_G1_MIN_DELTA_SHARPE,
        passed=delta_sharpe >= GATE_P5_G1_MIN_DELTA_SHARPE,
        note=f"Sharpe(arm)={sharpe_arm:.3f} Sharpe(A)={sharpe_ref:.3f} "
             f"Δ={delta_sharpe:+.3f} threshold≥{GATE_P5_G1_MIN_DELTA_SHARPE:+.2f}",
    ))

    # P5-G2: MaxDD worsening
    delta_dd = max_dd_arm - max_dd_ref
    gates.append(GateResult(
        gate_id="P5-G2",
        arm=arm_id,
        scenario=scenario,
        arm_value=max_dd_arm,
        reference_value=max_dd_ref,
        delta=delta_dd,
        threshold=GATE_P5_G2_MAX_DELTA_MAXDD,
        passed=delta_dd <= GATE_P5_G2_MAX_DELTA_MAXDD,
        note=f"MaxDD(arm)={max_dd_arm*100:.2f}% MaxDD(A)={max_dd_ref*100:.2f}% "
             f"Δ={delta_dd*100:+.2f}pp threshold≤{GATE_P5_G2_MAX_DELTA_MAXDD*100:+.1f}pp",
    ))

    # P5-G3: Admission improvement (Arm C only)
    if arm_id == "arm_c":
        delta_adm = adm_arm - adm_ref
        gates.append(GateResult(
            gate_id="P5-G3",
            arm=arm_id,
            scenario=scenario,
            arm_value=adm_arm,
            reference_value=adm_ref,
            delta=delta_adm,
            threshold=GATE_P5_G3_MIN_DELTA_ADMISSION,
            passed=delta_adm >= GATE_P5_G3_MIN_DELTA_ADMISSION,
            note=f"admission(arm)={adm_arm:.3f} admission(A)={adm_ref:.3f} "
                 f"Δ={delta_adm*100:+.2f}pp threshold≥{GATE_P5_G3_MIN_DELTA_ADMISSION*100:+.1f}pp",
        ))

    for g in gates:
        status = "PASS ✓" if g.passed else "FAIL ✗"
        log.info("Gate %s [%s]: %s — %s", g.gate_id, arm_id.upper(), status, g.note)

    return gates


# ---------------------------------------------------------------------------
# 5. Phase 5 verdict
# ---------------------------------------------------------------------------

def compute_verdict(
    arm_b_lu: ArmResult,
    arm_c_lu: ArmResult,
) -> Phase5Verdict:
    """Derive Layer 1 + Layer 2 verdict per SPEC §7.3.

    Layer 1:
        CONFIGURATION_SELECTED   — at least one arm passes all applicable gates
        CONFIGURATION_NOT_SELECTED — no arm passes
        INCOMPLETE                — not triggered here (arms were run)

    Layer 2:
        SELECTED: [arm(s)]         — named passing arm(s)
        FURTHER_RESEARCH_REQUIRED  — neither arm passes

    Note: RETAIN_20TD_RS60D_STUDY (SPEC §7.3) is not emitted by this runner.
    Arm B passing gates → CONFIGURATION_SELECTED: ARM_B, not NOT_SELECTED + RETAIN.

    Pre-registered hypotheses for Arm C (reported regardless of gate outcome):
        H1: Sharpe(C, LU) > 1.613     [Arm A Low-Uplift Sharpe]
        H2: Sharpe(C, LU) >= 2.128    [Arm B Low-Uplift Sharpe from Phase 4]
    """
    gate_summary: dict = {}
    notes: list[str] = []

    for arm_result in (arm_b_lu, arm_c_lu):
        arm_id = arm_result.arm
        gates  = arm_result.gates
        gate_summary[arm_id] = {
            g.gate_id: {"passed": g.passed, "delta": round(g.delta, 4), "note": g.note}
            for g in gates
        }
        if all(g.passed for g in gates):
            log.info("Arm %s: ALL gates PASSED", arm_id.upper())
        else:
            failed = [g.gate_id for g in gates if not g.passed]
            log.info("Arm %s: gates FAILED: %s", arm_id.upper(), failed)

    # Pre-registered hypotheses for Arm C
    arm_a_sharpe_lu = 1.613   # Phase 3 / Phase 4 confirmed reference
    arm_b_sharpe_lu = 2.128   # Phase 4 Track B reference
    sharpe_c = arm_c_lu.risk_metrics.get("sharpe", np.nan)
    h1 = not np.isnan(sharpe_c) and sharpe_c > arm_a_sharpe_lu
    h2 = not np.isnan(sharpe_c) and sharpe_c >= arm_b_sharpe_lu
    notes.append(
        f"Arm C pre-registered: H1 (Sharpe(C,LU)>{arm_a_sharpe_lu}) = "
        f"{'SUPPORTED' if h1 else 'NOT SUPPORTED'} "
        f"[observed={sharpe_c:.3f}]"
    )
    notes.append(
        f"Arm C pre-registered: H2 (Sharpe(C,LU)>={arm_b_sharpe_lu}) = "
        f"{'SUPPORTED' if h2 else 'NOT SUPPORTED'} "
        f"[observed={sharpe_c:.3f}]"
    )
    for note in notes:
        log.info("Hypothesis: %s", note)

    # Determine layer verdicts (P5-FIX-001: rewritten to eliminate dead branch).
    # The original elif block was unreachable: if arm_b passes all gates it is
    # already in `selected`, so the first branch fires.  Both booleans are
    # evaluated explicitly to keep the verdict tree transparent and auditable.
    arm_b_passed = all(g.passed for g in arm_b_lu.gates)
    arm_c_passed = all(g.passed for g in arm_c_lu.gates)

    if arm_b_passed or arm_c_passed:
        layer1 = "CONFIGURATION_SELECTED"
        layer2 = "SELECTED: " + ", ".join(
            a.upper() for a, passed in [("arm_b", arm_b_passed), ("arm_c", arm_c_passed)]
            if passed
        )
    else:
        # Neither arm passes all gates.  FURTHER_RESEARCH_REQUIRED is the only
        # valid layer2 in this branch: arm_b_passed=False and arm_c_passed=False
        # by construction (if either were True, the first branch fires).
        # RETAIN_20TD_RS60D_STUDY is not reachable — see Phase5Verdict.layer2 comment.
        layer1 = "CONFIGURATION_NOT_SELECTED"
        layer2 = "FURTHER_RESEARCH_REQUIRED"

    log.info("=== Phase 5 Verdict: %s / %s ===", layer1, layer2)

    return Phase5Verdict(
        layer1=layer1,
        layer2=layer2,
        selected_arms=[a for a, p in [("arm_b", arm_b_passed), ("arm_c", arm_c_passed)] if p],
        gate_summary=gate_summary,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# 6. Bootstrap (reused pattern from Phase 4)
# ---------------------------------------------------------------------------

def _bootstrap_delta_a3_two_sample(
    ledger_t: pd.DataFrame,
    ledger_b: pd.DataFrame,
    h: int,
) -> dict:
    """Two-sample stationary block bootstrap Δ_A3 at horizon h.

    Supplementary only — not a Phase 5 gate criterion (D2).
    Block length: L = max(5, h) per SPEC §6 (frozen from Phase 4).
    B = 5,000 replications.
    """
    from arch.bootstrap import StationaryBootstrap

    fwd_col    = "fwd_return_h"
    treat_vals = ledger_t[ledger_t["valid_path"]][fwd_col].dropna().values
    base_vals  = ledger_b[ledger_b["valid_path"]][fwd_col].dropna().values

    if len(treat_vals) < 20 or len(base_vals) < 20:
        log.warning(
            "Insufficient obs for bootstrap h=%d (treat=%d base=%d) — NaN CI",
            h, len(treat_vals), len(base_vals),
        )
        return {
            "h": h, "delta_obs": np.nan, "ci_lo": np.nan, "ci_hi": np.nan,
            "n_treat": len(treat_vals), "n_base": len(base_vals),
            "B": BOOTSTRAP_B, "block_length": bootstrap_block_length(h),
            "method": "two_sample_stationary_block",
            "note": "SUPPLEMENTARY ONLY — not a Phase 5 gate criterion",
        }

    L         = bootstrap_block_length(h)
    delta_obs = float(np.mean(treat_vals) - np.mean(base_vals))

    bs_treat = StationaryBootstrap(L, treat_vals)
    bs_base  = StationaryBootstrap(L, base_vals)

    deltas = [
        float(np.mean(t_data[0]) - np.mean(b_data[0]))
        for (t_data, _), (b_data, _) in zip(
            bs_treat.bootstrap(BOOTSTRAP_B),
            bs_base.bootstrap(BOOTSTRAP_B),
        )
    ]

    ci_lo = float(np.percentile(deltas, 2.5))
    ci_hi = float(np.percentile(deltas, 97.5))

    log.info(
        "Bootstrap Δ_A3[%dtd, supplementary]: obs=+%.4f%% CI=[%.4f%%, %.4f%%] L=%d",
        h, delta_obs * 100, ci_lo * 100, ci_hi * 100, L,
    )
    return {
        "h": h, "delta_obs": delta_obs, "ci_lo": ci_lo, "ci_hi": ci_hi,
        "n_treat": len(treat_vals), "n_base": len(base_vals),
        "B": BOOTSTRAP_B, "block_length": L,
        "method": "two_sample_stationary_block",
        "note": "SUPPLEMENTARY ONLY — not a Phase 5 gate criterion",
    }


# ---------------------------------------------------------------------------
# 7. Artifact writer
# ---------------------------------------------------------------------------

def write_artifacts(
    panel: pd.DataFrame,
    all_results: list[ArmResult],
    verdict: Phase5Verdict,
    gap_report: DataGapReport,
    fp_result: FingerprintResult,
    arm_a_lineage_ok: bool,
) -> None:
    """Write Phase 5 artifacts to data/_storage/r8_phase5/v0.1.0/."""
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    # Forward return matrix (fwd_10td + fwd_20td)
    fwd_cols = (
        ["stock_id", "date", "universe", "regime", "near_limit_up"]
        + [c for c in ["fwd_10td", "fwd_20td"] if c in panel.columns]
    )
    panel[fwd_cols].to_parquet(
        ARTIFACT_DIR / "forward_return_matrix.parquet", index=False
    )
    log.info("Wrote forward_return_matrix.parquet (%d rows)", len(panel))

    # Arm results (risk metrics + gate evaluation)
    # gate_applicable: True only for low_uplift rows of Arms B and C.
    # Gates are not evaluated on full_sample or on Arm A (lineage check only).
    # NaN in gate_* columns means "not applicable", not "missing" or "fail".
    arm_rows = []
    for r in all_results:
        gates_apply = (r.scenario == "low_uplift") and (r.arm in ("arm_b", "arm_c"))
        row = {
            "arm":              r.arm,
            "label":            r.label,
            "scenario":         r.scenario,
            "h":                r.h,
            "rank_col":         r.rank_col,
            "n_candidates":     r.n_candidates,
            "n_scheduled":      r.n_scheduled,
            "admission_rate":   r.admission_rate,
            "passed_all_gates": r.passed_all_gates if gates_apply else None,
            "gate_applicable":  gates_apply,
        }
        for k, v in r.risk_metrics.items():
            row[k] = v
        # Gate columns: present only when gates were evaluated; None = not applicable
        for gate_id in ("P5-G1", "P5-G2", "P5-G3"):
            matching = [g for g in r.gates if g.gate_id == gate_id]
            if matching:
                row[f"gate_{gate_id}_passed"] = matching[0].passed
                row[f"gate_{gate_id}_delta"]  = matching[0].delta
            else:
                row[f"gate_{gate_id}_passed"] = None   # not applicable
                row[f"gate_{gate_id}_delta"]  = None
        arm_rows.append(row)

    pd.DataFrame(arm_rows).to_parquet(
        ARTIFACT_DIR / "p5_arm_results.parquet", index=False
    )
    log.info("Wrote p5_arm_results.parquet (%d rows)", len(arm_rows))

    # Bootstrap results (supplementary)
    bootstrap_rows = []
    for r in all_results:
        bd = dict(r.bootstrap_delta)
        bd["arm"]      = r.arm
        bd["scenario"] = r.scenario
        bootstrap_rows.append(bd)

    pd.DataFrame(bootstrap_rows).to_parquet(
        ARTIFACT_DIR / "p5_bootstrap.parquet", index=False
    )
    log.info("Wrote p5_bootstrap.parquet (%d rows)", len(bootstrap_rows))

    # Manifest
    import subprocess
    try:
        commit_hash = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(_REPO_ROOT), text=True,
        ).strip()
    except Exception:
        commit_hash = "unknown"

    manifest = {
        "script_version":     SCRIPT_VERSION,
        "spec_version":       SPEC_VERSION,
        "generated_at":       pd.Timestamp.now(tz="Asia/Taipei").isoformat(),
        "commit_hash":        commit_hash,
        "db_path":            str(DB_PATH),
        "artifact_dir":       str(ARTIFACT_DIR),
        "panel_source":       "load_panel() from run_r8_phase1_a3 — identical CTE",
        "fwd_return_source":  "compute_forward_returns(horizons=[10, 20])",
        "arms": {
            arm_id: {
                "h":       cfg["h"],
                "rank_col": cfg["rank_col"],
                "label":   cfg["label"],
            }
            for arm_id, cfg in ARM_CONFIGS.items()
        },
        "gate_criteria": {
            "P5-G1": {
                "criterion":  "Sharpe(arm,LU) - Sharpe(A,LU) >= -0.10",
                "threshold":  GATE_P5_G1_MIN_DELTA_SHARPE,
                "type":       "governance_heuristic",
                "note":       "Not a statistical significance boundary",
            },
            "P5-G2": {
                "criterion":  "MaxDD(arm,LU) - MaxDD(A,LU) <= +3pp",
                "threshold":  GATE_P5_G2_MAX_DELTA_MAXDD,
                "type":       "governance_heuristic",
                "note":       "Not a statistical significance boundary",
            },
            "P5-G3": {
                "criterion":  "admission_rate(C,LU) - admission_rate(A,LU) >= +10pp",
                "threshold":  GATE_P5_G3_MIN_DELTA_ADMISSION,
                "applies_to": "arm_c only",
                "type":       "governance_heuristic",
                "note":       "Not a statistical significance boundary",
            },
        },
        "verdict": {
            "layer1":        verdict.layer1,
            "layer2":        verdict.layer2,
            "selected_arms": verdict.selected_arms,
            "notes":         verdict.notes,
            "gate_summary":  verdict.gate_summary,
        },
        "arm_a_lineage_check": {
            "passed":    arm_a_lineage_ok,
            "reference": ARM_A_REFERENCE,
            "tolerances": {
                "sharpe":         ARM_A_SHARPE_TOL,
                "admission_rate": ARM_A_ADMISSION_TOL,
            },
        },
        "bootstrap_note": (
            "Bootstrap Δ_A3 reported as supplementary evidence only. "
            "Not used as Phase 5 gate criterion (D2). "
            "Low-Uplift CI crosses zero at all horizons in Phase 4 — "
            "CI > 0 gate would reject Phase 3 baseline (logical contradiction)."
        ),
        "price_snapshot_refresh": {
            "status": "DETECTED_AND_ACCEPTED",
            "reason": (
                "daily_price_adj retroactive adjustment after Phase 3/4 lock. "
                "Likely TWSE corporate action / ex-dividend restatement in "
                "historical adj_close / adj_open series."
            ),
            "first_nav_divergence_date": "2023-07-14",
            "diverging_nav_dates_count": 694,
            "locked_phase3_full_sample": {
                "nav_end": 6.477569,
                "sharpe":  2.377654,
                "source":  "data/_storage/r8_phase3/v0.1.0/p3a_nav_series.parquet",
            },
            "phase5_recomputed_full_sample": {
                "nav_end": 6.974622,
                "sharpe":  2.498050,
                "source":  "current DuckDB daily_price_adj snapshot (2026-06-08)",
            },
            "low_uplift_sharpe_delta_vs_phase3": -0.044,
            "governance_note": (
                "Phase 3/4 artifacts remain locked and are not overwritten. "
                "Phase 5 uses the current adj-price snapshot for all arms "
                "(A, B, C) to preserve cross-arm comparability on a consistent "
                "price basis. ARM_A_REFERENCE values are the Phase 5 "
                "price-snapshot baseline, not a revision of Phase 3/4 findings. "
                "See research/r8_phase5_price_snapshot_refresh_note.md."
            ),
        },
        "governance": {
            "fingerprint_check":  "P3-FP-001: net_s1 = +1.64% ± 1bp (not Sharpe)",
            "bootstrap_formula":  "two_sample_stationary_block, L=max(5,h), B=5000",
            "exit_date_formula":  "exit_date = trading_calendar[pos + h]",
            "nav_source":         "D1A: daily simple PnL from daily_price_adj.adj_close",
            "capital_scheduler":  "Interpretation B: shared pool, exposure <= 100%",
            "ranking_note":       "RS-60d = beta_adj_rs_60d DESC within each signal_date",
        },
        "data_gaps": {
            "missing_tables": gap_report.missing_tables,
            "empty_tables":   gap_report.empty_tables,
            "coverage_gaps":  gap_report.coverage_gaps,
        },
        "p3_fp_001": {
            "gross_mean":           fp_result.gross_mean,
            "net_s1":               fp_result.net_s1,
            "mean_deployed_weight": fp_result.mean_deployed_weight,
            "n_signal_dates":       fp_result.n_signal_dates,
            "passed":               fp_result.passed,
        },
        "artifacts": [
            "forward_return_matrix.parquet",
            "p5_arm_results.parquet",
            "p5_bootstrap.parquet",
            "manifest.json",
        ],
    }

    with open(ARTIFACT_DIR / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2, default=str)
    log.info("Wrote manifest.json")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Run Phase 5 Configuration Selection (Arms A, B, C)."""
    log.info("=== Phase 5 runner v%s (SPEC v%s) ===", SCRIPT_VERSION, SPEC_VERSION)
    log.info("Arms: A (20td+FIFO), B (20td+RS-60d), C (10td+RS-60d)")
    log.info("Gates: P5-G1 (Sharpe ≥ −0.10), P5-G2 (MaxDD ≤ +3pp), P5-G3 (admission ≥ +10pp, Arm C)")
    log.info("Bootstrap Δ_A3: supplementary only — NOT a gate criterion")

    if not DB_PATH.exists():
        log.error("DuckDB not found: %s", DB_PATH)
        sys.exit(1)

    with duckdb.connect(str(DB_PATH), read_only=True) as con:

        gap_report = validate_schema_and_document_gaps(con)
        if "daily_price_adj" in gap_report.missing_tables:
            log.error("Cannot proceed: daily_price_adj missing.")
            sys.exit(1)

        # Load panel and compute Phase 5 forward returns (horizons 10 + 20)
        log.info("Loading panel and computing forward returns (horizons=10,20)...")
        panel  = load_panel(con)
        prices = load_price_series(con)
        panel  = build_phase5_forward_returns(panel, prices)

        # P3-FP-001: lineage fingerprint (20td full-sample net_s1)
        fp_result = verify_p3_fingerprint(panel, prices, con=con)

        # --- Arm A ---
        log.info("=== Arm A: 20td + FIFO (lineage verification) ===")
        arm_a_results = run_arm("arm_a", panel, prices, con)

        arm_a_lineage_ok = check_arm_a_lineage(arm_a_results)
        if not arm_a_lineage_ok:
            log.error(
                "Arm A lineage check FAILED. "
                "Phase 5 cannot proceed with unreproducible baseline. "
                "Inspect panel / price data for changes since Phase 3/4."
            )
            sys.exit(1)

        # Arm A Low-Uplift result is the gate reference
        arm_a_lu = next(r for r in arm_a_results if r.scenario == "low_uplift")

        # --- Arm B ---
        log.info("=== Arm B: 20td + RS-60d (isolated ranking effect) ===")
        arm_b_results = run_arm("arm_b", panel, prices, con)
        arm_b_lu = next(r for r in arm_b_results if r.scenario == "low_uplift")
        arm_b_lu.gates = evaluate_gates(arm_b_lu, arm_a_lu)
        arm_b_lu.passed_all_gates = all(g.passed for g in arm_b_lu.gates)

        # --- Arm C ---
        log.info("=== Arm C: 10td + RS-60d (combined candidate) ===")
        arm_c_results = run_arm("arm_c", panel, prices, con)
        arm_c_lu = next(r for r in arm_c_results if r.scenario == "low_uplift")
        arm_c_lu.gates = evaluate_gates(arm_c_lu, arm_a_lu)
        arm_c_lu.passed_all_gates = all(g.passed for g in arm_c_lu.gates)

        # --- Phase 5 Verdict ---
        verdict = compute_verdict(arm_b_lu, arm_c_lu)

        # --- Write artifacts ---
        all_results = arm_a_results + arm_b_results + arm_c_results
        write_artifacts(
            panel=panel,
            all_results=all_results,
            verdict=verdict,
            gap_report=gap_report,
            fp_result=fp_result,
            arm_a_lineage_ok=arm_a_lineage_ok,
        )

    log.info(
        "=== Phase 5 complete. Verdict: %s / %s ===",
        verdict.layer1, verdict.layer2,
    )
    log.info("Artifacts: %s", ARTIFACT_DIR)
    log.info("Next: author research/r8_phase5_configuration_report.md")


if __name__ == "__main__":
    main()
