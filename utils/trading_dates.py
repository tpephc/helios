# utils/trading_dates.py
"""Trading date utilities — v0.1.15. Canonical date resolution for cron scripts.

Centralises the policy for resolving 'today' in the context of market data:
calendar date is unreliable (holidays, typhoon days, incomplete ETL runs).
The correct reference is the latest date present in the feature pipeline.
"""

from __future__ import annotations

from datetime import date as date_type

from data.database import connect


def resolve_as_of(explicit: str | None = None) -> date_type:
    """Return the as-of date for signal/alert scripts.

    If ``explicit`` is provided, parse and return it directly.
    Otherwise, return the latest date present in ``daily_features``.

    Using ``date.today()`` is unsafe in cron scripts: holidays, typhoon
    days, and incomplete feature runs produce a date with no data.

    Args:
        explicit: ISO-format date string, or None to use latest feature date.

    Returns:
        Resolved as-of date.

    Raises:
        RuntimeError: If ``daily_features`` is empty and no explicit date given.
    """
    if explicit is not None:
        return date_type.fromisoformat(explicit)

    with connect(read_only=True) as conn:
        row = conn.execute("SELECT MAX(date) FROM daily_features").fetchone()

    if row is None or row[0] is None:
        raise RuntimeError(
            "No data in daily_features — run compute_features.py first"
        )
    return row[0]
