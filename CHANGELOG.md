# Helios Changelog

專案層級的變更紀錄。檔案層級的細節版號在各檔案 docstring 內。

格式：[Keep a Changelog](https://keepachangelog.com/) + [Semantic Versioning](https://semver.org/)。

## [Unreleased]

### Planned for v0.1.14.2 — Paper Trading Execution (per ADR-001 minimalist scope)
- `execution/paper_broker.py` — simulated fills + cost model + T+1 settlement
- `storage/positions.py` 整合 (approved signal → positions 表)
- `scripts/daily_run.py` — cron pipeline (T-1 ingest → features → signals → exit → telegram)
- `communication/telegram/` — 訊號推送 + 人工 approval (per ADR-004)

**Explicit non-goals** (per ADR-001):
- ❌ No websocket / streaming
- ❌ No async runtime / event loop
- ❌ No distributed scheduler
- ❌ No real-time market data

### Planned for v0.2.0 — TWT49U + corporate_actions confidence engine

---

## [v0.1.14.1.2] — 2026-05-17 — Architecture crystallized + ADR records

### 觸發
Reviewer (再次) 強調: 「現在最值得保護的不是 code, 是系統哲學」.
警告 complexity creep 是量化系統最常見死因 (不是 strategy fail).
建議 explicit identity statement + explicit non-goals + ADR (Architecture Decision Records).

### Why this matters
> v0.1.14.1.1 ARCHITECTURE.md had decent layer-map but missing **identity**, **operational
> assumptions**, **known limitations**, and **explicit non-goals** for v0.1.14.2.
> Without these, future "scope creep pressure" (add websocket / add LLM / add Kelly) has
> no written counter. Identity statement is the **complexity firewall**.

### Added

- **`docs/ARCHITECTURE.md`** — substantial rewrite, now 14 sections including:
  - **§0 Identity** (NEW, leading position) — "Helios IS / IS NOT" lists
  - **§2 Why Helios is intentionally NOT HFT** (NEW) — table of complexity vectors closed off
  - **§9 Operational Assumptions** (NEW) — system "physics" (single user / daily batch / T+1 / approval)
  - **§11 Known Limitations** (NEW) — alpha character + scope + methodological limits
  - **§12 Future Roadmap** — added v0.1.14.2 explicit non-goals
  - **§14 Decision Records** — links to ADRs

- **`docs/RESEARCH_JOURNAL.md`** — renamed from JOURNAL.md (per reviewer naming),
  header tweaked to clarify role vs ARCHITECTURE / data_behavior_notes / decision_records

- **`docs/decision_records/`** new directory:
  - `README.md` — Michael Nygard ADR format + when to write a new ADR + current index
  - `ADR-001-no-hft.md` — daily-batch is non-negotiable
  - `ADR-002-polars-native-indicators.md` — no TA-Lib / pandas-ta
  - `ADR-003-portfolio-before-papertrading.md` — capital validation before execution
  - `ADR-004-human-approval-required.md` — no autopilot; exits auto, entries manual
  - `ADR-005-deterministic-regime.md` — no HMM / ML for regime
  - `ADR-006-cohesion-over-abstraction.md` — single file per layer in v0.1

### Why ADRs (and not just notes)
Each ADR closes off a **complexity vector** with a written rationale.
6 months from now, when the temptation to "add websocket" / "switch to TA-Lib" / "add a Kelly sizing
optimizer" arises, the ADR is the firewall — either the change supersedes the ADR (with explicit
new reasoning), or it doesn't belong in Helios.

### Skipped (per reviewer)
- ❌ F (budget sweep run) — premature optimization; `scripts/budget_sweep.py` stays in repo as future tool
- ❌ G (telecom removal) — n=6 too small; telecom serves as "low-momentum control group"

### Bumped
- `pyproject.toml` 0.1.14.1.1 → 0.1.14.1.2

### v0.1.14.1.2 deliverable
System identity now formally crystallized in repo. Future scope-pressure has a documented
counter. Next: v0.1.14.2 paper trading with strict scope (per ADR-001 non-goals).

---

## [v0.1.14.1.1] — 2026-05-17 — Docs + Notebook + Budget Sweep

### 觸發
v0.1.14.1 substantively STRONG PASS. User chose E+F: 暫停整理 + low-cost budget 實驗,
然後再進 v0.1.14.2 paper trading.

### Added
- **`docs/ARCHITECTURE.md`** (~300 行):
  - Mission + design tenets (5 priorities)
  - Layer map (Foundation → Data → Feature → Strategy+Backtest → Portfolio → Execution[planned])
  - Per-layer detail with decisions
  - Empirical findings snapshot
  - Future roadmap + hard rules

- **`docs/JOURNAL.md`** (~260 行):
  - Reverse chronological per-version: what / why / key insight / reviewer feedback
  - Cumulative reviewer wisdom (top 10 lessons)
  - "Lessons that surprised us" table

- **`notebooks/portfolio_analysis.ipynb`** (19 cells):
  - Load equity.csv / trades.csv / decisions.csv
  - Plots: equity curve / drawdown / exposure / trade scatter / return histogram
  - Tables: by sector / exit reason / regime / reject distribution
  - Score-decision matrix

- **`scripts/budget_sweep.py`** (~200 行):
  - F experiment — sweep 5 budget configs:
    - CURRENT (5×20%) — default
    - CONCENTRATED (3×30%) — fewer but bigger positions
    - EFFECTIVE-4 (4×22%) — match cash_buffer binding
    - WIDER (5×18%, etf=50%, sec=35%) — more diversified
    - NO-ETF-CAP (5×20%, etf=100%) — see ETF cap impact
  - Side-by-side comparison (CAGR / DD / PF / Win% / Exposure / Rejects)
  - Reject reason distribution variation per config

