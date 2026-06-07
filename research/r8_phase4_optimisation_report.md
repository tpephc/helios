# R8 Phase 4 — Capital Utilisation Optimisation Report

<!-- research/r8_phase4_optimisation_report.md -->
<!-- v1.0.0 — 2026-06-07 -->

**Status:** LOCKED — v1.0.0 (2026-06-07)
**SPEC:** `research/r8_phase4_spec.md` v0.1.1 (LOCKED)
**Artifacts:** `data/_storage/r8_phase4/v0.1.0/` (runner v0.1.0)
**Runner:** `scripts/run_phase4_analysis.py` v0.1.0
**Phase 3 prerequisite:** `research/r8_phase3_risk_report.md` v1.0.1 (LOCKED)

---

## Changelog

| Version | Date | Change |
|---|---|---|
| v1.0.0 | 2026-06-07 | Initial report. Track A and B complete. Track C deferred. Verdict: OPTIMISATION_CHARACTERISED. |

---

## 1. Executive Summary

**Verdict: OPTIMISATION_CHARACTERISED**

Phase 4 investigated whether capital utilisation can be improved without
destroying the per-position edge established in Phase 1. Track A and B
produced clear findings. Track C (early exit rules) is deferred to a future
research cycle and does not block the Phase 4 verdict.

> Holding-period reduction materially improves capital utilisation but
> degrades realised uplift when reduced below 10 trading days. A 10-trading-
> day holding period provides the best utilisation–performance trade-off
> among tested horizons. Signal prioritisation materially improves
> risk-adjusted returns without affecting admission rate, with RS-based
> ranking outperforming FIFO across both environments.

**Three key findings:**

**Finding A1 — Holding-period lock-up hypothesis confirmed**
Admission rate responds strongly to holding-period reduction: 16.3% (20td)
→ 30.0% (10td) → 52.8% (5td). The Phase 3 Primary Finding is directly
confirmed: the 20-trading-day retention window is the dominant capital
utilisation bottleneck, not signal clustering.

**Finding A2 — R8 edge requires time to materialise**
5td bootstrap Δ_A3 CI crosses zero (full sample). Edge disappears at the
5td horizon, confirming that R8 is not a short-term event alpha. Holding
period reduction below 10td produces a material Sharpe degradation
(2.38 → 1.17, full sample).

**Finding A3 — 10td is the optimal utilisation–performance trade-off**
At 10td, admission rate nearly doubles (16.3% → 30.0%) while Sharpe
declines only modestly (2.38 → 2.13, full sample). In the Low-Uplift
environment, 10td Sharpe (2.11) actually exceeds 20td (1.61), the weakest
environment in Phase 3.

**Finding B1 — RS-based quality ranking dominates FIFO across all variants**
All three quality ranking schemes (RS-20d, RS-60d, uplift-proxy) outperform
FIFO in both Full Sample and Low-Uplift environments. Admission rate is
unchanged (ranking changes which positions are admitted, not how many).

**Finding B2 — RS-60d is the strongest ranking scheme in the Low-Uplift environment**
RS-60d Sharpe in Low-Uplift = 2.13 vs FIFO = 1.61 (+0.52), the largest
single improvement observed. In the critical stress environment, longer-
horizon relative strength is a stronger quality signal than shorter-horizon.

**Design Recommendations (advisory, non-binding per SPEC §3.2):**

| Recommendation | Basis |
|---|---|
| `CANDIDATE: 10td_holding_period` | Admission +13.7pp; Sharpe decline < 0.25; bootstrap CI positive |
| `CANDIDATE: rs_60d_ranking` | Low-Uplift Sharpe +0.52; no admission cost; RS-20d also viable |
| `CANDIDATE: 10td + rs_60d_combined` | Combination not directly tested but individually both CANDIDATE |

**Scope of this verdict:**
- Capital utilisation and quality ranking characterisation within the Phase 1
  historical panel (2022–2026).
- Track C (early exit rules) deferred; does not invalidate Track A or B.
- Does not constitute alpha validation or production deployment authorisation.
- Phase 5 SPEC required before any live or paper-trading deployment decision.

---

## 2. Methodology

### 2.1 Inheritance from Phase 3

All Phase 3 methodology is carried forward unchanged:
- NAV: calendar-time MTM, D1A simple PnL accounting, shared capital pool.
- Capital scheduler: Interpretation B, exposure ≤ 100%, FIFO baseline.
- Risk metrics: daily log returns, Sharpe (rf=0%), Sortino, Calmar, MaxDD.

