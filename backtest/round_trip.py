# backtest/round_trip.py
"""Round-trip backtest engine — first complete deterministic trade lifecycle.

Reviewer §53: 「v0.1.13.2 不是 production trading engine, 是第一個完整
deterministic trade lifecycle.」

Simulation flow (close-based, 無 look-ahead):
  For each trading date d (chronological):
    1. Update open positions' running stats with adj_close[d]
    2. Check exit rules (priority order: RegimeExit → TrailingStop)
       → 若 fire, exit at close[d]
    3. Open new positions from strategy signals fired at close[d]
       (一個 symbol 同時只開一個 position; 重複訊號忽略)

End of simulation:
  - 強制結算剩餘 open positions (exit_reason='end_of_backtest')
  - 計算 reviewer §50 全部 metrics

Metrics output:
  - win_rate / mean_return / median_return / best / worst
  - profit_factor (winners $ / losers $)
  - win_loss_ratio (avg_win / |avg_loss|)
  - avg_mfe / avg_mae (reviewer §50)
  - avg_holding_days
  - exit_reason distribution (regime_exit_share vs trailing_stop_share)
  - by_regime_at_entry (alpha decomposition prep)

Version: v0.1.1 (2026-05-17)
Changelog:
  v0.1.1 (2026-05-17): TransactionCosts + IS/OOS partition support (v0.1.13.3)
  v0.1.0 (2026-05-17): Initial — close-based round-trip simulation
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date as date_type
from typing import Any

import polars as pl

from data.database import connect
from strategies.base import Signal, Strategy
from strategies.exit.base import ExitRule, Position
from strategies.exit.regime_exit import RegimeExit
from strategies.exit.trailing_stop import TrailingStop

# ─────────────────────────────────────────────────────────────
# Transaction costs (v0.1.13.3)
# ─────────────────────────────────────────────────────────────


@dataclass
class TransactionCosts:
    """Taiwan stock market default rates (per-side as fractions, 不是 %).

    台股實際:
      commission   0.1425% per side (買 + 賣 各一次)
      sell_tax     0.3% (證交稅, 只賣方)
      slippage     0.05%~0.10% per side (market order spread, 預設 0)

    Total round-trip = 2*commission + sell_tax + 2*slippage
                     ≈ 0.585% (no slippage) ~ 0.785% (0.1% slippage)
    """
    commission_rate: float = 0.001425
    sell_tax_rate: float = 0.003
    slippage_rate: float = 0.0

    @property
    def total_round_trip_pct(self) -> float:
        """總成本 as percentage points (deducted from gross_return_pct)."""
        return (2 * self.commission_rate
                + self.sell_tax_rate
                + 2 * self.slippage_rate) * 100

    def describe(self) -> str:
        return (
            f"commission={self.commission_rate*100:.4f}%x2 + "
            f"sell_tax={self.sell_tax_rate*100:.4f}% + "
            f"slippage={self.slippage_rate*100:.4f}%x2 "
            f"= total {self.total_round_trip_pct:.3f}% round-trip"
        )


NO_COSTS = TransactionCosts(0.0, 0.0, 0.0)

# ─────────────────────────────────────────────────────────────
# Metrics
# ─────────────────────────────────────────────────────────────


@dataclass
class RoundTripMetrics:
    """Reviewer §50 metrics + 基本 descriptive."""
    n_trades: int = 0
    win_rate: float = 0.0
    mean_return: float = 0.0
    median_return: float = 0.0
    best_return: float = 0.0
    worst_return: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    win_loss_ratio: float = 0.0   # avg_win / |avg_loss|
    profit_factor: float = 0.0    # sum(winners) / |sum(losers)|
    avg_mfe: float = 0.0
    avg_mae: float = 0.0
    avg_holding_days: float = 0.0
    exit_reasons: dict[str, int] = field(default_factory=dict)
    by_entry_regime: dict[str, int] = field(default_factory=dict)
    by_symbol: dict[str, int] = field(default_factory=dict)


def compute_metrics(
    trades: list[Position],
    costs: TransactionCosts | None = None,
) -> RoundTripMetrics:
    """Compute aggregate metrics, optionally deducting transaction costs from each trade.

    Args:
        trades: completed Positions
        costs: TransactionCosts; if None or NO_COSTS, returns gross metrics
    """
    m = RoundTripMetrics()
    if not trades:
        return m

    cost_pct = costs.total_round_trip_pct if costs is not None else 0.0
    raw_returns = [t.gross_return_pct for t in trades if t.gross_return_pct is not None]
    returns = [r - cost_pct for r in raw_returns]  # net (or gross if cost_pct=0)
    m.n_trades = len(returns)
    if m.n_trades == 0:
        return m

    winners = [r for r in returns if r > 0]
    losers = [r for r in returns if r <= 0]

    m.win_rate = len(winners) / m.n_trades * 100
    m.mean_return = sum(returns) / m.n_trades
    sorted_r = sorted(returns)
    m.median_return = sorted_r[m.n_trades // 2]
    m.best_return = max(returns)
    m.worst_return = min(returns)
    m.avg_win = sum(winners) / len(winners) if winners else 0.0
    m.avg_loss = sum(losers) / len(losers) if losers else 0.0
    m.win_loss_ratio = (m.avg_win / abs(m.avg_loss)) if losers and m.avg_loss != 0 else float("inf")
    m.profit_factor = (sum(winners) / abs(sum(losers))) if losers and sum(losers) != 0 else float("inf")
    m.avg_mfe = sum(t.mfe_pct for t in trades) / len(trades)
    m.avg_mae = sum(t.mae_pct for t in trades) / len(trades)
    m.avg_holding_days = (
        sum(t.holding_days for t in trades if t.holding_days is not None) / m.n_trades
    )
    # exit_reason normalization (strip parens)
    m.exit_reasons = dict(
        Counter(
            (t.exit_reason.split(" (")[0] if t.exit_reason else "unknown")
            for t in trades
        )
    )
    m.by_entry_regime = dict(Counter(t.regime_at_entry for t in trades))
    m.by_symbol = dict(Counter(t.stock_id for t in trades))
    return m


# ─────────────────────────────────────────────────────────────
# Backtest engine
# ─────────────────────────────────────────────────────────────


class RoundTripBacktest:
    """Daily close-based simulator.

    Stateless input (DB read-only) + in-memory positions; 不寫 DB.
    Reviewer §53: "原型", 不要過早把 backtest state 持久化.
    """

    def __init__(
        self,
        strategy: Strategy,
        exit_rules: list[ExitRule] | None = None,
        symbols: list[str] | None = None,
    ) -> None:
        self.strategy = strategy
        self.exit_rules: list[ExitRule] = (
            exit_rules if exit_rules is not None
            else [RegimeExit(), TrailingStop()]
        )
        # Sort by priority
        self.exit_rules.sort(key=lambda r: r.priority)

        self.symbols = symbols
        self.open_positions: dict[str, Position] = {}
        self.completed_trades: list[Position] = []
        self._daily_close: dict[tuple[str, date_type], float] = {}
        self._daily_atr: dict[tuple[str, date_type], float | None] = {}
        self._daily_regime: dict[date_type, str] = {}
        self._signals_by_date: dict[date_type, list[Signal]] = {}

    # ── Preload (一次 query, 後續 dict 查) ──────────────────

    def _preload_market_data(self) -> list[date_type]:
        """Load adj_close, atr_14, regime into in-memory dicts. Return all dates."""
        sym_filter = ""
        params: list = []
        if self.symbols:
            ph = ",".join(["?"] * len(self.symbols))
            sym_filter = f" AND stock_id IN ({ph})"
            params = list(self.symbols)

        with connect(read_only=True) as conn:
            # Prices
            rows = conn.execute(
                f"SELECT stock_id, date, adj_close FROM daily_price_adj "
                f"WHERE 1=1{sym_filter} ORDER BY date, stock_id",
                params,
            ).fetchall()
            for sid, d, c in rows:
                self._daily_close[(sid, d)] = c

            # ATR
            rows = conn.execute(
                f"SELECT stock_id, date, atr_14 FROM daily_features "
                f"WHERE 1=1{sym_filter} ORDER BY date, stock_id",
                params,
            ).fetchall()
            for sid, d, a in rows:
                self._daily_atr[(sid, d)] = a

            # Regime
            rows = conn.execute(
                "SELECT date, regime FROM market_regime ORDER BY date"
            ).fetchall()
            for d, r in rows:
                self._daily_regime[d] = r

        # All dates that have BOTH daily_features and market_regime
        dates_with_features = {d for _, d in self._daily_atr}
        dates_with_regime = set(self._daily_regime)
        all_dates = sorted(dates_with_features & dates_with_regime)
        return all_dates

    def _generate_all_signals(self, dates: list[date_type]) -> None:
        """Pre-compute strategy signals per date (slow part)."""
        for d in dates:
            sigs = self.strategy.generate_signals(as_of=d, symbols=self.symbols)
            if sigs:
                self._signals_by_date[d] = sigs

    # ── Daily step ─────────────────────────────────────────

    def _update_open_positions(self, d: date_type) -> None:
        for pos in self.open_positions.values():
            close = self._daily_close.get((pos.stock_id, d))
            if close is not None:
                pos.update_running_stats(close, d)

    def _check_exits(self, d: date_type) -> None:
        regime = self._daily_regime.get(d, "unknown")
        to_close: list[Position] = []
        for sid, pos in self.open_positions.items():
            close = self._daily_close.get((sid, d))
            atr = self._daily_atr.get((sid, d))
            if close is None:
                continue
            # Check each rule in priority order
            for rule in self.exit_rules:
                decision = rule.check(pos, d, close, atr, regime)
                if decision.should_exit:
                    pos.exit_date = d
                    pos.exit_price = close
                    pos.exit_reason = decision.reason
                    pos.regime_at_exit = regime
                    pos.exit_metadata = decision.metadata
                    to_close.append(pos)
                    break  # 不再 evaluate 更低優先 rule
        for pos in to_close:
            del self.open_positions[pos.stock_id]
            self.completed_trades.append(pos)

    def _open_new_positions(self, d: date_type) -> None:
        for sig in self._signals_by_date.get(d, []):
            if sig.stock_id in self.open_positions:
                continue  # 已開倉, 不重複 (reviewer §51 沒做 sizing)
            pos = Position(
                stock_id=sig.stock_id,
                entry_date=sig.signal_date,
                entry_price=sig.entry_price,
                entry_atr=sig.entry_atr,
                regime_at_entry=sig.regime,
                strategy=sig.strategy,
                score=sig.score,
            )
            self.open_positions[sig.stock_id] = pos

    # ── Force close at end ─────────────────────────────────

    def _force_close_remaining(self, last_date: date_type) -> None:
        regime = self._daily_regime.get(last_date, "unknown")
        for sid, pos in list(self.open_positions.items()):
            close = self._daily_close.get((sid, last_date))
            if close is None:
                continue
            pos.exit_date = last_date
            pos.exit_price = close
            pos.exit_reason = "end_of_backtest"
            pos.regime_at_exit = regime
            self.completed_trades.append(pos)
        self.open_positions.clear()

    # ── Public API ─────────────────────────────────────────

    def run(self) -> list[Position]:
        """Run full backtest, return completed trades list."""
        all_dates = self._preload_market_data()
        if not all_dates:
            return []
        # Skip SMA200 warmup (strategy needs sma_200 which is null for first ~200 days)
        if len(all_dates) > 200:
            all_dates = all_dates[200:]

        self._generate_all_signals(all_dates)

        for d in all_dates:
            self._update_open_positions(d)
            self._check_exits(d)
            self._open_new_positions(d)

        self._force_close_remaining(all_dates[-1])
        return self.completed_trades

    def trades_to_polars(self) -> pl.DataFrame:
        """Export completed trades as Polars DataFrame for CSV/analysis."""
        if not self.completed_trades:
            return pl.DataFrame()
        rows: list[dict[str, Any]] = []
        for t in self.completed_trades:
            rows.append({
                "stock_id": t.stock_id,
                "entry_date": t.entry_date,
                "exit_date": t.exit_date,
                "holding_days": t.holding_days,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "gross_return_pct": t.gross_return_pct,
                "mfe_pct": t.mfe_pct,
                "mae_pct": t.mae_pct,
                "entry_atr": t.entry_atr,
                "regime_at_entry": t.regime_at_entry,
                "regime_at_exit": t.regime_at_exit,
                "exit_reason": (
                    t.exit_reason.split(" (")[0] if t.exit_reason else None
                ),
                "score": t.score,
                "strategy": t.strategy,
            })
        return pl.DataFrame(rows)


# ─────────────────────────────────────────────────────────────
# IS/OOS partition helper (v0.1.13.3)
# ─────────────────────────────────────────────────────────────


def partition_by_date(
    trades: list[Position], is_end: date_type
) -> tuple[list[Position], list[Position]]:
    """Split completed trades into IS (entry_date <= is_end) vs OOS (entry_date > is_end).

    用 entry_date 切, 因為「decision was made at entry」.
    OOS 不包含 IS-entry-but-OOS-exit 的 trades (entry 那刻就決定 partition).
    """
    is_trades = [t for t in trades if t.entry_date <= is_end]
    oos_trades = [t for t in trades if t.entry_date > is_end]
    return is_trades, oos_trades
