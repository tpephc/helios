# tests/monitoring/test_intraday_monitor.py
"""Unit tests for intraday monitoring — v0.1.15.

Uses in-memory DuckDB and FakeQuoteSource.  No network I/O, no Telegram calls.

Schema loaded from the production migration SQL file (P1-4 fix).

Invariants verified
-------------------
1.  Zone transitions emit exactly one notification per edge.
2.  Hysteresis: dead-band price does not trigger NORMAL ↔ APPROACH.
3.  BREACH recovery: APPROACH before NORMAL when price is in approach band.
4.  Gap-down: NORMAL → BREACH (skipping APPROACH) handled correctly.
5.  BREACH ↔ APPROACH oscillation is correctly counted as separate transitions.
6.  Positions table is never modified (notify-only contract).
7.  Every zone transition appends a PENDING row to intraday_alert_transitions.
8.  DB is written BEFORE Telegram send (verified via CheckingBot).
9.  FAILED send still advances state; next poll does not re-trigger (P0-3).
10. RETURNING returns False when UPDATE matches 0 rows — no duplicate INSERT (P0-4).
11. Degraded feed does NOT suppress valid-quote position checks (P0-1).
12. Stale quotes are skipped without triggering transitions (P0-2).
13. System alert fires below threshold; cooldown suppresses duplicates.
14. Positions with entry_atr=0, max_close_since_entry=0, shares=0 are excluded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest

from execution.stop_logic import PriceZone, classify_zone, compute_stop_levels
from monitoring.intraday_monitor import (
    RunSummary,
    _OpenPosition,
    _try_advance_state_and_log,
    run_monitor,
)
from monitoring.quote_source import QuoteResult

# ---------------------------------------------------------------------------
# Schema setup
# ---------------------------------------------------------------------------

_MIGRATION_SQL = (
    Path(__file__).parents[2] / "data" / "migrations" / "add_intraday_tables.sql"
)

_POSITIONS_DDL = """
CREATE TABLE positions (
    position_id           TEXT    NOT NULL PRIMARY KEY,
    symbol                TEXT    NOT NULL,
    entry_atr             DOUBLE,
    max_close_since_entry DOUBLE,
    shares                BIGINT  NOT NULL,
    entry_price           DOUBLE  NOT NULL,
    status                TEXT    NOT NULL
);
"""

# Canonical test position:
#   max_close=60, entry_atr=1
#   → trailing_stop  = 58.0
#   → approach_enter = 58.5   (stop + 0.5 × atr)
#   → approach_exit  = 58.8   (stop + 0.8 × atr)
_SYM = "2891"
_POS_ID = "pos_test_001"
_T0 = datetime(2026, 5, 22, 1, 5, 0, tzinfo=timezone.utc)  # 09:05 TST


def _make_db() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect()
    conn.execute(_POSITIONS_DDL)
    conn.execute(_MIGRATION_SQL.read_text())
    return conn


def _insert_position(
    conn: duckdb.DuckDBPyConnection,
    position_id: str = _POS_ID,
    symbol: str = _SYM,
    entry_atr: float = 1.0,
    max_close_since_entry: float = 60.0,
    shares: int = 100,
    entry_price: float = 55.0,
) -> None:
    conn.execute(
        "INSERT INTO positions VALUES (?, ?, ?, ?, ?, ?, 'OPEN')",
        [position_id, symbol, entry_atr, max_close_since_entry, shares, entry_price],
    )


def _make_open_position(
    position_id: str = _POS_ID,
    symbol: str = _SYM,
    entry_atr: float = 1.0,
    max_close_since_entry: float = 60.0,
    shares: int = 100,
    entry_price: float = 55.0,
) -> _OpenPosition:
    return _OpenPosition(
        position_id=position_id,
        symbol=symbol,
        entry_atr=entry_atr,
        max_close_since_entry=max_close_since_entry,
        shares=shares,
        entry_price=entry_price,
    )


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class FakeQuoteSource:
    prices: dict[str, float | None]
    stale_symbols: set[str] = field(default_factory=set)

    def get_quotes(self, symbols: list[str]) -> dict[str, QuoteResult]:
        return {
            sym: QuoteResult(
                symbol=sym,
                price=self.prices.get(sym),
                price_ts=_T0 if self.prices.get(sym) is not None else None,
                is_stale=sym in self.stale_symbols or self.prices.get(sym) is None,
                error=None if self.prices.get(sym) is not None else "not_in_fixture",
            )
            for sym in symbols
        }


@dataclass
class FakeTelegramBot:
    messages: list[str] = field(default_factory=list)
    fail_send: bool = False

    def send_message(self, text: str, parse_mode: str | None = None) -> bool:
        if self.fail_send:
            return False
        self.messages.append(text)
        return True


def _poll(
    conn: duckdb.DuckDBPyConnection,
    price: float | None,
    minute_offset: int = 0,
    bot: FakeTelegramBot | None = None,
    stale: bool = False,
    symbol: str = _SYM,
) -> tuple[RunSummary, FakeTelegramBot]:
    if bot is None:
        bot = FakeTelegramBot()
    h, m = divmod(_T0.hour * 60 + _T0.minute + minute_offset, 60)
    run_at = _T0.replace(hour=h % 24, minute=m)
    stale_set = {symbol} if stale else set()
    summary = run_monitor(
        conn,
        FakeQuoteSource({symbol: price}, stale_symbols=stale_set),
        bot,
        run_at=run_at,
    )
    return summary, bot


# ---------------------------------------------------------------------------
# Tests: stop_logic classify_zone — hysteresis unit tests
# ---------------------------------------------------------------------------


class TestClassifyZone:
    def _lvl(self):
        return compute_stop_levels(max_close_since_entry=60.0, entry_atr=1.0)

    def test_normal_above_enter_stays_normal(self):
        assert classify_zone(59.0, self._lvl(), PriceZone.NORMAL) == PriceZone.NORMAL

    def test_normal_at_enter_triggers_approach(self):
        assert classify_zone(58.5, self._lvl(), PriceZone.NORMAL) == PriceZone.APPROACH

    def test_hysteresis_dead_band_from_approach_stays_approach(self):
        lvl = self._lvl()
        assert classify_zone(58.6, lvl, PriceZone.APPROACH) == PriceZone.APPROACH
        assert classify_zone(58.79, lvl, PriceZone.APPROACH) == PriceZone.APPROACH

    def test_hysteresis_dead_band_from_normal_stays_normal(self):
        lvl = self._lvl()
        assert classify_zone(58.7, lvl, PriceZone.NORMAL) == PriceZone.NORMAL

    def test_approach_exits_to_normal_above_exit(self):
        assert classify_zone(58.9, self._lvl(), PriceZone.APPROACH) == PriceZone.NORMAL

    def test_breach_unconditional_from_any_zone(self):
        lvl = self._lvl()
        assert classify_zone(58.0, lvl, PriceZone.NORMAL) == PriceZone.BREACH
        assert classify_zone(58.0, lvl, PriceZone.APPROACH) == PriceZone.BREACH
        assert classify_zone(57.0, lvl, PriceZone.BREACH) == PriceZone.BREACH

    def test_breach_partial_recovery_to_approach(self):
        assert classify_zone(58.5, self._lvl(), PriceZone.BREACH) == PriceZone.APPROACH

    def test_breach_full_recovery_to_normal(self):
        assert classify_zone(59.0, self._lvl(), PriceZone.BREACH) == PriceZone.NORMAL

    def test_gap_down_normal_to_breach(self):
        assert classify_zone(57.0, self._lvl(), PriceZone.NORMAL) == PriceZone.BREACH


# ---------------------------------------------------------------------------
# P0-4: RETURNING idempotency — unit test of _try_advance_state_and_log
# ---------------------------------------------------------------------------


class TestReturningIdempotency:
    """Test the RETURNING-based race protection directly."""

    def test_advance_succeeds_when_zone_matches(self):
        conn = _make_db()
        _insert_position(conn)
        # Seed initial state as NORMAL
        now_str = _T0.isoformat()
        conn.execute("""
            INSERT INTO intraday_alert_state
                (position_id, zone, zone_entered_at, last_price, last_checked_at, updated_at)
            VALUES (?, 'NORMAL', ?, NULL, ?, ?)
        """, [_POS_ID, now_str, now_str, now_str])

        position = _make_open_position()
        levels = compute_stop_levels(60.0, 1.0)
        advanced = _try_advance_state_and_log(
            conn, position, "run_test", _T0,
            PriceZone.NORMAL, PriceZone.APPROACH, 58.3, levels,
            transition_id="txn_test_001",
        )
        assert advanced is True
        count = conn.execute(
            "SELECT COUNT(*) FROM intraday_alert_transitions"
        ).fetchone()[0]
        assert count == 1

    def test_advance_returns_false_when_zone_already_changed(self):
        """Core P0-4 test: UPDATE WHERE zone='NORMAL' must match 0 rows when
        the DB already shows 'APPROACH' (another process won the race).
        RETURNING returns None → advanced=False → no duplicate INSERT."""
        conn = _make_db()
        _insert_position(conn)
        now_str = _T0.isoformat()
        # Simulate another process having already advanced to APPROACH
        conn.execute("""
            INSERT INTO intraday_alert_state
                (position_id, zone, zone_entered_at, last_price, last_checked_at, updated_at)
            VALUES (?, 'APPROACH', ?, 58.3, ?, ?)
        """, [_POS_ID, now_str, now_str, now_str])

        position = _make_open_position()
        levels = compute_stop_levels(60.0, 1.0)
        # Our process thinks zone is NORMAL and tries NORMAL → APPROACH
        advanced = _try_advance_state_and_log(
            conn, position, "run_test", _T0,
            PriceZone.NORMAL, PriceZone.APPROACH, 58.3, levels,
            transition_id="txn_test_002",
        )
        assert advanced is False
        # Critical: no duplicate transition must be inserted
        count = conn.execute(
            "SELECT COUNT(*) FROM intraday_alert_transitions"
        ).fetchone()[0]
        assert count == 0

    def test_advance_returns_false_leaves_existing_zone_unchanged(self):
        """After a failed advance attempt, the DB zone must still be APPROACH
        (not corrupted by the failed UPDATE)."""
        conn = _make_db()
        _insert_position(conn)
        now_str = _T0.isoformat()
        conn.execute("""
            INSERT INTO intraday_alert_state
                (position_id, zone, zone_entered_at, last_price, last_checked_at, updated_at)
            VALUES (?, 'APPROACH', ?, 58.3, ?, ?)
        """, [_POS_ID, now_str, now_str, now_str])

        position = _make_open_position()
        levels = compute_stop_levels(60.0, 1.0)
        _try_advance_state_and_log(
            conn, position, "run_test", _T0,
            PriceZone.NORMAL, PriceZone.APPROACH, 58.3, levels,
            transition_id="txn_test_003",
        )
        row = conn.execute(
            "SELECT zone FROM intraday_alert_state WHERE position_id = ?", [_POS_ID]
        ).fetchone()
        assert row[0] == "APPROACH"


# ---------------------------------------------------------------------------
# P0-1: degraded feed must not suppress valid-quote positions
# ---------------------------------------------------------------------------


class TestDegradedFeedP01:
    def test_valid_position_still_checked_when_feed_partially_degraded(self):
        conn = _make_db()
        _insert_position(conn, position_id="pos_a", symbol="2330")
        _insert_position(conn, position_id="pos_b", symbol="2891")
        bot = FakeTelegramBot()
        # 1/2 succeed (not below 0.5 threshold, so no system alert)
        run_monitor(
            conn,
            FakeQuoteSource({"2330": None, "2891": 58.3}),
            bot,
            run_at=_T0,
        )
        assert any("⚠️" in m for m in bot.messages)

    def test_system_alert_and_valid_position_both_fire(self):
        conn = _make_db()
        for pid, sym in [("pos_a", "2330"), ("pos_b", "2891"), ("pos_c", "2412")]:
            _insert_position(conn, position_id=pid, symbol=sym)
        bot = FakeTelegramBot()
        # 1/3 succeed → system_alert fires; the 1 valid position still processed
        run_monitor(
            conn,
            FakeQuoteSource({"2330": None, "2891": None, "2412": 58.3}),
            bot,
            run_at=_T0,
        )
        system_alerts = [m for m in bot.messages if "異常" in m]
        zone_alerts = [m for m in bot.messages if "接近停損" in m]
        assert len(system_alerts) == 1
        assert len(zone_alerts) == 1


# ---------------------------------------------------------------------------
# P0-2: stale quotes must not trigger transitions
# ---------------------------------------------------------------------------


class TestStaleQuoteP02:
    def test_stale_does_not_trigger_transition(self):
        conn = _make_db()
        _insert_position(conn)
        _, bot = _poll(conn, price=58.3, stale=True)
        # stale → success_rate=0 → system alert fires correctly.
        # Only assert no zone transition was triggered.
        assert conn.execute(
            "SELECT COUNT(*) FROM intraday_alert_transitions"
        ).fetchone()[0] == 0

    def test_stale_does_not_log_transition(self):
        conn = _make_db()
        _insert_position(conn)
        _poll(conn, price=58.3, stale=True)
        assert conn.execute(
            "SELECT COUNT(*) FROM intraday_alert_transitions"
        ).fetchone()[0] == 0

    def test_non_stale_same_price_triggers(self):
        conn = _make_db()
        _insert_position(conn)
        _, bot = _poll(conn, price=58.3, stale=False)
        assert len(bot.messages) == 1


# ---------------------------------------------------------------------------
# P0-3: outbox pattern — DB written before Telegram, FAILED still advances state
# ---------------------------------------------------------------------------


class TestOutboxPatternP03:
    def test_db_written_before_telegram_send(self):
        """PENDING transition must exist in DB at the moment send_message is called."""
        conn = _make_db()
        _insert_position(conn)

        class CheckingBot(FakeTelegramBot):
            def send_message(self, text: str, parse_mode: str | None = None) -> bool:
                # At send time, the PENDING row must already be committed.
                count = conn.execute(
                    "SELECT COUNT(*) FROM intraday_alert_transitions "
                    "WHERE notification_status = 'PENDING'"
                ).fetchone()[0]
                assert count == 1, "PENDING transition must be in DB before Telegram send"
                return super().send_message(text)

        _poll(conn, price=58.3, bot=CheckingBot())

    def test_successful_send_marks_sent(self):
        conn = _make_db()
        _insert_position(conn)
        _poll(conn, price=58.3)
        status = conn.execute(
            "SELECT notification_status FROM intraday_alert_transitions"
        ).fetchone()[0]
        assert status == "SENT"

    def test_failed_send_marks_failed(self):
        conn = _make_db()
        _insert_position(conn)
        _poll(conn, price=58.3, bot=FakeTelegramBot(fail_send=True))
        status = conn.execute(
            "SELECT notification_status FROM intraday_alert_transitions"
        ).fetchone()[0]
        assert status == "FAILED"

    def test_failed_send_still_advances_state_no_retrigger(self):
        """Zone must advance even when Telegram fails.
        Next poll with same zone must not log another transition."""
        conn = _make_db()
        _insert_position(conn)
        bot = FakeTelegramBot(fail_send=True)
        _poll(conn, price=58.3, minute_offset=0, bot=bot)   # NORMAL→APPROACH, FAILED
        _poll(conn, price=58.3, minute_offset=15, bot=bot)  # still APPROACH, no retrigger
        assert conn.execute(
            "SELECT COUNT(*) FROM intraday_alert_transitions"
        ).fetchone()[0] == 1


# ---------------------------------------------------------------------------
# Zone transitions
# ---------------------------------------------------------------------------


class TestTransitions:
    def test_normal_to_approach(self):
        conn = _make_db()
        _insert_position(conn)
        _, bot = _poll(conn, price=58.3)
        assert len(bot.messages) == 1
        assert "⚠️" in bot.messages[0]

    def test_approach_to_breach(self):
        conn = _make_db()
        _insert_position(conn)
        bot = FakeTelegramBot()
        _poll(conn, price=58.3, minute_offset=0, bot=bot)
        _poll(conn, price=57.5, minute_offset=15, bot=bot)
        assert "🔴" in bot.messages[1]

    def test_gap_down_normal_to_breach(self):
        conn = _make_db()
        _insert_position(conn)
        _, bot = _poll(conn, price=57.0)
        assert "🔴" in bot.messages[0]

    def test_breach_partial_recovery_to_approach(self):
        conn = _make_db()
        _insert_position(conn)
        bot = FakeTelegramBot()
        _poll(conn, price=57.5, minute_offset=0, bot=bot)
        _poll(conn, price=58.5, minute_offset=15, bot=bot)
        assert "↗️" in bot.messages[1]

    def test_full_recovery_three_alerts(self):
        conn = _make_db()
        _insert_position(conn)
        bot = FakeTelegramBot()
        _poll(conn, price=57.5, minute_offset=0, bot=bot)
        _poll(conn, price=58.5, minute_offset=15, bot=bot)
        _poll(conn, price=59.0, minute_offset=30, bot=bot)
        assert len(bot.messages) == 3
        assert "✅" in bot.messages[2]

    def test_breach_approach_breach_oscillation(self):
        """BREACH → APPROACH → BREACH should log 3 transitions and send 3 alerts.
        Each edge is independent; oscillation between adjacent zones is valid
        signal, not noise (unlike the dead-band NORMAL ↔ APPROACH case)."""
        conn = _make_db()
        _insert_position(conn)
        bot = FakeTelegramBot()
        _poll(conn, price=57.0, minute_offset=0, bot=bot)   # NORMAL → BREACH
        _poll(conn, price=58.5, minute_offset=15, bot=bot)  # BREACH → APPROACH
        _poll(conn, price=57.0, minute_offset=30, bot=bot)  # APPROACH → BREACH
        assert len(bot.messages) == 3
        txns = conn.execute(
            "SELECT from_zone, to_zone FROM intraday_alert_transitions "
            "ORDER BY transitioned_at"
        ).fetchall()
        assert txns == [
            ("NORMAL", "BREACH"),
            ("BREACH", "APPROACH"),
            ("APPROACH", "BREACH"),
        ]

    def test_hysteresis_no_oscillation_in_dead_band(self):
        conn = _make_db()
        _insert_position(conn)
        bot = FakeTelegramBot()
        for i, p in enumerate([59.0, 58.5, 58.7, 58.5, 58.7]):
            _poll(conn, price=p, minute_offset=i * 15, bot=bot)
        assert len(bot.messages) == 1

    def test_dead_band_from_normal_no_trigger(self):
        conn = _make_db()
        _insert_position(conn)
        bot = FakeTelegramBot()
        for i, p in enumerate([59.0, 58.7, 58.7, 58.7]):
            _poll(conn, price=p, minute_offset=i * 15, bot=bot)
        assert bot.messages == []


# ---------------------------------------------------------------------------
# RunSummary fields
# ---------------------------------------------------------------------------


class TestRunSummaryFields:
    def test_transitions_logged_vs_alerts_sent_on_failed_telegram(self):
        conn = _make_db()
        _insert_position(conn)
        summary, _ = _poll(conn, price=58.3, bot=FakeTelegramBot(fail_send=True))
        assert summary.transitions_logged == 1
        assert summary.alerts_sent == 0

    def test_transitions_logged_equals_alerts_sent_on_success(self):
        conn = _make_db()
        _insert_position(conn)
        summary, _ = _poll(conn, price=58.3)
        assert summary.transitions_logged == 1
        assert summary.alerts_sent == 1


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------


class TestInvariants:
    def test_positions_table_never_modified(self):
        conn = _make_db()
        _insert_position(conn)
        for p in [57.0, 58.5, 59.0]:
            _poll(conn, price=p)
        rows = conn.execute("SELECT status FROM positions").fetchall()
        assert all(r[0] == "OPEN" for r in rows)

    def test_every_transition_logged(self):
        conn = _make_db()
        _insert_position(conn)
        bot = FakeTelegramBot()
        _poll(conn, price=58.3, minute_offset=0, bot=bot)
        _poll(conn, price=57.5, minute_offset=15, bot=bot)
        txns = conn.execute(
            "SELECT from_zone, to_zone FROM intraday_alert_transitions ORDER BY transitioned_at"
        ).fetchall()
        assert txns == [("NORMAL", "APPROACH"), ("APPROACH", "BREACH")]

    def test_zone_entered_at_preserved_on_same_zone_poll(self):
        conn = _make_db()
        _insert_position(conn)
        _poll(conn, price=58.3, minute_offset=0)
        original = conn.execute(
            "SELECT zone_entered_at FROM intraday_alert_state"
        ).fetchone()[0]
        _poll(conn, price=58.3, minute_offset=15)
        after = conn.execute(
            "SELECT zone_entered_at FROM intraday_alert_state"
        ).fetchone()[0]
        assert original == after


# ---------------------------------------------------------------------------
# P1-1: invalid position data must be excluded
# ---------------------------------------------------------------------------


class TestInvalidPositionData:
    def test_entry_atr_zero_excluded(self):
        conn = _make_db()
        _insert_position(conn, entry_atr=0.0)
        _, bot = _poll(conn, price=58.3)
        assert bot.messages == []

    def test_max_close_zero_excluded(self):
        """max_close_since_entry=0 would produce a negative stop level."""
        conn = _make_db()
        _insert_position(conn, max_close_since_entry=0.0)
        _, bot = _poll(conn, price=58.3)
        assert bot.messages == []

    def test_shares_zero_excluded(self):
        conn = _make_db()
        _insert_position(conn, shares=0)
        _, bot = _poll(conn, price=58.3)
        assert bot.messages == []

    def test_all_invalid_excluded_no_crash(self):
        """None of the three invalid positions should cause an exception."""
        conn = _make_db()
        _insert_position(conn, position_id="pos_atr0", entry_atr=0.0)
        _insert_position(conn, position_id="pos_mc0", max_close_since_entry=0.0)
        _insert_position(conn, position_id="pos_sh0", shares=0)
        summary, bot = _poll(conn, price=58.3)
        assert bot.messages == []
        assert summary.positions_checked == 0


# ---------------------------------------------------------------------------
# System alert
# ---------------------------------------------------------------------------


class TestSystemAlert:
    def test_fires_on_all_failures(self):
        conn = _make_db()
        _insert_position(conn)
        _, bot = _poll(conn, price=None)
        assert any("異常" in m for m in bot.messages)

    def test_cooldown_suppresses_second(self):
        conn = _make_db()
        _insert_position(conn)
        bot = FakeTelegramBot()
        _poll(conn, price=None, minute_offset=0, bot=bot)
        _poll(conn, price=None, minute_offset=20, bot=bot)
        assert len([m for m in bot.messages if "異常" in m]) == 1

    def test_50_percent_success_does_not_trigger(self):
        """1/2 = 0.5 is NOT strictly less than the 0.5 threshold."""
        conn = _make_db()
        _insert_position(conn, position_id="pos_a", symbol="2330")
        _insert_position(conn, position_id="pos_b", symbol="2891")
        bot = FakeTelegramBot()
        run_monitor(
            conn,
            FakeQuoteSource({"2330": 100.0, "2891": None}),
            bot,
            run_at=_T0,
        )
        assert not any("異常" in m for m in bot.messages)


# ---------------------------------------------------------------------------
# P0: system alert Telegram failure must not block position supervision
# ---------------------------------------------------------------------------


class TestSystemAlertIsolation:
    """Verify that bot exceptions in _maybe_send_system_alert() are swallowed
    and position supervision continues (Advisor C v3 P0 finding)."""

    def test_system_alert_raises_does_not_crash_run_monitor(self):
        """bot.send_message() raising must not propagate out of run_monitor()."""
        conn = _make_db()
        for pid, sym in [("pos_a", "2330"), ("pos_b", "2891"), ("pos_c", "2412")]:
            _insert_position(conn, position_id=pid, symbol=sym)

        class AlwaysRaisesBot(FakeTelegramBot):
            def send_message(self, text: str, parse_mode: str | None = None) -> bool:
                raise ConnectionError("telegram unreachable")

        # 1/3 quotes succeed → success_rate < 0.5, system alert triggered,
        # bot raises.  run_monitor() must complete without exception.
        summary = run_monitor(
            conn,
            FakeQuoteSource({"2330": None, "2891": None, "2412": 58.3}),
            AlwaysRaisesBot(),
            run_at=_T0,
        )
        # positions_checked = positions passing SQL validity filter = 3.
        assert summary.positions_checked == 3
        # Zone transition written to DB even though Telegram is down.
        assert summary.transitions_logged == 1
        # No successful Telegram sends (bot raised on every call).
        assert summary.alerts_sent == 0

    def test_system_alert_raises_valid_position_zone_alert_still_fires(self):
        """When system alert raises but subsequent zone-alert bot call succeeds,
        the zone notification must be delivered (separate call, separate fate)."""
        conn = _make_db()
        for pid, sym in [("pos_a", "2330"), ("pos_b", "2891"), ("pos_c", "2412")]:
            _insert_position(conn, position_id=pid, symbol=sym)

        class FirstCallRaisesBot(FakeTelegramBot):
            """Raises on the system alert (first call); succeeds on zone alerts."""
            _call_count: int = 0

            def send_message(self, text: str, parse_mode: str | None = None) -> bool:
                self._call_count += 1
                if self._call_count == 1:
                    raise ConnectionError("system alert down")
                return super().send_message(text)

        bot = FirstCallRaisesBot()
        summary = run_monitor(
            conn,
            FakeQuoteSource({"2330": None, "2891": None, "2412": 58.3}),
            bot,
            run_at=_T0,
        )
        assert summary.positions_checked == 3
        assert summary.transitions_logged == 1
        # Zone alert for 2412 must have succeeded (second bot call).
        assert summary.alerts_sent == 1
        assert any("⚠️" in m for m in bot.messages)
