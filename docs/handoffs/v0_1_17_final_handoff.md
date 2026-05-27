# Helios v0.1.17 Session Handoff — 2026-05-27 (final)

**Status:** v0.1.17 TAGGED (ce48da8), all backlog items resolved
**Next:** v0.1.18 — multi-account architecture (#23)

---

## 1. Git HEAD

```
b54f0d6 (HEAD -> main) docs: v0.1.17 final handoff
ce48da8 (tag: v0.1.17) feat: v0.1.17 step 7 — update_order_spec fix + E2E
19acbfc feat: v0.1.17 steps 5+6 — cron entries + open-gap calibration (#16)
d50ab7a feat: v0.1.17 step 4 — startup_recovery handles stale READY_FOR_SUBMISSION
a04bc53 feat: v0.1.17 step 3 — execution_submitter + cancel sweep
6302f15 feat: v0.1.17 step 2 — daily_run decoupled from broker
ad17a75 feat: v0.1.17 step 1 — READY_FOR_SUBMISSION status + target_fill_date schema migration
```

---

## 2. v0.1.17 完成項目

| Backlog | 狀態 |
|---------|------|
| #15 Decouple signal/submission | ✅ done |
| #16 Open-gap calibration | ✅ 0.03 [CALIBRATED] P95=2.97% |
| #17 READY_FOR_SUBMISSION schema | ✅ done |

### Architecture delivered

```
T  16:00  daily_run
            → generate signals
            → record_intent → mark_ready_for_submission
            → Telegram: queued summary
            → NO broker API call (INV-1)

T+1 08:30  execution_submitter --mode submit
            → read READY_FOR_SUBMISSION WHERE target_fill_date = today
            → pre-submission checks
            → limit_price = prev_close × (1 + 0.03) (INV-2)
            → Shioaji LMT ROD → mark_submitted
            → Telegram: submission summary

T+1 09:05  execution_submitter --mode cancel
            → cancel stale SUBMITTED
            → expire leftover READY_FOR_SUBMISSION

T+1 16:00  daily_run (next cycle)
            → startup_recovery resolves orphans + stale READY
```

### Cron 時序（完整）

```
08:30  execution_submitter --mode submit
09:05  execution_submitter --mode cancel
09-13  intraday_monitor (每 15 分鐘, :05/:20/:35/:50)
15:30  auto_backup
16:00  shioaji_download + build_adjusted + compute_features +
       bearish/bullish features + daily_run
16:05  signal_preview
16:30  find_bearish_stocks
16:35  score_short_candidates
16:40  find_bullish_setups
19:30  evening_digest
```

---

## 3. 明天觀察重點

| 時間 | 觀察 | Log |
|------|------|-----|
| 08:30 | execution_submitter 第一次跑（應該 0 orders） | logs/execution_submitter.log |
| 09:05 | cancel sweep（應該 0 stale） | logs/execution_submitter.log |
| 16:00 | daily_run 產生 READY_FOR_SUBMISSION | logs/daily_run_cron.log（看 `queued=`）|
| 16:00 | daily_quotes rows ≥ 1500 | logs/daily_run_cron.log |

---

## 4. 已知問題

| 問題 | 狀態 | 影響 |
|------|------|------|
| `paper_broker._record_order` stale schema | pre-existing v0.1.16 | blocks test_fill_and_drift_gate |
| Shioaji cancel API semantics (Q3) | deferred to P-obs-2 | cancel sweep marks EXPIRED without broker cancel |
| daily_quotes 16:00 rows count | 明天觀察 | 如果 < 1500 需調整 cron 或改用 snapshots |

---

## 5. 完整 Backlog

| # | 標題 | Priority | Version |
|---|------|----------|---------|
| #15 | Decouple signal/submission | P0 | ✅ v0.1.17 |
| #16 | Open-gap calibration | P1 | ✅ v0.1.17 |
| #17 | READY_FOR_SUBMISSION schema | P0 | ✅ v0.1.17 |
| #18 | Bearish outcome study (MAE/ATR fix) | P0 | v0.2 |
| #19 | bullish_features layer | — | v0.2 |
| #20 | Notification abstraction | — | v0.2 |
| #21 | Shioaji daily_quotes pipeline + data_ready_semantics | — | v0.2 |
| #22 | daily_price source provenance | — | v0.2 |
| #23 | Multi-account architecture | P0 | **v0.1.18** |
| #24 | MACD + Lower-Highs-Lows feature expansion | — | v0.2 |
| #25 | intraday_monitor recovery notification | — | v0.2 |
| #26 | paper_broker._record_order stale schema fix | P1 | v0.1.18 or v0.2 |

---

## 6. v0.1.18 Scope: Multi-Account (#23)

### 目標

DB tables 加 `account_id`，讓 orders/positions 可以區分帳號。
v0.2 multi-account P&L 依賴此基礎。

### 改動估計

| 層級 | 改動 | 大小 |
|------|------|------|
| Schema | orders + positions ADD account_id (recreate) | 小 |
| order_journal.py | 所有 query 加 account_id filter | 中 |
| positions storage | 同上 | 中 |
| daily_run.py | 傳 account_id | 小 |
| execution_submitter.py | 傳 account_id | 小 |
| startup_recovery.py | account_id filter | 小 |
| intraday_monitor.py | per-account position lookup | 中 |
| reconcile_fills.py | per-account reconcile | 中 |
| config/account_config.py | 已有 v0.1.17-A stub | 小 |
| Tests | 帶 account_id | 中 |

估計：1.5–2 sessions。

### 設計決策（pre-register）

1. `account_id` NOT NULL（新 rows），backfill 現有 rows 用 default account
2. `account_id` 作為 compound key 的一部分（不改 PK，加 index）
3. `config/accounts.yaml` 已有結構，`_account.account_id` 已在 daily_run 可用
4. `--account all` 仍然 gated（v0.1.17-A guard 已存在）

### 開工前需要的資料

```bash
# 1. accounts.yaml 結構
cat config/accounts.yaml

# 2. positions table schema
uv run python -c "
import duckdb
conn = duckdb.connect('data/_storage/helios.duckdb', read_only=True)
for r in conn.execute('DESCRIBE positions').fetchall(): print(r)
"

# 3. positions rows count
uv run python -c "
import duckdb
conn = duckdb.connect('data/_storage/helios.duckdb', read_only=True)
print('positions:', conn.execute('SELECT COUNT(*) FROM positions').fetchone())
print('orders:', conn.execute('SELECT COUNT(*) FROM orders').fetchone())
"

# 4. account_config.py load_accounts interface
head -60 config/account_config.py

# 5. 現有 --account 參數怎麼用的
grep -n "account" scripts/daily_run.py | head -15
```

---

## 7. DB 狀態

```bash
uv run python -c "
import duckdb
conn = duckdb.connect('data/_storage/helios.duckdb', read_only=True)
print('orders:', conn.execute('SELECT status, COUNT(*) FROM orders GROUP BY status').fetchall())
print('positions OPEN:', conn.execute(\"SELECT symbol, entry_price FROM positions WHERE status='OPEN'\").fetchall())
print('daily_price max:', conn.execute('SELECT MAX(date) FROM daily_price').fetchone())
"
```

---

## 8. 下次對話帶回來

1. **這份 handoff**
2. `tail -20 logs/execution_submitter.log`（08:30 + 09:05 output）
3. `tail -30 logs/daily_run_cron.log`（16:00 output，看 `queued=`）
4. §6 裡的 5 個開工前指令的輸出
