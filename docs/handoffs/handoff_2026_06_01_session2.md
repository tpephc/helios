# Helios Handoff — 2026-06-01 (Session 2)

Continues `handoff_2026_06_01.md` (Session 1: R8 Phase 0, healthcheck deploy).
This session covers: operational diagnosis (no Telegram entry notification),
sector classification bug fix, Forward Return Tracker stock name fix, trading
capital refactor, equity reset, duplicate signal hotfix, and signal storage
idempotency backlog.

All figures from live DB queries executed this session. No estimates.

---

## 1. 問題診斷：今日未收到進場通知

**起因：** 用戶未收到 Telegram 進場通知。

**診斷路徑：**

1. intraday_monitor — 正常（20/20 runs，無 fatal，無 skip）。今日無 zone transition，`alerts_sent=0` 是正確行為。
2. 三個既有持倉（4919、2891、8210）均為上週開倉（5/27、5/28），今日無新開倉。
3. `daily_run.py` 今日 `as_of=2026-05-29`（正確：`previous_trading_day` 回傳上個交易日），有產生 6 個 breakout 訊號候選，但全部被 `sector_cap_unknown` 擋掉。

**根本原因：`sector_cap_unknown`（見 Section 2）。**

**附帶確認：18 vs 20 expected runs 問題解決。**
兩個 post-close fires（13:37、13:52）確認都有寫 DB row，`--expected-runs 20` 是正確值，不需要修改。

---

## 2. Bug Fix：sector 分類改為動態查表

**問題：** `portfolio/selector.py` 的 `SECTOR_MAP` 只硬編碼 15 支股票。Universe 擴展到 200+ 支後，未登錄的股票全部回傳 `unknown`。今日 8210（已持倉，notional 190,590）和 6 個新 breakout 候選都是 `unknown`，合計超過 sector_cap 30%，全部觸發 `sector_cap_unknown`。

**修復：** `selector.py` v0.2.0

- `SECTOR_MAP` 移除，改為查詢 `company_metadata.industry_code`
- 新增 `INDUSTRY_SECTOR_MAP`：30 個 TWSE 產業代碼 → sector 標籤
- `lru_cache` 避免每次呼叫重複開 DB 連線
- `__init__.py` 對應更新：`SECTOR_MAP` → `INDUSTRY_SECTOR_MAP`
- 備份：`portfolio/selector.py.pre_v0_2_0.bak`

**驗證：** `process_entries.py --as-of 2026-05-29` 修復後產生 2 個 PENDING 訊號（1605 華新 industrials、2357 華碩 electronics），4 個候選因 `max_positions_reached` 被擋（正確行為）。

**Commit：** `24e4665` `fix(portfolio): replace hardcoded SECTOR_MAP with dynamic industry_code lookup`

---

## 3. Fix：Forward Return Tracker 股票簡稱

**問題：** `tracker_digest.py` JOIN `stock_info` 表取 `stock_name`，但 `stock_info` 表為空（已知 DQ 問題），導致 Telegram 訊息無股名。

**修復：** JOIN 改為 `company_metadata.short_name`，截斷從 `[:4]` 改為 `[:5]`。

**驗證：** evening digest 手動觸發，Telegram 訊息正確顯示股名（中華電、強茂、全新、中信金等）及即時報酬。

**Commit：** `a518947` `修復：Forward Return Tracker 改從 company_metadata 取得股票簡稱`

---

## 4. Refactor：trading capital 統一管理

**問題：** `daily_run.py` 和 `process_entries.py` 各自有 `default=1_000_000` 的 argparse，兩個 default 獨立存在，容易產生不一致。

**修復：**

- `accounts.yaml` / `AccountConfig` 新增 `trading_capital` 欄位
- 兩個腳本的 `--capital` 改為 optional override，預設從 `_account.trading_capital` 讀取
- `philip_sim`：`trading_capital: 100000`

**Commit：** 包含在 `a49646c`

---

## 5. Feature：equity_reset_date 機制

**背景：** 三個既有持倉（4919、2891、8210）是在 1,000,000 capital 下開的，capital 改成 100,000 後，`_account_equity()` 計算出 cash = -381,787（positions_value 437,640 > capital 100,000）。

**手動平倉：** 三個持倉以 last_close 價格強制平倉，exit_reason = `manual_close_capital_reset`，exit_date = 2026-06-01。

**equity_reset_date 機制：**

- `AccountConfig` 新增 `equity_reset_date: date | None`
- `_account_equity()` 新增同名參數：`exit_date <= equity_reset_date` 的已平倉記錄不計入 PnL
- `philip_sim`：`equity_reset_date: "2026-06-01"`
- 效果：equity 重設為 NTD 100,000（全新起點）

**Commit：** `a49646c` `修復：交易資本改從 account config 讀取，新增 equity 重設機制`

---

## 6. Crontab 變更：--auto-approve 加入 daily_run

`daily_run.py` 的 crontab 加入 `--auto-approve`，之後每日 16:00 收盤後自動 approve 訊號並開倉，不再需要手動 Telegram approve。

```
0 16 * * 1-5  ... scripts/daily_run.py --auto-approve --as-of $(...)
```

此為系統狀態變更，未 commit 至 repo。

---

## 7. Pending 訊號清理

今日重複執行 `process_entries.py` 產生 14 筆 PENDING 訊號（1605、2357、6531、8210 各有重複），全部手動 REJECT（`approved_by = manual_reject_capital_reset`）。

---

