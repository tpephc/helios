# R8 MA5 Momentum — Phase 5 Configuration Selection Report

<!-- research/r8_phase5_configuration_report.md -->
<!-- v1.0.2 — 2026-06-19 -->

**Status:** LOCKED — v1.0.2 (2026-06-19)

**Changelog:**

| Version | Date | Change |
|---|---|---|
| v1.0.0 | 2026-06-08 | Initial report draft |
| v1.0.1 | 2026-06-08 | P5-RPT-001: §6.2 Arm C gate result labelled MARGINAL PASS with explicit margin language. P5-RPT-002: §3.4 expanded with full price-snapshot divergence table (694/1013 dates, nav_end 6.477→6.975, Sharpe 2.378→2.498). P5-RPT-003+006: §7 Finding P5-4 H1/H2 interpretation section added — failure ≠ Arm C fail; capacity and Sharpe are separate dimensions. P5-RPT-004: §1 Executive Summary Primary/Secondary candidate distinction made explicit. P5-RPT-005: §9.3 Phase 6 research hypothesis reframed around "reduce capital occupancy without truncating alpha harvesting period" — not further ranking refinement. |
| v1.0.2 | 2026-06-19 | P5-PATCH-001: ARM_C reclassified from SELECTED (marginal P5-G1) to CAPACITY_DEMONSTRATED / SHARPE_UNRESOLVED. Gate-passage facts unchanged; verdict label revised to reflect that Sharpe preservation is not statistically distinguishable from noise. P5-PATCH-002: §7 Finding P5-4 downgraded to Working Hypothesis P5-4 — Phase 4 single-factor estimates and Phase 5 combined estimate were measured on different `daily_price_adj` snapshots; interaction identification is not clean. Resolution scoped as P5-FOLLOWUP-001 (owned by Phase 6 SPEC). P5-PATCH-003: §7 P5-3 statistical-significance wording corrected — gate margin is not a significance criterion. P5-PATCH-004: §3.4 and new §8.6 disclose that lineage-gate attribution to the adj-price refresh is plausibility-based, not independently reconciled at symbol level. Forward governance requirement for future lineage-gate overrides recorded as a Phase 6 SPEC item. §9 Phase 6 motivation restructured so that capital occupancy (Arm A admission 17.5%, 82.5% rejected due to lock-up) is the primary justification for exit-policy research; the working hypothesis P5-4 is supplementary, not load-bearing. |
**Verdict:** CONFIGURATION_SELECTED
**Selected Arms:** ARM_B (20td + RS-60d)
**Reclassified Arms:** ARM_C (10td + RS-60d) → CAPACITY_DEMONSTRATED / SHARPE_UNRESOLVED
**Recommended Deployment Baseline:** ARM_B
**Runner:** `scripts/run_phase5_analysis.py` v0.1.0
**Artifacts:** `data/_storage/r8_phase5/v0.1.0/`
**SPEC:** `research/r8_phase5_spec.md` v0.1.0 (LOCKED)
**Price Snapshot:** `data/_storage/helios.duckdb` as of 2026-06-08
  (retroactive adj-price update detected; see §8 and
  `research/r8_phase5_price_snapshot_refresh_note.md`)

---

## 1. Executive Summary

Phase 5 evaluated three pre-registered portfolio configurations against
the capital utilisation and risk-adjusted performance questions carried
forward from Phase 3 and Phase 4.

ARM_B (20td + RS-60d ranking) is selected as the sole deployable Phase 6
baseline. ARM_C (10td + RS-60d ranking) is reclassified as
**CAPACITY_DEMONSTRATED / SHARPE_UNRESOLVED**: its admission gain is a
mechanical, robust finding, but its Sharpe gate passage is not
statistically distinguishable from noise and is sensitive to the
adj-price snapshot. The phase verdict remains **CONFIGURATION_SELECTED**
because the Phase 5 research question (which configuration should be
brought to deployment evaluation) is answered by ARM_B alone.

**ARM_B is the recommended deployment baseline for Phase 6.** It
demonstrated a substantial improvement in Low-Uplift Sharpe (+0.635 vs
Arm A) and a meaningful reduction in maximum drawdown (−3.23pp), with
no loss of admission capacity. The gate margins are wide, and the Phase
4 CANDIDATE designation for RS-60d ranking is fully confirmed.

**ARM_C satisfied all three pre-registered gates at evaluation, but only
marginally satisfied the Sharpe gate (P5-G1, Δ = −0.093 against a
threshold of −0.10, margin = +0.007).** The +0.007 margin is narrow
relative to the sampling error of the Sharpe estimate at this sample
size, and the Low-Uplift bootstrap CI (§5) crosses zero. Under the
locked Phase 3 price snapshot, Arm C's P5-G1 Δ would be −0.137, which
would not pass. ARM_C demonstrates that 10td holding substantially
increases admission rate (17.5% → 32.4%) — this is a mechanical effect
of capital turnover and is robust; its claimed Sharpe preservation is
not. ARM_C is therefore reclassified rather than treated as a
co-equal deployment candidate.

Three findings and one working hypothesis emerged from the Phase 5
analysis:

