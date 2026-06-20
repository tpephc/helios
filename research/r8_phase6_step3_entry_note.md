# Phase 6 — Step 3 Entry Note

**Date:** 2026-06-20

This note is a forward-looking governance boundary marker. It rec­ords
the transition point at which Phase 6 Step 2 is closed and Step 3 is
declared not-yet-started. It is intentionally brief: it does not
specify implementation, does not enumerate ABI evidence, and does not
re-derive risk content from `r8_phase6_wiring_precondition.md` v0.1.1.

The next Step 3 session should read this note first (target: 3 minutes)
before any code or grep.

---

## Current Governance State

**Completed:**

- Phase 6 SPEC v0.1.1 LOCKED
- Wiring precondition v0.1.1 LOCKED
- Step 1 rename complete (`78f8c3b`, v0.1.2)
- Step 2 lineage wiring complete (`b33bd19` → `c177151` → `9121e2b`,
  v0.1.3 → v0.1.5)
- R5 validated
- R6 active

**Evidence:**

- `research/r8_phase6_step2_lineage_closeout_2026_06_20.md`
- `research/r8_phase6/step2_lineage_verified_2026_06_20.json`
- Arm A LU + full_sample fingerprints reproduced within tolerance
  (sharpe Δ ≤ 2.09e-4, admission Δ ≤ 3.00e-3)

**Current HEAD:**

- `141f774`

---

## Step 3 Objective

Implement adaptive-exit evaluation framework (E1–E4) while preserving:

- Phase 5 admission semantics
- Phase 3 NAV math
- R1 / R2 / R3 / R6 invariants
- WG-1 structural reuse gate

---

## Step 3 Sub-Steps

### Step 3A — Feature ABI discovery

**Scope:**
- Confirm feature source columns (`bullish_features`, ATR columns,
  MA columns) required by E1–E4 exit decisions.
- Confirm persistence-layer access pattern (read path, not compute path).
- Confirm caller pattern.

**Not in scope:** evaluation logic.

**Completion:** ABI evidence table fully populated for every feature
column consumed by E1–E4.

### Step 3B — Exit decision functions

**Scope:**
- `should_exit_e1`, `should_exit_e2`, `should_exit_e3`, `should_exit_e4`
- Pure functions only (no I/O, no DB access, no state mutation).

**Completion:** unit tests pass (per-policy + boundary conditions).

### Step 3C — `adaptive_release_engine`

**Scope:**
- Implement t+1 release semantics.
- Structural reuse of admission logic (per CCI-7 wiring surface
  note; not function-call reuse).

**Gate:** WG-1 mandatory.

**Completion:** degenerate-equivalence test passes (bit-identical
NAV when adaptive features are degenerate; engine reduces to ARM_B
canonical Phase 5 behaviour).

### Step 3D — `evaluate_candidate` wiring

**Scope:**
- ARM_B canonical path.
- Challenger path (E1–E4 over `adaptive_release_engine`).

**Completion:** candidate evaluation executes end-to-end on
current snapshot.

### Step 3E — `bootstrap_delta_sharpe`

**Scope:**
- Lo (2002) stationary block bootstrap implementation per SPEC §5.4.

**Completion:** smoke tests pass on degenerate (zero Δ) and
non-degenerate inputs; reproducible under `--bootstrap-seed`.

### Step 3F — Gate orchestration

**Scope:**
- G1–G5 implementation per SPEC §6.

**Completion:** `CandidateVerdict` generated end-to-end per candidate.

### Step 3G — Full evaluation

**Scope:**
- E1–E4 execution on current snapshot.

**Completion:** evaluation artifacts produced; provenance.json
includes per-candidate metrics, gates, verdicts.

---

## Hard Gates

**WG-1 MUST pass before Step 3D.**

No challenger evaluation may begin before:

- Step 3A complete
- Step 3B complete
- Step 3C complete (with WG-1 passing)

These are hard ordering constraints, not recommendations. Violation
invalidates Step 3 evidence chain.

---

## Lessons Carried Forward

1. **Signature confirmed ≠ ABI confirmed.**
2. ABI confirmation requires three artefacts:
   - signature
   - body access pattern
   - caller usage pattern
3. Provenance payloads must use Python-native types
   (`float`, `bool`, `int`, `str`, `None`); numpy / pandas
   implementation types do not cross the governance boundary.
4. **Structural reuse does not imply function-call reuse.**
   Copy-block-with-modification + a degenerate-equivalence test is
   the correct discipline when invariants must be preserved while
   the surrounding logic changes (per CCI-7).
5. **Admission engine drift is a higher risk than release-engine
   implementation defects.** A subtle drift in `schedule_positions`
   semantics breaks ARM_B baseline comparability silently; a
   release-engine bug fails loudly.

---

## Explicit Non-Goals

Not part of Step 3:

- New ranking features
- New admission rules
- Capacity-model redesign
- Portfolio sizing redesign
- Phase 5 benchmark modification
- Governance amendments unless a new risk is discovered

If a non-goal becomes necessary mid-implementation, Step 3 halts;
the work moves to a separate `r8_phase6_wiring_precondition` v0.1.2
or a Phase 7 SPEC, depending on scope.

---

*Entry note authored at end of Step 2 closeout session. No code or
ABI grep performed in writing this note. Next Step 3 session begins
with Step 3A.*
