"""DI wiring integration test for the real DuckDBWriter.

PR-2B.1 [4/4] verifies that the concrete writer can be injected and
used with a real compute artifact.

This test intentionally does not invoke ``build_full()``. The PR-2A
safety gate rejects producer execution while PF-B1, PF-B2, and PF-B6
remain shell implementations. True gated producer end-to-end coverage
belongs to PR-2C when those rider-closing checks become real.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb

from features.win_rate_21d.compute import compute
from features.win_rate_21d.duckdb_writer import DuckDBWriter
from features.win_rate_21d.producer import (
    BuildScope,
    ProducerContext,
    _BuildDependencies,
)

_TEST_TARGET_TABLE = "test_win_rate_21d_wiring_output"


def test_real_writer_dependency_persists_real_compute_artifact(
    win_rate_21d_pit_db: Path,
) -> None:
    """Verify DI compatibility, metadata propagation, and persistence."""
    scope = BuildScope(
        requested_start=date(2020, 1, 2),
        requested_end=date(2020, 1, 6),
    )
    context = ProducerContext(
        duckdb_path=str(win_rate_21d_pit_db),
        target_table=_TEST_TARGET_TABLE,
    )
    writer = DuckDBWriter(
        duckdb_path=win_rate_21d_pit_db,
        target_table=context.target_table,
    )
    dependencies = _BuildDependencies(writer=writer)

    assert dependencies.writer is writer

    artifact = compute(scope, context)

    assert artifact.table_name == context.target_table
    assert artifact.row_count == 3

    dependencies.writer.write_full(artifact)

    with duckdb.connect(
        str(win_rate_21d_pit_db),
        read_only=True,
    ) as conn:
        row_count = conn.execute(f"SELECT COUNT(*) FROM {_TEST_TARGET_TABLE}").fetchone()[0]

    assert row_count == 3
    assert row_count == artifact.row_count
