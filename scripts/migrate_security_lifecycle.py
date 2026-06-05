#!/usr/bin/env python3
# scripts/migrate_security_lifecycle.py
"""Migrate security_lifecycle table — v1.0.0.

Creates the security_lifecycle table in the Helios DuckDB instance if it
does not already exist.  Safe to run multiple times (idempotent).

Usage
-----
    python scripts/migrate_security_lifecycle.py [--db PATH] [--dry-run]

Authority: SPEC-P1-DATA-REMEDIATION-v1 § 4
"""

import argparse
import logging
import sys
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)

_DEFAULT_DB = "data/_storage/helios.duckdb"

_DDL = """
CREATE TABLE IF NOT EXISTS security_lifecycle (
    stock_id     TEXT      NOT NULL,
    listed_from  DATE      NOT NULL,
    listed_to    DATE,
    market       TEXT      NOT NULL,
    source_type  TEXT      NOT NULL,
    source_url   TEXT      NOT NULL,
    verified_at  TIMESTAMP,
    verified_by  TEXT,
    notes        TEXT,

    PRIMARY KEY (stock_id, listed_from),

    CHECK (listed_to IS NULL OR listed_from < listed_to),
    CHECK (market IN ('EMERGING', 'OTC', 'TWSE', 'TPEx'))
);
"""

_VALIDATE_SQL = """
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'security_lifecycle'
ORDER BY ordinal_position;
"""

_EXPECTED_COLUMNS = {
    "stock_id",
    "listed_from",
    "listed_to",
    "market",
    "source_type",
    "source_url",
    "verified_at",
    "verified_by",
    "notes",
}


def migrate(db_path: str, dry_run: bool = False) -> None:
    """Create security_lifecycle table and validate schema.

    Parameters
    ----------
    db_path:
        Path to the DuckDB file.
    dry_run:
        If True, print DDL without executing.
    """
    path = Path(db_path)
    if not path.exists():
        logger.error("DuckDB file not found: %s", db_path)
        sys.exit(1)

    if dry_run:
        print("--- DRY RUN: DDL that would be executed ---")
        print(_DDL)
        return

    logger.info("Connecting to %s", db_path)
    con = duckdb.connect(db_path)
    try:
        logger.info("Applying security_lifecycle DDL")
        con.execute(_DDL)
        _validate_schema(con)
        logger.info("Migration complete: security_lifecycle table ready")
    finally:
        con.close()


def _validate_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Verify all expected columns exist in security_lifecycle.

    Parameters
    ----------
    con:
        Open DuckDB connection.

    Raises
    ------
    RuntimeError
        If any expected column is missing.
    """
    rows = con.execute(_VALIDATE_SQL).fetchall()
    present = {row[0] for row in rows}
    missing = _EXPECTED_COLUMNS - present
    if missing:
        raise RuntimeError(
            f"security_lifecycle schema validation failed. "
            f"Missing columns: {sorted(missing)}"
        )
    logger.info(
        "Schema validation passed: %d columns present", len(present)
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create security_lifecycle table in Helios DuckDB."
    )
    parser.add_argument(
        "--db",
        default=_DEFAULT_DB,
        help=f"Path to DuckDB file (default: {_DEFAULT_DB})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print DDL without executing",
    )
    return parser


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = _build_parser().parse_args()
    migrate(db_path=args.db, dry_run=args.dry_run)
