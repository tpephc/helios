#!/usr/bin/env python3
# scripts/seed_security_lifecycle.py
"""Seed security_lifecycle table — v1.0.1.

Loads security_lifecycle_seed_v1.csv into the security_lifecycle table.
For each of the 18 seed stocks, inserts exactly two lifecycle rows:

    EMERGING row: [otc_first_date, mainboard_date)
    TWSE row:     [mainboard_date, ∞)

All provenance fields are copied directly from the seed CSV row.
No provenance field is inferred, generated, or modified during ETL.

The operation is transactional and idempotent:
    BEGIN
    DELETE existing rows for all seed stock_ids
    INSERT 36 rows
    VALIDATE (PG-2, PG-2b, provenance, row count)
    COMMIT

Usage
-----
    python scripts/seed_security_lifecycle.py [--db PATH] [--seed PATH] [--dry-run]

Authority: SPEC-P1-DATA-REMEDIATION-v1 § 5
"""

import argparse
import logging
import sys
from pathlib import Path

import duckdb
import pandas as pd

logger = logging.getLogger(__name__)

_DEFAULT_DB = "data/_storage/helios.duckdb"
_DEFAULT_SEED = "data/reference/security_lifecycle_seed_v1.csv"

_REQUIRED_SEED_COLUMNS = {
    "stock_id",
    "otc_first_date",
    "mainboard_date",
    "mainboard_type",
    "source_type",
    "source_url",
    "verified_at",
    "verified_by",
    "notes",
}

# Overlap detection query: canonical ordering ensures each pair is
# evaluated exactly once.  NULL listed_to treated as DATE '9999-12-31'.
_OVERLAP_QUERY = """
SELECT a.stock_id
FROM security_lifecycle a
JOIN security_lifecycle b
  ON a.stock_id    = b.stock_id
 AND a.listed_from < b.listed_from
WHERE a.listed_from < COALESCE(b.listed_to, DATE '9999-12-31')
  AND b.listed_from < COALESCE(a.listed_to, DATE '9999-12-31')
"""

