# Helios Handoff — 2026-06-05 Session End

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
- **DuckDB 路徑：`data/_storage/helios.duckdb`**（`data/helios.db` 是空的空殼）

---

## Session 範圍

本 session 完成 P1-DATA IF-1 remediation 全部三個 Phase：

1. **Phase 1**：`security_lifecycle` interval model DDL + seed ETL + 驗收測試
2. **Phase 2**：panel eligibility filter 注入 feature pipeline
3. **Phase 3**：full panel rebuild + R1/R2/R5/R8 re-run + delta report + promotion gate

---

## Commit 記錄

| Hash | 說明 |
|---|---|
| `3268d97` | fix(p1-data): align database.py schema with interval lifecycle model |
| `16a4038` | feat(p1-data): inject listed-market eligibility filter into feature pipeline |
| `a738249` | feat(p1-data): redirect R8 chain output to r8_phase1_remediated/ |
| `915990b` | feat(p1-data): add lifecycle migration, seed ETL, and validation tests |
| `2c1d942` | docs(p1-data): add SPEC-P1-DATA-REMEDIATION-v1 to data/reference |
| `5164c10` | docs: add P1-DATA and observability backlog items |
| `8a2d8d5` | chore(deps): add lxml>=6.1.1 |

HEAD: `8a2d8d50477a2c1d3d624566ee0a006603002338`

All hashes verified via `git log --oneline` on 2026-06-05.

---

## 系統狀態

### Test suite
158 passed / 0 failed

### P1-DATA IF-1 Remediation

**Promotion Gate: ALL PASS**

| Gate | 結果 |
|---|---|
| PG-1 security_lifecycle 36 rows | PASS |
| PG-2 two rows per seed stock | PASS |
| PG-2b no interval overlap | PASS |
| PG-3 no EMERGING rows in daily_features | PASS |
| PG-3b exclusion count non-zero for all 18 | PASS |
| PG-4 bullish_features no EMERGING rows | PASS |
| PG-4b bearish_features no EMERGING rows | PASS |
| PG-5 remediated R8 artifacts exist | PASS |
| PG-6 delta report schema complete | PASS |
| PG-7 benchmark deltas documented | PASS |
| PG-8 provisional artifacts preserved | PASS |

**Delta Report 摘要（`data/_storage/p1_data_remediation/delta_report.json`）：**

```text
total_rows_excluded:   7331（18 stocks，EMERGING period rows）
n_events:              8012 → 8012  (delta = 0)
rs_t3_null_rows:       348  → 348   (delta = 0)
near_limit_up_ratio:   0.2923 → 0.2923 (delta = 0.0)
Benchmark A ret_20d:   +2.52% → +2.53%  (Δ +0.005%)
Benchmark B ret_20d:   +2.54% → +2.56%  (Δ +0.012%)
Benchmark C ret_20d:   +6.77% → +6.85%  (Δ +0.087%)
```

**artifact_integrity_note：**
Provisional `r8_events.parquet/csv/manifest` 在第一次 remediation attempt 時被覆蓋。
其餘 provisional artifacts 已備份至 `data/_storage/r8_phase1_provisional_backup/`。

**R8 findings 狀態：NON-PROVISIONAL REVIEWABLE**
（資料污染 gate 已解除，可進入正式 research review；≠ alpha validated）

### 關鍵架構變更

**`security_lifecycle` table（interval model）：**
```sql
PRIMARY KEY (stock_id, listed_from)
-- 每個 stock 兩筆 row：
-- EMERGING: [otc_first_date, mainboard_date)
-- TWSE:     [mainboard_date, NULL)
```

**`listed_market_daily_price_adj` view（single enforcement point）：**
```sql
SELECT p.* FROM daily_price_adj p
WHERE p.date >= COALESCE(
    (SELECT MIN(l.listed_from) FROM security_lifecycle l
     WHERE l.stock_id = p.stock_id AND l.market IN ('TWSE', 'TPEx')),
    DATE '1900-01-01'
)
```
對 18 stocks 等價於 `date >= mainboard_date`。
非 18 stocks pass-through。

**`data/eligible_universe.py` v1.1.0：**
`eligible_date_predicate(alias)` — 供 compute_bullish/bearish_features.py 使用的 defensive filter。
Phase 3 完成後可移除 bullish/bearish 的 defensive duplication（daily_features 已是 canonical panel）。

