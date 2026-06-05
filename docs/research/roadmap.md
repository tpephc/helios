# Helios Research Roadmap

Last updated: 2026-06-03

---

## Governance Principle

Research sequencing is strictly enforced:
Falsify
↓
Verify incremental information
↓
Build feature
↓
Build strategy
↓
Production
Prohibited: build framework first, then search for alpha.

---

## Research Invariants

All research in this roadmap must satisfy the following invariants.
Violation of any invariant is grounds for immediate rejection.

1. **Per-horizon spacing**: forward return windows must not overlap within
   the same event cohort.
2. **PIT feature construction**: all features must be computed using only
   information available on `signal_date`. No future constituent information.
3. **Lag-1 environment features**: environment features must use
   `feature_date = signal_date - 1 trading day`. `breadth_t` is prohibited.
4. **Forward-only joins**: feature tables may only be joined on dates ≤
   `signal_date`.
5. **No survivorship bias**: market breadth and industry breadth must be
   computed over the universe as it existed on `signal_date`, not over
   today's surviving constituents. Using 2026 survivors to compute 2021
   breadth is a hard error.
6. **Null benchmark required**: every environment cell result must be
   reported relative to (a) universe baseline, (b) RS_T3 alone, and
   (c) RS_T3 + Dist_T1 + Beta. Absolute returns without a benchmark
   are not interpretable.

---

## Confirmed Alpha (Phase 0 + Phase A)

The only alpha source with robust empirical support to date:
RS Persistence + Beta + Pullback Timing (dist < 0)
Best confirmed cell:
RS_T3 (beta_adj_rs_20d, top tercile cross-sectionally)

Dist_T1 (close < MA20, i.e. dist_above_ma20_atr < 0)
Beta_T3 (beta_60, top tercile)
Plain-language interpretation:
- RS_T3:   stock is in top 1/3 of market by recent relative performance
- Dist_T1: strong stock has pulled back below MA20 (healthy retracement)
- Beta_T3: prioritise high-elasticity names within the strong cohort

This approximates Trend Following + Pullback Entry, not Breakout Chase.
Typical names: semiconductors, AI, thermal management, high-growth electronics.

---

## Completed

- [x] Phase 0: Feature outcome baseline
- [x] Phase A: Trend quality (distance/slope/spread) — mostly RS proxy
- [x] Per-horizon spacing fix (v4)
- [x] Distance refinement → pullback entry confirmed
- [x] Phase A closeout: best confirmed cell = RS_T3 + Dist_T1 + Beta_T3

---

## Active Research

### R8 — MA5 Momentum Pullback/Reclaim

Status: Phase 1 infrastructure complete, findings PROVISIONAL
Constraint: all findings provisional pending P1-DATA IF-1 remediation

Phase 1 artifacts (data/_storage/r8_phase1/):
- r8_events.parquet          (8430 events)
- r8_forward_returns.parquet (ret_1/3/5/10/20d, entry anchor T+1 open)
- r8_lifecycle_metrics.parquet
- r8_benchmarks.parquet      (Benchmark A/B/C, regime-stratified)
- r8_phase1_canonical.parquet
- r8_phase1_manifest.json    (AC results, bootstrap config, provenance)

Key provisional statistics:
- Benchmark C (R8 within RS_T3): ret_20d mean = +6.84%
- Benchmark A (RS_T3 Hold):      ret_20d mean = +2.63%
- n_eff = 396.2 (date-level moving block bootstrap, block=5td, n=10000)

Next: Phase 1 analysis notebook / report after P1-DATA remediation.

---

## Pending Research Pipeline

Full sequence:
SA-ENV-Prep  (industry mapping)
↓
SA-ENV Stage 0  (environment falsification)
↓ PASS
Stage 1  (breadth research)
↓ PASS
Stage 2A  (revenue availability audit)
↓ PASS
Stage 2  (revenue drift)
↓ PASS
Stage 3  (industry RS)
↓ PASS
Stage 4  (institutional flow)
↓ PASS
Future: cross-sectional ranking
↓
Production candidate

