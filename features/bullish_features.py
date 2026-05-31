# features/bullish_features.py
"""Bullish accumulation/markup temporal features — pure computation layer — v0.1.0.

Computes multi-bar path-dependent features that capture the
accumulation → markup transition process. These are the temporal
observation layer between raw indicators (daily_features) and future
entry classifiers.

Design invariants (same as bearish_regime.py):
  - Pure functions only: no DB access, no file I/O, no Telegram.
  - Input: Polars DataFrame with columns from daily_features joined with
           daily_price_adj, sorted by date ASC for a single stock_id.
  - Output: DataFrame with bullish feature columns appended.
  - NaN-safe: missing input produces null output, never raises.
  - No state: each call is self-contained.
  - No lookahead: every feature is observable at day t close only.

Feature families:
  1. Persistence      — how long has price been above each MA?
  2. Reclaim quality  — did the reclaim sustain, or was it fleeting?
  3. Accumulation     — volume contraction + tight range (base formation)
  4. Breakout quality — volume expansion + failed breakdown (demand absorption)
  5. Relative strength— beta-adjusted RS vs TAIEX (leadership vs followership)
  6. Volatility       — ATR compression (base formation confirmation)

What this is NOT:
  - Not a scoring function (no weights, no labels)
  - Not a signal generator (find_bullish_setups.py handles listing)
  - Not the inverse of bearish_features
    bearish = downside deterioration detection
    bullish = accumulation timing + breakout confirmation
  - Not a state machine (entry_classifier is Phase 3, after backlog #18/#19)

REMOVED features (lookahead risk — see backlog #19):
  breakout_followthrough_5d: requires close[t+1..t+5], lookahead leakage.
    Belongs in research/bullish_feature_outcomes.py.
  atr_expansion_after_breakout: definition ambiguous without strict
    temporal boundary. Deferred until breakout event is cleanly defined.

All thresholds are [ASSUMED] heuristics pending calibration via
forward outcome study (backlog #18 methodology applied to bullish side).

Version: v0.1.0 (2026-05-26)
Changelog:
  v0.1.0 (2026-05-26): Initial — temporal feature layer for bullish regime.
    Mirrors bearish_regime.py architecture.
    Schema reviewed by Advisor C: lookahead features removed per
    same discipline as bearish P0-2 (failed_reclaim t+1 assignment).
"""
from __future__ import annotations

from math import prod as _prod

import polars as pl


# ── [ASSUMED] thresholds — calibrate from forward outcome study ───────
_HIGH_VOL_THRESHOLD: float = 1.5    # rel_volume_20 >= this → breakout volume
_CONTRACTION_VOL_THRESHOLD: float = 0.7  # rel_volume_20 < this → vol contraction
_ATR_COMPRESSION_MILD: float = 0.8  # atr_14 / baseline < this → mild compression
_ATR_COMPRESSION_FULL: float = 0.6  # atr_14 / baseline < this → full compression
_TIGHT_RANGE_ATR_RATIO: float = 0.8 # same as compression mild — bar is "tight"


# ── Input validation ──────────────────────────────────────────────────

_REQUIRED_COLS = {
    "date", "adj_close", "sma_20", "sma_50", "sma_200",
    "rel_volume_20", "atr_14",
}


def _validate(df: pl.DataFrame) -> None:
    """Raise ValueError if required columns are missing or df is empty."""
    missing = _REQUIRED_COLS - set(df.columns)
    if missing:
        raise ValueError(
            f"bullish_features: missing required columns: {sorted(missing)}"
        )
    if df.is_empty():
        raise ValueError("bullish_features: input DataFrame is empty")


# ── Family 1: Persistence ─────────────────────────────────────────────

