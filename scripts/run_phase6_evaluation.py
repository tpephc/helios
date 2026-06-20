#!/usr/bin/env python3
# scripts/run_phase6_evaluation.py
"""Phase 6 Exit Policy Evaluation runner — v0.1.3.

Multi-arm champion-vs-challengers evaluation of four pre-registered
exit policy candidates (E1 ATR Trailing, E2 MA20 Failure, E3 RS
Deterioration, E4 Donchian) against the frozen ARM_B baseline
(20td + RS-60d ranking), per single-variable intervention principle
(P6-INV-001): only the exit contract varies; entry, ranking, sizing,
admission, and capital rules are frozen at ARM_B specification.

Owned by:
    research/r8_phase6_spec.md v0.1.1 (LOCKED)

Parent verdicts:
    research/r8_phase5_configuration_report.md v1.0.2 (LOCKED)
    research/helios_research_roadmap.md v0.1.1 (LOCKED)

Sibling:
    research/r8_phase5_followup_001_spec.md v1.0.0 (parallel, non-blocking)

Frozen parameter anchor:
    Helios HEAD edd42b14d1d5f2c858730ee140cbd7b5683b2d0a
    (E1 production source: strategies/exit/trailing_stop.py v0.2.0)

Pre-execution invariants enforced (per SPEC §10.3):
    P6-INV-001: single-variable intervention (exit-only variation)
    P6-INV-002: no in-sample parameter tuning within Phase 6

================================================================
A2 — REMINDER: E3 robustness disclosure obligation
================================================================
E3 (RS Deterioration Exit) uses a structural-symmetry threshold
(50th percentile, mirroring ARM_B's top-quintile entry) rather than
a market-mechanism literature default. The Phase 6 evaluation report
MUST include a robustness flag in §4 (Candidate Results) when E3 is:

    (a) the unique SELECTED candidate, OR
    (b) SELECTED with the widest margin among multi-SELECTED outcomes

In either case the report must list a Phase 6A threshold robustness
re-verification as a required follow-up before any deployment
authorisation. This reminder is also enforced at verdict-emission
time in derive_verdict() below; do not remove the runtime check
without removing this docstring reminder.
================================================================

Methodological note (Phase 6 evaluation harness vs production
exit stack):

This runner does NOT use the production TrailingStop / RegimeExit /
TimeStop class instances directly via portfolio_simulator. The Phase 5
ARM_B baseline was evaluated under the paper-price NAV reconstruction
methodology (Phase 5 v1.0.2 §3), which differs structurally from the
production live exit pipeline. To preserve apples-to-apples comparison
between ARM_B and challengers E1-E4, the Phase 6 evaluation:

  - Uses the same paper-price NAV reconstruction harness as Phase 5.
  - Applies adaptive exit decisions as pure functions on
    snapshot-consistent OHLC/feature data (see exit_e1..e4 below).
  - Excludes RegimeExit from all evaluations including E1 (per SPEC
    §3.2 interpretation A — RegimeExit is part of production but not
    part of ARM_B baseline methodology).
  - Enforces the 20td hard ceiling uniformly across baseline and all
    candidates (P6-INV-001).

Version: v0.1.3 (2026-06-20)

Changelog:
    v0.1.0 — Initial skeleton.
    v0.1.1 — Five-blocker patch (review-driven):
        1. --output-dir actually threads through emit_provenance(),
           emit_verdicts(), emit_gate_evaluation(); they now take
           output_dir explicitly. Module-level full-path constants
           replaced with filename-only constants (PROVENANCE_FILENAME
           etc.) joined with the runtime output_dir.
        2. Pre-execution checks fail-closed. verify_snapshot_id() and
           verify_arm_a_lineage_reference() raising NotImplementedError
           now causes the run (including --dry-run) to abort with new
           exit code 3 ("pre-execution check stubbed or failed"),
           preserving the pre-execution-guard semantic. Dry-run no
           longer returns 0 while critical checks are unwired.
        3. Bootstrap docstring corrected to SPEC §5.4 wording
           (L = max(5, h)). The "mean_holding_days" formulation from
           v0.1.0 was an unregistered estimator and has been removed;
           the docstring now warns callers not to substitute.
        4. Marginal-margin discipline restricted to P6-G1 (Sharpe)
           per SPEC §6.3 Lo (2002) framing. P6-G2 (MaxDD) and P6-G3
           (admission) GateResult.marginal is always False. Raw G2/G3
           margins emitted as descriptive notes in derive_verdict()
           without affecting verdict label (no invented 2pp heuristic).
        5. verify_arm_b_reference() renamed to
           verify_arm_a_lineage_reference() to match SPEC §8.1
           semantics (Arm A lineage check, not ARM_B baseline check).
    v0.1.2 — Step 1 wiring (rename-only, no behavioural change):
        1. verify_snapshot_id() renamed to verify_snapshot_lineage().
           Helios architecture has no physical snapshot identity
           mechanism; daily_price_adj is a live mutable DuckDB table
           (per r8_phase5_price_snapshot_refresh_note.md 2023-07-14
           retroactive adjustment event). Lineage identity is
           established by recomputing Arm A LU + full_sample Sharpe
           and admission_rate on the current snapshot and comparing
           against persisted reference values within tolerance. The
           rename reflects this architectural reality; the name
           "snapshot_id" implied byte identity, which Helios cannot
           provide.
        2. Provenance JSON key "snapshot_id" replaced by
           "lineage_check": {"anchor_label": ...}. emit_provenance()
           parameter renamed accordingly.
        3. CLI --snapshot-id flag retained for backward compatibility;
           help text rewritten to clarify the value is a human-readable
           lineage anchor label (e.g. "2026-06-08") recorded in
           provenance, NOT a physical snapshot identifier participating
           in verification logic.
        4. Fail-closed contract preserved. verify_snapshot_lineage()
           continues to raise NotImplementedError until Step 2 wires
           verify_arm_a_lineage_reference() to the Phase 1/3/4
           harness chain. NotImplementedError message updated to point
           at Step 2 scope.
        5. No new imports. No Phase 1/3/4/5 harness ABI consumption.
           No recomputation logic. Phase 4 ABI confirmation and Arm A
           regeneration wiring are Step 2 scope per
           research/r8_phase6_wiring_precondition.md v0.1.1 §2.
        See research/r8_phase6_wiring_precondition.md v0.1.1 §3 R5 and
        Cross-cutting Issue 1 (snapshot identity = lineage equivalence,
        not byte identity).
    v0.1.3 — Step 2 wiring: verify_arm_a_lineage_reference implementation.
        1. Phase 1/3/4/5 harness imports added (confirmed ABI per Step 2A
           evidence collection). Specifically: load_panel,
           load_price_series, compute_forward_returns from
           scripts.run_r8_phase1_a3; compute_risk_metrics from
           scripts.run_phase3_analysis; build_signal_ledger_for_horizon,
           schedule_positions, reconstruct_nav_for_horizon, BASELINE_CAP,
           BASELINE_MAX_POS from scripts.run_phase4_analysis;
           ARM_A_REFERENCE, ARM_A_SHARPE_TOL, ARM_A_ADMISSION_TOL from
           scripts.run_phase5_analysis (single source of truth).
        2. LineageStatus dataclass introduced (frozen). Fields: verified,
           lineage_anchor_label, results (per-scenario computed +
           reference + deltas + gates), divergences (populated when not
           verified), sharpe_tol, admission_tol.
        3. verify_arm_a_lineage_reference() implemented. Recomputes
           Arm A LU + full_sample fingerprints via canonical Phase 1/3/4
           harness chain (load_panel + load_price_series +
           compute_forward_returns + build_signal_ledger_for_horizon +
           schedule_positions + reconstruct_nav_for_horizon +
           compute_risk_metrics). Compares against ARM_A_REFERENCE
           within ARM_A_SHARPE_TOL (±0.050) and ARM_A_ADMISSION_TOL
           (±0.020). Returns per-scenario results dict with computed,
           reference, deltas, gates. max_drawdown recorded but
           informational only (lineage gates only on sharpe +
           admission_rate per Phase 5 lineage practice).
        4. verify_snapshot_lineage() rewritten as orchestrator: delegates
           fingerprint computation to verify_arm_a_lineage_reference,
           builds LineageStatus, returns. No more NotImplementedError.
        5. main() opens DuckDB connection (HELIOS_DB_PATH constant),
           passes to verify_snapshot_lineage, processes LineageStatus
           (exit 3 on not verified, with structured divergence log per
           Phase 5 v1.0.2 §9.4 item 5 forward governance protocol).
        6. emit_provenance lineage_check block expanded to include
           anchor_label, verified, results, divergences, tolerances,
           reference_source, governance_ref.
        7. ABI key mapping handled: compute_risk_metrics returns
           "max_drawdown"; ARM_A_REFERENCE has "max_dd". The lineage
           check maps these explicitly; max_dd is recorded as
           informational diagnostic, not a gate criterion.
        8. main() flow restructured for SPEC §8.2 documented-
           evidence-chain guarantee:
             a. output_dir conflict check (exit 2) moved to BEFORE
                pre-execution checks. Previously the order
                "lineage → output_dir check" meant a non-empty
                output_dir + lineage divergence would exit 2 without
                persisting the lineage evidence to provenance.
             b. emit_provenance now runs BEFORE divergence/dry-run
                exits. Both lineage divergence (exit 3) and dry-run
                (exit 0) write provenance.json capturing
                LineageStatus.
           Behaviour change from v0.1.2: dry-run now writes
           provenance (previously it exited 0 with no artifact).
           Rationale: SPEC §8.2 requires "documented evidence chain"
           for lineage divergence; logs alone are insufficient.
        9. Removed v0.1.2-and-earlier module-local Arm A lineage
           constants ARM_A_LU_SHARPE_EXPECTED and
           ARM_A_LU_SHARPE_TOLERANCE. These would have constituted
           a second source of truth alongside ARM_A_REFERENCE /
           ARM_A_SHARPE_TOL imported from scripts.run_phase5_analysis
           (per precondition v0.1.1 §3 R6 persistence-first).
       10. Removed unused imports (hashlib, pandas as pd). pandas
           DataFrames are used by harness functions internally but
           Phase 6 runner does not type-annotate them or call pd.*
           directly.
        See research/r8_phase6_wiring_precondition.md v0.1.1 §3 R5 and
        §2 Step 2 completion criterion.
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable

import duckdb

# Helios harness imports (per research/r8_phase6_wiring_precondition.md
# v0.1.1 §3 R6 persistence-first hierarchy and Cross-cutting Issue 2
# harness layering: Phase 1 loader + Phase 3 foundation + Phase 4
# generalisation + Phase 5 references).
#
# ABI confirmed per Step 2A discovery (2026-06-20).
from scripts.run_r8_phase1_a3 import (  # noqa: E402
    compute_forward_returns,
    load_panel,
    load_price_series,
)
from scripts.run_phase3_analysis import (  # noqa: E402
    compute_risk_metrics,
)
from scripts.run_phase4_analysis import (  # noqa: E402
    BASELINE_CAP,
    BASELINE_MAX_POS,
    build_signal_ledger_for_horizon,
    reconstruct_nav_for_horizon,
    schedule_positions,
)
from scripts.run_phase5_analysis import (  # noqa: E402
    ARM_A_ADMISSION_TOL,
    ARM_A_REFERENCE,
    ARM_A_SHARPE_TOL,
)


# =====================================================================
# Versioning and provenance
# =====================================================================

__version__ = "0.1.3"
RUNNER_NAME = "run_phase6_evaluation"

PHASE_6_SPEC_VERSION = "v0.1.1"
PHASE_6_SPEC_PATH = "research/r8_phase6_spec.md"

HELIOS_HEAD_ANCHOR_SHA = "edd42b14d1d5f2c858730ee140cbd7b5683b2d0a"
"""SHA at which Phase 6 SPEC v0.1.1 E1 parameter freeze was applied.
Runtime SHA may differ; differences must be recorded in provenance
and reviewed against the §3.2 E1 evidence chain."""

HELIOS_DB_PATH = Path("data/_storage/helios.duckdb")
"""Canonical Helios DuckDB path. Phase 6 verification queries
daily_price_adj / daily_features / bullish_features via this
connection. Lineage convention: the database is a live mutable
table; identity is fingerprint-based (per Cross-cutting Issue 1)."""

# Module-level logger used by functions outside main(). main() uses
# the same logger after basicConfig is set up.
_log = logging.getLogger(RUNNER_NAME)


# =====================================================================
# Path constants (per SPEC §9.1)
# =====================================================================

DEFAULT_OUTPUT_DIR = Path("data/_storage/r8_phase6/v0.1.0")
"""Default output directory. CLI --output-dir may override; emit_*
functions take the resolved Path explicitly and never read this
default at write time."""

# Output filenames (joined with the runtime output_dir, not the default)
PROVENANCE_FILENAME = "provenance.json"
LOG_FILENAME = "execution_log.json"
VERDICTS_FILENAME = "verdicts.json"
GATE_EVAL_FILENAME = "gate_evaluation.json"
BOOTSTRAP_FILENAME = "bootstrap_results.json"
ARM_B_METRICS_FILENAME = "arm_b_baseline_metrics.json"

# Monitored repo directories that must be clean before run
MONITORED_DIRS = ("scripts/", "core/", "research/", "strategies/", "features/")


# =====================================================================
# Snapshot and scenarios (per SPEC §5.1, §8)
# =====================================================================

SNAPSHOT_ID = "2026-06-08"  # L1 — Phase 5 daily_price_adj snapshot

LU_START = date(2023, 10, 24)  # Low-Uplift scenario start (Phase 5 §4.3)
LU_END = date(2025, 8, 8)
FS_START = date(2021, 9, 13)   # Full Sample start
FS_END = date(2025, 8, 8)


# =====================================================================
# ARM_B baseline reference (per SPEC §2; immutable post-LOCK)
# =====================================================================

ARM_B_REFERENCE: dict[str, dict[str, float]] = {
    "low_uplift": {
        "sharpe": 2.204,
        "ann_return": 0.5022,
        "ann_vol": 0.2279,
        "max_dd": 0.1731,
        "calmar": 2.901,
        "admission_rate": 0.175,
    },
    # Full Sample reference: populated post-Phase-5; see Phase 5 v1.0.2 §4
    # for verification values. TODO(wiring): cross-check at execution time
    # against persisted Phase 5 artifacts before relying on these numbers.
}

# Note: Arm A lineage reference (LU + full_sample sharpe / max_dd /
# admission_rate) and tolerances are imported from
# scripts.run_phase5_analysis (ARM_A_REFERENCE, ARM_A_SHARPE_TOL,
# ARM_A_ADMISSION_TOL) — single source of truth per Phase 5 v1.0.2
# §9.4 forward governance protocol. Previous v0.1.2-and-earlier
# module-local constants ARM_A_LU_SHARPE_EXPECTED and
# ARM_A_LU_SHARPE_TOLERANCE removed in v0.1.3 to prevent second
# source of truth (per precondition v0.1.1 §3 R6).


# =====================================================================
# Gate thresholds (per SPEC §6.1; immutable post-LOCK)
# =====================================================================

P6_G1_SHARPE_DELTA_MIN = -0.15
"""Sharpe Δ vs ARM_B (LU) must be ≥ −0.15. Per §6.2, this is
approximately 1.9 × SE(Sharpe_ARM_B) under the Lo (2002) iid
approximation — a governance noise-floor reference, not a formal
significance criterion."""

P6_G2_MAXDD_DELTA_MAX = 0.03
"""MaxDD Δ vs ARM_B (LU) must be ≤ +3pp. Mirrors Phase 5 P5-G2."""

P6_G3_ADMISSION_DELTA_MIN = 0.05
"""Admission Δ vs ARM_B (LU) must be ≥ +5pp. Deliberately moderate
to accommodate adaptive-exit-driven capacity gains, which are
expected to be smaller than ARM_C's mechanical +14.83pp."""

