# R8 MA5 Momentum — Phase 2B Execution Bridge Specification

<!-- research/r8_phase2b_spec.md -->
<!-- v0.1.2 — 2026-06-07 -->

**Status:** LOCKED — v0.1.2 (2026-06-07)
**Inherits from:**
- `research/r8_phase1_interim_findings.md` v1.0.0 (CONFIRMED)
- `research/r8_phase1_lifecycle_spec.md` v0.2.1 (LOCKED)
- `research/phase2_research_roadmap.md` v0.3.0 (LOCKED)
- `research/r8_phase2a_spec.md` v0.3.0 (LOCKED)
- `research/r8_phase2a_validation_report.md` v1.0.0 (STABLE)
**Prerequisite:** Phase 2A STABLE verdict (confirmed 2026-06-07)
**Authorises:** Phase 2B execution bridge analysis only.
**Does not authorise:** Production deployment, live signal generation,
alpha validation, portfolio optimisation, or Phase 2C work.

---

## Changelog

| Version | Date | Change |
|---|---|---|
| v0.1.0 | 2026-06-07 | Initial SPEC LOCKED. D1–D3 decisions frozen. Commission and slippage independently specified. Three mandatory concentration scenarios frozen. |
| v0.1.1 | 2026-06-07 | Weight formula clarified to `min(1/N, 10%)` (removes redundant single-position cap constraint). Verdict names changed TRADEABLE→FEASIBLE, NOT TRADEABLE→NOT FEASIBLE to avoid deployment-readiness misreading. No D1–D3 parameters modified. |
| v0.1.2 | 2026-06-07 | Position sizing semantics clarified: `min(1/N, 10%)` is a per-position deployment budget (partial-NAV model). Portfolio gross = sum of NAV-weighted position returns; event gross mean retained as reference column. No D1–D3 parameters modified. |

---

## 1. Executive Summary

Phase 2A established that the bull-regime R8 uplift is **temporally robust**
(STABLE verdict). The remaining question is:

> Does the STABLE uplift survive realistic execution friction under both
> high-uplift and low-uplift environments?

Phase 2B translates Phase 2A's measurement findings into execution-adjusted
PnL estimates. It is an **execution feasibility assessment**, not a
signal re-validation or portfolio optimisation exercise.

**What Phase 2B answers:**

- How much of the gross uplift survives after commission and slippage?
- Is the net return positive under realistic cost assumptions?
- Does the answer change materially between high-uplift and low-uplift
  environments (as identified in Phase 2A)?

**What Phase 2B does not answer:**

- Whether R8 constitutes independent alpha (requires Phase 3 SPEC).
- Whether the strategy is suitable for live deployment.
- Whether a different signal parameterisation would perform better.

---

## 2. Inheritance from Phase 2A

### Key findings carried forward

| Finding | Value | Source |
|---|---|---|
| Full-sample Δ_A3 (20td) | +1.92% gross | Phase 2A fingerprint |
| High-uplift environment (Seg 1+4 mean 20td) | ≈ +3.02% gross | Phase 2A P2A-1 |
| Low-uplift environment (Seg 2+3 mean 20td) | ≈ +0.34% gross | Phase 2A P2A-1 |
| Material concentration (top-2 share) | 89.9% | Phase 2A G5 |
| Rolling-window minimum Δ_A3 (20td) | +0.33% | Phase 2A P2A-2 |

### Mandatory Phase 2B assumptions (from Phase 2A §10)

1. Scenario analysis must include a low-uplift environment
   (Segments 2 and 3, Δ_20td ≈ +0.34% average).
2. Full-sample average (+1.92%) must not be assumed uniformly available.
3. Capacity analysis must reflect the clustering structure identified
   in Phase 1 (up to 70+ simultaneous R8 signals on single dates).

---

## 3. Research Question

> Does the STABLE bull-regime R8 uplift survive realistic execution
> friction under both high-uplift and low-uplift environments?

**Framing note:** Phase 2B takes gross uplift as given (established by
Phase 2A). The question is not "is there an edge?" but "how much of the
edge survives execution costs?" Gross uplift is an input; net PnL is the
output.

---

## 4. Cost Model

### 4.1 Structure

Costs are reported in two independent components. They are never
pre-combined into a single number during analysis; the final output
table always shows Gross, Commission, Slippage, and Net separately.

