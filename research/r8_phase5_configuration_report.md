# R8 MA5 Momentum — Phase 5 Configuration Selection Report

<!-- research/r8_phase5_configuration_report.md -->
<!-- v1.0.1 — 2026-06-08 -->

**Status:** LOCKED — v1.0.1 (2026-06-08)

**Changelog:**

| Version | Date | Change |
|---|---|---|
| v1.0.0 | 2026-06-08 | Initial report draft |
| v1.0.1 | 2026-06-08 | P5-RPT-001: §6.2 Arm C gate result labelled MARGINAL PASS with explicit margin language. P5-RPT-002: §3.4 expanded with full price-snapshot divergence table (694/1013 dates, nav_end 6.477→6.975, Sharpe 2.378→2.498). P5-RPT-003+006: §7 Finding P5-4 H1/H2 interpretation section added — failure ≠ Arm C fail; capacity and Sharpe are separate dimensions. P5-RPT-004: §1 Executive Summary Primary/Secondary candidate distinction made explicit. P5-RPT-005: §9.3 Phase 6 research hypothesis reframed around "reduce capital occupancy without truncating alpha harvesting period" — not further ranking refinement. |
**Verdict:** CONFIGURATION_SELECTED
**Selected Arms:** ARM_B (20td + RS-60d), ARM_C (10td + RS-60d)
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

Both ARM_B (20td + RS-60d ranking) and ARM_C (10td + RS-60d ranking)
satisfied all applicable pre-registered gate criteria in the Low-Uplift
stress environment, yielding a verdict of **CONFIGURATION_SELECTED**.

**ARM_B is the recommended deployment baseline for Phase 6.** It
demonstrated a substantial improvement in Low-Uplift Sharpe (+0.635 vs
Arm A) and a meaningful reduction in maximum drawdown (−3.23pp), with
no loss of admission capacity. The gate margins are wide, and the Phase
4 CANDIDATE designation for RS-60d ranking is fully confirmed.

**ARM_C satisfied all three gates, including the admission improvement
gate (P5-G3, +14.83pp), but only marginally satisfied the Sharpe gate
(P5-G1, Δ = −0.093 against a threshold of −0.10, margin = +0.007).**
Its SELECTED status should be interpreted with caution: under the locked
Phase 3 price snapshot, Arm C's P5-G1 Δ would be −0.137, which would
not pass. Arm C demonstrates that 10td holding substantially increases
capital capacity (17.5% → 32.4%), but this gain comes at a measurable
Sharpe cost.

Four findings emerged from the Phase 5 analysis:

- **P5-1:** RS-60d ranking is confirmed as a robust improvement in the
  Low-Uplift environment.
- **P5-2:** 10td holding period materially increases capital utilisation.
- **P5-3:** The capacity gain from shorter holding is not free; Sharpe
  declines.
- **P5-4:** The benefits of RS-60d ranking and 10td holding are not
  additive when combined. This is the most unexpected finding of Phase 5
  and directly motivates the Phase 6 exit policy research direction.

Phase 5 remains a research track only. Neither ARM_B nor ARM_C selection
authorises modification of the Helios paper-trading exit contract.
Phase 6 requires a new SPEC.

**Primary Candidate: ARM_B (20td + RS-60d).** Wide-margin gate passage,
simultaneous Sharpe improvement and MaxDD reduction, no snapshot
sensitivity. This is the recommended Phase 6 deployment baseline.

**Secondary Candidate: ARM_C (10td + RS-60d).** Marginal P5-G1 passage
(margin = +0.007), snapshot-sensitive, Sharpe below Arm A in absolute
terms. ARM_C establishes the proof of concept that 10td holding can
materially expand capacity (+14.83pp admission); it does not establish
that 10td is the right production parameter. The evidence for ARM_C
is materially weaker than for ARM_B.

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
1.476 despite RS-60d ranking. This is in contrast to Phase 4 Track A
findings, where 10td alone (FIFO baseline) produced Low-Uplift Sharpe
2.114 vs 1.613 for 20td FIFO — a different direction. The interaction
between 10td and RS-60d ranking is discussed in §7 (Finding P5-4).

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

