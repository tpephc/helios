# R8 MA5 Momentum — Phase 4 Capital Utilisation Optimisation Specification

<!-- research/r8_phase4_spec.md -->
<!-- v0.1.1 — 2026-06-07 -->

**Status:** LOCKED — v0.1.1 (2026-06-07)
**Inherits from:**
- `research/r8_phase1_interim_findings.md` v1.0.0 (CONFIRMED)
- `research/r8_phase1_lifecycle_spec.md` v0.2.1 (LOCKED)
- `research/phase2_research_roadmap.md` v0.3.0 (LOCKED)
- `research/r8_phase2a_spec.md` v0.3.0 (LOCKED)
- `research/r8_phase2a_validation_report.md` v1.0.0 (STABLE)
- `research/r8_phase2b_spec.md` v0.1.2 (LOCKED)
- `research/r8_phase2b_feasibility_memo.md` v1.0.0 (FEASIBLE)
- `research/r8_phase3_spec.md` v0.1.2 (LOCKED)
- `research/r8_phase3_risk_report.md` v1.0.1 (LOCKED)
**Prerequisite:** Phase 3 CHARACTERISED verdict (confirmed 2026-06-07)
**Authorises:** Phase 4 Capital Utilisation Optimisation research only.
**Does not authorise:** Production deployment, live signal generation,
modification of the Helios paper-trading exit contract, or any Phase 5 work.

---

## Changelog

| Version | Date | Change |
|---|---|---|
| v0.1.0 | 2026-06-07 | Initial SPEC DRAFT. D1–D3 decisions frozen. Three-track structure defined. |
| v0.1.1 | 2026-06-07 | §5.3: bootstrap block length frozen to L = max(5, h) for each horizon. D2 §3.2: added explicit heuristic disclaimer for CANDIDATE thresholds. No D-level parameters modified. |

---

## 1. Research Question

> Can capital utilisation be improved without destroying the per-position
> edge observed in Phase 1?

The Phase 1–3 research chain established:

| Phase | Finding |
|---|---|
| Phase 1 | R8 signal edge exists (bull-regime, Δ_A3 +1.92% at 20td) |
| Phase 2A | Edge is temporally stable (27/27 rolling windows positive) |
| Phase 2B | Edge survives realistic execution costs (FEASIBLE) |
| Phase 3 | Edge deployment is constrained by holding-period capital lock-up (16.3% admission rate) |

Phase 4 addresses the Phase 3 Primary Finding: the 20-trading-day holding
period causes holding-period-induced capital lock-up, not signal clustering.
The primary lever to improve capital utilisation is therefore exit contract
design, not position sizing.

**Scope boundary:** Phase 4 researches the same R8 signals (frozen from
Phase 1), varying the exit horizon and exit rules. It does not re-validate
the signal edge, modify signal entry conditions, or target signal
parameter optimisation.

**Relationship to paper trading:** Phase 4 is a research track only. It runs
counterfactual portfolios on the historical panel. Phase 4 findings do not
authorise direct modification of the Helios paper-trading exit contract.
The governance path is: Phase 4 → design recommendations → Phase 5 deployment
evaluation SPEC → paper-trading candidate. Phase 4 and paper trading are
explicitly separated tracks (D3).

---

## 2. Inheritance from Phase 3

### Key findings carried forward

| Finding | Value | Source |
|---|---|---|
| Full-sample admission rate (baseline) | 16.3% (350/2,143) | Phase 3 §3.1 |
| Capital lock-up driver | Holding-period retention, not clustering | Phase 3 §3.2 |
| Signal dates with > 10 simultaneous signals | 2.1% (13/615) | Phase 3 §3.2 |
| Mean signals per date | 3.7 | Phase 3 §3.2 |
| FIFO selection bias | Admitted ≠ highest-quality signals | Phase 3 L-1 |
| Low-Uplift Sharpe Δ (R8 vs RS_T3) | 0.007 (no material advantage) | Phase 3 §4.3 |
| Cap relaxation finding | Higher caps degraded risk profile (B3 MaxDD 41.56%) | Phase 3 §5.2 |

### Mandatory Phase 4 assumptions (from Phase 3 §7)

1. Holding-period reduction is the primary capital utilisation lever.
   Cap relaxation is deprioritised (Track B evidence).
2. Low-Uplift must remain the primary stress environment for Phase 4
   evaluation (as in Phase 3 baseline).
