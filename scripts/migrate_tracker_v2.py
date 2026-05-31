#!/usr/bin/env python3
# scripts/migrate_tracker_v2.py
"""Tracker Schema Migration — v1.1.0.

Applies the forward_return_observations schema v1 → v2 DDL.
Adds five new columns required by tracker v0.3.0.

This script is idempotent: if the columns already exist it reports them as
already present and exits cleanly.  Running it twice is safe.

Usage
-----
    # Schema changes only (referenced in runbook Phase D, Step D-2):
    uv run python scripts/migrate_tracker_v2.py --schema-only

    # Full dry-run migration (referenced in runbook Phase B):
    HELIOS_DB_PATH=data/helios_dryrun_YYYYMMDD.db \\
        uv run python scripts/migrate_tracker_v2.py

Notes
-----
- This script does NOT delete v1 rows.  Row deletion is a manual step in the
  runbook (Phase E) after the backup and count asserts pass.
- Column IF NOT EXISTS syntax varies by DB engine.  This script checks the
  existing columns via schema inspection and only issues ALTER TABLE for
  missing columns.
"""

from __future__ import annotations

import argparse
import sys

from data.database import connect


# New columns to add, in order.
# Each entry: (column_name, column_type, default_sql_literal | None).
# None means no DEFAULT clause (column accepts NULL on existing rows).
_V2_COLUMNS: list[tuple[str, str, str | None]] = [
    ("forced_resolved",    "BOOLEAN", "false"),
    ("imputed_exit",       "BOOLEAN", "false"),
    ("imputation_reason",  "VARCHAR", None),    # no default — NULL on existing rows
    ("entry_slippage_bps", "DOUBLE",  None),    # no default — NULL on existing rows
    ("cost_bps",           "DOUBLE",  None),    # no default — NULL on existing rows
]

_OBS_TABLE: str = "forward_return_observations"


def _get_existing_columns(conn) -> set[str]:
    """Return the set of column names currently in the observation table."""
    rows = conn.execute(f"PRAGMA table_info({_OBS_TABLE})").fetchall()
    return {r[1] for r in rows}


def apply_schema_migration(conn, *, verbose: bool = True) -> bool:
    """Add v2 columns to the observation table.

    Returns True if any columns were added, False if all already existed.
    Raises if the observation table does not exist.
    """
    existing = _get_existing_columns(conn)

    # Verify table exists (raises if not).
    if not existing:
        raise RuntimeError(
            f"Table '{_OBS_TABLE}' does not exist or has no columns.  "
            "Run forward_return_tracker.py once to bootstrap the schema."
        )

    added: list[str] = []
    skipped: list[str] = []

    for col_name, col_type, col_default in _V2_COLUMNS:
        if col_name in existing:
            skipped.append(col_name)
            continue

        if col_default is None:
            ddl = (
                f"ALTER TABLE {_OBS_TABLE} "
                f"ADD COLUMN {col_name} {col_type}"
            )
        else:
            ddl = (
                f"ALTER TABLE {_OBS_TABLE} "
                f"ADD COLUMN {col_name} {col_type} DEFAULT {col_default}"
            )

        conn.execute(ddl)
        added.append(col_name)

    # Defensive commit: safe whether connect() uses auto-commit or explicit
    # transaction.  If connect() already auto-commits, this is a no-op.
    # If connect() wraps an explicit transaction without committing on exit,
    # this ensures the DDL persists.  Verify data.database.connect() behaviour
    # if DDL changes do not appear after this script runs.
    if added:
        conn.commit()

    if verbose:
        if added:
            print(f"  Added columns   : {', '.join(added)}")
        if skipped:
            print(f"  Already present : {', '.join(skipped)}")

    return bool(added)


def verify_schema(conn) -> None:
    """Assert that all v2 columns are now present.  Raises on failure."""
    existing = _get_existing_columns(conn)
    missing = [c for c, _, _ in _V2_COLUMNS if c not in existing]
    if missing:
        raise RuntimeError(
            f"Schema verification failed.  Missing columns: {missing}"
        )
    print(f"  Schema verification PASS — all v2 columns present.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply forward_return_observations schema v1 → v2.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Schema-only (no row deletion):
  uv run python scripts/migrate_tracker_v2.py --schema-only

  # Against a dry-run copy:
  HELIOS_DB_PATH=data/helios_dryrun_20260531.db \\
      uv run python scripts/migrate_tracker_v2.py --schema-only
        """,
    )
    parser.add_argument(
        "--schema-only", action="store_true",
        help=(
            "Apply DDL changes only.  "
            "Does not delete v1 rows (row deletion is a manual runbook step)."
        ),
    )
    args = parser.parse_args()

    print("Tracker schema migration v1 → v2")
    print("=" * 48)

    with connect() as conn:
        print(f"  Table           : {_OBS_TABLE}")

        any_added = apply_schema_migration(conn, verbose=True)
        verify_schema(conn)

        if not any_added:
            print("  Nothing to do — schema already at v2.")
        else:
            print("  Migration complete.")

        if args.schema_only:
            print(
                "\n  --schema-only: row deletion skipped.\n"
                "  Proceed with runbook Assert D-1 (backup) and Assert D-3\n"
                "  (self-sufficiency) before deleting v1 rows manually."
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
