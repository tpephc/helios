#!/usr/bin/env python3
# scripts/run_backtest.py
"""Round-trip backtest with transaction costs + IS/OOS split (v0.1.13.3).

執行範例:
  # 基本 (含預設台股 cost: 0.585% round-trip)
  uv run python scripts/run_backtest.py

  # 加 slippage assumption
  uv run python scripts/run_backtest.py --slippage 0.001

  # IS/OOS side-by-side (推薦, 用 v0.1.13.1 同 split 點)
  uv run python scripts/run_backtest.py --is-end 2023-12-31

  # 完整 deployable-grade check
  uv run python scripts/run_backtest.py --is-end 2023-12-31 --slippage 0.001

  # Gross only (no cost)
  uv run python scripts/run_backtest.py --no-costs

Verdict thresholds (per user spec):
  STRONG PASS:  OOS net mean > 1.0%, net PF > 1.7, win/loss > 1.5
  PASS:         OOS net mean > 0, net PF > 1.3, crisis leak = 0, sufficient trades
  FAIL:         其他

Version: v0.1.1 (2026-05-17)
Changelog:
  v0.1.1 (2026-05-17): TransactionCosts + IS/OOS split (v0.1.13.3)
  v0.1.0 (2026-05-17): Initial round-trip backtest (v0.1.13.2)
"""
from __future__ import annotations

import argparse
import sys
from datetime import date as date_type
from datetime import datetime

from backtest.round_trip import (
    NO_COSTS,
    RoundTripBacktest,
    TransactionCosts,
    compute_metrics,
    partition_by_date,
)
from data.database import init_schema
from strategies.exit.base import Position
from strategies.trend_breakout import TrendBreakoutStrategy


def fmt_pct(v: float, dec: int = 2, signed: bool = False) -> str:
    if v == float("inf"):
        return "  ∞"
    sign = "+" if signed else ""
    return f"{v:{sign}.{dec}f}%"


def print_metrics_block(label: str, trades: list[Position], costs: TransactionCosts) -> None:
    """Print one column of metrics (used for IS or OOS)."""
    gross = compute_metrics(trades, NO_COSTS)
    net = compute_metrics(trades, costs)
    if gross.n_trades == 0:
        print(f"\n[{label}] (no trades)\n")
        return

    print(f"\n{'─'*72}")
    print(f"[{label}]  n_trades={gross.n_trades}")
    print(f"{'─'*72}")
    print(f"  {'Metric':<28s} {'Gross':>16s} {'Net':>16s}")
    print(f"  {'-'*28} {'-'*16} {'-'*16}")
    rows = [
        ("Win rate",        f"{gross.win_rate:>14.1f}%",  f"{net.win_rate:>14.1f}%"),
        ("Mean return",     fmt_pct(gross.mean_return, signed=True),
                            fmt_pct(net.mean_return, signed=True)),
        ("Median return",   fmt_pct(gross.median_return, signed=True),
                            fmt_pct(net.median_return, signed=True)),
        ("Best trade",      fmt_pct(gross.best_return, signed=True),
                            fmt_pct(net.best_return, signed=True)),
        ("Worst trade",     fmt_pct(gross.worst_return, signed=True),
                            fmt_pct(net.worst_return, signed=True)),
        ("Avg win",         fmt_pct(gross.avg_win, signed=True),
                            fmt_pct(net.avg_win, signed=True)),
        ("Avg loss",        fmt_pct(gross.avg_loss, signed=True),
                            fmt_pct(net.avg_loss, signed=True)),
        ("Win/Loss ratio",  f"{gross.win_loss_ratio:>15.2f}",
                            f"{net.win_loss_ratio:>15.2f}"),
        ("Profit factor",   f"{gross.profit_factor:>15.2f}",
                            f"{net.profit_factor:>15.2f}"),
        ("Avg holding days",f"{gross.avg_holding_days:>15.1f}",
                            f"{net.avg_holding_days:>15.1f}"),
    ]
    for label_row, g, n in rows:
        print(f"  {label_row:<28s} {g:>16s} {n:>16s}")

    print(f"  {'-'*28} {'-'*16} {'-'*16}")
    print(f"  {'Avg MFE':<28s} {fmt_pct(gross.avg_mfe, signed=True):>16s}  (unrealized, no cost)")
    print(f"  {'Avg MAE':<28s} {fmt_pct(gross.avg_mae, signed=True):>16s}  (unrealized, no cost)")

    # Exit reasons
    print("\n  Exit reasons:")
    total = sum(gross.exit_reasons.values())
    for reason, n in sorted(gross.exit_reasons.items(), key=lambda x: -x[1]):
        pct = n / total * 100
        print(f"    {reason:<22s} {n:>3d} ({pct:>5.1f}%)")


