# strategies/exit/trailing_stop.py
"""ATR trailing stop — v0.2.0.

Priority 2 (after RegimeExit).

Formula:
    stop_price = max_close_since_entry - 2 * entry_atr
    exit if close <= stop_price

v0.2.0 changes:
  1. ATR basis changed from current (daily recalculated) to entry_atr
     (fixed at position open).  Rationale: with RegimeExit narrowed to
     bear-only (v0.2.0), crisis periods no longer trigger forced exit.
     Using current ATR during crisis would widen the stop (high vol →
     high ATR → lower stop) exactly when risk protection is most
     needed.  Fixed entry_atr ensures deterministic, auditable stop
     levels that do not weaken during volatility expansion.
  2. Trigger changed from ``close < stop`` to ``close <= stop`` to
     match the exit contract specification.

Design:
  - Multiplier fixed at 2.0 (reviewer §37: no adaptive).
  - Close-based trigger (no intraday high/low).
  - max_close trails upward only (updated by run_exit_scan before
    this rule is evaluated).
  - The ``atr`` parameter in check() is still received per the
    ExitRule interface but is NOT used for stop calculation.
    entry_atr is read from the position object.

Version: v0.2.0 (2026-05-31)
"""
from __future__ import annotations

from datetime import date as date_type

from strategies.exit.base import ExitDecision, ExitRule, Position

ATR_STOP_MULTIPLIER = 2.0


class TrailingStop(ExitRule):
    name = "trailing_stop"
    priority = 2  # after regime_exit

    def __init__(self, multiplier: float = ATR_STOP_MULTIPLIER) -> None:
        self.multiplier = multiplier

    def check(
        self,
        position: Position,
        as_of: date_type,
        close: float,
        atr: float | None,
        regime: str,
    ) -> ExitDecision:
        if position.entry_atr <= 0:
            return ExitDecision(should_exit=False, reason="")

        stop_price = (
            position.max_close_since_entry
            - self.multiplier * position.entry_atr
        )

        if close <= stop_price:
            return ExitDecision(
                should_exit=True,
                reason=(
                    f"{self.name} (close={close:.2f} <= stop={stop_price:.2f}, "
                    f"max_close={position.max_close_since_entry:.2f}, "
                    f"entry_atr={position.entry_atr:.2f}, mult={self.multiplier})"
                ),
                metadata={
                    "exit_price": close,
                    "stop_price": stop_price,
                    "max_close_since_entry": position.max_close_since_entry,
                    "entry_atr": position.entry_atr,
                    "multiplier": self.multiplier,
                },
            )
        return ExitDecision(should_exit=False, reason="")
