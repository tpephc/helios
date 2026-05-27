-- ============================================================================
-- Helios Migration: 0002_orders_journal_v0_1_16
-- ============================================================================
-- Target version: v0.1.16 (post-review v2)
-- Author: DEV C
-- Date: 2026-05-24
--
-- PURPOSE
-- -------
-- Replaces the legacy `orders` table with a proper order journal that supports
-- the v0.1.16 lifecycle state machine, transport/broker_reject failure
-- distinction, and crash-recovery semantics.
--
-- v2 changes from v1 (per advisor review):
--   - Adds `fill_date` column (C-P0-1, K-P1-4): reconcile MUST query by
--     expected execution date, not by intent date.
--   - Renames `requested_qty` → `requested_lots` (K-P0-1, decision 1):
--     unit-bearing name forces caller to think about units.
--   - Renames `filled_qty` → `filled_shares` (K-P0-1, decision 1):
--     unit-bearing name documents the broker-native deal unit.
--   - CHECK constraints updated to reflect new unit semantics.
--   - Defensive backup uses DROP IF EXISTS to handle re-application
--     (K-P2-d).
--
-- DESIGN BASIS
-- ------------
-- Audit report: docs/decision_records/v0_1_16_backtest_audit_report.md
-- Lifecycle: 7 states (INTENT, SUBMITTED, FILLED, PARTIAL, FAILED, CANCELLED, EXPIRED)
-- No PLACED state; "polled but unfilled" is encoded via last_polled_at + filled_shares=0.
--
-- UNIT CONVENTION (CRITICAL — read before touching this table)
-- ------------------------------------------------------------
-- requested_lots: integer count of Common lots (Taiwan stock: 1 lot = 1000 shares)
--                 Value 1 means "1 張" (1 lot = 1000 shares of intended trade)
-- filled_shares:  integer count of SHARES actually filled (broker-native unit
--                 from Shioaji `deal.quantity`)
--                 Value 1 means "1 股" (1 share filled)
-- limit_price:    TWD per share
-- notional:       limit_price * requested_lots * 1000 (TWD; full commitment)
--
-- Comparing requested_lots to filled_shares directly is ALWAYS WRONG.
-- Conversion: requested_shares = requested_lots * 1000
--
-- IDEMPOTENCY
-- -----------
-- DROP TABLE orders is destructive. Run only when:
--   1. No production orders exist (verified: dev_bootstrap cleaned, OPEN=0)
--   2. daily_run.py is NOT executing concurrently
--   3. intraday_monitor.py is NOT executing concurrently
--
-- ROLLBACK
-- --------
-- If migration must be reverted:
--   DROP TABLE orders;
--   ALTER TABLE orders_legacy_pre_v0_1_16 RENAME TO orders;
--   ALTER TABLE positions DROP COLUMN source_order_id;
--
-- CALLER CONTRACT
-- ---------------
-- All writers to `orders` MUST:
--   - use UPPERCASE 'BUY' / 'SELL' (CHECK constraint)
--   - use UPPERCASE status values (CHECK constraint)
--   - use OrderSide enum at domain boundary (no string normalization in
--     repository — see execution_model.md §10.2)
--   - populate intent_at AND fill_date on insert
--   - update updated_at on every UPDATE (application-layer, no trigger)
--   - set failure_type when status='FAILED' (CHECK constraint)
-- ============================================================================


-- ---------------------------------------------------------------------------
-- Step 1: Defensive backup of legacy orders table
-- ---------------------------------------------------------------------------
-- v2: DROP IF EXISTS guards against re-application leaving stale backup
-- with outdated structure.
DROP TABLE IF EXISTS orders_legacy_pre_v0_1_16;
CREATE TABLE orders_legacy_pre_v0_1_16 AS
SELECT * FROM orders;


-- ---------------------------------------------------------------------------
-- Step 2: Drop legacy orders table
-- ---------------------------------------------------------------------------
DROP TABLE orders;


