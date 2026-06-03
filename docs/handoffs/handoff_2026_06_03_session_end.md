# Helios Handoff — 2026-06-03 Session End

## 全域慣例（所有後續 session 適用）

- **主要對話語言：中文**
- **所有 Python 檔案：嚴格遵循 PEP 格式**
  - PEP 8：程式碼風格與排版
  - PEP 257：docstring 格式
  - 所有 public function/method 必須有 type hints
  - 變數名、函式名、class 名、log 訊息、docstring、註解：**英文**
- **檔案 header 慣例（所有新 Python 檔案）：**
  - scripts：`#!/usr/bin/env python3` + `# scripts/filename.py` + `"""Title — vX.Y.Z. Brief.`
  - modules：`# path/to/file.py` + `"""Title — vX.Y.Z. Brief.`
  - 檔名不含版本號

---

## Session 範圍

本 session 完成三項主要工作：

1. P1-TEST `bullish_features` 修復
2. R8 Phase 1 lifecycle replay infrastructure 完整實作（5 個模組）
3. 技術債清理（trading_calendar.py docstring）

---

## Commit 記錄

| Hash | 說明 |
|---|---|
| `fb16f4f` | fix(schema): add bullish_features to SCHEMA_SQL — P1-TEST RESOLVED |
| `a8370a6` | docs(r8): add Phase 1 effective-n bootstrap ADR |
| `2fc8ed2` | docs(calendar): clarify weekday-only limitation |
| `05246a6` | research(r8): event builder v0.1.1 |
| `53ccd0c` | research(r8): forward return calculator v0.1.0 |
| `03f257d` | research(r8): lifecycle metrics v0.1.1 |
| `58cbeeb` | research(r8): benchmark comparisons v0.1.1 |
| `d7e17bb` | research(r8): export and AC verification v0.1.0 |

All hashes verified via `git rev-parse --verify` on 2026-06-03.

---

## 系統狀態

### Test suite
134 passed / 0 failed
P1-TEST `bullish_features` RESOLVED：`init_schema()` 補 minimal schema，
`test_push_failure_does_not_leave_pending` 恢復綠燈。

### R8 Phase 1 Infrastructure

五個模組完成，AC-1 ~ AC-7 PASS under current implementation and
dry-run validation. All findings remain PROVISIONAL pending P1-DATA
remediation.
research/r8_event_builder.py       v0.1.1  05246a6
research/r8_forward_returns.py     v0.1.0  53ccd0c
research/r8_lifecycle_metrics.py   v0.1.1  03f257d
research/r8_benchmarks.py          v0.1.1  58cbeeb
research/r8_phase1_export.py       v0.1.0  d7e17bb
**輸出 artifacts（不進 repo，位於 `data/_storage/r8_phase1/`）：**

| 檔案 | 說明 |
|---|---|
| `r8_events.parquet` | 8430 events，含 T-1 de-circularised RS_T3、regime、near-limit-up |
| `r8_forward_returns.parquet` | ret_1/3/5/10/20d，entry anchor = T+1 open |
| `r8_lifecycle_metrics.parquet` | MA5 telemetry，new_high_flag，min_return_from_entry |
| `r8_benchmarks.parquet` | Benchmark A/B/C，regime stratified，near-limit-up subset |
| `r8_phase1_canonical.parquet` | events + fwd returns + lifecycle merged |
| `r8_phase1_manifest.json` | AC results，bootstrap config，provenance |

**關鍵統計（PROVISIONAL）：**
n_events             = 8430
n_unique_dates       = 1117
near_limit_up        = 2465 (29.2%)
rs_t3_null_rows      = 355  (4.2%)
Benchmark A (RS_T3 Hold):                  ret_20d mean = +2.63%
Benchmark B (RS_T3 + Pullback):            ret_20d mean = +2.63%
Benchmark C (R8 within RS_T3):             ret_20d mean = +6.84%
Benchmark C (RS_T3 unconditional aligned): ret_20d mean = +2.82%
**effective-n（AC-5）：**
n_obs          = 7955
n_unique_dates = 1097
n_eff          = 396.2
estimator      = date-level moving block bootstrap
block_length   = 5 trading days
n_replications = 10,000
seed           = 42
Note: AC-5 estimator was revised twice during this session
(formula fix + clamp). The current implementation is:
  raw_n_eff = n_dates * var_iid / var_bootstrap
  n_eff = clamp(raw_n_eff, 1.0, n_dates)