def compute_persistence_features(df: pl.DataFrame) -> pl.DataFrame:
    """Count consecutive days the close has been above each MA.

    Counter resets to 0 on any day where close <= MA.
    Null MA values reset the counter (conservative).

    Output columns:
        above_ma20_streak:  int, consecutive trading days close > sma_20
        above_ma50_streak:  int, consecutive trading days close > sma_50

    Naming rationale: "streak" is unambiguous — always a consecutive count
    that resets to 0. Same convention as bearish_regime.py below_ma*_streak.
    """
    _validate(df)

    close = df["adj_close"].to_list()
    ma20  = df["sma_20"].to_list()
    ma50  = df["sma_50"].to_list()

    def _streak(close_list: list, ma_list: list) -> list:
        result = []
        count = 0
        for c, m in zip(close_list, ma_list):
            if c is None or m is None:
                count = 0
                result.append(None)
            elif c > m:
                count += 1
                result.append(count)
            else:
                count = 0
                result.append(0)
        return result

    return df.with_columns([
        pl.Series("above_ma20_streak", _streak(close, ma20), dtype=pl.Int32),
        pl.Series("above_ma50_streak", _streak(close, ma50), dtype=pl.Int32),
    ])


# ── Family 2: Reclaim quality ─────────────────────────────────────────

def compute_reclaim_features(
    df: pl.DataFrame,
    ma20_confirm_days: int = 3,
    ma50_confirm_days: int = 5,
) -> pl.DataFrame:
    """Detect sustained MA reclaims (not fleeting crosses).

    A reclaim is "confirmed" if close has stayed above MA for at least
    confirm_days consecutive bars after crossing from below.

    Temporal semantics: assigned to the day the confirmation threshold
    is first reached (day t), not the crossing day (day t-N). This means
    the feature is observable at day t close — no lookahead.

    Output columns:
        ma20_reclaim_confirmed: int, days since MA20 reclaim was confirmed
            (0 = not recently confirmed, N = confirmed N days ago)
        ma50_reclaim_confirmed: int, same for MA50

    Design note: we store "days since confirmation" rather than a boolean,
    which lets the classifier decide whether a recent confirmation (3 days
    ago) is more valuable than an older one (20 days ago).
    """
    _validate(df)

    close = df["adj_close"].to_list()
    ma20  = df["sma_20"].to_list()
    ma50  = df["sma_50"].to_list()
    n = len(close)

    def _reclaim_confirmed(close_list: list, ma_list: list, confirm: int) -> list:
        """Return days-since-confirmation series."""
        result = [0] * n
        confirmed_at: int | None = None
        consecutive = 0

        for i in range(n):
            c, m = close_list[i], ma_list[i]
            if c is None or m is None:
                consecutive = 0
                confirmed_at = None
                result[i] = 0
                continue

            if c > m:
                consecutive += 1
                if consecutive >= confirm and confirmed_at is None:
                    confirmed_at = i
            else:
                consecutive = 0
                confirmed_at = None

            if confirmed_at is not None:
                result[i] = i - confirmed_at + 1
            else:
                result[i] = 0

        return result

    return df.with_columns([
        pl.Series("ma20_reclaim_confirmed",
                  _reclaim_confirmed(close, ma20, ma20_confirm_days),
                  dtype=pl.Int32),
        pl.Series("ma50_reclaim_confirmed",
                  _reclaim_confirmed(close, ma50, ma50_confirm_days),
                  dtype=pl.Int32),
    ])


# ── Family 3: Accumulation (base formation) ───────────────────────────

