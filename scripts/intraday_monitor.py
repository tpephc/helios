#!/usr/bin/env python3
# scripts/intraday_monitor.py
"""Intraday position monitor — cron entry point — v0.1.16.

Cron schedule (server timezone: Asia/Taipei):
    5,20,35,50 9-13 * * 1-5  cd ~/projects/helios && \\
        uv run python scripts/intraday_monitor.py >> logs/intraday_monitor.log 2>&1

Process-level lock
------------------
This script acquires an exclusive non-blocking file lock before doing any work.
If a previous cron invocation is still running (e.g. slow yfinance batch), the
new process exits immediately (return code 0, not treated as an error).

The lock file lives under the project's ``.lock/`` directory rather than
``/tmp`` so it persists across server reboots and its lifecycle is tied to
the project, not the OS temp directory.

Unix-only: the locking mechanism uses ``fcntl``, which is not available on
Windows.  This script is intended to run on Linux only (the nexus server).
If you need to test on macOS it will also work; Windows is not supported.

Changelog
---------
v0.1.16 (2026-06-07): P1-OBS — fatal self-alert and sentinel DB row.
    On any fatal exception:
      1. Send immediate Telegram alert (_send_fatal_alert).
      2. Write a sentinel row to intraday_monitor_runs with
         system_alert_sent reflecting actual Telegram delivery status.
    DuckDB lock conflict on connect() retried up to _DB_RETRY_COUNT times
    with _DB_RETRY_SLEEP_S delay before raising (_connect_with_retry).
    system_alert_sent in the sentinel row is 1 iff Telegram was actually
    delivered — never hardcoded.
v0.1.15: initial implementation.
"""

from __future__ import annotations

import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import structlog

from data.database import connect
from monitoring.intraday_monitor import run_monitor
from monitoring.quote_source import ShioajiQuoteSource

logger = structlog.get_logger(__name__)

# Lock file under the project root's .lock/ directory.
# scripts/intraday_monitor.py → scripts/../.lock/intraday_monitor.lock
_LOCK_DIR = Path(__file__).parents[1] / ".lock"
_LOCK_PATH = _LOCK_DIR / "intraday_monitor.lock"

# DuckDB lock retry configuration.
# The lock is typically held by a short-lived writer (e.g. daily_run.py at
# 09:00). Retrying avoids a fatal on transient contention.
_DB_RETRY_COUNT = 3
_DB_RETRY_SLEEP_S = 5
_DUCKDB_LOCK_MARKER = "Could not set lock on file"

# fcntl is Unix-only.  Import at module level so the missing-module error
# is caught early; fall back gracefully if somehow running on Windows.
try:
    import fcntl
    _HAS_FCNTL = True
except ImportError:  # pragma: no cover
    _HAS_FCNTL = False
    logger.warning("fcntl_unavailable_no_process_lock")


def _try_acquire_lock() -> "tuple[bool, object]":
    """Attempt to acquire an exclusive non-blocking file lock.

    Returns:
        (acquired: bool, lock_fd: file object or None)
        Caller is responsible for releasing the lock and closing lock_fd.
    """
    if not _HAS_FCNTL:
        # No locking available: proceed without protection.
        # Log a warning so the operator knows concurrent runs are possible.
        logger.warning("intraday_monitor_lock_skipped_no_fcntl")
        return True, None

    _LOCK_DIR.mkdir(parents=True, exist_ok=True)
    lock_fd = open(_LOCK_PATH, "w")  # noqa: SIM115
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True, lock_fd
    except BlockingIOError:
        lock_fd.close()
        return False, None


def _release_lock(lock_fd: object) -> None:
    if lock_fd is None or not _HAS_FCNTL:
        return
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("intraday_monitor_lock_release_failed",
            lock_path=str(_LOCK_PATH), error=type(exc).__name__)


def _build_bot() -> object:
    """Instantiate the Telegram bot using the same pattern as daily_run.py."""
    from communication.telegram import TelegramBot, TelegramConfig
    cfg = TelegramConfig.from_env()
    if cfg is None:
        raise RuntimeError("Telegram config not found in environment")
    return TelegramBot(cfg)


def _is_duckdb_lock_error(exc: BaseException) -> bool:
    """Return True if exc is a DuckDB write-lock conflict.

    Identified by exception type name 'IOException' and the canonical
    lock-conflict message fragment observed in production logs
    (2026-05-28, 2026-05-29).
    """
    return (
        type(exc).__name__ == "IOException"
        and _DUCKDB_LOCK_MARKER in str(exc)
    )