**`compute_features.py`：**
直接讀 `listed_market_daily_price_adj`，不再直接讀 `daily_price_adj`。

**R8 chain 輸出路徑：**
```text
remediated: data/_storage/r8_phase1_remediated/
provisional: data/_storage/r8_phase1/（保留）
backup:      data/_storage/r8_phase1_provisional_backup/
```

### Baseline Audit Artifact
```text
data/_storage/p1_data_remediation/row_exclusion_baseline.csv
data/_storage/p1_data_remediation/delta_report.json
data/_storage/p1_data_remediation/promotion_gate_result.json
```

---

## 重要技術釐清（本 session 確認）

### IF-1 污染語意修正
- **原本誤解**：污染 = `date < otc_first_date`
- **正確語意**：污染 = EMERGING period rows（`otc_first_date <= date < mainboard_date`）
- `daily_price_adj` 的 panel 起始日（2021-05-21）晚於部分 stock 的 `otc_first_date`，但仍在 EMERGING period 內

### RS blast radius 機制修正
- `beta_adj_rs_20d` 是 stock vs TAIEX 的 **time-series** beta-adjusted return，不是 cross-sectional rank
- Full-panel recomputation 的原因：
  1. `r8_event_builder.py` 的 RS_T3 threshold 是 per-date cross-sectional（`PERCENTILE_CONT(2/3) WITHIN GROUP (ORDER BY beta_adj_rs_20d)`），移除 7331 rows 後 threshold 分佈改變
  2. mixed-generation panel invariant（不允許污染版與修復版混用）

### `listed_market_daily_price_adj` view 歷史
- v0.1.20 原始定義引用 flat schema `s.mainboard_date`
- flat schema DROP 後 view 進入 broken state
- 本 session 修復為 interval model predicate

### R1/R2/R5 entry points（已確認）
| 研究 | Script |
|---|---|
| R1 | `research/rs_persistence_decay.py` |
| R2 | `research/rs_acceleration.py` |
| R5 | `research/pullback_quality.py` |

`research/replay_engine.py` 是 bull strategy replay engine，不對應任何研究編號，不在 remediation re-run scope。

---

## Backlog 現狀

### P1-DATA：IF-1（RESOLVED）
Status: RESOLVED（Promotion Gate ALL PASS，2026-06-05）

### P1-DATA：IF-2 Empty `stock_info`
Status: OPEN，本 session 未動

### P1-DATA：IF-3 Empty `corporate_actions`
Status: OPEN，本 session 未動

### P1-DATA-FOLLOWUP：retire/rewrite `scripts/ingest_security_lifecycle.py`
Status: OPEN
`ingest_security_lifecycle.py` 針對已移除的 flat schema，語意錯誤，應在下個 session 前 retire 或 rewrite。

### TWSE Holiday Calendar（P1，OPEN）
`is_trading_day()` 只做 weekday check，不處理台灣國定假日。

### P1-OBS：Intraday Monitor Self-Alert（OPEN）
### P2-OBS：Healthcheck Single Run Gap（OPEN）
### P3-OPS：Session Write Lock Policy（OPEN）

---

## 下個 Session 建議優先順序

1. **R8 Phase 1 分析** — remediation 完成，findings NON-PROVISIONAL REVIEWABLE，可開始撰寫分析 notebook/report

2. **Kairos go-live gate** — 確認 `forward_return_tracker.py` v0.2.0 的 n≥150/strategy Track A 進度

3. **TWSE Holiday Calendar** — 升級 `is_trading_day()` 為 holiday-aware 實作

4. **retire `ingest_security_lifecycle.py`** — 清除語意錯誤的舊 script

5. **IF-2/IF-3** — stock_info、corporate_actions 空表

---

## 掛起事項（Deferred，沿用）

- v0.1.17 ARCHITECTURE.md refresh（deferred from v0.1.16）
- timestamp semantics backlog #14（deferred to v0.1.17）
- Kairos Phase B bearish/TX futures directional signal
- Kairos backlog items #27/#28/#29
- R8 Benchmark C date-level weighting refactor
- r8_forward_returns engine 統一（deferred refactor）
- `eligible_universe.py` defensive duplication 清理（Phase 3 cleanup，待 daily_features 確認為 canonical panel 後執行）
- `eligible_date_predicate()` 改名為 `panel_start_date_predicate()`（Phase 3 cleanup）

---

*End of handoff_2026_06_05_session_end.md*