- **P5-1 (finding):** RS-60d ranking is confirmed as a robust improvement
  in the Low-Uplift environment.
- **P5-2 (finding):** 10td holding period materially increases capital
  utilisation.
- **P5-3 (finding):** The capacity gain from shorter holding is not free;
  Sharpe declines.
- **P5-4 (working hypothesis, not established):** RS-60d ranking and
  10td holding may be sub-additive when combined. Identification is
  blocked by a snapshot inconsistency between Phase 4 single-factor
  estimates (old snapshot) and the Phase 5 combined estimate (new
  snapshot). Resolution is scoped as P5-FOLLOWUP-001 and owned by the
  Phase 6 SPEC.

Phase 5 remains a research track only. ARM_B selection does not
authorise modification of the Helios paper-trading exit contract.
Phase 6 requires a new SPEC.

**Selected Arm: ARM_B (20td + RS-60d).** Wide-margin gate passage,
simultaneous Sharpe improvement and MaxDD reduction, no snapshot
sensitivity. This is the Phase 6 deployment baseline.

**Reclassified Arm: ARM_C (10td + RS-60d) → CAPACITY_DEMONSTRATED /
SHARPE_UNRESOLVED.** ARM_C establishes that shorter fixed holding can
materially expand admission rate (+14.83pp, mechanical and robust). It
does not establish that 10td is a deployable production parameter:
P5-G1 passage is marginal, snapshot-sensitive, and within the Sharpe
estimator's sampling error. ARM_C is retained in the Phase 5 record as
a capacity reference, not as a Phase 6 candidate.

---

## 2. Objectives

Phase 5 asked a single pre-registered research question:

> Can the capital-utilisation improvements identified in Phase 4 be
> converted into a superior deployable portfolio configuration without
> materially degrading risk-adjusted performance in the Low-Uplift
> environment?

This question connects directly to the Phase 3–5 arc:

| Phase | Question answered |
|---|---|
| Phase 3 | Can the edge be deployed? (CHARACTERISED) |
| Phase 4 | Can capital utilisation be improved? (OPTIMISATION_CHARACTERISED) |
| Phase 5 | Which configuration should be brought to deployment evaluation? |

Phase 5 does not re-validate the R8 signal edge. That question was
answered in Phase 1 (CONFIRMED), Phase 2A (STABLE), and Phase 2B
(FEASIBLE). Phase 5 takes the edge as given and asks whether specific
portfolio construction choices improve the Phase 3 baseline in a
deployable way.

---

## 3. Experimental Design

### 3.1 Three-arm structure (D1)

Three arms were pre-registered and evaluated in parallel:

| Arm | Configuration | Purpose |
|---|---|---|
| **A** | 20td + FIFO | Frozen Phase 3 baseline; lineage verification only |
| **B** | 20td + RS-60d ranking | Isolated ranking effect; Phase 4 CANDIDATE |
| **C** | 10td + RS-60d ranking | Combined candidate; primary Phase 5 question |

Arm A is not a candidate. It exists to anchor gate criteria and verify
reproducibility.

### 3.2 Gate criteria (D2)

Gates are evaluated on the Low-Uplift scenario only (Segments 2+3,
2023-10-24 to 2025-08-08), which is the primary stress environment per
Phase 3 §4.3. All thresholds are governance heuristics, not statistical
significance boundaries.

| Gate | Criterion | Threshold | Applies to |
|---|---|---|---|
| P5-G1 | Sharpe(arm, LU) − Sharpe(A, LU) | ≥ −0.10 | Arms B and C |
| P5-G2 | MaxDD(arm, LU) − MaxDD(A, LU) | ≤ +3pp | Arms B and C |
| P5-G3 | Admission(arm, LU) − Admission(A, LU) | ≥ +10pp | Arm C only |

CI-based gates were not used because the Low-Uplift bootstrap CI crosses
zero at all tested horizons (Phase 4 confirmation). A gate requiring
CI > 0 would reject the Phase 3 baseline itself — a logical
contradiction.

### 3.3 Forward returns and bootstrap

Phase 5 required `fwd_10td` (Arm C) and `fwd_20td` (Arms A and B).
Bootstrap Δ_A3 was computed at each arm's holding horizon using the
two-sample stationary block bootstrap (B = 5,000, L = max(5, h)).
Bootstrap results are supplementary only and are not gate criteria.

### 3.4 Price snapshot note — retroactive adj-price update

During Phase 5 execution, a retroactive adjustment to `daily_price_adj`
was detected. This affected 694 of 1013 common trading dates, with the
first NAV divergence at 2023-07-14 (consistent with TWSE annual
ex-dividend restatement season).

| Metric | Phase 3 locked | Phase 5 recomputed | Delta |
|---|---|---|---|
| Full-sample Sharpe (Arm A) | 2.377654 | 2.498050 | +0.120 |
| Full-sample nav_end | 6.477569 | 6.974622 | +0.497 |
| Low-Uplift Sharpe (Arm A) | 1.613070 | 1.569000 | −0.044 |

