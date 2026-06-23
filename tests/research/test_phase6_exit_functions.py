# tests/research/test_phase6_exit_functions.py
"""Step 3B — Unit tests for Phase 6 adaptive exit decision functions.

Covers per-policy and boundary conditions for:
    exit_arm_b, exit_e1_atr_trailing, exit_e2_ma20_failure,
    exit_e3_rs_deterioration, exit_e4_donchian

ABI locked to:
    PositionState, MarketSnapshot, ExitDecision
    from scripts.run_phase6_evaluation

Completion criterion (Step 3B):
    All tests PASS → Step 3B CLOSED → Step 3C unblocked.

Governance notes:
    FIXTURE FAIL PROTOCOL:
        If make_pos() or make_mkt() raise TypeError at construction,
        treat as an ABI change to PositionState / MarketSnapshot, NOT
        a test defect. Audit against Step 3A carrier contract before
        modifying fixtures.

    METADATA KEY ASSERTIONS:
        Tests that assert specific keys in result.metadata are locking
        ExitDecision metadata schema ABI. A key rename is an intentional
        ABI change; test failure in that case is expected and correct.

    OUT-OF-DOMAIN RANK (E3):
        rs_60d_rank is sourced from bullish_features and expected to be
        in [0, 1]. The exit functions do NOT validate this domain.
        Out-of-domain values (-0.01, 1.01) are tested to document
        current behaviour. If SPEC adds domain validation, these tests
        must be updated to expect ValueError or equivalent.
"""

from __future__ import annotations

from datetime import date

import pytest

from scripts.run_phase6_evaluation import (
    E1_TRAILING_MULTIPLIER,
    E2_CONFIRMATION_LAG,
    E3_RS_RANK_THRESHOLD,
    HOLD_CEILING_DAYS,
    ExitDecision,
    MarketSnapshot,
    PositionState,
    exit_arm_b,
    exit_e1_atr_trailing,
    exit_e2_ma20_failure,
    exit_e3_rs_deterioration,
    exit_e4_donchian,
)

# =====================================================================
# Fixtures
# =====================================================================

_ENTRY_DATE = date(2024, 1, 2)
_AS_OF = date(2024, 1, 10)


def make_pos(**overrides) -> PositionState:
    """Return a PositionState with safe defaults; override as needed."""
    defaults = dict(
        symbol="2330",
        entry_date=_ENTRY_DATE,
        entry_price=100.0,
        entry_atr=2.0,
        max_close_since_entry=110.0,
        days_held=5,
    )
    return PositionState(**{**defaults, **overrides})


def make_mkt(**overrides) -> MarketSnapshot:
    """Return a MarketSnapshot with safe defaults; override as needed.

    Defaults chosen so no exit rule fires under normal conditions:
        close=105 > stop=106 (E1 does not fire)
        close=105 > ma20=100 (E2 does not fire)
        rs_60d_rank=0.60 >= 0.50 (E3 does not fire)
        close=105 > donchian=98 (E4 does not fire)
    """
    defaults = dict(
        as_of=_AS_OF,
        close=105.0,
        close_prev=104.0,
        ma20=100.0,
        ma20_prev=99.0,
        rs_60d_rank=0.60,
        donchian_low_excl=98.0,
    )
    return MarketSnapshot(**{**defaults, **overrides})


# =====================================================================
# Sanity: constant values match governance spec
# =====================================================================


def test_constants_match_spec() -> None:
    """Governance sanity — constants must match SPEC §3 values."""
    assert HOLD_CEILING_DAYS == 20
    assert E1_TRAILING_MULTIPLIER == 2.0
    assert E2_CONFIRMATION_LAG == 2
    assert E3_RS_RANK_THRESHOLD == 0.50


# =====================================================================
# ARM_B — fixed 20td hold only
# =====================================================================


class TestExitArmB:
    def test_below_ceiling_no_exit(self) -> None:
        pos = make_pos(days_held=HOLD_CEILING_DAYS - 1)
        result = exit_arm_b(pos, make_mkt())
        assert result.should_exit is False

    def test_at_ceiling_exits(self) -> None:
        pos = make_pos(days_held=HOLD_CEILING_DAYS)
        result = exit_arm_b(pos, make_mkt())
        assert result.should_exit is True
        assert "arm_b time_stop" in result.reason
        assert result.metadata["days_held"] == float(HOLD_CEILING_DAYS)

    def test_above_ceiling_exits(self) -> None:
        # Defensive: days_held should never exceed ceiling in practice,
        # but function must still return should_exit=True.
        pos = make_pos(days_held=HOLD_CEILING_DAYS + 3)
        result = exit_arm_b(pos, make_mkt())
        assert result.should_exit is True

    def test_day_zero_no_exit(self) -> None:
        pos = make_pos(days_held=0)
        result = exit_arm_b(pos, make_mkt())
        assert result.should_exit is False


