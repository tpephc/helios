#!/usr/bin/env python3
"""scripts/backtest_ma5_strategy.py  — v2

Backtest: MA5 momentum / trend-exhaustion strategy.

Entry rule
----------
Signal fires on day T when:
    close[T] / close[T-1] > 1.05  AND  close[T] > open[T]

All state transitions are decided at close[T] but EXECUTED at open[T+1].
Overnight risk between T and T+1 always reflects the PRE-transition position.

Accounting
----------
Uses cash-flow accounting normalised to initial entry price P0:

    entry (1.0 units @ P0):           cash_flow = -1.0
    partial sell (s units @ P):        cash_flow = +s × P/P0
    partial buy  (s units @ P):        cash_flow = -s × P/P0  [new lot tracked]
    final exit   (remaining @ P):      cash_flow = +lots_value(P/P0)

    net_return = sum(cash_flows) + transaction_costs

Lot accounting uses FIFO. Each lot tracks its own cost_basis/P0.
This correctly handles:
    FULL → HALF → FULL → exit   (multiple partial sell/rebuy cycles)

State machine
-------------
States: FLAT (0.0), FULL (1.0), HALF (0.5)

Transitions (all PENDING at close[T], EXECUTED at open[T+1]):

  FLAT  → FULL   Entry signal AND gap OK
  FULL  → HALF   Rule 3: ext_score = (close − MA5) / ATR14 ≥ ext_threshold
  FULL  → HALF   Rule 4: close < MA5
  HALF  → FULL   Rule 3 recovery: ext_score < ext_threshold AND close ≥ MA5
  HALF  → FULL   Rule 4 recovery: close ≥ MA5
  HALF  → FLAT   Rule 5: 3 consecutive closes below MA5 (FULL exit)

Rules 3 and 4 are checked in that order; Rule 3 takes priority.
Recovery checks both conditions: the half position is restored as soon as
close ≥ MA5 AND (if triggered by Rule 3) extension is no longer excessive.

Transaction costs (Taiwan)
--------------------------
  Buy  : statutory 0.1425%  + slippage_bps (default 10 bps)
  Sell : statutory 0.1425% + 0.30% tax + slippage_bps

Overnight gap protection
------------------------
  Entry skipped if (open[T+1] − close[T]) / close[T] > max_entry_gap_pct (default 3%).
  Evaluated at execution time (T+1 open), so no look-ahead.

Usage
-----
    uv run python scripts/backtest_ma5_strategy.py
    uv run python scripts/backtest_ma5_strategy.py --ext-threshold 2.5 --slippage-bps 20
    uv run python scripts/backtest_ma5_strategy.py --symbols 2330,2455,2891
    uv run python scripts/backtest_ma5_strategy.py --max-entry-gap 2.0 --slippage-bps 30
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date as date_type

import polars as pl

from data.database import connect, init_schema
from utils.logger import get_logger

logger = get_logger(__name__)

# ── Statutory costs ──────────────────────────────────────────────────────────
COMMISSION = 0.001425
SELL_TAX   = 0.003


# ── Lot / Trade records ──────────────────────────────────────────────────────

@dataclass
class Lot:
    """Single purchase lot, expressed relative to initial entry price P0.

    cost_ratio = lot_purchase_price / P0  (== 1.0 for the first lot)
    """
    size: float        # units held (0.5 or 1.0)
    cost_ratio: float  # purchase_price / P0


@dataclass
class Trade:
    symbol: str
    entry_date: date_type
    entry_price: float
    exit_date: date_type
    exit_price: float
    net_return: float        # cash-flow-based, after all costs
    gross_return: float      # without transaction costs
    avg_exposure: float      # average position held (0.5–1.0)
    hold_days: int
    exit_reason: str
    regime_at_entry: str = "unknown"

    @property
    def is_win(self) -> bool:
        return self.net_return > 0

    @property
    def exposure_adjusted_return(self) -> float:
        """Return / avg_exposure: fair comparison across position sizes."""
        return self.net_return / self.avg_exposure if self.avg_exposure > 0 else 0.0


# ── Feature computation ──────────────────────────────────────────────────────

def _compute_features(df: pl.DataFrame) -> pl.DataFrame:
    """Vectorised: MA5, ATR14, extension_score, entry_signal."""
    df = df.with_columns(
        pl.col("adj_close").rolling_mean(5).alias("ma5"),
    )
    prev_close = pl.col("adj_close").shift(1)
    tr = pl.max_horizontal(
        pl.col("adj_high") - pl.col("adj_low"),
        (pl.col("adj_high") - prev_close).abs(),
        (pl.col("adj_low")  - prev_close).abs(),
    )
    df = df.with_columns(tr.alias("true_range"))
    df = df.with_columns(
        pl.col("true_range").rolling_mean(14).alias("atr14"),
    )
    df = df.with_columns(
        ((pl.col("adj_close") - pl.col("ma5")) / pl.col("atr14"))
        .alias("extension_score")
    )
    prev_close2 = pl.col("adj_close").shift(1)
    df = df.with_columns(
        (
            (pl.col("adj_close") / prev_close2 > 1.05) &
            (pl.col("adj_close") > pl.col("adj_open"))
        ).alias("entry_signal")
    )
    return df


# ── Cash-flow accounting helpers ─────────────────────────────────────────────

def _lots_value(lots: list[Lot], price_ratio: float) -> float:
    """Mark-to-market value of all lots at price_ratio (= price / P0)."""
    return sum(lot.size * price_ratio for lot in lots)


def _lots_cost(lots: list[Lot]) -> float:
    """Total cash invested in current lots (as fraction of P0 notional)."""
    return sum(lot.size * lot.cost_ratio for lot in lots)


def _sell_lots_fifo(
    lots: list[Lot],
    sell_size: float,
    price_ratio: float,
) -> tuple[float, float]:
    """FIFO sell. Returns (cash_received, gross_pnl) both as fraction of P0.

    cash_received = sell_size × price_ratio
    gross_pnl     = sum over sold lots of: qty × (price_ratio - lot.cost_ratio)
    """
    cash_received = sell_size * price_ratio
    gross_pnl = 0.0
    remaining = sell_size
    while remaining > 1e-9 and lots:
        lot = lots[0]
        qty = min(remaining, lot.size)
        gross_pnl += qty * (price_ratio - lot.cost_ratio)
        remaining -= qty
        if qty >= lot.size - 1e-9:
            lots.pop(0)
        else:
            lots[0] = Lot(lot.size - qty, lot.cost_ratio)
    return cash_received, gross_pnl


# ── State machine simulator ──────────────────────────────────────────────────

def _simulate_symbol(
    rows: list[dict],
    ext_threshold: float,
    regime_map: dict[date_type, str],
    max_entry_gap: float,
    buy_cost_rate: float,
    sell_cost_rate: float,
    allowed_regimes: set[str] | None = None,
) -> list[Trade]:
    """Simulate the 5-rule MA5 strategy with correct pending-transition semantics.

    Key invariant: position changes happen at open[T+1], not at close[T].
    Between close[T] and open[T+1], the position is still the PRE-signal size.
    """
    trades: list[Trade] = []

    # ── Position state ───────────────────────────────────────────────────────
    lots: list[Lot] = []           # current open lots (FIFO)
    entry_date: date_type | None = None
    entry_price = 0.0              # P0: first lot's actual price (for recording)

    # ── Pending transition (decided at close[T], executes at open[T+1]) ─────
    # Possible values: None | "entry" | "reduce" | "restore" | "exit"
    pending: str | None = None
    pending_exit_reason: str = ""

    # ── Per-trade accumulators ───────────────────────────────────────────────
    cumulative_cash: float = 0.0   # net cash flows (buys are negative)
    cumulative_cost: float = 0.0   # total cost drag
    cumulative_gross_pnl: float = 0.0
    exposure_days: float = 0.0     # sum of daily position sizes (for avg_exposure)
    days_held: int = 0

    # ── Rule 5 counter ───────────────────────────────────────────────────────
    consecutive_below_ma5: int = 0
    half_reason: str = ""          # "above" (Rule3) | "below" (Rule4)

    n = len(rows)

    def current_position() -> float:
        return sum(lot.size for lot in lots)

    def _close_trade(exit_date: date_type, exit_price_val: float, reason: str) -> None:
        """Finalise trade, append to trades list, reset state."""
        nonlocal cumulative_cash, cumulative_cost, cumulative_gross_pnl
        nonlocal exposure_days, days_held, consecutive_below_ma5, half_reason

        pos = current_position()
        if pos <= 0:
            return
        p_ratio = exit_price_val / entry_price
        cash_recv, gpnl = _sell_lots_fifo(lots, pos, p_ratio)
        sell_c = pos * sell_cost_rate
        cumulative_cash    += cash_recv
        cumulative_cost    += sell_c
        cumulative_gross_pnl += gpnl

        net = cumulative_cash - cumulative_cost
        avg_exp = exposure_days / max(days_held, 1)
        trades.append(Trade(
            symbol=rows[0].get("stock_id", "?"),
            entry_date=entry_date,
            entry_price=entry_price,
            exit_date=exit_date,
            exit_price=exit_price_val,
            net_return=net,
            gross_return=cumulative_gross_pnl,
            avg_exposure=avg_exp,
            hold_days=days_held,
            exit_reason=reason,
            regime_at_entry=regime_map.get(entry_date, "unknown"),
        ))
        # Reset
        cumulative_cash = 0.0
        cumulative_cost = 0.0
        cumulative_gross_pnl = 0.0
        exposure_days = 0.0
        days_held = 0
        consecutive_below_ma5 = 0
        half_reason = ""

    # ── Main loop ────────────────────────────────────────────────────────────
    for i, row in enumerate(rows):
        ma5   = row["ma5"]
        atr   = row["atr14"]
        ext   = row["extension_score"]
        close = row["adj_close"]
        today_open = row["adj_open"]
        signal = row["entry_signal"]
        today  = row["date"]
        has_next = (i + 1 < n)

        # ── Step 1: execute pending transition at today's open ────────────
        if pending is not None:
            pos = current_position()
            if pending == "entry":
                # Gap check: was the overnight gap acceptable?
                prev_close = rows[i - 1]["adj_close"] if i > 0 else today_open
                gap = (today_open - prev_close) / prev_close if prev_close > 0 else 0.0
                if gap <= max_entry_gap and pos == 0.0:
                    # Execute entry
                    entry_price = today_open
                    entry_date = today
                    p_ratio = 1.0  # first lot always at cost_ratio=1.0
                    lots.append(Lot(1.0, 1.0))
                    buy_c = 1.0 * buy_cost_rate
                    cumulative_cash -= 1.0   # invested 1.0 unit of P0 notional
                    cumulative_cost += buy_c
                pending = None

            elif pending == "reduce" and pos > 0.5:
                # Sell 0.5 at today's open
                p_ratio = today_open / entry_price
                cash_recv, gpnl = _sell_lots_fifo(lots, 0.5, p_ratio)
                sell_c = 0.5 * sell_cost_rate
                cumulative_cash     += cash_recv
                cumulative_cost     += sell_c
                cumulative_gross_pnl += gpnl
                pending = None

            elif pending == "restore" and pos < 1.0:
                # Buy back 0.5 at today's open
                p_ratio = today_open / entry_price
                lots.append(Lot(0.5, p_ratio))
                buy_c = 0.5 * buy_cost_rate
                cumulative_cash -= 0.5 * p_ratio
                cumulative_cost += buy_c
                pending = None

            elif pending == "exit" and pos > 0:
                _close_trade(today, today_open, pending_exit_reason)
                pending = None

        pos = current_position()

        if ma5 is None or atr is None or atr <= 0:
            continue

        # ── Step 2: accumulate exposure and below-MA5 counter ─────────────
        if pos > 0:
            days_held += 1
            exposure_days += pos
            if close < ma5:
                consecutive_below_ma5 += 1
            else:
                consecutive_below_ma5 = 0

        # ── Step 3: decide next pending action ────────────────────────────
        if not has_next:
            # End of data — force close at today's close
            if pos > 0:
                _close_trade(today, close, "data_end")
            continue

        if pos > 0:
            # Rule 5: 3 consecutive below MA5 → full exit (pending)
            if consecutive_below_ma5 >= 3:
                pending = "exit"
                pending_exit_reason = "rule5_3days_below_ma5"
                continue

            # Rule 3: extension excessive → reduce (pending)
            if pos > 0.5 and ext >= ext_threshold:
                pending = "reduce"
                half_reason = "above"
                continue

            # Rule 4: close below MA5 → reduce (pending)
            if pos > 0.5 and close < ma5:
                pending = "reduce"
                half_reason = "below"
                continue

            # Recovery from HALF
            if pos == 0.5:
                recover = (
                    (half_reason == "above" and ext < ext_threshold and close >= ma5)
                    or (half_reason == "below" and close >= ma5)
                )
                if recover:
                    pending = "restore"
                    half_reason = ""

        else:
            # No position: check entry signal
            entry_regime = regime_map.get(today, "unknown")
            regime_ok = allowed_regimes is None or entry_regime in allowed_regimes
            if signal and regime_ok:
                pending = "entry"

    return trades


# ── Main ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MA5 strategy backtest v2")
    parser.add_argument("--ext-threshold", type=float, default=2.0,
                        help="ATR-normalised extension for Rule 3 (default 2.0)")
    parser.add_argument("--max-entry-gap", type=float, default=3.0,
                        help="skip entry if gap-up > N%% at T+1 open (default 3.0)")
    parser.add_argument("--slippage-bps", type=float, default=10.0,
                        help="one-way slippage in basis points (default 10)")
    parser.add_argument("--symbols", type=str, default=None,
                        help="comma-separated symbols (default: all)")
    parser.add_argument("--start", type=str, default="2021-05-21")
    parser.add_argument("--end",   type=str, default=None)
    parser.add_argument("--regime", type=str, default=None,
                        help="only enter in these regimes, comma-sep (e.g. bull or bull,crisis)")
    args = parser.parse_args(argv)

    slip = args.slippage_bps / 10000
    buy_cost_rate  = COMMISSION + slip
    sell_cost_rate = COMMISSION + SELL_TAX + slip

    init_schema()

    sym_filter = (
        f"AND stock_id IN ({','.join(repr(s) for s in args.symbols.split(','))})"
        if args.symbols else ""
    )
    end_filter = f"AND date <= '{args.end}'" if args.end else ""

    print(f"Loading price data from {args.start} ...")
    with connect(read_only=True) as conn:
        df = conn.execute(f"""
            SELECT stock_id, date, adj_open, adj_high, adj_low, adj_close
            FROM daily_price_adj
            WHERE date >= '{args.start}' {end_filter} {sym_filter}
            ORDER BY stock_id, date
        """).pl()

    if df.is_empty():
        print("No data found.")
        return 1

    symbols = df["stock_id"].unique().to_list()
    print(f"Symbols: {len(symbols)}, rows: {len(df):,}")

    with connect(read_only=True) as conn:
        regime_df = conn.execute(
            "SELECT date, regime FROM market_regime ORDER BY date"
        ).pl()
    regime_map: dict[date_type, str] = {
        row["date"]: row["regime"]
        for row in regime_df.iter_rows(named=True)
    }

    allowed_regimes: set[str] | None = (
        set(args.regime.split(",")) if args.regime else None
    )

    all_trades: list[Trade] = []
    for sym in sorted(symbols):
        sub = df.filter(pl.col("stock_id") == sym).sort("date")
        sub = _compute_features(sub)
        rows = sub.to_dicts()
        trades = _simulate_symbol(
            rows,
            ext_threshold=args.ext_threshold,
            regime_map=regime_map,
            max_entry_gap=args.max_entry_gap / 100,
            buy_cost_rate=buy_cost_rate,
            sell_cost_rate=sell_cost_rate,
            allowed_regimes=allowed_regimes,
        )
        all_trades.extend(trades)

    if not all_trades:
        print("No trades generated.")
        return 0

    n = len(all_trades)
    wins   = [t for t in all_trades if t.is_win]
    losses = [t for t in all_trades if not t.is_win]

    win_rate = len(wins) / n
    avg_ret  = sum(t.net_return for t in all_trades) / n
    avg_win  = sum(t.net_return for t in wins)  / max(len(wins),  1)
    avg_loss = sum(t.net_return for t in losses) / max(len(losses), 1)
    avg_hold = sum(t.hold_days  for t in all_trades) / n
    avg_exp  = sum(t.avg_exposure for t in all_trades) / n
    avg_exp_adj = sum(t.exposure_adjusted_return for t in all_trades) / n

    win_pnl  = sum(t.net_return for t in wins)
    loss_pnl = abs(sum(t.net_return for t in losses))
    profit_factor = win_pnl / max(loss_pnl, 1e-9)

    hdr = f"  MA5 Backtest v2 — ext={args.ext_threshold} gap={args.max_entry_gap}% slip={args.slippage_bps}bps"
    sep = "=" * max(56, len(hdr) + 2)
    print(f"\n{sep}")
    print(hdr)
    print(f"  Period: {args.start} → {args.end or 'latest'} | Symbols: {len(symbols)}")
    print(sep)
    print(f"  Total trades:          {n:>6,}")
    print(f"  Win rate:              {win_rate:>6.1%}")
    print(f"  Avg net return:        {avg_ret:>+7.2%}  per trade")
    print(f"  Avg winner:            {avg_win:>+7.2%}")
    print(f"  Avg loser:             {avg_loss:>+7.2%}")
    print(f"  Profit factor:         {profit_factor:>6.2f}")
    print(f"  Avg hold days:         {avg_hold:>6.1f}")
    print(f"  Avg exposure:          {avg_exp:>6.2f}  (1.0=always full)")
    print(f"  Exposure-adj return:   {avg_exp_adj:>+7.2%}  (net_return / avg_exposure)")
    print("─" * 56)
    for regime in ["bull", "neutral", "bear", "crisis"]:
        rt = [t for t in all_trades if t.regime_at_entry == regime]
        if not rt:
            continue
        wr = sum(1 for t in rt if t.is_win) / len(rt)
        ar = sum(t.net_return for t in rt) / len(rt)
        print(f"  {regime:<8}  n={len(rt):>4}  win={wr:.0%}  avg={ar:>+.2%}")
    print("─" * 56)
    for reason, cnt in Counter(t.exit_reason for t in all_trades).most_common():
        rt = [t for t in all_trades if t.exit_reason == reason]
        ar = sum(t.net_return for t in rt) / len(rt)
        wr = sum(1 for t in rt if t.is_win) / len(rt)
        print(f"  {reason:<30}  n={cnt:>4}  win={wr:.0%}  avg={ar:>+.2%}")
    print(sep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
