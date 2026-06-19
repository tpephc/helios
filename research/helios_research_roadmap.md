# Helios R8 MA5 Momentum — Research Roadmap

<!-- research/helios_research_roadmap.md -->
<!-- v0.1.1 — 2026-06-19 -->

**Status:** ACTIVE — updated after Phase 5 v1.0.2 governance patch
  (ARM_C reclassified, P5-4 downgraded to working hypothesis)
**Maintainer:** Governed by research SPEC chain; updates require rationale.

---

## Governance Summary

```
Phase 1:    CLOSED / CONFIRMED / ARCHIVED
Phase 2A:   CLOSED / STABLE
Phase 2B:   CLOSED / FEASIBLE
Phase 3:    CLOSED / CHARACTERISED / LOCKED
Phase 4:    CLOSED / OPTIMISATION_CHARACTERISED / LOCKED
Phase 5:    CLOSED / CONFIGURATION_SELECTED / LOCKED (v1.0.2)
            ARM_B SELECTED; ARM_C reclassified to
            CAPACITY_DEMONSTRATED / SHARPE_UNRESOLVED
Phase 6:    NOT STARTED — requires Phase 6 SPEC;
            P5-FOLLOWUP-001 to be addressed (resolve or formally defer)
```

**Phase 5 Verdict (v1.0.2):**
  Layer 1: `CONFIGURATION_SELECTED`
  Layer 2: `SELECTED: ARM_B`
  Reclassified: `ARM_C → CAPACITY_DEMONSTRATED / SHARPE_UNRESOLVED`

---

## Phase 5 Key Findings (carried forward)

| Finding | Description | Value |
|---|---|---|
| P5-1 | RS-60d ranking confirmed in Low-Uplift | Sharpe 1.569 → 2.204; MaxDD −3.23pp |
| P5-2 | 10td holding materially increases capacity | Admission 17.5% → 32.4% (+14.83pp, mechanical) |
| P5-3 | Capacity gain from 10td is not free | Sharpe 1.569 → 1.476; difference within sampling error of Sharpe estimator |
| P5-4 (WH) | Working hypothesis: RS-60d ranking and 10td holding may be sub-additive — pending P5-FOLLOWUP-001 (snapshot-consistent re-evaluation of Phase 4 single-factor arms) |
| P5-REF | Price snapshot refresh detected | daily_price_adj retroactive adj; first divergence 2023-07-14; attribution plausibility-based (see Phase 5 §8.6) |

**Phase 6 deployment baseline:** ARM_B (20td + RS-60d) — sole baseline
**Capacity reference (not a candidate):** ARM_C (10td + RS-60d) —
  CAPACITY_DEMONSTRATED / SHARPE_UNRESOLVED; admission gain confirmed
  as mechanical and robust; Sharpe preservation is not statistically
  distinguishable from noise at this sample size and is sensitive to
  the adj-price snapshot

---

## Active Research Tracks

### Track A — Portfolio Construction & Deployment Evaluation
*Governed by Phase SPEC chain. Sequential; each phase requires prior phase verdict.*

```
Phase 6: Exit Policy Evaluation
Status:  NOT STARTED
Requires: Phase 6 SPEC (must address ARM_B as sole baseline,
          ARM_C capacity-demonstration reference, price-snapshot
          refresh, forward lineage-gate override governance, and
          P5-FOLLOWUP-001 ownership — resolve or formally defer)
Priority: HIGH — direct path to paper-trading candidate

Phase 6 scope (anticipated, not pre-authorised):
  Track C: ATR-trailing exit
  Track D: MA20-failure exit
  Track E: RS-deterioration exit   ← most theoretically motivated
  Track F: Donchian exit
  Baseline: ARM_B (20td + RS-60d, fixed exit)

Research question:
  Can an adaptive exit policy release capital occupancy without
  degrading Low-Uplift Sharpe vs ARM_B fixed-hold baseline?

Primary motivation (snapshot-robust, mechanical):
  ARM_B LU admission = 17.5%: 82.5% of signals rejected due to
  capital lock-up, not signal quality. This is the structural
  bottleneck Phase 6 targets. The motivation is independent of
  P5-4 and is robust to the P5-FOLLOWUP-001 outcome.

Supplementary motivation (pending identification):
  Working Hypothesis P5-4 suggests that RS-60d ranking and 10td
  holding may be sub-additive; if confirmed by P5-FOLLOWUP-001,
  this strengthens the case for adaptive (state-conditional) exit
  over fixed shorter holding. If rejected, the Phase 6 direction
  is not invalidated — capacity expansion via shorter fixed hold
  was demonstrated by ARM_C (admission +14.83pp), but at Sharpe
  cost that is not statistically distinguishable from noise. An
  adaptive exit policy aims to recover capacity without imposing
  a uniform truncation on all positions.
```

