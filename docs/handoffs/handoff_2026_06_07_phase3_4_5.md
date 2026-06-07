# Helios Handoff — 2026-06-07 Phase 3 / 4 / 5 Session

## 全域慣例（所有後續 session 適用）

- **主要對話語言：中文**
- **所有 Python 檔案：嚴格遵循 PEP 格式**
- **DuckDB 路徑：`data/_storage/helios.duckdb`**
- **Server：`tradeagent@nexus:~/projects/helios`**

---

## Session 範圍

本 session 完成：

1. Phase 3 SPEC v0.1.2 LOCKED + runner v0.1.0 executed + report v1.0.1 LOCKED
2. Phase 4 SPEC v0.1.1 LOCKED + runner v0.1.0 executed + report v1.0.0 LOCKED
3. Phase 5 SPEC v0.1.0 LOCKED

---

## 今日 Commits（建議）

```
docs(research): lock Phase 5 spec v0.1.0
feat(research): implement Phase 4 runner v0.1.0 and lock report v1.0.0
feat(research): implement Phase 3 runner v0.1.0 and lock report v1.0.1
docs(research): lock Phase 3 spec v0.1.2
```

---

## 治理狀態

```
Phase 1:    CLOSED / CONFIRMED / ARCHIVED
Phase 2A:   CLOSED / STABLE
Phase 2B:   CLOSED / FEASIBLE
Phase 3:    CLOSED / CHARACTERISED / LOCKED
Phase 4:    CLOSED / OPTIMISATION_CHARACTERISED / LOCKED
Phase 5:    SPEC LOCKED (v0.1.0) / RUNNER NOT STARTED
```

---

## Phase 3 Summary

**Verdict: CHARACTERISED**

Runner: `scripts/run_phase3_analysis.py` v0.1.0
Artifacts: `data/_storage/r8_phase3/v0.1.0/`
Report: `research/r8_phase3_risk_report.md` v1.0.1 LOCKED

**Architecture decisions:**
- D1A: calendar-time MTM NAV from `daily_price_adj.adj_close` (step-function prohibited)
- D2: RS_T3 baseline primary benchmark; TAIEX price proxy secondary
- D3: Cap sensitivity (Track B) sensitivity only, baseline = 10% cap
- D4: AUM breakeven inverse approach (no ADV model)
- Verdict structure: CHARACTERISED / INCOMPLETE (advisory, no Sharpe threshold gate)

**Key findings:**
- Primary Finding: 16.3% admission rate driven by **holding-period-induced capital lock-up**, not signal clustering
  - Mean signals/date = 3.7, median = 3.0, only 2.1% of dates had > 10 signals
  - Little's Law approximation: 3.7 × 20td = 74 slot-days demand vs 10 available slots
- Finding B: Low-Uplift R8 Sharpe (1.613) ≈ RS_T3 (1.606), Δ = 0.007 — no material edge
- Finding C: Higher caps degraded risk profile (B3 25% cap → MaxDD 41.56%)

**Track A risk metrics (baseline cap, FIFO scheduler):**

| Environment | R8 Sharpe | R8 MaxDD | RS_T3 Sharpe |
|---|---|---|---|
| Full Sample | 2.378 | 21.65% | 1.313 |
| Low-Uplift | 1.613 | 20.54% | 1.606 |
| High-Uplift | 2.271 | 12.18% | 0.709 |

**Correlation (Full Sample):**
- R8 vs RS_T3: Pearson 0.668
- R8 vs TAIEX (price proxy): Pearson 0.484
- Bull regime mean daily log ret: +0.281%; Bear: −0.050%

**Scheduler diagnostics:**
- Full Sample treatment: 350/2143 admitted (16.3%)
- Full Sample baseline: 360/38075 admitted (0.9%)
- P3-FP-001 PASS: net_s1 = +1.6432% ✓
- P3-FP-002 PASS: max_daily_exposure = 100.0% ✓

**Data gaps confirmed:**
- VIX: no table in DuckDB
- sector_index_daily: empty (0 rows)
- TAIEX: price proxy only via `market_regime.taiex_close`

---

## Phase 4 Summary

**Verdict: OPTIMISATION_CHARACTERISED**

