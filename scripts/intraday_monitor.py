#!/usr/bin/env python3
# scripts/intraday_monitor.py
"""Intraday position monitor — cron entry point — v0.1.15.

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
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import structlog

from data.database import connect
from monitoring.intraday_monitor import run_monitor
from monitoring.quote_source import YFinanceQuoteSource

logger = structlog.get_logger(__name__)

# Lock file under the project root's .lock/ directory.
# scripts/intraday_monitor.py → scripts/../.lock/intraday_monitor.lock
_LOCK_DIR = Path(__file__).parents[1] / ".lock"
_LOCK_PATH = _LOCK_DIR / "intraday_monitor.lock"

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
        quote_source = YFinanceQuoteSource()

        with connect() as conn:
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
        logger.error(
            "intraday_monitor_fatal",
            error=type(exc).__name__,
            detail=str(exc),
        )
        return 1

    finally:
        _release_lock(lock_fd)


if __name__ == "__main__":
    sys.exit(main())
