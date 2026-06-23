# tests/features/test_ud_ratio_schema.py
"""Schema tests for ud_ratio_21d — v0.1.4 (Phase B scope).

Asserts module constants and public API signature for
features.ud_ratio. Row-level invariants on actual output are
deferred to Step 1 PR (alongside the implementation), per
GATE-S1-IMPL-001 / spec §8.

Spec reference: docs/features/ud_ratio_21d_spec.md (v0.1.4)
"""
from __future__ import annotations

import inspect
from typing import get_type_hints

import polars as pl
import pytest

from features.ud_ratio import (
    FEATURE_ID,
    MIN_OBS,
    SPEC_VERSION,
    WINDOW,
    WINDOW_LOOKBACK_BUFFER_DAYS,
    add_ud_ratio_21d,
)


# ── Module-level constants ────────────────────────────────────────────

class TestConstants:
    """Spec-locked constants must match v0.1.4 exactly."""

    def test_min_obs_locked(self) -> None:
        assert MIN_OBS == 15

    def test_window_locked(self) -> None:
        assert WINDOW == 21

    def test_feature_id_locked(self) -> None:
        assert FEATURE_ID == "ud_ratio_21d"

    def test_spec_version_locked(self) -> None:
        assert SPEC_VERSION == "v0.1.4"

    def test_window_lookback_buffer_locked(self) -> None:
        # Mechanical bound (spec §12.3); not a research threshold.
        assert WINDOW_LOOKBACK_BUFFER_DAYS == 45

    def test_min_obs_le_window(self) -> None:
        # Structural sanity: min_obs must not exceed window.
        assert MIN_OBS <= WINDOW

    def test_window_lookback_buffer_exceeds_window(self) -> None:
        # The buffer must comfortably exceed WINDOW in calendar days.
        # Taiwan's longest holiday cluster yields ~10 non-trading days;
        # 45 calendar days provides ~30+ trading days. Strict
        # `>` here catches accidental equality.
        assert WINDOW_LOOKBACK_BUFFER_DAYS > WINDOW


# ── Public API signature ──────────────────────────────────────────────

class TestPublicAPISignature:
    """add_ud_ratio_21d signature must match the locked contract."""

    def test_function_is_callable(self) -> None:
        assert callable(add_ud_ratio_21d)

    def test_signature_parameters(self) -> None:
        sig = inspect.signature(add_ud_ratio_21d)
        params = sig.parameters

        # df is positional-or-keyword
        assert "df" in params
        df_param = params["df"]
        assert df_param.kind in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.POSITIONAL_ONLY,
        )
        assert df_param.default is inspect.Parameter.empty, (
            "df must be a required parameter (no default)"
        )

        # min_obs is keyword-only with default == MIN_OBS
        assert "min_obs" in params
        min_obs_param = params["min_obs"]
        assert min_obs_param.kind == inspect.Parameter.KEYWORD_ONLY, (
            "min_obs must be keyword-only (after `*`)"
        )
        assert min_obs_param.default == MIN_OBS

    def test_only_expected_parameters(self) -> None:
        # Lock the parameter set: any new public parameter requires
        # a spec change, not a silent API drift.
        sig = inspect.signature(add_ud_ratio_21d)
        assert set(sig.parameters.keys()) == {"df", "min_obs"}

    def test_return_annotation_is_polars_dataframe(self) -> None:
        # Use get_type_hints to resolve PEP 563 string annotations
        # (the module uses `from __future__ import annotations`).
        hints = get_type_hints(add_ud_ratio_21d)
        assert hints.get("return") is pl.DataFrame

    def test_min_obs_annotation_is_int(self) -> None:
        hints = get_type_hints(add_ud_ratio_21d)
        assert hints.get("min_obs") is int

    def test_df_annotation_is_polars_dataframe(self) -> None:
        hints = get_type_hints(add_ud_ratio_21d)
        assert hints.get("df") is pl.DataFrame


# ── Phase B placeholder behaviour ────────────────────────────────────

class TestPhaseBPlaceholder:
    """While Step 1 is pending, the function must raise
    NotImplementedError. When Step 1 lands and implementation
    replaces the placeholder, this test will start FAILING — that
    failure is the signal to remove this test (or replace it with
    real behavioural tests under tests/features/test_ud_ratio_*).
    """

    def test_raises_not_implemented(self) -> None:
        # Minimal valid-shape input so we get past any input-validation
        # that Step 1 may add before raising NotImplementedError.
        # Phase B body raises immediately regardless of input.
        df = pl.DataFrame(
            schema={
                "stock_id": pl.Utf8,
                "date": pl.Date,
                "adj_close": pl.Float64,
            }
        )
        with pytest.raises(NotImplementedError, match="Phase B skeleton"):
            add_ud_ratio_21d(df)