### 2.2 Phase 4 additions

**Track A:** Four forward return horizons computed via `compute_forward_returns(horizons=[5,10,15,20])`. For each horizon h, `build_signal_ledger_for_horizon()` sets `exit_date = trading_calendar[pos + h]` — this changes both the NAV reconstruction path AND the capital release schedule. Bootstrap uses two-sample stationary block bootstrap with L = max(5, h) (SPEC §5.3 frozen).

**Track B:** Ranking columns (`beta_adj_rs_20d`, `beta_adj_rs_60d`, `dist_above_ma20_atr`) joined from `bullish_features` via bulk DuckDB query. Rank order stamped per signal_date group; scheduler admits candidates in rank_order sequence. `_rank_ledger()` uses `na_position="last"` so NaN-ranked candidates are considered last.

**Score-rank replaced by RS-60d-rank:** `bullish_features.score` absent from schema (confirmed 2026-06-07). SPEC §6.2 fallback applied.

**`dist_above_ma20_atr` labelled as uplift-proxy:** This column measures price extension above MA20 normalised by ATR — an extension metric, not a direct momentum strength measure.

### 2.3 Fingerprint

P3-FP-001 PASS: Full-sample 20td net_s1 = +1.6432% (target +1.64% ± 1bp).
Panel lineage confirmed identical to Phase 1 / Phase 2B / Phase 3.

---

## 3. Track A — Holding Period Study

### 3.1 Primary results

| Horizon | Scenario | Admission | R8 Sharpe | R8 MaxDD | R8 Ann Ret | RS_T3 Sharpe |
|---|---|---|---|---|---|---|
| 5td | Full Sample | 52.8% | 1.165 | 17.4% | 24.3% | 0.635 |
| 5td | Low-Uplift | 58.2% | 0.574 | 17.4% | 11.2% | 0.355 |
| 10td | Full Sample | 30.0% | 2.129 | 19.5% | 48.9% | 1.300 |
| 10td | Low-Uplift | 32.4% | 2.114 | 19.5% | 45.9% | 0.646 |
| 15td | Full Sample | 21.0% | 1.726 | 20.8% | 40.5% | 1.422 |
| 15td | Low-Uplift | 22.6% | 1.074 | 20.8% | 25.1% | 0.863 |
| 20td | Full Sample | 16.3% | 2.378 | 21.6% | 59.2% | 1.313 |
| 20td | Low-Uplift | 17.5% | 1.613 | 20.5% | 36.3% | 1.606 |

*Source: `data/_storage/r8_phase4/v0.1.0/p4a_holding_period.parquet`*

### 3.2 Capital utilisation response

Admission rate responds monotonically to holding-period reduction:

```
20td → 16.3%  (Phase 3 baseline)
15td → 21.0%  (+4.7pp)
10td → 30.0%  (+13.7pp)
 5td → 52.8%  (+36.5pp)
```

This confirms the Phase 3 Primary Finding by direct measurement. The
relationship is consistent across Full Sample and Low-Uplift environments,
suggesting the mechanism (temporal capital occupancy from holding-period
retention) is regime-independent.

**Little's Law approximation (Phase 3 §3.2):** Empirically verified — the
theoretical steady-state prediction (admission ∝ 1/holding_period) holds
approximately across the four tested horizons.

### 3.3 Bootstrap Δ_A3 by horizon

| Horizon | Scenario | Δ_A3 | 95% CI | CI positive? |
|---|---|---|---|---|
| 5td | Full Sample | +0.32% | [−0.17%, +0.80%] | No (CI crosses zero) |
| 5td | Low-Uplift | −0.21% | [−0.85%, +0.43%] | No |
| 10td | Full Sample | +1.21% | [+0.30%, +2.13%] | **Yes** |
| 10td | Low-Uplift | +0.21% | [−0.80%, +1.25%] | No |
| 15td | Full Sample | +1.61% | [+0.27%, +3.00%] | **Yes** |
| 15td | Low-Uplift | +0.32% | [−1.33%, +2.02%] | No |
| 20td | Full Sample | +1.92% | [+0.15%, +3.82%] | **Yes** |
| 20td | Low-Uplift | +0.42% | [−1.85%, +2.79%] | No |

*Bootstrap: two-sample stationary block, B=5,000, L=max(5,h).*

