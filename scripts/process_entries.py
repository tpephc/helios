#!/usr/bin/env python3
# scripts/process_entries.py
"""Daily entry-signal generation + portfolio constraints + (optional) auto-fill.

Flow:
  1. Run TrendBreakoutStrategy.generate_signals for as_of date
  2. Apply portfolio constraints (selector logic, considering currently-OPEN positions)
  3. Write accepted signals to signals table with status PENDING
  4. If --auto-approve: also call PaperBroker.submit_buy + open positions (FOR TESTING)
     Otherwise: leave PENDING for Telegram approval flow (Round 2)
  5. Print summary including risk preview per review #4 (portfolio context for informed approval)

Per ADR-004: entries require human approval. --auto-approve bypasses this for testing only.

Per review #4: Telegram message format should include "if approved, exposure goes from X% → Y%"
risk preview. This script computes that preview for each candidate signal.

Version: v0.1.0 (2026-05-17)
"""
from __future__ import annotations

import argparse
import sys
from datetime import date as date_type
from datetime import datetime
from typing import Any

from data.database import connect, init_schema
from execution.paper_broker import DEFAULT_TW_FEES, PaperBroker, TransactionFees
from portfolio.risk_budget import DEFAULT_RISK_BUDGET, RiskBudget
from portfolio.selector import get_sector, is_etf
from storage import positions as pos_store
from storage.signals import save_signal, update_approval
from strategies.trend_breakout import TrendBreakoutStrategy
from utils.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────
# Portfolio snapshot (for risk preview)
# ─────────────────────────────────────────────────────────────


def _account_equity(initial_capital: float, as_of: date_type) -> tuple[float, float, dict]:
    """Returns (cash, equity, sector_exposures).

    cash = initial_capital + sum(realized P&L from CLOSED positions) - sum(notional of OPEN)
    equity = cash + sum(market value of OPEN positions at as_of close)
    """
    cash = initial_capital
    sector_value: dict[str, float] = {}
    etf_value = 0.0
    positions_value = 0.0

    # Realized: CLOSED contribute net_pnl_ntd
    for p in pos_store.get_closed_positions():
        if p.exit_proceeds is None:
            continue
        # cash flow: -notional_at_entry (originally went out)
        #            -entry_costs (already in notional? no, additional)
        #            +exit_proceeds (came back, net of exit costs)
        cash += p.exit_proceeds - p.notional_at_entry - p.entry_commission - p.entry_slippage_cost

    # Open: cash decreased by notional+entry_costs; equity includes mark-to-market
    for p in pos_store.get_open_positions():
        cash -= (p.notional_at_entry + p.entry_commission + p.entry_slippage_cost)

        # mark-to-market via latest adj_close
        with connect(read_only=True) as conn:
            row = conn.execute(
                "SELECT adj_close FROM daily_price_adj WHERE stock_id=? AND date <= ? ORDER BY date DESC LIMIT 1",
                [p.symbol, as_of],
            ).fetchone()
        mkt_price = float(row[0]) if row and row[0] else p.entry_price
        val = p.shares * mkt_price
        positions_value += val
        sector_value[p.sector] = sector_value.get(p.sector, 0.0) + val
        if p.is_etf:
            etf_value += val

    equity = cash + positions_value
    return cash, equity, {"sector": sector_value, "etf": etf_value, "positions_value": positions_value}


