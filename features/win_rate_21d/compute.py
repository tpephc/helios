# features/win_rate_21d/compute.py
"""Compute stage for win_rate_21d producer.

Purpose (PR-2B, D-PR2B-3 compute/write separation):
    This module owns artifact production.  It takes a build scope and
    context, reads canonical inputs, computes the cross-sectional
    median frame, and returns an immutable ``BuildArtifact``.  It does
    NOT touch storage.  It does NOT know about the writer.  It does
    NOT know about producer orchestration.

Module dependency (PR-2B blocking-issue remediation):
    Inputs (``BuildScope``, ``ProducerContext``) are imported from
    ``build_types`` rather than from ``producer``.  This module is
    strictly downstream of ``build_types`` and ``writer``, and has no
    reverse edge to ``producer``.  A compute layer aware of the
    orchestration it participates in would be an architectural
    inversion: the producer composes compute, not the other way round.

Governance dispositions (locked in PR-2B disposition ledger):
    D-PR2B-3: compute produces ``BuildArtifact``; downstream writer
        consumes.  No direct compute -> writer coupling.
    Q-PR2B-gamma (deferred): the PIT view name is intentionally NOT
        introduced as a governance constant in PR-2B.  When the real
        compute lands (PR-2B.1 or PR-2C), the canonical source view
        constant is introduced together with the PF-B2 real
        implementation that verifies its use.  Doing it here now would
        add governance surface with no verifier.
    D-PR2B-4: compute MUST be a pure function over its arguments.
        No writes, no environment mutation, no logging that would
        create observable side effects.  This is enforced by
        convention (docstring) in PR-2B and by test spy in
        ``tests/features/win_rate_21d/test_producer_body.py``.

PR-2B status: shell.
    Real compute requires:
        - Access to the canonical PIT view (Q-PR2B-gamma deferred).
        - A locked in-memory representation choice (Q-PR2B-epsilon
          deliberately unlocked at PR-2B).
        - Median-per-date and window aggregation logic
          (SPEC_LOCKED v0.1.0 sections 3.6, 3.7).
    None of those preconditions is met at PR-2B; the callable
    signature is real, the body raises ``NotImplementedError``.
    Tests inject a stub via the ``ProducerBuildRequest.dependencies``
    seam.
"""

from __future__ import annotations

from features.win_rate_21d.build_types import BuildScope, ProducerContext
from features.win_rate_21d.writer import BuildArtifact

__all__ = ["compute"]


def compute(scope: BuildScope, context: ProducerContext) -> BuildArtifact:
    """Produce the ``BuildArtifact`` for the requested scope.

    PR-2B shell.  Real implementation deferred; see module docstring.

    Args:
        scope: Requested trading-date scope.
        context: Environment-varying configuration (paths, target table).

    Returns:
        BuildArtifact: immutable artifact containing target table name,
            payload frame, row count, and canonical column order.

    Raises:
        NotImplementedError: PR-2B shell; real compute pending
            PIT view access and transport-type lock.
    """
    raise NotImplementedError(
        "real compute pending PIT view access and transport-type lock"
    )
