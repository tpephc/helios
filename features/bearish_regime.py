# features/bearish_regime.py
"""Bearish regime temporal features — pure computation layer — v0.1.0.

Computes multi-bar path-dependent features that capture distribution
regime structure. These features are the temporal abstraction layer
between raw indicators (daily_features) and future regime classifiers.

Design invariants:
  - Pure functions only: no DB access, no file I/O, no Telegram.
  - Input: Polars DataFrame with columns from daily_features joined with
           daily_price_adj, sorted by date ASC for a single stock_id.
  - Output: DataFrame with bearish feature columns appended.
  - NaN-safe: missing input produces null output, never raises.
  - No state: each call is self-contained.

Feature families:
  1. Persistence    — how long has deterioration lasted?
  2. Failed reclaim — how many times has recovery been rejected?
  3. Distribution   — breakdown -> weak rebound -> re-breakdown?
  4. Rel. weakness  — beta-adjusted RS vs TAIEX
  5. Volatility     — ATR expansion persistence

What this is NOT:
  - Not a scoring function (no weights, no labels)
  - Not a state machine (DISTRIBUTING / PANIC states are Phase 3)
  - Not a signal generator

All thresholds are [ASSUMED] heuristics pending calibration via
forward outcome study (see backlog #16 analogue for bearish regime).

Version: v0.1.0 (2026-05-26)
"""
from __future__ import annotations

from math import prod as _prod

import polars as pl


# ── [ASSUMED] thresholds — calibrate from forward outcome study ───────
_HIGH_VOL_THRESHOLD: float = 1.5   # rel_volume_20 >= this → high volume
_WEAK_VOL_THRESHOLD: float = 1.0   # rel_volume_20 < this  → weak volume
_ATR_EXPANSION_MILD: float = 1.2   # atr_14 / baseline > this → mild
_ATR_EXPANSION_FULL: float = 1.5   # atr_14 / baseline > this → full


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
            f"bearish_regime: missing required columns: {sorted(missing)}"
        )
    if df.is_empty():
        raise ValueError("bearish_regime: input DataFrame is empty")


# ── Family 1: Persistence ─────────────────────────────────────────────

def compute_persistence_features(df: pl.DataFrame) -> pl.DataFrame:
    """Count consecutive days the close has been below each MA.

    Counter resets to 0 on any day where close >= MA.
    Null MA values reset the counter to 0 (conservative).

    Output columns:
        below_ma20_streak:  int, consecutive trading days close < sma_20
        below_ma50_streak:  int, consecutive trading days close < sma_50
        below_ma200_streak: int, consecutive trading days close < sma_200

    Naming rationale: "streak" is unambiguous — it is always a consecutive
    count that resets to 0 on any day close >= MA. "days" is ambiguous
    (rolling count? calendar days? trading days?).
    """
    _validate(df)

    close  = df["adj_close"].to_list()
    ma20   = df["sma_20"].to_list()
    ma50   = df["sma_50"].to_list()
    ma200  = df["sma_200"].to_list()

    def _streak(close_list: list, ma_list: list) -> list:
        result = []
        count = 0
        for c, m in zip(close_list, ma_list):
            if c is None or m is None:
                count = 0
                result.append(None)
            elif c < m:
                count += 1
                result.append(count)
            else:
                count = 0
                result.append(0)
        return result

    return df.with_columns([
        pl.Series("below_ma20_streak",  _streak(close, ma20),  dtype=pl.Int32),
        pl.Series("below_ma50_streak",  _streak(close, ma50),  dtype=pl.Int32),
        pl.Series("below_ma200_streak", _streak(close, ma200), dtype=pl.Int32),
    ])


# ── Family 2: Failed reclaim ──────────────────────────────────────────

