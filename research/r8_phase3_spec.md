# R8 MA5 Momentum — Phase 3 Risk & Capital Efficiency Validation Specification

<!-- research/r8_phase3_spec.md -->
<!-- v0.1.2 — 2026-06-07 -->

**Status:** LOCKED — v0.1.2 (2026-06-07)
**Inherits from:**
- `research/r8_phase1_interim_findings.md` v1.0.0 (CONFIRMED)
- `research/r8_phase1_lifecycle_spec.md` v0.2.1 (LOCKED)
- `research/phase2_research_roadmap.md` v0.3.0 (LOCKED)
- `research/r8_phase2a_spec.md` v0.3.0 (LOCKED)
- `research/r8_phase2a_validation_report.md` v1.0.0 (STABLE)
- `research/r8_phase2b_spec.md` v0.1.2 (LOCKED)
- `research/r8_phase2b_feasibility_memo.md` v1.0.0 (FEASIBLE)
**Prerequisite:** Phase 2B FEASIBLE verdict (confirmed 2026-06-07)
**Authorises:** Phase 3 Risk & Capital Efficiency Validation only.
**Does not authorise:** Production deployment, live signal generation,
signal parameter optimisation, or any Phase 4 work.

---

## Changelog

| Version | Date | Change |
|---|---|---|
| v0.1.0 | 2026-06-07 | Initial SPEC DRAFT. D1–D4 decisions frozen. Three-track structure defined. |
| v0.1.1 | 2026-06-07 | D1: added D1A sub-decision mandating daily_price_adj MTM source; forward-return-only reconstruction prohibited. D4: added explicit impact scaling assumption. §6.1: corrected B1 max positions from 7 to 6 (floor(1/0.15)=6). §8.3: replaced binary VIABLE/NOT VIABLE gate with advisory risk characterisation; removed hard Sharpe/MaxDD thresholds. |
| v0.1.2 | 2026-06-07 | §5.2: added explicit frozen declaration that all risk metrics use daily log returns; mixed simple/log return usage prohibited. Track C renamed to "Illustrative Capacity Analysis" throughout; research question updated to reflect illustrative scope. No D-level parameters modified. |

---

## 1. Executive Summary

Phase 2B established that the bull-regime R8 uplift survives realistic
execution friction (**FEASIBLE** verdict). The remaining question is:

> Is the strategy viable from a risk-adjusted and capital-efficiency
> perspective, and how much capacity headroom exists before execution
> costs extinguish the edge?

Phase 3 answers three distinct questions, organised as independent tracks:

| Track | Research Question |
|---|---|
| **A — Risk Metrics** | What is the risk-adjusted return profile of the R8 portfolio? |
| **B — Capital Efficiency** | Does the 33% mean deployment represent an exploitable inefficiency? |
| **C — Illustrative Capacity Analysis** | At what AUM does additional market impact consume the remaining edge, under simplified assumptions? |

Phase 3 is a **risk validation and capital efficiency assessment**, not
alpha re-validation or deployment authorisation. Gross uplift and cost
structure are taken as given from Phase 2A and Phase 2B. The Phase 3
verdict governs whether a Phase 4 production SPEC may be initiated.

**What Phase 3 answers:**

- Risk structure: drawdown characteristics, Sharpe, Calmar, Sortino,
  correlation with market risk factors.
- Capital efficiency: impact of relaxing the 10% single-position cap.
- Capacity headroom: AUM-equivalent impact budget before Low-Uplift S3
  edge is extinguished, under simplified linear impact assumptions.

**What Phase 3 does not answer:**

- Whether R8 constitutes independent alpha (not established by this SPEC).
- Whether the strategy is suitable for live deployment (requires Phase 4 SPEC).
- Whether a different signal parameterisation would perform better.
- Whether gross uplift will persist on future data.

---

## 2. Inheritance from Phase 2B

### Key findings carried forward

