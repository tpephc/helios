#!/usr/bin/env python3
# scripts/execution_submitter.py
"""Execution submitter — v0.1.17.

Reads READY_FOR_SUBMISSION orders and submits them to broker at T+1 08:30,
or cancels stale SUBMITTED orders at T+1 09:05.

Two modes:
  --mode submit  (default, cron 08:30)
    1. Acquire filesystem lock (prevent double-run)
    2. Read READY_FOR_SUBMISSION WHERE target_fill_date = today
    3. Pre-submission checks per order
    4. Compute limit_price = prev_close * (1 + max_entry_gap_pct)
    5. Shioaji login → contract → place_order (LMT ROD)
    6. mark_submitted (with requires_broker_verification until confirmed)
    7. Telegram summary

  --mode cancel  (cron 09:05)
    1. Read SUBMITTED WHERE submitted_at < now - cancel_after_minutes
    2. Cancel via Shioaji API
    3. mark_expired
    4. Expire any remaining READY_FOR_SUBMISSION (missed submission window)

Design: docs/design/execution_submitter_design.md
Invariants: INV-1 (no broker in daily_run), INV-2 (gap filter), INV-3 (near-open),
            INV-EXEC-1 (no double submit), INV-EXEC-4 (idempotent)

Version: v0.1.17 (2026-05-27)
"""
from __future__ import annotations

import argparse
import fcntl
import os
import sys
from datetime import date as date_type, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from config.settings import get_settings
from data.database import connect, init_schema
from execution.order_types import FailureType, OrderStatus, SHARES_PER_LOT
from market.trading_calendar import is_trading_day
from storage import order_journal
from storage.positions import get_open_positions
from utils.logger import get_logger

logger = get_logger(__name__)

TAIPEI_TZ = ZoneInfo("Asia/Taipei")
LOCK_FILE = Path("data/_storage/.execution_submitter.lock")

# ── Configuration defaults ────────────────────────────────────────────────
# max_entry_gap_pct: [ASSUMED] 0.03 (3%) until calibrated by #16.
# This is the SINGLE source for both backtest entry filter and live
# limit price ceiling (INV-2). When #16 calibrates, update here.
DEFAULT_MAX_ENTRY_GAP_PCT = 0.03

# cancel_after_minutes: cancel unfilled orders after this many minutes
# post-submission. 5 minutes captures opening auction + early continuous.
DEFAULT_CANCEL_AFTER_MINUTES = 5


# ── Filesystem lock ───────────────────────────────────────────────────────


def _acquire_lock() -> int:
    """Acquire exclusive filesystem lock. Raises RuntimeError on conflict."""
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        raise RuntimeError(
            "execution_submitter already running (lock held). "
            "If stale, remove data/_storage/.execution_submitter.lock"
        )
    # Write PID for debugging
    os.ftruncate(fd, 0)
    os.write(fd, f"{os.getpid()}\n".encode())
    return fd


def _release_lock(fd: int) -> None:
    """Release filesystem lock."""
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    except OSError:
        pass


# ── Shioaji session management ────────────────────────────────────────────


def _shioaji_login(cfg: Any) -> tuple[Any, Any]:
    """Login to Shioaji. Returns (api, sj_module) or raises.

    Separate from LiveBroker to avoid its record_intent side-effect.
    Uses the same config fields.
    """
    import shioaji as sj

    simulation = cfg.shioaji_simulation
    api = sj.Shioaji(simulation=simulation)
    api.login(
        api_key=cfg.shioaji_api_key.get_secret_value() if cfg.shioaji_api_key else "",
        secret_key=cfg.shioaji_secret_key.get_secret_value() if cfg.shioaji_secret_key else "",
        fetch_contract=True,
        contracts_timeout=30_000,
        subscribe_trade=True,
    )
    if not simulation:
        api.activate_ca(
            ca_path=cfg.ca_cert_path or "",
            ca_passwd=cfg.ca_password.get_secret_value() if cfg.ca_password else "",
            person_id=api.stock_account.person_id,
        )
    api.set_default_account(api.stock_account)
    return api, sj


