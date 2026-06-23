# tests/features/conftest.py
"""Shared fixtures for tests/features/ — Phase 1A scope.

Provides:
  - isolate_calendar_db_lookup (autouse): monkeypatch
    market.trading_calendar._is_in_twse_holidays_db -> False
    to remove DB coupling from calendar logic (spec §12.5).
  - make_adj_close_panel:  synthetic panel builder (spec §13.1).

Anchored-real DB fixtures (PIT-7, PIT-8, PIT-10) are NOT defined
here in Phase 1A; they will be added in Phase 1D.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Callable

import polars as pl
import pytest


# ── Calendar DB-coupling isolation (autouse, spec §12.5) ─────────────


@pytest.fixture(autouse=True)
def isolate_calendar_db_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable Layer 1 (twse_holidays DB lookup) for deterministic tests.

    Pattern from tests/test_trading_calendar_v0_2_0.py:49.
    Applied autouse to all tests in tests/features/.
    """
    try:
        import market.trading_calendar as cal_mod
        monkeypatch.setattr(
            cal_mod, "_is_in_twse_holidays_db", lambda d: False
        )
    except ImportError:
        # If market.trading_calendar not importable, tests that need
        # it will fail with a clearer error. Don't mask that here.
        pass


# ── Synthetic panel builder (spec §13.1) ─────────────────────────────


def _make_adj_close_panel(
    ticker: str,
    end_date: date,
    returns: list[float | None],
    base_price: float = 100.0,
) -> pl.DataFrame:
    """Construct a synthetic adj_close panel ending at end_date.

    CONTRACT (spec §13.1):
        len(returns) == number of daily return observations
        len(panel)   == len(returns) + 1

        Row 0 (earliest): adj_close = base_price, no associated return
        Row i (i >= 1):   adj_close = adj_close[i-1] * (1 + returns[i-1])
                          (None if returns[i-1] is None)

    NaN semantics:
        returns[i] = None  -> adj_close[i+1] = None.
        The next iteration uses the last valid adj_close as prev,
        i.e., None does NOT propagate forward.

    Phase 1A note: this builder produces consecutive WEEKDAY dates
    only (no holiday alignment). Tests that exercise calendar logic
    (PIT-12, PIT-13) construct dates explicitly rather than relying
    on this builder.

    Args:
        ticker:     stock_id value
        end_date:   latest date in panel
        returns:    sequence of daily returns; len = N observations
        base_price: starting adj_close at row 0 (must be > 0)

    Returns:
        Polars DataFrame with len(returns) + 1 rows, sorted ascending
        by date. Schema: stock_id (Utf8), date (Date), adj_close
        (Float64).
    """
    if base_price <= 0:
        raise ValueError(f"base_price must be > 0, got {base_price}")

    n_returns = len(returns)
    n_rows = n_returns + 1

    # Build consecutive weekday dates ending at end_date
    rev_dates: list[date] = []
    cur = end_date
    while len(rev_dates) < n_rows:
        if cur.weekday() < 5:
            rev_dates.append(cur)
        cur = cur - timedelta(days=1)
    dates = list(reversed(rev_dates))

    closes: list[float | None] = [base_price]
    prev = base_price
    for r in returns:
        if r is None:
            closes.append(None)
        else:
            new_close = prev * (1.0 + r)
            closes.append(new_close)
            prev = new_close

    assert len(closes) == n_rows
    assert len(dates) == n_rows

    return pl.DataFrame(
        {
            "stock_id": [ticker] * n_rows,
            "date": dates,
            "adj_close": closes,
        },
        schema={
            "stock_id": pl.Utf8,
            "date": pl.Date,
            "adj_close": pl.Float64,
        },
    )


@pytest.fixture
def make_adj_close_panel() -> Callable[..., pl.DataFrame]:
    """Expose _make_adj_close_panel as a pytest fixture."""
    return _make_adj_close_panel
