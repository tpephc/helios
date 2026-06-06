# Helios Handoff — 2026-06-02 Session End

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

本 session 完成四項 handoff 待辦，對應 `handoff_2026_06_02.md`：

1. R8 Phase 1 SPEC commit
2. Artifact C governance decision record
3. P1-DATA panel integrity assessment commit
4. account_id migration test debt 清除

---

## Commit 記錄

| Hash | 說明 |
|---|---|
| `4b94124` | docs(r8): lock phase 1 lifecycle specification v0.1.2 |
| `ae5a35f` | docs(r8): add governance decision record |
| `fb38ae4` | docs(data): add panel integrity assessment |
| `0226c09` | docs(r8): add phase 0 feasibility study |
| `5f529d7` | fix(tests): resolve account_id migration debt and schema drift |

---

## 系統狀態

### Test suite

```
修復前：20 failed / 114 passed
修復後：1 failed / 133 passed
```

殘餘 1 個 failure：`test_push_failure_does_not_leave_pending`
Root cause：`bullish_features` 表不存在於 `init_schema()`
分類：**P1 test-infra debt**（見 Backlog 章節）

### R8 Governance Chain

四份文件已全部進 repo，角色無重疊：

```
research/r8_phase0_feasibility.md              ← Phase 0 evidence
research/r8_phase1_lifecycle_spec.md  v0.1.2   ← WHAT（SPEC）
docs/decision_records/r8_phase1_governance.md  ← WHY（governance）
research/P1-DATA_panel_integrity_assessment.md ← data evidence
```

### account_id migration（v0.1.18/v0.1.19）

修正內容：

| 分類 | 內容 |
|---|---|
| conftest | 新增 `test_account_id` fixture，回傳 `"test_account"` |
| test signatures | 13 個 test function 補 `test_account_id` 參數 |
| call sites | `PaperBroker()`、`approve_signal()`、`open_position()`、`scan_and_exit()`、`listen_for_approvals()`、`generate_pending_signals()` 全部補 `account_id` |
| schema drift | `orders` 表新增 `order_lot_type` column；CHECK constraint 補 ODD lot 路徑 |
| production bug fix | `generate_pending_signals()` signature 補 `equity_reset_date` 參數；`daily_run.py` call site 同步補傳 |
| Category E | `test_next_dev_signal_id_increments`：DEV-TEST-002 改用 `signal_date=date(2026, 5, 15)`，符合 canonical key semantics |

---

## Backlog 現狀

### P1-TEST：`init_schema()` missing `bullish_features`（新增，本 session 發現）

```
File: 尚未建立 backlog 文件
Severity: P1 test-infra debt
Production impact: none observed
Regression risk: medium
```

`test_push_failure_does_not_leave_pending` 驗證「missed signal > wrong trade」safety
invariant（P0-3 reviewer requirement）。`generate_pending_signals()` 是 production
path，依賴 `bullish_features`，但 `init_schema()` 未建此表，造成 safety path
regression coverage 靜默失效。

**建議修法（優先順序）：**

1. `init_schema()` 補 minimal `bullish_features` schema（preferred）
2. test 內 mock 掉 `bullish_features` query
3. **不建議 skip**：此 test 覆蓋 safety-critical path

---

### P1-DATA：Panel Integrity（既有）

```
File: docs/backlog/backlog_P1-DATA_listing_status_integrity.md
Assessment: research/P1-DATA_panel_integrity_assessment.md
```

三個 integrity gap 均 open：

- IF-1：18 stocks / 7331 rows 含興櫃歷史（最高優先）
- IF-2：`stock_info` 表為空
- IF-3：`corporate_actions` 表為空（DQ-338 中 203 rows 無法細分）

所有 R8 Phase 1 findings 標記為 **provisional** 直到 P1-DATA 完成。
`date >= listing_date` filter 已明確 reject（見 assessment 文件）。

---

### P1-OPS：Signal Storage Idempotency（已完成）

```
File: docs/backlog/P1-OPS_signal_storage_idempotency.md
Status: RESOLVED（commit 7bce3cb）
```

canonical key `(symbol, strategy, signal_type, signal_date)` 已鎖定。
`save_signal()` contract：`SaveSignalResult(signal_id, created)`。

---

### P1-OBS：Intraday Monitor Self-Alert（既有）

```
File: docs/backlog/backlog_P1-OBS_intraday_monitor_self_alert.md
Status: OPEN
```

---

### P2-OBS：Healthcheck Single Run Gap（既有）

```
File: docs/backlog/backlog_P2-OBS_healthcheck_single_run_gap.md
Status: OPEN
```

---

### P3-OPS：Session Write Lock Policy（既有）

```
File: docs/backlog/backlog_P3-OPS_session_write_lock_policy.md
Status: OPEN
```

---

## 下一個 Session 建議優先順序

1. **P1-TEST `bullish_features`** — `init_schema()` 補 minimal schema，讓
   `test_push_failure_does_not_leave_pending` 恢復綠燈。Safety invariant 不應長期
   失效。

2. **R8 Phase 1 實作開始** — SPEC 和 governance chain 已完整落地，可以開始
   lifecycle replay infrastructure。進入前確認 P1-DATA status。

3. **Kairos go-live gate** — 確認 forward_return_tracker.py v0.2.0 的 n≥150
   per strategy Track A 進度。

4. **P1-DATA remediation planning** — 確認 trusted security lifecycle source，
   起草 remediation SPEC。

---

## 掛起事項（Deferred）

- v0.1.17 ARCHITECTURE.md refresh（deferred from v0.1.16）
- timestamp semantics backlog #14（deferred to v0.1.17）
- Kairos Phase B bearish/TX futures directional signal
- Kairos backlog items #27/#28/#29
- `docs/research/` 下的部分 untracked 文件尚未 commit（非 blocking）

---

*End of handoff_2026_06_02_session_end.md*
