# R8 MA5 Momentum — Phase 5 Configuration Selection Specification

<!-- research/r8_phase5_spec.md -->
<!-- v0.1.0 — 2026-06-07 -->

**Status:** LOCKED — v0.1.0 (2026-06-07)
**Inherits from:**
- `research/r8_phase1_interim_findings.md` v1.0.0 (CONFIRMED)
- `research/r8_phase1_lifecycle_spec.md` v0.2.1 (LOCKED)
- `research/r8_phase3_spec.md` v0.1.2 (LOCKED)
- `research/r8_phase3_risk_report.md` v1.0.1 (LOCKED)
- `research/r8_phase4_spec.md` v0.1.1 (LOCKED)
- `research/r8_phase4_optimisation_report.md` v1.0.0 (LOCKED)
**Prerequisite:** Phase 4 OPTIMISATION_CHARACTERISED verdict (confirmed 2026-06-07)
**Authorises:** Phase 5 Configuration Selection research only.
**Does not authorise:** Production deployment, live signal generation,
modification of the Helios paper-trading exit contract, or any Phase 6 work.

---

## Changelog

| Version | Date | Change |
|---|---|---|
| v0.1.0 | 2026-06-07 | Initial SPEC DRAFT. D1–D3 decisions frozen. Three-arm structure defined. P5-G1/G2/G3 gate criteria frozen. |

---

## 1. Research Question

> Can the capital-utilisation improvements identified in Phase 4 be
> converted into a superior deployable portfolio configuration without
> materially degrading risk-adjusted performance in the Low-Uplift
> environment?

This question connects the Phase 3–5 arc directly:

| Phase | Question answered |
|---|---|
| Phase 3 | Can the edge be deployed? (CHARACTERISED) |
| Phase 4 | Can capital utilisation be improved? (OPTIMISATION_CHARACTERISED) |
| Phase 5 | Which configuration should be brought to deployment evaluation? |

Phase 5 does not re-validate R8 signal edge. That question was answered
in Phase 1 (CONFIRMED), Phase 2A (STABLE), and Phase 2B (FEASIBLE). Phase 5
takes the edge as given and asks whether a specific portfolio construction
configuration improves on the Phase 3 baseline in a deployable way.

**Relationship to paper trading:** Phase 5 remains a research track only.
Findings do not authorise modification of the Helios paper-trading exit
contract. The governance path is: Phase 5 → Phase 5 SPEC verdict →
Phase 6 deployment evaluation SPEC → paper-trading candidate.

---

## 2. Inheritance from Phase 4

### Key findings carried forward

| Finding | Value | Source |
|---|---|---|
| Phase 3 baseline Sharpe (Full Sample, 20td FIFO) | 2.378 | Phase 3 Track A |
| Phase 3 baseline Sharpe (Low-Uplift, 20td FIFO) | 1.613 | Phase 3 Track A |
| Phase 3 baseline MaxDD (Full Sample) | 21.6% | Phase 3 Track A |
| Phase 3 baseline admission rate | 16.3% (Full Sample) | Phase 3 §3.1 |
| RS-60d CANDIDATE: Low-Uplift Δ Sharpe | +0.515 | Phase 4 Track B |
| 10td RESEARCH_FINDING: admission improvement | +13.7pp | Phase 4 Track A |
| 10td RESEARCH_FINDING: Low-Uplift Δ Sharpe | +0.501 | Phase 4 Track A |
| 10td + RS-60d combined | Not directly tested | Phase 4 §8 |
| Low-Uplift bootstrap CI | Crosses zero at all horizons | Phase 4 Track A |

### Mandatory Phase 5 assumptions (from Phase 4 §7)

1. Low-Uplift is the primary stress environment for all Phase 5 evaluation.
2. Low-Uplift bootstrap CI crosses zero at all tested horizons — this is not
   used as a gate criterion (see D2).
3. 10td + RS-60d combined configuration has not been directly tested; Phase 5
   is the first direct evaluation.