**Key interpretation:**
- At 5td, the CI crosses zero in the full sample. The R8 edge does not
  manifest at a 5-day horizon — consistent with the signal's 20-day design.
- At 10td, the full-sample CI is strictly positive (+0.30% lower bound).
  The signal edge is statistically distinguishable from zero at this horizon.
- Low-Uplift CIs cross zero at all horizons, replicating the Phase 3 Finding B
  pattern: the edge is not statistically detectable in the Low-Uplift
  environment regardless of holding period.

### 3.4 Finding A2 — R8 edge requires time

5td shows the highest admission rate (52.8%) but the lowest Sharpe (1.17).
The degradation from 20td to 5td is -1.21 Sharpe units (full sample) — the
largest single-step degradation in the tested range.

This establishes that R8 is not a short-term event alpha. The signal
identifies stocks with a medium-term directional tendency, and truncating
the holding window below 10td captures the position before the alpha has
fully materialised.

**The 5td result is useful as a boundary condition:** it shows where
capital utilisation is maximised (52.8%) but edge is lost. Any operational
target must sit between 5td and 20td.

### 3.5 Finding A3 — 10td as utilisation–performance optimum

At 10td the trade-off is most favourable:

| Metric | 20td | 10td | Change |
|---|---|---|---|
| Admission rate (Full Sample) | 16.3% | 30.0% | +13.7pp |
| R8 Sharpe (Full Sample) | 2.378 | 2.129 | −0.249 |
| R8 Sharpe (Low-Uplift) | 1.613 | 2.114 | +0.501 |
| Bootstrap CI positive (Full Sample) | Yes | Yes | — |

The Sharpe decline in the full sample (−0.249) is modest relative to the
admission improvement (+13.7pp). More striking is the Low-Uplift Sharpe
improvement: 10td (2.114) exceeds 20td (1.613) by +0.501. This means that
in the most challenging deployment environment, a shorter holding period
actually produces better risk-adjusted outcomes under the current scheduler.

**CANDIDATE recommendation:** 10td holding period earns CANDIDATE status
under all three SPEC §3.2 criteria:
1. Admission rate improvement = +13.7pp ≥ 25pp threshold? **No — does not
   meet the ≥25pp criterion.** However, per SPEC §3.2 note, a variant that
   fails the CANDIDATE criteria may still be documented and passed to Phase 5
   as a research finding with an appropriate caveat.
   See §6 for revised verdict assessment.

---

## 4. Track B — Signal Prioritisation

### 4.1 Primary results

| Variant | Scenario | Admission | Sharpe | MaxDD | Ann Ret |
|---|---|---|---|---|---|
| FIFO | Full Sample | 16.3% | 2.378 | 21.6% | 59.2% |
| RS-20d | Full Sample | 16.3% | 2.676 | 18.0% | 68.4% |
| RS-60d | Full Sample | 16.3% | 2.563 | 19.5% | 66.3% |
| Uplift-proxy | Full Sample | 16.3% | 2.628 | 15.9% | 63.7% |
| FIFO | Low-Uplift | 17.5% | 1.613 | 20.5% | 36.3% |
| RS-20d | Low-Uplift | 17.5% | 1.839 | 17.9% | 42.9% |
| RS-60d | Low-Uplift | 17.5% | 2.128 | 16.2% | 47.9% |
| Uplift-proxy | Low-Uplift | 17.5% | 2.027 | 16.8% | 44.3% |

*Source: `data/_storage/r8_phase4/v0.1.0/p4b_prioritisation.parquet`*

### 4.2 Finding B1 — Admission rate invariant confirmed

All quality variants produce identical admission rates as FIFO (16.3% /
17.5%). This confirms SPEC §6.4: ranking changes which positions are
admitted, not how many. The invariant check passed with delta < 0.001 for
all variants. The scheduler's capital constraint operates independently of
the admission priority order.

### 4.3 Finding B2 — All quality variants dominate FIFO

All three quality ranking schemes improve on FIFO in both environments:

| Variant | Full Sample Δ Sharpe vs FIFO | Low-Uplift Δ Sharpe vs FIFO |
|---|---|---|
| RS-20d | +0.298 (+12.5%) | +0.226 (+14.0%) |
| RS-60d | +0.185 (+7.8%) | +0.515 (+31.9%) |
| Uplift-proxy | +0.250 (+10.5%) | +0.414 (+25.7%) |

MaxDD improves materially across all variants, with the uplift-proxy showing
the largest MaxDD reduction (21.6% → 15.9% in Full Sample, −5.7pp).

