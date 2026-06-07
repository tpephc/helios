# R8 MA5 Momentum — Phase 2 Research Roadmap

<!-- research/phase2_research_roadmap.md -->
<!-- v0.3.0 — 2026-06-07 -->

---

**Status:** LOCKED — v0.3.0 (2026-06-07)
**Supersedes:** None
**Inherits from:** `research/r8_phase1_lifecycle_spec.md` v0.2.1 (CONFIRMED),
`research/r8_phase1_interim_findings.md` v1.0.0 (CONFIRMED)

**Phase 2 is NOT authorised by Phase 1 confirmation.**
This roadmap is a planning document only.
Phase 2 implementation requires a new versioned SPEC.

---

## 1. Executive Summary

Phase 1 established a confirmed in-sample finding:

> In bull regimes, R8 events within RS_T3 are followed by statistically robust
> incremental forward returns at 10td and 20td horizons (Δ ≈ +1.35% / +2.10%).

The central unresolved question after Phase 1 is **not** effect size, but
**effect persistence**:

> Is this uplift stable enough to deserve execution modelling?

Phase 2 is therefore structured as a **validation-first roadmap**:

| Phase | Purpose | Governance status |
|---|---|---|
| **2A** | Stability validation (temporal robustness) | Prerequisite for 2B/2C |
| **2B** | Execution bridge | Conditional on 2A STABLE |
| **2C** | Signal refinement | Deferred (conditional on 2A STABLE) |

**Core research question for Phase 2A:**

> Is the bull-regime R8 uplift stable enough to justify execution modelling?

**What Phase 2 is not:**

- An attempt to improve R8 before validation
- An execution simulation on an unvalidated signal
- A pullback-resolution project (requires more data)

---

## 2. Inheritance from Phase 1

### Confirmed findings (Phase 1 v1.0.0)

| Finding | Condition |
|---|---|
| R8 uplift at 10td / 20td | Bull regime, `near_limit_up=0`, RS_T3 universe |
| Δ ≈ +1.35% (10td), +2.10% (20td) | 95% CI strictly positive, robust across bootstrap |
| RS_T3 baseline ≈ +3.03% at 20td | Bull regime, same conditions |
| A-2 pullback sparsity | Treatment_2 = 4.9% of Treatment_1; inferential evaluation impossible |

### Open questions carried forward

| Question | Required next step |
|---|---|
| Sub-period stability of R8 uplift | Phase 2A |
| Influence of clustered dates (e.g., 2024-08-07) | Phase 2A |
| Rolling-window persistence | Phase 2A |
| Effect concentration across periods | Phase 2A (G5 diagnostic) |
| Execution-cost adjusted returns | Phase 2B (conditional) |
| H1/H2 pullback resolution | Deferred — requires more data |
| Sector/stock concentration sensitivity | Deferred — requires IF-2 closure |

---

## 3. Phase 2A — Stability Validation (Temporal Robustness)

### 3.0 Scope clarification

Phase 2A evaluates **temporal robustness** within the available historical
sample (same data as Phase 1, re-segmented).

Methods used:
- Sub-period analysis (bull-support-balanced segments)
- Rolling-window analysis
- Influence diagnostics
- Concentration diagnostic

These methods test whether the Phase 1 finding is robust to temporal
segmentation and extreme-date influence.

**What Phase 2A does NOT do:**

- True out-of-sample validation (requires future, never-seen observations)
- Walk-forward or expanding-window with a held-out test set

**Terminology note:** All Phase 2A methods re-use the same historical panel
as Phase 1, segmented differently. The correct term is **temporal robustness
analysis**, not out-of-sample validation. These are not equivalent. Phase 2A
STABLE does not imply OOS validity; it implies that the Phase 1 finding is
not explained by a single cluster, single year, or single regime pocket
within the existing sample. A future-data test remains outside scope.

### 3.1 Research questions

| ID | Question | Method |
|---|---|---|
| P2A-1 | Is Δ_A3 directionally consistent across bull-support-balanced sub-periods? | Sub-period analysis (see Section 3.2) |
| P2A-2 | Does Δ_A3 persist over rolling windows, or is it concentrated in a short interval? | Rolling-window analysis (see Section 3.3) |
| P2A-3 | Does the Tier 1 finding survive removal of the largest influential date clusters? | Influence diagnostics (see Section 3.4) |
| P2A-4 | Is the uplift broadly distributed across segments, or concentrated in a small number? | Concentration diagnostic (see Section 3.5) |