**Rationale:** Separating commission from slippage preserves cost
attribution. A net return of +0.30% has different implications depending
on whether it reflects (a) a strong gross uplift mostly consumed by
commission, or (b) a weak gross uplift with low execution friction.
Combined costs obscure this distinction.

### 4.2 Commission (fixed structural cost)

Taiwan equity standard commission and transaction tax:

| Component | Rate | Notes |
|---|---|---|
| Entry commission | 0.1425% | Broker commission (inclusive of tax) |
| Exit commission | 0.1425% | Broker commission |
| Exit transaction tax | 0.3000% | TWSE securities transaction tax |
| **Round-trip total** | **0.5850%** | Fixed; applied to all scenarios uniformly |

Commission is a regulatory/structural cost. It is not scenario-dependent
and does not vary with execution quality.

### 4.3 Slippage ladder (D1)

Four scenarios representing execution quality assumptions. Each scenario
applies symmetrically to entry and exit. Slippage is applied on top of the
`adj_open[T+1]` fill price (Phase 1 frozen formula).

| Scenario | Entry slippage | Exit slippage | Round-trip slippage | Purpose |
|---|---|---|---|---|
| **S0** | 0 bps | 0 bps | 0 bps | Phase 1↔2B bridge; commission-only baseline |
| **S1** | 10 bps | 10 bps | 20 bps | Realistic; liquid large-cap Taiwan equity |
| **S2** | 25 bps | 25 bps | 50 bps | Moderate stress; mid-cap or elevated volatility |
| **S3** | 50 bps | 50 bps | 100 bps | Severe stress; thin liquidity or cluster-day crowding |

**Scope constraint:** Dynamic slippage models (ATR-dependent,
volume-dependent, price-impact models) are explicitly out of scope.
Phase 2B establishes feasibility under fixed assumptions. Dynamic
modelling is Phase 3 scope.

### 4.4 Net return formula

```
Net_return(horizon, scenario) =
    Gross_return(horizon)
    − Commission_roundtrip          (0.585%, fixed)
    − Slippage_roundtrip(scenario)  (0 / 0.20% / 0.50% / 1.00%)
```

Total cost deduction per scenario:

| Scenario | Total deduction (commission + slippage) |
|---|---|
| S0 | 0.585% |
| S1 | 0.785% |
| S2 | 1.085% |
| S3 | 1.585% |

---

## 5. Position Sizing and Capacity (D2)

### 5.1 Position sizing

**Method:** Per-position deployment budget of `min(1/N, 10%)`.

**Semantics:** This is a **partial-NAV deployment model**, not a
fully-invested equal-weight portfolio. Each position receives
`min(1/N, 10%)` of NAV. When N = 10, the portfolio is fully deployed
(10 × 10% = 100% NAV). When N < 10, the portfolio is partially deployed
(e.g., N=3 → 30% NAV, 70% cash). Undeployed capital earns 0%.

This reflects realistic deployment constraints: the strategy does not
lever up to stay fully invested when few signals qualify. Normalising
weights to sum to 1.0 when N < 10 would misrepresent the deployment
decision and overstate concentration risk.

Rationale: Isolates per-position signal edge from portfolio construction
effects. Introducing weighting schemes (Kelly, vol-targeting) would
conflate signal edge with portfolio construction edge.

**Portfolio construction rules (frozen):**

| Parameter | Value | Notes |
|---|---|---|
| Per-position weight | `min(1/N, 10%)` | N = active positions on entry date |
| Max simultaneous positions | 10 | Hard cap; 10 positions = 100% NAV |
| Holding period | 20 trading days | Matches Phase 1 primary horizon |
| Undeployed capital | Cash (0% return) | Not modelled as a return source |

**Gross return definition:** Portfolio gross return on a signal date =
`sum(weight_i × fwd_return_i)` — a NAV-weighted return, not the mean of
selected event returns. The event-level mean (`event_gross_mean`) is
retained as a reference column but is not the primary Gross figure
in the output table.

### 5.2 Overflow handling

On dates where N > 10 R8 signals qualify simultaneously, two selection
methods are evaluated as sensitivity analysis:

| Method | Description |
|---|---|
| **First-10** | Take the first 10 signals by stock_id sort order |
| **Random-10** | Random selection of 10 from qualifying signals (seed=42) |

