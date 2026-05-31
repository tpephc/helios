#!/usr/bin/env python3
# scripts/migrate_orders_lot_type.py
"""Schema migration: add order_lot_type to orders table.

Adds order_lot_type VARCHAR DEFAULT 'COMMON' and relaxes the CHECK
constraint on filled_shares to support both COMMON and ODD lot orders.

COMMON: filled_shares = requested_lots * 1000
ODD:    filled_shares = requested_lots  (requested_lots = requested shares)

DuckDB does not support ALTER CONSTRAINT, so this recreates the table.
Idempotent: skips if order_lot_type column already exists.
"""
from __future__ import annotations

import sys
from data.database import connect, init_schema

NEW_DDL = """
CREATE TABLE orders (
    order_id VARCHAR PRIMARY KEY,
    account_id VARCHAR NOT NULL,
    signal_id VARCHAR,
    symbol VARCHAR NOT NULL,
    side VARCHAR NOT NULL,
    order_lot_type VARCHAR DEFAULT 'COMMON' NOT NULL,
    requested_lots INTEGER NOT NULL,
    filled_shares INTEGER DEFAULT 0 NOT NULL,
    avg_fill_price DOUBLE,
    limit_price DOUBLE,
    status VARCHAR NOT NULL,
    failure_type VARCHAR,
    error_code VARCHAR,
    error_message VARCHAR,
    requires_broker_verification BOOLEAN DEFAULT FALSE NOT NULL,
    broker VARCHAR,
    broker_order_id VARCHAR,
    intent_at TIMESTAMP NOT NULL,
    fill_date DATE NOT NULL,
    target_fill_date DATE,
    submitted_at TIMESTAMP,
    last_polled_at TIMESTAMP,
    finalized_at TIMESTAMP,
    notional DOUBLE DEFAULT 0,
    commission DOUBLE DEFAULT 0,
    tax DOUBLE DEFAULT 0,
    metadata VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,

    CHECK (side IN ('BUY', 'SELL')),
    CHECK (requested_lots > 0),
    CHECK (filled_shares >= 0),
    CHECK (status IN ('INTENT', 'READY_FOR_SUBMISSION', 'SUBMITTED',
                      'FILLED', 'PARTIAL', 'FAILED', 'CANCELLED', 'EXPIRED')),
    CHECK (failure_type IS NULL OR failure_type IN ('transport', 'broker_reject')),
    CHECK (order_lot_type IN ('COMMON', 'ODD')),

    -- Lot-type-aware fill constraint
    CHECK (
        (status = 'FILLED' AND (
            (order_lot_type = 'COMMON' AND filled_shares = requested_lots * 1000) OR
            (order_lot_type = 'ODD'    AND filled_shares = requested_lots)
        ))
        OR
        (status = 'PARTIAL' AND filled_shares > 0 AND (
            (order_lot_type = 'COMMON' AND filled_shares < requested_lots * 1000) OR
            (order_lot_type = 'ODD'    AND filled_shares < requested_lots)
        ))
        OR
        (status IN ('INTENT', 'READY_FOR_SUBMISSION', 'SUBMITTED',
                    'FAILED', 'CANCELLED', 'EXPIRED'))
    ),

    CHECK ((status = 'FAILED' AND failure_type IS NOT NULL) OR
           (status != 'FAILED' AND failure_type IS NULL)),
    CHECK (metadata IS NULL OR json_valid(metadata))
)
"""

def main() -> int:
    init_schema()
    with connect() as conn:
        # Idempotency check
        cols = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'orders' AND column_name = 'order_lot_type'"
        ).fetchall()
        if cols:
            print("✅  order_lot_type column already exists, skipping migration.")
            return 0

        n_before = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        print(f"📦  Recreating orders table (dropping {n_before} existing rows)...")

        conn.execute("DROP TABLE orders")
        conn.execute(NEW_DDL)

        print(f"✅  Migration complete: orders table recreated with order_lot_type.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
