# R8 Phase 1 — Interim Findings

<!-- research/r8_phase1_interim_findings.md -->
<!-- v0.1.0 — 2026-06-06 -->

---

> **Status: PROVISIONAL**
>
> This document is provisional per lifecycle spec AC-6. IF-2 (empty `stock_info`)
> and IF-3 (empty `corporate_actions`, DQ-CA-001) remain OPEN. No finding in this
> document may be cited as validated or publication-ready. No production strategy
> changes may be derived from this document. All findings require a clean-panel
> re-run after IF-2 and IF-3 are closed before any downstream use.

---

## 1. Executive Summary

Phase 1 has completed all three required benchmark analyses (A-1, A-2, A-3).
The primary finding is that R8 events within the RS_T3 universe are followed
by statistically robust incremental forward returns in bull regimes at 10-day
and 20-day horizons. The RS_T3 benchmark itself carries meaningful positive
returns in bull regimes, so R8 should be understood as a timing enhancement
layered on top of an already-positive baseline, not as the primary return driver.

The pullback-state analysis (A-2) produced a substantive structural finding:
Treatment_2 (R8 ∩ RS_T3 ∩ pullback state) contains only 262 observations
across 109 dates — 4.9% of Treatment_1. This sparsity precludes inferential
evaluation. Directional estimates are available but carry no statistical weight.
This is a pre-registered finding, not a methodological failure.

All three analyses are now artifact-complete. Phase 1 overall status remains
IN PROGRESS pending clean-panel re-run (AC-6 condition).

---

## 2. Research Question

**Primary question:**

> Does the R8 +5% breakout event provide incremental timing information within
> the RS top-tertile (RS_T3) universe, beyond what is explained by RS exposure
> alone?

This question is comparative, not absolute. The relevant counterfactual is
"holding high-RS names on R8 event dates," not "cash." Phase 1 tests whether
the R8 trigger adds timing information within an already-conditioned universe.

**What this question is not:**

- "Can R8 generate positive returns?" — absolute profitability is outside scope.
- "Is R8 a viable production strategy?" — Phase 1 measures; it does not validate.
- "Does R8 have alpha?" — Phase 1 establishes incremental forward return
  differences under specific conditions; it does not validate net-of-cost alpha.

---

## 3. Benchmark Definitions

All three benchmarks are evaluated on R8 event dates (D_R8), stratified by
`regime[T-1] × near_limit_up`. Forward return formula (frozen):
`adj_close[T+h] / adj_open[T+1] - 1`. Construction C (event-matched,
date-anchored) per ADR-R8P1-002.

| Benchmark | Treatment | Baseline | Estimand |
|---|---|---|---|
| **A-1: RS_T3 Hold** | — | RS_T3 non-R8 stocks on D_R8 dates (Baseline_1) | θ_base = mean(Baseline_1 fwd_return) |
| **A-2: RS_T3 + Pullback** | R8 ∩ RS_T3 ∩ pullback (Treatment_2) | RS_T3 non-R8 ∩ pullback (Baseline_2) | Δ_A2 = θ_treat − θ_base |
| **A-3: R8 within RS_T3** | R8 ∩ RS_T3 (Treatment_1) | RS_T3 non-R8 (Baseline_1) | Δ_A3 = θ_treat − θ_base |

Pullback filter (A-2): `dist_above_ma20_atr < 0`, applied symmetrically to
both sides per ADR-R8P1-002 interpretation β.

---

## 4. A-1 Findings — RS_T3 Hold Benchmark

**Artifact:** `data/_storage/r8_phase1_a1/v0.1.0/`
**Mode:** Descriptive with bootstrap uncertainty (no hypothesis test, no p-value)
**Panel:** Baseline_1 — 63,363 observations, 1,068 unique dates, 204 stocks

### PASS cells (full bootstrap CI available)

Three cells reached joint adequacy PASS: bull/nlu=0, bear/nlu=0, neutral/nlu=0.

**Bull regime, nlu=0** (n=38,080–39,074 obs; 636–655 dates depending on horizon)

| Horizon | θ_base | 95% CI (L=20) | n_eff |
|---|---|---|---|
| 1td | −0.13% | [−0.18%, −0.08%] | 1,227 |
| 5td | +0.62% | [+0.28%, +0.96%] | 198 |
| 10td | +1.50% | [+0.85%, +2.13%] | 105 |
| 20td | +3.03% | [+1.84%, +4.17%] | 71 |

