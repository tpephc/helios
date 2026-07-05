# features/win_rate_21d/manifest.py
"""Manifest schema stub for win_rate_21d producer builds.

This module anchors TM-078 from the Executable Governance Navigation
Document.  It defines the SD-A2-5 manifest v1.0.0 shape using stdlib
dataclasses only (no third-party dependency).

PR-1 intentionally provides schema shape, schema-level validation, and
canonical JSON serialization, but does not populate real build-time values.

Governance sources:
    SD-A2-5 N-A2-5-6 (LOCKED at 23b249b): manifest schema v1.0.0.
    SD-A2-8 N-A2-8-1 (LOCKED at 9963d72): producer table dtypes.
    Executable Governance Navigation Document (commit a110500).

Design notes:
    - ``validate()`` is the sole public validation entry point.  Its body
      is decomposed into private ``_validate_*`` sub-methods for
      readability; the semantics are unchanged (fail-fast, single
      ``ValueError`` raise on the first violation).
    - Canonical JSON serialization is decomposed into ``to_dict()`` and
      ``to_canonical_json()`` so that future callers can hash the dict
      representation without re-parsing JSON.
    - Collection types on the schema use ``tuple`` and ``Mapping`` to
      preserve immutability semantics matching ``frozen=True`` dataclasses.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any, Final

from features.win_rate_21d.constants import (
    FEATURE_ID,
    MANIFEST_SCHEMA_VERSION,
    MIN_CROSS_SECTION_OBS_PER_DATE,
    PRODUCER_TABLE_NAME,
    SHA1_HEX_LEN,
    SHA256_HEX_LEN,
)

# ─────────────────────────────────────────────────────────────
# Format regexes (built from hex-length constants)
# ─────────────────────────────────────────────────────────────

SHA256_RE: Final[re.Pattern[str]] = re.compile(
    rf"^[0-9a-f]{{{SHA256_HEX_LEN}}}$"
)

# Issue 1 disposition — forward-compatible git commit SHA.
# Accepts current git default (SHA-1, 40 hex) and post-transition git
# (SHA-256, 64 hex).  SD-A2-5 does not lock the length; this regex avoids
# a governance amendment when git migrates.
# OVERRIDE HERE if you want strict SHA-1 or strict SHA-256 only.
GIT_SHA_RE: Final[re.Pattern[str]] = re.compile(
    rf"^[0-9a-f]{{{SHA1_HEX_LEN}}}$|^[0-9a-f]{{{SHA256_HEX_LEN}}}$"
)

SNAPSHOT_ID_RE: Final[re.Pattern[str]] = re.compile(
    r"^win_rate_21d_\d{8}T\d{6}Z_[0-9a-f]{12}$"
)

SEMVER_RE: Final[re.Pattern[str]] = re.compile(r"^\d+\.\d+\.\d+$")


# ─────────────────────────────────────────────────────────────
# Manifest schema (SD-A2-5 N-A2-5-6 v1.0.0)
# ─────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ProducerIdentity:
    """Producer identity block required by SD-A2-5 manifest v1.0.0.

    Issue 3 disposition:
        ``producer_id`` MUST equal the SD-A2-2 locked producer table name
        (``PRODUCER_TABLE_NAME``).  The redundancy is intentional; it makes
        the manifest self-describing without an external config lookup.
    """

    producer_id: str
    producer_code_sha: str
    producer_config_hash: str
    repository_clean: bool


@dataclass(frozen=True, slots=True)
class CanonicalizedEnvironment:
    """Canonicalized process environment values.

    Locked by SD-A2-5 N-A2-5-5: ``LC_ALL=C.UTF-8``, ``TZ=UTC``,
    ``PYTHONHASHSEED=0``.
    """

    LC_ALL: str
    TZ: str
    PYTHONHASHSEED: str


@dataclass(frozen=True, slots=True)
class ProducerEnvironment:
    """Producer execution environment block."""

    python_version: str
    os_platform: str
    arrow_library_version: str
    polars_version: str | None
    canonicalized: CanonicalizedEnvironment


@dataclass(frozen=True, slots=True)
class InputSnapshot:
    """Direct upstream snapshot reference."""

    role: str
    snapshot_id: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class ParquetGovernanceFixedConfig:
    """Governance-fixed Parquet writer invariants from SD-A2-5 N-A2-5-2."""

    compression: str
    coerce_timestamps: str
    allow_truncated_timestamps: bool
    use_dictionary: bool
    column_sort: str
    wall_clock_metadata: bool


@dataclass(frozen=True, slots=True)
class ParquetWriterConfig:
    """Parquet writer configuration block.

    ``governance_fixed`` values are locked by SD-A2-5 N-A2-5-2.
    ``recorded`` values are preserved for reproducibility but are not
    governance-fixed.  The recorded block is typed as ``Mapping`` to
    signal that its values MUST NOT be mutated after manifest construction.
    """

    governance_fixed: ParquetGovernanceFixedConfig
    recorded: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ManifestV1:
    """SD-A2-5 manifest schema v1.0.0.

    Required top-level fields: 19, matching SD-A2-5 N-A2-5-6.

    Collection field types:
        - ``input_snapshots`` uses ``tuple`` for immutability.
        - ``column_names`` uses ``tuple`` for immutability and canonical
          ordering.
        - ``column_dtypes`` uses ``Mapping`` for read-only-by-convention
          semantics.
    """

    manifest_format: str
    manifest_schema_version: str
    producer_version: str
    snapshot_id: str
    content_hash: str
    content_hash_algorithm: str
    feature: str
    producer_identity: ProducerIdentity
    producer_environment: ProducerEnvironment
    build_utc_timestamp: str
    build_host: str
    input_snapshots: tuple[InputSnapshot, ...]
    row_count: int
    column_names: tuple[str, ...]
    column_dtypes: Mapping[str, str]
    min_cross_section_obs_per_date: int
    parquet_writer_config: ParquetWriterConfig
    random_seed: int | None

    # ─────────────────────────────────────────────────────
    # Public validation entry point
    # ─────────────────────────────────────────────────────

    def validate(self) -> None:
        """Validate all schema-level invariants available at PR-1 scope.

        Fail-fast semantics: the first violation raises ``ValueError``.
        The body is decomposed into private ``_validate_*`` sub-methods
        for readability; semantic behavior is unchanged from the
        pre-decomposition version.

        Raises:
            ValueError: on any schema-level invariant violation.
        """
        self._validate_schema()
        self._validate_identity()
        self._validate_hash_fields()
        self._validate_environment()
        self._validate_output_schema()

    # ─────────────────────────────────────────────────────
    # Private sub-validators
    # ─────────────────────────────────────────────────────

    def _validate_schema(self) -> None:
        """Validate top-level schema shape and format constants."""
        if self.manifest_format != "json":
            raise ValueError("manifest_format must equal 'json'")
        if self.manifest_schema_version != MANIFEST_SCHEMA_VERSION:
            raise ValueError(
                f"manifest_schema_version must equal "
                f"{MANIFEST_SCHEMA_VERSION!r}"
            )
        if not SEMVER_RE.fullmatch(self.producer_version):
            raise ValueError("producer_version must be semver")
        if not SNAPSHOT_ID_RE.fullmatch(self.snapshot_id):
            raise ValueError("snapshot_id does not match SD-A2-5 format")
        if self.content_hash_algorithm != "sha256":
            raise ValueError("content_hash_algorithm must equal 'sha256'")
        if self.feature != FEATURE_ID:
            raise ValueError(f"feature must equal {FEATURE_ID!r}")

    def _validate_identity(self) -> None:
        """Validate producer identity block against SD-A2-2 and formats."""
        # Issue 3 enforcement: producer_id == SD-A2-2 locked identity.
        if self.producer_identity.producer_id != PRODUCER_TABLE_NAME:
            raise ValueError(
                "producer_identity.producer_id must equal "
                f"PRODUCER_TABLE_NAME ({PRODUCER_TABLE_NAME!r}) per SD-A2-2"
            )

        # Issue 1: git commit SHA (SHA-1 40 hex OR SHA-256 64 hex).
        if not GIT_SHA_RE.fullmatch(
            self.producer_identity.producer_code_sha
        ):
            raise ValueError(
                "producer_code_sha must be a git commit SHA "
                f"({SHA1_HEX_LEN}-hex SHA-1 or "
                f"{SHA256_HEX_LEN}-hex SHA-256)"
            )

        # Issue 2: producer_config_hash format check.
        # SD-A2-5 N-A2-5-6 annotates this field as
        # 'SHA-256 of resolved config as canonical JSON'.
        if not SHA256_RE.fullmatch(
            self.producer_identity.producer_config_hash
        ):
            raise ValueError(
                "producer_config_hash must be "
                f"{SHA256_HEX_LEN} lowercase hex characters"
            )

    def _validate_hash_fields(self) -> None:
        """Validate content_hash and input_snapshot content_hashes."""
        if not SHA256_RE.fullmatch(self.content_hash):
            raise ValueError(
                "content_hash must be "
                f"{SHA256_HEX_LEN} lowercase hex characters"
            )
        for item in self.input_snapshots:
            if not SHA256_RE.fullmatch(item.content_hash):
                raise ValueError(
                    "input_snapshots[*].content_hash must be "
                    f"{SHA256_HEX_LEN} lowercase hex characters"
                )

    def _validate_environment(self) -> None:
        """Validate environment canonicalization per SD-A2-5 N-A2-5-5."""
        canonicalized = self.producer_environment.canonicalized
        if canonicalized.LC_ALL != "C.UTF-8":
            raise ValueError(
                "producer_environment.canonicalized.LC_ALL must be 'C.UTF-8'"
            )
        if canonicalized.TZ != "UTC":
            raise ValueError(
                "producer_environment.canonicalized.TZ must be 'UTC'"
            )
        if canonicalized.PYTHONHASHSEED != "0":
            raise ValueError(
                "producer_environment.canonicalized.PYTHONHASHSEED "
                "must be '0'"
            )

    def _validate_output_schema(self) -> None:
        """Validate row count and column schema shape."""
        if self.row_count < 0:
            raise ValueError("row_count must be non-negative")
        if not self.column_names:
            raise ValueError("column_names must not be empty")
        if set(self.column_names) != set(self.column_dtypes):
            raise ValueError(
                "column_names and column_dtypes keys mismatch"
            )
        if (
            self.min_cross_section_obs_per_date
            != MIN_CROSS_SECTION_OBS_PER_DATE
        ):
            raise ValueError(
                f"min_cross_section_obs_per_date must equal "
                f"{MIN_CROSS_SECTION_OBS_PER_DATE}"
            )

    # ─────────────────────────────────────────────────────
    # Serialization
    # ─────────────────────────────────────────────────────

    def to_dict(self) -> Mapping[str, Any]:
        """Serialize to a plain Python dict, validated.

        The dict is suitable for direct hashing (e.g., ``sha256`` over a
        stable serialization) without going through JSON parse/serialize
        round-trips.
        """
        self.validate()
        return asdict(self)

    def to_canonical_json(self) -> str:
        """Serialize to canonical JSON text, validated.

        Determinism guarantees:
            - ``sort_keys=True`` for stable key ordering across builds.
            - ``separators=(',', ':')`` for no spurious whitespace.
            - ``ensure_ascii=False`` to preserve UTF-8 for the caller.
            - Trailing newline for POSIX text-file convention.

        The output does NOT include any wall-clock or hostname derived
        entropy beyond what is already stored in the manifest fields.
        """
        return json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ) + "\n"


# ─────────────────────────────────────────────────────────────
# Config hash shell (Issue 2)
# ─────────────────────────────────────────────────────────────


def canonical_config_hash(config: Mapping[str, Any]) -> str:
    """Compute canonical SHA-256 hash of a producer config dict.

    PR-1 shell only.

    Rationale for shell status:
        The producer config surface (what fields, what nested types,
        what canonical encoding for ``date`` / ``Enum`` / ``Literal``)
        is not yet finalized.  Implementing this before the producer
        body exists would either lock a canonicalization scheme too
        early or create a vacuous implementation that silently accepts
        any input.

    Real implementation lands in the PR that finalizes the producer
    config surface.
    """
    raise NotImplementedError(
        "canonical_config_hash pending producer config surface finalization"
    )