Runner: `scripts/run_phase4_analysis.py` v0.1.0
Artifacts: `data/_storage/r8_phase4/v0.1.0/`
Report: `research/r8_phase4_optimisation_report.md` v1.0.0 LOCKED

**Architecture decisions:**
- D1: Four horizons: 5/10/15/20td — `exit_date = calendar[pos + h]` (not pos+20)
- D2: OPTIMISATION_CHARACTERISED + Design Recommendations (two-layer verdict)
- D3: Paper trading fully separated; Track C reserved for Phase 6
- Bootstrap: two-sample stationary block, L = max(5, h), B = 5000

**Critical implementation notes:**
- `bullish_features` ranking columns NOT in `load_panel()` output (CTE does not expose them)
- Must pass `con=<DuckDBPyConnection>` to `build_signal_ledger_for_horizon()` for bulk join
- `__pycache__` must be cleared after updating runner (`find . -name "*.pyc" -path "*/scripts/*" -delete`)
- `schedule_positions()` uses `rank_order` column from `_rank_ledger()` to preserve quality ranking
- Track C: `raise NotImplementedError` — do not run

**Track A results (FIFO baseline cap):**

| h | Scenario | Admission | R8 Sharpe | Bootstrap Δ_A3 CI |
|---|---|---|---|---|
| 5td | Full Sample | 52.8% | 1.165 | [−0.17%, +0.80%] (crosses 0) |
| 10td | Full Sample | 30.0% | 2.129 | [+0.30%, +2.13%] ✓ |
| 15td | Full Sample | 21.0% | 1.726 | [+0.27%, +3.00%] ✓ |
| 20td | Full Sample | 16.3% | 2.378 | [+0.15%, +3.82%] ✓ |
| 5td | Low-Uplift | 58.2% | 0.574 | crosses 0 |
| 10td | Low-Uplift | 32.4% | 2.114 | crosses 0 |
| 15td | Low-Uplift | 22.6% | 1.074 | crosses 0 |
| 20td | Low-Uplift | 17.5% | 1.613 | crosses 0 |

**Track B results (20td, quality ranking):**

| Variant | Full Sample Sharpe | Low-Uplift Sharpe | Full MaxDD |
|---|---|---|---|
| FIFO | 2.378 | 1.613 | 21.6% |
| RS-20d | 2.676 | 1.839 | 18.0% |
| RS-60d | 2.563 | 2.128 | 19.5% |
| Uplift-proxy | 2.628 | 2.027 | 15.9% |

**Design Recommendations:**
- `CANDIDATE: rs_60d_ranking` — Low-Uplift Δ Sharpe = +0.515 ≥ 0.2 threshold
- `RESEARCH_FINDING: 10td_holding_period` — +13.7pp admission; below 25pp CANDIDATE threshold
- `RETAIN_20TD_BASELINE` pending Track C
- Track C reserved for Phase 6

**Key observations (for Phase 5):**
- RS-60d strongest in Low-Uplift (stress environment) vs RS-20d strongest in Full Sample
- 5td: edge disappears (CI crosses zero) — hard lower bound on holding period
- 10td: best utilisation–performance trade-off among tested horizons
- All quality variants dominate FIFO — FIFO should not be Phase 5 baseline

---

## Phase 5 SPEC Summary

SPEC: `research/r8_phase5_spec.md` v0.1.0 LOCKED

**Research question:**
> Can the capital-utilisation improvements identified in Phase 4 be converted into a superior deployable portfolio configuration without materially degrading risk-adjusted performance in the Low-Uplift environment?

**Three-arm structure (D1):**

| Arm | Configuration | Purpose |
|---|---|---|
| A | 20td + FIFO | Frozen Phase 3 baseline (lineage verification) |
| B | 20td + RS-60d | Isolated ranking effect (Phase 4 CANDIDATE) |
| C | 10td + RS-60d | Combined candidate (primary Phase 5 question) |

**Gate criteria (D2) — relative, not CI-based:**

| Gate | Criterion | Threshold |
|---|---|---|
| P5-G1 | Low-Uplift Sharpe deterioration vs Arm A | ≥ −0.10 |
| P5-G2 | Low-Uplift MaxDD worsening vs Arm A | ≤ +3pp |
| P5-G3 | Admission improvement vs Arm A (Arm C only) | ≥ +10pp |

