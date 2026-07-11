# tests/features/win_rate_21d/test_duckdb_writer_sql_boundary.py
"""Static boundary tests for win_rate_21d DuckDBWriter SQL ownership."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from features.win_rate_21d import duckdb_writer

assert duckdb_writer.__file__ is not None
_WRITER_PATH = Path(duckdb_writer.__file__)


_FORBIDDEN_WRITER_PATTERNS = (
    r"\bINSERT\s+INTO\b",
    r"\bUPDATE\b",
    r"\bDELETE\s+FROM\b",
    r"\bDROP\b",
    r"\bALTER\b",
    r"\bTRUNCATE\b",
    r"\bMERGE\b",
    r"\bATTACH\b",
    r"\bDETACH\b",
)


_FORBIDDEN_STORAGE_CONSTANTS = frozenset({"DUCKDB_PATH", "PRODUCER_TABLE_NAME"})


def _writer_ast() -> ast.Module:
    return ast.parse(_WRITER_PATH.read_text(encoding="utf-8"))


def test_sql_template_uses_create_or_replace_table() -> None:
    """Writer DDL must be CREATE OR REPLACE TABLE (Q-PR2B-δ)."""
    query = duckdb_writer._SQL_TEMPLATE

    assert (
        re.search(
            r"\bCREATE\s+OR\s+REPLACE\s+TABLE\b",
            query,
            flags=re.IGNORECASE,
        )
        is not None
    )


def test_sql_template_uses_explicit_projection() -> None:
    """Writer must project the three governed columns by name."""
    query = duckdb_writer._SQL_TEMPLATE

    assert re.search(r"\bSELECT\s+\*", query, flags=re.IGNORECASE) is None

    for column in ("date", "median_daily_return", "n_obs_cross_section"):
        assert re.search(rf"\b{column}\b", query, flags=re.IGNORECASE) is not None, column


@pytest.mark.parametrize("pattern", _FORBIDDEN_WRITER_PATTERNS)
def test_sql_template_forbids_other_write_forms(pattern: str) -> None:
    """Writer SQL surface is limited to CREATE OR REPLACE TABLE."""
    query = duckdb_writer._SQL_TEMPLATE

    assert re.search(pattern, query, flags=re.IGNORECASE) is None, pattern


def test_duckdb_writer_does_not_reference_storage_constants() -> None:
    """Writer must not read storage config from module-level constants.

    Both DUCKDB_PATH and PRODUCER_TABLE_NAME are constructor-injected
    per D-PR2B.1-5 Z-amendment. AST scan covers:
      - ImportFrom aliases (``from ... import CONST [as X]``)
      - Bare Name references (``CONST``)
      - Attribute references (``constants.CONST``)
    """
    tree = _writer_ast()

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                assert alias.name not in _FORBIDDEN_STORAGE_CONSTANTS, (
                    f"duckdb_writer.py must not import {alias.name}"
                )
        elif isinstance(node, ast.Name):
            assert node.id not in _FORBIDDEN_STORAGE_CONSTANTS, (
                f"duckdb_writer.py must not reference {node.id} by name"
            )
        elif isinstance(node, ast.Attribute):
            assert node.attr not in _FORBIDDEN_STORAGE_CONSTANTS, (
                f"duckdb_writer.py must not reference constants.{node.attr} via attribute access"
            )
