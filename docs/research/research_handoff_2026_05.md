# Helios Research Program Handoff — 2026-05

## Scope

Read-only panel studies on the Helios Taiwan stock paper-trading system.
All research used the same Step-2 universe (bullish_features ⋈ daily_price_adj,
~227k rows, 205 stocks, 1,142 dates, 2021-09-10 to 2026-05-29) and shared
inference framework (cohort-excess within RS/dist strata, date-clustered
moving-block bootstrap CI as sole inference tool).

**Single-regime caveat applies to ALL findings:** the panel spans one market
regime (~bull/recovery 2021–2026); current-constituent survivorship; RAW LHS
carries market beta; no multiple-testing correction across studies.

---

## Closed Studies

### R1 — RS Persistence Decay

| Field | Value |
|---|---|
| Question | Within RS_T3, does time-in-leadership (age) predict forward return decay? |
| Result | **Negative** |
| Finding | Spearman(age, fwd_ret) ≈ +0.03–0.04 (positive, opposite of decay hypothesis); within-band (0.67–0.75) rho ≈ 0, CI spans zero. Positive association is between-spell selection (long spells = sustained strong stocks), not within-spell signal. |
| Production impact | None. No age filter justified. |
| Assets | `research/rs_persistence_decay.py` v0.1.4 |

### R2 — Failed Breakdown / MA20 Reclaim Quality

| Field | Value |
|---|---|
| Question | Does failed_breakdown_count_10d (MA20 reclaim count) predict forward return in the pullback universe? |
| Result | **Weak Negative** |
| Finding | No bullish absorption signal. Direction is chop penalty (negative), monotone dose in broad universe at 60d (CI excludes zero). In primary pullback universe (RS_T3 ∩ dist<0): h60 point estimate −2.1% but CI spans zero. |
| Key insight | `failed_breakdown_count_10d` is an MA20 whipsaw counter, NOT a demand-absorption indicator. |
| Production impact | None (no strategy change). Docstring correction needed (see Pending Hygiene). |
| Assets | `research/failed_breakdown_quality.py` v0.1.1, `failed_breakdown_v0_1_0.parquet` |

### R5 — Pullback Quality Transfer Study

| Field | Value |
|---|---|
| Question | Do find_bullish_setups's consolidation/trend features transfer from the above-MA20 base universe to the below-MA20 pullback universe? |
| Result | **Weak Positive** (1 of 3 axes survived) |
| Findings by axis | |
| Axis 1 — ATR compression | NULL. Transfer failed. |
| Axis 2 — Volume contraction | **Suggestive positive.** Monotone dose-response across all horizons; h60 Spearman CI excludes zero (barely: +0.010 to +0.139). Dose transition at ~4 days aligns with live heuristic threshold. |
| Axis 3 — Trend structure | NULL. Conditional on RS rank + pullback depth, additional trend maturity metrics add no incremental predictive value. |
| Production audit | `above_ma20_streak` sort key in find_bullish_setups NOT forward-return validated (Spearman slightly negative at 20/40d, null at 60d). |
| Production impact | Volume contraction as soft priority input (not hard filter); monitor via tracker. |
| Assets | `research/pullback_quality.py` v0.1.1, `pullback_quality_v0_1_0.parquet`, `research/r5_precheck.py` |

### Study B — RS Acceleration

| Field | Value |
|---|---|
| Question | Within RS_T3, does recent rank velocity (Δ5 = rs_pctile[t] − rs_pctile[t−5]) predict forward returns? |
| Result | **Negative** |
| Finding | Primary band (0.75–0.90, n=34k): Spearman rho ≈ −0.01, all three horizons CI span zero. Dose (adaptive tercile) shows no monotone pattern. |
| Context finding | 0.90–1.00 band: acceleration is negatively correlated with fwd_ret (h20/h40 CI exclude zero) — consistent with overbought/mean-reversion. Flagged as future research seed, not actionable. |
| Meta-finding | Combined with R1 (age = null): within T3, RS LEVEL is the signal; temporal dynamics (age, velocity) add nothing. Closes the RS-dynamics research line. |
| Production impact | None. |
| Assets | `research/rs_acceleration.py` v0.1.0, `rs_acceleration_v0_1_0.parquet`, `research/study_b_precheck.py` |

