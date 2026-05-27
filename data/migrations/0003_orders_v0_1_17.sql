-- Migration 0003: orders table v0.1.17
-- Adds READY_FOR_SUBMISSION status and target_fill_date column.
-- DuckDB CHECK constraints cannot be ALTERed; table must be recreated.
--
-- Prerequisites: migration 0002 (orders_journal_v0_1_16) applied.
-- Idempotent: safe to re-run (checks for target_fill_date column).
--
-- Applied by: data/database.py _migrate_orders_v0_1_17()
-- Date: 2026-05-27

ALTER TABLE orders RENAME TO _orders_v0_1_16_bak;

CREATE TABLE orders (
    order_id        TEXT    PRIMARY KEY,
    signal_id       TEXT,
    symbol          TEXT    NOT NULL,
    side            TEXT    NOT NULL CHECK (side IN ('BUY', 'SELL')),
    requested_lots  INTEGER NOT NULL CHECK (requested_lots > 0),
    filled_shares   INTEGER NOT NULL DEFAULT 0 CHECK (filled_shares >= 0),
    avg_fill_price  DOUBLE,
    limit_price     DOUBLE,
    status          TEXT    NOT NULL
                            CHECK (status IN (
                                'INTENT', 'READY_FOR_SUBMISSION', 'SUBMITTED',
                                'FILLED', 'PARTIAL', 'FAILED', 'CANCELLED', 'EXPIRED'
                            )),
    failure_type    TEXT    CHECK (failure_type IS NULL
                                   OR failure_type IN ('transport', 'broker_reject')),
    error_code      TEXT,
    error_message   TEXT,
    requires_broker_verification BOOLEAN NOT NULL DEFAULT FALSE,
    broker          TEXT,
    broker_order_id TEXT,
    intent_at       TIMESTAMP NOT NULL,
    fill_date       DATE    NOT NULL,
    target_fill_date DATE,
    submitted_at    TIMESTAMP,
    last_polled_at  TIMESTAMP,
    finalized_at    TIMESTAMP,
    notional        DOUBLE DEFAULT 0,
    commission      DOUBLE DEFAULT 0,
    tax             DOUBLE DEFAULT 0,
    metadata        TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        (status = 'FILLED'  AND filled_shares = requested_lots * 1000)
        OR (status = 'PARTIAL' AND filled_shares > 0
                               AND filled_shares < requested_lots * 1000)
        OR (status IN ('INTENT', 'READY_FOR_SUBMISSION', 'SUBMITTED',
                       'FAILED', 'CANCELLED', 'EXPIRED'))
    ),
    CHECK (
        (status = 'FAILED' AND failure_type IS NOT NULL)
        OR (status <> 'FAILED' AND failure_type IS NULL)
    ),
    CHECK (metadata IS NULL OR json_valid(metadata))
);

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
FROM _orders_v0_1_16_bak;

DROP TABLE _orders_v0_1_16_bak;

CREATE INDEX IF NOT EXISTS idx_orders_intent_date ON orders (CAST(intent_at AS DATE));
CREATE INDEX IF NOT EXISTS idx_orders_fill_date ON orders (fill_date);
CREATE INDEX IF NOT EXISTS idx_orders_target_fill_date ON orders (target_fill_date);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders (status);
CREATE INDEX IF NOT EXISTS idx_orders_status_target ON orders (status, target_fill_date);
CREATE INDEX IF NOT EXISTS idx_orders_broker_order_id ON orders (broker_order_id);
CREATE INDEX IF NOT EXISTS idx_orders_signal_id ON orders (signal_id);
CREATE INDEX IF NOT EXISTS idx_orders_signal_intent ON orders (signal_id, intent_at);
