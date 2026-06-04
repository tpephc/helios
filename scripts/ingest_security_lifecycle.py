#!/usr/bin/env python3
# scripts/ingest_security_lifecycle.py
"""Ingest security lifecycle seed — v0.1.1.

Step 1 of P1-DATA remediation: load the MOPS-verified seed dataset into
the ``security_lifecycle`` table in the Helios DuckDB.

Governance
----------
SPEC : docs/decision_records/p1_data_remediation_spec.md v1.0.0
Seed : data/reference/security_lifecycle_seed_v1.csv
       SHA-256: 6a0989936f2ab382b42a505d4cdd936a08a186709c11b1b29d74bb2647c4625a

Usage
-----
    uv run python scripts/ingest_security_lifecycle.py [--dry-run]

Options
-------
--dry-run   Validate and print rows without writing to the database.

Changelog
---------
v0.1.1  P0 fixes: explicit schema guard, transaction atomicity;
        P1: CSV header validation, seed version metadata in logs.
v0.1.0  Initial implementation.
"""

import argparse
import csv
import hashlib
import logging
import sys
from datetime import date
from pathlib import Path

import structlog

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = REPO_ROOT / "data" / "reference" / "security_lifecycle_seed_v1.csv"
EXPECTED_SHA256 = "6a0989936f2ab382b42a505d4cdd936a08a186709c11b1b29d74bb2647c4625a"
EXPECTED_ROW_COUNT = 18
SEED_VERSION = "v1"

# Required columns in the CSV header (before rename).
REQUIRED_CSV_COLUMNS = {
    "stock_id",
    "otc_first_date",
    "mainboard_date",
    "mainboard_type",
    "source_type",   # renamed to 'source' on insert
    "source_url",
    "verified_at",
    "verified_by",
    "notes",
}

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def verify_seed_sha256(path: Path) -> str:
    """Return hex digest and raise if it does not match EXPECTED_SHA256."""
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != EXPECTED_SHA256:
        raise ValueError(
            f"Seed SHA-256 mismatch.\n"
            f"  Expected : {EXPECTED_SHA256}\n"
            f"  Actual   : {digest}\n"
            "Seed file may have been modified after governance freeze."
        )
    return digest


def parse_seed(path: Path) -> list[dict]:
    """Parse and validate seed CSV rows.

    Applies column rename (source_type -> source) and converts empty
    strings to None for nullable fields.

    Returns
    -------
    list[dict]
        One dict per row, keys matching ``security_lifecycle`` column names.
    """
    rows: list[dict] = []

    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)

        # P1: fail-fast on CSV schema drift before touching any data rows.
        actual_columns = set(reader.fieldnames or [])
        missing = REQUIRED_CSV_COLUMNS - actual_columns
        if missing:
            raise ValueError(
                f"Seed CSV is missing required columns: {sorted(missing)}. "
                "CSV schema may have drifted from the expected seed format."
            )

        for lineno, raw in enumerate(reader, start=2):  # line 1 = header
            # Explicit column mapping — do not rely on automatic name matching.
            row: dict = {
                "stock_id":       raw["stock_id"].strip(),
                "otc_first_date": raw["otc_first_date"].strip() or None,
                "mainboard_date": raw["mainboard_date"].strip(),
                "mainboard_type": raw["mainboard_type"].strip(),
                "source":         raw["source_type"].strip(),   # rename
                "source_url":     raw["source_url"].strip() or None,
                "verified_at":    raw["verified_at"].strip(),
                "verified_by":    raw["verified_by"].strip(),
                "notes":          raw["notes"].strip() or None,
            }

            # Required field checks
            for field in ("stock_id", "mainboard_date", "mainboard_type",
                          "source", "verified_at", "verified_by"):
                if not row[field]:
                    raise ValueError(
                        f"Line {lineno}: required field '{field}' is empty "
                        f"(stock_id={row['stock_id']!r})"
                    )

            # Date order: otc_first_date < mainboard_date (where present)
            if row["otc_first_date"]:
                otc = date.fromisoformat(row["otc_first_date"])
                mb = date.fromisoformat(row["mainboard_date"])
                if otc >= mb:
                    raise ValueError(
                        f"Line {lineno}: otc_first_date ({otc}) >= "
                        f"mainboard_date ({mb}) for stock_id={row['stock_id']}"
                    )

            rows.append(row)

    if len(rows) != EXPECTED_ROW_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_ROW_COUNT} rows, got {len(rows)}. "
            "Seed file may have been modified after governance freeze."
        )

    return rows