---

## Current Alpha Inventory

Signals with empirical support (varying strength):

| Signal | Source | Strength | Status |
|---|---|---|---|
| RS_T3 membership | Live screener | Foundation (not separately tested; structural) | In production |
| Pullback entry (dist < 0) | Live screener | Foundation | In production |
| Volume contraction (dose ≥ 4) | R5 Axis 2 | Weak positive (suggestive, h60 CI excludes zero) | Candidate for soft priority |

Signals tested and NOT supported:

| Signal | Study | Result |
|---|---|---|
| RS age / persistence | R1 | Negative |
| Failed breakdown count | R2 | Weak negative (chop, not absorption) |
| ATR compression (pullback) | R5 Axis 1 | NULL (transfer failed) |
| Trend structure (pullback) | R5 Axis 3 | NULL |
| RS acceleration (Δ5) | Study B | Negative |
| above_ma20_streak (sort key) | R5 Section C | NOT validated |

---

## Pending Hygiene

1. **R2 — `failed_breakdown_count_10d` docstring correction.**
   Current: "demand absorption — buyers stepped in to defend." Must change to
   neutral MA20 reclaim/whipsaw description per R2 finding. Corrected text
   drafted (see R2 session). Commit message: `docs(features): correct
   failed_breakdown_count_10d semantics`.

2. **R5 — find_bullish_setups sort key audit.**
   `above_ma20_streak` used as sort key without forward-return support (R5
   Section C). Backlog: consider replacing sort with `volume_contraction_days_10d`
   or `matched_profile_count`.

3. **R2 — Usage audit (grep).**
   Confirm `failed_breakdown_count_10d` is not silently feeding any live
   ranking/filter as a bullish input. Preliminary evidence: pullback screener
   uses beta_adj_rs/dist/beta_60, not fb. Full grep pending.

---

## Methodological Assets

Reusable across future studies:

- **Cohort-excess × date-clustered block-bootstrap CI framework.** Handles
  serial dependence, avoids anti-conservative permutation nulls for
  rolling-count features. Block-CI is sole inference tool.
- **Step-2 universe pipeline.** Standardized load → RS assignment (per-day
  weak-ECDF, live-matching T3 threshold) → forward return with global
  trading-day ordinal invariant.
- **Multi-feature study discipline.** Pre-register features/axes, report all
  (no cherry-pick), axis-level interpretation when collinear, CI-in-primary
  as bar.
- **Feasibility pre-check pattern.** Distribution audit + collinearity matrix
  + base-rate check BEFORE writing the main study script.

---

## Roadmap

```
Phase 0 — Immediate (this session)
  Portfolio Construction Feasibility Audit
    Q1: replay/simulation infrastructure exists?
    Q2: daily candidate count distribution
    Q3: signal strength basis for weighting

Phase 1 — Portfolio Construction (gated on Phase 0)
  BLOCKED until infrastructure confirmed
  Parameters: n_stocks, weighting, position cap
  Anti-overfit: time-series split, report all, realistic costs

Phase 2 — New Alpha Lines
  Leadership Breadth (requires feature engineering)
  Sector Breadth

Phase 3 — Queued
  R3 Regime-Conditioned Entry (gate: resolved n >= 30)
  Microstructure / Execution Layer

Deferred
  R6 Bearish Phase B (scope explosion)
```

---

## File Header Convention (applies to all new Python files)

- Scripts: shebang + `# scripts/filename.py` + `"""Title — vX.Y.Z. Brief.`
- Modules: `# path/to/file.py` + `"""Title — vX.Y.Z. Brief.`
- Filenames never include version numbers.

## Environments

- Helios remote: `tradeagent@nexus:~/projects/helios`
- Kairos remote: `tradeagent@100.116.99.68:~/projects/kairos`
- Local: Windows Terminal, downloads `C:\Users\tpephc\Downloads`
- DuckDB: `data/_storage/helios.duckdb` (read-only outside cron windows)
- Runtime: `uv run python ...` (Python 3.13)
