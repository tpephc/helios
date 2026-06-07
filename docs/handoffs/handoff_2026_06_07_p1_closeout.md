# Helios Handoff — 2026-06-07 P1 Backlog Closeout

## 全域慣例（所有後續 session 適用）

- **主要對話語言：中文**
- **所有 Python 檔案：嚴格遵循 PEP 格式**
- **DuckDB 路徑：`data/_storage/helios.duckdb`**
- **Server：`tradeagent@nexus:~/projects/helios`**

---

## Session 範圍

本 session 完成 P1 backlog 完整清零。

**Governance 狀態：**

```
P1 backlog:               EMPTY
AC-6 blockers:            0
Research blockers:        0
Data blockers:            0
Observability blockers:   0
```

---

## 今日 Commits

```
1beb8ff  test(obs): regression tests for P1-OBS fatal self-alert
41849e2  fix(obs): move run_at outside try block to prevent UnboundLocalError
e8f4dc3  fix(obs): self-alert intraday monitor fatal failures
f9c4b3c  chore(data): retire obsolete security lifecycle ingest script
e6c58c9  feat(calendar): three-layer hybrid trading calendar v0.2.0; add twse_holidays migration and ingestion
```

---

## P1 Closeout 總表

| Ticket | 最終狀態 | 證據 |
|---|---|---|
| TWSE-HOLIDAY-CAL | **CLOSED** | XTAI + TWSE API holiday ingestion；`trading_calendar.py` v0.2.0 三層 hybrid；44 regression tests PASS |
| P1-DATA-FOLLOWUP | **CLOSED** | `ingest_security_lifecycle.py` retired（tombstone + SystemExit）；pytest guard 1 passed |
| P1-OBS | **CLOSED** | fatal self-alert（Telegram）+ DuckDB lock retry（3×5s）+ sentinel DB row；`system_alert_sent` 動態化；17 regression tests PASS |
| IF-3A / DQ-CA-001A | **CLOSED** | commit `76f1f45`；dividend/split ingestion；coverage 20 → 199 symbols；1,106 rows |
| IF-3B / DQ-CA-001B | **RECLASSIFIED P2** | composition audit；r8_events confirmed halt-resumption = 0；non-binding |
| DQ-ADJ-003 | **CLOSED** | 2327 adj anomaly = capital reduction event；正確分類 |

---

## 各 Ticket 技術摘要

### TWSE-HOLIDAY-CAL

**架構：三層 hybrid（優先順序高→低）**

| Layer | 來源 | 覆蓋範圍 |
|---|---|---|
| 1 | `twse_holidays` DB table（TWSE OpenAPI） | 當年度官方公告（24 筆/年，3 筆交易日通知已過濾） |
| 2 | `exchange_calendars` XTAI | 2006-06-07 → 2027-06-07（含颱風假） |
| 3 | `TW_HOLIDAYS_FALLBACK` | 2027-06-08 之後的 safety net |

**年度維護事項：**
- 每年初執行 `uv run python scripts/ingest_twse_holidays.py`
- `exchange_calendars` 升版後確認 XTAI `last_session`，縮減 Fallback 範圍

**新增檔案：**
- `market/trading_calendar.py` v0.2.0
- `scripts/migrate_add_twse_holidays.py`
- `scripts/ingest_twse_holidays.py`
- `tests/test_trading_calendar_v0_2_0.py`

---

### P1-DATA-FOLLOWUP

`scripts/ingest_security_lifecycle.py` 針對舊 schema（`otc_first_date, mainboard_date`），與現行 PIT schema（`listed_from, listed_to`）完全不相容。已 tombstone，執行立即 `SystemExit`。

**Canonical seed tool：** `scripts/seed_security_lifecycle.py`（保留，針對現行 schema）

**新增檔案：**
- `tests/test_retired_scripts.py`（tombstone guard）

---

### P1-OBS

**Root cause（production logs 2026-05-28/29）：**
```
DuckDB IOException: Could not set lock on helios.duckdb
```
Monitor 在 `connect()` fatal，不寫 DB row，不送 Telegram。

**修正內容（`scripts/intraday_monitor.py` v0.1.16）：**

| 函式 | 用途 |
|---|---|
| `_is_duckdb_lock_error(exc)` | 精確識別 DuckDB lock conflict（type + message） |
| `_connect_with_retry()` | 3×5s retry on lock error，非 lock error 立即 raise |
| `_send_fatal_alert(run_at, detail)` | 即時 Telegram alert，回傳 bool（實際送出狀態） |
| `_write_fatal_run_row(run_at, detail, sent)` | sentinel DB row，`system_alert_sent` = 實際送出結果 |

**設計決策：**
- `fcntl` process lock 不 retry（保持原 no-overlap semantics）
- `run_at` 移到 `try` 外（防 `UnboundLocalError`）
- `system_alert_sent` 絕不 hardcode（observability 語意）

**新增檔案：**
- `tests/test_intraday_monitor_fatal.py`（17 tests，AC-1/AC-2/AC-3）

---

## 當前 Backlog 狀態

### P2 — OPEN

| ID | 描述 | 備註 |
|---|---|---|
| IF-3B | suspension/halt dataset — FinMind + MOPS 待查 | non-binding，source discovery spec v0.1.1 存在 |
| IF-2 → P2 | stock_info population pipeline | — |
| BACKLOG-IF1-GUARD | repo-wide pytest guard: no direct `daily_price_adj` outside allowlist | — |
| r8_forward_returns 差異 | A-3 panel SQL vs `r8_benchmarks.py` n 不一致原因 | n=4,021 vs ~5,030 |
| P2-OBS | Healthcheck Single Run Gap | — |

### P3 — OPEN

| ID | 描述 |
|---|---|
| P3-OPS | Session Write Lock Policy（pairs with P1-OBS retry） |

---

## 下個 Session 的起點

P1 backlog 已清零。下個工作區間建議：

**選項 A：P2-RESEARCH（Phase 1 findings promotion）**
- Phase 1 findings 從 PROVISIONAL → CONFIRMED 的正式文件化
- Benchmark C fingerprint 鎖定後的 downstream implications

**選項 B：P2-DATA（IF-3B source discovery）**
- FinMind suspension/halt API feasibility
- MOPS/TWSE 歷史停牌資料評估

**選項 C：Phase 2 研究規劃**
- R8 Phase 2 設計
- 新策略 backlog

開始前請讀：

```bash
cat ~/projects/helios/research/r8_phase1_interim_findings.md   # v0.2.0 CONFIRMED
cat ~/projects/helios/research/r8_phase1_lifecycle_spec.md     # v0.1.6
```

---

## Status Invariant

```
P1 backlog:     EMPTY
AC-6:           CLOSED
Phase 1 findings: CONFIRMED (measurement scope only)
```

---

*End of handoff_2026_06_07_p1_closeout.md*