# Marginal-margin discipline threshold (per SPEC §6.3)
MARGINAL_MARGIN_SE_MULTIPLE = 2.0
"""Gate passages with margin < 2 × SE(metric) under Lo (2002)
approximation are labelled SELECTED (marginal P6-Gn) in the verdict."""


# =====================================================================
# Universal exit-contract constraints (per SPEC §3.1)
# =====================================================================

HOLD_CEILING_DAYS = 20
"""20td hard ceiling — effective holding = min(adaptive_signal_day,
HOLD_CEILING_DAYS). Applies uniformly to ARM_B and E1-E4."""


# =====================================================================
# E1 — ATR Trailing Exit (frozen per SPEC §3.2; HEAD edd42b1)
# =====================================================================

E1_TRAILING_MULTIPLIER = 2.0
"""Production source: strategies/exit/trailing_stop.py:43
ATR_STOP_MULTIPLIER. Confirmed across 4 instantiation sites and
1 monitoring-path hard-coded coefficient (execution/stop_logic.py:82).
Pre-Phase-6 (v0.2.0 commit 2026-05-31)."""

E1_ATR_WINDOW = 14
"""features/technical.py:92 add_atr(period: int = 14).
Confirmed by trend_pullback/types.py:48,
trend_pullback/signal_generator.py:43,
execution/stop_logic.py:76 ("ATR14 at entry date. Frozen")."""

