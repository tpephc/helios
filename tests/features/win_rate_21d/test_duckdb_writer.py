# tests/features/win_rate_21d/test_duckdb_writer.py
"""Behavioural tests for DuckDBWriter (PR-2B.1 [4/4]).

Covers writer-layer cases only. Producer-level end-to-end wiring is
covered by test_producer_wiring_e2e.py. SQL boundary invariants are
covered by test_duckdb_writer_sql_boundary.py.

Artifact frames are constructed via DuckDB in-memory rather than
hand-built with ``pa.table({...})``. The fixture constructs the
Arrow schema through DuckDB, making ``schema == schema`` equality
a meaningful regression check on the CTAS round-trip: any drift in
name / type / nullable between what the writer accepts as input and
what DuckDB persists is caught by the assertion.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pytest

from features.win_rate_21d.duckdb_writer import DuckDBWriter
from features.win_rate_21d.writer import BuildArtifact

_TEST_TARGET_TABLE = "test_win_rate_21d_writer_target"


def _to_arrow_table(result: Any) -> pa.Table:
    """Normalize a DuckDB ``.arrow()`` result to a ``pa.Table``.

    Older DuckDB builds return ``pa.RecordBatchReader``; newer builds
    return ``pa.Table`` directly. Both cases are covered.
    """
    return result.read_all() if hasattr(result, "read_all") else result


def _artifact_from_duckdb(sql: str) -> BuildArtifact:
    """Build a BuildArtifact via an isolated in-memory DuckDB connection.

    Uses ``duckdb.connect(':memory:')`` with an explicit context
    manager rather than the module-level default connection, keeping
    connection lifecycle observable and avoiding any shared state
    across tests.
    """
    with duckdb.connect(":memory:") as conn:
        frame = _to_arrow_table(conn.execute(sql).arrow())

    return BuildArtifact(
        table_name=_TEST_TARGET_TABLE,
        frame=frame,
        row_count=frame.num_rows,
        column_names=tuple(frame.column_names),
    )


def _artifact_nonempty() -> BuildArtifact:
    return _artifact_from_duckdb(
        """
        SELECT * FROM (
            VALUES
                (DATE '2020-01-02', CAST(NULL AS DOUBLE), CAST(0 AS BIGINT)),
                (DATE '2020-01-03', CAST(0.165 AS DOUBLE), CAST(30 AS BIGINT))
        ) AS t(date, median_daily_return, n_obs_cross_section)
        """
    )


def _artifact_empty() -> BuildArtifact:
    return _artifact_from_duckdb(
        """
        SELECT
            CAST(NULL AS DATE) AS date,
            CAST(NULL AS DOUBLE) AS median_daily_return,
            CAST(NULL AS BIGINT) AS n_obs_cross_section
        WHERE FALSE
        """
    )


def _read_target_table(path: Path, table_name: str) -> pa.Table:
    with duckdb.connect(str(path), read_only=True) as conn:
        return _to_arrow_table(conn.execute(f"SELECT * FROM {table_name}").arrow())


def test_write_full_normal_path(tmp_path: Path) -> None:
    db_path = tmp_path / "writer_normal.duckdb"
    writer = DuckDBWriter(duckdb_path=db_path, target_table=_TEST_TARGET_TABLE)
    artifact = _artifact_nonempty()

    writer.write_full(artifact)

    result = _read_target_table(db_path, _TEST_TARGET_TABLE)

    # Schema equality: names, types, and nullable metadata all match.
    assert result.schema == artifact.frame.schema

    # Content equality: writer did not permute, corrupt, or rewrite
    # values. Sort defensively; SQL row order without ORDER BY is not
    # contract.
    expected = artifact.frame.sort_by([("date", "ascending")])
    actual = result.sort_by([("date", "ascending")])
    assert actual.equals(expected)


def test_write_full_empty_path(tmp_path: Path) -> None:
    db_path = tmp_path / "writer_empty.duckdb"
    writer = DuckDBWriter(duckdb_path=db_path, target_table=_TEST_TARGET_TABLE)
    artifact = _artifact_empty()

    writer.write_full(artifact)  # must not raise

    result = _read_target_table(db_path, _TEST_TARGET_TABLE)
    assert result.num_rows == 0
    assert result.schema == artifact.frame.schema


def test_write_full_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "writer_idempotent.duckdb"
    writer = DuckDBWriter(duckdb_path=db_path, target_table=_TEST_TARGET_TABLE)
    artifact = _artifact_nonempty()

    writer.write_full(artifact)
    writer.write_full(artifact)  # must not raise

    result = _read_target_table(db_path, _TEST_TARGET_TABLE)

    # Content equality after repeat call: rules out corruption,
    # duplication, or NULL rewriting on the second write.
    assert result.schema == artifact.frame.schema
    expected = artifact.frame.sort_by([("date", "ascending")])
    actual = result.sort_by([("date", "ascending")])
    assert actual.equals(expected)


def test_write_full_releases_file_handle(tmp_path: Path) -> None:
    db_path = tmp_path / "writer_lifecycle.duckdb"
    writer = DuckDBWriter(duckdb_path=db_path, target_table=_TEST_TARGET_TABLE)
    artifact = _artifact_nonempty()

    writer.write_full(artifact)

    # Immediately reopen; must succeed with no file-handle conflict.
    with duckdb.connect(str(db_path), read_only=True) as conn:
        row_count = conn.execute(f"SELECT COUNT(*) FROM {_TEST_TARGET_TABLE}").fetchone()[0]
        assert row_count == artifact.row_count


_INVALID_IDENTIFIERS = [
    "bad.identifier",  # dot-qualified (potential schema.table probe)
    "foo bar",  # embedded whitespace
    '"quoted"',  # embedded double quotes
    "1table",  # starts with digit
    "",  # empty string
    "with-dash",  # embedded hyphen
    "foo;DROP TABLE t",  # SQL fragment
]


@pytest.mark.parametrize("invalid_identifier", _INVALID_IDENTIFIERS)
def test_write_full_rejects_invalid_identifier(tmp_path: Path, invalid_identifier: str) -> None:
    """Identifier validation is a pre-connection guard.

    Asserts the contract (rejection of invalid single-part identifiers),
    not the specific validation mechanism. Parametrization covers a
    representative set of invalid shapes; the contract is uniform
    ``ValueError`` before any connection is opened.
    """
    db_path = tmp_path / "writer_identifier.duckdb"
    writer = DuckDBWriter(duckdb_path=db_path, target_table=invalid_identifier)
    artifact = _artifact_nonempty()

    with pytest.raises(ValueError, match="single-part DuckDB identifier"):
        writer.write_full(artifact)

    # Pre-connection guard: DuckDB file must not have been created.
    assert not db_path.exists()
