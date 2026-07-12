# tests/features/win_rate_21d/test_producer_body.py
"""Tests for PR-2B producer body orchestration + DI seam.

Covers:
    D-PR2B-1.a: ``dependencies`` field on ``ProducerBuildRequest``,
        keyword-only, default constructs canonical shells + no-op hook.
    D-PR2B-3: compute produces ``BuildArtifact``; producer body passes
        it to writer.  No compute -> writer direct coupling.
    D-PR2B-4: no observable side effect before gate passes.  Gate
        failure produces zero writer invocations, zero body-enter
        observations, zero compute invocations.
    D-PR2B-5: body-enter is INDEPENDENTLY observable via hook.  Writer
        invocation is not treated as body-enter proxy.

Module-dependency remediation note:
    Post-remediation, ``BuildScope`` and ``ProducerContext`` live in
    ``build_types``.  This test file continues to import them from
    ``producer`` to exercise the re-export path (locking the API
    stability guarantee described in ``producer.__all__``).  Tests
    that need the canonical compute shell import it directly from
    ``compute`` (its true home) rather than through a producer-local
    alias, because there is no longer any such alias.

The gate-passes-then-writer-called-in-order invariants are covered by
``test_safety_gate.test_build_full_enters_body_after_gate``.  This
module focuses on complementary invariants that keep the two test
files orthogonal.
"""

from __future__ import annotations

from datetime import date

import pyarrow as pa
import pytest

from features.win_rate_21d import pre_flight as pf
from features.win_rate_21d.build_types import PreFlightContext
from features.win_rate_21d.compute import compute as canonical_compute
from features.win_rate_21d.constants import (
    DUCKDB_PATH,
    PRODUCER_TABLE_NAME,
)
from features.win_rate_21d.pre_flight import (
    PreFlightResult,
    PreFlightSeverity,
    PreFlightShellError,
)
from features.win_rate_21d.producer import (
    BuildScope,
    ProducerBuildRequest,
    ProducerContext,
    _BuildDependencies,
    _noop_body_enter_hook,
    _ShellWriter,
    build_full,
)
from features.win_rate_21d.writer import BuildArtifact


# ---------------------------------------------------------------------------
# Test fixtures / helpers
# ---------------------------------------------------------------------------


def _canonical_scope() -> BuildScope:
    return BuildScope(
        requested_start=date(2020, 1, 2),
        requested_end=date(2020, 1, 10),
    )


