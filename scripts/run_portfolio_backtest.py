#!/usr/bin/env python3
# scripts/run_portfolio_backtest.py
"""Portfolio-constrained backtest — v0.1.14.1 deliverable.

跑帶資金約束的 round-trip backtest, 輸出 equity curve / max DD / 信號接受率
+ IS/OOS partition + verdict (per user spec exit criteria).

執行:
  # Default (capital 100 萬 NTD, default 台股 cost, default budget)
  uv run python scripts/run_portfolio_backtest.py

  # IS/OOS side-by-side (主菜)
  uv run python scripts/run_portfolio_backtest.py --is-end 2023-12-31

  # 加 slippage 保險
  uv run python scripts/run_portfolio_backtest.py --is-end 2023-12-31 --slippage 0.001

  # 改 budget
  uv run python scripts/run_portfolio_backtest.py --max-positions 4 --per-position 0.18

  # 匯出 CSV
  uv run python scripts/run_portfolio_backtest.py \\
    --export-equity equity.csv \\
    --export-trades trades.csv \\
    --export-decisions decisions.csv

Verdict (user spec):
  ✓✓ STRONG PASS:
    OOS net PF > 1.7
    OOS max DD 可接受 (絕對值 < 15%)
    平均曝險合理 (40-80%)
    沒有單一 reject reason 過度集中
  ✓ PASS:
    OOS net PF > 1.3
    OOS max DD < 25%
    no extreme concentration
  ⚠ FAIL: 其他

Version: v0.1.0 (2026-05-17)
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date as date_type
from datetime import datetime

from backtest.portfolio_simulator import (
    EquitySnapshot,
    PortfolioBacktest,
    PortfolioMetrics,
    PortfolioPosition,
    SignalDecision,
    compute_portfolio_metrics,
)
from backtest.round_trip import TransactionCosts
from data.database import init_schema
from portfolio.risk_budget import RiskBudget
from strategies.trend_breakout import TrendBreakoutStrategy

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────


def fmt_pct(v: float, dec: int = 2, signed: bool = False) -> str:
    if v == float("inf"):
        return "  ∞"
    sign = "+" if signed else ""
    return f"{v:{sign}.{dec}f}%"


def fmt_ntd(v: float) -> str:
    return f"NTD {v:>15,.0f}"


def compute_partition_metrics(
    equity_curve: list[EquitySnapshot],
    trades: list[PortfolioPosition],
    decisions: list[SignalDecision],
    period_start: date_type,
    period_end: date_type,
    initial_capital_for_period: float,
) -> PortfolioMetrics:
    """Compute metrics restricted to [period_start, period_end] window."""
    period_curve = [s for s in equity_curve if period_start <= s.date <= period_end]
    period_trades = [
        t for t in trades
        if t.entry_date is not None
        and period_start <= t.entry_date <= period_end
    ]
    period_decisions = [
        d for d in decisions if period_start <= d.date <= period_end
    ]
    return compute_portfolio_metrics(
        period_curve, period_trades, period_decisions, initial_capital_for_period
    )


def print_metrics(label: str, m: PortfolioMetrics) -> None:
    print(f"\n{'─'*72}")
    print(f"[{label}]")
    print(f"{'─'*72}")
    print(f"  Initial capital      {fmt_ntd(m.initial_capital)}")
    print(f"  Final equity         {fmt_ntd(m.final_equity)}")
    print(f"  Total return         {fmt_pct(m.total_return_pct, signed=True):>16s}")
    print(f"  CAGR                 {fmt_pct(m.cagr_pct, signed=True):>16s}")
    print(f"  Max drawdown         {fmt_pct(m.max_drawdown_pct, signed=True):>16s}  "
          f"({m.max_dd_date})")
    print(f"  Avg exposure         {fmt_pct(m.avg_exposure_pct):>16s}")
    print(f"  Avg # positions      {m.avg_n_positions:>15.2f}")
    print("  ─")
    print(f"  Trades (closed)      {m.n_trades:>16d}")
    print(f"  Win rate             {fmt_pct(m.win_rate):>16s}")
    print(f"  Profit factor        {m.profit_factor:>16.2f}")
    print(f"  Avg trade return     {fmt_pct(m.avg_trade_return_pct, signed=True):>16s}")
    print("  ─")
    print(f"  Signals seen         {m.n_signals_seen:>16d}")
    print(f"  Signals rejected     {m.n_signals_rejected:>16d}  "
          f"({m.n_signals_rejected/max(m.n_signals_seen,1)*100:.1f}%)")

    if m.reject_reasons:
        total = sum(m.reject_reasons.values())
        print("\n  Reject distribution:")
        for reason, n in sorted(m.reject_reasons.items(), key=lambda x: -x[1]):
            print(f"    {reason:<25s} {n:>4d} ({n/total*100:>5.1f}%)")


def verdict_oos(m: PortfolioMetrics) -> tuple[str, list[str]]:
    """User-spec verdict on OOS partition."""
    notes: list[str] = []
    if m.n_trades < 15:
        notes.append(f"⚠ OOS trades 太少 (n={m.n_trades})")
        return "⚠ FAIL (insufficient sample)", notes

    pf = m.profit_factor
    max_dd = abs(m.max_drawdown_pct)
    avg_exp = m.avg_exposure_pct
    reject_pct = m.n_signals_rejected / max(m.n_signals_seen, 1) * 100

    # Hard fails
    if pf < 1.3:
        notes.append(f"⚠ OOS PF {pf:.2f} < 1.3 (edge 不足)")
        return "⚠ FAIL", notes
    if max_dd > 25:
        notes.append(f"⚠ OOS max DD {max_dd:.1f}% > 25% (風險過大)")
        return "⚠ FAIL", notes
    if m.total_return_pct < 0:
        notes.append(f"⚠ OOS total return {m.total_return_pct:+.2f}% < 0")
        return "⚠ FAIL (negative return)", notes

    # Check STRONG PASS
    strong = (
        pf > 1.7
        and max_dd < 15
        and 30 <= avg_exp <= 90
    )
    if strong:
        notes.append(f"✓✓ PF {pf:.2f} > 1.7, max DD {max_dd:.1f}% < 15%")
        notes.append(f"✓✓ avg exposure {avg_exp:.1f}% in 30-90%")
        notes.append(f"   reject rate {reject_pct:.1f}% (signals filtered)")
        return "✓✓ STRONG PASS", notes

    notes.append(f"✓ PF {pf:.2f} > 1.3")
    notes.append(f"✓ max DD {max_dd:.1f}% < 25%")
    notes.append(f"  avg exposure {avg_exp:.1f}%  /  reject rate {reject_pct:.1f}%")
    return "✓ PASS", notes


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Portfolio-constrained backtest (v0.1.14.1)"
    )
    parser.add_argument("--capital", type=float, default=1_000_000.0,
                        help="initial capital NTD (default 1,000,000)")
    parser.add_argument("--symbols", type=str, help="逗號分隔")
    parser.add_argument("--is-end", type=str, default=None,
                        help="IS 結束日 (YYYY-MM-DD) — 觸發 IS/OOS partition")

    # Risk budget knobs
    parser.add_argument("--max-positions", type=int, default=5)
    parser.add_argument("--per-position", type=float, default=0.20)
    parser.add_argument("--max-etf", type=float, default=0.40)
    parser.add_argument("--max-sector", type=float, default=0.30)
    parser.add_argument("--cash-buffer", type=float, default=0.10)

    # Costs
    parser.add_argument("--commission", type=float, default=0.001425)
    parser.add_argument("--sell-tax", type=float, default=0.003)
    parser.add_argument("--slippage", type=float, default=0.0)

    # Exports
    parser.add_argument("--export-equity", type=str, default=None)
    parser.add_argument("--export-trades", type=str, default=None)
    parser.add_argument("--export-decisions", type=str, default=None)

    args = parser.parse_args()
    init_schema()

    budget = RiskBudget(
        max_positions=args.max_positions,
        per_position_pct=args.per_position,
        max_etf_exposure_pct=args.max_etf,
        max_sector_exposure_pct=args.max_sector,
        cash_buffer_pct=args.cash_buffer,
    )
    costs = TransactionCosts(args.commission, args.sell_tax, args.slippage)

    print(f"Helios run_portfolio_backtest — {datetime.now().isoformat(timespec='seconds')}")
    print(f"Capital: {fmt_ntd(args.capital)}")
    print(f"Budget:  {budget.describe()}")
    print(f"Costs:   {costs.describe()}")
    if args.is_end:
        print(f"Split:   IS ≤ {args.is_end} < OOS")
    print()

    symbols = (
        [s.strip() for s in args.symbols.split(",") if s.strip()]
        if args.symbols else None
    )

    t0 = datetime.now()
    bt = PortfolioBacktest(
        strategy=TrendBreakoutStrategy(),
        initial_capital=args.capital,
        budget=budget,
        symbols=symbols,
        costs=costs,
    )
    print("Running portfolio-constrained backtest...")
    trades = bt.run()
    elapsed = (datetime.now() - t0).total_seconds()
    print(f"  → {len(trades)} completed trades, "
          f"{len(bt.signal_decisions)} signal decisions  ({elapsed:.1f}s)")

    if not bt.equity_curve:
        print("⚠ No equity curve generated")
        return 0

    # FULL HISTORY metrics
    full_m = compute_portfolio_metrics(
        bt.equity_curve, bt.completed_trades, bt.signal_decisions, args.capital,
    )

    if args.is_end:
        is_end = date_type.fromisoformat(args.is_end)
        first_date = bt.equity_curve[0].date
        last_date = bt.equity_curve[-1].date

        # IS portion
        is_curve = [s for s in bt.equity_curve if s.date <= is_end]
        is_m = compute_partition_metrics(
            bt.equity_curve, bt.completed_trades, bt.signal_decisions,
            first_date, is_end, args.capital,
        )
        # OOS portion — starting equity = equity at end of IS
        oos_start_equity = is_curve[-1].equity if is_curve else args.capital
        oos_m = compute_partition_metrics(
            bt.equity_curve, bt.completed_trades, bt.signal_decisions,
            is_end, last_date, oos_start_equity,
        )

        # Print
        print_metrics("FULL HISTORY", full_m)
        print_metrics("IN-SAMPLE (2021-2023)", is_m)
        print_metrics("OUT-OF-SAMPLE (2024-2026)", oos_m)

        # Verdict on OOS
        result, notes = verdict_oos(oos_m)
        print(f"\n{'='*72}\nVERDICT (on OOS): {result}\n{'='*72}")
        for note in notes:
            print(f"  {note}")
    else:
        print_metrics("FULL HISTORY", full_m)

    # Sector exposure of completed trades
    if bt.completed_trades:
        print(f"\n{'─'*72}")
        print("Sector exposure (of completed trades, by count):")
        sector_count = Counter(t.sector for t in bt.completed_trades)
        for sector, n in sector_count.most_common():
            sector_trades = [t for t in bt.completed_trades if t.sector == sector]
            sector_returns = [
                t.gross_return_pct for t in sector_trades
                if t.gross_return_pct is not None
            ]
            mean_r = sum(sector_returns) / len(sector_returns) if sector_returns else 0
            pct = n / len(bt.completed_trades) * 100
            print(f"  {sector:<15s} n={n:<3d}  ({pct:>5.1f}%)  "
                  f"mean_return={fmt_pct(mean_r, signed=True)}")

    # Equity curve highlights
    print(f"\n{'─'*72}")
    print("Equity curve sample points:")
    n_pts = len(bt.equity_curve)
    sample_idx = [0, n_pts // 4, n_pts // 2, 3 * n_pts // 4, n_pts - 1]
    seen = set()
    for i in sample_idx:
        if i in seen or i >= n_pts:
            continue
        seen.add(i)
        s = bt.equity_curve[i]
        print(f"  {s.date}  equity={fmt_ntd(s.equity)}  "
              f"cash={s.cash:>11,.0f}  pos={s.n_positions}  "
              f"exposure={s.exposure_pct:>5.1f}%")

    # Exports
    if args.export_equity:
        bt.equity_curve_to_polars().write_csv(args.export_equity)
        print(f"\n✓ Equity curve → {args.export_equity}")
    if args.export_trades:
        bt.trades_to_polars().write_csv(args.export_trades)
        print(f"✓ Trades → {args.export_trades}")
    if args.export_decisions:
        bt.decisions_to_polars().write_csv(args.export_decisions)
        print(f"✓ Decisions → {args.export_decisions}")

    print(f"\n{'='*72}")
    print("✓ v0.1.14.1 portfolio backtest complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
