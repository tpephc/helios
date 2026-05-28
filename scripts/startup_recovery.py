# scripts/startup_recovery.py
"""Startup recovery for in-flight orders — v0.1.18.

Called by daily_run.py as Step 0a, BEFORE any business logic. Scans the
orders journal for in-flight rows from a previous process and resolves
them defensively.

v0.1.18: account_id parameter added to recover_in_flight_orders and
  threaded through all order_journal calls.

v2 changes from v1 (per advisor review):
  - C-P0-5: stale SUBMITTED detection uses fill_date + trading calendar.
  - D-P1-7: Telegram notification consolidated into one summary message.
  - K-P2-a: uses Asia/Taipei timezone explicitly.

Version: v0.1.18 (2026-05-28)
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

INTENT_ORPHAN_THRESHOLD = timedelta(minutes=10)


def _last_completed_trading_day(
    as_of: date_type,
    is_trading_day: Callable[[date_type], bool] | None = None,
) -> date_type:
    """Return the most recent trading day strictly before as_of."""
    if is_trading_day is None:
        is_trading_day = lambda d: d.weekday() < 5

    cursor = as_of - timedelta(days=1)
    for _ in range(10):
        if is_trading_day(cursor):
            return cursor
        cursor = cursor - timedelta(days=1)
    logger.warning(
        "last_completed_trading_day_fallback",
        as_of=str(as_of), cursor=str(cursor),
    )
    return cursor


def recover_in_flight_orders(
    *,
    account_id: str,
    as_of: date_type | None = None,
    now: datetime | None = None,
    is_trading_day: Callable[[date_type], bool] | None = None,
    notify: Callable[[str], None] | None = None,
) -> dict:
    """Resolve in-flight orders from a previous process run.

    v0.1.18: account_id is required. All order_journal queries are
    scoped to this account.

    Args:
        account_id: broker account identifier.
        as_of: today's date (for stale-detection cutoff).
        now: reference time (default: datetime.now(TAIPEI_TZ)).
        is_trading_day: optional trading calendar predicate.
        notify: optional callback for Telegram summary alert.

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
        "stale_ready_resolved": 0,
        "orphan_intent_ids": [],
        "stale_submitted_ids": [],
        "stale_ready_ids": [],
        "resolution_errors": [],
    }

    # ── Resolve orphan INTENTs ────────────────────────────────────────
    orphan_intents = order_journal.list_orphan_intents(
        account_id=account_id,
        older_than=INTENT_ORPHAN_THRESHOLD,
        now=when,
    )
    for orphan in orphan_intents:
        try:
            order_journal.mark_failed(
                order_id=orphan.order_id,
                account_id=account_id,
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
                order_id=orphan.order_id, account_id=account_id,
                symbol=orphan.symbol,
                side=orphan.side.value if orphan.side else None,
                intent_age_minutes=(
                    (when - orphan.intent_at).total_seconds() / 60
                    if orphan.intent_at else None
                ),
            )
        except Exception as exc:
            logger.error(
                "startup_recovery_orphan_intent_resolve_failed",
                order_id=orphan.order_id, account_id=account_id,
                error=str(exc),
            )
            summary["resolution_errors"].append({
                "order_id": orphan.order_id,
                "kind": "orphan_intent",
                "error": str(exc),
            })

    # ── Resolve stale SUBMITTEDs ──────────────────────────────────────
    expired_cutoff = _last_completed_trading_day(today, is_trading_day)
    stale_submitted = order_journal.list_stale_submitted_by_fill_date(
        expired_on_or_before=expired_cutoff,
        account_id=account_id,
        now=when,
    )
    for stale in stale_submitted:
        try:
            order_journal.mark_expired(
                order_id=stale.order_id,
                account_id=account_id,
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
                order_id=stale.order_id, account_id=account_id,
                symbol=stale.symbol,
                side=stale.side.value if stale.side else None,
                fill_date=str(stale.fill_date) if stale.fill_date else None,
                expired_cutoff=str(expired_cutoff),
            )
        except Exception as exc:
            logger.error(
                "startup_recovery_stale_submitted_resolve_failed",
                order_id=stale.order_id, account_id=account_id,
                error=str(exc),
            )
            summary["resolution_errors"].append({
                "order_id": stale.order_id,
                "kind": "stale_submitted",
                "error": str(exc),
            })

    # ── Resolve stale READY_FOR_SUBMISSION ────────────────────────────
    stale_ready = order_journal.list_stale_ready_for_submission(
        expired_on_or_before=expired_cutoff,
        account_id=account_id,
    )
    for stale in stale_ready:
        try:
            order_journal.mark_expired(
                order_id=stale.order_id,
                account_id=account_id,
                reason=(
                    f"READY_FOR_SUBMISSION with target_fill_date="
                    f"{stale.target_fill_date} <= "
                    f"last_trading_day={expired_cutoff}; "
                    f"submission window missed."
                ),
                finalized_at=when,
            )
            summary["stale_ready_resolved"] += 1
            summary["stale_ready_ids"].append(stale.order_id)
            logger.warning(
                "startup_recovery_stale_ready_resolved",
                order_id=stale.order_id, account_id=account_id,
                symbol=stale.symbol,
                target_fill_date=(
                    str(stale.target_fill_date)
                    if stale.target_fill_date else None
                ),
                expired_cutoff=str(expired_cutoff),
            )
        except Exception as exc:
            logger.error(
                "startup_recovery_stale_ready_resolve_failed",
                order_id=stale.order_id, account_id=account_id,
                error=str(exc),
            )
            summary["resolution_errors"].append({
                "order_id": stale.order_id,
                "kind": "stale_ready",
                "error": str(exc),
            })

    logger.info(
        "startup_recovery_complete",
        account_id=account_id,
        orphan_intents_resolved=summary["orphan_intents_resolved"],
        stale_submitted_resolved=summary["stale_submitted_resolved"],
        stale_ready_resolved=summary["stale_ready_resolved"],
        resolution_errors=len(summary["resolution_errors"]),
    )

    # Consolidated Telegram notification
    if notify is not None and (
        summary["orphan_intents_resolved"]
        or summary["stale_submitted_resolved"]
        or summary["stale_ready_resolved"]
        or summary["resolution_errors"]
    ):
        lines = [f"🔧 啟動修復摘要 ({account_id})"]
        if summary["orphan_intents_resolved"]:
            lines.append(
                f"孤兒 INTENT: {summary['orphan_intents_resolved']} 筆 "
                f"(需 reconcile 查券商)"
            )
        if summary["stale_submitted_resolved"]:
            lines.append(
                f"過期 SUBMITTED: {summary['stale_submitted_resolved']} 筆"
            )
        if summary["stale_ready_resolved"]:
            lines.append(
                f"過期 READY: {summary['stale_ready_resolved']} 筆 "
                f"(submitter 未執行)"
            )
        if summary["resolution_errors"]:
            lines.append(
                f"⚠️ 修復失敗: {len(summary['resolution_errors'])} 筆 "
                f"(查 log)"
            )
        notify("\n".join(lines))

    return summary


