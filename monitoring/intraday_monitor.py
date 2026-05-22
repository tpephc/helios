# monitoring/intraday_monitor.py
"""Intraday position monitoring — v0.1.15. State machine, alert dispatch, audit logging.

Architecture
------------
* **Stateless per invocation**: all persistent state lives in
  ``intraday_alert_state`` (current zone) and ``intraday_alert_transitions``
  (append-only audit log).
* **Notifications fire only on zone transitions** (edge-triggered).
  Hysteresis in :func:`classify_zone` prevents oscillation near thresholds.
* **Write-first ordering (outbox pattern)**:
    1. ``BEGIN TRANSACTION``
    2. ``UPDATE ... WHERE zone = prev_zone RETURNING position_id``
    3. If RETURNING returned a row: ``INSERT`` transition with status='PENDING'.
    4. ``COMMIT``
    5. Send Telegram.
    6. ``UPDATE`` transition status → 'SENT' or 'FAILED'.
  If the process crashes between steps 4 and 5, the operator misses one
  notification but state remains consistent.
* **Idempotency**: ``RETURNING`` on the UPDATE eliminates the SELECT-after-UPDATE
  race: only the process whose UPDATE matched rows inserts the transition log.
* **Transaction contract** (important for callers):
  ``run_monitor()`` requires ``conn`` to be in auto-commit mode — i.e. no
  active ``BEGIN TRANSACTION`` issued by the caller.  Internal helpers that
  require atomicity manage their own transactions via
  ``BEGIN TRANSACTION / COMMIT / ROLLBACK``.  An outer single-transaction
  design would break the outbox pattern, which requires the PENDING
  transition to be committed *before* the Telegram send.
  ``data.database.connect()`` satisfies this contract: it opens the DuckDB
  connection and yields it without issuing ``BEGIN``.

Out of scope
------------
* Auto-closing positions (notify only — never writes to ``positions`` table).
* Entry signal generation (EOD indicators are not valid intraday).
* System liveness heartbeat (separate operational concern).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

import structlog

from execution.stop_logic import (
    PriceZone,
    StopLevels,
    classify_zone,
    compute_stop_levels,
)
from monitoring.quote_source import IntradayQuoteSource

logger = structlog.get_logger(__name__)

_SYSTEM_DEGRADED_THRESHOLD: float = 0.5
_SYSTEM_ALERT_COOLDOWN_MINUTES: float = 60.0


# ---------------------------------------------------------------------------
# Protocols and public data structures
# ---------------------------------------------------------------------------


class TelegramBotProtocol(Protocol):
    def send_message(self, text: str, parse_mode: str | None = None) -> bool:
        """Send a text message to the operator chat.  Returns True on success."""
        ...


@dataclass
class RunSummary:
    """Metadata for one polling cycle, persisted in ``intraday_monitor_runs``."""

    run_id: str
    run_at: datetime
    symbols_attempted: int
    symbols_succeeded: int
    positions_checked: int
    """Number of OPEN positions that passed the validity filter and were evaluated.
    Positions excluded by ``_load_open_positions()`` (entry_atr=0, etc.) are
    not counted here.  See ``intraday_monitor_runs.positions_checked`` column."""
    transitions_logged: int
    """Zone transitions written to DB, regardless of Telegram outcome."""
    alerts_sent: int
    """Transitions where Telegram ``send_message`` returned True.
    Always ≤ ``transitions_logged``.  A gap indicates FAILED notifications;
    query ``intraday_alert_transitions WHERE notification_status = 'FAILED'``."""
    system_alert_sent: bool
    error_summary: str | None
    duration_seconds: float


# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------


@dataclass
class _OpenPosition:
    position_id: str
    symbol: str
    entry_atr: float
    max_close_since_entry: float
    shares: int
    entry_price: float


@dataclass
class _AlertState:
    position_id: str
    zone: PriceZone
    zone_entered_at: str
    last_price: float | None
    last_checked_at: str


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_monitor(
    conn: object,
    quote_source: IntradayQuoteSource,
    bot: TelegramBotProtocol,
    run_at: datetime | None = None,
) -> RunSummary:
    """Execute one polling cycle of the intraday monitor.

    Args:
        conn: DuckDB connection in **auto-commit mode** (no active transaction).
            See module docstring for the transaction contract.
        quote_source: Price feed implementation.
        bot: Telegram notification interface.
        run_at: Timestamp for this run; defaults to ``datetime.now(UTC)``.

    Returns:
        :class:`RunSummary` written to ``intraday_monitor_runs``.

    Invariant:
        This function never modifies the ``positions`` table.
    """
    if run_at is None:
        run_at = datetime.now(timezone.utc)
    t0 = time.monotonic()
    run_id = f"imon_{run_at.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    positions = _load_open_positions(conn)
    if not positions:
        summary = RunSummary(
            run_id=run_id, run_at=run_at,
            symbols_attempted=0, symbols_succeeded=0,
            positions_checked=0, transitions_logged=0, alerts_sent=0,
            system_alert_sent=False, error_summary=None,
            duration_seconds=time.monotonic() - t0,
        )
        _log_run(conn, summary)
        logger.info("intraday_monitor_no_open_positions", run_id=run_id)
        return summary

    # Deduplicate symbols for the quote fetch.
    # Multiple OPEN positions for the same symbol (governance violation, but
    # possible during dev) must not cause duplicate API calls or skewed
    # success_rate calculation.
    # dict.fromkeys preserves insertion order (Python 3.7+).
    unique_symbols = list(dict.fromkeys(p.symbol for p in positions))
    quotes = quote_source.get_quotes(unique_symbols)

    succeeded_count = sum(
        1 for q in quotes.values()
        if q.price is not None and not q.is_stale
    )
    # Denominator is unique symbol count, not position count.
    success_rate = succeeded_count / len(unique_symbols)

    # P0-1: send system alert when feed is degraded, but DO NOT return early.
    # Valid-quote positions must still be evaluated.
    # P0 contract: system alert Telegram failure must not propagate here;
    # _maybe_send_system_alert() catches all bot exceptions internally.
    system_alert_sent = False
    if success_rate < _SYSTEM_DEGRADED_THRESHOLD:
        system_alert_sent = _maybe_send_system_alert(
            conn, bot, run_at, succeeded_count, len(unique_symbols)
        )

    # Batch ensure state rows exist, then load all in one SELECT.
    _batch_ensure_state_rows(conn, positions, run_at)
    state_map = _batch_load_states(conn, [p.position_id for p in positions])

    transitions_logged = 0
    alerts_sent = 0

    for position in positions:
        quote = quotes[position.symbol]

        # P0-2: skip None and stale quotes.
        if quote.price is None or quote.is_stale:
            logger.warning(
                "intraday_monitor_skip_invalid_quote",
                symbol=position.symbol,
                price_is_none=quote.price is None,
                is_stale=quote.is_stale,
                error=quote.error,
            )
            continue

        levels = compute_stop_levels(position.max_close_since_entry, position.entry_atr)

        prev_state = state_map.get(position.position_id)
        prev_zone = prev_state.zone if prev_state else PriceZone.NORMAL
        new_zone = classify_zone(quote.price, levels, prev_zone)

        if new_zone == prev_zone:
            _update_state_last_seen(conn, position.position_id, quote.price, run_at)
            continue

        # P0-3 + P0-4: atomic advance with RETURNING + outbox INSERT.
        transition_id = f"txn_{uuid.uuid4().hex[:12]}"
        advanced = _try_advance_state_and_log(
            conn, position, run_id, run_at,
            prev_zone, new_zone, quote.price, levels,
            transition_id=transition_id,
        )

        if not advanced:
            logger.info(
                "intraday_zone_advance_skipped",
                symbol=position.symbol,
                reason="zone_already_advanced",
                run_id=run_id,
            )
            continue

        transitions_logged += 1

        # Send Telegram only after DB has committed the PENDING transition.
        send_ok = _send_zone_alert(bot, position, quote.price, levels, prev_zone, new_zone)
        _update_transition_status(conn, transition_id, "SENT" if send_ok else "FAILED")

        if send_ok:
            alerts_sent += 1

        logger.info(
            "intraday_zone_transition",
            symbol=position.symbol,
            from_zone=prev_zone.value,
            to_zone=new_zone.value,
            price=quote.price,
            trailing_stop=levels.trailing_stop,
            notification="SENT" if send_ok else "FAILED",
        )

    summary = RunSummary(
        run_id=run_id, run_at=run_at,
        symbols_attempted=len(unique_symbols),
        symbols_succeeded=succeeded_count,
        positions_checked=len(positions),
        transitions_logged=transitions_logged,
        alerts_sent=alerts_sent,
        system_alert_sent=system_alert_sent,
        error_summary=None,
        duration_seconds=time.monotonic() - t0,
    )
    _log_run(conn, summary)
    return summary


# ---------------------------------------------------------------------------
# DB helpers — state management
# ---------------------------------------------------------------------------


def _load_open_positions(conn: object) -> list[_OpenPosition]:
    """Load OPEN positions with valid, positive stop data.

    Excludes rows with non-positive entry_atr, max_close_since_entry, or shares
    to prevent division-by-zero or nonsensical stop thresholds.
    Positions opened today (max_close_since_entry IS NULL) are excluded and
    will be picked up after the next nightly EOD run.
    """
    rows = conn.execute("""
        SELECT position_id, symbol, entry_atr, max_close_since_entry,
               shares, entry_price
        FROM   positions
        WHERE  status                = 'OPEN'
          AND  entry_atr             IS NOT NULL
          AND  entry_atr             > 0
          AND  max_close_since_entry IS NOT NULL
          AND  max_close_since_entry > 0
          AND  shares                > 0
    """).fetchall()
    return [
        _OpenPosition(
            position_id=str(r[0]),
            symbol=str(r[1]),
            entry_atr=float(r[2]),
            max_close_since_entry=float(r[3]),
            shares=int(r[4]),
            entry_price=float(r[5]),
        )
        for r in rows
    ]


def _batch_ensure_state_rows(
    conn: object,
    positions: list[_OpenPosition],
    run_at: datetime,
) -> None:
    """Ensure every position has a state row (NORMAL by default).

    Uses executemany inside one explicit transaction to minimise round-trips.
    ON CONFLICT DO NOTHING is safe for concurrent callers: exactly one INSERT
    per position_id will succeed.

    Transaction note: issues its own BEGIN/COMMIT.  Caller must not already
    be inside a transaction (see module-level transaction contract).
    """
    if not positions:
        return
    now_str = run_at.isoformat()
    conn.execute("BEGIN TRANSACTION")
    try:
        conn.executemany(
            """
            INSERT INTO intraday_alert_state
                (position_id, zone, zone_entered_at, last_price,
                 last_checked_at, updated_at)
            VALUES (?, 'NORMAL', ?, NULL, ?, ?)
            ON CONFLICT (position_id) DO NOTHING
            """,
            [(p.position_id, now_str, now_str, now_str) for p in positions],
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def _batch_load_states(
    conn: object,
    position_ids: list[str],
) -> dict[str, _AlertState]:
    """Load all alert states for the given position IDs in a single SELECT."""
    if not position_ids:
        return {}
    placeholders = ",".join("?" * len(position_ids))
    rows = conn.execute(
        f"""
        SELECT position_id, zone, zone_entered_at, last_price, last_checked_at
        FROM   intraday_alert_state
        WHERE  position_id IN ({placeholders})
        """,
        position_ids,
    ).fetchall()
    return {
        str(r[0]): _AlertState(
            position_id=str(r[0]),
            zone=PriceZone(r[1]),
            zone_entered_at=str(r[2]),
            last_price=float(r[3]) if r[3] is not None else None,
            last_checked_at=str(r[4]),
        )
        for r in rows
    }


def _try_advance_state_and_log(
    conn: object,
    position: _OpenPosition,
    run_id: str,
    run_at: datetime,
    prev_zone: PriceZone,
    new_zone: PriceZone,
    price: float,
    levels: StopLevels,
    transition_id: str,
) -> bool:
    """Atomically advance zone and write a PENDING transition log entry.

    Uses an explicit transaction containing:
    1. ``UPDATE ... WHERE zone = prev_zone RETURNING position_id``
    2. ``INSERT INTO intraday_alert_transitions`` (only if UPDATE matched rows)

    The ``RETURNING`` clause determines whether the UPDATE matched any rows
    without a subsequent SELECT.  A SELECT-after-UPDATE is NOT safe: a
    concurrent writer could change the zone between the UPDATE and the SELECT,
    yielding a false-positive ``advanced = True`` and a duplicate INSERT.

    Transaction note: issues its own BEGIN/COMMIT.  Caller must not already
    be inside a transaction (see module-level transaction contract).

    Returns:
        True  — this process successfully advanced the state.
        False — ``WHERE zone = prev_zone`` matched 0 rows; another process
                already advanced the state.  No transition row is inserted.
    """
    now_str = run_at.isoformat()
    conn.execute("BEGIN TRANSACTION")
    try:
        returning_row = conn.execute(
            """
            UPDATE intraday_alert_state
            SET zone            = ?,
                zone_entered_at = ?,
                last_price      = ?,
                last_checked_at = ?,
                updated_at      = ?
            WHERE position_id = ? AND zone = ?
            RETURNING position_id
            """,
            [
                new_zone.value, now_str, price, now_str, now_str,
                position.position_id, prev_zone.value,
            ],
        ).fetchone()

        advanced = returning_row is not None

        if advanced:
            conn.execute(
                """
                INSERT INTO intraday_alert_transitions (
                    transition_id, position_id, run_id, transitioned_at,
                    from_zone, to_zone, price,
                    trailing_stop, approach_enter, approach_exit,
                    max_close_since_entry, entry_atr,
                    notification_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
                """,
                [
                    transition_id,
                    position.position_id,
                    run_id,
                    now_str,
                    prev_zone.value,
                    new_zone.value,
                    price,
                    levels.trailing_stop,
                    levels.approach_enter,
                    levels.approach_exit,
                    position.max_close_since_entry,
                    position.entry_atr,
                ],
            )

        conn.execute("COMMIT")
        return advanced

    except Exception:
        conn.execute("ROLLBACK")
        raise


def _update_state_last_seen(
    conn: object,
    position_id: str,
    price: float,
    run_at: datetime,
) -> None:
    """Refresh last_price and last_checked_at on a same-zone poll (no transition)."""
    now_str = run_at.isoformat()
    conn.execute(
        """
        UPDATE intraday_alert_state
        SET last_price      = ?,
            last_checked_at = ?,
            updated_at      = ?
        WHERE position_id   = ?
        """,
        [price, now_str, now_str, position_id],
    )


def _update_transition_status(
    conn: object,
    transition_id: str,
    status: str,
) -> None:
    """Update notification outcome on an existing PENDING row.

    Swallows exceptions: notification status is observability-only and must
    not disrupt the main poll loop.  If the UPDATE fails, the transition row
    remains 'PENDING' and can be identified for manual follow-up.
    """
    try:
        conn.execute(
            """
            UPDATE intraday_alert_transitions
            SET notification_status = ?
            WHERE transition_id = ?
            """,
            [status, transition_id],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "intraday_transition_status_update_failed",
            transition_id=transition_id,
            status=status,
            error=type(exc).__name__,
        )


def _log_run(conn: object, summary: RunSummary) -> None:
    conn.execute(
        """
        INSERT INTO intraday_monitor_runs (
            run_id, run_at,
            symbols_attempted, symbols_succeeded,
            positions_checked, transitions_logged, alerts_sent,
            system_alert_sent, error_summary, duration_seconds
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            summary.run_id,
            summary.run_at.isoformat(),
            summary.symbols_attempted,
            summary.symbols_succeeded,
            summary.positions_checked,
            summary.transitions_logged,
            summary.alerts_sent,
            1 if summary.system_alert_sent else 0,
            summary.error_summary,
            summary.duration_seconds,
        ],
    )