θ_base increases monotonically with horizon. The 95% CI excludes zero at 5td
and beyond; at 20td the entire CI lies above +1.8%. Bootstrap uncertainty
widens substantially at longer horizons (n_eff drops from 1,227 at 1td to 71
at 20td), reflecting temporal autocorrelation in bull-regime RS_T3 returns.

Sensitivity: primary findings are robust across L={5,10,20,40}. At 20td, the
CI lower bound ranges from +1.84% to +2.15% across all block lengths.

**Bear regime, nlu=0** (n≈12,128–12,155 obs; 203 dates)

| Horizon | θ_base | 95% CI (L=20) | n_eff |
|---|---|---|---|
| 1td | −0.14% | [−0.25%, −0.03%] | 286 |
| 5td | −0.38% | [−1.04%, +0.30%] | 72 |
| 10td | −0.69% | [−2.01%, +0.69%] | 44 |
| 20td | −1.14% | [−3.43%, +1.23%] | 35 |

All 95% CIs from 5td onward contain zero. Bear-regime RS_T3 baseline carries
no reliably positive return; the point estimate drifts monotonically negative.

Sensitivity: consistent across L={5,10,20,40}. The zero-crossing of CIs is
stable regardless of block length.

**Neutral regime, nlu=0** (n≈8,126–8,148 obs; 142 dates)

| Horizon | θ_base | 95% CI (L=20) | n_eff |
|---|---|---|---|
| 1td | −0.23% | [−0.37%, −0.10%] | 145 |
| 5td | −0.14% | [−0.71%, +0.40%] | 58 |
| 10td | −0.02% | [−1.18%, +1.11%] | 27 |
| 20td | +0.21% | [−1.88%, +2.48%] | 15 |

All CIs contain zero at 5td and beyond. n_eff at 20td = 15, reflecting
structural low date support; wide CIs are an honest disclosure of sparse
coverage, not a defect.

### Summary

The RS_T3 baseline itself is materially positive only in bull regimes and at
longer horizons. In bear and neutral regimes, the RS_T3 Hold strategy does not
produce reliably positive returns on R8 event dates. This provides essential
context for interpreting A-3 uplifts.

---

## 5. A-2 Findings — RS_T3 + Pullback Benchmark

**Artifact:** `data/_storage/r8_phase1_a2/v0.1.0/`
**Mode:** DESCRIPTIVE ONLY — no bootstrap, no CI, no p-value
**Panel:** Treatment_2 — 262 observations, 109 dates; Baseline_2 — 8,846 observations, 956 dates

### Structural finding: Treatment_2 sparsity

Treatment_2 (R8 events additionally satisfying `dist_above_ma20_atr < 0`) is
4.9% of Treatment_1. This is an economically meaningful result: R8 event
definition requires a +5% intraday move with close above open, which typically
places the stock above its MA20 by ATR units. Post-trigger pullback state
(`dist_above_ma20_atr < 0`) is therefore unusual at the R8 event date itself.

Pre-run adequacy audit:

| Cell | Treatment_2 n_dates | Baseline_2 n_dates | Joint adequacy |
|---|---|---|---|
| bull, nlu=0 | 38 | 607 | DIRECTIONAL_ONLY |
| bear, nlu=0 | 36 | 167 | DIRECTIONAL_ONLY |
| crisis, nlu=0 | 14 | 53 | INSUFFICIENT |
| neutral, nlu=0 | 14 | 129 | INSUFFICIENT |
| all nlu=1 cells | ≤11 | ≤1 | INSUFFICIENT |

**Result: 0 PASS cells. A-2 cannot be evaluated inferentially under the
current sample.** This is the primary A-2 finding and is pre-registered as an
expected outcome in ADR-R8P1-002.

### Research hypotheses revisited

Prior to A-2, two interpretations of the relationship between R8 and pullback
state were possible:

**H1 — Pullback captures timing value:**
If pullback state alone explains the R8 uplift, then restricting to
pullback-conditioned stocks should reduce the R8 incremental value. Prediction:
Δ_A2 substantially smaller than Δ_A3.

**H2 — R8 uplift independent of pullback state:**
If R8 timing adds information beyond the pullback condition, the incremental
value should persist even within the pullback-conditioned universe. Prediction:
Δ_A2 ≈ Δ_A3.

