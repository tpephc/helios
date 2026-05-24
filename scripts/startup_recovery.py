# scripts/startup_recovery.py
"""Startup recovery for in-flight orders — v0.1.16 (post-review v2).

Called by daily_run.py as Step 0a, BEFORE any business logic. Scans the
orders journal for in-flight rows from a previous process and resolves
them defensively.

v2 changes from v1 (per advisor review):
  - C-P0-5: stale SUBMITTED detection uses fill_date + trading calendar,
    NOT wall-clock 16 hours. Friday 16:00 → Monday 09:00 is 65 wall hours
    but the order with fill_date=Monday is NOT stale Sunday.
  - D-P1-7: Telegram notification is consolidated into one summary
    message at the end, not one message per resolved order. Reduces API
    calls and prevents alert fatigue.
  - K-P2-a: uses Asia/Taipei timezone explicitly.

Two categories handled:

1. Orphan INTENT (status=INTENT, intent_at > 10 min old):
   The previous process recorded intent but did not transition to
   SUBMITTED. Either it crashed before api.place_order(), or place_order
   raised but the failure handler never ran.

   Action: mark as FAILED.transport with requires_broker_verification=True.
   reconcile_fills.py MUST query the broker.

2. Stale SUBMITTED (fill_date <= last completed trading day):
   ROD order whose expected execution date has already passed without
   resolution. The order has definitionally expired.

   Action: mark as EXPIRED. If reconcile later finds a corresponding
   broker fill, the EXPIRED row is incorrect but the fill is safe;
   flag as anomaly.

Version: v0.1.16 (2026-05-24, v2)
"""
from __future__ import annotations

from datetime import date as date_type
from datetime import datetime, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

from execution.order_types import FailureType
from storage import order_journal
from utils.logger import get_logger

logger = get_logger(__name__)

TAIPEI_TZ = ZoneInfo("Asia/Taipei")

# INTENT orphan threshold: normal INTENT→SUBMITTED is sub-second. 10 min
# is generous and avoids false positives during slow CI/test runs.
INTENT_ORPHAN_THRESHOLD = timedelta(minutes=10)


def _last_completed_trading_day(
    as_of: date_type,
    is_trading_day: Callable[[date_type], bool] | None = None,
) -> date_type:
    """Return the most recent trading day strictly before as_of.

    Walks backward day by day. Defaults to Mon-Fri if no calendar provided
    (does NOT account for Taiwan holidays — caller should pass an
    is_trading_day callable that consults company_metadata or a holiday
    table in production).

    Args:
        as_of: today's date (typically daily_run.py's `as_of` argument)
        is_trading_day: optional predicate. If None, uses weekday default.

    Returns:
        The last trading day on or before (as_of - 1). For Monday, returns
        previous Friday (assuming no holiday).
    """
    if is_trading_day is None:
        is_trading_day = lambda d: d.weekday() < 5  # Mon=0 ... Fri=4

    cursor = as_of - timedelta(days=1)
    # Safety limit: don't walk back more than 10 days
    for _ in range(10):
        if is_trading_day(cursor):
            return cursor
        cursor = cursor - timedelta(days=1)
    # Pathological case: 10 consecutive non-trading days. Return as-is.
    logger.warning(
        "last_completed_trading_day_fallback",
        as_of=str(as_of), cursor=str(cursor),
    )
    return cursor