def compute_accumulation_features(
    df: pl.DataFrame,
    vol_contraction_window: int = 10,
    tight_range_window: int = 10,
    atr_baseline_window: int = 20,
) -> pl.DataFrame:
    """Detect base formation via volume contraction and tight price range.

    Base formation is characterised by:
      - Volume drying up (no sellers, no buyers, equilibrium)
      - ATR shrinking (price range compressing)
      - Price stabilising near MAs

    These are NOT entry signals — they are preconditions for a valid
    breakout. A breakout without a prior base is more likely to fail.

    Output columns:
        volume_contraction_days_{window}d: int, count of days in window
            where rel_volume_20 < _CONTRACTION_VOL_THRESHOLD (0.7x).
            [ASSUMED] threshold: calibrate from outcome study.
        tight_range_days_{window}d: int, count of days in window where
            atr_14 < _TIGHT_RANGE_ATR_RATIO × rolling_mean(atr_14).
            Measures price range compression, not just low volume.
            Together with volume_contraction, forms "price + volume
            compression" confirmation of base formation.
    """
    _validate(df)

    rvol = df["rel_volume_20"].to_list()
    atr  = df["atr_14"].to_list()
    n = len(rvol)

    # Volume contraction: below threshold
    vol_contract = [
        1 if (rv is not None and rv < _CONTRACTION_VOL_THRESHOLD) else 0
        for rv in rvol
    ]

    # ATR compression: current atr < ratio × rolling baseline
    # Baseline uses past atr_baseline_window bars (excludes today — no lookahead)
    atr_ratios: list[float | None] = [None] * n
    for i in range(atr_baseline_window, n):
        baseline_data = [v for v in atr[i - atr_baseline_window:i] if v is not None]
        if not baseline_data:
            continue
        baseline = sum(baseline_data) / len(baseline_data)
        if baseline > 0 and atr[i] is not None:
            atr_ratios[i] = atr[i] / baseline

    tight_range = [
        1 if (r is not None and r < _TIGHT_RANGE_ATR_RATIO) else 0
        for r in atr_ratios
    ]

    def _rolling_sum(vals: list, w: int) -> list:
        result = []
        for i in range(len(vals)):
            start = max(0, i - w + 1)
            result.append(sum(vals[start:i + 1]))
        return result

    return df.with_columns([
        pl.Series(f"volume_contraction_days_{vol_contraction_window}d",
                  _rolling_sum(vol_contract, vol_contraction_window),
                  dtype=pl.Int32),
        pl.Series(f"tight_range_days_{tight_range_window}d",
                  _rolling_sum(tight_range, tight_range_window),
                  dtype=pl.Int32),
    ])


# ── Family 4: Breakout quality ────────────────────────────────────────

def compute_breakout_quality_features(
    df: pl.DataFrame,
    breakout_window: int = 5,
    absorption_window: int = 10,
) -> pl.DataFrame:
    """Detect breakout quality and demand absorption.

    volume_breakout_days_{window}d: count of high-vol up days.
        High volume on up days signals demand reappearance. Contrasts
        with bearish high_vol_down_days which signals supply.

    failed_breakdown_count_{window}d: trailing count of MA20 close reclaims,
        where a reclaim is close[t-1] < MA20[t-1] AND close[t] > MA20[t].
        This measures MA20 cross-back FREQUENCY, not demand absorption.
        High values may reflect recovery OR repeated whipsaw / chop.
        Treat as a reclaim/whipsaw counter, NOT a bullish-quality score.
        See research/failed_breakdown_quality.py (R2, 2026-05).

    Temporal semantics for failed_breakdown:
        We approximate intraday breakdown as: prev_close < sma_20 on day t-1
        AND close[t] > sma_20 (day t closes above). This is observable at
        day t close — no lookahead. It is assigned to day t, not day t-1,
        because confirmation requires the day t close.

    Output columns:
        volume_breakout_days_{window}d:     int
        failed_breakdown_count_{window}d:   int
    """
    _validate(df)

    close     = df["adj_close"].to_list()
    rvol      = df["rel_volume_20"].to_list()
    ma20      = df["sma_20"].to_list()
    n = len(close)

    hvup = [0] * n   # high-vol up day
    fabd = [0] * n   # failed breakdown (assigned to day t — confirmation)

    for i in range(1, n):
        c_prev, c_cur = close[i - 1], close[i]
        rv = rvol[i]
        m20_prev = ma20[i - 1]
        m20_cur  = ma20[i]

        if c_prev is None or c_cur is None:
            continue

        is_up = c_cur > c_prev

        # High-volume up day: demand reappearance signal
        if is_up and rv is not None and rv >= _HIGH_VOL_THRESHOLD:
            hvup[i] = 1

        # Failed breakdown: prev close was below MA20, today closes above MA20
        # Assigned to day i (the confirmation day) — observable at day i close.
        if (m20_prev is not None and m20_cur is not None
                and c_prev < m20_prev and c_cur > m20_cur):
            fabd[i] = 1

    def _rolling_sum(vals: list, w: int) -> list:
        result = []
        for i in range(len(vals)):
            start = max(0, i - w + 1)
            result.append(sum(vals[start:i + 1]))
        return result

    return df.with_columns([
        pl.Series(f"volume_breakout_days_{breakout_window}d",
                  _rolling_sum(hvup, breakout_window), dtype=pl.Int32),
        pl.Series(f"failed_breakdown_count_{absorption_window}d",
                  _rolling_sum(fabd, absorption_window), dtype=pl.Int32),
    ])


