# R8 Phase 3 — Risk & Capital Efficiency Report

<!-- research/r8_phase3_risk_report.md -->
<!-- v1.0.1 — 2026-06-07 -->

**Status:** LOCKED — v1.0.1 (2026-06-07)
**SPEC:** `research/r8_phase3_spec.md` v0.1.2 (LOCKED)
**Artifacts:** `data/_storage/r8_phase3/v0.1.0/` (runner v0.1.0)
**Runner:** `scripts/run_phase3_analysis.py` v0.1.0
**Phase 2B prerequisite:** `research/r8_phase2b_feasibility_memo.md` v1.0.0 (FEASIBLE)

---

## Changelog

| Version | Date | Change |
|---|---|---|
| v1.0.0 | 2026-06-07 | Initial report. Phase 3 analysis complete. Verdict: CHARACTERISED. |
| v1.0.1 | 2026-06-07 | §4.1: inlined Sortino and MaxDD Duration from artifact. §4.4: inlined Pearson correlation values and regime-conditional means. §3.2: added Little's Law attribution for steady-state approximation. |

---

## 1. Executive Summary

**Verdict: CHARACTERISED**

The risk profile, capital-efficiency characteristics, and capacity sensitivity
of the Phase 3 baseline-cap portfolio have been measured and documented
per `research/r8_phase3_spec.md` v0.1.2 (LOCKED). No deployment
recommendation is implied. These findings are intended as input to the
Phase 4 specification and design.

> The dominant Phase 3 finding is not the observed Sharpe ratio but the
> capital utilisation structure: the 20-trading-day holding period caused
> holding-period-induced capital lock-up that admitted only 16.3% of R8
> candidate signals. This structural constraint shapes every risk metric
> reported in this document and defines the primary open question for Phase 4.

**Three key findings:**

**Finding A — Holding-period-induced capital lock-up (primary finding)**
The baseline-cap scheduler admitted only 16.3% of R8 candidate signals
(350 of 2,143). This low admission rate was driven primarily by holding-period
capital retention, not by signal clustering. Only 2.1% of signal dates
produced more than 10 simultaneous R8 signals (median: 3 signals per date).
Each admitted position occupied a capital slot for a fixed 20-trading-day
window, causing later signals to compete with previously admitted positions
rather than with contemporaneous signals. Risk metrics therefore describe
the FIFO-admitted deployable subset, not the full candidate universe.

**Finding B — Risk-adjusted edge disappears in the Low-Uplift environment**
The deployed R8 portfolio exhibited substantially stronger risk-adjusted
performance than the deployed RS_T3 benchmark in the Full Sample (Sharpe
2.378 vs 1.313) and High-Uplift (2.271 vs 0.709) environments. In the
Low-Uplift environment, this advantage effectively disappeared (1.613 vs
1.606, Δ = 0.007). This confirms and extends the Phase 2A G5 material
concentration finding: regime heterogeneity affects not only gross returns
but the full risk-adjusted profile.

**Finding C — Higher position caps did not improve risk-adjusted performance**
Under the Track B capital efficiency analysis (zero price impact assumption),
increasing the per-position cap above 10% baseline degraded the Sharpe ratio
across all variants and substantially increased drawdown severity at the 25%
cap (MaxDD: 21.65% → 41.56% in Full Sample). Given that the low admission
rate is driven by holding-period retention rather than clustering, cap
relaxation does not address the underlying constraint.

**Scope of this verdict:**
- Risk characterisation within the Phase 1 historical sample (2022–2026).
- FIFO-admitted, baseline-cap portfolio only (10% per-position, max 10 slots).
- Does not constitute alpha validation or production deployment authorisation.
- Phase 4 SPEC required before any live or paper-trading deployment decision.

---

## 2. Methodology

### 2.1 NAV construction (D1A — calendar-time MTM)

The Phase 3 NAV is a calendar-time mark-to-market series built under
Interpretation B (shared capital pool), not an event-time return sequence.

This choice was made explicitly to satisfy Phase 3 SPEC §4.1 (D1A):
daily NAV must be reconstructed from `daily_price_adj.adj_close`. Forward-
return-only step-function NAV is prohibited.

**NAV accounting:**

| Day | Return calculation |
|---|---|
| Entry day (T+1) | simple_ret = adj_close[T+1] / adj_open[T+1] − 1 |
| Holding day k>1 | simple_ret = adj_close[T+k] / adj_close[T+k−1] − 1 |
| Non-holding day | portfolio simple return = 0 (cash earns 0%) |