# =====================================================================
# E1 — ATR trailing stop
# =====================================================================
#
# stop_price = max_close_since_entry - E1_TRAILING_MULTIPLIER * entry_atr
# With defaults: stop = 110.0 - 2.0 * 2.0 = 106.0


class TestExitE1AtrTrailing:
    def _stop(self, pos: PositionState) -> float:
        return pos.max_close_since_entry - E1_TRAILING_MULTIPLIER * pos.entry_atr

    def test_above_stop_no_exit(self) -> None:
        pos = make_pos()  # stop=106.0
        mkt = make_mkt(close=106.01)
        result = exit_e1_atr_trailing(pos, mkt)
        assert result.should_exit is False

    def test_exactly_at_stop_exits(self) -> None:
        # Boundary: close <= stop_price uses <=, so equality triggers exit.
        pos = make_pos()  # stop=106.0
        mkt = make_mkt(close=106.0)
        result = exit_e1_atr_trailing(pos, mkt)
        assert result.should_exit is True
        assert "trailing_stop" in result.reason

    def test_below_stop_exits(self) -> None:
        pos = make_pos()  # stop=106.0
        mkt = make_mkt(close=100.0)
        result = exit_e1_atr_trailing(pos, mkt)
        assert result.should_exit is True

    def test_metadata_fields_present(self) -> None:
        pos = make_pos()
        mkt = make_mkt(close=106.0)
        result = exit_e1_atr_trailing(pos, mkt)
        assert result.should_exit is True
        for key in ("exit_price", "stop_price", "max_close_since_entry",
                    "entry_atr", "multiplier"):
            assert key in result.metadata, f"Missing metadata key: {key}"

    def test_zero_atr_silent_skip(self) -> None:
        # entry_atr=0: production guard matches trailing_stop.py:56.
        # Behaviour: should_exit=False with empty reason and no metadata
        # (silent skip). This test locks the silent-skip ABI so any
        # future change to this path (e.g. raising instead of skipping)
        # is caught explicitly.
        # Step 3C producer must guarantee entry_atr > 0 to avoid
        # relying on this guard silently.
        pos = make_pos(entry_atr=0.0)
        mkt = make_mkt(close=50.0)  # far below any stop
        result = exit_e1_atr_trailing(pos, mkt)
        assert result.should_exit is False
        assert result.reason == ""
        assert result.metadata == {}

    def test_ceiling_takes_priority_over_atr(self) -> None:
        # Ceiling check comes before ATR check in function body.
        pos = make_pos(days_held=HOLD_CEILING_DAYS, entry_atr=2.0)
        mkt = make_mkt(close=50.0)  # ATR stop would also fire
        result = exit_e1_atr_trailing(pos, mkt)
        assert result.should_exit is True
        assert "time_stop" in result.reason  # ceiling reason, not ATR reason

    def test_below_ceiling_atr_fires(self) -> None:
        pos = make_pos(days_held=HOLD_CEILING_DAYS - 1)  # stop=106.0
        mkt = make_mkt(close=106.0)
        result = exit_e1_atr_trailing(pos, mkt)
        assert result.should_exit is True
        assert "trailing_stop" in result.reason

    def test_negative_entry_atr_silent_skip(self) -> None:
        # entry_atr <= 0 is guarded. Negative ATR is a data error;
        # function silently skips trailing-stop evaluation.
        pos = make_pos(entry_atr=-1.0)
        mkt = make_mkt(close=50.0)
        result = exit_e1_atr_trailing(pos, mkt)
        assert result.should_exit is False


# =====================================================================
# E2 — MA20 failure (two consecutive days below SMA20)
# =====================================================================


