# data/database.py
"""DuckDB 連線管理 + schema 載入。

Schema 設計原則：
- 價量資料：複合主鍵 (stock_id, date)，INSERT OR REPLACE 增量更新
- Event log (signals/orders): append-only，全程留下審計軌跡
- snapshots: 每日狀態快照，配合 event log 可重建任意時點

Version: v0.1.5 (2026-05-17)
Changelog:
  v0.1.5 (2026-05-17): 新增 daily_features 表 + market_regime 表 (v0.1.11 indicators + regime)
  v0.1.4 (2026-05-16): 新增 daily_price_adj 表 + adjustment_state 表 (v0.1.10 還原權息)
  v0.1.3 (2026-05-16): 新增 company_metadata 表 (TWSE t187ap03_L 來源);
                       新增 corporate_actions 表 (FinMind dividend_result + TWSE TWT48U)
  v0.1.2 (2026-05-16): 新增 sector_index_daily 表 (TWSE MI_INDEX 來源)
  v0.1.1 (2026-05-16): signals 表新增 entry_atr、expired_reason 欄位；EXPIRED_DRIFT 狀態
  v0.1.0 (2026-05-16): Initial implementation
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import duckdb

from config.settings import get_settings
from utils.logger import get_logger

logger = get_logger(__name__)


SCHEMA_SQL = """
-- ═══════════════════════════════════════════════════════════
-- Reference & Price Data
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS stock_info (
    stock_id    VARCHAR PRIMARY KEY,
    stock_name  VARCHAR NOT NULL,
    industry    VARCHAR,
    market      VARCHAR,                 -- TWSE / OTC / EMERGING
    listed_date DATE,
    is_etf      BOOLEAN DEFAULT FALSE,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS daily_price (
    stock_id     VARCHAR NOT NULL,
    date         DATE NOT NULL,
    open         DOUBLE,
    high         DOUBLE,
    low          DOUBLE,
    close        DOUBLE,
    volume       BIGINT,                 -- 張數
    turnover     DOUBLE,                 -- 成交金額
    transactions BIGINT,                 -- 筆數
    spread       DOUBLE,                 -- 漲跌
    PRIMARY KEY (stock_id, date)
);
CREATE INDEX IF NOT EXISTS idx_daily_price_date ON daily_price(date);

CREATE TABLE IF NOT EXISTS institutional_investors (
    stock_id     VARCHAR NOT NULL,
    date         DATE NOT NULL,
    foreign_buy  BIGINT,
    foreign_sell BIGINT,
    trust_buy    BIGINT,
    trust_sell   BIGINT,
    dealer_buy   BIGINT,
    dealer_sell  BIGINT,
    PRIMARY KEY (stock_id, date)
);

CREATE TABLE IF NOT EXISTS monthly_revenue (
    stock_id      VARCHAR NOT NULL,
    revenue_year  INTEGER NOT NULL,
    revenue_month INTEGER NOT NULL,
    date          DATE,                  -- 公告日
    revenue       BIGINT,
    revenue_yoy   DOUBLE,
    PRIMARY KEY (stock_id, revenue_year, revenue_month)
);

-- ═══════════════════════════════════════════════════════════
-- Event Log Tables (Append-Only, Helios ADR-001/008/010)
-- ═══════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS signals (
    signal_id        VARCHAR PRIMARY KEY,
    timestamp        TIMESTAMP NOT NULL,
    symbol           VARCHAR NOT NULL,
    strategy         VARCHAR NOT NULL,
    signal_type      VARCHAR NOT NULL,   -- buy / sell / exit
    score            DOUBLE,
    price            DOUBLE,             -- 訊號當下參考價 (entry reference)
    entry_atr        DOUBLE,             -- 訊號當下 ATR (ATR-drift expiry 用)
    stop_loss        DOUBLE,
    take_profit      DOUBLE,
    reason           JSON,               -- Explainable: ["20D breakout", "ADX>32"]
    regime           VARCHAR,            -- strong_bull / weak_bull / neutral / bear / crisis
    approval_status  VARCHAR NOT NULL,   -- PENDING / APPROVED / REJECTED / TIMEOUT / EXPIRED_DRIFT / AUTO_APPROVED
    approved_at      TIMESTAMP,
    approved_by      VARCHAR,            -- telegram / cli / auto
    timeout_at       TIMESTAMP,
    expired_reason   VARCHAR,            -- timeout / atr_drift / manual_reject
    metadata         JSON
);
CREATE INDEX IF NOT EXISTS idx_signals_ts     ON signals(timestamp);
CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(approval_status);
CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol);