### Directional evidence (DIRECTIONAL_ONLY cells — inference prohibited)

**Bull regime, nlu=0** (63 treatment obs, 38 treatment dates):

| Horizon | θ_treat | θ_base | Δ_A2 | treat_hit_rate | base_hit_rate |
|---|---|---|---|---|---|
| 1td | +0.46% | −0.12% | +0.57% | 50.8% | 43.0% |
| 5td | +0.28% | +0.87% | −0.59% | 39.7% | 52.6% |
| 10td | +3.35% | +1.65% | +1.70% | 66.1% | 54.7% |
| 20td | +5.42% | +3.22% | +2.20% | 63.9% | 58.3% |

**Bear regime, nlu=0** (57 treatment obs, 36 treatment dates):

| Horizon | θ_treat | θ_base | Δ_A2 | treat_hit_rate | base_hit_rate |
|---|---|---|---|---|---|
| 1td | +0.20% | −0.29% | +0.49% | 45.6% | 40.9% |
| 5td | +0.56% | −0.95% | +1.51% | 49.1% | 43.8% |
| 10td | +2.57% | −1.36% | +3.93% | 50.9% | 42.7% |
| 20td | +3.98% | −1.02% | +5.00% | 63.2% | 46.3% |

The 5td reversal in the bull cell (Δ_A2 = −0.59%) and the large bear point
estimates relative to sample size are consistent with high-noise, low-date-count
estimates. These numbers must not be read as findings.

### Directional consistency with H2

At 10td and 20td in the bull cell, Δ_A2 (+1.70%, +2.20%) is numerically
similar to Δ_A3 (+1.35%, +2.10%). This is directionally consistent with H2
(R8 uplift independent of pullback state), but **inference is prohibited**.
With 38 treatment dates, the point estimates have wide unquantified uncertainty.
The H1/H2 question remains open pending a larger sample.

---

## 6. A-3 Findings — R8 within RS_T3 vs RS_T3 Unconditional

**Artifact:** `data/_storage/r8_phase1_a3/v0.1.0/`
**Mode:** Full inferential (stationary block bootstrap, B=5000, L=20 primary)
**Panel:** Treatment_1 — 5,330 events; Baseline_1 — 63,363 observations

Full inference available for PASS cells: bull/nlu=0, bear/nlu=0, neutral/nlu=0.

### Tier 1 — Robust findings

**Bull regime, nlu=0**
(treatment ≈2,141–2,276 events; 596–614 treatment dates per horizon)

| Horizon | Δ_obs | 95% CI (L=20) | CI lower bound range across L | p (L=20) | n_eff |
|---|---|---|---|---|---|
| 10td | +1.35% | [+0.69%, +2.18%] | +0.61% to +0.72% | 0.0002 | 299 |
| 20td | +2.10% | [+0.94%, +3.45%] | +0.77% to +1.11% | 0.0008 | 258 |

**Sensitivity verdict: ROBUST.** At all block lengths L={5,10,20,40}, the 95%
CI lower bound is strictly positive. p ≤ 0.004 across the full sensitivity
grid. The finding does not depend on the L=20 choice.

**Monotone pattern:** Δ_obs increases with horizon (1td: −0.03%, 5td: +0.38%,
10td: +1.35%, 20td: +2.10%), consistent with trend-continuation dynamics.
Causal interpretation is outside Phase 1 scope.

### Tier 2 — Consistent direction, insufficient evidence

**Bull regime, nlu=0, 5td:** Δ_obs = +0.38%. Positive at all block lengths;
p ranges 0.046–0.085. Does not meet α=0.05 consistently across sensitivity grid.

### Tier 3 — Suggestive, not promoted

**Bear regime, nlu=0, 20td:** Δ_obs = +1.46%. p ranges 0.025–0.034
(nominally significant), but 95% percentile CI contains zero at all block
lengths (lower bound −0.19% to −0.11%). Under the ADR-locked precedence rule
(CI method > p-value method), this result is not promoted.

### No-signal cells

Bear/nlu=0 at 1td–10td: p > 0.23 at all block lengths. Neutral/nlu=0 at all
horizons: CIs contain zero, p > 0.05 across full grid; n_eff at 20td = 47–60.

---

## 7. Integrated Interpretation

