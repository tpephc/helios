# research/r8_phase6_governance_report.md

# Phase 6 — Governance Report

**Date:** 2026-06-21
**Evaluation:** R8 Phase 6 Exit Policy Evaluation
**SPEC version:** v0.1.1
**Status:** STEP 3 COMPLETE / FINDING REGISTERED

---

## Step Completion Status

| Step | Description | Status | Evidence |
|------|-------------|--------|----------|
| 3A | Feature ABI discovery | CLOSED | ABI matrix, 3-layer evidence (signature + body + caller) |
| 3B | Exit decision functions | CLOSED | 39 unit tests PASS |
| 3C | adaptive_release_engine + WG-1 | CLOSED | WG-1 PASS (3 tests, degenerate equivalence) |
| 3D | evaluate_candidate wiring | CLOSED | ARM_B + E1–E4 smoke PASS, E3 rank ABI locked |
| 3E | bootstrap_delta_sharpe | CLOSED | T1–T4 smoke PASS (NAV-aligned, B=5000 capable) |
| 3F | Gate orchestration | CLOSED | Integration run PASS, all 5 candidates |
| 3G | Full evaluation | CLOSED | B=5000, provenance.json written |

---

## Governance Artifacts Produced

```text
scripts/phase6_adaptive_engine.py     — Step 3C engine (WG-1 verified)
scripts/phase6_evaluate_candidate.py  — Step 3D wiring
scripts/phase6_bootstrap.py           — Step 3E bootstrap
scripts/phase6_orchestration.py       — Step 3F orchestration
research/r8_phase6/
    step3g_provenance_2026_06_21.json — Step 3G provenance artifact
research/r8_phase6_findings.md        — F-P6-01
research/r8_phase6_candidate_disposition.md
research/r8_phase6_governance_report.md
research/r8_phase6_closeout.md
```

---

## Key Invariants Verified

| Invariant | Verification |
|-----------|-------------|
| WG-1 degenerate equivalence | PASS — adaptive engine bit-identical to Phase 5 canonical under never_exit_policy |
| P3-FP-002 exposure invariant | PASS — all candidates, max_exposure ≤ 100% |
| ARM_B admission unchanged | PASS — canonical path does not touch adaptive engine |
| Bootstrap NAV-aligned | PASS — common block indices, inner join on date |
| Block length L = max(5,20) = 20 | ENFORCED — ValueError on deviation |
| Bootstrap supplementary only | ENFORCED — bootstrap not wired to gate evaluation |
| E3 rank ABI SPEC §3.4 | LOCKED — PERCENT_RANK over ARM_B valid_path universe per date range |

---

## Open Items (Non-blocking for Step 3 closeout)

| ID | Description | Severity | Target |
|----|-------------|----------|--------|
| P6-3F-001 | scenario_start/end not yet filtering evaluation window | Medium | Phase 6A or Step 4 |
| DQ-P6-001 | Symbols 6919, 910322 missing close bars | Low | Data audit |
| OBS-P6-E3-001 | E3 rank universe is scenario-wide, not exact per-date eligible | Low | Phase 6A if E3 re-evaluated |
| OBS-P6-E4-001 | E4 near-ARM_B (89.9% ceiling) — exploratory value preserved | Observation | Phase 6A scope |

---

## Governance Discipline Notes

**Spec-first discipline maintained:** All E1–E4 parameters were
pre-registered in SPEC v0.1.1 before implementation. No parameters
were modified after seeing results.

**Lock-before-look maintained:** Step 3A ABI discovery completed and
locked before Step 3B implementation. WG-1 passed before Step 3D.

**Structural reuse (CCI-7):** adaptive_release_engine uses Phase 4
schedule_positions admission block as copy-with-modification. WG-1
confirms bit-identical behaviour under degenerate policy.

**Provenance types:** All provenance.json values are Python-native
types (float, int, str) per governance convention.

**A2 robustness obligation:** E3 uses structural-symmetry threshold.
If E3 is re-evaluated in Phase 6A, the evaluation report must include
the robustness flag per SPEC §2 A2.