3. Phase 4 must explicitly define its portfolio estimand (Interpretation B:
   calendar-time MTM NAV, shared capital pool — Phase 3 SPEC §2.1).
4. The Phase 4 SPEC author is responsible for assessing whether Phase 3
   risk metrics are acceptable as a baseline for comparison.

---

## 3. Decisions

### D1: Outcome horizons (new data requirement)

**Decision:** Phase 4 computes forward returns at four horizons:
5, 10, 15, and 20 trading days.

**Rationale:** The Phase 1 forward return (20td) is frozen as a research
outcome, not a portfolio construction parameter. Once holding period becomes
a research variable, a single 20td outcome is insufficient. Phase 4 treats
exit horizon as an independent variable and requires a full set of comparable
outcomes.

**Formula (frozen, extends Phase 1):**

```
fwd_return[T+h] = adj_close[T+h] / adj_open[T+1] - 1
```

for h ∈ {5, 10, 15, 20}. The entry fill price `adj_open[T+1]` is unchanged
from Phase 1. Only the exit price varies by horizon.

**New data requirement:** The Phase 1 panel contains `fwd_20td` only.
Phase 4 runner must call `compute_forward_returns(panel, prices,
horizons=[5, 10, 15, 20])` from `run_r8_phase1_a3.py` to produce
`fwd_5td`, `fwd_10td`, `fwd_15td`, `fwd_20td` for all panel rows.

**Note on Phase 1 compatibility:** The 20td outcome column produced by Phase 4
must reproduce the Phase 1 fingerprint (P3-FP-001: Full-sample S1 net =
+1.64% ± 1 bp at 20td). This serves as a lineage check across phases.

### D2: Verdict structure (two-layer)

**Decision:** Phase 4 produces a two-layer verdict.

**Layer 1 — Research completion:**

| Verdict | Definition |
|---|---|
| **OPTIMISATION_CHARACTERISED** | All mandatory analyses completed; Design Recommendations issued |
| **INCOMPLETE** | One or more mandatory analyses missing; Phase 5 blocked |

OPTIMISATION_CHARACTERISED does not imply that a superior exit design was
found. It asserts that the research was completed and the results — whether
positive or null — are documented and usable as Phase 5 input.

**Layer 2 — Design Recommendations (advisory, non-binding):**

The Phase 4 report issues at minimum one of:

| Recommendation type | Meaning |
|---|---|
| `RETAIN_20TD_BASELINE` | No tested exit variant improves on the 20td baseline across the primary evaluation criteria |
| `CANDIDATE: [variant]` | Named variant merits evaluation in Phase 5; criteria satisfied |
| `FURTHER_RESEARCH_REQUIRED` | Results are inconclusive; specific gaps identified |

Design Recommendations are advisory. They do not constitute deployment
authorisation. Phase 5 SPEC must independently assess each CANDIDATE
recommendation before paper-trading consideration.

**Criterion for issuing a CANDIDATE recommendation:**

A variant earns CANDIDATE status if it satisfies all three:
1. Full-sample admission rate improvement ≥ 25 percentage points vs
   baseline (16.3% → ≥ 41.3%)
2. Low-Uplift Sharpe ≥ 1.0 (Phase 3 baseline: 1.613 — must not degrade
   below a meaningful floor)
3. Full-sample MaxDD ≤ Phase 3 baseline + 5 pp (≤ 26.65%)

These criteria are heuristics, not statistically derived thresholds. They
must be documented as design decisions in the Phase 4 report, and are
not intended to represent statistical significance or economic optimality.
A variant that fails the CANDIDATE criteria may still be documented and
passed to Phase 5 as a research finding with the appropriate caveat.

### D3: Separation from paper trading

**Decision:** Phase 4 is a research track only. It operates on the
historical panel. It has no authority to modify the Helios paper-trading
system, its exit contract, or any production parameter.

**Authorisation chain for paper-trading modification:**

```
Phase 4 findings
    ↓
Design Recommendation (advisory)
    ↓
Phase 5 Deployment Evaluation SPEC (new document required)
    ↓
Paper-trading candidate (requires Phase 5 SPEC approval)
```

No shortcut through this chain is permitted. A Phase 4 CANDIDATE
recommendation does not authorise paper-trading modification without a
Phase 5 SPEC.

---

## 4. Research Tracks