Governance decision (Option A, approved 2026-06-08): all three arms
were evaluated on the current adj-price snapshot to preserve cross-arm
comparability. Phase 3/4 locked artifacts are not modified.
ARM_A_REFERENCE was updated to Phase 5 price-snapshot baseline values
(P5-REF-001 in `scripts/run_phase5_analysis.py`).

**Attribution note (P5-PATCH-004):** Attribution of the +0.120 Sharpe
shift to a `daily_price_adj` retroactive adjustment is based on the
observed divergence pattern (694/1013 dates, first divergence
2023-07-14) and its consistency with annual TWSE ex-dividend
restatement timing. No independent symbol-level reconciliation against
TWSE source records was performed at the time of the lineage-gate
override. The plausibility argument was accepted because: (i) the
divergence was concentrated in the pre-2024 segment, (ii) Phase 5 LU
Sharpe shift (−0.044) was within tolerance, suggesting recent prices
were stable, and (iii) the position/date pool was unchanged. This is
recorded as a limitation in §8.6. A forward governance requirement
covering future lineage-gate overrides is recorded for the Phase 6
SPEC.

The full-sample Sharpe shift (+0.120) exceeds the lineage gate tolerance
(±0.050) and triggered the P5-BLOCK-001 abort on the first run. The
Low-Uplift Sharpe shift (−0.044) is within tolerance, confirming that
recent adj prices (2023–2025) are stable and that the drift is
concentrated in the pre-2024 historical segment.

**Critical consequence:** Arm C's P5-G1 gate result is sensitive to
this snapshot. See §6.2 Sensitivity Note for the full impact.

For complete traceability see:
`research/r8_phase5_price_snapshot_refresh_note.md` v0.1.0

---

## 4. Arm Results

### 4.1 Arm A — Frozen baseline (20td + FIFO)

Lineage check: PASS (both scenarios within tolerance).

| Metric | Full Sample | Low-Uplift |
|---|---|---|
| Sharpe | 2.498 | 1.569 |
| Ann. Return | 62.12% | 35.34% |
| Ann. Volatility | 24.87% | 22.52% |
| MaxDD | 21.65% | 20.54% |
| Calmar | 2.869 | 1.721 |
| Admission rate | 16.3% | 17.5% |
| Scheduled / Candidates | 350 / 2143 | 180 / 1027 |

RS_T3 benchmark (Low-Uplift): Sharpe 1.543, MaxDD 18.94%.

Arm A full-sample Sharpe (2.498) differs from the locked Phase 3
reference (2.378) due to the adj-price retroactive update. This is
expected and documented. The lineage check passed against the Phase 5
price-snapshot baseline (ARM_A_REFERENCE updated per P5-REF-001).

### 4.2 Arm B — Isolated ranking (20td + RS-60d)

| Metric | Full Sample | Low-Uplift |
|---|---|---|
| Sharpe | 2.813 | 2.204 |
| Ann. Return | 72.65% | 50.22% |
| Ann. Volatility | 25.82% | 22.79% |
| MaxDD | 17.28% | 17.31% |
| Calmar | 4.203 | 2.901 |
| Admission rate | 16.3% | 17.5% |
| Scheduled / Candidates | 350 / 2143 | 180 / 1027 |

RS_T3 benchmark (Low-Uplift): Sharpe 1.543, MaxDD 18.94%.

Arm B admission rate is identical to Arm A (as expected: ranking
affects *which* positions are admitted, not *how many*). The Sharpe
improvement is entirely attributable to selecting higher-quality signals
within the same capital constraints.

### 4.3 Arm C — Combined candidate (10td + RS-60d)

| Metric | Full Sample | Low-Uplift |
|---|---|---|
| Sharpe | 1.754 | 1.476 |
| Ann. Return | 42.88% | 34.00% |
| Ann. Volatility | 24.45% | 23.03% |
| MaxDD | 20.71% | 20.71% |
| Calmar | 2.071 | 1.642 |
| Admission rate | 30.0% | 32.4% |
| Scheduled / Candidates | 663 / 2207 | 333 / 1029 |

RS_T3 benchmark (Low-Uplift): Sharpe 0.634, MaxDD 26.87%.

Arm C nearly doubles admission rate vs Arm A in Low-Uplift (17.5% →
32.4%, ×1.85). However, Low-Uplift Sharpe falls from 1.569 (Arm A) to
1.476 despite RS-60d ranking. This is in apparent contrast to Phase 4
Track A findings, where 10td alone (FIFO baseline) produced Low-Uplift
Sharpe 2.114 vs 1.613 for 20td FIFO. The contrast is read with caution
because the Phase 4 single-factor estimates were collected on a
different `daily_price_adj` snapshot from the Phase 5 estimates above;
see Working Hypothesis P5-4 in §7 for the identification problem and
P5-FOLLOWUP-001 for the resolution path.

---

## 5. Bootstrap Analysis (Supplementary)

Bootstrap Δ_A3 is reported as supplementary evidence only. Per D2, it
is not a Phase 5 gate criterion.

