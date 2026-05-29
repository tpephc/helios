# strategies/trend_pullback/types.py
"""trend_pullback_v1 domain types — v0.1.18.

Structured data for screener → signal_generator pipeline.
Avoids dict leak between modules.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type
from enum import Enum


class PullbackPriority(Enum):
    """Entry priority based on distance from MA20.

    HIGH:   dist < -1 ATR (deep pullback, 59.3% hit, +2.09% median 20d)
    NORMAL: -1 <= dist < 0 (shallow pullback, 55.0% hit, +0.91% median 20d)
    """

    HIGH = "HIGH"
    NORMAL = "NORMAL"


@dataclass(frozen=True)
class PullbackCandidate:
    """Screener output: one stock passing all pullback filters.

    All fields populated by screener.py. Immutable to prevent
    downstream mutation before signal generation.
    """

    symbol: str
    as_of: date_type

    # ── Feature values (raw) ─────────────────────────────────────
    beta_adj_rs_20d: float
    dist_above_ma20_atr: float
    beta_60: float

    # ── Tercile classification ───────────────────────────────────
    rs_percentile: float          # cross-sectional percentile [0, 1]
    beta_percentile: float        # cross-sectional percentile [0, 1]

    # ── Context ──────────────────────────────────────────────────
    regime: str                   # market_regime on as_of
    adj_close: float              # closing price on as_of
    entry_atr: float              # ATR(14) on as_of

    # ── Derived ──────────────────────────────────────────────────
    priority: PullbackPriority

    # ── Optional enrichment ──────────────────────────────────────
    sma20_slope_10d: float | None = None
    sector: str | None = None
    is_etf: bool = False

    @property
    def score(self) -> float:
        """Composite score for ranking within same priority tier.

        Higher = better. Combines RS strength with pullback depth.
        RS contributes positively; deeper pullback (more negative dist)
        contributes positively via negation.

        Not a calibrated model — just a deterministic tiebreaker.
        """
        return self.beta_adj_rs_20d + (-self.dist_above_ma20_atr)
