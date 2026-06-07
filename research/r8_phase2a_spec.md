# R8 MA5 Momentum — Phase 2A Stability Validation Specification

<!-- research/r8_phase2a_spec.md -->
<!-- v0.3.0 — 2026-06-07 -->

**Status:** LOCKED — v0.3.0 (2026-06-07)
**Inherits from:** `research/r8_phase1_interim_findings.md` v1.0.0 (CONFIRMED),
`research/r8_phase1_lifecycle_spec.md` v0.2.1 (LOCKED),
`research/phase2_research_roadmap.md` v0.3.0 (LOCKED)
**Authorises:** Phase 2A analysis execution only.
**Does not authorise:** Phase 2B (execution bridge), Phase 2C (signal refinement),
production deployment, alpha validation, or any claim of out-of-sample validity.

**Phase 2A is NOT authorised by Phase 1 confirmation.**
This SPEC must be LOCKED before any analysis execution begins.

---

## Changelog

| Version | Date | Change |
|---|---|---|
| v0.1.0 | 2026-06-07 | Initial SPEC LOCKED. All D1–D7 decisions frozen. |
| v0.2.0 | 2026-06-07 | Added Executive Summary section. Added Data and Panel section (§4). Unified adequacy terminology: LOW_POWER renamed DIRECTIONAL_ONLY throughout. Full Inherits-from chain added to header. No D1–D7 parameters modified. |
| v0.3.0 | 2026-06-07 | Section numbering corrected (subsections aligned to parent section numbers). Author-discretion wording replaced: verdict determined by locked gate framework; analyst may not override gate outcome. Mandatory top-5 collective removal appendix added to §12 Validation Report Structure. No D1–D7 parameters modified. |

---

## 1. Executive Summary

Phase 1 established a confirmed in-sample finding:

> In bull regimes, R8 events within RS_T3 are followed by statistically robust
> incremental forward returns at 10td and 20td horizons (Δ ≈ +1.35% / +2.10%).

Phase 2A evaluates **temporal robustness** of this finding within the available
historical sample. It does not claim out-of-sample validity. It tests whether
the effect is stable across sub-periods, rolling windows, and extreme-date
removals, and whether it is concentrated in a small number of segments.

**Core research question (inherited from roadmap):**

> Is the bull-regime R8 uplift stable enough to justify execution modelling?

**Governance principle:**

> PASS ≠ every segment statistically significant
> PASS = effect is not explained by one cluster / one year / one regime pocket

**Gate outcome summary:**

| Outcome | Meaning | Next step |
|---|---|---|
| **STABLE** | G1 + G2 + G3 + G4 pass; G5 reported | Proceed to Phase 2B SPEC |
| **NOT STABLE** | Effect explained by single cluster / year / regime pocket | Terminate per §11.2; no signal refinement |
| **INCONCLUSIVE** | Insufficient ADEQUACY_ELIGIBLE units for evaluation | SPEC amendment required before proceeding |

---

## 2. Research Question

> Is the bull-regime R8 uplift stable enough to justify execution modelling?

**Estimand (inherited from Phase 1):**

```
Δ_A3 = E[fwd_return | R8 ∩ RS_T3 ∩ bull ∩ nlu=0]
      − E[fwd_return | RS_T3 ∩ ¬R8 ∩ bull ∩ nlu=0]
```

Evaluated at 10td and 20td horizons. Forward return formula frozen:
`adj_close[T+h] / adj_open[T+1] - 1`.

**What this SPEC does not address:**

- True out-of-sample validation (requires future, never-seen observations).
- Execution feasibility or cost adjustment (Phase 2B scope).
- Signal refinement or parameter optimisation (Phase 2C scope).

**Terminology constraint:** Methods in this SPEC re-use the same historical
panel as Phase 1, segmented differently. The correct term is **temporal
robustness analysis**. Phase 2A STABLE does not imply OOS validity.

---

## 3. Required Analyses

All four analyses are mandatory. Omitting any analysis is a protocol
violation regardless of findings in the others.

| ID | Analysis | Section |
|---|---|---|
| P2A-1 | Sub-period analysis (bull-support-balanced segments) | §6 |
| P2A-2 | Rolling-window analysis | §7 |
| P2A-3 | Influence diagnostics | §8 |
| P2A-4 | Concentration diagnostic | §9 |

---

## 4. Data and Panel

### 4.1 Data sources

Same panel as Phase 1 clean-panel re-run (commit `4a307e6`):

- `r8_events` — confirmed R8 signal events
- `daily_price_adj` — adjusted close and open prices for forward return computation
- `bullish_features` — RS_T3 proxy and regime classification