# E1_ATR_BASIS = "entry_atr_frozen_at_signal_date"  (structural, not
# a tunable). entry_atr is set at position open and held constant for
# the position's lifetime (per strategies/exit/trailing_stop.py v0.2.0
# rationale §11).


# =====================================================================
# E2 — MA20 Failure Exit (frozen per SPEC §3.3)
# =====================================================================

E2_MA_WINDOW = 20
E2_CONFIRMATION_LAG = 2
"""Two consecutive trading days below SMA(20). Trend-following
convention (Faber 2007, Wilder 1978 use 1-day; SPEC errs toward 2-day
anti-whipsaw)."""


# =====================================================================
# E3 — RS Deterioration Exit (frozen per SPEC §3.4)
# =====================================================================

E3_RS_RANK_THRESHOLD = 0.50
"""50th percentile of RS_60d (beta_adj_rs_60d) within trading
universe. Structural-symmetry choice — ARM_B admits at top quintile
(top 20%); exit when position falls below median. NOT a literature
default. See A2 reminder in module docstring."""


# =====================================================================
# E4 — Donchian Exit (frozen per SPEC §3.5)
# =====================================================================

E4_DONCHIAN_LOOKBACK = 10
"""10-day Donchian low. Faith 2003 / Curtis Faith Way of the Turtle
short-term exit. Lookback excludes day t itself; computed over
trading days [t-10, t-1]."""


# =====================================================================
# Bootstrap (per SPEC §5.4)
# =====================================================================

BOOTSTRAP_B = 5000
BOOTSTRAP_L_MIN = 5
"""Stationary block bootstrap on daily NAV returns. L = max(5, h)
where h is the candidate's effective horizon per SPEC §5.4.
Do not substitute mean holding days unless a later SPEC amendment
authorises it."""


# =====================================================================
# Enums
# =====================================================================


class Candidate(str, Enum):
    """Phase 6 evaluation candidates."""

    ARM_B = "arm_b"
    E1 = "e1_atr_trailing"
    E2 = "e2_ma20_failure"
    E3 = "e3_rs_deterioration"
    E4 = "e4_donchian"


class VerdictLabel(str, Enum):
    """Per-candidate verdict (per SPEC §6.3)."""

    SELECTED = "selected"
    SELECTED_MARGINAL = "selected_marginal"
    CHARACTERISED = "characterised"
    REJECTED = "rejected"


# =====================================================================
# Frozen dataclasses
# =====================================================================


@dataclass(frozen=True)
class PositionState:
    """Position-level state required by adaptive exit decision functions.

    Mirrors fields from strategies/exit/base.py Position but constructed
    by the Phase 6 evaluation harness, not by the live position state
    machine. Naming kept consistent with production for cross-reference.
    """

    symbol: str
    entry_date: date
    entry_price: float
    entry_atr: float                  # ATR(14) at entry, frozen
    max_close_since_entry: float
    days_held: int


@dataclass(frozen=True)
class MarketSnapshot:
    """Day-t market state passed to exit decision functions.

    Each field is computed on adj-close per the L1 snapshot.
    Feature aggregations (SMA, RS rank, n-day low) are computed
    upstream and passed in to keep exit functions pure and
    side-effect-free.
    """

    as_of: date
    close: float                      # day-t close
    close_prev: float                 # day t-1 close
    ma20: float                       # SMA(20) at day t
    ma20_prev: float                  # SMA(20) at day t-1
    rs_60d_rank: float                # rank within universe, [0, 1]
    donchian_low_excl: float          # min(close) over [t-10, t-1]


@dataclass(frozen=True)
class ExitDecision:
    """Phase 6 adaptive exit decision."""

    should_exit: bool
    reason: str
    metadata: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class CandidateMetrics:
    """Per-scenario metrics for one candidate (per SPEC §5.2)."""

    candidate: Candidate
    scenario: str                     # "low_uplift" | "full_sample"
    sharpe: float
    ann_return: float
    ann_vol: float
    max_dd: float
    calmar: float
    admission_rate: float
    scheduled_count: int
    candidates_count: int
    mean_holding_days: float
    mean_holding_pct_of_ceiling: float


@dataclass(frozen=True)
class GateResult:
    """Per-gate result for one candidate."""

    gate_id: str                      # "P6-G1" | "P6-G2" | "P6-G3"
    candidate: Candidate
    metric_value: float
    delta_vs_arm_b: float
    threshold: float
    margin: float                     # how much past threshold (signed)
    pass_: bool                       # True if gate criterion met
    marginal: bool                    # True if margin < 2 × SE


@dataclass(frozen=True)
class CandidateVerdict:
    """Final per-candidate verdict (per SPEC §6.3)."""

    candidate: Candidate
    label: VerdictLabel
    gates: dict[str, GateResult]
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class LineageStatus:
    """Result of L1 snapshot lineage verification via Arm A fingerprint.

    Helios architecture has no physical snapshot identity mechanism
    (daily_price_adj is a live mutable DuckDB table per Cross-cutting
    Issue 1 in research/r8_phase6_wiring_precondition.md v0.1.1).
    Lineage equivalence is established by recomputing Arm A LU +
    full_sample fingerprints (sharpe + admission_rate) on the current
    snapshot and comparing against persisted Phase 5 reference values
    within tolerance.

    Fields:
        verified: True iff ALL per-scenario gates pass within tolerance.
        lineage_anchor_label: Human-readable anchor label from CLI
            (e.g. "2026-06-08"). Recorded in provenance for audit
            traceability; does not participate in verification logic.
        results: Per-scenario verification details. Schema per scenario:
            {
              "computed":  {sharpe, admission_rate, max_drawdown},
              "reference": {sharpe, admission_rate, max_dd},
              "deltas":    {sharpe, admission_rate, max_dd},
              "gates":     {sharpe_within_tol, admission_within_tol},
            }
            Note the key naming asymmetry: compute_risk_metrics returns
            "max_drawdown"; ARM_A_REFERENCE has "max_dd". Both
            preserved as-emitted by their source.
        divergences: Populated when not verified. Each entry:
            {scenario, sharpe_delta, admission_delta, gates}.
        sharpe_tol: ARM_A_SHARPE_TOL (±0.050) from Phase 5.
        admission_tol: ARM_A_ADMISSION_TOL (±0.020) from Phase 5.

    Lineage gates use ONLY sharpe + admission_rate per Phase 5 lineage
    practice. max_dd is recorded as informational diagnostic but does
    not affect verified status.
    """

    verified: bool
    lineage_anchor_label: str
    results: dict[str, dict]
    divergences: list[dict]
    sharpe_tol: float
    admission_tol: float


# =====================================================================
# Exit policy decision functions (pure, deterministic)
# =====================================================================
#
# Each function takes (PositionState, MarketSnapshot) and returns an
# ExitDecision. They are pure: same inputs → same output, no I/O, no
# state mutation. This makes them trivially testable and replayable.


def exit_arm_b(pos: PositionState, mkt: MarketSnapshot) -> ExitDecision:
    """ARM_B baseline: fixed 20td hold only.

    Per Phase 5 v1.0.2 §3, ARM_B is paper-price NAV reconstruction
    with fixed 20-trading-day holding. The 20td check is the universal
    hard ceiling (P6-INV-001 §3.1) and is the SOLE exit rule for
    ARM_B in Phase 6 evaluation.
    """
    if pos.days_held >= HOLD_CEILING_DAYS:
        return ExitDecision(
            should_exit=True,
            reason=f"arm_b time_stop (days_held={pos.days_held})",
            metadata={"days_held": float(pos.days_held)},
        )
    return ExitDecision(should_exit=False, reason="")


