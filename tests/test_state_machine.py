# tests/test_state_machine.py
"""v0.1.14.2-c state-machine + lifecycle + approval + idempotency tests.

Covers reviewer's mandated test list:
  - test_approve_pending_to_position           (P0-4)
  - test_reject_pending                        (P0-4)
  - test_late_approve_marks_timeout            (P0-4 + P1-5)
  - test_atr_drift_expiry                      (P0-4)
  - test_double_approve_idempotent             (P0-4 + P1-6)
  - test_same_symbol_double_open_blocked       (P0-4)
  - test_t_plus_1_fill_date                    (P0-4 + P0-2)
  - test_push_failure_does_not_leave_pending   (P0-4 + P0-3)
  - test_unauthorized_chat_ignored             (P0-4 + P0-1)
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

from tests.conftest import MockTelegramBot, seed_price

# ─────────────────────────────────────────────────────────────
# P0-1: unauthorized chat
# ─────────────────────────────────────────────────────────────


def test_unauthorized_chat_ignored(tmp_db, test_account_id):
    """Messages from unconfigured chat_id must be ignored (security gate).

    v0.1.14.3.7: listener now drains pre-startup updates, so pre-seeding the
    bot queue would just get drained away. We inject via the on_poll hook,
    which fires only on real polls (timeout > 0) — i.e., after the drain.
    """
    from communication.telegram.listener import listen_for_approvals
    from execution.paper_broker import PaperBroker

    bot = MockTelegramBot(chat_id="AUTHORIZED")

    def inject_on_first_poll(poll_num: int) -> None:
        if poll_num == 0:
            # Inbound msg from a DIFFERENT chat (post-drain, mid-loop)
            bot.enqueue_text("/help", chat_id="ATTACKER")
    bot.on_poll = inject_on_first_poll

    summary = listen_for_approvals(
        bot=bot, broker=PaperBroker(account_id=test_account_id),
        account_id=test_account_id,
        fill_date=date(2026, 5, 2),
        target_notional_for=lambda _: 100000.0,
        duration_seconds=1, poll_timeout=1,
    )

    # The /help command should have been blocked → not in sent messages
    assert not any("commands" in s.lower() for s in bot.sent), (
        f"unauthorized chat got response: {bot.sent}"
    )
    # And tracked as ignored with the right reason
    assert any("unauthorized_chat" in r for _, r in summary["ignored"]), (
        f"expected unauthorized_chat in ignored, got: {summary['ignored']}"
    )


# ─────────────────────────────────────────────────────────────
# P0-2: T+1 fill_date
# ─────────────────────────────────────────────────────────────


def test_t_plus_1_fill_date(tmp_db, seed_calendar):
    """next_fillable_day(T) returns next trading day with data, not T itself."""
    from market.trading_calendar import next_fillable_day

    cal = seed_calendar  # 10 consecutive trading days starting Mon 2026-05-04
    nxt = next_fillable_day(cal[0])
    assert nxt == cal[1], f"expected {cal[1]}, got {nxt}"

    # Last day in calendar has no successor within max_forward_days bound
    nxt_end = next_fillable_day(cal[-1], max_forward_days=2)
    assert nxt_end is None


def test_t_plus_1_fill_uses_next_day_open(tmp_db, seed_calendar, test_account_id):
    """PaperBroker.submit_buy must use the fill_date's adj_open, not T's.

    v0.1.14.3.1: renamed from `..._next_day_close` — under v0.1.14.3+ the
    semantic IS next-day open. Test body unchanged: seed_calendar puts
    adj_open == adj_close so the ref_price 140.5 assertion still validates
    that the broker reads cal[1] (T+1), not cal[0] (T). Column-correctness
    is covered by `test_fill_uses_adj_open_not_adj_close`; together they
    cover both axes (which day + which column).
    """
    from execution.paper_broker import PaperBroker

    broker = PaperBroker(account_id=test_account_id)
    cal = seed_calendar
    # close on cal[0] = 140.0; close on cal[1] = 140.5 (per seed_calendar pattern)
    result = broker.submit_buy(
        symbol="0050", target_notional=100000, fill_date=cal[1],
    )
    assert result.success
    # ref_price should be 140.5 (cal[1] open=close), not 140.0 (cal[0])
    assert abs(result.ref_price - 140.5) < 1e-6, (
        f"fill used wrong day: ref_price={result.ref_price}"
    )


# ─────────────────────────────────────────────────────────────
# P0-4 / P0-3: push failure
# ─────────────────────────────────────────────────────────────


def test_push_failure_does_not_leave_pending(tmp_db, seed_calendar, monkeypatch, test_account_id):
    """If Telegram push returns None, signal must be transitioned out of PENDING.

    Per reviewer P0-3: 'missed signal > wrong trade'.
    """
    from scripts.process_entries import generate_pending_signals

    bot = MockTelegramBot(succeed=False)  # send_message returns None

    # Stub strategy to produce one candidate matching seed_calendar's symbol
    from typing import ClassVar

    class FakeSig:
        stock_id = "0050"
        strategy = "trend_breakout_v1"
        side = "buy"
        score = 0.9
        entry_price = 140.0
        entry_atr = 2.0
        regime = "bull"
        reason: ClassVar[list[str]] = ["test"]
        metadata: ClassVar[dict] = {}

    import scripts.process_entries as pe
    monkeypatch.setattr(pe, "TrendBreakoutStrategy",
                        lambda: type("S", (), {"generate_signals": lambda self, as_of: [FakeSig()]})())
    monkeypatch.setattr(pe, "_evaluate_constraints",
                        lambda candidates, **kw: [(c, True, None) for c in candidates])

    pending, _ = generate_pending_signals(
        as_of=seed_calendar[0], capital=1_000_000, bot=bot,
        account_id=test_account_id,
    )

    # Expected: pending list is empty (push failed, signal expired)
    assert pending == [], f"push failure left PENDING: {pending}"
    # Signal should exist in DB but with status != PENDING
    from data.database import connect
    with connect(read_only=True) as conn:
        rows = conn.execute(
            "SELECT signal_id, approval_status, expired_reason FROM signals"
        ).fetchall()
    assert len(rows) == 1, f"expected 1 signal, got {rows}"
    assert rows[0][1] in ("TIMEOUT", "EXPIRED_DRIFT"), (
        f"signal not transitioned out of PENDING: {rows[0]}"
    )
    assert rows[0][2] == "telegram_push_failed", f"wrong reason: {rows[0][2]}"


# ─────────────────────────────────────────────────────────────
# Approve / Reject / Idempotency
# ─────────────────────────────────────────────────────────────


def test_approve_pending_to_position(tmp_db, seed_calendar, test_account_id):
    """Happy path: PENDING signal → approve → OPEN position."""
    from execution.approvals import approve_signal
    from execution.paper_broker import PaperBroker
    from storage.positions import get_open_positions
    from storage.signals import save_signal

    sid = save_signal(
        symbol="0050", strategy="trend_breakout_v1", signal_type="buy",
        score=0.9, price=140.0, reason=["test"],
        signal_date=seed_calendar[0],
        entry_atr=2.0, regime="bull",
    ).signal_id

    ok, msg, pos_id = approve_signal(
        sid, target_notional=100_000, fill_date=seed_calendar[1],
        broker=PaperBroker(account_id=test_account_id), approved_by="pytest",
        account_id=test_account_id,
    )
    assert ok, f"approve failed: {msg}"
    assert pos_id is not None

    opens = get_open_positions(symbol="0050", account_id=test_account_id)
    assert len(opens) == 1
    assert opens[0].entry_signal_id == sid
    assert opens[0].regime_at_entry == "bull"


def test_reject_pending(tmp_db, seed_calendar):
    from execution.approvals import reject_signal
    from storage.signals import get_signal, save_signal

    sid = save_signal(
        symbol="0050", strategy="trend_breakout_v1", signal_type="buy",
        score=0.5, price=140.0, reason=["x"],
        signal_date=seed_calendar[0],
        entry_atr=2.0, regime="bull",
    ).signal_id
    ok, _msg = reject_signal(sid)
    assert ok
    assert get_signal(sid).approval_status == "REJECTED"


def test_late_approve_marks_timeout(tmp_db, seed_calendar, monkeypatch, test_account_id):
    """P1-5: late /approve must transition signal to TIMEOUT, not just error out."""
    from execution.approvals import approve_signal
    from execution.paper_broker import PaperBroker
    from storage.signals import get_signal, save_signal

    sid = save_signal(
        symbol="0050", strategy="trend_breakout_v1", signal_type="buy",
        score=0.5, price=140.0, reason=["x"],
        signal_date=seed_calendar[0],
        entry_atr=2.0, regime="bull", timeout_minutes=1,
    ).signal_id
    # Wind the clock past timeout — patch datetime.now() in approvals module
    from execution import approvals as ap
    fake_now = datetime.now() + timedelta(minutes=10)
    monkeypatch.setattr(ap, "datetime",
                        type("DT", (), {"now": staticmethod(lambda: fake_now)}))

    ok, msg, _ = approve_signal(
        sid, target_notional=100_000, fill_date=seed_calendar[1],
        broker=PaperBroker(account_id=test_account_id),
        account_id=test_account_id,
    )
    assert not ok
    assert "已逾時" in msg
    # KEY assertion: signal now TIMEOUT, not PENDING
    assert get_signal(sid).approval_status == "TIMEOUT"
    assert get_signal(sid).expired_reason == "late_approval_after_timeout"


def test_double_approve_idempotent(tmp_db, seed_calendar, test_account_id):
    """P1-6: second /approve on same signal returns False, doesn't double-fill."""
    from execution.approvals import approve_signal
    from execution.paper_broker import PaperBroker
    from storage.positions import get_open_positions
    from storage.signals import save_signal

    sid = save_signal(
        symbol="0050", strategy="trend_breakout_v1", signal_type="buy",
        score=0.5, price=140.0, reason=["x"],
        signal_date=seed_calendar[0],
        entry_atr=2.0, regime="bull",
    ).signal_id

    broker = PaperBroker(account_id=test_account_id)
    ok1, _, _ = approve_signal(sid, target_notional=100_000,
                               fill_date=seed_calendar[1], broker=broker,
                               account_id=test_account_id)
    ok2, _msg2, pos2 = approve_signal(sid, target_notional=100_000,
                                      fill_date=seed_calendar[1], broker=broker,
                                      account_id=test_account_id)
    assert ok1
    assert not ok2
    assert pos2 is None
    # Still exactly one open position
    assert len(get_open_positions(symbol="0050", account_id=test_account_id)) == 1


