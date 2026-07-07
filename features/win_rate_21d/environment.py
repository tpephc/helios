# features/win_rate_21d/environment.py
"""Process environment verification for win_rate_21d.

Purpose:
    PR-1 asserts canonical environment values (``LC_ALL``, ``TZ``,
    ``PYTHONHASHSEED``) at the manifest layer (see
    ``manifest.CanonicalizedEnvironment`` and
    ``ManifestV1._validate_environment``), but the README explicitly
    notes that no code actually verifies these values are set at
    process start.  This module is the extension point the README
    reserves.

Governance (Q-PR2A-R3, Q-PR2A-R8):
    - This module is a programmatic API.  PR-2A does not introduce a
      ``__main__`` entry point or wrapper script; those are deferred
      to a later PR that lands process-entry contracts.
    - Verification and policy are strictly separated (Q-PR2A-epsilon):
      ``verify_process_environment`` collects facts and returns an
      immutable ``EnvironmentReport``.  It does not raise on invalid
      environment content, does not log, and does not mutate
      ``os.environ``.  Callers decide whether to raise, warn, or
      translate to an exit code.
    - The canonical field set is fixed by ``SD-A2-5 N-A2-5-5`` and
      mirrored by ``manifest.CanonicalizedEnvironment``:
      ``LC_ALL='C.UTF-8'``, ``TZ='UTC'``, ``PYTHONHASHSEED='0'``.
      This module intentionally does NOT check the Python interpreter
      version: ``pyproject.toml`` (``requires-python = ">=3.12"``)
      already enforces that at install time via uv.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final

__all__ = [
    "EnvironmentReport",
    "EnvironmentVerificationError",
    "verify_process_environment",
    "CANONICAL_ENVIRONMENT",
]


# Canonical environment values sourced from SD-A2-5 N-A2-5-5 and mirrored
# in ``manifest.CanonicalizedEnvironment``.  Keys and values are exact
# string matches; any drift here is a manifest-schema violation waiting
# to happen and must be caught at review time.
CANONICAL_ENVIRONMENT: Final[Mapping[str, str]] = MappingProxyType({
    "LC_ALL": "C.UTF-8",
    "TZ": "UTC",
    "PYTHONHASHSEED": "0",
})


@dataclass(frozen=True, slots=True)
class EnvironmentReport:
    """Immutable verification result.

    Shared source of truth for programmatic callers, tests, and any
    future diagnostics.  Callers decide policy: raise, warn, log, or
    surface as an exit code (Q-PR2A-epsilon, Q-PR2A-R8).

    Immutability contract (PR-2A review Blocking Issue 2):
        ``observed`` is a ``MappingProxyType`` view, not a plain
        ``dict``.  Attempting ``report.observed[key] = value`` raises
        ``TypeError``.  Combined with ``frozen=True`` on the dataclass
        itself, the report is fully immutable at both the binding level
        and the container level.

    Attributes:
        observed: Read-only snapshot of the observed values for the
            canonical environment keys at verification time.  A key
            with value ``None`` indicates the variable was unset.
        violations: Tuple of human-readable violation messages, one
            per canonical field that failed.  Empty tuple means the
            environment matches ``CANONICAL_ENVIRONMENT`` exactly.
    """

    observed: Mapping[str, str | None]
    violations: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_valid(self) -> bool:
        """Whether the observed environment matches canonical values."""
        return len(self.violations) == 0


class EnvironmentVerificationError(RuntimeError):
    """Raised by a policy layer (never by ``verify_process_environment``).

    Carries the immutable ``EnvironmentReport`` so downstream consumers
    share a single source of truth for violation content.  The exception
    message is intentionally short; callers that need violation detail
    read ``exc.report.violations`` directly rather than parsing the
    exception string (PR-2A review NB2).
    """

    def __init__(self, report: EnvironmentReport) -> None:
        self.report = report
        super().__init__("process environment verification failed")


def verify_process_environment() -> EnvironmentReport:
    """Collect facts about the current process environment.

    Reads the canonical environment keys from ``os.environ`` and
    compares each observed value against ``CANONICAL_ENVIRONMENT``.
    Does NOT mutate ``os.environ``, does not modify any interpreter
    state, and does not raise for environment content.  Programming
    errors (e.g., a corrupted ``CANONICAL_ENVIRONMENT`` constant) may
    still surface as their native exception types; those are not
    caught here.

    Returns:
        EnvironmentReport: immutable snapshot plus a violation tuple.
        ``report.is_valid`` is ``True`` iff every canonical field
        matches exactly.

    Scope (PR-2A review NB4):
        This function verifies only process environment variables.
        Filesystem availability, locale database presence, timezone
        database presence, DuckDB writeability, and other runtime
        capabilities are intentionally out of scope for this module.
        Those verifications belong in their respective PF-B pre-flight
        checks (see, for example, ``pre_flight.pf_b6_duckdb_writeability_check``).

        Python interpreter version is also NOT checked here:
        ``pyproject.toml`` (``requires-python = ">=3.12"``) enforces
        version at install time via uv, and duplicating that check at
        runtime would create a governance surface with no owner.
    """
    observed: dict[str, str | None] = {}
    violations: list[str] = []

    for key, required in CANONICAL_ENVIRONMENT.items():
        actual = os.environ.get(key)
        observed[key] = actual
        if actual != required:
            if actual is None:
                violations.append(
                    f"{key} is unset; canonical value is {required!r}"
                )
            else:
                violations.append(
                    f"{key} = {actual!r}, canonical value is {required!r}"
                )

    return EnvironmentReport(
        observed=MappingProxyType(observed),
        violations=tuple(violations),
    )
