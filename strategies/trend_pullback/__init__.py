# strategies/trend_pullback/__init__.py
"""trend_pullback_v1 — RS momentum + MA20 pullback entry strategy.

Public API:
    find_pullback_candidates(as_of) → list[PullbackCandidate]
    generate_signals(candidates, ...) → list[PullbackSignalRequest]

Evidence: docs/research/phase0_findings.md v4
  RS_T3 + dist < 0 + regime ≠ bear + beta T2/T3
  20d: +1.66% lift, 62.3% hit rate

Exit: Phase 1 reuses RegimeExit + TrailingStop (not separately validated).
"""
from strategies.trend_pullback.config import DEFAULT_CONFIG, TrendPullbackConfig
from strategies.trend_pullback.screener import find_pullback_candidates
from strategies.trend_pullback.signal_generator import (
    PullbackSignalRequest,
    generate_signals,
)
from strategies.trend_pullback.types import PullbackCandidate, PullbackPriority

__all__ = [
    "DEFAULT_CONFIG",
    "TrendPullbackConfig",
    "PullbackCandidate",
    "PullbackPriority",
    "PullbackSignalRequest",
    "find_pullback_candidates",
    "generate_signals",
]