def _connect_with_retry():
    """Open a DuckDB connection, retrying on transient lock conflicts.

    Retries up to _DB_RETRY_COUNT times with _DB_RETRY_SLEEP_S delay.
    Re-raises immediately on any non-lock exception or after all retries
    are exhausted.

    Returns:
        An open DuckDB connection context manager (from data.database.connect).
    """
    for attempt in range(1, _DB_RETRY_COUNT + 2):  # +1 for initial try
        try:
            return connect()
        except Exception as exc:  # noqa: BLE001
            if not _is_duckdb_lock_error(exc) or attempt > _DB_RETRY_COUNT:
                raise
            logger.warning(
                "intraday_monitor_db_lock_retry",
                attempt=attempt,
                retry_in_s=_DB_RETRY_SLEEP_S,
                detail=str(exc)[:120],
            )
            time.sleep(_DB_RETRY_SLEEP_S)
    raise RuntimeError("unreachable")  # satisfies type checker


def _send_fatal_alert(run_at: datetime, error_detail: str) -> bool:
    """Send an immediate Telegram alert on fatal monitor failure.

    Returns:
        True if the alert was successfully sent, False otherwise.
        Best-effort: logs and swallows all exceptions so the fatal handler
        never raises again on alert delivery failure.
    """
    try:
        bot = _build_bot()
        from communication.telegram.sender import push_simple
        msg = (
            "\U0001F6A8 intraday_monitor FATAL\n"
            f"run_at {run_at.isoformat()}\n"
            f"error: {error_detail}\n"
            "The monitor did NOT complete this cycle. "
            "Check logs/intraday_monitor.log."
        )
        push_simple(bot, msg)
        logger.info("intraday_monitor_fatal_alert_sent", run_at=run_at.isoformat())
        return True
    except Exception as alert_exc:  # noqa: BLE001
        logger.warning(
            "intraday_monitor_fatal_alert_failed",
            error=type(alert_exc).__name__,
            detail=str(alert_exc),
        )
        return False


def _write_fatal_run_row(
    run_at: datetime,
    error_detail: str,
    system_alert_sent: bool,
) -> None:
    """Write a sentinel row to intraday_monitor_runs for this fatal run.

    Uses _connect_with_retry() because the fatal may itself be a transient
    lock conflict that clears before we attempt the write.
    Truncates error_detail to 500 chars to stay within VARCHAR budget.

    system_alert_sent is set to 1 iff the Telegram alert was actually
    delivered — never hardcoded. This preserves observability semantics:
    a failed alert delivery is visible in the DB.

    Best-effort: logs and swallows all exceptions — the DB may itself be
    the reason for the fatal (e.g. lock conflict).

    Args:
        run_at: Timestamp of the failed run.
        error_detail: Exception type and message from the fatal handler.
        system_alert_sent: Whether the Telegram alert was successfully sent.
    """
    run_id = f"imon_{run_at.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    try:
        with _connect_with_retry() as conn:
            conn.execute(
                """
                INSERT INTO intraday_monitor_runs (
                    run_id, run_at,
                    symbols_attempted, symbols_succeeded,
                    positions_checked, transitions_logged, alerts_sent,
                    system_alert_sent, error_summary, duration_seconds
                ) VALUES (?, ?, 0, 0, 0, 0, 0, ?, ?, 0.0)
                """,
                [
                    run_id,
                    run_at.isoformat(),
                    1 if system_alert_sent else 0,
                    error_detail[:500],
                ],
            )
        logger.info("intraday_monitor_fatal_row_written", run_id=run_id)
    except Exception as db_exc:  # noqa: BLE001
        # DB itself may be unavailable (e.g. lock conflict is the fatal cause).
        logger.warning(
            "intraday_monitor_fatal_row_failed",
            error=type(db_exc).__name__,
            detail=str(db_exc),
        )


def main() -> int:
    acquired, lock_fd = _try_acquire_lock()
    if not acquired:
        logger.warning(
            "intraday_monitor_already_running",
            lock_path=str(_LOCK_PATH),
        )
        return 0

    try:
        run_at = datetime.now(timezone.utc)
        logger.info("intraday_monitor_start", run_at=run_at.isoformat())

        bot = _build_bot()
        quote_source = ShioajiQuoteSource()

        with _connect_with_retry() as conn:
            summary = run_monitor(conn, quote_source, bot, run_at=run_at)

        logger.info(
            "intraday_monitor_complete",
            run_id=summary.run_id,
            positions_checked=summary.positions_checked,
            transitions_logged=summary.transitions_logged,
            alerts_sent=summary.alerts_sent,
            symbols_succeeded=summary.symbols_succeeded,
            symbols_attempted=summary.symbols_attempted,
            duration_seconds=round(summary.duration_seconds, 2),
        )
        return 0

    except Exception as exc:  # noqa: BLE001
        error_detail = f"{type(exc).__name__}: {exc}"
        logger.error(
            "intraday_monitor_fatal",
            error=type(exc).__name__,
            detail=str(exc),
        )
        # AC-1: immediate Telegram alert on fatal.
        # AC-2: sentinel DB row; system_alert_sent reflects actual delivery.
        sent = _send_fatal_alert(run_at, error_detail)
        _write_fatal_run_row(run_at, error_detail, sent)
        return 1

    finally:
        _release_lock(lock_fd)


if __name__ == "__main__":
    sys.exit(main())
