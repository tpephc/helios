# Helios Changelog

專案層級的變更紀錄。檔案層級的細節版號在各檔案 docstring 內。

格式：[Keep a Changelog](https://keepachangelog.com/) + [Semantic Versioning](https://semver.org/)。

## [Unreleased]

### Planned for Step 2.5 (v0.1.6) — Real Data Ingestion + Systematic Profiling
- `scripts/download_daily.py` — 抓 2330 / 0050 / 006208 / 0056 / 00878 / TAIEX / 主流產業 ETF 的 5 年日 K
- `scripts/data_quality_report.py` — 系統化 profiling，產出 JSON + Markdown 報告
- `notebooks/01_data_behavior.ipynb` — 視覺探索
- `docs/data_behavior_notes.md` — 累積學習檔（Step 3 indicators 的需求來源）

---

## [v0.1.5] — 2026-05-16

### Added — 防禦性 hardening (採納外部 review)
- **`data/fetcher.py::FetchResult`** 加 `success: bool` + `error: str | None` 欄位
  - 解決「空 DataFrame 語意混淆」：success=True 空資料 (該期間無交易) vs success=False (fetch 失敗)
  - 下游應檢查 `result.success`，不再用 `result.data.is_empty()` 判斷錯誤
- **`data/sources/finmind_client.py`** 所有 return path 強制 `sort + unique`
  - daily_price / institutional / monthly_revenue / taiex / stock_info 全部加上
  - 主因：FinMind 偶爾回傳重複日（盤後 rerun）或亂序，下游不該被迫處理
- **`data/sources/finmind_client.py`** 數值欄位改用 `cast(strict=False)`
  - API 偶發 null / 空字串時轉為 null 而非整批炸錯
- **`data/cache.py`** 加 `CACHE_SCHEMA_VERSION = 1` 常數，嵌入快取檔名
  - 未來欄位語意/型別變動時 bump 版號，舊 cache 自動失效（hash 不同）
- **`data/cache.py`** 新增 trading-day-aware cache mode
  - `get_for_trading_day()` / `set_for_trading_day()`
  - 用「最後一個 trading day」當 key 一部分，跨 trading day 自動 invalidation
  - 比 TTL 更貼合 market data 性質 (盤後 14:30 後新資料才公佈)
- **`data/cache.py`** 加 `clear_old_schema_versions()` 清理孤兒舊版本檔

### Removed
- `[dependency-groups].features` (即 `pandas-ta>=0.3.14b,<0.4`)
  - 原因：pandas-ta 0.3.x 已從 PyPI 下架，constraint 無法解析
  - Step 3 開工時再評估 indicator 庫選項 (pandas-ta 0.4.x / TA-Lib / Polars-native)

### Changed
- `data/fetcher.py::daily_price` 與 `taiex` 預設 `cache_mode="trading_day"` (legacy TTL 保留)

### Bumped
- `pyproject.toml` 0.1.4 → 0.1.5
- `data/fetcher.py` v0.1.0 → v0.1.1
- `data/sources/finmind_client.py` v0.1.0 → v0.1.1
- `data/cache.py` v0.1.0 → v0.1.1

---

## [v0.1.4] — 2026-05-16

### Fixed
- **依賴問題**：`pandas-ta` (0.4.x) 與 `vectorbt` 透過 `numba` 帶入 `llvmlite`，
  在 Python 3.13/3.14 上 wheel 未跟上、source build 失敗（setuptools API 衝突）
  - `pandas-ta` 從 main `dependencies` 移到 `[dependency-groups].features`，pin `<0.4`
    避開 numba（0.3.x 是純 Python era）
  - `vectorbt` 從 main `dependencies` 移到 `[dependency-groups].backtest`
- **`.python-version`** 新增於專案根，pin Python `3.12` 讓 uv 自動選對版本
  - Python 3.14 上預編 wheel 對 numba/llvmlite 仍不完整，3.12 是最穩的選擇

### Changed
- `uv sync` 預設只裝主依賴 (Step 1+2 所需)，pandas-ta/vectorbt 等 Step 3+ 才裝
- Step 3 開始：`uv sync --group features`
- Step 6 開始：`uv sync --group backtest`

### Bumped
- `pyproject.toml` 0.1.3 → 0.1.4

---

## [v0.1.3] — 2026-05-16

### Added
- **`scripts/validate_install.py`** — 自我診斷腳本，11 項檢查覆蓋 Python 版本、套件、目錄權限、Settings、Logger、DuckDB schema、Storage 端到端、Trading calendar、(可選) FinMind 連線。`uv run python scripts/validate_install.py [--with-api]`

### Code Review 修復 (7 項)

**🔴 Bug fixes:**
- **`storage/signals.py::update_approval`** 改用 `UPDATE...RETURNING` 確保原子性
  - 修掉 UPDATE+SELECT 之間的 race window
  - 同時減少 1 次 round-trip (hot path)
- **`storage/signals.py::expire_drifted`** 改批次處理
  - 原本 N+1 query (100 pending = 200+ DB calls)，改成 1 SELECT + N UPDATE
  - 統一 log 一次，不洗 200 行
- **`storage/orders.py::has_duplicate_recent`** 新增 `exclude_order_id` 參數
  - 修掉「剛 record 完馬上 check 會把自己當 duplicate」的 API 缺陷
  - 讓 runtime 可在 record 後做事後驗證
- **`storage/positions.py::_apply_fill`** 過量賣出處理
  - 賣超過持有量時 clamp 到實際持有量 + log warning
  - 修掉假 realized_pnl（賣 2000 但只有 1000 時錯算成 10× 利潤）

**🟡 Design fixes:**
- **`market/trading_calendar.py`** DB 缺 TAIEX 資料時 log warning
  - 避免使用者誤以為 fallback 規則準確（颱風假可能被誤判為交易日）
  - 同日只 warn 一次，避免回測時瘋狂洗 log
- **`utils/logger.py`** 檔案輪轉用 `settings.timezone`
  - UTC server 上原本 log 檔以 UTC 切日，現在以 Asia/Taipei 切日
  - `_add_timestamp` processor signature 改為 `MutableMapping` 符合 structlog 介面

**🔵 Lint / Style:**
- ruff config 排除 RUF001-003（中文標點 false positive）
- 修 17 個 import 排序、5 個 `__all__` 排序、10 個 `zip(..., strict=True)`、4 個 ternary、1 個 dead variable
- 結果：`ruff check .` 全綠

### Bumped
- `pyproject.toml` 0.1.2 → 0.1.3
- `storage/signals.py`         v0.1.0 → v0.1.1
- `storage/orders.py`          v0.1.0 → v0.1.1
- `storage/positions.py`       v0.1.0 → v0.1.1
- `market/trading_calendar.py` v0.1.0 → v0.1.1
- `utils/logger.py`            v0.1.0 → v0.1.1

### 未處理 (留到 v0.1.4)
- 34 個 mypy strict 嚴格度警告 (`dict` 沒參數化、`fetchone()[0]` 沒 None 檢查、smoke test `__main__` block None access) — 不影響 runtime，留待專門的 type cleanup pass

---

## [v0.1.2] — 2026-05-16

### Changed
- **檔案命名慣例**：每個 code/config 檔案的第一行加上「相對於專案根的路徑註解」
  - 套用範圍：.py / .yaml / .toml / .env.example (共 23 個檔案)
  - 不套用：.md（自身會被閱讀） / .gitignore
- **`docs/versioning.md`** 新增「路徑註解規範」章節
- **`pyproject.toml`** 版本 0.1.1 → 0.1.2

### Note
此為全域格式統一，**未對個別檔案 bump patch** —— 它是慣例採納，非功能變更。

---

## [v0.1.1] — 2026-05-16

### Changed (Review 後升級)
- **`config/risk_limits.yaml`** 結構性重寫
  - 部位上限分 ETF (15%) / 個股 (10%)
  - 取代固定 80% 曝險 → **regime-adjusted exposure** (strong_bull 80% → crisis 0%)
  - 取代二元 `require_regime` → **regime_policy 矩陣** (5 個 regime × asset_types × size multiplier)
  - **Graduated circuit breaker** 三級門檻 (1.5% 警示 / 2% 軟降 / 3% 硬停)
  - 新增 `trade.signal_max_drift_atr` (ATR-based signal expiry)
  - `approval.timeout_minutes` 10 → 30
- **`data/database.py`** schema 升級
  - `signals` 表新增 `entry_atr DOUBLE` (ATR drift 判斷必須)
  - `signals` 表新增 `expired_reason VARCHAR` (區分 timeout / atr_drift / manual_reject)
  - `approval_status` 新增 `EXPIRED_DRIFT` 狀態
- **`config/settings.py`** `telegram_approval_timeout_min` 預設 10 → 30
- **`config/strategy_config.yaml`** 移除 `require_regime` (改由 regime_policy 處理)
- **`.env.example`** TIMEOUT 預設值同步調整
- **`README.md`** 風險與紀律段落改寫

### Added
- **`storage/`** 模組（Step 2 交付）
  - `signals.py` — signal event log + ATR drift expiry
  - `orders.py` — order event log + duplicate detection
  - `positions.py` — 從 orders 計算持倉
  - `snapshots.py` — 每日 EOD 快照 + drawdown 計算
- **`market/`** 模組（Step 2 交付）
  - `trading_calendar.py` — hybrid 交易日曆（DB + fallback holidays）
- **版號規範** — 每個檔案 docstring 內含 Version + Changelog

### Fixed
- `market/calendar.py` 與 Python stdlib `calendar` 命名衝突 → 重命名為 `market/trading_calendar.py`

---

## [v0.1.0] — 2026-05-16

### Added (Step 1 — 4 hours)
- **`config/`** — Pydantic Settings + YAML loader (universe / strategy_config / risk_limits)
- **`data/`** — DuckDB schema + Parquet cache + FinMind client + 統一 fetcher
- **`utils/logger.py`** — structlog JSON 輸出
- **`scripts/init_db.py`** — 初始化資料庫 schema + 載入 stock_info

### 架構決策
- Python 3.12+ + uv
- DuckDB 為主資料庫 (single file, columnar, OLAP-friendly)
- Polars 為主 DataFrame (pandas 輔助)
- pandas-ta 為主指標庫 (v0.1 不裝 TA-Lib)
- structlog JSON logging
- Ubuntu Server x86_64 為目標環境
- systemd 為 v0.3 排程方案 (取代 macOS launchd)
- python-telegram-bot v20+ async (Step 8)
- Human-in-the-loop semi-auto 為預設模式
