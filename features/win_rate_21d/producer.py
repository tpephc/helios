# features/win_rate_21d/producer.py
"""win_rate_21d cross-sectional median producer.

Build strategy: one-shot full rebuild per invocation.
    Governed by SD-A2-3 (LOCKED at 40c0cd1).
    Incremental append is EXPLICITLY OUT OF SCOPE for Gate A2.
    Any function suggesting incremental semantics (``build_incremental``,
    ``build_since``, ``build_partial``, ``update``, ``patch``, ``merge_into``,
    ``append_new_dates``) is FORBIDDEN and enforced by
    tests/features/win_rate_21d/test_no_forbidden_names.py.

PR-1 intentionally did not implement median, DuckDB writes, or manifest
emission.  PR-2A added the rider-closing safety gate.  PR-2B (this
revision) adds the producer body orchestration and the dependency
injection seam:

    gate  ->  body_enter_hook  ->  compute  ->  writer.write_full

Every arrow crosses a locked boundary that supports independent
observation (D-PR2B-5).  Compute produces an immutable ``BuildArtifact``
(D-PR2B-3); the writer consumes it.  No compute -> writer coupling.

Module dependency (PR-2B blocking-issue remediation):
    ``BuildScope`` and ``ProducerContext`` now live in
    ``features/win_rate_21d/build_types.py``.  They are re-exported
    here so every existing import path
    (``from features.win_rate_21d.producer import BuildScope``) stays
    valid.  The re-export is deliberate API-stability infrastructure,
    not accidental laziness.  Dependency direction is now:

        build_types.py
        /            \\
        producer.py    compute.py
        \\            /
         writer.py

    with no circular edge between producer and compute.  ``compute``
    imports its inputs from ``build_types`` rather than from
    ``producer``, so ``compute`` is unaware of orchestration.

Later PRs still owe:
    - Real PF-B1 / PF-B2 / PF-B6 (PR-2C rider closure).
    - Concrete DuckDB writer (PR-2B.1 or PR-2C).
    - Real compute (PR-2B.1 or PR-2C).
    - PF-L family, __main__ + wrapper, manifest emission, ledger
      append (PR-3).

PR-2A gate ordering (Q-PR2A-alpha', preserved):
    1. ``BUILD_STRATEGY`` defensive guard is the first executable
       statement.  It survives ``python -O`` (does not use ``assert``).
    2. ``verify_rider_closing_checks_are_real()`` is the second gate.
    3. Body entry follows the gate.

D-PR2B-4 invariant:
    No observable side effect before the gate passes.  Body entry, the
    body_enter_hook call, the compute call, and the writer call all
    happen strictly after ``verify_rider_closing_checks_are_real()``
    returns without raising.  Tested by
    ``test_producer_body.test_gate_failure_produces_no_side_effect``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from features.win_rate_21d.build_types import (
    BuildScope,
    PreFlightContext,
    ProducerContext,
)
from features.win_rate_21d.compute import compute as _default_compute
from features.win_rate_21d.constants import BUILD_STRATEGY
from features.win_rate_21d.pre_flight import (
    run_rider_closing_checks,
    verify_rider_closing_checks_are_real,
)
from features.win_rate_21d.writer import BuildArtifact, Writer

# Re-export the moved types so existing import paths remain valid.
# See module docstring for the rationale.
__all__ = [
    "BuildScope",
    "ProducerContext",
    "ProducerBuildRequest",
    "resolve_scope",
    "build_full",
]


# ---------------------------------------------------------------------------
# PR-2B DI seam (D-PR2B-1)
# ---------------------------------------------------------------------------


# Type alias for the compute callable.  Uses the (scope, context) pair
# rather than the full ProducerBuildRequest to keep compute unaware of
# orchestration (D-PR2B-3): compute must not have a handle to the
# writer that its output will be passed to.
ComputeCallable = Callable[[BuildScope, ProducerContext], BuildArtifact]

# Type alias for the body-enter hook.  Parameterless by design
# (D-PR2B-5 body-enter observable): the hook exists solely to be
# observed; it takes no context because it makes no decisions.
BodyEnterHook = Callable[[], None]


def _noop_body_enter_hook() -> None:
    """Canonical default body-enter hook: pure no-op.

    Kept as a named function (rather than a lambda) so:
        1. Test assertions that compare against the default can use
           identity (``deps.body_enter_hook is _noop_body_enter_hook``)
           rather than fragile lambda equality.
        2. Stack traces name it usefully if it ever raises (it should
           not, but defensive naming costs nothing).
    """
    return None


class _ShellWriter:
    """Default writer used when no override is injected.

    PR-2B does not land a concrete DuckDB writer (scope constraint).
    The default writer raises ``NotImplementedError`` on invocation so
    that a caller who somehow reaches the write step without injecting
    a real writer sees a loud, immediate failure rather than a silent
    no-op.

    This writer is intentionally a class rather than a plain function
    because ``Writer`` is a Protocol with a ``write_full`` method; the
    class satisfies the Protocol structurally without contortion.
    """

    def write_full(self, artifact: BuildArtifact) -> None:
        raise NotImplementedError(
            "concrete writer pending (deferred to PR-2B.1 or PR-2C); "
            "inject a real Writer via ProducerBuildRequest.dependencies"
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class _BuildDependencies:
    """Injectable dependencies for a producer build invocation.

    Location rationale (D-PR2B-1.a Option B, LOCKED):
        This dataclass lives as a field on ``ProducerBuildRequest``
        rather than as a separate parameter of ``build_full``.  A
        second parameter on ``build_full`` would create two calling
        conventions (``build_full(request)`` and
        ``build_full(request, deps=...)``); the single-field-on-request
        design preserves exactly one canonical API.

    Underscore prefix:
        The name is private (``_BuildDependencies``) to signal that
        this is a governance-controlled injection seam, not a general
        public API.  Callers construct via
        ``ProducerBuildRequest.dependencies`` field override; direct
        construction of ``_BuildDependencies`` is permitted for tests
        but not encouraged for production code.

    Fields:
        writer: Storage-layer writer.  Default is ``_ShellWriter``
            (raises ``NotImplementedError`` on invocation).
        compute: Artifact-producing compute callable.  Default is the
            ``compute.compute`` shell (raises ``NotImplementedError``
            on invocation).
        body_enter_hook: Observable hook fired immediately after the
            rider-closing safety gate returns and before compute is
            invoked.  Default is ``_noop_body_enter_hook``.

    Immutability:
        ``frozen=True`` prevents field reassignment; ``kw_only=True``
        prevents positional-construction accidents when fields are
        added.  Neither guarantees the referenced callables are
        themselves pure; that is a compositional contract, tested by
        spy in ``test_producer_body``.
    """

    writer: Writer = field(default_factory=_ShellWriter)
    compute: ComputeCallable = field(default=_default_compute)
    body_enter_hook: BodyEnterHook = field(default=_noop_body_enter_hook)


@dataclass(frozen=True, slots=True, kw_only=True)
class ProducerBuildRequest:
    """Per-invocation build request.

    Contains parameters that vary per build within the same context,
    plus the DI seam added in PR-2B.

    Keyword-only construction (consistent with ``ProducerContext``):
        Fields are keyword-only.  Positional construction is forbidden.

    Fields:
        scope: Requested build scope.
        context: Environment-varying configuration.  Defaults to
            canonical SD-A2-2 values.
        dependencies: Injectable seam (writer, compute, body-enter
            hook).  Defaults to canonical shells + no-op hook.
            Added in PR-2B per D-PR2B-1.a Option B.
    """

    scope: BuildScope
    context: ProducerContext = field(default_factory=ProducerContext)
    dependencies: _BuildDependencies = field(
        default_factory=_BuildDependencies
    )


def resolve_scope() -> BuildScope:
    """Resolve R8/R1-relevant scope plus W-1 trading-day buffer.

    TM-041 shell only.  Real implementation requires:
        - Access to the R8/R1 date range (upstream artifact),
        - Trading-calendar API access (deferred to SD-A2-6),
        - A defined buffer contract in code (spec section 5.2, SD-A2-2).
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
    re-runs the full pipeline.

    Ordering (Q-PR2A-alpha' preserved; extended in PR-2B and PR-2C.0):
        1. ``BUILD_STRATEGY`` defensive guard (PR-1, runtime backstop).
        2. ``PreFlightContext`` construction (D-PR2C-1).
        3a. ``verify_rider_closing_checks_are_real(ctx)`` (PR-2A gate,
            signature migrated in PR-2C.0).
        3b. ``run_rider_closing_checks(ctx)`` (D-PR2C-2 runtime gate).
        4. ``body_enter_hook()`` (PR-2B body-entry observable).
        5. ``compute(scope, context)`` -> ``BuildArtifact``.
        6. ``writer.write_full(artifact)``.

    D-PR2B-4 invariant (strengthened by D-PR2C-2):
        Steps 4-6 execute only if BOTH step 3a and step 3b return
        without raising.  A shell state (``PreFlightShellError``), a
        failed pre-flight result (``PreFlightExecutionError``), or any
        operational exception propagated by either gate short-circuits
        before any observable side effect.  Enforced by
        ``test_producer_body.test_gate_failure_produces_no_side_effect``
        and by
        ``test_safety_gate``
        ``.test_build_full_runtime_gate_blocks_body_on_failed_result``.
    """
    # Step 1: defensive governance guard.  Do NOT replace with assert:
    # assertions are removed under python -O and this is a
    # governance-critical check that must survive optimized execution.
    if BUILD_STRATEGY != "one_shot_full_rebuild":
        raise RuntimeError(
            f"Unsupported build strategy: {BUILD_STRATEGY!r}. "
            "Only 'one_shot_full_rebuild' is permitted at Gate A2."
        )

    # Step 2: construct the immutable pre-flight context (D-PR2C-1).
    # Constructed here, not by the caller: both fields are derivable from
    # the request, so ProducerBuildRequest's public shape is unchanged.
    # Construction is pure -- no observable side effect.
    preflight_context = PreFlightContext(
        scope=request.scope,
        producer_context=request.context,
    )

    # Step 3a: shell-state gate (PR-2A, signature migrated in PR-2C.0).
    # PreFlightShellError subclasses NotImplementedError (Q-PR2A-R5),
    # so PR-1's contract that build_full raises NotImplementedError in
    # shell state is preserved.
    verify_rider_closing_checks_are_real(preflight_context)

    # Step 3b: runtime pre-flight enforcement (D-PR2C-2, new in PR-2C.0).
    # Distinct from 3a: 3a asks "is every check implemented?", 3b asks
    # "did every check pass?".  A check returning passed=False is
    # invisible to 3a by design and is caught here.  Results are
    # discarded in PR-2C.0; PR-3 will thread them into the manifest.
    run_rider_closing_checks(preflight_context)

    # Steps 4-6: PR-2B body orchestration.  All three steps are
    # observable through the injected dependencies:
    #     - body_enter_hook: independent body-entry signal
    #       (D-PR2B-5, does NOT rely on writer invocation as proxy).
    #     - compute: pure artifact producer (D-PR2B-3, D-PR2B-4).
    #     - writer.write_full: storage-layer consumer.
    #
    # D-PR2B-4 invariant, strengthened by D-PR2C-2: none of these may run
    # until BOTH pre-flight stages return without raising.
    deps = request.dependencies
    deps.body_enter_hook()
    artifact = deps.compute(request.scope, request.context)
    deps.writer.write_full(artifact)
