# scripts/phase6_orchestration.py
"""Phase 6 Step 3F — Gate orchestration and full evaluation pipeline.

Wires evaluate_candidate → bootstrap_delta_sharpe → evaluate_gates
→ derive_verdict into a complete CandidateVerdict per candidate.

Entry point: run_phase6_evaluation(con, bootstrap_seed) which returns
a list of CandidateVerdict objects and a provenance dict.

Governance constraints:
    - ARM_B is evaluated first; its metrics form the gate reference.
    - E1–E4 evaluated in order; each independently.
    - Bootstrap is supplementary per SPEC §5.4 (not a gate criterion).
    - No Phase 5 benchmark modification.
    - No admission rule change.
    - No capacity redesign.

Known limitations (tracked):
    P6-3F-001: scenario_start/scenario_end recorded in provenance but do
        not yet filter the evaluation window (evaluate_candidate evaluates
        full low_uplift snapshot). Must be resolved before Step 4
        multi-scenario runs.
    P6-3F-003: n_obs passed to evaluate_gates is len(arm_b_nav)-1, not
        the bootstrap-aligned count. These may differ if NAV date ranges
        do not fully overlap.

arm_b_lu key schema:
    {"sharpe": float, "max_dd": float, "admission_rate": float}
    Note: "max_dd" not "max_drawdown" — matches evaluate_gates ABI
    confirmed at line 394 of run_phase6_evaluation.py.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    import duckdb

log = logging.getLogger(__name__)


# =====================================================================
# arm_b_lu extraction
# =====================================================================


def _extract_arm_b_lu(metrics: "CandidateMetrics") -> dict[str, float]:
    """Extract ARM_B Low-Uplift reference dict for gate evaluation.

    Key schema matches evaluate_gates(arm_b_lu) ABI:
        "sharpe"         — annualised Sharpe
        "max_dd"         — maximum drawdown (NOT "max_drawdown")
        "admission_rate" — fraction of candidates admitted

    The key "max_dd" (not "max_drawdown") is confirmed from
    run_phase6_evaluation.py line 394 ARM_B_REFERENCE schema and
    evaluate_gates body at line 1135.
    """
    return {
        "sharpe":          float(metrics.sharpe),
        "max_dd":          float(metrics.max_dd),
        "admission_rate":  float(metrics.admission_rate),
    }


# =====================================================================
# Full evaluation pipeline
# =====================================================================


def run_phase6_evaluation(
    con: "duckdb.DuckDBPyConnection",
    bootstrap_seed: int,
    scenario_start: date,
    scenario_end: date,
    lineage_anchor_label: str,
    n_bootstrap: int = 5000,
    block_length: int | None = None,
) -> tuple[list["CandidateVerdict"], dict]:
    """Run full Phase 6 gate orchestration for all candidates.

    Step 3F wiring: evaluate ARM_B then E1–E4, compute gates and
    verdicts, return structured results.

    Args:
        con: DuckDB connection (caller-owned).
        bootstrap_seed: Deterministic seed for bootstrap (--bootstrap-seed).
        scenario_start: Evaluation window start (passed to evaluate_candidate).
        scenario_end: Evaluation window end.
        lineage_anchor_label: Label for provenance tagging.
        n_bootstrap: Bootstrap replications (SPEC default 5000).
        block_length: Bootstrap block length L = max(5, h). SPEC: L=max(5,20)=20.

    Returns:
        (verdicts, provenance)
        verdicts: list[CandidateVerdict] for ARM_B + E1–E4
        provenance: dict with per-candidate metrics, bootstrap results,
                    gate results, verdicts (Python-native types).
    """
    from scripts.run_phase6_evaluation import (
        Candidate,
        CandidateVerdict,
        derive_verdict,
        evaluate_gates,
    )
    from scripts.phase6_evaluate_candidate import evaluate_candidate
    from scripts.phase6_bootstrap import bootstrap_delta_sharpe

    # P6-3F-002: block_length enforcement per SPEC §5.4.
    # L = max(5, h) = max(5, 20) = 20. Caller passes None for SPEC default
    # or 20 explicitly. Any other value raises.
    from scripts.run_phase6_evaluation import HOLD_CEILING_DAYS, BOOTSTRAP_L_MIN
    _spec_L = max(BOOTSTRAP_L_MIN, HOLD_CEILING_DAYS)  # = 20
    if block_length is None:
        block_length = _spec_L
    elif block_length != _spec_L:
        raise ValueError(
            f"run_phase6_evaluation: block_length={block_length} violates "
            f"SPEC §5.4 (L = max({BOOTSTRAP_L_MIN}, {HOLD_CEILING_DAYS}) = {_spec_L}). "
            "Pass None to use SPEC default."
        )

    verdicts: list[CandidateVerdict] = []
    provenance: dict = {
        "bootstrap_seed": bootstrap_seed,
        "block_length":   block_length,
        "n_bootstrap":    n_bootstrap,
        "scenario_start": str(scenario_start),
        "scenario_end":   str(scenario_end),
        "anchor":         lineage_anchor_label,
        "candidates":     {},
    }

    # ── Step 1: ARM_B canonical path ─────────────────────────────────
    log.info("Phase 6: evaluating ARM_B ...")
    arm_b_metrics, arm_b_nav = evaluate_candidate(
        con=con,
        candidate=Candidate.ARM_B,
        scenario_start=scenario_start,
        scenario_end=scenario_end,
        lineage_anchor_label=lineage_anchor_label,
    )
    arm_b_lu = _extract_arm_b_lu(arm_b_metrics)
    n_obs = int(len(arm_b_nav) - 1)  # exclude construction row

    log.info(
        "ARM_B: sharpe=%.4f max_dd=%.4f admission=%.4f n_obs=%d",
        arm_b_lu["sharpe"], arm_b_lu["max_dd"],
        arm_b_lu["admission_rate"], n_obs,
    )

    provenance["candidates"]["arm_b"] = {
        "sharpe":          arm_b_lu["sharpe"],
        "max_dd":          arm_b_lu["max_dd"],
        "admission_rate":  arm_b_lu["admission_rate"],
        "mean_holding_days": float(arm_b_metrics.mean_holding_days),
        "scheduled_count": int(arm_b_metrics.scheduled_count),
        "candidates_count": int(arm_b_metrics.candidates_count),
    }

    # ARM_B gets a trivial verdict (it is the reference, not evaluated
    # against gates). Include for completeness of output.
    arm_b_verdict = CandidateVerdict(
        candidate=Candidate.ARM_B,
        label=None,      # ARM_B is reference; no verdict label
        gates={},
        notes=["ARM_B is the reference candidate. No gate evaluation."],
    )
    verdicts.append(arm_b_verdict)

    # ── Step 2: E1–E4 adaptive paths ─────────────────────────────────
    for candidate in [Candidate.E1, Candidate.E2, Candidate.E3, Candidate.E4]:
        log.info("Phase 6: evaluating %s ...", candidate.value)

        cand_metrics, cand_nav = evaluate_candidate(
            con=con,
            candidate=candidate,
            scenario_start=scenario_start,
            scenario_end=scenario_end,
            lineage_anchor_label=lineage_anchor_label,
        )

        # Bootstrap (supplementary, per SPEC §5.4)
        boot = bootstrap_delta_sharpe(
            challenger_nav=cand_nav,
            arm_b_nav=arm_b_nav,
            block_length=block_length,
            n_bootstrap=n_bootstrap,
            seed=bootstrap_seed,
        )

        # Gate evaluation
        gates = evaluate_gates(
            candidate=candidate,
            metrics=cand_metrics,
            arm_b_lu=arm_b_lu,
            lu_n_obs=n_obs,
        )

        # Verdict
        verdict = derive_verdict(candidate=candidate, gates=gates)
        verdicts.append(verdict)

        gate_summary = {
            gid: {"pass": g.pass_, "delta": g.delta_vs_arm_b, "margin": g.margin}
            for gid, g in gates.items()
        }

        log.info(
            "%s: sharpe=%.4f delta_sharpe=%.4f "
            "G1=%s G2=%s G3=%s verdict=%s "
            "bootstrap_95CI=[%.4f,%.4f]",
            candidate.value,
            cand_metrics.sharpe,
            boot["observed_delta_sharpe"],
            "PASS" if gates["P6-G1"].pass_ else "FAIL",
            "PASS" if gates["P6-G2"].pass_ else "FAIL",
            "PASS" if gates["P6-G3"].pass_ else "FAIL",
            verdict.label.value if verdict.label else "N/A",
            boot["ci_025"], boot["ci_975"],
        )

        provenance["candidates"][candidate.value] = {
            "sharpe":               float(cand_metrics.sharpe),
            "max_dd":               float(cand_metrics.max_dd),
            "admission_rate":       float(cand_metrics.admission_rate),
            "mean_holding_days":    float(cand_metrics.mean_holding_days),
            "scheduled_count":      int(cand_metrics.scheduled_count),
            "candidates_count":     int(cand_metrics.candidates_count),
            "delta_sharpe_obs":     float(boot["observed_delta_sharpe"]),
            "bootstrap_ci_025":     float(boot["ci_025"]),
            "bootstrap_ci_500":     float(boot["ci_500"]),
            "bootstrap_ci_975":     float(boot["ci_975"]),
            "bootstrap_prob_le_0":  float(boot["bootstrap_prob_delta_le_zero"]),
            "bootstrap_n_obs":      int(boot["n_obs"]),
            "bootstrap_n_valid":    int(boot["n_bootstrap_valid"]),
            "gates":                gate_summary,
            "verdict":              verdict.label.value if verdict.label else None,
            "notes":                list(verdict.notes),
        }

    return verdicts, provenance
