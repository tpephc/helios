#!/usr/bin/env python3
# scripts/run_exit_scan.py
"""Daily exit scan — per ADR-004, exits auto-execute (no approval needed).

For each OPEN position:
  1. Look up today's adj_close + ATR + market regime
  2. Update running stats (max_close, min_close, last_close)
  3. Apply exit rules in priority order: RegimeExit → TrailingStop
  4. If exit fires → submit sell via PaperBroker → mark position CLOSED

ARCHITECTURE §6.5 state machine:
  OPEN → CLOSING (sell submitted) → CLOSED (paper: same step, instant)
  Per ADR-001: synchronous, no async, no streaming.

Usage:
  uv run python scripts/run_exit_scan.py                    # today
  uv run python scripts/run_exit_scan.py --as-of 2026-05-15 # specific date

Version: v0.1.0 (2026-05-17)
"""
from __future__ import annotations

import argparse
import sys
from datetime import date as date_type
from datetime import datetime

from data.database import connect, init_schema
from execution.lifecycle import close_position_for_exit
from execution.paper_broker import DEFAULT_TW_FEES, PaperBroker, TransactionFees
from storage import positions as pos_store
from storage.positions import (
    Position,
    get_open_positions,
    update_running_stats,
)
from strategies.exit.base import Position as RuleInputPosition
from strategies.exit.regime_exit import RegimeExit
from strategies.exit.trailing_stop import TrailingStop
from utils.logger import get_logger

logger = get_logger(__name__)


EXIT_RULES = sorted(
    [RegimeExit(), TrailingStop()],
    key=lambda r: r.priority,
)


def _to_rule_input(pos: Position) -> RuleInputPosition:
    """Adapter: storage Position → strategies.exit.base.Position interface."""
    p = RuleInputPosition(
        stock_id=pos.symbol,
        entry_date=pos.entry_date,
        entry_price=pos.entry_price,
        entry_atr=pos.entry_atr,
        regime_at_entry=pos.regime_at_entry,
        strategy=pos.strategy,
        score=0.0,  # not needed by exit rules
    )
    # Hydrate running stats
    if pos.max_close_since_entry is not None:
        p.max_close_since_entry = pos.max_close_since_entry
        p.max_close_date = pos.max_close_date
    if pos.min_close_since_entry is not None:
        p.min_close_since_entry = pos.min_close_since_entry
        p.min_close_date = pos.min_close_date
    return p


def _lookup_today(symbol: str, as_of: date_type) -> tuple[float, float, str] | None:
    """Return (close, atr_14, regime) for symbol on as_of, or None if missing."""
    with connect(read_only=True) as conn:
        price_row = conn.execute(
            "SELECT adj_close FROM daily_price_adj WHERE stock_id = ? AND date = ?",
            [symbol, as_of],
        ).fetchone()
        if not price_row or price_row[0] is None:
            return None
        atr_row = conn.execute(
            "SELECT atr_14 FROM daily_features WHERE stock_id = ? AND date = ?",
            [symbol, as_of],
        ).fetchone()
        regime_row = conn.execute(
            "SELECT regime FROM market_regime WHERE date = ?",
            [as_of],
        ).fetchone()
    if not atr_row or atr_row[0] is None:
        return None
    if not regime_row:
        return None
    return float(price_row[0]), float(atr_row[0]), str(regime_row[0])