All four must be evaluated. Omitting any question is a protocol violation
regardless of findings in the others.

### 3.2 Sub-period analysis (P2A-1)

**Estimand:** Δ_A3 | regime[T-1] = bull, near_limit_up = 0, sub-period s

**Sub-period construction policy:**

Sub-periods are constructed as bull-support-balanced segments, not calendar
years. Calendar-year tables are reported descriptively but do not constitute
the primary gate evidence.

Rationale: The Phase 2A estimand conditions on bull regime. A calendar year
with sparse bull-date support (e.g., 2022) produces small effective-n in
the bull cell. Treating such a year as a normal sub-period would conflate
regime composition with signal instability — a "no signal found" result
in a year with few bull dates is not evidence of instability.

**Construction requirements (to be frozen in Phase 2A SPEC):**

1. Partition the full sample date range into 3–5 segments.
2. Each segment must satisfy minimum bull treatment_dates and effective-n
   thresholds (thresholds frozen in Phase 2A SPEC before execution).
3. Segments failing the minimum threshold are classified
   DIRECTIONAL_ONLY or INSUFFICIENT, not FAIL.
4. Calendar-year boundaries and regime transition dates are recorded as
   annotations alongside segment results.

**Inference mode:**

Full inferential (block bootstrap, same ADR-R8P1-001 method) for PASS
segments. DIRECTIONAL_ONLY for segments below threshold.

### 3.3 Rolling-window analysis (P2A-2)

**Method:** Compute rolling Δ_A3 over a fixed window (candidate: 24 months
of bull treatment dates; exact window locked in Phase 2A SPEC).

**Reporting requirements:**

- Time series of rolling Δ_A3 at 10td and 20td horizons.
- Distribution summary (median, IQR, fraction of windows positive).
- Flag any sustained negative window explicitly; do not suppress.
- Report effective-n per rolling window; windows below threshold are
  classified DIRECTIONAL_ONLY.

**Purpose:** Detect whether the full-sample finding is driven by a short
burst of positive windows (cluster-driven) or reflects a persistent positive
tendency across the observation period.

### 3.4 Influence diagnostics (P2A-3)

**Background:** Phase 1 identified same-day clustering up to 77 simultaneous
signals on 2024-08-07. The block bootstrap accounts for temporal clustering,
but does not directly test whether a small number of influential dates drive
the point estimate.

**Method:**

1. Identify the top-N influential treatment dates by contribution to Δ_A3
   at 10td and 20td (N to be locked in Phase 2A SPEC; candidate N = 5–10).
2. Re-run Δ_A3 bootstrap with each influential date (and its cluster) removed.
3. Report: Does the 10td / 20td bull finding survive removal of the largest
   cluster? Does it survive removal of the top-N?

**Pass condition:** The Tier 1 finding direction is not erased by removal of
any single influential date cluster. Magnitude reduction is acceptable and
must be quantified. Sign reversal is a hard FAIL regardless of CI.

### 3.5 Concentration diagnostic (P2A-4)

**Purpose:** Detect whether the full-sample uplift is economically
concentrated in a small number of segments, even if directionally consistent.

**Motivation:** A pattern such as:

```
Segment A: Δ_A3 = +9%
Segment B: Δ_A3 = +7%
Segment C: Δ_A3 = −1%
Segment D: Δ_A3 = −2%
```

could pass G1 (mostly positive) and G2 (positive central tendency) while
the deployable effect is actually concentrated in two early segments. This
matters directly for capacity, portfolio construction, and regime-dependency
of Phase 2B conclusions.

**Method (to be frozen in Phase 2A SPEC):**

1. Compute each segment's contribution to the pooled Δ_A3 estimate
   (candidate: fraction of total effect attributable to top-k segments).
2. Report a concentration metric (candidate: top-segment contribution share,
   or Gini coefficient across segment Δ_A3 values).
3. Flag any case where the top-1 or top-2 segments account for a
   disproportionate fraction of the aggregate uplift (threshold in SPEC).

