# execution/shutdown.py
"""Graceful shutdown semantics for daily_run.py.

Per v0.1.14.2-b decision-confirmation: idempotency becomes critical once paper
trading starts. The shutdown_guard context manager:

1. **Durable state preservation** — DuckDB commits are atomic per `with connect()`
   block, so this is mostly automatic. The guard ensures we don't leak open
   connections.

2. **Pending signal expiry** — if daily_run aborts after pushing PENDING signals
   to Telegram but before approval window completes, those signals would
   otherwise stay PENDING forever (the next daily_run's expire_by_timeout would
   catch them eventually, but that may be 24h later). Better: explicitly expire
   on abort, forcing operator to re-evaluate.

3. **Operator notification** — telegram error message describing the abort.

4. **Marker file with status='aborted'** — next daily_run's prev-day check
   refuses to proceed (per review #3) until operator investigates.

Failure mode this guards against (ARCHITECTURE §9):
  > "Process crash mid-state-transition — on next cron start, recover from
  > signals.status column. Re-evaluate each pending signal against current state."

Usage:
    with shutdown_guard(as_of, telegram_bot=bot) as guard:
        # ... do work
        guard.set_summary({"trades": n, ...})
    # On normal exit: write 'ok' marker
    # On exception: expire pending, notify, write 'aborted' marker, re-raise

Version: v0.1.0 (2026-05-17)
"""
from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import date as date_type
from datetime import datetime
from pathlib import Path
from typing import Any

from execution.expiry import expire_all_pending
from utils.logger import get_logger

logger = get_logger(__name__)


MARKER_PATH = Path.home() / ".helios_last_run.json"

# v0.1.14.3: append-only run history for 5-day stability rollup.
# Purely additive — no decision logic reads this; `check_previous_run` continues
# to use MARKER_PATH (single most-recent marker). `scripts/run_summary.py` reads
# this file. Separated from MARKER_PATH so the prev-check contract is unchanged.
HISTORY_PATH = Path.home() / ".helios_run_history.jsonl"


class ShutdownState:
    """Mutable state holder. Caller sets summary; guard reads on exit.

    v0.1.14.3.1: gained a stable `run_id` (uuid4 hex prefix) set at construction.
    Every marker / history record written during this run carries the same
    run_id, enabling cross-log correlation in crash-recovery investigation,
    duplicate-run detection, retry chains, and "same as_of multiple executions"
    scenarios.
    """
    def __init__(self) -> None:
        self.summary: dict[str, Any] = {}
        self.error: BaseException | None = None
        self.run_id: str = uuid.uuid4().hex[:12]

    def set_summary(self, summary: dict) -> None:
        self.summary = summary


class PreflightDecline(Exception):  # noqa: N818 — intentionally NOT *Error suffix
    """Signaled by daily_run preflight checks (Steps 0-3) to indicate a
    *controlled refusal to start*, not a mid-pipeline crash.

    Naming rationale (deliberate N818 violation): a decline is not an error
    in the operational-semantics sense. Like stdlib's StopIteration /
    KeyboardInterrupt / SystemExit / GeneratorExit (also no "Error" suffix),
    this exception signals a control-flow event, not a failure. The whole
    point of c3's bug fix is the distinction "拒絕執行 ≠ 執行失敗".

    v0.1.14.2-c3 — distinct from RuntimeError so shutdown_guard can:
      - NOT write status='aborted' (preflight never started actual work, no
        marker cascade)
      - NOT expire pending signals (no in-flight state to clean up)
      - NOT spam telegram with crash notification
      - print a clean single-line message instead of Python traceback
      - exit with SystemExit(1)

    The previous architecture treated every exception uniformly via
    _abort_cleanup, which caused the marker cascade discovered in c2's
    nexus smoke test (every preflight refusal wrote a new 'aborted' marker,
    permanently blocking the next run).
    """
    def __init__(self, reason: str, *, exit_code: int = 1) -> None:
        super().__init__(reason)
        self.reason = reason
        self.exit_code = exit_code


