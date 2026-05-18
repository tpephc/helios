#!/usr/bin/env python3
# scripts/dev_push_signal.py
"""Development-only fake signal injection — v0.1.14.3.3.

Push a fake PENDING signal into the system and (optionally) run a listener
loop, exercising the full operator-interaction path:

    push → Telegram → /approve|/reject → PaperBroker fill → DB state change

WITHOUT requiring the real strategy pipeline to actually produce a signal.

Why this exists
---------------
The 5-day paper-trade observation window starts with quiet days (no signals,
no positions). To observe approval / listener / fill / lifecycle semantics
under real Telegram conditions, the operator needs to inject signals
manually rather than wait for the strategy to fire.

The script lives outside `daily_run` deliberately. Production code paths
(daily_run, process_entries, approvals, lifecycle) carry NO `if DEV_MODE`
branches. A dev-injected signal is structurally indistinguishable from a
real one EXCEPT for two filterable markers:

    signal_id   prefix `DEV-` (e.g. `DEV-TEST-001`)
    strategy    "dev_injected"
    reason      ["dev_test"]
    metadata    {"dev_test": true, ...}

Any of these can be used to grep dev signals out of logs / markers / scars.

Marker/history isolation
------------------------
This script does NOT wrap itself in `shutdown_guard`. The dev run does not
write to MARKER_PATH or HISTORY_PATH and so does not pollute the 5-day
observation ledger. The signal itself IS persisted in the `signals` DB
table and visible to `run_summary`'s signal_flow query — sufficient audit
trail without confusing the daily_run-level operational journal.

Usage
-----
    # Push + listen (default 10 min, requires TELEGRAM_*_TOKEN in env)
    uv run python scripts/dev_push_signal.py --ticker 2330 --price 950

    # Same, but bootstrap synthetic fill data so broker fill succeeds
    # before today's EOD sync has run (v0.1.14.3.8):
    uv run python scripts/dev_push_signal.py --ticker 2330 --price 950 \\
        --bootstrap-price

    # Push only — useful to test TIMEOUT path
    uv run python scripts/dev_push_signal.py --ticker 2330 --no-listener

    # Custom id (re-runnable for the same scenario)
    uv run python scripts/dev_push_signal.py --signal-id DEV-LATE-001 \\
        --listener-minutes 1

Operator flow:
    1. Run script → Telegram receives push
    2. On phone: reply 「同意」 (or /approve DEV-TEST-NNN)
    3. Script's listener processes the response, broker fills, position opens
    4. Script prints final approval_status and exits

Version: v0.1.1 (2026-05-18 — v0.1.14.3.8 --bootstrap-price)
"""
from __future__ import annotations

import argparse
import sys
from datetime import date as date_type
from datetime import datetime

from communication.telegram import TelegramBot, TelegramConfig
from communication.telegram.listener import listen_for_approvals
from communication.telegram.sender import push_entry_request
from data.database import init_schema
from execution.paper_broker import DEFAULT_TW_FEES, PaperBroker
from market.trading_calendar import next_fillable_day
from portfolio.risk_budget import DEFAULT_RISK_BUDGET
from storage.signals import get_signal, save_signal
from utils.logger import get_logger

logger = get_logger(__name__)


def next_dev_signal_id(prefix: str = "DEV-TEST-") -> str:
    """Find next available DEV-TEST-NNN identifier.

    Scans existing signals with the given prefix and returns the next
    sequential integer (zero-padded to 3 digits). If no DEV signals exist
    yet, starts at `<prefix>001`.

    Pure function over DB state — also called from the test that pins this
    behavior, so the increment logic is testable without running the
    full script.
    """
    from data.database import connect
    with connect(read_only=True) as conn:
        rows = conn.execute(
            "SELECT signal_id FROM signals WHERE signal_id LIKE ? "
            "ORDER BY signal_id DESC LIMIT 1",
            [f"{prefix}%"],
        ).fetchone()
    if not rows:
        return f"{prefix}001"
    last = rows[0]
    try:
        n = int(last.removeprefix(prefix))
    except ValueError:
        # Existing entry didn't follow the NNN pattern; fall back to 001
        # and let the PK collision (if any) surface as a real error.
        n = 0
    return f"{prefix}{n + 1:03d}"