---

### Track B — Production System Evidence Accumulation
*Live paper-trading evidence pipeline. Independent of research track.*

```
forward_return_tracker.py v0.2.0
  Cron: 16:10 TST
  Go-live gate: n ≥ 150 signals per strategy

bull_strategy_sanity_harness.py v0.3.0
  Status: INCONCLUSIVE (FAIL not triggered)

Go-live path: Track A real-time evidence only
Deferred: #27 / #28 / #29
           breakout rule in harness
           Phase B bearish (TX futures directional signal)
```

---

### Track C — Signal Characterisation & Trend Quality
*Feature research. Sequential within track; each item builds on prior findings.*
*Does not authorise production modification. Feeds into Track A Phase 6+.*

```
C-001  RS Internal Structure                         [READY — NEXT]
  Goal:    Decompose RS_T3 internal heterogeneity
  Question: Within same RS strength, which structural features
            explain future return dispersion?
  Motivation: ARM_B confirms RS-60d ranking works; C-001 asks why
              and whether the signal can be sharpened further.

C-002  Pullback Geometry                             [READY]
  Goal:    Characterise pullback quality within RS_T3 signals
  Candidates: dist_T1, dist_T2, dist_T3,
              below_ma20_days, failed_breakdown
  Dependency: C-001 (RS internal structure provides conditioning context)

C-003  Up-Day Persistence                            [BACKLOG APPROVED]
  Goal:    Test whether trend persistence structure within RS_T3
           predicts future return differences
  Feature: up_fraction_21, persistence_score_21
  Question: RS_T3 with 18 up / 3 down days vs 11 up / 10 down days —
            does persistence independently predict returns after
            conditioning on RS strength?
  Dependency: C-001 + C-002 required first.
  Rationale:  High persistence + low pullback depth may confound.
              Isolating persistence requires pullback geometry controlled.

C-004  Trend Smoothness                              [BACKLOG]
  Goal:    Characterise price path quality
  Candidates: daily_return_std, ATR-normalised drift,
              path efficiency, linear fit R²
  Dependency: C-003

C-005  Volatility Compression                        [BACKLOG]
  Goal:    Re-examine whether volatility compression has predictive
           power after conditioning on RS
  Rationale: Prior analysis unconditional; C-001–C-004 provide
             conditioning framework
  Dependency: C-004

C-006  Multi-Factor Attribution                      [BACKLOG]
  Goal:    Build decomposition framework across
           RS + Pullback + Persistence + Beta + Regime
  Output:  Attributable contribution of each factor to forward return
  Dependency: C-001 through C-005
```

**Track C execution sequence:**
```
Phase 5 complete
    ↓
C-001 RS Internal Structure
    ↓
C-002 Pullback Geometry
    ↓
C-003 Up-Day Persistence
    ↓
C-004 Trend Smoothness
    ↓
C-005 Volatility Compression
    ↓
C-006 Multi-Factor Attribution
```

**Why sequential (not parallel):**
C-003 interpretation depends on C-001 and C-002. For example:
RS_T3 + high persistence could reflect (A) genuinely stronger trend,
or (B) simply fewer pullbacks. Without Pullback Geometry controlled,
persistence analysis risks confounding cause and mechanism. Sequential
execution preserves interpretability of each finding.

---

### Track D — Bearish / Short-Side Research
*Deferred. No SPEC authorised.*

```
Phase B bearish (TX futures directional signal): DEFERRED
  Dependency: Track B go-live gate achieved for bullish strategies
```

---

## Research Dependencies (summary)

```
Phase 1 CONFIRMED
    ├── Phase 2A STABLE
    │       └── Phase 2B FEASIBLE
    │               └── Phase 3 CHARACTERISED
    │                       └── Phase 4 OPTIMISATION_CHARACTERISED
    │                               └── Phase 5 CONFIGURATION_SELECTED
    │                                       └── Phase 6 [NOT STARTED]
    │                                               └── Paper-trading candidate
    │
    └── Track C-001
              └── C-002
                    └── C-003
                          └── C-004
                                └── C-005
                                      └── C-006
                                            → feeds Phase 7+ entry refinement
```

---

## What This Roadmap Does Not Establish

- That Phase 6 findings will persist on future data.
- That Track C findings will be incorporated into production without
  a Phase SPEC and formal research chain.
- That ARM_C's CAPACITY_DEMONSTRATED status authorises 10td as a
  production parameter. ARM_C is a research reference for the scale
  of admission gain achievable via shorter fixed hold; it is not a
  Phase 6 candidate.
- That Working Hypothesis P5-4 is an established finding. It is
  retained pending P5-FOLLOWUP-001.
- That Track C can proceed in parallel with Track A without SPEC
  authorisation for any production modification.

---

*End of helios_research_roadmap.md v0.1.1*