def compute_failed_reclaim_features(
    df: pl.DataFrame,
    ma20_window: int = 5,
    ma50_window: int = 10,
) -> pl.DataFrame:
    """Count failed recovery attempts within rolling windows.

    A failed reclaim attempt is observed across three consecutive days:
        day t-1: close < MA  (stock was below MA)
        day t:   close >= MA (briefly touched or crossed)
        day t+1: close < MA  (could not sustain — failure confirmed)

    Temporal semantics: the event is assigned to day t+1, NOT day t.
    The failure is only known at t+1 close. Assigning to day t would
    use close[t+1] as a feature available at day t — lookahead leakage.

    This is a daily-close approximation — intraday reclaims are not
    distinguishable from actual reclaims without intraday data.

    Output columns:
        failed_ma20_reclaim_{ma20_window}d: int (rolling count)
        failed_ma50_reclaim_{ma50_window}d: int (rolling count)
    """
    _validate(df)

    close = df["adj_close"].to_list()
    ma20  = df["sma_20"].to_list()
    ma50  = df["sma_50"].to_list()
    n = len(close)

    fa20 = [0] * n
    fa50 = [0] * n

    for i in range(1, n - 1):
        c_prev, c_cur, c_next = close[i - 1], close[i], close[i + 1]

        m20_p, m20_c, m20_n = ma20[i - 1], ma20[i], ma20[i + 1]
        if all(v is not None for v in (c_prev, c_cur, c_next, m20_p, m20_c, m20_n)):
            if c_prev < m20_p and c_cur >= m20_c and c_next < m20_n:
                # Assign to i+1 (not i): the failed reclaim is only confirmed
                # at day t+1 close. Assigning to day t would use future data
                # (close[t+1]) as a feature available at day t — lookahead.
                fa20[i + 1] = 1

        m50_p, m50_c, m50_n = ma50[i - 1], ma50[i], ma50[i + 1]
        if all(v is not None for v in (c_prev, c_cur, c_next, m50_p, m50_c, m50_n)):
            if c_prev < m50_p and c_cur >= m50_c and c_next < m50_n:
                fa50[i + 1] = 1

    def _rolling_sum(vals: list, w: int) -> list:
        result = []
        for i in range(len(vals)):
            start = max(0, i - w + 1)
            result.append(sum(vals[start:i + 1]))
        return result

    return df.with_columns([
        pl.Series(f"failed_ma20_reclaim_{ma20_window}d",
                  _rolling_sum(fa20, ma20_window), dtype=pl.Int32),
        pl.Series(f"failed_ma50_reclaim_{ma50_window}d",
                  _rolling_sum(fa50, ma50_window), dtype=pl.Int32),
    ])


# ── Family 3: Distribution sequence ──────────────────────────────────

