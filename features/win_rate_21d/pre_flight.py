# features/win_rate_21d/pre_flight.py
"""PF-B pre-flight framework for win_rate_21d.

PR-1 implements only checks that are fully evaluable from locked constants:

    PF-B3: MIN_CROSS_SECTION_OBS_PER_DATE consistency
    PF-B4: WINDOW / MIN_OBS consistency

Other PF-B checks are explicit shells that raise ``NotImplementedError``.
They MUST NOT return pass vacuously — enforced by
tests/features/win_rate_21d/test_pre_flight_shell.py.

Governance source: SD-A2-3 LOCKED at 40c0cd1.

Severity model (Issue F):
    ``PreFlightResult.severity`` captures the graded outcome of a check.
    PR-1 uses ``INFO`` on pass and ``ERROR`` on fail.  Later PRs (in
    particular PF-L checks with non-fatal drift indicators such as
    Parquet ``recorded`` config differences) can emit ``WARNING`` without
    changing the dataclass shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from features.win_rate_21d.constants import (
    MIN_CROSS_SECTION_OBS_PER_DATE,
    MIN_OBS,
    WINDOW,
)


class PreFlightSeverity(str, Enum):
    """Severity level for a pre-flight check result.

    Values are strings so they serialize cleanly into manifest and log
    records without extra encoding.

    Semantic contract:
        - ``INFO``: check passed, no attention required.
        - ``WARNING``: check passed with an observation that should be
          reviewed but does not block the build.
        - ``ERROR``: check failed, build MUST NOT proceed.
    """

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class PreFlightResult:
    """Result of one pre-flight check.

    Attributes:
        check_id: Stable identifier used across logs and audit trails
            (e.g., ``"PF-B3"``).  Must match the identifier defined in
            SD-A2-3 or SD-A2-5.
        passed: Whether the check passed.  A passing result MAY still
            carry ``severity == WARNING``; a failing result MUST carry
            ``severity == ERROR``.
        severity: Graded outcome; see ``PreFlightSeverity``.
        message: Human-readable description of the result.  On failure,
            the message MUST include enough context to reproduce the
            failure without additional logging.
    """

    check_id: str
    passed: bool
    severity: PreFlightSeverity
    message: str


def pf_b1_scope_check() -> PreFlightResult:
    """PF-B1 requested-vs-materialized scope validation.

    Governance: SD-A2-3 defines this check as the SD-A2-1 rider closure
    gate for the DuckDB branch.  Materialized scope from
    ``listed_market_daily_price_adj`` must not materially broaden or
    shrink the requested scope.

    PR-1 status: shell.  Real implementation requires the scope resolver
    and the DuckDB read path, both landing in a later PR.
    """
    raise NotImplementedError(
        "PF-B1 pending scope resolver + DuckDB read path"
    )


def pf_b2_canonical_source_check() -> PreFlightResult:
    """PF-B2 canonical source validation.

    Governance: SD-A2-3 requires producer code reads only from the
    canonical PIT view.  Direct reads of the raw price table are
    FORBIDDEN and constitute a P0 lineage violation per spec §4.4.

    Verification is structural (AST-level or DuckDB EXPLAIN
    introspection), not string-level.  See spec §8.4 and Section 7 H17
    of the readiness document.

    PR-1 status: shell.  Real implementation requires the producer body
    to inspect.
    """
    raise NotImplementedError(
        "PF-B2 pending producer body implementation"
    )


def pf_b3_min_cross_section_check(
    observed_value: int = MIN_CROSS_SECTION_OBS_PER_DATE,
) -> PreFlightResult:
    """PF-B3 MIN_CROSS_SECTION_OBS_PER_DATE consistency check.

    Verifies that the observed producer-side constant matches the
    SD-A2-1 locked value of 30.  The default argument is the constant
    imported from ``features.win_rate_21d.constants``; explicit values
    are accepted to allow testing of mismatch cases.
    """
    expected = 30
    if observed_value != expected:
        return PreFlightResult(
            check_id="PF-B3",
            passed=False,
            severity=PreFlightSeverity.ERROR,
            message=(
                "MIN_CROSS_SECTION_OBS_PER_DATE mismatch: "
                f"expected {expected}, observed {observed_value}"
            ),
        )
    return PreFlightResult(
        check_id="PF-B3",
        passed=True,
        severity=PreFlightSeverity.INFO,
        message=(
            "MIN_CROSS_SECTION_OBS_PER_DATE matches SD-A2-1 "
            f"(value={expected})"
        ),
    )


def pf_b4_window_constants_check(
    observed_window: int = WINDOW,
    observed_min_obs: int = MIN_OBS,
) -> PreFlightResult:
    """PF-B4 WINDOW / MIN_OBS consistency check.

    Verifies that the observed WINDOW and MIN_OBS constants match
    SPEC_LOCKED v0.1.0 §3.6 (WINDOW=21, MIN_OBS=15).  Both defaults are
    imported from ``features.win_rate_21d.constants``; explicit values
    are accepted to allow testing of mismatch cases.
    """
    expected_window = 21
    expected_min_obs = 15
    window_ok = observed_window == expected_window
    min_obs_ok = observed_min_obs == expected_min_obs
    if not (window_ok and min_obs_ok):
        return PreFlightResult(
            check_id="PF-B4",
            passed=False,
            severity=PreFlightSeverity.ERROR,
            message=(
                "WINDOW/MIN_OBS mismatch: "
                f"expected (WINDOW={expected_window}, "
                f"MIN_OBS={expected_min_obs}), "
                f"observed (WINDOW={observed_window}, "
                f"MIN_OBS={observed_min_obs})"
            ),
        )
    return PreFlightResult(
        check_id="PF-B4",
        passed=True,
        severity=PreFlightSeverity.INFO,
        message=(
            "WINDOW and MIN_OBS match SPEC_LOCKED v0.1.0 §3.6 "
            f"(WINDOW={expected_window}, MIN_OBS={expected_min_obs})"
        ),
    )


def pf_b6_duckdb_writeability_check() -> PreFlightResult:
    """PF-B6 DuckDB target writeability check.

    Governance: SD-A2-3 requires the DuckDB file to be writable and the
    target table name to be free of lock contention at build time.
    Does NOT perform trial writes (which would violate the "no side
    effects on pre-flight failure" contract).

    PR-1 status: shell.  Real implementation requires the DuckDB
    integration path in a later PR.
    """
    raise NotImplementedError(
        "PF-B6 pending DuckDB integration path"
    )