4. FIFO is not a viable baseline for Phase 5 comparison (Phase 4 confirmed
   all quality variants dominate FIFO). Phase 3 FIFO baseline is retained
   only as the frozen reference point for gate criteria calculations.

---

## 3. Decisions

### D1: Research arm structure

**Decision:** Three pre-registered arms evaluated in parallel.

| Arm | Configuration | Purpose |
|---|---|---|
| **A — Frozen baseline** | 20td + FIFO | Frozen Phase 3 reference; not a candidate |
| **B — Isolated ranking** | 20td + RS-60d ranking | Isolates Track B effect; CANDIDATE per Phase 4 |
| **C — Combined candidate** | 10td + RS-60d ranking | Primary combined configuration; first direct test |

**Rationale for arm structure:**

Arm A is frozen from Phase 3. It is never a candidate; it exists only
to anchor the gate criteria. Including it in Phase 5 execution produces
reproducibility verification, not new research.

Arm B isolates the ranking effect at the baseline holding period. This is
the cleanest test of the Phase 4 Track B finding. If Arm B passes the gate
criteria, the RS-60d ranking alone is sufficient for a CANDIDATE recommendation.

Arm C is the primary Phase 5 question: does combining 10td holding period
with RS-60d ranking produce a configuration that retains the Low-Uplift
improvement from both tracks? Phase 4 found each component individually
promising; this is their first combined test.

**Why `10td + FIFO` is not a primary arm:**
Phase 4 confirmed RS-60d ranking as a robust improvement (CANDIDATE status).
Evaluating `10td + FIFO` without ranking would test a configuration already
known to be suboptimal relative to RS-60d. Arm C subsumes this question.

**Why Track C (early exit rules) is excluded:**
Track C introduces path-dependent exit policy — a categorically different
problem from portfolio construction (holding period + ranking). Combining
Track C with Arms A/B/C in the same SPEC would create a multi-dimensional
parameter space that makes results difficult to interpret. Track C is
reserved for Phase 6. See §9 (Scope Constraints).

### D2: Gate criteria (P5-G1, P5-G2, P5-G3)

**Decision:** Phase 5 gates measure relative improvement vs Phase 3/4
baseline. CI-based gates are not used because the Low-Uplift bootstrap
CI crosses zero at all tested horizons (Phase 4 confirmation). A gate
requiring CI > 0 would reject the Phase 3 baseline itself — a logical
contradiction.

**Primary environment: Low-Uplift** (Segments 2+3, 2023-10-24 to 2025-08-08).
This is the most conservative stress environment per Phase 3 §4.3.

| Gate | Criterion | Measurement | Threshold |
|---|---|---|---|
| **P5-G1** | Low-Uplift Sharpe must not deteriorate vs Phase 3 baseline | `Sharpe(arm) - Sharpe(Arm A)` | **≥ −0.10** |
| **P5-G2** | Low-Uplift MaxDD must not worsen materially vs Phase 3 baseline | `MaxDD(arm) - MaxDD(Arm A)` | **≤ +3pp** |
| **P5-G3** | Admission rate improvement must be retained | `admission_rate(arm) - admission_rate(Arm A)` | **≥ +10pp** for Arm C; not applicable to Arm B |

**Gate rationale:**

P5-G1 (Sharpe −0.10 tolerance): The Phase 4 Low-Uplift Sharpe for 20td
FIFO is 1.613. A −0.10 tolerance allows small degradation from the combined
configuration while requiring that the overall risk-adjusted profile is not
materially harmed. This reflects the Phase 3 methodology: risk characterisation
is the goal, not proof of alpha.

P5-G2 (MaxDD +3pp tolerance): The Phase 3 baseline MaxDD in Low-Uplift is
20.5%. A +3pp ceiling (≤ 23.5%) prevents configurations that improve Sharpe
via higher volatility from passing undetected.