def exit_e1_atr_trailing(
    pos: PositionState, mkt: MarketSnapshot
) -> ExitDecision:
    """E1 ATR Trailing Exit (per SPEC §3.2).

    stop_price = max_close_since_entry - 2.0 * entry_atr
    Exit if close <= stop_price.

    RegimeExit is intentionally excluded (interpretation A).
    Hard 20td ceiling enforced universally.
    """
    if pos.days_held >= HOLD_CEILING_DAYS:
        return ExitDecision(
            should_exit=True,
            reason="e1 time_stop (ceiling)",
            metadata={"days_held": float(pos.days_held)},
        )
    if pos.entry_atr <= 0:
        # Match production guard (trailing_stop.py:56)
        return ExitDecision(should_exit=False, reason="")
    stop_price = (
        pos.max_close_since_entry
        - E1_TRAILING_MULTIPLIER * pos.entry_atr
    )
    if mkt.close <= stop_price:
        return ExitDecision(
            should_exit=True,
            reason=(
                f"e1 trailing_stop (close={mkt.close:.2f} "
                f"<= stop={stop_price:.2f}, "
                f"max_close={pos.max_close_since_entry:.2f}, "
                f"entry_atr={pos.entry_atr:.2f}, "
                f"mult={E1_TRAILING_MULTIPLIER})"
            ),
            metadata={
                "exit_price": mkt.close,
                "stop_price": stop_price,
                "max_close_since_entry": pos.max_close_since_entry,
                "entry_atr": pos.entry_atr,
                "multiplier": E1_TRAILING_MULTIPLIER,
            },
        )
    return ExitDecision(should_exit=False, reason="")


def exit_e2_ma20_failure(
    pos: PositionState, mkt: MarketSnapshot
) -> ExitDecision:
    """E2 MA20 Failure Exit (per SPEC §3.3).

    Exit when close_t < MA20_t AND close_{t-1} < MA20_{t-1}
    (two consecutive trading days below SMA(20)).
    """
    if pos.days_held >= HOLD_CEILING_DAYS:
        return ExitDecision(
            should_exit=True,
            reason="e2 time_stop (ceiling)",
            metadata={"days_held": float(pos.days_held)},
        )
    # Confirmation requires position to be at least E2_CONFIRMATION_LAG
    # days old, since we need close_{t-1} below MA20_{t-1} as well.
    if pos.days_held < E2_CONFIRMATION_LAG:
        return ExitDecision(should_exit=False, reason="")
    today_below = mkt.close < mkt.ma20
    yesterday_below = mkt.close_prev < mkt.ma20_prev
    if today_below and yesterday_below:
        return ExitDecision(
            should_exit=True,
            reason=(
                f"e2 ma20_failure (close_t={mkt.close:.2f} < "
                f"ma20_t={mkt.ma20:.2f}; "
                f"close_t-1={mkt.close_prev:.2f} < "
                f"ma20_t-1={mkt.ma20_prev:.2f})"
            ),
            metadata={
                "close_t": mkt.close,
                "ma20_t": mkt.ma20,
                "close_t-1": mkt.close_prev,
                "ma20_t-1": mkt.ma20_prev,
            },
        )
    return ExitDecision(should_exit=False, reason="")


def exit_e3_rs_deterioration(
    pos: PositionState, mkt: MarketSnapshot
) -> ExitDecision:
    """E3 RS Deterioration Exit (per SPEC §3.4).

    Exit when day-t RS_60d rank of the position within the trading
    universe falls below the 50th percentile.

    Threshold is structural-symmetry; see A2 reminder in module
    docstring for robustness disclosure obligation.
    """
    if pos.days_held >= HOLD_CEILING_DAYS:
        return ExitDecision(
            should_exit=True,
            reason="e3 time_stop (ceiling)",
            metadata={"days_held": float(pos.days_held)},
        )
    if mkt.rs_60d_rank < E3_RS_RANK_THRESHOLD:
        return ExitDecision(
            should_exit=True,
            reason=(
                f"e3 rs_deterioration "
                f"(rs_60d_rank={mkt.rs_60d_rank:.3f} < "
                f"{E3_RS_RANK_THRESHOLD})"
            ),
            metadata={
                "rs_60d_rank": mkt.rs_60d_rank,
                "threshold": E3_RS_RANK_THRESHOLD,
            },
        )
    return ExitDecision(should_exit=False, reason="")


def exit_e4_donchian(
    pos: PositionState, mkt: MarketSnapshot
) -> ExitDecision:
    """E4 Donchian Exit (per SPEC §3.5).

    Exit when day-t close is at or below the lowest close of the
    prior 10 trading days, excluding day t itself.
    """
    if pos.days_held >= HOLD_CEILING_DAYS:
        return ExitDecision(
            should_exit=True,
            reason="e4 time_stop (ceiling)",
            metadata={"days_held": float(pos.days_held)},
        )
    # Donchian only meaningful once we have ≥ lookback days of history.
    # For positions younger than lookback, defer to the universe-level
    # data: if mkt.donchian_low_excl is computed from a window starting
    # before entry, it still represents a valid technical signal.
    if mkt.close <= mkt.donchian_low_excl:
        return ExitDecision(
            should_exit=True,
            reason=(
                f"e4 donchian (close={mkt.close:.2f} <= "
                f"donchian_{E4_DONCHIAN_LOOKBACK}d_low="
                f"{mkt.donchian_low_excl:.2f})"
            ),
            metadata={
                "close": mkt.close,
                "donchian_low_excl": mkt.donchian_low_excl,
                "lookback": float(E4_DONCHIAN_LOOKBACK),
            },
        )
    return ExitDecision(should_exit=False, reason="")


EXIT_FUNCTIONS: dict[Candidate, Callable[[PositionState, MarketSnapshot], ExitDecision]] = {
    Candidate.ARM_B: exit_arm_b,
    Candidate.E1: exit_e1_atr_trailing,
    Candidate.E2: exit_e2_ma20_failure,
    Candidate.E3: exit_e3_rs_deterioration,
    Candidate.E4: exit_e4_donchian,
}


# =====================================================================
# Pre-execution checks
# =====================================================================


def verify_code_sha(expected_sha: str | None) -> str:
    """Verify the runtime git HEAD SHA against expected.

    Returns the current HEAD SHA. If expected_sha is None, returns
    HEAD without verification (audit only). If expected_sha is set,
    raises RuntimeError on mismatch.

    Also enforces clean working tree on MONITORED_DIRS.
    """
    head_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()
    if expected_sha is not None and head_sha != expected_sha:
        raise RuntimeError(
            f"HEAD SHA mismatch: expected {expected_sha}, got {head_sha}. "
            "Reproducibility requires a known codebase state."
        )
    status = subprocess.check_output(
        ["git", "status", "--porcelain", "--"] + list(MONITORED_DIRS),
        text=True,
    ).strip()
    if status:
        raise RuntimeError(
            "Uncommitted changes detected in monitored directories. "
            "Phase 6 evaluation requires a clean working tree. "
            f"Uncommitted:\n{status}"
        )
    if head_sha != HELIOS_HEAD_ANCHOR_SHA:
        logging.warning(
            "Runtime HEAD (%s) differs from Phase 6 SPEC v0.1.1 anchor (%s). "
            "Verify §3.2 E1 evidence chain still holds; "
            "record divergence in provenance.",
            head_sha,
            HELIOS_HEAD_ANCHOR_SHA,
        )
    return head_sha


