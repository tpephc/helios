# tests/features/win_rate_21d/test_build_artifact.py
"""Tests for ``features.win_rate_21d.writer.BuildArtifact``.

Verifies:
    - Field shape locked in PR-2B ledger (D-PR2B-3):
      ``table_name``, ``frame``, ``row_count``, ``column_names``.
    - Immutability at the dataclass level (frozen).
    - Keyword-only construction (positional construction raises).
    - Writer Protocol structural conformance:
      a class exposing ``write_full(artifact)`` satisfies ``Writer``
      without inheritance.

Deferred fields (NOT tested here because they do not exist in PR-2B):
    ``content_hash``, ``snapshot_id``, ``build_utc_timestamp``,
    ``input_snapshots``.  These land at manifest emission (PR-3).
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from typing import Any

import pytest

from features.win_rate_21d.writer import BuildArtifact, Writer


# ---------------------------------------------------------------------------
# Field shape (D-PR2B-3 minimum viable shape)
# ---------------------------------------------------------------------------


def test_build_artifact_has_locked_field_set() -> None:
    """Guard against premature field additions per DGP-01."""
    field_names = {f.name for f in fields(BuildArtifact)}
    assert field_names == {
        "table_name",
        "frame",
        "row_count",
        "column_names",
    }


def test_build_artifact_construction_accepts_locked_fields() -> None:
    artifact = BuildArtifact(
        table_name="test_target",
        frame=object(),
        row_count=42,
        column_names=("date", "stock_id", "win_rate_21d"),
    )
    assert artifact.table_name == "test_target"
    assert artifact.row_count == 42
    assert artifact.column_names == ("date", "stock_id", "win_rate_21d")


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


def test_build_artifact_is_frozen() -> None:
    """frozen=True locked by ledger: no field reassignment."""
    artifact = BuildArtifact(
        table_name="t",
        frame=object(),
        row_count=0,
        column_names=(),
    )
    with pytest.raises(FrozenInstanceError):
        artifact.table_name = "other"  # type: ignore[misc]


def test_build_artifact_column_names_is_tuple() -> None:
    """Immutable container matches manifest schema convention.

    ``manifest.ManifestV1.column_names`` is ``tuple[str, ...]``.
    Using a list here would be an unstated mutability seam that could
    diverge between artifact and manifest.
    """
    artifact = BuildArtifact(
        table_name="t",
        frame=object(),
        row_count=0,
        column_names=("a", "b"),
    )
    assert isinstance(artifact.column_names, tuple)


# ---------------------------------------------------------------------------
# Keyword-only construction
# ---------------------------------------------------------------------------


def test_build_artifact_rejects_positional_construction() -> None:
    """Consistent with ProducerContext / ProducerBuildRequest.

    Positional callers would silently misbind values when future fields
    are added; keyword-only makes that failure loud.
    """
    with pytest.raises(TypeError):
        BuildArtifact("t", object(), 0, ())  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Writer Protocol conformance
# ---------------------------------------------------------------------------


def test_writer_protocol_accepts_structural_conformer() -> None:
    """A duck-typed writer with write_full(artifact) satisfies Writer.

    Verifies D-PR2B-1.c: the seam is a Protocol, not an ABC.  No
    inheritance from Writer is required.
    """

    class _MyWriter:
        def write_full(self, artifact: BuildArtifact) -> None:
            return None

    # runtime_checkable Protocol supports isinstance.
    assert isinstance(_MyWriter(), Writer)


def test_writer_protocol_rejects_non_conformer() -> None:
    """A class without write_full does NOT satisfy Writer."""

    class _NotAWriter:
        def something_else(self, artifact: BuildArtifact) -> None:
            return None

    assert not isinstance(_NotAWriter(), Writer)


def test_writer_protocol_write_full_return_annotation_is_none() -> None:
    """Writer.write_full documents return type None.

    Any diagnostic surface belongs on the manifest / ledger layer
    landing in PR-3, not on the writer.  A non-None return type would
    prematurely lock a seam that should stay unlocked.
    """
    hints = _get_annotations(Writer.write_full)
    # ``from __future__ import annotations`` at module load time in
    # writer.py stores annotations as strings; we check both forms
    # (string ``"None"`` or ``type(None)``) to survive that toggle.
    assert hints.get("return") in ("None", type(None)), (
        f"Writer.write_full return annotation drift: {hints.get('return')!r}"
    )


def _get_annotations(func: Any) -> dict[str, Any]:
    # Prefer inspect.get_annotations under 3.10+; falls back to
    # __annotations__ if unavailable.
    try:
        import inspect

        return inspect.get_annotations(func)
    except AttributeError:  # pragma: no cover
        return getattr(func, "__annotations__", {})
