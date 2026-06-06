# ADR-R8P1-001 — Block-Bootstrap Effective-n Estimation Method

<!-- research/adr/ADR-R8P1-001-block-bootstrap-effective-n.md -->
<!-- v0.1.0 — 2026-06-06 -->

**Status:** LOCKED — v0.1.0
**Lock date:** 2026-06-06
**Authority:** Implementation ADR mandated by
`research/r8_phase1_lifecycle_spec.md` v0.1.2, Scope §7 and AC-5.
**Scope:** Fixes the block-bootstrap method used to estimate effective
sample size (`n_eff`) and bootstrap inference for all R8 Phase 1
inferential outputs.
**Does not authorise:** Any analysis output. This ADR locks the method;
the first Phase 1 analysis output may only be produced after this ADR
is signed off.

---

## Context

R8 Phase 1 SPEC v0.1.2 requires (AC-5, LA-6, Scope §7) that any
inferential statistic produced under Phase 1 be accompanied by a
block-bootstrap effective-n estimate, with method fixed before the
first Phase 1 output is produced.

The motivating dependence structure is established by Phase 0 and
inherited as LA-6:

- Same-day clustering: up to 77 simultaneous R8 signals on a single
  trading date (2024-08-07).
- Industry concentration: the electronics complex accounts for ~78%
  of R8 signals (inherited fact from Phase 0).
- Forward-return overlap: forward returns at horizon `h = 20` trading
  days share observation windows across temporally adjacent events,
  inducing mechanical autocorrelation up to lag 20.

The raw event count (`n_raw = 8012` in the IF-1-remediated event
panel used by the 2026-06-05 handoff; future re-runs must read
`n_raw` from the event manifest rather than rely on this value)
is therefore not an independent-observation count. Inference
assuming i.i.d. events will systematically understate standard
errors.

This ADR fixes the resampling unit, bootstrap variant, block length,
and reporting format. All choices are locked and may not be silently
changed; any change requires a versioned ADR amendment with explicit
rationale.

---

## Decision

### D1. Resampling unit: date-level

The unit of resampling is the **trading date**. When a date is drawn
into a bootstrap sample, all R8 events occurring on that date are
included as a unit. Event-level resampling is prohibited because it
breaks same-day clustering (LA-6).

### D2. Bootstrap variant: stationary bootstrap

The stationary bootstrap of Politis & Romano (1994) is used. Block
lengths are drawn from a geometric distribution with mean equal to
the parameter `L` defined in D3. Moving block bootstrap (Künsch 1989)
and circular block bootstrap (Politis & Romano 1992) are not used in
the locked method.

### D3. Block length

**Primary expected block length** (used for all primary inference):

    L_primary = 20 trading days

**Sensitivity grid** (reported alongside primary, never as standalone):

    L_grid = {5, 10, 20, 40} trading days

**Hard rule (locked, not a guideline):**

> No inferential statement may rely solely on `L ∈ {5, 10}`. For any
> forward-return horizon `h ≤ 20td`, primary inference must use
> `L_primary = 20`. Block lengths 5 and 10 are reported only as
> sensitivity diagnostics.

This constraint is a direct consequence of D4 and is non-negotiable
within Phase 1.

**Excluded from locked core:** the automatic block-length selector of
Politis & White (2004) with the Patton-Politis-White (2009) correction
is **not** part of the locked method. It may be reported as exploratory
robustness only, and may not be cited as primary inference or as an
acceptance dependency. Rationale: introducing a spectral-density-based
selector adds package/implementation variance and a governance surface
disproportionate to its marginal value in Phase 1.

### D4. Overlap handling

Forward-return windows at horizon `h` create overlap up to lag `h - 1`
trading days. The locked method handles this by requiring:

    L_primary >= max_horizon = 20

so that overlapping observation windows fall within the same bootstrap
block with high probability. This is the structural justification for
`L_primary = 20`; it is not a tuning choice.

Newey-West HAC-adjusted analytical standard errors may be reported as
cross-check, but are not part of the locked acceptance gate.

### D5. Statistics subject to bootstrap

The following statistics, when reported in any Phase 1 output, must
be accompanied by bootstrap inference per this ADR:

| Statistic | Bootstrap required | Resampling discipline |
|---|---|---|
| Per-horizon mean forward return (A-1, A-2, A-3 cells) | Yes | Marginal |
| Median forward return | Yes | Marginal |
| Hit rate `P(return > 0)` | Yes | Marginal |
| Trimmed mean (5%, 10%) | Yes | Marginal |
| **Difference of means across universes** (e.g. `A-3 − A-1`) | **Yes, joint resample** | See below |
| Top-decile contribution to total return | Optional | Descriptive |