def verify_snapshot_lineage(
    lineage_anchor_label: str,
    con: duckdb.DuckDBPyConnection,
) -> LineageStatus:
    """Verify L1 snapshot lineage equivalence via Arm A fingerprint.

    Helios architecture has no physical snapshot identity mechanism;
    `daily_price_adj` is a live mutable DuckDB table (per the
    2023-07-14 retroactive adjustment event documented in
    r8_phase5_price_snapshot_refresh_note.md). Lineage identity is
    established by recomputing Arm A LU + full_sample Sharpe and
    admission_rate on the current snapshot and comparing against
    persisted reference values within tolerance (ARM_A_SHARPE_TOL,
    ARM_A_ADMISSION_TOL from scripts.run_phase5_analysis).

    The `lineage_anchor_label` parameter (passed in as --snapshot-id
    on CLI) is a human-readable label like '2026-06-08' and is
    recorded in provenance for audit traceability. It does NOT
    participate in verification logic — verification is purely
    fingerprint-based.

    This function is an orchestrator: it delegates the actual
    recomputation + tolerance comparison to
    verify_arm_a_lineage_reference(), then wraps the per-scenario
    results into a LineageStatus dataclass with the anchor label,
    divergence list, and tolerance bounds.

    Returns:
        LineageStatus with verified=True iff ALL per-scenario gates
        (sharpe_within_tol AND admission_within_tol for each scenario)
        pass. Otherwise verified=False with populated divergences list.

    See:
      research/r8_phase5_price_snapshot_refresh_note.md (reference origin)
      research/r8_phase6_wiring_precondition.md v0.1.1 §3 R5
        (universe membership consistency via lineage)
      research/r8_phase6_wiring_precondition.md v0.1.1 §0.4 CCI-1
        (snapshot identity = lineage equivalence, not byte identity)
    """
    results = verify_arm_a_lineage_reference(con)

    divergences: list[dict] = []
    for scenario, r in results.items():
        gates = r["gates"]
        if not (gates["sharpe_within_tol"] and gates["admission_within_tol"]):
            divergences.append({
                "scenario": scenario,
                "sharpe_delta": r["deltas"]["sharpe"],
                "admission_delta": r["deltas"]["admission_rate"],
                "max_dd_delta": r["deltas"]["max_dd"],
                "gates": dict(gates),
                "computed": dict(r["computed"]),
                "reference": dict(r["reference"]),
            })

    verified = len(divergences) == 0

    if verified:
        _log.info(
            "Snapshot lineage VERIFIED: anchor=%s; %d/%d scenarios "
            "within tolerance (sharpe±%.3f, admission±%.3f)",
            lineage_anchor_label,
            len(results), len(results),
            ARM_A_SHARPE_TOL, ARM_A_ADMISSION_TOL,
        )
    else:
        _log.error(
            "Snapshot lineage DIVERGED: anchor=%s; %d/%d scenarios "
            "outside tolerance",
            lineage_anchor_label,
            len(divergences), len(results),
        )

    return LineageStatus(
        verified=verified,
        lineage_anchor_label=lineage_anchor_label,
        results=results,
        divergences=divergences,
        sharpe_tol=ARM_A_SHARPE_TOL,
        admission_tol=ARM_A_ADMISSION_TOL,
    )


def verify_arm_a_lineage_reference(
    con: duckdb.DuckDBPyConnection,
) -> dict[str, dict]:
    """Recompute Arm A LU + full_sample fingerprints and verify lineage.

    The L1 lineage check per SPEC §8.1: recompute Arm A (treatment_1,
    FIFO, h=20) on the current snapshot via the canonical Phase 1/3/4
    harness chain and compare against ARM_A_REFERENCE from
    scripts.run_phase5_analysis (single source of truth) within
    ARM_A_SHARPE_TOL (±0.050) and ARM_A_ADMISSION_TOL (±0.020).

    This is NOT a re-verification of ARM_B baseline metrics. The
    Arm A → ARM_B baseline relationship is preserved if Arm A LU
    Sharpe + admission_rate AND Arm A full_sample Sharpe +
    admission_rate both reproduce within tolerance.

    Harness call sequence (per Step 2A ABI confirmation):
        1. load_panel(con) → treatment_1 + baseline_1 universe assignments
        2. load_price_series(con) → (stock_id, date)-indexed adj prices
        3. compute_forward_returns(panel, prices, horizons=[20])
           → attaches fwd_20td column (REQUIRED prerequisite for
           build_signal_ledger_for_horizon — see Step 2A discovery 1)
        4. For each scenario ∈ {"low_uplift", "full_sample"}:
           a. build_signal_ledger_for_horizon(panel, prices,
              pool="treatment_1", scenario, h=20, con=con)
           b. schedule_positions(ledger, BASELINE_CAP, BASELINE_MAX_POS)
              — Arm A is FIFO (no _rank_ledger); ledger has no
              rank_order column; schedule_positions uses FIFO branch
              with stock_id tertiary tie-breaking
           c. reconstruct_nav_for_horizon(scheduled, prices,
              BASELINE_CAP, h=20)
           d. compute_risk_metrics(nav_df, label)

    ABI key mapping note (Step 2A discovery 2):
        compute_risk_metrics returns dict with key "max_drawdown".
        ARM_A_REFERENCE uses key "max_dd". Both preserved as-emitted;
        delta computed via explicit cross-key access.

    Gate criteria note (Step 2A discovery 3):
        Lineage gates use ONLY sharpe + admission_rate. max_dd is
        recorded as diagnostic but does not affect verified status.

    Returns:
        Per-scenario results dict suitable for LineageStatus.results.
        Schema per scenario:
            {
              "computed":  {sharpe, admission_rate, max_drawdown},
              "reference": {sharpe, admission_rate, max_dd},
              "deltas":    {sharpe, admission_rate, max_dd},
              "gates":     {sharpe_within_tol, admission_within_tol},
            }

    Raises:
        RuntimeError if any harness call returns inconsistent shape
        (e.g. compute_risk_metrics returns error dict).

    On failure (lineage divergence), the caller
    (verify_snapshot_lineage) populates LineageStatus.divergences and
    sets verified=False. Recovery paths per SPEC §8.1: snapshot
    reconstruction, or L2 fallback. Per SPEC §8.2, plausibility
    arguments are insufficient for lineage-gate override; requires
    divergence localisation + independent attribution + documented
    evidence chain.
    """
    _log.info("Loading base panel for lineage verification ...")
    panel = load_panel(con)

    _log.info("Loading price series for lineage verification ...")
    prices = load_price_series(con)

    _log.info("Computing forward returns (horizons=[20]) ...")
    panel = compute_forward_returns(panel, prices, horizons=[20])

    results: dict[str, dict] = {}

    for scenario in ("low_uplift", "full_sample"):
        _log.info("Lineage verification: scenario=%s", scenario)

        ledger = build_signal_ledger_for_horizon(
            panel,
            prices,
            pool="treatment_1",
            scenario=scenario,
            h=20,
            con=con,
        )

        # Arm A is FIFO: no _rank_ledger call. Ledger has no
        # rank_order column; schedule_positions takes the FIFO branch
        # (sort by signal_date, stock_id) per Phase 4 ABI.
        scheduled, diag = schedule_positions(
            ledger, BASELINE_CAP, BASELINE_MAX_POS,
        )

        nav = reconstruct_nav_for_horizon(
            scheduled, prices, BASELINE_CAP, h=20,
        )

        metrics = compute_risk_metrics(
            nav, f"arm_a_lineage_{scenario}",
        )

        if "error" in metrics:
            raise RuntimeError(
                f"compute_risk_metrics returned error for "
                f"scenario={scenario}: {metrics['error']}. "
                f"Cannot verify lineage."
            )

        # Computed fingerprints
        c_sharpe = metrics["sharpe"]
        c_admission = diag["admission_rate"]
        c_max_dd = metrics["max_drawdown"]

        # Reference fingerprints (note key naming asymmetry: ref uses
        # "max_dd"; metrics dict uses "max_drawdown")
        ref = ARM_A_REFERENCE[scenario]
        r_sharpe = ref["sharpe"]
        r_admission = ref["admission_rate"]
        r_max_dd = ref["max_dd"]

        # Handle None defensively: compute_risk_metrics returns None
        # for NaN values via _f() helper. NaN/None implies degenerate
        # NAV path (e.g. all-zero returns) — treat as lineage failure
        # by setting delta to inf.
        sharpe_delta = (
            abs(c_sharpe - r_sharpe)
            if c_sharpe is not None
            else float("inf")
        )
        admission_delta = abs(c_admission - r_admission)
        max_dd_delta = (
            abs(c_max_dd - r_max_dd)
            if c_max_dd is not None
            else None
        )

        # Lineage gates: sharpe + admission_rate only (per Phase 5
        # lineage practice + precondition v0.1.1 §3 R5)
        sharpe_within = sharpe_delta <= ARM_A_SHARPE_TOL
        admission_within = admission_delta <= ARM_A_ADMISSION_TOL

        results[scenario] = {
            "computed": {
                "sharpe": c_sharpe,
                "admission_rate": c_admission,
                "max_drawdown": c_max_dd,
            },
            "reference": {
                "sharpe": r_sharpe,
                "admission_rate": r_admission,
                "max_dd": r_max_dd,
            },
            "deltas": {
                "sharpe": sharpe_delta if sharpe_delta != float("inf") else None,
                "admission_rate": admission_delta,
                "max_dd": max_dd_delta,
            },
            "gates": {
                "sharpe_within_tol": sharpe_within,
                "admission_within_tol": admission_within,
            },
        }

        _log.info(
            "lineage[%s]: sharpe=%s (ref=%.3f, Δ=%s, tol=%.3f) %s | "
            "admission=%.3f (ref=%.3f, Δ=%.3f, tol=%.3f) %s",
            scenario,
            f"{c_sharpe:.3f}" if c_sharpe is not None else "NaN",
            r_sharpe,
            f"{sharpe_delta:.3f}" if sharpe_delta != float("inf") else "inf",
            ARM_A_SHARPE_TOL,
            "PASS" if sharpe_within else "FAIL",
            c_admission, r_admission, admission_delta,
            ARM_A_ADMISSION_TOL,
            "PASS" if admission_within else "FAIL",
        )

    return results