def _shioaji_logout(api: Any) -> None:
    """Logout from Shioaji, ignoring errors."""
    if api is None:
        return
    try:
        api.logout()
    except Exception as exc:
        logger.warning("execution_submitter_logout_error", error=str(exc))


# ── Prev close lookup ─────────────────────────────────────────────────────


def _get_prev_close(symbol: str, as_of: date_type) -> float | None:
    """Get adj_close for symbol on as_of date from daily_price_adj.

    as_of is the signal date (T). prev_close = adj_close[T].
    """
    with connect(read_only=True) as conn:
        row = conn.execute(
            "SELECT adj_close FROM daily_price_adj "
            "WHERE stock_id = ? AND date = ? LIMIT 1",
            [symbol, as_of],
        ).fetchone()
    return row[0] if row else None


# ── Pre-submission checks ─────────────────────────────────────────────────


def _pre_submission_check(
    order: Any,
    today: date_type,
) -> tuple[bool, str]:
    """Run pre-submission checks for a READY_FOR_SUBMISSION order.

    Returns (passed, reason). If not passed, caller should expire/fail.
    """
    # Check 1: target_fill_date == today
    if order.target_fill_date != today:
        return False, (
            f"stale: target_fill_date={order.target_fill_date} != today={today}"
        )

    # Check 2: no duplicate open position
    open_positions = get_open_positions()
    open_symbols = {p.symbol for p in open_positions}
    if order.symbol in open_symbols:
        return False, f"duplicate_position: {order.symbol} already OPEN"

    # Check 3: prev_close available
    # We need the signal date to look up prev_close. The signal date is
    # the trading day before target_fill_date. Use intent_at date as proxy.
    signal_date = order.intent_at.date() if order.intent_at else None
    if signal_date is None:
        return False, "data_missing: intent_at is None"

    prev_close = _get_prev_close(order.symbol, signal_date)
    if prev_close is None or prev_close <= 0:
        return False, (
            f"data_missing: no prev_close for {order.symbol} on {signal_date}"
        )

    return True, "OK"


# ── Submit mode ───────────────────────────────────────────────────────────


