# data/database.py
"""DuckDB 連線管理 + schema 載入。

Schema 設計原則：
- 價量資料：複合主鍵 (stock_id, date)，INSERT OR REPLACE 增量更新
- Event log (signals/orders): append-only，全程留下審計軌跡
- snapshots: 每日狀態快照，配合 event log 可重建任意時點

Version: v0.1.18 (2026-05-28)
Changelog:
  v0.1.18 (2026-05-28): orders + positions 加 account_id NOT NULL;
    positions 補 is_synthetic/bootstrap_batch_id/source_order_id 進 SCHEMA_SQL;
    compound indexes on (account_id, status), (account_id, symbol);
    migration: table recreate + backfill with 'philip_sim' default.
  v0.1.6 (2026-05-17): 新增 positions 表 (v0.1.14.2 paper trading state machine)
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
    signal_date      DATE NOT NULL,      -- 市場語意日期 (as_of of the run that generated it)
    created_at       TIMESTAMP NOT NULL, -- 系統建立時間 (when row was inserted)
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
CREATE INDEX IF NOT EXISTS idx_signals_signal_date ON signals(signal_date);
CREATE INDEX IF NOT EXISTS idx_signals_created_at  ON signals(created_at);
CREATE INDEX IF NOT EXISTS idx_signals_status      ON signals(approval_status);
CREATE INDEX IF NOT EXISTS idx_signals_symbol      ON signals(symbol);
CREATE INDEX IF NOT EXISTS idx_signals_idempotency
    ON signals(symbol, strategy, signal_type, signal_date, approval_status);
CREATE UNIQUE INDEX IF NOT EXISTS uq_signals_canonical_key
    ON signals(symbol, strategy, signal_type, signal_date);

-- ─────────────────────────────────────────────────────────────────────────
-- orders journal — v0.1.18
-- Migration from v0.1.17: added account_id NOT NULL.
-- Canonical migration: migrations/0003_orders_v0_1_17.sql (v0.1.17),
--   _migrate_table_add_account_id() in database.py (v0.1.18).
-- KEEP THIS BLOCK IN SYNC WITH MIGRATIONS. A semantic-equivalence
-- smoke test in tests/test_schema_consistency.py verifies the two.
--
-- UNIT CONVENTION (read before touching this table):
--   requested_lots: Common lot count (1 lot = 1000 shares)
--   filled_shares:  broker-native share count from Shioaji deals
--   Comparing the two without × 1000 conversion is a banned anti-pattern
--   (see docs/design/execution_model.md §UNIT CONVENTION).
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orders (
    -- Identity
    order_id        TEXT    PRIMARY KEY,
    account_id      TEXT    NOT NULL,
    signal_id       TEXT,

    -- Trade specification
    symbol          TEXT    NOT NULL,
    side            TEXT    NOT NULL
                            CHECK (side IN ('BUY', 'SELL')),
    order_lot_type  TEXT    NOT NULL DEFAULT 'COMMON'
                            CHECK (order_lot_type IN ('COMMON', 'ODD')),

    -- Quantities (unit-bearing names; see UNIT CONVENTION above)
    requested_lots  INTEGER NOT NULL
                            CHECK (requested_lots > 0),
    filled_shares   INTEGER NOT NULL DEFAULT 0
                            CHECK (filled_shares >= 0),
    avg_fill_price  DOUBLE,
    limit_price     DOUBLE,

    -- Lifecycle state (8 states; v0.1.17 adds READY_FOR_SUBMISSION)
    status          TEXT    NOT NULL
                            CHECK (status IN (
                                'INTENT',
                                'READY_FOR_SUBMISSION',
                                'SUBMITTED',
                                'FILLED',
                                'PARTIAL',
                                'FAILED',
                                'CANCELLED',
                                'EXPIRED'
                            )),

    -- Failure classification (only set when status='FAILED')
    failure_type    TEXT    CHECK (failure_type IS NULL
                                   OR failure_type IN ('transport', 'broker_reject')),
    error_code      TEXT,
    error_message   TEXT,
    requires_broker_verification BOOLEAN NOT NULL DEFAULT FALSE,

    -- Broker integration
    broker          TEXT,
    broker_order_id TEXT,

    -- Timestamps
    intent_at       TIMESTAMP NOT NULL,
    fill_date       DATE    NOT NULL,
    target_fill_date DATE,
    submitted_at    TIMESTAMP,
    last_polled_at  TIMESTAMP,
    finalized_at    TIMESTAMP,

    -- Financial (TWD)
    notional        DOUBLE DEFAULT 0,
    commission      DOUBLE DEFAULT 0,
    tax             DOUBLE DEFAULT 0,

    -- Debug context
    metadata        TEXT,

    -- Audit
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Invariant 1: status/fill consistency (unit-aware; share-equivalent)
    CHECK (
        (status = 'FILLED'  AND order_lot_type = 'COMMON' AND filled_shares = requested_lots * 1000)
        OR
        (status = 'FILLED'  AND order_lot_type = 'ODD'    AND filled_shares = requested_lots)
        OR
        (status = 'PARTIAL' AND order_lot_type = 'COMMON' AND filled_shares > 0
                            AND filled_shares < requested_lots * 1000)
        OR
        (status = 'PARTIAL' AND order_lot_type = 'ODD'    AND filled_shares > 0
                            AND filled_shares < requested_lots)
        OR
        (status IN ('INTENT', 'READY_FOR_SUBMISSION', 'SUBMITTED',
                    'FAILED', 'CANCELLED', 'EXPIRED'))
    ),
    -- Invariant 2: FAILED <=> failure_type set
    CHECK (
        (status = 'FAILED' AND failure_type IS NOT NULL)
        OR
        (status <> 'FAILED' AND failure_type IS NULL)
    ),
    -- Invariant 3: metadata must be valid JSON if present
    CHECK (metadata IS NULL OR json_valid(metadata))
);

CREATE INDEX IF NOT EXISTS idx_orders_intent_date
    ON orders (CAST(intent_at AS DATE));
CREATE INDEX IF NOT EXISTS idx_orders_fill_date
    ON orders (fill_date);
CREATE INDEX IF NOT EXISTS idx_orders_target_fill_date
    ON orders (target_fill_date);
CREATE INDEX IF NOT EXISTS idx_orders_status
    ON orders (status);
CREATE INDEX IF NOT EXISTS idx_orders_status_target
    ON orders (status, target_fill_date);
CREATE INDEX IF NOT EXISTS idx_orders_broker_order_id
    ON orders (broker_order_id);
CREATE INDEX IF NOT EXISTS idx_orders_signal_id
    ON orders (signal_id);
CREATE INDEX IF NOT EXISTS idx_orders_signal_intent
    ON orders (signal_id, intent_at);
CREATE INDEX IF NOT EXISTS idx_orders_account_status
    ON orders (account_id, status);
CREATE INDEX IF NOT EXISTS idx_orders_account_symbol
    ON orders (account_id, symbol);
CREATE INDEX IF NOT EXISTS idx_orders_account_broker_oid
    ON orders (account_id, broker_order_id);

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

-- ═══════════════════════════════════════════════════════════
-- v0.1.14.2: positions table (paper trading state machine)
-- v0.1.18: added account_id NOT NULL; formalized is_synthetic,
--   bootstrap_batch_id, source_order_id (existed in DB but were
--   missing from SCHEMA_SQL).
-- ═══════════════════════════════════════════════════════════
-- ARCHITECTURE.md §6.5 Signal Lifecycle State Machine.
--
-- Promotes positions from derived-from-orders to first-class entity,
-- because v0.1.14.2 needs stateful per-position fields (max_close_since_entry,
-- regime_at_entry, MFE/MAE) that cannot be cleanly derived from orders alone.
-- The old event-sourced compute_current_positions() is now legacy/derived-helper.
--
-- States (status column): OPENING / OPEN / CLOSING / CLOSED
--   OPENING  - buy order submitted, awaiting fill (transient; paper broker: instant)
--   OPEN     - filled, running daily updates of MFE/MAE/max_close
--   CLOSING  - sell order submitted, awaiting fill (transient)
--   CLOSED   - fully realized; exit fields populated
CREATE TABLE IF NOT EXISTS positions (
    position_id              VARCHAR PRIMARY KEY,
    account_id               VARCHAR NOT NULL,
    entry_signal_id          VARCHAR,                -- FK signals.signal_id (entry)
    entry_order_id           VARCHAR,                -- FK orders.order_id (buy)
    exit_signal_id           VARCHAR,                -- FK signals.signal_id (exit), nullable
    exit_order_id            VARCHAR,                -- FK orders.order_id (sell), nullable

    symbol                   VARCHAR NOT NULL,
    strategy                 VARCHAR NOT NULL,

    -- Entry context
    entry_date               DATE NOT NULL,
    entry_price              DOUBLE NOT NULL,
    entry_atr                DOUBLE NOT NULL,
    regime_at_entry          VARCHAR NOT NULL,       -- per review #1
    sector                   VARCHAR NOT NULL,
    is_etf                   BOOLEAN NOT NULL DEFAULT FALSE,

    -- Sizing
    shares                   BIGINT NOT NULL,
    notional_at_entry        DOUBLE NOT NULL,        -- target capital deployed (NTD)
    entry_commission         DOUBLE NOT NULL DEFAULT 0,
    entry_slippage_cost      DOUBLE NOT NULL DEFAULT 0,

    -- Running stats (updated daily while OPEN)
    last_close               DOUBLE,
    last_updated_date        DATE,
    max_close_since_entry    DOUBLE,
    max_close_date           DATE,
    min_close_since_entry    DOUBLE,
    min_close_date           DATE,

    -- Exit (populated when CLOSED)
    exit_date                DATE,
    exit_price               DOUBLE,
    exit_reason              VARCHAR,                -- regime_exit / trailing_stop / manual / end_of_paper
    regime_at_exit           VARCHAR,
    exit_commission          DOUBLE DEFAULT 0,
    exit_tax                 DOUBLE DEFAULT 0,
    exit_slippage_cost       DOUBLE DEFAULT 0,
    exit_proceeds            DOUBLE,                 -- net NTD received from sell

    status                   VARCHAR NOT NULL,       -- OPENING / OPEN / CLOSING / CLOSED
    created_at               TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at               TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Bootstrap / synthetic fields (formalized in v0.1.18 SCHEMA_SQL)
    is_synthetic             BOOLEAN DEFAULT FALSE,
    bootstrap_batch_id       VARCHAR,
    source_order_id          VARCHAR
);

CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol);
CREATE INDEX IF NOT EXISTS idx_positions_entry_date ON positions(entry_date);
CREATE INDEX IF NOT EXISTS idx_positions_account_status
    ON positions (account_id, status);
CREATE INDEX IF NOT EXISTS idx_positions_account_symbol
    ON positions (account_id, symbol);
CREATE INDEX IF NOT EXISTS idx_positions_source_order_id
    ON positions (source_order_id);

-- v0.1.19: pullback strategy feature cache
-- Source: features/pullback_features.py
-- Columns mirror find_pullback_candidates() query requirements exactly.
CREATE TABLE IF NOT EXISTS bullish_features (
    stock_id            VARCHAR,
    date                DATE,
    beta_adj_rs_20d     DOUBLE,
    dist_above_ma20_atr DOUBLE,
    beta_60             DOUBLE,
    sma20_slope_10d     DOUBLE,
    computed_at         TIMESTAMP,
    PRIMARY KEY (stock_id, date)
);
CREATE INDEX IF NOT EXISTS idx_bullish_features_date ON bullish_features(date);

-- v0.1.20: security lifecycle — original listing / board-transfer dates
-- Source: MOPS hand-verified; seed at data/reference/security_lifecycle_seed_v1.csv
-- Covers only the 18 stocks with IF-1 pre-listing contamination.
-- Stocks absent from this table are assumed fully listed throughout the panel.
-- Used by: listed_market_daily_price_adj view (P1-DATA remediation).
-- Governance: docs/decision_records/p1_data_remediation_spec.md v1.0.0
CREATE TABLE IF NOT EXISTS security_lifecycle (
    stock_id        VARCHAR     NOT NULL,
    otc_first_date  DATE,
    mainboard_date  DATE        NOT NULL,
    mainboard_type  VARCHAR     NOT NULL,
    source          VARCHAR     NOT NULL,
    source_url      VARCHAR,
    verified_at     DATE        NOT NULL,
    verified_by     VARCHAR     NOT NULL,
    notes           VARCHAR,
    PRIMARY KEY (stock_id)
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


def _migrate_orders_v0_1_17() -> bool:
    """Migrate orders table: add READY_FOR_SUBMISSION status + target_fill_date.

    DuckDB CHECK constraints cannot be ALTERed, so we recreate the table.
    Strategy: rename old → let init_schema's SCHEMA_SQL create new → copy → drop old.

    Called by init_schema() BEFORE conn.execute(SCHEMA_SQL). This ordering
    ensures the old table is renamed so SCHEMA_SQL creates a fresh one with
    the v0.1.17 schema (READY_FOR_SUBMISSION + target_fill_date).

    Safe for small tables (expected <100 rows in paper trading phase).
    Returns True if migration was applied, False if already migrated.
    """
    with connect() as conn:
        # Check if orders table exists
        tables = [r[0] for r in conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_name = 'orders'"
        ).fetchall()]

        if not tables:
            return False  # fresh DB, no migration needed

        cols = [r[0] for r in conn.execute("DESCRIBE orders").fetchall()]
        if "target_fill_date" in cols:
            return False  # already migrated

        old_count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        logger.info("migrate_orders_v0_1_17_start", existing_rows=old_count)

        # Drop indexes first — DuckDB cannot rename tables with dependencies.
        for idx in conn.execute(
            "SELECT index_name FROM duckdb_indexes() "
            "WHERE table_name = 'orders'"
        ).fetchall():
            conn.execute(f"DROP INDEX {idx[0]}")

        # Rename old table. SCHEMA_SQL (called next by init_schema) will
        # create a fresh orders table with the v0.1.17 schema.
        conn.execute("ALTER TABLE orders RENAME TO _orders_v0_1_16_bak")

    # Return True to signal that init_schema must run the copy-back step.
    # We store old_count for verification in the post-copy step.
    _migrate_orders_v0_1_17._pending_count = old_count
    return True


def _migrate_orders_v0_1_17_copy_back() -> None:
    """Copy data from backup table into new orders table after SCHEMA_SQL runs.

    Called by init_schema() AFTER conn.execute(SCHEMA_SQL) when migration
    was applied. Backfills target_fill_date = fill_date for existing rows.
    """
    with connect() as conn:
        # Check backup table exists
        tables = [r[0] for r in conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_name = '_orders_v0_1_16_bak'"
        ).fetchall()]

        if not tables:
            return  # no backup to copy from

        conn.execute("""
            INSERT INTO orders (
                order_id, signal_id, symbol, side, requested_lots,
                filled_shares, avg_fill_price, limit_price, status,
                failure_type, error_code, error_message,
                requires_broker_verification, broker, broker_order_id,
                intent_at, fill_date, target_fill_date,
                submitted_at, last_polled_at, finalized_at,
                notional, commission, tax, metadata,
                created_at, updated_at
            )
            SELECT
                order_id, signal_id, symbol, side, requested_lots,
                filled_shares, avg_fill_price, limit_price, status,
                failure_type, error_code, error_message,
                requires_broker_verification, broker, broker_order_id,
                intent_at, fill_date, fill_date,
                submitted_at, last_polled_at, finalized_at,
                notional, commission, tax, metadata,
                created_at, updated_at
            FROM _orders_v0_1_16_bak
        """)

        # Verify row count
        expected = getattr(_migrate_orders_v0_1_17, '_pending_count', None)
        new_count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        if expected is not None and expected != new_count:
            raise RuntimeError(
                f"Migration row count mismatch: expected={expected}, "
                f"got={new_count}. Backup _orders_v0_1_16_bak preserved."
            )

        conn.execute("DROP TABLE _orders_v0_1_16_bak")
        logger.info("migrate_orders_v0_1_17_complete", rows_migrated=new_count)


# ─────────────────────────────────────────────────────────────────────────────
# v0.1.18 migration: add account_id to orders + positions
# ─────────────────────────────────────────────────────────────────────────────

_V0_1_18_DEFAULT_ACCOUNT = "philip_sim"
_V0_1_18_ALLOWED_TABLES = {"orders", "positions"}


def _needs_account_id_migration(table: str) -> bool:
    """Check if a table exists but lacks account_id column."""
    if table not in _V0_1_18_ALLOWED_TABLES:
        raise ValueError(
            f"_needs_account_id_migration: table must be one of "
            f"{sorted(_V0_1_18_ALLOWED_TABLES)}, got {table!r}"
        )
    with connect() as conn:
        tables = [r[0] for r in conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_name = ?",
            [table],
        ).fetchall()]
        if not tables:
            return False  # table doesn't exist yet; SCHEMA_SQL will create it
        cols = [r[0] for r in conn.execute(f"DESCRIBE {table}").fetchall()]
        return "account_id" not in cols


def _migrate_table_add_account_id(table: str) -> bool:
    """Rename table so SCHEMA_SQL recreates it with account_id.

    Same two-phase pattern as v0.1.17:
      Phase 1 (this function): DROP indexes → RENAME to _bak
      Phase 2 (_copy_back): INSERT ... SELECT with backfill → DROP _bak

    Returns True if migration was initiated, False if not needed.
    """
    if not _needs_account_id_migration(table):
        return False

    bak_name = f"_{table}_v0_1_17_bak"

    with connect() as conn:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        logger.info(
            "migrate_account_id_start",
            table=table, existing_rows=count,
        )

        # Drop indexes (DuckDB cannot rename tables with index dependencies)
        for idx in conn.execute(
            "SELECT index_name FROM duckdb_indexes() "
            "WHERE table_name = ?",
            [table],
        ).fetchall():
            conn.execute(f"DROP INDEX {idx[0]}")

        conn.execute(f"ALTER TABLE {table} RENAME TO {bak_name}")

    # Store count for verification
    _migrate_table_add_account_id._pending_counts = getattr(
        _migrate_table_add_account_id, "_pending_counts", {}
    )
    _migrate_table_add_account_id._pending_counts[table] = count
    return True


def _copy_back_with_account_id(table: str) -> None:
    """Copy data from backup table into new table (with account_id backfill).

    Called AFTER SCHEMA_SQL creates the new table with account_id column.
    Preserves new table column order; backfills account_id with default.
    """
    if table not in _V0_1_18_ALLOWED_TABLES:
        raise ValueError(
            f"_copy_back_with_account_id: table must be one of "
            f"{sorted(_V0_1_18_ALLOWED_TABLES)}, got {table!r}"
        )

    bak_name = f"_{table}_v0_1_17_bak"

    with connect() as conn:
        # Check backup exists
        tables = [r[0] for r in conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_name = ?",
            [bak_name],
        ).fetchall()]
        if not tables:
            return

        # Get column lists
        old_cols = set(
            r[0] for r in conn.execute(f"DESCRIBE {bak_name}").fetchall()
        )
        new_cols = [
            r[0] for r in conn.execute(f"DESCRIBE {table}").fetchall()
        ]

        # Build INSERT/SELECT preserving new table column order.
        # For each new column:
        #   - account_id → backfill with default
        #   - exists in old table → copy
        #   - new column not in old table → skip (will get DB default);
        #     log warning so future maintainers know it's not magic-safe
        insert_cols: list[str] = []
        select_exprs: list[str] = []

        for col in new_cols:
            if col == "account_id":
                insert_cols.append(col)
                select_exprs.append(
                    f"'{_V0_1_18_DEFAULT_ACCOUNT}'"
                )
            elif col in old_cols:
                insert_cols.append(col)
                select_exprs.append(col)
            else:
                # New column not in old table — relies on DB DEFAULT.
                # If column is NOT NULL without DEFAULT, INSERT will fail
                # at runtime (desired: fail-fast over silent corruption).
                logger.warning(
                    "migration_column_default_assumed",
                    table=table,
                    column=col,
                )

        if len(insert_cols) != len(select_exprs):
            raise RuntimeError(
                f"_copy_back_with_account_id: insert/select column count "
                f"mismatch: {len(insert_cols)} vs {len(select_exprs)}"
            )

        sql = (
            f"INSERT INTO {table} ({', '.join(insert_cols)})\n"
            f"SELECT {', '.join(select_exprs)}\n"
            f"FROM {bak_name}"
        )
        logger.info(
            "migrate_account_id_copy_back",
            table=table,
            insert_cols_count=len(insert_cols),
            old_cols_count=len(old_cols),
            new_cols_count=len(new_cols),
        )
        conn.execute(sql)

        # Verify row count
        expected = getattr(
            _migrate_table_add_account_id, "_pending_counts", {}
        ).get(table)
        new_count = conn.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]

        if expected is not None and expected != new_count:
            raise RuntimeError(
                f"Migration row count mismatch for {table}: "
                f"expected={expected}, got={new_count}. "
                f"Backup {bak_name} preserved."
            )

        # Verify no NULL account_id
        null_count = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE account_id IS NULL"
        ).fetchone()[0]
        if null_count > 0:
            raise RuntimeError(
                f"Migration integrity check failed: {null_count} rows in "
                f"{table} have NULL account_id. Backup {bak_name} preserved."
            )

        conn.execute(f"DROP TABLE {bak_name}")
        logger.info(
            "migrate_account_id_complete",
            table=table, rows_migrated=new_count,
            default_account=_V0_1_18_DEFAULT_ACCOUNT,
        )


def verify_post_migration() -> None:
    """Post-migration integrity checks for v0.1.18.

    Verifies:
    1. account_id column exists and is NOT NULL in both tables
    2. Row counts (logged for audit)
    3. Required indexes exist
    """
    with connect(read_only=True) as conn:
        for table in ("orders", "positions"):
            # Check account_id column exists
            cols = [r[0] for r in conn.execute(
                f"DESCRIBE {table}"
            ).fetchall()]
            if "account_id" not in cols:
                raise RuntimeError(
                    f"verify_post_migration: {table} missing "
                    f"account_id column"
                )

            # Check no NULL account_id
            null_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE account_id IS NULL"
            ).fetchone()[0]
            if null_count > 0:
                raise RuntimeError(
                    f"verify_post_migration: {table} has {null_count} "
                    f"rows with NULL account_id"
                )

        # Row count sanity (log for audit — counts may legitimately
        # differ from pre-migration if concurrent writes occurred,
        # but this is the migration completion gate so we log them)
        orders_count = conn.execute(
            "SELECT COUNT(*) FROM orders"
        ).fetchone()[0]
        positions_count = conn.execute(
            "SELECT COUNT(*) FROM positions"
        ).fetchone()[0]

        # Check indexes exist
        index_names = {r[0] for r in conn.execute(
            "SELECT index_name FROM duckdb_indexes()"
        ).fetchall()}

        required_indexes = {
            "idx_orders_account_status",
            "idx_orders_account_symbol",
            "idx_orders_account_broker_oid",
            "idx_positions_account_status",
            "idx_positions_account_symbol",
        }
        missing = required_indexes - index_names
        if missing:
            raise RuntimeError(
                f"verify_post_migration: missing indexes: "
                f"{sorted(missing)}"
            )

    logger.info(
        "verify_post_migration_passed",
        orders_count=orders_count,
        positions_count=positions_count,
    )


def init_schema() -> None:
    """初始化所有 table (idempotent).

    Migration order:
      1. v0.1.17: orders table READY_FOR_SUBMISSION + target_fill_date
      2. v0.1.18: orders + positions add account_id
      3. Execute SCHEMA_SQL (creates any missing tables)
      4. Copy-back migrated data from backup tables
      5. Post-migration verification (only if migrations ran)
    """
    s = get_settings()
    s.ensure_dirs()

    # ── Phase 1: Rename tables that need migration ──────────────────────
    # v0.1.17: orders table schema migration
    _migrated_v0_1_17 = _migrate_orders_v0_1_17()

    # v0.1.18: account_id migration (orders + positions)
    _migrated_orders_v0_1_18 = _migrate_table_add_account_id("orders")
    _migrated_positions_v0_1_18 = _migrate_table_add_account_id("positions")

    any_migration = (
        _migrated_v0_1_17
        or _migrated_orders_v0_1_18
        or _migrated_positions_v0_1_18
    )

    # ── Phase 2: Create fresh tables from SCHEMA_SQL ────────────────────
    with connect() as conn:
        _drop_pre_c3_signals_if_present(conn)
        conn.execute(SCHEMA_SQL)

    # ── Phase 3: Copy data back from backup tables ──────────────────────
    if _migrated_v0_1_17:
        _migrate_orders_v0_1_17_copy_back()

    if _migrated_orders_v0_1_18:
        _copy_back_with_account_id("orders")

    if _migrated_positions_v0_1_18:
        _copy_back_with_account_id("positions")

    # ── Phase 4: Post-migration verification ────────────────────────────
    if any_migration:
        verify_post_migration()

    logger.info("schema_initialized", db_path=str(s.db_path))


def _drop_pre_c3_signals_if_present(conn) -> None:
    """If signals table exists with old timestamp column (no signal_date), drop it.

    Old schema (pre-c3): signal_id, timestamp, symbol, ...
    New schema (c3):     signal_id, signal_date, created_at, symbol, ...

    Detection: column 'signal_date' missing in existing signals table.
    """
    existing = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='main' AND table_name='signals'"
    ).fetchone()
    if not existing:
        return
    cols = {row[0] for row in conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='main' AND table_name='signals'"
    ).fetchall()}
    if "signal_date" not in cols:
        logger.warning("pre_c3_signals_schema_detected", action="DROP_AND_REBUILD")
        conn.execute("DROP TABLE signals")


def list_tables() -> list[str]:
    with connect(read_only=True) as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='main' ORDER BY table_name"
        ).fetchall()
    return [r[0] for r in rows]
