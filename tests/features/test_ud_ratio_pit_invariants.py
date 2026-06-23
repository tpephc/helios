# tests/features/test_ud_ratio_pit_invariants.py
"""PIT invariant tests for ud_ratio_21d — Phase 1A.

Phase 1A delivers PIT-12 + PIT-13 only. Tests for PIT-1..6, 9, 11
arrive in Phase 1B/1C; PIT-7, 8, 10 arrive in Phase 1D. Each phase's
PIT tests land in the SAME commit as the implementation increment
that makes them green.

Spec reference: docs/features/ud_ratio_21d_spec.md (v0.1.4)
"""
from __future__ import annotations

from datetime import date, timedelta

import polars as pl
import pytest

from features.ud_ratio import (
    WINDOW,
    WINDOW_LOOKBACK_BUFFER_DAYS,
    add_ud_ratio_21d,
)


# ── PIT-12 — Non-trading-day window_end rejected ─────────────────────


class TestPIT12NonTradingDayRejection:
    """Spec §12.2: a date used as window_end must be a trading day.

    Phase 1A scope: validate the guard fires for known non-trading
    dates. Each test constructs a minimal one-row panel where the
    single row's `date` is a known non-trading day; the guard MUST
    raise ValueError before reaching the NotImplementedError body.
    """

    def _make_one_row_panel(self, d: date) -> pl.DataFrame:
        return pl.DataFrame(
            {
                "stock_id": ["2330"],
                "date":     [d],
                "adj_close": [100.0],
            },
            schema={
                "stock_id":  pl.Utf8,
                "date":      pl.Date,
                "adj_close": pl.Float64,
            },
        )

    def test_saturday_rejected(self) -> None:
        # 2026-06-20 is a Saturday
        sat = date(2026, 6, 20)
        assert sat.weekday() == 5
        df = self._make_one_row_panel(sat)
        with pytest.raises(ValueError, match="not a trading day"):
            add_ud_ratio_21d(df)

    def test_sunday_rejected(self) -> None:
        # 2026-06-21 is a Sunday
        sun = date(2026, 6, 21)
        assert sun.weekday() == 6
        df = self._make_one_row_panel(sun)
        with pytest.raises(ValueError, match="not a trading day"):
            add_ud_ratio_21d(df)

    def test_cny_in_xtai_coverage_rejected(self) -> None:
        # 2026-02-17 is CNY 2026 (in xtai stub _KNOWN_HOLIDAYS)
        cny = date(2026, 2, 17)
        df = self._make_one_row_panel(cny)
        with pytest.raises(ValueError, match="not a trading day"):
            add_ud_ratio_21d(df)

    def test_typhoon_closure_in_xtai_coverage_rejected(self) -> None:
        # 2024-07-24 is Typhoon Gaemi day 1
        gaemi = date(2024, 7, 24)
        df = self._make_one_row_panel(gaemi)
        with pytest.raises(ValueError, match="not a trading day"):
            add_ud_ratio_21d(df)


# ── PIT-13 — Window construction parity + fail-fast ───────────────────


