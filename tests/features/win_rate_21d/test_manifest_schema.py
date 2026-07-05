# tests/features/win_rate_21d/test_manifest_schema.py
"""Tests for SD-A2-5 manifest schema stub.

Coverage:
    - Valid manifest passes schema validation.
    - Canonical JSON is deterministic and terminates with newline.
    - ``to_dict()`` and ``to_canonical_json()`` are consistent.
    - min_cross_section_obs_per_date lock enforced.
    - producer_id lock enforced (Issue 3 disposition).
    - producer_code_sha accepts SHA-1 (40 hex) and SHA-256 (64 hex)
      (Issue 1 disposition: forward-compat).
    - producer_config_hash must be SHA-256 (Issue 2 disposition).
    - Sub-validator private methods can be exercised individually and
      preserve fail-fast semantics.
    - canonical_config_hash shell raises NotImplementedError.
"""

from dataclasses import replace

import pytest

from features.win_rate_21d.manifest import (
    CanonicalizedEnvironment,
    InputSnapshot,
    ManifestV1,
    ParquetGovernanceFixedConfig,
    ParquetWriterConfig,
    ProducerEnvironment,
    ProducerIdentity,
    canonical_config_hash,
)


def _valid_manifest() -> ManifestV1:
    content_hash = "a" * 64
    return ManifestV1(
        manifest_format="json",
        manifest_schema_version="1.0.0",
        producer_version="0.1.0",
        snapshot_id=f"win_rate_21d_20260705T010203Z_{content_hash[:12]}",
        content_hash=content_hash,
        content_hash_algorithm="sha256",
        feature="win_rate_21d",
        producer_identity=ProducerIdentity(
            producer_id="win_rate_21d_cross_section_median",
            producer_code_sha="b" * 40,
            producer_config_hash="c" * 64,
            repository_clean=True,
        ),
        producer_environment=ProducerEnvironment(
            python_version="3.13.0",
            os_platform="Linux-test",
            arrow_library_version="pyarrow==0.0.0",
            polars_version=None,
            canonicalized=CanonicalizedEnvironment(
                LC_ALL="C.UTF-8",
                TZ="UTC",
                PYTHONHASHSEED="0",
            ),
        ),
        build_utc_timestamp="2026-07-05T01:02:03Z",
        build_host="nexus",
        input_snapshots=(
            InputSnapshot(
                role="listed_market_daily_price_adj",
                snapshot_id=(
                    "listed_market_daily_price_adj_"
                    "20260705T000000Z_abc123abc123"
                ),
                content_hash="d" * 64,
            ),
        ),
        row_count=0,
        column_names=(
            "date",
            "median_daily_return",
            "n_obs_cross_section",
            "source_snapshot_id",
        ),
        column_dtypes={
            "date": "date32[day]",
            "median_daily_return": "float64",
            "n_obs_cross_section": "uint16",
            "source_snapshot_id": "string",
        },
        min_cross_section_obs_per_date=30,
        parquet_writer_config=ParquetWriterConfig(
            governance_fixed=ParquetGovernanceFixedConfig(
                compression="zstd",
                coerce_timestamps="us",
                allow_truncated_timestamps=False,
                use_dictionary=True,
                column_sort="alphabetical",
                wall_clock_metadata=False,
            ),
            recorded={
                "compression_level": 3,
                "row_group_size": 65536,
                "data_page_version": "2.0",
            },
        ),
        random_seed=None,
    )


# ─────────────────────────────────────────────────────────────
# Baseline
# ─────────────────────────────────────────────────────────────


def test_manifest_schema_validates() -> None:
    _valid_manifest().validate()


def test_manifest_canonical_json_is_deterministic() -> None:
    manifest = _valid_manifest()
    first = manifest.to_canonical_json()
    second = manifest.to_canonical_json()
    assert first == second
    assert first.endswith("\n")


