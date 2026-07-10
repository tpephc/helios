# tests/features/win_rate_21d/test_compute_sql_boundary.py
"""Static boundary tests for win_rate_21d compute SQL ownership."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from features.win_rate_21d import compute


assert compute.__file__ is not None
_COMPUTE_PATH = Path(compute.__file__)

_FORBIDDEN_AGGREGATION_PATTERNS = (
    r"\bCREATE\s+TABLE\b",
    r"\bCREATE\s+OR\s+REPLACE\s+TABLE\b",
    r"\bCREATE\s+VIEW\b",
    r"\bCREATE\s+OR\s+REPLACE\s+VIEW\b",
    r"\bALTER\b",
    r"\bDROP\b",
    r"\bINSERT\s+INTO\b",
    r"\bUPDATE\b",
    r"\bDELETE\s+FROM\b",
    r"\bMERGE\b",
    r"\bCOPY\b",
    r"\bEXPORT\b",
    r"\bATTACH\b",
    r"\bDETACH\b",
)


def _compute_ast() -> ast.Module:
    return ast.parse(_COMPUTE_PATH.read_text(encoding="utf-8"))


def test_median_query_has_no_persistent_side_effect_sql() -> None:
    """Aggregation SQL must remain read-only."""
    query = compute._SQL_MEDIAN_QUERY_TEMPLATE  # noqa: SLF001

    for pattern in _FORBIDDEN_AGGREGATION_PATTERNS:
        assert re.search(pattern, query, flags=re.IGNORECASE) is None, pattern


def test_attach_statement_is_read_only_lifecycle_sql() -> None:
    """Connection lifecycle SQL may attach, but only read-only."""
    stmt = compute._ATTACH_STATEMENT_TEMPLATE.upper()  # noqa: SLF001

    assert "ATTACH" in stmt
    assert "READ_ONLY" in stmt
    assert "READ_WRITE" not in stmt
    assert "DETACH" not in stmt


def test_compute_does_not_import_duckdb_writer() -> None:
    """Compute must not know about persistence writer symbols."""
    tree = _compute_ast()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "duckdb_writer" not in alias.name
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert "duckdb_writer" not in module


def test_compute_does_not_reference_duckdb_path_constant() -> None:
    """Compute must use context.duckdb_path, not constants.DUCKDB_PATH."""
    tree = _compute_ast()

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                assert alias.name != "DUCKDB_PATH"
        elif isinstance(node, ast.Name):
            assert node.id != "DUCKDB_PATH"
        elif isinstance(node, ast.Attribute):
            assert node.attr != "DUCKDB_PATH"
