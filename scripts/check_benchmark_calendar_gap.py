#!/usr/bin/env python3
# scripts/check_benchmark_calendar_gap.py
"""Benchmark Calendar Gap Detector — v1.2.0.

Asserts that the trading-day calendar derived from daily_price_adj is
complete for the specified lookback window.

Why this exists (INV-1 from tracker_v2_migration runbook)
----------------------------------------------------------
forward_return_tracker.py derives its trading-day index from all distinct dates
in daily_price_adj.  If a real TWSE trading day is missing from this table due
to a data pipeline failure, all in-progress signal elapsed-day counts are
silently corrupted from that date forward.  This is a correlated, systematic
distortion — not random noise.

This script detects such gaps before any migration proceeds.

Detection strategy
------------------
Two-tier approach (uses whichever is available):

Tier 1 — Authoritative (preferred):
    Uses the 'exchange_calendars' package (XTAI = Taiwan Stock Exchange).
    Provides correct holiday awareness.
    Install: uv add exchange_calendars

Tier 2 — Heuristic fallback:
    If exchange_calendars is not available, uses a weekday-only approximation
    (no Taiwan public holiday awareness).  Will produce false positives on
    public holidays.  Accept only as a rough check; install exchange_calendars
    for production use.

Pass criterion (runbook Phase A)
---------------------------------
    Zero gaps reported for --lookback-days window.
    Any gap → ABORT the migration.

Usage
-----
    uv run python scripts/check_benchmark_calendar_gap.py
    uv run python scripts/check_benchmark_calendar_gap.py --lookback-days 90
    uv run python scripts/check_benchmark_calendar_gap.py --lookback-days 30 --verbose
"""

from __future__ import annotations

import argparse
import sys
from datetime import date as Date
from datetime import datetime as DateTime
from datetime import timedelta

from data.database import connect


# ---------------------------------------------------------------------------
# Calendar loading
# ---------------------------------------------------------------------------

def _load_authoritative_calendar(start: Date, end: Date) -> list[Date] | None:
    """Load TWSE trading dates from exchange_calendars (XTAI).

    Returns None if the package is not installed, signalling fallback.
    """
    try:
        import exchange_calendars as xcals
        cal = xcals.get_calendar("XTAI")
        sessions = cal.sessions_in_range(
            start.strftime("%Y-%m-%d"),
            end.strftime("%Y-%m-%d"),
        )
        return [s.date() for s in sessions]
    except ImportError:
        return None
    except Exception as exc:  # noqa: BLE001
        print(
            f"  ⚠  exchange_calendars raised an unexpected error: {exc}\n"
            "  Falling back to weekday heuristic."
        )
        return None


def _load_weekday_calendar(start: Date, end: Date) -> list[Date]:
    """Return all weekdays in [start, end].

    Fallback only.  Does NOT exclude Taiwan public holidays; will produce
    false positives on holiday-adjacent pipeline checks.
    """
    dates: list[Date] = []
    d = start
    while d <= end:
        if d.weekday() < 5:  # 0=Mon … 4=Fri
            dates.append(d)
        d += timedelta(days=1)
    return dates


# ---------------------------------------------------------------------------
# DB queries
# ---------------------------------------------------------------------------

def _load_db_dates(conn, start: Date, end: Date) -> set[Date]:
    """Return all distinct dates in daily_price_adj for the given window."""
    rows = conn.execute(
        "SELECT DISTINCT date FROM daily_price_adj "
        "WHERE date >= $1 AND date <= $2 ORDER BY date",
        [start, end],
    ).fetchall()
    return {r[0] for r in rows}


# ---------------------------------------------------------------------------
# Gap detection
# ---------------------------------------------------------------------------