| Finding | Value | Source |
|---|---|---|
| Full-sample net return (S1) | +1.64% | Phase 2B primary table |
| Low-Uplift net return (S1) | +0.82% | Phase 2B primary table |
| High-Uplift net return (S1) | +2.51% | Phase 2B primary table |
| Low-Uplift net return (S3) | +0.55% | Phase 2B primary table — capacity headroom anchor |
| Mean deployed NAV | 33.4% | Phase 2B Appendix A |
| Commission share of total cost drag | 75% at S1 | Phase 2B §5 |
| Overflow sensitivity | < 5 bps | Phase 2B §4 |
| Per-date portfolio gross return series | In Phase 2B runner memory | `simulate_portfolio()` |

### Mandatory Phase 3 assumptions (from Phase 2B §9)

1. Base-case evaluation environment is **Low-Uplift (Scenario B, S1)**,
   not the full-sample average. The +1.64% full-sample net is not assumed
   uniformly available.
2. Baseline position sizing is **10% per-position cap** (Phase 2B SPEC §5.1
   frozen). Track B sensitivity analysis uses this as the reference.
3. Cluster-day capacity risk is not yet quantified; Track C must provide a
   headroom estimate without requiring ADV data or price-impact models
   (per D4 decision, §4.4).
4. The first-10 deterministic overflow policy is used as the Phase 3
   baseline (Phase 2B §4 confirmed < 5 bps sensitivity).

---

## 3. Research Questions

**Track A:**
> What are the drawdown characteristics and risk-adjusted metrics of the
> R8 portfolio under full-sample and Low-Uplift environments?

**Track B:**
> If the 10% single-position cap is relaxed to 15%, 20%, or 25%, how does
> deployed NAV, gross portfolio return, and risk-adjusted performance change,
> assuming no price-impact degradation?

**Track C:**
> What is the maximum additional round-trip cost (impact budget) that can
> be absorbed before the Low-Uplift S3 net return reaches breakeven (0%),
> and what AUM-equivalent does this budget imply under simplified linear
> impact assumptions? This analysis is illustrative, not a production
> capacity estimate.

**Framing note:** All three tracks take the Phase 2B cost model and gross
uplift as inputs. Phase 3 does not re-estimate gross uplift or re-run
bootstrap inference. The estimand Δ_A3 is frozen from Phase 1.

---

## 4. Decisions

### D1: Calendar-Time NAV Construction (primary data representation)

**Decision:** Reconstruct a daily calendar-time NAV series from Phase 2B
per-date portfolio returns. All risk metrics are computed on this series.

**Rationale:** Signal-date returns are non-uniformly spaced in calendar
time. Risk metrics computed on an irregular series (e.g., signal-date
Sharpe) measure conditional opportunity quality, not deployable portfolio
risk. Because Phase 3 asks "what happens to real capital?", the relevant
domain is calendar time, not event time.

**NAV construction rules (frozen):**

| Day type | NAV change |
|---|---|
| Signal entry date | Position opens at T+1 adj_open |
| Holding window day | Mark-to-market using adj_close |
| Non-signal day (cash) | NAV change = 0 (cash earns 0%) |
| Signal exit date | Position closes at T+20td adj_close |

Positions opened on different signal dates may overlap; the aggregate
NAV on any day reflects all open positions weighted by their entry-date
allocation.

**Scope constraint:** The NAV series is a portfolio accounting
reconstruction, not a live execution simulation. Intraday dynamics,
partial fills, and margin requirements are out of scope.

**D1A — MTM data source (mandatory sub-decision):**

Daily NAV **must** be reconstructed from `daily_price_adj` (DuckDB), pulling
`adj_close[T+k]` for each trading day k = 0 … 20 within each holding window.
Forward-return-only reconstruction — where NAV stays flat during the holding
window and jumps at exit — is **prohibited**. The two approaches produce
materially different Sharpe, Sortino, MaxDD, and Recovery Time values;
using the step-function approximation would invalidate the Track A risk
characterisation.

Specifically prohibited pattern:

```python
# PROHIBITED — forward-return-only reconstruction
nav[entry_date:exit_date] = 0          # flat
nav[exit_date] += position_weight * fwd_return_20td
```

Required pattern:

```python
# REQUIRED — daily MTM from price series
for k in range(1, 21):
    trading_day_t = entry_date + k_trading_days
    daily_return = adj_close[trading_day_t] / adj_close[trading_day_t - 1] - 1
    nav[trading_day_t] += position_weight * daily_return
```

