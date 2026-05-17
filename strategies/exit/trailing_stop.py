# strategies/exit/trailing_stop.py
"""ATR Trailing Stop (Priority 2, after RegimeExit).

公式 (reviewer §36, fixed multiplier 2.0):
  stop_price = max_close_since_entry - 2 * ATR14_current
  exit if close < stop_price

設計選擇:
- ATR14 用 **current** (每日重算), 不是 entry 當下 fixed
- Multiplier 固定 2.0 (reviewer §37 禁止 adaptive)
- 不做 chandelier 變種、ML-based、volatility-aware
- 收盤觸發 (close-based), 不看盤中 high/low

不會：
- 砍掉最好 winners (max_close trailing 跟漲)
- 在 sideways 中過早被洗 (2*ATR 是寬 buffer)
- 在 regime collapse 時保命 (那是 RegimeExit 的工作)

Version: v0.1.0 (2026-05-17)
"""
from __future__ import annotations

from datetime import date as date_type

from strategies.exit.base import ExitDecision, ExitRule, Position

ATR_STOP_MULTIPLIER = 2.0


class TrailingStop(ExitRule):
    name = "trailing_stop"
    priority = 2  # 在 regime_exit 之後

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
        if atr is None or atr <= 0:
            return ExitDecision(should_exit=False, reason="")

        stop_price = position.max_close_since_entry - self.multiplier * atr

        if close < stop_price:
            return ExitDecision(
                should_exit=True,
                reason=(
                    f"{self.name} (close={close:.2f} < stop={stop_price:.2f}, "
                    f"max_close={position.max_close_since_entry:.2f}, "
                    f"atr={atr:.2f}, mult={self.multiplier})"
                ),
                metadata={
                    "exit_price": close,
                    "stop_price": stop_price,
                    "max_close_since_entry": position.max_close_since_entry,
                    "atr_at_exit": atr,
                    "multiplier": self.multiplier,
                },
            )
        return ExitDecision(should_exit=False, reason="")