def test_manifest_canonical_json_uses_sorted_keys() -> None:
    """Determinism check: keys appear in alphabetical order at every level."""
    import json as _json

    text = _valid_manifest().to_canonical_json()
    parsed = _json.loads(text)
    reserialized = _json.dumps(
        parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    assert text.rstrip("\n") == reserialized


def test_manifest_to_dict_matches_json_roundtrip() -> None:
    """``to_dict()`` output should JSON-serialize to the canonical text."""
    import json as _json

    manifest = _valid_manifest()
    as_dict = manifest.to_dict()
    as_json = _json.dumps(
        as_dict, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ) + "\n"
    assert as_json == manifest.to_canonical_json()


# ─────────────────────────────────────────────────────────────
# min_cross_section_obs_per_date lock
# ─────────────────────────────────────────────────────────────


def test_manifest_requires_min_cross_section_30() -> None:
    manifest = _valid_manifest()
    bad = replace(manifest, min_cross_section_obs_per_date=29)
    with pytest.raises(ValueError, match="min_cross_section_obs_per_date"):
        bad.validate()


# ─────────────────────────────────────────────────────────────
# Issue 3 disposition tests (producer_id lock)
# ─────────────────────────────────────────────────────────────


def test_manifest_producer_id_must_match_table_name() -> None:
    manifest = _valid_manifest()
    bad_identity = replace(
        manifest.producer_identity,
        producer_id="not_the_table_name",
    )
    bad = replace(manifest, producer_identity=bad_identity)
    with pytest.raises(ValueError, match="producer_id"):
        bad.validate()


# ─────────────────────────────────────────────────────────────
# Issue 1 disposition tests (producer_code_sha format)
# ─────────────────────────────────────────────────────────────


def test_manifest_accepts_sha1_producer_code_sha() -> None:
    """Current git default: SHA-1 (40 hex characters)."""
    manifest = _valid_manifest()
    good_identity = replace(
        manifest.producer_identity,
        producer_code_sha="0" * 40,
    )
    good = replace(manifest, producer_identity=good_identity)
    good.validate()


def test_manifest_accepts_sha256_producer_code_sha() -> None:
    """Forward-compat: git SHA-256 transition (64 hex characters)."""
    manifest = _valid_manifest()
    good_identity = replace(
        manifest.producer_identity,
        producer_code_sha="0" * 64,
    )
    good = replace(manifest, producer_identity=good_identity)
    good.validate()


def test_manifest_rejects_wrong_length_producer_code_sha() -> None:
    manifest = _valid_manifest()
    for bad_length in (39, 41, 63, 65):
        bad_identity = replace(
            manifest.producer_identity,
            producer_code_sha="a" * bad_length,
        )
        bad = replace(manifest, producer_identity=bad_identity)
        with pytest.raises(ValueError, match="producer_code_sha"):
            bad.validate()


def test_manifest_rejects_non_hex_producer_code_sha() -> None:
    manifest = _valid_manifest()
    bad_identity = replace(
        manifest.producer_identity,
        producer_code_sha="Z" * 40,
    )
    bad = replace(manifest, producer_identity=bad_identity)
    with pytest.raises(ValueError, match="producer_code_sha"):
        bad.validate()


# ─────────────────────────────────────────────────────────────
# Issue 2 disposition tests (producer_config_hash format)
# ─────────────────────────────────────────────────────────────


def test_manifest_rejects_invalid_producer_config_hash() -> None:
    manifest = _valid_manifest()
    bad_identity = replace(
        manifest.producer_identity,
        producer_config_hash="c" * 63,
    )
    bad = replace(manifest, producer_identity=bad_identity)
    with pytest.raises(ValueError, match="producer_config_hash"):
        bad.validate()


def test_canonical_config_hash_is_shell() -> None:
    with pytest.raises(NotImplementedError):
        canonical_config_hash({"any": "input"})


# ─────────────────────────────────────────────────────────────
# Environment canonicalization enforcement
# ─────────────────────────────────────────────────────────────


def test_manifest_rejects_non_canonical_locale() -> None:
    manifest = _valid_manifest()
    bad_env = replace(
        manifest.producer_environment.canonicalized,
        LC_ALL="en_US.UTF-8",
    )
    bad_producer_env = replace(
        manifest.producer_environment, canonicalized=bad_env
    )
    bad = replace(manifest, producer_environment=bad_producer_env)
    with pytest.raises(ValueError, match="LC_ALL"):
        bad.validate()


def test_manifest_rejects_non_utc_timezone() -> None:
    manifest = _valid_manifest()
    bad_env = replace(
        manifest.producer_environment.canonicalized,
        TZ="Asia/Taipei",
    )
    bad_producer_env = replace(
        manifest.producer_environment, canonicalized=bad_env
    )
    bad = replace(manifest, producer_environment=bad_producer_env)
    with pytest.raises(ValueError, match="TZ"):
        bad.validate()


def test_manifest_rejects_non_zero_hash_seed() -> None:
    manifest = _valid_manifest()
    bad_env = replace(
        manifest.producer_environment.canonicalized,
        PYTHONHASHSEED="1",
    )
    bad_producer_env = replace(
        manifest.producer_environment, canonicalized=bad_env
    )
    bad = replace(manifest, producer_environment=bad_producer_env)
    with pytest.raises(ValueError, match="PYTHONHASHSEED"):
        bad.validate()


# ─────────────────────────────────────────────────────────────
# Sub-validator decomposition tests (Issue B, option α)
# ─────────────────────────────────────────────────────────────


def test_sub_validators_can_be_called_directly() -> None:
    """Private ``_validate_*`` methods should be callable and pass on valid input.

    This documents the decomposition and lets future tests target
    specific validators without going through the full ``validate()``
    orchestration.
    """
    manifest = _valid_manifest()
    manifest._validate_schema()
    manifest._validate_identity()
    manifest._validate_hash_fields()
    manifest._validate_environment()
    manifest._validate_output_schema()


def test_validate_is_fail_fast() -> None:
    """When multiple invariants are violated, only the first-checked error is raised.

    The check order is: schema, identity, hash_fields, environment,
    output_schema.  A manifest with both a schema error and a hash error
    should raise the schema error first.
    """
    manifest = _valid_manifest()
    # Break both manifest_format (schema) and content_hash (hash_fields).
    bad = replace(
        manifest,
        manifest_format="yaml",  # schema violation
        content_hash="not-a-valid-sha256",  # hash violation
    )
    with pytest.raises(ValueError, match="manifest_format"):
        bad.validate()


# ─────────────────────────────────────────────────────────────
# Column collection immutability documentation
# ─────────────────────────────────────────────────────────────


def test_manifest_column_names_is_tuple() -> None:
    """Documents that ``column_names`` is intentionally immutable."""
    manifest = _valid_manifest()
    assert isinstance(manifest.column_names, tuple)


def test_manifest_input_snapshots_is_tuple() -> None:
    """Documents that ``input_snapshots`` is intentionally immutable."""
    manifest = _valid_manifest()
    assert isinstance(manifest.input_snapshots, tuple)