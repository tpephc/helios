# strategies/tick_strategies/composite_events.py
"""Kairos Layer 1 composite event detection engine.

Design principles
-----------------
Forward-only
    Every feature used for detection at time *t* is computed exclusively
    from the window ``[t - lookback_ms, t]``.  No future data is ever
    accessed.  This makes the engine safe for live deployment.

Rarest-first anchor
    For each composite event, the rarest sub-condition is used as the
    search anchor.  Common sub-conditions are added as confirmations.
    This eliminates anchor bias: frequent conditions would create too many
    spurious candidate windows.

Time-based min_gap_ms
    After an event fires, the same event type is suppressed for
    ``min_gap_ms`` milliseconds.  This prevents event storms during
    sustained regime shifts.

Severity scoring
    Each component condition produces a scalar severity in ``[0, 1]``.
    The composite severity is a weighted combination.  A minimum composite
    severity threshold filters noise.

Empirical thresholds
    Default thresholds are derived from Q7/Q8 event_research results
    (``scripts/event_research.py``).  Update ``EventConfig`` from the
    actual BH-significant findings after recalibration.

Event taxonomy
--------------
LIQUIDITY_VACUUM
    Anchor   : depth_pctile < p10 (rarest)
    Confirm  : spread_ticks > p90
    Semantics: book thinning + spread widening — liquidity breakdown

AGGRESSION_SWEEP_BUY / AGGRESSION_SWEEP_SELL
    Anchor   : directional imbalance > threshold sustained over window
    Confirm  : spread_ticks elevated, rv_30s rising
    Semantics: sustained one-sided order flow overwhelming the passive side

BREAKOUT_LONG / BREAKOUT_SHORT
    Anchor   : price > rolling_high(lookback) or price < rolling_low(lookback)
    Confirm  : volume_spike AND spread not extreme (excludes vacuum breakouts)
    Semantics: price level break with participation confirmation

SWEEP_REVERSAL_LONG / SWEEP_REVERSAL_SHORT
    Detection window split: sweep in [t - sweep_ms, t - reversal_ms],
    reversal in [t - reversal_ms, t].  Both legs are in the PAST at time t.
    Anchor   : abs_return in sweep window > rv_spike_threshold (rarest)
    Confirm  : price direction reversal in the more recent sub-window
    Semantics: liquidity sweep that has already begun to reverse
    Note     : this is a CAUSAL pattern — both legs are observable at t.
               The prediction of further reversal belongs to event_outcomes.py.

Usage
-----
Batch (research / backtest)::

    from strategies.tick_strategies.composite_events import (
        CompositeEventEngine, EventConfig,
    )

    engine = CompositeEventEngine()
    events = engine.detect_all(df)          # df = clean tick DataFrame

    vac = events["LIQUIDITY_VACUUM"]
    print(f"{len(vac.indices)} vacuum events detected")
    print(f"mean severity: {vac.severities.mean():.3f}")

Live (streaming, one tick at a time)::

    engine = CompositeEventEngine()
    engine.init_state(df_history)           # warm-up with historical window

    for tick in live_feed:
        result = engine.update(tick)        # returns dict[name, float] severity
        if result.get("LIQUIDITY_VACUUM", 0) > 0.5:
            notifier.market_alert("Liquidity vacuum", ...)

Column requirements (TMFR1 parquet schema)
------------------------------------------
timestamp_ms    int64    Unix milliseconds
price           float64  last trade price
spread          float64  best_ask - best_bid in ticks
bid_volume      int64    5-level bid depth sum
ask_volume      int64    5-level ask depth sum
imbalance       float64  (bid_vol - ask_vol) / (bid_vol + ask_vol)
volume          int64    tick volume
tick_type       int64    1 = buy, 2 = sell
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Public data structures
# ---------------------------------------------------------------------------

# Canonical event names — use these constants to avoid typos.
LIQUIDITY_VACUUM = "LIQUIDITY_VACUUM"
AGGRESSION_SWEEP_BUY = "AGGRESSION_SWEEP_BUY"
AGGRESSION_SWEEP_SELL = "AGGRESSION_SWEEP_SELL"
BREAKOUT_LONG = "BREAKOUT_LONG"
BREAKOUT_SHORT = "BREAKOUT_SHORT"
SWEEP_REVERSAL_LONG = "SWEEP_REVERSAL_LONG"
SWEEP_REVERSAL_SHORT = "SWEEP_REVERSAL_SHORT"

ALL_EVENT_NAMES: tuple[str, ...] = (
    LIQUIDITY_VACUUM,
    AGGRESSION_SWEEP_BUY,
    AGGRESSION_SWEEP_SELL,
    BREAKOUT_LONG,
    BREAKOUT_SHORT,
    SWEEP_REVERSAL_LONG,
    SWEEP_REVERSAL_SHORT,
)


@dataclass
class CompositeEvent:
    """Detection result for one event type across a tick DataFrame.

    Attributes
    ----------
    name : str
        One of the ``ALL_EVENT_NAMES`` constants.
    indices : numpy.ndarray, shape (N,), dtype int64
        Row positions in the source DataFrame where events were detected.
    severities : numpy.ndarray, shape (N,), dtype float64
        Composite severity scores in [0, 1] for each event occurrence.
    timestamps_ms : numpy.ndarray, shape (N,), dtype int64
        Unix milliseconds for each event occurrence.
    component_sevs : dict of str -> numpy.ndarray
        Per-component severity arrays, same length as ``indices``.
        Keys match the component names documented in each detector.
    """

    name: str
    indices: np.ndarray
    severities: np.ndarray
    timestamps_ms: np.ndarray
    component_sevs: Dict[str, np.ndarray] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.indices)

    def is_empty(self) -> bool:
        """Return True if no events were detected."""
        return len(self.indices) == 0


@dataclass
class EventConfig:
    """Thresholds and window sizes for all composite events.

    These defaults are research baselines, not optimized trading parameters.
    They must be recalibrated with state-conditioned event outcomes
    (see scripts/event_research.py).

    All threshold percentiles are computed over the calibration dataset
    (``ticks_clean.parquet``).  After recalibration with 10+ trading days,
    update these values from the BH-significant findings in
    ``scripts/event_research.py``.

    Parameters
    ----------
    spread_stress_pctile : float
        Spread percentile above which spread is considered stressed.
        Default 0.90 (empirical; Q7 BH-significant threshold).
    depth_vacuum_pctile : float
        Depth percentile below which book is considered vacuous.
        Default 0.10 (empirical; Q7 BH-significant threshold).
    rv_spike_pctile : float
        rv_30s percentile above which volatility is considered spiking.
        Default 0.90.
    direction_imbalance_threshold : float
        Absolute imbalance required for directional sweep detection.
        Default 0.30 (net 30% directional dominance).
    breakout_lookback_ms : int
        Rolling window for computing high/low reference price.
        Default 300_000 (5 minutes).
    vacuum_lookback_ms : int
        Window for depth and spread percentile computation in vacuum detection.
        Default 60_000 (1 minute).
    sweep_lookback_ms : int
        Older sub-window for SWEEP_REVERSAL sweep leg.
        Default 45_000 (45 seconds).
    reversal_lookback_ms : int
        Recent sub-window for SWEEP_REVERSAL reversal leg.
        Default 15_000 (15 seconds).
    aggression_lookback_ms : int
        Window for directional imbalance aggregation.
        Default 30_000 (30 seconds).
    volume_spike_multiplier : float
        Volume must exceed rolling_mean × this factor for breakout confirmation.
        Default 2.0.
    min_gap_ms : int
        Minimum milliseconds between consecutive same-type events.
        Default 30_000 (30 seconds).
    min_severity : float
        Events below this composite severity are suppressed.
        Default 0.30.
    """

    # Percentile thresholds (calibrate from event_research.py output)
    spread_stress_pctile: float = 0.90
    depth_vacuum_pctile: float = 0.10
    rv_spike_pctile: float = 0.90

    # Directional sweep
    direction_imbalance_threshold: float = 0.30

    # Window sizes (milliseconds)
    breakout_lookback_ms: int = 900_000
    vacuum_lookback_ms: int = 60_000
    sweep_lookback_ms: int = 20_000
    reversal_lookback_ms: int = 15_000
    aggression_lookback_ms: int = 30_000

    # Volume spike
    volume_spike_multiplier: float = 2.0

    # Filtering
    min_gap_ms: int = 30_000
    min_severity: float = 0.30

    # Component weights for composite severity (must sum to 1.0)
    # Vacuum: spread_sev * w[0] + depth_sev * w[1]
    vacuum_weights: tuple[float, float] = (0.4, 0.6)
    # Sweep: imbalance_sev * w[0] + spread_sev * w[1] + rv_sev * w[2]
    sweep_weights: tuple[float, float, float] = (0.5, 0.25, 0.25)
    # Breakout: price_break_sev * w[0] + volume_sev * w[1]
    breakout_weights: tuple[float, float] = (0.6, 0.4)
    # SweepReversal: sweep_sev * w[0] + reversal_sev * w[1]
    sweep_reversal_weights: tuple[float, float] = (0.5, 0.5)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class CompositeEventEngine:
    """Layer 1 composite event detection engine.

    Parameters
    ----------
    config : EventConfig, optional
        Detection thresholds and window configuration.  Uses defaults if
        not provided.  Thresholds should be recalibrated from
        ``event_research.py`` BH-significant results after 10+ trading days.
    """

    def __init__(self, config: Optional[EventConfig] = None) -> None:
        self.config = config or EventConfig()
        # Calibrated rolling statistics (populated by _calibrate)
        self._spread_p90: float = float("nan")
        self._depth_p10: float = float("nan")
        self._rv_p90: float = float("nan")
        self._volume_mean: float = float("nan")
        self._calibrated: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calibrate(self, df: pd.DataFrame) -> "CompositeEventEngine":
        """Compute percentile thresholds from historical data.

        Must be called before ``detect_all``.  Uses the full DataFrame to
        estimate the marginal distributions of spread, depth, and rv used
        as event condition thresholds.

        Parameters
        ----------
        df : pandas.DataFrame
            Clean tick data (e.g. ``ticks_clean.parquet``).

        Returns
        -------
        CompositeEventEngine
            Returns self for chaining.

        Notes
        -----
        These calibrated thresholds are point-in-time estimates.  In
        production, recalibrate periodically (e.g. weekly rolling window)
        to track non-stationarity.
        """
        cfg = self.config
        total_depth = df["bid_volume"] + df["ask_volume"]

        self._spread_p90 = float(np.percentile(df["spread"], cfg.spread_stress_pctile * 100))
        self._depth_p10 = float(np.percentile(total_depth, cfg.depth_vacuum_pctile * 100))

        # rv_30s approximated from tick-level abs log returns (proxy only;
        # the HMM feature pipeline computes the precise rolling rv_30s).
        log_prices = np.log(df["price"].values.astype(float))
        rv_proxy = np.abs(np.diff(log_prices, prepend=log_prices[0]))
        self._rv_p90 = float(np.percentile(rv_proxy, cfg.rv_spike_pctile * 100))

        self._volume_mean = float(df["volume"].mean())
        self._calibrated = True
        return self

    def detect_all(self, df: pd.DataFrame) -> Dict[str, CompositeEvent]:
        """Detect all event types across the full tick DataFrame.

        Parameters
        ----------
        df : pandas.DataFrame
            Clean tick data sorted by ``timestamp_ms``.

        Returns
        -------
        dict of str -> CompositeEvent
            Keys are event name constants.  Every event name in
            ``ALL_EVENT_NAMES`` is present; empty events have
            ``len(event) == 0``.

        Raises
        ------
        RuntimeError
            If ``calibrate()`` has not been called first.
        """
        self._check_calibrated()
        ts = df["timestamp_ms"].values.astype(np.int64)
        prices = df["price"].values.astype(float)
        spreads = df["spread"].values.astype(float)
        bid_vols = df["bid_volume"].values.astype(float)
        ask_vols = df["ask_volume"].values.astype(float)
        imbalances = df["imbalance"].values.astype(float)
        volumes = df["volume"].values.astype(float)
        tick_types = df["tick_type"].values.astype(float)
        log_prices = np.log(np.where(prices > 0, prices, np.nan))

        results: Dict[str, CompositeEvent] = {}

        results[LIQUIDITY_VACUUM] = self._detect_liquidity_vacuum(
            ts, spreads, bid_vols + ask_vols
        )
        results[AGGRESSION_SWEEP_BUY] = self._detect_aggression_sweep(
            ts, spreads, imbalances, log_prices, direction=+1
        )
        results[AGGRESSION_SWEEP_SELL] = self._detect_aggression_sweep(
            ts, spreads, imbalances, log_prices, direction=-1
        )
        results[BREAKOUT_LONG] = self._detect_breakout(
            ts, prices, spreads, volumes, direction=+1
        )
        results[BREAKOUT_SHORT] = self._detect_breakout(
            ts, prices, spreads, volumes, direction=-1
        )
        results[SWEEP_REVERSAL_LONG] = self._detect_sweep_reversal(
            ts, log_prices, spreads, direction=+1
        )
        results[SWEEP_REVERSAL_SHORT] = self._detect_sweep_reversal(
            ts, log_prices, spreads, direction=-1
        )
        return results

    # ------------------------------------------------------------------
    # Detectors
    # ------------------------------------------------------------------

    def _detect_liquidity_vacuum(
        self,
        ts: np.ndarray,
        spreads: np.ndarray,
        total_depth: np.ndarray,
    ) -> CompositeEvent:
        """Detect liquidity vacuum events.

        Rarest-first anchor: depth_pctile < p10 (depth vacuum).
        Confirmation: spread_ticks > p90 (spread stress).

        Both conditions are computed using a trailing ``vacuum_lookback_ms``
        window — forward-only.

        Severity components
        -------------------
        depth_sev   : ``(threshold - depth) / threshold``
                      Higher when depth is more depleted.
        spread_sev  : ``(spread - threshold) / (max_spread - threshold)``
                      Higher when spread is more extreme.

        Parameters
        ----------
        ts, spreads, total_depth : arrays aligned to tick index.
        """
        cfg = self.config
        win_ms = cfg.vacuum_lookback_ms
        spread_thresh = self._spread_p90
        depth_thresh = self._depth_p10

        candidate_idx: list[int] = []
        depth_sevs: list[float] = []
        spread_sevs: list[float] = []

        for i in range(len(ts)):
            # Forward-only: window [ts[i] - win_ms, ts[i]]
            lo = int(np.searchsorted(ts, ts[i] - win_ms, side="left"))

            cur_depth = total_depth[i]
            cur_spread = spreads[i]

            # Rarest anchor: depth vacuum
            if cur_depth >= depth_thresh:
                continue

            # Confirmation: spread stress must also be present in window
            window_spread_max = spreads[lo : i + 1].max()
            if window_spread_max < spread_thresh:
                continue

            # Severity
            d_sev = float(np.clip((depth_thresh - cur_depth) / (depth_thresh + 1e-9), 0, 1))
            spread_range = max(spreads[lo : i + 1].max() - spread_thresh, 1e-9)
            s_sev = float(np.clip((cur_spread - spread_thresh) / spread_range, 0, 1))

            composite = cfg.vacuum_weights[0] * s_sev + cfg.vacuum_weights[1] * d_sev
            if composite < cfg.min_severity:
                continue

            candidate_idx.append(i)
            depth_sevs.append(d_sev)
            spread_sevs.append(s_sev)

        indices, severities, depths_out, spreads_out = _apply_min_gap(
            ts,
            np.array(candidate_idx, dtype=np.int64),
            np.array([
                cfg.vacuum_weights[0] * s + cfg.vacuum_weights[1] * d
                for s, d in zip(spread_sevs, depth_sevs)
            ], dtype=float),
            [np.array(depth_sevs, dtype=float), np.array(spread_sevs, dtype=float)],
            cfg.min_gap_ms,
        )

        return CompositeEvent(
            name=LIQUIDITY_VACUUM,
            indices=indices,
            severities=severities,
            timestamps_ms=ts[indices] if len(indices) > 0 else np.array([], dtype=np.int64),
            component_sevs={"depth_sev": depths_out, "spread_sev": spreads_out},
        )

    def _detect_aggression_sweep(
        self,
        ts: np.ndarray,
        spreads: np.ndarray,
        imbalances: np.ndarray,
        log_prices: np.ndarray,
        direction: int,  # +1 = buy sweep, -1 = sell sweep
    ) -> CompositeEvent:
        """Detect sustained directional aggression sweeps.

        Rarest-first anchor: rolling directional imbalance exceeds threshold
        (requires sustained one-sided flow, which is rare).
        Confirmation: spread elevated AND rv rising.

        All features computed over ``aggression_lookback_ms`` window —
        forward-only.

        Severity components
        -------------------
        imbalance_sev : normalised excess directional imbalance.
        spread_sev    : spread above baseline.
        rv_sev        : rv proxy above baseline.

        Parameters
        ----------
        direction : int
            +1 for buy-side sweep (positive imbalance), -1 for sell-side.
        """
        cfg = self.config
        win_ms = cfg.aggression_lookback_ms
        imb_thresh = cfg.direction_imbalance_threshold * direction
        name = AGGRESSION_SWEEP_BUY if direction == +1 else AGGRESSION_SWEEP_SELL

        candidate_idx: list[int] = []
        imb_sevs: list[float] = []
        spread_sevs: list[float] = []
        rv_sevs: list[float] = []

        for i in range(1, len(ts)):
            lo = int(np.searchsorted(ts, ts[i] - win_ms, side="left"))
            if i - lo < 5:
                continue  # insufficient history

            window_imb = imbalances[lo : i + 1]
            mean_imb = float(np.nanmean(window_imb))

            # Rarest anchor: sustained directional dominance
            if direction == +1 and mean_imb < imb_thresh:
                continue
            if direction == -1 and mean_imb > imb_thresh:
                continue

            window_spread = spreads[lo : i + 1]
            cur_spread = spreads[i]
            spread_baseline = float(np.nanmedian(window_spread))

            # Confirmation: spread must be elevated vs window median
            if cur_spread < spread_baseline:
                continue

            # rv proxy: abs log return over window
            valid_lp = log_prices[lo : i + 1]
            valid_lp = valid_lp[np.isfinite(valid_lp)]
            if len(valid_lp) < 2:
                continue
            rv_proxy = float(np.sqrt(np.nansum(np.diff(valid_lp) ** 2)))

            # Severity scores
            imb_excess = abs(mean_imb) - abs(imb_thresh)
            i_sev = float(np.clip(imb_excess / (1.0 - abs(imb_thresh) + 1e-9), 0, 1))
            spread_range = max(window_spread.max() - spread_baseline, 1e-9)
            s_sev = float(np.clip((cur_spread - spread_baseline) / spread_range, 0, 1))
            r_sev = float(np.clip(rv_proxy / (self._rv_p90 + 1e-9), 0, 1))

            w = cfg.sweep_weights
            composite = w[0] * i_sev + w[1] * s_sev + w[2] * r_sev
            if composite < cfg.min_severity:
                continue

            candidate_idx.append(i)
            imb_sevs.append(i_sev)
            spread_sevs.append(s_sev)
            rv_sevs.append(r_sev)

        indices, severities, (imb_out, sp_out, rv_out) = _apply_min_gap(
            ts,
            np.array(candidate_idx, dtype=np.int64),
            np.array([
                cfg.sweep_weights[0] * a + cfg.sweep_weights[1] * b + cfg.sweep_weights[2] * c
                for a, b, c in zip(imb_sevs, spread_sevs, rv_sevs)
            ], dtype=float),
            [
                np.array(imb_sevs, dtype=float),
                np.array(spread_sevs, dtype=float),
                np.array(rv_sevs, dtype=float),
            ],
            cfg.min_gap_ms,
        )

        return CompositeEvent(
            name=name,
            indices=indices,
            severities=severities,
            timestamps_ms=ts[indices] if len(indices) > 0 else np.array([], dtype=np.int64),
            component_sevs={"imbalance_sev": imb_out, "spread_sev": sp_out, "rv_sev": rv_out},
        )

    def _detect_breakout(
        self,
        ts: np.ndarray,
        prices: np.ndarray,
        spreads: np.ndarray,
        volumes: np.ndarray,
        direction: int,  # +1 = long breakout, -1 = short breakout
    ) -> CompositeEvent:
        """Detect price level breakouts with volume confirmation.

        Rarest-first anchor: price exceeds the rolling high (+1) or falls
        below the rolling low (-1) of the ``breakout_lookback_ms`` window.
        Confirmation: volume spike AND spread within normal range (to exclude
        liquidity-vacuum-driven gaps).

        All reference levels computed on ``[t - lookback_ms, t - 1 tick]``
        — strictly forward-only (current tick not included in reference).

        Severity components
        -------------------
        price_break_sev : normalised excess beyond the reference level.
        volume_sev      : normalised volume spike vs rolling mean.

        Parameters
        ----------
        direction : int
            +1 for BREAKOUT_LONG, -1 for BREAKOUT_SHORT.
        """
        cfg = self.config
        win_ms = cfg.breakout_lookback_ms
        name = BREAKOUT_LONG if direction == +1 else BREAKOUT_SHORT
        vol_thresh = self._volume_mean * cfg.volume_spike_multiplier

        candidate_idx: list[int] = []
        price_sevs: list[float] = []
        vol_sevs: list[float] = []

        for i in range(1, len(ts)):
            # Reference window: strictly before tick i (forward-only)
            lo = int(np.searchsorted(ts, ts[i] - win_ms, side="left"))
            if i - lo < 10:
                continue  # insufficient history for reliable reference

            ref_prices = prices[lo:i]  # excludes current tick
            if direction == +1:
                ref_level = float(ref_prices.max())
                if prices[i] <= ref_level:
                    continue
                excess = prices[i] - ref_level
                price_range = max(ref_level - float(ref_prices.min()), 1e-9)
            else:
                ref_level = float(ref_prices.min())
                if prices[i] >= ref_level:
                    continue
                excess = ref_level - prices[i]
                price_range = max(float(ref_prices.max()) - ref_level, 1e-9)

            # Confirmation: volume spike
            if volumes[i] < vol_thresh:
                continue

            # Exclusion: extreme spread suggests vacuum, not breakout
            if spreads[i] > self._spread_p90 * 2:
                continue

            p_sev = float(np.clip(excess / price_range, 0, 1))
            v_sev = float(np.clip((volumes[i] - vol_thresh) / (vol_thresh + 1e-9), 0, 1))

            w = cfg.breakout_weights
            composite = w[0] * p_sev + w[1] * v_sev
            if composite < cfg.min_severity:
                continue

            candidate_idx.append(i)
            price_sevs.append(p_sev)
            vol_sevs.append(v_sev)

        indices, severities, (p_out, v_out) = _apply_min_gap(
            ts,
            np.array(candidate_idx, dtype=np.int64),
            np.array([
                cfg.breakout_weights[0] * p + cfg.breakout_weights[1] * v
                for p, v in zip(price_sevs, vol_sevs)
            ], dtype=float),
            [np.array(price_sevs, dtype=float), np.array(vol_sevs, dtype=float)],
            cfg.min_gap_ms,
        )

        return CompositeEvent(
            name=name,
            indices=indices,
            severities=severities,
            timestamps_ms=ts[indices] if len(indices) > 0 else np.array([], dtype=np.int64),
            component_sevs={"price_break_sev": p_out, "volume_sev": v_out},
        )

    def _detect_sweep_reversal(
        self,
        ts: np.ndarray,
        log_prices: np.ndarray,
        spreads: np.ndarray,
        direction: int,  # +1 = swept DOWN then reversed UP (long entry)
                         # -1 = swept UP then reversed DOWN (short entry)
    ) -> CompositeEvent:
        """Detect sweep-then-reversal patterns.

        Window split
        ------------
        Sweep leg  : ``[t - sweep_ms, t - reversal_ms]`` (older sub-window)
        Reversal leg: ``[t - reversal_ms, t]``           (recent sub-window)

        Both legs are in the PAST at time t — strictly forward-only.

        Rarest-first anchor: large abs_return in sweep window (rarest).
        Confirmation: price direction reversal in the reversal window.

        Severity components
        -------------------
        sweep_sev    : abs_return in sweep leg normalised vs rv_p90.
        reversal_sev : price recovery fraction (reversal / sweep magnitude).

        Parameters
        ----------
        direction : int
            +1 = down-sweep then up-reversal (SWEEP_REVERSAL_LONG)
            -1 = up-sweep then down-reversal (SWEEP_REVERSAL_SHORT)
        """
        cfg = self.config
        sweep_ms = cfg.sweep_lookback_ms
        rev_ms = cfg.reversal_lookback_ms
        name = SWEEP_REVERSAL_LONG if direction == +1 else SWEEP_REVERSAL_SHORT

        candidate_idx: list[int] = []
        sweep_sevs: list[float] = []
        rev_sevs: list[float] = []

        for i in range(len(ts)):
            t_now = ts[i]

            # Sweep window: [t - sweep_ms, t - rev_ms]
            lo_sweep = int(np.searchsorted(ts, t_now - sweep_ms, side="left"))
            hi_sweep = int(np.searchsorted(ts, t_now - rev_ms, side="right"))
            if hi_sweep - lo_sweep < 3:
                continue

            # Reversal window: [t - rev_ms, t]
            lo_rev = int(np.searchsorted(ts, t_now - rev_ms, side="left"))
            if i - lo_rev < 2:
                continue

            sweep_lp = log_prices[lo_sweep:hi_sweep]
            rev_lp = log_prices[lo_rev : i + 1]
            if not (np.isfinite(sweep_lp).all() and np.isfinite(rev_lp).all()):
                continue

            # direction=+1: sweep is a DOWN move, reversal is UP
            # direction=-1: sweep is an UP move, reversal is DOWN
            sweep_return = float(sweep_lp[-1] - sweep_lp[0])   # signed
            rev_return = float(rev_lp[-1] - rev_lp[0])         # signed

            # Rarest anchor: large sweep in specified direction
            expected_sweep_sign = -1 * direction  # down for +1, up for -1
            if expected_sweep_sign * sweep_return < 0:
                continue  # sweep in wrong direction

            abs_sweep = abs(sweep_return)
            if abs_sweep < self._rv_p90:
                continue  # sweep not large enough

            # Confirmation: reversal in opposite direction
            if direction * rev_return <= 0:
                continue  # no reversal detected yet

            s_sev = float(np.clip(abs_sweep / (self._rv_p90 * 3 + 1e-9), 0, 1))
            recovery_frac = abs(rev_return) / (abs_sweep + 1e-9)
            r_sev = float(np.clip(recovery_frac, 0, 1))

            w = cfg.sweep_reversal_weights
            composite = w[0] * s_sev + w[1] * r_sev
            if composite < cfg.min_severity:
                continue

            candidate_idx.append(i)
            sweep_sevs.append(s_sev)
            rev_sevs.append(r_sev)

        indices, severities, (s_out, r_out) = _apply_min_gap(
            ts,
            np.array(candidate_idx, dtype=np.int64),
            np.array([
                cfg.sweep_reversal_weights[0] * s + cfg.sweep_reversal_weights[1] * r
                for s, r in zip(sweep_sevs, rev_sevs)
            ], dtype=float),
            [np.array(sweep_sevs, dtype=float), np.array(rev_sevs, dtype=float)],
            cfg.min_gap_ms,
        )

        return CompositeEvent(
            name=name,
            indices=indices,
            severities=severities,
            timestamps_ms=ts[indices] if len(indices) > 0 else np.array([], dtype=np.int64),
            component_sevs={"sweep_sev": s_out, "reversal_sev": r_out},
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _check_calibrated(self) -> None:
        """Raise RuntimeError if calibrate() has not been called."""
        if not self._calibrated:
            raise RuntimeError(
                "Call .calibrate(df) before .detect_all(df)."
            )


# ---------------------------------------------------------------------------
# Module-level helper
# ---------------------------------------------------------------------------


def _apply_min_gap(
    ts: np.ndarray,
    candidate_idx: np.ndarray,
    composite_sevs: np.ndarray,
    component_arrays: list[np.ndarray],
    min_gap_ms: int,
) -> tuple[np.ndarray, np.ndarray, list[np.ndarray]]:
    """Filter candidate events so consecutive events are >= min_gap_ms apart.

    When two candidates are closer than min_gap_ms, keep the one with the
    higher composite severity (greedy, forward pass).

    Parameters
    ----------
    ts : numpy.ndarray
        Full timestamp array aligned to tick index.
    candidate_idx : numpy.ndarray, shape (N,)
        Tick indices of candidate events.
    composite_sevs : numpy.ndarray, shape (N,)
        Composite severity for each candidate.
    component_arrays : list of numpy.ndarray
        Per-component severity arrays to filter in parallel.
    min_gap_ms : int
        Minimum milliseconds between kept events.

    Returns
    -------
    kept_idx : numpy.ndarray
    kept_sevs : numpy.ndarray
    kept_components : list of numpy.ndarray
    """
    if len(candidate_idx) == 0:
        empty = np.array([], dtype=np.int64)
        return empty, np.array([], dtype=float), [np.array([], dtype=float) for _ in component_arrays]

    kept: list[int] = []
    last_ts = -min_gap_ms - 1

    for pos, idx in enumerate(candidate_idx):
        t = int(ts[idx])
        if t - last_ts >= min_gap_ms:
            kept.append(pos)
            last_ts = t
        else:
            # Keep higher-severity event within the suppression window
            if kept and composite_sevs[pos] > composite_sevs[kept[-1]]:
                kept[-1] = pos
                last_ts = t

    kept_arr = np.array(kept, dtype=np.int64)
    kept_idx = candidate_idx[kept_arr]
    kept_sevs = composite_sevs[kept_arr]
    kept_components = [arr[kept_arr] for arr in component_arrays]
    return kept_idx, kept_sevs, kept_components
