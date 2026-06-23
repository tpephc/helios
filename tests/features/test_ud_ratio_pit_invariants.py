# tests/features/test_ud_ratio_pit_invariants.py
"""PIT invariant tests for ud_ratio_21d — Phase 1B (fixture fix).

Phase 1A delivered PIT-12, PIT-13.
Phase 1B (this commit) adds PIT-3, PIT-4, PIT-5, PIT-6, PIT-9.
Phase 1C will add PIT-1, PIT-2, PIT-11.
Phase 1D will add PIT-7, PIT-8, PIT-10.

Each phase's tests land in the SAME commit as the implementation
increment that makes them green.

FIXTURE NOTE (Phase 1B fix, 2026-06-23):
    Earlier draft used a weekday-only walk-back for synthetic panel
    dates, which produced dates landing on Taiwan public holidays
    (e.g. 2026-06-19 Dragon Boat Festival) -> 15 tests failed under
    the real market.trading_calendar v0.2.0 on nexus.

    Fix: _trading_dates_ending() uses the real
    market.trading_calendar.get_trading_days(...) so synthetic panel
    dates ARE genuine trading days. The 90-calendar-day look-back
    buffer comfortably covers any holiday cluster while remaining
    contained within a single CNY-to-CNY period.

    Sandbox self-test of this file will use the sandbox stub
    calendar; final green/red gate is on nexus.

Spec reference: docs/features/ud_ratio_21d_spec.md (v0.1.4)
"""
from __future__ import annotations

from datetime import date, timedelta

import polars as pl
import pytest

from features.ud_ratio import (
    MIN_OBS,
    WINDOW,
    add_ud_ratio_21d,
)
from market.trading_calendar import get_trading_days


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────


def _trading_dates_ending(end: date, n_rows: int) -> list[date]:
    """Return the last `n_rows` trading days ending at `end`.

    Uses the real market.trading_calendar so synthetic panel rows are
    guaranteed to be on actual trading days (no weekends, no Taiwan
    public holidays, no typhoon closures). Spec §13.1.

    Args:
        end: latest trading day (must be a trading day per the
             calendar; otherwise get_trading_days will not include
             it as the last element and AssertionError fires).
        n_rows: number of trading days desired.

    Returns:
        list[date] of length n_rows, ascending, with [-1] == end.

    Raises:
        AssertionError: insufficient trading days in the 90-day
                        buffer (extreme holiday cluster, or `end`
                        not a trading day).
    """
    start = end - timedelta(days=90)
    days = get_trading_days(start, end)
    if len(days) < n_rows:
        raise AssertionError(
            f"_trading_dates_ending: need {n_rows} trading days in "
            f"[{start}, {end}] but calendar returned {len(days)}. "
            f"Likely cause: extreme holiday cluster OR `end` is not "
            f"itself a trading day."
        )
    if days[-1] != end:
        raise AssertionError(
            f"_trading_dates_ending: calendar returned last day "
            f"{days[-1]}, expected end={end}. `end` is likely NOT "
            f"a trading day."
        )
    return days[-n_rows:]


def _build_panel_ending(
    ticker: str,
    end_date: date,
    returns: list[float | None],
    base_price: float = 100.0,
) -> pl.DataFrame:
    """Build an N-row panel for `ticker` ending at `end_date`.

    Uses _trading_dates_ending so all rows are real trading days.
    Length contract: len(panel) = len(returns) + 1.
    """
    n = len(returns) + 1
    dates = _trading_dates_ending(end_date, n)

    closes: list[float | None] = [base_price]
    prev = base_price
    for r in returns:
        if r is None:
            closes.append(None)
        else:
            new = prev * (1.0 + r)
            closes.append(new)
            prev = new

    return pl.DataFrame(
        {
            "stock_id":  [ticker] * n,
            "date":      dates,
            "adj_close": closes,
        },
        schema={
            "stock_id":  pl.Utf8,
            "date":      pl.Date,
            "adj_close": pl.Float64,
        },
    )