def _print_risk_preview(
    candidate_symbol: str, candidate_notional: float, budget: RiskBudget,
    cash: float, equity: float, exposures: dict,
) -> None:
    """Per review #4: show portfolio impact preview."""
    pos_val = exposures["positions_value"]
    cur_exposure = (pos_val / equity * 100) if equity > 0 else 0
    new_exposure = ((pos_val + candidate_notional) / equity * 100) if equity > 0 else 0

    cur_cash_pct = (cash / equity * 100) if equity > 0 else 100
    new_cash_pct = ((cash - candidate_notional) / equity * 100) if equity > 0 else 0

    sym_sector = get_sector(candidate_symbol)
    sec_value = exposures["sector"].get(sym_sector, 0.0)
    sec_new = sec_value + candidate_notional
    sec_cur_pct = (sec_value / equity * 100) if equity > 0 else 0
    sec_new_pct = (sec_new / equity * 100) if equity > 0 else 0

    print("    Risk preview if approved:")
    print(f"      Portfolio exposure:  {cur_exposure:>5.1f}% → {new_exposure:>5.1f}%  "
          f"(cap none, per-position {budget.per_position_pct*100:.0f}%)")
    print(f"      Cash buffer:         {cur_cash_pct:>5.1f}% → {new_cash_pct:>5.1f}%  "
          f"(min {budget.cash_buffer_pct*100:.0f}%)")
    print(f"      Sector {sym_sector!r:<12s} {sec_cur_pct:>5.1f}% → {sec_new_pct:>5.1f}%  "
          f"(cap {budget.max_sector_exposure_pct*100:.0f}%)")
    if is_etf(candidate_symbol):
        etf_v = exposures["etf"]
        etf_cur = (etf_v / equity * 100) if equity > 0 else 0
        etf_new = ((etf_v + candidate_notional) / equity * 100) if equity > 0 else 0
        print(f"      ETF total:           {etf_cur:>5.1f}% → {etf_new:>5.1f}%  "
              f"(cap {budget.max_etf_exposure_pct*100:.0f}%)")


# ─────────────────────────────────────────────────────────────
# Constraints (live version of portfolio_simulator's logic)
# ─────────────────────────────────────────────────────────────


def _evaluate_constraints(
    candidates: list, *,
    cash: float, equity: float, exposures: dict, budget: RiskBudget,
) -> list[tuple[Any, bool, str | None]]:
    """Return (signal, accepted, reject_reason) for each candidate.

    Same constraint order as backtest/portfolio_simulator.py:
      symbol_already_held → max_positions → cash_buffer → etf_cap → sector_cap
    """
    open_symbols = {p.symbol for p in pos_store.get_open_positions()}
    n_open = len(open_symbols)
    etf_value = exposures["etf"]
    sector_value = dict(exposures["sector"])
    results = []

    # Sort by score DESC
    sorted_cands = sorted(candidates, key=lambda s: -s.score)
    per_pos_notional = budget.per_position_pct * equity
    cash_floor = budget.cash_buffer_pct * equity
    fees = DEFAULT_TW_FEES
    buy_cost = per_pos_notional * (1 + fees.commission_rate + fees.slippage_rate)

    for sig in sorted_cands:
        if sig.stock_id in open_symbols:
            results.append((sig, False, "symbol_already_held"))
            continue
        if n_open >= budget.max_positions:
            results.append((sig, False, "max_positions_reached"))
            continue
        if cash - buy_cost < cash_floor:
            results.append((sig, False, "cash_buffer"))
            continue
        sym_is_etf = is_etf(sig.stock_id)
        if sym_is_etf and (etf_value + per_pos_notional) > budget.max_etf_exposure_pct * equity:
            results.append((sig, False, "etf_cap"))
            continue
        sym_sector = get_sector(sig.stock_id)
        if (sector_value.get(sym_sector, 0.0) + per_pos_notional) > budget.max_sector_exposure_pct * equity:
            results.append((sig, False, f"sector_cap_{sym_sector}"))
            continue

        # Accepted — update running tallies
        results.append((sig, True, None))
        open_symbols.add(sig.stock_id)
        n_open += 1
        cash -= buy_cost
        if sym_is_etf:
            etf_value += per_pos_notional
        sector_value[sym_sector] = sector_value.get(sym_sector, 0.0) + per_pos_notional

    return results


# ─────────────────────────────────────────────────────────────
# Auto-approve helper (for testing without Telegram)
# ─────────────────────────────────────────────────────────────