def compute_distribution_sequence_features(
    df: pl.DataFrame,
    window: int = 5,
    rebound_window: int = 10,
) -> pl.DataFrame:
    """Capture distribution sequence using primitive observable features.

    Rather than storing a composite heuristic boolean, we store the
    primitives that classifiers can combine as needed. The "rebound"
    definition will evolve — primitives let the classifier adapt
    without requiring a feature recomputation.

    Output columns:
        high_vol_down_days_{window}d:        int, rolling count of high-vol
            down days (rel_vol >= 1.5, close < prev_close)
        weak_rebound_days_{rebound_window}d: int, rolling count of weak-vol
            up days (rel_vol < 1.0, close > prev_close)
        new_low_after_rebound_{window}d:     int, rolling count of days that
            made a new 5d closing low AND were preceded by a weak rebound day

    Rationale for primitives over composite boolean:
        - rebreakdown_after_rebound bakes in a specific threshold
        - primitives are composable: classifier weights them independently
        - easier to validate each primitive in isolation
        - schema stays stable even as the classifier definition changes

    [ASSUMED] thresholds:
        High volume: rel_volume_20 >= 1.5
        Weak volume: rel_volume_20 < 1.0
        New low: close[t] < min(close[t-5:t])
    """
    _validate(df)

    close = df["adj_close"].to_list()
    rvol  = df["rel_volume_20"].to_list()
    n = len(close)

    hvd = [0] * n   # high-volume down bar
    wvu = [0] * n   # weak-volume up bar
    nlo = [0] * n   # new 5d low after weak rebound

    for i in range(1, n):
        c_prev, c_cur = close[i - 1], close[i]
        rv = rvol[i]

        if c_prev is None or c_cur is None:
            continue

        is_down = c_cur < c_prev
        is_up   = c_cur > c_prev

        if is_down and rv is not None and rv >= _HIGH_VOL_THRESHOLD:
            hvd[i] = 1

        if is_up and rv is not None and rv < _WEAK_VOL_THRESHOLD:
            wvu[i] = 1

        # New 5d low after recent weak rebound: any of past 3 bars was
        # a weak rebound, today makes a new closing low vs prior 5 bars.
        # Using a 3-bar window (not just yesterday) captures the case
        # where the distribution pause lasts 2-3 days before re-break.
        # [ASSUMED]: 3 bars is a heuristic — calibrate from outcome study.
        if i >= 5:
            recent_rebound = any(wvu[max(0, i - 3):i])
            if recent_rebound and is_down:
                lookback = [c for c in close[i - 5:i] if c is not None]
                if lookback and c_cur < min(lookback):
                    nlo[i] = 1

    def _rolling_sum(vals: list, w: int) -> list:
        result = []
        for i in range(len(vals)):
            start = max(0, i - w + 1)
            result.append(sum(vals[start:i + 1]))
        return result

    return df.with_columns([
        pl.Series(f"high_vol_down_days_{window}d",
                  _rolling_sum(hvd, window), dtype=pl.Int32),
        pl.Series(f"weak_rebound_days_{rebound_window}d",
                  _rolling_sum(wvu, rebound_window), dtype=pl.Int32),
        pl.Series(f"new_low_after_rebound_{window}d",
                  _rolling_sum(nlo, window), dtype=pl.Int32),
    ])


# ── Family 4: Relative weakness ───────────────────────────────────────

def compute_relative_weakness_features(
    df: pl.DataFrame,
    taiex_df: pl.DataFrame,
    rs_windows: tuple[int, ...] = (20, 60),
) -> pl.DataFrame:
    """Compute beta-adjusted relative return vs TAIEX.

    beta_adj_rs_Nd = cumulative_stock_return_Nd
                     - beta_Nd * cumulative_taiex_return_Nd

    where beta_Nd = rolling_cov(stock, taiex) / rolling_var(taiex).

    Plain RS (stock - index) is misleading for high-beta names. A -5%
    stock return during a -3% TAIEX day is beta-normal for a beta=2
    stock and should not be penalised as individual weakness.

    Args:
        df: Stock DataFrame with adj_close and date columns.
        taiex_df: DataFrame with columns: date, taiex_close.
        rs_windows: Lookback periods in days.

    Output columns:
        beta_adj_rs_20d: float (percentage points)
        beta_adj_rs_60d: float
        beta_60:         float — rolling 60d beta vs TAIEX (the beta
            used in beta_adj_rs_60d computation). Stored separately
            because beta itself is an informative feature: a rising beta
            during a downtrend indicates increasing market correlation,
            a pattern associated with institutional deleveraging.

    [ASSUMED]: rolling beta is a stable estimator over the window.
    In practice, beta shifts with regime — this is an approximation
    adequate for daily screening but not for precise attribution.
    """
    _validate(df)
    if "taiex_close" not in taiex_df.columns or "date" not in taiex_df.columns:
        raise ValueError("taiex_df must have 'date' and 'taiex_close' columns")

    merged = df.join(
        taiex_df.select(["date", "taiex_close"]),
        on="date",
        how="left",
    )

    close  = merged["adj_close"].to_list()
    taiex  = merged["taiex_close"].to_list()
    n = len(close)

    # [BACKLOG P1-2]: beta calculation is O(N²) — acceptable for current
    # universe size (~200 symbols × 1200 bars ≈ 0.8s/symbol). If universe
    # expands or nightly pipeline time grows, vectorize using Polars
    # rolling_cov / rolling_var expressions instead of Python loops.

    # v0.1.18: geometric compounding (prod(1+r)-1) replaces arithmetic sum.
    # Previously used sum(daily_returns) which understates cumulative
    # return for volatile stocks. Beta calculation unchanged (cov/var
    # is scale-invariant).

    new_cols: dict[str, list] = {}
    beta_60_vals: list[float | None] = [None] * n  # stored separately

    for window in rs_windows:
        rs_vals: list[float | None] = [None] * n

        for i in range(window, n):
            # Compute daily returns for the window
            s_rets = []
            t_rets = []
            for j in range(i - window + 1, i + 1):
                c_prev, c_cur = close[j - 1], close[j]
                t_prev, t_cur = taiex[j - 1], taiex[j]
                if all(v is not None and v != 0
                       for v in (c_prev, c_cur, t_prev, t_cur)):
                    s_rets.append((c_cur / c_prev - 1) * 100)
                    t_rets.append((t_cur / t_prev - 1) * 100)

            if len(s_rets) < window // 2:
                continue  # insufficient valid data

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
                    beta_60_vals[i] = None  # undefined when market flat
            else:
                beta = cov / var_t
                rs_vals[i] = total_s - beta * total_t
                if window == 60:
                    beta_60_vals[i] = beta

        new_cols[f"beta_adj_rs_{window}d"] = rs_vals

    # Always include beta_60 (None if 60 not in rs_windows)
    new_cols["beta_60"] = beta_60_vals

    return df.with_columns([
        pl.Series(name, vals, dtype=pl.Float64)
        for name, vals in new_cols.items()
    ])