CREATE TABLE IF NOT EXISTS orders (
    order_id    VARCHAR PRIMARY KEY,
    signal_id   VARCHAR,                -- 關聯訊號
    timestamp   TIMESTAMP NOT NULL,
    symbol      VARCHAR NOT NULL,
    side        VARCHAR NOT NULL,       -- buy / sell
    order_type  VARCHAR NOT NULL,       -- market / limit
    quantity    INTEGER NOT NULL,
    price       DOUBLE,
    status      VARCHAR NOT NULL,       -- submitted / filled / partial / rejected / cancelled
    filled_qty  INTEGER DEFAULT 0,
    avg_price   DOUBLE,
    commission  DOUBLE DEFAULT 0,
    tax         DOUBLE DEFAULT 0,
    broker      VARCHAR,                -- paper / shioaji
    metadata    JSON
);
CREATE INDEX IF NOT EXISTS idx_orders_ts     ON orders(timestamp);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);

CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_date     DATE PRIMARY KEY,
    portfolio_value   DOUBLE NOT NULL,
    cash              DOUBLE NOT NULL,
    total_exposure    DOUBLE NOT NULL,
    positions         JSON,
    regime            VARCHAR,
    drawdown          DOUBLE,
    pending_approvals INTEGER DEFAULT 0,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ═══════════════════════════════════════════════════════════
-- Operational Tables
-- ═══════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS ingest_watermark (
    stock_id   VARCHAR,
    dataset    VARCHAR,                 -- daily_price / institutional / monthly_revenue
    last_date  DATE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (stock_id, dataset)
);

CREATE TABLE IF NOT EXISTS data_quality_log (
    run_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source        VARCHAR,
    dataset       VARCHAR,
    stock_id      VARCHAR,
    rows_fetched  INTEGER,
    status        VARCHAR,              -- ok / empty / error / warn
    error_msg     VARCHAR
);

-- 每日 universe 快照 (point-in-time，避免 survivorship bias)
CREATE TABLE IF NOT EXISTS universe_snapshot (
    snapshot_date    DATE,
    universe_name    VARCHAR,
    stock_id         VARCHAR,
    avg_turnover_20d DOUBLE,
    avg_volume_20d   BIGINT,
    days_traded_60d  INTEGER,
    passed           BOOLEAN,
    reject_reason    VARCHAR,
    PRIMARY KEY (snapshot_date, universe_name, stock_id)
);

-- v0.1.8: 產業類股 / 大盤主要指數 每日收盤 (來源 TWSE MI_INDEX)
-- 用途：sector rotation feature、regime detection、產業相對強弱
CREATE TABLE IF NOT EXISTS sector_index_daily (
    date         DATE,
    index_name   VARCHAR,  -- 例: "半導體類指數", "電子工業類指數", "金融保險類指數"
    close        DOUBLE,
    change_pct   DOUBLE,   -- 漲跌百分比 (含正負號)
    source       VARCHAR DEFAULT 'TWSE_MI_INDEX',
    PRIMARY KEY (date, index_name)
);
CREATE INDEX IF NOT EXISTS idx_sector_index_date ON sector_index_daily(date);

-- v0.1.9: 上市公司 metadata (來源 TWSE t187ap03_L)
-- 用途：universe management、產業分類、上市日篩選
CREATE TABLE IF NOT EXISTS company_metadata (
    stock_id          VARCHAR PRIMARY KEY,
    company_name      VARCHAR,        -- 全名 (e.g. "台灣積體電路製造股份有限公司")
    short_name        VARCHAR,        -- 簡稱 (e.g. "台積電")
    industry_code     VARCHAR,        -- TWSE 產業代碼 (e.g. "24"=半導體)
    listing_date      DATE,           -- 上市日
    paid_in_capital   BIGINT,         -- 實收資本額 (NTD)
    issued_shares     BIGINT,         -- 已發行普通股數
    last_synced_at    TIMESTAMP,
    source            VARCHAR DEFAULT 'TWSE_t187ap03_L'
);

-- v0.1.9: 公司行動 (除權息、拆分、現金增資...)
-- 用途：features/dividend_adjustment.py 的原料表
-- confirmed=true: 歷史已發生 (源自 FinMind dividend_result)
-- confirmed=false: 未來預告 (源自 TWSE TWT48U)
-- PRIMARY KEY (date, stock_id, kind) 允許同一檔同一天有「權」+「息」兩筆
CREATE TABLE IF NOT EXISTS corporate_actions (
    date              DATE,           -- 除權息交易日
    stock_id          VARCHAR,
    kind              VARCHAR,        -- "權" / "息" / "權息" / "split" / "cash_increase"
    before_price      DOUBLE,         -- 除權息前收盤 (confirmed only)
    after_price       DOUBLE,         -- 除權息參考價 (confirmed only)
    adjustment_factor DOUBLE,         -- after / before (用於 backwards adjustment)
    cash_dividend     DOUBLE,         -- 現金股利 (元/股)
    stock_div_ratio   DOUBLE,         -- 無償配股率 (配 X 股)
    confirmed         BOOLEAN,        -- true=已發生, false=預告
    source            VARCHAR,        -- 'finmind_dividend_result' / 'twse_twt48u' / 'twse_stock_day_note'
    notes             VARCHAR,        -- 自由欄位 (e.g. "1拆4 split")
    ingested_at       TIMESTAMP,
    PRIMARY KEY (date, stock_id, kind)
);
CREATE INDEX IF NOT EXISTS idx_corp_actions_stock ON corporate_actions(stock_id, date);