**Implementation note:** Phase 2B artifacts store only the 20td aggregate
return per signal, not the per-holding-day path. Phase 3 requires a new
data pull: for every (stock, entry_date) pair in the signal pool, retrieve
the full daily `adj_close` sequence for T+1 through T+20td from DuckDB.
This is a materially larger data access than Phase 2B and must be accounted
for in runner design.

### D2: Benchmark Definitions (frozen)

**Decision:**

| Benchmark | Role | Rationale |
|---|---|---|
| RS_T3 baseline portfolio | Primary | Phase 1 estimand counterfactual: RS_T3 ∩ ¬R8 ∩ bull ∩ nlu=0 |
| TAIEX Total Return Index | Secondary | Market-level context; standard reporting reference |
| Cash (0% return) | Reference | Consistent with Phase 2B undeployed capital assumption |

**Rationale:** The Phase 1 estimand is Δ_A3 = R8 ∩ RS_T3 minus RS_T3 only.
The true counterfactual for the R8 strategy is not the market index but
the RS_T3 basket held without the R8 overlay. Using TAIEX as the sole
benchmark would confound R8 alpha with RS_T3 factor exposure. TAIEX is
retained as a secondary benchmark for standard reporting and correlation
diagnostics.

**RS_T3 baseline NAV construction:** Apply the same partial-NAV model
(10% per-position, max 10 positions) to the Phase 1 baseline_1 pool
(RS_T3 ∩ ¬R8 ∩ bull ∩ nlu=0 dates), using adj_open[T+1] entry and
adj_close[T+20td] exit. This produces a comparable calendar-time NAV
series as the R8 portfolio benchmark.

### D3: Capital Efficiency Analysis Scope (Track B)

**Decision:** Cap sensitivity is included in Phase 3 as a standalone
sensitivity analysis under Track B. The Phase 3 **verdict is determined
solely by the 10% baseline cap**. Track B findings inform Phase 4 SPEC
scope but do not alter the Phase 3 verdict.

**Rationale:** The Phase 2B memo (Appendix A) explicitly raises the
capital efficiency question. With mean deployed NAV at 33.4%, the 10%
cap is effectively binding on 303/306 Low-Uplift dates. This represents
a structural deployment inefficiency that is material enough to warrant
analysis but too loosely bounded to anchor a verdict.

**Cap ladder (Track B, frozen):**

| Variant | Per-position cap | Max positions | Max deployed NAV | Note |
|---|---|---|---|---|
| Baseline (Phase 2B) | 10% | 10 | 100% | |
| B1 | 15% | 6 | 90% | `floor(1.0 / 0.15) = 6`; leaves 10% cash at full deployment |
| B2 | 20% | 5 | 100% | |
| B3 | 25% | 4 | 100% | |

**B1 rounding note:** `floor(1.0 / 0.15) = 6`, not 7. Seven positions at 15%
would require 105% NAV, which would need leverage. Max positions for B1 is
therefore 6 (maximum deployed NAV = 90%). This leaves a permanent 10% cash
residual when N ≥ 6, which is slightly less capital-efficient than B2 or B3 at
full deployment. This must be reported as-is in Track B; do not normalise
weights to reach 100%.

**Scope constraint:** Track B assumes zero price-impact degradation at
larger per-position sizes. This assumption must be stated explicitly in
the Phase 3 report. Track B findings are labelled
**SENSITIVITY (ZERO PRICE IMPACT)** and must not be interpreted as
production-realistic return estimates.

### D4: Illustrative Capacity Analysis (Track C)

**Decision:** Use AUM breakeven analysis (inverse approach) rather than
a price-impact model. No ADV data, participation-rate assumptions, or
Almgren-Chriss parameters are required.

**Rationale:** A square-root or linear market-impact model requires
empirical estimation of the impact coefficient k, which cannot be
derived from current Helios data (no order-level ADV data, no
participation-rate observations). Introducing a model with an
unestimated free parameter produces false precision. The inverse
approach is conservative and honest: it answers "how much headroom is
available?" without claiming to know "how fast does impact accumulate?"

**Track C methodology:**

Step 1 — Compute impact budget:

```
impact_budget = Low-Uplift S3 net return
              = +0.55%   (Phase 2B primary table, first_10)
```