Both methods are reported. Material difference between methods is a
finding, not a defect. Overflow days are annotated in the output.

**Rationale:** Phase 1 identified clustering up to 77 simultaneous signals
on a single date (2024-08-07). The overflow policy directly addresses the
practical portfolio capacity question raised by Phase 2A G5 concentration.

### 5.3 Entry and exit mechanics

| Item | Specification |
|---|---|
| Entry | T+1 adj_open (Phase 1 frozen formula) |
| Exit | T+20td adj_close (Phase 1 frozen formula) |
| Partial exits | Out of scope (Phase 2B uses full position sizing only) |
| Re-entry | Not permitted within the same holding window |
| Simultaneous positions | Overlapping windows permitted (positions are independent) |

---

## 6. Concentration Scenarios (D3)

### 6.1 Overview

Phase 2A identified material concentration (G5): 89.9% of the aggregate
positive uplift at 20td comes from Segments 1 and 4. Phase 2B must
explicitly evaluate both high-uplift and low-uplift environments.

Three mandatory scenarios:

| Scenario | Date range | Segments | Gross Δ_20td (approx) | Purpose |
|---|---|---|---|---|
| **A — Full Sample** | 2022-03-22 – 2026-06-04 | 1+2+3+4 | +1.92% | Historical realised baseline |
| **B — Low-Uplift** | 2023-10-24 – 2025-08-08 | 2+3 | ≈ +0.34% | Stress test; most conservative |
| **C — High-Uplift** | 2022-03-22 – 2023-10-20 + 2025-08-11 – 2026-06-04 | 1+4 | ≈ +3.02% | Favourable regime; upper bound |

### 6.2 Why Scenario B is the most important

Scenario B (Low-Uplift) directly tests whether the strategy is viable in
conditions that may be more representative of future deployment than the
full-sample average. If the net return in Scenario B is negative under
S1 (realistic slippage), Phase 2B's conclusion must be:

> The strategy is not viable in low-uplift environments under realistic
> execution costs.

This would be a valid and useful finding, not a failure. Phase 2B is a
feasibility assessment; FEASIBLE and NOT FEASIBLE are both valid
outcomes.

### 6.3 Scenario construction

Scenarios B and C use the exact segment date boundaries from Phase 2A
(per `r8_phase2a_spec.md` §6.1 segment construction):

- Segment 1: 2022-03-22 to 2023-10-20 (inclusive)
- Segment 2: 2023-10-24 to 2024-07-09 (inclusive)
- Segment 3: 2024-07-10 to 2025-08-08 (inclusive)
- Segment 4: 2025-08-11 to 2026-06-04 (inclusive)

Scenario C uses Segments 1 and 4 as non-contiguous date pools. Treatment
events are pooled across both segments; no time-continuity assumption is
made.

---

## 7. Output Specification

### 7.1 Primary output table

The primary Phase 2B output is a 12-row matrix (3 scenarios × 4 slippage
levels) with four cost columns:

| Environment | Scenario | Gross | Commission | Slippage | Net |
|---|---|---|---|---|---|
| Full Sample | S0 | x.xx% | −0.585% | 0.000% | x.xx% |
| Full Sample | S1 | x.xx% | −0.585% | −0.200% | x.xx% |
| Full Sample | S2 | x.xx% | −0.585% | −0.500% | x.xx% |
| Full Sample | S3 | x.xx% | −0.585% | −1.000% | x.xx% |
| Low-Uplift | S0 | x.xx% | −0.585% | 0.000% | x.xx% |
| Low-Uplift | S1 | x.xx% | −0.585% | −0.200% | x.xx% |
| Low-Uplift | S2 | x.xx% | −0.585% | −0.500% | x.xx% |
| Low-Uplift | S3 | x.xx% | −0.585% | −1.000% | x.xx% |
| High-Uplift | S0 | x.xx% | −0.585% | 0.000% | x.xx% |
| High-Uplift | S1 | x.xx% | −0.585% | −0.200% | x.xx% |
| High-Uplift | S2 | x.xx% | −0.585% | −0.500% | x.xx% |
| High-Uplift | S3 | x.xx% | −0.585% | −1.000% | x.xx% |

