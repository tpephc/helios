#!/usr/bin/env python3
# scripts/process_entries.py
"""Daily entry-signal generation + portfolio constraints + (optional) auto-fill.

Flow:
  1. Run TrendBreakoutStrategy.generate_signals for as_of date
  2. Run trend_pullback_v1 screener (parallel strategy, v0.1.18)
  3. Apply portfolio constraints (shared budget, considering OPEN positions)
  4. Conflict resolution: breakout vs pullback same symbol -> higher score wins
  5. Write accepted signals to signals table with status PENDING
  6. If --auto-approve: also call PaperBroker.submit_buy + open positions
     Otherwise: leave PENDING for Telegram approval flow

Per ADR-004: entries require human approval. --auto-approve bypasses this.

v0.1.18: account_id threading + trend_pullback_v1 parallel strategy.
  Pullback runs as second pass after breakout, sharing portfolio budget.
  Pullback signal_generator handles breakout conflict resolution.

Version: v0.1.18 (2026-05-28)
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


# -------------------------------------------------------------
# Portfolio snapshot (for risk preview)
# -------------------------------------------------------------


def _account_equity(
    initial_capital: float,
    as_of: date_type,
    account_id: str,
    equity_reset_date: date_type | None = None,
) -> tuple[float, float, dict]:
    """Returns (cash, equity, sector_exposures).

    v0.1.18: account_id required for positions queries.
    equity_reset_date: if set, closed positions before this date are excluded
    from PnL calculation; initial_capital is treated as the reset balance.
    """
    cash = initial_capital
    sector_value: dict[str, float] = {}
    etf_value = 0.0
    positions_value = 0.0

    for p in pos_store.get_closed_positions(account_id=account_id):
        if p.exit_proceeds is None:
            continue
        if equity_reset_date and p.exit_date <= equity_reset_date:
            continue
        cash += p.exit_proceeds - p.notional_at_entry - p.entry_commission - p.entry_slippage_cost

    for p in pos_store.get_open_positions(account_id=account_id):
        cash -= (p.notional_at_entry + p.entry_commission + p.entry_slippage_cost)

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
    print(f"      Portfolio exposure:  {cur_exposure:>5.1f}% -> {new_exposure:>5.1f}%  "
          f"(cap none, per-position {budget.per_position_pct*100:.0f}%)")
    print(f"      Cash buffer:         {cur_cash_pct:>5.1f}% -> {new_cash_pct:>5.1f}%  "
          f"(min {budget.cash_buffer_pct*100:.0f}%)")
    print(f"      Sector {sym_sector!r:<12s} {sec_cur_pct:>5.1f}% -> {sec_new_pct:>5.1f}%  "
          f"(cap {budget.max_sector_exposure_pct*100:.0f}%)")
    if is_etf(candidate_symbol):
        etf_v = exposures["etf"]
        etf_cur = (etf_v / equity * 100) if equity > 0 else 0
        etf_new = ((etf_v + candidate_notional) / equity * 100) if equity > 0 else 0
        print(f"      ETF total:           {etf_cur:>5.1f}% -> {etf_new:>5.1f}%  "
              f"(cap {budget.max_etf_exposure_pct*100:.0f}%)")


# -------------------------------------------------------------
# Constraints (live version of portfolio_simulator's logic)
# -------------------------------------------------------------


def _evaluate_constraints(
    candidates: list, *,
    cash: float, equity: float, exposures: dict, budget: RiskBudget,
    account_id: str,
) -> list[tuple[Any, bool, str | None]]:
    """Return (signal, accepted, reject_reason) for each candidate.

    v0.1.18: account_id required for positions queries.
    """
    open_symbols = {p.symbol for p in pos_store.get_open_positions(account_id=account_id)}
    n_open = len(open_symbols)
    etf_value = exposures["etf"]
    sector_value = dict(exposures["sector"])
    results = []

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

        results.append((sig, True, None))
        open_symbols.add(sig.stock_id)
        n_open += 1
        cash -= buy_cost
        if sym_is_etf:
            etf_value += per_pos_notional
        sector_value[sym_sector] = sector_value.get(sym_sector, 0.0) + per_pos_notional

    return results


# -------------------------------------------------------------
# Auto-approve helper (for testing without Telegram)
# -------------------------------------------------------------


def _auto_approve_and_fill(
    sig, signal_id: str, *,
    target_notional: float, as_of: date_type, fees: TransactionFees,
    account_id: str,
) -> str | None:
    """Approve + fill + open position. Returns position_id or None.

    v0.1.18: account_id required for open_position.
    v0.1.19: supports both breakout (.stock_id/.entry_price) and
             pullback (.symbol/.price) signal objects via getattr.
    """
    # Resolve field names: breakout sig uses stock_id/entry_price,
    # pullback sig uses symbol/price.
    symbol: str = getattr(sig, "stock_id", None) or sig.symbol
    entry_price: float = getattr(sig, "entry_price", None) or sig.price

    update_approval(signal_id, "AUTO_APPROVED", approved_by="auto")
    broker = PaperBroker(fees=fees, account_id=account_id)
    fill = broker.submit_buy(
        symbol=symbol, target_notional=target_notional,
        fill_date=as_of, signal_id=signal_id,
    )
    if not fill.success:
        logger.warning("auto_approve_fill_failed", signal_id=signal_id, reason=fill.error)
        return None
    pos_id = pos_store.open_position(
        account_id=account_id,
        symbol=symbol, strategy=sig.strategy,
        entry_date=as_of,
        entry_price=fill.fill_price or entry_price,
        entry_atr=sig.entry_atr,
        regime_at_entry=sig.regime,
        sector=get_sector(symbol),
        is_etf=is_etf(symbol),
        shares=fill.shares,
        notional_at_entry=fill.notional,
        entry_commission=fill.commission,
        entry_slippage_cost=fill.slippage_cost,
        entry_signal_id=signal_id,
        entry_order_id=fill.order_id,
        status=pos_store.OPEN,
    )
    return pos_id


# -------------------------------------------------------------
# Main
# -------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="v0.1.19 entry signal processing")
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--capital", type=float, default=None,
                        help="Override trading_capital from account config.")
    parser.add_argument("--auto-approve", action="store_true",
                        help="bypass approval; immediately fill + open (paper/sim only)")
    parser.add_argument("--slippage", type=float, default=0.001)
    parser.add_argument(
        "--account", type=str, default=None,
        metavar="ACCOUNT_ID",
        help="Account ID from config/accounts.yaml. "
             "Default: first enabled account.",
    )
    args = parser.parse_args()

    init_schema()
    as_of = (
        date_type.fromisoformat(args.as_of) if args.as_of
        else date_type.today()
    )
    fees = TransactionFees(slippage_rate=args.slippage)
    budget = DEFAULT_RISK_BUDGET

    # ── Account resolution (v0.1.19: no more hardcoded philip_sim) ──
    from config.account_config import load_accounts, get_account

    if args.account:
        _account = get_account(args.account)
    else:
        _accounts = load_accounts()
        _account = _accounts[0]

    account_id = _account.account_id
    capital = args.capital if args.capital is not None else _account.trading_capital
    equity_reset_date = _account.equity_reset_date

    # ── Paper-only guard for --auto-approve ──
    _SAFE_ENVS = {"paper", "simulation", "dev", "sim"}
    if args.auto_approve:
        env = getattr(_account, "environment", "unknown")
        if env.lower() not in _SAFE_ENVS:
            print(
                f"❌  --auto-approve blocked: account {account_id!r} "
                f"environment={env!r} is not in {_SAFE_ENVS}.\n"
                f"    Auto-approve is only allowed for paper/simulation accounts."
            )
            return 1

    print(f"Helios process_entries -- {datetime.now().isoformat(timespec='seconds')}")
    print(f"As-of: {as_of}  /  Capital: NTD {capital:,.0f}  /  Budget: {budget.describe()}")
    print(f"Account: {account_id} ({_account.environment})")
    if args.auto_approve:
        print("!! AUTO-APPROVE MODE (paper/sim only -- bypasses ADR-004)\n")
    print()

    # 1. Generate breakout signals
    strategy = TrendBreakoutStrategy()
    candidates = strategy.generate_signals(as_of=as_of)
    print(f"[breakout] fired: {len(candidates)} candidate signals")

    # 2. Snapshot account state
    cash, equity, exposures = _account_equity(
        capital, as_of, account_id=account_id,
        equity_reset_date=equity_reset_date,
    )
    print(f"Account: cash NTD {cash:,.0f} / equity NTD {equity:,.0f} / "
          f"positions_value NTD {exposures['positions_value']:,.0f}\n")

    # 3. Apply constraints (breakout)
    if candidates:
        decisions = _evaluate_constraints(
            candidates, cash=cash, equity=equity, exposures=exposures, budget=budget,
            account_id=account_id,
        )
        accepted = [(s, r) for s, ok, r in decisions if ok]
        rejected = [(s, r) for s, ok, r in decisions if not ok]
    else:
        accepted = []
        rejected = []

    per_pos_notional = budget.per_position_pct * equity

    # 4. Print breakout results
    if accepted:
        print("=== Accepted breakout signals ===")
        for sig, _ in accepted:
            if _has_active_signal_for(
                symbol=sig.stock_id, strategy=sig.strategy,
                signal_type=sig.side, signal_date=as_of,
            ):
                logger.info(
                    "skip_duplicate_signal",
                    symbol=sig.stock_id, strategy=sig.strategy,
                    as_of=str(as_of),
                )
                print(f"  {sig.stock_id} skip: active signal already exists")
                continue
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
                print(f"    * {r}")
            _print_risk_preview(
                sig.stock_id, per_pos_notional, budget, cash, equity, exposures,
            )

            if args.auto_approve:
                pos_id = _auto_approve_and_fill(
                    sig, signal_id,
                    target_notional=per_pos_notional, as_of=as_of, fees=fees,
                    account_id=account_id,
                )
                if pos_id:
                    print(f"    ok auto-filled -> position {pos_id}")
                else:
                    print("    x fill failed")
            else:
                print(f"    [PENDING approval -- telegram /approve {signal_id[:8]}]")
    else:
        print("(no breakout candidates accepted)")

    if rejected:
        print(f"\n=== Rejected breakout signals ({len(rejected)}) ===")
        for sig, reason in rejected:
            print(f"  {sig.stock_id:<8s}  score={sig.score:.2f}  reason: {reason}")

    # 5. Pullback strategy (parallel, v0.1.18)
    from strategies.trend_pullback import find_pullback_candidates
    pullback_cands = find_pullback_candidates(as_of)
    print(f"\n[pullback] fired: {len(pullback_cands)} candidate signals")

    if pullback_cands:
        from strategies.trend_pullback import generate_signals as pullback_gen
        open_syms = {p.symbol for p in pos_store.get_open_positions(account_id=account_id)}
        breakout_accepted = {s.stock_id: s.score for s, _ in accepted}
        open_for_dedup = open_syms | set(breakout_accepted.keys())

        pb_signals = pullback_gen(
            pullback_cands,
            open_symbols=open_for_dedup,
            pending_symbols=breakout_accepted,
        )

        if pb_signals:
            print(f"\n=== Accepted pullback signals ({len(pb_signals)}) ===")
            for pb in pb_signals:
                if _has_active_signal_for(
                    symbol=pb.symbol, strategy=pb.strategy,
                    signal_type=pb.signal_type, signal_date=as_of,
                ):
                    logger.info(
                        "skip_duplicate_signal",
                        symbol=pb.symbol, strategy=pb.strategy,
                        as_of=str(as_of),
                    )
                    print(f"  {pb.symbol} skip: active signal already exists")
                    continue
                signal_id = save_signal(
                    symbol=pb.symbol, strategy=pb.strategy,
                    signal_type=pb.signal_type, score=pb.score,
                    price=pb.price, signal_date=as_of,
                    reason=[
                        f"pullback: dist={pb.metadata['dist_above_ma20_atr']:.2f} ATR",
                        f"RS={pb.metadata['beta_adj_rs_20d']:.1f}",
                        f"beta={pb.metadata['beta_60']:.2f}",
                        f"priority={pb.priority.value}",
                    ],
                    entry_atr=pb.entry_atr,
                    regime=pb.regime, metadata=pb.metadata,
                    approval_status=("AUTO_APPROVED" if args.auto_approve else "PENDING"),
                )
                print(f"\n  {pb.symbol} ({get_sector(pb.symbol)})  "
                      f"score={pb.score:.2f}  px={pb.price:.2f}  "
                      f"ATR={pb.entry_atr:.2f}  dist={pb.metadata['dist_above_ma20_atr']:.2f}  "
                      f"priority={pb.priority.value}")
                print(f"    signal_id: {signal_id}")

                if args.auto_approve:
                    pos_id = _auto_approve_and_fill(
                        pb, signal_id,
                        target_notional=per_pos_notional, as_of=as_of,
                        fees=fees, account_id=account_id,
                    )
                    if pos_id:
                        print(f"    ok auto-filled -> position {pos_id}")
                    else:
                        print("    x fill failed")
                else:
                    print(f"    [PENDING approval -- telegram /approve {signal_id[:8]}]")
        else:
            print("(all pullback candidates filtered out)")

    print(f"\n{'='*60}")
    print(f"Summary: breakout={len(accepted)}, pullback={len(pullback_cands) if pullback_cands else 0}")
    return 0


# -------------------------------------------------------------
# Callable API (used by daily_run.py Step 6)
# -------------------------------------------------------------


def generate_pending_signals(
    as_of: date_type,
    capital: float,
    bot=None,
    budget: RiskBudget | None = None,
    account_id: str | None = None,
    auto_approve: bool = False,
) -> tuple[list[str], dict[str, float]]:
    """Generate entry signals + filter + push to Telegram.

    v0.1.18: runs breakout + pullback strategies in sequence.
    Pullback is second pass, sharing portfolio budget with breakout.
    Conflict resolution: breakout accepted symbols are passed to
    pullback signal_generator as pending_symbols.

    v0.1.19: account_id required (no implicit fallback).
    """
    if account_id is None:
        raise ValueError(
            "account_id is required. Pass explicitly from daily_run or CLI."
        )
    from storage.signals import update_approval
    budget = budget if budget is not None else DEFAULT_RISK_BUDGET

    cash, equity, exposures = _account_equity(
        capital, as_of, account_id=account_id,
        equity_reset_date=equity_reset_date,
    )
    per_pos_notional = budget.per_position_pct * equity
    fees = DEFAULT_TW_FEES
    buy_cost = per_pos_notional * (1 + fees.commission_rate + fees.slippage_rate)

    pending_ids: list[str] = []
    notional_map: dict[str, float] = {}

    # -- Pass 1: Breakout strategy ---------------------------------
    strategy = TrendBreakoutStrategy()
    breakout_candidates = strategy.generate_signals(as_of=as_of)

    breakout_accepted_symbols: dict[str, float] = {}

    if breakout_candidates:
        decisions = _evaluate_constraints(
            breakout_candidates, cash=cash, equity=equity,
            exposures=exposures, budget=budget, account_id=account_id,
        )

        for sig, ok, _reason in decisions:
            if not ok:
                continue

            if _has_active_signal_for(
                symbol=sig.stock_id, strategy=sig.strategy,
                signal_type=sig.side, signal_date=as_of,
            ):
                logger.info(
                    "skip_duplicate_signal",
                    symbol=sig.stock_id, strategy=sig.strategy,
                    as_of=str(as_of),
                )
                continue

            if _has_active_signal_for(
                symbol=sig.stock_id, strategy=sig.strategy,
                signal_type=sig.side, signal_date=as_of,
            ):
                logger.info(
                    "skip_duplicate_signal",
                    symbol=sig.stock_id, strategy=sig.strategy,
                    as_of=str(as_of),
                )
                continue

            signal_id = save_signal(
                symbol=sig.stock_id, strategy=sig.strategy,
                signal_type=sig.side, score=sig.score, price=sig.entry_price,
                signal_date=as_of,
                reason=sig.reason, entry_atr=sig.entry_atr,
                regime=sig.regime, metadata=sig.metadata,
                approval_status="AUTO_APPROVED" if auto_approve else "PENDING",
            )

            accepted = False
            if auto_approve:
                pos_id = _auto_approve_and_fill(
                    sig, signal_id,
                    target_notional=per_pos_notional, as_of=as_of,
                    fees=fees, account_id=account_id,
                )
                accepted = pos_id is not None
            else:
                accepted = _push_to_telegram(
                    bot, signal_id, sig, per_pos_notional,
                    cash, equity, exposures, budget,
                )

            if accepted:
                pending_ids.append(signal_id)
                notional_map[signal_id] = per_pos_notional
                breakout_accepted_symbols[sig.stock_id] = sig.score

    logger.info(
        "process_entries_breakout_complete",
        as_of=str(as_of),
        candidates=len(breakout_candidates) if breakout_candidates else 0,
        accepted=len(breakout_accepted_symbols),
    )

    # -- Pass 2: Pullback strategy ---------------------------------
    from strategies.trend_pullback import (
        find_pullback_candidates,
        generate_signals as pullback_generate,
    )

    pullback_candidates = find_pullback_candidates(as_of)
    pullback_accepted = 0

    if pullback_candidates:
        open_symbols = {
            p.symbol for p in pos_store.get_open_positions(account_id=account_id)
        }
        open_for_dedup = open_symbols | set(breakout_accepted_symbols.keys())

        pullback_signals = pullback_generate(
            pullback_candidates,
            open_symbols=open_for_dedup,
            pending_symbols=breakout_accepted_symbols,
        )

        # Apply remaining portfolio constraints for pullback signals.
        n_open = len(open_symbols) + len(breakout_accepted_symbols)
        remaining_cash = cash - len(breakout_accepted_symbols) * buy_cost
        cash_floor = budget.cash_buffer_pct * equity

        for pb_sig in pullback_signals:
            if n_open >= budget.max_positions:
                logger.info(
                    "pullback_reject_max_positions",
                    symbol=pb_sig.symbol, n_open=n_open,
                )
                break

            if remaining_cash - buy_cost < cash_floor:
                logger.info(
                    "pullback_reject_cash_buffer",
                    symbol=pb_sig.symbol,
                    remaining_cash=round(remaining_cash, 0),
                )
                break

            sym_sector = get_sector(pb_sig.symbol)
            sec_val = exposures["sector"].get(sym_sector, 0.0)
            if (sec_val + per_pos_notional) > budget.max_sector_exposure_pct * equity:
                logger.info(
                    "pullback_reject_sector_cap",
                    symbol=pb_sig.symbol, sector=sym_sector,
                )
                continue

            if is_etf(pb_sig.symbol):
                etf_val = exposures["etf"]
                if (etf_val + per_pos_notional) > budget.max_etf_exposure_pct * equity:
                    logger.info(
                        "pullback_reject_etf_cap",
                        symbol=pb_sig.symbol,
                    )
                    continue

            if _has_active_signal_for(
                symbol=pb_sig.symbol, strategy=pb_sig.strategy,
                signal_type=pb_sig.signal_type, signal_date=as_of,
            ):
                logger.info(
                    "skip_duplicate_signal",
                    symbol=pb_sig.symbol, strategy=pb_sig.strategy,
                    as_of=str(as_of),
                )
                continue

            signal_id = save_signal(
                symbol=pb_sig.symbol, strategy=pb_sig.strategy,
                signal_type=pb_sig.signal_type, score=pb_sig.score,
                price=pb_sig.price,
                signal_date=as_of,
                reason=[
                    f"pullback: dist={pb_sig.metadata['dist_above_ma20_atr']:.2f} ATR",
                    f"RS={pb_sig.metadata['beta_adj_rs_20d']:.1f} (pctl {pb_sig.metadata['rs_percentile']:.0%})",
                    f"beta={pb_sig.metadata['beta_60']:.2f} (pctl {pb_sig.metadata['beta_percentile']:.0%})",
                    f"priority={pb_sig.priority.value}",
                ],
                entry_atr=pb_sig.entry_atr,
                regime=pb_sig.regime,
                metadata=pb_sig.metadata,
                approval_status="AUTO_APPROVED" if auto_approve else "PENDING",
            )

            accepted = False
            if auto_approve:
                pos_id = _auto_approve_and_fill(
                    pb_sig, signal_id,
                    target_notional=per_pos_notional, as_of=as_of,
                    fees=fees, account_id=account_id,
                )
                accepted = pos_id is not None
            else:
                accepted = _push_to_telegram(
                    bot, signal_id, pb_sig, per_pos_notional,
                    remaining_cash, equity, exposures, budget,
                )

            if accepted:
                pending_ids.append(signal_id)
                notional_map[signal_id] = per_pos_notional
                pullback_accepted += 1
                n_open += 1
                remaining_cash -= buy_cost

    logger.info(
        "process_entries_pullback_complete",
        as_of=str(as_of),
        candidates=len(pullback_candidates) if pullback_candidates else 0,
        accepted=pullback_accepted,
    )

    return pending_ids, notional_map


def _push_to_telegram(
    bot, signal_id: str, sig, per_pos_notional: float,
    cash: float, equity: float, exposures: dict, budget: RiskBudget,
) -> bool:
    """Push signal to Telegram. Returns True if OK (or no bot).

    On failure, marks signal as TIMEOUT to prevent stale PENDING.
    Handles both breakout (sig.stock_id) and pullback (sig.symbol)
    candidate types via getattr.
    """
    if bot is None:
        return True

    from communication.telegram.sender import push_entry_request
    from storage.signals import get_signal as _get_signal

    sig_row = _get_signal(signal_id)
    msg_id = None
    if sig_row:
        symbol = getattr(sig, 'stock_id', None) or getattr(sig, 'symbol', None)
        msg_id = push_entry_request(
            bot, sig_row,
            target_notional=per_pos_notional,
            cash=cash, equity=equity,
            sector_value=exposures["sector"].get(get_sector(symbol), 0.0),
            etf_value=exposures["etf"],
            pos_value=exposures["positions_value"],
            budget=budget,
        )
    if msg_id is None:
        update_approval(
            signal_id, "TIMEOUT",
            expired_reason="telegram_push_failed",
        )
        logger.warning(
            "entry_push_failed_marked_expired",
            signal_id=signal_id,
        )
        return False
    return True


def _has_active_signal_for(
    *, symbol: str, strategy: str, signal_type: str, signal_date: date_type,
) -> bool:
    """P1-8 helper: check for non-terminal duplicate signal for given trading day."""
    with connect(read_only=True) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) FROM signals
            WHERE symbol = ? AND strategy = ? AND signal_type = ?
              AND signal_date = ?
              AND approval_status IN ('PENDING', 'APPROVED', 'AUTO_APPROVED')
            """,
            [symbol, strategy, signal_type, signal_date],
        ).fetchone()
    return (row[0] or 0) > 0


if __name__ == "__main__":
    sys.exit(main())