def _maybe_send_system_alert(
    conn: object,
    bot: TelegramBotProtocol,
    run_at: datetime,
    succeeded: int,
    total: int,
) -> bool:
    """Send system degradation alert unless recently sent.

    P0 contract: all Telegram exceptions are caught here.  A bot failure
    must NOT propagate to run_monitor() and interrupt position supervision.

    Returns:
        True if the alert was sent successfully.
        False if suppressed by cooldown, or if bot.send_message() raised.
    """
    cooldown_cutoff = run_at.timestamp() - _SYSTEM_ALERT_COOLDOWN_MINUTES * 60
    row = conn.execute("""
        SELECT MAX(run_at)
        FROM   intraday_monitor_runs
        WHERE  system_alert_sent = 1
    """).fetchone()
    if row and row[0] is not None:
        if datetime.fromisoformat(row[0]).timestamp() > cooldown_cutoff:
            logger.info("intraday_system_alert_suppressed_cooldown")
            return False

    text = (
        f"⚠️ Helios 盤中監控異常\n"
        f"報價取得：{succeeded}/{total} 個股票\n"
        f"請手動確認持倉"
    )
    try:
        result = bool(bot.send_message(text))
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "intraday_system_alert_send_failed",
            error=type(exc).__name__,
            succeeded=succeeded,
            total=total,
        )
        return False

    if result:
        logger.warning(
            "intraday_system_alert_sent", succeeded=succeeded, total=total
        )
    return result