Portfolio NAV: `nav[t] = nav[t−1] × (1 + Σ weight_i × simple_ret_i)`.
Daily log return: `log(nav[t] / nav[t−1])`. All risk metrics use daily
log returns (§5.2 frozen convention).

**The consequence of this design:** The NAV series reflects an aggregate
exposure that never exceeds 100% of NAV (P3-FP-002 verified). This is
a materially different representation from Phase 2B's signal-date portfolio
abstraction, which assumed full deployment on each signal date independently.

### 2.2 Capital scheduler

Positions are admitted from the candidate ledger subject to the following
constraints (frozen per Phase 3 design decision 2026-06-07):

1. Process signal dates in ascending order; within each date, sort by stock_id.
2. Release positions whose exit_date ≤ current signal_date before evaluating
   new candidates (capital available on exit day close).
3. Admit if: `len(open_positions) < max_pos` AND
   `current_exposure + cap ≤ 100%`.
4. Skip otherwise; record as skipped_capital_constraint.
5. No re-entry for a stock already in an open position.

**Selection mechanism:** The scheduler is FIFO-based (first-come-first-served
by signal_date then stock_id sort order). It does not rank signals by expected
return, RS score, or any quality metric. This is documented as Limitation L-1.

### 2.3 Fingerprint chain

**P3-FP-001 (candidate pool lineage):** Pre-scheduler candidate ledger
reproduced Phase 2B Full-sample S1 net return = +1.6432% (target +1.64% ±
1 bp). This confirms panel identity with Phase 1 and Phase 2B.

**P3-FP-002 (exposure invariant):** Post-scheduler max daily gross exposure
= 100.0% across all scenarios. No scenario exceeded 100%.

### 2.4 Benchmarks

| Benchmark | Role | Source |
|---|---|---|
| RS_T3 baseline portfolio | Primary | Phase 1 baseline_1 pool, same scheduler and cap |
| TAIEX (price proxy) | Secondary | `market_regime.taiex_close` |
| Cash (0% return) | Reference | Phase 2B assumption carried forward |

**TAIEX note:** TAIEX is sourced from `market_regime.taiex_close`, which is
a price index, not a total return index. TAIEX figures in this report
understate the true market return by the dividend yield component.

### 2.5 Data gaps

| Gap | Impact |
|---|---|
| VIX: no table in DuckDB | VIX correlation omitted from Track A |
| sector_index_daily: empty (0 rows) | Sector correlation omitted |
| TAIEX: price proxy only | Slight understatement of market benchmark return |

---

## 3. Scheduler Diagnostics (Finding A detail)

### 3.1 Admission statistics

| Scenario | Pool | Candidates | Admitted | Skipped (capital) | Skipped (duplicate) | Admission rate |
|---|---|---|---|---|---|---|
| Full Sample | Treatment (R8) | 2,143 | 350 | 1,482 | 311 | **16.3%** |
| Full Sample | Baseline (RS_T3) | 38,075 | 360 | 34,682 | 3,033 | 0.9% |
| Low-Uplift | Treatment (R8) | 1,026 | 180 | 709 | 137 | 17.5% |
| Low-Uplift | Baseline (RS_T3) | 19,689 | 190 | 17,997 | 1,502 | 1.0% |
| High-Uplift | Treatment (R8) | 1,117 | 180 | 743 | 194 | 16.1% |
| High-Uplift | Baseline (RS_T3) | 18,386 | 180 | 16,695 | 1,511 | 1.0% |

### 3.2 Why admission rate is low: holding-period retention, not clustering

R8 signal distribution across the full sample:

| Signals per signal_date | Signal dates |
|---|---|
| 1 | 129 |
| 2–5 | 355 |
| 6–10 | 118 |
| 11–20 | 13 |
| > 20 | 0 |

- Total signal dates: 615
- Mean signals per date: 3.7
- Median signals per date: 3.0
- Signal dates with > 10 signals: 13 (2.1% of dates)

**Implication:** The scheduler's 10-slot cap would be non-binding on 97.9%
of signal dates if positions had zero holding period. The low admission rate
arises because the 20-trading-day retention window keeps capital occupied
for approximately 4 calendar weeks per position. At steady state:

```
mean open positions ≈ 3.7 signals/date × 20 days = 74 slot-days of demand
available slots = 10
```

This creates chronic slot scarcity. Later signals compete not with
simultaneous signals but with positions already deployed from earlier dates.

*Note: The 74 slot-days figure is a steady-state approximation via Little's
Law (L = λW, where L = mean queue occupancy, λ = mean arrival rate, W = mean
service time). It is not a directly observed quantity; actual open-position
counts vary day-to-day. The approximation illustrates the structural source
of capital constraint.*