def recover_in_flight_orders(
    *,
    as_of: date_type | None = None,
    now: datetime | None = None,
    is_trading_day: Callable[[date_type], bool] | None = None,
    notify: Callable[[str], None] | None = None,
) -> dict:
    """Resolve in-flight orders from a previous process run.

    Args:
        as_of: today's date (for stale-detection cutoff). Defaults to
               today in Taipei.
        now: reference time (default: datetime.now(TAIPEI_TZ)).
        is_trading_day: optional trading calendar predicate (see
               _last_completed_trading_day).
        notify: optional callback for Telegram summary alert. Signature:
                notify(msg). v2: invoked ONCE with summary, not per order.

    Returns:
        Summary dict with counts and order IDs of resolved orphans.
    """
    when = now or datetime.now(tz=TAIPEI_TZ)
    if when.tzinfo is None:
        when = when.replace(tzinfo=TAIPEI_TZ)
    today = as_of or when.date()

    summary = {
        "orphan_intents_resolved": 0,
        "stale_submitted_resolved": 0,
        "orphan_intent_ids": [],
        "stale_submitted_ids": [],
        "resolution_errors": [],
    }

    # ── Resolve orphan INTENTs (wall-clock threshold is correct here ──
    # because INTENT→SUBMITTED is sub-second; 10 min is a crash signal,
    # not a market-time concept) ────────────────────────────────────────
    orphan_intents = order_journal.list_orphan_intents(
        older_than=INTENT_ORPHAN_THRESHOLD, now=when,
    )
    for orphan in orphan_intents:
        try:
            order_journal.mark_failed(
                order_id=orphan.order_id,
                failure_type=FailureType.TRANSPORT,
                error_code="startup_recovery_orphan_intent",
                error_message=(
                    f"INTENT older than {INTENT_ORPHAN_THRESHOLD}; "
                    f"previous process likely crashed before mark_submitted. "
                    f"requires_broker_verification=True."
                ),
                finalized_at=when,
            )
            summary["orphan_intents_resolved"] += 1
            summary["orphan_intent_ids"].append(orphan.order_id)
            logger.warning(
                "startup_recovery_orphan_intent_resolved",
                order_id=orphan.order_id, symbol=orphan.symbol,
                side=orphan.side.value if orphan.side else None,
                intent_age_minutes=(
                    (when - orphan.intent_at).total_seconds() / 60
                    if orphan.intent_at else None
                ),
            )
        except Exception as exc:
            logger.error(
                "startup_recovery_orphan_intent_resolve_failed",
                order_id=orphan.order_id, error=str(exc),
            )
            summary["resolution_errors"].append({
                "order_id": orphan.order_id,
                "kind": "orphan_intent",
                "error": str(exc),
            })

    # ── Resolve stale SUBMITTEDs (trading-calendar-aware, NOT wall-clock) ─
    expired_cutoff = _last_completed_trading_day(today, is_trading_day)
    stale_submitted = order_journal.list_stale_submitted_by_fill_date(
        expired_on_or_before=expired_cutoff, now=when,
    )
    for stale in stale_submitted:
        try:
            order_journal.mark_expired(
                order_id=stale.order_id,
                reason=(
                    f"SUBMITTED with fill_date={stale.fill_date} <= "
                    f"last_trading_day={expired_cutoff}; ROD expired."
                ),
                finalized_at=when,
            )
            summary["stale_submitted_resolved"] += 1
            summary["stale_submitted_ids"].append(stale.order_id)
            logger.warning(
                "startup_recovery_stale_submitted_resolved",
                order_id=stale.order_id, symbol=stale.symbol,
                side=stale.side.value if stale.side else None,
                fill_date=str(stale.fill_date) if stale.fill_date else None,
                expired_cutoff=str(expired_cutoff),
            )
        except Exception as exc:
            logger.error(
                "startup_recovery_stale_submitted_resolve_failed",
                order_id=stale.order_id, error=str(exc),
            )
            summary["resolution_errors"].append({
                "order_id": stale.order_id,
                "kind": "stale_submitted",
                "error": str(exc),
            })

    logger.info(
        "startup_recovery_complete",
        orphan_intents_resolved=summary["orphan_intents_resolved"],
        stale_submitted_resolved=summary["stale_submitted_resolved"],
        resolution_errors=len(summary["resolution_errors"]),
    )

    # v2 (D-P1-7): single consolidated notification, not per-order
    if notify is not None and (
        summary["orphan_intents_resolved"]
        or summary["stale_submitted_resolved"]
        or summary["resolution_errors"]
    ):
        lines = ["🔧 啟動修復摘要"]
        if summary["orphan_intents_resolved"]:
            lines.append(
                f"孤兒 INTENT: {summary['orphan_intents_resolved']} 筆 "
                f"(需 reconcile 查券商)"
            )
        if summary["stale_submitted_resolved"]:
            lines.append(
                f"過期 SUBMITTED: {summary['stale_submitted_resolved']} 筆"
            )
        if summary["resolution_errors"]:
            lines.append(
                f"⚠️ 修復失敗: {len(summary['resolution_errors'])} 筆 "
                f"(查 log)"
            )
        notify("\n".join(lines))

    return summary


def main() -> int:
    """CLI: run startup_recovery standalone (for manual invocation)."""
    summary = recover_in_flight_orders()
    print("Startup recovery summary:")
    print(f"  Orphan INTENTs resolved:     {summary['orphan_intents_resolved']}")
    print(f"  Stale SUBMITTEDs resolved:   {summary['stale_submitted_resolved']}")
    if summary["orphan_intent_ids"]:
        print(f"  Orphan INTENT IDs: {summary['orphan_intent_ids']}")
    if summary["stale_submitted_ids"]:
        print(f"  Stale SUBMITTED IDs: {summary['stale_submitted_ids']}")
    if summary["resolution_errors"]:
        print(f"  Resolution errors: {summary['resolution_errors']}")
    return 0 if not summary["resolution_errors"] else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
