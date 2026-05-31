#!/usr/bin/env python3
# scripts/run_exit_scan.py
"""Daily exit scan — per ADR-004, exits auto-execute (no approval needed).

For each OPEN position:
  1. Compute holding_trading_days (does not require today's price)
  2. Look up today's adj_close + ATR + market regime
  3. Update running stats (max_close, min_close, last_close)
  4. Apply exit rules in priority order: RegimeExit -> TrailingStop -> TimeStop
  5. If exit fires -> submit sell via PaperBroker -> mark position CLOSED

Forced exit (P0 invariant):
  If today's price data is unavailable (halt / missing) BUT
  holding_trading_days >= 20, TimeStop fires as a forced exit
  using last available adj_close.  This prevents halted stocks
  from silently bypassing the max holding period.

Exit metadata audit:
  Every exit (normal or forced) writes a row to exit_audit table
  with the full rule metadata (stop_price, max_close, entry_atr,
  holding_trading_days, etc.) for strategy gate audit.

Exit contract (v0.2.0, 2026-05-31):
  Priority 1  RegimeExit     regime == "bear"
  Priority 2  TrailingStop   close <= max_close - 2 * entry_atr
  Priority 3  TimeStop       holding_trading_days >= 20

ARCHITECTURE 6.5 state machine:
  OPEN -> CLOSING (sell submitted) -> CLOSED (paper: same step, instant)

Version: v0.1.18 (2026-05-28) + exit contract v0.2.0 (2026-05-31)
"""
from __future__ import annotations

import argparse
import json
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
    mark_position_closed,
    update_running_stats,
)
from strategies.exit.base import Position as RuleInputPosition
from strategies.exit.regime_exit import RegimeExit
from strategies.exit.time_stop import DEFAULT_MAX_HOLDING_DAYS, TimeStop
from strategies.exit.trailing_stop import TrailingStop
from utils.logger import get_logger

logger = get_logger(__name__)


# -----------------------------------------------------------------
# Exit rules (sorted by priority: 1=regime, 2=trailing, 3=time)
# -----------------------------------------------------------------

EXIT_RULES = sorted(
    [RegimeExit(), TrailingStop(), TimeStop()],
    key=lambda r: r.priority,
)

# Taiwan sell-side securities transaction tax (fixed by law).
_SELL_TAX_RATE = 0.003


# -----------------------------------------------------------------
# Exit audit table (self-contained; does not modify positions schema)
# -----------------------------------------------------------------