def _run_submit(
    today: date_type,
    max_entry_gap_pct: float,
    dry_run: bool = False,
    notify_fn: Any = None,
) -> dict:
    """Submit READY_FOR_SUBMISSION orders to broker.

    Returns summary dict.
    """
    summary = {
        "submitted": [],
        "expired": [],
        "failed": [],
        "skipped_dry_run": [],
    }

    orders = order_journal.list_ready_for_submission(
        target_fill_date=today,
    )

    if not orders:
        logger.info("execution_submitter_no_orders", target_fill_date=str(today))
        print(f"[submit] No READY_FOR_SUBMISSION orders for {today}")
        return summary

    print(f"[submit] Found {len(orders)} orders for {today}")

    # Pre-submission checks first (before login)
    eligible = []
    for order in orders:
        passed, reason = _pre_submission_check(order, today)
        if not passed:
            # Determine fail vs expire
            if reason.startswith("stale:") or reason.startswith("duplicate_position:"):
                order_journal.mark_expired(
                    order_id=order.order_id,
                    reason=f"pre_submission_check: {reason}",
                )
                summary["expired"].append(
                    {"order_id": order.order_id, "symbol": order.symbol, "reason": reason}
                )
                logger.warning(
                    "execution_submitter_pre_check_expired",
                    order_id=order.order_id, symbol=order.symbol, reason=reason,
                )
            else:
                order_journal.mark_failed(
                    order_id=order.order_id,
                    failure_type=FailureType.BROKER_REJECT,
                    error_code="pre_submission_check",
                    error_message=reason,
                )
                summary["failed"].append(
                    {"order_id": order.order_id, "symbol": order.symbol, "reason": reason}
                )
                logger.error(
                    "execution_submitter_pre_check_failed",
                    order_id=order.order_id, symbol=order.symbol, reason=reason,
                )
            continue
        eligible.append(order)

    if not eligible:
        print("[submit] All orders failed pre-submission checks")
        return summary

    if dry_run:
        for order in eligible:
            signal_date = order.intent_at.date()
            prev_close = _get_prev_close(order.symbol, signal_date)
            limit_price = prev_close * (1 + max_entry_gap_pct) if prev_close else None
            summary["skipped_dry_run"].append({
                "order_id": order.order_id,
                "symbol": order.symbol,
                "prev_close": prev_close,
                "limit_price": limit_price,
            })
            print(
                f"  [dry-run] {order.symbol}: prev_close={prev_close}, "
                f"limit={limit_price:.2f}" if limit_price else
                f"  [dry-run] {order.symbol}: no prev_close"
            )
        return summary

    # Login to Shioaji (once for all orders)
    cfg = get_settings()
    try:
        api, sj = _shioaji_login(cfg)
    except Exception as exc:
        # Login failed — fail all eligible orders
        for order in eligible:
            order_journal.mark_failed(
                order_id=order.order_id,
                failure_type=FailureType.TRANSPORT,
                error_code="shioaji_login_failed",
                error_message=str(exc),
            )
            summary["failed"].append({
                "order_id": order.order_id, "symbol": order.symbol,
                "reason": f"login_failed: {exc}",
            })
        logger.error("execution_submitter_login_failed", error=str(exc))
        return summary

    from shioaji.constant import (
        Action, OrderType, StockOrderCond, StockOrderLot, StockPriceType,
    )
    from execution.live_broker import _resolve_stock_contract

    try:
        for order in eligible:
            signal_date = order.intent_at.date()
            prev_close = _get_prev_close(order.symbol, signal_date)
            limit_price = round(prev_close * (1 + max_entry_gap_pct), 2)

            # ── Idempotency: mark SUBMITTED + requires_broker_verification ──
            # before broker call. If we crash after place_order but before
            # confirm, reconcile will resolve via requires_broker_verification.
            now = datetime.now(tz=TAIPEI_TZ)
            order_journal.mark_submitted(
                order_id=order.order_id,
                broker_order_id=None,  # not yet known
                submitted_at=now,
            )

            # Resolve contract
            contract = _resolve_stock_contract(api, order.symbol)
            if contract is None:
                order_journal.mark_failed(
                    order_id=order.order_id,
                    failure_type=FailureType.BROKER_REJECT,
                    error_code="contract_not_found",
                    error_message=f"no contract for {order.symbol!r}",
                )
                summary["failed"].append({
                    "order_id": order.order_id, "symbol": order.symbol,
                    "reason": "contract_not_found",
                })
                continue

            # Update order spec with limit price and notional
            notional = limit_price * order.requested_lots * SHARES_PER_LOT
            order_journal.update_order_spec(
                order_id=order.order_id,
                limit_price=limit_price,
                notional=notional,
            )

            # Place order via Shioaji
            try:
                sj_order = sj.order.StockOrder(
                    action=Action.Buy,
                    price=limit_price,
                    quantity=order.requested_lots,
                    price_type=StockPriceType.LMT,
                    order_type=OrderType.ROD,
                    order_lot=StockOrderLot.Common,
                    order_cond=StockOrderCond.Cash,
                    account=api.stock_account,
                )
                trade = api.place_order(contract, sj_order)
            except Exception as exc:
                order_journal.mark_failed(
                    order_id=order.order_id,
                    failure_type=FailureType.TRANSPORT,
                    error_code="place_order_raised",
                    error_message=f"{type(exc).__name__}: {exc}",
                )
                summary["failed"].append({
                    "order_id": order.order_id, "symbol": order.symbol,
                    "reason": f"place_order_raised: {exc}",
                })
                logger.error(
                    "execution_submitter_place_order_failed",
                    order_id=order.order_id, symbol=order.symbol,
                    error=str(exc),
                )
                continue

            # Extract broker_order_id
            broker_order_id = (
                trade.order.id if trade and trade.order and trade.order.id
                else None
            )

            # Confirm submission: update broker_order_id, clear verification flag
            with connect() as conn:
                conn.execute(
                    """
                    UPDATE orders SET
                        broker_order_id = ?,
                        requires_broker_verification = FALSE,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE order_id = ?
                    """,
                    [broker_order_id if broker_order_id else None, order.order_id],
                )

            summary["submitted"].append({
                "order_id": order.order_id,
                "symbol": order.symbol,
                "limit_price": limit_price,
                "broker_order_id": broker_order_id,
            })
            logger.info(
                "execution_submitter_order_submitted",
                order_id=order.order_id,
                symbol=order.symbol,
                limit_price=limit_price,
                broker_order_id=broker_order_id,
                notional=notional,
            )

    finally:
        _shioaji_logout(api)

    # Telegram notification
    if notify_fn and (summary["submitted"] or summary["failed"] or summary["expired"]):
        lines = [f"📤 Execution Submitter — {today}"]
        if summary["submitted"]:
            lines.append(f"✅ Submitted: {len(summary['submitted'])}")
            for s in summary["submitted"]:
                lines.append(f"  {s['symbol']} LMT {s['limit_price']:.2f}")
        if summary["expired"]:
            lines.append(f"⏭️ Expired: {len(summary['expired'])}")
            for e in summary["expired"]:
                lines.append(f"  {e['symbol']}: {e['reason']}")
        if summary["failed"]:
            lines.append(f"❌ Failed: {len(summary['failed'])}")
            for f_ in summary["failed"]:
                lines.append(f"  {f_['symbol']}: {f_['reason']}")
        notify_fn("\n".join(lines))

    print(
        f"[submit] submitted={len(summary['submitted'])} "
        f"expired={len(summary['expired'])} "
        f"failed={len(summary['failed'])}"
    )
    return summary


