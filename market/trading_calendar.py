# market/trading_calendar.py
"""Taiwan Stock Exchange trading calendar — v0.2.0.

Three-layer hybrid design (priority order, highest first):

  Layer 1 — TWSE official holiday table (twse_holidays in DuckDB):
      Authoritative source for officially announced non-trading days.
      Updated annually by scripts/ingest_twse_holidays.py.
      Currently covers only the current ROC year (TWSE API limitation).

  Layer 2 — exchange_calendars XTAI:
      Covers 2006-06-07 through 2027-06-07 (as of exchange_calendars
      package version at time of writing). Encodes statutory holidays,
      Lunar New Year, typhoon closures, and make-up session rules.
      Treated as authoritative for any date within its session range
      not overridden by Layer 1.

  Layer 3 — TW_HOLIDAYS_FALLBACK (static set):
      Safety net for dates beyond XTAI's last_session.
      Scope is intentionally narrow: only dates after XTAI coverage ends.
      Must be reviewed annually.

Decision logic for is_trading_day(d):
    1. Saturday/Sunday  → False  (hard invariant; see note below)
    2. d in twse_holidays DB → False
    3. d within XTAI range  → xtai.is_session(d)
    4. d in TW_HOLIDAYS_FALLBACK → False
    5. Otherwise → True

Weekend policy note:
    Since 2019, Taiwan equity and futures markets remain closed on
    Saturday make-up workdays. Weekend sessions are therefore treated
    as non-trading days by policy, not as a simplification. A future
    trading_sessions table would be required to support any weekend
    override.

Changelog:
    v0.2.0 (2026-06-07):
        Three-layer hybrid. Added XTAI (exchange_calendars) as Layer 2.
        Added twse_holidays DB lookup as Layer 1. TW_HOLIDAYS_FALLBACK
        narrowed to XTAI post-coverage dates only (2027-06-08+).
        All public functions retain identical signatures.
    v0.1.1 (2026-05-16):
        DB missing TAIEX data logs warning to avoid typhoon-day misclassification.
    v0.1.0 (2026-05-16):
        Initial implementation.
"""
from __future__ import annotations

import functools
from datetime import date, timedelta

import exchange_calendars as ec
import pandas as pd

from data.database import connect
from utils.logger import get_logger

logger = get_logger(__name__)


# ── Layer 2: exchange_calendars XTAI ────────────────────────────────────────

@functools.lru_cache(maxsize=1)
def _get_xtai_calendar() -> ec.ExchangeCalendar:
    """Return a cached XTAI calendar instance.

    Cached at module level — construction is non-trivial and the calendar
    object is thread-safe for read operations.
    """
    return ec.get_calendar("XTAI")


def _xtai_last_session() -> date:
    """Return the last date covered by the XTAI calendar."""
    return _get_xtai_calendar().last_session.date()


def _xtai_first_session() -> date:
    """Return the first date covered by the XTAI calendar."""
    return _get_xtai_calendar().first_session.date()


def _xtai_is_session(d: date) -> bool:
    """Check whether d is a trading session per XTAI.

    Args:
        d: Date to check. Caller is responsible for ensuring d is within
           [_xtai_first_session(), _xtai_last_session()].

    Returns:
        True if d is an XTAI trading session.
    """
    return _get_xtai_calendar().is_session(pd.Timestamp(d))


# ── Layer 3: Fallback holidays ───────────────────────────────────────────────
# Scope: dates AFTER XTAI last_session (currently 2027-06-07).
# Do not add dates within XTAI coverage here — XTAI is authoritative for
# that range and duplicates here are redundant noise.

TW_HOLIDAYS_FALLBACK: frozenset[date] = frozenset(
    {
        # 2027 (post-XTAI, partial year — XTAI ends 2027-06-07)
        # National Day area
        date(2027, 10, 10),
        date(2027, 10, 11),
        # Year-end
        date(2027, 12, 31),
        # 2028 — placeholder; update after TWSE publishes official schedule
        date(2028, 1, 1),   # New Year's Day
        date(2028, 2, 5),   # Lunar New Year (estimated)
        date(2028, 2, 6),
        date(2028, 2, 7),
        date(2028, 2, 8),
        date(2028, 2, 9),
        date(2028, 4, 4),   # Children's Day / Tomb Sweeping (estimated)
        date(2028, 5, 1),   # Labour Day
        date(2028, 6, 8),   # Dragon Boat (estimated)
        date(2028, 9, 28),  # Mid-Autumn (estimated)
        date(2028, 10, 10), # National Day
    }
)


# ── Layer 1: DB lookup helpers ───────────────────────────────────────────────

def _is_in_twse_holidays_db(d: date) -> bool:
    """Check whether d appears in the twse_holidays table.

    Returns False (conservatively allows trading) if the DB is unavailable
    or the table does not exist. Logs a warning in that case.

    Args:
        d: Date to check.

    Returns:
        True if d is a recorded TWSE holiday, False otherwise.
    """
    try:
        with connect(read_only=True) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM twse_holidays WHERE holiday_date = ?",
                [d],
            ).fetchone()
        return row is not None and row[0] > 0
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "twse_holidays_db_check_failed",
            date=str(d),
            error=str(exc),
            hint="Run scripts/migrate_add_twse_holidays.py to create the table.",
        )
        return False


# ── Public API ───────────────────────────────────────────────────────────────

