# tests/features/win_rate_21d/test_safety_gate.py
"""Tests for the PR-2A rider-closing safety gate.

Verifies (Q-PR2A-alpha', Q-PR2A-R5, Q-PR2A-R6, Q-PR2A-D1):
    - ``PreFlightShellError`` subclasses ``NotImplementedError`` so
      PR-1's ``test_build_full_is_shell`` contract is preserved.
    - ``verify_rider_closing_checks_are_real`` raises
      ``PreFlightShellError`` when any rider-closing check is shell.
    - The raised error names every shell found (aggregate diagnostic).
    - The gate passes silently when all rider-closing checks are real.
    - ``build_full`` invokes the gate AFTER the ``BUILD_STRATEGY``
      guard, and the gate raises before any producer body runs.
    - ``RIDER_CLOSING_CHECKS`` is the correct PR-2A subset:
      ``{pf_b1, pf_b2, pf_b6}``; PF-B3 and PF-B4 are excluded
      because they are already real.

Test lifecycle notes:
    - PR-1's ``test_build_full_is_shell`` continues to PASS through
      PR-2A because ``PreFlightShellError`` is a subtype of
      ``NotImplementedError``.
    - When PR-2C replaces PF-B1 / PF-B2 / PF-B6 shells with real
      implementations, ``test_gate_raises_by_default`` in this file
      will fail: the gate will pass and ``build_full`` will proceed
      to the deferred ``NotImplementedError`` for the producer body.
      That failure is the correct signal that the rider is closer to
      closure and this test needs restructuring to monkeypatch one
      check back to shell.
"""

from __future__ import annotations

from datetime import date

import pytest

from features.win_rate_21d import pre_flight as pf
from features.win_rate_21d.pre_flight import (
    ALL_PRE_FLIGHT_CHECKS,
    PreFlightShellError,
    RIDER_CLOSING_CHECKS,
    PreFlightResult,
    PreFlightSeverity,
    pf_b1_scope_check,
    pf_b2_canonical_source_check,
    pf_b3_min_cross_section_check,
    pf_b4_window_constants_check,
    pf_b6_duckdb_writeability_check,
    verify_rider_closing_checks_are_real,
)
from features.win_rate_21d.producer import (
    BuildScope,
    ProducerBuildRequest,
    build_full,
)


# ---------------------------------------------------------------------------
# PreFlightShellError type invariants (Q-PR2A-R5)
# ---------------------------------------------------------------------------


def test_preflight_shell_error_is_not_implemented_subclass() -> None:
    """Q-PR2A-R5: subclassing preserves PR-1's raises(NotImplementedError)."""
    assert issubclass(PreFlightShellError, NotImplementedError)


def test_preflight_shell_error_is_catchable_as_not_implemented() -> None:
    """A caller writing ``except NotImplementedError`` catches the gate."""
    with pytest.raises(NotImplementedError):
        raise PreFlightShellError("test")


def test_preflight_shell_error_is_catchable_as_narrower_type() -> None:
    """A PR-2A caller can distinguish gate failure from body deferral."""
    with pytest.raises(PreFlightShellError):
        raise PreFlightShellError("test")


# ---------------------------------------------------------------------------
# Tuple contents (Q-PR2A-R6)
# ---------------------------------------------------------------------------


def test_all_pre_flight_checks_contains_five_pf_b_checks() -> None:
    """PR-1 defines exactly PF-B1, B2, B3, B4, B6.  PF-B5 is not a member."""
    assert ALL_PRE_FLIGHT_CHECKS == (
        pf_b1_scope_check,
        pf_b2_canonical_source_check,
        pf_b3_min_cross_section_check,
        pf_b4_window_constants_check,
        pf_b6_duckdb_writeability_check,
    )


def test_rider_closing_checks_excludes_pf_b3_and_pf_b4() -> None:
    """PF-B3 and PF-B4 are real in PR-1; the rider does not wait on them."""
    assert pf_b3_min_cross_section_check not in RIDER_CLOSING_CHECKS
    assert pf_b4_window_constants_check not in RIDER_CLOSING_CHECKS


def test_rider_closing_checks_content() -> None:
    """The gate probes exactly the three PR-1 shells."""
    assert RIDER_CLOSING_CHECKS == (
        pf_b1_scope_check,
        pf_b2_canonical_source_check,
        pf_b6_duckdb_writeability_check,
    )


def test_rider_closing_checks_is_subset_of_all() -> None:
    """Structural: every rider-closing check is a defined PF-B check."""
    assert set(RIDER_CLOSING_CHECKS).issubset(set(ALL_PRE_FLIGHT_CHECKS))


# ---------------------------------------------------------------------------
# Gate behavior (Q-PR2A-alpha', Q-PR2A-D1 aggregate)
# ---------------------------------------------------------------------------


def test_gate_raises_by_default() -> None:
    """All three PR-1 rider-closing checks are shells; gate MUST raise.

    PR-2C acceptance criterion: when this test fails because all shells
    have become real, restructure it to monkeypatch one check to shell
    and verify the gate still detects it.
    """
    with pytest.raises(PreFlightShellError):
        verify_rider_closing_checks_are_real()


