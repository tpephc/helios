# features/ud_ratio.py
"""21D Up/Down Ratio — v0.1.4. Module skeleton (Phase B; Step 1 pending).

DataFrame-native feature aligned with the features/* subsystem
convention (panel-in, panel-out, pure function, Polars-native,
LazyFrame-compatible).

This module currently exposes only:
    - Module constants (MIN_OBS, WINDOW, FEATURE_ID, SPEC_VERSION,
      WINDOW_LOOKBACK_BUFFER_DAYS)
    - The public API signature for add_ud_ratio_21d

The function body is intentionally unimplemented in Phase B. Step 1
will fill in the computation under the contracts locked in
docs/features/ud_ratio_21d_spec.md (v0.1.4).

Spec reference: docs/features/ud_ratio_21d_spec.md (v0.1.4)
"""
from __future__ import annotations

import polars as pl


# ── Module constants (locked in spec v0.1.4) ─────────────────────────

# Minimum number of valid daily-return observations required within
# the 21-trading-day window for ud_ratio_21d to be non-null.
# Spec §4.3. Heuristic, NOT empirically optimized.
MIN_OBS: int = 15

# Trailing window length in TRADING days (not calendar days).
# Spec §3.1, §4.3. Locked.
WINDOW: int = 21

# Canonical feature identifier used by downstream consumers and
# governance artefacts. Spec §5.1.
FEATURE_ID: str = "ud_ratio_21d"

# Spec version this module implements against. Bumped in lockstep
# with docs/features/ud_ratio_21d_spec.md version history (§9).
SPEC_VERSION: str = "v0.1.4"

# Calendar-day buffer used by the window-construction algorithm.
# Mechanical bound (not a research threshold) chosen so that
# get_trading_days(t - K calendar days, t) reliably returns >= WINDOW
# trading days even across Taiwan's longest holiday clusters.
# Spec §12.3. Runtime guard inside add_ud_ratio_21d asserts the
# returned length >= WINDOW and raises ValueError on regression.
WINDOW_LOOKBACK_BUFFER_DAYS: int = 45


# ── Public API ────────────────────────────────────────────────────────

def add_ud_ratio_21d(
    df: pl.DataFrame,
    *,
    min_obs: int = MIN_OBS,
) -> pl.DataFrame:
    """Append ud_ratio_21d, n_obs_21d, n_up_21d columns to a panel.

    Sign-frequency persistence feature: fraction of valid trading days
    within the trailing 21-trading-day window on which the daily simple
    return on adjusted close was strictly positive.

    Input contract
    --------------
    df : pl.DataFrame
        Panel with at least:
            stock_id  (Utf8)
            date      (Date)
            adj_close (Float64)
        Sorted ascending by (stock_id, date). One row per
        (stock_id, date) trading-day observation. adj_close sourced
        from listed_market_daily_price_adj (spec §4.4). Direct
        queries against daily_price_adj are FORBIDDEN.

    min_obs : int
        Minimum |S_{i,t}| required for ud_ratio_21d to be non-null.
        Defaults to MIN_OBS (= 15). Exposed for Step 2 sensitivity
        testing in {12, 15, 18}; do NOT mutate the module-level
        constant.

    Output contract
    ---------------
    pl.DataFrame
        Input columns preserved with three appended columns:

            ud_ratio_21d : Float64
                Ratio in [0.0, 1.0] when n_obs_21d >= min_obs,
                else null.
            n_obs_21d : UInt8
                Number of valid return days in the 21d window.
                Range [0, 21].
            n_up_21d : UInt8
                Number of strictly-positive return days.
                Range [0, n_obs_21d] per row.

    Row-level invariants (spec §5.3)
    --------------------------------
    I1  0 <= n_up_21d <= n_obs_21d <= 21
    I2  ud_ratio_21d in [0.0, 1.0]  OR  null
    I3  ud_ratio_21d is null  iff  n_obs_21d < min_obs
    I4  if ud_ratio_21d is not null:
            |ud_ratio_21d - n_up_21d / n_obs_21d| < 1e-12

    Lineage
    -------
    Daily simple returns computed via the canonical R8/Phase 1–6 recipe
    (spec §4.1). Lineage equivalence enforced by PIT-10 (bit-exact
    parity with research/r8_event_builder.py price_panel CTE).

    Trading calendar
    ----------------
    Uses market.trading_calendar (>= v0.2.0). Forbidden imports:
    utils.trading_calendar, utils.trading_dates (spec §12.4).

    Raises
    ------
    ValueError
        Input contract violation: missing columns, wrong dtypes, or
        unsorted panel.
    ValueError
        A date used as window_end is not a trading day (spec §12.2).
        Scope is intentionally narrowed: only rows that participate
        as window_end in computation are validated. Rows that do not
        participate (e.g. insufficient lookback) need not be trading
        days.
    ValueError
        Calendar regression: get_trading_days returned fewer than
        WINDOW (= 21) trading days within
        [date - WINDOW_LOOKBACK_BUFFER_DAYS, date] (spec §12.3).
    NotImplementedError
        Phase B placeholder. Step 1 implementation pending.

    Notes
    -----
    Phase B status: signature and constants are locked. Body is
    NotImplementedError until Step 1 PR lands the computation +
    PIT-1..13 tests.
    """
    raise NotImplementedError(
        "add_ud_ratio_21d is a Phase B skeleton. Step 1 implementation "
        "pending. See docs/features/ud_ratio_21d_spec.md (v0.1.4)."
    )
