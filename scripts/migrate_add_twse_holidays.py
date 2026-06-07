#!/usr/bin/env python3
# scripts/migrate_add_twse_holidays.py
"""Migration — add twse_holidays table — v1.0.0.

Creates the twse_holidays table for persisting TWSE official holiday
announcements. This table is Layer 1 of the three-layer hybrid calendar
introduced in market/trading_calendar.py v0.2.0.

Safe to run multiple times (CREATE TABLE IF NOT EXISTS + idempotent index).

Usage:
    uv run python scripts/migrate_add_twse_holidays.py
"""
from __future__ import annotations

import sys

from data.database import connect
from utils.logger import get_logger

logger = get_logger(__name__)

DDL = """
CREATE TABLE IF NOT EXISTS twse_holidays (
    holiday_date  DATE      PRIMARY KEY,
    holiday_name  TEXT      NOT NULL,
    source        TEXT      NOT NULL DEFAULT 'TWSE_API',
    year_roc      INTEGER   NOT NULL,
    ingested_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

# Verify the table shape after creation — guards against partial migrations
# from a previous failed run with an incompatible schema.
_EXPECTED_COLUMNS = {"holiday_date", "holiday_name", "source", "year_roc", "ingested_at"}


def run_migration() -> None:
    """Execute the migration and verify the resulting schema."""
    logger.info("migration_start", table="twse_holidays")

    with connect() as conn:
        conn.execute(DDL)
        logger.info("migration_ddl_executed")

        # Verify columns
        rows = conn.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'twse_holidays'
            """
        ).fetchall()
        actual = {r[0] for r in rows}

        missing = _EXPECTED_COLUMNS - actual
        if missing:
            logger.error(
                "migration_schema_mismatch",
                missing_columns=sorted(missing),
            )
            sys.exit(1)

        row_count = conn.execute(
            "SELECT COUNT(*) FROM twse_holidays"
        ).fetchone()[0]

    logger.info(
        "migration_complete",
        table="twse_holidays",
        columns=sorted(actual),
        existing_rows=row_count,
    )
    print(
        f"[OK] twse_holidays table ready — {row_count} existing rows, "
        f"columns: {sorted(actual)}"
    )


if __name__ == "__main__":
    run_migration()
