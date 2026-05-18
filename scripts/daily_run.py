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
from communication.telegram.listener import listen_for_approvals
from communication.telegram.sender import push_simple
from data.database import init_schema
from execution import (
    PaperBroker,
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
    args = parser.parse_args()

    init_schema()
    as_of = date_type.fromisoformat(args.as_of) if args.as_of else date_type.today()
    print(f"Helios daily_run — {datetime.now().isoformat(timespec='seconds')}  as_of={as_of}")
    tg_cfg = TelegramConfig.from_env()
    bot = TelegramBot(tg_cfg) if tg_cfg else None
    telegram_notify = partial(push_simple, bot) if bot else None

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

        # ── Step 7: Telegram approval window ──────────────
        listener_summary = {"approved": [], "rejected": [], "polls": 0}
        if pending and bot and not args.no_listener:
            print(f"[7] listener starting ({args.listener_minutes} min, fill_date={fill_date})...")
            listener_summary = listen_for_approvals(
                bot=bot, broker=PaperBroker(fees=fees), fill_date=fill_date,
                target_notional_for=lambda s: notional_map.get(_resolve_short(s, notional_map), 0.0),
                duration_seconds=args.listener_minutes * 60,
            )
            print(f"[7] approved={len(listener_summary['approved'])} "
                  f"rejected={len(listener_summary['rejected'])}")
        else:
            print(f"[7] listener skipped ({'no_telegram' if not bot else 'no_pending_or_disabled'})")

        # ── Step 8: reconciliation (stub) ─────────────────
        recon = reconciliation.reconcile(as_of)
        print(f"[8] reconciliation: {'skipped' if recon.skipped else 'ran'} "
              f"({recon.skip_reason or 'OK'})")

        # ── Summary (v0.1.14.3: + stability fields from exit_summary) ──
        guard.set_summary({
            "exits": exit_summary["exits_fired"], "pending_pushed": len(pending),
            "approved": len(listener_summary["approved"]),
            "rejected": len(listener_summary["rejected"]),
            "reconciliation": "skipped" if recon.skipped else "ran",
            **{k: exit_summary[k] for k in ("exits_failed", "exits_failed_symbols",
                "skipped_no_data", "skipped_no_data_symbols", "open_position_days",
                "avg_position_days", "max_position_days")},
        })
        print("✓ daily_run complete")
        return 0


def _resolve_short(s: str, notional_map: dict) -> str:
    """Telegram users type prefixes — find full signal_id in our map."""
    if s in notional_map:
        return s
    for full_id in notional_map:
        if full_id.startswith(s):
            return full_id
    return ""


if __name__ == "__main__":
    sys.exit(main())
