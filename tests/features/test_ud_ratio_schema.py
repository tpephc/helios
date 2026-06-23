# tests/features/test_ud_ratio_schema.py
"""Schema tests for ud_ratio_21d — v0.1.4 (Phase 1A).

Asserts module constants, public API signature, and input contract
validation for features.ud_ratio.

Phase B (committed): TestConstants, TestPublicAPISignature,
                     TestPhaseBPlaceholder (the last now removed
                     since Phase 1A delivers entry-point validation
                     before the NotImplementedError body).
Phase 1A (this file): TestInputValidation added.
PIT calendar/window tests live in
    tests/features/test_ud_ratio_pit_invariants.py.

Spec reference: docs/features/ud_ratio_21d_spec.md (v0.1.4)
"""
from __future__ import annotations

import inspect
from datetime import date
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
        assert WINDOW_LOOKBACK_BUFFER_DAYS == 45

    def test_min_obs_le_window(self) -> None:
        assert MIN_OBS <= WINDOW

    def test_window_lookback_buffer_exceeds_window(self) -> None:
        assert WINDOW_LOOKBACK_BUFFER_DAYS > WINDOW


# ── Public API signature ──────────────────────────────────────────────


class TestPublicAPISignature:
    """add_ud_ratio_21d signature must match the locked contract."""

    def test_function_is_callable(self) -> None:
        assert callable(add_ud_ratio_21d)

    def test_signature_parameters(self) -> None:
        sig = inspect.signature(add_ud_ratio_21d)
        params = sig.parameters

        assert "df" in params
        df_param = params["df"]
        assert df_param.kind in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.POSITIONAL_ONLY,
        )
        assert df_param.default is inspect.Parameter.empty

        assert "min_obs" in params
        min_obs_param = params["min_obs"]
        assert min_obs_param.kind == inspect.Parameter.KEYWORD_ONLY
        assert min_obs_param.default == MIN_OBS

    def test_only_expected_parameters(self) -> None:
        sig = inspect.signature(add_ud_ratio_21d)
        assert set(sig.parameters.keys()) == {"df", "min_obs"}

    def test_return_annotation_is_polars_dataframe(self) -> None:
        hints = get_type_hints(add_ud_ratio_21d)
        assert hints.get("return") is pl.DataFrame

    def test_min_obs_annotation_is_int(self) -> None:
        hints = get_type_hints(add_ud_ratio_21d)
        assert hints.get("min_obs") is int

    def test_df_annotation_is_polars_dataframe(self) -> None:
        hints = get_type_hints(add_ud_ratio_21d)
        assert hints.get("df") is pl.DataFrame


# ── Input validation (Phase 1A) ───────────────────────────────────────


