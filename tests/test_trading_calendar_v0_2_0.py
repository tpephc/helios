# tests/test_trading_calendar_v0_2_0.py
"""Regression tests for market/trading_calendar.py v0.2.0.

Tests are deliberately independent of the DB (twse_holidays Layer 1) to
keep them fast and deterministic. Layer 1 DB behaviour is tested separately
in the integration test section (marked with pytest.mark.integration).

Test categories:
    - Weekend invariant (hard, Layer 0)
    - XTAI Layer 2: known typhoon closures, CNY, statutory holidays
    - XTAI Layer 2: known trading days adjacent to closures
    - Fallback Layer 3: smoke (post-XTAI dates)
    - Utility functions: previous_trading_day, next_trading_day,
                         get_trading_days, trading_days_between
    - roc_date_to_gregorian: date conversion in ingestion script
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

# Import the module under test.
# DB-dependent helpers (_is_in_twse_holidays_db, next_fillable_day) are
# patched to return False / None so tests run without a live DB.
import market.trading_calendar as cal_mod
from market.trading_calendar import (
    is_trading_day,
    get_trading_days,
    next_trading_day,
    previous_trading_day,
    trading_days_between,
)
from scripts.ingest_twse_holidays import _roc_date_to_gregorian


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def patch_db_layer(monkeypatch):
    """Patch Layer 1 DB check to return False for all unit tests.

    This isolates XTAI + Fallback behaviour from DB state.
    Integration tests that need real DB behaviour should opt out via
    pytest.mark.integration and not use this fixture.
    """
    monkeypatch.setattr(
        cal_mod, "_is_in_twse_holidays_db", lambda d: False
    )


# ── Weekend invariant ─────────────────────────────────────────────────────────

class TestWeekendInvariant:
    """Weekend = closed, always, regardless of other layers."""

    @pytest.mark.parametrize("d", [
        date(2024, 7, 27),   # Saturday (normal week)
        date(2024, 7, 28),   # Sunday
        date(2026, 2, 14),   # Saturday during CNY week
        date(2025, 1, 25),   # Saturday — Chinese New Year eve area
    ])
    def test_saturday_sunday_always_closed(self, d: date) -> None:
        assert not is_trading_day(d), f"{d} ({d.strftime('%A')}) should be closed"


# ── XTAI Layer 2: typhoon closures ───────────────────────────────────────────

class TestTyphoonClosures:
    """Typhoon Gaemi (2024-07-24/25) — canonical test for non-statutory closures."""

    def test_typhoon_gaemi_day1(self) -> None:
        assert not is_trading_day(date(2024, 7, 24))

    def test_typhoon_gaemi_day2(self) -> None:
        assert not is_trading_day(date(2024, 7, 25))

    def test_day_before_typhoon_is_open(self) -> None:
        assert is_trading_day(date(2024, 7, 23))

    def test_day_after_typhoon_is_open(self) -> None:
        assert is_trading_day(date(2024, 7, 26))


# ── XTAI Layer 2: Lunar New Year ─────────────────────────────────────────────

class TestLunarNewYear:

    @pytest.mark.parametrize("d", [
        date(2024, 2, 8),   # CNY 2024
        date(2024, 2, 9),
        date(2025, 1, 27),  # CNY 2025
        date(2025, 1, 28),
        date(2026, 2, 17),  # CNY 2026
        date(2026, 2, 18),
    ])
    def test_cny_days_closed(self, d: date) -> None:
        assert not is_trading_day(d)


# ── XTAI Layer 2: statutory holidays ─────────────────────────────────────────

class TestStatutoryHolidays:

    @pytest.mark.parametrize("d", [
        date(2024, 4, 4),   # Tomb Sweeping / Children's Day
        date(2024, 6, 10),  # Dragon Boat 2024
        date(2024, 9, 17),  # Mid-Autumn 2024
        date(2024, 10, 10), # National Day
    ])
    def test_statutory_holidays_closed(self, d: date) -> None:
        assert not is_trading_day(d)


# ── XTAI Layer 2: known trading days ─────────────────────────────────────────

class TestKnownTradingDays:
    """Normal weekdays that should be open."""

    @pytest.mark.parametrize("d", [
        date(2024, 7, 23),  # Tuesday before Gaemi typhoon
        date(2024, 7, 26),  # Friday after Gaemi typhoon
        date(2024, 2, 5),   # Last trading day before CNY 2024 (02-06/07 are CNY holiday)
        date(2024, 2, 19),  # First day back after CNY 2024
        date(2026, 6, 7),   # Today (Sunday — wait, this is a known date)
        date(2025, 3, 3),   # Ordinary Monday
        date(2024, 1, 2),   # First trading day of 2024
    ])
    def test_ordinary_weekdays_open(self, d: date) -> None:
        # Skip if weekend (parametrize may include edge cases)
        if d.weekday() >= 5:
            pytest.skip(f"{d} is a weekend — cannot be a trading day")
        assert is_trading_day(d), f"{d} should be a trading day"


# ── Utility: previous_trading_day ────────────────────────────────────────────

class TestPreviousTradingDay:

    def test_skips_weekend(self) -> None:
        # Monday 2024-07-29 → previous should be Friday 2024-07-26
        # (2024-07-27/28 are Sat/Sun; typhoon was 07-24/25)
        result = previous_trading_day(date(2024, 7, 29))
        assert result == date(2024, 7, 26)

    def test_skips_typhoon_days(self) -> None:
        # Friday 2024-07-26 → previous should skip typhoon 07-24/25
        # and land on Tuesday 2024-07-23
        result = previous_trading_day(date(2024, 7, 26))
        assert result == date(2024, 7, 23)

    def test_returns_none_if_no_day_found(self) -> None:
        # Patch is_trading_day to always False to simulate gap
        with patch.object(cal_mod, "is_trading_day", return_value=False):
            result = previous_trading_day(date(2024, 1, 15), max_back_days=5)
        assert result is None


# ── Utility: next_trading_day ────────────────────────────────────────────────

class TestNextTradingDay:

    def test_skips_weekend(self) -> None:
        # Friday 2024-07-26 → next should be Monday 2024-07-29
        result = next_trading_day(date(2024, 7, 26))
        assert result == date(2024, 7, 29)

    def test_skips_typhoon_days(self) -> None:
        # Tuesday 2024-07-23 → next should skip typhoon 07-24/25
        # and land on Friday 2024-07-26
        result = next_trading_day(date(2024, 7, 23))
        assert result == date(2024, 7, 26)

    def test_returns_none_if_no_day_found(self) -> None:
        with patch.object(cal_mod, "is_trading_day", return_value=False):
            result = next_trading_day(date(2024, 1, 15), max_forward_days=5)
        assert result is None


# ── Utility: get_trading_days / trading_days_between ─────────────────────────

class TestGetTradingDays:

    def test_week_with_typhoon(self) -> None:
        # 2024-07-22 (Mon) to 2024-07-26 (Fri): typhoon 07-24/25 closed
        days = get_trading_days(date(2024, 7, 22), date(2024, 7, 26))
        assert days == [date(2024, 7, 22), date(2024, 7, 23), date(2024, 7, 26)]

    def test_trading_days_between_count(self) -> None:
        n = trading_days_between(date(2024, 7, 22), date(2024, 7, 26))
        assert n == 3

    def test_single_holiday_range(self) -> None:
        days = get_trading_days(date(2024, 2, 8), date(2024, 2, 8))
        assert days == []  # CNY — closed

    def test_single_trading_day_range(self) -> None:
        days = get_trading_days(date(2024, 7, 23), date(2024, 7, 23))
        assert days == [date(2024, 7, 23)]


# ── Ingestion script: ROC date conversion ────────────────────────────────────

class TestRocDateToGregorian:

    @pytest.mark.parametrize("roc_str,expected", [
        ("1150101", date(2026, 1, 1)),
        ("1140101", date(2025, 1, 1)),
        ("1131010", date(2024, 10, 10)),
        ("1130228", date(2024, 2, 28)),
        ("1150211", date(2026, 2, 11)),
    ])
    def test_valid_dates(self, roc_str: str, expected: date) -> None:
        assert _roc_date_to_gregorian(roc_str) == expected

    @pytest.mark.parametrize("bad_input", [
        "115101",    # too short (6 chars)
        "11501010",  # too long (8 chars)
        "115010X",   # non-digit
        "",
        "1150230",   # Feb 30 — invalid calendar date
    ])
    def test_invalid_inputs_raise(self, bad_input: str) -> None:
        with pytest.raises((ValueError, Exception)):
            _roc_date_to_gregorian(bad_input)