P5-G3 (Admission +10pp for Arm C): Arm C must demonstrate a meaningful
capital utilisation improvement. The +10pp threshold is below the Phase 4
observed improvement (+13.7pp for 10td alone) to allow for some interaction
effect from combining with RS-60d ranking. If Arm C fails P5-G3, it means
the combined configuration eliminates the holding-period utilisation benefit.

**Important caveat (thresholds are governance heuristics):** These thresholds
are not statistically derived. They are design decisions intended to
operationalise "materially not worse" in a quantifiable way. The Phase 5
report must document them as such and must not present them as statistical
significance boundaries.

### D3: Track C exclusion (Phase 6 reservation)

**Decision:** Track C (ATR-trailing, MA20-failure, RS-deterioration early
exit rules) is explicitly excluded from Phase 5 scope.

**Rationale:** Track C is a path-dependent exit policy problem. Evaluating
it alongside holding-period selection and ranking would create a multi-
dimensional parameter space where individual contributions are difficult
to attribute. Phase 4 Track A and B produced clean, interpretable findings
precisely because each track isolated one variable. Phase 5 preserves this
discipline.

**Phase 6 reservation:** RS-deterioration exit (monitoring `beta_adj_rs_20d`
or `beta_adj_rs_60d` during the holding window) is the most theoretically
motivated early exit rule — it directly monitors whether the signal condition
that triggered entry is still valid. Phase 6 should evaluate RS-deterioration
exit in combination with the Phase 5 selected configuration, not alongside it.

---

## 4. Arms

### Arm A — Frozen baseline (20td + FIFO)

Re-execute Phase 3 / Phase 4 Arm A methodology with identical parameters:
- Holding period: 20 trading days
- Ranking: FIFO (signal_date ASC, stock_id ASC)
- Capital scheduler: Interpretation B, 10% cap, max 10 positions
- NAV: D1A calendar-time MTM
- Scenarios: Full Sample + Low-Uplift

**Purpose:** Verify reproducibility of Phase 3/4 baseline. If Arm A
deviates materially from Phase 3 reference values (Sharpe 2.378 / 1.613,
admission 16.3% / 17.5%), the runner has a data or lineage issue. This
constitutes a Phase 5 abort condition (not a gate failure).

**Reference values (from Phase 3 / Phase 4):**

| Metric | Full Sample | Low-Uplift |
|---|---|---|
| Sharpe | 2.378 | 1.613 |
| MaxDD | 21.6% | 20.5% |
| Admission rate | 16.3% | 17.5% |

### Arm B — Isolated ranking (20td + RS-60d)

Phase 4 Track B baseline configuration:
- Holding period: 20 trading days
- Ranking: RS-60d (`beta_adj_rs_60d` DESC within each signal_date)
- Capital scheduler: identical to Arm A
- Scenarios: Full Sample + Low-Uplift

**Reference values from Phase 4 Track B:**

| Metric | Full Sample | Low-Uplift |
|---|---|---|
| Sharpe | 2.563 | 2.128 |
| MaxDD | 19.5% | 16.2% |
| Admission rate | 16.3% | 17.5% |

Arm B Phase 5 execution should reproduce these values (within minor
floating-point variation from fresh DuckDB reads). Material deviation
indicates a lineage issue.

### Arm C — Combined candidate (10td + RS-60d)

Primary Phase 5 research configuration:
- Holding period: 10 trading days
- Ranking: RS-60d (`beta_adj_rs_60d` DESC within each signal_date)
- Capital scheduler: identical to Arms A/B but with 10td exit_date
- Scenarios: Full Sample + Low-Uplift

**Expected admission rates (from Phase 4 Track A, FIFO baseline):**
~30% (Full Sample), ~32% (Low-Uplift). With RS-60d ranking the admission
rate is unchanged (ranking affects which positions are admitted, not count).

**The combined effect is untested:** Phase 4 found each component individually
beneficial. The interaction — whether 10td holding + RS-60d ranking produces
additive, sub-additive, or super-additive improvement — is the primary
empirical question of Phase 5.