@contextmanager
def shutdown_guard(as_of: date_type, telegram_notify=None):
    """Context manager wrapping daily_run flow.

    Args:
        as_of: trading date for marker file
        telegram_notify: optional callable(text: str) for abort notifications

    Yields ShutdownState with .set_summary(dict).
    """
    state = ShutdownState()
    logger.info("run_started", run_id=state.run_id, as_of=str(as_of))
    try:
        yield state
        # Success path
        _write_marker(as_of, "ok", state.summary, run_id=state.run_id)
        logger.info(
            "shutdown_clean", run_id=state.run_id, as_of=str(as_of), summary=state.summary,
        )

    except PreflightDecline as e:
        # Controlled refusal — distinct from mid-pipeline crash.
        # Write a 'declined_preflight' marker (audit trail) but no abort cleanup.
        logger.info(
            "shutdown_declined_preflight",
            run_id=state.run_id, as_of=str(as_of), reason=e.reason,
        )
        _write_marker(
            as_of, "declined_preflight", {"reason": e.reason}, run_id=state.run_id,
        )
        # Clean, single-line operator message (no traceback)
        import sys
        print(f"daily_run declined: {e.reason}", file=sys.stderr)
        raise SystemExit(e.exit_code) from None

    except KeyboardInterrupt as e:
        logger.warning("shutdown_keyboard_interrupt", run_id=state.run_id, as_of=str(as_of))
        _abort_cleanup(as_of, "keyboard_interrupt", state, telegram_notify, e)
        raise
    except SystemExit:
        raise  # don't trap explicit sys.exit
    except BaseException as e:
        logger.exception(
            "shutdown_aborted", run_id=state.run_id, as_of=str(as_of), error=str(e),
        )
        _abort_cleanup(as_of, f"exception:{type(e).__name__}", state, telegram_notify, e)
        raise


# ─────────────────────────────────────────────────────────────
# Internals
# ─────────────────────────────────────────────────────────────


def _abort_cleanup(
    as_of: date_type,
    reason: str,
    state: ShutdownState,
    telegram_notify,
    error: BaseException,
) -> None:
    """Best-effort cleanup on abort:
       1. Expire PENDING signals (operator should re-evaluate)
       2. Notify operator via Telegram (if configured)
       3. Write 'aborted' marker
    Each step wrapped in try/except — never raise from cleanup.
    """
    # 1. Expire pending
    try:
        expired = expire_all_pending(reason=f"daily_run_abort:{reason}")
        state.summary["expired_on_abort"] = len(expired)
    except Exception as e:
        logger.error("abort_expire_failed", error=str(e))
        state.summary["expired_on_abort_error"] = str(e)

    # 2. Telegram notify
    if telegram_notify is not None:
        try:
            msg = (
                f"⚠️ Helios daily_run 已中止({as_of})\n"
                f"原因:{reason}\n"
                f"錯誤:{str(error)[:200]}\n"
                f"已失效的待處理訊號:{state.summary.get('expired_on_abort', '?')} 筆\n"
                f"請先排查後再執行下一次 daily_run。"
            )
            telegram_notify(msg)
            state.summary["telegram_notified"] = True
        except Exception as e:
            logger.error("abort_telegram_failed", error=str(e))
            state.summary["telegram_notified"] = False

    # 3. Marker
    state.summary["abort_reason"] = reason
    state.summary["abort_error"] = str(error)[:500]
    _write_marker(as_of, "aborted", state.summary, run_id=state.run_id)


def _write_marker(
    as_of: date_type, status: str, summary: dict, *, run_id: str | None = None,
) -> None:
    """Write marker file. Never raise — last line of defense.

    v0.1.14.3: also appends a copy to HISTORY_PATH (jsonl) for the 5-day
    rollup reporter. Best-effort; failures are logged but never propagate.
    The marker file remains the single source for `check_previous_run`.

    v0.1.14.3.1: `run_id` (when supplied by shutdown_guard) is recorded in
    every marker / history record, so crash-recovery and retry-chain
    investigation can correlate this run with logs and downstream effects.
    The arg is kw-only with a default to keep the signature backward-compatible
    for any test or external caller that constructs markers directly.
    """
    payload = {
        "as_of": str(as_of),
        "completed_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "summary": summary,
    }
    if run_id is not None:
        payload["run_id"] = run_id
    try:
        MARKER_PATH.write_text(json.dumps(payload, indent=2))
    except OSError as e:
        logger.error("marker_write_failed", error=str(e))
    _append_history(payload)