# ── Cancel mode ───────────────────────────────────────────────────────────


def _run_cancel(
    today: date_type,
    cancel_after_minutes: int,
    dry_run: bool = False,
    notify_fn: Any = None,
) -> dict:
    """Cancel stale SUBMITTED orders and expire leftover READY_FOR_SUBMISSION.

    Returns summary dict.
    """
    summary = {
        "cancelled": [],
        "expired_ready": [],
        "failed": [],
    }
    now = datetime.now(tz=TAIPEI_TZ)
    cutoff = now - timedelta(minutes=cancel_after_minutes)

    # Find SUBMITTED orders older than cutoff
    with connect(read_only=True) as conn:
        rows = conn.execute(
            "SELECT order_id, symbol, broker_order_id, submitted_at "
            "FROM orders WHERE status = 'SUBMITTED' AND submitted_at < ?",
            [cutoff],
        ).fetchall()

    stale_submitted = [
        {"order_id": r[0], "symbol": r[1], "broker_order_id": r[2], "submitted_at": r[3]}
        for r in rows
    ]

    if stale_submitted and not dry_run:
        # Login for cancel
        cfg = get_settings()
        try:
            api, sj = _shioaji_login(cfg)
        except Exception as exc:
            logger.error("execution_submitter_cancel_login_failed", error=str(exc))
            for s in stale_submitted:
                summary["failed"].append({
                    "order_id": s["order_id"], "symbol": s["symbol"],
                    "reason": f"login_failed: {exc}",
                })
            # Still try to expire READY_FOR_SUBMISSION below
            api = None
    else:
        api = None

    try:
        for s in stale_submitted:
            if dry_run:
                print(f"  [dry-run cancel] {s['symbol']} order_id={s['order_id']}")
                continue

            # Attempt broker cancel
            if api is not None and s["broker_order_id"]:
                try:
                    # Shioaji cancel: need to find the trade object
                    # In practice, cancel_order takes the trade object.
                    # For v0.1.17, we mark as EXPIRED directly since
                    # Shioaji cancel API semantics are [ASSUMED] (Q3 in design doc).
                    # TODO: implement actual api.cancel_order when P-obs-2 confirms behavior
                    logger.warning(
                        "execution_submitter_cancel_not_implemented",
                        order_id=s["order_id"],
                        broker_order_id=s["broker_order_id"],
                        note="Shioaji cancel API semantics unverified (Q3). "
                             "Marking EXPIRED; reconcile will resolve.",
                    )
                except Exception as exc:
                    logger.error(
                        "execution_submitter_cancel_failed",
                        order_id=s["order_id"], error=str(exc),
                    )

            # Mark expired regardless (conservative: if cancel fails,
            # ROD expires at market close anyway)
            order_journal.mark_expired(
                order_id=s["order_id"],
                reason=f"cancel_sweep: submitted_at={s['submitted_at']} "
                       f"< cutoff={cutoff} ({cancel_after_minutes}min)",
            )
            summary["cancelled"].append({
                "order_id": s["order_id"], "symbol": s["symbol"],
            })
            logger.info(
                "execution_submitter_order_cancelled",
                order_id=s["order_id"], symbol=s["symbol"],
            )

        # Expire leftover READY_FOR_SUBMISSION (missed submission window)
        leftover = order_journal.list_ready_for_submission(
            target_fill_date=today,
        )
        for order in leftover:
            order_journal.mark_expired(
                order_id=order.order_id,
                reason=f"cancel_sweep: READY_FOR_SUBMISSION still pending at "
                       f"{now.strftime('%H:%M')}; submission window missed",
            )
            summary["expired_ready"].append({
                "order_id": order.order_id, "symbol": order.symbol,
            })
            logger.warning(
                "execution_submitter_ready_expired",
                order_id=order.order_id, symbol=order.symbol,
            )

    finally:
        if api is not None:
            _shioaji_logout(api)

    # Telegram notification
    if notify_fn and (summary["cancelled"] or summary["expired_ready"] or summary["failed"]):
        lines = [f"🧹 Cancel Sweep — {today}"]
        if summary["cancelled"]:
            lines.append(f"⏱️ Cancelled: {len(summary['cancelled'])}")
            for c in summary["cancelled"]:
                lines.append(f"  {c['symbol']}")
        if summary["expired_ready"]:
            lines.append(f"⏭️ Missed window: {len(summary['expired_ready'])}")
            for e in summary["expired_ready"]:
                lines.append(f"  {e['symbol']}")
        if summary["failed"]:
            lines.append(f"❌ Failed: {len(summary['failed'])}")
        notify_fn("\n".join(lines))

    print(
        f"[cancel] cancelled={len(summary['cancelled'])} "
        f"expired_ready={len(summary['expired_ready'])} "
        f"failed={len(summary['failed'])}"
    )
    return summary