# =====================================================================
# Evaluation orchestration
# =====================================================================


def evaluate_candidate(
    candidate: Candidate,
    scenario_start: date,
    scenario_end: date,
    lineage_anchor_label: str,
) -> tuple[CandidateMetrics, "DailyNAV"]:
    """Evaluate one candidate over one scenario window.

    Returns (metrics, daily_nav_series).

    The evaluation orchestrates:
      1. Load frozen signal pool (per ARM_B): list of
         (signal_date, symbol, rs_60d_rank, signal_metadata) — this is
         the candidate set, NOT the admission outcome. Regenerate
         admission decisions under this candidate's slot dynamics
         (per research/r8_phase6_wiring_precondition.md v0.1.1 §3 R3
         — frozen signal pool ≠ frozen admission schedule; ARM_B's
         persisted admission schedule is an OUTCOME, not an INPUT).
      2. For each admitted position, simulate paper-price holding with
         the candidate's exit decision function applied daily.
      3. Aggregate position returns into portfolio daily NAV.
      4. Compute metrics on the NAV series and admission pool.

    TODO(wiring): implement via the Phase 5 paper-price NAV
    reconstruction harness with adaptive exit overlay. Key integration
    points:
      - Signal source: Phase 5 frozen signal pool via
        build_signal_ledger_for_horizon (must match ARM_B inputs).
      - Admission: regenerate via schedule_positions for ARM_B path;
        adaptive_release_engine (Step 3 new code) for E1-E4 challengers
        with bit-identical admission semantics (per WG-1 degenerate
        equivalence test).
      - Daily loop: for each open position, build MarketSnapshot from
        adj-close + persisted feature columns (daily_features /
        bullish_features per R6 persistence-first), call
        EXIT_FUNCTIONS[candidate].
      - Position state update: max_close_since_entry trails upward;
        days_held increments; entry_atr never changes.
      - Slot release: ARM_B same-day at exit_date; E1-E4 t+1 per
        SPEC §3.1 (per R1 adaptive-exits-only invariant).
    """
    raise NotImplementedError(
        f"Candidate evaluation orchestration not yet wired. "
        f"Requires Phase 5 paper-price NAV reconstruction harness. "
        f"Candidate: {candidate}, scenario: {scenario_start}..{scenario_end}, "
        f"lineage_anchor: {lineage_anchor_label}"
    )


# Forward-declared type alias for the NAV series object. Replace with
# the concrete polars DataFrame type once wired.
DailyNAV = object


def compute_metrics(
    nav_series: DailyNAV,
    admission_stats: dict[str, int],
    holding_stats: dict[str, float],
) -> dict[str, float]:
    """Compute the §5.2 metric set on a daily NAV series.

    Sharpe is annualised with 252-day convention. MaxDD is computed on
    the equity curve. Holding statistics are aggregated across exited
    positions; admission stats from the admission pool.

    TODO(wiring): implement using existing metric utilities or polars
    primitives. Sharpe must be deterministic (no multi-threaded
    reductions). Use the same metric definitions as Phase 5 v1.0.2 §4
    to ensure cross-phase comparability.
    """
    raise NotImplementedError("Metric computation not yet wired.")


# =====================================================================
# Bootstrap (stationary block, per SPEC §5.4)
# =====================================================================


def bootstrap_delta_sharpe(
    challenger_nav: DailyNAV,
    arm_b_nav: DailyNAV,
    block_length: int,
    n_bootstrap: int = BOOTSTRAP_B,
    seed: int = 0,
) -> dict[str, float]:
    """Stationary block bootstrap on Δ_Sharpe = Sharpe(challenger) -
    Sharpe(ARM_B).

    Per SPEC §5.4, this is supplementary, not a gate criterion.
    Returns 95% CI summary and observed Δ.

    Per SPEC §5.4 exact wording: `B = 5000`, `L = max(5, h)` where
    `h` is the candidate's effective horizon at the per-call level
    (callers must supply `block_length` matching this convention; the
    runner is not free to substitute a different L estimator such as
    mean holding period).

    TODO(wiring): implement stationary block bootstrap. Use the same
    seed partitioning convention as Phase 5 to allow cross-phase
    audit.
    """
    raise NotImplementedError("Bootstrap not yet wired.")


# =====================================================================
# Gate evaluation (per SPEC §6)
# =====================================================================


def lo_sharpe_se(sharpe: float, n_obs: int) -> float:
    """Lo (2002) iid approximation of Sharpe estimator SE.

    SE(Sharpe) ≈ sqrt((1 + Sharpe^2 / 2) / T).

    Used only as a governance noise-floor reference, not as a formal
    inference procedure. Underestimates SE under autocorrelation.
    """
    if n_obs <= 0:
        return float("inf")
    return ((1.0 + 0.5 * sharpe * sharpe) / n_obs) ** 0.5


def evaluate_gates(
    candidate: Candidate,
    metrics: CandidateMetrics,
    arm_b_lu: dict[str, float],
    lu_n_obs: int,
) -> dict[str, GateResult]:
    """Evaluate P6-G1, P6-G2, P6-G3 for one candidate on Low-Uplift.

    Gate comparisons are signed deltas.

    Marginal-margin discipline (per SPEC §6.3) applies ONLY to P6-G1
    (Sharpe), because the Lo (2002) SE approximation is the
    sampling-error reference that defines "marginal" in the SPEC.
    P6-G2 (MaxDD) and P6-G3 (admission) do not have a SPEC-defined
    marginal-margin rule; their GateResult.marginal field is always
    False. Descriptive near-threshold context for G2/G3 is emitted
    by derive_verdict() as informational notes that do NOT affect
    the verdict label.
    """
    results: dict[str, GateResult] = {}

    # ---- P6-G1: Sharpe Δ ≥ -0.15 ----
    sharpe_delta = metrics.sharpe - arm_b_lu["sharpe"]
    g1_margin = sharpe_delta - P6_G1_SHARPE_DELTA_MIN
    g1_pass = sharpe_delta >= P6_G1_SHARPE_DELTA_MIN
    # Marginal if |margin| < 2 × pooled SE under Lo (2002) iid
    se_arm_b = lo_sharpe_se(arm_b_lu["sharpe"], lu_n_obs)
    se_cand = lo_sharpe_se(metrics.sharpe, lu_n_obs)
    se_pooled = (se_arm_b * se_arm_b + se_cand * se_cand) ** 0.5
    g1_marginal = g1_pass and (
        abs(g1_margin) < MARGINAL_MARGIN_SE_MULTIPLE * se_pooled
    )
    results["P6-G1"] = GateResult(
        gate_id="P6-G1",
        candidate=candidate,
        metric_value=metrics.sharpe,
        delta_vs_arm_b=sharpe_delta,
        threshold=P6_G1_SHARPE_DELTA_MIN,
        margin=g1_margin,
        pass_=g1_pass,
        marginal=g1_marginal,
    )

    # ---- P6-G2: MaxDD Δ ≤ +3pp ----
    # SPEC §6.3 marginal-margin discipline is defined via Lo (2002)
    # Sharpe SE only; MaxDD has no SPEC-defined marginal rule.
    # marginal=False unconditionally to avoid inventing un-registered
    # governance heuristics.
    maxdd_delta = metrics.max_dd - arm_b_lu["max_dd"]
    g2_margin = P6_G2_MAXDD_DELTA_MAX - maxdd_delta
    g2_pass = maxdd_delta <= P6_G2_MAXDD_DELTA_MAX
    results["P6-G2"] = GateResult(
        gate_id="P6-G2",
        candidate=candidate,
        metric_value=metrics.max_dd,
        delta_vs_arm_b=maxdd_delta,
        threshold=P6_G2_MAXDD_DELTA_MAX,
        margin=g2_margin,
        pass_=g2_pass,
        marginal=False,
    )

    # ---- P6-G3: Admission Δ ≥ +5pp ----
    # SPEC §6.3 marginal-margin discipline is defined via Lo (2002)
    # Sharpe SE only; admission rate has no SPEC-defined marginal
    # rule. marginal=False unconditionally.
    admission_delta = metrics.admission_rate - arm_b_lu["admission_rate"]
    g3_margin = admission_delta - P6_G3_ADMISSION_DELTA_MIN
    g3_pass = admission_delta >= P6_G3_ADMISSION_DELTA_MIN
    results["P6-G3"] = GateResult(
        gate_id="P6-G3",
        candidate=candidate,
        metric_value=metrics.admission_rate,
        delta_vs_arm_b=admission_delta,
        threshold=P6_G3_ADMISSION_DELTA_MIN,
        margin=g3_margin,
        pass_=g3_pass,
        marginal=False,
    )

    return results