def _patch_gate_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace all rider-closing checks with real stubs."""

    def _real(context: PreFlightContext) -> PreFlightResult:
        return PreFlightResult(
            check_id="dummy",
            passed=True,
            severity=PreFlightSeverity.INFO,
            message="test-substituted real check",
        )

    monkeypatch.setattr(pf, "RIDER_CLOSING_CHECKS", (_real, _real, _real))


def _stub_artifact() -> BuildArtifact:
    """Minimum-viable ``BuildArtifact`` for orchestration tests.

    Uses an empty (0x0) ``pyarrow.Table`` because orchestration tests
    do not inspect frame contents; they only need a value that passes
    ``BuildArtifact.__post_init__`` invariants (D-PR2B.1-2).

    ``row_count`` and ``column_names`` are derived from the frame so
    this helper stays trivially consistent with the cross-validation
    invariants regardless of pyarrow's internal empty-table shape.
    """
    empty = pa.table({})
    return BuildArtifact(
        table_name="x",
        frame=empty,
        row_count=empty.num_rows,
        column_names=tuple(empty.column_names),
    )


# ---------------------------------------------------------------------------
# D-PR2B-1.a: dependencies field on ProducerBuildRequest
# ---------------------------------------------------------------------------


def test_request_default_dependencies_uses_canonical_shells() -> None:
    """Default dependencies wire canonical shells + no-op hook.

    The default compute is ``compute.compute`` (the shell in PR-2B),
    referenced by identity via the module-level import here.  A
    producer-local alias would obscure the fact that compute lives in
    ``compute.py``, not in ``producer.py``.
    """
    request = ProducerBuildRequest(scope=_canonical_scope())
    assert isinstance(request.dependencies.writer, _ShellWriter)
    assert request.dependencies.compute is canonical_compute
    assert request.dependencies.body_enter_hook is _noop_body_enter_hook


def test_request_accepts_explicit_dependencies() -> None:
    class _MyWriter:
        def write_full(self, artifact: BuildArtifact) -> None:
            return None

    def _my_compute(
        scope: BuildScope, context: ProducerContext
    ) -> BuildArtifact:
        return _stub_artifact()

    def _my_hook() -> None:
        return None

    deps = _BuildDependencies(
        writer=_MyWriter(),
        compute=_my_compute,
        body_enter_hook=_my_hook,
    )
    request = ProducerBuildRequest(
        scope=_canonical_scope(), dependencies=deps
    )
    assert request.dependencies is deps


def test_dependencies_is_frozen() -> None:
    """_BuildDependencies is a governance-controlled seam; frozen."""
    from dataclasses import FrozenInstanceError

    deps = _BuildDependencies()
    with pytest.raises(FrozenInstanceError):
        deps.writer = _ShellWriter()  # type: ignore[misc]


def test_dependencies_rejects_positional_construction() -> None:
    """Consistent with ProducerContext / ProducerBuildRequest."""
    with pytest.raises(TypeError):
        _BuildDependencies(  # type: ignore[misc]
            _ShellWriter(), canonical_compute, _noop_body_enter_hook
        )


def test_context_default_is_canonical() -> None:
    """Sanity: PR-1 canonical context defaults preserved."""
    request = ProducerBuildRequest(scope=_canonical_scope())
    assert request.context.duckdb_path == DUCKDB_PATH
    assert request.context.target_table == PRODUCER_TABLE_NAME


# ---------------------------------------------------------------------------
# D-PR2B-4: no observable side effect before gate passes
# ---------------------------------------------------------------------------


def test_gate_failure_produces_no_side_effect() -> None:
    """The hardest new invariant in PR-2B.

    When the rider-closing safety gate raises (default state: all
    three PR-1 shells are still shells), the producer body MUST NOT:
        - call body_enter_hook,
        - call compute,
        - call writer.write_full.

    Spies count invocations of all three; every count MUST be zero.
    """
    body_enter_count = 0
    compute_count = 0
    writer_count = 0

    def _hook() -> None:
        nonlocal body_enter_count
        body_enter_count += 1

    def _compute(
        scope: BuildScope, context: ProducerContext
    ) -> BuildArtifact:
        nonlocal compute_count
        compute_count += 1
        return _stub_artifact()

    class _CountingWriter:
        def write_full(self, artifact: BuildArtifact) -> None:
            nonlocal writer_count
            writer_count += 1

    deps = _BuildDependencies(
        writer=_CountingWriter(),
        compute=_compute,
        body_enter_hook=_hook,
    )
    request = ProducerBuildRequest(
        scope=_canonical_scope(), dependencies=deps
    )

    # Gate is closed in default state (PR-1 shells present).
    with pytest.raises(PreFlightShellError):
        build_full(request)

    assert body_enter_count == 0
    assert compute_count == 0
    assert writer_count == 0


def test_build_strategy_guard_failure_produces_no_side_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Extension of D-PR2B-4 to the BUILD_STRATEGY guard.

    If the outermost guard (which precedes the gate per Q-PR2A-alpha')
    fires, no downstream step MAY execute either.  Gate itself must
    also be untouched.
    """
    import features.win_rate_21d.producer as producer_mod

    monkeypatch.setattr(producer_mod, "BUILD_STRATEGY", "incremental_bad")

    body_enter_count = 0
    compute_count = 0
    writer_count = 0

    def _hook() -> None:
        nonlocal body_enter_count
        body_enter_count += 1

    def _compute(
        scope: BuildScope, context: ProducerContext
    ) -> BuildArtifact:
        nonlocal compute_count
        compute_count += 1
        return _stub_artifact()

    class _CountingWriter:
        def write_full(self, artifact: BuildArtifact) -> None:
            nonlocal writer_count
            writer_count += 1

    deps = _BuildDependencies(
        writer=_CountingWriter(),
        compute=_compute,
        body_enter_hook=_hook,
    )
    request = ProducerBuildRequest(
        scope=_canonical_scope(), dependencies=deps
    )

    with pytest.raises(RuntimeError):
        build_full(request)

    assert body_enter_count == 0
    assert compute_count == 0
    assert writer_count == 0


# ---------------------------------------------------------------------------
# D-PR2B-5: body-enter is INDEPENDENTLY observable
# ---------------------------------------------------------------------------