| Arm | Scenario | Obs. Δ | 95% CI | L | Interpretation |
|---|---|---|---|---|---|
| A | Full Sample | +1.877% | [+0.106%, +3.738%] | 20 | CI excludes zero — consistent with Phase 1 |
| A | Low-Uplift | +0.426% | [−1.792%, +2.713%] | 20 | CI crosses zero — expected per Phase 4 |
| B | Full Sample | +1.877% | [+0.144%, +3.709%] | 20 | CI excludes zero |
| B | Low-Uplift | +0.426% | [−1.799%, +2.685%] | 20 | CI crosses zero — same Δ as Arm A (identical baseline pool) |
| C | Full Sample | +1.166% | [+0.274%, +2.090%] | 10 | CI excludes zero |
| C | Low-Uplift | +0.214% | [−0.804%, +1.181%] | 10 | CI crosses zero |

All Low-Uplift CIs cross zero. This is consistent with Phase 4 findings
and is the reason CI-based gates were not adopted for Phase 5 (D2).
The Full-Sample CIs excluding zero provide directional consistency
with the Phase 1 CONFIRMED finding but do not constitute new
out-of-sample evidence.

Note: Arm A and Arm B share the same baseline pool (baseline_1,
full_sample) and thus produce the same Δ_obs and near-identical CIs.
This is expected — the bootstrap tests raw signal edge, not
configuration-conditional return.

---

## 6. Gate Evaluation

All gates evaluated against Arm A Low-Uplift (Phase 5 price-snapshot
baseline: Sharpe 1.569, MaxDD 20.54%, Admission 17.5%).

### 6.1 Arm B gate results

| Gate | Criterion | Observed Δ | Threshold | Margin | Result |
|---|---|---|---|---|---|
| P5-G1 | Sharpe Δ | +0.635 | ≥ −0.10 | +0.735 | **PASS** |
| P5-G2 | MaxDD Δ | −3.23pp | ≤ +3pp | +6.23pp | **PASS** |

Arm B passes both gates with wide margins. The RS-60d ranking produces
a substantial and unambiguous improvement in the Low-Uplift stress
environment.

### 6.2 Arm C gate results

| Gate | Criterion | Observed Δ | Threshold | Margin | Result |
|---|---|---|---|---|---|
| P5-G1 | Sharpe Δ | −0.093 | ≥ −0.10 | +0.007 | **MARGINAL PASS** |
| P5-G2 | MaxDD Δ | +0.17pp | ≤ +3pp | +2.83pp | **PASS** |
| P5-G3 | Admission Δ | +14.83pp | ≥ +10pp | +4.83pp | **PASS** |

**Arm C satisfied P5-G1 by a margin of only +0.007 Sharpe units relative
to the frozen gate threshold. This should be interpreted as a marginal
gate passage, not as strong evidence of Sharpe preservation.** P5-G2 and
P5-G3 are genuine passes with comfortable margins.

**Sensitivity note — P5-G1 for Arm C:**
The P5-G1 result is sensitive to the adj-price snapshot used for the
Arm A reference Sharpe (see §3.4). Under the Phase 5 price-snapshot
baseline (Sharpe(A) = 1.569), Arm C passes with a margin of +0.007.
Under the locked Phase 3 reference (Sharpe(A) = 1.613), the observed
Δ would be −0.137, which would **not** satisfy P5-G1 (threshold −0.10).

This sensitivity does not invalidate the gate-passage facts at
evaluation time — all three arms were evaluated on a consistent
adj-price basis under approved governance. However, ARM_C's gate
passage is not robust to snapshot timing. In v1.0.2, ARM_C is
reclassified to CAPACITY_DEMONSTRATED / SHARPE_UNRESOLVED (§6.3) and is
not carried forward as a Phase 6 deployment candidate. ARM_B remains
the sole Phase 6 deployment baseline.

### 6.3 Verdict

| Arm | Gates passed (at evaluation) | Verdict label (v1.0.2) |
|---|---|---|
| A | N/A (lineage reference) | — |
| B | P5-G1 ✓, P5-G2 ✓ | **SELECTED** |
| C | P5-G1 ✓ (marginal), P5-G2 ✓, P5-G3 ✓ | **CAPACITY_DEMONSTRATED / SHARPE_UNRESOLVED** (see note) |

Gate-passage facts (column 2) are historical record at evaluation time
and are not modified by v1.0.2. The verdict label (column 3) reflects
post-evaluation interpretation. Arm C's P5-G1 margin of +0.007 is
narrow relative to the sampling error of the Sharpe estimator at this
sample size (see §7 Finding P5-3) and is sensitive to the adj-price
snapshot (see §6.2). The mechanical admission gain (P5-G3) is robust;
the Sharpe-preservation interpretation is not. ARM_C is therefore
reclassified rather than carried as a co-equal SELECTED arm.

**Layer 1:** CONFIGURATION_SELECTED
**Layer 2:** SELECTED: ARM_B
**Reclassified:** ARM_C → CAPACITY_DEMONSTRATED / SHARPE_UNRESOLVED

---

## 7. Findings

### Finding P5-1: RS-60d ranking is confirmed

RS-60d ranking (`beta_adj_rs_60d` DESC within each signal date)
produces a robust improvement in the Low-Uplift stress environment.
Holding period is unchanged from Phase 3 baseline (20td); the
improvement is entirely attributable to signal selection quality.