def verdict(
    oos_net,  # RoundTripMetrics
    oos_trades: list[Position],
) -> tuple[str, list[str]]:
    """User-spec verdict (PASS / STRONG PASS / FAIL).

    STRONG PASS: OOS net mean > 1.0%, net PF > 1.7, win/loss > 1.5
    PASS:        OOS net mean > 0, net PF > 1.3, crisis leak = 0, sufficient trades
    FAIL:        其他
    """
    notes: list[str] = []
    n = oos_net.n_trades
    mean = oos_net.mean_return
    pf = oos_net.profit_factor
    wlr = oos_net.win_loss_ratio
    crisis_n = sum(1 for t in oos_trades if t.regime_at_entry == "crisis")
    sufficient = n >= 30  # 至少 30 trades 才有 statistical power

    # FAIL conditions (any of these → FAIL)
    if not sufficient:
        notes.append(f"⚠ Trades 太少 (n={n} < 30) — statistical power 不足")
        return "⚠ FAIL (insufficient sample)", notes
    if crisis_n > 0:
        notes.append(f"⚠ Crisis leakage: {crisis_n} trades 在 crisis regime 進場")
        return "⚠ FAIL (regime gate broken)", notes
    if mean <= 0:
        notes.append(f"⚠ OOS net mean return {mean:+.2f}% (must be > 0)")
        return "⚠ FAIL (negative expectancy)", notes
    if pf < 1.3:
        notes.append(f"⚠ OOS net profit factor {pf:.2f} (must be > 1.3)")
        return "⚠ FAIL (insufficient edge after cost)", notes

    # PASS criteria met. Check STRONG PASS:
    notes.append(f"✓ n={n} ≥ 30 (sufficient)")
    notes.append("✓ crisis leakage = 0")
    notes.append(f"✓ OOS net mean {mean:+.2f}% > 0")
    notes.append(f"✓ OOS net profit factor {pf:.2f} > 1.3")

    if mean > 1.0 and pf > 1.7 and wlr > 1.5:
        notes.append(
            f"✓✓ STRONG: mean {mean:+.2f}% > 1.0%, PF {pf:.2f} > 1.7, W/L {wlr:.2f} > 1.5"
        )
        return "✓✓ STRONG PASS", notes
    return "✓ PASS", notes


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Round-trip backtest (TrendBreakout v1) with cost + IS/OOS split"
    )
    parser.add_argument("--symbols", type=str, help="逗號分隔 (預設全部)")
    parser.add_argument("--export-csv", type=str, help="輸出 trades CSV 路徑")

    # Costs (台股 default)
    parser.add_argument("--commission", type=float, default=0.001425,
                        help="commission rate per side (default 0.1425%%)")
    parser.add_argument("--sell-tax", type=float, default=0.003,
                        help="sell tax rate (default 0.3%%)")
    parser.add_argument("--slippage", type=float, default=0.0,
                        help="slippage per side (default 0%%, set ~0.001 for realistic)")
    parser.add_argument("--no-costs", action="store_true",
                        help="gross only, ignore cost params")

    # IS/OOS
    parser.add_argument("--is-end", type=str, default=None,
                        help="IS 結束日 (YYYY-MM-DD). 若給, 跑 IS vs OOS side-by-side")

    args = parser.parse_args()
    init_schema()

    costs = (
        NO_COSTS if args.no_costs
        else TransactionCosts(args.commission, args.sell_tax, args.slippage)
    )

    print(f"Helios run_backtest — {datetime.now().isoformat(timespec='seconds')}")
    print(
        "Strategy: trend_breakout_v1  |  "
        "Exit: RegimeExit(priority=1) → TrailingStop(2*ATR)"
    )
    print(f"Costs: {costs.describe()}")
    if args.is_end:
        print(f"Split: IS ≤ {args.is_end} < OOS")
    print()

    symbols = (
        [s.strip() for s in args.symbols.split(",") if s.strip()]
        if args.symbols else None
    )

    # Run backtest once on full history
    t0 = datetime.now()
    bt = RoundTripBacktest(
        strategy=TrendBreakoutStrategy(),
        symbols=symbols,
    )
    print("Running backtest (preload + signal gen + lifecycle)...")
    trades = bt.run()
    elapsed = (datetime.now() - t0).total_seconds()
    print(f"  → {len(trades)} completed trades in {elapsed:.1f}s")

    if not trades:
        print("\n⚠ No completed trades")
        return 0

    # If IS/OOS split requested, partition trades
    if args.is_end:
        is_end = date_type.fromisoformat(args.is_end)
        is_trades, oos_trades = partition_by_date(trades, is_end)
        print("\nPartition by entry_date:")
        print(f"  IS  trades (entry ≤ {is_end}): {len(is_trades)}")
        print(f"  OOS trades (entry  > {is_end}): {len(oos_trades)}")

        print_metrics_block("IN-SAMPLE", is_trades, costs)
        print_metrics_block("OUT-OF-SAMPLE", oos_trades, costs)

        # Verdict on OOS net
        oos_net = compute_metrics(oos_trades, costs)
        result, notes = verdict(oos_net, oos_trades)
        print(f"\n{'='*72}")
        print(f"VERDICT (on OOS net): {result}")
        print(f"{'='*72}")
        for note in notes:
            print(f"  {note}")
    else:
        # Single-period full-history
        print_metrics_block("FULL HISTORY", trades, costs)

    # Symbol distribution (always show)
    print(f"\n{'─'*72}")
    print("By entry regime (full history):")
    by_regime: dict[str, list[Position]] = {}
    for t in trades:
        by_regime.setdefault(t.regime_at_entry, []).append(t)
    for r, ts in sorted(by_regime.items(), key=lambda x: -len(x[1])):
        gross_r = sum(t.gross_return_pct for t in ts if t.gross_return_pct is not None) / len(ts)
        net_r = gross_r - costs.total_round_trip_pct
        print(f"  {r:<10s} n={len(ts):<3d}  gross_mean={fmt_pct(gross_r, signed=True)}  "
              f"net_mean={fmt_pct(net_r, signed=True)}")

    if args.export_csv:
        df = bt.trades_to_polars()
        df.write_csv(args.export_csv)
        print(f"\n✓ Exported {df.height} trades to {args.export_csv}")

    print(f"\n{'='*72}")
    print("✓ Run complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