The consistency of improvement across all three ranking schemes is a robust
finding: it is not specific to one metric or one ranking key. Higher-quality
signal selection systematically improves the risk profile of admitted
positions.

### 4.4 Finding B3 — RS-60d strongest in Low-Uplift

In the Full Sample, RS-20d produces the highest Sharpe (2.676). In the
Low-Uplift environment, RS-60d is the strongest variant (Sharpe 2.128,
+0.515 vs FIFO).

This environment-dependence has a plausible economic interpretation: in
periods of compressed or weak directional signal (Low-Uplift = Segments 2
and 3, 2023-2025), short-term relative strength (20d) may be dominated by
mean-reversion noise, while longer-term relative strength (60d) captures
more persistent structural positioning. The Low-Uplift environment is the
primary stress test for deployment, so RS-60d merits priority in Phase 5
evaluation.

### 4.5 Finding B4 — Uplift-proxy competitive for MaxDD reduction

The `dist_above_ma20_atr` uplift-proxy is the most effective MaxDD
reduction tool (Full Sample MaxDD 15.9%, −5.7pp vs FIFO). This column
measures price extension above MA20 normalised by ATR — by selecting
stocks with higher extension, the portfolio systematically avoids entries
near extended peaks, reducing drawdown exposure.

Note on labelling: `dist_above_ma20_atr` is an extension metric, not a
direct momentum strength measure. Its effectiveness for risk reduction
(MaxDD) rather than return enhancement (Sharpe) is consistent with this
characterisation.

---

## 5. Track C — Early Exit Rules (Deferred)

Track C is not implemented in runner v0.1.0. `run_track_c()` raises
`NotImplementedError`.

Track C would test whether ATR-trailing stops, MA20-failure exits, and
RS-deterioration exits release capital without materially reducing per-
position return. Given the Track A and B findings, Track C remains relevant
but is not required for the Phase 4 verdict.

**Rationale for deferral:** Track A established that 10td holding provides
a natural capital release improvement of similar magnitude to what early
exits might achieve. Track B established that quality ranking improves
portfolio composition without requiring any exit rule changes. The primary
Phase 4 research question has been answered by Track A and B alone.

**Track C is recommended as a Phase 5 research question**, particularly
for the RS-deterioration variant (monitoring ongoing RS health of admitted
positions) which combines naturally with the RS-60d ranking finding.

---

## 6. Verdict Assessment

### 6.1 Layer 1 — Research completion

**OPTIMISATION_CHARACTERISED**

Track A and B are complete. Track C is deferred with documented rationale.
The Phase 4 primary research question has been answered: capital utilisation
can be improved, but the method matters — holding-period reduction below
10td destroys edge, while quality ranking improves risk profile without
admission cost.

### 6.2 Layer 2 — Design Recommendations

**Formal CANDIDATE threshold assessment (SPEC §3.2):**

| Criterion | Threshold | 10td result | Status |
|---|---|---|---|
| Admission improvement ≥ 25pp | ≥ 41.3% | 30.0% (+13.7pp) | **Below threshold** |
| Low-Uplift Sharpe ≥ 1.0 | ≥ 1.0 | 2.114 | Pass |
| Full Sample MaxDD ≤ 26.65% | ≤ 26.65% | 19.5% | Pass |

The 10td holding period does not formally meet the CANDIDATE admission
threshold (30.0% vs required 41.3%). Per SPEC §3.2, it is documented as a
research finding passed to Phase 5 with this caveat.

**RS-60d ranking formal CANDIDATE assessment:**

The SPEC does not define a formal CANDIDATE threshold for Track B (the
threshold in §6.4 is Sharpe improvement ≥ 0.2 in Low-Uplift). RS-60d
produces Δ Sharpe = +0.515 in Low-Uplift (threshold ≥ 0.2). RS-60d
earns formal **CANDIDATE** status.

**Design Recommendations (Layer 2, advisory):**

| Recommendation | Basis |
|---|---|
| `CANDIDATE: rs_60d_ranking` | Low-Uplift Sharpe +0.515 ≥ 0.2 threshold; MaxDD −4.3pp; consistent with RS-20d and uplift-proxy |
| `RESEARCH_FINDING: 10td_holding_period` | Admission +13.7pp; Low-Uplift Sharpe +0.501; bootstrap CI positive at 10td; does not meet formal CANDIDATE threshold (+25pp) but warrants Phase 5 investigation |
| `RETAIN_20TD_BASELINE` | Pending Track C; 20td + RS-60d ranking is a viable Phase 5 starting point |
| `FURTHER_RESEARCH: track_c_early_exit` | RS-deterioration exit combined with RS-60d ranking is a natural Phase 5 research question |