def test_same_symbol_double_open_blocked(tmp_db, seed_calendar, test_account_id):
    """lifecycle.open_position_from_signal must refuse to open second position
    when one is already OPEN for that symbol."""
    from execution.lifecycle import open_position_from_signal
    from execution.paper_broker import PaperBroker
    from storage.positions import OPEN, get_open_positions, open_position
    from storage.signals import save_signal

    # Pre-seed an OPEN position for 0050
    open_position(
        account_id=test_account_id,
        symbol="0050", strategy="trend_breakout_v1",
        entry_date=seed_calendar[0], entry_price=140.0, entry_atr=2.0,
        regime_at_entry="bull", sector="etf", is_etf=True,
        shares=100, notional_at_entry=14000, status=OPEN,
    )
    sid = save_signal(
        symbol="0050", strategy="trend_breakout_v1", signal_type="buy",
        score=0.9, price=140.0, reason=["x"],
        signal_date=seed_calendar[0],
        entry_atr=2.0, regime="bull",
    ).signal_id
    # storage requires APPROVED status before lifecycle.open will proceed
    from storage.signals import update_approval
    update_approval(sid, "APPROVED", approved_by="pytest")

    pos_id = open_position_from_signal(
        signal_id=sid, target_notional=100_000,
        fill_date=seed_calendar[1], broker=PaperBroker(account_id=test_account_id),
        account_id=test_account_id,
    )
    assert pos_id is None, "second open for same symbol must be refused"
    assert len(get_open_positions(symbol="0050", account_id=test_account_id)) == 1


# ─────────────────────────────────────────────────────────────
# ATR drift expiry
# ─────────────────────────────────────────────────────────────


