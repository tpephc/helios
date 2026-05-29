# Phase 0: Feature Outcome Baseline — Findings

**Status:** Final (v4 — post per-horizon spacing fix)  
**Date:** 2026-05-29  
**Scope:** Bullish + bearish temporal features → forward return baseline + interaction + regime conditioning + Phase A trend quality  
**Note:** Per-horizon spacing fix (v4) overturned several v3 findings. All results below are post-fix.

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
- **Sample spacing:** Per-horizon (5d→every 5th row, 10d→every 10th, 20d→every 20th). Bucket assignment runs on full data for better quantile estimation; sub-sampling applied per horizon inside stats computation. Prior versions used global spacing=20 which severely under-sampled 5d horizon and produced artifact findings.
- **Point-in-time universe flag:** Uses `universe_snapshot` table (not `config/universe.yaml`). However, only 1 snapshot date exists (2026-05-20), making PIT top200 analysis currently unusable for historical periods.
- **Integer features:** Fixed semantic buckets (not quantile) to avoid bucket collapse on sparse count distributions.

### Interaction Study
- **RS bucket:** Rolling 252-trading-day cross-sectional percentile tercile (regime-invariant). RS=5 in bull market may be T2; in bear market may be T3.
- **Beta bucket:** Same rolling percentile tercile method applied to beta_60.
- **Interaction lift:** `cell_mean - marginal_A - marginal_B + grand_mean`. Positive lift = genuine interaction beyond additive single-feature effects.
- **Feature B buckets:** Fixed semantic thresholds (interpretable, no leakage risk).
- **Regime conditioning:** Uses `market_regime` table to filter by bull/bear/crisis/neutral. Regime-split results are separate CSVs.

### RS Methodology
- **Geometric compounding:** `prod(1 + r) - 1` replaces arithmetic `sum(r)` for beta_adj_rs_20d/60d. Baseline re-run confirmed findings robust to this change (Q5 RS 20d w.mean +2.83% → +2.85%).

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

### 3.2 RS_T3 + Pullback Entry Is the Strongest Confirmed Interaction

**v4 update: absorption finding overturned, pullback entry confirmed.**

The per-horizon spacing fix (v4) overturned the absorption finding from v3. The v3 absorption bear lift (+0.94%) was a spacing artifact: absolute returns turned negative for both has_abs and no_abs groups when properly sampled. The relative advantage of absorption survives but is not actionable.

The strongest confirmed interaction is now RS_T3 + Dist_T1 (pullback to MA20):

| Cell (20d) | Mean | Lift | Hit% | n |
|------------|------|------|------|---|
| RS_T3 + Dist_T1 (close to MA20) | +4.32% | **+1.66%** | **62.3%** | 366 |
| RS_T3 + Dist_T2 (mid distance) | +3.07% | +0.11% | 51.4% | 1024 |
| RS_T3 + Dist_T3 (far extended) | +2.63% | -0.48% | 49.8% | 2580 |

Lift is positive only for Dist_T1. Dist_T2/T3 are additive or slightly negative — no synergy.

**Best triple cell: RS_T3 + Dist_T1 + Beta_T3 (20d):**

| Metric | Value |
|--------|-------|
| Mean | +4.85% |
| Trimmed mean | +4.11% |
| Median | +3.10% |
| Hit rate | 60.0% |
| n | 215 |
| Net (after 58.5 bps) | +4.26% |

Consistent across 5d (+1.74%, 58.0% hit) and 10d (+3.43%, 61.0% hit). All metrics aligned.

**Regime-dependent (RS_T3 + Dist_T1, 20d):**

| Regime | Mean | Hit% | n | Action |
|--------|------|------|---|--------|
| Crisis | +12.29% | 79.7% | 158 | Maximum conviction |
| Bull | +4.68% | 61.2% | 206 | Normal entry |
| Neutral | +0.13% | 54.0% | 161 | Reduced position |
| Bear | **-2.30%** | **40.6%** | 212 | **Prohibited** |

**Optimal ATR distance thresholds (RS_T3, 20d):**

| Zone | Hit% | Median | Action |
|------|------|--------|--------|
| dist < -1 (below MA20) | 59.3% | +2.09% | Best entry |
| -1 ≤ dist < 0 (just below) | 55.0% | +0.91% | Good entry |
| 0 ≤ dist < 2 (above MA20) | 45-48% | negative | Dead zone — avoid |
| dist ≥ 3 (far extended) | 54.3% | +1.08% | Momentum (high variance) |

**Production rule:**

```
IF  beta_adj_rs_20d ∈ top tercile (RS_T3)
AND dist_above_ma20_atr < 0
AND market_regime ≠ bear
AND beta_60 ∈ T2 or T3
THEN entry priority = HIGH
```

**Overturned v3 findings:**

| Finding | v3 (spacing=20) | v4 (per-horizon) | Status |
|---------|-----------------|-------------------|--------|
| Absorption bear lift | +0.94% | Absolute returns negative | **Overturned** |
| RS_T3+Slope_T1 "trap" | lift -1.29% | lift +0.64% | **Reversed** |
| Beta_T1+has_abs "rescue" | lift +1.27% | lift +0.13% | **Much weaker** |

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

### 3.6 Beta and RS Are Additive, Not Synergistic

**beta_60 × beta_adj_rs_20d (all-regime, 20d):**