This sensitivity does not invalidate the Phase 5 result — all three
arms were evaluated on a consistent adj-price basis under approved
governance. However, ARM_C's SELECTED status is not robust to
snapshot timing. ARM_C is a secondary candidate. ARM_B remains the
recommended deployment baseline.

### 6.3 Verdict

| Arm | Gates passed | Result |
|---|---|---|
| A | N/A (lineage reference) | — |
| B | P5-G1 ✓, P5-G2 ✓ | **SELECTED** |
| C | P5-G1 ✓ (marginal), P5-G2 ✓, P5-G3 ✓ | **SELECTED (marginal P5-G1)** |

**Layer 1:** CONFIGURATION_SELECTED
**Layer 2:** SELECTED: ARM_B, ARM_C

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

The Sharpe cost is modest in absolute terms but statistically meaningful
given the pre-registered gate margin of 0.007. Phase 6 should treat
Arm C as a proof-of-concept for capacity expansion rather than as a
production-ready parameter choice.

### Finding P5-4: RS-60d ranking and 10td holding are not additive

This is the most unexpected finding of Phase 5 and the most directly
informative for Phase 6 design.

Phase 4 established separately that:
- RS-60d ranking improved Low-Uplift Sharpe from 1.613 to 2.128
  (+0.515) relative to FIFO at 20td.
- 10td holding improved Low-Uplift Sharpe from 1.613 to 2.114
  (+0.501) relative to FIFO at 20td.

The implicit assumption was that combining both improvements might yield
an additive or super-additive result. Phase 5 directly tested this
combination for the first time. The result was sub-additive:

| Configuration | Low-Uplift Sharpe | vs Arm A (FIFO, 20td) |
|---|---|---|
| Arm A: 20td + FIFO | 1.569 | baseline |
| Arm B: 20td + RS-60d | 2.204 | +0.635 |
| Arm C: 10td + RS-60d | 1.476 | −0.093 |

Adding RS-60d ranking at 20td raises Sharpe substantially. Adding 10td
holding *on top of* RS-60d ranking reduces Sharpe below even the FIFO
baseline. This is a non-additive interaction: f(RS-60d) + f(10td) ≠
f(RS-60d + 10td).

**Pre-registered hypotheses for Arm C (from SPEC §9):**
- H1: Sharpe(C, LU) > 1.613 — **NOT SUPPORTED** (observed: 1.476)
- H2: Sharpe(C, LU) ≥ 2.128 — **NOT SUPPORTED** (observed: 1.476)

**Interpretation of H1/H2 failure:**
The failure of H1 and H2 does not invalidate Arm C or its SELECTED
status. Arm C satisfied all three pre-registered gate criteria. H1 and
H2 were pre-registered as documentary hypotheses — expected-value
statements based on Phase 4 separate-component findings — not as gate
criteria. Their function is to characterise the interaction effect.

What H1/H2 failure tells us is specific and valuable: the capacity
improvement observed in Phase 4 for 10td holding did not translate into
superior risk-adjusted performance when combined with RS-60d ranking.
10td holding impairs the alpha extraction that RS-60d ranking enables.
This is the core content of Finding P5-4.

A reader should not interpret H1/H2 NOT SUPPORTED as "Arm C failed".
The correct interpretation is: "Arm C's value is capacity expansion,
not Sharpe improvement. These are separate things."

The practical implication is that capacity expansion and Sharpe
preservation are in tension when achieved via fixed holding-period
reduction. This motivates the Phase 6 research hypothesis: an
**adaptive exit policy** may be able to release capital from
underperforming positions early (recovering capacity) while allowing
strong positions to run toward 20td (preserving alpha), thereby
decoupling capacity from holding period.

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
interaction (Finding P5-4) was not anticipated. This is a normal
consequence of testing combinations rather than components — the finding
is informative rather than invalidating, but it means Phase 6 should
not assume that other combinations of Phase 4 candidates will also be
additive.

### 8.5 Scope constraints

Phase 5 did not evaluate Track C early exit rules, bearish signals,
dynamic slippage modelling, or live execution. All findings are
conditional on the fixed-hold, paper-price NAV reconstruction
methodology used in Phases 3–5.

---

## 9. Phase 6 Implications

### 9.1 Recommended baseline