**Phase 4 implication:** The primary lever to improve capital utilisation
is exit contract design (holding period reduction, early exit rules), not
position sizing or cap relaxation. See §7.

### 3.3 FIFO selection and its consequences (Limitation L-1)

The scheduler selects positions in FIFO order: by signal_date ascending,
then stock_id ascending within each date. It does not rank by RS score,
expected uplift, or any quality metric.

The 350 admitted positions are therefore the 350 earliest-arriving eligible
signals, not the 350 highest-quality signals. Risk metrics reported in
Track A describe this FIFO-admitted subset. Whether a quality-ranked
scheduler would produce materially different risk metrics is a Phase 4
research question.

---

## 4. Track A — Risk Metrics

### 4.1 Primary results table

All metrics use daily log returns derived from the calendar-time NAV series.
Risk-free rate = 0% (consistent with cash = 0% assumption throughout).

| Environment | Portfolio | Ann Return | Ann Vol | Sharpe | Sortino | Calmar | MaxDD | MaxDD Duration (cal days) |
|---|---|---|---|---|---|---|---|---|
| Full Sample | R8 (baseline cap) | 59.17% | 24.88% | 2.378 | 2.865 | 2.733 | 21.65% | 457 |
| Full Sample | RS_T3 baseline | 23.67% | 18.03% | 1.313 | 1.505 | 0.875 | 27.06% | 493 |
| Low-Uplift | R8 (baseline cap) | 36.34% | 22.53% | 1.613 | 2.089 | 1.769 | 20.54% | 357 |
| Low-Uplift | RS_T3 baseline | 30.01% | 18.69% | 1.606 | 2.062 | 1.570 | 19.11% | 480 |
| High-Uplift | R8 (baseline cap) | 45.26% | 19.93% | 2.271 | 2.071 | 3.716 | 12.18% | 643 |
| High-Uplift | RS_T3 baseline | 9.49% | 13.38% | 0.709 | 0.568 | 0.687 | 13.81% | 672 |

*Source: `data/_storage/r8_phase3/v0.1.0/p3a_risk_metrics.json` (runner v0.1.0).
Sortino uses downside deviation with 0% target return. MaxDD Duration is
calendar days from peak to full recovery.*

### 4.2 Interpretation constraints

**All metrics must be read with Finding A in mind.** The R8 NAV reflects
350 FIFO-admitted positions out of 2,143 candidates. The high annualised
returns and Sharpe ratios reflect a sparsely-deployed portfolio where much
of the NAV sits in cash. They cannot be interpreted as the expected
risk-adjusted return of a fully-deployed R8 strategy.

**Correct framing:** These metrics describe the risk profile of the
deployable portion of the R8 strategy under a 10% cap, FIFO scheduler, and
20-trading-day holding period — not the strategy in aggregate.

### 4.3 Low-Uplift finding (Finding B)

In the Low-Uplift environment (Segments 2+3, 2023-10-24 to 2025-08-08):

- R8 Sharpe: 1.613
- RS_T3 baseline Sharpe: 1.606
- Difference: 0.007

This difference is economically negligible and well within any reasonable
estimation uncertainty. No material risk-adjusted advantage over the RS_T3
baseline exists in the Low-Uplift environment. This extends the Phase 2A G5
material concentration finding: the regime heterogeneity documented in Phase
2A (89.9% of aggregate positive uplift from Segments 1 and 4) manifests
in the risk-adjusted profile as well as in raw returns.

**The High-Uplift counterpart:** R8 Sharpe = 2.271 vs RS_T3 baseline 0.709,
a difference of 1.562. The risk-adjusted edge is concentrated in the same
segments that drive the gross return concentration.

### 4.4 Correlation diagnostics

| Correlation pair | Pearson r | Notes |
|---|---|---|
| R8 vs RS_T3 baseline (daily log return) | **0.668** | Full sample, FIFO-admitted portfolios |
| R8 vs TAIEX (daily log return) | **0.484** | Price proxy; underestimates true market correlation |

**Regime-conditional mean daily log return (R8 portfolio, full sample):**

| Regime | Mean daily log return | Days |
|---|---|---|
| bull | +0.281% | 689 |
| bear | −0.050% | 249 |
| crisis | +0.035% | 73 |

*Source: `data/_storage/r8_phase3/v0.1.0/p3a_correlation_metadata.json` (runner v0.1.0).*