# ---------------------------------------------------------------------------
# Notification formatting
# ---------------------------------------------------------------------------


def _send_zone_alert(
    bot: TelegramBotProtocol,
    position: _OpenPosition,
    price: float,
    levels: StopLevels,
    from_zone: PriceZone,
    to_zone: PriceZone,
) -> bool:
    """Send zone-transition notification.  Returns True if Telegram accepted."""
    text = _format_zone_message(position, price, levels, from_zone, to_zone)
    try:
        return bool(bot.send_message(text))
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "intraday_telegram_send_failed",
            symbol=position.symbol,
            error=type(exc).__name__,
        )
        return False


def _format_zone_message(
    position: _OpenPosition,
    price: float,
    levels: StopLevels,
    from_zone: PriceZone,
    to_zone: PriceZone,
) -> str:
    """Build a plain-text Telegram message for a zone transition.

    Plain text only — no Markdown — to avoid parse_mode edge cases.
    """
    sym = position.symbol
    stop = levels.trailing_stop
    distance = price - stop
    distance_pct = (distance / stop * 100.0) if stop > 0 else 0.0

    if to_zone == PriceZone.BREACH:
        return (
            f"🔴 {sym} 觸及停損\n"
            f"持股 {position.shares} 股\n"
            f"當前價：{price:.2f}\n"
            f"停損水位：{stop:.2f}\n"
            f"請確認是否手動平倉"
        )
    if to_zone == PriceZone.APPROACH:
        if from_zone == PriceZone.BREACH:
            return (
                f"↗️ {sym} 停損區部分回升\n"
                f"當前價：{price:.2f}\n"
                f"停損水位：{stop:.2f}\n"
                f"仍在警示區間，請持續觀察"
            )
        return (
            f"⚠️ {sym} 接近停損\n"
            f"持股 {position.shares} 股\n"
            f"當前價：{price:.2f}\n"
            f"停損水位：{stop:.2f}\n"
            f"距停損：{distance:.2f}（{distance_pct:.1f}%）"
        )
    return (
        f"✅ {sym} 已脫離警示\n"
        f"當前價：{price:.2f}\n"
        f"停損水位：{stop:.2f}\n"
        f"距停損：{distance_pct:.1f}%"
    )
