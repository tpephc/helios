# features/win_rate_21d/duckdb_writer.py
"""Concrete DuckDB writer for win_rate_21d producer — v0.1.0.

Implements the ``Writer`` protocol from ``features/win_rate_21d/writer.py``
using ``CREATE OR REPLACE TABLE ... AS SELECT ... FROM arrow_binding``
against caller-supplied DuckDB path and target table identifier.

Governance:
    - closes D-PR2B.1-5 (concrete writer + SQL form + connection
      lifecycle + Arrow binding lifetime + empty artifact behaviour +
      identifier handling + transactionality limitation).
    - closes D-PR2B.1-6 (``_ShellWriter`` remains
      ``_BuildDependencies.writer`` default; this module does not
      alter that wiring).

Storage configuration is caller-owned: neither ``DUCKDB_PATH`` nor
``PRODUCER_TABLE_NAME`` is imported by this module. Callers pass both
values from a canonical configuration source (typically
``ProducerContext``) at writer construction time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import duckdb

from features.win_rate_21d.writer import BuildArtifact, Writer

__all__ = ["DuckDBWriter"]


# Implementation detail.
# Validation mechanism is intentionally not part of the governance contract.
_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


_SQL_TEMPLATE = """
CREATE OR REPLACE TABLE {target} AS
SELECT
    date,
    median_daily_return,
    n_obs_cross_section
FROM arrow_binding
"""


@dataclass(frozen=True, slots=True)
class DuckDBWriter(Writer):
    """Persist a ``BuildArtifact`` to DuckDB via full replacement.

    Explicit inheritance from ``Writer`` documents conformance to the
    writer protocol and allows static type checkers to verify that
    the ``write_full`` method signature is compatible with the
    protocol declaration in ``features/win_rate_21d/writer.py``.

    The writer is stateless beyond the injected storage configuration.
    Each call to ``write_full`` opens a fresh context-managed
    connection, registers the artifact's Arrow table, executes a
    single ``CREATE OR REPLACE TABLE`` DDL, and closes.

    Fields:
        duckdb_path: Filesystem path to the target DuckDB database.
            The file is created if absent. Governance-canonical value
            for production builds is ``constants.DUCKDB_PATH``, but
            the writer does not import that constant; the caller
            supplies the path.
        target_table: Single-part DuckDB identifier for the target
            table. Governance-canonical value for production builds
            is ``constants.PRODUCER_TABLE_NAME``, but the writer does
            not import that constant; the caller supplies the name.
    """

    duckdb_path: Path
    target_table: str

    def write_full(self, artifact: BuildArtifact) -> None:
        """Replace the target table with ``artifact.frame``.

        Empty artifacts (``row_count == 0``) are valid input and
        materialize a zero-row table with the three-column schema
        preserved. Empty-as-danger interpretation is a
        producer/orchestration-layer concern, not a writer concern.

        The writer does not verify ``artifact.table_name`` against
        ``self.target_table``. ``artifact.table_name`` is treated as
        informational metadata; identity consistency between artifact
        metadata and the configured storage target remains outside
        writer responsibility (D-PR2B.1-5 Non-goals).
        """
        if _IDENTIFIER_PATTERN.fullmatch(self.target_table) is None:
            raise ValueError(
                f"Invalid target_table: {self.target_table!r}.\n"
                "Expected a valid single-part DuckDB identifier."
            )

        sql = _SQL_TEMPLATE.format(target=self.target_table)

        with duckdb.connect(str(self.duckdb_path)) as conn:
            conn.register("arrow_binding", artifact.frame)
            conn.execute(sql)
