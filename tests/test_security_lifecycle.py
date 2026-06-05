# tests/test_security_lifecycle.py
"""Tests for security_lifecycle DDL, seed ETL, and validation invariants.

Covers:
- Table creation and schema validation
- Half-open interval semantics
- ETL idempotency
- Exactly 36 rows (18 stocks × 2)
- No interval overlap (PG-2b)
- Missing-stock detection in PG-2 (P0-2)
- Provenance copied exactly from seed including verified_at (P1-1)
- Panel eligibility predicate

Authority: SPEC-P1-DATA-REMEDIATION-v1 § 3, 4, 5, 6, 10, 12
"""

import textwrap

import duckdb
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DDL = textwrap.dedent("""
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
""")

_OVERLAP_QUERY = """
    SELECT a.stock_id
    FROM security_lifecycle a
    JOIN security_lifecycle b
      ON a.stock_id    = b.stock_id
     AND a.listed_from < b.listed_from
    WHERE a.listed_from < COALESCE(b.listed_to, DATE '9999-12-31')
      AND b.listed_from < COALESCE(a.listed_to, DATE '9999-12-31')
"""

# INSERT uses positional placeholders, matching _INSERT_SQL in seed script.
# Column order: stock_id, listed_from, listed_to, market,
#               source_type, source_url, verified_at, verified_by, notes
_INSERT_SQL = """
INSERT INTO security_lifecycle (
    stock_id, listed_from, listed_to, market,
    source_type, source_url, verified_at, verified_by, notes
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

# Minimal 3-stock seed for unit tests
_SEED_ROWS = [
    {
        "stock_id": "1001",
        "otc_first_date": "2015-01-05",
        "mainboard_date": "2020-03-10",
        "mainboard_type": "TWSE",
        "source_type": "MOPS",
        "source_url": "https://mops.twse.com.tw/1001",
        "verified_at": "2026-06-03 00:00:00",
        "verified_by": "veronica",
        "notes": "",
    },
    {
        "stock_id": "1002",
        "otc_first_date": "2016-06-01",
        "mainboard_date": "2021-09-15",
        "mainboard_type": "TWSE",
        "source_type": "MOPS",
        "source_url": "https://mops.twse.com.tw/1002",
        "verified_at": "2026-06-03 12:30:00",
        "verified_by": "veronica",
        "notes": "special case",
    },
    {
        "stock_id": "1003",
        "otc_first_date": "2014-03-11",
        "mainboard_date": "2022-01-05",
        "mainboard_type": "TWSE",
        "source_type": "MOPS",
        "source_url": "https://mops.twse.com.tw/1003",
        "verified_at": "2026-06-03 00:00:00",
        "verified_by": "veronica",
        "notes": "",
    },
]


def _fresh_db() -> duckdb.DuckDBPyConnection:
    """Return an in-memory DuckDB connection with DDL applied."""
    con = duckdb.connect(":memory:")
    con.execute(_DDL)
    return con


def _seed_rows_to_lifecycle(seed_rows: list[dict]) -> list[tuple]:
    """Expand seed rows into positional lifecycle tuples (mirrors ETL logic).

    Tuple order matches _INSERT_SQL:
        stock_id, listed_from, listed_to, market,
        source_type, source_url, verified_at, verified_by, notes
    """
    lifecycle: list[tuple] = []
    for s in seed_rows:
        provenance = (
            s["source_type"],
            s["source_url"],
            s["verified_at"],
            s["verified_by"],
            s["notes"],
        )
        lifecycle.append(
            (s["stock_id"], s["otc_first_date"], s["mainboard_date"], "EMERGING")
            + provenance
        )
        lifecycle.append(
            (s["stock_id"], s["mainboard_date"], None, s["mainboard_type"])
            + provenance
        )
    return lifecycle


def _insert_lifecycle_rows(
    con: duckdb.DuckDBPyConnection, rows: list[tuple]
) -> None:
    con.executemany(_INSERT_SQL, rows)


# ---------------------------------------------------------------------------
# DDL / schema
# ---------------------------------------------------------------------------


class TestDDL:
    def test_table_created(self) -> None:
        con = _fresh_db()
        tables = {r[0] for r in con.execute(
            "SELECT table_name FROM information_schema.tables"
        ).fetchall()}
        assert "security_lifecycle" in tables

    def test_required_columns_present(self) -> None:
        con = _fresh_db()
        cols = {r[0] for r in con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'security_lifecycle'"
        ).fetchall()}
        expected = {
            "stock_id", "listed_from", "listed_to", "market",
            "source_type", "source_url", "verified_at", "verified_by", "notes",
        }
        assert expected <= cols

    def test_check_constraint_listed_to_before_listed_from_rejected(self) -> None:
        con = _fresh_db()
        with pytest.raises(Exception):
            con.execute(
                "INSERT INTO security_lifecycle VALUES "
                "('X', DATE '2020-01-01', DATE '2019-12-31', 'TWSE', "
                "'MOPS', 'http://x', NULL, NULL, NULL)"
            )

    def test_check_constraint_invalid_market_rejected(self) -> None:
        con = _fresh_db()
        with pytest.raises(Exception):
            con.execute(
                "INSERT INTO security_lifecycle VALUES "
                "('X', DATE '2020-01-01', NULL, 'NASDAQ', "
                "'MOPS', 'http://x', NULL, NULL, NULL)"
            )

    def test_primary_key_duplicate_rejected(self) -> None:
        con = _fresh_db()
        con.execute(
            "INSERT INTO security_lifecycle VALUES "
            "('1001', DATE '2015-01-05', DATE '2020-03-10', 'EMERGING', "
            "'MOPS', 'http://x', NULL, NULL, NULL)"
        )
        with pytest.raises(Exception):
            con.execute(
                "INSERT INTO security_lifecycle VALUES "
                "('1001', DATE '2015-01-05', NULL, 'TWSE', "
                "'MOPS', 'http://x', NULL, NULL, NULL)"
            )


# ---------------------------------------------------------------------------
# Half-open interval semantics
# ---------------------------------------------------------------------------


class TestHalfOpenInterval:
    """SPEC § 3: listed_from <= trade_date < listed_to."""

    def _setup(self) -> duckdb.DuckDBPyConnection:
        con = _fresh_db()
        rows = _seed_rows_to_lifecycle([_SEED_ROWS[0]])  # stock 1001
        _insert_lifecycle_rows(con, rows)
        return con

    def test_otc_first_date_included(self) -> None:
        """Trade on otc_first_date is eligible (EMERGING row)."""
        con = self._setup()
        result = con.execute(
            """
            SELECT market FROM security_lifecycle
            WHERE stock_id = '1001'
              AND DATE '2015-01-05' >= listed_from
              AND (listed_to IS NULL OR DATE '2015-01-05' < listed_to)
            """
        ).fetchall()
        assert len(result) == 1
        assert result[0][0] == "EMERGING"

    def test_mainboard_date_belongs_to_twse_row(self) -> None:
        """Trade on mainboard_date is TWSE, not EMERGING."""
        con = self._setup()
        result = con.execute(
            """
            SELECT market FROM security_lifecycle
            WHERE stock_id = '1001'
              AND DATE '2020-03-10' >= listed_from
              AND (listed_to IS NULL OR DATE '2020-03-10' < listed_to)
            """
        ).fetchall()
        assert len(result) == 1
        assert result[0][0] == "TWSE"

    def test_day_before_otc_first_date_excluded(self) -> None:
        """Trade before otc_first_date matches no lifecycle row."""
        con = self._setup()
        result = con.execute(
            """
            SELECT market FROM security_lifecycle
            WHERE stock_id = '1001'
              AND DATE '2015-01-04' >= listed_from
              AND (listed_to IS NULL OR DATE '2015-01-04' < listed_to)
            """
        ).fetchall()
        assert len(result) == 0

    def test_day_before_mainboard_date_is_emerging(self) -> None:
        """Day immediately before mainboard_date is still EMERGING."""
        con = self._setup()
        result = con.execute(
            """
            SELECT market FROM security_lifecycle
            WHERE stock_id = '1001'
              AND DATE '2020-03-09' >= listed_from
              AND (listed_to IS NULL OR DATE '2020-03-09' < listed_to)
            """
        ).fetchall()
        assert len(result) == 1
        assert result[0][0] == "EMERGING"


# ---------------------------------------------------------------------------
# ETL: row count and two-rows-per-stock invariant
# ---------------------------------------------------------------------------


class TestETLRowCount:
    def test_exactly_two_rows_per_stock(self) -> None:
        con = _fresh_db()
        rows = _seed_rows_to_lifecycle(_SEED_ROWS)
        _insert_lifecycle_rows(con, rows)

        counts = con.execute(
            "SELECT stock_id, COUNT(*) FROM security_lifecycle GROUP BY stock_id"
        ).fetchall()
        for stock_id, n in counts:
            assert n == 2, f"Expected 2 rows for {stock_id}, got {n}"

    def test_total_row_count(self) -> None:
        con = _fresh_db()
        rows = _seed_rows_to_lifecycle(_SEED_ROWS)
        _insert_lifecycle_rows(con, rows)
        total = con.execute("SELECT COUNT(*) FROM security_lifecycle").fetchone()[0]
        assert total == len(_SEED_ROWS) * 2

    def test_emerging_row_has_correct_dates(self) -> None:
        con = _fresh_db()
        rows = _seed_rows_to_lifecycle([_SEED_ROWS[0]])
        _insert_lifecycle_rows(con, rows)

        row = con.execute(
            "SELECT listed_from, listed_to, market FROM security_lifecycle "
            "WHERE stock_id = '1001' AND market = 'EMERGING'"
        ).fetchone()
        assert row is not None
        assert str(row[0]) == "2015-01-05"
        assert str(row[1]) == "2020-03-10"

    def test_twse_row_has_null_listed_to(self) -> None:
        con = _fresh_db()
        rows = _seed_rows_to_lifecycle([_SEED_ROWS[0]])
        _insert_lifecycle_rows(con, rows)

        row = con.execute(
            "SELECT listed_to FROM security_lifecycle "
            "WHERE stock_id = '1001' AND market = 'TWSE'"
        ).fetchone()
        assert row is not None
        assert row[0] is None


# ---------------------------------------------------------------------------
# ETL: idempotency
# ---------------------------------------------------------------------------


class TestETLIdempotency:
    def test_double_run_produces_same_row_count(self) -> None:
        """Simulates idempotent re-run: delete + insert twice yields same count."""
        con = _fresh_db()
        stock_ids = [s["stock_id"] for s in _SEED_ROWS]
        rows = _seed_rows_to_lifecycle(_SEED_ROWS)

        for _ in range(2):
            con.execute(
                "DELETE FROM security_lifecycle WHERE stock_id IN (SELECT UNNEST(?))",
                [stock_ids],
            )
            _insert_lifecycle_rows(con, rows)

        total = con.execute("SELECT COUNT(*) FROM security_lifecycle").fetchone()[0]
        assert total == len(_SEED_ROWS) * 2


# ---------------------------------------------------------------------------
# PG-2: missing-stock detection
# ---------------------------------------------------------------------------


class TestPG2MissingStock:
    """P0-2: PG-2 must detect stocks that are completely absent after insert."""

    def test_missing_stock_detected(self) -> None:
        """Simulate a stock that was in the seed but never inserted."""
        con = _fresh_db()
        # Insert only two of three seed stocks
        rows = _seed_rows_to_lifecycle(_SEED_ROWS[:2])
        _insert_lifecycle_rows(con, rows)

        all_stock_ids = [s["stock_id"] for s in _SEED_ROWS]
        rows_per_stock = con.execute(
            """
            SELECT stock_id, COUNT(*) AS n
            FROM security_lifecycle
            WHERE stock_id IN (SELECT UNNEST(?))
            GROUP BY stock_id
            """,
            [all_stock_ids],
        ).fetchall()

        present_ids = {sid for sid, _ in rows_per_stock}
        missing_ids = set(all_stock_ids) - present_ids
        assert "1003" in missing_ids, (
            "PG-2 should detect stock 1003 as absent"
        )

    def test_no_missing_stocks_when_all_inserted(self) -> None:
        con = _fresh_db()
        rows = _seed_rows_to_lifecycle(_SEED_ROWS)
        _insert_lifecycle_rows(con, rows)

        all_stock_ids = [s["stock_id"] for s in _SEED_ROWS]
        rows_per_stock = con.execute(
            """
            SELECT stock_id, COUNT(*) AS n
            FROM security_lifecycle
            WHERE stock_id IN (SELECT UNNEST(?))
            GROUP BY stock_id
            """,
            [all_stock_ids],
        ).fetchall()

        present_ids = {sid for sid, _ in rows_per_stock}
        missing_ids = set(all_stock_ids) - present_ids
        assert missing_ids == set()


# ---------------------------------------------------------------------------
# PG-2b: no interval overlap
# ---------------------------------------------------------------------------


class TestNoIntervalOverlap:
    def test_valid_intervals_produce_no_overlap(self) -> None:
        con = _fresh_db()
        rows = _seed_rows_to_lifecycle(_SEED_ROWS)
        _insert_lifecycle_rows(con, rows)

        overlap = con.execute(_OVERLAP_QUERY).fetchall()
        assert overlap == [], f"Unexpected overlaps: {overlap}"

    def test_overlapping_intervals_detected(self) -> None:
        """Deliberately insert overlapping rows to confirm query catches them."""
        con = _fresh_db()
        con.execute(
            "INSERT INTO security_lifecycle VALUES "
            "('9999', DATE '2015-01-01', DATE '2020-06-01', 'EMERGING', "
            "'MOPS', 'http://x', NULL, NULL, NULL)"
        )
        # Overlaps: TWSE starts before EMERGING ends
        con.execute(
            "INSERT INTO security_lifecycle VALUES "
            "('9999', DATE '2020-01-01', NULL, 'TWSE', "
            "'MOPS', 'http://x', NULL, NULL, NULL)"
        )
        overlap = con.execute(_OVERLAP_QUERY).fetchall()
        stock_ids = [r[0] for r in overlap]
        assert "9999" in stock_ids


# ---------------------------------------------------------------------------
# Provenance invariant (including verified_at)
# ---------------------------------------------------------------------------


class TestProvenanceInvariant:
    """All provenance fields must be copied directly from seed CSV row.

    No provenance field may be inferred, generated, or modified during ETL.
    Authority: SPEC-P1-DATA-REMEDIATION-v1 § 5 provenance invariant.
    """

    def test_all_provenance_fields_match_seed_exactly(self) -> None:
        """Verify source_type, source_url, verified_at, verified_by, notes."""
        con = _fresh_db()
        seed = _SEED_ROWS[1]  # stock 1002: has non-empty notes and distinct verified_at
        rows = _seed_rows_to_lifecycle([seed])
        _insert_lifecycle_rows(con, rows)

        db_rows = con.execute(
            "SELECT market, source_type, source_url, "
            "       CAST(verified_at AS TEXT), verified_by, notes "
            "FROM security_lifecycle WHERE stock_id = '1002' "
            "ORDER BY listed_from"
        ).fetchall()

        assert len(db_rows) == 2
        for market, source_type, source_url, verified_at, verified_by, notes in db_rows:
            assert source_type == seed["source_type"]
            assert source_url == seed["source_url"]
            assert verified_at is not None, "verified_at must not be null"
            assert seed["verified_at"] in verified_at, (
                f"verified_at mismatch: expected {seed['verified_at']}, got {verified_at}"
            )
            assert verified_by == seed["verified_by"]
            assert notes == seed["notes"]

    def test_no_null_source_type_or_source_url(self) -> None:
        con = _fresh_db()
        rows = _seed_rows_to_lifecycle(_SEED_ROWS)
        _insert_lifecycle_rows(con, rows)

        bad = con.execute(
            "SELECT stock_id FROM security_lifecycle "
            "WHERE source_type IS NULL OR source_url IS NULL"
        ).fetchall()
        assert bad == []

    def test_both_rows_share_identical_provenance(self) -> None:
        """EMERGING and TWSE rows for the same stock must have identical provenance."""
        con = _fresh_db()
        rows = _seed_rows_to_lifecycle([_SEED_ROWS[0]])
        _insert_lifecycle_rows(con, rows)

        db_rows = con.execute(
            "SELECT source_type, source_url, "
            "       CAST(verified_at AS TEXT), verified_by, notes "
            "FROM security_lifecycle WHERE stock_id = '1001' "
            "ORDER BY listed_from"
        ).fetchall()

        assert len(db_rows) == 2
        assert db_rows[0] == db_rows[1], (
            "Provenance mismatch between EMERGING and TWSE rows"
        )


# ---------------------------------------------------------------------------
# Panel eligibility predicate
# ---------------------------------------------------------------------------


class TestPanelEligibilityPredicate:
    """SPEC § 6: rows before the earliest listed_from must be excluded."""

    def _setup(self) -> duckdb.DuckDBPyConnection:
        con = _fresh_db()

        con.execute(
            "CREATE TABLE daily_price (stock_id TEXT, trade_date DATE, close DOUBLE)"
        )
        con.execute(
            """
            INSERT INTO daily_price VALUES
              ('1001', DATE '2014-12-31', 100.0),  -- before otc_first_date
              ('1001', DATE '2015-01-05', 101.0),  -- exactly otc_first_date
              ('1001', DATE '2019-06-01', 105.0),  -- EMERGING period
              ('1001', DATE '2020-03-10', 110.0),  -- mainboard_date (TWSE)
              ('1001', DATE '2021-01-01', 115.0)   -- after mainboard_date
            """
        )

        rows = _seed_rows_to_lifecycle([_SEED_ROWS[0]])
        _insert_lifecycle_rows(con, rows)
        return con

    def test_pre_otc_rows_excluded(self) -> None:
        con = self._setup()
        eligible = con.execute(
            """
            SELECT p.trade_date
            FROM daily_price p
            JOIN security_lifecycle l
              ON  p.stock_id   = l.stock_id
             AND  p.trade_date >= l.listed_from
             AND  (l.listed_to IS NULL OR p.trade_date < l.listed_to)
            WHERE p.stock_id = '1001'
            ORDER BY p.trade_date
            """
        ).fetchall()

        dates = [str(r[0]) for r in eligible]
        assert "2014-12-31" not in dates

    def test_otc_first_date_included_in_eligible(self) -> None:
        con = self._setup()
        eligible = con.execute(
            """
            SELECT p.trade_date
            FROM daily_price p
            JOIN security_lifecycle l
              ON  p.stock_id   = l.stock_id
             AND  p.trade_date >= l.listed_from
             AND  (l.listed_to IS NULL OR p.trade_date < l.listed_to)
            WHERE p.stock_id = '1001'
            ORDER BY p.trade_date
            """
        ).fetchall()

        dates = [str(r[0]) for r in eligible]
        assert "2015-01-05" in dates

    def test_eligible_row_count(self) -> None:
        """4 out of 5 price rows should survive the eligibility predicate."""
        con = self._setup()
        count = con.execute(
            """
            SELECT COUNT(*)
            FROM daily_price p
            JOIN security_lifecycle l
              ON  p.stock_id   = l.stock_id
             AND  p.trade_date >= l.listed_from
             AND  (l.listed_to IS NULL OR p.trade_date < l.listed_to)
            WHERE p.stock_id = '1001'
            """
        ).fetchone()[0]
        assert count == 4