---

## 5. Forward return requirements

Phase 5 requires `fwd_10td` in addition to `fwd_20td`. Use:

```python
compute_forward_returns(panel, prices, horizons=[10, 20])
```

The 20td outcome is required for Arm A and B evaluation. The 10td outcome
is required for Arm C. Bootstrap Δ_A3 is computed at the arm's holding
horizon: h=20 for Arms A/B, h=10 for Arm C.

**P3-FP-001 fingerprint:** Arm A must reproduce Full-sample 20td net_s1 =
+1.64% ± 1 bp before any analysis proceeds. Failure aborts the run.

---

## 6. Bootstrap

Two-sample stationary block bootstrap per Phase 4 SPEC §5.3:
- B = 5,000
- Block length: L = max(5, h) where h is the arm's holding period
- Both treatment and baseline resampled independently

Bootstrap Δ_A3 is computed for each arm but is **not used as a gate criterion**
(per D2). It is reported as supplementary evidence only. Phase 5 gates are
P5-G1, P5-G2, and P5-G3.

---

## 7. Output Specification

### 7.1 Deliverable

**Phase 5 Configuration Selection Report**
(`research/r8_phase5_configuration_report.md`)

Sections:
1. Executive Summary (arm verdicts + Design Recommendation for Phase 6)
2. Methodology (D1–D3 decisions, arm definitions, gate criteria)
3. Arm A — Baseline reproduction (reproducibility check)
4. Arm B — Isolated ranking results vs gates
5. Arm C — Combined candidate results vs gates
6. Cross-arm comparison
7. Verdict Assessment (Layer 1 + Layer 2)
8. Phase 6 Assumptions
9. Residual Limitations
10. Governance

### 7.2 Artifacts

| Artifact | Path | Content |
|---|---|---|
| Forward return matrix | `data/_storage/r8_phase5/v0.1.0/forward_return_matrix.parquet` | fwd_10td, fwd_20td for all panel rows |
| Arm results | `data/_storage/r8_phase5/v0.1.0/p5_arm_results.parquet` | Risk metrics + gate evaluation per arm × scenario |
| Bootstrap results | `data/_storage/r8_phase5/v0.1.0/p5_bootstrap.parquet` | Δ_A3 CI per arm (supplementary only) |
| Manifest | `data/_storage/r8_phase5/v0.1.0/manifest.json` | Artifact inventory + commit hash |

### 7.3 Verdict structure

**Layer 1 — Research completion:**

| Verdict | Definition |
|---|---|
| **CONFIGURATION_SELECTED** | At least one arm (B or C) passes all applicable gates; Design Recommendation issued |
| **CONFIGURATION_NOT_SELECTED** | No arm passes all applicable gates; RETAIN_20TD_RS60D_STUDY or FURTHER_RESEARCH issued |
| **INCOMPLETE** | One or more mandatory arms could not be evaluated |

**Layer 2 — Design Recommendations (advisory):**

| Recommendation type | Issued when |
|---|---|
| `SELECTED: [arm]` | Named arm passes P5-G1, P5-G2, and (if Arm C) P5-G3 |
| `RETAIN_20TD_RS60D_STUDY` | Arm B passes gates but Arm C fails; 20td + RS-60d is the Phase 6 starting point |
| `FURTHER_RESEARCH_REQUIRED` | Neither Arm B nor C passes all gates; specific failure modes documented |

**Gate evaluation per arm:**

Arm B gates: P5-G1 (Sharpe ≥ −0.10 vs Arm A), P5-G2 (MaxDD ≤ +3pp vs Arm A).
Arm C gates: P5-G1, P5-G2, and P5-G3 (Admission ≥ +10pp vs Arm A).

An arm that passes all its gates earns `SELECTED` status.
Both arms may pass simultaneously — report both.

---

## 8. Scope Constraints

### Explicitly out of scope