class TestPIT13WindowConstruction:
    """Spec §12.3: window construction algorithm.

    Phase 1A scope:
        (a) Calendar regression triggers fail-fast: when the calendar
            returns < WINDOW trading days within the buffer, the
            function MUST raise ValueError with an actionable message.
        (b) Healthy calendar: a trading-day window_end with normal
            buffer coverage MUST pass through both validation guards
            and reach the NotImplementedError body (proving the
            guards do NOT spuriously reject valid inputs).

    Independent calendar derivation (the "compute_ud_ratio_21d
    window_start matches get_trading_days(t-45, t)[-21] derived
    independently" assertion in spec §11) requires the body to
    actually produce a window_start observable in the output. That
    test arrives in Phase 1B alongside the computation. Phase 1A
    asserts only the structural guards.
    """

    def _make_one_row_panel(self, d: date) -> pl.DataFrame:
        return pl.DataFrame(
            {
                "stock_id":  ["2330"],
                "date":      [d],
                "adj_close": [100.0],
            },
            schema={
                "stock_id":  pl.Utf8,
                "date":      pl.Date,
                "adj_close": pl.Float64,
            },
        )

    def test_healthy_calendar_passes_guards(self) -> None:
        """A trading-day window_end with adequate buffer must pass
        validation guards and reach the NotImplementedError body.

        Guards passed for a trading day proves PIT-12 doesn't
        over-reject. Reaching NotImplementedError (Phase 1B sentinel)
        proves the calendar derivation succeeded without raising.
        """
        # 2026-06-22 is a Monday and within the stub's normal
        # trading-day coverage (no holiday in the preceding 45 days
        # other than CNY which is well outside the buffer here).
        mon = date(2026, 6, 22)
        df = self._make_one_row_panel(mon)
        with pytest.raises(NotImplementedError, match="Phase 1B"):
            add_ud_ratio_21d(df)

    def test_calendar_regression_triggers_fail_fast(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Monkeypatch get_trading_days to return < WINDOW days.

        The fail-fast guard MUST raise ValueError before the
        NotImplementedError body — i.e. silent short-window
        production is impossible.
        """
        import features.ud_ratio as ur_mod

        # Make the calendar return only WINDOW - 1 days regardless
        # of inputs. The returned list must still satisfy
        # all_td[-1] == window_end so the defensive RuntimeError
        # doesn't fire first. So craft a sequence ending at the
        # query end-date.
        def stub_get_trading_days(start: date, end: date) -> list[date]:
            # Return WINDOW - 1 days, ending at `end`, walking
            # backwards on weekdays.
            n = WINDOW - 1
            out: list[date] = []
            cur = end
            while len(out) < n:
                if cur.weekday() < 5:
                    out.append(cur)
                cur = cur - timedelta(days=1)
            return list(reversed(out))

        monkeypatch.setattr(ur_mod, "get_trading_days", stub_get_trading_days)

        mon = date(2026, 6, 22)
        df = self._make_one_row_panel(mon)

        with pytest.raises(ValueError) as exc_info:
            add_ud_ratio_21d(df)

        # Verify the error message is actionable (mentions the
        # actual vs required counts and the buffer constant).
        msg = str(exc_info.value)
        assert "calendar returned" in msg.lower() or "trading-day" in msg.lower()
        assert str(WINDOW) in msg
        assert str(WINDOW - 1) in msg

    def test_calendar_returning_exactly_window_passes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Boundary: exactly WINDOW trading days returned must pass
        the >= WINDOW guard (not >).
        """
        import features.ud_ratio as ur_mod

        def stub_get_trading_days(start: date, end: date) -> list[date]:
            n = WINDOW  # exactly threshold
            out: list[date] = []
            cur = end
            while len(out) < n:
                if cur.weekday() < 5:
                    out.append(cur)
                cur = cur - timedelta(days=1)
            return list(reversed(out))

        monkeypatch.setattr(ur_mod, "get_trading_days", stub_get_trading_days)

        mon = date(2026, 6, 22)
        df = self._make_one_row_panel(mon)
        # Should pass guards, reach Phase 1B sentinel.
        with pytest.raises(NotImplementedError, match="Phase 1B"):
            add_ud_ratio_21d(df)

    def test_calendar_inconsistency_triggers_runtime_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Defensive guard: if the calendar returns >= WINDOW days
        but the last day is NOT window_end, _derive_window_dates
        raises RuntimeError (calendar contract violation).
        """
        import features.ud_ratio as ur_mod

        def stub_get_trading_days(start: date, end: date) -> list[date]:
            # Return WINDOW + 5 days but the last day is BEFORE `end`,
            # simulating a broken calendar.
            out: list[date] = []
            cur = end - timedelta(days=10)
            while len(out) < WINDOW + 5:
                if cur.weekday() < 5:
                    out.append(cur)
                cur = cur - timedelta(days=1)
            return list(reversed(out))

        monkeypatch.setattr(ur_mod, "get_trading_days", stub_get_trading_days)

        mon = date(2026, 6, 22)
        df = self._make_one_row_panel(mon)
        with pytest.raises(RuntimeError, match="calendar contract"):
            add_ud_ratio_21d(df)