| Environment | Arm A Sharpe | Arm B Sharpe | Δ Sharpe | Arm A MaxDD | Arm B MaxDD | Δ MaxDD |
|---|---|---|---|---|---|---|
| Full Sample | 2.498 | 2.813 | +0.315 | 21.65% | 17.28% | −4.37pp |
| Low-Uplift | 1.569 | 2.204 | +0.635 | 20.54% | 17.31% | −3.23pp |

The improvement is stronger in Low-Uplift than Full Sample, indicating
that RS-60d ranking is particularly effective in the stress environment
Phase 5 was designed to evaluate. This confirms the Phase 4 CANDIDATE
designation and elevates RS-60d ranking to a Phase 6 design baseline.

### Finding P5-2: 10td holding materially increases capital utilisation

Reducing holding period from 20td to 10td (Arm C vs Arm A, both using
RS-60d ranking) substantially increases the fraction of signals that
can be admitted under the 10-position, 10%-cap constraint.

| Scenario | Arm A Admission | Arm C Admission | Δ Admission |
|---|---|---|---|
| Full Sample | 16.3% | 30.0% | +13.7pp |
| Low-Uplift | 17.5% | 32.4% | +14.9pp |

In Low-Uplift, Arm C admits approximately 1.85× as many signals as Arm
A. The mechanism is straightforward: shorter holding releases capital
earlier, reducing the lock-up probability for subsequent signals. This
is consistent with the Little's Law approximation from Phase 3:
signal demand × holding period drives slot-day occupancy.

The P5-G3 gate (+10pp threshold) was passed with a margin of +4.83pp,
confirming that the capacity improvement is genuine and not an artefact
of sample selection.

### Finding P5-3: The capacity gain from shorter holding is not free

Arm C's capacity improvement comes at a measurable cost to
risk-adjusted performance. In Low-Uplift, Sharpe declines from 1.569
(Arm A) to 1.476 (Arm C), a reduction of 0.093 — just inside the
pre-registered P5-G1 gate.

| Metric | Arm A (20td+FIFO) | Arm C (10td+RS-60d) | Δ |
|---|---|---|---|
| Low-Uplift Sharpe | 1.569 | 1.476 | −0.093 |
| Low-Uplift MaxDD | 20.54% | 20.71% | +0.17pp |
| Low-Uplift Admission | 17.5% | 32.4% | +14.83pp |

The Sharpe cost is modest in absolute terms. **The gate margin (+0.007)
is narrow relative to the sampling error of the Sharpe estimate at this
sample size; the Sharpe difference between Arm C and Arm A is not
statistically distinguishable from noise** (the Low-Uplift bootstrap CI
crosses zero, §5). The pre-registered gate margin is a governance
threshold, not a statistical-significance criterion. Phase 6 should
treat Arm C as a proof-of-concept for capacity expansion rather than as
a production-ready parameter choice; the reclassification to
CAPACITY_DEMONSTRATED / SHARPE_UNRESOLVED in §6.3 reflects this.

### Working Hypothesis P5-4: RS-60d ranking and 10td holding may be sub-additive

**Status:** WORKING HYPOTHESIS — not an established finding. Resolution
is scoped as **P5-FOLLOWUP-001**, owned by the Phase 6 SPEC. Downgrade
from "Finding" to "Working Hypothesis" in v1.0.2 (P5-PATCH-002).

**Why this is not an established finding (identification problem):**
The apparent non-additivity rests on comparing Phase 4 single-factor
Sharpe estimates against the Phase 5 combined-configuration Sharpe
estimate. These two sets of estimates were measured on **different
`daily_price_adj` snapshots**:

| Configuration | Source | Snapshot |
|---|---|---|
| 20td + FIFO Sharpe = 1.613 | Phase 4 | pre-2026-06-08 |
| 20td + RS-60d Sharpe = 2.128 | Phase 4 | pre-2026-06-08 |
| 10td + FIFO Sharpe = 2.114 | Phase 4 | pre-2026-06-08 |
| Arm A (20td + FIFO) Sharpe = 1.569 | Phase 5 | 2026-06-08 |
| Arm B (20td + RS-60d) Sharpe = 2.204 | Phase 5 | 2026-06-08 |
| Arm C (10td + RS-60d) Sharpe = 1.476 | Phase 5 | 2026-06-08 |

The snapshot refresh shifted Arm A's Low-Uplift Sharpe by −0.044 (§3.4).
This is the **same order of magnitude** as the apparent interaction
effect that would need to be present for "non-additivity" to be a clean
conclusion. Phase 4's `10td + FIFO` configuration was not re-evaluated
on the Phase 5 snapshot, so the interaction term

```
Δ_interaction = Sharpe(RS-60d + 10td) − Sharpe(RS-60d, 20td)
                                       − Sharpe(FIFO, 10td)
                                       + Sharpe(FIFO, 20td)
```

cannot be computed from a snapshot-consistent set of estimates. Until
this is done, the apparent sub-additivity is **suggestive but not
identified**: it may be a real interaction, or it may be partially or
fully an artefact of the cross-snapshot comparison.