def test_atr_drift_expiry(tmp_db):
    """expire_by_drift must transition signals whose price moved > 0.5×ATR."""
    from execution.expiry import expire_by_drift
    from storage.signals import get_signal, save_signal

    # Seed price for 0050 on day_T+1 — moved well above 0.5×ATR=1.0
    seed_price("0050", date(2026, 5, 2), close=145.0, atr_14=2.0)

    sid = save_signal(
        symbol="0050", strategy="trend_breakout_v1", signal_type="buy",
        score=0.5, price=140.0, reason=["x"],
        signal_date=date(2026, 5, 1),
        entry_atr=2.0, regime="bull",
    ).signal_id
    # Drift = |145 - 140| = 5.0, threshold = 0.5 * 2.0 = 1.0 → must expire
    expired = expire_by_drift(date(2026, 5, 2))
    assert sid in expired, f"signal not in expired list: {expired}"
    assert get_signal(sid).approval_status == "EXPIRED_DRIFT"


def test_atr_drift_under_threshold_no_expire(tmp_db):
    """Drift within 0.5×ATR must NOT expire (negative case for symmetry)."""
    from execution.expiry import expire_by_drift
    from storage.signals import get_signal, save_signal

    seed_price("0050", date(2026, 5, 2), close=140.5, atr_14=2.0)
    # Drift = 0.5, threshold = 1.0 → should NOT expire

    sid = save_signal(
        symbol="0050", strategy="trend_breakout_v1", signal_type="buy",
        score=0.5, price=140.0, reason=["x"],
        signal_date=date(2026, 5, 1),
        entry_atr=2.0, regime="bull",
    ).signal_id
    expired = expire_by_drift(date(2026, 5, 2))
    assert sid not in expired
    assert get_signal(sid).approval_status == "PENDING"


# ─────────────────────────────────────────────────────────────
# v0.1.14.2-c2 — T+1 freshness contract regression
# ─────────────────────────────────────────────────────────────


def test_freshness_blocks_when_no_t_plus_1_data(tmp_db):
    """v0.1.14.2-c2: check_data_freshness must require T+1 data, not just as_of.

    Regression from nexus smoke test 2026-05-17: with `latest == as_of`, Step 1
    (freshness) passed because `latest >= as_of`, but Step 4 raised an opaque
    RuntimeError because `next_trading_day(as_of)` returned None (no T+1 data).

    Helios principle: errors must be early, clean, and explainable. Step 1 is
    the gate; the controlled-abort message must name the failure precisely.
    """
    from execution.shutdown import check_data_freshness

    # Seed data only up to as_of=2026-05-15; no 2026-05-18 data ingested yet.
    seed_price("0050", date(2026, 5, 14), close=140.0)
    seed_price("0050", date(2026, 5, 15), close=140.5)

    # latest == as_of: must be controlled-abort, not pass-and-explode-later.
    ok, msg = check_data_freshness(date(2026, 5, 15))
    assert ok is False, f"expected False, got True (msg={msg!r})"
    assert "data_not_ready_for_t_plus_1_fill" in msg, f"bad msg: {msg!r}"
    assert "as_of=2026-05-15" in msg
    assert "latest=2026-05-15" in msg

    # Symmetry: latest > as_of (5/14 has 5/15 as T+1) must still pass.
    ok2, msg2 = check_data_freshness(date(2026, 5, 14))
    assert ok2 is True, f"expected True, got False (msg={msg2!r})"
    assert "T+1 fill day 2026-05-15 covered" in msg2


# ─────────────────────────────────────────────────────────────
# v0.1.14.2-c3 — temporal semantics + calendar consolidation
# ─────────────────────────────────────────────────────────────


def test_cross_day_idempotency_under_clock_drift(tmp_db, seed_calendar, monkeypatch):
    """P0-2: idempotency must use signal_date (market semantic), NOT created_at::date.

    Pre-c3 bug: `_has_active_signal_for` queried `CAST(timestamp AS DATE) = signal_date`.
    A catch-up run (e.g. saving Fri's signal on Sat) wrote timestamp=Sat, signal_date=Fri.
    Querying for Fri's signal returned nothing → duplicate created.

    This test simulates the cross-day scenario by monkey-patching datetime.now()
    in storage.signals so the row's created_at is in a different calendar day
    than its signal_date. Idempotency must still find the duplicate.
    """
    from scripts.process_entries import _has_active_signal_for
    from storage import signals as _signals
    from storage.signals import save_signal

    target_day = seed_calendar[0]  # market semantic date

    # First save "happens" Friday 16:30 post-close (after target_day was already over)
    class _FakeNowFri:
        @staticmethod
        def now():
            return datetime(2026, 5, 8, 16, 30)
    monkeypatch.setattr(_signals, "datetime", _FakeNowFri)
    save_signal(
        symbol="0050", strategy="trend_breakout_v1", signal_type="buy",
        score=0.9, price=140.0, reason=["catch-up test"],
        signal_date=target_day,
        entry_atr=2.0, regime="bull",
    )

    # Verify cross-day: created_at::date != signal_date
    from data.database import connect
    with connect(read_only=True) as conn:
        row = conn.execute(
            "SELECT signal_date, CAST(created_at AS DATE) FROM signals"
        ).fetchone()
    assert row[0] == target_day, f"signal_date stored wrong: {row[0]}"
    assert row[1] != target_day, (
        f"test setup broken: created_at::date should differ from signal_date "
        f"(got both = {target_day})"
    )

    # Second "run" on a third day — different created_at again
    class _FakeNowSat:
        @staticmethod
        def now():
            return datetime(2026, 5, 9, 10, 0)
    monkeypatch.setattr(_signals, "datetime", _FakeNowSat)

    # The actual P0-2 assertion: idempotency MUST find the prior signal
    # for target_day, despite created_at::date never matching target_day.
    found = _has_active_signal_for(
        symbol="0050", strategy="trend_breakout_v1",
        signal_type="buy", signal_date=target_day,
    )
    assert found is True, (
        "P0-2 regression: cross-day idempotency missed duplicate "
        "(this is exactly the bug pre-c3 had)"
    )

    # Negative: a different signal_date is correctly not matched
    other_day = seed_calendar[1]
    not_found = _has_active_signal_for(
        symbol="0050", strategy="trend_breakout_v1",
        signal_type="buy", signal_date=other_day,
    )
    assert not_found is False


