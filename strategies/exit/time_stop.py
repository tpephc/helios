# strategies/exit/time_stop.py
"""Time stop (max holding period) — v0.1.0.

Priority 3 (after RegimeExit and TrailingStop).

Ensures every position has a bounded holding period.  Fires when
holding_trading_days >= max_holding_days (default 20).

Alignment with evidence framework:
  forward_return_tracker.py measures 20-trading-day forward returns
  as the signal-quality gate.  TimeStop at 20 days ensures the
  tracker's horizon is an upper bound on actual holding period.
  Positions that survive RegimeExit and TrailingStop for the full
  term exit at the same point the tracker measures, making signal
  gate and strategy gate directly comparable for full-term holds.

holding_trading_days is computed by the caller (run_exit_scan.py)
and set on the Position object before check() is called.  This
keeps the rule as pure logic with no DB dependency.

Version: v0.1.0 (2026-05-31)
"""
from __future__ import annotations

from datetime import date as date_type

from strategies.exit.base import ExitDecision, ExitRule, Position

DEFAULT_MAX_HOLDING_DAYS = 20


class TimeStop(ExitRule):
    name = "time_stop"
    priority = 3  # after regime_exit (1) and trailing_stop (2)

    def __init__(
        self, max_holding_days: int = DEFAULT_MAX_HOLDING_DAYS,
    ) -> None:
        self.max_holding_days = max_holding_days

    def check(
        self,
        position: Position,
        as_of: date_type,
        close: float,
        atr: float | None,
        regime: str,
    ) -> ExitDecision:
        if position.holding_trading_days is None:
            return ExitDecision(
                should_exit=False,
                reason="holding_trading_days not set",
            )

        if position.holding_trading_days >= self.max_holding_days:
            return ExitDecision(
                should_exit=True,
                reason=(
                    f"{self.name} (held {position.holding_trading_days} "
                    f"trading days >= max {self.max_holding_days})"
                ),
                metadata={
                    "exit_price": close,
                    "holding_trading_days": position.holding_trading_days,
                    "max_holding_days": self.max_holding_days,
                },
            )
        return ExitDecision(should_exit=False, reason="")