# ── Family 5: Relative strength ───────────────────────────────────────

def compute_relative_strength_features(
    df: pl.DataFrame,
    taiex_df: pl.DataFrame,
    rs_windows: tuple[int, ...] = (20, 60),
) -> pl.DataFrame:
    """Compute beta-adjusted relative return vs TAIEX.

    Identical implementation to bearish_regime.compute_relative_weakness_features.
    The sign interpretation differs:
      - Positive value = stock outperforming TAIEX on beta-adjusted basis
        → relative strength leadership (bullish signal)
      - Negative value = underperformance → relative weakness (bearish signal)

    Both bearish_features and bullish_features use the same column names
    (beta_60, beta_adj_rs_20d, beta_adj_rs_60d) so a join or union is
    straightforward if the classifier needs both perspectives.

    Output columns:
        beta_60:         float, rolling 60d beta vs TAIEX
        beta_adj_rs_20d: float, percentage points
        beta_adj_rs_60d: float, percentage points

    [BACKLOG P1-2]: vectorize with Polars rolling_cov for O(N) vs O(N²).
    v0.1.18: geometric compounding (prod(1+r)-1) replaces arithmetic sum.
        Previously used sum(daily_returns) which understates cumulative
        return for volatile stocks. Beta calculation unchanged (cov/var
        is scale-invariant).
    """
    _validate(df)
    if "taiex_close" not in taiex_df.columns or "date" not in taiex_df.columns:
        raise ValueError("taiex_df must have 'date' and 'taiex_close' columns")

    merged = df.join(
        taiex_df.select(["date", "taiex_close"]),
        on="date",
        how="left",
    )

    close = merged["adj_close"].to_list()
    taiex = merged["taiex_close"].to_list()
    n = len(close)

    new_cols: dict[str, list] = {}
    beta_60_vals: list[float | None] = [None] * n

    for window in rs_windows:
        rs_vals: list[float | None] = [None] * n

        for i in range(window, n):
            s_rets, t_rets = [], []
            for j in range(i - window + 1, i + 1):
                cp, cc = close[j - 1], close[j]
                tp, tc = taiex[j - 1], taiex[j]
                if all(v is not None and v != 0 for v in (cp, cc, tp, tc)):
                    s_rets.append((cc / cp - 1) * 100)
                    t_rets.append((tc / tp - 1) * 100)

            if len(s_rets) < window // 2:
                continue

            nv = len(s_rets)
            s_mean = sum(s_rets) / nv
            t_mean = sum(t_rets) / nv
            cov   = sum((s - s_mean) * (t - t_mean)
                        for s, t in zip(s_rets, t_rets)) / nv
            var_t = sum((t - t_mean) ** 2 for t in t_rets) / nv

            # Geometric compounding (v0.1.18 fix: was arithmetic sum)
            total_s = (_prod(1 + r / 100 for r in s_rets) - 1) * 100
            total_t = (_prod(1 + r / 100 for r in t_rets) - 1) * 100

            if var_t < 1e-10:
                rs_vals[i] = total_s - total_t
                if window == 60:
                    beta_60_vals[i] = None
            else:
                beta = cov / var_t
                rs_vals[i] = total_s - beta * total_t
                if window == 60:
                    beta_60_vals[i] = beta

        new_cols[f"beta_adj_rs_{window}d"] = rs_vals

    new_cols["beta_60"] = beta_60_vals

    return df.with_columns([
        pl.Series(name, vals, dtype=pl.Float64)
        for name, vals in new_cols.items()
    ])


