# strategies/trend_pullback/screener.py
"""trend_pullback_v1 screener — v0.1.18.

Finds pullback candidates from bullish_features table on a given date.

Data flow:
  1. Check market_regime → reject if bear (regime gate)
  2. Query bullish_features for as_of date (all universe stocks)
  3. Compute cross-sectional tercile thresholds for RS and Beta
  4. Filter: RS_T3 AND dist < 0 AND Beta >= T2
  5. Classify priority (HIGH / NORMAL) and rank

Dependencies:
  - bullish_features table (must include dist_above_ma20_atr, beta_adj_rs_20d,
    beta_60, sma20_slope_10d)
  - market_regime table
  - daily_price_adj table (for adj_close)
  - daily_features table (for atr_14)

Evidence: docs/research/phase0_findings.md v4
"""
from __future__ import annotations

from datetime import date as date_type

import structlog

from data.database import connect
from strategies.trend_pullback.config import DEFAULT_CONFIG, TrendPullbackConfig
from strategies.trend_pullback.types import PullbackCandidate, PullbackPriority

logger = structlog.get_logger(__name__)


def _get_regime(as_of: date_type) -> str | None:
    """Read market regime for as_of date. Returns None if missing."""
    with connect(read_only=True) as conn:
        row = conn.execute(
            "SELECT regime FROM market_regime WHERE date = ?",
            [as_of],
        ).fetchone()
    return str(row[0]) if row else None


def _compute_tercile_thresholds(
    values: list[float],
    lower_pct: float,
    upper_pct: float,
) -> tuple[float, float]:
    """Compute cross-sectional percentile thresholds.

    Returns (lower_threshold, upper_threshold) such that:
      T1: value < lower_threshold
      T2: lower_threshold <= value < upper_threshold
      T3: value >= upper_threshold

    Uses linear interpolation (same as numpy percentile default).
    """
    if not values:
        return 0.0, 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)

    def _percentile(pct: float) -> float:
        idx = pct * (n - 1)
        lo = int(idx)
        hi = min(lo + 1, n - 1)
        frac = idx - lo
        return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac

    return _percentile(lower_pct), _percentile(upper_pct)