# Phase 1B anchor — INTENTIONALLY FIXED.
#
# 2026-06-22 is a Monday in a quiet Taiwan-calendar period:
#   - itself: trading day (verified against XTAI)
#   - preceding 90 calendar days: contain >=60 trading days
#   - excluded by get_trading_days (correctly):
#         2026-06-19 (Dragon Boat Festival, Friday)
#         all Sat/Sun weekends
#
# DO NOT change this anchor casually. Changing it requires PIT
# re-validation against market.trading_calendar:
#   (a) is_trading_day(_END) must be True
#   (b) get_trading_days(_END - 90 calendar days, _END) must
#       return >= 22 trading days (longest fixture is 21 returns +
#       1 base = 22 rows)
#   (c) Re-confirm none of the assertions in PIT-3..PIT-9 below
#       depend on a specific calendar configuration around _END
#       (e.g. PIT-5 mutating row index 10 assumes that index lies
#       in the middle of the window, not at the boundary).
#
# Spec §13.1: "Synthetic fixtures MUST be deterministic, bit-exact
# reproducible". Using max(get_trading_days(...)) here would violate
# determinism by tying test outcomes to calendar-source revisions.
_END = date(2026, 6, 22)


# ── PIT-12 — Non-trading-day window_end rejected (Phase 1A) ──────────


class TestPIT12NonTradingDayRejection:
    """Spec §12.2."""

    def _make_one_row_panel(self, d: date) -> pl.DataFrame:
        return pl.DataFrame(
            {"stock_id": ["2330"], "date": [d], "adj_close": [100.0]},
            schema={"stock_id": pl.Utf8, "date": pl.Date, "adj_close": pl.Float64},
        )

    def test_saturday_rejected(self) -> None:
        sat = date(2026, 6, 20)
        assert sat.weekday() == 5
        with pytest.raises(ValueError, match="not a trading day"):
            add_ud_ratio_21d(self._make_one_row_panel(sat))

    def test_sunday_rejected(self) -> None:
        sun = date(2026, 6, 21)
        with pytest.raises(ValueError, match="not a trading day"):
            add_ud_ratio_21d(self._make_one_row_panel(sun))

    def test_cny_in_xtai_coverage_rejected(self) -> None:
        with pytest.raises(ValueError, match="not a trading day"):
            add_ud_ratio_21d(self._make_one_row_panel(date(2026, 2, 17)))

    def test_typhoon_closure_in_xtai_coverage_rejected(self) -> None:
        with pytest.raises(ValueError, match="not a trading day"):
            add_ud_ratio_21d(self._make_one_row_panel(date(2024, 7, 24)))


# ── PIT-13 — Window construction parity + fail-fast (Phase 1A) ───────