def _auto_approve_and_fill(
    sig, signal_id: str, *,
    target_notional: float, as_of: date_type, fees: TransactionFees,
) -> str | None:
    """Approve + fill + open position. Returns position_id or None."""
    update_approval(signal_id, "AUTO_APPROVED", approved_by="auto")
    broker = PaperBroker(fees=fees)
    fill = broker.submit_buy(
        symbol=sig.stock_id, target_notional=target_notional,
        fill_date=as_of, signal_id=signal_id,
    )
    if not fill.success:
        logger.warning("auto_approve_fill_failed", signal_id=signal_id, reason=fill.error)
        return None
    pos_id = pos_store.open_position(
        symbol=sig.stock_id, strategy=sig.strategy,
        entry_date=as_of,
        entry_price=fill.fill_price or sig.entry_price,
        entry_atr=sig.entry_atr,
        regime_at_entry=sig.regime,
        sector=get_sector(sig.stock_id),
        is_etf=is_etf(sig.stock_id),
        shares=fill.shares,
        notional_at_entry=fill.notional,
        entry_commission=fill.commission,
        entry_slippage_cost=fill.slippage_cost,
        entry_signal_id=signal_id,
        entry_order_id=fill.order_id,
        status=pos_store.OPEN,
    )
    return pos_id


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="v0.1.14.2 entry signal processing")
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--capital", type=float, default=1_000_000)
    parser.add_argument("--auto-approve", action="store_true",
                        help="(TESTING ONLY) bypass approval; immediately fill + open")
    parser.add_argument("--slippage", type=float, default=0.001)
    args = parser.parse_args()

    init_schema()
    as_of = (
        date_type.fromisoformat(args.as_of) if args.as_of
        else date_type.today()
    )
    fees = TransactionFees(slippage_rate=args.slippage)
    budget = DEFAULT_RISK_BUDGET

    print(f"Helios process_entries — {datetime.now().isoformat(timespec='seconds')}")
    print(f"As-of: {as_of}  /  Capital: NTD {args.capital:,.0f}  /  Budget: {budget.describe()}")
    if args.auto_approve:
        print("⚠ AUTO-APPROVE MODE (testing only — bypasses ADR-004)\n")
    print()

    # 1. Generate signals
    strategy = TrendBreakoutStrategy()
    candidates = strategy.generate_signals(as_of=as_of)
    print(f"Strategy fired: {len(candidates)} candidate signals")
    if not candidates:
        print("(no candidates today)")
        return 0

    # 2. Snapshot account state
    cash, equity, exposures = _account_equity(args.capital, as_of)
    print(f"Account: cash NTD {cash:,.0f} / equity NTD {equity:,.0f} / "
          f"positions_value NTD {exposures['positions_value']:,.0f}\n")

    # 3. Apply constraints
    decisions = _evaluate_constraints(
        candidates, cash=cash, equity=equity, exposures=exposures, budget=budget,
    )
    accepted = [(s, sid, r) for (s, ok, r), sid in zip(decisions, [None]*len(decisions), strict=False) if ok]
    # Re-zip with index
    accepted = [(s, r) for s, ok, r in decisions if ok]
    rejected = [(s, r) for s, ok, r in decisions if not ok]

    per_pos_notional = budget.per_position_pct * equity

    # 4. Save signals + (optional) fill
    print("=== Accepted signals ===")
    for sig, _ in accepted:
        signal_id = save_signal(
            symbol=sig.stock_id, strategy=sig.strategy,
            signal_type=sig.side, score=sig.score, price=sig.entry_price,
            signal_date=as_of,
            reason=sig.reason, entry_atr=sig.entry_atr,
            regime=sig.regime, metadata=sig.metadata,
            approval_status=("AUTO_APPROVED" if args.auto_approve else "PENDING"),
        )
        print(f"\n  {sig.stock_id} ({get_sector(sig.stock_id)})  "
              f"score={sig.score:.2f}  px={sig.entry_price:.2f}  "
              f"ATR={sig.entry_atr:.2f}")
        print(f"    signal_id: {signal_id}")
        for r in sig.reason[:4]:
            print(f"    • {r}")
        _print_risk_preview(
            sig.stock_id, per_pos_notional, budget, cash, equity, exposures,
        )

        if args.auto_approve:
            pos_id = _auto_approve_and_fill(
                sig, signal_id,
                target_notional=per_pos_notional, as_of=as_of, fees=fees,
            )
            if pos_id:
                print(f"    ✓ auto-filled → position {pos_id}")
            else:
                print("    ✗ fill failed")
        else:
            print(f"    [PENDING approval — Round 2 telegram /approve {signal_id[:8]}]")

    if rejected:
        print(f"\n=== Rejected signals ({len(rejected)}) ===")
        for sig, reason in rejected:
            print(f"  {sig.stock_id:<8s}  score={sig.score:.2f}  reason: {reason}")

    print(f"\n{'='*60}")
    print(f"Summary: {len(accepted)} accepted, {len(rejected)} rejected")
    return 0


# ─────────────────────────────────────────────────────────────
# Callable API (used by daily_run.py Step 5)
# ─────────────────────────────────────────────────────────────