def find_gaps(
    conn,
    lookback_days: int = 90,
    verbose: bool = False,
) -> list[Date] | None:
    """Return TWSE trading dates missing from daily_price_adj.

    Anchors to today (not MAX(date) from the DB).  This ensures that pipeline
    failures on the most recent sessions are detected — if the anchor were
    MAX(date), a complete pipeline failure on the latest day would move the
    window earlier and report PASS, masking the outage.

    Window: [today - lookback_days, yesterday].
    Excludes today to avoid false positives from in-progress pipeline runs
    (tracker data expected post-16:10; running this before that is safe).

    Args:
        conn:          Active DB connection.
        lookback_days: How many calendar days back to check.
        verbose:       Print progress details.

    Returns:
        List of missing trading dates.  Empty list = PASS (no gaps).
        None = DB is empty or unreadable; caller must treat as FAIL.
    """
    today = Date.today()
    end_date: Date = today - timedelta(days=1)    # yesterday: last expected session
    start_date: Date = today - timedelta(days=lookback_days)

    # Verify daily_price_adj is not completely empty.
    max_db_date_raw = conn.execute(
        "SELECT MAX(date) FROM daily_price_adj"
    ).fetchone()[0]

    if max_db_date_raw is None:
        print("  ERROR: daily_price_adj is empty.  Cannot verify calendar integrity.")
        return None

    # Normalise to datetime.date regardless of what DuckDB returns.
    if isinstance(max_db_date_raw, str):
        max_db_date: Date = Date.fromisoformat(max_db_date_raw)
    elif isinstance(max_db_date_raw, DateTime):
        max_db_date = max_db_date_raw.date()
    else:
        max_db_date = max_db_date_raw

    # Pipeline delay warning: separate from gap detection.
    # A stale DB means recent gaps may also be present in the window.
    if max_db_date < end_date and today.weekday() < 5:
        print(
            f"  ⚠  WARNING: daily_price_adj latest date is {max_db_date}, "
            f"expected {end_date} or later."
        )
        print("  build_adjusted_prices.py may not have completed for recent sessions.")

    # Load authoritative calendar anchored to today's reference.
    expected_dates = _load_authoritative_calendar(start_date, end_date)
    calendar_source: str

    if expected_dates is not None:
        calendar_source = "exchange_calendars (XTAI) — authoritative"
    else:
        print()
        print("  ⚠  WARNING: exchange_calendars not installed.")
        print("  Using weekday heuristic — FALLBACK MODE.")
        print("  This WILL produce false positives on Taiwan public holidays.")
        print("  A FAIL result from this fallback is NOT authoritative.")
        print("  Install before relying on this check for migration go/no-go:")
        print("      uv add exchange_calendars")
        print()
        expected_dates = _load_weekday_calendar(start_date, end_date)
        calendar_source = "weekday heuristic (FALLBACK — holiday-unaware)"

    db_dates = _load_db_dates(conn, start_date, end_date)

    if verbose:
        print(f"  Calendar source  : {calendar_source}")
        print(f"  Window           : {start_date} → {end_date}  (today={today})")
        print(f"  Expected sessions: {len(expected_dates)}")
        print(f"  DB dates present : {len(db_dates)}")

    missing = sorted(d for d in expected_dates if d not in db_dates)
    return missing


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detect trading-day gaps in daily_price_adj (runbook Phase A).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exit codes:
  0  No gaps found (PASS — safe to proceed with migration)
  1  Gaps detected (FAIL — ABORT the migration and investigate)
  2  Unexpected error

Examples:
  uv run python scripts/check_benchmark_calendar_gap.py
  uv run python scripts/check_benchmark_calendar_gap.py --lookback-days 90
  uv run python scripts/check_benchmark_calendar_gap.py --lookback-days 30 --verbose
        """,
    )
    parser.add_argument(
        "--lookback-days", type=int, default=90,
        help="How many calendar days back to inspect (default: 90).",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Print calendar source and window details.",
    )
    args = parser.parse_args()

    print("Benchmark Calendar Gap Detector")
    print("=" * 48)

    try:
        with connect() as conn:
            missing = find_gaps(
                conn,
                lookback_days=args.lookback_days,
                verbose=args.verbose,
            )
    except Exception as exc:  # noqa: BLE001
        print(f"  ERROR: {exc}")
        return 2

    if missing is None:
        # find_gaps returns None when data is absent or unusable.
        print(f"  FAIL — daily_price_adj is empty or unreadable.")
        print("  ACTION: do NOT proceed with migration.")
        return 1

    if not missing:
        print(f"  PASS — no gaps in trailing {args.lookback_days}-day window.")
        return 0

    print(
        f"\n  FAIL — {len(missing)} gap(s) detected in "
        f"trailing {args.lookback_days}-day window:"
    )
    for d in missing:
        print(f"    {d}  (TWSE session missing from daily_price_adj)")
    print(
        "\n  ACTION: do NOT proceed with migration.\n"
        "  Investigate daily_price_adj pipeline for the dates above."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