def main() -> int:
    """CLI: run startup_recovery standalone (for manual invocation).

    v0.1.18: loads account from config. Uses first enabled account
    if --account not specified.
    """
    import argparse
    from config.account_config import load_accounts, get_account

    parser = argparse.ArgumentParser(description="Startup recovery (standalone)")
    parser.add_argument("--account", type=str, default=None)
    args = parser.parse_args()

    if args.account == "all":
        raise RuntimeError(
            "--account all is not supported for startup_recovery. "
            "Use --account <id> and run separately per account."
        )

    if args.account:
        _account = get_account(args.account)
    else:
        _account = load_accounts()[0]

    summary = recover_in_flight_orders(account_id=_account.account_id)
    print(f"Startup recovery summary (account={_account.account_id}):")
    print(f"  Orphan INTENTs resolved:     {summary['orphan_intents_resolved']}")
    print(f"  Stale SUBMITTEDs resolved:   {summary['stale_submitted_resolved']}")
    print(f"  Stale READYs resolved:       {summary['stale_ready_resolved']}")
    if summary["orphan_intent_ids"]:
        print(f"  Orphan INTENT IDs: {summary['orphan_intent_ids']}")
    if summary["stale_submitted_ids"]:
        print(f"  Stale SUBMITTED IDs: {summary['stale_submitted_ids']}")
    if summary["stale_ready_ids"]:
        print(f"  Stale READY IDs: {summary['stale_ready_ids']}")
    if summary["resolution_errors"]:
        print(f"  Resolution errors: {summary['resolution_errors']}")
    return 0 if not summary["resolution_errors"] else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
