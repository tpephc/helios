# Track C Step 2 — R1 Pre-Registration: `ud_ratio_21d`

**Feature:** `ud_ratio_21d`
**Track:** C
**Step:** 2 / R1 Correlation Analysis
**Status:** DRAFT — NOT LOCKED
**Date:** 2026-06-23
**Spec:** `docs/features/ud_ratio_21d_spec.md` v0.1.4
**Prior closeout:** `research/track_c_step1_closeout.md`

This document pre-registers the R1 correlation analysis before any
correlation numbers are computed, inspected, logged, or interpreted.

No R1 empirical results are included in this document.

---

## 1. Objective

R1 tests whether `ud_ratio_21d` is materially distinct from existing
momentum / persistence proxies used or referenced in Helios:

* `RS_60d`
* `ROC_20d`
* `win_rate_21d`

R1 is a feature orthogonality / redundancy screen. It does not
establish alpha. Its purpose is to detect proxy-collapse risk before
further Track C escalation.

---

## 2. Governance Boundary

R1 does NOT:

* test forward returns
* estimate portfolio Sharpe
* evaluate execution viability
* tune thresholds for alpha selection
* modify `ud_ratio_21d` implementation
* amend spec v0.1.4
* unlock Step 3

---

## 3. R1-U1 Universe Contract

Primary universe:

```text
R8 treatment_1 signal-date panel only
```

Rationale: `ud_ratio_21d` is being evaluated for use inside the R8
Track C research path. Correlation on the full listed universe could
be dominated by universe composition rather than feature semantics in
the actual consumption context.

Rejected alternatives (may only be revisited in a separately
pre-registered robustness study, not inside R1 primary analysis):

```text
(a) listed_market_daily_price_adj full universe after min_obs filtering
(b) R8 treatment_1 ∪ control universe
```

---

## 4. R1-U2 Observation Date Contract

Primary observation dates:

```text
R8 signal dates only
```

Robustness check:

```text
Year-stratified report for 2022, 2023, 2024, 2025
```

Non-signal trading days are excluded from primary R1.

---

## 5. R1-U3 Missing-Value Policy

Upstream contract (from spec v0.1.4):

```text
n_obs_21d < min_obs  ->  ud_ratio_21d is null by construction
```

R1 pairwise exclusion rules:

```text
any of {ud_ratio_21d, RS_60d, ROC_20d, win_rate_21d} null
    -> exclude the (stock, date) observation from that pair only
```

Forbidden:

```text
imputation
forward-fill
backfill
zero-fill
cross-sectional median fill
```

---

## 6. R1-U4 Statistic Contract

Primary statistic:

```text
Per-day cross-sectional Spearman rho
```

Forbidden substitutions:

```text
Pearson correlation
pooled panel correlation
time-series correlation
rank IC against forward returns
```

Feature pairs:

```text
rho(ud_ratio_21d, RS_60d)
rho(ud_ratio_21d, ROC_20d)
rho(ud_ratio_21d, win_rate_21d)
```

For each pair, report:

```text
median
Q25
Q75
P05
P95
min
max
n_dates                  (count of dates passing R1-U4a)
n_pairs_total            (sum of per-date pair counts)
median_pairs_per_day
min_pairs_per_day
```

Do not report mean correlation in the primary table.

---

## 6a. R1-U4a Cross-Section Adequacy Contract

A signal date participates in R1 summary statistics only if:

```text
n_pairs_day >= N_MIN_CROSS_SECTION
```

Constant:

```text
N_MIN_CROSS_SECTION = TBD before lock
Recommended range:    20 <= N <= 30
Current working value (NOT LOCKED): 20
```

Dates failing this threshold are excluded from the primary summary
and reported separately in the coverage table as
`n_dates_below_min_cross_section`.

This constant must be locked independently of, and prior to, the
escalation threshold in R1-U6. It must not be tuned after observing
the coverage distribution.

---

## 7. R1-U5 Regime Conditioning Contract

Allowed conditioning variables (must come from the existing R8
regime layer):

```text
nlu state: 0 / 1 / 2
bull / bear classification
```

Reporting structure:

```text
Primary report:    marginal conditioning
                     - nlu state (3 cells: 0/1/2)
                     - bull/bear (2 cells)

Secondary report:  joint conditioning (2 x 3 = 6 cells)
                     - report only cells with
                       n_dates >= N_MIN_REGIME_DATES
                     - cells failing this threshold are labeled
                       INSUFFICIENT and rho is not reported
```

Constant:

```text
N_MIN_REGIME_DATES = TBD before lock
Recommended:         30
Current working value (NOT LOCKED): 30
```

Forbidden post-hoc conditioning variables:

```text
market cap bucket
liquidity bucket
sector
volatility bucket
year-month
event density
drawdown regime
```

If additional conditioning appears necessary after R1, R1 must be
closed as insufficient and a new R2 pre-registration must be written.