**Joint resampling rule for differences:**

When estimating any statistic of the form `θ_A − θ_B` where A and B
are two universes drawn from the same panel (e.g. R8∩RS_T3 vs RS_T3
unconditional), the same date resample must be applied to both
universes within each bootstrap replication. Independent resampling
of A and B is prohibited: it discards the cross-sectional correlation
that is the very source of variance reduction in the comparison.

### D6. Reporting format

For each statistic `θ` reported under Phase 1 with bootstrap inference:

    θ_hat              : point estimate from raw data
    SE_naive(θ)        : i.i.d. standard error (n = n_raw events)
    SE_bootstrap(θ)    : block-bootstrap standard error (this ADR)
    VIF(θ)             : (SE_bootstrap / SE_naive)^2
    n_eff(θ)           : n_raw / VIF(θ)
    CI_95(θ)           : percentile method, B = 5000 replications

**Locked constants:**

- `B = 5000` bootstrap replications.
- **Percentile method** for CI (BCa, basic, and studentised intervals
  are explicitly excluded from the locked core to avoid additional
  tuning surface; they may be reported as exploratory robustness).
- **Statistic-level `n_eff` and VIF**: effective-n is a property of
  a specific statistic on a specific dataset, not of the dataset
  alone. Different statistics on the same data will yield different
  `n_eff`; this is correct behaviour, not a defect to be averaged
  away.

**Locked seed discipline:**

- A single integer seed must be recorded in the output manifest for
  every Phase 1 bootstrap run.
- Re-runs with the same seed must reproduce identical CI bounds.
- The seed value itself is not locked by this ADR; seed reproducibility
  is.

### D7. Regime stratification

All bootstrap estimation is performed **stratified within regime**, in
direct correspondence with SPEC AC-3 and LA-3 (regime is attached as
`regime[T-1]`).

Procedure per regime `r`:

    1. Restrict the panel to events with regime[T-1] = r.
    2. Restrict the date pool to dates on which any such event occurs.
    3. Apply D1–D6 within this restricted panel:
         - date-level resampling
         - stationary bootstrap, mean block length = 20
         - B = 5000
         - percentile CI
    4. Estimate θ_hat, SE_bootstrap, VIF, n_eff, CI_95 separately
       for regime r.

Pooled-then-stratify is prohibited. Cross-regime statistics (e.g.
"the difference between Bull and Crisis means") require joint
stratified resampling: each bootstrap replication draws dates within
each regime independently, then computes the cross-regime statistic
on the joint resample.

**Honest disclosure requirement:** where a regime cell yields a
small `n_eff` (e.g. Crisis regime with few active R8 dates), the
resulting wide CI is a Phase 1 finding to be reported, not a defect
to be hidden by pooling or by reverting to i.i.d. SEs.

---

## Rationale

The decision set above is driven by three principles:

1. **Match the locked SPEC, not optimise around it.** SPEC v0.1.2
   AC-3, AC-5 and LA-6 dictate that inference must reflect same-day
   clustering, regime structure, and overlapping forward returns.
   Date-level + stationary bootstrap + `L ≥ max_horizon` + regime
   stratification is the minimal method that satisfies all three
   simultaneously.

2. **Minimise governance surface.** Every additional tuning knob
   (auto block length, BCa intervals, alternative bootstrap variants)
   is a future source of silent change and re-litigation. The locked
   core is deliberately minimal; optional robustness items are
   explicitly demarcated.

3. **Disclose, do not paper over, low `n_eff`.** The likely outcome
   of stratified estimation is that some regime cells will have
   `n_eff` an order of magnitude below `n_raw`. This is the honest
   answer to "how much evidence does Phase 1 actually have?" and
   must be reported.

---

## Consequences

### Computational

- Each statistic requires `B × n_regimes × |L_grid|` bootstrap
  replications when sensitivity is fully reported, where
  `n_regimes = number of distinct regime[T-1] labels present in the
  current Phase 1 event panel`. Regime labels must be recorded
  verbatim from the production regime model in the output manifest;
  this ADR does not enumerate them. With `B = 5000` and
  `|L_grid| = 4`, total replications per statistic scale as
  `20000 × n_regimes`.
- Implementation should vectorise resampling at the date level and
  pre-compute per-date aggregates where possible. Implementation
  detail is out of scope for this ADR.

### Statistical

- Reported CI for primary statistics will be wider than under naive
  i.i.d. SE. This is by construction.
- `n_eff` for some regime cells is likely to be small. This is an
  expected outcome, not a failure mode.
