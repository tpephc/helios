# research/r8_phase6_candidate_disposition.md

# Phase 6 — Candidate Disposition

**Date:** 2026-06-21
**Anchor:** r8_phase6_step3g_lu
**Status:** LOCKED

---

## Disposition Table

| Candidate | Verdict | Disposition | Rationale |
|-----------|---------|-------------|-----------|
| ARM_B | REFERENCE | **RETAIN AS REFERENCE** | Phase 5 SELECTED. Phase 6 confirms no challenger improves on ARM_B. |
| E1 ATR Trailing | CHARACTERISED | **REJECTED** | G1 FAIL (ΔSharpe=−1.035). Early exits reduce performance. |
| E2 MA20 Failure | CHARACTERISED | **REJECTED** | G1 FAIL (ΔSharpe=−1.825), G2 FAIL. Worst performer. MaxDD worsened. |
| E3 RS Deterioration | CHARACTERISED | **REJECTED** | G1 FAIL (ΔSharpe=−1.070), G3 FAIL. Structural-symmetry hypothesis not supported. |
| E4 Donchian | CHARACTERISED | **ARCHIVE FOR FUTURE STUDY** | G1 FAIL but CI straddles zero. 89.9% ceiling rate: infrequently triggered, near-ARM_B. |

---

## ARM_B — RETAIN AS REFERENCE

Phase 5 verdict SELECTED / SELECTED_ARM_B stands. Phase 6 evaluation
finds no adaptive exit that improves risk-adjusted performance. ARM_B
fixed 20-trading-day hold remains the deployment baseline.

No change to Phase 5 governance artifacts required.

---

## E1 ATR Trailing — REJECTED

- ΔSharpe = −1.035 (G1 FAIL by 0.885 above threshold)
- mean_holding_days = 14.1td (29% shorter than ARM_B)
- Admission increased +7.0pp but quality of admitted setups declined
- Bootstrap interval entirely below zero; evidence is consistent with degradation.
- **Disposition:** REJECTED. Not considered for Phase 7 or Phase 6A.

---

## E2 MA20 Failure — REJECTED

- ΔSharpe = −1.825 (worst challenger)
- ΔMaxDD = +7.1pp (G2 FAIL — drawdown worsened materially)
- mean_holding_days = 14.0td
- Bootstrap 95% CI [−2.24, −0.62]: prob(Δ≤0)=99.98%
- **Disposition:** REJECTED. The MA20 failure signal is a noise
  amplifier in this universe. Not considered further.

---

## E3 RS Deterioration — REJECTED

- ΔSharpe = −1.070 (G1 FAIL)
- ΔAdmission = +3.9pp (G3 FAIL — below +5pp threshold)
- 30% of positions triggered early exit (mean_hd=5.8td when fired)
- Bootstrap 95% CI [−1.55, −0.12]: prob(Δ≤0)=99.1%
- Structural-symmetry hypothesis (top-quintile entry, median exit)
  not supported in Low-Uplift scenario
- **Disposition:** REJECTED. A2 robustness obligation (SPEC §2) noted:
  if E3 is re-evaluated in Phase 6A with alternative thresholds,
  the evaluation report must include the robustness flag and reference
  the structural-symmetry rationale explicitly.

---

## E4 Donchian — ARCHIVE FOR FUTURE STUDY

- ΔSharpe = −0.354 (G1 FAIL, but smallest deficit)
- 89.9% of positions exit at ceiling — E4 ≈ ARM_B in practice
- Bootstrap 95% CI [−0.90, +0.17]: CI straddles zero
  (prob(Δ≤0)=91.7% — elevated uncertainty)
- G3 FAIL: admission delta only +0.8pp (near-ARM_B slot dynamics)
- **Key observation (OBS-P6-E4-001):** The finding is that Donchian
  breakdown is rare within the 20td window for ARM_B-admitted stocks,
  not that Donchian exit is ineffective as a general rule.
- **Disposition:** ARCHIVE. E4 retains exploratory value for Phase 6A
  under modified parameters (longer lookback, alternative universe,
  or combined with admission changes). Not promoted to Phase 7.

---

## Implications for Phase 6A (if scoped)

If Phase 6A is authorised, the only candidate with residual
exploratory value is E4. Suggested Phase 6A scope:

1. E4 with alternative lookback periods (15td, 20td, 30td)
2. E4 applied to a broader universe or different scenario
3. Interaction between admission ranking and exit trigger
   (does RS-top-quintile selection explain the ceiling rate?)

E1/E2/E3 are considered falsified in the ARM_B Low-Uplift context
and should not be re-evaluated without a material change to the
admission universe or research hypothesis.
