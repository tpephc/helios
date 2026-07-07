# tests/features/win_rate_21d/test_environment.py
"""Tests for ``features.win_rate_21d.environment``.

Verifies:
    - ``verify_process_environment`` returns an ``EnvironmentReport``
      (never raises for environment content).
    - It does not mutate ``os.environ``.
    - Missing / mismatched canonical variables produce violations,
      matching values produce ``is_valid == True``.
    - ``EnvironmentReport`` is immutable.
    - ``EnvironmentVerificationError`` carries the report.
    - The canonical environment values match ``manifest.py`` exactly
      (governance mirror invariant per Q-PR2A-R3).
"""

from __future__ import annotations

import os
from types import MappingProxyType

import pytest

from features.win_rate_21d.environment import (
    CANONICAL_ENVIRONMENT,
    EnvironmentReport,
    EnvironmentVerificationError,
    verify_process_environment,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _set_canonical(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in CANONICAL_ENVIRONMENT.items():
        monkeypatch.setenv(key, value)


# ---------------------------------------------------------------------------
# Return-type / side-effect invariants (Q-PR2A-epsilon)
# ---------------------------------------------------------------------------


def test_returns_environment_report(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_canonical(monkeypatch)
    report = verify_process_environment()
    assert isinstance(report, EnvironmentReport)


def test_does_not_mutate_environ(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_canonical(monkeypatch)
    before = dict(os.environ)
    verify_process_environment()
    after = dict(os.environ)
    assert before == after


def test_does_not_raise_on_invalid_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Q-PR2A-epsilon: verification returns; policy is caller's job."""
    for key in CANONICAL_ENVIRONMENT:
        monkeypatch.delenv(key, raising=False)
    # Must return, not raise.
    report = verify_process_environment()
    assert not report.is_valid


# ---------------------------------------------------------------------------
# Content invariants
# ---------------------------------------------------------------------------


def test_canonical_environment_produces_no_violations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_canonical(monkeypatch)
    report = verify_process_environment()
    assert report.is_valid
    assert report.violations == ()
    # MappingProxyType == dict comparison is delegated to the underlying
    # mapping, so this equality holds.
    assert dict(report.observed) == dict(CANONICAL_ENVIRONMENT)


def test_missing_lc_all_produces_violation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_canonical(monkeypatch)
    monkeypatch.delenv("LC_ALL", raising=False)
    report = verify_process_environment()
    assert not report.is_valid
    assert any("LC_ALL" in v for v in report.violations)
    assert report.observed["LC_ALL"] is None


def test_wrong_tz_produces_violation(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_canonical(monkeypatch)
    monkeypatch.setenv("TZ", "Asia/Taipei")
    report = verify_process_environment()
    assert not report.is_valid
    assert any("TZ" in v and "Asia/Taipei" in v for v in report.violations)


def test_wrong_hashseed_produces_violation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_canonical(monkeypatch)
    monkeypatch.setenv("PYTHONHASHSEED", "42")
    report = verify_process_environment()
    assert not report.is_valid
    assert any(
        "PYTHONHASHSEED" in v and "42" in v for v in report.violations
    )


def test_multiple_violations_are_all_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All canonical fields are checked; the report is not fail-fast.

    Diagnostic parity with ``verify_rider_closing_checks_are_real``
    (which aggregates per Q-PR2A-D1).
    """
    for key in CANONICAL_ENVIRONMENT:
        monkeypatch.delenv(key, raising=False)
    report = verify_process_environment()
    assert len(report.violations) == len(CANONICAL_ENVIRONMENT)


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


def test_environment_report_is_frozen() -> None:
    report = EnvironmentReport(observed=MappingProxyType({}), violations=())
    with pytest.raises(Exception):  # FrozenInstanceError subclass of Exception
        report.violations = ("x",)  # type: ignore[misc]


def test_environment_report_observed_is_immutable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PR-2A review Blocking Issue 2: report.observed is a read-only view.

    A plain ``dict`` would be mutable even inside a frozen dataclass:
    ``report.observed[key] = value`` would silently succeed and corrupt
    the immutable-report contract.  ``MappingProxyType`` forbids item
    assignment at the container level.
    """
    _set_canonical(monkeypatch)
    report = verify_process_environment()
    with pytest.raises(TypeError):
        report.observed["LC_ALL"] = "BAD"  # type: ignore[index]
    with pytest.raises(TypeError):
        del report.observed["LC_ALL"]  # type: ignore[attr-defined]


def test_canonical_environment_module_constant_is_immutable() -> None:
    """The module-level ``CANONICAL_ENVIRONMENT`` is also read-only.

    Prevents accidental mutation of the SD-A2-5 mirror at import time by
    a downstream module.
    """
    with pytest.raises(TypeError):
        CANONICAL_ENVIRONMENT["LC_ALL"] = "BAD"  # type: ignore[index]


# ---------------------------------------------------------------------------
# Error type
# ---------------------------------------------------------------------------


def test_verification_error_carries_report() -> None:
    report = EnvironmentReport(
        observed=MappingProxyType(
            {"LC_ALL": None, "TZ": None, "PYTHONHASHSEED": None}
        ),
        violations=(
            "LC_ALL is unset; canonical value is 'C.UTF-8'",
            "TZ is unset; canonical value is 'UTC'",
            "PYTHONHASHSEED is unset; canonical value is '0'",
        ),
    )
    exc = EnvironmentVerificationError(report)
    # Report is preserved identically for downstream consumers.
    assert exc.report is report
    assert exc.report.violations == report.violations
    # Message is intentionally short (PR-2A review NB2); detail lives on
    # exc.report, not in the string form.
    assert str(exc) == "process environment verification failed"


# ---------------------------------------------------------------------------
# Governance mirror invariant (Q-PR2A-R3)
# ---------------------------------------------------------------------------


def test_canonical_environment_matches_manifest_schema() -> None:
    """``CANONICAL_ENVIRONMENT`` MUST mirror ``CanonicalizedEnvironment``.

    Both are downstream of SD-A2-5 N-A2-5-5.  Drift between the two
    would mean a build could pass ``verify_process_environment`` and
    still fail ``ManifestV1._validate_environment`` (or vice versa),
    which would be a governance-level inconsistency.
    """
    from dataclasses import fields

    from features.win_rate_21d.manifest import CanonicalizedEnvironment

    manifest_fields = {f.name for f in fields(CanonicalizedEnvironment)}
    canonical_keys = set(CANONICAL_ENVIRONMENT.keys())
    assert manifest_fields == canonical_keys, (
        f"CANONICAL_ENVIRONMENT keys {sorted(canonical_keys)} do not "
        f"match manifest CanonicalizedEnvironment fields "
        f"{sorted(manifest_fields)}"
    )