| Cell | Mean | Trimmed | Hit% | Lift |
|------|------|---------|------|------|
| Beta_T3 + RS_T3 | +4.62% | +3.29% | 55.2% | **-0.01%** |
| Beta_T3 + RS_T1 | +3.07% | +2.17% | 54.8% | -0.21% |
| Beta_T1 + RS_T3 | +1.45% | +0.44% | **48.4%** | **-0.56%** |
| Beta_T2 + RS_T3 | +3.30% | +2.21% | 55.0% | +0.29% |

The strongest cell (Beta_T3 + RS_T3) has zero interaction lift — its return is purely the sum of beta premium and RS premium. Beta and RS are independent, additive factors.

**Beta_T1 + RS_T3 is a trap:** Low-beta stocks with high RS (defensive leaders like food, telecom, utilities) have the worst hit rate (48.4%) and negative lift (-0.56%). This is regime-invariant: bull lift = -0.65%, bear lift = -1.54%.

### 3.7 Regime Split Reveals Hidden Structure

**Bull regime (692 trading days):**
- Beta_T3 + RS_T3: mean +5.56%, trimmed +4.22%, hit **58.4%** — strongest cell in the entire study
- RS + absorption lift: +0.06% (negligible — absorption doesn't help in bull)
- All RS terciles have positive returns; even RS_T1 mean = +2.09%

**Bear regime (253 trading days):**
- Overall returns much lower; RS_T2 marginal 20d = -0.25%
- RS_T3 + has_absorption: +1.57% (the only reliably positive cell)
- RS_T3 + no_absorption: **-0.70%** (genuinely bearish — first confirmed bearish continuation signal)
- Beta_T1 + RS_T3: **-2.22%**, hit **38.1%** — strongest negative finding in the study
- RS_T1 (low RS in bear): still +0.80% mean, confirming Taiwan's mean-reversion tendency even in bear markets

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
| **Absorption**         | failed_breakdown (conditioned on high RS)        | **Overturned** — v3 bear lift was spacing artifact |
| **Continuation failure**| new_low_after_rebound, high_vol_down            | Weak negative (still positive in Taiwan) |
| **Trend quality**      | dist_above_ma20_atr, sma20_slope_10d, spread    | Mostly RS proxy; distance useful for entry timing |

### Regime-Dependent Behavior

| Feature / Interaction | Bull Regime | Bear Regime |
|----------------------|-------------|-------------|
| RS persistence (Q5) | Strong continuation (+3.74% marginal) | Weak (+0.18% marginal) |
| RS_T3 + Dist_T1 (pullback) | +4.68%, 61.2% hit | **-2.30%, 40.6% hit (AVOID)** |
| RS_T3 + Dist_T1 (crisis) | N/A | **+12.29%, 79.7% hit** |
| Beta_T3 + RS_T3 | Strongest cell (+5.56%) | Modest (+1.57%) |
| Beta_T1 + RS_T3 | Trap (-0.65% lift) | Severe trap |

---

## 6. Next-Step Rationale

### Completed Since Initial Checkpoint

1. **Geometric RS fix** — `prod(1+r)-1` replaces `sum(r)`. Baseline robust to change. Commit `61a6174`.
2. **Beta × RS interaction** — Confirms additive (not synergistic). Beta_T1+RS_T3 identified as trap. Commit `d869893`.
3. **Regime-conditioned analysis** — Initial absorption finding in bear regime.
4. **Absorption validation pack** — Initial findings (v3). Commit `5c71bad`.
5. **Phase A features** — 6 new columns (distance/slope/spread). Commit `0c837e9`.
6. **Phase A interactions** — RS × distance/slope/spread. Slope/spread mostly RS proxy. Commit `7576bd7`.
7. **Per-horizon spacing fix (v4)** — Overturned absorption finding, reversed slope trap, strengthened pullback entry.
8. **Distance refinement** — Optimal entry zone (dist < 0), regime dependence, Beta_T3 best triple.

### What Should Come Next

**Production integration** — Implement the confirmed entry rule: RS_T3 + dist_above_ma20_atr < 0 + regime ≠ bear + Beta T2/T3. This is the single most actionable finding from Phase 0/A research.

**Do NOT prioritize:** Absorption refinement (overturned), more standalone features, complex multi-factor models. The research shows RS dominance with pullback entry timing and regime gating as the only confirmed interaction effects.

---

## 7. Tool Inventory

| File | Purpose |
|------|---------|
| `research/feature_outcome_study.py` | Per-feature quantile bucket → forward return baseline |
| `research/feature_interaction_study.py` | 2-feature cross-bucket → interaction lift + regime filter (v4, per-horizon) |
| `research/absorption_validation.py` | Absorption validation (v3, per-horizon — findings overturned) |
| `research/distance_refinement.py` | RS_T3 pullback entry refinement (regime, beta cross, ATR thresholds) |
| `research/outputs/bullish_features_outcome_baseline.csv` | 197 bucket-horizon combinations |
| `research/outputs/bearish_features_outcome_baseline.csv` | 184 bucket-horizon combinations |
| `research/outputs/feature_interaction_baseline.csv` | 252 cell-horizon combinations (v4, 8 interactions) |
| `research/outputs/absorption_validation_bear.csv` | 75 rows (overturned — kept for reference) |
| `research/outputs/absorption_validation_bull.csv` | 75 rows |
| `research/outputs/distance_refinement.csv` | 75 rows (current best findings) |

---

*This document is the final Phase 0/A research summary (v4, post spacing fix). Several v3 findings were overturned by the per-horizon spacing correction. The pullback entry rule (RS_T3 + dist < 0 + regime ≠ bear) is ready for production integration. All other findings should be treated as observational patterns requiring out-of-sample validation.*