Phase 4 is organised into three tracks. Each track is an independent
analysis that can be completed in any order. All three are required for
OPTIMISATION_CHARACTERISED.

| Track | Research Question |
|---|---|
| **A — Holding Period Study** | How does reducing the holding period from 20td affect per-position edge, admission rate, and risk-adjusted performance? |
| **B — Signal Prioritisation** | Does replacing FIFO admission with a quality-ranked scheduler improve the risk-adjusted profile of admitted positions? |
| **C — Early Exit Rules** | Do mechanical early exit triggers (ATR trailing, MA20 failure, RS deterioration) release capital without materially reducing per-position return? |

---

## 5. Track A — Holding Period Study

### 5.1 Research question

> Does holding-period reduction preserve per-position edge while improving
> capital utilisation?

This is P4-A from Phase 3 §7.

### 5.2 Methodology

Compute the full forward return matrix for all panel rows:

| Column | Definition |
|---|---|
| `fwd_5td` | `adj_close[T+5] / adj_open[T+1] - 1` |
| `fwd_10td` | `adj_close[T+10] / adj_open[T+1] - 1` |
| `fwd_15td` | `adj_close[T+15] / adj_open[T+1] - 1` |
| `fwd_20td` | `adj_close[T+20] / adj_open[T+1] - 1` (Phase 1 frozen) |

For each horizon h ∈ {5, 10, 15}:

1. Run the Phase 3 capital scheduler with `HOLDING_DAYS = h` and baseline
   cap (10%, max 10 positions).
2. Reconstruct calendar-time MTM NAV using `adj_close[T+k]` for k=1..h
   (D1A methodology from Phase 3 SPEC §4.1, adapted for shorter window).
3. Compute all Phase 3 Track A mandatory risk metrics.
4. Compute admission rate and mean daily exposure.

The 20td baseline is taken directly from Phase 3 artifacts (no re-run needed
unless fingerprint check fails).

### 5.3 Per-position edge preservation check

For each horizon, compute the bootstrap Δ_A3 at that horizon:

```
Δ_A3[h] = E[fwd_h | treatment_1] - E[fwd_h | baseline_1]
```

using the Phase 1 stationary block bootstrap (B=5,000, block length
`L = max(5, h)` for each horizon h, percentile CI). The `max(5, h)` rule
ensures a minimum block length of 5 regardless of horizon, and scales with
the holding period to capture autocorrelation at the relevant timescale.
This block length formula is frozen; implementations must not substitute
alternative values without a SPEC amendment.

This checks whether the signal edge at shorter horizons is
statistically distinguishable from zero.

**Scope constraint:** This bootstrap is a descriptive check on per-position
edge at shorter horizons. It does not constitute re-validation of the Phase 1
Tier 1 finding. The Phase 1 CONFIRMED status is unaffected regardless of the
outcome.

### 5.4 Output

| Metric | 5td | 10td | 15td | 20td (Phase 3 baseline) |
|---|---|---|---|---|
| Admission rate | — | — | — | 16.3% |
| Full-sample Sharpe | — | — | — | 2.378 |
| Low-Uplift Sharpe | — | — | — | 1.613 |
| Full-sample MaxDD | — | — | — | 21.65% |
| Δ_A3 point estimate | — | — | — | +1.92% (Phase 1) |
| Δ_A3 CI lower bound | — | — | — | +0.79% (Phase 1) |

---

## 6. Track B — Signal Prioritisation

### 6.1 Research question

> Does replacing FIFO admission with a quality-ranked scheduler improve
> the risk-adjusted profile of admitted positions?

This is P4-C from Phase 3 §7 (renamed Track B here for document
organisation; Phase 3 priority P4-B on early exit is Track C below).

### 6.2 Ranking candidates

Three ranking schemes evaluated as variants:

| Variant | Ranking key | Rationale |
|---|---|---|
| FIFO (baseline) | signal_date ASC, stock_id ASC | Phase 3 baseline; no quality ordering |
| RS-rank | `beta_adj_rs_20d` DESC at signal_date | Higher relative strength at entry |
| Score-rank | `score` from `signals` table DESC | Existing signal quality score if populated |
| Uplift-proxy | `dist_above_ma20_atr` DESC | Proxy for momentum strength at entry |

**Note:** The `score` column in the `signals` table may be sparsely populated
(confirmed from schema inspection 2026-06-07). If fewer than 60% of
treatment_1 rows have non-null `score`, the Score-rank variant is replaced
by a second RS-based variant (e.g., `beta_adj_rs_60d`). This decision is
made at runner implementation time and documented in the Phase 4 report.

