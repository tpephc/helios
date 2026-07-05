# tests/features/win_rate_21d/test_no_forbidden_names.py
"""Guardrail tests for PR-1 producer skeleton.

Enforces (at the module surface level, without executing producer code):
    - SD-A2-3 one-shot full rebuild strategy (no incremental function or
      kwarg names).
    - SD-A2-8 clerical reconciliation on the panel identity key name.
    - Spec §4.4 PIT universe invariant (no direct raw-table reference in
      the producer file).
    - build_full is the only permitted public build entry point.
    - No forbidden method call on any object (Issue G): guards against
      ``some_builder.update(...)`` style attribute calls that the
      ``FunctionDef`` scan would miss.

These tests use static AST analysis and file-content inspection.  They do
NOT execute producer code, so a NotImplementedError inside build_full
does not fail the guardrails.

Deliberate lexical hygiene:
    Forbidden identifiers are constructed by string concatenation at test
    runtime so the source text of this file does not literally contain
    them.  This prevents the tests from tripping on their own file when
    globbing over the test directory.  Raw-table detection uses a
    word-boundary regex to avoid false positives against the canonical
    source view name that legitimately embeds the raw name as a substring.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Final


def _find_repo_root(start: Path) -> Path:
    """Ascend from ``start`` until a directory containing ``pyproject.toml``.

    More robust than a fixed number of ``.parent`` calls: survives
    re-nesting of test files or repo root moves as long as
    ``pyproject.toml`` remains the canonical repo-root marker.
    """
    current = start.resolve()
    while True:
        if (current / "pyproject.toml").is_file():
            return current
        if current == current.parent:
            raise RuntimeError(
                "Could not locate repo root: no pyproject.toml found "
                f"ascending from {start}"
            )
        current = current.parent


_REPO_ROOT: Final[Path] = _find_repo_root(Path(__file__))
PRODUCER_PATH: Final[Path] = (
    _REPO_ROOT / "features" / "win_rate_21d" / "producer.py"
)
FEATURE_DIR: Final[Path] = _REPO_ROOT / "features" / "win_rate_21d"
TEST_DIR: Final[Path] = _REPO_ROOT / "tests" / "features" / "win_rate_21d"

# Function-level forbidden names: caught by the FunctionDef scan.
FORBIDDEN_FUNCTION_NAMES: Final[frozenset[str]] = frozenset(
    {
        "build_incremental",
        "build_since",
        "build_partial",
        "update",
        "patch",
        "merge_into",
        "append_new_dates",
    }
)

# Keyword-argument forbidden names.
FORBIDDEN_KWARG_NAMES: Final[frozenset[str]] = frozenset(
    {
        "incremental",
        "since_date",
        "start_from",
        "resume_from",
    }
)

# Issue G: Attribute-call forbidden names.
# Restricted subset of FORBIDDEN_FUNCTION_NAMES.  Only names that would
# create semantic ambiguity if invoked as a method on any object.  Names
# like ``build_full`` / ``build_since`` are excluded because they are
# unambiguous top-level functions and would be caught by the FunctionDef
# scan; scanning them as attributes would create no additional signal.
FORBIDDEN_ATTRIBUTE_NAMES: Final[frozenset[str]] = frozenset(
    {
        "update",
        "patch",
        "merge_into",
        "append_new_dates",
    }
)


def _producer_ast() -> ast.Module:
    return ast.parse(PRODUCER_PATH.read_text(encoding="utf-8"))


def test_producer_file_exists() -> None:
    """Fail loudly if repo-root resolution went sideways."""
    assert PRODUCER_PATH.is_file(), f"producer.py not found at {PRODUCER_PATH}"


def test_producer_has_no_forbidden_function_names() -> None:
    tree = _producer_ast()
    found = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in FORBIDDEN_FUNCTION_NAMES
    }
    assert found == set(), (
        f"forbidden function names present: {sorted(found)}"
    )


def test_producer_has_no_forbidden_argument_names() -> None:
    tree = _producer_ast()
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.arg) and node.arg in FORBIDDEN_KWARG_NAMES:
            found.add(node.arg)
        if (
            isinstance(node, ast.keyword)
            and node.arg is not None
            and node.arg in FORBIDDEN_KWARG_NAMES
        ):
            found.add(node.arg)
    assert found == set(), (
        f"forbidden argument names present: {sorted(found)}"
    )


def test_producer_has_no_forbidden_attribute_calls() -> None:
    """Issue G: catch ``some_object.update(...)`` style method invocations.

    The FunctionDef scan would miss these because the identifier is on
    the ``attr`` of an ``ast.Attribute`` node used as the callable of
    an ``ast.Call``, not a defined function name.
    """
    tree = _producer_ast()
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in FORBIDDEN_ATTRIBUTE_NAMES:
                found.add(node.func.attr)
    assert found == set(), (
        f"forbidden attribute calls present: {sorted(found)}"
    )


def test_added_files_do_not_use_deprecated_stock_key_name() -> None:
    """SD-A2-8 clerical reconciliation: no deprecated key literal anywhere.

    The reconciliation renamed the panel identity key from its earlier form
    to the canonical spec §6.1 name.  Grepping across added files must yield
    zero matches for the deprecated form.

    The literal is constructed by string concatenation at test runtime so
    the source of this file does not itself contain the forbidden string,
    which would otherwise trip the check when the test globs its own file.
    """
    deprecated = "symbol" + "_id"
    paths = [
        *FEATURE_DIR.glob("*.py"),
        *TEST_DIR.glob("*.py"),
    ]
    offenders = [
        str(path)
        for path in paths
        if deprecated in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], (
        f"deprecated key name present in: {offenders}"
    )


def test_producer_file_does_not_reference_raw_price_table() -> None:
    """Spec §4.4 PIT universe invariant: no direct raw-table reference.

    Word-boundary regex prevents false positives against the canonical
    source view name, which legitimately embeds the raw-table name as a
    substring.  A match here means the producer references the raw table
    as a standalone identifier, which is a P0 lineage violation.
    """
    raw_table = "daily" + "_price_adj"
    # Match raw_table only when not preceded or followed by identifier
    # characters.  This treats the canonical source view name (which has
    # 'market_' immediately preceding the raw substring) as non-matching
    # while still catching a standalone reference.
    pattern = re.compile(
        rf"(?<![A-Za-z0-9_]){re.escape(raw_table)}(?![A-Za-z0-9_])"
    )
    content = PRODUCER_PATH.read_text(encoding="utf-8")
    match = pattern.search(content)
    assert match is None, (
        f"producer file references forbidden raw table {raw_table!r} "
        f"at offset {match.start() if match else -1}"
    )


def test_producer_exposes_only_full_build_surface() -> None:
    """Positive assertion: build_full exists; no forbidden variants.

    TM-042 anchor at test level.
    """
    tree = _producer_ast()
    function_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }
    assert "build_full" in function_names, (
        "build_full must be defined in producer.py"
    )
    assert function_names.isdisjoint(FORBIDDEN_FUNCTION_NAMES), (
        "producer.py exposes a forbidden build variant: "
        f"{sorted(function_names & FORBIDDEN_FUNCTION_NAMES)}"
    )