### Benchmark hierarchy (bull regime, nlu=0, 20td)

| Benchmark | θ_treat | θ_base | Δ | Inference |
|---|---|---|---|---|
| A-1: RS_T3 Hold | — | +3.03% | — | Bootstrap CI: [+1.84%, +4.17%] |
| A-2: RS_T3 Pullback | +5.42% | +3.22% | +2.20% | None — DIRECTIONAL_ONLY |
| A-3: R8 vs RS_T3 | ≈+5.13%* | +3.03% | +2.10% | Bootstrap CI: [+0.94%, +3.45%] |

*θ_treat (A-3) = θ_base + Δ_A3 = 3.03% + 2.10% = 5.13% (implied; not directly
reported in A-3 artifact).

### Reading the hierarchy

**A-1 establishes the baseline level.** The RS_T3 Hold strategy in bull regimes
already generates approximately +3% at 20td on R8 event dates. R8 operates on
top of a strongly positive baseline, not a flat one.

**A-3 establishes incremental timing value.** The +2.10% uplift is robust and
accounts for approximately 41% of the implied treatment return (+5.13%).
R8 is a timing enhancement with meaningful but not dominant incremental value
relative to a passive RS_T3 hold.

**A-2 leaves the pullback question open.** The directional A-2 estimates
(Δ_A2 ≈ +2.20% at 20td in bull) are numerically consistent with H2 — R8 uplift
does not appear to depend on pullback state. However, Treatment_2 has only 38
dates in the most favourable cell. This observation is directionally consistent
with H2 but provides no inferential support for it. The H1/H2 question requires
a larger sample to resolve.

**A-2 pullback baseline (θ_base = +3.22%) is close to A-1 baseline (+3.03%).**
Filtering to pullback state does not materially change the RS_T3 baseline
return. Pullback state alone, as captured by `dist_above_ma20_atr < 0`, does
not appear to select for meaningfully different expected returns among RS_T3
stocks on R8 event dates.

### Regime context

The findings are materially regime-dependent. In bull regimes, both the RS_T3
baseline and the R8 uplift are positive and statistically distinguishable from
zero. In bear and neutral regimes, the RS_T3 baseline itself carries no reliable
positive return; the R8 uplift in bear is suggestive at 20td but not
inferentially supported (CI contains zero). This regime-conditioning is
structurally important: R8 is not a regime-neutral strategy based on Phase 1
evidence.

---

## 8. Phase 1 Answer to Primary Research Question

> **Does the R8 +5% breakout event provide incremental timing information
> within the RS_T3 universe, beyond what is explained by RS exposure alone?**

| Regime | Answer | Basis |
|---|---|---|
| **Bull** | **YES (PROVISIONAL)** | A-3 Tier 1: Δ_obs = +1.35% / +2.10% at 10td / 20td; robust across bootstrap sensitivity grid; CI strictly positive at all block lengths |
| **Bear** | **INCONCLUSIVE** | A-3 Tier 3: Δ_obs = +1.46% at 20td nominally significant (p ≈ 0.03) but 95% CI contains zero; not promoted under CI-precedence rule |
| **Neutral** | **NO EVIDENCE** | A-3: all deltas negative or near-zero; all CIs contain zero; p > 0.05 across full grid |
| **Pullback interaction** | **UNRESOLVED** | A-2: Treatment_2 too sparse (38 max treatment dates); directional estimates consistent with H2 but inference prohibited |

**Scope boundaries on the "YES" answer:**

The bull-regime finding is conditional on the RS_T3 proxy (LA-4), evaluated
on R8 event dates in bull regimes with `near_limit_up = 0`. It establishes
incremental forward return differences at 10td and 20td horizons. It does not
establish exploitability net of costs, temporal stability, or regime-generality.
The +2.10% uplift at 20td is a timing enhancement on top of a +3.03% baseline —
R8 improves timing within an already-positive universe; it is not the primary
return source.

**What remains open after Phase 1:**

The H1/H2 question (whether pullback state captures the timing value or R8
adds independent information within pullback state) cannot be resolved until
Treatment_2 accumulates sufficient date support. Phase 1 findings are also
conditional on IF-2 and IF-3 closure — see Section 9.

---

## 9. Phase 1 Conclusions

### What Phase 1 has established (subject to PROVISIONAL status)

