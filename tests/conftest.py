# tests/conftest.py
"""Shared pytest fixtures for v0.1.14.2-c hotfix test suite.

Per reviewer P0-4: tests must live in the repo (not just inline smoke tests).
This file defines fixtures that let each test get an isolated DuckDB instance
with a clean schema + synthetic price data.

Fixtures:
  tmp_db          - per-test DuckDB at a temp path; auto-cleans
  seeded_prices   - seeds daily_price_adj + daily_features + market_regime
                    with synthetic data for selected (symbol, date) tuples
  mock_bot        - in-memory TelegramBot stand-in (records send_message calls)
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

# ─────────────────────────────────────────────────────────────
# DB fixture (per-test isolation via env var override)
# ─────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Per-test DuckDB at a temp path.

    Builds a fresh Settings instance pointing at tmp_path's DB and injects it
    as the module-level singleton. Schema is auto-initialized.
    """
    from config import settings as _settings

    db_path = tmp_path / "helios_test.duckdb"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    cache_dir = tmp_path / "_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    test_settings = _settings.Settings(db_path=db_path, cache_dir=cache_dir)
    monkeypatch.setattr(_settings, "_settings", test_settings)

    # Init schema in the fresh DB
    from data.database import init_schema
    init_schema()
    return db_path


@pytest.fixture
def isolated_marker(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Override the shutdown marker AND history paths to a temp location.

    v0.1.14.3: also redirects HISTORY_PATH so tests using shutdown_guard
    don't pollute the operator's real ~/.helios_run_history.jsonl.
    """
    marker = tmp_path / "test_marker.json"
    history = tmp_path / "test_history.jsonl"
    from execution import shutdown as _sd
    monkeypatch.setattr(_sd, "MARKER_PATH", marker)
    monkeypatch.setattr(_sd, "HISTORY_PATH", history)
    return marker


# ─────────────────────────────────────────────────────────────
# Synthetic data seeding helpers
# ─────────────────────────────────────────────────────────────


def seed_price(
    symbol: str, d: date, *,
    close: float = 100.0,
    open_price: float | None = None,
    volume: int = 1_000_000,
    atr_14: float = 2.0,
    regime: str = "bull",
) -> None:
    """Seed one row each in daily_price_adj, daily_features, market_regime.

    v0.1.14.3: `open_price` and `volume` are now overridable so fill-realism
    tests can verify the broker reads adj_open (not adj_close) and the
    liquidity gate uses raw volume. Defaults keep all pre-v0.1.14.3 tests
    unchanged (open_price defaults to close; volume defaults to 1M, well
    above any test's fill-share count).
    """
    op = open_price if open_price is not None else close
    from data.database import connect
    with connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO daily_price_adj
              (stock_id, date, adj_open, adj_high, adj_low, adj_close,
               raw_close, cum_factor, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1.0, ?)
            """,
            [symbol, d, op, close, close, close, close, volume],
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO daily_features
              (stock_id, date, atr_14)
            VALUES (?, ?, ?)
            """,
            [symbol, d, atr_14],
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO market_regime
              (date, taiex_close, sma_200, vol_20, regime, computed_at)
            VALUES (?, 17000, 16800, 0.01, ?, ?)
            """,
            [d, regime, datetime.now()],
        )


@pytest.fixture
def seed_calendar(tmp_db: Path):
    """Seed 10 consecutive *trading days* of price data starting Mon 2026-05-04.

    v0.1.14.2-c3: switched from `base + timedelta(days=i)` to stepping via
    `market.trading_calendar.next_trading_day`, since c3 made is_trading_day
    calendar-aware (skips weekends + Taiwan holidays). The old fixture seeded
    weekends as if they were trading days, which the new calendar correctly
    refuses. Starts Mon 2026-05-04 (post-Labor Day, no nearby holidays).
    """
    from market.trading_calendar import next_trading_day as _next_td
    days: list[date] = []
    cur = date(2026, 5, 4)  # Mon, post-Labor Day
    for i in range(10):
        days.append(cur)
        seed_price("0050", cur, close=140.0 + i * 0.5)
        nxt = _next_td(cur)
        if nxt is None:
            break
        cur = nxt
    return days


# ─────────────────────────────────────────────────────────────
# Mock TelegramBot
# ─────────────────────────────────────────────────────────────


class MockTelegramBot:
    """Records send_message calls; configurable get_updates queue + chat_id.

    v0.1.14.3.7: get_updates semantics tightened to match real Telegram:
      - offset == -1: returns LAST item only, does not confirm/drop
      - offset >=  0: returns items with update_id >= offset; items with
                      update_id < offset are confirmed (dropped from queue)
      - timeout == 0: treated as a probe/drain call; the on_poll hook does
                      NOT fire (real polls have timeout > 0)
      - timeout >  0: real poll; on_poll hook fires if registered, allowing
                      tests to inject post-startup messages mid-loop

    update_id is now monotonic (assigned from `_next_update_id`) so that
    items added by an on_poll hook get ids greater than the drain confirmed,
    and aren't accidentally re-confirmed-away.
    """

    def __init__(self, chat_id: str = "TEST_CHAT", succeed: bool = True) -> None:
        self.sent: list[str] = []
        self.update_queue: list[dict] = []
        self.succeed = succeed
        self._next_update_id = 1
        self.poll_count = 0
        # Hook: tests may set `bot.on_poll = lambda n: ...` to inject messages
        # mid-loop. Called BEFORE each real poll (timeout > 0) with the
        # zero-based poll index.
        self.on_poll: Any = None

        class _Cfg:
            pass
        self.config = _Cfg()
        self.config.chat_id = chat_id  # type: ignore[attr-defined]

    def send_message(self, text: str, **kw: Any) -> int | None:
        self.sent.append(text)
        return 1 if self.succeed else None

    def get_updates(self, *, offset: int = 0, timeout: int = 30, **kw: Any) -> list[dict]:
        is_real_poll = timeout > 0
        if is_real_poll and self.on_poll is not None:
            # Hook fires BEFORE filtering, so any messages it enqueues are
            # visible to this same poll (if their update_id >= offset).
            self.on_poll(self.poll_count)
            self.poll_count += 1

        if offset == -1:
            # Telegram special: return last item only; do NOT confirm/drop.
            return [self.update_queue[-1]] if self.update_queue else []

        # Items with update_id >= offset are returned AND kept (caller must
        # confirm with a later, higher-offset call). Items < offset are dropped.
        kept = [u for u in self.update_queue if u.get("update_id", 0) >= offset]
        self.update_queue = kept
        return kept

    def enqueue_text(self, text: str, *, chat_id: str | None = None) -> None:
        """Helper: simulate inbound user message. update_id is monotonic."""
        upd_id = self._next_update_id
        self._next_update_id += 1
        self.update_queue.append({
            "update_id": upd_id,
            "message": {
                "chat": {"id": chat_id if chat_id is not None else self.config.chat_id},
                "text": text,
            },
        })


@pytest.fixture
def mock_bot() -> MockTelegramBot:
    return MockTelegramBot()


@pytest.fixture
def test_account_id() -> str:
    """Fixed account_id string for tests requiring v0.1.18 account isolation."""
    return "test_account"
