#!/usr/bin/env python3
# scripts/daily_run.py
"""Daily run orchestration — v0.1.14.3. Orchestration ONLY (no business logic).

Pipeline: prev-check → is_trading_day → T+1 readiness → freshness → expire →
exits → entries → listener → reconcile. Each step = single module call.

c3: step reorder (calendar before data); PreflightDecline (no marker overwrite,
no traceback); calendar consolidated to market.trading_calendar. See CHANGELOG
for v0.1.14.3 stability instrumentation. ARCHITECTURE.md §6.5 + §9.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date as date_type
from datetime import datetime
from functools import partial

from communication.telegram import TelegramBot, TelegramConfig
from communication.telegram.sender import push_simple
from data.database import init_schema
from execution import (
    PreflightDecline,
    TransactionFees,
    check_data_freshness,
    check_previous_run,
    expiry,
    reconciliation,
    shutdown_guard,
)
from market.trading_calendar import is_trading_day, next_fillable_day
from scripts.run_exit_scan import scan_and_exit
from utils.logger import get_logger

logger = get_logger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="v0.1.14.3 daily paper-trading run")
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--capital", type=float, default=1_000_000)
    parser.add_argument("--listener-minutes", type=int, default=30)
    parser.add_argument("--no-listener", action="store_true",
                        help="skip telegram listener (CI / smoke test)")
    parser.add_argument("--ignore-prev-check", action="store_true")
    parser.add_argument(
        "--account", type=str, default=None,
        metavar="ACCOUNT_ID",
        help="Account ID from config/accounts.yaml. "
             "Default: first enabled account. "
             "Multi-account execution (--account all) requires "
             "DB account_id columns (backlog #23 v0.1.18).",
    )
    args = parser.parse_args()

    init_schema()
    as_of = date_type.fromisoformat(args.as_of) if args.as_of else date_type.today()

    # ── v0.1.17-A: account config loading ────────────────────────────
    # Scope: notification + credential routing only.
    # Live execution remains single-account until DB has account_id columns
    # (backlog #23 v0.1.18). See docs/decision_records/CHANGELOG_v0_1_16_v1_to_v2.md.
    from config.account_config import load_accounts, get_account
    if args.account and args.account != "all":
        _account = get_account(args.account)
    else:
        _accounts = load_accounts()
        # Hard gate: --account all with execution enabled is not allowed
        # until DB tables include account_id (would cause silent collision).
        if args.account == "all" and len(_accounts) > 1:
            raise RuntimeError(
                "Multi-account live execution requires account_id columns in "
                "orders/positions tables. Complete backlog #23 v0.1.18 before "
                "running --account all with execution enabled. "
                "For dry-run observation, use --account <id> per account."
            )
        _account = _accounts[0]
    logger.info(
        "daily_run_account_selected",
        account_id=_account.account_id,
        owner=_account.owner,
        environment=_account.environment,
    )

    print(f"Helios daily_run — {datetime.now().isoformat(timespec='seconds')}  as_of={as_of}")
    print(f"  account={_account.account_id} ({_account.owner}, {_account.environment})")

    # ── Telegram: account-aware routing (v0.1.17-A) ──────────────────
    _chat_id = _account.resolved_telegram_chat_id
    if _chat_id:
        from config.settings import get_settings as _get_settings_for_tg
        _tg_token = _get_settings_for_tg().telegram_bot_token
        if _tg_token:
            tg_cfg = TelegramConfig(
                bot_token=_tg_token.get_secret_value(),
                chat_id=_chat_id,
            )
            bot = TelegramBot(tg_cfg)
        else:
            bot = None
    else:
        # Fall back to legacy single-account .env config
        tg_cfg = TelegramConfig.from_env()
        bot = TelegramBot(tg_cfg) if tg_cfg else None
    telegram_notify = partial(push_simple, bot) if bot else None

    # ═══════════════════════════════════════════════════════════════════
    # Startup Recovery (pre-flight consistency restoration)
    # ═══════════════════════════════════════════════════════════════════
    # NOT a daily pipeline stage. Restores journal consistency before
    # shutdown_guard's prev_check evaluates state. Must run OUTSIDE
    # shutdown_guard because:
    #   1. shutdown_guard's prev_check assumes journal is consistent.
    #   2. Orphan INTENT orders would otherwise pollute the check.
    #
    # Wrapped in top-level try/except because shutdown_guard has not yet
    # been entered — observability must be self-contained here.
    print(f"=== Startup Recovery ===")
    from scripts.startup_recovery import recover_in_flight_orders
    from utils.trading_calendar import is_trading_day as _is_trading_day
    try:
        recovery_summary = recover_in_flight_orders(
            as_of=as_of,
            is_trading_day=_is_trading_day,
            notify=telegram_notify,
        )
        print(
            f"  orphan_intents_resolved={recovery_summary['orphan_intents_resolved']} "
            f"stale_submitted_resolved={recovery_summary['stale_submitted_resolved']} "
            f"errors={len(recovery_summary['resolution_errors'])}"
        )
    except Exception as exc:
        # Self-observability: shutdown_guard not yet active, must notify directly.
        import structlog
        structlog.get_logger(__name__).critical(
            "startup_recovery_fatal", error=str(exc), error_type=type(exc).__name__,
        )
        if telegram_notify is not None:
            try:
                telegram_notify(
                    f"🚨 STARTUP RECOVERY FATAL\n"
                    f"{type(exc).__name__}: {exc}\n"
                    f"daily_run aborted before shutdown_guard."
                )
            except Exception:
                pass
        raise

    with shutdown_guard(as_of, telegram_notify=telegram_notify) as guard:
        # ── Step 0: prev-run check ────────────────────────
        if not args.ignore_prev_check:
            ok, msg = check_previous_run(as_of)
            print(f"[0] {msg}")
            if not ok:
                raise PreflightDecline(f"prev_check_failed: {msg}")

        # ── Step 1: trading day (cheap, calendar-only) ───
        if not is_trading_day(as_of):
            print(f"[1] {as_of} not a trading day; declining")
            raise PreflightDecline(f"non_trading_day: {as_of}")
        print(f"[1] {as_of} is a trading day ✓")

        # ── Step 2: T+1 fill readiness ────────────────────
        fill_date = next_fillable_day(as_of)
        if fill_date is None:
            raise PreflightDecline(
                f"t_plus_1_fill_unavailable: as_of={as_of} "
                f"(next trading day's data not yet ingested)"
            )
        print(f"[2] T+1 fill day = {fill_date} ✓")

        # ── Step 3: data freshness (as_of itself) ─────────
        ok, msg = check_data_freshness(as_of)
        print(f"[3] {msg}")
        if not ok:
            raise PreflightDecline(f"data_freshness_failed: {msg}")

        # ── Step 4: expire stale pending ──────────────────
        n_to = expiry.expire_by_timeout()
        n_dr = expiry.expire_by_drift(as_of)
        print(f"[4] expired: timeout={n_to}, drift={len(n_dr)}")

        # ── Step 5: exit scan (auto-execute per ADR-004; T+1 fill) ──
        # v0.1.16 v2: HELIOS_SKIP_EXIT_SCAN=1 bypasses scan_and_exit because
        # paper_broker.py still writes legacy v0.1.14 schema (lowercase
        # status/side, no fill_date). v0.1.17 P1 #2 will align paper_broker
        # to v2 journal; until then, exit scan is gated behind env var.
        # See docs/design/execution_model.md §9.2.
        import os as _os
        if _os.environ.get("HELIOS_SKIP_EXIT_SCAN", "").lower() in ("1", "true", "yes"):
            print("[5] HELIOS_SKIP_EXIT_SCAN=1, skipping exit scan "
                  "(paper_broker schema mismatch; v0.1.17 will fix)")
            exit_summary = {
                "exits_fired": 0,
                "exits_failed": 0,
                "exits_failed_symbols": [],
                "skipped_no_data": 0,
                "skipped_no_data_symbols": [],
                "open_position_days": [],
                "avg_position_days": 0,
                "max_position_days": 0,
            }
        else:
            fees = TransactionFees()
            exit_summary = scan_and_exit(as_of=as_of, fill_date=fill_date, fees=fees)
            print(f"[5] exit scan: {exit_summary['exits_fired']} fired, "
                  f"{exit_summary['exits_failed']} failed")

        # ── Step 6: entry signal generation ───────────────
        from scripts.process_entries import generate_pending_signals
        pending, notional_map = generate_pending_signals(
            as_of=as_of, capital=args.capital, bot=bot,
        )
        print(f"[6] entry pipeline: {len(pending)} pending signals pushed")

        # ── Step 7: auto-execute entry signals via LiveBroker ────────────
        # v0.1.16 v2: uses OrderSubmissionResult.position_opened (NOT
        # result.success) to decide whether to count as executed.
        # SUBMITTED-but-unfilled orders go to pending_reconcile (reconcile
        # will resolve at T+1 morning). FAILED/PARTIAL/CANCELLED/EXPIRED
        # go to failed bucket.
        # sim_relaxed guard thresholds applied when shioaji_simulation=True
        # (week-1 smoke test profile; see docs/design/execution_model.md §6).
        from execution.live_broker import LiveBroker
        from execution.pre_trade_guard import PreTradeGuard
        from config.settings import get_settings

        _cfg = get_settings()
        # v0.1.17-A: use account.environment instead of global shioaji_simulation
        _is_sim = _account.is_simulation
        _guard_mode = "sim_relaxed" if _is_sim else "production"
        _guard_config = (
            PreTradeGuard.sim_relaxed() if _is_sim
            else PreTradeGuard()
        )
        logger.info(
            "daily_run_pre_trade_guard_selected",
            mode=_guard_mode,
            max_order_notional=_guard_config.max_order_notional,
            max_daily_notional=_guard_config.max_daily_notional,
        )

        exec_summary = {
            "executed": [],            # FILLED + position opened
            "pending_reconcile": [],   # SUBMITTED (awaiting fill)
            "failed": [],              # FAILED / PARTIAL / CANCELLED / EXPIRED
        }
        if pending:
            # v0.1.16 v2: process_entries.generate_pending_signals returns
            # list[str] of signal_ids (not list[dict]). Resolve symbol +
            # signal_type via storage.signals.get_signal.
            from storage.signals import get_signal as _get_signal
            broker = LiveBroker(bot=bot, guard=_guard_config)
            for signal_id in pending:
                sig_row = _get_signal(signal_id)
                if sig_row is None:
                    logger.warning(
                        "daily_run_signal_not_found",
                        signal_id=signal_id,
                    )
                    exec_summary["failed"].append(signal_id)
                    continue
                symbol = sig_row.symbol
                if not symbol:
                    logger.warning(
                        "daily_run_skip_no_symbol",
                        signal_id=signal_id,
                    )
                    exec_summary["failed"].append(signal_id)
                    continue
                # v0.1.16 v2 only auto-executes buy signals. sell/exit
                # signals come from exit scan (currently disabled via
                # HELIOS_SKIP_EXIT_SCAN; v0.1.17 will route through journal).
                if sig_row.signal_type != "buy":
                    logger.warning(
                        "daily_run_skip_non_buy_signal",
                        signal_id=signal_id,
                        signal_type=sig_row.signal_type,
                        symbol=symbol,
                    )
                    exec_summary["failed"].append(symbol)
                    continue
                result = broker.submit_buy(
                    symbol=symbol,
                    lots=1,
                    fill_date=fill_date,
                    signal_id=signal_id,
                )
                if result.position_opened:
                    exec_summary["executed"].append(symbol)
                    logger.info(
                        "daily_run_entry_executed",
                        symbol=symbol, status=result.status.value,
                        avg_fill_price=result.avg_fill_price,
                        filled_shares=result.filled_shares,
                        order_id=result.order_id,
                    )
                elif result.is_pending:
                    exec_summary["pending_reconcile"].append(symbol)
                    logger.warning(
                        "daily_run_entry_pending_reconcile",
                        symbol=symbol, status=result.status.value,
                        order_id=result.order_id,
                        broker_order_id=result.broker_order_id,
                    )
                else:
                    exec_summary["failed"].append(symbol)
                    logger.warning(
                        "daily_run_entry_failed",
                        symbol=symbol, status=result.status.value,
                        error_code=result.error_code,
                        error_message=result.error_message,
                        order_id=result.order_id,
                    )
            print(
                f"[7] executed={len(exec_summary['executed'])} "
                f"pending_reconcile={len(exec_summary['pending_reconcile'])} "
                f"failed={len(exec_summary['failed'])} "
                f"(guard={_guard_mode})"
            )
        else:
            print(f"[7] no pending signals, skip execution (guard={_guard_mode})")

        # ── Step 8: reconciliation (stub) ─────────────────
        recon = reconciliation.reconcile(as_of)
        print(f"[8] reconciliation: {'skipped' if recon.skipped else 'ran'} "
              f"({recon.skip_reason or 'OK'})")

        # ── Summary (v0.1.16 v2: + recovery + pending_reconcile + guard_mode) ──
        guard.set_summary({
            "account_id": _account.account_id,   # v0.1.17-A
            "exits": exit_summary["exits_fired"],
            "pending_pushed": len(pending),
            "executed": len(exec_summary["executed"]),
            "pending_reconcile": len(exec_summary["pending_reconcile"]),
            "failed_entries": len(exec_summary["failed"]),
            "reconciliation": "skipped" if recon.skipped else "ran",
            "recovery_orphan_intents":
                recovery_summary["orphan_intents_resolved"],
            "recovery_stale_submitted":
                recovery_summary["stale_submitted_resolved"],
            "recovery_errors":
                len(recovery_summary["resolution_errors"]),
            "guard_mode": _guard_mode,
            **{k: exit_summary[k] for k in ("exits_failed", "exits_failed_symbols",
                "skipped_no_data", "skipped_no_data_symbols", "open_position_days",
                "avg_position_days", "max_position_days")},
        })
        print("✓ daily_run complete")
        return 0



if __name__ == "__main__":
    sys.exit(main())