## 8. Hotfix：重複 active signal guard

**問題：** `process_entries.py` 的 breakout 路徑沒有重複訊號 guard（pullback 的 `generate_pending_signals()` 路徑已有 `_has_active_signal_for()`，但 breakout 和 `main()` 路徑沒有）。重複執行會對同一個 `(symbol, strategy, signal_type, signal_date)` 寫入多筆 PENDING/AUTO_APPROVED 訊號。

**修復：** 在以下三個路徑加入 `_has_active_signal_for()` guard：

1. `generate_pending_signals()` breakout loop（cron 路徑）
2. `main()` breakout loop（手動執行路徑）
3. `main()` pullback loop（手動執行路徑）

**驗證：** 連跑兩次 `process_entries.py --as-of 2026-05-29`，第二次正確觸發 `skip_duplicate_signal`，DB active signal count 未增加。

**語意說明：** 這是「避免 active duplicate signal」的 application-level hotfix，不是完整的 Signal Event idempotency。`_has_active_signal_for()` 只擋 PENDING/APPROVED/AUTO_APPROVED，REJECTED/EXPIRED/TIMEOUT 狀態的同一事件可以重新產生（語意上是否正確尚未決定）。

**Commit：** `96391af` `fix(entries): guard duplicate active signals before save`

---

## 9. Backlog：P1-OPS Signal Storage Idempotency

**新增 backlog：** `docs/backlog/P1-OPS_signal_storage_idempotency.md`

兩個已知 gap 需要後續處理：

1. **TOCTOU race condition：** 兩個 process 同時通過 guard 仍可能各自 INSERT。
2. **Terminal-state re-generation：** REJECTED/EXPIRED signal 可以重新產生新 `signal_id`，event history 分裂。

**必要的 storage-level fix：**

- `save_signal()` 改為回傳 `SaveSignalResult(signal_id, created)`
- DB `UNIQUE(symbol, strategy, signal_type, signal_date)` constraint
- 所有呼叫端（21 個 call site）更新：`created=False` 時跳過 Telegram 通知
- 現有重複 row（REJECTED 狀態）在加 constraint 前需先清理

**Commit：** `57f2147` `docs(backlog): P1-OPS signal storage idempotency`

---

## 10. 目前系統狀態

```
持倉：          0（全部平倉重設）
equity：        NTD 100,000
per_position：  NTD 20,000（20% × 100,000）
sector 分類：   動態查表，universe 200+ 支全覆蓋
auto-approve：  啟用（crontab，明日 16:00 起生效）
PENDING 訊號：  0
duplicate guard：啟用（breakout + pullback 所有路徑）
```

**per_position = 20,000 的實際意涵：**
- 整股（1000 股）：只有股價 ≤ 20 元的股票可以買整股
- 零股：paper_broker 自動走 ODD lot 路徑（已確認盤中零股支援）
- 高價股（如 2357 華碩 761 元）：約可買 26 股零股

**Forward Return Tracker 目前狀態（2026-06-01）：**

```
PULLBACK  4 signals in progress
  7750 新代   D5/20  -12.90%  TS
  2354 鴻準   D2/20   +5.99%  TO
  8210 勤誠   D2/20   +2.49%  TO
  8210 勤誠   D0/20       —   RJ

BREAKOUT  14 signals in progress
  2412 中華電  D9/20   -1.85%  TO
  2481 強茂    D9/20  +14.15%  TO
  2455 全新    D8/20   +0.89%  TO
  2891 中信金  D8/20   +6.80%  TO
  6139 亞翔    D7/20   -4.29%  TO
  3042 晶技    D6/20   +4.20%  TO
  2455 全新    D5/20   -5.70%  TS
  4919 新唐    D5/20   -8.41%  TS
  6442 光聖    D4/20  -17.77%  TO
  1773 勝一    D3/20   -6.54%  TO
  2882 國泰金  D3/20   +2.83%  TO
  （1605/2357/6531 今日 RJ，D0 無報酬）
```

upstream dup warning（raw 48 → dedup 18）為歷史累積，hotfix 後不再增加。

---

## 11. 下一個 Session 待辦

- **P1-OPS signal storage idempotency：** `save_signal()` contract + DB UNIQUE constraint + 21 個 call site 更新（見 `docs/backlog/P1-OPS_signal_storage_idempotency.md`）
- **R8 Phase 1 SPEC 進 repo：** `r8_phase1_lifecycle_spec.md` v0.1.1 尚未 commit 至 repo（目前為本地 artifact）
- **P1-DATA panel integrity：** `P1-DATA_panel_integrity_assessment.md` 同上
- **Artifact C：** `docs/decision_records/r8_phase1_governance.md` 尚未產出
- **upstream dup 歷史清理：** signals 表現有重複 REJECTED rows 需在加 UNIQUE constraint 前清理

---

## 12. Commit 記錄（今日，全部已 push 至 origin/main）

| Hash | 說明 |
|------|------|
| `57f2147` | docs(backlog): P1-OPS signal storage idempotency |
| `96391af` | fix(entries): guard duplicate active signals before save |
| `a49646c` | 修復：交易資本改從 account config 讀取，新增 equity 重設機制 |
| `a518947` | 修復：Forward Return Tracker 改從 company_metadata 取得股票簡稱 |
| `24e4665` | fix(portfolio): replace hardcoded SECTOR_MAP with dynamic industry_code lookup |
| `80d8639` | feat(monitoring): intraday monitor post-close healthcheck v0.1.0（Session 1） |