### 4.2 Panel version lock

Phase 2A analysis locks the panel at the Phase 1 v0.2.0 state. No updates
to `r8_events` or `daily_price_adj` are permitted during Phase 2A execution
without a SPEC amendment. Any panel change invalidates previously completed
analysis runs and requires re-execution from the affected step.

### 4.3 Filter conditions

All analyses apply the following filters, inherited from Phase 1:

| Filter | Value |
|---|---|
| `regime[T-1]` | `bull` |
| `near_limit_up` | `0` |
| Treatment | `r8_event = True` AND `rs_t3_t_minus_1 = True` |
| Baseline | RS_T3 non-R8 observations on R8 event dates (`r8_event = False` AND `rs_t3_t_minus_1 = True`) |

**Estimand (Phase 1 A-3 definition):**

```
Δ_A3 = E[fwd_return | treatment] − E[fwd_return | baseline]
```

where `fwd_return = adj_close[T+h] / adj_open[T+1] - 1`, evaluated at
h = 10td and 20td (trading days).

Construction C (event-matched, date-anchored) per ADR-R8P1-002. No
deviation from Phase 1 forward return formula is permitted.

---

## 5. Adequacy Classification System

This classification system is applied uniformly across all P2A-1, P2A-2,
and P2A-3 analyses. It replaces binary PASS/FAIL adequacy with a three-tier
system that distinguishes data sparsity from signal failure.

| Class | Criteria | Inference permitted |
|---|---|---|
| **ADEQUACY_ELIGIBLE** | `treatment_dates ≥ 60` AND `n_eff ≥ 20` | Full inferential (block bootstrap) |
| **DIRECTIONAL_ONLY** | `treatment_dates ≥ 60` AND `n_eff < 20` | Directional only; point estimate reported; CI reported with DIRECTIONAL_ONLY label |
| **INSUFFICIENT** | `treatment_dates < 60` | Point estimate reported for transparency; no CI; not included in gate evaluation |

**n_eff estimation method:** Stationary block bootstrap, L=20 (primary),
same method as Phase 1 (ADR-R8P1-001). n_eff is the effective number of
independent date-level observations in the treatment pool.

**Gate evaluation rule:** Only ADEQUACY_ELIGIBLE results participate in G1
and G2 gate evaluation. DIRECTIONAL_ONLY and INSUFFICIENT results are reported
but excluded from PASS/FAIL counts. They are not counted as failures.

**Rationale:** A sparse segment (e.g., a bear-dominant calendar year with
few bull treatment dates) that produces INSUFFICIENT classification is a
structural data property, not evidence of signal instability. Treating
it as a FAIL would conflate regime composition with signal failure, violating
the core principle established in the roadmap.

---

## 6. P2A-1 — Sub-period Analysis

### 6.1 Segment construction

**Method:** Quantile-based bull-support-balanced partition.

1. Pool all bull/nlu=0 treatment dates from the Phase 1 panel.
2. Sort chronologically.
3. Divide into **4 segments** of approximately equal treatment_dates count
   (quantile cut on the sorted date pool).
4. Segment boundaries are date-based (not calendar-year-based).
5. Record calendar-year span and regime transition dates as annotations
   for each segment.

**Expected range:** 3–5 segments. Fixed at 4 by this SPEC.

**Rationale for quantile construction:** Equal treatment_dates per segment
ensures each segment has comparable baseline power for detecting Δ_A3.
Calendar-year cuts would produce asymmetric power across segments due to
regime variation (e.g., 2022 has sparse bull dates).

### 6.2 Estimand per segment

For each segment s:

```
Δ_A3(s) = E[fwd_return | R8 ∩ RS_T3 ∩ bull ∩ nlu=0, date ∈ s]
         − E[fwd_return | RS_T3 ∩ ¬R8 ∩ bull ∩ nlu=0, date ∈ s]
```

Evaluated at 10td and 20td.

### 6.3 Inference method

Full stationary block bootstrap (B=5000, L=20 primary, sensitivity grid
L={5,10,20,40}) for ADEQUACY_ELIGIBLE segments. Same ADR-R8P1-001 method
as Phase 1. CI method: percentile (95%). p-value method: null-shifted
two-tailed. Joint resample applied to treatment and baseline within each
replication.

### 6.4 Reporting requirements

Per segment, report:

- Segment date range (first and last treatment date).
- Calendar-year span annotation.
- treatment_dates count, n_obs (treatment), n_obs (baseline), n_eff (L=20).
- Adequacy classification (ADEQUACY_ELIGIBLE / DIRECTIONAL_ONLY / INSUFFICIENT).
- Δ_A3 point estimate at 10td and 20td.
- 95% CI and p-value (ADEQUACY_ELIGIBLE only).
- Sensitivity grid summary (ADEQUACY_ELIGIBLE only).