-- ---------------------------------------------------------------------------
-- Step 3: Create new orders journal
-- ---------------------------------------------------------------------------
CREATE TABLE orders (
    -- ── Identity ─────────────────────────────────────────────────────────
    order_id        TEXT    PRIMARY KEY,
    signal_id       TEXT,                       -- FK signals.signal_id (nullable)

    -- ── Trade specification ──────────────────────────────────────────────
    symbol          TEXT    NOT NULL,
    side            TEXT    NOT NULL
                            CHECK (side IN ('BUY', 'SELL')),

    -- Unit-bearing column names: requested_lots = Common lot count (1 lot
    -- = 1000 shares); filled_shares = broker-native share count from deals.
    -- See UNIT CONVENTION at top of file.
    requested_lots  INTEGER NOT NULL
                            CHECK (requested_lots > 0),
    filled_shares   INTEGER NOT NULL DEFAULT 0
                            CHECK (filled_shares >= 0),
    avg_fill_price  DOUBLE,
    limit_price     DOUBLE,                     -- nullable: pre-guard-fail orders have none

    -- ── State machine (7 states) ─────────────────────────────────────────
    status          TEXT    NOT NULL
                            CHECK (status IN (
                                'INTENT',
                                'SUBMITTED',
                                'FILLED',
                                'PARTIAL',
                                'FAILED',
                                'CANCELLED',
                                'EXPIRED'
                            )),

    -- ── Failure classification (only set when status='FAILED') ───────────
    failure_type    TEXT    CHECK (failure_type IS NULL
                                   OR failure_type IN ('transport', 'broker_reject')),
    error_code      TEXT,
    error_message   TEXT,
    requires_broker_verification BOOLEAN NOT NULL DEFAULT FALSE,

    -- ── Broker integration ───────────────────────────────────────────────
    broker          TEXT,                        -- 'paper' / 'shioaji_sim' / 'shioaji_live'
    broker_order_id TEXT,                        -- NULL until broker accepts (empty
                                                 -- string is normalized to NULL by repository)

    -- ── Timestamps ───────────────────────────────────────────────────────
    intent_at       TIMESTAMP NOT NULL,          -- business decision time (T day)
    fill_date       DATE    NOT NULL,            -- expected execution date (T+1)
    submitted_at    TIMESTAMP,
    last_polled_at  TIMESTAMP,
    finalized_at    TIMESTAMP,

    -- ── Financial (TWD) ──────────────────────────────────────────────────
    -- notional = limit_price * requested_lots * 1000 (full intended commitment)
    -- This is set at INTENT time when limit_price is known, NOT recomputed
    -- from filled_shares. The intent represents committed capital regardless
    -- of fill outcome.
    notional        DOUBLE DEFAULT 0,
    commission      DOUBLE DEFAULT 0,
    tax             DOUBLE DEFAULT 0,

    -- ── Debug context ────────────────────────────────────────────────────
    metadata        TEXT,                        -- JSON; CHECK json_valid below

    -- ── Audit ────────────────────────────────────────────────────────────
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- ── Invariant 1: status/fill consistency ─────────────────────────────
    -- FILLED   => filled_shares == requested_lots * 1000 (full fill)
    -- PARTIAL  => 0 < filled_shares < requested_lots * 1000
    -- INTENT/SUBMITTED/FAILED/CANCELLED/EXPIRED: filled_shares unconstrained
    --   (typically 0)
    --
    -- Note: this CHECK explicitly multiplies by 1000 to mirror the
    -- requested_lots → shares conversion. If shares_per_lot ever changes
    -- (extremely unlikely for Taiwan equities), this constraint AND the
    -- application layer must update together.
    CHECK (
        (status = 'FILLED'  AND filled_shares = requested_lots * 1000)
        OR
        (status = 'PARTIAL' AND filled_shares > 0
                            AND filled_shares < requested_lots * 1000)
        OR
        (status IN ('INTENT', 'SUBMITTED', 'FAILED', 'CANCELLED', 'EXPIRED'))
    ),

    -- ── Invariant 2: FAILED requires failure_type ────────────────────────
    CHECK (
        (status = 'FAILED' AND failure_type IS NOT NULL)
        OR
        (status <> 'FAILED' AND failure_type IS NULL)
    ),

    -- ── Invariant 3: metadata must be valid JSON if present ──────────────
    CHECK (metadata IS NULL OR json_valid(metadata))
);

-- ---------------------------------------------------------------------------
-- Step 4: Indexes
-- ---------------------------------------------------------------------------
-- intent_at date prefix: legacy queries (reports scoped to decision day).
CREATE INDEX idx_orders_intent_date
    ON orders (CAST(intent_at AS DATE));

-- fill_date: PRIMARY reconcile lookup. T+1 morning reconcile queries by
-- fill_date == today, which captures all orders expected to settle today
-- regardless of when intent was recorded.
CREATE INDEX idx_orders_fill_date
    ON orders (fill_date);

-- status: PreTradeGuard queries today's order count; reconcile filters by status.
CREATE INDEX idx_orders_status
    ON orders (status);

-- broker_order_id: primary reconcile match key (orders ↔ broker trades).
CREATE INDEX idx_orders_broker_order_id
    ON orders (broker_order_id);

-- signal_id: backreference from signals to orders.
CREATE INDEX idx_orders_signal_id
    ON orders (signal_id);

-- (signal_id, intent_at): used for duplicate detection.
CREATE INDEX idx_orders_signal_intent
    ON orders (signal_id, intent_at);


-- ---------------------------------------------------------------------------
-- Step 5: ALTER positions for source_order_id FK
-- ---------------------------------------------------------------------------
ALTER TABLE positions
    ADD COLUMN IF NOT EXISTS source_order_id TEXT;

CREATE INDEX IF NOT EXISTS idx_positions_source_order_id
    ON positions (source_order_id);


-- ---------------------------------------------------------------------------
-- Step 6: Migration verification queries (run manually after applying)
-- ---------------------------------------------------------------------------
--
--   -- New table empty:
--   SELECT COUNT(*) FROM orders;  -- => 0
--
--   -- Schema reflects new unit-bearing columns:
--   PRAGMA table_info('orders');
--   -- requested_lots and filled_shares MUST appear, NOT requested_qty/filled_qty
--
--   -- fill_date column present:
--   -- (covered by PRAGMA above)
--
--   -- CHECK constraint enforces uppercase side (this INSERT should FAIL):
--   INSERT INTO orders (
--       order_id, symbol, side, requested_lots, status, intent_at, fill_date
--   ) VALUES (
--       'test_001', '2330', 'buy', 1, 'INTENT', CURRENT_TIMESTAMP, CURRENT_DATE
--   );
--   -- => CHECK violation on side (lowercase 'buy')
--
--   -- positions.source_order_id present:
--   PRAGMA table_info('positions');
--
--   -- Legacy backup exists:
--   SELECT COUNT(*) FROM orders_legacy_pre_v0_1_16;


-- ============================================================================
-- END MIGRATION
-- ============================================================================
