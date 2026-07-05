# tests/features/win_rate_21d/test_producer_surface.py
"""Tests for the ``producer`` module's public surface.

PR-1 scope covers:
    - Keyword-only construction of ``ProducerContext`` (guard against
      accidental positional calls when future fields are added).
    - ``ProducerBuildRequest`` default construction accepts a scope and
      defaults to a canonical context.

Later PRs will add tests for the producer body (median computation,
DuckDB writes, manifest emission).  Those are intentionally out of scope
here; see ``tests/features/win_rate_21d/README.md``.
"""

from datetime import date

import pytest

from features.win_rate_21d.constants import (
    DUCKDB_PATH,
    PRODUCER_TABLE_NAME,
)
from features.win_rate_21d.producer import (
    BuildScope,
    ProducerBuildRequest,
    ProducerContext,
    build_full,
    resolve_scope,
)


# ─────────────────────────────────────────────────────────────
# ProducerContext keyword-only construction
# ─────────────────────────────────────────────────────────────


def test_producer_context_default_uses_canonical_values() -> None:
    """Default construction inherits SD-A2-2 canonical identity."""
    ctx = ProducerContext()
    assert ctx.duckdb_path == DUCKDB_PATH
    assert ctx.target_table == PRODUCER_TABLE_NAME


def test_producer_context_accepts_keyword_overrides() -> None:
    """Overrides are permitted for testability per the override contract."""
    ctx = ProducerContext(
        duckdb_path="tmp/test.duckdb",
        target_table="tmp_test_table",
    )
    assert ctx.duckdb_path == "tmp/test.duckdb"
    assert ctx.target_table == "tmp_test_table"


def test_producer_context_rejects_positional_construction() -> None:
    """Guard against silent misbinding when future fields are added.

    Keyword-only construction is enforced via ``kw_only=True`` on the
    dataclass.  Positional callers would silently rebind values to the
    wrong fields when the field order changes in a later PR; keyword-only
    makes that failure loud instead of silent.
    """
    with pytest.raises(TypeError):
        ProducerContext("tmp/test.duckdb", "tmp_test_table")  # type: ignore[misc]


# ─────────────────────────────────────────────────────────────
# ProducerBuildRequest construction
# ─────────────────────────────────────────────────────────────


def test_build_request_default_context_is_canonical() -> None:
    """Absent an explicit context, the request uses canonical defaults."""
    scope = BuildScope(
        requested_start=date(2020, 1, 2),
        requested_end=date(2020, 1, 10),
    )
    request = ProducerBuildRequest(scope=scope)
    assert request.context.duckdb_path == DUCKDB_PATH
    assert request.context.target_table == PRODUCER_TABLE_NAME


def test_build_request_accepts_explicit_context() -> None:
    """Explicit context is respected."""
    scope = BuildScope(
        requested_start=date(2020, 1, 2),
        requested_end=date(2020, 1, 10),
    )
    ctx = ProducerContext(
        duckdb_path="tmp/test.duckdb",
        target_table="tmp_test_table",
    )
    request = ProducerBuildRequest(scope=scope, context=ctx)
    assert request.context is ctx


def test_build_request_rejects_positional_construction() -> None:
    """Guard against silent misbinding when future fields are added.

    Consistent with ``ProducerContext``: keyword-only construction is
    enforced via ``kw_only=True``.  Future fields such as ``build_id``,
    ``snapshot_id``, ``dry_run``, or ``requested_by`` would silently
    rebind values under positional construction; keyword-only makes
    that failure loud instead of silent.
    """
    scope = BuildScope(
        requested_start=date(2020, 1, 2),
        requested_end=date(2020, 1, 10),
    )
    ctx = ProducerContext(
        duckdb_path="tmp/test.duckdb",
        target_table="tmp_test_table",
    )
    with pytest.raises(TypeError):
        ProducerBuildRequest(scope, ctx)  # type: ignore[misc]


# ─────────────────────────────────────────────────────────────
# Producer body shells
# ─────────────────────────────────────────────────────────────


def test_resolve_scope_is_shell() -> None:
    with pytest.raises(NotImplementedError):
        resolve_scope()


def test_build_full_is_shell() -> None:
    """PR-1: build_full is a shell that raises NotImplementedError.

    The build-strategy defensive guard runs before the shell raise; the
    guard passes because BUILD_STRATEGY == 'one_shot_full_rebuild', so
    execution reaches the NotImplementedError raise as expected.
    """
    scope = BuildScope(
        requested_start=date(2020, 1, 2),
        requested_end=date(2020, 1, 10),
    )
    request = ProducerBuildRequest(scope=scope)
    with pytest.raises(NotImplementedError):
        build_full(request)