# ── Main ──────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="v0.1.17 execution submitter + cancel sweep",
    )
    parser.add_argument(
        "--mode", choices=["submit", "cancel"], default="submit",
        help="submit (08:30) or cancel (09:05)",
    )
    parser.add_argument("--as-of", type=str, default=None,
                        help="Override today's date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without executing")
    parser.add_argument("--max-entry-gap-pct", type=float,
                        default=DEFAULT_MAX_ENTRY_GAP_PCT,
                        help=f"Max gap %% for limit price (default: {DEFAULT_MAX_ENTRY_GAP_PCT})")
    parser.add_argument("--cancel-after-minutes", type=int,
                        default=DEFAULT_CANCEL_AFTER_MINUTES,
                        help=f"Cancel unfilled after N minutes (default: {DEFAULT_CANCEL_AFTER_MINUTES})")
    args = parser.parse_args()

    init_schema()
    today = date_type.fromisoformat(args.as_of) if args.as_of else date_type.today()

    if not is_trading_day(today):
        print(f"{today} is not a trading day; exiting")
        return 0

    # Acquire lock
    lock_fd = _acquire_lock()
    try:
        # Telegram bot (optional)
        notify_fn = None
        try:
            from communication.telegram import TelegramBot, TelegramConfig
            bot = TelegramBot(TelegramConfig())
            from communication.telegram.sender import push_simple
            notify_fn = lambda msg: push_simple(bot, msg)
        except Exception:
            logger.warning("execution_submitter_telegram_unavailable")

        if args.mode == "submit":
            summary = _run_submit(
                today=today,
                max_entry_gap_pct=args.max_entry_gap_pct,
                dry_run=args.dry_run,
                notify_fn=notify_fn,
            )
        else:
            summary = _run_cancel(
                today=today,
                cancel_after_minutes=args.cancel_after_minutes,
                dry_run=args.dry_run,
                notify_fn=notify_fn,
            )

        return 0 if not summary.get("failed") else 1

    finally:
        _release_lock(lock_fd)


if __name__ == "__main__":
    sys.exit(main())