class TestExitE2Ma20Failure:
    def test_below_lag_no_exit(self) -> None:
        # days_held < E2_CONFIRMATION_LAG=2: skip regardless of price.
        for days in range(E2_CONFIRMATION_LAG):
            pos = make_pos(days_held=days)
            mkt = make_mkt(close=90.0, close_prev=89.0,
                           ma20=100.0, ma20_prev=99.0)
            result = exit_e2_ma20_failure(pos, mkt)
            assert result.should_exit is False, f"Should not exit at days_held={days}"

    def test_at_lag_both_below_exits(self) -> None:
        pos = make_pos(days_held=E2_CONFIRMATION_LAG)
        mkt = make_mkt(close=99.0, close_prev=98.0,
                       ma20=100.0, ma20_prev=99.5)
        result = exit_e2_ma20_failure(pos, mkt)
        assert result.should_exit is True
        assert "ma20_failure" in result.reason

    def test_today_below_yesterday_above_no_exit(self) -> None:
        pos = make_pos(days_held=E2_CONFIRMATION_LAG)
        mkt = make_mkt(close=99.0, close_prev=101.0,
                       ma20=100.0, ma20_prev=100.0)
        result = exit_e2_ma20_failure(pos, mkt)
        assert result.should_exit is False

    def test_today_above_yesterday_below_no_exit(self) -> None:
        pos = make_pos(days_held=E2_CONFIRMATION_LAG)
        mkt = make_mkt(close=101.0, close_prev=99.0,
                       ma20=100.0, ma20_prev=100.0)
        result = exit_e2_ma20_failure(pos, mkt)
        assert result.should_exit is False

    def test_both_above_no_exit(self) -> None:
        pos = make_pos(days_held=E2_CONFIRMATION_LAG)
        mkt = make_mkt(close=105.0, close_prev=104.0,
                       ma20=100.0, ma20_prev=99.0)
        result = exit_e2_ma20_failure(pos, mkt)
        assert result.should_exit is False

    def test_exactly_equal_to_ma20_no_exit(self) -> None:
        # Boundary: predicate is strict <, so equality does not trigger.
        pos = make_pos(days_held=E2_CONFIRMATION_LAG)
        mkt = make_mkt(close=100.0, close_prev=99.0,
                       ma20=100.0, ma20_prev=100.0)
        result = exit_e2_ma20_failure(pos, mkt)
        # close_t == ma20_t → today_below is False → no exit
        assert result.should_exit is False

    def test_ceiling_takes_priority(self) -> None:
        pos = make_pos(days_held=HOLD_CEILING_DAYS)
        mkt = make_mkt(close=90.0, close_prev=89.0,
                       ma20=100.0, ma20_prev=99.0)
        result = exit_e2_ma20_failure(pos, mkt)
        assert result.should_exit is True
        assert "time_stop" in result.reason

    def test_metadata_fields_present(self) -> None:
        pos = make_pos(days_held=E2_CONFIRMATION_LAG)
        mkt = make_mkt(close=99.0, close_prev=98.0,
                       ma20=100.0, ma20_prev=99.5)
        result = exit_e2_ma20_failure(pos, mkt)
        assert result.should_exit is True
        for key in ("close_t", "ma20_t", "close_t-1", "ma20_t-1"):
            assert key in result.metadata, f"Missing metadata key: {key}"


# =====================================================================
# E3 — RS deterioration
# =====================================================================


class TestExitE3RsDeterioration:
    def test_above_threshold_no_exit(self) -> None:
        pos = make_pos()
        mkt = make_mkt(rs_60d_rank=E3_RS_RANK_THRESHOLD + 0.01)
        result = exit_e3_rs_deterioration(pos, mkt)
        assert result.should_exit is False

    def test_exactly_at_threshold_no_exit(self) -> None:
        # Boundary: predicate is strict <, equality does not trigger.
        pos = make_pos()
        mkt = make_mkt(rs_60d_rank=E3_RS_RANK_THRESHOLD)
        result = exit_e3_rs_deterioration(pos, mkt)
        assert result.should_exit is False

    def test_below_threshold_exits(self) -> None:
        pos = make_pos()
        mkt = make_mkt(rs_60d_rank=E3_RS_RANK_THRESHOLD - 0.01)
        result = exit_e3_rs_deterioration(pos, mkt)
        assert result.should_exit is True
        assert "rs_deterioration" in result.reason

    def test_rank_zero_exits(self) -> None:
        pos = make_pos()
        mkt = make_mkt(rs_60d_rank=0.0)
        result = exit_e3_rs_deterioration(pos, mkt)
        assert result.should_exit is True

    def test_rank_one_no_exit(self) -> None:
        pos = make_pos()
        mkt = make_mkt(rs_60d_rank=1.0)
        result = exit_e3_rs_deterioration(pos, mkt)
        assert result.should_exit is False

    def test_rank_out_of_domain_below_zero(self) -> None:
        # rs_60d_rank is expected in [0, 1] by contract.
        # Current implementation does NOT validate domain; -0.01 fires
        # E3 because it satisfies rank < threshold. This test documents
        # current behaviour. If SPEC adds domain validation, update to
        # expect ValueError or equivalent.
        pos = make_pos()
        mkt = make_mkt(rs_60d_rank=-0.01)
        result = exit_e3_rs_deterioration(pos, mkt)
        assert result.should_exit is True  # fires: -0.01 < 0.50

    def test_rank_out_of_domain_above_one(self) -> None:
        # rs_60d_rank > 1.0: does not fire E3 (1.01 >= 0.50).
        # Documents current behaviour for out-of-domain inputs.
        pos = make_pos()
        mkt = make_mkt(rs_60d_rank=1.01)
        result = exit_e3_rs_deterioration(pos, mkt)
        assert result.should_exit is False  # does not fire: 1.01 >= 0.50

    def test_ceiling_takes_priority(self) -> None:
        pos = make_pos(days_held=HOLD_CEILING_DAYS)
        mkt = make_mkt(rs_60d_rank=0.0)
        result = exit_e3_rs_deterioration(pos, mkt)
        assert result.should_exit is True
        assert "time_stop" in result.reason

    def test_metadata_fields_present(self) -> None:
        pos = make_pos()
        mkt = make_mkt(rs_60d_rank=0.49)
        result = exit_e3_rs_deterioration(pos, mkt)
        assert result.should_exit is True
        assert "rs_60d_rank" in result.metadata
        assert "threshold" in result.metadata
        assert result.metadata["threshold"] == E3_RS_RANK_THRESHOLD