### 6.3 Methodology

For each ranking scheme:

1. Sort candidates by the ranking key (descending quality) before passing
   to the capital scheduler. Signal dates and capital constraints are
   unchanged.
2. Run the Phase 3 scheduler (same cap, max_pos, holding period = 20td).
3. Compute all Phase 3 Track A mandatory risk metrics.
4. Compute admission rate (should be identical to Phase 3 baseline;
   admission count is determined by capital, not ranking).

**Key distinction:** Ranking does not change how many positions are admitted;
it changes which positions are admitted. Admission rate should be
approximately identical across ranking variants. The research question is
whether quality-ranked admission produces better risk-adjusted outcomes from
the same pool size.

### 6.4 Comparison basis

Primary comparison: Sharpe and MaxDD of quality-ranked NAV vs FIFO NAV
(Phase 3 baseline) under Full Sample and Low-Uplift scenarios.

If quality ranking produces Sharpe improvement in Low-Uplift ≥ 0.2
(1.613 → ≥ 1.813), the variant earns CANDIDATE status subject to Track A
and C findings.

---

## 7. Track C — Early Exit Rules

### 7.1 Research question

> Do mechanical early exit triggers release capital without materially
> reducing per-position return?

This is P4-B from Phase 3 §7.

### 7.2 Exit rule candidates

Three early exit rule families evaluated:

| Variant | Trigger condition | Capital release timing |
|---|---|---|
| ATR-trailing | Position drawdown from entry exceeds `N × ATR_14` at signal_date | Day after trigger fires |
| MA20-failure | `adj_close[T+k] < sma_20[T+k]` for 3 consecutive days | Day after third consecutive close below MA20 |
| RS-deterioration | `beta_adj_rs_20d` at exit assessment date falls below 0 | Assessed weekly (every 5td); capital released next day |

ATR multiplier `N` evaluated at {1.0, 1.5, 2.0}. MA20-failure assessed
from `daily_features.sma_20`. RS-deterioration requires rejoining
`bullish_features` for the stock at each assessment date.

**Scope constraint:** Early exit rules are mechanical and pre-specified.
No optimisation of trigger parameters is permitted within this SPEC. If
results suggest a different parameter range is promising, a SPEC amendment
is required.

### 7.3 Methodology

For each early exit variant:

1. Apply the Phase 3 scheduler (FIFO, baseline cap, 20td maximum holding).
2. For each admitted position, evaluate the exit trigger daily from k=1.
3. If the trigger fires at day k < 20, close the position at T+k adj_close
   and mark capital as released.
4. Record `actual_holding_days` for each position.
5. Reconstruct calendar-time MTM NAV using the actual (potentially shorter)
   holding window.
6. Compute all Phase 3 Track A mandatory risk metrics.
7. Compute mean actual holding days and resulting admission rate improvement
   (released capital enables earlier re-deployment of subsequent signals).

### 7.4 Per-position return impact

For each exit variant, compute:

```
mean_actual_return = mean(fwd_return at actual exit day)
mean_20td_return   = mean(fwd_20td) for the same admitted positions
drag               = mean_20td_return - mean_actual_return
```

A variant is viable only if `drag` is small relative to the admission rate
improvement it enables. The report must present both quantities side by side.

---

## 8. Output Specification

### 8.1 Deliverable

**Phase 4 Capital Utilisation Optimisation Report**
(`research/r8_phase4_optimisation_report.md`)

Sections:

1. Executive Summary (Layer 1 verdict + Design Recommendations)
2. Methodology (D1–D3 decisions, forward return matrix, scheduler)
3. Track A — Holding Period Study results
4. Track B — Signal Prioritisation results
5. Track C — Early Exit Rules results
6. Cross-Track Synthesis
7. Verdict Assessment (Layer 1 + Layer 2)
8. Phase 5 Assumptions (derived from Phase 4)
9. Residual Limitations
10. Governance

### 8.2 Artifacts