def derive_verdict(
    candidate: Candidate,
    gates: dict[str, GateResult],
) -> CandidateVerdict:
    """Derive per-candidate verdict from gate results (per SPEC §6.3).

    SELECTED:        all three gates pass
    SELECTED (marginal): all three pass, AND P6-G1 (Sharpe) margin is
                     marginal under Lo (2002) iid SE approximation.
                     Only G1 can trigger marginal status because SPEC
                     §6.3 defines marginal-margin discipline through
                     Lo (2002) Sharpe SE; G2/G3 have no SPEC-defined
                     marginal rule.
    CHARACTERISED:   at least one but not all gates pass
    REJECTED:        none pass

    For G2 (MaxDD) and G3 (admission), the raw margin is included as
    a descriptive note in the verdict when the candidate is SELECTED
    or SELECTED_MARGINAL. These notes are informational; they do not
    affect the verdict label.

    Also enforces the A2 E3 robustness reminder: if this candidate is
    E3 and is SELECTED in any form, the verdict carries a note that
    the evaluation report MUST include the robustness flag.
    """
    n_pass = sum(g.pass_ for g in gates.values())
    notes: list[str] = []

    if n_pass == 3:
        g1 = gates["P6-G1"]
        if g1.marginal:
            label = VerdictLabel.SELECTED_MARGINAL
            notes.append(
                f"Marginal gate: P6-G1 (Sharpe Δ = {g1.delta_vs_arm_b:+.3f}, "
                f"margin past threshold = {g1.margin:+.3f}). "
                "Margin smaller than 2 × pooled SE(Sharpe) under Lo (2002) "
                "iid approximation; per SPEC §6.3, evaluation report "
                "must justify marginal status with sampling-error context."
            )
        else:
            label = VerdictLabel.SELECTED
        # Descriptive context for G2/G3 (no impact on label)
        g2 = gates["P6-G2"]
        g3 = gates["P6-G3"]
        notes.append(
            "Gate margins (descriptive, no marginal-status implication "
            "for G2/G3 per SPEC §6.3): "
            f"P6-G2 MaxDD Δ={g2.delta_vs_arm_b:+.4f} "
            f"(margin past threshold {g2.margin:+.4f}); "
            f"P6-G3 admission Δ={g3.delta_vs_arm_b:+.4f} "
            f"(margin past threshold {g3.margin:+.4f})."
        )
    elif n_pass > 0:
        label = VerdictLabel.CHARACTERISED
        notes.append(
            f"Partial gate passage ({n_pass}/3). "
            "Per SPEC §6.3, CHARACTERISED candidates are not Phase 6 "
            "deployment candidates."
        )
    else:
        label = VerdictLabel.REJECTED

    # A2 reminder: E3 structural-symmetry threshold robustness flag
    if candidate == Candidate.E3 and label in (
        VerdictLabel.SELECTED,
        VerdictLabel.SELECTED_MARGINAL,
    ):
        notes.append(
            "A2 ROBUSTNESS OBLIGATION: E3 uses a structural-symmetry "
            "RS-rank threshold (50th percentile), not a market-mechanism "
            "literature default. Evaluation report §4 MUST include a "
            "robustness flag and list Phase 6A threshold robustness "
            "re-verification as a required follow-up before any "
            "deployment authorisation."
        )

    return CandidateVerdict(
        candidate=candidate, label=label, gates=gates, notes=notes
    )


# =====================================================================
# Artifact emission
# =====================================================================


