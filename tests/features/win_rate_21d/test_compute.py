# tests/features/win_rate_21d/test_compute.py
"""Tests for real win_rate_21d compute implementation."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pyarrow as pa
import pytest

from features.win_rate_21d.compute import compute
from features.win_rate_21d.constants import CANONICAL_PIT_VIEW_NAME
from features.win_rate_21d.producer import BuildScope, ProducerContext


def _scope() -> BuildScope:
    return BuildScope(
        requested_start=date(2020, 1, 2),
        requested_end=date(2020, 1, 6),
    )


@pytest.fixture()
def duckdb_path(tmp_path: Path) -> Path:
    db_path = tmp_path / "helios_test.duckdb"

    with duckdb.connect(str(db_path)) as conn:
        conn.execute(
            f"""
            CREATE TABLE {CANONICAL_PIT_VIEW_NAME} (
                stock_id VARCHAR,
                date DATE,
                adj_close DOUBLE
            )
            """
        )

        rows: list[tuple[str, str, float]] = []

        for i in range(1, 31):
            stock_id = f"S{i:03d}"
            rows.append((stock_id, "2020-01-02", 100.0))
            rows.append((stock_id, "2020-01-03", 101.0 + i))

        # Invalid current price on 2020-01-03; must be excluded.
        rows.append(("S031", "2020-01-02", 100.0))
        rows.append(("S031", "2020-01-03", 0.0))

        # Below-threshold date: only five valid returns.
        for i in range(1, 6):
            stock_id = f"S{i:03d}"
            rows.append((stock_id, "2020-01-06", 102.0 + i))

        conn.executemany(
            f"INSERT INTO {CANONICAL_PIT_VIEW_NAME} VALUES (?, ?, ?)",
            rows,
        )

    return db_path


def test_compute_raises_file_not_found_when_db_absent(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.duckdb"
    context = ProducerContext(duckdb_path=str(missing_path))

    with pytest.raises(FileNotFoundError, match="DuckDB database not found"):
        compute(_scope(), context)


def test_compute_returns_build_artifact_with_arrow_table(
    duckdb_path: Path,
) -> None:
    context = ProducerContext(
        duckdb_path=str(duckdb_path),
        target_table="test_target",
    )

    artifact = compute(_scope(), context)

    assert artifact.table_name == "test_target"
    assert isinstance(artifact.frame, pa.Table)
    assert artifact.row_count == artifact.frame.num_rows
    assert artifact.column_names == tuple(artifact.frame.column_names)
    assert artifact.column_names == (
        "date",
        "median_daily_return",
        "n_obs_cross_section",
    )


def test_compute_retains_dates_and_applies_null_threshold(
    duckdb_path: Path,
) -> None:
    context = ProducerContext(duckdb_path=str(duckdb_path))

    artifact = compute(_scope(), context)
    rows = artifact.frame.to_pylist()

    assert [row["date"].isoformat() for row in rows] == [
        "2020-01-02",
        "2020-01-03",
        "2020-01-06",
    ]

    by_date = {row["date"].isoformat(): row for row in rows}

    assert by_date["2020-01-02"]["n_obs_cross_section"] == 0
    assert by_date["2020-01-02"]["median_daily_return"] is None

    assert by_date["2020-01-03"]["n_obs_cross_section"] == 30
    assert by_date["2020-01-03"]["median_daily_return"] == pytest.approx(
        0.165
    )

    assert by_date["2020-01-06"]["n_obs_cross_section"] == 5
    assert by_date["2020-01-06"]["median_daily_return"] is None


def test_compute_empty_view_returns_empty_artifact(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.duckdb"

    with duckdb.connect(str(db_path)) as conn:
        conn.execute(
            f"""
            CREATE TABLE {CANONICAL_PIT_VIEW_NAME} (
                stock_id VARCHAR,
                date DATE,
                adj_close DOUBLE
            )
            """
        )

    context = ProducerContext(duckdb_path=str(db_path))

    artifact = compute(_scope(), context)

    assert artifact.row_count == 0
    assert artifact.column_names == (
        "date",
        "median_daily_return",
        "n_obs_cross_section",
    )
    assert artifact.frame.num_rows == 0