# ── Family 6: Volatility compression ─────────────────────────────────

def compute_volatility_compression_features(
    df: pl.DataFrame,
    baseline_window: int = 20,
    compression_window: int = 10,
) -> pl.DataFrame:
    """Compute ATR compression ratio and persistence.

    Base formation is often accompanied by ATR compression: the daily
    range shrinks as supply and demand reach equilibrium before a
    directional resolution.

    atr_compression_ratio: atr_14[t] / mean(atr_14[t-baseline:t])
        Values < 1.0 indicate below-average volatility (compression).
        Values > 1.0 indicate expansion (breakout or breakdown in progress).

    atr_compression_days_{window}d: count of days in the past window
        where atr_compression_ratio < _ATR_COMPRESSION_MILD.
        Persistence of compression is more meaningful than a single
        compressed bar — markets can compress for weeks before resolving.

    Output columns:
        atr_compression_ratio:              float (e.g. 0.65 = 35% below baseline)
        atr_compression_days_{window}d:     int
    """
    _validate(df)

    atr = df["atr_14"].to_list()
    n = len(atr)

    ratio_vals: list[float | None] = [None] * n
    for i in range(baseline_window, n):
        baseline_data = [v for v in atr[i - baseline_window:i] if v is not None]
        if not baseline_data:
            continue
        baseline = sum(baseline_data) / len(baseline_data)
        if baseline > 0 and atr[i] is not None:
            ratio_vals[i] = atr[i] / baseline

    compressed_flags = [
        1 if (r is not None and r < _ATR_COMPRESSION_MILD) else 0
        for r in ratio_vals
    ]

    def _rolling_sum(vals: list, w: int) -> list:
        result = []
        for i in range(len(vals)):
            start = max(0, i - w + 1)
            result.append(sum(vals[start:i + 1]))
        return result

    return df.with_columns([
        pl.Series("atr_compression_ratio",
                  ratio_vals, dtype=pl.Float64),
        pl.Series(f"atr_compression_days_{compression_window}d",
                  _rolling_sum(compressed_flags, compression_window),
                  dtype=pl.Int32),
    ])


# ── Composite entry point ─────────────────────────────────────────────

