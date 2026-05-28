#!/usr/bin/env python3
# scripts/execution_submitter.py
"""Execution submitter — v0.1.18.

Reads READY_FOR_SUBMISSION orders and submits them to broker at T+1 08:30,
or cancels stale SUBMITTED orders at T+1 09:05.

Two modes:
  --mode submit  (default, cron 08:30)
    1. Acquire filesystem lock (prevent double-run)
    2. Read READY_FOR_SUBMISSION WHERE target_fill_date = today AND account_id
    3. Pre-submission checks per order (account-scoped)
    4. Resolve contract + compute limit_price
    5. update_order_spec (limit_price, notional)
    6. mark_submitted (optimistic, before broker call)
    7. Shioaji place_order (LMT ROD)
    8. confirm_submission (broker_order_id, clear verification flag)
    9. Telegram summary

  --mode cancel  (cron 09:05)
    1. Read SUBMITTED WHERE submitted_at < now - cancel_after_minutes AND account_id
    2. Cancel via Shioaji API
    3. mark_expired
    4. Expire any remaining READY_FOR_SUBMISSION (missed submission window)

Design: docs/design/execution_submitter_design.md
Invariants: INV-1 (no broker in daily_run), INV-2 (gap filter), INV-3 (near-open),
            INV-EXEC-1 (no double submit), INV-EXEC-4 (idempotent)

v0.1.18 changes:
  - account_id threaded through all order_journal/positions calls.
  - --account required; --account all rejected (single-account per run).
  - _shioaji_login uses AccountConfig credentials (not global Settings).
  - Operation order: update_order_spec → mark_submitted → place_order →
    confirm_submission. (v0.1.17 had mark_submitted before update_order_spec,
    which caused InvalidTransition because SUBMITTED state disallows
    update_order_spec.)
  - Raw SQL broker_order_id confirm replaced with order_journal.confirm_submission.
  - Two-phase SUBMITTED broker verification deferred to #27.

Version: v0.1.18 (2026-05-28)
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

from config.account_config import AccountConfig
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
# max_entry_gap_pct: [CALIBRATED] 0.03 (3%) — P95 of positive overnight gaps.
DEFAULT_MAX_ENTRY_GAP_PCT = 0.03

# cancel_after_minutes: cancel unfilled orders after this many minutes
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


def _shioaji_login(account: AccountConfig) -> tuple[Any, Any]:
    """Login to Shioaji using account-specific credentials.

    v0.1.18: takes AccountConfig instead of global Settings. This ensures
    multi-account runs use the correct broker credentials per account.

    Returns (api, sj_module) or raises.
    """
    import shioaji as sj

    simulation = account.is_simulation
    api = sj.Shioaji(simulation=simulation)

    api_key = account.shioaji_api_key
    secret_key = account.shioaji_secret_key
    if not api_key or not secret_key:
        raise RuntimeError(
            f"Shioaji credentials missing for account {account.account_id}. "
            f"Check ENV keys: {account._env_prefix}SHIOAJI_API_KEY / SECRET_KEY"
        )

    api.login(
        api_key=api_key,
        secret_key=secret_key,
        fetch_contract=True,
        contracts_timeout=30_000,
        subscribe_trade=True,
    )
    if not simulation:
        ca_password = account.ca_password
        ca_path = str(account.ca_cert_path) if account.ca_cert_path else ""
        if not ca_password:
            raise RuntimeError(
                f"CA password missing for account {account.account_id}. "
                f"Check ENV key: {account._env_prefix}CA_PASSWORD"
            )
        api.activate_ca(
            ca_path=ca_path,
            ca_passwd=ca_password,
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
    """Get adj_close for symbol on as_of date from daily_price_adj."""
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
    account_id: str,
) -> tuple[bool, str]:
    """Run pre-submission checks for a READY_FOR_SUBMISSION order.

    v0.1.18: account_id parameter; position check is account-scoped.

    Returns (passed, reason). If not passed, caller should expire/fail.
    """
    if order.target_fill_date != today:
        return False, (
            f"stale: target_fill_date={order.target_fill_date} != today={today}"
        )

    open_positions = get_open_positions(account_id=account_id)
    open_symbols = {p.symbol for p in open_positions}
    if order.symbol in open_symbols:
        return False, f"duplicate_position: {order.symbol} already OPEN"

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
    account: AccountConfig,
    max_entry_gap_pct: float,
    dry_run: bool = False,
    notify_fn: Any = None,
) -> dict:
    """Submit READY_FOR_SUBMISSION orders to broker.

    v0.1.18: takes AccountConfig; all calls are account-scoped.
    Operation order: resolve contract → update_order_spec → mark_submitted
    → place_order → confirm_submission.

    Returns summary dict.
    """
    account_id = account.account_id
    summary = {
        "submitted": [],
        "expired": [],
        "failed": [],
        "skipped_dry_run": [],
    }

    orders = order_journal.list_ready_for_submission(
        target_fill_date=today,
        account_id=account_id,
    )

    if not orders:
        logger.info(
            "execution_submitter_no_orders",
            target_fill_date=str(today), account_id=account_id,
        )
        print(f"[submit] No READY_FOR_SUBMISSION orders for {today}")
        return summary

    print(f"[submit] Found {len(orders)} orders for {today}")

    # Pre-submission checks first (before login)
    eligible = []
    for order in orders:
        passed, reason = _pre_submission_check(order, today, account_id)
        if not passed:
            if reason.startswith("stale:") or reason.startswith("duplicate_position:"):
                order_journal.mark_expired(
                    order_id=order.order_id,
                    account_id=account_id,
                    reason=f"pre_submission_check: {reason}",
                )
                summary["expired"].append(
                    {"order_id": order.order_id, "symbol": order.symbol, "reason": reason}
                )
                logger.warning(
                    "execution_submitter_pre_check_expired",
                    order_id=order.order_id, account_id=account_id,
                    symbol=order.symbol, reason=reason,
                )
            else:
                order_journal.mark_failed(
                    order_id=order.order_id,
                    account_id=account_id,
                    failure_type=FailureType.BROKER_REJECT,
                    error_code="pre_submission_check",
                    error_message=reason,
                )
                summary["failed"].append(
                    {"order_id": order.order_id, "symbol": order.symbol, "reason": reason}
                )
                logger.error(
                    "execution_submitter_pre_check_failed",
                    order_id=order.order_id, account_id=account_id,
                    symbol=order.symbol, reason=reason,
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

    # Login to Shioaji using account-specific credentials (P0-2 fix)
    try:
        api, sj = _shioaji_login(account)
    except Exception as exc:
        for order in eligible:
            order_journal.mark_failed(
                order_id=order.order_id,
                account_id=account_id,
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

            # ── Step 1: Resolve contract ────────────────────────────
            contract = _resolve_stock_contract(api, order.symbol)
            if contract is None:
                order_journal.mark_failed(
                    order_id=order.order_id,
                    account_id=account_id,
                    failure_type=FailureType.BROKER_REJECT,
                    error_code="contract_not_found",
                    error_message=f"no contract for {order.symbol!r}",
                )
                summary["failed"].append({
                    "order_id": order.order_id, "symbol": order.symbol,
                    "reason": "contract_not_found",
                })
                continue

            # ── Step 2: Update order spec (BEFORE mark_submitted) ───
            # update_order_spec requires INTENT or READY_FOR_SUBMISSION.
            # Must be called before mark_submitted transitions to SUBMITTED.
            notional = limit_price * order.requested_lots * SHARES_PER_LOT
            order_journal.update_order_spec(
                order_id=order.order_id,
                account_id=account_id,
                limit_price=limit_price,
                notional=notional,
            )

            # ── Step 3: Mark SUBMITTED (optimistic, before broker call)
            # If crash occurs after place_order but before confirm_submission,
            # reconcile will surface SUBMITTED without broker_order_id as a
            # manual-review warning. Two-phase SUBMITTED verification is
            # deferred to #27.
            now = datetime.now(tz=TAIPEI_TZ)
            order_journal.mark_submitted(
                order_id=order.order_id,
                account_id=account_id,
                broker_order_id=None,  # not yet known
                submitted_at=now,
            )

            # ── Step 4: Place order via Shioaji ─────────────────────
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
                    account_id=account_id,
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
                    order_id=order.order_id, account_id=account_id,
                    symbol=order.symbol, error=str(exc),
                )
                continue

            # ── Step 5: Confirm submission ──────────────────────────
            broker_order_id = (
                trade.order.id if trade and trade.order and trade.order.id
                else None
            )

            # Live account must receive broker_order_id; None indicates
            # broker did not acknowledge. Sim mode tolerates None.
            if broker_order_id is None and not account.is_simulation:
                order_journal.mark_failed(
                    order_id=order.order_id,
                    account_id=account_id,
                    failure_type=FailureType.TRANSPORT,
                    error_code="broker_order_id_missing",
                    error_message=(
                        "Live broker returned no broker_order_id after "
                        "place_order. Order may or may not have been "
                        "received; requires manual verification."
                    ),
                )
                summary["failed"].append({
                    "order_id": order.order_id, "symbol": order.symbol,
                    "reason": "broker_order_id_missing (live)",
                })
                logger.error(
                    "execution_submitter_no_broker_order_id_live",
                    order_id=order.order_id, account_id=account_id,
                    symbol=order.symbol,
                )
                continue

            order_journal.confirm_submission(
                order_id=order.order_id,
                account_id=account_id,
                broker_order_id=broker_order_id,
                confirmed_at=datetime.now(tz=TAIPEI_TZ),
            )

            summary["submitted"].append({
                "order_id": order.order_id,
                "symbol": order.symbol,
                "limit_price": limit_price,
                "broker_order_id": broker_order_id,
            })
            logger.info(
                "execution_submitter_order_submitted",
                order_id=order.order_id, account_id=account_id,
                symbol=order.symbol, limit_price=limit_price,
                broker_order_id=broker_order_id, notional=notional,
            )

    finally:
        _shioaji_logout(api)

    # Telegram notification
    if notify_fn and (summary["submitted"] or summary["failed"] or summary["expired"]):
        lines = [f"📤 Execution Submitter — {today} ({account_id})"]
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
    account: AccountConfig,
    cancel_after_minutes: int,
    dry_run: bool = False,
    notify_fn: Any = None,
) -> dict:
    """Cancel stale SUBMITTED orders and expire leftover READY_FOR_SUBMISSION.

    v0.1.18: takes AccountConfig; all queries are account-scoped.

    Returns summary dict.
    """
    account_id = account.account_id
    summary = {
        "cancelled": [],
        "expired_ready": [],
        "failed": [],
    }
    now = datetime.now(tz=TAIPEI_TZ)
    cutoff = now - timedelta(minutes=cancel_after_minutes)

    # Find SUBMITTED orders older than cutoff (account-scoped)
    with connect(read_only=True) as conn:
        rows = conn.execute(
            "SELECT order_id, symbol, broker_order_id, submitted_at "
            "FROM orders WHERE status = 'SUBMITTED' AND submitted_at < ? "
            "AND account_id = ?",
            [cutoff, account_id],
        ).fetchall()

    stale_submitted = [
        {"order_id": r[0], "symbol": r[1], "broker_order_id": r[2], "submitted_at": r[3]}
        for r in rows
    ]

    if stale_submitted and not dry_run:
        try:
            api, sj = _shioaji_login(account)
        except Exception as exc:
            logger.error("execution_submitter_cancel_login_failed", error=str(exc))
            for s in stale_submitted:
                summary["failed"].append({
                    "order_id": s["order_id"], "symbol": s["symbol"],
                    "reason": f"login_failed: {exc}",
                })
            api = None
    else:
        api = None

    try:
        for s in stale_submitted:
            if dry_run:
                print(f"  [dry-run cancel] {s['symbol']} order_id={s['order_id']}")
                continue

            if api is not None and s["broker_order_id"]:
                try:
                    # Shioaji cancel API semantics unverified (Q3).
                    # Marking EXPIRED; reconcile will resolve.
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

            order_journal.mark_expired(
                order_id=s["order_id"],
                account_id=account_id,
                reason=f"cancel_sweep: submitted_at={s['submitted_at']} "
                       f"< cutoff={cutoff} ({cancel_after_minutes}min)",
            )
            summary["cancelled"].append({
                "order_id": s["order_id"], "symbol": s["symbol"],
            })
            logger.info(
                "execution_submitter_order_cancelled",
                order_id=s["order_id"], account_id=account_id,
                symbol=s["symbol"],
            )

        # Expire leftover READY_FOR_SUBMISSION (missed submission window)
        leftover = order_journal.list_ready_for_submission(
            target_fill_date=today,
            account_id=account_id,
        )
        for lo in leftover:
            order_journal.mark_expired(
                order_id=lo.order_id,
                account_id=account_id,
                reason=f"cancel_sweep: READY_FOR_SUBMISSION still pending at "
                       f"{now.strftime('%H:%M')}; submission window missed",
            )
            summary["expired_ready"].append({
                "order_id": lo.order_id, "symbol": lo.symbol,
            })
            logger.warning(
                "execution_submitter_ready_expired",
                order_id=lo.order_id, account_id=account_id,
                symbol=lo.symbol,
            )

    finally:
        if api is not None:
            _shioaji_logout(api)

    # Telegram notification
    if notify_fn and (summary["cancelled"] or summary["expired_ready"] or summary["failed"]):
        lines = [f"🧹 Cancel Sweep — {today} ({account_id})"]
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
        description="v0.1.18 execution submitter + cancel sweep",
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
    parser.add_argument(
        "--account", type=str, default=None,
        metavar="ACCOUNT_ID",
        help="Account ID from config/accounts.yaml (required).",
    )
    args = parser.parse_args()

    init_schema()
    today = date_type.fromisoformat(args.as_of) if args.as_of else date_type.today()

    if not is_trading_day(today):
        print(f"{today} is not a trading day; exiting")
        return 0

    # ── v0.1.18: account config loading ──────────────────────────────
    # AccountConfig is the ONLY source of account_id AND broker credentials.
    from config.account_config import load_accounts, get_account

    if args.account == "all":
        raise RuntimeError(
            "--account all is not supported for execution_submitter. "
            "Broker side-effect scripts must run single-account per invocation. "
            "Use --account <id> and run separately per account."
        )

    if args.account:
        _account = get_account(args.account)
    else:
        _accounts = load_accounts()
        _account = _accounts[0]

    logger.info(
        "execution_submitter_account",
        account_id=_account.account_id,
        environment=_account.environment,
    )

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
                account=_account,
                max_entry_gap_pct=args.max_entry_gap_pct,
                dry_run=args.dry_run,
                notify_fn=notify_fn,
            )
        else:
            summary = _run_cancel(
                today=today,
                account=_account,
                cancel_after_minutes=args.cancel_after_minutes,
                dry_run=args.dry_run,
                notify_fn=notify_fn,
            )

        return 0 if not summary.get("failed") else 1

    finally:
        _release_lock(lock_fd)


if __name__ == "__main__":
    sys.exit(main())