1. **Positive RS_T3 baseline in bull regimes.** RS_T3 Hold generates
   approximately +3% at 20td in bull-regime conditions on R8 event dates.
   This is the benchmark against which R8 timing value is measured.

2. **Robust R8 timing uplift in bull regimes.** R8 events within RS_T3 are
   followed by approximately +1.35% and +2.10% incremental forward returns at
   10td and 20td respectively, relative to RS_T3 non-R8 observations. The
   finding is statistically robust across the full bootstrap sensitivity grid.

3. **R8 is a timing enhancement, not the primary return driver.** The +2.10%
   uplift at 20td represents approximately 41% of the implied treatment return;
   the RS_T3 baseline contributes the remainder. Characterising R8 as "generating
   returns" is imprecise — R8 improves timing within an already-positive universe.

4. **Pullback-state R8 is too sparse for inferential evaluation.** Treatment_2
   contains only 262 events (4.9% of Treatment_1). This is a structural
   characteristic of the R8 definition, not a sample size problem to be
   resolved by extending the time series modestly. The directional evidence is
   consistent with A-3 but carries no inferential weight.

5. **No reliable R8 uplift outside bull regimes.** Bear-regime evidence is
   suggestive at 20td but the CI contains zero. Neutral-regime evidence is
   negative or flat with wide CIs. Phase 1 does not support generalising the
   bull-regime finding to other regimes.

### What Phase 1 has not established

- That R8 is exploitable net of execution costs.
- That the R8 uplift is stable across different time sub-periods.
- That the pullback condition (H1 vs H2) is resolved.
- That the findings are robust to panel remediation (IF-2, IF-3 remain open).
- That R8 constitutes independent alpha.

---

## 10. Open Items

### Binding constraints on findings validity

| ID | Description | Status | Impact |
|---|---|---|---|
| AC-6 | All Phase 1 findings remain PROVISIONAL until clean-panel re-run | OPEN | All findings require re-confirmation after IF-2 and IF-3 are closed |
| IF-2 | Empty `stock_info` — RECLASSIFIED P2 | NOT BINDING | Phase 1 scripts do not query `stock_info`; sector validation uses `company_metadata.industry_code`. Does not block AC-6 closeout. |
| IF-3 | Empty `corporate_actions` (DQ-CA-001) | OPEN | Halt/suspension events cannot be excluded; may inflate or deflate forward returns in affected events |

### IF-2 Reclassification

IF-2 (`stock_info` empty table) is reclassified from an AC-6 binding
blocker to a P2 data backlog item, effective 2026-06-06.

Rationale:
- Phase 1 A-1/A-2/A-3 estimand construction does not query `stock_info`.
- Sector composition validation is diagnostic only and does not enter
  forward-return computation.
- `company_metadata.industry_code` (source: TWSE t187ap03_L, 1088 rows,
  last synced 2026-05-22) is accepted as the Phase 1 sector diagnostic
  source.

AC-6 binding blockers are now: IF-3A (corporate_actions dividend/split
population) and IF-3B (suspension/halt/resumption tradability dataset).
The `stock_info` population pipeline remains deferred as P2 data
infrastructure work.

### Research questions not addressed by Phase 1

| Question | Required next step |
|---|---|
| H1 vs H2 (pullback captures timing value?) | Larger sample required; re-evaluate after 1–2 years of additional data |
| Sub-period stability of R8 uplift | Phase 2 scope: rolling-window or OOS validation |
| Execution-cost adjusted returns | Phase 2 scope: requires execution simulation |
| Sector/stock concentration sensitivity | Requires IF-2 closure to verify electronics-concentration structure |

### Governance status

| Analysis | Artifact | Inference mode | AC-2 contribution |
|---|---|---|---|
| A-1 RS_T3 Hold | `r8_phase1_a1/v0.1.0/` | Descriptive + bootstrap CI | COMPLETE |
| A-2 RS_T3 Pullback | `r8_phase1_a2/v0.1.0/` | Descriptive only (0 PASS cells) | COMPLETE — adequacy outcome |
| A-3 R8 within RS_T3 | `r8_phase1_a3/v0.1.0/` | Full inferential | COMPLETE |

AC-2 (all three required comparisons measured and reported) is satisfied.
AC-6 remains binding. Phase 1 overall status: **IN PROGRESS** pending
clean-panel re-run.

---

*End of r8_phase1_interim_findings.md v0.1.0*
