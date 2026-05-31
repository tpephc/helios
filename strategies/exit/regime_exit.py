# strategies/exit/regime_exit.py
"""Regime-collapse exit — v0.2.0.

Priority 1 (highest). Exits when TAIEX market regime enters bear.

v0.2.0 change: trigger narrowed from ``regime != "bull"`` to
``regime == "bear"``.  Rationale: crisis regime is intentionally
allowed at entry (V-recovery thesis; screener config
``prohibited_regimes = {"bear"}``).  Exiting on crisis would
immediately reverse V-recovery entries, defeating the entry thesis.
Bear is the only structurally adverse regime for a long momentum
strategy; crisis and neutral are transient states where the
trailing stop and time stop provide sufficient protection.

Design:
  - Single condition: regime == "bear" → EXIT.
  - No condition expansion (no ATR spike, no multi-day confirm).
  - Interpretability > sophistication (reviewer §35-38).

Version: v0.2.0 (2026-05-31)
"""
from __future__ import annotations

from datetime import date as date_type

from strategies.exit.base import ExitDecision, ExitRule, Position


class RegimeExit(ExitRule):
    name = "regime_exit"
    priority = 1  # highest — checked first

    def check(
        self,
        position: Position,
        as_of: date_type,
        close: float,
        atr: float | None,
        regime: str,
    ) -> ExitDecision:
        if regime == "bear":
            return ExitDecision(
                should_exit=True,
                reason=(
                    f"{self.name} (regime=bear, "
                    f"entry_regime={position.regime_at_entry})"
                ),
                metadata={
                    "regime_at_exit": regime,
                    "regime_at_entry": position.regime_at_entry,
                    "exit_price": close,
                },
            )
        return ExitDecision(should_exit=False, reason="")