---

### SA-ENV-Prep — Industry Mapping

Prerequisite for SA-ENV Stage 0 industry breadth features.

Problem: `bullish_features` has no industry field. Historical PIT industry
mapping does not currently exist in the DB. Without it, industry breadth
cannot be computed reproducibly.

Deliverable: `data/reference/industry_mapping.parquet`

Schema:
```python
stock_id        # str
industry_code   # str
industry_name   # str
effective_date  # date — PIT: the date from which this mapping is valid
```

Acceptance criteria:
- Covers all symbols in `daily_price_adj` panel
- PIT: no future industry reclassification applied retroactively
- Source documented with provenance

---

### SA-ENV Stage 0 — Environment Feature Falsification Pack

Version: SA-ENV-0.1
Status: NOT STARTED — first priority after P1-DATA remediation and
SA-ENV-Prep complete

**Objective:** Answer before investing weeks of engineering:

> Do Environment Features provide incremental information beyond RS_T3?

**Scope:**

Market Breadth features:
- market_pct_above_ma20_lag1
- market_pct_above_ma50_lag1
- market_breadth_delta_5d

Industry Breadth features (requires SA-ENV-Prep):
- industry_pct_above_ma20_lag1
- industry_pct_above_ma50_lag1
- industry_breadth_delta_5d

Out of scope for Stage 0: Industry RS, Revenue, Institutional Flow,
Leader-Laggard.

**Research Questions:**
- Q1: Does RS_T3 fail in Low Market Breadth environments?
- Q2: Does RS_T3 fail during Market Breadth Deterioration?
- Q3: Does RS_T3 + Dist_T1 + Beta_T2/T3 fail in Low Market Breadth?
- Q4: Does RS_T3 + Dist_T1 + Beta_T2/T3 fail during Breadth Deterioration?
- Q5: Does RS_T3 fail in Low Industry Breadth?
- Q6: Does RS_T3 + Dist_T1 + Beta_T2/T3 fail in Low Industry Breadth?