### Bumped
- `pyproject.toml` 0.1.14.1 → 0.1.14.1.1

### v0.1.14.1.1 deliverable
1. 跑 `scripts/budget_sweep.py --is-end 2023-12-31` 拿到 5-config comparison
2. 在 `notebooks/portfolio_analysis.ipynb` 開圖看 equity / DD / exposure
3. Decide budget profile (or stay default) → 進 v0.1.14.2 paper trading

---

## [v0.1.14.1] — 2026-05-17 — Portfolio Layer + Constrained Backtest (deployment reality check)

### 觸發
v0.1.13.3 round-trip 跑出 ✓✓ STRONG PASS (OOS net PF 2.50, mean +1.99%).
但 reviewer §40-49 警告: **trade-level metrics ≠ portfolio-level deployability**:
- 假設每個 signal 都能開倉 (unconstrained capital)
- 沒考慮 ETF + 金融 cluster 高度 correlated
- 真實 portfolio max DD 可能是 trade-level worst (-7.7%) 的 2-3 倍
- 在 paper trade 前必須跑 **constrained** backtest
→ v0.1.14.1 = "deployment reality check", 不是 paper trading 本身.

### Architecture decisions (per reviewer §43-46 + user spec)
- **Equal-weight 20% per position** (no Kelly / no covariance optimization)
- **max_positions=5** (但 cash_buffer 10% 實際上 binding 在 4 positions)
- **max_etf_exposure=40%** (ETF cluster cap, 防 over-concentration)
- **max_sector_exposure=30%** (任一 sector 不可超過)
- **cash_buffer=10%** (永遠留現金, 緊急 buffer + 心理安全)
- **Sector classification hardcoded** in v0.1 (15 symbols), 未來轉 company_metadata.industry_code
- **NO portfolio optimizer / HRP / risk parity** (reviewer §45 明文)

### Added
- **`portfolio/`** new module:
  - `__init__.py` — exports
  - `risk_budget.py` v0.1.0 — `RiskBudget` frozen dataclass
    - `DEFAULT_RISK_BUDGET` (per user spec)
    - `describe()` for logging
  - `selector.py` v0.1.0 — sector classification:
    - `SECTOR_MAP` (15 symbols hardcoded: 5 etf / 3 semi / 3 electronics / 3 financial / 1 telecom)
    - `get_sector(stock_id)` / `is_etf(stock_id)` / `all_sectors()`

- **`backtest/portfolio_simulator.py`** v0.1.0:
  - `PortfolioPosition` — Position + sizing (notional / shares / sector / is_etf_pos)
  - `EquitySnapshot` — daily (cash / positions_value / equity / n_positions / exposure_pct)
  - `SignalDecision` — per-signal (accepted / rejected + reject_reason)
  - `PortfolioMetrics` — CAGR / max DD / avg exposure / reject distribution
  - `PortfolioBacktest` class:
    - Preload close + ATR + regime + signals
    - Daily flow: update → exit check (priority order) → process signals (constraints) → record equity
    - Multi-signal selection: sort by score DESC, apply constraints
    - Costs applied: buy = notional × (1 + commission + slippage); sell = proceeds × (1 - commission - tax - slippage)
    - Force-close remaining open at end

- **`scripts/run_portfolio_backtest.py`** v0.1.0:
  - Full CLI: capital / budget knobs / costs / IS-OOS split / CSV exports
  - 3-panel output: FULL HISTORY / IN-SAMPLE / OUT-OF-SAMPLE
  - Verdict logic (user spec):
    - ✓✓ STRONG PASS: OOS PF > 1.7, max DD < 15%, avg exposure 30-90%
    - ✓ PASS: OOS PF > 1.3, max DD < 25%
    - ⚠ FAIL: insufficient sample / negative return / weak edge
  - Sector exposure breakdown + equity curve sample points

### Verified (workspace)
- Sector classification correct for all 15 universe symbols ✓
- DEFAULT_RISK_BUDGET matches user spec ✓
- 5-sector distribution: etf=5, semi=3, electronics=3, financial=3, telecom=1 ✓
- Critical implication: cash_buffer 10% binding before max_positions 5 ✓
- All imports clean, CLI loads cleanly ✓

### Bumped
- `pyproject.toml` 0.1.13.3 → 0.1.14.1

### v0.1.14.1 deliverable (per user spec exit criteria)
跑 `scripts/run_portfolio_backtest.py --is-end 2023-12-31` 拿到:
- OOS net PF (要 > 1.7 for STRONG)
- OOS max DD (要可接受)
- 平均曝險 (合理範圍)
- 拒絕訊號分布 (沒過度集中)
→ STRONG PASS → 進 v0.1.14.2 (paper trading execution)
→ PASS → 也進 v0.1.14.2, 但 risk 控制更嚴
→ FAIL → 調整 budget 或退回 v0.1.12 重審

---

## [v0.1.13.3] — 2026-05-17 — OOS round-trip + transaction costs (deployment-grade)

### 觸發
v0.1.13.2 round-trip backtest 跑出 profit factor 2.67, MFE/|MAE| 4.47, 教科書級 trend signature.
但結果是 **in-sample (5 年全部) + 零成本**. 進 paper trading 前必須回答:
  - exit logic 在 OOS 期間是否一樣有效?
  - 扣台股 ~0.6% round-trip 成本後 alpha 還在嗎?
