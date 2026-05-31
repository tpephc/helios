# strategies/exit/base.py
"""Exit framework abstractions — v0.2.0.

Per reviewer §40: exit signal must carry exit_reason / stop_price /
MFE / MAE / holding_days / regime_at_exit (discloses strategy risk
profile).

Design:
  - Position dataclass — mutable lifecycle object (entry → hold → exit).
  - ExitDecision dataclass — exit rule return value.
  - ExitRule ABC — one class per rule, sorted by priority.

Priority: lower number = higher priority (regime_exit < trailing_stop
< time_stop).

v0.2.0 change: added ``holding_trading_days`` field to Position.
  Set by run_exit_scan.py before rule evaluation.  Used by TimeStop
  to enforce max holding period in trading days (not calendar days).

Version: v0.2.0 (2026-05-31)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date as date_type
from typing import Any

# ─────────────────────────────────────────────────────────────
# Position lifecycle dataclass
# ─────────────────────────────────────────────────────────────


@dataclass
class Position:
    """Single trade lifecycle (entry → hold → exit) with full audit fields.

    Mutable: max/min_close updated daily with close prices.
    """

    # Entry (immutable after open)
    stock_id: str
    entry_date: date_type
    entry_price: float
    entry_atr: float
    regime_at_entry: str
    strategy: str
    score: float
    signal_id: str | None = None

    # Running stats (updated daily by run_exit_scan)
    max_close_since_entry: float = 0.0
    max_close_date: date_type | None = None
    min_close_since_entry: float = 0.0
    min_close_date: date_type | None = None

    # Holding duration in market trading days (set by run_exit_scan
    # before rule evaluation; None if not yet computed).
    holding_trading_days: int | None = None

    # Exit (None = still open)
    exit_date: date_type | None = None
    exit_price: float | None = None
    exit_reason: str | None = None
    regime_at_exit: str | None = None
    exit_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.max_close_since_entry == 0.0:
            self.max_close_since_entry = self.entry_price
            self.max_close_date = self.entry_date
        if self.min_close_since_entry == 0.0:
            self.min_close_since_entry = self.entry_price
            self.min_close_date = self.entry_date

    @property
    def is_open(self) -> bool:
        return self.exit_date is None

    @property
    def holding_calendar_days(self) -> int | None:
        """Calendar days from entry to exit (not trading days)."""
        if self.exit_date is None:
            return None
        return (self.exit_date - self.entry_date).days

    @property
    def gross_return_pct(self) -> float | None:
        if self.exit_price is None or self.entry_price <= 0:
            return None
        return (self.exit_price / self.entry_price - 1.0) * 100.0

    @property
    def mfe_pct(self) -> float:
        """Max Favorable Excursion (reviewer §40)."""
        if self.entry_price <= 0:
            return 0.0
        return (self.max_close_since_entry / self.entry_price - 1.0) * 100.0

    @property
    def mae_pct(self) -> float:
        """Max Adverse Excursion (reviewer §40, typically negative)."""
        if self.entry_price <= 0:
            return 0.0
        return (self.min_close_since_entry / self.entry_price - 1.0) * 100.0

    def update_running_stats(self, close: float, d: date_type) -> None:
        """Daily close update for max/min tracking."""
        if close > self.max_close_since_entry:
            self.max_close_since_entry = close
            self.max_close_date = d
        if close < self.min_close_since_entry:
            self.min_close_since_entry = close
            self.min_close_date = d


# ─────────────────────────────────────────────────────────────
# Exit decision
# ─────────────────────────────────────────────────────────────


@dataclass
class ExitDecision:
    """Return value from a single exit rule evaluation."""

    should_exit: bool
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────
# Exit rule abstract base
# ─────────────────────────────────────────────────────────────


class ExitRule(ABC):
    """Exit rule base class.

    Subclasses must set:
      - name: rule identifier (written into exit_reason).
      - priority: int, lower = higher priority.
    """

    name: str
    priority: int = 999

    @abstractmethod
    def check(
        self,
        position: Position,
        as_of: date_type,
        close: float,
        atr: float | None,
        regime: str,
    ) -> ExitDecision:
        """Evaluate whether this position should exit.

        Args:
            position: open position with running stats current as of
                today (updated by caller before this method is called).
            as_of: evaluation date.
            close: today's adj_close for this symbol.
            atr: today's ATR(14) for this symbol (may be None).
            regime: today's TAIEX market regime.

        Returns:
            ExitDecision with should_exit flag, human-readable reason,
            and optional metadata dict.
        """
        raise NotImplementedError