# ── Family 5: Volatility clustering ──────────────────────────────────

def compute_volatility_features(
    df: pl.DataFrame,
    baseline_window: int = 20,
    persistence_window: int = 5,
) -> pl.DataFrame:
    """Compute ATR expansion ratio and persistence count.

    atr_expansion_ratio: atr_14[t] / mean(atr_14[t-baseline_window:t])
        Excludes today from baseline to avoid look-ahead.

    atr_expansion_days_{persistence_window}d: count of days in past
        persistence_window where expansion_ratio > _ATR_EXPANSION_MILD.

    Output columns:
        atr_expansion_ratio:                float
        atr_expansion_days_{window}d:       int
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

    # Persistence: count of days in window with ratio > mild threshold
    expanded_flags = [
        1 if (r is not None and r > _ATR_EXPANSION_MILD) else 0
        for r in ratio_vals
    ]

    def _rolling_sum(vals: list, w: int) -> list:
        result = []
        for i in range(len(vals)):
            start = max(0, i - w + 1)
            result.append(sum(vals[start:i + 1]))
        return result

    return df.with_columns([
        pl.Series("atr_expansion_ratio",
                  ratio_vals, dtype=pl.Float64),
        pl.Series(f"atr_expansion_days_{persistence_window}d",
                  _rolling_sum(expanded_flags, persistence_window),
                  dtype=pl.Int32),
    ])


# ── Composite entry point ─────────────────────────────────────────────

def compute_all_bearish_features(
    df: pl.DataFrame,
    taiex_df: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Compute all bearish temporal features for one stock symbol.

    Args:
        df: Daily features + adjusted prices joined, sorted by date ASC,
            single stock_id. Required columns: date, adj_close, sma_20,
            sma_50, sma_200, rel_volume_20, atr_14.
        taiex_df: TAIEX price series (date, taiex_close). If None,
            relative weakness features are skipped gracefully.

    Returns:
        df with all bearish feature columns appended. Original columns
        are preserved unchanged.
    """
    _validate(df)

    df = compute_persistence_features(df)
    df = compute_failed_reclaim_features(df)
    df = compute_distribution_sequence_features(df)

    if taiex_df is not None and not taiex_df.is_empty():
        df = compute_relative_weakness_features(df, taiex_df)

    df = compute_volatility_features(df)

    # Phase A: continuous distance, slope, spread features
    df = _compute_distance_features_below(df)
    df = _compute_trend_velocity_features(df)

    return df