def compute_all_bullish_features(
    df: pl.DataFrame,
    taiex_df: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Compute all bullish temporal features for one stock symbol.

    Args:
        df: Daily features + adjusted prices joined, sorted by date ASC,
            single stock_id. Required columns: date, adj_close, sma_20,
            sma_50, sma_200, rel_volume_20, atr_14.
        taiex_df: TAIEX price series (date, taiex_close). If None,
            relative strength features are skipped gracefully.

    Returns:
        df with all bullish feature columns appended.
    """
    _validate(df)

    df = compute_persistence_features(df)
    df = compute_reclaim_features(df)
    df = compute_accumulation_features(df)
    df = compute_breakout_quality_features(df)

    if taiex_df is not None and not taiex_df.is_empty():
        df = compute_relative_strength_features(df, taiex_df)

    df = compute_volatility_compression_features(df)

    # Phase A: continuous distance, slope, spread features
    df = compute_distance_features(df, direction="above")
    df = compute_trend_velocity_features(df)

    return df


# ── Phase A: Distance from MA (ATR-normalized) ───────────────────────


def compute_distance_features(
    df: pl.DataFrame,
    direction: str = "above",
) -> pl.DataFrame:
    """Distance from MA in ATR units.

    Phase A addition (per Phase 0 finding: streak features have limited
    discriminative power; continuous distance captures "how far" not just
    "how many days").

    For bullish (direction="above"):
      dist_above_ma20_atr = (close - sma_20) / atr_14
      dist_above_ma50_atr = (close - sma_50) / atr_14
      Positive = above MA (bullish), negative = below.

    For bearish (direction="below"):
      dist_below_ma20_atr = (sma_20 - close) / atr_14
      dist_below_ma50_atr = (sma_50 - close) / atr_14
      Positive = below MA (bearish), negative = above.
    """
    close = pl.col("adj_close")
    ma20 = pl.col("sma_20")
    ma50 = pl.col("sma_50")
    atr = pl.col("atr_14")

    if direction == "above":
        prefix = "dist_above"
        sign = 1
    else:
        prefix = "dist_below"
        sign = -1

    return df.with_columns([
        (sign * (close - ma20) / atr).alias(f"{prefix}_ma20_atr"),
        (sign * (close - ma50) / atr).alias(f"{prefix}_ma50_atr"),
    ])


def compute_trend_velocity_features(df: pl.DataFrame) -> pl.DataFrame:
    """Trend velocity: MA slope + MA spread (shared bullish/bearish).

    Slope: rate of change of MA over lookback window.
      sma20_slope_10d = sma_20[t] / sma_20[t-10] - 1
      sma50_slope_20d = sma_50[t] / sma_50[t-20] - 1

    Spread: distance between MAs in ATR units (trend separation).
      ma20_ma50_spread_atr = (sma_20 - sma_50) / atr_14
      ma50_ma200_spread_atr = (sma_50 - sma_200) / atr_14

    Positive slope = MA rising. Positive spread = faster MA above slower.
    """
    return df.with_columns([
        # Slope
        (pl.col("sma_20") / pl.col("sma_20").shift(10) - 1)
            .alias("sma20_slope_10d"),
        (pl.col("sma_50") / pl.col("sma_50").shift(20) - 1)
            .alias("sma50_slope_20d"),
        # Spread
        ((pl.col("sma_20") - pl.col("sma_50")) / pl.col("atr_14"))
            .alias("ma20_ma50_spread_atr"),
        ((pl.col("sma_50") - pl.col("sma_200")) / pl.col("atr_14"))
            .alias("ma50_ma200_spread_atr"),
    ])


# ── Schema metadata ───────────────────────────────────────────────────

BULLISH_FEATURE_COLUMNS: list[tuple[str, str]] = [
    # Family 1: Persistence
    ("above_ma20_streak",              "INTEGER"),
    ("above_ma50_streak",              "INTEGER"),
    # Family 2: Reclaim quality
    ("ma20_reclaim_confirmed",         "INTEGER"),
    ("ma50_reclaim_confirmed",         "INTEGER"),
    # Family 3: Accumulation
    ("volume_contraction_days_10d",    "INTEGER"),
    ("tight_range_days_10d",           "INTEGER"),
    # Family 4: Breakout quality
    ("volume_breakout_days_5d",        "INTEGER"),
    ("failed_breakdown_count_10d",     "INTEGER"),
    # Family 5: Relative strength (nullable — requires TAIEX)
    ("beta_60",                        "DOUBLE"),
    ("beta_adj_rs_20d",                "DOUBLE"),
    ("beta_adj_rs_60d",                "DOUBLE"),
    # Family 6: Volatility compression
    ("atr_compression_ratio",          "DOUBLE"),
    ("atr_compression_days_10d",       "INTEGER"),
    # Family 7: Distance from MA (Phase A)
    ("dist_above_ma20_atr",            "DOUBLE"),
    ("dist_above_ma50_atr",            "DOUBLE"),
    # Family 8: Trend velocity (Phase A)
    ("sma20_slope_10d",                "DOUBLE"),
    ("sma50_slope_20d",                "DOUBLE"),
    ("ma20_ma50_spread_atr",           "DOUBLE"),
    ("ma50_ma200_spread_atr",          "DOUBLE"),
]

BULLISH_FEATURE_COLUMN_NAMES: list[str] = [c for c, _ in BULLISH_FEATURE_COLUMNS]
