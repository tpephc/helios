# Phase 0: Feature Outcome Baseline — Findings

**Status:** Research checkpoint (frozen)  
**Date:** 2026-05-28  
**Scope:** Bullish + bearish temporal features → forward return baseline  
**Commit purpose:** Freeze first credible baseline before any feature engineering changes

---

## 1. Methodology Scope

### Data
- **Universe:** All stocks with bullish_features / bearish_features computed (205 stocks)
- **Date range:** 2021-06-18 to 2026-05-28 (~5 years)
- **Forward return:** `adj_close[t+N] / adj_close[t] - 1` (dividend/split adjusted)
- **Horizons:** 5d, 10d, 20d trading days
- **MAE/MFE:** Close-based only (`close_mae`, `close_mfe`); no intraday high/low

### Leakage Controls
- **Expanding window quantile:** Bucket boundaries at row t use only data from rows < t (per-stock). Current row's value does not influence its own bucket assignment.
- **Sample spacing:** Every `max(horizon)` rows per stock (per-stock sequence index, not calendar). Reduces forward return overlap but does not eliminate it.
- **Point-in-time universe flag:** Uses `universe_snapshot` table (not `config/universe.yaml`). However, only 1 snapshot date exists (2026-05-20), making PIT top200 analysis currently unusable for historical periods.
- **Integer features:** Fixed semantic buckets (not quantile) to avoid bucket collapse on sparse count distributions.

### Interaction Study
- **RS bucket:** Rolling 252-trading-day cross-sectional percentile tercile (regime-invariant). RS=5 in bull market may be T2; in bear market may be T3.
- **Interaction lift:** `cell_mean - marginal_A - marginal_B + grand_mean`. Positive lift = genuine interaction beyond additive single-feature effects.
- **Feature B buckets:** Fixed semantic thresholds (interpretable, no leakage risk).

### Cost Model
- **Round-trip cost:** 58.5 bps (commission 28.5 bps + tax 30 bps)
- **No slippage, no spread, no execution model** — gross and simple_net only

### Statistical Metrics Per Bucket
- mean, median, trimmed mean (5% each tail), std, hit rate, p10, p90, close_mae, close_mfe, sample_count, is_underpowered flag (n < 30)

---

## 2. Known Limitations

These are not bugs — they are methodology boundaries that constrain the strength of conclusions.

1. **Rolling percentile uses calendar-day approximation** for trading-session window (`window * 1.5` calendar days ≈ 252 trading days). Holiday density, COVID halts, and Lunar New Year create uneven sample depth. Fix: use actual trading-session count.

2. **Interaction lift assumes linear additive decomposition.** Market interactions may be multiplicative or nonlinear. `lift > 0` does not imply causal synergy — it means the observed cell return exceeds the additive prediction.

3. **Sample spacing = max(horizon) does not eliminate autocorrelation.** Adjacent samples share macro regime, trend episodes, and market structure. Do not interpret bucket statistics as independent observations. Purged walk-forward and clustered bootstrap deferred to Phase B.

4. **`universe_snapshot` contains only 1 date (2026-05-20).** All PIT top200 analysis covers only the most recent ~7 rows per stock. Historical top200 membership is not available. Top200 slice results should be disregarded until historical snapshots are backfilled.

5. **No multiple testing control.** Many features × many horizons × many buckets = high false discovery risk. BH-FDR deferred to Phase B.

6. **Close-based MAE/MFE underestimates true adverse excursion.** Intraday drawdowns (especially common in Taiwan stocks with limit-down mechanics) are not captured.

---

## 3. Confirmed Observations

These are consistent observational patterns across the baseline study. They are NOT validated alpha claims, and they are NOT statistically tested for significance.

### 3.1 RS Persistence Is the Dominant Single Feature

`beta_adj_rs_20d` and `beta_60` show the cleanest monotonic relationship with forward returns across all horizons.

**beta_adj_rs_20d (20d, all universe):**

| Bucket | Winsorized Mean | Hit Rate |
|--------|----------------|----------|
| Q1     | +1.21%         | 53.5%    |
| Q2     | +1.20%         | 53.3%    |
| Q3     | +1.07%         | 51.5%    |
| Q4     | +1.13%         | 52.3%    |
| Q5     | +2.83%         | 54.7%    |

Q5 is distinctly separated from Q1-Q4. Discriminative power concentrates in the extreme positive tail — RS is not a linear factor but a threshold effect.

**beta_60 (20d, all universe):**

| Bucket | Winsorized Mean | Hit Rate |
|--------|----------------|----------|
| Q1     | +0.63%         | 50.8%    |
| Q5     | +2.89%         | 57.1%    |

Cleanest monotonicity of any feature. Q1→Q5 spread ~2.3% with hit rate improvement from 50.8% to 57.1%.

**Important caveat:** beta_60's edge may be beta exposure premium (high-beta stocks outperform in an upward-drifting market) rather than stock-specific alpha. Regime segmentation needed to disentangle.

### 3.2 RS + Failed Breakdown Is the Only Genuine Interaction

**RS_T3_high + has_absorption (20d):**

| Metric           | Value  |
|-----------------|--------|
| Mean return      | +3.48% |
| RS_T3 marginal   | +3.26% |
| Interaction lift  | +0.30% |
| Median           | +1.13% |
| Hit rate         | 54.0%  |

This is the only interaction where lift, median, AND hit rate all improve simultaneously. The effect is small but consistent — not driven by tail outliers.

**Interpretation:** Failed breakdown in high-RS stocks may proxy for institutional demand absorption (buyers defending a level during a dip). This is the closest thing to a microstructure signal in the current feature set.

### 3.3 Bearish Features Mostly Capture Exhaustion/Rebound, Not Continuation