→ v0.1.13.3 = 「deployment-grade check」前的最後一關.

### Added
- **`backtest/round_trip.py`** v0.1.0 → v0.1.1:
  - `TransactionCosts` dataclass (commission / sell_tax / slippage)
  - `total_round_trip_pct` property: 2*commission + sell_tax + 2*slippage
  - 台股 default: commission=0.1425% / sell_tax=0.3% / slippage=0
  - `compute_metrics(trades, costs)` — 接受 costs, 從 gross_return 扣除
  - `partition_by_date(trades, is_end)` — IS/OOS split by entry_date
  - `NO_COSTS` constant for clarity

- **`scripts/run_backtest.py`** v0.1.0 → v0.1.1 (完全 rewrite):
  - `--commission` / `--sell-tax` / `--slippage` / `--no-costs` 旗標
  - `--is-end YYYY-MM-DD` 啟用 IS/OOS side-by-side
  - Gross vs Net 兩欄並列 (確認 cost impact)
  - Verdict logic per user spec:
    - ✓✓ STRONG PASS: OOS net mean > 1.0% AND PF > 1.7 AND W/L > 1.5
    - ✓ PASS: OOS net mean > 0 AND PF > 1.3 AND crisis = 0 AND n >= 30
    - ⚠ FAIL: insufficient sample / regime broken / negative expectancy / weak edge

### Cost model (台股)
```
buy:  commission 0.1425%
sell: commission 0.1425% + tax 0.3% = 0.4425%
total round-trip = 0.585% (no slippage)
                 = 0.785% (with 0.1% slippage)
```

### Verified (workspace unit tests)
- TransactionCosts math: default 0.585%, +0.1% slippage = 0.785% ✓
- compute_metrics with cost: gross +1.71% → net +1.13% (correct -0.585% drag) ✓
- compute_metrics PF: 3.00 → 2.02 with cost ✓
- partition_by_date splits 7 trades into 4 IS / 3 OOS at boundary ✓

### Bumped
- `pyproject.toml` 0.1.13.2 → 0.1.13.3

### v0.1.13.3 deliverable
跑 `scripts/run_backtest.py --is-end 2023-12-31` 拿到 VERDICT (PASS/STRONG PASS/FAIL).
PASS+ → 可進 paper trading prep (v0.1.14).
FAIL  → 退回 v0.1.12 重審 strategy 條件.

---

## [v0.1.13.2] — 2026-05-17 — Exit Logic + Round-trip Backtest (第一個完整 trade lifecycle)

### 觸發
v0.1.13.1 OOS validation 跑出 ✓ REAL ALPHA (OOS 65% hit_20 > IS 60%, mean 2.93% > IS 1.65%).
Reviewer §53: 「v0.1.13.2 不是 production engine, 是第一個完整 deterministic trade lifecycle」.
→ 從 half-loop (entry only) 變 full-loop (entry + exit + round-trip metrics).

### Architecture decisions (採納 reviewer §33-52 全部建議)
- **Regime exit priority > ATR stop** (§43): 大虧通常來自 regime collapse, ATR 太慢
- **Fixed multiplier 2.0** (§36): NOT adaptive / ML / volatility-aware
- **No time stop** (§47): 會切掉最好 winners, trend-following 大忌
- **Exit metadata 必含 MFE/MAE/exit_reason** (§40): risk profile transparency
- **No Kelly / sizing / portfolio overlap** (§51): 單策略行為理解優先
- **Backtest 不寫 DB** (§53 "原型"): in-memory positions, 不過早 schema persist

### Added
- **`strategies/exit/`** new module:
  - `__init__.py` — exports
  - `base.py` v0.1.0 — `ExitRule` ABC + `Position` lifecycle dataclass + `ExitDecision`
    - `Position` 含 MFE/MAE/holding_days/is_open 等 property
    - `update_running_stats(close, date)` 跟隨 max/min close
  - `regime_exit.py` v0.1.0 — priority=1, 規則簡單: regime != 'bull' → exit
  - `trailing_stop.py` v0.1.0 — priority=2, 規則: close < max_close - 2 * atr_14

- **`backtest/`** new module:
  - `__init__.py` — exports
  - `round_trip.py` v0.1.0:
    - `RoundTripBacktest` class — daily close-based simulator
    - 預載 (close + atr + regime + signals) 後 in-memory iteration
    - Flow: update stats → check exits (priority order) → open new positions
    - Force-close 剩餘 open positions at end (exit_reason='end_of_backtest')
    - `compute_metrics()` → `RoundTripMetrics` (reviewer §50 全部欄位)
    - `trades_to_polars()` → DataFrame 給 CSV export

- **`scripts/run_backtest.py`** v0.1.0:
  - 跑全歷史 round-trip + 印 reviewer §50 metrics:
    - win_rate / mean / median / best / worst / avg_win / avg_loss
    - win_loss_ratio / profit_factor / avg_holding_days
    - avg_mfe / avg_mae + MFE/|MAE| ratio
    - exit_reason distribution (regime_exit_share vs trailing_stop_share)
    - by_entry_regime + top symbols + per-symbol win_rate
  - `--export-csv` 輸出 trades 表

### Verified (workspace unit tests)
- `Position.update_running_stats` 正確 tracking max/min close
- MFE/MAE 計算精確 (entry=600, max=620 → MFE=+3.33%, min=590 → MAE=-1.67%)
- `TrailingStop` triggers correctly at 589 < 590 (max 620 - 2*15 ATR)
- `RegimeExit` triggers on crisis, NOT on bull
- Priority order: regime_exit (p=1) before trailing_stop (p=2)
- Position lifecycle (entry → update → exit) 完整正確

