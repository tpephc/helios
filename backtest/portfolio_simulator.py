# backtest/portfolio_simulator.py
"""Portfolio-aware backtest — Extends round_trip with capital + risk constraints.

Key differences from round_trip.RoundTripBacktest:
  - 有 initial_capital, 真實追蹤 cash / equity
  - 同日多個 signals 排 score, 套 risk_budget constraints
  - 每日記錄 EquitySnapshot (給 equity curve / max DD 計算)
  - 每個 signal 記錄 SignalDecision (accepted / rejected + reason)
  - Position size 由 per_position_pct × current_equity 決定

Simulation flow (close-based, 無 look-ahead):
  For each trading date d:
    1. Update open positions running stats with adj_close[d]
    2. Check exits (priority order); release capital back to cash
    3. Evaluate today's signals (sorted by score DESC):
       a. Skip if already held
       b. Reject if max_positions / etf_cap / sector_cap / cash_buffer violated
       c. Open with notional = per_position_pct × current_equity
    4. Record EquitySnapshot

Reviewer §43-49 framework:
  - Equal-weight per_position (no Kelly)
  - Sector cap (no covariance optimization)
  - Cash buffer (no leverage)
  - Deterministic (no ML)

Version: v0.1.0 (2026-05-17)
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date as date_type
from typing import Any

import polars as pl

from backtest.round_trip import NO_COSTS, TransactionCosts
from data.database import connect
from portfolio.risk_budget import DEFAULT_RISK_BUDGET, RiskBudget
from portfolio.selector import get_sector, is_etf
from strategies.base import Signal, Strategy
from strategies.exit.base import ExitRule
from strategies.exit.regime_exit import RegimeExit
from strategies.exit.trailing_stop import TrailingStop

# ─────────────────────────────────────────────────────────────
# Position with sizing
# ─────────────────────────────────────────────────────────────


@dataclass
class PortfolioPosition:
    """Position with sizing (notional + shares) + sector classification.

    Mirrors strategies.exit.base.Position but adds capital fields for
    portfolio-aware backtest.
    """
    stock_id: str
    entry_date: date_type
    entry_price: float
    entry_atr: float
    regime_at_entry: str
    strategy: str
    score: float

    # Sizing
    notional_at_entry: float       # 計畫投入金額 (含 fees, 從 cash 扣的金額)
    shares: float                  # 實際取得股數 (= net_notional / entry_price)
    sector: str
    is_etf_pos: bool

    # Running stats (updated each day)
    max_close_since_entry: float = 0.0
    max_close_date: date_type | None = None
    min_close_since_entry: float = 0.0
    min_close_date: date_type | None = None

    # Exit
    exit_date: date_type | None = None
    exit_price: float | None = None
    exit_reason: str | None = None
    regime_at_exit: str | None = None
    exit_proceeds: float | None = None  # 賣出後實際回到 cash 的錢

    def __post_init__(self) -> None:
        if self.max_close_since_entry == 0.0:
            self.max_close_since_entry = self.entry_price
            self.max_close_date = self.entry_date
        if self.min_close_since_entry == 0.0:
            self.min_close_since_entry = self.entry_price
            self.min_close_date = self.entry_date

    def update_running_stats(self, close: float, d: date_type) -> None:
        if close > self.max_close_since_entry:
            self.max_close_since_entry = close
            self.max_close_date = d
        if close < self.min_close_since_entry:
            self.min_close_since_entry = close
            self.min_close_date = d

    @property
    def is_open(self) -> bool:
        return self.exit_date is None

    @property
    def holding_days(self) -> int | None:
        if self.exit_date is None:
            return None
        return (self.exit_date - self.entry_date).days

    @property
    def gross_return_pct(self) -> float | None:
        if self.exit_price is None or self.entry_price <= 0:
            return None
        return (self.exit_price / self.entry_price - 1.0) * 100.0

    @property
    def net_pnl_ntd(self) -> float | None:
        """Realized P&L in NTD (after all costs)."""
        if self.exit_proceeds is None:
            return None
        return self.exit_proceeds - self.notional_at_entry


# ─────────────────────────────────────────────────────────────
# Equity / decision tracking
# ─────────────────────────────────────────────────────────────


@dataclass
class EquitySnapshot:
    date: date_type
    cash: float
    positions_value: float
    equity: float
    n_positions: int
    exposure_pct: float


@dataclass
class SignalDecision:
    date: date_type
    stock_id: str
    score: float
    decision: str             # 'accepted' / 'rejected'
    reject_reason: str | None = None


# ─────────────────────────────────────────────────────────────
# Metrics
# ─────────────────────────────────────────────────────────────


@dataclass
class PortfolioMetrics:
    initial_capital: float = 0.0
    final_equity: float = 0.0
    total_return_pct: float = 0.0
    cagr_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    max_dd_date: date_type | None = None
    avg_exposure_pct: float = 0.0
    avg_n_positions: float = 0.0
    n_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_trade_return_pct: float = 0.0
    n_signals_seen: int = 0
    n_signals_rejected: int = 0
    reject_reasons: dict[str, int] = field(default_factory=dict)
    sector_avg_exposure: dict[str, float] = field(default_factory=dict)


def compute_portfolio_metrics(
    equity_curve: list[EquitySnapshot],
    trades: list[PortfolioPosition],
    decisions: list[SignalDecision],
    initial_capital: float,
) -> PortfolioMetrics:
    m = PortfolioMetrics(initial_capital=initial_capital)
    if not equity_curve:
        return m

    # Return / CAGR
    m.final_equity = equity_curve[-1].equity
    m.total_return_pct = (m.final_equity / initial_capital - 1) * 100
    years = len(equity_curve) / 250.0
    m.cagr_pct = ((m.final_equity / initial_capital) ** (1 / years) - 1) * 100 \
        if years > 0 and m.final_equity > 0 else 0.0

    # Max DD (peak-to-trough on daily equity)
    peak = initial_capital
    max_dd, max_dd_d = 0.0, None
    for snap in equity_curve:
        if snap.equity > peak:
            peak = snap.equity
        dd = (snap.equity - peak) / peak * 100 if peak > 0 else 0
        if dd < max_dd:
            max_dd = dd
            max_dd_d = snap.date
    m.max_drawdown_pct = max_dd
    m.max_dd_date = max_dd_d

    # Exposure / position count
    m.avg_exposure_pct = sum(s.exposure_pct for s in equity_curve) / len(equity_curve)
    m.avg_n_positions = sum(s.n_positions for s in equity_curve) / len(equity_curve)

    # Trade-level
    realized = [t for t in trades if t.gross_return_pct is not None]
    m.n_trades = len(realized)
    if realized:
        returns = [t.gross_return_pct for t in realized]
        m.avg_trade_return_pct = sum(returns) / len(returns)
        winners = [r for r in returns if r > 0]
        losers = [r for r in returns if r <= 0]
        m.win_rate = len(winners) / len(returns) * 100
        m.profit_factor = (
            sum(winners) / abs(sum(losers)) if losers and sum(losers) != 0
            else float("inf")
        )

    # Signal decisions
    m.n_signals_seen = len(decisions)
    rejected = [d for d in decisions if d.decision == "rejected"]
    m.n_signals_rejected = len(rejected)
    m.reject_reasons = dict(Counter(
        d.reject_reason for d in rejected if d.reject_reason
    ))

    return m


# ─────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────


class PortfolioBacktest:
    """Portfolio-constrained daily close-based simulator.

    Stateless input (DB read-only) + in-memory state.
    """

    def __init__(
        self,
        strategy: Strategy,
        initial_capital: float = 1_000_000.0,
        budget: RiskBudget | None = None,
        exit_rules: list[ExitRule] | None = None,
        symbols: list[str] | None = None,
        costs: TransactionCosts | None = None,
    ) -> None:
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.budget = budget if budget is not None else DEFAULT_RISK_BUDGET
        self.exit_rules: list[ExitRule] = sorted(
            (exit_rules if exit_rules is not None else [RegimeExit(), TrailingStop()]),
            key=lambda r: r.priority,
        )
        self.symbols = symbols
        self.costs = costs if costs is not None else NO_COSTS

        # State
        self.cash: float = initial_capital
        self.open_positions: dict[str, PortfolioPosition] = {}
        self.completed_trades: list[PortfolioPosition] = []
        self.equity_curve: list[EquitySnapshot] = []
        self.signal_decisions: list[SignalDecision] = []

        # Preloaded data
        self._daily_close: dict[tuple[str, date_type], float] = {}
        self._daily_atr: dict[tuple[str, date_type], float | None] = {}
        self._daily_regime: dict[date_type, str] = {}
        self._signals_by_date: dict[date_type, list[Signal]] = {}

    # ── Preload ────────────────────────────────────────────

    def _preload(self) -> list[date_type]:
        sym_filter = ""
        params: list = []
        if self.symbols:
            ph = ",".join(["?"] * len(self.symbols))
            sym_filter = f" AND stock_id IN ({ph})"
            params = list(self.symbols)

        with connect(read_only=True) as conn:
            for sid, d, c in conn.execute(
                f"SELECT stock_id, date, adj_close FROM daily_price_adj "
                f"WHERE 1=1{sym_filter} ORDER BY date, stock_id",
                params,
            ).fetchall():
                self._daily_close[(sid, d)] = c

            for sid, d, a in conn.execute(
                f"SELECT stock_id, date, atr_14 FROM daily_features "
                f"WHERE 1=1{sym_filter} ORDER BY date, stock_id",
                params,
            ).fetchall():
                self._daily_atr[(sid, d)] = a

            for d, r in conn.execute(
                "SELECT date, regime FROM market_regime ORDER BY date"
            ).fetchall():
                self._daily_regime[d] = r

        dates_with_features = {d for _, d in self._daily_atr}
        dates_with_regime = set(self._daily_regime)
        return sorted(dates_with_features & dates_with_regime)

    # ── Equity / exposure ──────────────────────────────────

    def _positions_value(self, d: date_type) -> float:
        total = 0.0
        for pos in self.open_positions.values():
            close = self._daily_close.get((pos.stock_id, d), pos.entry_price)
            total += pos.shares * close
        return total

    def _current_equity(self, d: date_type) -> float:
        return self.cash + self._positions_value(d)

    def _current_exposures(self, d: date_type) -> tuple[float, dict[str, float]]:
        """Returns (etf_value, {sector: value}) at close[d]."""
        etf_value = 0.0
        sector_val: dict[str, float] = {}
        for pos in self.open_positions.values():
            close = self._daily_close.get((pos.stock_id, d), pos.entry_price)
            val = pos.shares * close
            if pos.is_etf_pos:
                etf_value += val
            sector_val[pos.sector] = sector_val.get(pos.sector, 0.0) + val
        return etf_value, sector_val

    # ── Daily steps ────────────────────────────────────────

    def _update_positions(self, d: date_type) -> None:
        for pos in self.open_positions.values():
            close = self._daily_close.get((pos.stock_id, d))
            if close is not None:
                pos.update_running_stats(close, d)

    def _check_exits(self, d: date_type) -> None:
        regime = self._daily_regime.get(d, "unknown")
        to_close: list[PortfolioPosition] = []
        for sid, pos in self.open_positions.items():
            close = self._daily_close.get((sid, d))
            atr = self._daily_atr.get((sid, d))
            if close is None:
                continue
            for rule in self.exit_rules:
                decision = rule.check(pos, d, close, atr, regime)
                if decision.should_exit:
                    pos.exit_date = d
                    pos.exit_price = close
                    pos.exit_reason = decision.reason
                    pos.regime_at_exit = regime
                    # 賣出: shares × close × (1 - commission - tax - slippage)
                    gross_proceeds = pos.shares * close
                    fees = gross_proceeds * (
                        self.costs.commission_rate
                        + self.costs.sell_tax_rate
                        + self.costs.slippage_rate
                    )
                    pos.exit_proceeds = gross_proceeds - fees
                    self.cash += pos.exit_proceeds
                    to_close.append(pos)
                    break
        for pos in to_close:
            del self.open_positions[pos.stock_id]
            self.completed_trades.append(pos)

    def _try_open(
        self, sig: Signal, d: date_type,
        equity: float, etf_value: float, sector_value: dict[str, float],
    ) -> tuple[bool, str | None]:
        """Try opening a position. Returns (accepted, reject_reason_if_any).
        Mutates self.cash + self.open_positions if accepted.
        Updates etf_value / sector_value via return... actually need mutable, so caller updates after success.
        """
        sid = sig.stock_id

        if sid in self.open_positions:
            return False, "symbol_already_held"
        if len(self.open_positions) >= self.budget.max_positions:
            return False, "max_positions_reached"

        # Notional size (target investment, 含 fees 從 cash 扣)
        notional = self.budget.per_position_pct * equity
        buy_cost = notional * (1 + self.costs.commission_rate + self.costs.slippage_rate)

        # Cash buffer check
        cash_floor = self.budget.cash_buffer_pct * equity
        if self.cash - buy_cost < cash_floor:
            return False, "cash_buffer"

        # ETF cap
        sym_is_etf = is_etf(sid)
        if sym_is_etf:
            new_etf = etf_value + notional
            if new_etf > self.budget.max_etf_exposure_pct * equity:
                return False, "etf_cap"

        # Sector cap
        sym_sector = get_sector(sid)
        new_sector = sector_value.get(sym_sector, 0.0) + notional
        if new_sector > self.budget.max_sector_exposure_pct * equity:
            return False, f"sector_cap_{sym_sector}"

        # Pass — open
        # shares = notional / entry_price (slippage 已從 cash 扣的 buy_cost 中吸收)
        shares = notional / sig.entry_price
        pos = PortfolioPosition(
            stock_id=sid,
            entry_date=sig.signal_date,
            entry_price=sig.entry_price,
            entry_atr=sig.entry_atr,
            regime_at_entry=sig.regime,
            strategy=sig.strategy,
            score=sig.score,
            notional_at_entry=notional,
            shares=shares,
            sector=sym_sector,
            is_etf_pos=sym_is_etf,
        )
        self.open_positions[sid] = pos
        self.cash -= buy_cost
        return True, None

    def _process_signals(self, d: date_type) -> None:
        signals = self._signals_by_date.get(d, [])
        if not signals:
            return

        # Recompute exposures at this date (positions may have moved)
        equity = self._current_equity(d)
        etf_value, sector_value = self._current_exposures(d)

        # Sort by score DESC
        sorted_sigs = sorted(signals, key=lambda s: -s.score)

        for sig in sorted_sigs:
            accepted, reason = self._try_open(sig, d, equity, etf_value, sector_value)
            self.signal_decisions.append(SignalDecision(
                date=d, stock_id=sig.stock_id, score=sig.score,
                decision="accepted" if accepted else "rejected",
                reject_reason=reason,
            ))
            if accepted:
                # Update local view of exposures (next sig in this loop sees updated state)
                notional = self.budget.per_position_pct * equity
                if is_etf(sig.stock_id):
                    etf_value += notional
                sym_sector = get_sector(sig.stock_id)
                sector_value[sym_sector] = sector_value.get(sym_sector, 0.0) + notional

    def _record_equity(self, d: date_type) -> None:
        pos_value = self._positions_value(d)
        equity = self.cash + pos_value
        exposure_pct = (pos_value / equity * 100) if equity > 0 else 0.0
        self.equity_curve.append(EquitySnapshot(
            date=d, cash=self.cash, positions_value=pos_value,
            equity=equity, n_positions=len(self.open_positions),
            exposure_pct=exposure_pct,
        ))

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
            gross_proceeds = pos.shares * close
            fees = gross_proceeds * (
                self.costs.commission_rate
                + self.costs.sell_tax_rate
                + self.costs.slippage_rate
            )
            pos.exit_proceeds = gross_proceeds - fees
            self.cash += pos.exit_proceeds
            self.completed_trades.append(pos)
        self.open_positions.clear()

    # ── Public API ─────────────────────────────────────────

    def run(self) -> list[PortfolioPosition]:
        all_dates = self._preload()
        if not all_dates:
            return []
        if len(all_dates) > 200:
            all_dates = all_dates[200:]

        # Pre-compute signals
        for d in all_dates:
            sigs = self.strategy.generate_signals(as_of=d, symbols=self.symbols)
            if sigs:
                self._signals_by_date[d] = sigs

        for d in all_dates:
            self._update_positions(d)
            self._check_exits(d)
            self._process_signals(d)
            self._record_equity(d)

        self._force_close_remaining(all_dates[-1])
        return self.completed_trades

    def equity_curve_to_polars(self) -> pl.DataFrame:
        if not self.equity_curve:
            return pl.DataFrame()
        rows: list[dict[str, Any]] = []
        for s in self.equity_curve:
            rows.append({
                "date": s.date,
                "cash": s.cash,
                "positions_value": s.positions_value,
                "equity": s.equity,
                "n_positions": s.n_positions,
                "exposure_pct": s.exposure_pct,
            })
        return pl.DataFrame(rows)

    def decisions_to_polars(self) -> pl.DataFrame:
        if not self.signal_decisions:
            return pl.DataFrame()
        rows: list[dict[str, Any]] = []
        for d in self.signal_decisions:
            rows.append({
                "date": d.date,
                "stock_id": d.stock_id,
                "score": d.score,
                "decision": d.decision,
                "reject_reason": d.reject_reason,
            })
        return pl.DataFrame(rows)

    def trades_to_polars(self) -> pl.DataFrame:
        if not self.completed_trades:
            return pl.DataFrame()
        rows: list[dict[str, Any]] = []
        for t in self.completed_trades:
            rows.append({
                "stock_id": t.stock_id,
                "sector": t.sector,
                "is_etf": t.is_etf_pos,
                "entry_date": t.entry_date,
                "exit_date": t.exit_date,
                "holding_days": t.holding_days,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "shares": t.shares,
                "notional_at_entry": t.notional_at_entry,
                "exit_proceeds": t.exit_proceeds,
                "net_pnl_ntd": t.net_pnl_ntd,
                "gross_return_pct": t.gross_return_pct,
                "regime_at_entry": t.regime_at_entry,
                "regime_at_exit": t.regime_at_exit,
                "exit_reason": (
                    t.exit_reason.split(" (")[0] if t.exit_reason else None
                ),
                "score": t.score,
            })
        return pl.DataFrame(rows)