def test_calendar_vs_fillable_day_split(tmp_db):
    """P0-3: next_trading_day = calendar truth; next_fillable_day = calendar + data.

    Pre-c3: a single `next_trading_day` in execution.shutdown conflated these
    two concerns by querying daily_price_adj. c3 splits them in market.trading_calendar:
      - next_trading_day      → answers 'is this date on the market calendar?'
      - next_fillable_day     → answers 'is this date on the calendar AND ingested?'
    """
    from market.trading_calendar import next_fillable_day, next_trading_day

    # Seed data ONLY through Fri 2026-05-15. Mon 5/18 is a trading day per calendar
    # but has no data.
    seed_price("0050", date(2026, 5, 15), close=140.0)

    # Calendar truth: Mon 5/18 is the next trading day after Fri 5/15
    cal_next = next_trading_day(date(2026, 5, 15))
    assert cal_next == date(2026, 5, 18), (
        f"calendar next_trading_day: expected 2026-05-18, got {cal_next}"
    )

    # Fillability: 5/18 is calendar trading day BUT no data → None
    fill_next = next_fillable_day(date(2026, 5, 15))
    assert fill_next is None, (
        f"next_fillable_day must return None when data absent; got {fill_next}"
    )

    # After data ingest for 5/18: both agree
    seed_price("0050", date(2026, 5, 18), close=140.5)
    assert next_fillable_day(date(2026, 5, 15)) == date(2026, 5, 18)
    assert next_trading_day(date(2026, 5, 15)) == date(2026, 5, 18)


def test_preflight_decline_does_not_cascade(tmp_db, isolated_marker):
    """c2 smoke test bug: preflight RuntimeError wrote 'aborted' marker, blocking
    every subsequent run forever. c3 separates DECLINED from ABORTED:
      - shutdown_guard catches PreflightDecline → writes 'declined_preflight' marker
      - check_previous_run treats 'declined_preflight' as proceed-safe
        (preflight by definition made no side effects)
    """
    from execution.shutdown import (
        PreflightDecline,
        check_previous_run,
        read_marker,
        shutdown_guard,
    )

    # Simulate a run that declines at preflight
    exited = False
    try:
        with shutdown_guard(date(2026, 5, 15)) as _g:
            raise PreflightDecline("data_not_ready_for_t_plus_1_fill: as_of=2026-05-15")
    except SystemExit as e:
        exited = True
        assert e.code == 1, f"expected SystemExit(1), got SystemExit({e.code})"
    assert exited, "PreflightDecline must produce SystemExit, not propagate raw"

    # Marker must be 'declined_preflight', not 'aborted'
    marker = read_marker()
    assert marker is not None, "marker missing — should record decline for audit"
    assert marker["status"] == "declined_preflight", (
        f"got status={marker['status']!r}; pre-c3 wrote 'aborted' here, causing cascade"
    )

    # Critical anti-cascade assertion: a subsequent run must NOT be blocked.
    ok, msg = check_previous_run(date(2026, 5, 16))
    assert ok is True, (
        f"declined_preflight must be proceed-safe (no side effects to investigate); "
        f"got block: {msg}"
    )
    assert "no side effects" in msg or "declined_preflight" in msg


def test_is_trading_day_calendar_correctness(tmp_db):
    """Calendar correctness: weekends + known TW holidays are never trading days,
    regardless of whether data exists. Sanity check for the calendar consolidation."""
    from market.trading_calendar import is_trading_day

    # Weekend
    assert is_trading_day(date(2026, 5, 17)) is False, "Sunday must not be trading day"
    assert is_trading_day(date(2026, 5, 16)) is False, "Saturday must not be trading day"
    # Holiday (Labor Day 5/1 is in TW_HOLIDAYS_FALLBACK)
    assert is_trading_day(date(2026, 5, 1)) is False, "Labor Day must not be trading day"
    # Normal weekday
    assert is_trading_day(date(2026, 5, 4)) is True, "Monday post-Labor Day must be trading day"


# ─────────────────────────────────────────────────────────────
# v0.1.14.3 — Fill realism + liquidity sanity + stability instrumentation
# ─────────────────────────────────────────────────────────────


def test_fill_uses_adj_open_not_adj_close(tmp_db, test_account_id):
    """v0.1.14.3 A: PaperBroker must read adj_open (not adj_close) for fills.

    Seeds distinct adj_open and adj_close on the fill day, then asserts the
    returned ref_price equals adj_open. Defends against any regression that
    reverts to the pre-v0.1.14.3 adj_close lookup.
    """
    from execution.paper_broker import PaperBroker

    fill_date = date(2026, 5, 4)
    # adj_open=140.0, adj_close=145.0 — gap is the test signal
    seed_price("0050", fill_date, close=145.0, open_price=140.0)

    result = PaperBroker(account_id=test_account_id).submit_buy(
        symbol="0050", target_notional=50_000, fill_date=fill_date,
    )
    assert result.success, f"fill failed: {result.error}"
    assert abs(result.ref_price - 140.0) < 1e-6, (
        f"fill must use adj_open=140.0, got ref_price={result.ref_price} "
        f"(close=145.0 would indicate stale adj_close path)"
    )


def test_drift_gate_uses_adj_open(tmp_db, seed_calendar, test_account_id):
    """v0.1.14.3 A: approvals._check_atr_drift must compare signal price to
    adj_open[fill_date], not adj_close[fill_date].

    Constructs a case where adj_close[fill_date] is WITHIN drift threshold but
    adj_open[fill_date] is OUTSIDE — drift gate must reject (because the
    actual fill happens at open, not close). Under the pre-v0.1.14.3 path
    this would have passed.
    """
    from execution.approvals import approve_signal
    from execution.paper_broker import PaperBroker
    from storage.signals import get_signal, save_signal

    fill_date = seed_calendar[1]
    # signal price = 140.0 (set in seed_calendar). entry_atr = 2.0, threshold = 0.5×2 = 1.0
    # adj_open = 142.0 (drift 2.0 > 1.0 → must reject)
    # adj_close = 140.5 (drift 0.5 < 1.0 → would have passed under old code)
    seed_price("0050", fill_date, close=140.5, open_price=142.0, atr_14=2.0)

    sid = save_signal(
        symbol="0050", strategy="trend_breakout_v1", signal_type="buy",
        score=0.9, price=140.0, reason=["test"],
        signal_date=seed_calendar[0],
        entry_atr=2.0, regime="bull",
    ).signal_id
    ok, msg, _ = approve_signal(
        sid, target_notional=50_000, fill_date=fill_date,
        broker=PaperBroker(account_id=test_account_id), approved_by="pytest",
        account_id=test_account_id,
    )
    assert not ok, f"drift gate must reject — adj_open drifted 2.0 > 1.0. msg={msg}"
    assert "偏離" in msg
    # And the signal should be marked EXPIRED_DRIFT
    assert get_signal(sid).approval_status == "EXPIRED_DRIFT"