This is the maximum additional round-trip cost the strategy can absorb
before Low-Uplift S3 reaches breakeven (0% net).

Step 2 — Translate to per-position impact:

```
per_position_impact_budget = impact_budget / mean_deployed_weight
                           = 0.55% / 0.334
                           ≈ 1.65% additional round-trip per position
```

Step 3 — AUM breakeven under a simplified linear impact assumption:

```
impact(position) = impact_coefficient × (position_size_TWD / ADV_TWD)
```

Under the simplest linear model, impact_coefficient = 1.0 (conservative):

```
AUM_breakeven = impact_budget_per_position × ADV_TWD / position_weight
```

This is computed as a sensitivity table across assumed ADV levels
(NT$50M, NT$100M, NT$200M, NT$500M per stock), not as a point estimate.
The table shows: "given stock ADV of X, the R8 portfolio can scale to Y
AUM before additional impact consumes the Low-Uplift S3 headroom."

**Explicit limitations (must appear in Phase 3 report):**

- Linear impact (coefficient = 1.0) is a conservative assumption; actual
  impact may be lower for liquid large-cap Taiwan equities.
- ADV figures are hypothetical; Phase 3 does not pull live ADV data.
- The analysis is a first-order approximation, not a production capacity
  model. It provides order-of-magnitude guidance only.
- Track C does not establish a production AUM limit.

---

## 5. Track A — Risk Metrics

### 5.1 NAV series construction

Construct two calendar-time NAV series from the Phase 2B per-date
portfolio return data:

| Series | Description |
|---|---|
| R8 portfolio NAV | Phase 2B `simulate_portfolio()` output, reconstructed as daily NAV |
| RS_T3 baseline NAV | Identical methodology applied to Phase 1 baseline_1 pool |

Both series must share the same calendar-day index (2022-03-22 to
2026-06-04). Days with no open positions: NAV unchanged (cash).

### 5.2 Mandatory metrics

**Return type (frozen):** All risk metrics in this section shall be computed
on **daily log returns** derived from the calendar-time NAV series:

```python
daily_log_return[t] = log(NAV[t] / NAV[t-1])
```

This definition applies uniformly to annualised volatility, Sharpe,
Sortino, and all correlation computations. Mixing log returns for some
metrics and simple returns for others is prohibited. The annualised return
formula uses simple compounding (geometric), as defined in the return
metrics table below; this is consistent with log returns for individual
days — it is not a contradiction.

Compute for each combination of {Full Sample, Low-Uplift, High-Uplift}
× {R8 portfolio, RS_T3 baseline}:

**Return metrics:**

| Metric | Definition | Notes |
|---|---|---|
| Annualised return | `(NAV_end / NAV_start)^(252 / calendar_days) − 1` | Uses 252 trading days per year |
| Annualised volatility | `std(daily_returns) × sqrt(252)` | Daily returns = log(NAV_t / NAV_t-1) |

**Risk-adjusted metrics:**

| Metric | Definition | Notes |
|---|---|---|
| Sharpe ratio | `(annualised_return − 0%) / annualised_volatility` | Risk-free rate = 0% (consistent with cash = 0% assumption) |
| Sortino ratio | `annualised_return / downside_deviation` | Downside deviation uses daily returns below 0% target |
| Calmar ratio | `annualised_return / abs(max_drawdown)` | See drawdown definition below |

**Drawdown metrics:**

| Metric | Definition |
|---|---|
| Maximum drawdown | `max over t of (peak_NAV_up_to_t − NAV_t) / peak_NAV_up_to_t` |
| Average drawdown | Mean of all individual drawdown troughs relative to preceding peak |
| Maximum drawdown duration | Calendar days from peak to subsequent NAV recovery to prior peak |

**Scope constraint:** All metrics are computed in-sample on the Phase 1
historical panel. They are descriptive risk characteristics, not
forward-looking risk forecasts. Out-of-sample risk validity is not
established by Phase 3.

### 5.3 Correlation diagnostics

Compute for the R8 portfolio daily return series:

| Correlation | Counterpart series | Notes |
|---|---|---|
| R8 vs RS_T3 baseline | Daily returns | Primary benchmark correlation |
| R8 vs TAIEX | Daily TAIEX total return | Secondary benchmark |
| R8 vs VIX | Daily VIX level change | Risk-on/risk-off sensitivity |
| R8 vs market regime | Bull/bear/neutral indicator from `market_regime` table | Regime-conditional mean |

