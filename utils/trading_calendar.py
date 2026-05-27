# utils/trading_calendar.py
"""Trading calendar predicates — v0.1.16.

Minimal implementation. For production, replace with a calendar that
consults company_metadata or a TWSE holiday table.
"""
from __future__ import annotations

from datetime import date


def is_trading_day(d: date) -> bool:
    """Return True if d is a Taiwan stock market trading day.

    v0.1.16 minimum: weekday check only (Mon=0 ... Fri=4).
    Does NOT account for Taiwan public holidays. Operator MUST replace
    this before enabling live_trading_enabled=True.
    """
    return d.weekday() < 5