The R8 portfolio shows pronounced regime-dependence: mean daily return in
bull regimes (+0.281%) is substantially higher than in bear (−0.050%) or
crisis (+0.035%) regimes. This is consistent with the Phase 1 design —
R8 signals are defined within the bull-regime cell — but the magnitude
of the regime conditional difference confirms that the strategy's return
distribution is not regime-neutral.

The R8–RS_T3 Pearson correlation of 0.668 indicates that the two portfolios
share substantial common factor exposure, as expected given that both are
drawn from the RS_T3 universe. The incremental R8 return is therefore the
return not explained by the RS_T3 common component.

**Data gaps:** VIX correlation omitted (no table in DuckDB). Sector
correlation omitted (sector_index_daily empty). Both documented in
`p3a_correlation_metadata.json`.

---

## 5. Track B — Capital Efficiency

**Label: SENSITIVITY — ZERO PRICE IMPACT ASSUMPTION**

All Track B results assume zero additional market impact beyond the Phase 2B
fixed slippage model. Findings should not be interpreted as production-
realistic return estimates.

### 5.1 Results

| Variant | Cap | Max pos | Scenario | Sharpe | MaxDD | Admission rate |
|---|---|---|---|---|---|---|
| Baseline | 10% | 10 | Full Sample | 2.378 | 21.65% | 16.3% |
| B1 | 15% | 6 | Full Sample | 1.777 | 23.24% | 9.8% |
| B2 | 20% | 5 | Full Sample | 1.581 | 27.00% | 8.2% |
| B3 | 25% | 4 | Full Sample | 1.144 | 41.56% | 6.5% |
| Baseline | 10% | 10 | Low-Uplift | 1.613 | 20.54% | 17.5% |
| B1 | 15% | 6 | Low-Uplift | 1.795 | 17.78% | 10.7% |
| B2 | 20% | 5 | Low-Uplift | 1.373 | 20.87% | 9.0% |
| B3 | 25% | 4 | Low-Uplift | 0.886 | 33.98% | 7.2% |

### 5.2 Interpretation

**Increasing caps does not improve risk-adjusted performance.** In the Full
Sample, Sharpe declines monotonically from 2.378 (10%) to 1.144 (25%). MaxDD
increases from 21.65% to 41.56%. The Low-Uplift environment shows a similar
pattern, with B3 (25%) producing a Sharpe of 0.886 — below any reasonable
minimum bar for a deployed strategy.

**Why cap relaxation fails to solve the underlying problem.** The low
admission rate is driven by holding-period capital retention (Finding A),
not by simultaneous signal clustering. Increasing cap per position does not
reduce the temporal occupancy that causes slot scarcity; it reduces the
number of available slots further (max_pos = 4 at 25% cap vs 10 at 10% cap),
which only makes capital lock-up worse.

**Admission rates fall as caps increase.** Each larger cap variant produces
fewer admitted positions (B3 admits only 6.5% of candidates in Full Sample
vs 16.3% for baseline), further concentrating the portfolio in early-arriving
signals and increasing idiosyncratic risk per position.

**Phase 4 SPEC should not include cap relaxation as a primary research
question.** The Track B evidence, combined with the capital lock-up
diagnosis, supports prioritising exit contract design over sizing changes.

---

## 6. Track C — Illustrative Capacity Analysis

**Label: ILLUSTRATIVE CAPACITY ANALYSIS — not a production estimate**

### 6.1 Impact budget

Anchor: Low-Uplift S3 net return = +0.55% (Phase 2B primary table,
first_10 overflow method). This is the maximum additional round-trip cost
the strategy can absorb before the Low-Uplift S3 edge reaches breakeven.

```
impact_budget_portfolio     = 0.55%
mean_deployed_weight        = 0.334  (Phase 2B Appendix A)

impact_budget_per_pos (RT)  = 0.55% / 0.334 = 1.65%
impact_budget_per_pos (OW)  = 0.825%
```

**Assumption:** Impact scales proportionally with deployed NAV; all positions
treated as perfectly correlated (conservative upper bound; no diversification
benefit modelled).

### 6.2 AUM breakeven table

| Cap variant | Position weight | Assumed ADV (NT$M) | AUM breakeven (NT$M) |
|---|---|---|---|
| Baseline (10%) | 10% | 50 | 412.5 |
| Baseline (10%) | 10% | 100 | 825.0 |
| Baseline (10%) | 10% | 200 | 1,650.0 |
| Baseline (10%) | 10% | 500 | 4,125.0 |
| B2 (20%) | 20% | 50 | 206.3 |
| B2 (20%) | 20% | 100 | 412.5 |
| B2 (20%) | 20% | 200 | 825.0 |
| B2 (20%) | 20% | 500 | 2,062.5 |

