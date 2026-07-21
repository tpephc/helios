# features/win_rate_21d/pre_flight.py
"""PF-B pre-flight framework for win_rate_21d.

PR-1 implements only checks that are fully evaluable from locked constants:

    PF-B3: MIN_CROSS_SECTION_OBS_PER_DATE consistency
    PF-B4: WINDOW / MIN_OBS consistency

Other PF-B checks are explicit shells that raise ``NotImplementedError``.
They MUST NOT return pass vacuously -- enforced by
tests/features/win_rate_21d/test_pre_flight_shell.py.

Governance source: SD-A2-3 LOCKED at 40c0cd1.

Severity model (Issue F):
    ``PreFlightResult.severity`` captures the graded outcome of a check.
    PR-1 uses ``INFO`` on pass and ``ERROR`` on fail.  Later PRs (in
    particular PF-L checks with non-fatal drift indicators such as
    Parquet ``recorded`` config differences) can emit ``WARNING`` without
    changing the dataclass shape.

PR-2A additions (additive-only, Q-PR2A-R1):
    - ``PreFlightShellError`` (subclass of ``NotImplementedError``,
      Q-PR2A-R5 refined): dedicated exception type raised by PR-1's
      shell PF-B functions AND by the rider-closing safety gate.  It
      is a subclass so PR-1's existing
      ``pytest.raises(NotImplementedError)`` contracts continue to
      hold unchanged.  It is a distinct type so the safety gate
      identifies shells precisely rather than mis-catching a bare
      ``NotImplementedError`` that a real implementation's internal
      helper might raise.  The PR-1 shell functions
      ``pf_b1_scope_check``, ``pf_b2_canonical_source_check``, and
      ``pf_b6_duckdb_writeability_check`` have their raise type
      narrowed to this subclass.  This is an additive-safe change
      (subtype narrowing preserves all existing catch clauses).
    - ``PreFlightCallable`` type alias for callables returning a
      ``PreFlightResult``.
    - ``ALL_PRE_FLIGHT_CHECKS`` (Q-PR2A-R6): tuple of every SD-A2-3
      PF-B check in canonical order.
    - ``RIDER_CLOSING_CHECKS`` (Q-PR2A-R6): tuple of the PF-B checks
      that are currently shell and gate SD-A2-1 rider closure
      (PF-B1, PF-B2, PF-B6).  PF-B3 and PF-B4 are excluded because they
      are already real in PR-1.
    - ``verify_rider_closing_checks_are_real`` (Q-PR2A-alpha'):
      probe each rider-closing check by invocation; aggregate any that
      raise ``PreFlightShellError`` and raise ``PreFlightShellError``
      naming all shells for progress observability.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Final

from features.win_rate_21d.build_types import PreFlightContext
from features.win_rate_21d.constants import (
    MIN_CROSS_SECTION_OBS_PER_DATE,
    MIN_OBS,
    WINDOW,
)


class PreFlightSeverity(str, Enum):
    """Severity level for a pre-flight check result.

    Values are strings so they serialize cleanly into manifest and log
    records without extra encoding.

    Semantic contract:
        - ``INFO``: check passed, no attention required.
        - ``WARNING``: check passed with an observation that should be
          reviewed but does not block the build.
        - ``ERROR``: check failed, build MUST NOT proceed.
    """

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class PreFlightResult:
    """Result of one pre-flight check.

    Attributes:
        check_id: Stable identifier used across logs and audit trails
            (e.g., ``"PF-B3"``).  Must match the identifier defined in
            SD-A2-3 or SD-A2-5.
        passed: Whether the check passed.  A passing result MAY still
            carry ``severity == WARNING``; a failing result MUST carry
            ``severity == ERROR``.
        severity: Graded outcome; see ``PreFlightSeverity``.
        message: Human-readable description of the result.  On failure,
            the message MUST include enough context to reproduce the
            failure without additional logging.
    """

    check_id: str
    passed: bool
    severity: PreFlightSeverity
    message: str


# ---------------------------------------------------------------------------
# PR-2A shell marker (Q-PR2A-R5, refined per PR-2A review Blocking Issue 1).
#
# Defined here (immediately after PreFlightResult) rather than at the
# bottom of the module so that PR-1 shell functions below can raise it
# directly.  This is additive: no PR-1 symbol is removed or modified in
# meaning; the shell functions have their raise type narrowed to this
# subclass so that the safety gate identifies "is shell" precisely,
# not "raises NotImplementedError".
# ---------------------------------------------------------------------------


class PreFlightShellError(NotImplementedError):
    """Raised by a pre-flight shell to signal "not yet implemented".

    Governance semantics (Q-PR2A-R5, refined):
        Subclasses ``NotImplementedError`` deliberately so PR-1's
        contract that shell PF-B checks raise ``NotImplementedError``
        (locked by
        ``test_pf_b_shells_do_not_pass_vacuously`` and
        ``test_build_full_is_shell``) continues to hold: any caller
        writing ``except NotImplementedError`` still catches this.

        Distinct from bare ``NotImplementedError`` so the rider-closing
        safety gate can identify shells precisely.  A real
        implementation whose internal helper happens to raise
        ``NotImplementedError`` would be misclassified as a shell by
        a bare ``except NotImplementedError`` gate; the narrower
        exception type prevents that misclassification.
    """


def pf_b1_scope_check(context: PreFlightContext) -> PreFlightResult:
    """PF-B1 requested-vs-materialized scope validation.

    Governance: SD-A2-3 defines this check as the SD-A2-1 rider closure
    gate for the DuckDB branch.  Materialized scope from
    ``listed_market_daily_price_adj`` must not materially broaden or
    shrink the requested scope.

    PR-1 status: shell.  Real implementation requires the scope resolver
    and the DuckDB read path, both landing in a later PR.

    PR-2C.0 status: still shell.  The ``context`` parameter is accepted
    per the D-PR2C-1 invocation model but is deliberately NOT inspected
    yet.  Inspecting it without implementing the check would risk a
    vacuous pass, which ``test_pre_flight_shell.py`` forbids.
    """
    raise PreFlightShellError(
        "PF-B1 pending scope resolver + DuckDB read path"
    )


def pf_b2_canonical_source_check(
    context: PreFlightContext,
) -> PreFlightResult:
    """PF-B2 canonical source validation.

    Governance: SD-A2-3 requires producer code reads only from the
    canonical PIT view.  Direct reads of the raw price table are
    FORBIDDEN and constitute a P0 lineage violation per spec §4.4.

    Mechanism: AST dual-layer structural verification (D-PR2C-3).
    Layer 1 prohibits the forbidden raw-table literal; Layer 2 verifies
    the canonical identifier reaches a governed execution sink through
    a supported local data-flow chain (D-PR2C-10 §5 P-1/P-2/P-3).

    Source resolution: ``importlib.util.find_spec`` at invocation time
    (D-PR2C-10 §11).  The governed module is
    ``features.win_rate_21d.compute``.

    Infrastructure failures (source not found, parse error) propagate
    as non-``PreFlightShellError`` exceptions (D-PR2C-3).

    Args:
        context: Immutable runtime carrier (D-PR2C-1).  Not inspected
            by this check; PF-B2's target is the governed module, not
            runtime state.
    """
    _ = context  # accepted per D-PR2C-1; not inspected by PF-B2

    from importlib.util import find_spec
    from pathlib import Path

    from features.win_rate_21d._pf_b2_analyzer import (
        GOVERNED_MODULE,
        AnalysisVerdict,
        analyze_source,
    )

    spec = find_spec(GOVERNED_MODULE)
    if spec is None:
        raise ModuleNotFoundError(
            f"unable to resolve governed module: {GOVERNED_MODULE}"
        )
    if spec.origin is None:
        raise FileNotFoundError(
            f"governed module has no source origin: {GOVERNED_MODULE}"
        )

    source_path = Path(spec.origin)
    if source_path.suffix != ".py":
        raise FileNotFoundError(
            f"governed module does not resolve to Python source: "
            f"{source_path}"
        )

    source_text = source_path.read_text(encoding="utf-8")
    result = analyze_source(
        source_text,
        source_identity=source_path.name,
    )

    if result.verdict is AnalysisVerdict.PASS:
        return PreFlightResult(
            check_id="PF-B2",
            passed=True,
            severity=PreFlightSeverity.INFO,
            message="canonical PIT source structurally verified",
        )

    detail = "; ".join(result.diagnostics) or "no diagnostic detail"
    return PreFlightResult(
        check_id="PF-B2",
        passed=False,
        severity=PreFlightSeverity.ERROR,
        message=detail,
    )


def pf_b3_min_cross_section_check(
    observed_value: int = MIN_CROSS_SECTION_OBS_PER_DATE,
) -> PreFlightResult:
    """PF-B3 MIN_CROSS_SECTION_OBS_PER_DATE consistency check.

    Verifies that the observed producer-side constant matches the
    SD-A2-1 locked value of 30.  The default argument is the constant
    imported from ``features.win_rate_21d.constants``; explicit values
    are accepted to allow testing of mismatch cases.
    """
    expected = 30
    if observed_value != expected:
        return PreFlightResult(
            check_id="PF-B3",
            passed=False,
            severity=PreFlightSeverity.ERROR,
            message=(
                "MIN_CROSS_SECTION_OBS_PER_DATE mismatch: "
                f"expected {expected}, observed {observed_value}"
            ),
        )
    return PreFlightResult(
        check_id="PF-B3",
        passed=True,
        severity=PreFlightSeverity.INFO,
        message=(
            "MIN_CROSS_SECTION_OBS_PER_DATE matches SD-A2-1 "
            f"(value={expected})"
        ),
    )


def pf_b4_window_constants_check(
    observed_window: int = WINDOW,
    observed_min_obs: int = MIN_OBS,
) -> PreFlightResult:
    """PF-B4 WINDOW / MIN_OBS consistency check.

    Verifies that the observed WINDOW and MIN_OBS constants match
    SPEC_LOCKED v0.1.0 §3.6 (WINDOW=21, MIN_OBS=15).  Both defaults are
    imported from ``features.win_rate_21d.constants``; explicit values
    are accepted to allow testing of mismatch cases.
    """
    expected_window = 21
    expected_min_obs = 15
    window_ok = observed_window == expected_window
    min_obs_ok = observed_min_obs == expected_min_obs
    if not (window_ok and min_obs_ok):
        return PreFlightResult(
            check_id="PF-B4",
            passed=False,
            severity=PreFlightSeverity.ERROR,
            message=(
                "WINDOW/MIN_OBS mismatch: "
                f"expected (WINDOW={expected_window}, "
                f"MIN_OBS={expected_min_obs}), "
                f"observed (WINDOW={observed_window}, "
                f"MIN_OBS={observed_min_obs})"
            ),
        )
    return PreFlightResult(
        check_id="PF-B4",
        passed=True,
        severity=PreFlightSeverity.INFO,
        message=(
            "WINDOW and MIN_OBS match SPEC_LOCKED v0.1.0 §3.6 "
            f"(WINDOW={expected_window}, MIN_OBS={expected_min_obs})"
        ),
    )


def pf_b6_duckdb_writeability_check(
    context: PreFlightContext,
) -> PreFlightResult:
    """PF-B6 DuckDB target writeability check.

    Governance: SD-A2-3 requires the DuckDB file to be writable and the
    target table name to be free of lock contention at build time.
    Does NOT perform trial writes (which would violate the "no side
    effects on pre-flight failure" contract).

    PR-1 status: shell.  Real implementation requires the DuckDB
    integration path in a later PR.

    PR-2C.0 status: still shell.  The ``context`` parameter is accepted
    per the D-PR2C-1 invocation model but is deliberately NOT inspected
    yet.  Inspecting it without implementing the check would risk a
    vacuous pass, which ``test_pre_flight_shell.py`` forbids.
    """
    raise PreFlightShellError(
        "PF-B6 pending DuckDB integration path"
    )

# ---------------------------------------------------------------------------
# PR-2A additions (additive-only per Q-PR2A-R1).
#
# The definitions below extend PR-1's PF-B framework with a
# rider-closing safety gate primitive.  They do not modify any PR-1
# symbol or behavior; they only add new module-level names and narrow
# PR-1 shell raise types to a subclass of NotImplementedError (see
# PreFlightShellError near the top of this module).
# ---------------------------------------------------------------------------


# Heterogeneous alias.  ALL_PRE_FLIGHT_CHECKS is NOT signature-uniform:
# PF-B3 and PF-B4 are parameterised by their observed constants (int
# arguments with defaults), while the rider-closing checks take a
# PreFlightContext (D-PR2C-1).  Annotating the general registry with the
# narrow PreFlightCallable would be a type-contract falsehood.  Migrating
# PF-B3 / PF-B4 to the context model is out of scope for PR-2C.0: they
# are already real and do not gate the SD-A2-1 rider.
AnyPreFlightCallable = Callable[..., PreFlightResult]


# Homogeneous alias: the canonical rider-closing invocation model.
# Governance: D-PR2C-1 (LOCKED).
PreFlightCallable = Callable[[PreFlightContext], PreFlightResult]


# Complete tuple of every SD-A2-3 PF-B check defined in PR-1, in
# canonical order.  This is the general registry; the rider-closing
# subset is defined below as ``RIDER_CLOSING_CHECKS``.
ALL_PRE_FLIGHT_CHECKS: Final[tuple[AnyPreFlightCallable, ...]] = (
    pf_b1_scope_check,
    pf_b2_canonical_source_check,
    pf_b3_min_cross_section_check,
    pf_b4_window_constants_check,
    pf_b6_duckdb_writeability_check,
)


# Subset of ``ALL_PRE_FLIGHT_CHECKS`` that must transition from shell to
# real before SD-A2-1 rider closure.  As of PR-2A, this is exactly the
# three PR-1 shells (PF-B1, PF-B2, PF-B6).  PF-B3 and PF-B4 are excluded
# because they are already real implementations in PR-1.
#
# Signature note (Q-PR2A-D2): RESOLVED by D-PR2C-1 (LOCKED).
#     Each callable now takes exactly one PreFlightContext.  The
#     functools.partial and (callable, args_provider) alternatives were
#     rejected on structural evidence -- see D-PR2C-1.  Tuple membership
#     and ordering are unchanged from PR-2A.
RIDER_CLOSING_CHECKS: Final[tuple[PreFlightCallable, ...]] = (
    pf_b1_scope_check,
    pf_b2_canonical_source_check,
    pf_b6_duckdb_writeability_check,
)


def verify_rider_closing_checks_are_real(
    context: PreFlightContext,
) -> None:
    """Raise ``PreFlightShellError`` if any rider-closing check is shell.

    The gate probes each rider-closing check by invocation and catches
    ``PreFlightShellError`` (not the broader ``NotImplementedError``).
    This narrowness is deliberate (Q-PR2A-R5, refined): shells signal
    "not implemented" via the dedicated ``PreFlightShellError``
    subclass, so a real implementation whose internal helper happens to
    raise a bare ``NotImplementedError`` will propagate that exception
    upward as an unexpected error rather than being misclassified as a
    shell.

    Diagnostic semantics (Q-PR2A-D1, aggregate):
        All rider-closing checks are probed.  The raised
        ``PreFlightShellError`` names every shell found, so rider
        progress can be observed at a glance rather than one shell at
        a time.  This departs from ``manifest.py::validate`` (which is
        fail-fast) because the governance question here is
        "how far is the rider from closing?", not "is there any
        violation?".

        Aggregation applies only to shell-state diagnostics.  Any
        exception other than ``PreFlightShellError`` (for example, a
        ``RuntimeError`` from a real check that encountered a data
        problem) propagates immediately and halts the probe --- it is
        neither aggregated nor suppressed.  This preserves the
        distinction between "check not yet implemented" (a governance
        state we report on) and "check ran and something went wrong"
        (an operational error the caller must see promptly).

    Scope boundary (D-PR2C-2):
        This function performs shell CLASSIFICATION only.  It invokes
        each check and DISCARDS the returned ``PreFlightResult``.  It
        does NOT inspect ``PreFlightResult.passed``: runtime pass/fail
        enforcement belongs exclusively to ``run_rider_closing_checks``.
        A check returning ``passed=False`` passes this gate silently and
        is caught by the executor.  That division is intentional and is
        locked by
        ``test_verify_ignores_failed_result_but_run_enforces_it``.

    Side effects: none other than the potential raise.

    Args:
        context: Immutable runtime carrier (D-PR2C-1) passed to every
            check.  Not inspected by this function.

    Raises:
        PreFlightShellError: if one or more checks in
            ``RIDER_CLOSING_CHECKS`` raise ``PreFlightShellError`` when
            invoked with ``context``.  The message names every shell
            check found, comma-separated, in canonical order.
    """
    shell_names: list[str] = []
    for check in RIDER_CLOSING_CHECKS:
        try:
            check(context)
        except PreFlightShellError:
            shell_names.append(check.__name__)
    if shell_names:
        raise PreFlightShellError(
            "rider-closing pre-flight checks are still shell: "
            + ", ".join(shell_names)
        )


class PreFlightExecutionError(RuntimeError):
    """Raised when a rider-closing pre-flight check returns passed=False.

    Governance: D-PR2C-2 (LOCKED); concrete contract settled at PR-2C.0
    implementation review.

    Inheritance (deliberate, safety-critical):
        Inherits ``RuntimeError``, matching the
        ``EnvironmentVerificationError`` precedent in
        ``features/win_rate_21d/environment.py``.

        It MUST NOT inherit ``NotImplementedError``.  Many PR-1 call
        sites catch ``NotImplementedError`` to tolerate shell state.  If
        a genuine pre-flight FAILURE were catchable by those clauses, a
        failed governance check could be silently swallowed by code that
        merely intended to tolerate an unimplemented one -- exactly the
        gate hole D-PR2C-2 exists to close.  ``PreFlightExecutionError``
        and ``PreFlightShellError`` are disjoint types; no ``except``
        clause catches both without naming both.

    Storage:
        ``results`` carries every ``PreFlightResult`` collected up to and
        including the first failure.  Under the fail-fast contract it is
        strictly shorter than the registry whenever a check other than
        the last one fails.  Results that were never computed MUST NOT be
        fabricated.

    Message derivation:
        Fail-fast guarantees the last collected result is the failing
        one, so the message is derived from ``results[-1]`` with no
        branching.  This class deliberately does NOT validate its input:
        D-PR2C-2 specifies only that the exception carries the collected
        results.  Constructor rejection semantics would create a public
        contract with no governance basis and would protect nothing --
        ``run_rider_closing_checks`` is the sole construction site and
        constructs only on failure.

    Not a dataclass:
        No exception in this repository is a dataclass; ``@dataclass``
        complicates ``BaseException.args`` and pickling for no benefit.
    """

    def __init__(self, results: tuple[PreFlightResult, ...]) -> None:
        stored = tuple(results)
        failure = stored[-1]
        super().__init__(
            "pre-flight execution failed at check "
            f"{len(stored)}: {failure.check_id}: {failure.message}"
        )
        self.results: tuple[PreFlightResult, ...] = stored


def run_rider_closing_checks(
    context: PreFlightContext,
) -> tuple[PreFlightResult, ...]:
    """Execute rider-closing pre-flight checks and enforce their results.

    Governance: D-PR2C-2 (LOCKED).

    Semantics:
        - Checks run sequentially in canonical ``RIDER_CLOSING_CHECKS``
          order.  Never concurrently: ordering is part of the contract
          and PF-B6 will touch DuckDB once implemented.
        - The same ``context`` instance is passed to every check.
        - Execution is FAIL-FAST.  The first result with
          ``passed is False`` aborts the run; subsequent checks are not
          invoked.  This is a build gate, not a governance survey: the
          aggregate-diagnostic rationale that justifies aggregation in
          ``verify_rider_closing_checks_are_real`` does not apply.
          Concretely, probing PF-B6 (DuckDB writeability) after PF-B1
          (scope) has already failed carries no diagnostic value and
          touches an external resource under a broken precondition.
        - Operational exceptions propagate unchanged and are NEVER
          reclassified as shell state nor wrapped in
          ``PreFlightExecutionError``.
        - ``PreFlightShellError`` also propagates unchanged.  In the
          canonical ``build_full`` ordering this executor runs only after
          the shell detector has passed, so a shell reaching here means
          the registry was bypassed -- a governance bug that must surface
          with its original type rather than be absorbed.

    Idempotence requirement (consequence of the two-gate ordering):
        In the canonical ``build_full`` ordering every rider-closing
        check is invoked twice per build: once by
        ``verify_rider_closing_checks_are_real`` (result discarded) and
        once here (result enforced).  Real PF-B implementations MUST
        therefore be side-effect-free and idempotent.  This elevates
        PF-B6's existing "does NOT perform trial writes" constraint from
        a stylistic note to a correctness precondition.

    Args:
        context: Immutable runtime carrier (D-PR2C-1).

    Returns:
        Every ``PreFlightResult`` in canonical order, when all pass.
        Retained for the PR-3 manifest audit trail.

    Raises:
        PreFlightExecutionError: if any check returns
            ``passed is False``.  Carries the results collected up to and
            including that failure.
    """
    collected: list[PreFlightResult] = []
    for check in RIDER_CLOSING_CHECKS:
        result = check(context)
        collected.append(result)
        if not result.passed:
            raise PreFlightExecutionError(tuple(collected))
    return tuple(collected)