def generate_pending_signals(
    as_of: date_type,
    capital: float,
    bot=None,                              # TelegramBot | None
    budget: RiskBudget | None = None,
) -> tuple[list[str], dict[str, float]]:
    """Generate entry signals + filter + push to Telegram.

    Returns (pending_signal_ids, notional_map). notional_map is used by listener
    at approval time to call lifecycle.open_position_from_signal.

    P0-3: if Telegram push fails (bot configured but push returns None), the
    signal is immediately marked TIMEOUT with reason 'telegram_push_failed' and
    NOT included in returned pending_ids. The user must not be left with stale
    PENDING they didn't see ("missed signal > wrong trade").

    P1-8: same-day idempotency — skip candidates that already have a non-terminal
    signal for (symbol, strategy, signal_type, as_of). Prevents duplicate PENDING
    on accidental re-run of daily_run.
    """
    from storage.signals import update_approval
    budget = budget if budget is not None else DEFAULT_RISK_BUDGET
    strategy = TrendBreakoutStrategy()
    candidates = strategy.generate_signals(as_of=as_of)
    if not candidates:
        return [], {}

    cash, equity, exposures = _account_equity(capital, as_of)
    decisions = _evaluate_constraints(
        candidates, cash=cash, equity=equity, exposures=exposures, budget=budget,
    )
    per_pos_notional = budget.per_position_pct * equity

    pending_ids: list[str] = []
    notional_map: dict[str, float] = {}

    for sig, ok, _reason in decisions:
        if not ok:
            continue

        # P1-8: idempotency — skip if non-terminal duplicate exists for as_of
        if _has_active_signal_for(
            symbol=sig.stock_id, strategy=sig.strategy,
            signal_type=sig.side, signal_date=as_of,
        ):
            logger.info(
                "skip_duplicate_signal",
                symbol=sig.stock_id, strategy=sig.strategy, as_of=str(as_of),
            )
            continue

        signal_id = save_signal(
            symbol=sig.stock_id, strategy=sig.strategy,
            signal_type=sig.side, score=sig.score, price=sig.entry_price,
            signal_date=as_of,
            reason=sig.reason, entry_atr=sig.entry_atr,
            regime=sig.regime, metadata=sig.metadata,
            approval_status="PENDING",
        )

        # P0-3: try push; if push fails, mark expired (don't leak stale PENDING)
        push_ok = True
        if bot is not None:
            from communication.telegram.sender import push_entry_request
            from storage.signals import get_signal as _get_signal
            sig_row = _get_signal(signal_id)
            msg_id = None
            if sig_row:
                msg_id = push_entry_request(
                    bot, sig_row,
                    target_notional=per_pos_notional,
                    cash=cash, equity=equity,
                    sector_value=exposures["sector"].get(get_sector(sig.stock_id), 0.0),
                    etf_value=exposures["etf"],
                    pos_value=exposures["positions_value"],
                    budget=budget,
                )
            if msg_id is None:
                # Push failed — operator did not receive this. Mark expired.
                update_approval(
                    signal_id, "TIMEOUT",
                    expired_reason="telegram_push_failed",
                )
                logger.warning(
                    "entry_push_failed_marked_expired",
                    signal_id=signal_id, symbol=sig.stock_id,
                )
                push_ok = False

        if push_ok:
            pending_ids.append(signal_id)
            notional_map[signal_id] = per_pos_notional

    return pending_ids, notional_map


def _has_active_signal_for(
    *, symbol: str, strategy: str, signal_type: str, signal_date: date_type,
) -> bool:
    """P1-8 helper: check for non-terminal duplicate signal for given trading day.

    Active = PENDING or APPROVED (in-flight). Terminal statuses
    (REJECTED, TIMEOUT, EXPIRED_DRIFT, AUTO_APPROVED+filled) are OK to skip past.

    v0.1.14.2-c3: queries `signal_date` column directly (market semantic date),
    NOT `CAST(created_at AS DATE)` (which was the pre-c3 bug). With this fix
    cross-day reruns of the same as_of are correctly deduplicated regardless
    of when the row was originally inserted.
    """
    with connect(read_only=True) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) FROM signals
            WHERE symbol = ? AND strategy = ? AND signal_type = ?
              AND signal_date = ?
              AND approval_status IN ('PENDING', 'APPROVED')
            """,
            [symbol, strategy, signal_type, signal_date],
        ).fetchone()
    return (row[0] or 0) > 0


if __name__ == "__main__":
    sys.exit(main())
