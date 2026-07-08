# features/win_rate_21d/writer.py
"""Writer protocol and BuildArtifact boundary for win_rate_21d.

Purpose (PR-2B, D-PR2B-1 seam + D-PR2B-3 compute/write separation):
    This module defines the injection seam between the producer body
    and the concrete storage layer.  Compute produces an immutable
    ``BuildArtifact``; the writer consumes it.  Compute MUST NOT call
    the writer directly; the orchestration in ``producer.build_full``
    performs the sequencing.

Governance dispositions (locked in PR-2B disposition ledger):
    D-PR2B-1.b: writer method name is ``write_full`` (semantic
        symmetry with ``build_full``; survives the
        ``test_no_forbidden_names.FORBIDDEN_ATTRIBUTE_NAMES`` AST scan
        because ``write_full`` is not in the forbidden set).
    D-PR2B-1.c: writer surface is a ``typing.Protocol`` (structural
        typing).  No ``abc.ABC`` layer.
    D-PR2B-3: writer accepts a ``BuildArtifact``; compute produces one.
        There is no direct compute -> writer call path.
    Q-PR2B-epsilon: payload frame type is intentionally NOT locked.
        ``BuildArtifact.frame`` is typed ``object`` so PR-2B does not
        prejudge polars vs pyarrow vs duckdb-native.  The concrete
        writer landing PR (PR-2B.1 or PR-2C) will narrow this when
        empirical evidence demands.

Scope note (Q-PR2B-gamma deferred):
    The concrete DuckDB writer is intentionally NOT provided here.
    PR-2B lands the Protocol + a shell default in ``producer.py``.
    The real DuckDB-backed implementation is deferred to PR-2B.1 or
    folded into PR-2C.  This preserves the "no real DuckDB mutation"
    scope constraint on PR-2B.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

__all__ = [
    "BuildArtifact",
    "Writer",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class BuildArtifact:
    """Immutable output of ``compute``, input to ``Writer.write_full``.

    Field set (D-PR2B-3 minimum viable shape, locked in PR-2B ledger):
        table_name: Canonical target table for the write.  MUST equal
            ``constants.PRODUCER_TABLE_NAME`` for a governed build;
            the writer does NOT re-verify this (the check belongs at
            the manifest identity layer, PR-3).
        frame: Opaque payload.  Type intentionally ``object`` per
            Q-PR2B-epsilon.  The concrete writer PR will introduce a
            narrower type (``pyarrow.Table``, ``polars.DataFrame``, or
            a Protocol) once the compute pipeline is real and the
            transport-type choice can be made empirically rather than
            speculatively.
        row_count: Number of rows in ``frame``.  Redundant with the
            frame itself but carried explicitly on the artifact so
            manifest emission (PR-3) does not need to introspect an
            opaque payload.
        column_names: Ordered tuple of column names in ``frame``.
            Immutability (``tuple``) matches the manifest schema.

    Fields deliberately NOT on this dataclass in PR-2B:
        - ``content_hash``: PR-3 responsibility (requires canonical
          serialization scheme that has not been locked).
        - ``snapshot_id``: PR-3 responsibility.
        - ``build_utc_timestamp``: PR-3 responsibility.
        - ``input_snapshots``: PR-3 responsibility.
        Any of these landing here in PR-2B would be premature
        governance surface per DGP-01.
    """

    table_name: str
    frame: object
    row_count: int
    column_names: tuple[str, ...]


@runtime_checkable
class Writer(Protocol):
    """Injection seam for the storage-layer write step.

    Contract (locked in PR-2B ledger):
        - Single method: ``write_full(artifact)``.  Semantic pairing
          with ``BUILD_STRATEGY == "one_shot_full_rebuild"``.
        - Method name survives the AST forbidden-attribute scan
          (``update``, ``patch``, ``merge_into``, ``append_new_dates``
          are forbidden; ``write_full`` is not).
        - Return type ``None``: any diagnostic surface belongs on the
          manifest / ledger layer landing in PR-3, not on the writer.
        - No side effects if the caller has not already passed the
          rider-closing safety gate.  This is a compositional invariant
          enforced by ``producer.build_full`` (D-PR2B-4), not by the
          writer itself; the writer trusts its caller.

    Structural (Protocol) rather than nominal (ABC):
        Aligns with ``pre_flight.PreFlightCallable`` (also structural)
        and lets test doubles satisfy the contract without inheritance
        machinery.  ``@runtime_checkable`` is enabled so callers who
        want a runtime ``isinstance`` sanity check may perform one,
        without forcing every implementation through an ABC.
    """

    def write_full(self, artifact: BuildArtifact) -> None:
        """Persist ``artifact`` to storage as a full replacement.

        The concrete DuckDB implementation (not landed in PR-2B) will
        use ``CREATE OR REPLACE TABLE`` semantics per Q-PR2B-delta.
        """
        ...