### Bumped
- `pyproject.toml` 0.1.13.1 → 0.1.13.2

### v0.1.13.2 deliverable
Reviewer §54: 「entry + exit + round-trip 跑通, Helios 真正從 research infra
變成可部署交易系統原型」.
跑 `scripts/run_backtest.py` 拿到 round-trip metrics → ✓ 完成.

---

## [v0.1.13.1] — 2026-05-17 — Out-of-Sample validation (alpha 不是 AI bull noise 的 sanity check)

### 觸發
v0.1.12 audit 跑出 217 signals 5 年, hit rate 51→58→63% 隨 horizon 上升, 右偏分布.
Reviewer 警告:
  - 「2023-2025 是 AI mega trend, breakout strategy 天然吃這波」
  - 「最大風險不是沒 exit, 而是太早相信 alpha」
  - 「需要小型 OOS sanity, 不要 ML train/test 那種複雜」
→ 切簡單 IS/OOS, 不調參, 純驗證 alpha 跨期穩定性.

### Added
- **`scripts/oos_validation.py`** v0.1.0 (新檔):
  - Split: IS ≤ 2023-12-31 < OOS (預設, 可 --is-end override)
  - 跑 strategy 在 IS / OOS 各跑一遍, **不調 parameters**
  - Side-by-side metric table:
    - Period years / trading days / signal count / rate per year
    - Regime % (bull-only check) / Crisis count (gate check)
    - 5/10/20-day hit rate / median / mean / best / worst
  - Verdict logic (reviewer §32-33):
    - ✓ REAL ALPHA       — IS > 55% AND OOS > 55% hit_20
    - ○ MARGINAL         — IS > 55% AND OOS 50-55%
    - ⚠ OVERFIT WARNING  — IS > 60% AND OOS < 50%
    - ⚠ Crisis 在 OOS 漏訊號

### Architecture decision
- 用簡單 date split, **不做** ML-style cross-validation / walk-forward / Monte Carlo
  (reviewer §30 「不要 ML train/test 那種複雜」)
- 不寫專門的 metric module — 跟 signal_audit.py 有部分重複, 但 v0.1 cohesion > DRY
- Verdict 用 threshold 不用 statistical test (n=200+ 級 sample, threshold 已夠 informative)

### Verified (workspace)
- Import + 結構 OK; full run 要在 nexus 跑 (要 5 年 daily_features 資料)

### Bumped
- `pyproject.toml` 0.1.12 → 0.1.13.1

### 決策樹 (跑完 OOS 後)
  ✓ REAL ALPHA       → 繼續 v0.1.13.2 (exit logic)
  ○ MARGINAL         → 也繼續, 但要 v0.1.13.3 後再決定要不要 paper trade
  ⚠ OVERFIT WARNING  → 退回 v0.1.12, 重新審視 (可能放寬 condition 但要小心)
  ⚠ Crisis 漏訊號     → 退回 v0.1.11, 收緊 crisis_vol_threshold

---

## [v0.1.12] — 2026-05-17 — Strategy Framework + TrendBreakout v1 (第一個 deterministic decision loop)

### 觸發
v0.1.11 完成 feature layer 全部 9 indicators + 4-state regime.
Reviewer: "Helios 不是 feature factory, 是可執行的市場決策系統"
→ 不再 feature expansion, 直接進 feature → signal 的 decision loop.

### Architecture decisions (採納 reviewer 建議)
- **Conservative breakout 條件** (台股 fake-breakout 問題): close > donchian_high.shift(1), 不是 touch
- **Slope filter** (避免「在 SMA 上方但 trend 已死」): sma_50 > sma_50.shift(5)
- **Volume confirmation** (reviewer §35 台股 breakout 沒量很危險): rel_volume_20 >= 1.5
- **Regime gate** (Helios 真正 edge — 不在爛市場交易): regime == 'bull'
- **全 AND 不是 OR**: 寧少而精, 不要 over-fire (v0.1 不該 chase signal count)
- **Replay mode 預設 dry-run**: 避免 backtest 污染 production signals 表

### Added
- **`strategies/__init__.py`** v0.1.0 (新 module)
- **`strategies/base.py`** v0.1.0:
  - `Strategy` ABC — 子類必須實作 `generate_signals(as_of, symbols)`
  - `Signal` dataclass — 7 必填欄位 + reason list + metadata dict
  - Score 範圍驗證 (0.0 ~ 1.0), side 限定 buy/sell/exit
- **`strategies/trend_breakout.py`** v0.1.0:
  - Single SQL with LAG window functions (donchian.shift(1) + sma_50.shift(5))
  - 6 個 filter 全 AND 條件
  - Score 公式 0.5 baseline + 4 個 bonus (rel_vol 2x, 3x, RSI sweet spot, ROC > 5%)
  - Decision context: 6-7 行 human-readable reason + 17 個 structured metadata key
- **`scripts/generate_signals.py`** v0.1.0:
  - 3 modes: LIVE (today, write) / REPLAY-COMMIT (--date --commit) / DRY-RUN (--date 預設)
  - 美化的 signal 印出 (含 reason 條列)
- **`scripts/signal_audit.py`** v0.1.0:
  - Full historical sweep + 5 reviewer questions:
    1. Signals 太多嗎? (rate per year)
    2. Bull market 才觸發嗎? (regime distribution)
    3. Crisis 被過濾嗎? (crisis count vs trading days)
    4. Breakout 後延續嗎? (forward 5/10/20-day returns + hit rate)
    5. ATR spike 後續? (% 訊號後 20 日 ATR > 1.5x entry)
  - Verdict 自動評等 (✓/○/⚠)