Gross is the mean signal-date portfolio gross return across all signal
dates in the scenario date pool: `mean(sum(weight_i × fwd_return_i))`
per SPEC §5.1 partial-NAV model. `event_gross_mean` (mean of individual
event returns without NAV weighting) is retained as a reference column
but is not the primary Gross figure.

### 7.2 Supplementary outputs

| Output | Description |
|---|---|
| Overflow summary | Dates with N > 10 signals; count by First-10 vs Random-10 |
| Position-count distribution | Histogram of simultaneous active positions |
| First-10 vs Random-10 sensitivity | Net return difference across slippage scenarios |
| Per-segment cost breakdown | Gross/Net for each of the 4 Phase 2A segments under S1 |

### 7.3 Verdict categories

| Verdict | Definition |
|---|---|
| **FEASIBLE** | Net return positive under S1 (realistic) in Scenario A (Full Sample) AND Scenario B (Low-Uplift). Does not imply deployment readiness. |
| **CONDITIONAL** | Net return positive under S1 in Scenario A but negative under S1 in Scenario B |
| **NOT FEASIBLE** | Net return negative under S1 in Scenario A. Does not invalidate Phase 1 or Phase 2A findings. |

A CONDITIONAL verdict means the strategy is viable only in favourable
market conditions. This must be documented explicitly.

### 7.4 Deliverable

**Phase 2B Execution Feasibility Memo** (`research/r8_phase2b_feasibility_memo.md`)
containing:
- Primary output table (§7.1)
- Supplementary outputs (§7.2)
- Overflow policy sensitivity
- Capacity constraint assessment (cluster-day analysis)
- Verdict (FEASIBLE / CONDITIONAL / NOT FEASIBLE)
- Phase 3 assumptions derived from Phase 2B (if FEASIBLE or CONDITIONAL)

---

## 8. Scope Constraints

### Explicitly out of scope

The following are excluded from Phase 2B. Inclusion without a new SPEC
amendment constitutes a governance violation:

- Dynamic slippage models (ATR-based, volume-based, price-impact).
- Signal parameter optimisation (+5% threshold, MA5 lookback).
- Portfolio optimisation (Kelly sizing, vol-targeting, factor hedging).
- Multi-strategy portfolio construction.
- Live execution or paper-trading integration.
- Bearish signal evaluation (Phase 2B covers bull-regime R8 only).
- Any claim of independent alpha net of costs.

### Relationship to Phase 2A findings

Phase 2B does not re-validate the Phase 2A findings. Gross uplift values
are taken as given from Phase 2A artifacts. Phase 2B is not permitted to
modify, extend, or re-test the Phase 2A STABLE verdict.

---

## 9. Governance

### Upstream dependencies

| Document | Version | Status |
|---|---|---|
| `research/r8_phase1_interim_findings.md` | v1.0.0 | CONFIRMED |
| `research/r8_phase1_lifecycle_spec.md` | v0.2.1 | LOCKED |
| `research/phase2_research_roadmap.md` | v0.3.0 | LOCKED |
| `research/r8_phase2a_spec.md` | v0.3.0 | LOCKED |
| `research/r8_phase2a_validation_report.md` | v1.0.0 | STABLE |

### Downstream authorisations

| Phase | Authorised by | Requires |
|---|---|---|
| Phase 2B analysis | This SPEC | — |
| Phase 2C (signal refinement) | Phase 2B FEASIBLE or CONDITIONAL verdict | Phase 2C SPEC |
| Phase 3 (production deployment) | Phase 2B FEASIBLE verdict + Phase 2A STABLE | Phase 3 SPEC |

### Amendment policy

This SPEC may be amended by a new versioned document. Silent edits are
not permitted. Changes to D1 (slippage scenarios), D2 (position sizing
parameters), or D3 (concentration scenario date ranges) require a SPEC
version bump. The amendment must document why the change was necessary
and what analysis had already been completed under the prior version.

---

## 10. What Phase 2B Does Not Establish

Regardless of verdict:

- That R8 constitutes independent alpha net of all costs.
- That the strategy is suitable for live deployment (requires Phase 3 SPEC).
- That the gross uplift will persist in future periods not in the sample.
- That a different position sizing method would produce a better result.
- That a FEASIBLE verdict authorises production deployment.
- That a NOT FEASIBLE verdict invalidates Phase 1 or Phase 2A findings.

---

*End of r8_phase2b_spec.md v0.1.2*