class TestInputValidation:
    """Spec §5.1 input contract enforcement.

    Phase 1A scope (per GATE-S1-IMPL-001 Q3):
        1. Required columns present
        2. Dtypes exact (Utf8, Date, Float64; Float32 rejected)
        3. Sorted ascending by (stock_id, date)
        4. No duplicate (stock_id, date)
    """

    def _row(self, ticker: str, d: date, close: float) -> dict:
        return {"stock_id": ticker, "date": d, "adj_close": close}

    def _frame(self, rows: list[dict]) -> pl.DataFrame:
        return pl.DataFrame(
            rows,
            schema={
                "stock_id":  pl.Utf8,
                "date":      pl.Date,
                "adj_close": pl.Float64,
            },
        )

    # ── (1) required columns ──────────────────────────────────────

    def test_missing_stock_id_rejected(self) -> None:
        df = pl.DataFrame(
            {"date": [date(2026, 6, 22)], "adj_close": [100.0]},
            schema={"date": pl.Date, "adj_close": pl.Float64},
        )
        with pytest.raises(ValueError, match="missing required columns"):
            add_ud_ratio_21d(df)

    def test_missing_date_rejected(self) -> None:
        df = pl.DataFrame(
            {"stock_id": ["2330"], "adj_close": [100.0]},
            schema={"stock_id": pl.Utf8, "adj_close": pl.Float64},
        )
        with pytest.raises(ValueError, match="missing required columns"):
            add_ud_ratio_21d(df)

    def test_missing_adj_close_rejected(self) -> None:
        df = pl.DataFrame(
            {"stock_id": ["2330"], "date": [date(2026, 6, 22)]},
            schema={"stock_id": pl.Utf8, "date": pl.Date},
        )
        with pytest.raises(ValueError, match="missing required columns"):
            add_ud_ratio_21d(df)

    # ── (2) dtype enforcement ─────────────────────────────────────

    def test_float32_adj_close_rejected(self) -> None:
        df = pl.DataFrame(
            {
                "stock_id":  ["2330"],
                "date":      [date(2026, 6, 22)],
                "adj_close": [100.0],
            },
            schema={
                "stock_id":  pl.Utf8,
                "date":      pl.Date,
                "adj_close": pl.Float32,  # WRONG
            },
        )
        with pytest.raises(ValueError, match="adj_close.*Float32"):
            add_ud_ratio_21d(df)

    def test_int_adj_close_rejected(self) -> None:
        df = pl.DataFrame(
            {
                "stock_id":  ["2330"],
                "date":      [date(2026, 6, 22)],
                "adj_close": [100],
            },
            schema={
                "stock_id":  pl.Utf8,
                "date":      pl.Date,
                "adj_close": pl.Int64,  # WRONG
            },
        )
        with pytest.raises(ValueError, match="adj_close"):
            add_ud_ratio_21d(df)

    def test_datetime_date_column_rejected(self) -> None:
        # Date column must be pl.Date, not pl.Datetime
        df = pl.DataFrame(
            {
                "stock_id":  ["2330"],
                "date":      [date(2026, 6, 22)],
                "adj_close": [100.0],
            },
            schema={
                "stock_id":  pl.Utf8,
                "date":      pl.Datetime,  # WRONG
                "adj_close": pl.Float64,
            },
        )
        with pytest.raises(ValueError, match="date.*Datetime"):
            add_ud_ratio_21d(df)

    # ── (3) sort order ────────────────────────────────────────────

    def test_unsorted_by_date_rejected(self) -> None:
        df = self._frame([
            self._row("2330", date(2026, 6, 22), 100.0),
            self._row("2330", date(2026, 6, 20), 99.0),  # earlier date AFTER later
        ])
        with pytest.raises(ValueError, match="sorted ascending"):
            add_ud_ratio_21d(df)

    def test_unsorted_by_stock_id_rejected(self) -> None:
        df = self._frame([
            self._row("2330", date(2026, 6, 22), 100.0),
            self._row("1101", date(2026, 6, 22), 50.0),  # earlier ticker AFTER later
        ])
        with pytest.raises(ValueError, match="sorted ascending"):
            add_ud_ratio_21d(df)

    # ── (4) duplicate (stock_id, date) ───────────────────────────

    def test_duplicate_stock_date_rejected(self) -> None:
        df = self._frame([
            self._row("2330", date(2026, 6, 22), 100.0),
            self._row("2330", date(2026, 6, 22), 101.0),  # duplicate key
        ])
        with pytest.raises(ValueError, match="duplicate"):
            add_ud_ratio_21d(df)

    # ── (3b) shuffled multi-stock panel rejected ─────────────────

    def test_shuffled_multi_stock_panel_rejected(self) -> None:
        """A shuffled multi-stock panel must be rejected.

        Stronger coverage than test_unsorted_by_date_rejected and
        test_unsorted_by_stock_id_rejected (which use minimal 2-row
        fixtures): this exercises a larger multi-stock panel that
        more closely resembles production input shape.

        Migrated from Phase 1C TestPIT2Determinism (where it was
        tautological as a determinism check); it is correctly
        classified as an input-contract test.
        """
        from datetime import timedelta

        # Build 3 stocks x 10 consecutive weekday rows each.
        # Weekday-only dates are sufficient here because the sort
        # check fires BEFORE calendar validation; the rejection
        # path is reached without any trading-day lookup.
        rows: list[dict] = []
        d0 = date(2026, 6, 22)
        for ticker in ("AAA", "BBB", "CCC"):
            collected: list[date] = []
            cur = d0
            while len(collected) < 10:
                if cur.weekday() < 5:
                    collected.append(cur)
                cur = cur + timedelta(days=1)
            for d in collected:
                rows.append(
                    {"stock_id": ticker, "date": d, "adj_close": 100.0}
                )

        df_sorted = self._frame(rows).sort(["stock_id", "date"])

        # Use df.reverse() rather than df.sample(): in Polars 1.41.x,
        # sample(n=height, with_replacement=False) and
        # sample(fraction=1.0, shuffle=True, seed=...) can return rows
        # in original order for specific size/seed combinations.
        # Reverse is deterministic, guaranteed-non-trivial, and
        # version-independent.
        df_unsorted = df_sorted.reverse()

        # Sanity: reversed really differs from sorted.
        assert not df_unsorted.select(["stock_id", "date"]).equals(
            df_sorted.select(["stock_id", "date"])
        )

        with pytest.raises(ValueError, match="sorted ascending"):
            add_ud_ratio_21d(df_unsorted)

    # ── happy path: empty panel passes validation ────────────────

    def test_empty_panel_returns_empty_dataframe(self) -> None:
        """Empty panel passes validation and returns an empty result
        with the three appended columns present in the schema.
        Phase 1B: function no longer raises NotImplementedError."""
        df = self._frame([])
        out = add_ud_ratio_21d(df)
        assert out.is_empty()
        # The three appended columns must be in the output schema
        # even when the panel is empty.
        for col in ("ud_ratio_21d", "n_obs_21d", "n_up_21d"):
            assert col in out.columns