### Verified
- Mock test on synthetic data: strategy fires correctly with realistic noise
  - TEST symbol breakout: BUY @ 319.06, score=0.80, all 6 conditions verified
  - All explainability fields populated (reason list + metadata dict)
- Storage layer 既有的 `save_signal()` 介面 100% compatible (沒改 schema, reason/regime/metadata 欄位已存在)

### Bumped
- `pyproject.toml` 0.1.11 → 0.1.12

### Step 4 (v0.1.12) 完成定義
跑 `scripts/signal_audit.py` 拿到 5 個問題的明確 verdict → ✓ 完成
這 loop 是 Helios 從 "infra project" 變成 "trading system" 的關鍵分界線.

---

## [v0.1.11] — 2026-05-17 — Technical Indicators + Market Regime (Step 3)

### 觸發
v0.1.10.2 拿到 100% adjustment absorption, daily_price_adj 進入 production-clean state.
Reviewer 確認 §12 觀察是真實市場行為 (mechanical adj 跟 market reaction 區分清楚).
→ Step 2.5 正式完成, Step 3 開工: indicators + regime.

### Architecture decisions (採納 reviewer 建議)
- **Polars-native 手刻** (vs pandas-ta / TA-Lib): 透明、無新 dep、跟現有 stack 完美整合
- **單一 technical.py** (cohesion > abstraction in v0.1, 未來真複雜再拆)
- **Deterministic regime** (vs HMM): 先 market intuition encoding, 不上 latent state
- **LazyFrame-compatible helpers + materialized table**: 靈活查詢 + 快速 lookup

### Added
- **`features/technical.py`** v0.1.0 (新檔, 9 個 indicators):
  - Trend:      `add_sma(20/50/200)`, `add_ema(20)`
  - Momentum:   `add_rsi(14)` (Wilder smoothed), `add_roc(20)`
  - Volatility: `add_atr(14)` (Wilder smoothed, 用 adj OHLC 避免 dividend 污染)
  - Breakout:   `add_donchian(20)` (high + low)
  - Volume:     `add_volume_indicators(20)` (volume_ma + rel_volume)
  - Single source of truth: `compute_indicators(df)`

- **`features/regime.py`** v0.1.0 (新檔):
  - 4-state classification: bull / bear / crisis / neutral
  - 規則:
    - crisis:  vol_20 > 0.020 (TAIEX 20-day return stdev > 2%)
    - bull:    close > sma_200 AND vol_20 <= 0.020
    - bear:    close < sma_200 AND vol_20 <= 0.020
    - neutral: 過渡 (跨 SMA200 期間)
  - 不上 HMM (per reviewer 建議), v0.2 才考慮 expanding window quantile

- **`data/database.py`** v0.1.4 → v0.1.5:
  - 新增 `daily_features` 表 (11 個 indicator columns + PK + computed_at)
  - 新增 `market_regime` 表 (taiex_close, sma_200, vol_20, regime + computed_at)

- **`scripts/compute_features.py`** (新檔):
  - Phase 1: 對每個 symbol 從 daily_price_adj 算 indicators
  - Phase 2: 從 daily_price TAIEX 算 regime
  - `--indicators-only` / `--regime-only` 旗標

- **`scripts/feature_inspect.py`** (新檔, reviewer 的 Step 3 exit criteria):
  - 自動回答 5 個 strategy-readiness 問題:
    1. 現在是不是 bull regime?
    2. 個股是否高於 SMA200?
    3. 是否 volume breakout (rel_volume > 1.5x)?
    4. ATR 是否異常擴張 (vs 60d median > 1.5x)?
    5. 個股是否 Donchian-20 breakout/breakdown?

### 演算法驗證 (workspace mock tests, 全部 pass)
- SMA: trivial ✓
- RSI on alternating ±1 → 48.15 (≈ 50 expected) ✓
- RSI on monotonic uptrend → 100.00 ✓
- ATR Wilder on known TR series [4, 5, 4, 5, 5] → [4.000, 4.333, 4.222, 4.481, 4.654] (跟手算精確一致) ✓
- Regime on uptrending sine → 51 bull / 199 neutral days ✓
- compute_indicators 11 columns 全 non-null at latest row ✓

### Bumped
- `pyproject.toml` 0.1.10.2 → 0.1.11

### Step 3 exit criteria
跑 `scripts/feature_inspect.py` 能回答 reviewer 的 5 個問題 → ✓ 完成

---

## [v0.1.10.2] — 2026-05-16 — Splits: 改用 raw price 自動偵測 (Taiwan-aware)

### 觸發
v0.1.10.1 跑 `ingest_splits.py` (yfinance source) 拿到 result:
- 0050 **沒抓到** 2025-06-18 真實 1:4 split (yfinance 對台股 ETF split 不全)
- 113 個其他 events 全部是 **stock dividend 1.10-1.50 ratio** (台股無償配股)
- 跟 FinMind `dividend_result` 重疊 → 雙重 adjustment
- 2881 從 0 raw abnormal 變成 1 adj abnormal (+11.25%) ← 證據

→ **yfinance.splits 對台股「既誤報又漏報」**，不能用。

