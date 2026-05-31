#!/usr/bin/env python3
# research/forward_return_tracker.py
"""Forward Return Tracker — v0.3.6.

Tracks unbiased forward returns for all production signals.

Why this exists
---------------
Historical backtesting with a survivorship-biased universe (current-constituent
replay confirmed 2026-05-30) cannot serve as go-live alpha evidence.  The only
unbiased observations available are signals generated in real time, before their
outcomes are known.

This script:
  1. Scans the signals table for all strategy signals (all approval statuses).
  2. Looks up T+1 adj_open as the execution reference price.
  3. Computes forward returns at each available calendar day in the holding window.
  4. Persists observations incrementally; re-runs safely fill in missing days.
  5. Forces resolution when elapsed trading days >= MAX_HOLDING_DAYS, regardless
     of per-stock price availability.
  6. Prints a summary report of resolved observations.

Run schedule
------------
Add to cron after market close, after build_adjusted_prices.py completes:
    10 16 * * 1-5  cd ~/projects/helios && uv run python research/forward_return_tracker.py >> logs/forward_tracker.log 2>&1

Data model
----------
One row per (signal_id, holding_day).

    holding_day = 0   : obs_date = T+1 (entry day; close price after the open entry)
    holding_day = N-1 : obs_date = T+N (close on the Nth trading day after signal_date)

Entry is at T+1 adj_open.  Day-0 observation is T+1 adj_close (same calendar day).
The 20-day horizon therefore spans T+1 open → T+20 close.

Incremental update contract
----------------------------
The PRIMARY KEY is (signal_id, holding_day).  Each run:
  - skips signals already fully resolved (max_holding_day >= MAX_HOLDING_DAYS-1)
  - re-processes all partial signals, inserting only missing days via
    ON CONFLICT DO NOTHING

This is safe to run multiple times without data corruption.

Resolved semantics (v2)
-----------------------
resolved = True  iff  elapsed TWSE trading days >= MAX_HOLDING_DAYS and this is
the terminal row (holding_day = MAX_HOLDING_DAYS - 1).

Resolution is triggered by elapsed calendar days, NOT by per-stock price count.
Stocks halted during the window are resolved with imputed prices (forced_resolved
= True).  See forced_resolved and imputed_exit columns.

Missing-price policy (4-case)
------------------------------
case 1  at least one post-entry adj_close available, then halt:
        → terminal row uses last available adj_close
        → imputed_exit = True, imputation_reason = "last_available_adj_close"

case 3  zero post-entry adj_close available:
        → terminal row applies -100% net_return_t1 haircut
        → adj_close = NULL
        → imputed_exit = True, imputation_reason = "no_price_after_entry"
        → LONG_ONLY_INVARIANT: haircut is valid only for unlevered long cash-equity.
          Do NOT inherit for short strategies, futures, or leveraged products.

Intermediate rows with no price (case 3, non-terminal) are skipped to avoid
null-data pollution.  Intermediate rows with last-available imputation (case 1)
are inserted for audit continuity.

Entry price choices (both stored)
------------------------------------
signal_price      : signals.price at generation time.
                    Measures raw signal predictive power, no execution cost.

t1_adj_open       : adj_open on T+1 trading day (execution reference).
                    Subject to gap risk; not guaranteed fill.

Primary metric for go-live decision  : t1_adj_open-based net_return_t1.
Primary metric for signal quality    : signal_price-based gross_return_signal.

Cost model (v2)
---------------
Taiwan stock round-trip cost (discount broker):
    buy  brokerage   : ~4–5 bps
    sell brokerage   : ~4–5 bps
    sell tax         : 30 bps  (securities transaction tax, sell side only)
    entry slippage   : 5 bps   (assumed fill degradation vs adj_open)
    ─────────────────────────
    total deducted   : ~45 bps

cost_bps and entry_slippage_bps are stored per row so the cost model can be
audited and reconstructed independently of the constants in this file.

Confidence interval (v2)
--------------------------
The iid t-interval used in v1 was invalid: overlapping 20-day windows and a
shared market factor create cross-sectional dependence between signals entered
on the same date.  v2 replaces it with a cluster-by-signal-date bootstrap.

Effective n reported = number of unique signal_dates.  This is an upper bound on
the truly independent sample size (adjacent-entry serial overlap is not fully
captured by date clustering), but it is substantially more conservative than
nominal n.

Go-live gate (per strategy) — ALL five conditions required
-----------------------------------------------------------
  1. resolved_signals      >= 150
  2. mean_net_return_20d   >  0
  3. hit_rate_20d          >  0.52    [heuristic; see note below]
  4. ci_95_lower_bound     >  0       (cluster bootstrap; requires n_clusters >= 2)
  5. no_month_mean_below   >= -0.02   (worst calendar-month mean return)

Note: condition 3 (hit_rate > 52%) is a heuristic threshold.  It is necessary
but not sufficient: a positive-skew strategy can have hit < 50% and still carry
positive expectancy.  Treat as a diagnostic rather than a causal gate condition.
Condition 5 is also sensitive to small-sample noise; treat as a diagnostic when
n is well below 150.

Conditions 1–3 are necessary but not sufficient.
Conditions 4–5 require adequate sample size; n < 30 warning is emitted.
Do NOT relax any condition without explicit written justification.

Strategy version isolation
---------------------------
Signals from different strategy versions (trend_pullback_v1 vs v2) must not
be mixed in the same aggregate statistics.  tracker_schema_version guards
against schema changes that would silently corrupt the time series.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date as Date
from datetime import timedelta
from typing import NamedTuple

import numpy as np
import pandas as pd

from data.database import connect


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STRATEGIES: tuple[str, ...] = ("trend_pullback_v1", "trend_breakout_v1")
MAX_HOLDING_DAYS: int = 20

# Taiwan discount broker round-trip (buy + sell brokerage + sell tax).
ROUND_TRIP_COST_BPS: float = 40.0

# Assumed fill degradation vs T+1 adj_open (entry slippage, one-way).
# Must match or exceed the harness minimum (currently 5 bps).
ENTRY_SLIPPAGE_BPS: float = 5.0

# Bootstrap parameters for CI estimation.
BOOTSTRAP_N_SAMPLES: int = 10_000
BOOTSTRAP_CONFIDENCE: float = 0.95

OBS_TABLE: str = "forward_return_observations"

# Bump when schema changes; prevents mixing observations from incompatible
# versions.  v1 → v2: added forced_resolved, imputed_exit, imputation_reason,
# entry_slippage_bps, cost_bps; changed resolution trigger to elapsed trading
# days; replaced iid CI with cluster bootstrap.
TRACKER_SCHEMA_VERSION: int = 2


# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------

_CREATE_OBS_TABLE = f"""
CREATE TABLE IF NOT EXISTS {OBS_TABLE} (
    -- Identity
    signal_id              VARCHAR NOT NULL,
    symbol                 VARCHAR NOT NULL,
    strategy               VARCHAR NOT NULL,
    strategy_version       VARCHAR NOT NULL,
    tracker_schema_version INTEGER NOT NULL,

    -- Signal context at generation time
    approval_status        VARCHAR NOT NULL,
    signal_date            DATE    NOT NULL,
    regime                 VARCHAR,
    rs_percentile          DOUBLE,
    beta_percentile        DOUBLE,
    dist_ma20_atr          DOUBLE,
    priority_zone          VARCHAR,

    -- Entry prices (signal-level, repeated per row for query convenience)
    signal_price           DOUBLE,
    t1_adj_open            DOUBLE,
    t1_date                DATE,

    -- Observation
    holding_day            INTEGER NOT NULL,
    obs_date               DATE    NOT NULL,
    adj_close              DOUBLE,

    -- Derived returns (computed at insert time)
    gross_return_signal    DOUBLE,
    gross_return_t1        DOUBLE,
    net_return_t1          DOUBLE,

    -- Resolution
    -- resolved: True iff elapsed trading days >= MAX_HOLDING_DAYS and this is
    --           the terminal row (holding_day = MAX_HOLDING_DAYS - 1).
    resolved               BOOLEAN NOT NULL DEFAULT false,

    -- forced_resolved: True on the terminal row when resolved via elapsed-day
    --                  trigger despite missing per-stock prices in the window.
    forced_resolved        BOOLEAN NOT NULL DEFAULT false,

    -- imputed_exit: True on any row where adj_close was not a real market price.
    imputed_exit           BOOLEAN NOT NULL DEFAULT false,

    -- imputation_reason: 'last_available_adj_close' | 'no_price_after_entry' | NULL
    imputation_reason      VARCHAR,

    -- Cost governance: stored per row so the cost model is auditable even if
    --                  constants change in future versions.
    entry_slippage_bps     DOUBLE,
    cost_bps               DOUBLE,

    PRIMARY KEY (signal_id, holding_day)
)
"""

# All column names in schema order.  Used for explicit INSERT.
_OBS_COLUMNS: tuple[str, ...] = (
    "signal_id", "symbol", "strategy", "strategy_version",
    "tracker_schema_version", "approval_status", "signal_date", "regime",
    "rs_percentile", "beta_percentile", "dist_ma20_atr", "priority_zone",
    "signal_price", "t1_adj_open", "t1_date", "holding_day", "obs_date",
    "adj_close", "gross_return_signal", "gross_return_t1", "net_return_t1",
    "resolved", "forced_resolved", "imputed_exit", "imputation_reason",
    "entry_slippage_bps", "cost_bps",
)

_OBS_COLUMNS_SQL: str = ", ".join(_OBS_COLUMNS)


def _ensure_table(conn) -> None:
    conn.execute(_CREATE_OBS_TABLE)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_signals(conn) -> pd.DataFrame:
    """Load signals with deduplication.

    The signals table has no UNIQUE constraint on (symbol, strategy, signal_date).
    Multiple runs of find_bullish_setups.py can insert duplicate signal_ids for
    the same alpha event.  Counting duplicates as independent observations would
    inflate n, bias the mean, and corrupt the bootstrap CI.

    Dedup strategy: ROW_NUMBER() OVER (PARTITION BY symbol, strategy, signal_date
    ORDER BY created_at ASC, signal_id ASC) — keep the earliest signal per event.
    The signal_id tiebreaker makes the selection deterministic when created_at ties.
    """
    return conn.execute(
        """
        WITH ranked_signals AS (
            SELECT
                signal_id,
                symbol,
                strategy,
                approval_status,
                signal_date,
                regime,
                price AS signal_price,
                metadata,
                ROW_NUMBER() OVER (
                    PARTITION BY symbol, strategy, signal_date
                    ORDER BY created_at ASC, signal_id ASC
                ) AS rn
            FROM signals
            WHERE strategy IN (SELECT unnest($1))
        )
        SELECT
            signal_id,
            symbol,
            strategy,
            approval_status,
            signal_date,
            regime,
            signal_price,
            metadata
        FROM ranked_signals
        WHERE rn = 1
        ORDER BY signal_date, symbol, strategy
        """,
        [list(STRATEGIES)],
    ).df()


def _load_signal_progress(
    conn, canonical_signal_ids: frozenset[str]
) -> dict[str, int]:
    """Return {signal_id: max_holding_day} for canonical v2 signals with observations.

    Filtered to canonical_signal_ids so that stale observations written for
    duplicate (non-canonical) signal_ids from previous tracker runs do not
    affect incremental update logic or the complete_ids set in main().
    """
    rows = conn.execute(
        f"""
        SELECT signal_id, MAX(holding_day) AS max_day
        FROM {OBS_TABLE}
        WHERE tracker_schema_version = {TRACKER_SCHEMA_VERSION}
          AND signal_id IN (SELECT unnest($1))
        GROUP BY signal_id
        """,
        [list(canonical_signal_ids)],
    ).fetchall()
    return {r[0]: int(r[1]) for r in rows}


def _get_trading_dates_after(conn, from_date: Date, n: int) -> list[Date]:
    """Return up to n+1 trading dates >= from_date from daily_price_adj calendar.

    Note: internally fetches LIMIT n+1 rows.  Callers receive at most n+1 dates.
    The TWSE official calendar is the authoritative source; daily_price_adj
    coverage is validated by check_benchmark_calendar_gap.py before migration.
    """
    rows = conn.execute(
        "SELECT DISTINCT date FROM daily_price_adj "
        "WHERE date >= $1 ORDER BY date LIMIT $2",
        [from_date, n + 1],
    ).fetchall()
    return [r[0] for r in rows]


def _get_adj_close_series(
    conn, symbol: str, dates: list[Date]
) -> dict[Date, float]:
    """Return {date: adj_close} for available (symbol, date) pairs only.

    Returned dict may be sparse: missing dates indicate halted or suspended
    trading.  Callers must not assume every requested date is present.
    """
    if not dates:
        return {}
    # Both symbol and dates are parameterized.
    # DuckDB supports passing a list[Date] as a parameter and unnesting it
    # into an IN subquery, avoiding any string interpolation for date values.
    rows = conn.execute(
        "SELECT date, adj_close FROM daily_price_adj "
        "WHERE stock_id = $1 AND date IN (SELECT unnest($2))",
        [symbol, dates],
    ).fetchall()
    return {r[0]: float(r[1]) for r in rows}


# ---------------------------------------------------------------------------
# Metadata parsing
# ---------------------------------------------------------------------------

def _parse_metadata(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return {}


def _priority_zone(dist: float | None) -> str:
    if dist is None:
        return "UNKNOWN"
    if dist < -1.0:
        return "HIGH"
    if dist < 0.0:
        return "NORMAL"
    return "ABOVE_MA20"


def _strategy_version(strategy: str) -> str:
    """Extract version suffix from strategy name.

    Examples:
        "trend_pullback_v1"  → "v1"
        "trend_breakout_v2"  → "v2"
        "unknown_strategy"   → "unknown"
    """
    parts = strategy.rsplit("_", 1)
    if len(parts) == 2 and parts[1].startswith("v") and parts[1][1:].isdigit():
        return parts[1]
    return "unknown"


# ---------------------------------------------------------------------------
# Observation construction
# ---------------------------------------------------------------------------

def _build_observations(
    sig: dict,
    t1_date: Date,
    t1_adj_open: float,
    obs_dates: list[Date],
    price_series: dict[Date, float],
    start_day_idx: int,
    entry_slippage_bps: float,
    cost_bps: float,
) -> list[dict]:
    """Build observation rows for a single signal.

    Iterates over obs_dates (the TWSE trading calendar for this signal's
    forward window) rather than over price_series.  This ensures that
    missing per-stock prices trigger imputation rather than silent exclusion
    from the gate denominator.

    Resolution (v2):
        fully_resolved = len(obs_dates) >= MAX_HOLDING_DAYS
        Elapsed calendar days, NOT available price count.

    Imputation:
        case 1 (adj_close available on some days, then halt):
            intermediate and terminal rows use last available adj_close.
            imputed_exit = True on imputed rows.
        case 3 (zero adj_close since entry):
            intermediate rows are SKIPPED (no null-data pollution).
            terminal row: net_return_t1 = -1.0 (LONG_ONLY_INVARIANT).
            imputed_exit = True on terminal row.

    Only builds rows for holding_day >= start_day_idx (incremental update).
    """
    meta = _parse_metadata(sig.get("metadata"))
    dist = meta.get("dist_above_ma20_atr")
    signal_price: float | None = sig.get("signal_price")

    total_cost: float = (cost_bps + entry_slippage_bps) / 10_000

    # v2 resolution: driven by calendar completeness, not price availability.
    fully_resolved: bool = len(obs_dates) >= MAX_HOLDING_DAYS

    # forced_resolved applies to the terminal row when calendar is complete
    # but the stock has missing prices in the window.
    signal_is_forced: bool = (
        fully_resolved and (len(price_series) < MAX_HOLDING_DAYS)
    )

    rows: list[dict] = []
    last_price: float | None = None

    for day_idx, obs_date in enumerate(obs_dates):
        # Track last_price even for already-inserted days (imputation continuity).
        price_today = price_series.get(obs_date)
        if price_today is not None:
            last_price = price_today

        if day_idx < start_day_idx:
            continue  # already in DB; advance last_price tracking above

        is_terminal: bool = day_idx == MAX_HOLDING_DAYS - 1
        price_available: bool = obs_date in price_series

        # --- Determine adj_close and imputation metadata ---
        adj_close: float | None
        imputed: bool
        reason: str | None

        if price_available:
            adj_close = price_series[obs_date]
            imputed = False
            reason = None
        elif last_price is not None:
            adj_close = last_price           # case 1: carry last known price
            imputed = True
            reason = "last_available_adj_close"
        else:
            adj_close = None                 # case 3: no price since entry
            imputed = True
            reason = "no_price_after_entry"

        # Skip non-terminal case-3 rows: no meaningful data to store.
        if adj_close is None and not is_terminal:
            continue

        # --- Compute returns ---
        gross_t1: float | None
        net_t1: float | None

        if adj_close is not None and t1_adj_open and t1_adj_open > 0:
            gross_t1 = adj_close / t1_adj_open - 1.0
            net_t1 = gross_t1 - total_cost
        else:
            if is_terminal and reason == "no_price_after_entry":
                # LONG_ONLY_INVARIANT: -100% is the worst-case bound for an
                # unlevered long cash-equity position.  Do NOT inherit for
                # short strategies, futures, or leveraged products.
                # gross_t1 is set to -1.0 (same haircut) so that gross and
                # net return columns have consistent sample sizes in analysis.
                # This is a modelled value, not a market price calculation.
                gross_t1 = -1.0
                net_t1 = -1.0
            else:
                gross_t1 = None
                net_t1 = None

        gross_signal: float | None = (
            (adj_close / signal_price - 1.0)
            if (adj_close is not None and signal_price and signal_price > 0)
            else None
        )

        resolved: bool = fully_resolved and is_terminal
        # forced_resolved flags the terminal row of a force-resolved signal.
        forced_resolved_flag: bool = is_terminal and signal_is_forced

        rows.append({
            "signal_id":              sig["signal_id"],
            "symbol":                 sig["symbol"],
            "strategy":               sig["strategy"],
            "strategy_version":       _strategy_version(sig["strategy"]),
            "tracker_schema_version": TRACKER_SCHEMA_VERSION,
            "approval_status":        sig["approval_status"],
            "signal_date":            sig["signal_date"],
            "regime":                 sig.get("regime"),
            "rs_percentile":          meta.get("rs_percentile"),
            "beta_percentile":        meta.get("beta_percentile"),
            "dist_ma20_atr":          dist,
            "priority_zone":          _priority_zone(dist),
            "signal_price":           signal_price,
            "t1_adj_open":            t1_adj_open,
            "t1_date":                t1_date,
            "holding_day":            day_idx,
            "obs_date":               obs_date,
            "adj_close":              adj_close,
            "gross_return_signal":    gross_signal,
            "gross_return_t1":        gross_t1,
            "net_return_t1":          net_t1,
            "resolved":               resolved,
            "forced_resolved":        forced_resolved_flag,
            "imputed_exit":           imputed,
            "imputation_reason":      reason,
            "entry_slippage_bps":     entry_slippage_bps,
            "cost_bps":               cost_bps,
        })

    return rows


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

class BootstrapCI(NamedTuple):
    """Result of a cluster bootstrap confidence interval computation."""

    ci_lower: float
    ci_upper: float
    n_clusters: int   # number of unique signal_dates (effective n)


def _cluster_bootstrap_ci(
    returns: pd.Series,
    signal_dates: pd.Series,
    n_boot: int = BOOTSTRAP_N_SAMPLES,
    confidence: float = BOOTSTRAP_CONFIDENCE,
    seed: int = 42,
) -> BootstrapCI:
    """Cluster-by-signal-date bootstrap CI on the mean net return.

    Why cluster bootstrap (not iid t-interval):
        Signals entered on the same date share one forward market path for the
        entire 20-day window.  Treating them as independent observations
        understates variance and produces falsely narrow CIs (→ false positives
        on the gate).  Clustering by signal_date accounts for this
        cross-sectional dependence.

    Residual limitation:
        Signals entered on adjacent dates have overlapping forward windows and
        are still correlated.  Cluster-by-signal-date does not capture this
        serial dependence.  Effective n (n_clusters) is therefore an upper
        bound on the truly independent sample size, not an exact count.
        Do not interpret n_clusters as certifying full independence.

    Args:
        returns:      Series of net_return_t1 values for resolved signals.
        signal_dates: Series of signal_date values aligned with returns.
        n_boot:       Number of bootstrap resamples.
        confidence:   Confidence level (default 0.95).
        seed:         Random seed for reproducibility.

    Returns:
        BootstrapCI with (ci_lower, ci_upper, n_clusters).
        ci_lower and ci_upper are NaN when n_clusters < 2.
    """
    unique_dates = sorted(signal_dates.unique())
    n_clusters = len(unique_dates)

    if n_clusters < 2:
        return BootstrapCI(float("nan"), float("nan"), n_clusters)

    # Build cluster arrays once; resampling draws by cluster index.
    clusters: list[np.ndarray] = [
        returns[signal_dates == d].values for d in unique_dates
    ]

    rng = np.random.default_rng(seed)
    boot_means = np.empty(n_boot, dtype=np.float64)

    for i in range(n_boot):
        idx = rng.integers(0, n_clusters, size=n_clusters)
        sample = np.concatenate([clusters[j] for j in idx])
        boot_means[i] = sample.mean()

    alpha = 1.0 - confidence
    # np.quantile uses linear interpolation by default; consistent with
    # np.percentile but with a cleaner [0, 1] interface.
    # 10,000 samples gives ~0.1% precision on percentile estimates.
    # For n_clusters > 500, consider reducing to 5,000 with negligible precision loss.
    ci_lower = float(np.quantile(boot_means, alpha / 2.0))
    ci_upper = float(np.quantile(boot_means, 1.0 - alpha / 2.0))

    return BootstrapCI(ci_lower, ci_upper, n_clusters)


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def _find_stuck_signals(
    conn, canonical_signal_ids: frozenset[str]
) -> list[dict]:
    """Return canonical signals that should be resolved but have no resolved row.

    A signal is 'stuck' if elapsed TWSE trading days since t1_date >= MAX_HOLDING_DAYS
    but NO resolved=true row exists.  Under v2, forced-resolution logic should
    prevent this; presence of stuck signals indicates a processing error.

    Filters to canonical_signal_ids so duplicate signal observations from earlier
    runs are not misreported as stuck.

    Uses HAVING SUM(resolved) = 0 to correctly exclude signals that have
    intermediate (resolved=false) rows AND a terminal (resolved=true) row —
    those are fully resolved and must not appear here.
    """
    max_date_row = conn.execute(
        "SELECT MAX(date) FROM daily_price_adj"
    ).fetchone()
    if not max_date_row or max_date_row[0] is None:
        return []
    as_of_date = max_date_row[0]

    # Only return signal_ids with zero resolved=true rows at any holding_day.
    unresolved = conn.execute(
        f"""
        SELECT signal_id, strategy, symbol,
               MIN(t1_date) AS t1_date,
               MAX(holding_day) AS max_day
        FROM {OBS_TABLE}
        WHERE tracker_schema_version = {TRACKER_SCHEMA_VERSION}
          AND signal_id IN (SELECT unnest($1))
        GROUP BY signal_id, strategy, symbol
        HAVING SUM(CASE WHEN resolved THEN 1 ELSE 0 END) = 0
        """,
        [list(canonical_signal_ids)],
    ).fetchall()

    stuck: list[dict] = []
    for row in unresolved:
        signal_id, strategy, symbol, t1_date, max_day = row
        elapsed = conn.execute(
            "SELECT COUNT(DISTINCT date) FROM daily_price_adj "
            "WHERE date > $1 AND date <= $2",
            [t1_date, as_of_date],
        ).fetchone()[0]
        if elapsed >= MAX_HOLDING_DAYS:
            stuck.append({
                "signal_id":       signal_id,
                "strategy":        strategy,
                "symbol":          symbol,
                "t1_date":         t1_date,
                "elapsed_days":    elapsed,
                "max_holding_day": max_day,
            })

    return stuck


# ---------------------------------------------------------------------------
# Calendar integrity
# ---------------------------------------------------------------------------

def _assert_calendar_integrity(conn) -> None:
    """Abort execution if calendar gaps are detected (INV-1).

    Enforces that the trading-day index in daily_price_adj is complete before
    any observations are written.  A gap silently corrupts elapsed-day counts
    for all in-progress signals from the gap date forward.

    Raises RuntimeError on failure so the caller's context manager (with connect())
    runs its __exit__ and closes the connection before the process halts.

    Lookback: 30 calendar days (fast startup check for recent pipeline failures).
    For a full 90-day pre-migration validation run
    scripts/check_benchmark_calendar_gap.py separately.

    Requires exchange_calendars (uv add exchange_calendars).  ImportError is a
    hard failure — if the check cannot run, execution must not proceed.
    Use --skip-calendar-check to bypass explicitly in dev/debug environments.
    """
    try:
        import exchange_calendars as xcals
    except ImportError as exc:
        raise RuntimeError(
            "exchange_calendars is required for INV-1 calendar integrity check.\n"
            "  Install with: uv add exchange_calendars\n"
            "  Or bypass with: --skip-calendar-check  "
            "(not safe for production migration)"
        ) from exc

    today = Date.today()
    end_date = today - timedelta(days=1)
    start_date = today - timedelta(days=30)

    cal = xcals.get_calendar("XTAI")
    expected = {
        s.date()
        for s in cal.sessions_in_range(
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d"),
        )
    }

    db_dates = {
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT date FROM daily_price_adj "
            "WHERE date >= $1 AND date <= $2",
            [start_date, end_date],
        ).fetchall()
    }

    gaps = sorted(expected - db_dates)
    if gaps:
        missing_str = str([str(d) for d in gaps[:5]])
        suffix = " ..." if len(gaps) > 5 else ""
        raise RuntimeError(
            f"{len(gaps)} calendar gap(s) detected in daily_price_adj "
            f"(trailing 30 days).\n"
            f"  Missing: {missing_str}{suffix}\n"
            f"  Run check_benchmark_calendar_gap.py for full details.\n"
            f"  Do NOT write observations until gaps are resolved."
        )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _check_gate(
    n: int,
    mean_r: float,
    hit: float,
    ci_lower: float,
    worst_month_mean: float,
) -> dict[str, bool]:
    """Evaluate all five go-live gate conditions.

    Note: hit>52% and worst_month>=-2% are heuristic thresholds that are
    included as diagnostic indicators, not causal conditions.  hit rate without
    payoff context can reject a valid positive-skew signal.
    """
    return {
        "n>=150":           n >= 150,
        "mean>0":           mean_r > 0,
        "hit>52%":          hit > 0.52,
        "ci_lower>0":       (not np.isnan(ci_lower)) and ci_lower > 0,
        "worst_month>=-2%": worst_month_mean >= -0.02,
    }


def _print_summary(conn, seed: int = 42) -> None:
    print()
    print("=" * 72)
    print("FORWARD RETURN TRACKER — SUMMARY")
    print(f"  Schema version : {TRACKER_SCHEMA_VERSION}")
    print(
        f"  Entry ref      : T+1 adj_open  |  "
        f"Cost: {ROUND_TRIP_COST_BPS:.0f} bps + "
        f"{ENTRY_SLIPPAGE_BPS:.0f} bps slippage = "
        f"{ROUND_TRIP_COST_BPS + ENTRY_SLIPPAGE_BPS:.0f} bps total"
    )
    print(
        f"  Horizon        : {MAX_HOLDING_DAYS}d  |  "
        f"CI: cluster-by-signal-date bootstrap "
        f"(n={BOOTSTRAP_N_SAMPLES:,}, seed={seed})"
    )
    print("=" * 72)

    # --- Load canonical signal set ---
    # signals_df from _load_signals() is the single canonical truth after dedup.
    # Deriving canonical_ids here (rather than calling a separate query) avoids
    # a race condition if a new signal is inserted between two separate queries.
    _signals_for_report = _load_signals(conn)
    canonical_ids = frozenset(_signals_for_report["signal_id"].astype(str))
    # IN (SELECT unnest($1)) is acceptable at current scale (<10k signals).

    # --- Upstream duplicate diagnostic ---
    # Detects signals table inflation from repeated find_bullish_setups.py runs.
    # Reported every run so any worsening trend is visible in logs.
    dup_rows = conn.execute(
        """
        SELECT
            strategy,
            COUNT(*) AS raw_signal_rows,
            COUNT(DISTINCT symbol || '|' || strategy || '|' ||
                  CAST(signal_date AS VARCHAR)) AS dedup_events,
            COUNT(*) - COUNT(DISTINCT symbol || '|' || strategy || '|' ||
                             CAST(signal_date AS VARCHAR)) AS duplicate_rows
        FROM signals
        WHERE strategy IN (SELECT unnest($1))
        GROUP BY strategy
        ORDER BY strategy
        """,
        [list(STRATEGIES)],
    ).fetchall()

    has_duplicates = any(r[3] > 0 for r in dup_rows)
    if has_duplicates:
        print("\n  ⚠  UPSTREAM SIGNAL DUPLICATES (Layer 1 fix pending):")
        for r in dup_rows:
            print(
                f"    {r[0]:<35} "
                f"raw={r[1]}  dedup={r[2]}  duplicate_rows={r[3]}"
            )
    else:
        print("\n  Upstream signal integrity: OK (no duplicates detected)")

    # --- Load resolved terminal rows (canonical, v2 only, explicit column list) ---
    resolved_df = conn.execute(
        f"""
        SELECT {_OBS_COLUMNS_SQL} FROM {OBS_TABLE}
        WHERE resolved = true
          AND tracker_schema_version = {TRACKER_SCHEMA_VERSION}
          AND signal_id IN (SELECT unnest($1))
        ORDER BY signal_date
        """,
        [list(canonical_ids)],
    ).df()

    # --- In-progress counts (canonical, v2 only) ---
    inprogress = conn.execute(
        f"""
        SELECT strategy, COUNT(DISTINCT signal_id) AS n
        FROM {OBS_TABLE}
        WHERE resolved = false
          AND tracker_schema_version = {TRACKER_SCHEMA_VERSION}
          AND signal_id IN (SELECT unnest($1))
        GROUP BY strategy
        """,
        [list(canonical_ids)],
    ).fetchall()

    if not inprogress and resolved_df.empty:
        print("\n  No observations yet.")
        return

    if inprogress:
        print("\n  IN PROGRESS (not yet resolved):")
        for row in inprogress:
            print(f"    {row[0]:<35} {row[1]} signal(s)")

    # --- Stuck-signal check ---
    stuck = _find_stuck_signals(conn, canonical_ids)
    if stuck:
        print(f"\n  ⚠  STUCK SIGNALS (elapsed >= {MAX_HOLDING_DAYS}d, not resolved): "
              f"{len(stuck)}")
        for s in stuck:
            print(
                f"    {s['signal_id']}  {s['symbol']:<8}  "
                f"t1={s['t1_date']}  elapsed={s['elapsed_days']}d  "
                f"max_day={s['max_holding_day']}"
            )

    if resolved_df.empty:
        print(
            f"\n  No resolved observations yet "
            f"(need {MAX_HOLDING_DAYS} elapsed trading days)."
        )
        return

    # --- Per-strategy report ---
    for strat in STRATEGIES:
        sub_all = resolved_df[
            (resolved_df["strategy"] == strat) &
            (resolved_df["tracker_schema_version"] == TRACKER_SCHEMA_VERSION)
        ].dropna(subset=["net_return_t1"])

        if sub_all.empty:
            print(f"\n  {strat}: no resolved signals")
            continue

        n_all = len(sub_all)
        rets_all = sub_all["net_return_t1"]
        dates_all = sub_all["signal_date"]

        mean_all = float(rets_all.mean())
        med_all = float(rets_all.median())
        std_all = float(rets_all.std())
        hit_all = float((rets_all > 0).mean())
        tail_all = float(rets_all.quantile(0.05))

        ci_all = _cluster_bootstrap_ci(rets_all, dates_all, seed=seed)

        # Worst calendar-month mean return (with forced cases included).
        # signal_date may be datetime.date or ISO string; .astype(str) normalises both.
        sub_copy = sub_all.copy()
        sub_copy["month"] = pd.to_datetime(
            sub_copy["signal_date"].astype(str), format="%Y-%m-%d"
        ).dt.to_period("M")
        monthly = sub_copy.groupby("month")["net_return_t1"].mean()
        worst_month = float(monthly.min()) if not monthly.empty else float("nan")
        n_months = len(monthly)

        print(f"\n  {strat}  (n={n_all}  schema_v{TRACKER_SCHEMA_VERSION})")
        print(f"    mean net return (20d)  : {mean_all:>+.2%}")
        print(f"    median net return      : {med_all:>+.2%}")
        print(f"    hit rate               : {hit_all:.1%}")
        print(f"    std                    : {std_all:.2%}")
        print(f"    tail loss (5th pct)    : {tail_all:>+.2%}")
        print(
            f"    worst month mean       : {worst_month:>+.2%}"
            if not np.isnan(worst_month)
            else "    worst month mean       : n/a"
        )
        if n_months < 2:
            print("      ⚠  n_months < 2: worst_month stat is unreliable")

        ci_str = (
            f"{ci_all.ci_lower:>+.2%}"
            if not np.isnan(ci_all.ci_lower)
            else "n/a (need n_clusters >= 2)"
        )
        print(
            f"    95% CI lower           : {ci_str}"
            f"  [effective n = {ci_all.n_clusters} cluster(s); "
            f"nominal n = {n_all}]"
        )

        # --- Without-forced comparison ---
        # Requires forced_resolved column (v2 schema only).
        if "forced_resolved" in sub_all.columns:
            sub_noforced = sub_all[~sub_all["forced_resolved"]].dropna(
                subset=["net_return_t1"]
            )
            n_nf = len(sub_noforced)

            if n_nf > 0 and n_nf < n_all:
                mean_nf = float(sub_noforced["net_return_t1"].mean())
                ci_nf = _cluster_bootstrap_ci(
                    sub_noforced["net_return_t1"],
                    sub_noforced["signal_date"],
                    seed=seed,
                )
                mean_delta = mean_nf - mean_all
                ci_delta = (
                    (ci_nf.ci_lower - ci_all.ci_lower)
                    if not (np.isnan(ci_nf.ci_lower) or np.isnan(ci_all.ci_lower))
                    else float("nan")
                )
                print(f"\n    Forced-case sensitivity (excl. forced_resolved rows):")
                print(f"      n without forced       : {n_nf}")
                print(f"      mean (without forced)  : {mean_nf:>+.2%}")
                print(f"      mean_delta             : {mean_delta:>+.2%}  (without − with)")
                ci_nf_str = (
                    f"{ci_nf.ci_lower:>+.2%}"
                    if not np.isnan(ci_nf.ci_lower)
                    else "n/a"
                )
                print(f"      CI lower (w/o forced)  : {ci_nf_str}")
                ci_d_str = (
                    f"{ci_delta:>+.2%}"
                    if not np.isnan(ci_delta)
                    else "n/a"
                )
                print(f"      ci_delta               : {ci_d_str}  (without − with)")
            elif n_all > 0 and n_nf == n_all:
                print("    (no forced_resolved rows — with/without delta not applicable)")

            # Forced-case counts and cluster placement
            n_forced = int(sub_all["forced_resolved"].sum())
            n_imputed = int(sub_all["imputed_exit"].sum()) if "imputed_exit" in sub_all.columns else 0
            n_no_price = int(
                (sub_all["imputation_reason"] == "no_price_after_entry").sum()
            ) if "imputation_reason" in sub_all.columns else 0

            if n_forced > 0:
                print(f"\n    Forced-case counts (resolved signals only):")
                print(f"      forced_resolved_count  : {n_forced}")
                print(f"      imputed_exit_count     : {n_imputed}")
                print(f"      no_price_after_entry   : {n_no_price}")

                # Cluster placement: which signal_dates contain forced cases.
                # Dates formatted as ISO strings for clean display.
                forced_sub = sub_all[sub_all["forced_resolved"]]
                forced_by_date = {
                    str(d)[:10]: int(c)
                    for d, c in forced_sub.groupby("signal_date")
                    .size()
                    .sort_index()
                    .items()
                }
                print(f"      forced_cases_by_date   : {forced_by_date}")

        # --- Priority zone breakdown (pullback only) ---
        if strat == "trend_pullback_v1":
            for zone in ["HIGH", "NORMAL"]:
                z = sub_all[sub_all["priority_zone"] == zone].dropna(
                    subset=["net_return_t1"]
                )
                if not z.empty:
                    zr = z["net_return_t1"]
                    print(
                        f"    zone {zone:<10} "
                        f"n={len(z):<4} "
                        f"mean={zr.mean():>+.2%}  "
                        f"hit={(zr > 0).mean():.0%}"
                    )

        # --- Regime breakdown ---
        for reg in ["bull", "neutral", "bear", "crisis"]:
            r_sub = sub_all[sub_all["regime"] == reg].dropna(
                subset=["net_return_t1"]
            )
            if not r_sub.empty:
                rr = r_sub["net_return_t1"]
                print(
                    f"    regime {reg:<9} "
                    f"n={len(r_sub):<4} "
                    f"mean={rr.mean():>+.2%}  "
                    f"hit={(rr > 0).mean():.0%}"
                )

        # --- Go-live gate ---
        gate = _check_gate(n_all, mean_all, hit_all, ci_all.ci_lower, worst_month)
        all_pass = all(gate.values())
        print(f"\n    GO-LIVE GATE  [{'PASS' if all_pass else 'NOT YET'}]")
        for condition, passed in gate.items():
            print(f"      {'✓' if passed else '✗'}  {condition}")
        if n_all < 30:
            print("      ⚠  n < 30: CI, monthly stats, and hit rate are unreliable")

    print()
    print("  NOTE: mix of strategy versions in one aggregate is a research error.")
    print(f"  All rows above filtered to tracker_schema_version={TRACKER_SCHEMA_VERSION}.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Update and report forward return observations.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run python research/forward_return_tracker.py
  uv run python research/forward_return_tracker.py --report-only
  uv run python research/forward_return_tracker.py --report-only --seed 42
        """,
    )
    parser.add_argument(
        "--report-only", action="store_true",
        help="Print summary without updating observations.",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for bootstrap CI reproducibility (default: 42).",
    )
    parser.add_argument(
        "--skip-calendar-check", action="store_true",
        help=(
            "Skip INV-1 calendar integrity check.  "
            "Use only in debugging environments where exchange_calendars "
            "is unavailable or the check is known to produce false positives."
        ),
    )
    args = parser.parse_args()

    try:
        with connect() as conn:
            _ensure_table(conn)

            # INV-1: abort on calendar gaps before any observations are written.
            # Raises RuntimeError so connect().__exit__ runs before halting.
            if not args.skip_calendar_check:
                _assert_calendar_integrity(conn)

            if args.report_only:
                _print_summary(conn, seed=args.seed)
                return 0

            signals_df = _load_signals(conn)
            # Derive canonical set from the already-deduped signals_df.
            # Single source of truth: no separate query, no race condition.
            canonical_ids = frozenset(signals_df["signal_id"].astype(str))
            progress = _load_signal_progress(conn, canonical_ids)

            # Fully resolved = terminal row exists (max_holding_day >= 19).
            complete_ids = {
                sid for sid, max_day in progress.items()
                if max_day >= MAX_HOLDING_DAYS - 1
            }
            to_process = signals_df[~signals_df["signal_id"].isin(complete_ids)]

            if to_process.empty:
                print("All signals fully resolved. Nothing to update.")
            else:
                print(
                    f"Processing {len(to_process)} signal(s) "
                    f"({len(complete_ids)} already complete)..."
                )

            total_inserted = 0
            skipped_no_calendar = 0    # no trading dates found after signal_date
            skipped_no_t1_price = 0    # T+1 adj_open not yet in daily_price_adj

            for _, sig in to_process.iterrows():
                sig_dict = sig.to_dict()
                symbol = str(sig_dict["symbol"])
                signal_date = sig_dict["signal_date"]
                if isinstance(signal_date, str):
                    signal_date = Date.fromisoformat(signal_date)

                # T+1 = first trading day strictly after signal_date.
                # Fetch MAX_HOLDING_DAYS dates starting from T+1 (plus one extra
                # to ensure the slice never truncates the 20-day window).
                future_dates = _get_trading_dates_after(
                    conn,
                    signal_date + timedelta(days=1),
                    MAX_HOLDING_DAYS,
                )
                if not future_dates:
                    skipped_no_calendar += 1
                    continue

                t1_date = future_dates[0]

                # obs_dates: T+1 close through T+20 close.
                # Day 0 = T+1 close (same calendar day as entry open).
                # Day 19 = T+20 close (20-day holding period).
                obs_dates = future_dates[:MAX_HOLDING_DAYS]

                # T+1 adj_open (execution reference price).
                t1_rows = conn.execute(
                    "SELECT adj_open FROM daily_price_adj "
                    "WHERE stock_id = $1 AND date = $2",
                    [symbol, t1_date],
                ).fetchall()
                if not t1_rows:
                    skipped_no_t1_price += 1
                    continue
                t1_adj_open = float(t1_rows[0][0])

                # Per-stock price series (may be sparse — halts/suspensions).
                price_series = _get_adj_close_series(conn, symbol, obs_dates)

                # v2: do NOT skip on empty price_series.
                # An empty price_series with obs_dates present means the stock is
                # halted from day 0.  Once len(obs_dates) == MAX_HOLDING_DAYS,
                # _build_observations will force-resolve with a -100% terminal row.
                if not obs_dates:
                    skipped_no_calendar += 1
                    continue

                sid = str(sig_dict["signal_id"])
                start_day_idx = progress.get(sid, -1) + 1

                obs_rows = _build_observations(
                    sig_dict,
                    t1_date,
                    t1_adj_open,
                    obs_dates,
                    price_series,
                    start_day_idx,
                    entry_slippage_bps=ENTRY_SLIPPAGE_BPS,
                    cost_bps=ROUND_TRIP_COST_BPS,
                )
                if not obs_rows:
                    continue

                obs_df = pd.DataFrame(obs_rows)
                # Guard: column names must exactly match the schema definition.
                # DuckDB column matching is case-sensitive.
                assert set(obs_df.columns) == set(_OBS_COLUMNS), (
                    f"DataFrame columns do not match schema.\n"
                    f"  Extra   : {set(obs_df.columns) - set(_OBS_COLUMNS)}\n"
                    f"  Missing : {set(_OBS_COLUMNS) - set(obs_df.columns)}"
                )
                conn.execute(f"""
                    INSERT INTO {OBS_TABLE} (
                        {_OBS_COLUMNS_SQL}
                    )
                    SELECT
                        {_OBS_COLUMNS_SQL}
                    FROM obs_df
                    ON CONFLICT DO NOTHING
                """)
                total_inserted += len(obs_rows)

            if total_inserted:
                print(f"Inserted {total_inserted} new observation row(s).")
            if skipped_no_calendar:
                print(f"Skipped {skipped_no_calendar} signal(s) (no calendar dates found).")
            if skipped_no_t1_price:
                print(f"Skipped {skipped_no_t1_price} signal(s) (T+1 price not yet available).")

            # Defensive commit: ensures writes persist regardless of whether
            # data.database.connect() uses auto-commit or an explicit transaction.
            # Verify connect() behaviour if inserted rows do not appear after a run.
            if total_inserted:
                conn.commit()

            _print_summary(conn, seed=args.seed)

    except RuntimeError as exc:
        # Calendar integrity failure or other hard-abort condition.
        # connect().__exit__ has already run; connection is closed.
        print(f"\nABORT: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
