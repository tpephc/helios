# execution/broker_adapter.py
"""Broker adapter protocol — v0.1.16 (post-review v2).

Decouples reconcile and other consumers from broker SDK specifics.
Concrete brokers (LiveBroker, PaperBroker) implement this protocol; their
SDK imports (shioaji, etc.) stay inside the adapter implementation.

v2 (D-P0-2, decision 3a): replaces direct calls into LiveBroker._login /
_logout from reconcile_fills.py. The v1 design leaked Shioaji types into
the reconcile module (via `import shioaji as sj`) and broke encapsulation
by reaching into private methods.

Why a Protocol and not an ABC:
  - Protocol allows structural typing; existing LiveBroker can satisfy
    it without inheriting (less coupling).
  - runtime_checkable enables isinstance() for diagnostics if needed.
  - No metaclass machinery in domain layer.

Session handle is intentionally `object` — the protocol does not specify
what a session looks like, only that it is opaque to consumers and
passed back to the adapter for subsequent calls. Concrete adapters
return whatever they need (e.g. Shioaji api instance).

Version: v0.1.16 (2026-05-24, v2)
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date as date_type
from typing import Any, Iterator, Protocol, runtime_checkable


# Normalized broker data returned by adapter methods.
#
# Quantity unit convention (v0.1.16 v2.1, 2026-05-25):
#   All quantities returned by BrokerAdapter methods are in CANONICAL
#   SHARES (share-equivalent). Adapters MUST normalize broker-native
#   units to shares at their boundary before returning data through
#   this Protocol.
#
#   For Shioaji-backed adapters (LiveBroker):
#     - Common path: deal.quantity and pos.quantity are in LOTS at the
#       SDK boundary. LiveBroker × SHARES_PER_LOT before returning.
#     - IntradayOdd path: deal.quantity and pos.quantity are in SHARES
#       natively. NOT IMPLEMENTED in v0.1.16 v2.1; reserved for v0.1.17.
#
#   Design invariant (FROZEN):
#     "Broker adapters may expose broker-native quantity semantics, but
#      all persisted execution accounting inside Helios must use
#      canonical share-equivalent units."
#
#   Consumers (reconcile_fills, etc.) operate on canonical shares only.
#
# All prices in TWD per share.
# Date fields are date_type, not str.
#
# Using TypedDict-like plain dict for forward compat; structural typing
# at the consumer side.
#
# fetch_trades returns list of:
#   {
#       "broker_order_id": str | None,
#       "symbol": str,
#       "side": "BUY" | "SELL",
#       "filled_shares": int,
#       "avg_price": float | None,
#       "trade_date": date_type,
#       "raw_status": str,        # original broker status string
#   }
#
# fetch_holdings returns list of:
#   {
#       "symbol": str,
#       "shares": int,
#       "avg_cost": float,
#   }


@runtime_checkable
class BrokerAdapter(Protocol):
    """Protocol for broker adapters used by reconcile and other consumers.

    Implementations:
      - LiveBroker (execution/live_broker.py) — Shioaji-backed
      - PaperBroker — does NOT implement this protocol in v0.1.16 (paper
        broker has no concept of "broker holdings" or "broker trades"
        separate from Helios state)

    Concrete adapters MUST NOT leak SDK types (e.g. shioaji.Trade) across
    method boundaries. All data is normalized to dicts.
    """

    def login_session(self) -> Any:
        """Context manager-compatible session yield.

        Concrete adapters should provide this as a method that returns a
        context manager. Usage:

            with adapter.login_session() as session:
                trades = adapter.fetch_trades(session, as_of)
                holdings = adapter.fetch_holdings(session)

        Returns:
            A context manager. The yielded value is the opaque session
            handle passed to fetch_trades/fetch_holdings.
        """
        ...

    def fetch_trades(
        self, session: Any, as_of: date_type,
    ) -> list[dict]:
        """Fetch broker-confirmed trades for as_of date.

        Args:
            session: handle from login_session()
            as_of:   trade date filter (broker trade_date == as_of)

        Returns:
            List of normalized trade dicts (see module docstring).
            Empty list if no trades or fetch failed (adapter logs errors;
            does not raise).
        """
        ...

    def fetch_holdings(self, session: Any) -> list[dict]:
        """Fetch current broker-held positions snapshot.

        Args:
            session: handle from login_session()

        Returns:
            List of normalized holding dicts (see module docstring).
        """
        ...


class BrokerAdapterError(Exception):
    """Adapter-level errors (login failure, network issues during fetch)."""


# ─────────────────────────────────────────────────────────────────────────────
# Convenience: type-erased adapter wrapper
# ─────────────────────────────────────────────────────────────────────────────


@contextmanager
def open_adapter_session(adapter: BrokerAdapter) -> Iterator[Any]:
    """Convenience wrapper that turns adapter.login_session() into a
    plain context manager usable in `with ... as session:` blocks.

    Adapters can implement login_session as a @contextmanager method
    directly; this wrapper exists for cases where the adapter returns a
    bare context manager object that consumers want to use uniformly.

    Usage:
        with open_adapter_session(adapter) as session:
            trades = adapter.fetch_trades(session, as_of)
    """
    with adapter.login_session() as session:
        yield session