def is_trading_day(d: date) -> bool:
    """Return True if d is a Taiwan Stock Exchange trading day.

    Decision order (highest priority first):

        1. Weekend (Sat/Sun) → False
        2. d in twse_holidays DB → False
        3. d within XTAI coverage → xtai.is_session(d)
        4. d in TW_HOLIDAYS_FALLBACK → False
        5. Otherwise → True

    Args:
        d: Date to evaluate.

    Returns:
        True if d is expected to be a TWSE trading day.

    Note:
        For historical dates with TAIEX data in daily_price, the XTAI layer
        is now the authoritative source rather than the DB row-existence check
        used in v0.1.x. XTAI correctly handles typhoon closures and make-up
        sessions within its coverage window.
    """
    # Layer 0: weekend — hard invariant
    # Since 2019, Taiwan equity and futures markets remain closed on
    # Saturday make-up workdays. Weekend sessions are therefore treated
    # as non-trading days by policy, not as a simplification.
    if d.weekday() >= 5:
        return False

    # Layer 1: TWSE official holiday table
    if _is_in_twse_holidays_db(d):
        return False

    # Layer 2: exchange_calendars XTAI
    if _xtai_first_session() <= d <= _xtai_last_session():
        return _xtai_is_session(d)

    # Layer 3: static fallback (post-XTAI dates only)
    return d not in TW_HOLIDAYS_FALLBACK


def previous_trading_day(d: date, max_back_days: int = 30) -> date | None:
    """Return the most recent trading day strictly before d.

    Args:
        d: Reference date (exclusive).
        max_back_days: Maximum calendar days to search backwards.

    Returns:
        The previous trading day, or None if not found within max_back_days.
    """
    for i in range(1, max_back_days + 1):
        candidate = d - timedelta(days=i)
        if is_trading_day(candidate):
            return candidate
    logger.error("no_previous_trading_day_found", date=str(d), max_back=max_back_days)
    return None


def next_trading_day(d: date, max_forward_days: int = 30) -> date | None:
    """Return the nearest trading day strictly after d.

    Calendar truth: returns whether a date IS a trading day per the market
    calendar. Does NOT verify whether daily_price_adj data has been ingested
    for that date. For T+1 fill use cases, use next_fillable_day() instead.

    Args:
        d: Reference date (exclusive).
        max_forward_days: Maximum calendar days to search forward.

    Returns:
        The next trading day, or None if not found within max_forward_days.
    """
    for i in range(1, max_forward_days + 1):
        candidate = d + timedelta(days=i)
        if is_trading_day(candidate):
            return candidate
    logger.error("no_next_trading_day_found", date=str(d), max_forward=max_forward_days)
    return None


def next_fillable_day(d: date, max_forward_days: int = 30) -> date | None:
    """Return the next trading day with daily_price_adj data available.

    v0.1.14.2-c3: explicit split from next_trading_day() to separate two
    concerns:
        - next_trading_day(d): calendar truth ("is 5/18 a trading day?")
        - next_fillable_day(d): calendar + data availability
                                ("is 5/18 a trading day AND do we have data?")

    For T+1 fill semantics (signal on day T, fill at T+1 close as proxy),
    the FILLABLE variant is required: return the next trading day with data
    ingested. Returns None if the calendar's next trading day has no data yet.

    Args:
        d: Reference date (exclusive).
        max_forward_days: Maximum calendar days to search forward.

    Returns:
        Next trading day with ingested data, or None.
    """
    cal_next = next_trading_day(d, max_forward_days=max_forward_days)
    if cal_next is None:
        return None
    try:
        with connect(read_only=True) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM daily_price_adj WHERE date = ?", [cal_next]
            ).fetchone()
        return cal_next if row and row[0] > 0 else None
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "next_fillable_day_db_check_failed",
            date=str(cal_next),
            error=str(exc),
        )
        return None


def get_trading_days(start: date, end: date) -> list[date]:
    """Return all trading days in the closed interval [start, end].

    Args:
        start: Start date (inclusive).
        end: End date (inclusive).

    Returns:
        Sorted list of trading days.
    """
    result: list[date] = []
    cur = start
    while cur <= end:
        if is_trading_day(cur):
            result.append(cur)
        cur += timedelta(days=1)
    return result


def trading_days_between(start: date, end: date) -> int:
    """Return the count of trading days in [start, end].

    Args:
        start: Start date (inclusive).
        end: End date (inclusive).

    Returns:
        Number of trading days.
    """
    return len(get_trading_days(start, end))


# ── Smoke test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    today = date.today()
    print(f"Today ({today}) is trading day: {is_trading_day(today)}")

    xtai_range = (
        f"{_xtai_first_session()} → {_xtai_last_session()}"
    )
    print(f"XTAI coverage: {xtai_range}")

    prev = previous_trading_day(today)
    nxt = next_trading_day(today)
    print(f"Previous trading day: {prev}")
    print(f"Next trading day:     {nxt}")

    known_holidays = [
        (date(2026, 2, 17), "CNY 2026"),
        (date(2024, 7, 24), "Typhoon Gaemi day 1"),
        (date(2024, 7, 25), "Typhoon Gaemi day 2"),
        (date(2024, 2, 8),  "CNY 2024"),
        (date(2024, 4, 4),  "Tomb Sweeping 2024"),
    ]
    print("\nKnown holiday checks (all should be False):")
    for d, label in known_holidays:
        result = is_trading_day(d)
        marker = "✓" if not result else "✗ FAIL"
        print(f"  {d} ({label}): {result}  {marker}")

    known_trading = [
        (date(2024, 7, 23), "Day before Gaemi"),
        (date(2024, 7, 26), "Day after Gaemi"),
        (date(2026, 2, 11), "Last trading day before CNY 2026"),
    ]
    print("\nKnown trading day checks (all should be True):")
    for d, label in known_trading:
        result = is_trading_day(d)
        marker = "✓" if result else "✗ FAIL"
        print(f"  {d} ({label}): {result}  {marker}")