Also report a calendar-year descriptive table in an appendix. This table
is informational only and does not participate in gate evaluation.

---

## 7. P2A-2 — Rolling-Window Analysis

### 7.1 Window definition

- **Window length:** 24 calendar months.
- **Step size:** 1 calendar month.
- **Anchor:** Window defined by treatment dates falling within the 24-month
  span ending at each step month.

### 7.2 Window eligibility

| Condition | Classification |
|---|---|
| `treatment_dates < 30` | INSUFFICIENT — excluded from gate evaluation |
| `treatment_dates ≥ 30` AND `n_eff < 20` | DIRECTIONAL_ONLY — reported; not in gate count |
| `treatment_dates ≥ 30` AND `n_eff ≥ 20` | ELIGIBLE — participates in G2 gate |

**Rationale for lower floor (30 vs 60):** Rolling windows by construction
overlap heavily and share treatment dates. A 30-date floor is appropriate
for rolling analysis; the 60-date floor in P2A-1 applies to independent
segments where the full bootstrap inference is the primary output.

### 7.3 Estimand per window

```
Δ_A3(w) = E[fwd_return | R8 ∩ RS_T3 ∩ bull ∩ nlu=0, date ∈ w]
         − E[fwd_return | RS_T3 ∩ ¬R8 ∩ bull ∩ nlu=0, date ∈ w]
```

Evaluated at 20td (primary for G2 gate). 10td reported descriptively.

### 7.4 Reporting requirements

- Time series of rolling Δ_A3 at 10td and 20td with window eligibility
  classification annotated.
- Distribution summary over ELIGIBLE windows: median, IQR, fraction positive.
- Any sustained negative sequence explicitly flagged (see G2 gate definition).
- n_eff per window reported; DIRECTIONAL_ONLY windows labelled in plots and tables.

---

## 8. P2A-3 — Influence Diagnostics

### 8.1 Influential date identification

**Method:** Jackknife contribution — for each treatment date d, compute the
change in pooled Δ_A3 (20td, bull/nlu=0) when d and all same-day treatment
observations are removed.

**Top-N:** **5 dates** (top-5 by absolute contribution magnitude to Δ_A3
at 20td).

### 8.2 Required runs

| Run | Description |
|---|---|
| Baseline | Full Phase 1 panel (replication of Phase 1 Tier 1 result) |
| Remove date 1 | Top-1 influential date and its same-day cluster removed |
| Remove date 2 | Top-2 dates and clusters removed |
| Remove date 3 | Top-3 dates and clusters removed |
| Remove date 4 | Top-4 dates and clusters removed |
| Remove date 5 | Top-5 dates and clusters removed |
| Remove top-5 collectively | All top-5 dates and clusters removed simultaneously |

Each run uses full stationary block bootstrap (B=5000, L=20 primary).

### 8.3 Reporting requirements

For each run, report:

- treatment_dates remaining, n_eff.
- Δ_A3 point estimate at 10td and 20td.
- 95% CI and p-value.
- Δ vs baseline (magnitude change from full-sample result).

Summarise: at what removal level (if any) does the 95% CI lower bound
cross zero? At what level does sign reversal occur (if at all)?

---

## 9. P2A-4 — Concentration Diagnostic

### 9.1 Concentration metrics

Computed over the 4 ADEQUACY_ELIGIBLE or DIRECTIONAL_ONLY segments from P2A-1
(INSUFFICIENT segments excluded from concentration calculation).

**Metric 1:** Top-1 segment contribution share.

```
share_1 = Δ_A3(segment_max) / sum(Δ_A3(s) for s with Δ_A3(s) > 0)
```

**Metric 2:** Top-2 segment contribution share.

```
share_2 = sum of top-2 Δ_A3(s) / sum(Δ_A3(s) for s with Δ_A3(s) > 0)
```

Contribution shares are computed on positive-Δ_A3 segments only to avoid
division by net values that could be near zero or negative.

### 9.2 Disclosure thresholds

| Condition | Classification | Required action |
|---|---|---|
| `share_1 > 60%` | Material concentration | Explicit disclosure in Validation Report; carried forward as Phase 2B assumption |
| `share_2 > 80%` | Material concentration | Same as above |
| Neither | Distributed effect | Report metrics; no special disclosure required |

**G5 is a mandatory diagnostic, not a hard gate.** Material concentration
does not block Phase 2A STABLE. It must be disclosed and incorporated into
Phase 2B capacity and portfolio construction assumptions.