# =====================================================================
# E4 — Donchian low exit
# =====================================================================


class TestExitE4Donchian:
    def test_above_donchian_no_exit(self) -> None:
        pos = make_pos()
        mkt = make_mkt(close=99.0, donchian_low_excl=98.0)
        result = exit_e4_donchian(pos, mkt)
        assert result.should_exit is False

    def test_exactly_at_donchian_exits(self) -> None:
        # Boundary: predicate is <=, so equality triggers exit.
        pos = make_pos()
        mkt = make_mkt(close=98.0, donchian_low_excl=98.0)
        result = exit_e4_donchian(pos, mkt)
        assert result.should_exit is True
        assert "donchian" in result.reason

    def test_below_donchian_exits(self) -> None:
        pos = make_pos()
        mkt = make_mkt(close=97.0, donchian_low_excl=98.0)
        result = exit_e4_donchian(pos, mkt)
        assert result.should_exit is True

    def test_early_hold_below_donchian_exits(self) -> None:
        # Design decision: no days_held < lookback guard for E4.
        # Close <= donchian fires even on day 1 (per code comment:
        # "still represents a valid technical signal").
        pos = make_pos(days_held=1)
        mkt = make_mkt(close=97.0, donchian_low_excl=98.0)
        result = exit_e4_donchian(pos, mkt)
        assert result.should_exit is True

    def test_ceiling_takes_priority(self) -> None:
        pos = make_pos(days_held=HOLD_CEILING_DAYS)
        mkt = make_mkt(close=97.0, donchian_low_excl=98.0)
        result = exit_e4_donchian(pos, mkt)
        assert result.should_exit is True
        assert "time_stop" in result.reason

    def test_metadata_fields_present(self) -> None:
        pos = make_pos()
        mkt = make_mkt(close=97.0, donchian_low_excl=98.0)
        result = exit_e4_donchian(pos, mkt)
        assert result.should_exit is True
        for key in ("close", "donchian_low_excl", "lookback"):
            assert key in result.metadata, f"Missing metadata key: {key}"


# =====================================================================
# EXIT_FUNCTIONS registry — ABI lock
# =====================================================================


class TestExitFunctionsRegistry:
    """Confirm EXIT_FUNCTIONS maps every Candidate to a callable.

    This test locks the registry ABI so Step 3D wiring can rely on it.
    """

    def test_registry_contains_all_candidates(self) -> None:
        from scripts.run_phase6_evaluation import EXIT_FUNCTIONS, Candidate

        expected = {
            Candidate.ARM_B,
            Candidate.E1,
            Candidate.E2,
            Candidate.E3,
            Candidate.E4,
        }
        assert set(EXIT_FUNCTIONS.keys()) == expected

    def test_all_registry_values_callable(self) -> None:
        from scripts.run_phase6_evaluation import EXIT_FUNCTIONS

        for candidate, fn in EXIT_FUNCTIONS.items():
            assert callable(fn), f"EXIT_FUNCTIONS[{candidate}] is not callable"

    def test_registry_functions_return_exit_decision(self) -> None:
        from scripts.run_phase6_evaluation import EXIT_FUNCTIONS

        pos = make_pos()
        mkt = make_mkt()
        for candidate, fn in EXIT_FUNCTIONS.items():
            result = fn(pos, mkt)
            assert isinstance(result, ExitDecision), (
                f"EXIT_FUNCTIONS[{candidate}] returned {type(result)}, "
                f"expected ExitDecision"
            )