def test_liquidity_check_blocks_oversized_buy(tmp_db):
    """v0.1.14.3 B: PaperBroker must refuse buys whose share count exceeds
    MAX_FILL_RATIO (0.5%) of fill-day volume."""
    from execution.paper_broker import PaperBroker

    fill_date = date(2026, 5, 4)
    # Set fill price low (1.0) and volume tiny (10000) so a modest notional
    # produces shares = 50_000 / 1.0 ≈ 49_999, ratio ≈ 5.0 → way above 0.5%.
    seed_price("0050", fill_date, close=1.0, open_price=1.0, volume=10_000)

    result = PaperBroker().submit_buy(
        symbol="0050", target_notional=50_000, fill_date=fill_date,
    )
    assert not result.success
    assert result.error == "insufficient_liquidity", f"got {result.error!r}"


def test_liquidity_check_allows_normal_buy(tmp_db, test_account_id):
    """v0.1.14.3 B: a buy under the 0.5% liquidity threshold must pass."""
    from execution.paper_broker import PaperBroker

    fill_date = date(2026, 5, 4)
    # 100-NTD price, 1M volume. 50k notional → ~500 shares → 500/1M = 0.05% < 0.5%
    seed_price("0050", fill_date, close=100.0, open_price=100.0, volume=1_000_000)

    result = PaperBroker(account_id=test_account_id).submit_buy(
        symbol="0050", target_notional=50_000, fill_date=fill_date,
    )
    assert result.success, f"normal buy should pass, got error={result.error!r}"
    # Sanity check the ratio is well under 0.5%
    assert result.shares / 1_000_000 < 0.005


def test_liquidity_check_blocks_oversized_sell(tmp_db):
    """v0.1.14.3 B: sells are checked the same way as buys (symmetric guard)."""
    from execution.paper_broker import PaperBroker

    fill_date = date(2026, 5, 4)
    seed_price("0050", fill_date, close=100.0, open_price=100.0, volume=10_000)

    # 100 shares / 10_000 volume = 1.0% > 0.5% → must fail
    result = PaperBroker().submit_sell(
        symbol="0050", shares=100, fill_date=fill_date,
    )
    assert not result.success
    assert result.error == "insufficient_liquidity"


def test_scan_and_exit_reports_open_position_ages(tmp_db, seed_calendar, test_account_id):
    """v0.1.14.3 C: scan_and_exit summary must carry per-position age info
    so 5-day rollup can surface stuck-OPEN positions."""
    from scripts.run_exit_scan import scan_and_exit
    from storage.positions import OPEN, open_position

    open_position(
        account_id=test_account_id,
        symbol="0050", strategy="trend_breakout_v1",
        entry_date=seed_calendar[0], entry_price=140.0, entry_atr=2.0,
        regime_at_entry="bull", sector="etf", is_etf=True,
        shares=100, notional_at_entry=14000, status=OPEN,
    )
    summary = scan_and_exit(as_of=seed_calendar[3], fill_date=seed_calendar[4], account_id=test_account_id)
    ages = summary["open_position_days"]
    assert len(ages) == 1
    entry = ages[0]
    assert entry["symbol"] == "0050"
    # Age is in calendar days from entry to as_of (could be > 3 since
    # seed_calendar steps via trading days, skipping weekends).
    assert entry["age_days"] is not None and entry["age_days"] >= 3


def test_scan_and_exit_reports_failed_symbols(tmp_db, seed_calendar, monkeypatch, test_account_id):
    """v0.1.14.3 C: scan_and_exit must record symbols whose exit FILL failed,
    not just the count. run_summary uses this for cross-day streak detection."""
    from scripts.run_exit_scan import scan_and_exit
    from storage.positions import OPEN, open_position

    # Open a position. Seed today's data so exit RULE fires (regime exit needs
    # 'bear' regime to fire under defaults).
    open_position(
        account_id=test_account_id,
        symbol="0050", strategy="trend_breakout_v1",
        entry_date=seed_calendar[0], entry_price=140.0, entry_atr=2.0,
        regime_at_entry="bull", sector="etf", is_etf=True,
        shares=100, notional_at_entry=14000, status=OPEN,
    )
    as_of = seed_calendar[3]
    # Today's data with bear regime → regime_exit should trigger
    seed_price("0050", as_of, close=140.0, open_price=140.0, regime="bear")
    # Fill day has no data → close_position_for_exit will fail at broker
    # (no row in daily_price_adj for fill_date — but seed_calendar already
    # seeded fill_date as a trading day with close=140.5. We need to invalidate
    # the fill day's data to force failure.) Use a fill_date deliberately
    # outside seed_calendar — pick one we know has no data.
    from datetime import timedelta
    far_future = seed_calendar[-1] + timedelta(days=30)

    summary = scan_and_exit(as_of=as_of, fill_date=far_future, account_id=test_account_id)
    # Either the exit fired and fill failed, OR the rule didn't fire.
    # The test guarantees the rule fires (bear regime on a bull-entry position
    # triggers RegimeExit), so we expect a failed exit.
    assert summary["exits_failed"] >= 1, f"expected exit failure, got {summary}"
    assert "0050" in summary["exits_failed_symbols"]


def test_run_summary_compute_failure_streaks_basic():
    """v0.1.14.3 C: compute_failure_streaks correctly counts consecutive runs
    where a symbol appears in exits_failed_symbols, ignoring non-ok runs."""
    from scripts.run_summary import compute_failure_streaks

    history = [
        {"status": "ok", "summary": {"exits_failed_symbols": ["2330"]}},
        {"status": "ok", "summary": {"exits_failed_symbols": ["2330", "2317"]}},
        # Holiday — declined_preflight, no scan happened; should NOT break streak
        {"status": "declined_preflight", "summary": {"reason": "non_trading_day"}},
        {"status": "ok", "summary": {"exits_failed_symbols": ["2330"]}},
        # 2317 recovered (not in this run); 2330 still failing
    ]
    streaks = compute_failure_streaks(history)
    assert streaks == {"2330": 3}, f"got {streaks}"


