# tests/features/win_rate_21d/test_pre_flight_shell.py
"""Tests for PR-1 PF-B shell behavior.

Verifies:
    - PF-B3 and PF-B4 (fully implementable at PR-1) pass with locked
      constants and fail with wrong constants.
    - Severity model: passing checks are INFO, failing checks are ERROR.
    - PF-B1, PF-B2, PF-B6 (shells) raise NotImplementedError rather
      than returning a vacuous PASS.
"""

from collections.abc import Callable
from datetime import date

import pytest

from features.win_rate_21d.build_types import (
    BuildScope,
    PreFlightContext,
    ProducerContext,
)
from features.win_rate_21d.pre_flight import (
    PreFlightResult,
    PreFlightSeverity,
    pf_b1_scope_check,
    pf_b3_min_cross_section_check,
    pf_b4_window_constants_check,
    pf_b6_duckdb_writeability_check,
)


def test_pf_b3_passes_with_locked_constant() -> None:
    result = pf_b3_min_cross_section_check()
    assert result.check_id == "PF-B3"
    assert result.passed is True
    assert result.severity is PreFlightSeverity.INFO


def test_pf_b3_fails_with_wrong_constant() -> None:
    result = pf_b3_min_cross_section_check(observed_value=29)
    assert result.check_id == "PF-B3"
    assert result.passed is False
    assert result.severity is PreFlightSeverity.ERROR
    assert "29" in result.message


def test_pf_b4_passes_with_locked_constants() -> None:
    result = pf_b4_window_constants_check()
    assert result.check_id == "PF-B4"
    assert result.passed is True
    assert result.severity is PreFlightSeverity.INFO


def test_pf_b4_fails_with_wrong_window() -> None:
    result = pf_b4_window_constants_check(observed_window=20)
    assert result.check_id == "PF-B4"
    assert result.passed is False
    assert result.severity is PreFlightSeverity.ERROR
    assert "20" in result.message


def test_pf_b4_fails_with_wrong_min_obs() -> None:
    result = pf_b4_window_constants_check(observed_min_obs=14)
    assert result.check_id == "PF-B4"
    assert result.passed is False
    assert result.severity is PreFlightSeverity.ERROR
    assert "14" in result.message


def test_pre_flight_severity_enum_values() -> None:
    """Enum string values must serialize cleanly for manifests and logs."""
    assert PreFlightSeverity.INFO.value == "INFO"
    assert PreFlightSeverity.WARNING.value == "WARNING"
    assert PreFlightSeverity.ERROR.value == "ERROR"


@pytest.mark.parametrize(
    "check",
    [
        pf_b1_scope_check,
        pf_b6_duckdb_writeability_check,
    ],
)
def test_pf_b_shells_do_not_pass_vacuously(
    check: Callable[[PreFlightContext], PreFlightResult],
) -> None:
    """A shell MUST raise NotImplementedError rather than return PASS.

    Guardrail against a shell being replaced by a silent
    ``return PreFlightResult(check_id=..., passed=True, ...)``
    that would misrepresent implementation status as PASS.
    """
    context = PreFlightContext(
        scope=BuildScope(
            requested_start=date(2020, 1, 2),
            requested_end=date(2020, 1, 10),
        ),
        producer_context=ProducerContext(),
    )

    with pytest.raises(NotImplementedError):
        check(context)