- Sensitivity across `L_grid = {5, 10, 20, 40}` will reveal whether
  inference is stable in the neighbourhood of `L_primary = 20`.
  Large divergence at `L = 40` would warrant an ADR amendment
  reconsidering `L_primary`; large divergence at `L ∈ {5, 10}` is
  expected and does not warrant amendment (the hard rule already
  disallows primary inference from those block lengths).

### Provenance

Every Phase 1 inferential output must record in its manifest:

    bootstrap_method:        "stationary"
    resampling_unit:         "trading_date"
    block_length_primary:    20
    block_length_sensitivity: [5, 10, 20, 40]
    replications:            5000
    ci_method:               "percentile"
    regime_stratified:       true
    seed:                    <integer>
    adr_version:             "ADR-R8P1-001 v0.1.0"

Silent omission of any of these fields constitutes a governance
violation under AC-5.

---

## Validation Requirements

Before the first Phase 1 inferential output is produced, the
implementation must demonstrate:

1. **Reproducibility check.** Two runs with identical seed produce
   bit-identical CI bounds.
2. **Joint resample correctness.** On a constructed toy example with
   two universes sharing a documented fraction of dates, joint
   resampling preserves paired-date dependence and differs from
   independent resampling in the direction expected and documented
   by the test (typically: narrower CI for the difference under joint
   resampling, but the test must specify the expected sign and
   tolerance to avoid floating-point or edge-case false failures).
3. **Sensitivity surface populated.** All four block lengths in
   `L_grid` are computed and reported, not silently dropped.
4. **Regime stratification non-trivial.** Each regime cell with
   `n_raw ≥ 1` produces an estimate or is explicitly labelled
   "below minimum cell size" with the threshold documented.

A diagnostic notebook implementing items 1–4 on synthetic data is
recommended as a pre-flight artefact, separate from any Phase 1
output.

---

## Alternatives Considered and Rejected

| Alternative | Reason rejected |
|---|---|
| Event-level resampling | Breaks same-day clustering (LA-6); equivalent to i.i.d. assumption. |
| Moving block bootstrap (Künsch 1989) | Fixed block boundary breaks stationarity; stationary bootstrap is the safer default. |
| Circular block bootstrap | Edge-effect correction unnecessary given sample size; adds no inferential value here. |
| Politis-White auto block length in locked core | Introduces spectral-density-estimation variance and package dependency; better as optional robustness. |
| BCa or studentised CI | Additional tuning surface for marginal accuracy gain at Phase 1 scope. |
| Newey-West HAC as primary | Analytical, lacks small-sample robustness for clustered+overlapping setup; acceptable as cross-check only. |
| Pooled-then-stratify | Violates AC-3 in spirit; produces mixture-distribution SE not interpretable as regime-specific. |
| Subsampling to non-overlapping events | Severe sample reduction; effective-n loss exceeds the dependence cost being avoided. |

---

## Amendment Procedure

This ADR is locked when signed off. Amendment requires:

1. A new ADR version (`v0.1.1`, `v0.2.0`, ...) with explicit changelog.
2. Written rationale citing either (a) a SPEC change in
   `r8_phase1_lifecycle_spec.md`, or (b) empirical evidence that a
   locked choice produces materially misleading inference.
3. Re-run of any Phase 1 output that was produced under the prior ADR
   version. The amended ADR does not retroactively re-label prior
   outputs; they remain valid under their ADR version of record.

Silent edits are prohibited under SPEC §7.

---

## References

- Künsch, H. R. (1989). The jackknife and the bootstrap for general
  stationary observations. *Annals of Statistics*, 17(3), 1217–1241.
- Politis, D. N., & Romano, J. P. (1992). A circular block-resampling
  procedure for stationary data. In *Exploring the Limits of
  Bootstrap*. Wiley.
- Politis, D. N., & Romano, J. P. (1994). The stationary bootstrap.
  *Journal of the American Statistical Association*, 89(428),
  1303–1313.
- Politis, D. N., & White, H. (2004). Automatic block-length selection
  for the dependent bootstrap. *Econometric Reviews*, 23(1), 53–70.
- Patton, A., Politis, D. N., & White, H. (2009). Correction to
  "Automatic block-length selection for the dependent bootstrap" by
  D. Politis and H. White. *Econometric Reviews*, 28(4), 372–375.

---

## Sign-off

| Role | Status |
|---|---|
| Method author | Drafted v0.1.0, 2026-06-06 |
| Phase 1 SPEC owner | Signed off 2026-06-06 |
| Lock date | 2026-06-06 |

Until sign-off, no Phase 1 inferential output may be produced.

---

*End of ADR-R8P1-001 v0.1.0*
