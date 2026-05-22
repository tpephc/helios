# Intraday Monitor — Operations Guide

## 觸發機制

每個交易日 09:05–13:50，每 15 分鐘由 cron 啟動一個獨立 process。
每次啟動是無狀態的 — 所有持久狀態都在 DB。

Cron: `5,20,35,50 9-13 * * 1-5`
Log: `logs/intraday_monitor.log`

## 執行流程

1. 取得 file lock（防止 cron overlap）
2. 讀取所有 OPEN positions（排除 entry_atr=0 等無效資料）
3. 透過 yfinance 取得當前價格（約 15-20 分鐘延遲）
4. 計算 feed success rate
   - < 50%：推送系統異常通知（60 分鐘 cooldown 內不重複推送）
   - 繼續處理有效報價（異常通知失敗不得中斷 position supervision）
5. 逐一檢查每個 position：
   - 報價 stale 或 None → 跳過（不觸發 transition）
   - 計算停損水位，對照上次儲存的 zone，計算新 zone
   - zone 有變化 → 寫入 DB + 推送 Telegram
6. 寫入 run metadata（intraday_monitor_runs）
7. 釋放 file lock

## 狀態機

```
trailing_stop  = max_close_since_entry - 2.0 × entry_atr
approach_enter = trailing_stop + 0.5 × entry_atr
approach_exit  = trailing_stop + 0.8 × entry_atr
```
NORMAL   ──(price ≤ approach_enter)──────────────────► APPROACH
APPROACH ──(price > approach_exit)───────────────────► NORMAL
APPROACH ──(price ≤ trailing_stop)───────────────────► BREACH
BREACH   ──(price > approach_exit)───────────────────► NORMAL
BREACH   ──(trailing_stop < price ≤ approach_exit)───► APPROACH
任何 zone ──(price ≤ trailing_stop)──────────────────► BREACH（無條件）
NORMAL ↔ APPROACH 有 0.3×ATR dead-band（Schmitt trigger，防震盪）。
BREACH ↔ APPROACH 無 hysteresis，每次跨越都觸發通知（設計意圖）。

## 通知邏輯

| 轉換 | 訊息 |
|---|---|
| NORMAL → APPROACH | ⚠️ 接近停損 |
| * → BREACH | 🔴 觸及停損 |
| BREACH → APPROACH | ↗️ 停損區部分回升 |
| * → NORMAL | ✅ 已脫離警示 |

系統異常通知（feed degraded）有 60 分鐘 cooldown。

## 關鍵設計保證

- **Outbox pattern**：DB COMMIT 在 Telegram send 之前，crash 不遺失 transition 記錄
- **冪等性**：`UPDATE WHERE zone = prev_zone RETURNING position_id`
- **系統異常隔離**：bot exception 不中斷 position supervision
- **只通知，不平倉**：positions 表在整個執行過程中不被寫入

## DB Tables

- `intraday_alert_state` — 每個 position 的當前 zone
- `intraday_alert_transitions` — append-only 轉換 log（notification_status: PENDING/SENT/FAILED）
- `intraday_monitor_runs` — 每次執行的 metadata

## 查詢指令

```bash
# 最近 20 次執行
uv run python -c "
from data.database import connect
with connect(read_only=True) as conn:
    rows = conn.execute('''
        SELECT run_at, positions_checked, transitions_logged,
               alerts_sent, system_alert_sent, error_summary
        FROM intraday_monitor_runs
        ORDER BY run_at DESC LIMIT 20
    ''').fetchall()
    for r in rows: print(r)
"

# FAILED 通知（未送達的 transition）
uv run python -c "
from data.database import connect
with connect(read_only=True) as conn:
    rows = conn.execute('''
        SELECT position_id, transitioned_at, from_zone, to_zone, price
        FROM intraday_alert_transitions
        WHERE notification_status = 'FAILED'
        ORDER BY transitioned_at DESC
    ''').fetchall()
    for r in rows: print(r)
"
```