def find_pullback_candidates(
    as_of: date_type,
    *,
    config: TrendPullbackConfig = DEFAULT_CONFIG,
) -> list[PullbackCandidate]:
    """Screen universe for trend_pullback_v1 candidates on as_of.

    Returns list of PullbackCandidate sorted by:
      1. Priority descending (HIGH before NORMAL)
      2. Distance ascending (deeper pullback first)
      3. RS descending (stronger momentum first)

    Returns empty list if:
      - regime is bear (prohibited)
      - regime is missing (conservative reject)
      - no features data for as_of
      - no stocks pass all filters
    """
    # ── Step 1: Regime gate ──────────────────────────────────────
    regime = _get_regime(as_of)
    if regime is None:
        logger.warning(
            "pullback_screener_no_regime",
            as_of=str(as_of),
            action="reject_all",
        )
        return []

    if regime in config.prohibited_regimes:
        logger.info(
            "pullback_screener_regime_prohibited",
            as_of=str(as_of),
            regime=regime,
        )
        return []

    # ── Step 2: Query features ───────────────────────────────────
    with connect(read_only=True) as conn:
        rows = conn.execute(
            """
            SELECT
                bf.stock_id,
                bf.beta_adj_rs_20d,
                bf.dist_above_ma20_atr,
                bf.beta_60,
                bf.sma20_slope_10d,
                dp.adj_close,
                df.atr_14
            FROM bullish_features bf
            JOIN daily_price_adj dp
                ON dp.stock_id = bf.stock_id AND dp.date = bf.date
            LEFT JOIN daily_features df
                ON df.stock_id = bf.stock_id AND df.date = bf.date
            WHERE bf.date = ?
                AND bf.beta_adj_rs_20d IS NOT NULL
                AND bf.dist_above_ma20_atr IS NOT NULL
                AND bf.beta_60 IS NOT NULL
                AND dp.adj_close IS NOT NULL
                AND dp.adj_close > 0
            """,
            [as_of],
        ).fetchall()

    if not rows:
        logger.warning(
            "pullback_screener_no_features",
            as_of=str(as_of),
        )
        return []

    # ── Step 3: Compute cross-sectional tercile thresholds ───────
    all_rs = [float(r[1]) for r in rows]
    all_beta = [float(r[3]) for r in rows]

    _, rs_t3_threshold = _compute_tercile_thresholds(
        all_rs, lower_pct=config.rs_tercile_pct, upper_pct=config.rs_tercile_pct,
    )
    beta_t2_threshold, _ = _compute_tercile_thresholds(
        all_beta, lower_pct=config.beta_min_tercile_pct, upper_pct=config.rs_tercile_pct,
    )

    logger.info(
        "pullback_screener_thresholds",
        as_of=str(as_of),
        universe_size=len(rows),
        rs_t3_threshold=round(rs_t3_threshold, 4),
        beta_t2_threshold=round(beta_t2_threshold, 4),
        regime=regime,
    )

    # ── Step 4: Filter ───────────────────────────────────────────
    candidates: list[PullbackCandidate] = []

    for row in rows:
        symbol = str(row[0])
        rs_val = float(row[1])
        dist_val = float(row[2])
        beta_val = float(row[3])
        slope_val = float(row[4]) if row[4] is not None else None
        adj_close = float(row[5])
        atr_val = float(row[6]) if row[6] is not None else 0.0

        # RS gate: must be T3 (top tercile)
        if rs_val < rs_t3_threshold:
            continue

        # Distance gate: must be below MA20 (dist < 0)
        if dist_val >= config.dist_entry_max:
            continue

        # Beta gate: must be T2 or T3 (>= 33rd percentile)
        if beta_val < beta_t2_threshold:
            continue

        # ATR required for position sizing downstream
        if atr_val <= 0:
            logger.debug(
                "pullback_screener_skip_no_atr",
                symbol=symbol, as_of=str(as_of),
            )
            continue

        # ── Classify priority ────────────────────────────────────
        if dist_val < config.dist_high_threshold:
            priority = PullbackPriority.HIGH
        else:
            priority = PullbackPriority.NORMAL

        # ── Compute percentiles for diagnostics ──────────────────
        rs_pctile = sum(1 for v in all_rs if v <= rs_val) / len(all_rs)
        beta_pctile = sum(1 for v in all_beta if v <= beta_val) / len(all_beta)

        candidates.append(PullbackCandidate(
            symbol=symbol,
            as_of=as_of,
            beta_adj_rs_20d=rs_val,
            dist_above_ma20_atr=dist_val,
            beta_60=beta_val,
            rs_percentile=round(rs_pctile, 4),
            beta_percentile=round(beta_pctile, 4),
            regime=regime,
            adj_close=adj_close,
            entry_atr=atr_val,
            priority=priority,
            sma20_slope_10d=slope_val,
        ))

    # ── Step 5: Sort ─────────────────────────────────────────────
    # Priority descending (HIGH=0 before NORMAL=1 via enum ordering hack:
    # sort by HIGH first), then dist ascending, then RS descending.
    priority_order = {PullbackPriority.HIGH: 0, PullbackPriority.NORMAL: 1}
    candidates.sort(key=lambda c: (
        priority_order[c.priority],
        c.dist_above_ma20_atr,       # ascending (more negative = better)
        -c.beta_adj_rs_20d,           # descending (higher RS = better)
    ))

    logger.info(
        "pullback_screener_result",
        as_of=str(as_of),
        regime=regime,
        candidates_total=len(candidates),
        candidates_high=sum(1 for c in candidates if c.priority == PullbackPriority.HIGH),
        candidates_normal=sum(1 for c in candidates if c.priority == PullbackPriority.NORMAL),
    )

    return candidates
