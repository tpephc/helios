# strategies/exit/regime_exit.py
"""Regime-collapse exit (Priority 1 — higher than ATR stop, per reviewer §43).

理由 (reviewer §44-46):
- 真正大虧通常來自 market regime collapse (2022 升息 / COVID / flash crash)
- ATR trailing stop 在 regime collapse 時往往「來不及」(ATR 跟漲, 暴跌反應慢)
- regime gate exit 直接斷頭, 是 Helios 的核心 risk protection

規則:
  if regime != 'bull':  → EXIT

不要做 condition expansion (例如 regime != bull AND atr_spike); 保持簡單.
Reviewer §35-38: interpretability 比 sophistication 重要.

Version: v0.1.0 (2026-05-17)
"""
from __future__ import annotations

from datetime import date as date_type

from strategies.exit.base import ExitDecision, ExitRule, Position


class RegimeExit(ExitRule):
    name = "regime_exit"
    priority = 1  # 最高優先, 先檢查

    def check(
        self,
        position: Position,
        as_of: date_type,
        close: float,
        atr: float | None,
        regime: str,
    ) -> ExitDecision:
        if regime != "bull":
            return ExitDecision(
                should_exit=True,
                reason=f"{self.name} (regime={regime}, was bull at entry)",
                metadata={
                    "regime_at_exit": regime,
                    "regime_at_entry": position.regime_at_entry,
                    "exit_price": close,
                },
            )
        return ExitDecision(should_exit=False, reason="")