TAIEX and VIX data must be sourced from the existing Helios data
infrastructure. If either series is unavailable or has coverage gaps,
this must be documented and the affected correlation omitted (not
imputed). Do not use external data sources not already in the DuckDB.

### 5.4 Gate criteria (Track A)

Track A does not have a binary PASS/FAIL gate. It produces a risk
characterisation table. The Phase 3 verdict requires:

- All mandatory metrics computed and reported for at least Full Sample
  and Low-Uplift environments.
- No metric omitted without documented justification.
- Correlation diagnostics completed or gaps explicitly documented.

A Track A finding of extreme drawdown (e.g., max drawdown > 50% under
Low-Uplift) is a valid and important result — it narrows Phase 4 scope,
it does not invalidate the Phase 3 analysis.

---

## 6. Track B — Capital Efficiency

### 6.1 Methodology

Rerun `simulate_portfolio()` (Phase 2B runner) for each cap variant
(Baseline, B1, B2, B3) under:

- Scenario: Full Sample and Low-Uplift (primary stress environment)
- Slippage: S1 (realistic) only — B variants are sensitivity, not stress tests

Apply the same position sizing semantics as Phase 2B SPEC §5.1:
`weight_i = min(1/N, cap)` where cap is the variant-specific cap.
For B1 (15% cap), max positions = floor(1.0 / 0.15) = 6 (not 7; avoid
over 100% deployment). Document this rounding decision.

Reconstruct calendar-time NAV for each cap variant (per D1 methodology).
Compute the full Track A metric set for each variant.

### 6.2 Output table (Track B)

| Variant | Cap | Max pos | Mean deployed NAV | Gross | Net (S1) | Sharpe | Calmar | MaxDD |
|---|---|---|---|---|---|---|---|---|
| Baseline | 10% | 10 | ~33% | ... | ... | ... | ... | ... |
| B1 | 15% | 6 | ... | ... | ... | ... | ... | ... |
| B2 | 20% | 5 | ... | ... | ... | ... | ... | ... |
| B3 | 25% | 4 | ... | ... | ... | ... | ... | ... |

Mean deployed NAV is the empirical mean across signal dates for the
Low-Uplift scenario (primary stress environment).

### 6.3 Scope constraint

All Track B results must carry the label:
**"SENSITIVITY — ZERO PRICE IMPACT ASSUMPTION"**

Track B answers: "what would happen if position size were larger, holding
all else equal?" It does not answer: "is it safe to trade larger sizes?"
That question requires Track C and, ultimately, live execution data.

The Phase 3 verdict is based on the Baseline (10% cap) only.

---

## 7. Track C — Illustrative Capacity Analysis

### 7.1 Impact budget computation

**Anchor:** Low-Uplift S3 net return = +0.55% (Phase 2B primary table,
first_10 overflow method).

```python
impact_budget_portfolio = 0.0055          # 55 bps total portfolio
mean_deployed_weight     = 0.334           # Phase 2B Appendix A
mean_signals_per_date    = 3.35            # Phase 2B Appendix A

# Per-position budget (round-trip), assuming impact scales with weight
impact_budget_per_position = impact_budget_portfolio / mean_deployed_weight
# ≈ 1.65%  (165 bps round-trip per position)
```

**Assumption (explicit):** The division by `mean_deployed_weight` assumes
that additional market impact scales proportionally with deployed NAV and
affects all positions uniformly (i.e., positions are treated as perfectly
correlated with respect to impact). This is a conservative simplification:
in practice, impact across a diversified basket of independent positions may
be lower due to averaging effects. This assumption must appear alongside the
per-position budget figure in the Phase 3 report. Readers should interpret
the 165 bps estimate as an upper bound on per-position headroom, not a
precise allocation.

### 7.2 AUM breakeven table

For a range of assumed per-stock ADV values, compute:

```
AUM_breakeven =
    (impact_budget_per_position / 2)    # one-way impact budget
    × ADV_TWD                           # assumed ADV in NT$
    / position_weight                   # 10% of portfolio NAV
```