def _write_json(path: Path, payload: object) -> None:
    """Deterministic JSON write: sorted keys, 6-decimal float precision."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(
        payload,
        sort_keys=True,
        indent=2,
        default=_json_default,
    )
    path.write_text(text + "\n", encoding="utf-8")


def _json_default(o: object) -> object:
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    if isinstance(o, Enum):
        return o.value
    if hasattr(o, "__dataclass_fields__"):
        return asdict(o)  # type: ignore[arg-type]
    if isinstance(o, Path):
        return str(o)
    raise TypeError(f"Cannot serialise {type(o).__name__}")


def emit_provenance(
    output_dir: Path,
    runtime_head_sha: str,
    bootstrap_seed: int,
    lineage: LineageStatus,
    started_at: datetime,
) -> None:
    """Write provenance.json with full run identity + lineage record.

    The lineage_check block contains the complete LineageStatus
    (anchor label, per-scenario fingerprint results, divergences,
    tolerances, governance references). On verified=False runs, this
    captures the divergence evidence required by SPEC §8.2 (divergence
    localisation + independent attribution + documented evidence chain).
    """
    payload = {
        "runner": RUNNER_NAME,
        "runner_version": __version__,
        "phase_6_spec_path": PHASE_6_SPEC_PATH,
        "phase_6_spec_version": PHASE_6_SPEC_VERSION,
        "helios_head_anchor_sha": HELIOS_HEAD_ANCHOR_SHA,
        "runtime_head_sha": runtime_head_sha,
        "sha_matches_anchor": runtime_head_sha == HELIOS_HEAD_ANCHOR_SHA,
        "lineage_check": {
            "anchor_label": lineage.lineage_anchor_label,
            "verified": lineage.verified,
            "results": lineage.results,
            "divergences": lineage.divergences,
            "tolerances": {
                "sharpe": lineage.sharpe_tol,
                "admission_rate": lineage.admission_tol,
            },
            "reference_source": (
                "research/r8_phase5_price_snapshot_refresh_note.md "
                "(ARM_A_REFERENCE persisted in "
                "scripts.run_phase5_analysis)"
            ),
            "governance_ref": (
                "research/r8_phase6_wiring_precondition.md v0.1.1 §3 R5"
            ),
            "gate_criteria_note": (
                "Lineage gates use sharpe + admission_rate only. "
                "max_dd recorded as informational diagnostic, not "
                "a gate criterion."
            ),
        },
        "bootstrap_seed": bootstrap_seed,
        "started_at": started_at.isoformat(),
        "output_dir": str(output_dir),
    }
    _write_json(output_dir / PROVENANCE_FILENAME, payload)


def emit_verdicts(
    output_dir: Path,
    verdicts: dict[Candidate, CandidateVerdict],
) -> None:
    """Write verdicts.json with all four challenger verdicts."""
    payload = {
        candidate.value: verdict for candidate, verdict in verdicts.items()
    }
    _write_json(output_dir / VERDICTS_FILENAME, payload)


def emit_gate_evaluation(
    output_dir: Path,
    gate_results: dict[Candidate, dict[str, GateResult]],
) -> None:
    """Write gate_evaluation.json: P6-G1/G2/G3 per candidate."""
    payload = {
        candidate.value: {gid: gr for gid, gr in gates.items()}
        for candidate, gates in gate_results.items()
    }
    _write_json(output_dir / GATE_EVAL_FILENAME, payload)


# TODO(wiring): emit_candidate_outputs() — per-candidate NAV parquet
# and metrics JSON. Mirror followup SPEC v1.0.0 §8.2 artifact schema.
# Signature: emit_candidate_outputs(output_dir, candidate, metrics, nav)


# =====================================================================
# CLI
# =====================================================================


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=RUNNER_NAME,
        description=(
            "Phase 6 Exit Policy Evaluation runner v" + __version__
        ),
    )
    parser.add_argument(
        "--snapshot-id",
        required=True,
        metavar="LABEL",
        help=(
            "L1 snapshot lineage anchor label (e.g. '2026-06-08'). "
            "Helios has no physical snapshot identity mechanism; this "
            "label is recorded in provenance for audit traceability "
            "and does NOT participate in lineage verification logic. "
            "Verification is fingerprint-based via Arm A Sharpe + "
            "admission_rate within tolerance per Phase 5 reference. "
            "See research/r8_phase6_wiring_precondition.md v0.1.1 §3 R5."
        ),
    )
    parser.add_argument(
        "--bootstrap-seed",
        type=int,
        required=True,
        help="Deterministic seed for stationary block bootstrap.",
    )
    parser.add_argument(
        "--code-sha",
        required=True,
        help="Expected Helios HEAD SHA. Must match git rev-parse HEAD.",
    )
    parser.add_argument(
        "--candidates",
        nargs="+",
        choices=[c.value for c in Candidate if c != Candidate.ARM_B],
        default=[c.value for c in Candidate if c != Candidate.ARM_B],
        help="Candidates to evaluate (default: all four E1-E4).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Run pre-execution checks + lineage verification only. "
            "Exits 0 if lineage verifies. Emits provenance.json to "
            "--output-dir capturing the lineage check result (v0.1.3+). "
            "Skips evaluation orchestration."
        ),
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Phase 6 evaluation runner entry point.

    Exit codes:
        0 — success (real run completed, or dry-run pre-execution
            checks all passed)
        1 — operational error (CLI parsing, unexpected exception)
        2 — output-directory conflict (non-empty existing output dir)
        3 — pre-execution check failed: verify_snapshot_lineage /
            verify_arm_a_lineage_reference raised, OR lineage
            divergence detected (LineageStatus.verified == False).
            Distinct from operational error: indicates the runner
            cannot guarantee its pre-execution invariants under the
            current snapshot. Provenance is written before exit (v0.1.3+)
            to preserve divergence evidence per SPEC §8.2.
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logger = logging.getLogger(RUNNER_NAME)
    logger.info("Phase 6 evaluation runner v%s starting", __version__)

    output_dir: Path = args.output_dir
    logger.info("Resolved output directory: %s", output_dir)

    # --- Output directory (early — required as artifact destination
    # for lineage divergence provenance per SPEC §8.2) ---
    #
    # The output-directory conflict check (exit code 2) must happen
    # BEFORE any pre-execution check that could populate the lineage
    # divergence record. Otherwise a non-empty output_dir + lineage
    # divergence would exit 2 (output conflict) without persisting
    # the lineage evidence, breaking the SPEC §8.2 documented
    # evidence chain guarantee.
    if output_dir.exists() and any(output_dir.iterdir()):
        logger.error(
            "Output directory %s exists and is non-empty. "
            "Phase 6 evaluation refuses to overwrite prior outputs. "
            "Move or remove the directory and re-run.",
            output_dir,
        )
        return 2
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- Pre-execution checks (fail-closed) ---
    #
    # Per SPEC §8.1 + §8.2, snapshot ID verification and Arm A lineage
    # re-verification are pre-execution GUARDS, not advisory checks.
    # If they cannot be executed (current skeleton state), the runner
    # cannot guarantee that ARM_B reference values in §2 are reproducible
    # on the current snapshot. Continuing past a stubbed guard would
    # silently propagate an unverified baseline into all downstream
    # gate evaluations.
    #
    # Therefore, ANY pre-execution check failure aborts the run (or
    # the dry-run) with exit code 3. As of v0.1.3, this covers:
    #   - verify_code_sha mismatch (RuntimeError)
    #   - verify_snapshot_lineage raising (RuntimeError or unexpected
    #     Exception from harness chain), OR
    #   - LineageStatus.verified == False (divergence detected).
    # Stubs raising NotImplementedError still apply to remaining
    # unwired functions (evaluate_candidate, compute_metrics,
    # bootstrap_delta_sharpe — Step 3 scope).
    # This applies equally to --dry-run: dry-run is meant to verify
    # pre-execution readiness, so a failed lineage check means
    # dry-run is reporting genuine lineage failure, not stub failure.

    try:
        runtime_sha = verify_code_sha(args.code_sha)
        logger.info("Code SHA verified: %s", runtime_sha)
    except RuntimeError as exc:
        logger.error("Code SHA verification failed: %s", exc)
        return 3
    except subprocess.CalledProcessError as exc:
        logger.error("git invocation failed: %s", exc)
        return 3

    # --- Lineage verification (L1 snapshot fingerprint check) ---
    # Per SPEC §8.1, recompute Arm A LU + full_sample on current snapshot
    # and compare against Phase 5 reference within tolerance. On
    # divergence, exit 3 — recovery paths per SPEC §8.2 require
    # divergence localisation + independent attribution + documented
    # evidence chain; plausibility arguments insufficient.
    if not HELIOS_DB_PATH.exists():
        logger.error(
            "Helios DuckDB not found at %s — cannot perform lineage "
            "verification. Check data/_storage/ and confirm canonical "
            "path matches HELIOS_DB_PATH constant.",
            HELIOS_DB_PATH,
        )
        return 3

    try:
        con = duckdb.connect(str(HELIOS_DB_PATH), read_only=True)
    except Exception as exc:
        logger.error(
            "Failed to open Helios DuckDB at %s: %s",
            HELIOS_DB_PATH, exc,
        )
        return 3

    try:
        try:
            lineage = verify_snapshot_lineage(args.snapshot_id, con)
        except RuntimeError as exc:
            logger.error("Lineage verification error: %s", exc)
            return 3
        except Exception as exc:
            logger.error(
                "Unexpected error during lineage verification: %s "
                "(type=%s). Refusing to proceed.",
                exc, type(exc).__name__,
            )
            return 3

        if not lineage.verified:
            logger.error(
                "L1 lineage verification FAILED — %d/%d scenarios "
                "outside tolerance (sharpe±%.3f, admission±%.3f). "
                "Per SPEC §8.1, recovery requires either snapshot "
                "reconstruction or L2 fallback with full four-cell "
                "rerun. Per SPEC §8.2, plausibility arguments are "
                "insufficient for lineage-gate override.",
                len(lineage.divergences), len(lineage.results),
                lineage.sharpe_tol, lineage.admission_tol,
            )
            for d in lineage.divergences:
                logger.error(
                    "  divergence[%s]: sharpe_delta=%s "
                    "admission_delta=%.4f gates=%s",
                    d["scenario"],
                    f"{d['sharpe_delta']:.4f}"
                    if d['sharpe_delta'] is not None else "None/NaN",
                    d["admission_delta"],
                    d["gates"],
                )

        # Always proceed to persist LineageStatus to provenance —
        # divergence evidence is governance artifact per SPEC §8.2
        # (documented evidence chain). The verified status determines
        # whether we proceed to evaluation, but the lineage record
        # itself is persisted regardless.
        if lineage.verified:
            logger.info(
                "L1 lineage VERIFIED: anchor=%s; all scenarios within "
                "tolerance.", args.snapshot_id,
            )
    finally:
        con.close()

    # --- Provenance (always written, before dry-run / divergence exits) ---
    started_at = datetime.now(tz=timezone.utc)
    emit_provenance(
        output_dir=output_dir,
        runtime_head_sha=runtime_sha,
        bootstrap_seed=args.bootstrap_seed,
        lineage=lineage,
        started_at=started_at,
    )

    if not lineage.verified:
        logger.error(
            "Provenance written to %s. Exiting with code 3 due to "
            "lineage divergence. See provenance.json lineage_check "
            "block for full evidence.",
            output_dir / PROVENANCE_FILENAME,
        )
        return 3

    if args.dry_run:
        logger.info(
            "Dry-run mode: all pre-execution checks passed; "
            "provenance written to %s; exiting 0.",
            output_dir / PROVENANCE_FILENAME,
        )
        return 0

    # --- Evaluation loop (stubbed) ---
    logger.warning(
        "Evaluation orchestration is currently stubbed. "
        "Wire evaluate_candidate(), compute_metrics(), "
        "bootstrap_delta_sharpe() to the Phase 5 paper-price NAV "
        "reconstruction harness before production use."
    )

    # Skeleton sketch of the evaluation flow:
    #
    # arm_b_metrics, arm_b_nav = evaluate_candidate(
    #     Candidate.ARM_B, LU_START, LU_END, args.snapshot_id
    # )
    # _write_json(output_dir / ARM_B_METRICS_FILENAME, arm_b_metrics)
    #
    # gate_results: dict[Candidate, dict[str, GateResult]] = {}
    # verdicts: dict[Candidate, CandidateVerdict] = {}
    # for candidate_value in args.candidates:
    #     candidate = Candidate(candidate_value)
    #     metrics, nav = evaluate_candidate(
    #         candidate, LU_START, LU_END, args.snapshot_id
    #     )
    #     gates = evaluate_gates(
    #         candidate, metrics, ARM_B_REFERENCE["low_uplift"],
    #         lu_n_obs=...,  # number of trading days in LU window
    #     )
    #     verdict = derive_verdict(candidate, gates)
    #     gate_results[candidate] = gates
    #     verdicts[candidate] = verdict
    #     # emit_candidate_outputs(output_dir, candidate, metrics, nav)
    #
    # emit_gate_evaluation(output_dir, gate_results)
    # emit_verdicts(output_dir, verdicts)

    logger.info(
        "Phase 6 evaluation runner finished (skeleton, no work done)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