class TestPIT13WindowConstruction:
    """Spec §12.3."""

    def _make_one_row_panel(self, d: date) -> pl.DataFrame:
        return pl.DataFrame(
            {"stock_id": ["2330"], "date": [d], "adj_close": [100.0]},
            schema={"stock_id": pl.Utf8, "date": pl.Date, "adj_close": pl.Float64},
        )

    def test_healthy_calendar_one_row_short_history_returns_null(self) -> None:
        """A single row passes guards and produces a row whose
        ud_ratio_21d is null (only 1 obs valid, well below min_obs).
        """
        df = self._make_one_row_panel(_END)
        out = add_ud_ratio_21d(df)
        assert out.height == 1
        row = out.to_dicts()[0]
        assert row["n_obs_21d"] == 0
        assert row["n_up_21d"] == 0
        assert row["ud_ratio_21d"] is None

    def test_calendar_regression_triggers_fail_fast(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import features.ud_ratio as ur_mod

        def stub_get_trading_days(start: date, end: date) -> list[date]:
            n = WINDOW - 1
            out: list[date] = []
            cur = end
            while len(out) < n:
                if cur.weekday() < 5:
                    out.append(cur)
                cur -= timedelta(days=1)
            return list(reversed(out))

        monkeypatch.setattr(ur_mod, "get_trading_days", stub_get_trading_days)

        df = self._make_one_row_panel(_END)
        with pytest.raises(ValueError) as exc:
            add_ud_ratio_21d(df)
        msg = str(exc.value)
        assert str(WINDOW) in msg
        assert str(WINDOW - 1) in msg

    def test_calendar_returning_exactly_window_passes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Boundary: exactly WINDOW trading days returned, with the
        last day correctly equal to window_end, must pass both the
        >= WINDOW count guard AND the days[-1] == window_end
        alignment guard. Reviewer-requested: also assert the alignment
        invariant directly via the stub return, not just via the fact
        that the function did not raise.
        """
        import features.ud_ratio as ur_mod

        captured: dict[str, list[date]] = {}

        def stub_get_trading_days(start: date, end: date) -> list[date]:
            n = WINDOW
            out: list[date] = []
            cur = end
            while len(out) < n:
                if cur.weekday() < 5:
                    out.append(cur)
                cur -= timedelta(days=1)
            result = list(reversed(out))
            captured["last_call"] = result
            return result

        monkeypatch.setattr(ur_mod, "get_trading_days", stub_get_trading_days)

        df = self._make_one_row_panel(_END)
        out = add_ud_ratio_21d(df)
        assert out.height == 1
        # Direct alignment assertion on the stub's returned sequence:
        # days[-1] must equal window_end, otherwise _derive_window_dates
        # would have raised RuntimeError before reaching here.
        assert captured["last_call"][-1] == _END
        assert len(captured["last_call"]) == WINDOW

    def test_calendar_inconsistency_triggers_runtime_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import features.ud_ratio as ur_mod

        def stub_get_trading_days(start: date, end: date) -> list[date]:
            out: list[date] = []
            cur = end - timedelta(days=10)
            while len(out) < WINDOW + 5:
                if cur.weekday() < 5:
                    out.append(cur)
                cur -= timedelta(days=1)
            return list(reversed(out))

        monkeypatch.setattr(ur_mod, "get_trading_days", stub_get_trading_days)

        df = self._make_one_row_panel(_END)
        with pytest.raises(RuntimeError, match="calendar contract"):
            add_ud_ratio_21d(df)


# ── PIT-3 — min_obs coupling (Phase 1B) ─────────────────────────────


class TestPIT3MinObsCoupling:
    """Spec §4.3 + §5.3 (I3): ud_ratio_21d is null iff n_obs_21d < min_obs."""

    def test_14_returns_yields_null_at_last_row(self) -> None:
        returns = [+0.01] * 14
        df = _build_panel_ending("A", _END, returns)
        out = add_ud_ratio_21d(df)
        last = out.tail(1).to_dicts()[0]
        assert last["n_obs_21d"] == 14
        assert last["ud_ratio_21d"] is None

    def test_15_returns_yields_value_at_last_row(self) -> None:
        returns = [+0.01] * 15
        df = _build_panel_ending("A", _END, returns)
        out = add_ud_ratio_21d(df)
        last = out.tail(1).to_dicts()[0]
        assert last["n_obs_21d"] == 15
        assert last["ud_ratio_21d"] is not None
        assert abs(last["ud_ratio_21d"] - 15 / 15) < 1e-12

    def test_below_min_obs_remains_null_when_n_up_increases(self) -> None:
        returns = [+0.01] * 10
        df = _build_panel_ending("A", _END, returns)
        out = add_ud_ratio_21d(df)
        last = out.tail(1).to_dicts()[0]
        assert last["n_obs_21d"] == 10
        assert last["n_up_21d"] == 10
        assert last["ud_ratio_21d"] is None


# ── PIT-4 — Flat-day semantics (Phase 1B) ───────────────────────────


class TestPIT4FlatDaySemantic:
    """Spec §3.3 / L1: r == 0 counted in n_obs but NOT in n_up."""

    def test_20_up_plus_1_flat_yields_20_over_21(self) -> None:
        returns = [+0.01] * 20 + [0.0]
        assert len(returns) == 21
        df = _build_panel_ending("A", _END, returns)
        out = add_ud_ratio_21d(df)
        last = out.tail(1).to_dicts()[0]
        assert last["n_obs_21d"] == 21
        assert last["n_up_21d"] == 20
        assert last["ud_ratio_21d"] == 20 / 21

    def test_all_flat_days_yields_zero(self) -> None:
        returns = [0.0] * 21
        df = _build_panel_ending("A", _END, returns)
        out = add_ud_ratio_21d(df)
        last = out.tail(1).to_dicts()[0]
        assert last["n_obs_21d"] == 21
        assert last["n_up_21d"] == 0
        assert last["ud_ratio_21d"] == 0.0

    def test_mix_up_down_flat(self) -> None:
        returns = [+0.01] * 13 + [-0.01] * 7 + [0.0]
        df = _build_panel_ending("A", _END, returns)
        out = add_ud_ratio_21d(df)
        last = out.tail(1).to_dicts()[0]
        assert last["n_obs_21d"] == 21
        assert last["n_up_21d"] == 13
        assert abs(last["ud_ratio_21d"] - 13 / 21) < 1e-12

    def test_negative_zero_treated_as_flat(self) -> None:
        """IEEE 754: -0.0 == 0.0 so n_up does NOT increment.

        Pure language-level assertion; no fixture needed.
        """
        assert (-0.0 > 0.0) is False
        assert (-0.0 == 0.0) is True


# ── PIT-5 — NaN return handling (Phase 1B) ──────────────────────────


class TestPIT5NaNReturn:
    """Spec §3.3: NaN/null return contributes to NEITHER n_obs nor n_up.

    Invalidity-propagation contract (spec §4.2):
        An invalid adj_close at row t invalidates BOTH:
          - the return AT row t   (current adj_close fails validity)
          - the return AT row t+1 (prev_adj_close fails validity)
        i.e. a single corrupted price row removes exactly TWO returns
        from the rolling window.

    This is a property of the current validity predicate. If a future
    return pipeline switches to a different invalidation model (e.g.
    forward-fill imputation, or a separate validity mask passed in),
    these assertions need updating because n_obs would change.
    """

    def test_invalid_prev_close_excludes_from_both(self) -> None:
        # 21 positive returns, inject None at row 10. Per the
        # invalidity-propagation contract above, BOTH row 10's return
        # (current adj_close null) AND row 11's return (prev null)
        # become invalid -> 2 invalid, 19 valid (all positive).
        returns = [+0.01] * 21
        df = _build_panel_ending("A", _END, returns)
        closes = df["adj_close"].to_list()
        closes[10] = None
        df = df.with_columns(pl.Series("adj_close", closes, dtype=pl.Float64))

        out = add_ud_ratio_21d(df)
        last = out.tail(1).to_dicts()[0]
        assert last["n_obs_21d"] == 19
        assert last["n_up_21d"] == 19
        assert abs(last["ud_ratio_21d"] - 19 / 19) < 1e-12

    def test_nonpositive_adj_close_invalidates_return(self) -> None:
        # adj_close <= 0 fails validity predicate (§4.2). Same
        # invalidity-propagation contract: row 10's return invalid
        # (current = 0), row 11's return invalid (prev = 0) ->
        # 2 invalid, 19 valid.
        returns = [+0.01] * 21
        df = _build_panel_ending("A", _END, returns)
        closes = df["adj_close"].to_list()
        closes[10] = 0.0
        df = df.with_columns(pl.Series("adj_close", closes, dtype=pl.Float64))

        out = add_ud_ratio_21d(df)
        last = out.tail(1).to_dicts()[0]
        assert last["n_obs_21d"] == 19
        assert last["n_up_21d"] == 19


# ── PIT-6 — Window-end identity (Phase 1B) ──────────────────────────


class TestPIT6WindowEndIdentity:
    """Spec §5.5: each output row's `date` IS the window-end.

    v0.1.4 absorbed v0.1.3's `window_end == signal_date` into
    panel-row identity by construction.
    """

    def test_input_rows_preserved_in_output(self) -> None:
        returns = [+0.01] * 21
        df = _build_panel_ending("A", _END, returns)
        out = add_ud_ratio_21d(df)
        assert out.select(["stock_id", "date"]).equals(
            df.select(["stock_id", "date"])
        )

    def test_last_row_window_includes_signal_day_return(self) -> None:
        """If the last-row return is positive, n_up_21d must increment.
        Proves window is right-inclusive at `date`.
        """
        returns = [-0.01] * 20 + [+0.01]
        df = _build_panel_ending("A", _END, returns)
        out = add_ud_ratio_21d(df)
        last = out.tail(1).to_dicts()[0]
        assert last["n_obs_21d"] == 21
        assert last["n_up_21d"] == 1
        assert abs(last["ud_ratio_21d"] - 1 / 21) < 1e-12

    def test_output_schema_does_not_leak_daily_ret(self) -> None:
        """Internal daily_ret / temp columns must NOT appear in output."""
        returns = [+0.01] * 5
        df = _build_panel_ending("A", _END, returns)
        out = add_ud_ratio_21d(df)
        expected_cols = set(df.columns) | {"ud_ratio_21d", "n_obs_21d", "n_up_21d"}
        assert set(out.columns) == expected_cols
        for col in out.columns:
            assert not col.startswith("__ud_ratio_"), (
                f"Internal column {col!r} leaked into output"
            )


# ── PIT-9 — min_obs parameter override (Phase 1B) ───────────────────


class TestPIT9MinObsParameter:
    """Spec §4.3: min_obs keyword-only, default == MIN_OBS, overridable."""

    def test_default_min_obs_equals_module_constant(self) -> None:
        import inspect
        sig = inspect.signature(add_ud_ratio_21d)
        assert sig.parameters["min_obs"].default == MIN_OBS

    def test_min_obs_12_yields_value_at_n_obs_13(self) -> None:
        returns = [+0.01] * 13
        df = _build_panel_ending("A", _END, returns)
        out = add_ud_ratio_21d(df, min_obs=12)
        last = out.tail(1).to_dicts()[0]
        assert last["n_obs_21d"] == 13
        assert last["ud_ratio_21d"] is not None
        assert abs(last["ud_ratio_21d"] - 13 / 13) < 1e-12

    def test_min_obs_15_yields_null_at_n_obs_13(self) -> None:
        returns = [+0.01] * 13
        df = _build_panel_ending("A", _END, returns)
        out = add_ud_ratio_21d(df, min_obs=15)
        last = out.tail(1).to_dicts()[0]
        assert last["n_obs_21d"] == 13
        assert last["ud_ratio_21d"] is None

    def test_min_obs_18_yields_null_at_n_obs_13(self) -> None:
        returns = [+0.01] * 13
        df = _build_panel_ending("A", _END, returns)
        out = add_ud_ratio_21d(df, min_obs=18)
        last = out.tail(1).to_dicts()[0]
        assert last["n_obs_21d"] == 13
        assert last["ud_ratio_21d"] is None

    def test_min_obs_keyword_only(self) -> None:
        returns = [+0.01] * 21
        df = _build_panel_ending("A", _END, returns)
        with pytest.raises(TypeError):
            add_ud_ratio_21d(df, 12)  # type: ignore[misc]
        out = add_ud_ratio_21d(df, min_obs=12)
        assert out.height == df.height