Future bootstrap methodology changes require a SPEC amendment.

**所有 Phase 1 findings 標記為 PROVISIONAL。**
原因：P1-DATA panel integrity 未解決（18 stocks / 7331 rows
興櫃歷史污染風險），`stock_info` 和 `corporate_actions` 為空。

### ADR 記錄
docs/decision_records/r8_phase1_bootstrap_adr.md  a8370a6
Decision: date-level moving block bootstrap, block=5td
Prerequisite for r8_event_builder.py
### trading_calendar.py

docstring 已更新，明確禁止在以下場景使用 `is_trading_day()`：
- production order scheduling
- fill-date calculations
- trading-day horizon calculations

R8 Phase 1 forward returns 使用 `daily_price_adj` ROW_NUMBER()，不依賴此函式。

---

## Known Limitations（Phase 1）

| 項目 | 說明 |
|---|---|
| Forward return engine 重複 | `r8_benchmarks.py` 複製了 `r8_forward_returns.py` 的 engine；deferred refactor |
| Benchmark C row-level pooling | Uses row-level pooling rather than date-level weighting. High signal-density dates (e.g. 2024-08-07: 77 signals) may contribute disproportionate weight. Deferred refactor. |
| `ma5_initially_above` 語意 | 若 T+1~T+3 MA5 為 null，實際是第一個有效 MA5 觀測日；manifest 已標記 |
| AC-5 estimator clamped | raw_n_eff for ret_20d was below 1.0 before fix; current n_eff=396.2 after formula correction |

---

## Backlog 現狀

### P1-TEST：`bullish_features`（已解決）
Status: RESOLVED (fb16f4f)
### P1-DATA：Panel Integrity（既有，OPEN）
File: docs/backlog/backlog_P1-DATA_listing_status_integrity.md
Assessment: research/P1-DATA_panel_integrity_assessment.md
三個 integrity gap 均 open：

- IF-1：18 stocks / 7331 rows 含興櫃歷史（最高優先）
- IF-2：`stock_info` 表為空
- IF-3：`corporate_actions` 表為空

所有 R8 Phase 1 findings 標記為 **provisional** 直到 P1-DATA 完成。
P1-DATA 修復後需對 Phase 1 所有模組重跑（r8_event_builder →
r8_forward_returns → r8_lifecycle_metrics → r8_benchmarks → r8_phase1_export）。

### TWSE Holiday Calendar（新增，P1）
Severity: P1 production-infra debt
`is_trading_day()` 只做 weekday check，不處理台灣國定假日（春節等）。
影響範圍：production order scheduling、fill-date calculations。
R8 Phase 1 不受影響（使用 price-panel row ordering）。
需要升級成 TWSE holiday-aware calendar 才能安全用於 live trading。

### P1-OBS：Intraday Monitor Self-Alert（既有，OPEN）

### P2-OBS：Healthcheck Single Run Gap（既有，OPEN）

### P3-OPS：Session Write Lock Policy（既有，OPEN）

---

## 下一個 Session 建議優先順序

1. **P1-DATA remediation planning** — 確認 trusted security lifecycle
   source，起草 remediation SPEC。R8 Phase 1 findings 升級為
   non-provisional 的前提。

2. **Kairos go-live gate** — 確認 forward_return_tracker.py v0.2.0
   的 n≥150 per strategy Track A 進度。

3. **TWSE Holiday Calendar** — 升級 `is_trading_day()` 為
   holiday-aware 實作，消除 production scheduling 風險。

4. **R8 Phase 1 分析** — Infrastructure 就緒，可開始撰寫分析
   notebook / report。所有結論必須標記 provisional。

---

## 掛起事項（Deferred）

- v0.1.17 ARCHITECTURE.md refresh（deferred from v0.1.16）
- timestamp semantics backlog #14（deferred to v0.1.17）
- Kairos Phase B bearish/TX futures directional signal
- Kairos backlog items #27/#28/#29
- R8 Benchmark C date-level weighting refactor
- r8_forward_returns engine 統一（deferred refactor）

---

*End of handoff_2026_06_03_session_end.md*