_CREATE_EXIT_AUDIT = """
CREATE TABLE IF NOT EXISTS exit_audit (
    position_id    VARCHAR PRIMARY KEY,
    account_id     VARCHAR NOT NULL,
    symbol         VARCHAR NOT NULL,
    exit_date      DATE    NOT NULL,
    exit_rule      VARCHAR NOT NULL,
    exit_reason    TEXT    NOT NULL,
    forced         BOOLEAN NOT NULL DEFAULT false,
    metadata_json  TEXT,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


def _ensure_exit_audit_table(conn) -> None:
    conn.execute(_CREATE_EXIT_AUDIT)


def _log_exit_audit(
    position_id: str,
    account_id: str,
    symbol: str,
    exit_date: date_type,
    rule_name: str,
    reason: str,
    metadata: dict | None,
    *,
    forced: bool = False,
) -> None:
    """Persist exit metadata for strategy gate audit."""
    with connect() as conn:
        _ensure_exit_audit_table(conn)
        conn.execute(
            """
            INSERT INTO exit_audit
                (position_id, account_id, symbol, exit_date,
                 exit_rule, exit_reason, forced, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (position_id) DO NOTHING
            """,
            [
                position_id, account_id, symbol, exit_date,
                rule_name, reason, forced,
                json.dumps(metadata, default=str) if metadata else None,
            ],
        )


# -----------------------------------------------------------------
# Data helpers
# -----------------------------------------------------------------


def _to_rule_input(pos: Position) -> RuleInputPosition:
    """Adapter: storage Position -> strategies.exit.base.Position interface."""
    p = RuleInputPosition(
        stock_id=pos.symbol,
        entry_date=pos.entry_date,
        entry_price=pos.entry_price,
        entry_atr=pos.entry_atr,
        regime_at_entry=pos.regime_at_entry,
        strategy=pos.strategy,
        score=0.0,
    )
    if pos.max_close_since_entry is not None:
        p.max_close_since_entry = pos.max_close_since_entry
        p.max_close_date = pos.max_close_date
    if pos.min_close_since_entry is not None:
        p.min_close_since_entry = pos.min_close_since_entry
        p.min_close_date = pos.min_close_date
    return p


def _lookup_today(
    symbol: str, as_of: date_type,
) -> tuple[float, float, str] | None:
    """Return (close, atr_14, regime) for symbol on as_of, or None if missing."""
    with connect(read_only=True) as conn:
        price_row = conn.execute(
            "SELECT adj_close FROM daily_price_adj "
            "WHERE stock_id = ? AND date = ?",
            [symbol, as_of],
        ).fetchone()
        if not price_row or price_row[0] is None:
            return None
        atr_row = conn.execute(
            "SELECT atr_14 FROM daily_features "
            "WHERE stock_id = ? AND date = ?",
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


def _count_holding_trading_days(
    entry_date: date_type, as_of: date_type,
) -> int:
    """Count market trading days strictly after entry_date through as_of.

    Uses market_regime table as the trading calendar (one row per
    trading day, more efficient than COUNT DISTINCT on daily_price_adj).
    """
    with connect(read_only=True) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM market_regime "
            "WHERE date > ? AND date <= ?",
            [entry_date, as_of],
        ).fetchone()
    return int(row[0]) if row else 0


def _get_regime(as_of: date_type) -> str | None:
    """Get market regime for as_of (market-level, independent of stock)."""
    with connect(read_only=True) as conn:
        row = conn.execute(
            "SELECT regime FROM market_regime WHERE date = ?",
            [as_of],
        ).fetchone()
    return str(row[0]) if row else None


def _get_last_available_close(
    symbol: str, on_or_before: date_type,
) -> float | None:
    """Last available adj_close for symbol on or before the given date.

    Used as exit price for forced exits when today's data is missing
    (halted / suspended stock).
    """
    with connect(read_only=True) as conn:
        row = conn.execute(
            "SELECT adj_close FROM daily_price_adj "
            "WHERE stock_id = ? AND date <= ? "
            "ORDER BY date DESC LIMIT 1",
            [symbol, on_or_before],
        ).fetchone()
    return float(row[0]) if row and row[0] else None


# -----------------------------------------------------------------
# Forced TimeStop exit (P0-1: halted stock with holding >= 20d)
# -----------------------------------------------------------------


def _forced_time_stop_exit(
    pos: Position,
    as_of: date_type,
    fill_date: date_type,
    holding_td: int,
    fees: TransactionFees,
    account_id: str,
    summary: dict,
) -> None:
    """Force-close a position via TimeStop when today's price is unavailable.

    Bypasses PaperBroker (cannot sell a halted stock) and calls
    mark_position_closed directly with last available close.
    Transaction costs applied for evidence conservatism.
    """
    last_close = _get_last_available_close(pos.symbol, as_of)
    if last_close is None:
        logger.error(
            "forced_time_stop_no_price_history",
            position_id=pos.position_id,
            symbol=pos.symbol,
            account_id=account_id,
        )
        summary["exits_failed"] += 1
        summary["exits_failed_symbols"].append(pos.symbol)
        return

    regime = _get_regime(as_of) or "unknown"

    exit_reason = (
        f"time_stop_forced (held {holding_td} trading days "
        f">= {DEFAULT_MAX_HOLDING_DAYS}, "
        f"no data on {as_of}, exit at last_close={last_close:.2f})"
    )

    # Apply full sell-side costs for evidence conservatism.
    sell_notional = pos.shares * last_close
    exit_commission = sell_notional * fees.commission_rate
    exit_tax = sell_notional * _SELL_TAX_RATE
    exit_slippage = sell_notional * fees.slippage_rate
    exit_proceeds = sell_notional - exit_commission - exit_tax - exit_slippage

    try:
        mark_position_closed(
            pos.position_id,
            account_id=account_id,
            exit_date=fill_date,
            exit_price=last_close,
            exit_reason=exit_reason,
            regime_at_exit=regime,
            exit_commission=exit_commission,
            exit_tax=exit_tax,
            exit_slippage_cost=exit_slippage,
            exit_proceeds=exit_proceeds,
        )
    except Exception as exc:
        logger.error(
            "forced_time_stop_close_failed",
            position_id=pos.position_id,
            symbol=pos.symbol,
            error=str(exc),
        )
        summary["exits_failed"] += 1
        summary["exits_failed_symbols"].append(pos.symbol)
        return

    metadata = {
        "exit_price": last_close,
        "holding_trading_days": holding_td,
        "max_holding_days": DEFAULT_MAX_HOLDING_DAYS,
        "forced": True,
        "data_missing_date": str(as_of),
        "sell_notional": sell_notional,
        "exit_commission": exit_commission,
        "exit_tax": exit_tax,
        "exit_slippage": exit_slippage,
        "exit_proceeds": exit_proceeds,
    }
    _log_exit_audit(
        pos.position_id, account_id, pos.symbol, fill_date,
        "time_stop_forced", exit_reason, metadata,
        forced=True,
    )

    summary["exits_fired"] += 1
    summary["exits"].append({
        "position_id": pos.position_id,
        "symbol": pos.symbol,
        "exit_reason": exit_reason,
        "exit_price": last_close,
        "shares": pos.shares,
        "proceeds": exit_proceeds,
        "gross_return_pct": (
            (last_close / pos.entry_price - 1.0) * 100.0
            if pos.entry_price and pos.entry_price > 0 else 0.0
        ),
        "holding_trading_days": holding_td,
        "forced": True,
    })

    logger.info(
        "forced_time_stop_exit",
        position_id=pos.position_id,
        symbol=pos.symbol,
        holding_trading_days=holding_td,
        exit_price=last_close,
        exit_proceeds=round(exit_proceeds, 0),
    )


# -----------------------------------------------------------------
# Main scan
# -----------------------------------------------------------------


def scan_and_exit(
    as_of: date_type,
    fill_date: date_type | None = None,
    fees: TransactionFees | None = None,
    *,
    account_id: str,
) -> dict:
    """Execute exit scan for one trading day.

    Args:
        as_of: decision date (day-T close for rule evaluation).
        fill_date: T+1 fill day. If None, falls back to as_of.
        fees: transaction fee config. If None, uses DEFAULT_TW_FEES.
        account_id: broker account identifier.

    Returns:
        Summary dict for logging / reporting.
    """

    fees = fees if fees is not None else DEFAULT_TW_FEES
    broker = PaperBroker(fees=fees, account_id=account_id)
    open_positions = get_open_positions(account_id=account_id)
    # Exclude synthetic bootstrap positions from execution workflow.
    open_positions = [p for p in open_positions
                      if getattr(p, 'is_synthetic', None) is not True
                      and p.strategy != 'dev_bootstrap']
    fill_date = fill_date or as_of
    summary: dict = {
        "as_of": str(as_of),
        "fill_date": str(fill_date),
        "account_id": account_id,
        "open_positions_scanned": len(open_positions),
        "updated_stats": 0,
        "exits_fired": 0,
        "exits_failed": 0,
        "skipped_no_data": 0,
        "exits": [],
        "open_position_days": [],
        "exits_failed_symbols": [],
        "skipped_no_data_symbols": [],
    }

    for pos in open_positions:
        if pos.status != "OPEN":
            continue

        age_days = (as_of - pos.entry_date).days if pos.entry_date else None
        summary["open_position_days"].append({
            "position_id": pos.position_id,
            "symbol": pos.symbol,
            "age_days": age_days,
        })

        # -- Step 1: holding duration (no price dependency) --------
        holding_td = _count_holding_trading_days(pos.entry_date, as_of)

        # -- Step 2: today's price data ----------------------------
        lookup = _lookup_today(pos.symbol, as_of)

        if lookup is None:
            # No data for this symbol today (halted / missing).
            # RegimeExit and TrailingStop need close/atr -- cannot
            # evaluate.  But TimeStop MUST still fire if holding
            # period is exceeded (P0-1: no silent dropout).
            if holding_td >= DEFAULT_MAX_HOLDING_DAYS:
                _forced_time_stop_exit(
                    pos, as_of, fill_date, holding_td,
                    fees, account_id, summary,
                )
            else:
                logger.warning(
                    "exit_scan_no_data",
                    position_id=pos.position_id,
                    symbol=pos.symbol,
                    account_id=account_id,
                    as_of=str(as_of),
                    holding_trading_days=holding_td,
                )
                summary["skipped_no_data"] += 1
                summary["skipped_no_data_symbols"].append(pos.symbol)
            continue

        close, atr, regime = lookup

        # -- Step 3: update running stats --------------------------
        update_running_stats(
            pos.position_id, close=close, as_of=as_of,
            account_id=account_id,
        )
        summary["updated_stats"] += 1

        # -- Step 4: build rule input ------------------------------
        rule_input = _to_rule_input(pos)
        if rule_input.max_close_since_entry is None or close > rule_input.max_close_since_entry:
            rule_input.max_close_since_entry = close
            rule_input.max_close_date = as_of
        rule_input.holding_trading_days = holding_td

        # -- Step 5: apply exit rules (first trigger wins) ---------
        for rule in EXIT_RULES:
            decision = rule.check(rule_input, as_of, close, atr, regime)
            if not decision.should_exit:
                continue

            # -- Step 6: close position via lifecycle --------------
            ok = close_position_for_exit(
                position_id=pos.position_id,
                exit_date=fill_date,
                exit_reason=decision.reason or rule.name,
                regime_at_exit=regime,
                broker=broker,
                account_id=account_id,
            )
            if not ok:
                summary["exits_failed"] += 1
                summary["exits_failed_symbols"].append(pos.symbol)
                break

            # -- Step 7: persist exit metadata (P0-2) --------------
            _log_exit_audit(
                pos.position_id, account_id, pos.symbol,
                fill_date, rule.name,
                decision.reason or rule.name,
                decision.metadata,
                forced=False,
            )

            # -- Step 8: record in summary -------------------------
            closed = pos_store.get_position_for_account(
                pos.position_id, account_id=account_id,
            )
            summary["exits_fired"] += 1
            summary["exits"].append({
                "position_id": pos.position_id,
                "symbol": pos.symbol,
                "exit_reason": decision.reason or rule.name,
                "exit_price": closed.exit_price if closed else None,
                "shares": pos.shares,
                "proceeds": closed.exit_proceeds if closed else None,
                "gross_return_pct": (
                    closed.gross_return_pct
                    if closed and closed.gross_return_pct is not None
                    else 0.0
                ),
                "holding_trading_days": holding_td,
                "forced": False,
            })
            break

    ages = [d["age_days"] for d in summary["open_position_days"]
            if d["age_days"] is not None]
    summary["avg_position_days"] = sum(ages) / len(ages) if ages else None
    summary["max_position_days"] = max(ages) if ages else None

    return summary


# -----------------------------------------------------------------
# CLI
# -----------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="v0.1.18 daily exit scan")
    parser.add_argument(
        "--as-of", type=str, default=None,
        help="trading date (YYYY-MM-DD); default = today",
    )
    parser.add_argument(
        "--fill-date", type=str, default=None,
        help="override T+1 fill date",
    )
    parser.add_argument(
        "--slippage", type=float, default=None,
        help="override slippage rate (default 0.001 = 0.1%%)",
    )
    parser.add_argument(
        "--account", type=str, default=None,
        metavar="ACCOUNT_ID",
        help="Account ID from config/accounts.yaml.",
    )
    args = parser.parse_args()

    init_schema()

    # -- v0.1.18: account config loading ---------------------------
    from config.account_config import get_account, load_accounts

    if args.account == "all":
        raise RuntimeError(
            "--account all is not supported for run_exit_scan. "
            "Use --account <id> and run separately per account."
        )

    if args.account:
        _account = get_account(args.account)
    else:
        _account = load_accounts()[0]

    account_id = _account.account_id

    as_of = (
        date_type.fromisoformat(args.as_of) if args.as_of
        else date_type.today()
    )
    fees = (
        TransactionFees(slippage_rate=args.slippage) if args.slippage is not None
        else None
    )

    print(f"Helios run_exit_scan -- {datetime.now().isoformat(timespec='seconds')}")
    print(f"As-of date: {as_of}  account: {account_id}")

    from market.trading_calendar import next_fillable_day
    fill_date = (
        date_type.fromisoformat(args.fill_date) if args.fill_date
        else (next_fillable_day(as_of) or as_of)
    )
    print(f"Fill date:  {fill_date} "
          f"({'T+1 proxy' if fill_date != as_of else 'T-close fallback'})")
    print()

    summary = scan_and_exit(
        as_of=as_of, fill_date=fill_date, fees=fees,
        account_id=account_id,
    )

    print(f"Open positions scanned: {summary['open_positions_scanned']}")
    print(f"Running-stats updates:  {summary['updated_stats']}")
    print(f"Exits fired:            {summary['exits_fired']}")
    print(f"Exits failed:           {summary['exits_failed']}")
    print(f"Skipped (no data):      {summary['skipped_no_data']}")

    if summary["exits"]:
        print("\n--- Exits this run ---")
        for e in summary["exits"]:
            px = e["exit_price"] if e["exit_price"] is not None else 0.0
            pr = e["proceeds"] if e["proceeds"] is not None else 0.0
            htd = e.get("holding_trading_days", "?")
            forced_tag = " [FORCED]" if e.get("forced") else ""
            print(
                f"  {e['symbol']:<8s}  {e['exit_reason']:<45s}  "
                f"px {px:>8.2f}  "
                f"return {e['gross_return_pct']:+.2f}%  "
                f"held {htd}d{forced_tag}  "
                f"proceeds NTD {pr:>12,.0f}"
            )

    print("\n+ exit scan complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
