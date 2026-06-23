# features/ud_ratio.py
"""21D Up/Down Ratio — v0.1.4. Phase 1A: entry-point validation only.

Phase 1A scope:
    - Input contract validation (_validate_input)
    - Window-end trading-day guard (_validate_window_calendar)
    - K=45 lookback + len(all_td) >= WINDOW guard (_derive_window_dates)
    - All guards execute before raising NotImplementedError for the
      computation body, which is deferred to Phase 1B.

The function shape is locked at v0.1.4: DataFrame-native, panel-in,
panel-out (when fully implemented). The validation layer is the
boundary between "this call is well-formed" and "this call should
produce a result". Phase 1A delivers the former.

Spec reference: docs/features/ud_ratio_21d_spec.md (v0.1.4)
"""
from __future__ import annotations

from datetime import date, timedelta

import polars as pl

from market.trading_calendar import get_trading_days, is_trading_day


# ── Module constants (locked in spec v0.1.4) ─────────────────────────

MIN_OBS: int = 15
WINDOW: int = 21
FEATURE_ID: str = "ud_ratio_21d"
SPEC_VERSION: str = "v0.1.4"
WINDOW_LOOKBACK_BUFFER_DAYS: int = 45


# Required input column names with their canonical Polars dtypes.
# Spec §5.1.
_REQUIRED_INPUT_SCHEMA: dict[str, pl.DataType] = {
    "stock_id":  pl.Utf8,
    "date":      pl.Date,
    "adj_close": pl.Float64,
}


# ── Input validation ──────────────────────────────────────────────────

def _validate_input(df: pl.DataFrame) -> None:
    """Validate the input DataFrame against the spec §5.1 contract.

    Checks (Phase 1A scope per GATE-S1-IMPL-001 Q3):
        1. Required columns present:  stock_id, date, adj_close
        2. Dtypes exact:              Utf8, Date, Float64
                                      (Float32 explicitly rejected
                                      to avoid precision drift)
        3. Sorted ascending by (stock_id, date)
        4. No duplicate (stock_id, date) rows
           (panel contract; required for unambiguous rolling-window
           semantics)

    The function is intentionally narrow: it does NOT check
    adj_close > 0 (that is a row-level validity predicate inside the
    canonical SQL recipe per spec §4.2), and does NOT check that
    every date is a trading day (spec §12.2 narrows this to
    window_end dates only).

    Raises:
        ValueError: on any of the four checks failing. Error messages
                    identify which check and where (column names,
                    first-offending row indices) so failures are
                    diagnosable without re-running.
    """
    # 1. Required columns
    missing = set(_REQUIRED_INPUT_SCHEMA) - set(df.columns)
    if missing:
        raise ValueError(
            f"add_ud_ratio_21d: input is missing required columns "
            f"{sorted(missing)}; got columns {df.columns}"
        )

    # 2. Dtype exact match
    actual_schema = dict(df.schema)
    for col, expected_dtype in _REQUIRED_INPUT_SCHEMA.items():
        actual = actual_schema[col]
        if actual != expected_dtype:
            raise ValueError(
                f"add_ud_ratio_21d: column '{col}' has dtype "
                f"{actual!r}, expected {expected_dtype!r}. "
                f"Float32 / int variants are intentionally rejected "
                f"to avoid precision drift in the daily-return "
                f"computation."
            )

    # Empty panel is structurally valid (no rows to validate further)
    if df.is_empty():
        return

    # 3. Sorted ascending by (stock_id, date)
    sorted_df = df.sort(["stock_id", "date"])
    if not df["stock_id"].equals(sorted_df["stock_id"]) or not df["date"].equals(
        sorted_df["date"]
    ):
        raise ValueError(
            "add_ud_ratio_21d: input is not sorted ascending by "
            "(stock_id, date). Pre-sort with df.sort(['stock_id', "
            "'date']) before calling."
        )

    # 4. No duplicate (stock_id, date)
    n_total = df.height
    n_unique = df.select(["stock_id", "date"]).unique().height
    if n_unique != n_total:
        n_dupes = n_total - n_unique
        raise ValueError(
            f"add_ud_ratio_21d: input contains {n_dupes} duplicate "
            f"(stock_id, date) row(s). The panel contract requires "
            f"exactly one row per (stock_id, date); duplicates would "
            f"produce ambiguous rolling-window semantics."
        )


# ── Window calendar validation ────────────────────────────────────────

