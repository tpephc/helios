# utils/trading_calendar.py
"""Trading calendar predicates — v0.1.16.

Weekday-only fallback. Suitable for tests and offline research tooling only.

Must NOT be used for:
  - production order scheduling
  - fill-date or target_fill_date calculations
  - trading-day horizon calculations (e.g. forward return offsets)

Replace with a TWSE public-holiday-aware calendar before any production
scheduling or execution logic depends on this module.
"""
from __future__ import annotations

from datetime import date


def is_trading_day(d: date) -> bool:
    """Return True if d falls on a weekday (Mon-Fri).

    WARNING: This is a weekday-only approximation. It does NOT account
    for Taiwan public holidays (e.g. Lunar New Year, National Day).
    Do not use for production scheduling, fill-date logic, or any
    trading-day horizon calculation.
    """
    return d.weekday() < 5