**Observed Phase 5 comparison (snapshot-consistent within Phase 5
only):**

| Configuration | Low-Uplift Sharpe | vs Arm A (FIFO, 20td) |
|---|---|---|
| Arm A: 20td + FIFO | 1.569 | baseline |
| Arm B: 20td + RS-60d | 2.204 | +0.635 |
| Arm C: 10td + RS-60d | 1.476 | −0.093 |

What this table establishes (snapshot-consistent): adding RS-60d ranking
at 20td raises Sharpe substantially; the combined `10td + RS-60d`
configuration sits below `20td + FIFO`. What it does **not** establish
on its own is whether this is an interaction effect or a level effect
of 10td holding under the current snapshot — that requires comparison
to a snapshot-matched `10td + FIFO` estimate that Phase 5 did not
collect.

**Pre-registered hypotheses for Arm C (from SPEC §9):**
- H1: Sharpe(C, LU) > 1.613 — NOT SUPPORTED (observed: 1.476)
- H2: Sharpe(C, LU) ≥ 2.128 — NOT SUPPORTED (observed: 1.476)

**Interpretation of H1/H2 failure:**
H1 and H2 were pre-registered as documentary hypotheses — expected-value
statements derived from Phase 4 single-component estimates — not as
gate criteria, and not as identified interaction tests. Their failure
is consistent with a sub-additive interaction; it is also consistent
with the Phase 4 single-factor estimates being snapshot-biased. The
H1/H2 NOT SUPPORTED labels remain correct as documentary record but do
not by themselves resolve the identification question.

What can be said with confidence (snapshot-consistent within Phase 5,
free of any cross-phase comparison):
- ARM_C delivers a robust admission improvement (P5-2, mechanical).
- ARM_C's Sharpe is below Arm B's Sharpe (Phase 5 baseline) by 0.728.
- ARM_C's Sharpe is below Arm A's Sharpe by 0.093, within sampling
  error of the Sharpe estimator at this sample size (P5-3).

What cannot be said until P5-FOLLOWUP-001 resolves the snapshot
inconsistency: that the deficit `Arm_C − Arm_A = −0.093` is attributable
to an interaction between RS-60d ranking and 10td holding rather than
to a level effect of 10td holding under the current snapshot.

**Implication for Phase 6 motivation:** The working hypothesis is
suggestive enough to inform Phase 6 design but is **not load-bearing**
for the Phase 6 exit-policy research direction. The primary motivation
for exit-policy research is the capital-occupancy bottleneck (Arm A LU
admission = 17.5%, 82.5% of signals rejected due to capital lock-up;
see §9.2), which is established independently of P5-4. If
P5-FOLLOWUP-001 ultimately rejects the sub-additivity hypothesis, the
Phase 6 research direction does not need to be revised.

---

## 8. Limitations

### 8.1 Price snapshot sensitivity (Arm C P5-G1)

As described in §6.2, Arm C's P5-G1 gate result is sensitive to the
adj-price snapshot used for the Arm A reference Sharpe. The Phase 5
governance decision (Option A) ensures cross-arm consistency, but the
margin of 0.007 is narrow enough that a future adj-price restatement
could change the Arm C gate outcome. Arm B's SELECTED status is not
affected — its P5-G1 margin is +0.735.

### 8.2 Single price snapshot

All results reflect the `daily_price_adj` snapshot as of 2026-06-08.
TWSE adj-price restatements occur regularly, and historical metrics
may shift as further corporate action records are processed. The Phase 3
experience (694 of 1013 NAV dates affected by a single restatement
cycle) illustrates the potential magnitude of such shifts. Phase 6
should document its own snapshot date explicitly.

### 8.3 Low-Uplift bootstrap CI crosses zero

The Low-Uplift bootstrap CI crosses zero for all arms at all horizons.
This is not a new limitation — it was documented in Phase 4 and is
the reason CI-based gates were not adopted. It means the Low-Uplift
Sharpe improvements cannot be distinguished from noise by this
bootstrap test. The gate improvements are observed in the historical
sample; their persistence is not established.

### 8.4 Arm C is a first-ever direct test

Phase 4 tested RS-60d ranking and 10td holding separately. Phase 5 is
the first direct evaluation of their combination. The sub-additive
appearance (Working Hypothesis P5-4) was not anticipated. Because
Phase 4 single-factor estimates and the Phase 5 combined estimate were
collected on different `daily_price_adj` snapshots, the apparent
sub-additivity is not cleanly identified; resolution is scoped as
P5-FOLLOWUP-001. Phase 6 should not assume that other combinations of
Phase 4 candidates will be additive without snapshot-consistent
re-evaluation.

### 8.5 Scope constraints

Phase 5 did not evaluate Track C early exit rules, bearish signals,
dynamic slippage modelling, or live execution. All findings are
conditional on the fixed-hold, paper-price NAV reconstruction
methodology used in Phases 3–5.

### 8.6 Lineage-gate attribution is plausibility-based