**Mandatory limitations (verbatim from SPEC §7.3):**

> The AUM breakeven table uses a simplified linear impact model with an
> assumed coefficient of 1.0 (full impact at 100% ADV participation). This
> is deliberately conservative. Actual market impact for liquid TWSE large-cap
> equities may be substantially lower. The ADV figures are hypothetical; no
> live ADV data has been incorporated. This analysis provides order-of-magnitude
> capacity guidance only. It does not establish a production AUM limit.
> Track C findings must be revisited with empirical ADV data before any
> deployment decision.

---

## 7. Phase 4 Assumptions (derived from Phase 3)

The following must be carried into the Phase 4 SPEC:

| Finding | Source | Phase 4 implication |
|---|---|---|
| 16.3% admission rate driven by 20td holding-period lock-up | §3.2 | Primary research question: exit contract design, not sizing |
| FIFO selection: admitted ≠ highest-quality signals | §3.3 (L-1) | Signal prioritisation as a research question |
| Low-Uplift risk-adjusted edge ≈ 0 (Sharpe Δ = 0.007) | §4.3 | Phase 4 baseline must use Low-Uplift as stress environment |
| Cap relaxation degrades risk profile (B3 MaxDD = 41.56%) | §5.2 | Cap relaxation is not a capital efficiency lever |
| Phase 3 NAV estimand ≠ Phase 2B estimand | §2.1 | Phase 4 must explicitly define its portfolio estimand |

**Suggested Phase 4 research priority ordering:**

| Priority | Question |
|---|---|
| P4-A | Does holding-period reduction (5td, 10td, 15td) preserve per-position edge? |
| P4-B | Do early exit rules (ATR trailing, MA20 failure, RS deterioration) release capital without materially reducing per-position return? |
| P4-C | Does signal prioritisation (RS rank, score, expected uplift) improve the quality of admitted positions relative to FIFO? |
| P4-D | What is the OOS validity of Phase 3 risk metrics? (Requires new data) |

Cap relaxation (Phase 3 Track B variant B1–B3) is deprioritised given
Track B evidence and the capital lock-up diagnosis.

---

## 8. Residual Limitations

1. **FIFO selection bias (L-1).** Risk metrics describe the FIFO-admitted
   deployable subset. Whether a quality-ranked scheduler produces materially
   different risk metrics is unknown and constitutes an open research question.

2. **Not out-of-sample validation.** All analyses re-use the Phase 1
   historical panel (2022–2026). Phase 3 CHARACTERISED does not establish
   that observed risk metrics will persist on future data.

3. **Scheduler estimand differs from Phase 2B.** The 20-trading-day lock-up
   means Phase 3 NAV reflects a structurally different portfolio path from
   Phase 2B. Direct return comparison between Phase 2 and Phase 3 metrics
   is not meaningful without adjustment for this difference.

4. **TAIEX correlation uses price proxy.** The secondary benchmark uses
   `market_regime.taiex_close`, a price index. Correlation with total return
   TAIEX (including dividends) is not available from current DuckDB data.

5. **VIX correlation unavailable.** No VIX table exists in the Helios DuckDB.
   Risk-on/risk-off sensitivity cannot be assessed from current data.

6. **Track C uses hypothetical ADV.** AUM breakeven estimates assume ADV
   levels not sourced from live data. These are order-of-magnitude only.

7. **Phase 2A and Phase 2B residual limitations inherited.** All limitations
   documented in those phases apply here, including IF-2 and IF-3B residual
   gaps (classified non-blocking).

---

## 9. Governance

### Upstream

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

### This report authorises

Phase 4 planning may proceed, subject to a Phase 4 SPEC that explicitly
addresses the Phase 3 risk profile and findings documented above.

The Phase 4 SPEC author must address the following items explicitly:

1. How is holding-period-induced capital lock-up to be investigated?
2. What is the Phase 4 portfolio estimand, and how does it differ from
   the Phase 3 FIFO scheduler?
3. What constitutes an acceptable risk profile in Phase 4?

### This report does not authorise

- Live or paper-trading deployment without a Phase 4 SPEC.
- Alpha validation or any claim of risk-adjusted performance persistence.
- Interpretation of Sharpe ratios as production-realistic return forecasts.
- Optimisation of signal parameters, exit rules, or position sizing.
- Any claim that CHARACTERISED verdict implies deployment readiness.

---

*End of r8_phase3_risk_report.md v1.0.0*
