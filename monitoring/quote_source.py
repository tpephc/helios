# monitoring/quote_source.py
"""Intraday quote source abstraction — v0.1.15.

Stable interface for the price feed so the data source can be swapped
without touching any monitoring logic:

    v0.1.15:  :class:`YFinanceQuoteSource`  (poll-based, ~15-min delayed)
    v0.1.16+: ``ShioajiQuoteSource``        (real-time tick feed, planned)

Documented limitations of YFinanceQuoteSource
----------------------------------------------
* Data is typically 15–20 minutes delayed from TWSE last print.
* yfinance is an unofficial API; repeated calls above ~50/min may be blocked.
  For ≤20 symbols on a 15-min cron cadence this is well within safe limits.
* Only TWSE-listed symbols are handled ('`.TW`' suffix).
  TPEx-listed symbols require '`.TWO`' — not implemented here.
  All currently held positions must be TWSE-listed.  If a protected_symbol
  is TPEx-listed it must be excluded from intraday monitoring, or this
  module extended, before the next Shioaji integration (v0.1.16).
* Halted or suspended symbols return empty history; treated as fetch error.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

logger = logging.getLogger(__name__)

_TWSE_SUFFIX: str = ".TW"
_STALE_THRESHOLD_MINUTES: float = 30.0


@dataclass
class QuoteResult:
    """Outcome of a single-symbol quote fetch."""

    symbol: str
    """Internal Helios symbol (e.g. ``'2330'``), no exchange suffix."""

    price: float | None
    """Last-trade price, or ``None`` if the fetch failed."""

    price_ts: datetime | None
    """UTC timestamp of the last bar returned by the feed.
    ``None`` if unavailable (fast_info fallback or error)."""

    is_stale: bool
    """``True`` if ``price_ts`` is older than ``_STALE_THRESHOLD_MINUTES``,
    or if ``price_ts`` is ``None``.  Stale quotes are skipped in the
    zone-transition loop; they must not trigger Telegram alerts."""

    error: str | None
    """Exception class name on failure, else ``None``."""


class IntradayQuoteSource(Protocol):
    """Protocol for intraday price feed implementations.

    Implementations must:
    * Return exactly one :class:`QuoteResult` per requested symbol.
    * Never raise; represent failures via ``QuoteResult.error``.
    * Be safe to call repeatedly on a 15-min cadence with ≤20 symbols.
    """

    def get_quotes(self, symbols: list[str]) -> dict[str, QuoteResult]:
        """Fetch last-trade prices for the given symbols.

        Args:
            symbols: Internal Helios symbol codes (e.g. ``['2330', '0050']``).

        Returns:
            Mapping of symbol → :class:`QuoteResult`.  Every requested symbol
            has an entry; failures carry ``price=None`` and ``error`` set.
        """
        ...


class YFinanceQuoteSource:
    """yfinance-backed quote source for TWSE-listed symbols.

    Fetches today's 1-minute bars via ``Ticker.history()`` and returns
    the close of the last bar.  Falls back to ``fast_info`` if history is
    empty (e.g. in the first minutes after market open).
    """

    def get_quotes(self, symbols: list[str]) -> dict[str, QuoteResult]:
        """Fetch quotes for all symbols; errors are isolated per-symbol."""
        return {sym: self._fetch_one(sym) for sym in symbols}

    def _fetch_one(self, symbol: str) -> QuoteResult:
        import yfinance as yf  # deferred: fail fast if package missing

        yf_symbol = f"{symbol}{_TWSE_SUFFIX}"
        now_utc = datetime.now(timezone.utc)

        try:
            ticker = yf.Ticker(yf_symbol)
            hist = ticker.history(period="1d", interval="1m", auto_adjust=True)

            if not hist.empty:
                price = float(hist["Close"].iloc[-1])
                raw_ts = hist.index[-1]
                bar_ts = self._normalise_ts(raw_ts)
                age_minutes = (now_utc - bar_ts).total_seconds() / 60.0
                return QuoteResult(
                    symbol=symbol,
                    price=price,
                    price_ts=bar_ts,
                    is_stale=age_minutes > _STALE_THRESHOLD_MINUTES,
                    error=None,
                )

            # Fallback: fast_info has no reliable timestamp.
            fast = ticker.fast_info
            price_raw = fast.get("lastPrice") or fast.get("last_price")
            if price_raw is not None:
                logger.warning("intraday_quote_fallback_fast_info symbol=%s", symbol)
                return QuoteResult(
                    symbol=symbol,
                    price=float(price_raw),
                    price_ts=None,
                    is_stale=True,  # no timestamp → treat as stale
                    error=None,
                )

            return QuoteResult(
                symbol=symbol, price=None, price_ts=None,
                is_stale=True, error="empty_response",
            )

        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "intraday_quote_fetch_failed symbol=%s error=%s",
                symbol, type(exc).__name__,
            )
            return QuoteResult(
                symbol=symbol, price=None, price_ts=None,
                is_stale=True, error=type(exc).__name__,
            )

    @staticmethod
    def _normalise_ts(raw_ts: object) -> datetime:
        """Convert a pandas Timestamp to a UTC-aware datetime."""
        import pandas as pd

        if isinstance(raw_ts, pd.Timestamp):
            if raw_ts.tzinfo is not None:
                return raw_ts.to_pydatetime().astimezone(timezone.utc)
            return raw_ts.to_pydatetime().replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc)


class ShioajiQuoteSource:
    """Shioaji real-time quote source for TWSE-listed symbols.

    Replaces YFinanceQuoteSource with real-time last-trade prices
    (no 15-min delay). Requires production Shioaji API key in .env.
    Contract download adds ~5-10s startup per invocation; acceptable
    for a 15-min cron cadence.

    Falls back to QuoteResult(error=...) per symbol on any failure so
    the monitoring loop is never blocked by a data source error.
    """

    _BATCH = 50  # Shioaji snapshots limit per call

    def get_quotes(self, symbols: list[str]) -> dict[str, QuoteResult]:
        """Fetch real-time snapshots; errors isolated per symbol."""
        import shioaji as sj  # deferred: fail fast if package missing
        from config.settings import get_settings

        cfg = get_settings()
        # Use simulation=True if configured — simulation token does not
        # have production permission but supports snapshots API.
        _is_sim = cfg.shioaji_simulation
        api = sj.Shioaji(simulation=_is_sim)
        try:
            api.login(
                api_key=cfg.shioaji_api_key.get_secret_value(),
                secret_key=cfg.shioaji_secret_key.get_secret_value(),
                fetch_contract=False,   # contracts not needed for snapshots
                subscribe_trade=False,
            )
            return self._fetch(api, symbols)
        except Exception as exc:
            logger.warning(
                "shioaji_quote_source_login_failed error=%s", type(exc).__name__
            )
            return {
                sym: QuoteResult(
                    symbol=sym, price=None, price_ts=None,
                    is_stale=True, error=type(exc).__name__,
                )
                for sym in symbols
            }
        finally:
            try:
                api.logout()
            except Exception:
                pass

    def _fetch(self, api: object, symbols: list[str]) -> dict[str, QuoteResult]:
        """Resolve contracts, batch-snapshot, convert to QuoteResult."""
        from shioaji.contracts import Stock
        from shioaji.constant import Exchange
        contracts = [
            Stock(exchange=Exchange.TSE, code=sid, symbol=f"TSE{sid}")
            for sid in symbols
        ]

        # Batch snapshots
        snaps: list = []
        for i in range(0, len(contracts), self._BATCH):
            snaps.extend(api.snapshots(contracts[i : i + self._BATCH]))

        now_utc = datetime.now(timezone.utc)
        results: dict[str, QuoteResult] = {}

        for snap in snaps:
            try:
                price = snap.close
                ts_dt = datetime.fromtimestamp(snap.ts / 1_000_000_000.0,
                                               tz=timezone.utc)
                age_min = (now_utc - ts_dt).total_seconds() / 60.0
                results[snap.code] = QuoteResult(
                    symbol=snap.code,
                    price=float(price) if price else None,
                    price_ts=ts_dt,
                    is_stale=age_min > _STALE_THRESHOLD_MINUTES,
                    error=None,
                )
            except Exception as exc:
                results[snap.code] = QuoteResult(
                    symbol=snap.code, price=None, price_ts=None,
                    is_stale=True, error=type(exc).__name__,
                )

        # Fill symbols that got no snapshot
        for sym in symbols:
            if sym not in results:
                results[sym] = QuoteResult(
                    symbol=sym, price=None, price_ts=None,
                    is_stale=True, error="snapshot_missing",
                )

        return results