### 9.3 Reporting requirements

- Segment-level Δ_A3 at 20td with contribution share per segment.
- Metric 1 and Metric 2 values.
- Classification (material concentration / distributed).
- If material: narrative statement of which segments drive the aggregate
  effect and what this implies for Phase 2B.

---

## 10. Gate Framework

### 10.1 G1 — Directional stability

**Applies to:** ADEQUACY_ELIGIBLE segments from P2A-1 at 20td.

**Requirements:**

1. A majority of ADEQUACY_ELIGIBLE segments must have Δ_A3 > 0 at 20td.
   Majority = strictly more than half of ADEQUACY_ELIGIBLE segments.

2. No ADEQUACY_ELIGIBLE segment may have `Δ_A3_20td < −2.0%`
   (hard G1 FAIL).

3. Any ADEQUACY_ELIGIBLE segment with `−2.0% ≤ Δ_A3_20td < −1.0%` is
   classified as a **material adverse finding** requiring explicit narrative
   explanation in the Validation Report. It does not automatically fail G1,
   but must be documented and assessed for structural explanation
   (e.g., documented bear-pocket within the segment).

**G1 does not require:** Every segment to be individually statistically
significant. Segment CIs widen when the sample is partitioned; statistical
significance is not the criterion.

**Interpretation principle:**

> PASS = effect is not explained by one cluster, one year, or one regime pocket.
> PASS ≠ independently significant in every slice.

### 10.2 G2 — Rolling persistence

**Applies to:** ELIGIBLE rolling windows from P2A-2 at 20td.

**Requirements:**

1. The median Δ_A3 across ELIGIBLE rolling windows must be positive at 20td.

2. **Sustained negative sequence definition:**
   6 or more consecutive ELIGIBLE rolling windows with `Δ_A3_20td < 0`.

3. **Material sustained negative definition:**
   A sustained negative sequence (as defined above) where the mean
   `Δ_A3_20td` across the streak is `< −0.5%`.

4. A material sustained negative sequence without a documented structural
   explanation (e.g., fully contained within a verified bear regime period)
   is a **hard G2 FAIL**.

5. A sustained negative sequence (streak present, but streak mean ≥ −0.5%)
   requires explicit narrative documentation but does not automatically
   fail G2.

**Rationale for magnitude condition:** Rolling windows are highly overlapping.
A streak of marginally negative windows (e.g., −0.05% to −0.10%) may
reflect estimation noise in a low-Δ environment. The −0.5% streak mean
threshold ensures only economically meaningful negative persistence triggers
a hard FAIL.

### 10.3 G3 — Influence robustness

**Applies to:** P2A-3 runs at 20td (bull/nlu=0).

**Requirements:**

1. After removal of the single largest influential date cluster (top-1
   removal run), the 95% CI lower bound must remain non-negative.
   (CI lower bound crosses zero = soft flag requiring documentation;
   remains negative across the full sensitivity grid = hard G3 FAIL.)

2. Sign reversal (`Δ_A3_20td < 0`) after removal of any single date cluster
   is a **hard G3 FAIL** regardless of CI.

3. Magnitude reduction without sign reversal is acceptable and must be
   quantified (report Δ vs baseline for each run).

### 10.4 G4 — Adequacy integrity

**Requirement:**

INSUFFICIENT and DIRECTIONAL_ONLY results are excluded from gate evaluation counts.
They must be reported in full; they may not be omitted or suppressed.

This gate is satisfied if and only if all INSUFFICIENT and DIRECTIONAL_ONLY
classifications in the Validation Report are disclosed with their point
estimates and adequacy classifications clearly labelled.

G4 is violated if any sub-period or rolling window result is silently
excluded from the report, or if an INSUFFICIENT result is promoted to
a gate-eligible finding.

### 10.5 G5 — Concentration diagnostic (mandatory, not a hard gate)

See §7. G5 is satisfied when the concentration metrics are computed,
disclosed, and — if material — explicitly carried forward into Phase 2B
assumptions. G5 cannot fail; it can only be omitted (which constitutes a
protocol violation).

---

## 11. Verdict Definition

| Verdict | Condition |
|---|---|
| **STABLE** | G1 + G2 + G3 + G4 satisfy all requirements above. G5 reported. No hard FAIL triggered. |
| **NOT STABLE** | Any hard FAIL: G1 (segment Δ_20td < −2.0%); G2 (material sustained negative without structural explanation); G3 (sign reversal after single cluster removal). |
| **INCONCLUSIVE** | No hard FAIL, but insufficient ADEQUACY_ELIGIBLE segments (fewer than 2) to evaluate G1; or G1/G2 borderline requiring SPEC amendment. |