**Governance:** G5 is a mandatory diagnostic. It is reported in the Phase 2A
Validation Report regardless of other gate outcomes. Concentration findings
inform Phase 2B capacity and portfolio construction scope; they do not
independently block Phase 2A STABLE, but material concentration must be
explicitly disclosed and carried forward as a Phase 2B assumption.

### 3.6 Phase 2A Deliverable

**Validation Report** (v1.0.0) containing:

| Section | Content |
|---|---|
| Sub-period results | Bull-support-balanced segments + calendar-year appendix |
| Rolling-window analysis | Rolling Δ_A3 (10td / 20td) with central tendency summary |
| Influence diagnostics | Removal of largest date clusters; magnitude impact quantified |
| Concentration diagnostic (G5) | Segment contribution distribution; concentration metric |
| Adequacy classification | DIRECTIONAL_ONLY / INSUFFICIENT cells explicitly flagged |
| Verdict | STABLE / NOT STABLE / INCONCLUSIVE with full rationale |

**Governance gate:** Phase 2B and 2C require **STABLE** verdict. If **NOT
STABLE** or **INCONCLUSIVE**, Phase 2 terminates at the Validation Report
per Section 3.7.

### 3.7 Termination policy

A NOT STABLE verdict is a valid research outcome. It does not invalidate
Phase 1; it means the effect is not stable enough to justify execution
modelling investment at this time.

**Permitted actions after NOT STABLE:**

- Archive the Validation Report with full documentation of failure mode.
- Reassess research direction (e.g., return to discovery phase with a
  different signal hypothesis).
- Extend the time series and re-evaluate when more data is available.

**Prohibited actions after NOT STABLE:**

- Signal refinement or parameter optimisation targeting a better stability
  result. NOT STABLE is not a mandate to tune the signal until it passes.
- Moving to Phase 2B regardless of verdict.
- Treating Phase 2A failure as evidence that a different R8 parameterisation
  would pass, without a new pre-registered research question.

---

## 4. Phase 2A Gate Framework

Gate architecture is locked in this roadmap. Numeric thresholds are deferred
to Phase 2A SPEC and must be frozen before execution begins.

### G1 — Directional stability

Δ_A3 at 10td and 20td (bull/nlu=0) must show directional consistency across
bull-support-balanced segments, with no economically material negative uplift
in any segment.

**What G1 requires:**

- A majority of adequacy-eligible segments must show positive Δ_A3 at 10td
  and 20td. Exact majority definition frozen in Phase 2A SPEC.
- No single segment may be the sole basis for the promoted conclusion.
- No adequacy-eligible segment may show a large negative Δ_A3 that would
  reverse the overall interpretation if that segment were the full sample.
  (Threshold for "economically material negative" frozen in Phase 2A SPEC.)

**What G1 does not require:**

- Every segment is individually statistically significant. Segment CIs widen
  when sample is partitioned. Statistical significance is not the criterion.
- Every segment is positive. A near-zero or marginally negative segment
  does not fail G1 if the overall pattern is directionally consistent and
  no segment reversal is economically material.

**Segments classified DIRECTIONAL_ONLY or INSUFFICIENT are excluded from the
PASS/FAIL count.** They are not counted as failures.

**Interpretation principle:**

> PASS = effect is not explained by one cluster, one year, or one regime pocket.
> PASS ≠ independently significant in every slice.

### G2 — Rolling persistence

The rolling-window Δ_A3 distribution must have positive central tendency.

- Central tendency measure (median or trimmed mean) frozen in Phase 2A SPEC.
- Any sustained negative window must be explicitly documented and assessed
  for regime explanation. Definition of "sustained" frozen in Phase 2A SPEC.
- A sustained negative window fully explained by a documented bear regime
  period does not automatically fail G2, but requires narrative justification
  in the Validation Report.

### G3 — Influence robustness

The Tier 1 finding (bull/nlu=0, 10td and 20td) must not be erased by removal
of the largest influential date cluster.

- "Erased" means the 95% CI lower bound crosses zero after removal.
- Sign reversal (Δ_A3 becoming negative) is a hard FAIL regardless of CI.
- Magnitude reduction without sign reversal is acceptable and must be
  quantified in the report.

### G4 — Adequacy integrity

