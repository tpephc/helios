# Helios Handoff — 2026-06-07 IF-3B Composition Audit Complete

## 全域慣例（所有後續 session 適用）

- **主要對話語言：中文**
- **所有 Python 檔案：嚴格遵循 PEP 格式**
- **DuckDB 路徑：`data/_storage/helios.duckdb`**
- **Server：`tradeagent@nexus:~/projects/helios`**

---

## Session 範圍

本 session 完成：
1. IF-3B source discovery spec v0.1.1 撰寫
2. TWSE OpenAPI 143 endpoints 完整 audit
3. SUSPENSION_GAP 203 rows composition audit（234 rows，r8_events 現版）
4. DQ-ADJ-003 重新分類為 capital reduction event
5. IF-3B reclassified P1 binding → P2 non-binding
6. lifecycle spec v0.1.6 committed

| Artifact | 狀態 |
|---|---|
| `research/r8_phase1_lifecycle_spec.md` v0.1.6 | COMMITTED `39ba6c2` |
| `research/if3b_source_discovery_spec.md` v0.1.1 | COMMITTED `eae5844` |

---

## Commit 紀錄
39ba6c2  docs(r8-phase1): composition audit; IF-3B reclassified P2; DQ-ADJ-003 closed v0.1.6
eae5844  docs(if3b): add source discovery spec v0.1.1
---

## AC-6 現狀

| Blocker | 狀態 |
|---|---|
| IF-1 Pre-listing contamination | CLOSED (2026-06-04) |
| IF-2 Empty stock_info | RECLASSIFIED P2 (v0.1.5) |
| IF-3A corporate_actions dividend/split | CLOSED (commit 76f1f45) |
| IF-3B suspension/halt dataset | **RECLASSIFIED P2 (v0.1.6)** |

**AC-6 binding blockers: 全部清除。Clean-panel re-run 現在可以啟動。**

所有 Phase 1 findings 仍為 **PROVISIONAL** per AC-6（labelling 要求，非 blocker）。

---

## Composition Audit 結果摘要

**母體：** r8_events，`signal_daily_return >= 0.10`，排除 PRE_LISTING_OTC
**總數：** 234 rows（原始 203 是 2026-06-02 舊版 r8_events，方法論相同）

| Class | Count | % |
|---|---|---|
| 正常漲停板（1–4d gap, ret≈10%） | 227 | 97.0% |
| 假期後首日上漲（gap≥5d，已知假期） | 6 | 2.6% |
| Capital reduction 換發新股 | 1 | 0.4% |
| **確認 halt-resumption** | **0** | **0%** |

**IF-3B 原始風險假設（halt rows 污染 forward return）在 r8_events 母體不成立。**

殘留風險（已揭露於 spec）：T+1 至 T+20 observation dates 的 halt gap 未被本次
audit 覆蓋，但不預期對 A-3 Tier 1 findings 有系統性影響。

---

## DQ-ADJ-003 處置

| 項目 | 內容 |
|---|---|
| Symbol / Date | 2327 / 2022-10-31 |
| 原分類 | adjusted price 計算異常（adj +36.94% vs raw 正常） |
| 新分類 | 現金減資換發新股，停牌 12 calendar days 後復牌 |
| 來源確認 | cnyes.com/news/id/4972505 |
| Disposition | DQ-ADJ-003 CLOSED；root cause 歸入 DQ-CA-001 |
| 對 findings 影響 | 無（落在 bear/nlu=1，adequacy-restricted cell） |

---

## IF-3B Source Discovery 現狀

### 已確認（本 session）

| Source | 結果 |
|---|---|
| TWSE OpenAPI | 143 endpoints fully audited；TWTAWU schema 正確但 current snapshot only；無 5 年歷史；suspendListingCsvAndHtml 是 delisting，非 halt |
| TWSE OpenAPI `/holidaySchedule` | **可用**；27 筆，當年度假期；對 TWSE Holiday Calendar backlog 有用 |

### 待確認（IF-3B P2 工作）

| Source | 待辦 |
|---|---|
| FinMind | 正確 catalogue endpoint 未確認（`/api/v4/info` 路徑錯誤）；需找正確路徑查 halt dataset |
| MOPS | 完全未存取；`t05st10` 停復牌公告待查 |

IF-3B 作為 P2 繼續推進，目標是完整 panel DQ，不是保護 A-3 findings。

---

## 獨立待辦（建議開新 ticket）

**TWSE Holiday Calendar：**
`/holidaySchedule/holidaySchedule` 已確認可用（JSON，27 筆，當年度）。
建議獨立 ingestion task，不要卡在 IF-3B timeline。
- Ingest 至 Helios calendar infrastructure
- 確認歷史深度（目前看起來是當年度 only，需查多年份）
- 對 trading-day counting cron 有直接影響

---

## 下個 Session 的第一件事

**Clean-panel re-run（A-3）。**

所有 AC-6 blockers 已清除。Re-run 不需要等任何 P2 工作。

**開始前請讀：**
```bash
cat ~/projects/helios/research/r8_phase1_lifecycle_spec.md   # v0.1.6
cat ~/projects/helios/research/r8_phase1_interim_findings.md # v0.1.0
```

Re-run 的目標：
1. 在 IF-1 remediation 完成後的 clean panel 上重跑 A-1/A-2/A-3
2. 確認 Benchmark C（R8 within RS_T3, ret_20d）是否仍為 +6.77%（post-remediation baseline）
3. 升級 findings 從 PROVISIONAL（pending P1-DATA remediation）到 confirmed

---

## Backlog 變動

### 新增

| ID | 描述 | 優先度 |
|---|---|---|
| TWSE-HOLIDAY-CAL | `/holidaySchedule` ingestion — 獨立於 IF-3B | P1 — OPEN |

### 狀態變更

| ID | 描述 | 舊狀態 | 新狀態 |
|---|---|---|---|
| IF-3B | suspension/halt/resumption dataset | P1 AC-6 binding | **P2 non-binding** |
| DQ-ADJ-003 | 2327 adj anomaly | P2 OPEN | **CLOSED** (capital reduction, DQ-CA-001) |

### 沿用（未變動）

| ID | 描述 | 優先度 |
|---|---|---|
| IF-3B（P2） | suspension/halt dataset — FinMind catalogue + MOPS 待查 | P2 — OPEN |
| P1-DATA IF-3 / DQ-CA-001 | corporate_actions suspension gap classification | P1 — OPEN |
| P1-DATA-FOLLOWUP | retire/rewrite scripts/ingest_security_lifecycle.py | P1 — OPEN |
| TWSE Holiday Calendar | TWSE-HOLIDAY-CAL（新增） | P1 — OPEN |
| P1-OBS | Intraday Monitor Self-Alert | P1 — OPEN |
| IF-2 → P2 | stock_info population pipeline | P2 — OPEN |
| BACKLOG-IF1-GUARD | repo-wide pytest guard: no direct daily_price_adj outside allowlist | P2 — OPEN |
| P2-OBS | Healthcheck Single Run Gap | P2 — OPEN |
| P3-OPS | Session Write Lock Policy | P3 — OPEN |

---

## Status Invariant

所有 Phase 1 findings 仍為 **PROVISIONAL** per AC-6（labelling）。
AC-6 binding blockers 全部清除。
Clean-panel re-run 為下個 session 第一優先。

---

*End of handoff_2026_06_07_if3b_composition_audit.md*