def _append_history(payload: dict) -> None:
    """Append a run record to HISTORY_PATH (jsonl). v0.1.14.3.

    Never raises. Used by `scripts/run_summary.py` for cross-run aggregation.
    Failure here must not affect the run's exit status — it is purely
    observability, not state.
    """
    try:
        with HISTORY_PATH.open("a") as f:
            f.write(json.dumps(payload) + "\n")
    except OSError as e:
        logger.warning("history_append_failed", error=str(e))


def read_marker() -> dict | None:
    """Read last-run marker. Returns None if absent or invalid."""
    if not MARKER_PATH.exists():
        return None
    try:
        return json.loads(MARKER_PATH.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("marker_read_failed", error=str(e))
        return None


def read_history(n: int = 5) -> list[dict]:
    """Return the last `n` run records from HISTORY_PATH (oldest→newest).

    v0.1.14.3: consumer for the 5-day stability rollup. If the file is absent
    or unreadable, returns []. Tolerates malformed lines (skips with a warn).
    """
    if not HISTORY_PATH.exists():
        return []
    try:
        lines = HISTORY_PATH.read_text().splitlines()
    except OSError as e:
        logger.warning("history_read_failed", error=str(e))
        return []
    records: list[dict] = []
    for line in lines[-n:]:
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            logger.warning("history_skip_bad_line", line_preview=line[:80])
            continue
    return records


def check_previous_run(as_of: date_type) -> tuple[bool, str]:
    """Step 0: verify previous run completed cleanly (or declined cleanly).

    v0.1.14.2-c3: 'declined_preflight' is treated as proceed-safe, because
    a preflight decline means the previous run made NO side effects (no
    pending signals, no orders, no position state changes). Only 'aborted'
    (mid-pipeline crash) requires operator investigation before next run.

    Returns (ok_to_proceed, message).
    """
    marker = read_marker()
    if marker is None:
        return True, "no previous marker (first run)"
    prev_status = marker.get("status")
    prev_as_of = marker.get("as_of")
    if prev_status == "ok":
        return True, f"previous run OK ({prev_as_of})"
    if prev_status == "declined_preflight":
        return True, f"previous run declined_preflight ({prev_as_of}) — no side effects, proceeding"
    return False, (
        f"previous run NOT ok (as_of={prev_as_of}, status={prev_status}). "
        f"Investigate before proceeding. To override, delete {MARKER_PATH}."
    )


# ─────────────────────────────────────────────────────────────
# Pre-run state checks (sibling helpers to check_previous_run)
# ─────────────────────────────────────────────────────────────


def check_data_freshness(as_of: date_type) -> tuple[bool, str]:
    """Step 3 (v0.1.14.2-c3 reorder): verify daily_price_adj covers BOTH
    signal day (as_of) AND the T+1 fill day.

    Per §9 Data Freshness Contract: stale data silently propagating is a worse
    failure than skipped trading — abort, don't degrade.

    v0.1.14.2-c3: composition of two concerns previously conflated:
      - market.trading_calendar.next_trading_day(as_of) — calendar truth
      - market.trading_calendar.next_fillable_day(as_of) — calendar + data
    The latter returns None if next trading day's data isn't ingested yet,
    which is the actual gate for T+1 fill price availability. By delegating
    calendar logic to market/, execution layer no longer owns calendar
    implementation (single source of truth, per c3 P0-3).
    """
    from data.database import connect
    from market.trading_calendar import next_fillable_day

    with connect(read_only=True) as conn:
        latest = conn.execute("SELECT MAX(date) FROM daily_price_adj").fetchone()[0]
    if latest is None:
        return False, "no daily_price_adj data — run ingest pipeline first"
    if latest < as_of:
        return False, f"data stale: latest={latest}, requested={as_of}"
    nxt = next_fillable_day(as_of)
    if nxt is None:
        return False, (
            f"data_not_ready_for_t_plus_1_fill: as_of={as_of} latest={latest} "
            f"(T+1 fill price proxy unavailable — ingest next trading day's data first)"
        )
    return True, f"data fresh through {latest} (T+1 fill day {nxt} covered)"
