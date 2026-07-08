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
    - PR-2B.1 [2/4] invariants (D-PR2B.1-2):
      ``frame`` must be ``pyarrow.Table``; ``row_count`` must match
      ``frame.num_rows``; ``column_names`` must match
      ``frame.column_names``.

Deferred fields (NOT tested here because they do not exist in PR-2B):
    ``content_hash``, ``snapshot_id``, ``build_utc_timestamp``,
    ``input_snapshots``.  These land at manifest emission (PR-3).
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from typing import Any

import pyarrow as pa
import pytest

from features.win_rate_21d.writer import BuildArtifact, Writer


def _arrow_of(row_count: int, column_names: tuple[str, ...]) -> pa.Table:
    """Build a pyarrow.Table with the requested (rows, cols) shape.

    Uses explicit ``schema=`` so the fixture's shape intent is
    self-documenting and robust across pyarrow versions; the helper
    is not a test of pyarrow inference.  Column dtype (float64) is
    incidental; only shape matters for BuildArtifact invariants.
    """
    if not column_names:
        return pa.table({})

    return pa.table(
        {
            name: pa.array([None] * row_count, type=pa.float64())
            for name in column_names
        },
        schema=pa.schema(
            [(name, pa.float64()) for name in column_names]
        ),
    )


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
        frame=_arrow_of(42, ("date", "stock_id", "win_rate_21d")),
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
        frame=_arrow_of(0, ()),
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
        frame=_arrow_of(0, ("a", "b")),
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


# ---------------------------------------------------------------------------
# PR-2B.1 [2/4] cross-validation invariants (D-PR2B.1-2)
# ---------------------------------------------------------------------------


def test_build_artifact_rejects_non_arrow_frame() -> None:
    """__post_init__ rejects a frame that is not a pyarrow.Table."""
    with pytest.raises(TypeError, match="pyarrow.Table"):
        BuildArtifact(
            table_name="t",
            frame=object(),  # deliberate wrong type
            row_count=0,
            column_names=(),
        )


def test_build_artifact_rejects_row_count_mismatch() -> None:
    """__post_init__ rejects row_count that disagrees with frame.num_rows."""
    frame = _arrow_of(3, ("x",))  # frame has 3 rows
    with pytest.raises(ValueError, match="row_count"):
        BuildArtifact(
            table_name="t",
            frame=frame,
            row_count=99,  # disagrees
            column_names=("x",),
        )


def test_build_artifact_rejects_column_names_mismatch() -> None:
    """__post_init__ rejects column_names that disagree with frame.column_names."""
    frame = _arrow_of(0, ("a", "b"))
    with pytest.raises(ValueError, match="column_names"):
        BuildArtifact(
            table_name="t",
            frame=frame,
            row_count=0,
            column_names=("a", "c"),  # disagrees on second column
        )
