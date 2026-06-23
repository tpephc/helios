# Helios Handoff — 2026-06-06 IF-3A Complete

## 全域慣例（所有後續 session 適用）

- **主要對話語言：中文**
- **所有 Python 檔案：嚴格遵循 PEP 格式**
- **DuckDB 路徑：`data/_storage/helios.duckdb`**
- **Server：`tradeagent@nexus:~/projects/helios`**

---

## Session 範圍

本 session 完成：
1. IF-2 reclassification（`stock_info` 退出 AC-6 binding path）
2. IF-3A root cause diagnosis 與修復（dividend/split corporate_actions population）

| Artifact | 狀態 |
|---|---|
| `research/r8_phase1_lifecycle_spec.md` v0.1.5 | COMMITTED `77fb3c1` |
| `research/r8_phase1_interim_findings.md` v0.1.0+patch | COMMITTED `77fb3c1` |
| `scripts/ingest_dividends.py` resolver fix | COMMITTED `76f1f45` |
| `corporate_actions` table | POPULATED — 1106 rows, 199 symbols |

---

## Commit 紀錄
77fb3c1  docs(r8-phase1): reclassify IF-2 as P2; update AC-6 binding blockers v0.1.5
76f1f45  fix(data): include dynamic_top200 in dividend ingestion universe resolver
---

## AC-6 Binding Blockers 現狀

| ID | 描述 | 狀態 |
|---|---|---|
| IF-2 | `stock_info` empty | **RECLASSIFIED P2** — non-binding；`company_metadata` (1088 rows, TWSE) 作為 sector source |
| IF-3A | `corporate_actions` dividend/split population | **CLOSED (WITH RESIDUAL RISK)** — 1106 rows, 199 symbols covered；residual anomalies deferred to DQ-ADJ-001/002/003 |
| IF-3B | suspension/halt/resumption dataset | **OPEN** — AC-6 唯一剩餘 binding blocker |

---

## IF-3A 診斷摘要

**Root cause：** `get_universe_symbols()` 只掃 `universes.*.include_specific`，
跳過頂層 `dynamic_top200.symbols`。導致大多數 Phase 1 research-panel symbols 無
corporate_actions 記錄，adjusted price 對這些 symbols 等同 raw price。

**Fix：** resolver 新增對頂層 dict entries（含 `symbols` list）的迭代。

**驗證結果：**
- corporate_actions coverage：199 symbols with corporate_actions coverage
- corporate_actions rows：1106（1100 dividends + 6 splits）
- adjusted abnormal returns：224 → 144
- 6 symbols 在 FinMind 5 年歷史內確實無除權息事件，屬正常

**殘留 144 abnormal — 未 close，另開 DQ review：**

| ID | Symbol | Date | Pattern | 初步判斷 |
|---|---|---|---|---|
| DQ-ADJ-001 | 2540 | 2022-09-19 | -46.7% raw drop | 疑似 split 未被 ingest_splits 抓到 |
| DQ-ADJ-002 | 2603 | 2022-09-19 | 12 日資料缺口後跳價 | 資料缺口造成誤報，非 adjustment 問題 |
| DQ-ADJ-003 | 2327 | 2022-10-31 | adj +36.94% 但 raw 正常 | adjusted 計算異常，待查 |

IF-3A remediation objective satisfied；residual anomalies deferred。
這三個 cases 不 block AC-6。

---

## IF-3B：下一個工作重心

**性質：** 完全不存在的 pipeline，需要從 source discovery 開始設計。

**已知事實：**
- MOPS is a known authoritative disclosure source for suspension-related
  announcements. Whether it provides a usable historical feed has not yet
  been confirmed via source discovery.
- 203 SUSPENSION_GAP rows / 90 stocks 目前無法分類，root cause 在此
- `corporate_actions` 表 schema 已有欄位可存 halt/resumption，但無資料
- TWSE OpenAPI 是否有 historical tradability-interruption feed 尚未確認

**下個 session 的第一件事：**
撰寫 IF-3B source-discovery spec，內容包括：
1. MOPS / TWSE OpenAPI endpoint 調查
2. 可及性評估（historical depth、格式、授權）
3. 若無 clean API → 替代方案（price-gap detection、人工維護 seed）
4. schema 設計決策
5. 與 SUSPENSION_GAP 203 rows 的對照驗證方法

**開始前請讀：**
```bash
cat ~/projects/helios/research/r8_phase1_lifecycle_spec.md   # v0.1.5
cat ~/projects/helios/research/r8_phase1_interim_findings.md
```

---

## Backlog 變動

### 新增

| ID | 描述 | 優先度 |
|---|---|---|
| DQ-ADJ-001 | 2540 split 疑似未被 ingest_splits 抓到（2022-09-19 -46.7%） | P2 |
| DQ-ADJ-002 | 2603 資料缺口（2022-09-07 至 09-18）造成 validate_adjustments 誤報 | P2 |
| DQ-ADJ-003 | 2327 adjusted 計算異常（2022-10-31 adj +36.94% vs raw 正常） | P2 |

### 沿用（未變動）

| ID | 描述 | 優先度 |
|---|---|---|
| IF-3B | suspension/halt/resumption dataset — AC-6 binding | P1 — OPEN |
| P1-DATA IF-3 | `corporate_actions` DQ-CA-001（suspension gap classification） | P1 — OPEN |
| P1-DATA-FOLLOWUP | retire/rewrite `scripts/ingest_security_lifecycle.py` | P1 — OPEN |
| TWSE Holiday Calendar | — | P1 — OPEN |
| P1-OBS | Intraday Monitor Self-Alert | P1 — OPEN |
| IF-2 → P2 | `stock_info` population pipeline | P2 — OPEN |
| BACKLOG-IF1-GUARD | repo-wide pytest guard: no direct `daily_price_adj` outside allowlist | P2 — OPEN |
| P2-OBS | Healthcheck Single Run Gap | P2 — OPEN |
| P3-OPS | Session Write Lock Policy | P3 — OPEN |

---

## Status Invariant

所有 Phase 1 findings 仍為 **PROVISIONAL**，per `r8_phase1_lifecycle_spec.md` v0.1.5 AC-6。
IF-3B 未 closed → AC-6 unconditional binding。
IF-2 reclassification and IF-3A closure do not change the PROVISIONAL status
of any Phase 1 finding. Clean-panel rerun remains required before AC-6 can
be closed.

---

*End of handoff_2026_06_06_if3a_complete.md*
