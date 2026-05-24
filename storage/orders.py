# storage/orders.py
"""DEPRECATED legacy order repository — FROZEN as of v0.1.16 (v2).

This module is preserved for import compatibility (storage/__init__.py
re-exports it) but ALL public functions raise NotImplementedError.

Reason for freeze:
  v0.1.16 v2 replaced the orders schema with unit-bearing columns
  (requested_lots / filled_shares / fill_date) and uppercase enum values.
  This module's queries and INSERTs hardcode the legacy v0.1.14 schema
  (lowercase status/side, quantity column, timestamp column).

Migration target:
  Use storage.order_journal for all orders journal CRUD:

    Legacy (this module)           →  Replacement (storage.order_journal)
    ─────────────────────────────────────────────────────────────────────
    orders.record_order(...)       →  order_journal.record_intent(...)
    orders.update_order_status(...) →  order_journal.mark_filled/mark_partial/
                                       mark_failed/mark_cancelled/mark_expired
    orders.get_order(oid)          →  order_journal.get(oid)
    orders.get_open_orders()       →  order_journal.list_by_status(
                                          OrderStatus.SUBMITTED)
    orders.get_orders_for_signal() →  (custom query via order_journal.connect)
    orders.get_filled_orders_since() → (custom query via order_journal.connect)
    orders.has_duplicate_recent()  →  (PreTradeGuard.check_order handles)

  See docs/design/execution_model.md §4 (Journal API contract).

Removal target: v0.1.17 (after validate_install.py is updated).

Version: v0.1.16 (v2) — 2026-05-24
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


_FROZEN_MESSAGE = (
    "storage.orders is FROZEN as of v0.1.16 (v2). "
    "Use storage.order_journal instead. "
    "See module docstring for migration map, or "
    "docs/design/execution_model.md §4."
)


# ─────────────────────────────────────────────────────────────
# Type aliases (preserved for import-time compatibility)
# ─────────────────────────────────────────────────────────────


OrderSide = Literal["buy", "sell"]
OrderType = Literal["market", "limit"]
OrderStatus = Literal["submitted", "filled", "partial", "rejected", "cancelled"]


@dataclass
class OrderRow:
    """Legacy row dataclass. Preserved for import compatibility.

    The fields match the v0.1.14 schema; they no longer correspond to
    the v0.1.16+ orders table. Do not construct from query results.
    """
    order_id: str
    signal_id: str | None
    timestamp: datetime
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    price: float | None
    status: OrderStatus
    filled_qty: int = 0
    avg_price: float | None = None
    commission: float = 0.0
    tax: float = 0.0
    broker: str = "paper"
    metadata: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────
# Frozen public API
# ─────────────────────────────────────────────────────────────


def record_order(*args, **kwargs):
    """FROZEN — use storage.order_journal.record_intent instead."""
    raise NotImplementedError(_FROZEN_MESSAGE)


def update_order_status(*args, **kwargs):
    """FROZEN — use storage.order_journal.mark_filled / mark_partial /
    mark_failed / mark_cancelled / mark_expired instead."""
    raise NotImplementedError(_FROZEN_MESSAGE)


def get_order(*args, **kwargs):
    """FROZEN — use storage.order_journal.get instead."""
    raise NotImplementedError(_FROZEN_MESSAGE)


def get_open_orders(*args, **kwargs):
    """FROZEN — use storage.order_journal.list_by_status(OrderStatus.SUBMITTED)."""
    raise NotImplementedError(_FROZEN_MESSAGE)


def get_orders_for_signal(*args, **kwargs):
    """FROZEN — query order_journal directly. No drop-in replacement."""
    raise NotImplementedError(_FROZEN_MESSAGE)


def get_filled_orders_since(*args, **kwargs):
    """FROZEN — query order_journal directly. No drop-in replacement."""
    raise NotImplementedError(_FROZEN_MESSAGE)


def has_duplicate_recent(*args, **kwargs):
    """FROZEN — PreTradeGuard.check_order handles duplicate prevention."""
    raise NotImplementedError(_FROZEN_MESSAGE)
