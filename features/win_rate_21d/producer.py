# features/win_rate_21d/producer.py
"""win_rate_21d cross-sectional median producer.

Build strategy: one-shot full rebuild per invocation.
    Governed by SD-A2-3 (LOCKED at 40c0cd1).
    Incremental append is EXPLICITLY OUT OF SCOPE for Gate A2.
    Any function suggesting incremental semantics (``build_incremental``,
    ``build_since``, ``build_partial``, ``update``, ``patch``, ``merge_into``,
    ``append_new_dates``) is FORBIDDEN and enforced by
    tests/features/win_rate_21d/test_no_forbidden_names.py.

PR-1 intentionally does not implement:
    - median computation
    - DuckDB writes
    - fixture writer / ledger writer
    - manifest emission with real build-time values
    - environment canonicalization

Those land in later PRs per the Executable Governance Navigation Document
(docs/research/win_rate_21d_producer_build_readiness.md, commit a110500).

Context / Request separation (Issue D):
    ``ProducerContext`` holds environment-varying configuration (paths,
    target table names).  ``ProducerBuildRequest`` holds per-invocation
    build parameters (scope, embedded context).  Overrides on
    ``ProducerContext`` are permitted for testability only; governed
    builds MUST pass PF-B and manifest identity checks before their
    outputs can become canonical.  See ``ProducerContext`` docstring for
    the override contract.

PR-2A addition (Q-PR2A-alpha', additive-only per Q-PR2A-R1):
    ``build_full`` now invokes ``verify_rider_closing_checks_are_real``
    from ``pre_flight``, positioned AFTER the pre-existing
    ``BUILD_STRATEGY`` defensive guard and BEFORE the pre-existing
    ``NotImplementedError`` raise.  This ordering is deliberate:
        1. The ``BUILD_STRATEGY`` guard remains PR-1's first executable
           statement, preserving its locked role as the outermost
           runtime backstop.
        2. The safety gate is the first rider/build-readiness gate that
           runs once strategy is confirmed canonical.
        3. The ``NotImplementedError`` for the deferred producer body
           follows the gate, so PR-1's ``test_build_full_is_shell``
           still observes ``NotImplementedError`` (the gate raises
           ``PreFlightShellError``, which subclasses
           ``NotImplementedError`` per Q-PR2A-R5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from features.win_rate_21d.constants import (
    BUILD_STRATEGY,
    DUCKDB_PATH,
    PRODUCER_TABLE_NAME,
)
from features.win_rate_21d.pre_flight import (
    verify_rider_closing_checks_are_real,
)


@dataclass(frozen=True, slots=True)
class BuildScope:
    """Requested producer build date scope.

    Attributes:
        requested_start: Inclusive earliest trading date requested.
        requested_end: Inclusive latest trading date requested.

    Materialized scope may differ from requested (subject to PF-B1
    validation), but the requested scope is what the caller intended and
    what appears in the manifest ``build_scope`` block once implemented.
    """

    requested_start: date
    requested_end: date


@dataclass(frozen=True, slots=True, kw_only=True)
class ProducerContext:
    """Immutable runtime context for a producer invocation.

    Holds configuration that is stable across a build invocation but
    varies across environments (dev / CI / production nexus).

    Keyword-only construction:
        Fields are keyword-only.  Positional construction is forbidden
        to prevent silent bugs when future fields are added to this
        dataclass (positional callers would silently rebind values to
        the wrong fields).  All callers MUST use keyword arguments.

    Override contract:
        Overrides on ``duckdb_path`` and ``target_table`` are permitted
        for testability only (unit tests, dry-run harnesses, CI sandboxes).
        Governed builds MUST pass PF-B / manifest identity checks that
        assert the canonical SD-A2-2 values before any output can become
        canonical.  A non-canonical context that reaches build execution
        without such a check is a governance error.

        PR-1 does NOT enforce this contract at the type level; the
        producer body (later PR) is responsible for the check.  This
        docstring is the interim documentation of the invariant.
    """

    duckdb_path: str = DUCKDB_PATH
    target_table: str = PRODUCER_TABLE_NAME


@dataclass(frozen=True, slots=True, kw_only=True)
class ProducerBuildRequest:
    """Per-invocation build request.

    Contains parameters that vary per build within the same context.

    Keyword-only construction (consistent with ``ProducerContext``):
        Fields are keyword-only.  Positional construction is forbidden
        to prevent silent bugs when future fields are added (e.g.,
        ``build_id``, ``snapshot_id``, ``dry_run``, ``requested_by``).
    """

    scope: BuildScope
    context: ProducerContext = field(default_factory=ProducerContext)


def resolve_scope() -> BuildScope:
    """Resolve R8/R1-relevant scope plus W-1 trading-day buffer.

    TM-041 shell only.  Real implementation requires:
        - Access to the R8/R1 date range (upstream artifact),
        - Trading-calendar API access (deferred to SD-A2-6),
        - A defined buffer contract in code (spec §5.2, SD-A2-2).
    """
    raise NotImplementedError(
        "Scope resolver pending R8/R1 date-range access + trading calendar"
    )


def build_full(request: ProducerBuildRequest) -> None:
    """Run the one-shot full rebuild producer pipeline.

    TM-042 anchor:
        There is intentionally NO incremental build API in this module.
        There is intentionally NO ``build_since`` variant.
        There is intentionally NO resume-from-partial variant.

    Recovery from any partial state discards partial artifacts and
    re-runs the full pipeline (readiness document Section 4.4).
    """
    # Defensive governance guard.  Do NOT replace with assert:
    # assertions are removed under python -O and this is a
    # governance-critical check that must survive optimized execution.
    # The branch is a runtime backstop against constant modification
    # that bypasses the Literal type check (e.g., monkeypatching in
    # tests, typing.cast misuse, or a well-intentioned refactor that
    # widens the Literal annotation without updating this guard).
    if BUILD_STRATEGY != "one_shot_full_rebuild":
        raise RuntimeError(
            f"Unsupported build strategy: {BUILD_STRATEGY!r}. "
            "Only 'one_shot_full_rebuild' is permitted at Gate A2."
        )
    # PR-2A safety gate (Q-PR2A-alpha', additive-only):
    # Refuse to enter the producer body while any rider-closing PF-B
    # check is still shell.  ``PreFlightShellError`` subclasses
    # ``NotImplementedError`` (Q-PR2A-R5), so PR-1's contract that
    # ``build_full`` raises ``NotImplementedError`` in shell state is
    # preserved: PR-1 callers that catch ``NotImplementedError`` still
    # observe the shell failure; PR-2A callers may catch the narrower
    # ``PreFlightShellError`` type to distinguish "rider not closed"
    # from "producer body not yet implemented".
    verify_rider_closing_checks_are_real()
    raise NotImplementedError(
        "Producer full rebuild pending implementation "
        "(median computation + DuckDB write + manifest emission)"
    )