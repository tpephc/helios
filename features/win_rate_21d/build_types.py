# features/win_rate_21d/build_types.py
"""Shared types for producer / compute layers.

Purpose (PR-2B blocking-issue remediation):
    This module is the shared upstream of ``producer.py`` and
    ``compute.py``.  It exists solely to break the circular dependency
    that arises when both modules need ``BuildScope`` /
    ``ProducerContext`` and ``compute`` is a member of the seam that
    ``producer`` orchestrates.

Dependency direction after remediation:

        build_types.py            <- this module
        /            \\
        producer.py    compute.py
        \\            /
         writer.py                 <- BuildArtifact, Writer Protocol

    producer, compute -> build_types
    producer, compute -> writer
    producer -> compute (still, but no reverse edge)

Governance:
    Neither ``BuildScope`` nor ``ProducerContext`` was modified during
    the move.  The definitions here are byte-identical to their PR-1
    forms.  ``producer.py`` re-exports both symbols so every existing
    import path (``from features.win_rate_21d.producer import
    BuildScope``) remains valid.  This preserves the public API surface
    that ``test_producer_surface.py``, ``test_safety_gate.py``, and
    ``test_producer_body.py`` depend on -- no test change required.

    Because this is a pure refactor with no behavioral delta, it does
    not require a new SD lock; it is remediation of a PR-2B
    implementation defect flagged during review.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from features.win_rate_21d.constants import DUCKDB_PATH, PRODUCER_TABLE_NAME

__all__ = ["BuildScope", "PreFlightContext", "ProducerContext"]


@dataclass(frozen=True, slots=True)
class BuildScope:
    """Requested producer build date scope.

    Attributes:
        requested_start: Inclusive earliest trading date requested.
        requested_end: Inclusive latest trading date requested.

    Materialized scope may differ from requested (subject to PF-B1
    validation), but the requested scope is what the caller intended
    and what appears in the manifest ``build_scope`` block once
    implemented.
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

    Override contract (unchanged from PR-1):
        Overrides on ``duckdb_path`` and ``target_table`` are permitted
        for testability only.  Governed builds MUST pass PF-B /
        manifest identity checks that assert the canonical SD-A2-2
        values before any output can become canonical.
    """

    duckdb_path: str = DUCKDB_PATH
    target_table: str = PRODUCER_TABLE_NAME


@dataclass(frozen=True, slots=True, kw_only=True)
class PreFlightContext:
    """Immutable runtime carrier for rider-closing pre-flight checks.

    Governance: D-PR2C-1 (LOCKED).

    Invocation model:
        Q-PR2A-D2 deferred the registry-shape question to the PR
        introducing the first parameterised rider-closing check.
        D-PR2C-1 resolves it with a single homogeneous callable
        contract, ``Callable[[PreFlightContext], PreFlightResult]``,
        rather than ``functools.partial`` bindings or
        ``(callable, args_provider)`` pairs.  Both alternatives were
        rejected on structural evidence: the registry membership
        contract asserts exact tuple equality, and the aggregate shell
        diagnostic reads ``check.__name__`` -- neither survives partial
        object substitution.

    Field naming:
        ``producer_context`` rather than ``context`` so call sites read
        ``ctx.producer_context.duckdb_path`` instead of the ambiguous
        ``ctx.context.duckdb_path``.

    Construction point:
        Constructed inside ``producer.build_full()``, never by callers.
        Both fields are derivable from ``ProducerBuildRequest``, so the
        public build API is unchanged.

    Content restriction (D-PR2C-1 forward-compatibility clause):
        This context carries governance-stable immutable metadata only.
        Mutable resources, open DuckDB connections, writers, hooks,
        service objects, and compute callables are FORBIDDEN fields.
        Later PRs may append keyword-only fields with defaults without
        reopening D-PR2C-1 provided that restriction holds.

    Attributes:
        scope: Requested build date scope (PF-B1 input).
        producer_context: Environment-varying configuration; supplies
            ``duckdb_path`` and ``target_table`` (PF-B2 / PF-B6 inputs).
    """

    scope: BuildScope
    producer_context: ProducerContext