def scan_and_exit(
    as_of: date_type,
    fill_date: date_type | None = None,
    fees: TransactionFees | None = None,
) -> dict:
    """Execute exit scan for one trading day.

    Decision date is `as_of` (day-T close used for rule evaluation + running
    stats update). Fill date is `fill_date` (T+1 fill day per v0.1.14.2-c
    P0-2; under v0.1.14.3 this fills at adj_open[fill_date], not adj_close).
    If `fill_date` is None, falls back to `as_of` (legacy / unit-test
    convenience).

    Closure goes through `execution.lifecycle.close_position_for_exit` so the
    broker+storage write is the SAME code path that v0.1.15 will swap for live
    Shioaji (P1-7).

    v0.1.14.3 — summary now includes stability-instrumentation counters:
      - open_position_days: list of {position_id, symbol, age_days} for every
        OPEN position scanned. Lets the 5-day rollup surface stuck-OPEN cases.
      - exits_failed_symbols: list of symbols whose exit fired this run but
        failed at fill time (paper_broker returned success=False). Cross-run
        aggregation in run_summary.py detects "same symbol failing N days
        in a row" — a stability scar that wouldn't show in a single-day run.
      - skipped_no_data_symbols: symbols where today's data wasn't available
        (atr or regime missing). Mirror of skipped_no_data count.

    v0.1.14.3.1 — derived aggregates:
      - avg_position_days / max_position_days (computed from open_position_days)
        for the rollup's holding-time pathologies surface.

    No state-machine changes — counters are observation only.

    Returns summary dict for logging / reporting.
    """
    fees = fees if fees is not None else DEFAULT_TW_FEES
    broker = PaperBroker(fees=fees)
    open_positions = get_open_positions()
    # Exclude synthetic bootstrap positions from execution workflow.
    # Synthetic positions are for monitoring/alert testing only.
    open_positions = [p for p in open_positions
                      if getattr(p, 'is_synthetic', None) is not True
                      and p.strategy != 'dev_bootstrap']
    fill_date = fill_date or as_of
    summary = {
        "as_of": str(as_of),
        "fill_date": str(fill_date),
        "open_positions_scanned": len(open_positions),
        "updated_stats": 0,
        "exits_fired": 0,
        "exits_failed": 0,
        "skipped_no_data": 0,
        "exits": [],
        # v0.1.14.3 stability instrumentation
        "open_position_days": [],
        "exits_failed_symbols": [],
        "skipped_no_data_symbols": [],
    }

    for pos in open_positions:
        if pos.status != "OPEN":
            continue

        # v0.1.14.3: report every OPEN position's age — surface stuck positions.
        age_days = (as_of - pos.entry_date).days if pos.entry_date else None
        summary["open_position_days"].append({
            "position_id": pos.position_id,
            "symbol": pos.symbol,
            "age_days": age_days,
        })

        lookup = _lookup_today(pos.symbol, as_of)
        if lookup is None:
            logger.warning(
                "exit_scan_no_data",
                position_id=pos.position_id, symbol=pos.symbol, as_of=str(as_of),
            )
            summary["skipped_no_data"] += 1
            summary["skipped_no_data_symbols"].append(pos.symbol)
            continue
        close, atr, regime = lookup

        # 1. Update running stats using day-T close
        update_running_stats(pos.position_id, close=close, as_of=as_of)
        summary["updated_stats"] += 1

        # 2. Apply exit rules with fresh state
        rule_input = _to_rule_input(pos)
        if rule_input.max_close_since_entry is None or close > rule_input.max_close_since_entry:
            rule_input.max_close_since_entry = close
            rule_input.max_close_date = as_of

        for rule in EXIT_RULES:
            decision = rule.check(rule_input, as_of, close, atr, regime)
            if not decision.should_exit:
                continue

            # 3. P1-7: delegate closure to lifecycle (single source of truth)
            ok = close_position_for_exit(
                position_id=pos.position_id,
                exit_date=fill_date,
                exit_reason=decision.reason or rule.name,
                regime_at_exit=regime,
                broker=broker,
            )
            if not ok:
                summary["exits_failed"] += 1
                summary["exits_failed_symbols"].append(pos.symbol)
                break

            # Re-read closed position to report exit details
            closed = pos_store.get_position(pos.position_id)
            summary["exits_fired"] += 1
            summary["exits"].append({
                "position_id": pos.position_id,
                "symbol": pos.symbol,
                "exit_reason": decision.reason or rule.name,
                "exit_price": closed.exit_price if closed else None,
                "shares": pos.shares,
                "proceeds": closed.exit_proceeds if closed else None,
                "gross_return_pct": (
                    closed.gross_return_pct if closed and closed.gross_return_pct is not None else 0.0
                ),
            })
            break  # first triggering rule wins

    # v0.1.14.3.1: derived holding-time aggregates for the rollup. Avg/max
    # surface "stuck OPEN" patterns that the per-position list alone hides
    # (e.g. one outlier holding 60 days while everything else is 5).
    ages = [d["age_days"] for d in summary["open_position_days"]
            if d["age_days"] is not None]
    summary["avg_position_days"] = sum(ages) / len(ages) if ages else None
    summary["max_position_days"] = max(ages) if ages else None

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="v0.1.14.2 daily exit scan")
    parser.add_argument(
        "--as-of", type=str, default=None,
        help="trading date (YYYY-MM-DD); default = today",
    )
    parser.add_argument(
        "--fill-date", type=str, default=None,
        help="override T+1 fill date (default: next_trading_day(as-of))",
    )
    parser.add_argument(
        "--slippage", type=float, default=None,
        help="override slippage rate (default 0.001 = 0.1%%)",
    )
    args = parser.parse_args()

    init_schema()

    as_of = (
        date_type.fromisoformat(args.as_of) if args.as_of
        else date_type.today()
    )
    fees = (
        TransactionFees(slippage_rate=args.slippage) if args.slippage is not None
        else None
    )

    print(f"Helios run_exit_scan — {datetime.now().isoformat(timespec='seconds')}")
    print(f"As-of date: {as_of}")

    # P0-2 (c3): derive T+1 fill date unless explicit override; needs data ingested
    from market.trading_calendar import next_fillable_day
    fill_date = (
        date_type.fromisoformat(args.fill_date) if args.fill_date
        else (next_fillable_day(as_of) or as_of)
    )
    print(f"Fill date:  {fill_date} ({'T+1 proxy' if fill_date != as_of else 'T-close fallback'})")
    print()

    summary = scan_and_exit(as_of=as_of, fill_date=fill_date, fees=fees)

    print(f"Open positions scanned: {summary['open_positions_scanned']}")
    print(f"Running-stats updates:  {summary['updated_stats']}")
    print(f"Exits fired:            {summary['exits_fired']}")
    print(f"Exits failed:           {summary['exits_failed']}")
    print(f"Skipped (no data):      {summary['skipped_no_data']}")

    if summary["exits"]:
        print("\n--- Exits this run ---")
        for e in summary["exits"]:
            px = e['exit_price'] if e['exit_price'] is not None else 0.0
            pr = e['proceeds'] if e['proceeds'] is not None else 0.0
            print(
                f"  {e['symbol']:<8s}  {e['exit_reason']:<25s}  "
                f"px {px:>8.2f}  "
                f"return {e['gross_return_pct']:+.2f}%  "
                f"proceeds NTD {pr:>12,.0f}"
            )

    print("\n✓ exit scan complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