### Changed
- **`scripts/ingest_splits.py`** v0.1.0 → v0.2.0 完全改寫
  - 偵測邏輯：`close[T] / close[T-1] < 0.55` → 識別為真實 split
  - Taiwan-aware:
    - 台股 ±10% 漲跌停 → -10% 永遠不會觸發 0.55 閾值
    - 無償配股 (stock dividend) ratio ~0.85-0.95 → 不會誤抓 (FinMind 已涵蓋)
    - 真實 split 像 0050 1:4 = 0.252, 1:5 = 0.20 → 100% 抓到
  - source 改為 `auto_detected_price_drop`
  - 自動清掉 v0.1.10.1 的 yfinance 殘留 (DELETE WHERE kind='split')
  - Sanity warning: 若偵測到的 split 日同時是 dividend 日，印異常 warning

### 驗證 (workspace mock test)
3 合成案例:
- 0050 1:4 split (ratio=0.2522) → ✓ 偵測
- 2454 純現金股利 (ratio=0.91)  → ✓ 不誤判
- 2881 無償配股 (ratio=0.91)    → ✓ 不誤判

### Bumped
- `pyproject.toml` 0.1.10.1 → 0.1.10.2

---

## [v0.1.10.1] — 2026-05-16 — Splits ingestion (via yfinance) + validation 改進 [SUPERSEDED]

### 觸發
- 0050 在 2025-06-18 split day 顯示 raw -74.78% / adj -74.78% (factor 仍 0.97918)

根因確認：**FinMind `TaiwanStockDividendResult` 不包含 stock splits**。
影響：所有有 split 的 ETF/股票歷史 adjustment 都會殘留該日跳空。

### Added
- **`scripts/ingest_splits.py`** v0.1.0 (新檔)
  - 使用 `yfinance.Ticker(sid).splits` 抓 split history
  - 1:N split → `adjustment_factor = 1/N`
  - 寫入 corporate_actions, kind='split', source='yfinance_splits'
  - 跟 dividend 共表，可組合 cum_factor

### Changed
- **`scripts/validate_adjustments.py`** v0.1.0 → v0.1.1 (採納 reviewer 建議)
  - Per-type threshold:
    - stock = 0.105 (±10% 漲跌停 + buffer)
    - ETF   = 0.20  (ETF 無漲跌停限制)
  - 顯示 max |pct| residual per symbol (count=0 不等於完美)
  - 全市場 max_adj 摘要

### Bumped
- `pyproject.toml` 0.1.10 → 0.1.10.1

---

## [v0.1.10] — 2026-05-16 — Dividend Adjustment (自家還原權息層)

### 觸發
v0.1.9 累積 140 個歷史 dividend events 進 corporate_actions。
features layer 必須吸收這些事件，輸出 indicator-ready 的 adjusted prices。
這是 Step 3 (technical indicators) 的前置條件 — 用 raw 算 RSI/MACD 會被除息日污染。

### Added
- **`features/` 新 module**:
  - `__init__.py` — module docstring
  - `dividend_adjustment.py` v0.1.0:
    - `compute_adjusted(df_raw, df_events) -> AdjustmentResult` — 純函數，可獨立 unit test
    - `build_for_symbol(stock_id)` — DB 讀取 + compute
    - `write_adjusted_to_db(stock_id, result)` — 寫 daily_price_adj + adjustment_state
    - `get_freshness_status()` — 比對 raw / event / state 找出 stale symbols

- **演算法**: canonical backward adjustment
  - `cum_factor[T] = ∏ event_factor[E]` for all events `E.date > T`
  - 除權息日當天的 raw close 已是除息後價，不再乘自己 factor
  - Polars 實作: sort DESC + `shift(1, fill_value=1.0)` + `cum_prod()`

- **`data/database.py`** v0.1.3 → v0.1.4:
  - 新增 `daily_price_adj` 表 (stock_id, date, adj_OHLC, raw_close, cum_factor, volume)
  - 新增 `adjustment_state` 表 (stock_id, last_built_at, last_event_date_used, ...)

- **`scripts/build_adjusted_prices.py`** v0.1.0 (新檔):
  - Freshness check + incremental rebuild
  - `--force` 全量重建; `--symbols` 限定範圍

- **`scripts/validate_adjustments.py`** v0.1.0 (新檔):
  - 比對 raw vs adjusted 的 abnormal returns (|pct| > 10.5%)
  - 預期 absorption rate ≥ 80% (理想 100%)
  - 含 0050 split (2025-06-18) 的 golden case 顯示

### 演算法驗證 (workspace)
用 2454 真實 events (3 個 dividend, factor 0.90953 / 0.90317 / 0.97419) 合成 8 個 raw price 點:
- ✓ 全部 8 個 cum_factor 跟手算結果精確一致 (誤差 < 1e-5)
- ✓ 跨除息日 (2022-06-22 → 2022-06-23) 的 adj_close pct 變化 = **-0.000%**
- ✓ 對應 raw pct 變化 = -9.05% (被完美吸收)

### Bumped
- `pyproject.toml` 0.1.9 → 0.1.10

### Volume 不做調整 (v0.1.10 設計決定)
- Cash dividend 不影響股數 → 不需 volume adjustment
- Split 才需要，但 v0.1 universe 罕見 (僅 0050 一次)
- 若未來加 split-heavy 股，再加 volume / cum_factor 調整

---

## [v0.1.9] — 2026-05-16 — TWSE Truth + Corporate Actions

### 觸發
1. v0.1.8 cross-source audit 確認三家 raw OHLC 完全對齊 → 架構通過
2. 第一次 audit run 出現 1 個 silent missing case → 需要 retry + logging hotfix
3. v0.1.10 dividend_adjustment 需要「除權息事件原料表」 → 必須先有 ingestion