**Why CI not used:** Low-Uplift bootstrap CI crosses zero at all horizons in Phase 4 — using CI > 0 as gate would reject Phase 3 baseline itself (logical contradiction).

**Track C excluded (D3):** Reserved for Phase 6; path-dependent exit policy is a separate problem from portfolio construction.

**Verdict structure:**
- `CONFIGURATION_SELECTED`: at least one arm (B or C) passes all applicable gates
- `CONFIGURATION_NOT_SELECTED`: no arm passes; 20td + RS-60d remains best-observed
- `INCOMPLETE`: missing arm

**Runner planning notes:**
1. Arm B expected to pass gates (based on Phase 4 Track B numbers) — primarily lineage confirmation
2. Pre-registered hypotheses for Arm C: H1: Sharpe(C, LU) > 1.613; H2: Sharpe(C, LU) ≥ 2.128
3. CONFIGURATION_NOT_SELECTED does not invalidate 20td + RS-60d as best-observed config

---

## 關鍵 Artifact 路徑

```
data/_storage/r8_phase3/v0.1.0/
    p3a_nav_series.parquet
    p3a_risk_metrics.json
    p3a_correlation.parquet
    p3a_correlation_metadata.json
    p3b_cap_sensitivity.parquet
    p3c_aum_breakeven.json
    manifest.json

data/_storage/r8_phase4/v0.1.0/
    forward_return_matrix.parquet    # fwd_5td / 10td / 15td / 20td
    p4a_holding_period.parquet       # Track A results
    p4a_bootstrap.parquet            # Δ_A3 CI by horizon
    p4b_prioritisation.parquet       # Track B results
    manifest.json
```

---

## 重要技術細節（Phase 5 runner 必知）

### bullish_features join 問題
`load_panel()` 的最終 SELECT 只有 5 欄：`stock_id, date, regime, near_limit_up, universe`。`bullish_features` feature columns 不在 panel 裡。

Phase 5 runner 必須在 `build_signal_ledger_for_horizon()` 裡傳入 `con=con`，才能觸發 bulk join：

```python
ledger = build_signal_ledger_for_horizon(
    panel, prices, "treatment_1", scenario, h=10, con=con
)
```

### pycache 問題
每次更新 runner 後必須清除 pycache，否則 Python 會載入舊版：

```bash
find . -name "*.pyc" -path "*/scripts/*" -delete
find . -name "__pycache__" -path "*/scripts/*" -exec rm -rf {} + 2>/dev/null; true
```

### Phase 5 runner 基礎
可直接在 `run_phase4_analysis.py` 基礎上調整：
- Track A 邏輯（`build_signal_ledger_for_horizon` + `reconstruct_nav_for_horizon`）可重用
- Track B 邏輯（`_rank_ledger` + `schedule_positions`）可重用
- 新增：gate check 函數（P5-G1/G2/G3）
- 新增：arm 比較邏輯

Arm C 使用 `h=10`, `rank_col="beta_adj_rs_60d"`。

---

## 次の Session の起點

```bash
cat ~/projects/helios/research/r8_phase5_spec.md    # v0.1.0 LOCKED
cat ~/projects/helios/research/r8_phase4_optimisation_report.md  # v1.0.0 LOCKED
git log --oneline -8
```

Phase 5 runner 的起點是確認 Phase 4 runner 的 import 可以重用：

```bash
python - << 'PY'
import sys; sys.path.insert(0, ".")
from scripts.run_phase4_analysis import (
    build_signal_ledger_for_horizon,
    reconstruct_nav_for_horizon,
    schedule_positions,
    bootstrap_block_length,
    _rank_ledger,
)
print("Phase 4 imports OK")
PY
```

---

## Status Invariant

```
Phase 1:    CLOSED / CONFIRMED / ARCHIVED
Phase 2A:   CLOSED / STABLE
Phase 2B:   CLOSED / FEASIBLE
Phase 3:    CLOSED / CHARACTERISED / LOCKED
Phase 4:    CLOSED / OPTIMISATION_CHARACTERISED / LOCKED
Phase 5:    SPEC LOCKED (v0.1.0) / RUNNER NOT STARTED
Research blockers: 0
Data blockers:     0
```

---

*End of handoff_2026_06_07_phase3_4_5.md*
