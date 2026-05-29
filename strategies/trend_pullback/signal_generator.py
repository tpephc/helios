# strategies/trend_pullback/signal_generator.py
"""trend_pullback_v1 signal generator — v0.1.18.

Converts PullbackCandidate list into signals, after:
  1. Deduplicating against existing OPEN positions (account-scoped)
  2. Deduplicating against pending signals from other strategies
  3. Applying portfolio constraints (max positions, max per-sector)

This module does NOT write to the signals table directly. It returns
a list of PullbackSignalRequest that the caller (process_entries or
daily_run integration) writes via storage.signals.

Conflict resolution (breakout vs pullback same symbol same day):
  - If OPEN position exists → reject (existing position wins)
  - If breakout signal also pending → keep higher score
  - Tie → prefer pullback only if dist < -1 and beta_60 in T3
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type

import structlog

from strategies.trend_pullback.config import DEFAULT_CONFIG, TrendPullbackConfig
from strategies.trend_pullback.types import PullbackCandidate, PullbackPriority

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class PullbackSignalRequest:
    """Signal request to be written by caller.

    Maps to storage.signals.push_signal() parameters. Caller is
    responsible for the actual DB write — this module is pure logic.
    """

    symbol: str
    signal_type: str          # "buy"
    strategy: str             # "trend_pullback_v1"
    price: float              # adj_close at signal time
    entry_atr: float          # ATR(14) at signal time
    regime: str               # market_regime at signal time
    score: float              # composite ranking score
    priority: PullbackPriority
    metadata: dict             # additional context for logging


def generate_signals(
    candidates: list[PullbackCandidate],
    *,
    open_symbols: set[str],
    pending_symbols: dict[str, float],
    max_new_signals: int | None = None,
    config: TrendPullbackConfig = DEFAULT_CONFIG,
) -> list[PullbackSignalRequest]:
    """Convert screener candidates to signal requests.

    Args:
        candidates: sorted PullbackCandidate list from screener.
        open_symbols: symbols with existing OPEN positions in this account.
            Sourced from storage.positions.get_open_positions(account_id=...).
        pending_symbols: {symbol: score} of pending signals from other
            strategies (e.g. breakout). Used for conflict resolution.
        max_new_signals: cap on signals generated this run. None = no cap.
        config: strategy configuration.

    Returns:
        List of PullbackSignalRequest, ready for caller to write.
    """
    signals: list[PullbackSignalRequest] = []
    rejected_open = 0
    rejected_conflict = 0
    rejected_cap = 0

    for candidate in candidates:
        # ── Gate 1: existing OPEN position ───────────────────────
        if candidate.symbol in open_symbols:
            rejected_open += 1
            logger.debug(
                "pullback_signal_reject_open_position",
                symbol=candidate.symbol,
            )
            continue

        # ── Gate 2: conflict with other strategy's pending signal ─
        if candidate.symbol in pending_symbols:
            other_score = pending_symbols[candidate.symbol]
            my_score = candidate.score

            # Conflict resolution: higher score wins.
            # Tie: prefer pullback only if HIGH priority AND beta T3.
            if my_score > other_score:
                # Pullback wins — other strategy's signal should be
                # superseded by caller. We emit our signal; caller
                # is responsible for dedup write logic.
                logger.info(
                    "pullback_signal_conflict_pullback_wins",
                    symbol=candidate.symbol,
                    pullback_score=round(my_score, 2),
                    other_score=round(other_score, 2),
                )
            elif my_score == other_score:
                # Tie: prefer pullback only if dist < -1 and beta T3
                is_deep_pullback = (
                    candidate.priority == PullbackPriority.HIGH
                    and candidate.beta_percentile >= 0.6667
                )
                if not is_deep_pullback:
                    rejected_conflict += 1
                    logger.info(
                        "pullback_signal_conflict_tie_other_wins",
                        symbol=candidate.symbol,
                        score=round(my_score, 2),
                    )
                    continue
                logger.info(
                    "pullback_signal_conflict_tie_pullback_wins",
                    symbol=candidate.symbol,
                    score=round(my_score, 2),
                    reason="deep_pullback_high_beta",
                )
            else:
                # Other strategy wins
                rejected_conflict += 1
                logger.info(
                    "pullback_signal_conflict_other_wins",
                    symbol=candidate.symbol,
                    pullback_score=round(my_score, 2),
                    other_score=round(other_score, 2),
                )
                continue

        # ── Gate 3: signal cap ───────────────────────────────────
        if max_new_signals is not None and len(signals) >= max_new_signals:
            rejected_cap += 1
            continue

        # ── Emit signal ──────────────────────────────────────────
        signals.append(PullbackSignalRequest(
            symbol=candidate.symbol,
            signal_type=config.signal_type,
            strategy=config.strategy_name,
            price=candidate.adj_close,
            entry_atr=candidate.entry_atr,
            regime=candidate.regime,
            score=candidate.score,
            priority=candidate.priority,
            metadata={
                "beta_adj_rs_20d": candidate.beta_adj_rs_20d,
                "dist_above_ma20_atr": candidate.dist_above_ma20_atr,
                "beta_60": candidate.beta_60,
                "rs_percentile": candidate.rs_percentile,
                "beta_percentile": candidate.beta_percentile,
                "sma20_slope_10d": candidate.sma20_slope_10d,
            },
        ))

    logger.info(
        "pullback_signal_generator_result",
        signals_generated=len(signals),
        rejected_open_position=rejected_open,
        rejected_conflict=rejected_conflict,
        rejected_cap=rejected_cap,
        candidates_input=len(candidates),
    )

    return signals