def test_run_summary_compute_failure_streaks_recovery():
    """v0.1.14.3 C: a symbol that recovers (not in the latest ok run) must
    NOT appear in streaks output, even if it failed earlier."""
    from scripts.run_summary import compute_failure_streaks

    history = [
        {"status": "ok", "summary": {"exits_failed_symbols": ["2330"]}},
        {"status": "ok", "summary": {"exits_failed_symbols": []}},  # recovered
    ]
    assert compute_failure_streaks(history) == {}


def test_run_summary_history_round_trip(tmp_db, isolated_marker, tmp_path):
    """v0.1.14.3 C: shutdown_guard appends to HISTORY_PATH; read_history reads
    it back. End-to-end smoke of the observation channel."""
    from datetime import date as _date

    from execution.shutdown import read_history, shutdown_guard

    # Run 1: ok
    with shutdown_guard(_date(2026, 5, 4)) as g:
        g.set_summary({"exits": 1, "exits_failed_symbols": ["0050"]})

    # Run 2: ok with different state
    with shutdown_guard(_date(2026, 5, 5)) as g:
        g.set_summary({"exits": 0, "exits_failed_symbols": ["0050"]})

    history = read_history(n=5)
    assert len(history) == 2
    assert history[0]["as_of"] == "2026-05-04"
    assert history[1]["as_of"] == "2026-05-05"
    assert history[0]["status"] == "ok"
    # Both runs failed exit for 0050 → streak = 2
    from scripts.run_summary import compute_failure_streaks
    assert compute_failure_streaks(history) == {"0050": 2}


def test_scan_and_exit_summary_includes_age_aggregates(tmp_db, seed_calendar, test_account_id):
    """v0.1.14.3.1: scan_and_exit summary derives avg_position_days and
    max_position_days from open_position_days so the rollup can surface
    holding-time pathologies (e.g. one outlier stuck open for weeks while
    everything else cleared in days)."""
    from scripts.run_exit_scan import scan_and_exit
    from storage.positions import OPEN, open_position

    # Two OPEN positions with different entry dates → different ages
    open_position(
        account_id=test_account_id,
        symbol="0050", strategy="trend_breakout_v1",
        entry_date=seed_calendar[0], entry_price=140.0, entry_atr=2.0,
        regime_at_entry="bull", sector="etf", is_etf=True,
        shares=100, notional_at_entry=14000, status=OPEN,
    )
    open_position(
        account_id=test_account_id,
        symbol="2330", strategy="trend_breakout_v1",
        entry_date=seed_calendar[2], entry_price=600.0, entry_atr=10.0,
        regime_at_entry="bull", sector="semiconductor", is_etf=False,
        shares=10, notional_at_entry=6000, status=OPEN,
    )

    summary = scan_and_exit(as_of=seed_calendar[4], fill_date=seed_calendar[5], account_id=test_account_id)

    ages = [d["age_days"] for d in summary["open_position_days"]]
    assert summary["avg_position_days"] == sum(ages) / len(ages)
    assert summary["max_position_days"] == max(ages)
    assert summary["max_position_days"] > summary["avg_position_days"], (
        "max should differ from avg when entry dates differ"
    )


def test_scan_and_exit_summary_age_aggregates_when_no_positions(tmp_db, seed_calendar, test_account_id):
    """v0.1.14.3.1: when no positions are OPEN, age aggregates must be None
    (not 0, not NaN, not raise). run_summary renders None as '(no open positions)'."""
    from scripts.run_exit_scan import scan_and_exit

    summary = scan_and_exit(as_of=seed_calendar[4], fill_date=seed_calendar[5], account_id=test_account_id)
    assert summary["open_position_days"] == []
    assert summary["avg_position_days"] is None
    assert summary["max_position_days"] is None


# ─────────────────────────────────────────────────────────────
# v0.1.14.3.3 — Dev signal injection (scripts/dev_push_signal.py)
# ─────────────────────────────────────────────────────────────


def test_save_signal_honors_custom_signal_id(tmp_db):
    """v0.1.14.3.3: save_signal must accept an explicit signal_id kwarg
    (used by dev_push_signal.py to inject DEV-prefixed identifiers).
    Default behavior (None → uuid) preserved separately."""
    from storage.signals import get_signal, save_signal

    sid = save_signal(
        symbol="2330", strategy="dev_injected", signal_type="buy",
        score=0.99, price=950.0, reason=["dev_test"],
        signal_date=date(2026, 5, 14),
        entry_atr=20.0, regime="bull",
        signal_id="DEV-TEST-001",
    ).signal_id
    assert sid == "DEV-TEST-001", f"explicit signal_id ignored: got {sid}"
    row = get_signal("DEV-TEST-001")
    assert row is not None
    assert row.symbol == "2330"
    assert row.strategy == "dev_injected"


def test_save_signal_default_signal_id_is_uuid(tmp_db):
    """v0.1.14.3.3: when signal_id is omitted, save_signal still generates
    a uuid (no regression on production callers)."""
    from storage.signals import save_signal

    sid = save_signal(
        symbol="2330", strategy="trend_breakout_v1", signal_type="buy",
        score=0.5, price=950.0, reason=["x"],
        signal_date=date(2026, 5, 14),
        entry_atr=20.0, regime="bull",
    ).signal_id
    # uuid4 strings have 4 dashes (8-4-4-4-12)
    assert sid.count("-") == 4
    assert len(sid) == 36
    assert not sid.startswith("DEV-")


def test_next_dev_signal_id_starts_at_001(tmp_db):
    """v0.1.14.3.3: with no DEV signals in DB, auto-id starts at 001."""
    from scripts.dev_push_signal import next_dev_signal_id

    assert next_dev_signal_id() == "DEV-TEST-001"
    assert next_dev_signal_id(prefix="DEV-LATE-") == "DEV-LATE-001"