Sub-period and rolling results below pre-locked date/effective-n thresholds
are classified DIRECTIONAL_ONLY or INSUFFICIENT, not FAIL.

- This prevents the gate from penalising structurally data-sparse periods
  as signal failures.
- DIRECTIONAL_ONLY and INSUFFICIENT cells must be reported; they may not be
  omitted to improve the apparent pass rate.

### G5 — Concentration diagnostic (mandatory, not a hard gate)

The concentration of Δ_A3 across segments must be assessed and disclosed.

- Report the fraction of the aggregate uplift attributable to the top-1 and
  top-2 segments.
- Report the chosen concentration metric (e.g., Gini or top-k share).
- G5 does not independently block Phase 2A STABLE, but material concentration
  findings must be explicitly carried forward as assumptions in Phase 2B.

### Gate outcome states

| Outcome | Definition | Next step |
|---|---|---|
| **STABLE** | G1 + G2 + G3 + G4 pass architectural requirements (numeric thresholds per Phase 2A SPEC). G5 reported as diagnostic. | Proceed to Phase 2B SPEC. |
| **NOT STABLE** | Core effect is explained by a single cluster / single year / single regime pocket; or G3 hard FAIL (sign reversal). | Terminate per Section 3.7. |
| **INCONCLUSIVE** | Insufficient sample support to determine stability; no hard FAIL criteria triggered. | Phase 2A SPEC amendment required; do not proceed to 2B. |

**FAIL vs NOT STABLE terminology note:** Gate outcomes use STABLE / NOT
STABLE / INCONCLUSIVE rather than PASS / FAIL to avoid conflating research
validation with production certification. NOT STABLE does not mean Phase 1
is wrong; it means the stability question cannot be resolved affirmatively
at this time.

**Phase 1 status is unaffected by any Phase 2A outcome.** Phase 1 findings
are confirmed measurement-scope results; Phase 2A is a separate stability
assessment.

---

## 5. Phase 2B — Execution Bridge (Conditional on 2A STABLE)

**Prerequisite:** Phase 2A STABLE verdict.

**Scope (indicative — full scope locked in Phase 2B SPEC):**

- T+1 open slippage model for Taiwan equity market.
- Commission and transaction cost structure (TWSE standard).
- Gap risk at entry (limit-up open scenarios).
- Portfolio crowding and signal overlap: same-day R8 clustering (up to 70+
  simultaneous signals observed in Phase 1) requires explicit analysis of
  how many positions can be deployed concurrently without self-defeating
  capacity effects. This is not merely an overlap check; it is a central
  execution feasibility question given the known clustering structure.
- Capacity estimate: position count before market impact is non-negligible.
- Portfolio-level PnL under realistic position sizing.
- Integration with G5 concentration findings: if Phase 2A reveals that
  the uplift is concentrated in specific market conditions, Phase 2B must
  reflect that in its scenario assumptions.

**Deliverable:** Execution Feasibility Memo containing:

- Net PnL estimate (vs. gross from Phase 1).
- Sensitivity analysis across slippage assumptions.
- Capacity constraints including cluster-day crowding analysis.
- Verdict: **TRADEABLE** / **NOT TRADEABLE** / **CONDITIONAL**.

Output is a range, not a point estimate, to reflect execution uncertainty.

---

## 6. Phase 2C — Signal Refinement (Deferred)

**Prerequisite:** Phase 2B TRADEABLE or CONDITIONAL verdict.

**Not planned for Phase 2 unless Phase 2A STABLE and Phase 2B warrant further
signal investment.**

Potential directions (if pursued):

| Direction | Challenge |
|---|---|
| Pullback (H1 vs H2) | Treatment_2 = 262 events; 38 max bull dates; requires 1–2+ years additional data |
| MA5 observational patterns | Phase 1 recorded descriptive metrics only; execution use requires new SPEC |
| Sector concentration | Requires IF-2 closure |

**Explicitly deferred from Phase 2A and 2B:** No signal refinement work
will be conducted before Phase 2B gate outcome is known.

**Note on H1/H2:** The structural sparsity of Treatment_2 is unlikely to be
resolved by modest sample extension alone. Phase 2C SPEC must reassess
accumulated Treatment_2 date support before committing inferential resources.

