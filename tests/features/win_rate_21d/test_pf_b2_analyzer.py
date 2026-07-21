# tests/features/win_rate_21d/test_pf_b2_analyzer.py
"""Tests for PF-B2 canonical-source AST analyzer.

Covers:
    - D-PR2C-10 §12: real-module integration regression (blocking
      acceptance requirement).
    - Layer 1: exact-equality forbidden-literal detection.
    - Layer 2 P-1: canonical import provenance.
    - Layer 2 P-2: single-hop local assignment whitelist.
    - Layer 2 P-3: governed execute sink.
    - Template provenance.
    - Key negative regressions from review rounds v1.0-v1.5.
"""

from __future__ import annotations

from datetime import date
from textwrap import dedent

import pytest

from features.win_rate_21d._pf_b2_analyzer import (
    FORBIDDEN_SOURCE_LITERAL,
    GOVERNED_MODULE,
    SUPPORTED_TEMPLATE_FIELD,
    SUPPORTED_TEMPLATE_NAME,
    AnalysisVerdict,
    analyze_source,
)
from features.win_rate_21d.build_types import (
    BuildScope,
    PreFlightContext,
    ProducerContext,
)
from features.win_rate_21d.pre_flight import (
    PreFlightSeverity,
    pf_b2_canonical_source_check,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CANONICAL_IMPORT = "from features.win_rate_21d.constants import CANONICAL_PIT_VIEW_NAME"
_TEMPLATE_ASSIGN = f'{SUPPORTED_TEMPLATE_NAME} = """SELECT {{view_name}} WHERE n >= {{min_obs}}"""'
_FORMAT_CALL = (
    f"    sql = {SUPPORTED_TEMPLATE_NAME}.format("
    f"{SUPPORTED_TEMPLATE_FIELD}=CANONICAL_PIT_VIEW_NAME, min_obs=30)"
)
_EXECUTE = "    conn.execute(sql)"


def _good_source() -> str:
    """Minimal source that satisfies both layers."""
    return (
        f"{_CANONICAL_IMPORT}\n"
        f"{_TEMPLATE_ASSIGN}\n"
        f"def compute(scope, context):\n"
        f"{_FORMAT_CALL}\n"
        f"{_EXECUTE}\n"
    )


def _preflight_context() -> PreFlightContext:
    return PreFlightContext(
        scope=BuildScope(
            requested_start=date(2020, 1, 2),
            requested_end=date(2020, 1, 10),
        ),
        producer_context=ProducerContext(),
    )


# ---------------------------------------------------------------------------
# D-PR2C-10 §12 — real-module integration regression (BLOCKING acceptance)
# ---------------------------------------------------------------------------


def test_pf_b2_canonical_source_check_passes_for_real_compute_module() -> None:
    """PF-B2 accepts the production compute module at current HEAD.

    This is the PR-2C.1 blocking acceptance requirement (D-PR2C-10 §12).
    It exercises the full chain: find_spec resolution → source read →
    ast.parse → Layer 1 → Layer 2 → PreFlightResult mapping.
    """
    result = pf_b2_canonical_source_check(_preflight_context())

    assert result.check_id == "PF-B2"
    assert result.passed is True
    assert result.severity is PreFlightSeverity.INFO


def test_analyzer_accepts_current_compute_source() -> None:
    """Analyzer boundary: real compute.py source passes analysis."""
    from importlib.util import find_spec
    from pathlib import Path

    spec = find_spec(GOVERNED_MODULE)
    assert spec is not None
    assert spec.origin is not None

    source = Path(spec.origin).read_text(encoding="utf-8")
    result = analyze_source(source, source_identity="compute.py")

    assert result.passed
    assert result.verdict is AnalysisVerdict.PASS
    assert result.diagnostics == ()


# ---------------------------------------------------------------------------
# Layer 1 — forbidden literal
# ---------------------------------------------------------------------------


def test_layer1_rejects_exact_forbidden_literal() -> None:
    src = f'{_CANONICAL_IMPORT}\nx = "{FORBIDDEN_SOURCE_LITERAL}"'
    result = analyze_source(src, source_identity="test.py")

    assert result.verdict is AnalysisVerdict.LAYER1_VIOLATION
    assert FORBIDDEN_SOURCE_LITERAL in result.diagnostics[0]


def test_layer1_passes_forbidden_token_inside_longer_string() -> None:
    """Exact equality, not substring (D-PR2C-10 §2)."""
    src = (
        f"{_CANONICAL_IMPORT}\n"
        f'"""This docstring mentions {FORBIDDEN_SOURCE_LITERAL} safely."""\n'
        f"{_TEMPLATE_ASSIGN}\n"
        f"def f():\n{_FORMAT_CALL}\n{_EXECUTE}\n"
    )
    result = analyze_source(src, source_identity="test.py")
    assert result.passed


# ---------------------------------------------------------------------------
# Layer 2 P-1 — import provenance
# ---------------------------------------------------------------------------


def test_p1_rejects_wrong_source_module() -> None:
    src = f"from evil import CANONICAL_PIT_VIEW_NAME\n{_TEMPLATE_ASSIGN}\ndef f():\n{_FORMAT_CALL}\n{_EXECUTE}\n"
    result = analyze_source(src, source_identity="t.py")
    assert result.verdict is AnalysisVerdict.LAYER2_VIOLATION


def test_p1_rejects_aliased_import() -> None:
    src = f"from features.win_rate_21d.constants import OTHER as CANONICAL_PIT_VIEW_NAME\n{_TEMPLATE_ASSIGN}\ndef f():\n{_FORMAT_CALL}\n{_EXECUTE}\n"
    result = analyze_source(src, source_identity="t.py")
    assert result.verdict is AnalysisVerdict.LAYER2_VIOLATION


def test_p1_rejects_relative_import() -> None:
    src = f"from .features.win_rate_21d.constants import CANONICAL_PIT_VIEW_NAME\n{_TEMPLATE_ASSIGN}\ndef f():\n{_FORMAT_CALL}\n{_EXECUTE}\n"
    result = analyze_source(src, source_identity="t.py")
    assert result.verdict is AnalysisVerdict.LAYER2_VIOLATION


def test_p1_rejects_module_scope_reassignment() -> None:
    src = f"{_CANONICAL_IMPORT}\nCANONICAL_PIT_VIEW_NAME = 'hacked'\n{_TEMPLATE_ASSIGN}\ndef f():\n{_FORMAT_CALL}\n{_EXECUTE}\n"
    result = analyze_source(src, source_identity="t.py")
    assert result.verdict is AnalysisVerdict.LAYER2_VIOLATION
    assert "rebinding" in result.diagnostics[0]


def test_p1_rejects_second_alias_in_same_import() -> None:
    """D-PR2C-9 A1 per-alias exemption."""
    src = (
        "from features.win_rate_21d.constants import "
        "CANONICAL_PIT_VIEW_NAME, OTHER as CANONICAL_PIT_VIEW_NAME\n"
        f"{_TEMPLATE_ASSIGN}\ndef f():\n{_FORMAT_CALL}\n{_EXECUTE}\n"
    )
    result = analyze_source(src, source_identity="t.py")
    assert result.verdict is AnalysisVerdict.LAYER2_VIOLATION


def test_p1_rejects_structured_del() -> None:
    src = f"{_CANONICAL_IMPORT}\ndel (CANONICAL_PIT_VIEW_NAME,)\n{_TEMPLATE_ASSIGN}\ndef f():\n{_FORMAT_CALL}\n{_EXECUTE}\n"
    result = analyze_source(src, source_identity="t.py")
    assert result.verdict is AnalysisVerdict.LAYER2_VIOLATION


# ---------------------------------------------------------------------------
# Layer 2 P-2 — assignment whitelist
# ---------------------------------------------------------------------------


def test_p2_rejects_container_rhs() -> None:
    src = f"{_CANONICAL_IMPORT}\n{_TEMPLATE_ASSIGN}\ndef f():\n    sql = [CANONICAL_PIT_VIEW_NAME]\n{_EXECUTE}\n"
    result = analyze_source(src, source_identity="t.py")
    assert result.verdict is AnalysisVerdict.LAYER2_VIOLATION


def test_p2_rejects_lambda_rhs() -> None:
    src = f"{_CANONICAL_IMPORT}\n{_TEMPLATE_ASSIGN}\ndef f():\n    sql = lambda: CANONICAL_PIT_VIEW_NAME\n{_EXECUTE}\n"
    result = analyze_source(src, source_identity="t.py")
    assert result.verdict is AnalysisVerdict.LAYER2_VIOLATION


def test_p2_rejects_conditional_assignment() -> None:
    src = dedent("""\
        from features.win_rate_21d.constants import CANONICAL_PIT_VIEW_NAME

        _SQL_MEDIAN_QUERY_TEMPLATE = \"\"\"SELECT {view_name}\"\"\"

        def f(flag):
            if flag:
                sql = _SQL_MEDIAN_QUERY_TEMPLATE.format(
                    view_name=CANONICAL_PIT_VIEW_NAME,
                )
            conn.execute(sql)
    """)
    result = analyze_source(src, source_identity="t.py")
    assert result.verdict is AnalysisVerdict.LAYER2_VIOLATION


def test_p2_rejects_arbitrary_function_call() -> None:
    src = f"{_CANONICAL_IMPORT}\n{_TEMPLATE_ASSIGN}\ndef f():\n    sql = evil(CANONICAL_PIT_VIEW_NAME)\n{_EXECUTE}\n"
    result = analyze_source(src, source_identity="t.py")
    assert result.verdict is AnalysisVerdict.LAYER2_VIOLATION


def test_p2_rejects_unapproved_format_receiver() -> None:
    src = f"{_CANONICAL_IMPORT}\n{_TEMPLATE_ASSIGN}\ndef f():\n    sql = other.format(view_name=CANONICAL_PIT_VIEW_NAME)\n{_EXECUTE}\n"
    result = analyze_source(src, source_identity="t.py")
    assert result.verdict is AnalysisVerdict.LAYER2_VIOLATION


def test_p2_rejects_kwargs_splat_in_format() -> None:
    src = (
        f"{_CANONICAL_IMPORT}\n{_TEMPLATE_ASSIGN}\ndef f():\n"
        f"    sql = {SUPPORTED_TEMPLATE_NAME}.format("
        f"view_name=CANONICAL_PIT_VIEW_NAME, **opts)\n{_EXECUTE}\n"
    )
    result = analyze_source(src, source_identity="t.py")
    assert result.verdict is AnalysisVerdict.LAYER2_VIOLATION


def test_p2_rejects_double_assignment_to_v() -> None:
    src = f"{_CANONICAL_IMPORT}\n{_TEMPLATE_ASSIGN}\ndef f():\n{_FORMAT_CALL}\n    sql = 'x'\n{_EXECUTE}\n"
    result = analyze_source(src, source_identity="t.py")
    assert result.verdict is AnalysisVerdict.LAYER2_VIOLATION


def test_p2_rejects_parameter_named_v() -> None:
    src = f"{_CANONICAL_IMPORT}\n{_TEMPLATE_ASSIGN}\ndef f(sql):\n{_FORMAT_CALL}\n{_EXECUTE}\n"
    result = analyze_source(src, source_identity="t.py")
    assert result.verdict is AnalysisVerdict.LAYER2_VIOLATION


# ---------------------------------------------------------------------------
# Template provenance
# ---------------------------------------------------------------------------


def test_template_rejects_no_field_reference() -> None:
    """Template must actually reference {view_name} (D-PR2C-10 §15 lineage)."""
    src = (
        f'{_CANONICAL_IMPORT}\n{SUPPORTED_TEMPLATE_NAME} = "SELECT 1"\n'
        f"def f():\n    sql = {SUPPORTED_TEMPLATE_NAME}.format("
        f"view_name=CANONICAL_PIT_VIEW_NAME)\n{_EXECUTE}\n"
    )
    result = analyze_source(src, source_identity="t.py")
    assert result.verdict is AnalysisVerdict.LAYER2_VIOLATION


def test_template_rejects_wrong_field_consumed() -> None:
    src = (
        f'{_CANONICAL_IMPORT}\n{SUPPORTED_TEMPLATE_NAME} = "SELECT {{source}}"\n'
        f"def f():\n    sql = {SUPPORTED_TEMPLATE_NAME}.format("
        f"source='evil', view_name=CANONICAL_PIT_VIEW_NAME)\n{_EXECUTE}\n"
    )
    result = analyze_source(src, source_identity="t.py")
    assert result.verdict is AnalysisVerdict.LAYER2_VIOLATION


def test_template_rejects_chained_assignment() -> None:
    src = (
        f"{_CANONICAL_IMPORT}\nOTHER = {SUPPORTED_TEMPLATE_NAME} = "
        f'"SELECT {{view_name}}"\ndef f():\n{_FORMAT_CALL}\n{_EXECUTE}\n'
    )
    result = analyze_source(src, source_identity="t.py")
    assert result.verdict is AnalysisVerdict.LAYER2_VIOLATION


def test_template_rejects_conditional_reassignment() -> None:
    src = (
        f"{_CANONICAL_IMPORT}\n{_TEMPLATE_ASSIGN}\n"
        f"if flag:\n    {SUPPORTED_TEMPLATE_NAME} = evil\n"
        f"def f():\n{_FORMAT_CALL}\n{_EXECUTE}\n"
    )
    result = analyze_source(src, source_identity="t.py")
    assert result.verdict is AnalysisVerdict.LAYER2_VIOLATION


def test_template_rejects_parameter_shadowing() -> None:
    src = (
        f"{_CANONICAL_IMPORT}\n{_TEMPLATE_ASSIGN}\n"
        f"def f({SUPPORTED_TEMPLATE_NAME}):\n{_FORMAT_CALL}\n{_EXECUTE}\n"
    )
    result = analyze_source(src, source_identity="t.py")
    assert result.verdict is AnalysisVerdict.LAYER2_VIOLATION


def test_template_rejects_import_rebinding() -> None:
    src = (
        f"{_CANONICAL_IMPORT}\n"
        f"import evil as {SUPPORTED_TEMPLATE_NAME}\n"
        f"def f():\n{_FORMAT_CALL}\n{_EXECUTE}\n"
    )
    result = analyze_source(src, source_identity="t.py")
    assert result.verdict is AnalysisVerdict.LAYER2_VIOLATION


# ---------------------------------------------------------------------------
# Layer 2 P-3 — governed sink
# ---------------------------------------------------------------------------


def test_p3_rejects_missing_sink() -> None:
    src = f"{_CANONICAL_IMPORT}\n{_TEMPLATE_ASSIGN}\ndef f():\n{_FORMAT_CALL}\n    print(sql)\n"
    result = analyze_source(src, source_identity="t.py")
    assert result.verdict is AnalysisVerdict.LAYER2_VIOLATION


def test_p3_rejects_kwargs_splat_in_execute() -> None:
    src = f"{_CANONICAL_IMPORT}\n{_TEMPLATE_ASSIGN}\ndef f():\n{_FORMAT_CALL}\n    conn.execute(**sql)\n"
    result = analyze_source(src, source_identity="t.py")
    assert result.verdict is AnalysisVerdict.LAYER2_VIOLATION


def test_p3_accepts_keyword_argument_in_execute() -> None:
    src = f"{_CANONICAL_IMPORT}\n{_TEMPLATE_ASSIGN}\ndef f():\n{_FORMAT_CALL}\n    conn.execute(query=sql)\n"
    result = analyze_source(src, source_identity="t.py")
    assert result.passed


# ---------------------------------------------------------------------------
# Positive cases
# ---------------------------------------------------------------------------


def test_good_source_passes() -> None:
    result = analyze_source(_good_source(), source_identity="compute.py")
    assert result.passed
    assert result.verdict is AnalysisVerdict.PASS


def test_extra_unrelated_import_ok() -> None:
    src = (
        "from features.win_rate_21d.constants import "
        "CANONICAL_PIT_VIEW_NAME, OTHER\n"
        f"{_TEMPLATE_ASSIGN}\ndef f():\n{_FORMAT_CALL}\n{_EXECUTE}\n"
    )
    result = analyze_source(src, source_identity="t.py")
    assert result.passed


# ---------------------------------------------------------------------------
# Infrastructure failures
# ---------------------------------------------------------------------------


def test_syntax_error_propagates() -> None:
    """Parse failure is infrastructure, not a validation result."""
    with pytest.raises(SyntaxError):
        analyze_source("def (broken", source_identity="bad.py")