def test_gate_error_names_all_shells() -> None:
    """Q-PR2A-D1 aggregate diagnostic: message names every shell found."""
    with pytest.raises(PreFlightShellError) as excinfo:
        verify_rider_closing_checks_are_real()
    msg = str(excinfo.value)
    for check in RIDER_CLOSING_CHECKS:
        assert check.__name__ in msg, (
            f"expected {check.__name__!r} in gate error message; "
            f"got {msg!r}"
        )


def test_gate_passes_when_all_rider_closing_are_real(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Substitute rider-closing tuple with real callables; gate MUST pass."""
    def _real() -> PreFlightResult:
        return PreFlightResult(
            check_id="dummy",
            passed=True,
            severity=PreFlightSeverity.INFO,
            message="test-substituted real check",
        )

    monkeypatch.setattr(pf, "RIDER_CLOSING_CHECKS", (_real, _real, _real))
    # Should not raise.
    verify_rider_closing_checks_are_real()


def test_gate_partial_real_still_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If ANY rider-closing check is shell, gate MUST raise.

    Two-thirds substitute to real, one remains shell (pf_b6).  Verifies
    the aggregate diagnostic mentions only the remaining shell.
    """
    def _real() -> PreFlightResult:
        return PreFlightResult(
            check_id="dummy",
            passed=True,
            severity=PreFlightSeverity.INFO,
            message="test-substituted real check",
        )

    monkeypatch.setattr(
        pf,
        "RIDER_CLOSING_CHECKS",
        (_real, _real, pf_b6_duckdb_writeability_check),
    )

    with pytest.raises(PreFlightShellError) as excinfo:
        verify_rider_closing_checks_are_real()
    msg = str(excinfo.value)
    assert "pf_b6" in msg
    # The two substitutes have __name__ == "_real"; verify only one shell
    # is reported so the aggregate is truthful, not padded.
    assert "pf_b1" not in msg
    assert "pf_b2" not in msg


def test_gate_does_not_swallow_bare_not_implemented_from_real_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PR-2A review Blocking Issue 1: the gate detects shells precisely.

    A "real" implementation whose internal helper raises bare
    ``NotImplementedError`` (for example, a partial refactor where a
    delegated computation is stubbed) MUST NOT be silently classified
    as a shell by the gate.  The gate catches ``PreFlightShellError``,
    not ``NotImplementedError``, so the bare exception propagates
    upward as an unexpected error --- which is exactly the desired
    behavior: it signals a governance-level implementation bug rather
    than being reported as "shell progress".
    """
    def _partial_real_that_leaks() -> PreFlightResult:
        # Simulates a real impl calling into an unfinished helper.
        raise NotImplementedError("some deferred helper")

    def _real() -> PreFlightResult:
        return PreFlightResult(
            check_id="dummy",
            passed=True,
            severity=PreFlightSeverity.INFO,
            message="test-substituted real check",
        )

    monkeypatch.setattr(
        pf,
        "RIDER_CLOSING_CHECKS",
        (_real, _real, _partial_real_that_leaks),
    )

    # The bare NotImplementedError propagates unwrapped.  It is NOT
    # a PreFlightShellError, so a PR-2A caller catching the narrower
    # type will correctly miss it and let it surface as a bug.
    with pytest.raises(NotImplementedError) as excinfo:
        verify_rider_closing_checks_are_real()
    assert not isinstance(excinfo.value, PreFlightShellError)
    assert "some deferred helper" in str(excinfo.value)


def test_gate_propagates_non_shell_exceptions_immediately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PR-2A review NB1: aggregation applies only to shell-state.

    When a rider-closing check raises anything other than
    ``PreFlightShellError`` (for example, a ``RuntimeError`` from a
    real check that encountered a data problem), the exception
    propagates immediately and halts the probe.  It is neither
    aggregated with any shell diagnostics that came before, nor
    suppressed to allow subsequent checks to run.

    This preserves the distinction between "check not yet implemented"
    (a governance state we report on via ``PreFlightShellError``) and
    "check ran and something went wrong" (an operational error the
    caller must see promptly, unwrapped).
    """
    class _DataError(RuntimeError):
        pass

    def _real_that_fails() -> PreFlightResult:
        raise _DataError("upstream table missing")

    def _shell_after() -> PreFlightResult:
        # This check should never be reached because the RuntimeError
        # above halts the probe.
        raise PreFlightShellError("should not be reached")

    monkeypatch.setattr(
        pf,
        "RIDER_CLOSING_CHECKS",
        (pf_b1_scope_check, _real_that_fails, _shell_after),
    )

    # RuntimeError propagates directly; it is NOT wrapped in
    # PreFlightShellError, NOT aggregated with pf_b1's shell status.
    with pytest.raises(_DataError) as excinfo:
        verify_rider_closing_checks_are_real()
    assert "upstream table missing" in str(excinfo.value)


# ---------------------------------------------------------------------------
# build_full integration (Q-PR2A-alpha')
# ---------------------------------------------------------------------------


def _canonical_request() -> ProducerBuildRequest:
    scope = BuildScope(
        requested_start=date(2020, 1, 2),
        requested_end=date(2020, 1, 10),
    )
    return ProducerBuildRequest(scope=scope)


def test_build_full_raises_preflight_shell_error_by_default() -> None:
    """The gate fires when ``build_full`` is called in the PR-2A shell state.

    This test is precisely paired with PR-1's ``test_build_full_is_shell``
    (which catches ``NotImplementedError`` and still passes because
    ``PreFlightShellError`` is a subclass).  Here we assert the narrower
    type explicitly.
    """
    with pytest.raises(PreFlightShellError):
        build_full(_canonical_request())


def test_build_full_gate_error_is_still_notimplementederror() -> None:
    """Regression guard for the Q-PR2A-R5 contract: PR-1 catches still work."""
    with pytest.raises(NotImplementedError):
        build_full(_canonical_request())


def test_build_full_enters_body_after_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PR-2B D-PR2B-5 restructure: gate -> body -> compute -> write.

    Post-restructure invariants (all three MUST hold):
        1. Body entered exactly once (via injected body_enter_hook
           counter -- independent of writer invocation per
           D-PR2B-5 body-enter observable ruling).
        2. Compute called exactly once with (request.scope,
           request.context) and returns the stub artifact.
        3. Writer.write_full called exactly once with the stub artifact
           produced by compute.

    Ordering assertion:
        body_enter -> compute -> write.  Recorded via a shared call
        log; ordering is verified against the log rather than by
        exception plumbing (which was the PR-2A pre-body proxy).

    D-PR2B-4 sibling ("no observable side effect before gate passes")
    is tested separately in ``test_producer_body`` -- keeping the
    two invariants in distinct tests prevents an accidental pass-by-
    coincidence when one gate is weakened.
    """
    from features.win_rate_21d.producer import (
        ProducerContext,
        _BuildDependencies,
    )
    from features.win_rate_21d.writer import BuildArtifact

    def _real() -> PreFlightResult:
        return PreFlightResult(
            check_id="dummy",
            passed=True,
            severity=PreFlightSeverity.INFO,
            message="test-substituted real check",
        )

    monkeypatch.setattr(pf, "RIDER_CLOSING_CHECKS", (_real, _real, _real))

    call_log: list[str] = []
    stub_artifact = BuildArtifact(
        table_name="test_target_table",
        frame=object(),
        row_count=0,
        column_names=(),
    )
    compute_calls: list[tuple[BuildScope, ProducerContext]] = []
    writer_calls: list[BuildArtifact] = []

    def _hook() -> None:
        call_log.append("body_enter")

    def _stub_compute(
        scope: BuildScope, context: ProducerContext
    ) -> BuildArtifact:
        call_log.append("compute")
        compute_calls.append((scope, context))
        return stub_artifact

    class _StubWriter:
        def write_full(self, artifact: BuildArtifact) -> None:
            call_log.append("write")
            writer_calls.append(artifact)

    scope = BuildScope(
        requested_start=date(2020, 1, 2),
        requested_end=date(2020, 1, 10),
    )
    context = ProducerContext()
    deps = _BuildDependencies(
        writer=_StubWriter(),
        compute=_stub_compute,
        body_enter_hook=_hook,
    )
    request = ProducerBuildRequest(
        scope=scope, context=context, dependencies=deps
    )

    # No exception expected: gate passes (patched), body runs to
    # completion via stubs, writer accepts the stub artifact.
    build_full(request)

    # (1) Body entered exactly once.
    assert call_log.count("body_enter") == 1

    # (2) Compute called exactly once with (scope, context).
    assert len(compute_calls) == 1
    assert compute_calls[0] == (scope, context)

    # (3) Writer called exactly once with the artifact from compute.
    assert len(writer_calls) == 1
    assert writer_calls[0] is stub_artifact

    # Ordering: body_enter -> compute -> write.
    assert call_log == ["body_enter", "compute", "write"]


def test_build_full_gate_runs_after_build_strategy_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Q-PR2A-alpha' ordering: ``BUILD_STRATEGY`` guard fires first.

    If ``BUILD_STRATEGY`` is corrupted to a non-canonical value,
    ``build_full`` must raise ``RuntimeError`` (from PR-1's guard),
    NOT ``PreFlightShellError`` (which would indicate the gate ran
    before the strategy check).
    """
    import features.win_rate_21d.producer as producer_mod

    monkeypatch.setattr(producer_mod, "BUILD_STRATEGY", "incremental_bad")

    with pytest.raises(RuntimeError) as excinfo:
        build_full(_canonical_request())
    # RuntimeError, but MUST NOT be PreFlightShellError (which is a
    # NotImplementedError subclass, not a RuntimeError subclass).  This
    # asserts the order rather than just the outermost type.
    assert not isinstance(excinfo.value, PreFlightShellError)
    assert "Unsupported build strategy" in str(excinfo.value)