The +0.120 full-sample Sharpe shift that triggered the P5-BLOCK-001
lineage-gate abort (§3.4) was attributed to a `daily_price_adj`
retroactive update on the basis of: (i) the divergence pattern (694/1013
common dates affected, with first divergence on 2023-07-14), and (ii)
the consistency of this timing with the annual TWSE ex-dividend
restatement cycle. **No independent symbol-level reconciliation against
TWSE source records was performed at the time of the lineage-gate
override.** The reference baseline update (P5-REF-001) was therefore
accepted on a plausibility argument, not on an identified attribution.

The plausibility argument is strong but is not equivalent to an
identification. A future lineage-gate trigger of similar magnitude
could in principle have a non-snapshot cause (e.g., a corporate-action
ingestion bug, an upstream FinMind/Shioaji data anomaly, or a universe
drift defect) and would not be distinguishable from a price-snapshot
refresh by the diagnostic procedure used here.

Phase 5 v1.0.2 records this as a limitation but does not retroactively
add validation that did not occur. A forward governance requirement —
that future lineage-gate overrides require divergence localisation, an
independent attribution check, and a documented evidence chain before
the reference baseline is updated — is recorded as a Phase 6 SPEC item
(see §9.4).

---

## 9. Phase 6 Implications

### 9.1 Recommended baseline

ARM_B (20td + RS-60d) is the sole Phase 6 deployment baseline. It has
demonstrated consistent, wide-margin improvement over the FIFO baseline
in the Low-Uplift environment, and its gate margins provide a stable
reference against which Phase 6 exit policy variants can be compared.
ARM_C is not a Phase 6 candidate; its CAPACITY_DEMONSTRATED status is
a research reference for the scale of admission gain achievable through
fixed holding-period reduction, not a deployment endorsement.

### 9.2 Primary motivation for Phase 6: the capital-occupancy bottleneck

Phase 5 establishes that capital occupancy is the primary constraint on
R8 deployable capacity. In Low-Uplift:

```
Arm A LU admission rate:          17.5%
Signals rejected (capital lock):  82.5%
```

This is a **mechanical** observation, independent of any Sharpe
estimate. It is robust to snapshot timing, to sampling error in
risk-adjusted-performance estimators, and to the P5-4 identification
question. Of every 100 eligible R8 signals in the Low-Uplift stress
environment, 82 are rejected not because they look bad but because
slots are occupied by earlier positions in their fixed 20td hold. Arm B
improves signal selection within this constraint but does not relax
it. The Phase 5 deployable configuration (ARM_B) is therefore capacity-
bottlenecked by construction.

This observation is sufficient, on its own, to justify Phase 6
exit-policy research. The Phase 5 verdict (CONFIGURATION_SELECTED with
ARM_B) does not need any interaction-effect interpretation to motivate
that research direction.

### 9.3 Phase 6 research hypothesis

The right question for Phase 6 is:

> Can capital occupancy be reduced without truncating the alpha
> harvesting period?

This is the structural argument for adaptive exit policy research.
ARM_B holds every position for a fixed 20td regardless of how the
position performs during the hold. An adaptive exit policy would
release capital from underperforming positions earlier (recovering
occupancy) while allowing high-quality positions to run toward 20td
(preserving alpha). The achievable Pareto frontier between capacity
recovery and alpha preservation is the empirical Phase 6 question;
adaptive exit policies will incur some selection cost (positions exited
early that would have recovered) and Phase 6 will need to characterise
this cost as part of the evaluation.

The question Phase 6 should **not** ask is:

> Can another ranking factor outperform RS-60d?

Phase 5 (Finding P5-1) answered this: RS-60d ranking is confirmed and
becomes the fixed Phase 6 baseline. The signal selection problem is
largely solved within the current architecture; the bottleneck has
moved to capital occupancy.

**Supplementary motivation (working hypothesis P5-4):** If
P5-FOLLOWUP-001 confirms a genuine sub-additive interaction between
RS-60d ranking and fixed 10td holding, this provides additional reason
to prefer an adaptive (state-conditional) exit over a fixed shorter
hold. If P5-FOLLOWUP-001 rejects the interaction hypothesis, the Phase
6 research direction is not invalidated — capital occupancy is by
itself sufficient justification (§9.2).

### 9.4 Phase 6 design constraints

The Phase 6 SPEC must address:

1. ARM_B as the frozen baseline (not re-estimated in Phase 6).
2. ARM_C reclassification to CAPACITY_DEMONSTRATED / SHARPE_UNRESOLVED
   — Phase 6 must not treat 10td as a validated parameter; if any
   Phase 6 exit policy implicitly truncates effective holding period,
   the resulting Sharpe must be evaluated against ARM_B, not against
   ARM_C.
3. The price-snapshot refresh: Phase 6 must document its own snapshot
   date and check for further adj-price restatements since Phase 5.
4. **P5-FOLLOWUP-001 ownership:** The Phase 6 SPEC must decide whether
   to allocate research budget to a snapshot-consistent re-evaluation
   of Phase 4 single-factor configurations (`20td + FIFO`,
   `10td + FIFO`, `20td + RS-60d`) on the Phase 5 snapshot, in order
   to identify the interaction term and promote (or reject) Working
   Hypothesis P5-4. Phase 6 may decide that this is not the highest-
   value research expenditure; this decision must be explicit in the
   SPEC.