# INSERT uses positional placeholders (?) for executemany compatibility
# across DuckDB Python API versions.
# Column order: stock_id, listed_from, listed_to, market,
#               source_type, source_url, verified_at, verified_by, notes
_INSERT_SQL = """
INSERT INTO security_lifecycle (
    stock_id, listed_from, listed_to, market,
    source_type, source_url, verified_at, verified_by, notes
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _load_seed(seed_path: str) -> pd.DataFrame:
    """Load and validate seed CSV.

    Parameters
    ----------
    seed_path:
        Path to security_lifecycle_seed_v1.csv.

    Returns
    -------
    pd.DataFrame
        Validated seed dataframe.

    Raises
    ------
    SystemExit
        If file is missing or required columns are absent.
    """
    path = Path(seed_path)
    if not path.exists():
        logger.error("Seed file not found: %s", seed_path)
        sys.exit(1)

    df = pd.read_csv(seed_path, dtype=str)
    missing = _REQUIRED_SEED_COLUMNS - set(df.columns)
    if missing:
        logger.error("Seed CSV missing columns: %s", sorted(missing))
        sys.exit(1)

    # Strip whitespace; preserve NaN as None for nullable fields
    df = df.where(df.notna(), other=None)
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].str.strip() if df[col].notna().any() else df[col]

    logger.info("Loaded seed: %d stocks", len(df))
    return df


def _build_lifecycle_rows(seed: pd.DataFrame) -> list[tuple]:
    """Expand each seed row into two positional lifecycle tuples.

    Returns positional tuples rather than dicts to guarantee executemany
    compatibility across DuckDB Python API versions.  Tuple order matches
    _INSERT_SQL column order:
        stock_id, listed_from, listed_to, market,
        source_type, source_url, verified_at, verified_by, notes

    Parameters
    ----------
    seed:
        Validated seed dataframe.

    Returns
    -------
    list[tuple]
        36 tuples (2 per stock) ready for executemany insertion.
    """
    rows: list[tuple] = []
    for _, s in seed.iterrows():
        provenance = (
            s["source_type"],
            s["source_url"],
            s["verified_at"],
            s["verified_by"],
            s["notes"],
        )

        # EMERGING row: [otc_first_date, mainboard_date)
        rows.append(
            (s["stock_id"], s["otc_first_date"], s["mainboard_date"], "EMERGING")
            + provenance
        )

        # TWSE row: [mainboard_date, NULL)
        rows.append(
            (s["stock_id"], s["mainboard_date"], None, s["mainboard_type"])
            + provenance
        )

    return rows


def _validate_post_insert(
    con: duckdb.DuckDBPyConnection,
    stock_ids: list[str],
) -> None:
    """Run post-insert validation checks (PG-2, PG-2b, row count).

    Parameters
    ----------
    con:
        Open DuckDB connection (within transaction).
    stock_ids:
        List of seed stock_ids.

    Raises
    ------
    RuntimeError
        If any validation check fails.
    """
    n_stocks = len(stock_ids)
    expected_rows = n_stocks * 2

    # PG-2: exactly two rows per seed stock, with explicit missing-stock check
    rows_per_stock = con.execute(
        """
        SELECT stock_id, COUNT(*) AS n
        FROM security_lifecycle
        WHERE stock_id IN (SELECT UNNEST(?))
        GROUP BY stock_id
        """,
        [stock_ids],
    ).fetchall()

    present_ids = {sid for sid, _ in rows_per_stock}
    missing_ids = set(stock_ids) - present_ids
    if missing_ids:
        raise RuntimeError(
            f"PG-2 FAIL: stocks with zero rows (absent from table): "
            f"{sorted(missing_ids)}"
        )

    bad_counts = [(sid, n) for sid, n in rows_per_stock if n != 2]
    if bad_counts:
        raise RuntimeError(
            f"PG-2 FAIL: stocks with row count != 2: {bad_counts}"
        )

    total = sum(n for _, n in rows_per_stock)
    if total != expected_rows:
        raise RuntimeError(
            f"PG-2 FAIL: expected {expected_rows} rows, got {total}"
        )
    logger.info("PG-2 PASS: %d stocks × 2 rows = %d rows", n_stocks, total)

    # PG-2b: no interval overlap
    overlap_rows = con.execute(_OVERLAP_QUERY).fetchall()
    if overlap_rows:
        raise RuntimeError(
            f"PG-2b FAIL: interval overlap detected for: "
            f"{[r[0] for r in overlap_rows]}"
        )
    logger.info("PG-2b PASS: no interval overlap")

    # Provenance: source_type and source_url non-null for all inserted rows
    null_provenance = con.execute(
        """
        SELECT stock_id, listed_from
        FROM security_lifecycle
        WHERE stock_id IN (SELECT UNNEST(?))
          AND (source_type IS NULL OR source_url IS NULL)
        """,
        [stock_ids],
    ).fetchall()
    if null_provenance:
        raise RuntimeError(
            f"Provenance invariant FAIL: "
            f"null source_type/source_url for rows: {null_provenance}"
        )
    logger.info("Provenance invariant PASS")


def seed(
    db_path: str,
    seed_path: str,
    dry_run: bool = False,
) -> None:
    """Load seed CSV into security_lifecycle table.

    Parameters
    ----------
    db_path:
        Path to the DuckDB file.
    seed_path:
        Path to security_lifecycle_seed_v1.csv.
    dry_run:
        If True, print rows without writing to DB.
    """
    db = Path(db_path)
    if not db.exists():
        logger.error("DuckDB file not found: %s", db_path)
        sys.exit(1)

    seed_df = _load_seed(seed_path)
    stock_ids: list[str] = seed_df["stock_id"].tolist()
    lifecycle_rows = _build_lifecycle_rows(seed_df)

    if dry_run:
        print(f"--- DRY RUN: would insert {len(lifecycle_rows)} rows ---")
        for row in lifecycle_rows:
            print(row)
        return

    con = duckdb.connect(db_path)
    try:
        con.execute("BEGIN TRANSACTION")

        # Delete existing rows for seed stocks (idempotent re-run)
        deleted = con.execute(
            "DELETE FROM security_lifecycle WHERE stock_id IN (SELECT UNNEST(?))",
            [stock_ids],
        ).rowcount
        logger.info("Deleted %d existing lifecycle rows for seed stocks", deleted)

        # Insert 36 rows using positional placeholders
        con.executemany(_INSERT_SQL, lifecycle_rows)
        logger.info("Inserted %d lifecycle rows", len(lifecycle_rows))

        _validate_post_insert(con, stock_ids)

        con.execute("COMMIT")
        logger.info(
            "Seed complete: %d stocks, %d rows committed",
            len(stock_ids),
            len(lifecycle_rows),
        )

    except Exception:
        con.execute("ROLLBACK")
        logger.exception("Seed failed — transaction rolled back")
        raise
    finally:
        con.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Seed security_lifecycle table from CSV."
    )
    parser.add_argument(
        "--db",
        default=_DEFAULT_DB,
        help=f"Path to DuckDB file (default: {_DEFAULT_DB})",
    )
    parser.add_argument(
        "--seed",
        default=_DEFAULT_SEED,
        help=f"Path to seed CSV (default: {_DEFAULT_SEED})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print rows without writing to DB",
    )
    return parser


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = _build_parser().parse_args()
    seed(db_path=args.db, seed_path=args.seed, dry_run=args.dry_run)