---

## 8. R1-U6 Escalation Threshold Contract

The escalation threshold remains deliberately unlocked at this stage.

Sequencing rule:

```text
1. Generate distribution-shape diagnostics.
2. Lock escalation threshold AND decision-state boundaries before
   examining pass/fail classification.
3. Apply threshold once locked.
```

At threshold-lock stage, the following must be jointly defined:

```text
PASS    boundary
FAIL    boundary
INCONCLUSIVE  band (if any) — including delta and joint-regime
              consistency rule
```

The threshold and decision-state boundaries must be committed to git
before any statement such as "proxy collapse", "orthogonal enough",
or "escalate to Step 3" is made.

---

## 9. R1-U7 Proxy-Collapse Comparison Contract

This contract is split into eligibility, anchors, and statistic.

### 9.1 R1-U7A — Comparison-set Eligibility Rule

A prior Track-C study may be used as a comparison anchor only if all
of the following hold:

```text
1. reached a formal governance decision (PASS / FAIL / closed phase)
2. contains archived correlation evidence (per-day Spearman rho or
   a statistic from which it can be reconstructed)
3. used cross-sectional statistics (not pooled, not time-series)
4. evidence is reproducible from a git commit (commit SHA on record)
5. anchor case must originate from a research lineage independent of
   Track-C / ud_ratio_21d. Track-C own sub-steps (including but not
   limited to Step 1 closeout) are not U7B-eligible.
```

Studies failing any of these criteria are ineligible regardless of
narrative relevance.

**Rationale for criterion (5):** U7B is designed for cross-lineage
validation. Permitting same-lineage self-anchoring would defeat the
purpose. Same-lineage self-anchoring is analogous to the §15
prohibited-actions discipline against fabricating an orthogonal
anchor (§9.2 trailing paragraph): both substitute the independence
requirement with a self-referential construct.

**Operational enforcement:** see
`docs/research/ud_ratio_21d_r1_u7b_enumeration_boundary.md` §1.

**Amendment record:** criterion (5) amended 2026-06-23, BEFORE
R1-U7B enumeration begins. This is a pre-enumeration eligibility
clarification, not a post-result modification.

### 9.2 R1-U7B — Selected Historical Anchors

```text
Eligible anchors (filled before lock):

  Collapse anchor:
    Study:                TBD
    Phase / commit:       TBD
    Pair:                 TBD
    Median per-day rho:   TBD

  Orthogonal anchor:
    Study:                TBD
    Phase / commit:       TBD
    Pair:                 TBD
    Median per-day rho:   TBD
```

If no eligible orthogonal anchor exists in historical record, this
section must explicitly state:

```text
No prior confirmed-orthogonal Track-C case meets R1-U7A eligibility.
Comparison is single-anchor (collapse only).
Interpretation: distance from collapse anchor is descriptive only,
                not classificatory. Decision rests on R1-U6 absolute
                threshold, not on relative position.
```

Single-anchor framing is acceptable; fabricating an orthogonal
anchor to achieve two-sided comparison is not.

### 9.3 R1-U7C — Comparison Statistic

Primary comparison statistic:

```text
median per-day cross-sectional Spearman rho
(must equal R1-U4 primary statistic)
```

Secondary comparison statistics (reported, not decision-driving):

```text
Q75 per-day Spearman rho
P95 per-day Spearman rho
```

Comparison interpretation rule (locked before R1 run):

```text
Two-anchor case (if R1-U7B has both anchors):
  D_collapse = | median_rho_observed - median_rho_collapse_anchor |
  D_ortho    = | median_rho_observed - median_rho_orthogonal_anchor |
  IF D_ortho < D_collapse:  directional indicator -> orthogonality
  IF D_collapse < D_ortho:  directional indicator -> proxy collapse
  (this is directional only; binding decision still rests on R1-U6)

Single-anchor case:
  distance from collapse anchor is reported but is not classificatory.
```

Forbidden:

```text
selecting the most similar prior case after observing R1 results
changing comparison statistic after observing R1 results
using narrative similarity without a pre-specified summary statistic
```

---

## 10. Output Contract

R1 output must include:

```text
sample coverage table             (per R1-U4a, R1-U5)
missing-value summary
primary correlation summary table (unconditioned, all signal dates
                                    passing R1-U4a)
year-stratified robustness table
regime-conditioned table          (marginal + joint per R1-U5)
proxy-collapse comparison table   (per R1-U7)
threshold-lock addendum           (committed separately per R1-U6)
decision log
run manifest                      (per §13)
```

R1 output must not include:

```text
forward return analysis
portfolio simulation
alpha claim
Sharpe ratio
execution recommendation
```

---

## 11. Decision States

Allowed R1 outcomes:

```text
R1-PASS-ORTHOGONALITY-SUFFICIENT
R1-FAIL-PROXY-COLLAPSE
R1-INCONCLUSIVE-REQUIRES-R2
```

