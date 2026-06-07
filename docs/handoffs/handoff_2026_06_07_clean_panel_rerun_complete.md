# Helios Handoff — 2026-06-07 Clean-Panel Re-run Complete

## 全域慣例（所有後續 session 適用）

- **主要對話語言：中文**
- **所有 Python 檔案：嚴格遵循 PEP 格式**
- **DuckDB 路徑：`data/_storage/helios.duckdb`**
- **Server：`tradeagent@nexus:~/projects/helios`**

---

## Session 範圍

本 session 完成：
1. Clean-panel re-run（A-1 / A-2 / A-3 v0.2.0）
2. Benchmark C fingerprint canonical reproduction
3. `r8_phase1_interim_findings.md` v0.2.0 — PROVISIONAL → CONFIRMED
4. AC-6 正式 CLOSED

| Artifact | 狀態 |
|---|---|
| `research/r8_phase1_interim_findings.md` v0.2.0 | COMMITTED `711a559` |
| `data/_storage/r8_phase1_a1/v0.2.0/` | LOCAL ONLY（gitignored） |
| `data/_storage/r8_phase1_a2/v0.2.0/` | LOCAL ONLY（gitignored） |
| `data/_storage/r8_phase1_a3/v0.2.0/` | LOCAL ONLY（gitignored） |

---

## Commit 紀錄
711a559  docs(r8-phase1): confirm findings v0.2.0; close AC-6; clean-panel re-run complete
4a307e6  feat(r8-phase1): clean-panel re-run A-1/A-2/A-3 v0.2.0; add arch dependency
---

## AC-6 狀態

**AC-6 CLOSED（2026-06-07）。**

| Blocker | 狀態 |
|---|---|
| IF-1 Pre-listing contamination | CLOSED (2026-06-04) |
| IF-2 Empty stock_info | RECLASSIFIED P2 (v0.1.5) |
| IF-3A corporate_actions dividend/split | CLOSED (commit 76f1f45) |
| IF-3B suspension/halt dataset | RECLASSIFIED P2 (v0.1.6) |
| Clean-panel re-run | **CLOSED (2026-06-07, commit 4a307e6)** |

---

## Re-run 結果

### Panel 確認

| Table | Rows | 備註 |
|---|---|---|
| `daily_price_adj` | 244,044 | 含 IF-1 污染（不用於 A-3） |
| `listed_market_daily_price_adj` | 236,713 | IF-1 clean panel（A-3 實際來源） |
| 差值 | 7,331 | IF-1 remediation fingerprint ✓ |

### Benchmark 新舊比較（bull / nlu=0）

| Metric | v0.1.0 | v0.2.0 | 變化 |
|---|---|---|---|
| A-1 θ_base 20td | +3.03% | +3.48% | +0.45% |
| A-3 δ_obs 10td | +1.35% | +1.21% | −0.14% |
| A-3 δ_obs 20td | +2.10% | +1.92% | −0.18% |
| CI 下限 10td | +0.69% | +0.58% | strictly positive ✓ |
| CI 下限 20td | +0.94% | +0.79% | strictly positive ✓ |
| p-value 10td | 0.0002 | 0.0004 | < 0.005 ✓ |
| p-value 20td | 0.0008 | 0.0022 | < 0.005 ✓ |

**Tier 1 finding 維持。**

### Benchmark C Fingerprint

| 數字 | 出處 | 定義 |
|---|---|---|
| +6.7666% | `r8_benchmarks.py` provisional | R8∩RS_T3 unstratified pooled ret_20d mean，n=4,031 |
| +6.8538% | `r8_benchmarks.py` remediated | 同上，n=4,021（IF-1 clean panel）✓ |
| +5.39% | A-3 v0.2.0 inference | bull/nlu=0 stratified theta_treat_implied |

三個數字是不同 aggregation，不可互相替代。

---

## 鎖定的三個 Statements

1. **A-3 Tier 1 survived clean-panel re-run。**
   bull/nlu=0，10td δ=+1.21% CI=[+0.58%, +2.01%]，20td δ=+1.92% CI=[+0.79%, +3.26%]。
   CI 下限在所有 block length L={5,10,20,40} 均 strictly positive。

