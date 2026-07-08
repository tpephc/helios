# tests/features/win_rate_21d/test_constants.py
"""Tests for governance-locked win_rate_21d constants."""

from typing import Final, get_args, get_origin

from features.win_rate_21d import constants


def test_locked_numeric_constants_match_governance() -> None:
    assert constants.WINDOW == 21
    assert constants.MIN_OBS == 15
    assert constants.MIN_CROSS_SECTION_OBS_PER_DATE == 30


def test_producer_identity_constants_match_governance() -> None:
    assert constants.PRODUCER_TABLE_NAME == "win_rate_21d_cross_section_median"
    assert constants.DUCKDB_PATH == "data/_storage/helios.duckdb"
    assert constants.FEATURE_ID == "win_rate_21d"


def test_build_strategy_is_one_shot_full_rebuild() -> None:
    assert constants.BUILD_STRATEGY == "one_shot_full_rebuild"


def test_build_strategy_literal_admits_only_one_shot_full_rebuild() -> None:
    """Guard against silent widening of the BUILD_STRATEGY annotation.

    E.g., accidentally changing
    ``Literal['one_shot_full_rebuild']`` to
    ``Literal['one_shot_full_rebuild', 'incremental']``.

    The annotation is ``Final[Literal['one_shot_full_rebuild']]``, so we
    first unwrap ``Final`` and then read the ``Literal`` arguments.
    """
    annotation = constants.__annotations__["BUILD_STRATEGY"]
    # First unwrap Final[...] -> get the inner Literal[...] type.
    final_args = get_args(annotation)
    assert len(final_args) == 1, (
        "BUILD_STRATEGY annotation must be Final[Literal[...]] "
        f"(got Final args: {final_args})"
    )
    literal_type = final_args[0]
    # Then read the Literal[...] arguments.
    literal_args = get_args(literal_type)
    assert literal_args == ("one_shot_full_rebuild",)


def test_manifest_schema_version_matches_sd_a2_5() -> None:
    assert constants.MANIFEST_SCHEMA_VERSION == "1.0.0"


def test_hash_hex_length_constants_match_algorithm_output_sizes() -> None:
    """SHA-1 and SHA-256 hex-length constants must match algorithm outputs."""
    assert constants.SHA1_HEX_LEN == 40
    assert constants.SHA256_HEX_LEN == 64


def test_canonical_pit_view_name_matches_spec() -> None:
    """CANONICAL_PIT_VIEW_NAME equals the spec-locked PIT view name."""
    assert (
        constants.CANONICAL_PIT_VIEW_NAME
        == "listed_market_daily_price_adj"
    )
    assert type(constants.CANONICAL_PIT_VIEW_NAME) is str

    raw_annotation = constants.__annotations__["CANONICAL_PIT_VIEW_NAME"]
    assert get_origin(raw_annotation) is Final