def _validate_window_calendar(window_end: date) -> None:
    """Spec §12.2: a date used as window_end must be a trading day.

    Scope intentionally narrowed (vs every input row) per Edit A in
    v0.1.4: the feature layer's responsibility is to validate
    computation windows, not the entire dataset.

    Raises:
        ValueError: window_end is not a trading day per
                    market.trading_calendar.is_trading_day.
    """
    if not is_trading_day(window_end):
        raise ValueError(
            f"add_ud_ratio_21d: date {window_end} is not a trading "
            f"day (weekend, public holiday, or market closure). "
            f"Per spec §12.2, dates used as window_end must be "
            f"trading days."
        )


# ── Window date derivation ────────────────────────────────────────────

def _derive_window_dates(window_end: date) -> list[date]:
    """Derive the 21 trading days ending at window_end.

    Spec §12.3 algorithm:
        1. Look back K = WINDOW_LOOKBACK_BUFFER_DAYS (= 45) calendar days
        2. Collect all trading days in
           [window_end - K calendar days, window_end]
        3. Fail-fast if fewer than WINDOW (= 21) trading days returned
           (calendar regression or unusual holiday cluster)
        4. Return the most recent WINDOW trading days

    The fail-fast in step 3 is what guards against silent short-window
    results if K is ever insufficient for an unusual holiday cluster.

    Args:
        window_end: trading-day end of the rolling window. Caller is
                    responsible for calling _validate_window_calendar
                    first; this function does NOT re-check.

    Returns:
        Exactly WINDOW = 21 trading days in ascending order, with
        window[-1] == window_end.

    Raises:
        ValueError: the trading calendar returned fewer than WINDOW
                    days within the buffer window. The error message
                    includes the calendar interval and the count so
                    operators can diagnose calendar regressions.
    """
    look_back_start = window_end - timedelta(days=WINDOW_LOOKBACK_BUFFER_DAYS)
    all_td = get_trading_days(look_back_start, window_end)

    if len(all_td) < WINDOW:
        raise ValueError(
            f"add_ud_ratio_21d: trading-day calendar returned "
            f"{len(all_td)} days in [{look_back_start}, {window_end}], "
            f"need >= {WINDOW}. Possible causes: extended holiday "
            f"cluster, calendar regression, or "
            f"WINDOW_LOOKBACK_BUFFER_DAYS (= {WINDOW_LOOKBACK_BUFFER_DAYS}) "
            f"is too narrow. Investigate before adjusting the buffer."
        )

    # Defensive: the calendar should always return window_end as the
    # last element when it is a trading day. If the calendar contract
    # ever changes, fail loudly rather than silently producing a
    # misaligned window.
    if all_td[-1] != window_end:
        raise RuntimeError(
            f"add_ud_ratio_21d: internal consistency failure — "
            f"trading-day calendar returned last day {all_td[-1]}, "
            f"expected {window_end}. This indicates a calendar "
            f"contract violation in market.trading_calendar."
        )

    return all_td[-WINDOW:]


# ── Public API ────────────────────────────────────────────────────────

def add_ud_ratio_21d(
    df: pl.DataFrame,
    *,
    min_obs: int = MIN_OBS,
) -> pl.DataFrame:
    """Append ud_ratio_21d, n_obs_21d, n_up_21d columns to a panel.

    See docs/features/ud_ratio_21d_spec.md (v0.1.4) for the full
    contract. Phase 1A status: entry-point validation only. The
    computation body is delivered in Phase 1B.

    Raises:
        ValueError: input contract violation (missing columns, wrong
                    dtypes, unsorted, duplicate rows).
        ValueError: a date used as window_end is not a trading day.
        ValueError: trading-day calendar returned fewer than WINDOW
                    days within the lookback buffer.
        NotImplementedError: Phase 1B body not yet implemented.
    """
    _validate_input(df)

    # Phase 1A: validate window-end / calendar for each unique date
    # in the panel. Phase 1B may refine the set of "window_end" dates
    # (e.g. exclude rows that won't be computed due to insufficient
    # history); for now we validate ALL unique dates as a strict
    # upper bound. This is intentionally stricter than the eventual
    # behaviour and ensures Phase 1A test fixtures are clean.
    if not df.is_empty():
        unique_dates = df["date"].unique().sort().to_list()
        for window_end in unique_dates:
            _validate_window_calendar(window_end)
            _derive_window_dates(window_end)

    raise NotImplementedError(
        "add_ud_ratio_21d: Phase 1A delivers entry-point validation "
        "only. Computation body (Phase 1B) is pending. See "
        "docs/features/ud_ratio_21d_spec.md (v0.1.4)."
    )