def _bootstrap_price_row(
    symbol: str,
    fill_date: date_type,
    price: float,
    volume: int,
) -> None:
    """[DEV ONLY] Inject a synthetic daily_price_adj row so PaperBroker
    can fill before today's EOD sync has been pushed to the DB.

    Uses INSERT OR REPLACE — idempotent, and the next real EOD sync will
    overwrite with actual market data. Intended exclusively for
    `dev_push_signal --bootstrap-price`; never called from production paths.

    Why adj_open == adj_close == price: the signal price is the closest
    proxy to "what the broker would fill at" for intraday dev testing.
    Drift against itself is 0, so the approval drift gate also passes.

    v0.1.14.3.8: added to unblock dev testing before EOD sync runs.
    Previously, the operator had to either wait until FinMind published
    that day's data or inject the row manually.
    """
    from data.database import connect
    with connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO daily_price_adj
              (stock_id, date, adj_open, adj_high, adj_low, adj_close,
               raw_close, cum_factor, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1.0, ?)
            """,
            [symbol, fill_date, price, price, price, price, price, volume],
        )
    print(
        f"[DEV] ⚠️  已注入合成價格: {symbol} @ {fill_date} "
        f"adj_open={price:.1f} volume={volume:,} "
        f"— EOD sync 後會被真實資料覆蓋"
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="v0.1.14.3.8 dev signal injection")
    p.add_argument("--ticker", default="2330",
                   help="symbol to inject (default 2330)")
    p.add_argument("--price", type=float, default=950.0,
                   help="signal price (default 950.0)")
    p.add_argument("--atr", type=float, default=20.0,
                   help="entry_atr for drift gate sizing (default 20.0)")
    p.add_argument("--target-notional", type=float, default=50_000.0,
                   help="NTD to deploy on fill (default 50_000)")
    p.add_argument("--signal-id", default=None,
                   help="custom signal_id; auto-assigned DEV-TEST-NNN if omitted")
    p.add_argument("--prefix", default="DEV-TEST-",
                   help="namespace prefix for auto-assigned ids (default DEV-TEST-)")
    p.add_argument("--listener-minutes", type=int, default=10,
                   help="approve/reject wait window in minutes (default 10)")
    p.add_argument("--no-listener", action="store_true",
                   help="push only, don't wait (useful for testing TIMEOUT path)")
    p.add_argument(
        "--bootstrap-price", action="store_true",
        help=(
            "[DEV] push 前注入合成 daily_price_adj 給 (ticker, fill_date)。"
            "讓 broker fill 在 EOD sync 之前可以通過 adj_open + volume 兩個 gate。"
            "INSERT OR REPLACE — EOD sync 後自動被真實資料覆蓋。"
        ),
    )
    p.add_argument(
        "--bootstrap-volume", type=int, default=25_000_000,
        help="--bootstrap-price 的合成 volume (股)，預設 25,000,000",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    init_schema()
    as_of = date_type.today()
    fill_date = next_fillable_day(as_of) or as_of
    sid = args.signal_id or next_dev_signal_id(args.prefix)

    # [DEV] v0.1.14.3.8: bootstrap synthetic price data before pushing,
    # so the broker fill passes even before today's EOD sync has run.
    if args.bootstrap_price:
        _bootstrap_price_row(args.ticker, fill_date, args.price, args.bootstrap_volume)

    print(
        f"Helios dev_push_signal — {datetime.now().isoformat(timespec='seconds')}  "
        f"signal_id={sid}"
    )

    # 0. Telegram bot must be configured (the whole point is real-Telegram path)
    tg_cfg = TelegramConfig.from_env()
    bot = TelegramBot(tg_cfg) if tg_cfg else None
    if bot is None:
        print(
            "ERROR: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not configured. "
            "Set both in env (.env) before running dev_push_signal.py — "
            "the whole point is exercising the real-Telegram path.",
            file=sys.stderr,
        )
        return 1

    # 1. Save PENDING signal with DEV- prefix
    save_signal(
        symbol=args.ticker, strategy="dev_injected", signal_type="buy",
        score=0.99, price=args.price, reason=["dev_test"],
        signal_date=as_of, entry_atr=args.atr, regime="bull",
        timeout_minutes=args.listener_minutes,
        signal_id=sid,
        metadata={"dev_test": True, "target_notional": args.target_notional},
    )
    print(f"[1] saved PENDING signal {sid}  (timeout {args.listener_minutes} min)")

    # 2. Push via Telegram (same path as production process_entries)
    sig_row = get_signal(sid)
    if sig_row is None:
        print(f"ERROR: failed to read back signal {sid} after save", file=sys.stderr)
        return 2
    msg_id = push_entry_request(
        bot, sig_row,
        target_notional=args.target_notional,
        cash=1_000_000, equity=1_000_000,
        sector_value=0.0, etf_value=0.0, pos_value=0.0,
        budget=DEFAULT_RISK_BUDGET,
    )
    if msg_id is None:
        print(f"ERROR: Telegram push failed for {sid}", file=sys.stderr)
        return 3
    print(f"[2] pushed to Telegram (msg_id={msg_id})")

    # 3. (optional) Listen until signal transitions out of PENDING
    if args.no_listener:
        print(
            f"[3] listener skipped — {sid} will TIMEOUT in {args.listener_minutes} min "
            f"if not approved/rejected externally"
        )
        return 0

    print(
        f"[3] listening for {args.listener_minutes} min — "
        f"send `/approve {sid}` or `/reject {sid}` via Telegram"
    )
    listener_summary = listen_for_approvals(
        bot=bot, broker=PaperBroker(fees=DEFAULT_TW_FEES), fill_date=fill_date,
        # Single-signal dev mode: any sig_ref resolves to the same notional.
        target_notional_for=lambda _ref: args.target_notional,
        duration_seconds=args.listener_minutes * 60,
    )
    print(
        f"[3] listener returned: approved={len(listener_summary['approved'])} "
        f"rejected={len(listener_summary['rejected'])} "
        f"polls={listener_summary.get('polls', '?')}"
    )

    # 4. Final state report
    final = get_signal(sid)
    final_status = final.approval_status if final else "NOT_FOUND"
    print(f"[4] final approval_status: {final_status}")
    logger.info(
        "dev_push_signal_complete",
        signal_id=sid, final_status=final_status,
        approved=len(listener_summary["approved"]),
        rejected=len(listener_summary["rejected"]),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
