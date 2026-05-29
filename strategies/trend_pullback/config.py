# strategies/trend_pullback/config.py
"""trend_pullback_v1 configuration — v0.1.18.

All entry thresholds and parameters. Single source of truth for
screener and signal generator.

Evidence base: Phase 0/A research (docs/research/phase0_findings.md v4).
  - RS_T3 + dist < 0: +1.66% lift, 62.3% hit (20d)
  - Best triple (RS_T3 + Dist_T1 + Beta_T3): +4.85%, 60% hit (20d)
  - Regime gate: bear regime returns -2.30%, hit 40.6% → prohibited

Exit: Phase 1 reuses RegimeExit + TrailingStop. Pullback-specific
exit rules deferred to Phase 2.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TrendPullbackConfig:
    """Immutable configuration for trend_pullback_v1 screener.

    Tercile computation: cross-sectional percentile on screening date.
    RS_T3 = top tercile (>= 67th percentile of beta_adj_rs_20d).
    Beta_T2 = middle tercile (>= 33rd, < 67th percentile of beta_60).
    Beta_T3 = top tercile (>= 67th percentile of beta_60).
    """

    # ── RS filter ────────────────────────────────────────────────
    # Percentile threshold for RS top tercile (T3).
    # Stocks with beta_adj_rs_20d >= this percentile qualify.
    rs_tercile_pct: float = 0.6667

    # ── Distance filter ──────────────────────────────────────────
    # dist_above_ma20_atr < 0 required for entry.
    # HIGH priority: dist < dist_high_threshold
    # NORMAL priority: dist_high_threshold <= dist < 0
    dist_entry_max: float = 0.0
    dist_high_threshold: float = -1.0

    # ── Beta filter ──────────────────────────────────────────────
    # Beta_T2 or Beta_T3 required (>= 33rd percentile of beta_60).
    beta_min_tercile_pct: float = 0.3333

    # ── Regime gate ──────────────────────────────────────────────
    # Prohibited regimes. Signal rejected if market_regime in this set.
    prohibited_regimes: frozenset[str] = frozenset({"bear"})

    # ── Strategy metadata ────────────────────────────────────────
    strategy_name: str = "trend_pullback_v1"
    signal_type: str = "buy"

    # ── Ranking ──────────────────────────────────────────────────
    # Primary sort: priority (HIGH before NORMAL).
    # Secondary sort: dist ascending (deeper pullback = better).
    # Tertiary sort: RS descending (stronger momentum = better).


# Singleton — import this in screener and signal_generator.
DEFAULT_CONFIG = TrendPullbackConfig()
