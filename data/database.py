# data/database.py
"""DuckDB 連線管理 + schema 載入。

Schema 設計原則：
- 價量資料：複合主鍵 (stock_id, date)，INSERT OR REPLACE 增量更新
- Event log (signals/orders): append-only，全程留下審計軌跡
- snapshots: 每日狀態快照，配合 event log 可重建任意時點

Version: v0.1.1 (2026-05-16)
Changelog:
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
