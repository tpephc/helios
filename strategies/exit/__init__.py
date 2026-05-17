# strategies/exit/__init__.py
"""Exit rule framework — close half of the decision loop.

v0.1.13.2 (per reviewer §33):
  base.py          — ExitRule ABC + Position lifecycle dataclass + ExitDecision
  trailing_stop.py — ATR trailing (highest_close - 2*ATR14)
  regime_exit.py   — Priority-1 rule: regime != 'bull' → exit

不做 (reviewer §47): time stop (會切 winners)
不做 (reviewer §37): adaptive multiplier / ML stop / volatility regime stop
"""
from strategies.exit.base import ExitDecision, ExitRule, Position
from strategies.exit.regime_exit import RegimeExit
from strategies.exit.trailing_stop import TrailingStop

__all__ = ["ExitDecision", "ExitRule", "Position", "RegimeExit", "TrailingStop"]