| Artifact | Path | Content |
|---|---|---|
| Forward return matrix | `data/_storage/r8_phase4/v0.1.0/forward_return_matrix.parquet` | fwd_5td, fwd_10td, fwd_15td, fwd_20td for all panel rows |
| Track A results | `data/_storage/r8_phase4/v0.1.0/p4a_holding_period.parquet` | Risk metrics by horizon |
| Track A bootstrap | `data/_storage/r8_phase4/v0.1.0/p4a_bootstrap.parquet` | Δ_A3 CI by horizon |
| Track B results | `data/_storage/r8_phase4/v0.1.0/p4b_prioritisation.parquet` | Risk metrics by ranking scheme |
| Track C results | `data/_storage/r8_phase4/v0.1.0/p4c_early_exit.parquet` | Risk metrics + holding day stats by exit variant |
| Manifest | `data/_storage/r8_phase4/v0.1.0/manifest.json` | Artifact inventory + commit hash |

### 8.3 Runner

```
scripts/run_phase4_analysis.py
```

Version: v0.1.0 (to be implemented after SPEC LOCK).

The runner must verify the Phase 1/Phase 3 fingerprint (P3-FP-001) before
any new computation: full-sample 20td treatment net return at S1 must equal
+1.64% ± 1 bp. Failure aborts the run.

---

## 9. Scope Constraints

### Explicitly out of scope

The following are excluded from Phase 4. Inclusion without a SPEC amendment
constitutes a governance violation:

- Re-estimation of Phase 1 Δ_A3 or re-validation of the CONFIRMED finding.
- Signal parameter optimisation (R8 threshold, MA5 lookback, RS tertile).
- Portfolio-level optimisation (Kelly sizing, volatility targeting, factor hedging).
- Live or paper-trading execution, or modification of the paper-trading exit contract.
- Bearish signal evaluation.
- Dynamic slippage models or market impact estimation.
- Any claim that Phase 4 findings constitute OOS validation.
- Phase 5 work of any kind.

### Relationship to Phase 3

Phase 4 does not re-validate Phase 3 findings. The Phase 3 CHARACTERISED
verdict, 16.3% admission rate, and FIFO scheduler diagnostics are taken as
given. Phase 4 is not permitted to revise Phase 3 conclusions.

---

## 10. Governance

### Upstream dependencies

| Document | Version | Status |
|---|---|---|
| `research/r8_phase1_interim_findings.md` | v1.0.0 | CONFIRMED |
| `research/r8_phase1_lifecycle_spec.md` | v0.2.1 | LOCKED |
| `research/phase2_research_roadmap.md` | v0.3.0 | LOCKED |
| `research/r8_phase2a_spec.md` | v0.3.0 | LOCKED |
| `research/r8_phase2a_validation_report.md` | v1.0.0 | STABLE |
| `research/r8_phase2b_spec.md` | v0.1.2 | LOCKED |
| `research/r8_phase2b_feasibility_memo.md` | v1.0.0 | FEASIBLE |
| `research/r8_phase3_spec.md` | v0.1.2 | LOCKED |
| `research/r8_phase3_risk_report.md` | v1.0.1 | LOCKED |

### Downstream authorisations

| Phase | Authorised by | Requires |
|---|---|---|
| Phase 4 analysis | This SPEC | — |
| Phase 5 (deployment evaluation) | Phase 4 OPTIMISATION_CHARACTERISED | Phase 5 SPEC (must address each CANDIDATE recommendation) |

An INCOMPLETE verdict blocks Phase 5 until gaps are resolved via SPEC
amendment. OPTIMISATION_CHARACTERISED with no CANDIDATE recommendations
results in RETAIN_20TD_BASELINE or FURTHER_RESEARCH_REQUIRED; Phase 5 SPEC
may still proceed to evaluate deployment with the 20td baseline.

### Amendment policy

This SPEC may be amended by a new versioned document. Silent edits are not
permitted. Changes to D1 (horizon set), D2 (verdict structure or CANDIDATE
criteria), D3 (paper-trading separation), §5–§7 track methodology, or §8.3
fingerprint requirement mandate a SPEC version bump with documented rationale.

---

## 11. What Phase 4 Does Not Establish

Regardless of verdict:

- That any exit variant produces superior OOS performance.
- That a CANDIDATE recommendation authorises paper-trading modification.
- That RETAIN_20TD_BASELINE means the 20td holding period is optimal.
- That Phase 4 findings will persist on future data.
- That Phase 4 constitutes re-validation of Phase 1, 2A, 2B, or 3 findings.
- That OPTIMISATION_CHARACTERISED authorises Phase 5 without a new SPEC.

---

*End of r8_phase4_spec.md v0.1.0*
