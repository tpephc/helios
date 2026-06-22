# research/r8_phase6_closeout.md

# Phase 6 — Research Closeout

**Date:** 2026-06-21
**Anchor:** r8_phase6_step3g_lu
**Author note:** Authored at end of Step 3G production run.

---

## Closeout Declaration

Phase 6 Step 3 is complete. All sub-steps (3A–3G) are closed.
Finding F-P6-01 is registered. Candidate dispositions are locked.
No re-implementation or re-evaluation is authorised under Phase 6
scope without a formal SPEC amendment.

---

## Summary of Research Outcome

**Research question:** Do pre-registered adaptive exit policies
(E1 ATR trailing, E2 MA20 failure, E3 RS deterioration, E4 Donchian)
improve risk-adjusted performance over ARM_B fixed-horizon exit?

**Answer:** No. All four challengers are CHARACTERISED. None satisfied
the pre-registered gate criteria under the Low-Uplift scenario.

**ARM_B status:** RETAIN AS REFERENCE. Fixed 20-trading-day hold
remains the best known exit configuration for the R8 MA5 Momentum
strategy in the treatment_1 universe.

---

## What This Finding Means

The primary implication is not that adaptive exits are universally
ineffective. It is more specific:

> Within the ARM_B admission universe (RS-60d top quintile,
> Low-Uplift MA5 Momentum setup), the alpha is concentrated in
> the full 20td holding window. The admission criterion already
> selects for strong RS continuation; truncating the hold via
> adaptive exits reduces returns without proportionate risk reduction.

This is consistent with the Phase 4 and Phase 5 finding that
RS-60d ranking and 10td holding are sub-additive (P5-4): the
holding period and the admission criterion interact, and shortening
one without changing the other degrades the combination.

---

## Transition to Phase 7 (if authorised)

If Phase 7 research is authorised, the following directions have
support from Phase 6 evidence:

1. **E4 re-evaluation (Phase 6A):** Donchian lookback parameter
   study; alternative universes where price breakdowns are more
   frequent.

2. **Admission-exit joint optimisation:** The current Phase 6 design
   holds admission fixed (ARM_B) and varies only exit. A joint
   study relaxing both constraints is out of scope for Phase 6 but
   may be appropriate for Phase 7.

3. **Bearish regime exit (Track C):** Pre-Phase 6 backlog item,
   not addressed in Phase 6. Separate research scope.

---

## Phase 6 is Closed

```text
Phase 6 R8 Exit Policy Evaluation
Status: CLOSED
Finding: F-P6-01 (falsification of E1/E2/E3, observation on E4)
ARM_B: confirmed as deployment baseline
Date closed: 2026-06-21
```