Tabulate:

| Assumed ADV (NT$M) | Per-position size at AUM X (NT$M) | Breakeven AUM (NT$M) |
|---|---|---|
| 50 | ... | ... |
| 100 | ... | ... |
| 200 | ... | ... |
| 500 | ... | ... |

The table is computed for two cap assumptions: Baseline (10% cap) and
B2 (20% cap, from Track B).

### 7.3 Limitations statement (mandatory)

The following statement must appear verbatim in the Phase 3 report,
Track C section:

> The AUM breakeven table uses a simplified linear impact model with an
> assumed coefficient of 1.0 (full impact at 100% ADV participation). This
> is deliberately conservative. Actual market impact for liquid TWSE large-cap
> equities may be substantially lower. The ADV figures are hypothetical; no
> live ADV data has been incorporated. This analysis provides order-of-magnitude
> capacity guidance only. It does not establish a production AUM limit.
> Track C findings must be revisited with empirical ADV data before any
> deployment decision.

---

## 8. Output Specification

### 8.1 Deliverable

**Phase 3 Risk & Capital Efficiency Report**
(`research/r8_phase3_risk_report.md`)

Sections:

1. Executive Summary (verdict + headline numbers)
2. NAV series construction (methodology, D1 decisions)
3. Track A — Risk Metrics results table + correlation diagnostics
4. Track B — Capital Efficiency sensitivity table (zero-impact label)
5. Track C — Illustrative Capacity Analysis (AUM breakeven table + limitations)
6. Verdict Assessment
7. Phase 4 Assumptions (derived from Phase 3)
8. Residual Limitations
9. Governance

### 8.2 Artifacts

| Artifact | Path | Content |
|---|---|---|
| R8 NAV series | `data/_storage/r8_phase3/v0.1.0/p3a_nav_series.parquet` | Daily NAV for R8 and RS_T3 baseline |
| Risk metrics | `data/_storage/r8_phase3/v0.1.0/p3a_risk_metrics.json` | All Track A metrics by environment |
| Correlation results | `data/_storage/r8_phase3/v0.1.0/p3a_correlation.parquet` | Daily return pairs + rolling correlations |
| Cap sensitivity | `data/_storage/r8_phase3/v0.1.0/p3b_cap_sensitivity.parquet` | Track B metrics by cap variant |
| AUM breakeven | `data/_storage/r8_phase3/v0.1.0/p3c_aum_breakeven.json` | Track C breakeven table |
| Manifest | `data/_storage/r8_phase3/v0.1.0/manifest.json` | Artifact inventory + commit hash |

### 8.3 Verdict structure

Phase 3 produces an **advisory risk characterisation**, not a binary
governance gate based on hard metric thresholds.

**Rationale:** The Phase 1 → 2A → 2B research chain has consistently
used data-derived conclusions (bootstrap inference, stability gates,
cost modelling). Introducing subjective Sharpe or MaxDD thresholds as
governance triggers would misrepresent Phase 3 findings as statistically
grounded when they are not. A Sharpe of 0.48 vs 0.52 does not represent
a meaningful empirical distinction given the sample size and regime
heterogeneity documented in Phase 2A. Hard thresholds would also
create adverse incentives: a researcher aware of the threshold could
adjust methodology to clear it rather than to produce an honest
characterisation.

**Phase 3 verdict categories (advisory):**

| Verdict | Meaning |
|---|---|
| **CHARACTERISED** | All mandatory Track A metrics computed; Phase 4 SPEC may proceed with risk profile as input |
| **INCOMPLETE** | One or more mandatory Track A metrics could not be computed; Phase 4 blocked until gaps resolved |

The CHARACTERISED verdict does not make a positive or negative
judgement on the risk profile. It asserts that the risk structure
has been measured and documented with sufficient completeness for
Phase 4 to make an informed deployment decision.

**Phase 4 SPEC responsibility:** The Phase 4 SPEC author reviews the
Phase 3 risk profile and makes an explicit documented decision about
whether the observed Sharpe, MaxDD, and drawdown characteristics are
acceptable for the intended deployment scale and risk budget. That
decision belongs in Phase 4, not in Phase 3.

**Structural risk findings that must be highlighted (non-blocking
but mandatory disclosure):**