Boundary definitions between these states are deferred to the
threshold-lock event (R1-U6). No other decision label is allowed
without amending this document before results are inspected.

---

## 12. Result Inspection Order

The following sequence is binding. Each step must be completed and
its output committed before the next step begins:

```text
1. sample coverage table          (n_dates, pairs_per_day distribution)
2. missing-value summary
3. unconditioned primary table
4. year-stratified table
5. regime-conditioned table (marginal, then joint)
6. proxy-collapse comparison
7. threshold + decision-state boundary lock (per R1-U6)
8. decision
```

Skipping forward (e.g. from step 3 to step 6 because step 3 looked
unexpected) is forbidden. If step 3 surfaces a serious anomaly
(e.g. coverage collapse, all-null pairs), R1 must be paused and the
anomaly resolved via a separate commit before continuing — not by
jumping ahead in the sequence.

---

## 13. Reproducibility Manifest

Every R1 run must emit:

```text
research/ud_ratio_21d/r1_run_manifest.json
```

containing at minimum:

```text
commit_sha
snapshot_id
feature_spec_version
duckdb_version
polars_version
n_dates
n_pairs_total
panel_hash               (hash of input feature panel)
output_hash              (hash of primary summary table)
random_seed              (if any randomization is used; null otherwise)
run_timestamp_utc
```

---

## 14. R1 Outcome Routing

```text
If R1 = PASS-ORTHOGONALITY-SUFFICIENT:
  - unlock Step 3 pre-registration (forward return analysis)
  - Step 3 execution is NOT automatically triggered

If R1 = FAIL-PROXY-COLLAPSE:
  - ud_ratio_21d implementation retained in features/ud_ratio.py
  - marked NOT_FOR_R8_TRACK_C_USE in spec amendment
  - re-evaluation in other Tracks / universes permitted with
    separate pre-registration

If R1 = INCONCLUSIVE-REQUIRES-R2:
  - R2 pre-registration must be drafted within 30 working days
  - if not drafted within that window, ud_ratio_21d defaults to
    NOT_FOR_R8_TRACK_C_USE status (avoids indefinite suspension,
    per RP-01 discipline)
```

---

## 15. Prohibited Actions

During R1, do not:

```text
change universe after seeing correlation results
switch from median to mean after seeing tails
add conditioning variables post-hoc
pool all dates to increase apparent sample size
inspect forward returns
interpret correlation as alpha evidence
weaken missing-value rules
modify ud_ratio_21d implementation
adjust N_MIN_CROSS_SECTION or N_MIN_REGIME_DATES after coverage
  inspection
jump forward in the §12 inspection sequence
```

---

## 16. Lock Checklist

Before first Spearman query:

```text
[X] R1-U1 locked
[X] R1-U2 locked
[X] R1-U3 locked
[X] R1-U4 locked
[ ] R1-U4a N_MIN_CROSS_SECTION filled
[X] R1-U5 marginal + joint structure locked
[ ] R1-U5 N_MIN_REGIME_DATES filled
[X] R1-U6 sequencing accepted (threshold + decision-state boundaries
        deferred to threshold-lock event)
[X] R1-U7A eligibility rule accepted (criteria 1-5, amended 2026-06-23)
[ ] R1-U7B anchors filled (or single-anchor disclosure made)
[X] R1-U7C comparison statistic and interpretation rule locked
[X] §12 inspection order accepted
[X] §13 manifest schema accepted
[X] §14 outcome routing accepted
[ ] document committed to git with message indicating LOCKED status
```

---

## 17. Status

```text
Status: DRAFT — NOT LOCKED
Numbers inspected: NO
Threshold locked: NO
Ready to run R1: NO
```

Outstanding decisions required for LOCK:

```text
N_MIN_CROSS_SECTION       (§6a)  — working value 20, requires audit
N_MIN_REGIME_DATES        (§7)   — working value 30, requires audit
R1-U7B historical anchors (§9.2) — requires U7A eligibility audit
                                    against Track-C history
```

Next governance event:

```text
R1-U7B eligibility audit
  - enumerate candidate historical Track-C studies per
    docs/research/ud_ratio_21d_r1_u7b_enumeration_boundary.md
  - test each against R1-U7A criteria (1)-(5)
  - record eligible anchor pool (may be empty for orthogonal side)
  - if no eligible orthogonal anchor exists, apply single-anchor
    disclosure per §9.2
```

R1 may begin only after this document is reviewed, completed, locked,
and committed.

---

## Amendment Log

```text
2026-06-23  R1-U7A criterion (5) added — lineage independence.
            Pre-enumeration eligibility clarification.
            Status remains DRAFT — NOT LOCKED.
            Cross-reference: ud_ratio_21d_r1_u7b_enumeration_boundary.md
```

---

*End of pre-registration draft.*