- Re-estimation of Phase 1 Δ_A3 or re-validation of the CONFIRMED finding.
- Signal parameter optimisation.
- Track C early exit rules (reserved for Phase 6).
- Live or paper-trading execution or exit contract modification.
- Dynamic slippage or price-impact modelling.
- `10td + FIFO` as a standalone arm (subsumed by Arm C).
- `rs_20d_ranking` as a standalone arm (RS-60d designated per Phase 4 B3).
- Bearish signal evaluation.
- Any Phase 6 work of any kind.

### Relationship to Phase 4

Phase 5 does not re-validate Phase 4 findings. Arms A and B reproduce
Phase 3/4 baselines for lineage verification; they are not new research
on those configurations. Phase 5 is not permitted to revise Phase 4
CANDIDATE or RESEARCH_FINDING designations.

---

## 9. Governance

### Upstream dependencies

| Document | Version | Status |
|---|---|---|
| `research/r8_phase1_interim_findings.md` | v1.0.0 | CONFIRMED |
| `research/r8_phase3_risk_report.md` | v1.0.1 | LOCKED |
| `research/r8_phase4_spec.md` | v0.1.1 | LOCKED |
| `research/r8_phase4_optimisation_report.md` | v1.0.0 | LOCKED |

### Downstream authorisations

| Phase | Authorised by | Requires |
|---|---|---|
| Phase 5 analysis | This SPEC | — |
| Phase 6 (deployment evaluation) | Phase 5 CONFIGURATION_SELECTED | Phase 6 SPEC (must address selected configuration and Phase 5 residual limitations) |

CONFIGURATION_NOT_SELECTED does not block Phase 6. It requires a Phase 6
SPEC that explicitly addresses the gate failures and whether further
optimisation is warranted before deployment evaluation.

**If CONFIGURATION_NOT_SELECTED:** 20td + RS-60d (Arm B) remains the
current best-observed configuration from the Phase 1–5 research chain.
Failure to select a new configuration does not mean all candidates are
invalid — it means Arm C did not clear the combined gate criteria within
this historical sample.

INCOMPLETE blocks Phase 6 until the missing arm is resolved via SPEC amendment.

### Runner planning notes (non-blocking, for implementation reference)

1. **Arm B gate outcome is expected:** Based on Phase 4 Track B results
   (Low-Uplift Sharpe 2.128, MaxDD 16.2%), Arm B is expected to pass P5-G1
   and P5-G2. Phase 5 Arm B execution primarily serves as lineage confirmation.
   The Phase 5 report must state this explicitly rather than presenting Arm B
   as a new research finding.

2. **Arm C pre-registered hypotheses (for report interpretation only —
   not gate criteria):**
   - H1: Sharpe(C, Low-Uplift) > Sharpe(Arm A, Low-Uplift) [= 1.613]
   - H2: Sharpe(C, Low-Uplift) ≥ Sharpe(Arm B, Low-Uplift) [= 2.128]
   The Phase 5 report must state whether H1 and H2 were supported, regardless
   of gate outcomes. H2 failure (Arm C < Arm B) would indicate that 10td
   holding period degrades the quality ranking benefit.

### Amendment policy

Changes to D1 (arm definitions), D2 (gate thresholds or gate logic), D3
(Track C exclusion), §5 (horizon requirements), or §7.3 (verdict categories)
require a SPEC version bump with documented rationale. Silent edits are
not permitted.

---

## 10. What Phase 5 Does Not Establish

Regardless of verdict:

- That the selected configuration produces superior OOS returns.
- That CONFIGURATION_SELECTED authorises paper-trading modification.
- That CONFIGURATION_NOT_SELECTED invalidates Phase 1–4 findings.
- That Phase 5 findings will persist on future data.
- That the Phase 5 selected configuration is optimal within any larger
  parameter space.
- That SELECTED status authorises Phase 6 deployment without a new SPEC.

---

*End of r8_phase5_spec.md v0.1.0*