If the Phase 3 analysis finds any of the following, they must appear
prominently in the Executive Summary and must be explicitly addressed
in the Phase 4 SPEC:

- Annualised Sharpe < 0 under Low-Uplift (Baseline cap)
- Maximum drawdown > 50% of deployed NAV under any environment
- Sharpe under Low-Uplift materially lower than under High-Uplift,
  with no structural explanation

These are material findings requiring explicit Phase 4 acknowledgement,
not automatic blockers.

A CHARACTERISED verdict does not authorise Phase 4 deployment.
It authorises Phase 4 planning with the risk profile as a documented input.

---

## 9. Runner Specification

### 9.1 Entry point

```
scripts/run_phase3_analysis.py
```

Version: v0.1.0 (to be implemented)

### 9.2 Inputs

| Input | Source |
|---|---|
| Phase 2B per-date portfolio returns | Phase 2B runner `simulate_portfolio()` — rerun or load artifact |
| Phase 1 baseline_1 date pool | DuckDB `data/_storage/helios.duckdb` |
| TAIEX daily returns | DuckDB (existing table, if available) |
| VIX daily level | DuckDB (existing table, if available) |
| Market regime series | DuckDB `market_regime` table |

Phase 2B per-date portfolio returns must be reproducibly regenerated
from Phase 2B runner (commit 2d9f9c5) using the identical panel and
parameters. The runner must verify the Phase 2B fingerprint
(Full-sample S1 net = +1.64% ± 1 bp) before proceeding.

### 9.3 Dependencies

No new data infrastructure is required. All inputs exist within the
Helios DuckDB. If TAIEX or VIX tables are absent, Track A correlation
diagnostics for those series are skipped and documented as data gaps.

---

## 10. Scope Constraints

### Explicitly out of scope

The following are excluded from Phase 3. Inclusion without a SPEC
amendment constitutes a governance violation:

- Re-estimation of gross uplift or bootstrap inference on Δ_A3.
- Signal parameter optimisation.
- Dynamic position sizing (Kelly, volatility-targeting, factor hedging).
- Live or paper-trading execution.
- Bearish signal evaluation.
- Forward-looking risk forecasts.
- Statistical significance testing of risk metric differences across
  environments (would require out-of-sample data not present in panel).
- Production ADV modelling or empirical market-impact estimation.
- Any claim that CHARACTERISED verdict establishes forward-looking alpha.

### Relationship to Phase 2B

Phase 3 does not re-validate Phase 2B findings. Net returns and cost
structure are taken as given. Phase 3 is not permitted to modify the
Phase 2B cost model, slippage scenarios, or position sizing baseline.

---

## 11. Governance

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

### Downstream authorisations

| Phase | Authorised by | Requires |
|---|---|---|
| Phase 3 analysis | This SPEC | — |
| Phase 4 (production deployment prep) | Phase 3 CHARACTERISED verdict | Phase 4 SPEC (must explicitly address Phase 3 risk profile) |

An INCOMPLETE verdict blocks Phase 4 until the missing metrics are
resolved via a SPEC amendment. A CHARACTERISED verdict authorises Phase 4
planning; the Phase 4 SPEC author bears responsibility for evaluating
whether the observed risk profile is acceptable.

### Amendment policy

This SPEC may be amended by a new versioned document. Silent edits are
not permitted. Changes to D1 (NAV construction rules), D2 (benchmark
definitions), D3 (cap ladder), D4 (Track C methodology), §8.3 verdict
thresholds, or §5.2 mandatory metrics require a SPEC version bump with
documented rationale. The amendment must note what analysis had already
been completed under the prior version.

---

## 12. What Phase 3 Does Not Establish

Regardless of verdict:

- That R8 constitutes independent alpha net of factor exposures.
- That the strategy is suitable for live deployment.
- That historical risk metrics will persist in future periods.
- That Track B cap relaxation is safe to implement without live execution
  data.
- That Track C AUM estimates are production-accurate.
- That a CHARACTERISED verdict authorises Phase 4 deployment without a new SPEC.
- That an INCOMPLETE verdict invalidates Phase 1, 2A, or 2B findings.

---

*End of r8_phase3_spec.md v0.1.2*
