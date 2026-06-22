# research/r8_phase6_findings.md

# Phase 6 — Exit Policy Evaluation Findings

**Date:** 2026-06-21
**Anchor:** r8_phase6_step3g_lu
**Status:** FINDING REGISTERED / Step 3 COMPLETE

---

## F-P6-01 — Adaptive Exit Policies Do Not Improve ARM_B

**Context:**
- Evaluation: Low-Uplift scenario, treatment_1 pool
- Period: 2023-10-25 → 2025-09-05 (455 calendar days, 454 NAV obs)
- ARM_B baseline: Sharpe=2.2039, MaxDD=17.31%, admission_rate=17.5%
- Bootstrap: B=5000, L=20, seed=42 (stationary block, NAV-aligned)

**Candidate results:**

| Candidate | Sharpe | ΔSharpe | G1 | G2 | G3 | Verdict |
|-----------|-------:|--------:|----|----|----|---------|
| ARM_B | 2.2039 | baseline | — | — | — | REFERENCE |
| E1 ATR Trailing | 1.1689 | −1.035 | FAIL | PASS | PASS | CHARACTERISED |
| E2 MA20 Failure | 0.3773 | −1.825 | FAIL | FAIL | PASS | CHARACTERISED |
| E3 RS Deterioration | 1.1342 | −1.070 | FAIL | PASS | FAIL | CHARACTERISED |
| E4 Donchian | 1.6842 | −0.354 | FAIL | PASS | FAIL | CHARACTERISED |

**Bootstrap 95% CIs (B=5000, NAV-aligned, seed=42):**

| Candidate | CI lower | CI upper | prob(Δ≤0) |
|-----------|----------|----------|-----------|
| E1 | −1.485 | −0.084 | 98.6% |
| E2 | −2.235 | −0.623 | 99.98% |
| E3 | −1.552 | −0.117 | 99.1% |
| E4 | −0.901 | +0.169 | 91.7% |

**Gate definitions:**
- P6-G1: ΔSharpe ≥ −0.15
- P6-G2: ΔMaxDD ≤ +3pp
- P6-G3: ΔAdmission ≥ +5pp

**Finding:**
No challenger satisfied the pre-registered gate criteria. All four
adaptive exit policies are CHARACTERISED, not SELECTED.

---

## Research Interpretation

### Primary finding

ARM_B's edge does not arise from exit inefficiency. The original
implicit research hypothesis was:

> RS continuation edge + smarter exit = higher Sharpe

The evidence supports instead:

> RS continuation edge + fixed 20td hold ≈ near-optimal

### E1/E2 counter-evidence (early capital release)

E1 (ATR trailing) and E2 (MA20 failure) both increased admission
rate substantially (E1: +7.0pp, E2: +7.1pp) by releasing capital
earlier. However, risk-adjusted performance fell sharply:

- E1: mean_holding_days=14.1td, Sharpe dropped from 2.20 to 1.17
- E2: mean_holding_days=14.0td, Sharpe dropped from 2.20 to 0.38

**Interpretation:** Early capital release from adaptive exits enabled
admission of lower-quality subsequent setups. The admission engine
(RS-60d top-quintile + ARM_B timing) depends on the full 20td holding
window to harvest the continuation alpha. Truncating the hold at
days 10–14 cuts returns without proportionate risk reduction.

### E3 mechanism (RS deterioration)

E3 triggered in 30% of positions (69/229 policy exits), with
mean_holding_days=5.8td when triggered — very fast when it fires.
However, 70% of admitted positions did not deteriorate below the
50th RS percentile within 20td, consistent with the ARM_B admission
criterion (top-quintile entry stocks tend to maintain relative strength).

The structural-symmetry hypothesis (top-quintile entry, median exit)
was not supported in this evaluation context.

### E4 observation (OBS-P6-E4-001)

E4 triggered in only 10% of positions (19/188). The 89.9% ceiling
rate means E4 ≈ ARM_B in practice within this universe and period.

**This is an observational result, not a falsification of E4:**

> The finding is that Donchian breakdown rarely occurs within the
> 20td holding window for ARM_B-admitted stocks, not that Donchian
> exit is ineffective as a rule.

E4's CI straddles zero [−0.90, +0.17], reflecting genuine statistical
uncertainty. E4 retains exploratory value for Phase 6A.

---

## Caveats

1. **Single scenario:** Low-Uplift only. Full-sample evaluation
   deferred (P6-3F-001 scenario window not yet implemented).

2. **In-sample:** L1 snapshot, 2023-10 to 2025-09. No out-of-sample
   validation.

3. **E3 rank universe approximation:** Per OBS-P6-E3-001, rs_60d_rank
   computed over scenario-wide valid symbol set rather than exact
   per-date eligible universe. Expected to be second-order at 50th
   percentile threshold.

4. **Data quality:** DQ-P6-001 — symbols 6919 (5 bars) and 910322
   (1 bar) have missing close data in the simulation window. Impact
   assessed as minimal given low frequency.

5. **Bootstrap interpretation:** Bootstrap CIs are percentile intervals
   under the stationary block bootstrap distribution. They are not
   formal hypothesis test p-values. The bootstrap is supplementary
   per SPEC §5.4 and does not affect gate verdicts.