-- v0.1.10: 還原權息後的日 K 表
-- 來源：features/dividend_adjustment.py 用 daily_price (raw) + corporate_actions 計算
-- 演算法：backward adjustment (cum_factor = product of all FUTURE event factors)
--   - adj_close[T] = raw_close[T] * cum_factor[T]
--   - cum_factor[T] = ∏ event_factor[E] for E.date > T
--   - 除權息日當天的 raw close 已經是「除息後」價，所以不再乘
--   - volume 維持 raw (cash dividend 不影響股數)
CREATE TABLE IF NOT EXISTS daily_price_adj (
    stock_id          VARCHAR,
    date              DATE,
    adj_open          DOUBLE,
    adj_high          DOUBLE,
    adj_low           DOUBLE,
    adj_close         DOUBLE,
    raw_close         DOUBLE,    -- 保留 audit 用 (跟 daily_price 對照)
    cum_factor        DOUBLE,    -- 該日累計 factor (1.0 = 無調整)
    volume            BIGINT,    -- 維持 raw
    PRIMARY KEY (stock_id, date)
);
CREATE INDEX IF NOT EXISTS idx_daily_price_adj_date ON daily_price_adj(date);

-- v0.1.10: adjustment 建構狀態 (給 incremental rebuild 判斷用)
CREATE TABLE IF NOT EXISTS adjustment_state (
    stock_id              VARCHAR PRIMARY KEY,
    last_built_at         TIMESTAMP,
    last_event_date_used  DATE,        -- 用來偵測「新 event 進來但 adj 沒重建」
    n_events_applied      INTEGER,
    raw_first_date        DATE,
    raw_last_date         DATE
);

-- v0.1.11: 每日技術指標 (per-symbol)
-- 來源：features/technical.py 用 daily_price_adj 計算
-- 設計：欄位明確列出 (vs JSON blob) 方便 SQL 查詢 + 策略層使用
CREATE TABLE IF NOT EXISTS daily_features (
    stock_id            VARCHAR,
    date                DATE,
    -- Trend (4)
    sma_20              DOUBLE,
    sma_50              DOUBLE,
    sma_200             DOUBLE,
    ema_20              DOUBLE,
    -- Momentum (2)
    rsi_14              DOUBLE,
    roc_20              DOUBLE,   -- 20-day rate of change %
    -- Volatility (1)
    atr_14              DOUBLE,   -- Wilder smoothed
    -- Breakout (2)
    donchian_20_high    DOUBLE,
    donchian_20_low     DOUBLE,
    -- Volume (2)
    volume_ma_20        DOUBLE,
    rel_volume_20       DOUBLE,   -- today volume / 20-day avg
    -- meta
    computed_at         TIMESTAMP,
    PRIMARY KEY (stock_id, date)
);
CREATE INDEX IF NOT EXISTS idx_daily_features_date ON daily_features(date);

-- v0.1.11: 大盤 regime (single time series, 不分 symbol)
-- 來源：features/regime.py 用 TAIEX daily_price (raw, 指數無需 adj)
-- 規則 (deterministic):
--   crisis:  vol_20 > 0.020 (TAIEX 20-day return stdev > 2%)
--   bull:    close > sma_200 AND vol_20 <= 0.020
--   bear:    close < sma_200 AND vol_20 <= 0.020
--   neutral: 其他 (跨越 SMA200 的過渡)
CREATE TABLE IF NOT EXISTS market_regime (
    date         DATE PRIMARY KEY,
    taiex_close  DOUBLE,
    sma_200      DOUBLE,
    vol_20       DOUBLE,        -- 20-day stdev of daily returns
    regime       VARCHAR,        -- 'bull' / 'bear' / 'crisis' / 'neutral'
    computed_at  TIMESTAMP
);
"""


@contextmanager
def connect(read_only: bool = False) -> Iterator[duckdb.DuckDBPyConnection]:
    """DuckDB context manager。"""
    s = get_settings()
    conn = duckdb.connect(str(s.db_path), read_only=read_only)
    try:
        yield conn
    finally:
        conn.close()


def init_schema() -> None:
    """初始化所有 table (idempotent)。"""
    s = get_settings()
    s.ensure_dirs()
    with connect() as conn:
        conn.execute(SCHEMA_SQL)
    logger.info("schema_initialized", db_path=str(s.db_path))


def list_tables() -> list[str]:
    with connect(read_only=True) as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='main' ORDER BY table_name"
        ).fetchall()
    return [r[0] for r in rows]
