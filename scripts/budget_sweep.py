#!/usr/bin/env python3
# scripts/budget_sweep.py
"""F experiment — sweep budget configurations to find optimal CAGR / DD trade-off.

對照 v0.1.14.1 default (max_pos=5, per_pos=20%, etf=40%, sector=30%, cash=10%):
  - 是否 max_pos=3 with per_pos=30% 能提高 CAGR (concentrated bet)?
  - 是否 max_pos=4 with per_pos=22% 是 sweet spot (cash buffer 剛好 binding 在 4)?
  - 較寬鬆 sector cap 35% 會不會 unlock 更多 alpha?

執行:
  uv run python scripts/budget_sweep.py --is-end 2023-12-31

  # 加 slippage 看 robustness:
  uv run python scripts/budget_sweep.py --is-end 2023-12-31 --slippage 0.001

每個 config 跑同一條 backtest, 輸出 side-by-side 表格.
~5 個 config × ~45s = ~4 minutes total.

Version: v0.1.0 (2026-05-17)
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime

from backtest.portfolio_simulator import (
    PortfolioBacktest,
    compute_portfolio_metrics,
)
from backtest.round_trip import TransactionCosts
from data.database import init_schema
from portfolio.risk_budget import RiskBudget
from strategies.trend_breakout import TrendBreakoutStrategy


@dataclass(frozen=True)
class BudgetConfig:
    """Named budget configuration to compare."""
    name: str
    max_positions: int
    per_position_pct: float
    max_etf_pct: float
    max_sector_pct: float
    cash_buffer_pct: float

    def to_budget(self) -> RiskBudget:
        return RiskBudget(
            max_positions=self.max_positions,
            per_position_pct=self.per_position_pct,
            max_etf_exposure_pct=self.max_etf_pct,
            max_sector_exposure_pct=self.max_sector_pct,
            cash_buffer_pct=self.cash_buffer_pct,
        )

    def short_desc(self) -> str:
        return (
            f"pos={self.max_positions} x{self.per_position_pct*100:.0f}%  "
            f"etf<{self.max_etf_pct*100:.0f}%  "
            f"sec<{self.max_sector_pct*100:.0f}%  "
            f"cash>{self.cash_buffer_pct*100:.0f}%"
        )


# Configurations to sweep
SWEEP_CONFIGS: list[BudgetConfig] = [
    BudgetConfig("CURRENT", 5, 0.20, 0.40, 0.30, 0.10),
    BudgetConfig("CONCENTRATED", 3, 0.30, 0.40, 0.30, 0.10),
    BudgetConfig("EFFECTIVE-4", 4, 0.22, 0.40, 0.30, 0.10),
    BudgetConfig("WIDER", 5, 0.18, 0.50, 0.35, 0.10),
    BudgetConfig("NO-ETF-CAP", 5, 0.20, 1.00, 0.30, 0.10),
]


def fmt(v: float, dec: int = 2, signed: bool = False, suffix: str = "") -> str:
    sign = "+" if signed else ""
    return f"{v:{sign}.{dec}f}{suffix}"


def run_one(
    cfg: BudgetConfig, costs: TransactionCosts, capital: float,
    is_end: date_type | None,
) -> dict:
    """Run one config, return summary dict."""
    bt = PortfolioBacktest(
        strategy=TrendBreakoutStrategy(),
        initial_capital=capital,
        budget=cfg.to_budget(),
        costs=costs,
    )
    bt.run()

    if not bt.equity_curve:
        return {"name": cfg.name, "error": "no_equity_curve"}

    # Full metrics
    full = compute_portfolio_metrics(
        bt.equity_curve, bt.completed_trades, bt.signal_decisions, capital,
    )

    # OOS partition if requested
    oos = None
    if is_end:
        oos_curve = [s for s in bt.equity_curve if s.date > is_end]
        oos_trades = [
            t for t in bt.completed_trades
            if t.entry_date is not None and t.entry_date > is_end
        ]
        oos_decisions = [d for d in bt.signal_decisions if d.date > is_end]
        is_curve = [s for s in bt.equity_curve if s.date <= is_end]
        oos_initial = is_curve[-1].equity if is_curve else capital
        oos = compute_portfolio_metrics(
            oos_curve, oos_trades, oos_decisions, oos_initial,
        )

    return {
        "name": cfg.name,
        "cfg": cfg,
        "full": full,
        "oos": oos,
        "n_trades": len(bt.completed_trades),
        "n_decisions": len(bt.signal_decisions),
    }


def print_table(results: list[dict], focus: str = "oos") -> None:
    """Print side-by-side comparison."""
    label = "OUT-OF-SAMPLE" if focus == "oos" else "FULL HISTORY"
    print(f"\n{'='*100}")
    print(f"BUDGET SWEEP — {label}")
    print(f"{'='*100}\n")

    headers = ["Config", "CAGR", "Total Return", "Max DD", "PF", "Win%",
               "AvgExp%", "Trades", "Rejected%"]
    widths = [14, 8, 13, 9, 7, 7, 8, 7, 11]
    print("  ".join(f"{h:<{w}s}" for h, w in zip(headers, widths, strict=False)))
    print("  ".join("-" * w for w in widths))

    for r in results:
        if "error" in r:
            print(f"{r['name']:<14s}  ERROR: {r['error']}")
            continue
        m = r[focus]
        if m is None:
            continue
        reject_pct = m.n_signals_rejected / max(m.n_signals_seen, 1) * 100
        row = [
            r["name"],
            fmt(m.cagr_pct, signed=True, suffix="%"),
            fmt(m.total_return_pct, signed=True, suffix="%"),
            fmt(m.max_drawdown_pct, signed=True, suffix="%"),
            fmt(m.profit_factor, dec=2),
            fmt(m.win_rate, dec=1, suffix="%"),
            fmt(m.avg_exposure_pct, dec=1, suffix="%"),
            f"{m.n_trades}",
            fmt(reject_pct, dec=1, suffix="%"),
        ]
        print("  ".join(f"{c:<{w}s}" for c, w in zip(row, widths, strict=False)))

    print("\nConfig details:")
    for r in results:
        if "cfg" in r:
            print(f"  {r['name']:<14s}  {r['cfg'].short_desc()}")


def print_reject_dist(results: list[dict]) -> None:
    """Show reject reason variation across configs."""
    print(f"\n{'-'*100}")
    print("Reject reason distribution (OOS):")
    print(f"{'-'*100}")
    reasons_seen = set()
    for r in results:
        if r.get("oos") and r["oos"].reject_reasons:
            reasons_seen.update(r["oos"].reject_reasons.keys())

    header = ["Config", *sorted(reasons_seen)]
    widths = [14, *([22] * len(sorted(reasons_seen)))]
    print("  ".join(f"{h:<{w}s}" for h, w in zip(header, widths, strict=False)))
    print("  ".join("-" * w for w in widths))

    for r in results:
        if "error" in r or not r.get("oos"):
            continue
        m = r["oos"]
        total = max(sum(m.reject_reasons.values()), 1)
        row = [r["name"]]
        for reason in sorted(reasons_seen):
            n = m.reject_reasons.get(reason, 0)
            row.append(f"{n} ({n/total*100:.1f}%)" if n else "—")
        print("  ".join(f"{c:<{w}s}" for c, w in zip(row, widths, strict=False)))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Budget configuration sweep (v0.1.14.1 F experiment)"
    )
    parser.add_argument("--capital", type=float, default=1_000_000.0)
    parser.add_argument("--is-end", type=str, default="2023-12-31")
    parser.add_argument("--commission", type=float, default=0.001425)
    parser.add_argument("--sell-tax", type=float, default=0.003)
    parser.add_argument("--slippage", type=float, default=0.0)

    args = parser.parse_args()
    init_schema()

    is_end = date_type.fromisoformat(args.is_end) if args.is_end else None
    costs = TransactionCosts(args.commission, args.sell_tax, args.slippage)

    print(f"Helios budget_sweep — {datetime.now().isoformat(timespec='seconds')}")
    print(f"Capital: NTD {args.capital:,.0f}")
    print(f"Costs:   {costs.describe()}")
    if is_end:
        print(f"Split:   IS ≤ {is_end} < OOS")
    print(f"Configs: {len(SWEEP_CONFIGS)} ({', '.join(c.name for c in SWEEP_CONFIGS)})")

    results = []
    for i, cfg in enumerate(SWEEP_CONFIGS, 1):
        t0 = datetime.now()
        print(f"\n[{i}/{len(SWEEP_CONFIGS)}] {cfg.name}: {cfg.short_desc()}")
        result = run_one(cfg, costs, args.capital, is_end)
        elapsed = (datetime.now() - t0).total_seconds()
        if "error" in result:
            print(f"  ⚠ {result['error']}")
        else:
            oos_pf = result["oos"].profit_factor if result["oos"] else "—"
            print(
                f"  → {result['n_trades']} trades, "
                f"OOS PF={oos_pf if isinstance(oos_pf, str) else f'{oos_pf:.2f}'}  "
                f"({elapsed:.1f}s)"
            )
        results.append(result)

    # Print comparison
    print_table(results, focus="oos")
    if is_end:
        print_table(results, focus="full")
    print_reject_dist(results)

    # Recommendation hint
    print(f"\n{'='*100}")
    print("Hints for picking a config:")
    print("  - Highest OOS CAGR + acceptable Max DD = best risk-adjusted")
    print("  - Lowest Max DD = most conservative")
    print("  - Highest avg exposure = capital efficiency (less lazy cash)")
    print("  - PF still matters but 4+ is already extreme strong — diminishing returns")
    print(f"{'='*100}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
