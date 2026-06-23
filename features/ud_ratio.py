# features/ud_ratio.py
"""21D Up/Down Ratio — v0.1.4. Phase 1B: full computation.

Phase 1B scope:
    - Phase 1A guards retained (_validate_input, _validate_window_calendar,
      _derive_window_dates)
    - Daily simple return computed per spec §4.1 with validity predicate
      strictly aligned to §4.2 (prev_adj_close > 0, adj_close > 0,
      both non-null)
    - Rolling counts (n_obs_21d, n_up_21d) computed per stock via
      Polars rolling_sum with min_samples=1 (short-history support)
    - ud_ratio_21d = n_up_21d / n_obs_21d when n_obs_21d >= min_obs,
      else null (no imputation)
    - Internal intermediate columns are NOT exposed in the output

Output is the input panel with three appended columns:
    ud_ratio_21d : Float64
    n_obs_21d    : UInt8
    n_up_21d     : UInt8

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


# Required input schema (spec §5.1)
_REQUIRED_INPUT_SCHEMA: dict[str, pl.DataType] = {
    "stock_id":  pl.Utf8,
    "date":      pl.Date,
    "adj_close": pl.Float64,
}

# Internal intermediate column names. Prefixed with double underscore
# to clearly mark them as private; they are dropped before return.
_TMP_PREV_CLOSE = "__ud_ratio_prev_adj_close"
_TMP_DAILY_RET  = "__ud_ratio_daily_ret"
_TMP_IS_VALID   = "__ud_ratio_is_valid_return"
_TMP_IS_UP      = "__ud_ratio_is_up_return"


# ── Input validation ──────────────────────────────────────────────────

def _validate_input(df: pl.DataFrame) -> None:
    """Validate the input DataFrame against the spec §5.1 contract.

    See Phase 1A docstring for full description. Phase 1B reuses
    this verbatim from Phase 1A.
    """
    missing = set(_REQUIRED_INPUT_SCHEMA) - set(df.columns)
    if missing:
        raise ValueError(
            f"add_ud_ratio_21d: input is missing required columns "
            f"{sorted(missing)}; got columns {df.columns}"
        )

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

    if df.is_empty():
        return

    sorted_df = df.sort(["stock_id", "date"])
    if not df["stock_id"].equals(sorted_df["stock_id"]) or not df["date"].equals(
        sorted_df["date"]
    ):
        raise ValueError(
            "add_ud_ratio_21d: input is not sorted ascending by "
            "(stock_id, date). Pre-sort with df.sort(['stock_id', "
            "'date']) before calling."
        )

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
    """Spec §12.2: a date used as window_end must be a trading day."""
    if not is_trading_day(window_end):
        raise ValueError(
            f"add_ud_ratio_21d: date {window_end} is not a trading "
            f"day (weekend, public holiday, or market closure). "
            f"Per spec §12.2, dates used as window_end must be "
            f"trading days."
        )


# ── Window date derivation ────────────────────────────────────────────

def _derive_window_dates(window_end: date) -> list[date]:
    """Derive the 21 trading days ending at window_end (spec §12.3)."""
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

    if all_td[-1] != window_end:
        raise RuntimeError(
            f"add_ud_ratio_21d: internal consistency failure — "
            f"trading-day calendar returned last day {all_td[-1]}, "
            f"expected {window_end}. This indicates a calendar "
            f"contract violation in market.trading_calendar."
        )

    return all_td[-WINDOW:]


# ── Core computation ──────────────────────────────────────────────────

def _compute_ud_ratio_columns(df: pl.DataFrame, *, min_obs: int) -> pl.DataFrame:
    """Append ud_ratio_21d, n_obs_21d, n_up_21d to df.

    Implements §3.2, §3.3, §4.1, §4.2, §4.3, §5.2.

    Algorithm:
        1. Compute prev_adj_close = lag(adj_close) within stock_id.
        2. Compute daily_ret = adj_close / prev_adj_close - 1.0,
           NULL where validity predicate fails (§4.2).
        3. Compute boolean indicators:
               is_valid = daily_ret is not null
               is_up    = daily_ret > 0.0  (strict, no epsilon, L2)
        4. Rolling sums over 21-row windows, per stock_id:
               n_obs_21d = sum(is_valid)
               n_up_21d  = sum(is_up)
           min_samples=1 supports short history (rows 0..19 within
           a stock_id; spec L4).
        5. ud_ratio_21d = n_up_21d / n_obs_21d when n_obs_21d >= min_obs,
           else null (§4.3).
        6. Drop intermediates; return only public schema (L-extra:
           daily_ret is NOT exposed).

    The validity predicate (§4.2) is enforced inside the daily_ret
    expression:
        prev_adj_close IS NOT NULL AND prev_adj_close > 0
        adj_close      IS NOT NULL AND adj_close      > 0
    Any failure -> daily_ret = NULL, which propagates through the
    rolling sums (NULL excluded from sum by Polars semantics, and
    n_obs decrements correctly).
    """
    return (
        df
        # Step 1: lag adj_close within stock_id
        .with_columns(
            pl.col("adj_close").shift(1).over("stock_id").alias(_TMP_PREV_CLOSE)
        )
        # Step 2: daily simple return, NULL when validity fails
        .with_columns(
            pl.when(
                pl.col(_TMP_PREV_CLOSE).is_not_null()
                & (pl.col(_TMP_PREV_CLOSE) > 0.0)
                & pl.col("adj_close").is_not_null()
                & (pl.col("adj_close") > 0.0)
            )
            .then(pl.col("adj_close") / pl.col(_TMP_PREV_CLOSE) - 1.0)
            .otherwise(None)
            .alias(_TMP_DAILY_RET)
        )
        # Step 3: validity / up indicators (Int8 for rolling_sum)
        .with_columns(
            pl.col(_TMP_DAILY_RET).is_not_null().cast(pl.Int8).alias(_TMP_IS_VALID),
            # Strict r > 0.0 (L2: no epsilon). When daily_ret is null,
            # the comparison yields null; cast null -> 0 explicitly so
            # rolling sum is well-defined.
            pl.when(pl.col(_TMP_DAILY_RET).is_not_null() & (pl.col(_TMP_DAILY_RET) > 0.0))
              .then(pl.lit(1, dtype=pl.Int8))
              .otherwise(pl.lit(0, dtype=pl.Int8))
              .alias(_TMP_IS_UP),
        )
        # Step 4: rolling sums per stock_id, min_samples=1 for short history
        .with_columns(
            pl.col(_TMP_IS_VALID)
              .rolling_sum(window_size=WINDOW, min_samples=1)
              .over("stock_id")
              .cast(pl.UInt8)
              .alias("n_obs_21d"),
            pl.col(_TMP_IS_UP)
              .rolling_sum(window_size=WINDOW, min_samples=1)
              .over("stock_id")
              .cast(pl.UInt8)
              .alias("n_up_21d"),
        )
        # Step 5: ratio gated by min_obs
        .with_columns(
            pl.when(pl.col("n_obs_21d") >= min_obs)
              .then(pl.col("n_up_21d").cast(pl.Float64) / pl.col("n_obs_21d").cast(pl.Float64))
              .otherwise(None)
              .alias("ud_ratio_21d")
        )
        # Step 6: drop internals; keep ud_ratio_21d, n_obs_21d, n_up_21d
        .drop([_TMP_PREV_CLOSE, _TMP_DAILY_RET, _TMP_IS_VALID, _TMP_IS_UP])
    )


def _validate_output(df: pl.DataFrame, *, min_obs: int) -> None:
    """Defensive post-compute check of row-level invariants (§5.3).

    I1: 0 <= n_up_21d <= n_obs_21d <= 21
    I2: ud_ratio_21d in [0.0, 1.0] OR null
    I3: ud_ratio_21d is null iff n_obs_21d < min_obs
    I4: when not null, |ud_ratio_21d - n_up_21d / n_obs_21d| < 1e-12

    Raises RuntimeError on violation (not ValueError, because these
    are internal post-conditions, not input contract violations).
    """
    if df.is_empty():
        return

    # I1 range
    bad_i1 = df.filter(
        (pl.col("n_obs_21d") > WINDOW)
        | (pl.col("n_up_21d") > pl.col("n_obs_21d"))
    )
    if bad_i1.height > 0:
        raise RuntimeError(
            f"add_ud_ratio_21d: I1 violation in {bad_i1.height} row(s). "
            f"First offender: {bad_i1.head(1).to_dicts()[0]}"
        )

    # I2 range
    bad_i2 = df.filter(
        pl.col("ud_ratio_21d").is_not_null()
        & ((pl.col("ud_ratio_21d") < 0.0) | (pl.col("ud_ratio_21d") > 1.0))
    )
    if bad_i2.height > 0:
        raise RuntimeError(
            f"add_ud_ratio_21d: I2 violation in {bad_i2.height} row(s). "
            f"First offender: {bad_i2.head(1).to_dicts()[0]}"
        )

    # I3 coupling
    bad_i3 = df.filter(
        (pl.col("ud_ratio_21d").is_null() & (pl.col("n_obs_21d") >= min_obs))
        | (pl.col("ud_ratio_21d").is_not_null() & (pl.col("n_obs_21d") < min_obs))
    )
    if bad_i3.height > 0:
        raise RuntimeError(
            f"add_ud_ratio_21d: I3 violation in {bad_i3.height} row(s). "
            f"First offender: {bad_i3.head(1).to_dicts()[0]}"
        )

    # I4 self-consistency
    bad_i4 = df.filter(
        pl.col("ud_ratio_21d").is_not_null()
        & (
            (
                pl.col("ud_ratio_21d")
                - pl.col("n_up_21d").cast(pl.Float64) / pl.col("n_obs_21d").cast(pl.Float64)
            ).abs()
            > 1e-12
        )
    )
    if bad_i4.height > 0:
        raise RuntimeError(
            f"add_ud_ratio_21d: I4 violation in {bad_i4.height} row(s). "
            f"First offender: {bad_i4.head(1).to_dicts()[0]}"
        )


# ── Public API ────────────────────────────────────────────────────────

def add_ud_ratio_21d(
    df: pl.DataFrame,
    *,
    min_obs: int = MIN_OBS,
) -> pl.DataFrame:
    """Append ud_ratio_21d, n_obs_21d, n_up_21d columns to a panel.

    See docs/features/ud_ratio_21d_spec.md (v0.1.4) for the full
    contract.

    Phase 1B status: full computation implemented (Pure Polars).

    Raises:
        ValueError: input contract violation (missing columns, wrong
                    dtypes, unsorted, duplicate rows).
        ValueError: a date used as window_end is not a trading day.
        ValueError: trading-day calendar returned fewer than WINDOW
                    days within the lookback buffer.
        RuntimeError: internal post-condition violation (I1–I4).
        RuntimeError: calendar contract violation in market.trading_calendar.
    """
    _validate_input(df)

    if not df.is_empty():
        unique_dates = df["date"].unique().sort().to_list()
        for window_end in unique_dates:
            _validate_window_calendar(window_end)
            _derive_window_dates(window_end)

    result = _compute_ud_ratio_columns(df, min_obs=min_obs)
    _validate_output(result, min_obs=min_obs)
    return result