5. **Lineage-gate override governance (from §8.6):** Future lineage-gate
   triggers of comparable magnitude must require divergence
   localisation, an independent attribution check (e.g., symbol-level
   reconciliation against TWSE source records or cross-validation
   against a second adj-price source), and a documented evidence chain
   before the reference baseline is updated. Plausibility-based
   attribution is no longer sufficient.
6. Track C (signal characterisation) research proceeds independently
   and does not feed into Phase 6 unless explicitly authorised by
   a future SPEC.

### 9.5 Why exit policy, not further ranking refinement

Finding P5-1 confirms RS-60d ranking. The signal selection problem is
largely solved within the current architecture. Track C (C-001 through
C-006) will investigate whether further signal characterisation can
sharpen entry quality, but this is a longer-horizon research programme.
For the immediate Phase 6 question — how to bring an R8-based strategy
to paper-trading evaluation — the bottleneck is capital occupancy, not
entry ranking. Exit policy research directly targets this bottleneck.

---

## 10. Conclusion

Phase 5 achieved its pre-registered research objective. One
configuration is selected as the Phase 6 deployment baseline; a second
configuration is reclassified to a research reference rather than a
deployment candidate.

**ARM_B (20td + RS-60d) — SELECTED:** Robust, wide-margin improvement
over the Phase 3 baseline in the Low-Uplift stress environment.
Confirmed as the Phase 6 deployment baseline. The RS-60d ranking benefit
is consistent across full sample and stress environment, and across
multiple metrics (Sharpe and MaxDD).

**ARM_C (10td + RS-60d) — RECLASSIFIED to CAPACITY_DEMONSTRATED /
SHARPE_UNRESOLVED:** ARM_C satisfied all three pre-registered gates at
evaluation time. On post-evaluation review, its P5-G1 margin (+0.007)
is narrow relative to the sampling error of the Sharpe estimator at
this sample size, and the gate result is sensitive to the adj-price
snapshot. The mechanical admission gain (17.5% → 32.4%) is robust and
remains a valid research reference for capacity expansion via shorter
fixed holding. ARM_C is not a Phase 6 candidate.

The Phase 5 → Phase 6 research direction (capital occupancy as the
primary deployment bottleneck, exit policy as the primary research
target) rests on the mechanical Arm A LU admission figure (17.5%
admitted, 82.5% rejected due to capital lock-up). This argument is
independent of Working Hypothesis P5-4 and is therefore robust to the
P5-FOLLOWUP-001 outcome.

**Working Hypothesis P5-4** — that RS-60d ranking and 10td holding are
sub-additive — is retained as a working hypothesis because the
identification rests on a cross-snapshot comparison that Phase 5 did
not collect snapshot-consistent estimates to resolve. P5-FOLLOWUP-001
is owned by the Phase 6 SPEC, which decides whether to resolve it.

Phase 5 does not authorise paper-trading modification. Phase 6
requires a new SPEC.

---

## Governance

| Document | Version | Status |
|---|---|---|
| `research/r8_phase1_interim_findings.md` | v1.0.0 | CONFIRMED |
| `research/r8_phase3_risk_report.md` | v1.0.1 | LOCKED |
| `research/r8_phase4_optimisation_report.md` | v1.0.0 | LOCKED |
| `research/r8_phase5_spec.md` | v0.1.0 | LOCKED |
| `research/r8_phase5_price_snapshot_refresh_note.md` | v0.1.0 | GOVERNANCE NOTE |
| `research/r8_phase5_configuration_report.md` | v1.0.2 | **THIS DOCUMENT** |
| `research/r8_phase5_followup_001_spec.md` | v0.1.0 | SPEC SKELETON — owned by Phase 6 SPEC |

**Downstream authorisation:**
Phase 6 deployment evaluation SPEC is authorised by this verdict.
Phase 6 SPEC must explicitly address: ARM_B as the sole baseline,
ARM_C reclassification to CAPACITY_DEMONSTRATED / SHARPE_UNRESOLVED,
the price-snapshot refresh, capital occupancy as the primary research
target, P5-FOLLOWUP-001 ownership (resolve or formally defer), and the
forward lineage-gate override governance requirement (§9.4 item 5).

**What Phase 5 does not establish:**
- That ARM_B produces superior OOS returns.
- That CONFIGURATION_SELECTED authorises paper-trading modification.
- That Phase 5 findings will persist on future adj-price snapshots.
- That ARM_C is a deployable configuration. (ARM_C is reclassified to
  CAPACITY_DEMONSTRATED / SHARPE_UNRESOLVED and is not a Phase 6
  candidate.)
- That RS-60d ranking and 10td holding are sub-additive in interaction.
  (Working Hypothesis P5-4 is suggestive but not identified; see
  P5-FOLLOWUP-001.)
- That the +0.120 full-sample Sharpe shift in §3.4 was independently
  attributed to the adj-price refresh. (Attribution is plausibility-
  based; see §8.6.)
- That Track C findings are authorised for production without SPEC.

---

*End of r8_phase5_configuration_report.md v1.0.2*
