#!/usr/bin/env python3
# research/forward_return_tracker.py
"""Forward Return Tracker — v0.2.0.

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
  3. Computes forward returns at each available day in the holding window.
  4. Persists observations incrementally; re-runs safely fill in missing days.
  5. Prints a summary report of resolved observations.

Run schedule
------------
Add to cron after market close, after build_adjusted_prices.py completes:
    05 16 * * 1-5  cd ~/projects/helios && uv run python research/forward_return_tracker.py >> logs/forward_tracker.log 2>&1

Data model
----------
One row per (signal_id, holding_day).

    holding_day = 0   : obs_date is the first trading close after T+1 entry
    holding_day = N-1 : obs_date is the Nth trading close after T+1 entry

T+1 entry price (adj_open) is stored once per signal at the signal level,
not repeated per holding_day row.

Incremental update contract
----------------------------
The PRIMARY KEY is (signal_id, holding_day).  Each run:
  - skips signals already fully resolved (max_holding_day >= MAX_HOLDING_DAYS-1)
  - re-processes all partial signals, inserting only missing days via
    ON CONFLICT DO NOTHING
This is safe to run multiple times without data corruption.

Resolved semantics
------------------
resolved = True  iff  the signal has a COMPLETE series of MAX_HOLDING_DAYS rows.
It is set on the terminal row (holding_day = MAX_HOLDING_DAYS - 1) only when
len(price_series) >= MAX_HOLDING_DAYS at insert time.
If fewer days are available (e.g. signal is recent), resolved stays False
until a subsequent run fills in the remaining days.

Entry price choices (both stored)
------------------------------------
signal_price      : signals.price at generation time.
                    Measures raw signal predictive power, no execution cost.

t1_adj_open       : adj_open on T+1 trading day (execution reference).
                    Subject to gap risk; not guaranteed fill.

Primary metric for go-live decision  : t1_adj_open-based net_return_t1.
Primary metric for signal quality    : signal_price-based gross_return_signal.

Cost model
----------
Taiwan stock round-trip cost (discount broker):
    buy  brokerage : ~4–5 bps
    sell brokerage : ~4–5 bps
    sell tax       : 30 bps  (securities transaction tax, sell side only)
    ─────────────────────────
    total          : ~38–40 bps

Go-live gate (per strategy) — ALL five conditions required
-----------------------------------------------------------
  1. resolved_signals      >= 150
  2. mean_net_return_20d   >  0
  3. hit_rate_20d          >  0.52
  4. ci_95_lower_bound     >  0      (t-distribution, requires n >= 30)
  5. no_month_mean_below   >= -0.02  (worst calendar-month mean return)

Conditions 1–3 are necessary but not sufficient.
Conditions 4–5 require adequate sample size (see n<30 warning in output).
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

import numpy as np
import pandas as pd

from data.database import connect


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STRATEGIES: tuple[str, ...] = ("trend_pullback_v1", "trend_breakout_v1")
MAX_HOLDING_DAYS: int = 20

# Taiwan discount broker round-trip:
#   buy brokerage ~4–5 bps + sell brokerage ~4–5 bps + sell tax 30 bps ≈ 38–40 bps
ROUND_TRIP_COST_BPS: float = 40.0

OBS_TABLE: str = "forward_return_observations"

# Bump when schema changes; prevents mixing observations from incompatible versions.
TRACKER_SCHEMA_VERSION: int = 1


# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------

_CREATE_OBS_TABLE = f"""
CREATE TABLE IF NOT EXISTS {OBS_TABLE} (
    -- Identity
    signal_id              VARCHAR NOT NULL,
    symbol                 VARCHAR NOT NULL,
    strategy               VARCHAR NOT NULL,
    strategy_version       VARCHAR NOT NULL,  -- e.g. "v1" extracted from strategy name
    tracker_schema_version INTEGER NOT NULL,  -- bump on schema change

    -- Signal context at generation time
    approval_status        VARCHAR NOT NULL,
    signal_date            DATE    NOT NULL,
    regime                 VARCHAR,
    rs_percentile          DOUBLE,
    beta_percentile        DOUBLE,
    dist_ma20_atr          DOUBLE,
    priority_zone          VARCHAR,           -- HIGH | NORMAL | ABOVE_MA20 | UNKNOWN

    -- Entry prices (signal-level, repeated per row for query convenience)
    signal_price           DOUBLE,            -- signals.price at generation
    t1_adj_open            DOUBLE,            -- adj_open on T+1 (execution ref)
    t1_date                DATE,

    -- Observation
    holding_day            INTEGER NOT NULL,  -- 0-indexed days after T+1 entry
    obs_date               DATE    NOT NULL,
    adj_close              DOUBLE,

    -- Derived returns (computed at insert time)
    gross_return_signal    DOUBLE,            -- adj_close / signal_price - 1
    gross_return_t1        DOUBLE,            -- adj_close / t1_adj_open - 1
    net_return_t1          DOUBLE,            -- gross_return_t1 - round_trip_cost

    -- Resolution flag: True iff signal has a COMPLETE MAX_HOLDING_DAYS series
    -- and this is the terminal row (holding_day = MAX_HOLDING_DAYS - 1).
    resolved               BOOLEAN NOT NULL DEFAULT false,

    PRIMARY KEY (signal_id, holding_day)
)
"""


def _ensure_table(conn) -> None:
    conn.execute(_CREATE_OBS_TABLE)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_signals(conn) -> pd.DataFrame:
    strats = ", ".join(f"'{s}'" for s in STRATEGIES)
    return conn.execute(f"""
        SELECT
            signal_id,
            symbol,
            strategy,
            approval_status,
            signal_date,
            regime,
            price     AS signal_price,
            metadata
        FROM signals
        WHERE strategy IN ({strats})
        ORDER BY signal_date
    """).df()


def _load_signal_progress(conn) -> dict[str, int]:
    """Return {signal_id: max_holding_day} for all signals with any observations.

    Used to:
      - skip fully resolved signals (max_day >= MAX_HOLDING_DAYS - 1)
      - resume partial signals from where they left off
    """
    rows = conn.execute(f"""
        SELECT signal_id, MAX(holding_day) AS max_day
        FROM {OBS_TABLE}
        GROUP BY signal_id
    """).fetchall()
    return {r[0]: int(r[1]) for r in rows}


def _get_trading_dates_after(conn, from_date: Date, n: int) -> list[Date]:
    """Return up to n trading dates >= from_date from daily_price_adj calendar."""
    rows = conn.execute(f"""
        SELECT DISTINCT date FROM daily_price_adj
        WHERE date >= '{from_date}'
        ORDER BY date
        LIMIT {n + 1}
    """).fetchall()
    return [r[0] for r in rows]


def _get_adj_close_series(
    conn, symbol: str, dates: list[Date]
) -> dict[Date, float]:
    if not dates:
        return {}
    date_list = ", ".join(f"'{d}'" for d in dates)
    rows = conn.execute(f"""
        SELECT date, adj_close
        FROM daily_price_adj
        WHERE stock_id = '{symbol}'
          AND date IN ({date_list})
    """).fetchall()
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
    price_series: dict[Date, float],
    start_day_idx: int,
) -> list[dict]:
    """Build observation rows for a single signal.

    Only builds rows for holding_day >= start_day_idx (incremental update).
    resolved is True only on the terminal row of a COMPLETE series.

    P0 fix: resolved is computed at signal level (len(price_series) >= MAX_HOLDING_DAYS)
    and propagated to the terminal row only — not set per-row based on day_idx alone.
    """
    meta = _parse_metadata(sig.get("metadata"))
    dist = meta.get("dist_above_ma20_atr")
    cost = ROUND_TRIP_COST_BPS / 10000
    signal_price = sig.get("signal_price")

    # Signal-level resolved: True only if we have the full horizon today.
    fully_resolved = len(price_series) >= MAX_HOLDING_DAYS

    rows = []
    for day_idx, (obs_date, adj_close) in enumerate(sorted(price_series.items())):
        if day_idx < start_day_idx:
            continue  # already inserted in a previous run

        gross_signal = (
            (adj_close / signal_price - 1)
            if signal_price and signal_price > 0
            else None
        )
        gross_t1 = (
            (adj_close / t1_adj_open - 1)
            if t1_adj_open and t1_adj_open > 0
            else None
        )
        net_t1 = (gross_t1 - cost) if gross_t1 is not None else None

        # resolved = True iff this is the terminal row of a complete series.
        is_terminal = day_idx == MAX_HOLDING_DAYS - 1
        resolved = fully_resolved and is_terminal

        rows.append({
            "signal_id":             sig["signal_id"],
            "symbol":                sig["symbol"],
            "strategy":              sig["strategy"],
            "strategy_version":      _strategy_version(sig["strategy"]),
            "tracker_schema_version": TRACKER_SCHEMA_VERSION,
            "approval_status":       sig["approval_status"],
            "signal_date":           sig["signal_date"],
            "regime":                sig.get("regime"),
            "rs_percentile":         meta.get("rs_percentile"),
            "beta_percentile":       meta.get("beta_percentile"),
            "dist_ma20_atr":         dist,
            "priority_zone":         _priority_zone(dist),
            "signal_price":          signal_price,
            "t1_adj_open":           t1_adj_open,
            "t1_date":               t1_date,
            "holding_day":           day_idx,
            "obs_date":              obs_date,
            "adj_close":             adj_close,
            "gross_return_signal":   gross_signal,
            "gross_return_t1":       gross_t1,
            "net_return_t1":         net_t1,
            "resolved":              resolved,
        })
    return rows


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _check_gate(n: int, mean_r: float, hit: float,
                ci_lower: float, worst_month_mean: float) -> dict[str, bool]:
    """Evaluate all five go-live gate conditions."""
    return {
        "n>=150":            n >= 150,
        "mean>0":            mean_r > 0,
        "hit>52%":           hit > 0.52,
        "ci_lower>0":        (not np.isnan(ci_lower)) and ci_lower > 0,
        "worst_month>=-2%":  worst_month_mean >= -0.02,
    }


def _print_summary(conn) -> None:
    print()
    print("=" * 72)
    print("FORWARD RETURN TRACKER — SUMMARY")
    print(f"  Schema version : {TRACKER_SCHEMA_VERSION}")
    print(f"  Entry ref      : T+1 adj_open  |  Cost: {ROUND_TRIP_COST_BPS:.0f} bps round-trip")
    print(f"  Horizon        : {MAX_HOLDING_DAYS}d  |  Primary metric: net_return_t1 at day {MAX_HOLDING_DAYS - 1}")
    print("=" * 72)

    # Load resolved terminal rows only (holding_day = MAX_HOLDING_DAYS-1, resolved=True)
    resolved_df = conn.execute(f"""
        SELECT * FROM {OBS_TABLE}
        WHERE resolved = true
        ORDER BY signal_date
    """).df()

    # In-progress counts
    inprogress = conn.execute(f"""
        SELECT strategy, COUNT(DISTINCT signal_id) AS n
        FROM {OBS_TABLE}
        WHERE resolved = false
        GROUP BY strategy
    """).fetchall()

    if not inprogress and resolved_df.empty:
        print("\n  No observations yet.")
        return

    if inprogress:
        print("\n  IN PROGRESS (not yet resolved):")
        for row in inprogress:
            print(f"    {row[0]:<35} {row[1]} signal(s)")

    if resolved_df.empty:
        print(f"\n  No resolved observations yet (need {MAX_HOLDING_DAYS} trading days).")
        return

    for strat in STRATEGIES:
        sub = resolved_df[
            (resolved_df["strategy"] == strat) &
            (resolved_df["tracker_schema_version"] == TRACKER_SCHEMA_VERSION)
        ].dropna(subset=["net_return_t1"])

        if sub.empty:
            print(f"\n  {strat}: no resolved signals")
            continue

        n = len(sub)
        rets = sub["net_return_t1"]
        mean_r = float(rets.mean())
        med_r = float(rets.median())
        std_r = float(rets.std())
        hit = float((rets > 0).mean())
        tail = float(rets.quantile(0.05))

        # 95% CI on mean (t-distribution)
        if n >= 2 and std_r > 0:
            try:
                from scipy import stats as sp_stats
                ci_lower, ci_upper = sp_stats.t.interval(
                    0.95, df=n - 1, loc=mean_r, scale=std_r / np.sqrt(n)
                )
            except ImportError:
                ci_lower = ci_upper = float("nan")
        else:
            ci_lower = ci_upper = float("nan")

        # Worst calendar-month mean return
        sub_copy = sub.copy()
        sub_copy["month"] = pd.to_datetime(sub_copy["signal_date"]).dt.to_period("M")
        monthly = sub_copy.groupby("month")["net_return_t1"].mean()
        worst_month = float(monthly.min()) if not monthly.empty else float("nan")

        print(f"\n  {strat}  (n={n}  schema_v{TRACKER_SCHEMA_VERSION})")
        print(f"    mean net return (20d)  : {mean_r:>+.2%}")
        print(f"    median net return      : {med_r:>+.2%}")
        print(f"    hit rate               : {hit:.1%}")
        print(f"    std                    : {std_r:.2%}")
        ci_str = f"{ci_lower:>+.2%}" if not np.isnan(ci_lower) else "n/a (need n>=2)"
        print(f"    95% CI lower           : {ci_str}")
        print(f"    tail loss (5th pct)    : {tail:>+.2%}")
        print(f"    worst month mean       : {worst_month:>+.2%}" if not np.isnan(worst_month) else "    worst month mean       : n/a")

        # Priority zone breakdown (pullback only)
        if strat == "trend_pullback_v1":
            for zone in ["HIGH", "NORMAL"]:
                z = sub[sub["priority_zone"] == zone].dropna(subset=["net_return_t1"])
                if not z.empty:
                    zr = z["net_return_t1"]
                    print(f"    zone {zone:<10} n={len(z):<4} mean={zr.mean():>+.2%}  hit={(zr > 0).mean():.0%}")

        # Regime breakdown
        for reg in ["bull", "neutral", "bear"]:
            r_sub = sub[sub["regime"] == reg].dropna(subset=["net_return_t1"])
            if not r_sub.empty:
                rr = r_sub["net_return_t1"]
                print(f"    regime {reg:<9} n={len(r_sub):<4} mean={rr.mean():>+.2%}  hit={(rr > 0).mean():.0%}")

        # Go-live gate — all five conditions
        gate = _check_gate(n, mean_r, hit, ci_lower,
                           worst_month if not np.isnan(worst_month) else -999.0)
        all_pass = all(gate.values())
        print(f"\n    GO-LIVE GATE  [{'PASS' if all_pass else 'NOT YET'}]")
        for condition, passed in gate.items():
            print(f"      {'✓' if passed else '✗'}  {condition}")
        if n < 30:
            print("      ⚠  n < 30: ci_lower and monthly stats are unreliable")

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
        """,
    )
    parser.add_argument(
        "--report-only", action="store_true",
        help="Print summary without updating observations.",
    )
    args = parser.parse_args()

    with connect() as conn:
        _ensure_table(conn)

        if args.report_only:
            _print_summary(conn)
            return 0

        signals_df = _load_signals(conn)
        progress = _load_signal_progress(conn)

        # Only process signals that are not yet fully resolved.
        # Fully resolved = max_holding_day >= MAX_HOLDING_DAYS - 1.
        complete_ids = {
            sid for sid, max_day in progress.items()
            if max_day >= MAX_HOLDING_DAYS - 1
        }
        to_process = signals_df[~signals_df["signal_id"].isin(complete_ids)]

        if to_process.empty:
            print("All signals fully resolved. Nothing to update.")
        else:
            print(f"Processing {len(to_process)} signal(s) "
                  f"({len(complete_ids)} already complete)...")

        total_inserted = 0
        skipped = 0

        for _, sig in to_process.iterrows():
            sig_dict = sig.to_dict()
            symbol = str(sig_dict["symbol"])
            signal_date = sig_dict["signal_date"]
            if isinstance(signal_date, str):
                signal_date = Date.fromisoformat(signal_date)

            # T+1 = first trading day strictly after signal_date
            future_dates = _get_trading_dates_after(
                conn,
                signal_date + timedelta(days=1),
                MAX_HOLDING_DAYS + 1,
            )
            if not future_dates:
                skipped += 1
                continue

            t1_date = future_dates[0]
            # obs_dates: up to MAX_HOLDING_DAYS closes starting the day after T+1
            obs_dates = future_dates[1 : MAX_HOLDING_DAYS + 1]

            # T+1 adj_open
            t1_rows = conn.execute(f"""
                SELECT adj_open FROM daily_price_adj
                WHERE stock_id = '{symbol}' AND date = '{t1_date}'
            """).fetchall()
            if not t1_rows:
                skipped += 1
                continue
            t1_adj_open = float(t1_rows[0][0])

            # Forward adj_close series (only available days)
            price_series = _get_adj_close_series(conn, symbol, obs_dates)
            if not price_series:
                skipped += 1
                continue

            # Incremental: start from the day after what we already have
            sid = sig_dict["signal_id"]
            start_day_idx = progress.get(sid, -1) + 1

            obs_rows = _build_observations(
                sig_dict, t1_date, t1_adj_open, price_series, start_day_idx
            )
            if not obs_rows:
                continue

            obs_df = pd.DataFrame(obs_rows)
            conn.execute(f"""
                INSERT INTO {OBS_TABLE}
                SELECT * FROM obs_df
                ON CONFLICT DO NOTHING
            """)
            total_inserted += len(obs_rows)

        if total_inserted:
            print(f"Inserted {total_inserted} new observation row(s).")
        if skipped:
            print(f"Skipped {skipped} signal(s) "
                  "(T+1 price not yet available or no future dates).")

        _print_summary(conn)

    return 0


if __name__ == "__main__":
    sys.exit(main())
