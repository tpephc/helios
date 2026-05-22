-- Migration: add intraday monitoring tables
-- Replace NNN with the next sequential migration number in your runner.
-- Idempotent via IF NOT EXISTS.

-- Valid zone values.  Using a macro here so the set is defined once.
-- DuckDB does not support named constraints in CREATE TABLE IF NOT EXISTS
-- the same way PostgreSQL does, so we inline the CHECK expressions.

-- Current zone per position (one row per open position).
CREATE TABLE IF NOT EXISTS intraday_alert_state (
    position_id      TEXT    NOT NULL PRIMARY KEY,
    zone             TEXT    NOT NULL DEFAULT 'NORMAL'
                             CHECK (zone IN ('NORMAL', 'APPROACH', 'BREACH')),
    zone_entered_at  TEXT    NOT NULL,
    last_price       DOUBLE,
    last_checked_at  TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL
);

-- Append-only audit log: one row per zone transition.
-- notification_status lifecycle: PENDING → SENT | FAILED
--   PENDING : DB committed, Telegram not yet attempted
--   SENT    : Telegram accepted
--   FAILED  : Telegram rejected or process crashed after commit
-- FAILED rows can be queried for missed-notification follow-up.
CREATE TABLE IF NOT EXISTS intraday_alert_transitions (
    transition_id         TEXT    NOT NULL PRIMARY KEY,
    position_id           TEXT    NOT NULL,
    run_id                TEXT    NOT NULL,
    transitioned_at       TEXT    NOT NULL,
    from_zone             TEXT    NOT NULL
                                  CHECK (from_zone IN ('NORMAL', 'APPROACH', 'BREACH')),
    to_zone               TEXT    NOT NULL
                                  CHECK (to_zone IN ('NORMAL', 'APPROACH', 'BREACH')),
    price                 DOUBLE  NOT NULL,
    trailing_stop         DOUBLE  NOT NULL,
    approach_enter        DOUBLE  NOT NULL,
    approach_exit         DOUBLE  NOT NULL,
    max_close_since_entry DOUBLE  NOT NULL,
    entry_atr             DOUBLE  NOT NULL,
    notification_status   TEXT    NOT NULL DEFAULT 'PENDING'
                                  CHECK (notification_status IN ('PENDING', 'SENT', 'FAILED'))
);

CREATE INDEX IF NOT EXISTS idx_alert_transitions_position
    ON intraday_alert_transitions (position_id, transitioned_at);

-- Partial index: quickly find transitions that need attention.
CREATE INDEX IF NOT EXISTS idx_alert_transitions_non_sent
    ON intraday_alert_transitions (position_id, transitioned_at);

-- Run metadata: one row per cron execution.
-- transitions_logged: zone transitions written to DB (irrespective of Telegram outcome).
-- alerts_sent:        subset of transitions_logged where Telegram returned True.
-- If alerts_sent < transitions_logged, check intraday_alert_transitions for FAILED rows.
CREATE TABLE IF NOT EXISTS intraday_monitor_runs (
    run_id              TEXT    NOT NULL PRIMARY KEY,
    run_at              TEXT    NOT NULL,
    symbols_attempted   INTEGER NOT NULL DEFAULT 0,
    symbols_succeeded   INTEGER NOT NULL DEFAULT 0,
    positions_checked   INTEGER NOT NULL DEFAULT 0,
    transitions_logged  INTEGER NOT NULL DEFAULT 0,
    alerts_sent         INTEGER NOT NULL DEFAULT 0,
    system_alert_sent   INTEGER NOT NULL DEFAULT 0,
    error_summary       TEXT,
    duration_seconds    DOUBLE  NOT NULL DEFAULT 0.0
);

CREATE INDEX IF NOT EXISTS idx_monitor_runs_run_at
    ON intraday_monitor_runs (run_at);