**Required baselines (Research Invariant #6):**

Every environment cell must be reported against all three baselines:
```python
BASELINES = [
    "universe",          # all stocks, no filter
    "RS_T3",             # RS filter only
    "RS_T3+Dist_T1+Beta" # confirmed best cell
]
```
Absolute returns without baseline comparison are not acceptable.

**Data governance:**
- All breadth features: feature_date = signal_date − 1 trading day
- Survivorship-free: universe denominator = constituents on signal_date
- Breadth calculation: equal weight (market-cap weighting prohibited)

**Breadth calculation:**
```python
# Market (survivorship-free universe on signal_date)
market_pct_above_ma20 = count(close > ma20) / count(universe_on_signal_date)
market_breadth_delta_5d = breadth_t_minus_1 - breadth_t_minus_6

# Industry (requires industry_mapping.parquet, PIT join)
industry_pct_above_ma20 = groupby(industry_on_signal_date).mean(close > ma20)
industry_breadth_delta_5d = industry_breadth_t_minus_1 - industry_breadth_t_minus_6
```

**Outcomes:** forward_return_5d, forward_return_10d, forward_return_20d

**Metrics:** median_return, trimmed_mean, hit_rate

**Decision rule:**
- Primary:    directional consistency across 5d/10d/20d
- Secondary:  median lift and hit-rate lift vs baselines
- Exploratory: bootstrap confidence intervals

**Promotion criteria (PASS):**
Environment feature shows directional consistency across 5d/10d/20d AND
median / hit-rate improvement is sustained relative to all three baselines.

**Fail path:** If Stage 0 FAIL → retire breadth research entirely, proceed
directly to Stage 2A (Revenue Availability Audit).

**Deliverables:**
- research/environment_falsification.py
- research/outputs/environment_falsification.csv
- docs/research/environment_falsification_findings.md

**Recommended first action:**
```bash
git checkout -b research/environment-falsification
```

---

### Stage 1 — Breadth Research

Prerequisite: SA-ENV Stage 0 PASS

Objective: Verify whether Breadth can serve as a production filter.

Candidate features:
```python
# Market
market_pct_above_ma20, market_pct_above_ma50, advance_decline_ratio

# Industry
industry_pct_above_ma20, industry_pct_above_ma50, industry_new_high_ratio
```

Research question: Does RS_T3 + Dist_T1 + Breadth outperform RS_T3 + Dist_T1
across all three baselines?

Deliverable: research/breadth_interaction_study.py

---

### Stage 2A — Revenue Availability Audit

Prerequisite: Stage 1 PASS or SA-ENV Stage 0 FAIL (direct path)

**This stage must complete before any revenue drift research begins.**

Problem: Taiwan monthly revenue announcements arrive on varying dates
(1st, 5th, 10th of following month). The field `revenue_date` is not
sufficient. Revenue drift research requires `announcement_trading_date` —
the first trading day on which the revenue figure was publicly available.

Without this, any revenue-based signal is contaminated by lookahead bias.

Objective: Answer:
> Can Helios obtain reliable announcement availability timestamps for
> monthly revenue?

Acceptance criteria:
- `announcement_trading_date` can be sourced and verified for a sample
  of at least 50 stock-month pairs
- Source is reproducible (not manual one-off)

**If FAIL: Revenue Research Blocked. Do not proceed to Stage 2.**

Deliverable: docs/research/revenue_availability_audit.md

---

### Stage 2 — Revenue Drift Study

Prerequisite: Stage 2A PASS

Objective: Verify whether Monthly Revenue provides information beyond
price factors.

Research question: Is there return drift in the 1d/3d/5d window after
revenue announcements?

Features: revenue_yoy, revenue_mom, revenue_yoy_acceleration

Constraint: verify Revenue standalone first. Do not study RS × Revenue
interaction until standalone edge is confirmed.

Deliverable: research/revenue_drift_study.py

---

### Stage 3 — Industry RS

Prerequisite: Breadth confirmed effective (Stage 1 PASS)

Objective: Verify whether Industry RS provides information independent of
Stock RS.

Features: industry_return_20d, industry_return_60d, industry_rs_20d,
industry_rs_60d

Constraint: if Industry RS = Stock RS proxy → retire immediately.

Deliverable: research/industry_rs_study.py

---

### Stage 4 — Institutional Flow

Prerequisite: Breadth + Revenue + Industry RS all completed

Priority order: Investment Trust first, Foreign second.

Allowed features: trust_net_buy_20d, trust_ownership_change

Prohibited: N-day buy streak features (3d/5d/10d) unless pre-registered.
Rationale: parameter shopping risk.

---

### Phase B — Bearish Research

Status: deferred (no change from prior roadmap)

- Bearish interaction study (RS_T1 × dist_below × beta)
- Bounce fade validation (RS_T1 + above MA20)
- RS_T1 trap analysis
- Production screener: find_bearish_bounce_fade.py

---

## Future Research (not scheduled)

### Cross-Sectional Ranking

Natural evolution toward Helios v2. After bucket studies confirm which
factors carry independent alpha, the next step is composite scoring:

```python
score = w1 * rs_rank + w2 * breadth_rank + w3 * beta_rank
```

Then compare Top-N portfolios (10 / 20 / 50) vs bucket baselines.

Not scheduled. Prerequisites: Stages 1-4 complete with confirmed edges.

---

## Success Definition

If SA-ENV Stage 0 PASS:

Next-generation Helios core framework:
RS Persistence + Pullback Timing + Beta + Environment Filter
If SA-ENV Stage 0 FAIL:

Breadth research retired. Proceed directly to Stage 2A.
Weeks of engineering saved by falsification-first discipline.

---

## Dropped

- [x] ~~Absorption refinement~~ (overturned by v4 spacing fix)
- [x] ~~Compression × RS~~ (no edge)
- [x] ~~Volume breakout × RS~~ (no edge)
