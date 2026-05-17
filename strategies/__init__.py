# strategies/__init__.py
"""Strategy framework — feature → signal layer.

v0.1.12 第一個 deterministic strategy: TrendBreakoutStrategy.
未來 strategies 都繼承 strategies.base.Strategy.
"""
from strategies.base import Signal, Strategy
from strategies.trend_breakout import TrendBreakoutStrategy

__all__ = ["Signal", "Strategy", "TrendBreakoutStrategy"]