### Added
- **`data/sources/twse_client.py`** v0.1.0 → v0.1.1
  - `company_info()` → `/opendata/t187ap03_L` (~1000+ 上市公司基本資訊)
  - `dividend_forecast()` → `/exchangeReport/TWT48U` (除權息預告)
  - `_parse_western_compact` helper (西元年 YYYYMMDD，跟 ROC compact 區別)
  - `_get_json` 加 **tenacity retry** (3 次 exp backoff 1-8s)
  - `stock_month` 當 stat ≠ "OK" 時 log warning (留 trace)
- **`data/sources/finmind_client.py`** v0.1.3 → v0.1.4
  - `dividend_result()` → `TaiwanStockDividendResult` (免費版可用)
  - 自動計算 `adjustment_factor = after_price / before_price`
- **`data/database.py`** v0.1.2 → v0.1.3
  - 新增 `company_metadata` 表 (TWSE t187ap03_L 來源)
  - 新增 `corporate_actions` 表 (歷史 + 預告共表，PRIMARY KEY (date, stock_id, kind))
- **`scripts/sync_company_info.py`** (新檔)
  - TWSE t187ap03_L → company_metadata (全量重寫)
- **`scripts/ingest_dividends.py`** (新檔)
  - Phase 1: FinMind TaiwanStockDividendResult → corporate_actions (confirmed=true)
  - Phase 2: TWSE TWT48U → corporate_actions (confirmed=false, forecast)
  - 支援 `--historical-only` / `--forecast-only` / `--symbols`

### Changed
- **`scripts/cross_source_audit.py`** v0.1.0 → v0.1.1
  - `get_twse_row` 失敗的三種情況 (TwseError / 空 DF / 該日不在月份) 各自 log warning
  - 解決上次 1 個 missing case 完全 silent 的問題
- **`scripts/validate_install.py`** v0.1.1 → v0.1.2
  - `check_twse_api()`: smoke test company_info (確認 1000+ 公司、2330 listing_date)
  - `check_finmind_dividends()`: smoke test dividend_result (確認 2330 過去 3 年有事件、factor 非 null)

### Bumped
- `pyproject.toml` 0.1.8 → 0.1.9

### Deferred
- TWSE `suspendListing` (3 個 alt path 全 302，無公開 endpoint) → v0.5+ 接 trading 層再挖
- `features/dividend_adjustment.py` → v0.1.10 (corporate_actions 原料先建好)

---

## [v0.1.8] — 2026-05-16 — Multi-source Layer A (TWSE primary for daily ops)

### 觸發
v0.1.7 部署過程中發現：
1. FinMind `TaiwanStockPriceAdj` 是 Sponsor 付費限定（免費版 register tier 拒絕）
2. TWSE 4 個 endpoint 親自驗證後發現比預想能幹（STOCK_DAY_ALL 一次全市場、MI_INDEX 含 30+ 產業類股）
3. 外部 quant review 確認「TWSE = validation layer，不是 FinMind 備胎」

→ 架構重定位：**FinMind 從 primary 降級為 historical bulk + 國際 reference；TWSE 升為 daily ops primary**。

### Added
- **`data/sources/twse_client.py`** v0.1.0 (新檔)
  - 4 個 endpoint：`daily_all` (STOCK_DAY_ALL), `stock_month` (STOCK_DAY), `indices_today` (MI_INDEX), `taiex_recent` (MI_5MINS_HIST)
  - `stock_range` helper：跨多月 historical (慢，只用於 spot-check)
  - Parser 工具：`parse_roc_compact` (民國年連月日), `parse_roc_slashed` (民國年/月/日), `parse_twse_num` (千分號 + null + 帶符號)
  - 自律 rate limit (預設 1 秒間隔)
  - `stock_month` 保留 `twse_note` 欄位（拆分日標記 `**` 是 v0.1.9 corporate_actions 表的輸入）

- **`data/sources/yfinance_client.py`** v0.1.0 (新檔)
  - `daily_price()` / `taiex()` 包 yfinance，輸出 Polars
  - 同時回傳 raw `close` 和 `adj_close` — 後者是 v0.1.9 adjustment layer 的「第三方對照」
  - Helios stock_id ↔ yfinance ticker 自動轉換 (`2330` ↔ `2330.TW`, `TAIEX` ↔ `^TWII`)

- **`scripts/cross_source_audit.py`** v0.1.0 (新檔)
  - 隨機抽樣 N 個 (symbol, date)，三家對比 OHLC
  - Divergence threshold 0.1%
  - 輸出 `cross_source_audit_YYYY-MM-DD.{json,md}`
  - `--skip-yfinance` 選項避免 Yahoo 反爬擋

- **`data/database.py`** v0.1.1 → v0.1.2
  - 新增 `sector_index_daily` 表 (date, index_name, close, change_pct)
  - 來源是 TWSE MI_INDEX
  - 給 sector rotation feature / regime detection 用

### Changed
- **`pyproject.toml`** 0.1.7 → 0.1.8
  - 新增 dep: `yfinance>=0.2.40`
- **`docs/data_sources_catalog.md`** → 重大更新
  - FinMind 角色：primary → historical bulk + 國際 reference
  - TWSE 角色：validation → daily ops primary
  - 新增「FinMind 免費版 vs 付費版」對照表

---

## [v0.1.7] — 2026-05-16 — Data Layer Hardening

