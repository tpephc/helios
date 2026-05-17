# ADR-005: Deterministic regime over HMM/ML

**Status**: Accepted
**Date**: 2026-05-17
**Version**: v0.1.11

## Context

Market regime classification is foundational to Helios — it's the primary alpha source (per the round-trip backtest, regime gating contributed more to performance than entry breakout precision).

The classic question: how to detect regime?

**Option A: Statistical / latent state models**
- Hidden Markov Model (HMM) with N states
- Gaussian Mixture Models on return distributions
- Change-point detection (CUSUM, BOCPD)
- Volatility clustering models (GARCH)

**Option B: Deterministic rules**
- TAIEX close vs SMA200 → trending vs non-trending
- TAIEX 20-day vol stdev vs threshold → calm vs crisis
- Combined into 4 states: bull / bear / neutral / crisis

Option A is intellectually appealing — "let the data tell you the regime". Option B feels primitive.

But forces favor Option B for v0.1:
- **5-year sample is short for HMM** — fitting latent states risks finding pattern in noise
- **Reproducibility** — deterministic rules give identical regime classification on identical inputs across runs / versions
- **Debuggability** — when a signal looks wrong, "why is today bull?" is answerable in 2 lines
- **Operator intuition** — the operator can mentally simulate the regime classification, building trust
- **No new dependencies** — no scikit-learn, no hmmlearn, no overfit risk

Reviewer §30-33 framed it crisply:
> v0.1 需要 market intuition encoding, 不是 latent state estimation. 等 v0.2+ 有更多市場樣本 (尤其 包含 crisis transitions) 再考慮 statistical models.

## Decision

**Regime is classified by deterministic rules on TAIEX daily close in `features/regime.py`. No HMM, no ML, no fitted parameters.**

4-state classification:
- `crisis`: TAIEX 20-day return stdev > 0.020 (2% daily vol)
- `bull`: TAIEX close > sma_200 AND vol_20 ≤ 0.020
- `bear`: TAIEX close < sma_200 AND vol_20 ≤ 0.020
- `neutral`: transitional (close crossing sma_200 zone)

Thresholds (0.020 vol, sma_200) are **fixed in v0.1**, may become expanding-window quantiles in v0.2 (still deterministic, just adaptive).

## Consequences

**Positive**
- Every regime label is auditable in 2 lines of Polars
- Zero overfit (no parameters fitted to history)
- Identical results across all environments / runs / versions
- Empirically validated: 56.5% bull / 21.2% bear / 16.4% neutral / 6.0% crisis matches Taiwan 2021-2026 market memory
- Zero crisis-regime signal leakage across 5 years (73 crisis days, 0 signals through)

**Negative**
- Cannot capture multi-modal regimes (e.g., "bull but choppy" vs "bull and trending")
- Fixed thresholds may not transfer to other markets
- May misclassify edge cases (e.g., quick bull-bear-bull whipsaw)

**Risks**
- Regime classification could degrade if TAIEX volatility character shifts permanently. **Mitigation**: v0.2 plan to use expanding-window quantile thresholds.
- Crisis threshold (vol > 0.020) was set from observation, not fitted. **Mitigation**: backtested across full 5 years; flagged correctly on COVID 2020 H2 + 2022 rate hike + 2024 anomalies.

## Empirical validation

5-year backtest confirmed:
- Crisis days correctly flag 2022 March (升息恐慌), 2024 August (carry trade unwind), various geopolitical spikes
- Bull periods match user's memory of TAIEX healthy uptrend stretches
- 0 strategy signals leaked through crisis regime (perfect gating)

## Alternatives considered

1. **HMM with 4 states** — rejected. Latent state estimation needs more data than 5 years to be stable.
2. **GARCH for crisis detection** — rejected. Adds dependency (arch / statsmodels), parameter fitting, less interpretable than vol stdev.
3. **ML classifier (random forest on features)** — rejected. Overfit risk, no clear feature set, opacity.
4. **Per-symbol regime instead of TAIEX-anchored** — rejected. Too noisy for individual stocks; TAIEX is the right market-state proxy for TW equities.

## Forever-rule

When statistical regime detection is reconsidered (v0.2+):
- Must outperform deterministic rules on OOS backtest by a meaningful margin
- Must remain interpretable (e.g., posterior probabilities visible)
- Must NOT add a dependency that introduces version-drift risk
- Must be backed by a new ADR superseding ADR-005

Until then: **simple rules that the operator can mentally simulate beat fitted models the operator cannot reason about.**