def test_next_dev_signal_id_increments(tmp_db):
    """v0.1.14.3.3: after DEV-TEST-001 and DEV-TEST-002 exist, next_dev_signal_id
    returns 003 (not 002 again, not 001)."""
    from scripts.dev_push_signal import next_dev_signal_id
    from storage.signals import save_signal

    base = dict(
        symbol="2330", strategy="dev_injected", signal_type="buy",
        score=0.99, price=950.0, reason=["dev_test"],
        signal_date=date(2026, 5, 14),
        entry_atr=20.0, regime="bull",
    )
    save_signal(**base, signal_id="DEV-TEST-001")
    save_signal(**{**base, "signal_date": date(2026, 5, 15)}, signal_id="DEV-TEST-002")
    assert next_dev_signal_id() == "DEV-TEST-003"
    # Different prefix still starts at 001
    assert next_dev_signal_id(prefix="DEV-LATE-") == "DEV-LATE-001"


def test_dev_push_signal_exits_when_telegram_not_configured(tmp_db, monkeypatch, tmp_path):
    """v0.1.14.3.3: with no TELEGRAM_*_TOKEN in env, the script must refuse
    cleanly with exit code 1 — not crash, not silently no-op. The whole point
    is exercising real Telegram, so missing config is operator error.

    v0.1.14.3.4 isolation: TelegramConfig.from_env now routes through
    Settings, which reads .env. Override the Settings singleton with one
    pointing at an empty temp .env so the operator's real .env (if present
    on the test machine) doesn't leak into this test.
    """
    import config.settings as cs
    from config.settings import Settings
    from scripts.dev_push_signal import main

    # Clear any os.environ pollution
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("HELIOS_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("HELIOS_TELEGRAM_CHAT_ID", raising=False)

    # Override Settings with one reading an empty .env (isolates from operator's real config)
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("")
    monkeypatch.setattr(cs, "_settings", Settings(_env_file=str(empty_env)))

    exit_code = main(["--ticker", "2330", "--no-listener"])
    assert exit_code == 1, (
        f"expected exit 1 when Telegram unconfigured, got {exit_code}"
    )


# ─────────────────────────────────────────────────────────────
# v0.1.14.3.6 — classify_command pure-function tests
#
# These pin the new shortcut command vocabulary ("同意" / "放棄" / "1" / "0"
# / "yes" / "no" etc) and the single-pending resolution / multi-pending warn
# behavior. Pure function — no DB, no network, no broker mocks needed.
# ─────────────────────────────────────────────────────────────


def _pending(signal_id: str = "abc12345xyz", symbol: str = "2330"):
    """Lightweight stand-in for SignalRow — classify_command only reads
    .signal_id and .symbol, so duck-typing via SimpleNamespace is sufficient
    and keeps these tests free of DB setup."""
    return SimpleNamespace(signal_id=signal_id, symbol=symbol)


@pytest.mark.parametrize("text", [
    "同意", "Approve", "approve", "1", "yes", "YES", "y", "ok", "OK",
])
def test_classify_approve_shortcut_with_single_pending(text):
    """v0.1.14.3.6 contract: each approve-shortcut form, given exactly one
    PENDING signal, resolves to that signal's id without an explicit ref.

    The motivating scar: v0.1.14.3.5 screenshot showed operator typing
    'Approve' (no slash, no signal_id) — listener silently ignored.
    """
    from communication.telegram.listener import classify_command

    action = classify_command(text, [_pending("DEV-TEST-001-aaa")])
    assert action.kind == "approve", f"text {text!r} should approve, got {action.kind}"
    assert action.sig_ref == "DEV-TEST-001-aaa"


@pytest.mark.parametrize("text", [
    "放棄", "Reject", "reject", "0", "no", "NO", "n",
])
def test_classify_reject_shortcut_with_single_pending(text):
    from communication.telegram.listener import classify_command

    action = classify_command(text, [_pending("xyz999")])
    assert action.kind == "reject", f"text {text!r} should reject, got {action.kind}"
    assert action.sig_ref == "xyz999"


def test_classify_shortcut_with_zero_pending_warns():
    """No PENDING signals → shortcut must not silently approve/reject
    anything; instead emit operator-facing warn."""
    from communication.telegram.listener import classify_command

    action = classify_command("同意", [])
    assert action.kind == "warn"
    assert "沒有待處理訊號" in action.message


def test_classify_shortcut_with_multiple_pending_warns_with_ids():
    """Multiple PENDING signals → shortcut is ambiguous. Must warn AND
    surface the candidate signal_ids so operator can disambiguate."""
    from communication.telegram.listener import classify_command

    pending = [
        _pending("aaa11111", "2330"),
        _pending("bbb22222", "0050"),
    ]
    action = classify_command("1", pending)
    assert action.kind == "warn"
    # Both symbols must appear so operator can pick
    assert "2330" in action.message
    assert "0050" in action.message
    # And a sample of the explicit form
    assert "/approve" in action.message
    # Importantly: NO sig_ref guessed
    assert action.sig_ref is None


def test_classify_explicit_slash_command_with_arg_wins_over_pending_count():
    """v0.1.14.3.6: when operator types `/approve <id>` explicitly, classify
    must use that id even if there are 0 or many pending. This lets the
    operator override the single-pending heuristic."""
    from communication.telegram.listener import classify_command

    # Many pending — explicit ref still resolves directly
    pending = [_pending("aaa11111"), _pending("bbb22222")]
    action = classify_command("/approve aaa", pending)
    assert action.kind == "approve"
    assert action.sig_ref == "aaa"

    # Zero pending — explicit ref still passes through (approve_signal will
    # handle the not-found error downstream)
    action = classify_command("/reject ghost-id", [])
    assert action.kind == "reject"
    assert action.sig_ref == "ghost-id"


def test_classify_slash_approve_without_arg_falls_back_to_single_pending():
    """v0.1.14.3.6 unifies behavior: `/approve` alone (no arg) behaves
    identically to `同意` — falls back to single-pending resolution.

    This is also what BotFather's command-menu autofill produces (just
    `/approve` without args), so the UX needs to handle it gracefully."""
    from communication.telegram.listener import classify_command

    action = classify_command("/approve", [_pending("only-one-pending")])
    assert action.kind == "approve"
    assert action.sig_ref == "only-one-pending"

    # Same fallback path for /reject
    action = classify_command("/reject", [_pending("only-one")])
    assert action.kind == "reject"
    assert action.sig_ref == "only-one"


def test_classify_unknown_slash_command_returns_unknown_with_message():
    """Slash-prefixed but not in command set → 'unknown' (bot should reply
    with a /help hint)."""
    from communication.telegram.listener import classify_command

    action = classify_command("/foobar arg", [_pending()])
    assert action.kind == "unknown"
    assert "未知指令" in action.message
    assert "/foobar" in action.message
    assert "/help" in action.message


def test_classify_plain_unrecognized_text_is_noop():
    """Plain non-slash text that isn't a shortcut → noop (silently ignored,
    no bot reply). Prevents bot from chattering on every random message."""
    from communication.telegram.listener import classify_command

    for text in ["hello", "what's up", "test", "嗨", "謝謝", ""]:
        action = classify_command(text, [_pending()])
        assert action.kind == "noop", (
            f"text {text!r} should be noop, got {action.kind}"
        )
        assert action.sig_ref is None


def test_classify_help_and_status_independent_of_pending():
    """`/help` and `/status` are info commands — never resolve to a
    signal action, regardless of pending count."""
    from communication.telegram.listener import classify_command

    assert classify_command("/help", []).kind == "help"
    assert classify_command("/help", [_pending(), _pending()]).kind == "help"
    assert classify_command("/status", []).kind == "status"
    assert classify_command("/status", [_pending()]).kind == "status"


def test_classify_whitespace_and_case_robust():
    """Defensive: leading/trailing whitespace stripped; cmd is lowercased.
    Operator typing 'APPROVE  ' or '  同意' should still classify."""
    from communication.telegram.listener import classify_command

    assert classify_command("  同意  ", [_pending("x")]).kind == "approve"
    assert classify_command("APPROVE", [_pending("x")]).kind == "approve"
    assert classify_command("/Approve myid", [_pending()]).sig_ref == "myid"


# ─────────────────────────────────────────────────────────────
# v0.1.14.3.8: --bootstrap-price flag
# ─────────────────────────────────────────────────────────────


def test_bootstrap_price_enables_broker_fill(tmp_db, test_account_id):
    """v0.1.14.3.8: `_bootstrap_price_row` inserts a row that PaperBroker
    can use for adj_open (ref_price) and volume (liquidity gate).

    Without bootstrapping, submit_buy on a date with no daily_price_adj data
    returns FillResult(success=False, reason='no_price_data'). After calling
    _bootstrap_price_row, the same submit_buy must succeed and fill at a
    price derived from the bootstrapped adj_open.
    """
    from execution.paper_broker import DEFAULT_TW_FEES, PaperBroker
    from scripts.dev_push_signal import _bootstrap_price_row

    sym = "2330"
    fill_date = date(2026, 5, 18)  # a date with no real data in tmp_db
    price = 950.0
    volume = 25_000_000

    broker = PaperBroker(fees=DEFAULT_TW_FEES, account_id=test_account_id)

    # Before bootstrap: no data → fill must fail
    before = broker.submit_buy(
        symbol=sym, target_notional=50_000.0, fill_date=fill_date,
        signal_id="test-before",
    )
    assert not before.success, (
        f"expected fill failure before bootstrap (no price data), got {before}"
    )

    # Bootstrap
    _bootstrap_price_row(sym, fill_date, price, volume)

    # After bootstrap: adj_open and volume present → fill must succeed
    after = broker.submit_buy(
        symbol=sym, target_notional=50_000.0, fill_date=fill_date,
        signal_id="test-after",
    )
    assert after.success, (
        f"expected fill success after --bootstrap-price, got {after}"
    )
    # ref_price must be derived from bootstrapped adj_open (+ slippage)
    assert after.ref_price is not None
    assert abs(after.ref_price - price) < price * 0.01, (
        f"fill ref_price {after.ref_price:.2f} diverges from bootstrap "
        f"adj_open {price:.2f} by more than 1% — broker is not reading "
        f"the bootstrapped row"
    )


# ─────────────────────────────────────────────────────────────
# P1-OPS — Signal storage idempotency (2026-06-02)
# ─────────────────────────────────────────────────────────────


def test_save_signal_canonical_idempotency(tmp_db):
    """P1-OPS: repeated save_signal() calls with the same canonical key
    must return the same signal_id with created=False on subsequent calls.

    Signals are event-keyed: (symbol, strategy, signal_type, signal_date).
    """
    from storage.signals import SaveSignalResult, save_signal

    r1 = save_signal(
        symbol="IDEM_TEST", strategy="test_strategy", signal_type="buy",
        score=0.5, price=100.0, reason=["first"],
        signal_date=date(2026, 1, 1),
    )
    assert isinstance(r1, SaveSignalResult)
    assert r1.created is True

    r2 = save_signal(
        symbol="IDEM_TEST", strategy="test_strategy", signal_type="buy",
        score=0.9, price=105.0, reason=["rerun"],
        signal_date=date(2026, 1, 1),
    )
    assert isinstance(r2, SaveSignalResult)
    assert r2.created is False
    assert r2.signal_id == r1.signal_id


def test_terminal_state_does_not_permit_regeneration(tmp_db):
    """P1-OPS: a REJECTED signal must not regenerate a new signal_id.

    Terminal states (REJECTED, EXPIRED_DRIFT, TIMEOUT) permanently close
    the canonical signal event. This is the core Event-keyed semantic
    decided 2026-06-02.
    """
    from storage.signals import SaveSignalResult, get_signal, save_signal, update_approval

    r1 = save_signal(
        symbol="IDEM_TEST", strategy="test_strategy", signal_type="buy",
        score=0.5, price=100.0, reason=["first"],
        signal_date=date(2026, 1, 2),
    )
    assert r1.created is True

    ok = update_approval(r1.signal_id, "REJECTED", approved_by="test")
    assert ok is True
    assert get_signal(r1.signal_id).approval_status == "REJECTED"

    r2 = save_signal(
        symbol="IDEM_TEST", strategy="test_strategy", signal_type="buy",
        score=0.7, price=102.0, reason=["after reject"],
        signal_date=date(2026, 1, 2),
    )
    assert isinstance(r2, SaveSignalResult)
    assert r2.created is False
    assert r2.signal_id == r1.signal_id