def test_body_enter_hook_fires_before_compute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The hook must fire strictly before compute.

    A shared call log records both events; the invariant is checked
    against the log rather than by exception plumbing.  This is the
    independence guarantee: even if compute raises, the hook has
    already fired and is observable.
    """
    _patch_gate_open(monkeypatch)

    call_log: list[str] = []

    def _hook() -> None:
        call_log.append("hook")

    def _compute(
        scope: BuildScope, context: ProducerContext
    ) -> BuildArtifact:
        call_log.append("compute")
        raise RuntimeError("compute failure to prove hook already fired")

    class _WriterNeverCalled:
        def write_full(self, artifact: BuildArtifact) -> None:
            call_log.append("write")

    deps = _BuildDependencies(
        writer=_WriterNeverCalled(),
        compute=_compute,
        body_enter_hook=_hook,
    )
    request = ProducerBuildRequest(
        scope=_canonical_scope(), dependencies=deps
    )

    with pytest.raises(RuntimeError, match="compute failure"):
        build_full(request)

    # Hook fired, compute fired, writer did NOT.  Ordering preserved.
    assert call_log == ["hook", "compute"]


def test_body_enter_hook_default_is_noop() -> None:
    """The canonical default is a named no-op function.

    Identity comparison (``is``) is used deliberately; equality on a
    plain function is object identity, so this is the same, but the
    identity form documents the intent.
    """
    request = ProducerBuildRequest(scope=_canonical_scope())
    assert request.dependencies.body_enter_hook is _noop_body_enter_hook
    # And it is callable with no arguments and returns None.
    assert _noop_body_enter_hook() is None


# ---------------------------------------------------------------------------
# D-PR2B-3: compute purity spy (compute must not touch writer)
# ---------------------------------------------------------------------------


def test_compute_receives_scope_and_context_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Compute is called with (scope, context), not the full request.

    Passing the full request would give compute access to the writer
    and defeat D-PR2B-3 compute/write separation at the signature
    level.  Compute's signature must be scope+context only.
    """
    _patch_gate_open(monkeypatch)

    received: list[tuple[object, ...]] = []

    def _spy_compute(
        scope: BuildScope, context: ProducerContext
    ) -> BuildArtifact:
        received.append((scope, context))
        return _stub_artifact()

    class _NullWriter:
        def write_full(self, artifact: BuildArtifact) -> None:
            return None

    scope = _canonical_scope()
    context = ProducerContext()
    deps = _BuildDependencies(
        writer=_NullWriter(),
        compute=_spy_compute,
        body_enter_hook=_noop_body_enter_hook,
    )
    request = ProducerBuildRequest(
        scope=scope, context=context, dependencies=deps
    )

    build_full(request)

    assert len(received) == 1
    seen_scope, seen_context = received[0]
    assert seen_scope is scope
    assert seen_context is context


def test_canonical_compute_raises_file_not_found_when_db_absent() -> None:
    """Canonical default compute is real and fails clearly without a DB."""
    context = ProducerContext(
        duckdb_path="/nonexistent/win_rate_21d_test.duckdb",
    )

    with pytest.raises(FileNotFoundError, match="DuckDB database not found"):
        canonical_compute(_canonical_scope(), context)


def test_shell_writer_write_full_raises_not_implemented() -> None:
    """The default writer is a shell.

    Concrete DuckDB writer is deferred out of PR-2B scope.
    """
    writer = _ShellWriter()
    artifact = _stub_artifact()
    with pytest.raises(NotImplementedError):
        writer.write_full(artifact)


# ---------------------------------------------------------------------------
# Module-dependency remediation guard (PR-2B blocking-issue fix)
# ---------------------------------------------------------------------------


def test_compute_module_does_not_import_producer() -> None:
    """Structural guard: compute.py must not depend on producer.py.

    A regression here would silently reintroduce the circular
    dependency that ``build_types`` was created to break.  Static AST
    scan is cheap and catches any future import of ``producer`` from
    ``compute`` (direct or ``from ... import ...``), including lazy
    imports inside function bodies -- which is deliberately in scope,
    since the whole point of this guard is to prevent the exact class
    of "make it work with a lazy import" workaround that the original
    review flagged.
    """
    import ast
    from pathlib import Path

    compute_path = (
        Path(__file__).resolve().parents[3]
        / "features"
        / "win_rate_21d"
        / "compute.py"
    )
    tree = ast.parse(compute_path.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.endswith("producer"), (
                    f"compute.py imports producer via `import "
                    f"{alias.name}` -- reintroduces circular dependency"
                )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert not module.endswith("producer"), (
                f"compute.py imports from {module!r} -- "
                "reintroduces circular dependency"
            )


def test_producer_reexports_moved_types() -> None:
    """API stability: BuildScope / ProducerContext remain importable
    from producer even though their definitions moved to build_types.

    The re-export is deliberate infrastructure; this test locks it so
    a future refactor cannot silently break every downstream caller.
    """
    from features.win_rate_21d import producer as producer_mod
    from features.win_rate_21d.build_types import (
        BuildScope as _canonical_build_scope,
    )
    from features.win_rate_21d.build_types import (
        ProducerContext as _canonical_producer_context,
    )

    # Identity check: producer.BuildScope MUST be the same object as
    # build_types.BuildScope (not a shadow, not a re-declaration).
    assert producer_mod.BuildScope is _canonical_build_scope
    assert producer_mod.ProducerContext is _canonical_producer_context