2. **Benchmark C fingerprint 鎖定。**
   provisional +6.7666% → remediated +6.8538%。
   來源：`research/r8_benchmarks.py` pooled unstratified ret_20d mean。
   不等於 A-3 stratified theta_treat。

3. **Residual halt risk 保守措辭。**
   Forward-observation window（T+1 至 T+20）存在未量化殘餘風險，
   但目前無證據顯示足以系統性影響 A-3 Tier 1 findings 的方向或量級。

---

## 本 session 釐清的技術細節

### Panel SQL 來源
- A-3 `_PANEL_SQL` 從 `bullish_features`（非 `daily_features`）計算 rs_tertile
- regime 使用 `LAG(regime) OVER (ORDER BY date)`（T-1），非同日 join
- 這兩點在任何 future verifier 或 downstream script 必須保持一致

### r8_forward_returns.parquet population 差異
- `research/r8_forward_returns.py` 讀 `r8_phase1/r8_events.parquet` 作為 input
- A-3 `_PANEL_SQL` 動態從 DuckDB 重新計算 event population
- 兩者 n 不同（4,021 vs ~5,030）：原因未完全釐清，列為 P2 待查
- 不影響 A-3 inferential findings（A-3 用自己的 panel SQL）

### arch 依賴
- `arch>=8.0.0` 已加入 `pyproject.toml`（stationary bootstrap 用）
- commit `4a307e6`

---

## Scope 邊界（不得越界）

Phase 1 CONFIRMED 的範圍：
Phase 1 measurement findings under clean-panel re-run
不構成以下任何聲明：
alpha validated
production-ready
execution policy authorised
net-of-cost exploitability established
temporal stability confirmed
---

## 下個 Session 的第一件事

**TWSE-HOLIDAY-CAL ingestion（P1 data ticket）。**

`/holidaySchedule/holidaySchedule` endpoint 已確認可用（JSON，27 筆，當年度假期）。

目標：
1. Ingest 至 Helios calendar infrastructure
2. 確認歷史深度（目前看起來是當年度 only，需查多年份）
3. 升級 `is_trading_day()` 為 holiday-aware 實作
4. 對 trading-day counting cron 有直接影響

**開始前請讀：**
```bash
cat ~/projects/helios/research/r8_phase1_interim_findings.md   # v0.2.0 CONFIRMED
cat ~/projects/helios/research/r8_phase1_lifecycle_spec.md     # v0.1.6
```

---

## Backlog 狀態（未變動項目沿用）

| ID | 描述 | 優先度 |
|---|---|---|
| TWSE-HOLIDAY-CAL | `/holidaySchedule` ingestion | P1 — OPEN |
| P1-DATA IF-3 / DQ-CA-001 | corporate_actions suspension gap classification | P1 — OPEN |
| P1-DATA-FOLLOWUP | retire/rewrite scripts/ingest_security_lifecycle.py | P1 — OPEN |
| P1-OBS | Intraday Monitor Self-Alert | P1 — OPEN |
| IF-3B（P2） | suspension/halt dataset — FinMind + MOPS 待查 | P2 — OPEN |
| IF-2 → P2 | stock_info population pipeline | P2 — OPEN |
| BACKLOG-IF1-GUARD | repo-wide pytest guard: no direct daily_price_adj outside allowlist | P2 — OPEN |
| r8_forward_returns population 差異 | A-3 panel SQL vs r8_benchmarks.py n 不一致原因 | P2 — OPEN |
| P2-OBS | Healthcheck Single Run Gap | P2 — OPEN |
| P3-OPS | Session Write Lock Policy | P3 — OPEN |

---

## Status Invariant

Phase 1 findings：**CONFIRMED**（measurement scope only）。
AC-6：**CLOSED**。
下個 session 第一優先：**TWSE-HOLIDAY-CAL**。

---

*End of handoff_2026_06_07_clean_panel_rerun_complete.md*