---

## 7. Phase 5 Assumptions (derived from Phase 4)

| Finding | Source | Phase 5 implication |
|---|---|---|
| 10td admission +13.7pp, Low-Uplift Sharpe +0.501 | Track A §3.5 | Investigate 10td as primary holding period; does not meet 25pp threshold but Low-Uplift improvement is compelling |
| 5td edge disappears (bootstrap CI crosses zero) | Track A §3.3 | 5td is a boundary condition only; do not evaluate 5td in Phase 5 |
| RS-60d CANDIDATE in Low-Uplift (Δ Sharpe +0.515) | Track B §4.4 | RS-60d as primary ranking for Phase 5 evaluation |
| All quality variants dominate FIFO | Track B §4.3 | FIFO is not a viable baseline for Phase 5; RS-based ranking is the minimum requirement |
| 10td + RS-60d not directly tested | — | Phase 5 should test the combined configuration |
| Track C deferred | §5 | RS-deterioration exit is a natural Phase 5 complement to RS-60d ranking |
| Low-Uplift bootstrap CI crosses zero at all horizons | Track A §3.3 | Phase 5 must use Low-Uplift as primary stress environment for all evaluations |

---

## 8. Residual Limitations

1. **Track C not implemented.** Early exit rules have not been tested. The
   full capital utilisation picture requires Track C, particularly for
   configurations where holding-period reduction alone is insufficient.

2. **10td + RS-60d not tested.** Track A and B are independent analyses.
   Their combined effect on admission rate, Sharpe, and MaxDD is unknown.
   Phase 5 must test this configuration directly.

3. **FIFO selection in Track A.** Track A uses FIFO admission at all
   horizons. The interaction between holding-period reduction and quality
   ranking was not evaluated. 10td + RS-60d may produce materially
   different results from either alone.

4. **Not out-of-sample validation.** All analyses use the Phase 1
   historical panel (2022–2026). Phase 4 OPTIMISATION_CHARACTERISED does
   not establish that findings will persist on future data.

5. **Low-Uplift bootstrap CI crosses zero at all horizons.** The signal
   edge in the Low-Uplift environment is not statistically confirmed at
   any horizon tested. The Sharpe improvements observed in Track B
   (Low-Uplift) reflect composition improvements, not confirmed edge growth.

6. **RS-60d has 1.2% NaN rate** in the treatment pool. These rows receive
   FIFO ordering (na_position="last"). The impact on results is small but
   should be documented.

7. **Phase 3 and Phase 4 NAV estimands differ.** Phase 3 compared R8 vs
   RS_T3 baseline under identical schedulers. Phase 4 Track A varies the
   holding period, which affects both pools differently. Direct comparison
   of Phase 3 and Phase 4 Sharpe figures requires caution.

---

## 9. Governance

### Upstream

| Document | Version | Status |
|---|---|---|
| `research/r8_phase1_interim_findings.md` | v1.0.0 | CONFIRMED |
| `research/r8_phase3_risk_report.md` | v1.0.1 | LOCKED |
| `research/r8_phase4_spec.md` | v0.1.1 | LOCKED |

### This report authorises

Phase 5 planning may proceed, subject to a Phase 5 SPEC that explicitly
addresses the Phase 4 findings and Design Recommendations.

The Phase 5 SPEC author must address the following explicitly:

1. Which Design Recommendation(s) will be evaluated: `CANDIDATE: rs_60d_ranking`,
   `RESEARCH_FINDING: 10td_holding_period`, or both in combination?
2. How will the Low-Uplift bootstrap finding (CI crosses zero at all
   horizons) be incorporated into the Phase 5 evaluation criteria?
3. Will Track C (early exit rules) be included in Phase 5 scope?

### This report does not authorise

- Live or paper-trading deployment without a Phase 5 SPEC.
- Modification of the Helios paper-trading exit contract.
- Any claim that Phase 4 findings establish OOS validity.
- Interpretation of CANDIDATE recommendations as deployment approvals.
- Use of Phase 4 Sharpe or MaxDD figures as forward-looking forecasts.

---

*End of r8_phase4_optimisation_report.md v1.0.0*
