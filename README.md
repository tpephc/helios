# Helios — 個人版機構級台股中長期自動投資系統

> Version: v0.1.5 (2026-05-16) — 防禦性 hardening：FetchResult success/error / FinMind sort+unique / cache schema version + trading-day-aware
> v0.1 — Step 2 of 12 (data + storage + market layers)
> 目標環境: Ubuntu Server x86_64, Python 3.12, uv

## 系統定位

- 中低頻、中長期、多因子自動化投資系統
- 持股週期: 數天 ~ 數月
- 執行模式: Human-in-the-loop (Telegram 確認後下單)
- AI 角色: Regime 判斷與訊號過濾, 非價格預測

完整架構見 `docs/architecture.md`。

## v0.1 Step 1+2 — 已完成

```
config/    Pydantic Settings + YAML (universe / strategy / risk_limits)
data/      DuckDB schema + Parquet cache + FinMind client + 統一 fetcher
storage/   Signal/Order event log + position computation + daily snapshots
market/    台股交易日曆 (hybrid: DB + fallback holidays)
utils/     structlog JSON logger
scripts/   init_db.py — 初始化資料庫 schema 與股票基本資料
```

## 安裝

```bash
# 1. 安裝 uv (若尚未安裝)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 安裝主依賴 (Step 1+2 用)
cd helios
uv sync

# 3. 設定環境變數
cp .env.example .env
# 編輯 .env，填入 FINMIND_TOKEN (從 https://finmindtrade.com 取得)
```

**注意**：`.python-version` 已 pin Python 3.12。uv 第一次 sync 若系統沒裝 3.12 會自動下載。
`pandas-ta` 與 `vectorbt` 透過 `numba` 帶入 `llvmlite`，在 Python 3.13+ 的 wheel 仍不完整，
故 3.12 為**最穩**的選擇。

**之後 Step 開始時才裝**：

```bash
uv sync --group features   # Step 3：pandas-ta 指標庫 (純 Python，pin <0.4)
uv sync --group backtest   # Step 6：vectorbt 回測引擎
uv sync --group comm       # Step 8：python-telegram-bot v20+
```

## 第一次使用

```bash
# 初始化資料庫
uv run python scripts/init_db.py

# 驗證 (應顯示 12 張 tables, ~1700 檔股票)
uv run python -c "
from data.database import list_tables, connect
print('Tables:', list_tables())
with connect(read_only=True) as c:
    n = c.execute('SELECT COUNT(*) FROM stock_info').fetchone()[0]
    print('Stocks:', n)
"
```

## 開發

```bash
# Lint + format
uv run ruff check .
uv run ruff format .

# Type check
uv run mypy .

# Test (v0.1 Step 12 才會有完整測試)
uv run pytest
```

## 目錄結構

```
helios/
├── config/                 Settings + YAML
├── data/                   抓取、快取、DB
│   └── sources/            FinMind 等資料源實作
├── utils/                  通用工具 (logger)
├── scripts/                CLI 入口
├── tests/                  測試 (待 Step 12)
├── notebooks/              研究筆記本
└── docs/                   架構文件
```

## 路線圖

完整 12 個 Step 見 `docs/architecture.md` 第十一節。

| Step | 模組 | 狀態 |
| ---- | ----------------------------------------------------- | ---- |
| 1    | config + data layer                                   | ✅ v0.1.0  |
| 2    | storage + market (event log + 交易日曆)               | ✅ v0.1.0  |
| 3    | features/technical (MA/RSI/ATR/MACD/SuperTrend)       | ⏳   |
| 4    | strategies (plain fn + reason)                        | ⏳   |
| 5    | risk (ATR 部位 / 回撤控制 / 熔斷)                     | ⏳   |
| 6    | backtest engine (vectorbt + validator)                | ⏳   |
| 7    | runtime (TradeState + state_store + event_bus)        | ⏳   |
| 8    | communication/telegram                                | ⏳   |
| 9    | scripts/helios_cli.py                                 | ⏳   |
| 10   | monitoring/alerts.py                                  | ⏳   |
| 11   | execution/paper_trading                               | ⏳   |
| 12   | tests                                                 | ⏳   |

## 風險與紀律

- v0.1 **僅支援 paper trading**，禁止真實下單 (Shioaji 整合於 v0.4)
- 所有訊號需經 Telegram 確認；timeout 30 分鐘 **或** 價格偏離 entry 0.5 ATR 自動失效
- 部位上限：ETF 15%、個股 10%；最大持倉 10 檔
- **Regime-adjusted exposure**：strong_bull 80% → weak_bull 50% → neutral 40% → bear 20% → crisis 0%
- **Graduated circuit breaker**：日內 1.5% 警示 → 2% 軟降 (新倉 ×0.5) → 3% 硬停
- 帳戶最大回撤 15% 全面停手
- Bear regime：個股禁止，僅 ETF 可進倉 (risk-off 而非 shutdown)