---

## 7. What Phase 2 Is Not

The following are explicitly outside Phase 2 scope unless authorised by a
new versioned SPEC:

- Optimisation of R8 parameters (+5% threshold, MA5 lookback).
- Addition of new signal types beyond R8 definition.
- Portfolio construction beyond what is needed for execution bridge.
- Production deployment or live signal generation.
- Any claim of alpha independent of cost structure.
- Phase 2C work prior to Phase 2A and 2B gate completion.
- Treating Phase 2A NOT STABLE as a mandate to tune the signal.

---

## 8. Open Items (P2, not blocking Phase 2A)

| ID | Description | Impact | Recommendation |
|---|---|---|---|
| IF-2 | Empty `stock_info` | Sector validation deferred; does not block stability analysis | Deferred |
| IF-3B | Suspension/halt dataset | Residual uncertainty at T+1–T+20 observation dates; does not materially affect Phase 2A | Deferred |
| BACKLOG-IF1-GUARD | No repo-wide guard on `daily_price_adj` access | Reproducibility risk for forward return computation | **Strongly recommended** before Phase 2A execution begins. Not a binding blocker, but reproducibility risk is material. |

---

## 9. Governance

### Upstream dependencies

| Document | Version | Status |
|---|---|---|
| `research/r8_phase1_interim_findings.md` | v1.0.0 | CONFIRMED |
| `research/r8_phase1_lifecycle_spec.md` | v0.2.1 | LOCKED |

### Downstream authorisations

| Phase | Authorised by | Requires |
|---|---|---|
| Phase 2A analysis | This roadmap | Phase 2A SPEC (to be written) |
| Phase 2B analysis | Phase 2A STABLE verdict | Phase 2B SPEC |
| Phase 2C analysis | Phase 2B TRADEABLE or CONDITIONAL verdict | Phase 2C SPEC |

### Amendment policy

This roadmap may be amended by a new versioned document. Silent edits are
not permitted. Gate architecture changes (G1–G5 class definitions) require
a roadmap version bump. Numeric threshold changes within a gate class are
Phase 2A SPEC scope and do not require a roadmap amendment.

---

## 10. Immediate Next Steps

1. Write `research/r8_phase2a_spec.md` v0.1.0:
   - Freeze sub-period construction method and minimum support thresholds.
   - Freeze rolling window definition (candidate: 24-month bull-date window).
   - Freeze influence diagnostic top-N.
   - Freeze G1–G5 numeric thresholds and G5 concentration metric.
   - Specify artifact paths and output format.

2. Do not begin any Phase 2A analysis before the SPEC is locked.

3. Phase 2B and 2C planning is deferred until Phase 2A gate outcome is known.

4. Resolve BACKLOG-IF1-GUARD before Phase 2A execution begins (strongly
   recommended, not binding).

---

## 11. Version History

| Version | Date | Change |
|---|---|---|
| v0.1.0 | 2026-06-07 | Initial draft |
| v0.2.0 | 2026-06-07 | Added sub-period policy (bull-support-balanced segments). Added gate architecture (roadmap locks classes, SPEC locks thresholds). Clarified STABLE/NOT STABLE/INCONCLUSIVE definitions. |
| v0.2.1 | 2026-06-07 | Added Section 3.0 scope clarification (temporal robustness vs true OOS). Added G5 concentration robustness diagnostic. Strengthened G1 wording. Added Section 3.5 termination policy. Added portfolio crowding/overlap to Phase 2B. Upgraded BACKLOG-IF1-GUARD to strongly recommended. Changed "Target: 3–5 segments" to "Expected range". |
| v0.3.0 | 2026-06-07 | G1 rewritten: "mostly positive" replaced with explicit economically-material-negative-reversal criterion; clarified what G1 does and does not require. G5 promoted to named gate class with full section (3.5); concentration diagnostic motivation example added. Phase 2B portfolio crowding elevated to standalone item with Phase 1 cluster-count context and G5 integration requirement. Section 3.0 OOS terminology hardened: "temporal robustness analysis" distinguished from "OOS validation" with explicit misuse warning. P2A-4 added to research questions table. Amendment policy updated to G1–G5. |

---

*End of phase2_research_roadmap.md v0.3.0*