Most "bearish" features show positive forward returns:

- `below_ma200_streak` 1-2 days: 10d mean +2.36%, hit 60.5% (shakeout rebound)
- `atr_expansion_days_5d` 2+: 20d mean +4.42% (volatility climax rebound)
- `below_ma50_streak` 10+: 20d mean +1.46% (oversold mean reversion)

Taiwan's market microstructure (limit-down rules, retail leverage, margin calls, ETF passive buying, National Stabilization Fund expectations) creates strong reflexive rebounds from extreme weakness.

### 3.4 MA Streak Features Have Limited Discriminative Power

`above_ma20_streak` 0 vs 10+ (20d winsorized mean): +0.96% vs +1.38%. Difference is small, and hit rate actually decreases (53.1% → 50.8%) for longer streaks. Binary above/below loses distance information — supports adding `dist_above_ma_atr` as continuous replacement.

### 3.5 ATR Compression Ratio Shows Reverse Pattern

Higher ATR compression ratio (Q5, more volatile) has better forward returns than lower (Q1, more compressed). Compression alone is NOT bullish — it's inactivity. The transition from compression to expansion matters, not compression itself.

---

## 4. Rejected Hypotheses

These hypotheses were tested and found unsupported by the baseline data. Recording them prevents future re-investigation of dead ends.

### 4.1 "Compression Breakout Edge"
**Hypothesis:** Stocks with ATR compression and tight price range are forming bases that lead to profitable breakouts.  
**Result:** `atr_compression_days_10d`, `tight_range_days_10d` show no edge (bucket 3+ 20d winsorized mean +0.03%, worse than bucket 0 at +1.29%). Compression alone is indistinguishable from dead liquidity.  
**Interaction test:** RS_T3_high + comp_yes has lift +0.74% but median = 0%, hit rate = 48% — fat right tail only, not stable alpha.

### 4.2 "Volume Breakout Continuation"
**Hypothesis:** High-volume up days on strong stocks signal demand reappearance and continuation.  
**Result:** `volume_breakout_days_5d` has weak standalone edge. Interaction with high RS produces NEGATIVE lift (-0.43%) and lower hit rate (51.9% vs 53.6% without volume breakout). Volume breakout on high-RS stocks is more likely exhaustion/overextension than continuation.

### 4.3 "Bearish Continuation Cluster"
**Hypothesis:** Low RS + new low after rebound = downside continuation.  
**Result:** RS_T1_low + has_new_low has 20d mean = +1.38% (still positive), lift = +0.17%. Taiwan's institutional mechanics prevent sustained bearish continuation from this setup.

### 4.4 "Standalone Accumulation Features Have Alpha"
**Hypothesis:** Volume contraction, tight range, and failed breakdown independently predict positive forward returns.  
**Result:** All three features have weak or no discriminative power as standalone signals. Failed breakdown has marginal value only when conditioned on high RS.

---

## 5. Feature Taxonomy (Revised)

The baseline study reveals that the original bullish/bearish classification is misleading. Features are better categorized by their actual market behavior:

| Category               | Features                                        | Observed Behavior           |
|------------------------|------------------------------------------------|-----------------------------|
| **Trend persistence**  | beta_adj_rs_20d, beta_60, above_ma50_streak     | Positive continuation       |
| **Inactivity**         | atr_compression, tight_range, vol_contraction   | No edge / neutral           |
| **Exhaustion/rebound** | below_ma streak, atr_expansion, weak_rebound    | Mean reversion (positive)   |
| **Absorption**         | failed_breakdown (conditioned on high RS)        | Weak positive interaction   |
| **Continuation failure**| new_low_after_rebound, high_vol_down            | Weak negative (still positive in Taiwan) |

---

## 6. Next-Step Rationale

### Why Geometric RS Fix Is Next (Not New Features)

RS persistence is the only S-tier feature. The current implementation uses arithmetic sum approximation (`sum(daily_returns)`) instead of geometric compounding (`prod(1 + r) - 1`). For high-volatility stocks over 20-60 day windows, the difference can be material. Since RS is the strongest signal, improving its measurement precision has the highest ROI of any possible change.

**After fixing:** Re-run `feature_outcome_study.py` and `feature_interaction_study.py` to verify whether RS ranking and interaction lift change. Do not add new features until the strongest feature's measurement is correct.

### Why Regime-Conditioned Analysis Is Second Priority

The current study mixes bull, bear, and high-volatility regimes. RS + absorption interaction may only work in stressed/correction regimes. Volume breakout may only work in calm momentum regimes. Regime segmentation (using existing `market_regime` table) would reveal whether the observed patterns are stable or regime-specific.

### Why More Standalone Features Are Low Priority

The baseline conclusively shows that standalone compression/accumulation features have no edge. Adding `dist_above_ma_atr` or `ma_slope` may produce incrementally better continuous proxies for streak, but the fundamental finding (RS dominance) will not change. Feature expansion should wait until RS methodology is correct and regime segmentation is done.

---

## 7. Tool Inventory

| File | Purpose |
|------|---------|
| `research/feature_outcome_study.py` | Per-feature quantile bucket → forward return baseline |
| `research/feature_interaction_study.py` | 2-feature cross-bucket → interaction lift |
| `research/outputs/bullish_features_outcome_baseline.csv` | 197 bucket-horizon combinations |
| `research/outputs/bearish_features_outcome_baseline.csv` | 184 bucket-horizon combinations |
| `research/outputs/feature_interaction_baseline.csv` | 108 cell-horizon combinations |

---

*This document is a research checkpoint, not a production specification. Findings are observational patterns from a single study with known limitations. They should be validated with regime segmentation, out-of-sample testing, and proper statistical inference before informing any production signal logic.*