### Hotfix (later same day)
- **`data/sources/finmind_client.py`** v0.1.2 → v0.1.3
  - Revert `TaiwanStockPriceAdj` → `TaiwanStockPrice`（Sponsor 限定，免費版 400）
  - adjustment ownership 移到 v0.1.9 features/dividend_adjustment.py
- **`config/universe.yaml`** 加入 10 個權值股（2330, 2317, 2454, 2412, 2308, 2882, 2891, 2881, 2303, 3711）— 永久寫入，下次 tar 解壓不會掉

### 觸發
v0.1.6 第一次跑 16-symbol × 5 年資料後，profile 結果暴露 4 個資料層問題 (詳見 `docs/data_behavior_notes.md::2026-05-16`)：
1. 全市場「missing 80 days」是 trading_calendar 過度樂觀造成的偽陽性
2. 0050 在 2025-06-18 的 1拆4 拆分造成 -74.78% 的「假跳空」
3. 2317 在 2025-07-30 出現 close=0 的 FinMind 資料汙染，造成 +inf% 漲幅
4. 6-7 月台股除權息季造成跨股大量 10%+ 跳空

### Changed
- **`data/sources/finmind_client.py`** v0.1.1 → v0.1.2
  - `daily_price()` 改用 `TaiwanStockPriceAdj` (還原權息價)，解決 dividend / split 跳空
  - TAIEX 維持 `TaiwanStockPrice` (指數本身沒 split/dividend)
- **`data/fetcher.py`** v0.1.1 → v0.1.2
  - `daily_price()` 後串接 `data.sanity.validate_ohlc` 丟壞列
  - 壞列數 + 原因併入 `FetchResult.quality_issues` 並 log warning
- **`scripts/data_quality_report.py`** v0.1.0 → v0.1.1
  - `_count_expected_trading_days()` 改用 TAIEX baseline (DB 內的實際交易日數)
  - `abnormal_returns` 計算先 `filter(close > 0)` 避免零 close 造成 +inf%
  - `fetch_arrow_table()` → `to_arrow_table()` (Polars deprecation 修)

- **`data/cache.py`** v0.1.1 → v0.1.2
  - `CACHE_SCHEMA_VERSION` 1 → 2，舊 raw price cache 自動失效，
    避免拿到舊 cache 而再次寫入 raw price (那就白做 adjustment 切換)

### Added
- **`data/sanity.py`** v0.1.0 (新檔)
  - `validate_ohlc(df)` 回傳 `SanityResult(clean, dropped_count, dropped_reasons)`
  - 規則: close/open/high/low ≤ 0 / high < low / 全 OHLC null
  - 留 audit trail 不修改價格 (不做 imputation)

### Migration (用戶必做)
舊資料是 raw `TaiwanStockPrice`，新版改抓 `TaiwanStockPriceAdj`。**必須 `--full` 重抓覆蓋**：
```bash
uv run python scripts/download_daily.py --full
uv run python scripts/data_quality_report.py
```
預期變化：
- `missing_days` 從 ~80 降到接近 0 (TAIEX baseline)
- `abnormal_returns` count 大幅下降 (還原權息已吸收除權息跳空)
- 0050 跨 2025-06-18 拆分日將不再有 -74.78% (還原價會在所有歷史日同比例下調)
- 2317 的 close=0 那列會被 sanity filter 丟掉並寫進 quality_issues

### Bumped
- `pyproject.toml` 0.1.6 → 0.1.7

---

## [v0.1.6] — 2026-05-16 — Real Data Ingestion + Systematic Profiling

### Added (Step 2.5: 採納 reviewer 建議的「資料行為理解」交付)
- **`scripts/download_daily.py`** — 機械抓取日 K 到 DuckDB
  - 從 `config/universe.yaml` 讀 symbols + 強制加 TAIEX
  - 增量更新 (依 `ingest_watermark`)；`--full` 強制重抓
  - DELETE+INSERT 模式避免 PRIMARY KEY 衝突
  - 事件記錄到 `data_quality_log`，狀態軌跡完整
- **`scripts/data_quality_report.py`** — 系統化資料 profiling (核心交付)
  - per-symbol：rows / 缺日 / 重複 / 零成交 / 最大連續 gap / 異常漲跌幅 / 漲跌停 / 流動性 tier
  - cross-symbol：TAIEX alignment / supplementary table 覆蓋率
  - 輸出 JSON (機讀) + Markdown (人讀)，含「Findings hints」自動推斷異常
- **`notebooks/01_data_behavior.ipynb`** — 視覺探索 stub
  - 含 TAIEX 200MA regime、報酬率分布、探索建議清單
- **`docs/data_behavior_notes.md`** — 累積學習檔
  - 用結構化格式累積觀察 → 成為 Step 3 (indicators) 設計需求依據

### Changed
- `scripts/validate_install.py` v0.1.0 → v0.1.1
  - 修 lifecycle bug：`fetcher.daily_price` 移入 `with` 區塊內 (原本 fetcher 已關閉)
  - 版號改為動態讀 `pyproject.toml`，避免之後忘了更新

### Bumped
- `pyproject.toml` 0.1.5 → 0.1.6
- `scripts/validate_install.py` v0.1.0 → v0.1.1 (lifecycle bug hotfix)

### 工作流程
跑通 v0.1.6 後的標準動作：
```bash
uv run python scripts/download_daily.py --full   # 抓 5 年 (~30 symbols)
uv run python scripts/data_quality_report.py      # 看數字摘要
# 開 notebooks/01_data_behavior.ipynb 看視覺
# 把發現的 patterns 整理到 docs/data_behavior_notes.md
```

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