# ---------------------------------------------------------------------------
# Database operations
# ---------------------------------------------------------------------------

# P0-1: explicit DDL — do not rely on init_schema() having run or being
# current. security_lifecycle was added in v0.1.20; older DBs may not have it.
_ENSURE_TABLE_SQL = """
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

_INSERT_SQL = """
    INSERT INTO security_lifecycle
        (stock_id, otc_first_date, mainboard_date, mainboard_type,
         source, source_url, verified_at, verified_by, notes)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def ingest(rows: list[dict], dry_run: bool) -> None:
    """Insert rows into ``security_lifecycle``.

    Raises on duplicate ``stock_id``.
    All inserts are wrapped in a single transaction — partial writes are
    not possible.
    """
    if dry_run:
        log.info("dry_run_rows", count=len(rows))
        for row in rows:
            log.info("dry_run_row", **row)
        return

    from data.database import connect

    with connect() as con:
        # P0-1: ensure table exists regardless of init_schema() state.
        con.execute(_ENSURE_TABLE_SQL)

        # Idempotency guard: re-ingest must be explicit, not silent.
        existing = con.execute(
            "SELECT COUNT(*) FROM security_lifecycle"
        ).fetchone()[0]
        if existing > 0:
            raise RuntimeError(
                f"security_lifecycle already contains {existing} rows. "
                "Re-ingest is not supported. Clear the table manually "
                "if a re-seed is intentional and governance-approved."
            )

        # P0-2: atomic transaction — all rows or none.
        con.execute("BEGIN")
        try:
            params = [
                [
                    row["stock_id"],
                    row["otc_first_date"],
                    row["mainboard_date"],
                    row["mainboard_type"],
                    row["source"],
                    row["source_url"],
                    row["verified_at"],
                    row["verified_by"],
                    row["notes"],
                ]
                for row in rows
            ]
            con.executemany(_INSERT_SQL, params)
            con.execute("COMMIT")
        except Exception:
            try:
                con.execute("ROLLBACK")
            except Exception:
                pass  # driver may have already rolled back
            raise

        final_count = con.execute(
            "SELECT COUNT(*) FROM security_lifecycle"
        ).fetchone()[0]

    if final_count != EXPECTED_ROW_COUNT:
        raise RuntimeError(
            f"Post-insert count mismatch: expected {EXPECTED_ROW_COUNT}, "
            f"got {final_count}."
        )

    log.info(
        "ingest_complete",
        rows_inserted=final_count,
        seed_version=SEED_VERSION,
        seed_sha256=EXPECTED_SHA256,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run seed ingest with optional dry-run mode."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print rows without writing to the database.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    # Step 1a: verify seed integrity
    log.info("verifying_seed_sha256", path=str(SEED_PATH))
    digest = verify_seed_sha256(SEED_PATH)
    log.info(
        "seed_sha256_verified",
        seed_version=SEED_VERSION,
        digest=digest,
    )

    # Step 1b: parse and validate rows
    rows = parse_seed(SEED_PATH)
    log.info("seed_parsed", row_count=len(rows))

    # Step 1c: ingest (or dry-run)
    ingest(rows, dry_run=args.dry_run)

    if args.dry_run:
        log.info("dry_run_complete_no_writes")
    else:
        log.info(
            "step1_complete",
            event="AC-1 prerequisite satisfied: 18 rows inserted",
        )


if __name__ == "__main__":
    main()