ARM_B (20td + RS-60d) is the recommended Phase 6 starting point. It
has demonstrated consistent, wide-margin improvement over the FIFO
baseline in the Low-Uplift environment, and its gate margins provide
a stable reference against which Phase 6 exit policy variants can
be compared.

### 9.2 The capital occupancy problem

Phase 5 confirms that capital occupancy is the primary constraint on
R8 capacity. In Low-Uplift, Arm A (the best-historically-tested FIFO
configuration) admits only 17.5% of eligible signals — 82.5% are
rejected due to capital lock-up, not signal quality. Arm B improves
signal selection within this constraint but does not relax it. Arm C
demonstrates that fixed holding-period reduction is one way to relax
it, but at Sharpe cost.

### 9.3 Phase 6 research hypothesis

Phase 4 and Phase 5 findings jointly motivate a specific Phase 6
hypothesis. The right question for Phase 6 is not:

> Can another ranking factor outperform RS-60d?

Phase 5 (Finding P5-1) answers this: RS-60d ranking is confirmed and
becomes the fixed baseline. The signal selection problem is largely
solved within the current architecture.

The right question is:

> Can capital occupancy be reduced without truncating the alpha
> harvesting period?

This is the structural argument for adaptive exit policy research.
ARM_B holds every position for a fixed 20td regardless of how it
performs during the hold. An adaptive exit policy would release capital
from underperforming positions early (recovering occupancy) while
allowing high-quality positions to run toward 20td (preserving alpha).
If this hypothesis holds, Phase 6 could achieve both the +14.83pp
capacity improvement demonstrated by ARM_C and the +0.635 Sharpe
improvement demonstrated by ARM_B — without the Sharpe-capacity
trade-off that ARM_C revealed.

### 9.4 Phase 6 design constraints

The Phase 6 SPEC must address:

1. ARM_B as the frozen baseline (not re-estimated in Phase 6).
2. ARM_C marginal P5-G1 passage — Phase 6 should not treat 10td as
   a validated parameter without fresh evaluation.
3. The price-snapshot refresh: Phase 6 must document its own snapshot
   date and check for further adj-price restatements since Phase 5.
4. Track C (signal characterisation) research proceeds independently
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

Phase 5 achieved its pre-registered research objective. Two
configurations were selected:

**ARM_B (20td + RS-60d):** Robust, wide-margin improvement over the
Phase 3 baseline in the Low-Uplift stress environment. Confirmed as
the Phase 6 deployment baseline. The RS-60d ranking benefit is
consistent across full sample and stress environment, and across
multiple metrics (Sharpe and MaxDD).

**ARM_C (10td + RS-60d):** Marginal Sharpe gate passage (P5-G1 margin
= 0.007) with a robust capacity improvement (admission +14.83pp).
Selected as a secondary candidate, but Arm C's SELECTED status is
sensitive to the adj-price snapshot used for reference, and should not
be treated as equivalent in strength to Arm B. ARM_C establishes the
proof of concept that 10td holding can materially increase capacity;
it does not establish that 10td is the right production parameter.

The most consequential research finding is **P5-4**: RS-60d ranking
and 10td holding are not additive. Their combination produces a
sub-additive outcome — capacity improves but Sharpe regresses below
the FIFO baseline. This directly motivates Phase 6's exit policy
research direction: an adaptive exit policy is hypothesised to achieve
both capacity improvement and Sharpe preservation in a way that fixed
holding-period reduction cannot.

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
| `research/r8_phase5_configuration_report.md` | v1.0.1 | **THIS DOCUMENT** |

**Downstream authorisation:**
Phase 6 deployment evaluation SPEC is authorised by this verdict.
Phase 6 SPEC must explicitly address: ARM_B as baseline, ARM_C
marginal passage note, price-snapshot refresh, and capital occupancy
as the primary research target.

**What Phase 5 does not establish:**
- That ARM_B or ARM_C produces superior OOS returns.
- That CONFIGURATION_SELECTED authorises paper-trading modification.
- That Phase 5 findings will persist on future adj-price snapshots.
- That ARM_C is as robust a selection as ARM_B.
- That Track C findings are authorised for production without SPEC.

---

*End of r8_phase5_configuration_report.md v1.0.1*