def _compute_distance_features_below(df: pl.DataFrame) -> pl.DataFrame:
    """Distance below MA in ATR units (Phase A).

    dist_below_ma20_atr = (sma_20 - close) / atr_14
    dist_below_ma50_atr = (sma_50 - close) / atr_14

    Positive = below MA (bearish), negative = above.
    """
    return df.with_columns([
        ((pl.col("sma_20") - pl.col("adj_close")) / pl.col("atr_14"))
            .alias("dist_below_ma20_atr"),
        ((pl.col("sma_50") - pl.col("adj_close")) / pl.col("atr_14"))
            .alias("dist_below_ma50_atr"),
    ])


def _compute_trend_velocity_features(df: pl.DataFrame) -> pl.DataFrame:
    """Trend velocity: MA slope + MA spread (shared bullish/bearish).

    Same computation as bullish — slope and spread are directionally
    neutral (positive slope = MA rising in both contexts).
    """
    return df.with_columns([
        (pl.col("sma_20") / pl.col("sma_20").shift(10) - 1)
            .alias("sma20_slope_10d"),
        (pl.col("sma_50") / pl.col("sma_50").shift(20) - 1)
            .alias("sma50_slope_20d"),
        ((pl.col("sma_20") - pl.col("sma_50")) / pl.col("atr_14"))
            .alias("ma20_ma50_spread_atr"),
        ((pl.col("sma_50") - pl.col("sma_200")) / pl.col("atr_14"))
            .alias("ma50_ma200_spread_atr"),
    ])


# ── Schema metadata (consumed by data/database.py and migration) ──────

#: (column_name, sql_type) for bearish_features table
BEARISH_FEATURE_COLUMNS: list[tuple[str, str]] = [
    # Family 1: Persistence (consecutive trading day streak)
    ("below_ma20_streak",              "INTEGER"),
    ("below_ma50_streak",              "INTEGER"),
    ("below_ma200_streak",             "INTEGER"),
    # Family 2: Failed reclaim
    ("failed_ma20_reclaim_5d",         "INTEGER"),
    ("failed_ma50_reclaim_10d",        "INTEGER"),
    # Family 3: Distribution sequence (primitives — no composite boolean)
    ("high_vol_down_days_5d",          "INTEGER"),
    ("weak_rebound_days_10d",          "INTEGER"),
    ("new_low_after_rebound_5d",       "INTEGER"),
    # Family 4: Relative weakness (nullable — requires TAIEX data)
    ("beta_60",                        "DOUBLE"),   # rolling 60d beta vs TAIEX
    ("beta_adj_rs_20d",                "DOUBLE"),
    ("beta_adj_rs_60d",                "DOUBLE"),
    # Family 5: Volatility clustering
    ("atr_expansion_ratio",            "DOUBLE"),
    ("atr_expansion_days_5d",          "INTEGER"),
    # Family 6: Distance from MA (Phase A)
    ("dist_below_ma20_atr",            "DOUBLE"),
    ("dist_below_ma50_atr",            "DOUBLE"),
    # Family 7: Trend velocity (Phase A)
    ("sma20_slope_10d",                "DOUBLE"),
    ("sma50_slope_20d",                "DOUBLE"),
    ("ma20_ma50_spread_atr",           "DOUBLE"),
    ("ma50_ma200_spread_atr",          "DOUBLE"),
]

BEARISH_FEATURE_COLUMN_NAMES: list[str] = [c for c, _ in BEARISH_FEATURE_COLUMNS]