**Verdict is determined by the locked gate framework above, not by author
discretion.** The analyst is responsible for:

- Documenting all evidence per §12 report structure.
- Classifying adequacy per §5 rules.
- Providing structural explanations for any flagged findings.

The analyst may not override a gate outcome. If a gate outcome is disputed,
a SPEC amendment is required before the Validation Report is issued.

**Phase 1 CONFIRMED status is unaffected by any Phase 2A verdict.**

---

## 12. Validation Report Structure

The Phase 2A Validation Report (target: `research/r8_phase2a_validation_report.md`
v1.0.0) must contain the following sections:

| Section | Content |
|---|---|
| Executive summary | Verdict (STABLE / NOT STABLE / INCONCLUSIVE) with one-paragraph rationale |
| P2A-1: Sub-period results | 4-segment table with adequacy classification, Δ_A3, CI (ELIGIBLE only) |
| P2A-1: Calendar-year appendix | Descriptive calendar-year table; labelled as non-gate |
| P2A-2: Rolling-window results | Time series plot + distribution summary; ELIGIBLE / DIRECTIONAL_ONLY annotated |
| P2A-3: Influence diagnostics | Per-run table; CI lower bound trajectory across individual top-1 to top-5 removals |
| P2A-3: Collective removal appendix | Top-5 collectively removed result: Δ_A3, CI, magnitude change from baseline. Mandatory; not a gate input. Purpose: stress-test visibility for Phase 2B readers. |
| P2A-4: Concentration diagnostic | Contribution share table; concentration classification; Phase 2B implications if material |
| Gate evaluation | Per-gate (G1–G5): requirement, evidence, outcome |
| Verdict | Final STABLE / NOT STABLE / INCONCLUSIVE with full rationale |
| Residual limitations | Honest disclosure of what Phase 2A does and does not establish |
| Phase 2B assumptions | Derived from G5 and any G1/G2 material adverse findings |

---

## 13. Artifact Contract

| Artifact | Path | Description |
|---|---|---|
| Segment panel | `data/_storage/r8_phase2a/v0.1.0/segments/` | 4-segment treatment/baseline panels |
| Rolling window results | `data/_storage/r8_phase2a/v0.1.0/rolling/` | Per-window Δ_A3 time series |
| Influence diagnostic results | `data/_storage/r8_phase2a/v0.1.0/influence/` | Per-removal-run bootstrap outputs |
| Concentration diagnostic | `data/_storage/r8_phase2a/v0.1.0/concentration/` | Segment contribution table |
| Validation Report | `research/r8_phase2a_validation_report.md` | Final report (separate document) |

All artifacts must be versioned. Re-runs with different parameters require
a new version directory, not in-place overwrite.

---

## 14. Governance Constraints

### Binding on all Phase 2A work

| Constraint | Source |
|---|---|
| No Phase 2B or 2C work until Validation Report is complete | Roadmap v0.3.0 §2 |
| SPEC terms (D1–D7) may not be modified mid-analysis | This document |
| Any parameter change requires a new versioned SPEC amendment | This document |
| Phase 1 observation/execution boundary remains in force | Phase 1 lifecycle_spec v0.2.1 |
| IF-2 and IF-3B remain P2 non-binding; do not affect Phase 2A | Phase 1 findings v1.0.0 §10 |

### SPEC amendment policy

Mid-analysis discovery that a frozen parameter is unworkable (e.g., fewer
than 2 ADEQUACY_ELIGIBLE segments exist) requires a SPEC amendment before
proceeding. Amendment procedure:

1. Document the specific parameter that cannot be satisfied and why.
2. Propose a modified value with rationale.
3. Issue a new SPEC version (v0.1.1 or higher).
4. Do not retroactively apply the amended parameter to already-completed
   analysis runs; re-run from the affected step.

### Pre-analysis requirement

BACKLOG-IF1-GUARD (no repo-wide guard on `daily_price_adj` access outside
allowlist) is **strongly recommended** to be resolved before Phase 2A
execution begins. It is not a binding blocker, but its absence creates
a reproducibility risk for the forward return computation that Phase 2A
inherits from Phase 1.

---

## 15. What Phase 2A Does Not Establish

Regardless of verdict:

- That R8 is exploitable net of execution costs.
- That the finding is valid on future (never-seen) data.
- That the uplift is stable under a different strategy parameterisation.
- That Phase 2B is authorised without a Phase 2B SPEC.
- That a NOT STABLE verdict justifies parameter tuning to achieve STABLE.

---

*End of r8_phase2a_spec.md v0.3.0*
