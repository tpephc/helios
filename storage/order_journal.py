# storage/order_journal.py
"""Order journal repository — v0.1.18.

The orders table is an append-only event log with controlled UPDATEs for
state transitions. This module is the single source of truth for orders
table CRUD.

v0.1.18 changes:
  - OrderRow.__slots__ + _ORDER_COLUMNS: added account_id after order_id.
  - OrderRow.from_row: added length guard (column count mismatch → ValueError).
  - record_intent: requires account_id; INSERT includes account_id column.
  - record_intent / update_order_spec: added limit_price > 0 / notional >= 0
    validation guards.
  - get_for_account(): new scoped getter — all transition/update methods use
    it to fail-fast on account_id mismatch before touching DB.
  - All UPDATE-by-PK queries: added AND account_id = ? defense-in-depth.
  - All list/count/sum read queries: added account_id filter parameter.
  - find_by_broker_order_id: added account_id parameter; raises ValueError
    if broker_order_id is None/empty (caller bug, not "not found").
  - list_orders_requiring_verification: preserves v0.1.17 semantics
    (FAILED + TRANSPORT only). Two-phase SUBMITTED verification deferred
    to #27.
  - list_orders_for_date: raises NotImplementedError (cannot provide
    account_id; forces caller migration).

v2 changes from v1 (per advisor review):
  - record_intent: accepts fill_date (C-P0-1) and notional (caller-computed).
  - Renamed parameters: requested_qty → requested_lots, filled_qty →
    filled_shares (K-P0-1 / decision 1).
  - list_orders_by_fill_date: new method for reconcile (C-P0-1 / K-P1-4).
  - mark_polled: validates submitted_at IS NOT NULL (D-P0-1), rejects
    filled_shares=0 with non-None avg_fill_price (K-P2-b).
  - new_order_id: uses Asia/Taipei timezone explicitly (K-P2-a).
  - update_order_spec: new method for limit_price/notional (C-P0-3, K-P0-1).
  - mark_submitted: empty-string broker_order_id normalized to None (K-P1-5).

Design principles:
  1. ID generation: 'helios_{YYYYMMDD}_{uuid8}', Taipei time.
  2. Application-layer updated_at.
  3. State transition validation (illegal transitions raise).
  4. intent_at = decision time (T); fill_date = expected execution (T+1).
  5. Crash recovery + reconcile surfaces exposed.
  6. NO unit conversion or normalization in this layer — domain boundary
     responsibility.

Version: v0.1.18 (2026-05-28)
"""
from __future__ import annotations

import json
import uuid
import warnings
from datetime import date as date_type
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from data.database import connect
from execution.order_types import (
    FailureType,
    OrderSide,
    OrderStatus,
)
from utils.logger import get_logger

logger = get_logger(__name__)


# Module timezone: order_id date prefix uses local market time.
TAIPEI_TZ = ZoneInfo("Asia/Taipei")


# ─────────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────────


class OrderJournalError(Exception):
    """Base class for order journal failures."""


class OrderNotFound(OrderJournalError):
    """Raised when an order_id has no corresponding row."""


class InvalidTransition(OrderJournalError):
    """Raised when a state transition violates the lifecycle state machine.

    This is a caller bug. The journal will not silently accept illegal
    transitions because doing so masks application-layer state corruption.
    """


# ─────────────────────────────────────────────────────────────────────────────
# Legitimate state transitions
# ─────────────────────────────────────────────────────────────────────────────


_LEGITIMATE_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.INTENT: frozenset({
        OrderStatus.READY_FOR_SUBMISSION,  # v0.1.17: daily_run T 16:00
        OrderStatus.SUBMITTED,              # legacy direct-submit path
        OrderStatus.FAILED,
    }),
    OrderStatus.READY_FOR_SUBMISSION: frozenset({  # v0.1.17
        OrderStatus.SUBMITTED,              # execution_submitter T+1 08:30
        OrderStatus.EXPIRED,                # stale / suspended / limit-up
        OrderStatus.FAILED,                 # risk cap / data missing / transport
    }),
    OrderStatus.SUBMITTED: frozenset({
        OrderStatus.FILLED,
        OrderStatus.PARTIAL,
        OrderStatus.CANCELLED,
        OrderStatus.EXPIRED,
        OrderStatus.FAILED,
    }),
    # Terminal states
    OrderStatus.FILLED: frozenset(),
    OrderStatus.PARTIAL: frozenset(),
    OrderStatus.FAILED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
    OrderStatus.EXPIRED: frozenset(),
}


def _validate_transition(
    from_status: OrderStatus, to_status: OrderStatus
) -> None:
    """Raise InvalidTransition if not in the legitimate set."""
    if to_status not in _LEGITIMATE_TRANSITIONS[from_status]:
        raise InvalidTransition(
            f"Illegal state transition: {from_status.value} → {to_status.value}. "
            f"Allowed from {from_status.value}: "
            f"{sorted(s.value for s in _LEGITIMATE_TRANSITIONS[from_status])}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# ID generation
# ─────────────────────────────────────────────────────────────────────────────


def new_order_id(at: datetime | None = None) -> str:
    """Generate a journal order_id.

    Format: 'helios_{YYYYMMDD}_{uuid4_hex[:8]}'
    Example: 'helios_20260525_a3f8b2c1'

    v2 fix (K-P2-a): date prefix is Asia/Taipei local time.
    """
    when = at if at is not None else datetime.now(tz=TAIPEI_TZ)
    if when.tzinfo is None:
        when = when.replace(tzinfo=TAIPEI_TZ)
    else:
        when = when.astimezone(TAIPEI_TZ)
    return f"helios_{when.strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"


def _normalize_broker_order_id(value: str | None) -> str | None:
    """Normalize broker-assigned order ID: empty string → None (K-P1-5).

    Shioaji sim mode can return '' (empty string) for trade.order.id.
    Empty string is semantically equivalent to "no broker ID".
    """
    if value is None or value == "":
        return None
    return value


# ─────────────────────────────────────────────────────────────────────────────
# DTOs (read models)
# ─────────────────────────────────────────────────────────────────────────────


class OrderRow:
    """In-memory representation of an orders row.

    Plain class (not dataclass) to avoid OrderSubmissionResult's
    __post_init__ invariant coupling — the journal reads back rows in
    intermediate states that the result type would reject.

    v0.1.18: added account_id field + from_row length guard.
    v2: field names match the unit-bearing schema (requested_lots,
    filled_shares, fill_date).
    """

    __slots__ = (
        "order_id", "account_id", "signal_id", "symbol", "side",
        "requested_lots", "filled_shares", "avg_fill_price", "limit_price",
        "status", "failure_type", "error_code", "error_message",
        "requires_broker_verification", "broker", "broker_order_id",
        "intent_at", "fill_date", "target_fill_date",
        "submitted_at", "last_polled_at", "finalized_at",
        "notional", "commission", "tax", "metadata",
        "created_at", "updated_at",
    )

    def __init__(self, **kwargs: Any) -> None:
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))

    @classmethod
    def from_row(cls, row: tuple, columns: list[str]) -> OrderRow:
        """Build from DB row + column names.

        v0.1.18: added length guard to detect schema drift early.
        """
        if len(row) != len(columns):
            raise ValueError(
                f"OrderRow.from_row: expected {len(columns)} columns, "
                f"got {len(row)}. Schema drift detected — check "
                f"_ORDER_COLUMNS vs DB schema."
            )
        data = dict(zip(columns, row))
        if data.get("status") is not None:
            data["status"] = OrderStatus(data["status"])
        if data.get("side") is not None:
            data["side"] = OrderSide(data["side"])
        if data.get("failure_type") is not None:
            data["failure_type"] = FailureType(data["failure_type"])
        if data.get("metadata"):
            try:
                data["metadata"] = json.loads(data["metadata"])
            except (json.JSONDecodeError, TypeError):
                data["metadata"] = None
        return cls(**data)


# Canonical column order (matches schema declaration).
# v0.1.18: account_id added after order_id.
_ORDER_COLUMNS = [
    "order_id", "account_id", "signal_id", "symbol", "side",
    "requested_lots", "filled_shares", "avg_fill_price", "limit_price",
    "status", "failure_type", "error_code", "error_message",
    "requires_broker_verification", "broker", "broker_order_id",
    "intent_at", "fill_date", "target_fill_date",
    "submitted_at", "last_polled_at", "finalized_at",
    "notional", "commission", "tax", "metadata",
    "created_at", "updated_at",
]

_SELECT_ALL = f"SELECT {', '.join(_ORDER_COLUMNS)} FROM orders"


# ─────────────────────────────────────────────────────────────────────────────
# Scoped getters
# ─────────────────────────────────────────────────────────────────────────────


def get(order_id: str) -> OrderRow:
    """Fetch one order by PK. Raises OrderNotFound if absent.

    PK lookup — globally unique, no account_id filter needed.
    Used by callers that already know the order exists (e.g. internal
    helpers). For account-scoped operations, use get_for_account().
    """
    with connect(read_only=True) as conn:
        row = conn.execute(
            f"{_SELECT_ALL} WHERE order_id = ?",
            [order_id],
        ).fetchone()
    if row is None:
        raise OrderNotFound(f"order_id={order_id}")
    return OrderRow.from_row(row, _ORDER_COLUMNS)


def get_for_account(order_id: str, *, account_id: str) -> OrderRow:
    """Fetch one order by PK and verify account ownership.

    v0.1.18: all transition/update methods use this instead of get()
    to fail-fast on account_id mismatch BEFORE executing any UPDATE.
    This prevents silent 0-row updates when caller passes wrong account_id.

    Raises:
        OrderNotFound: if order_id does not exist OR belongs to a
            different account (intentionally same exception to avoid
            leaking cross-account existence).
    """
    order = get(order_id)
    if order.account_id != account_id:
        raise OrderNotFound(
            f"order_id={order_id} not found for account_id={account_id}"
        )
    return order


# ─────────────────────────────────────────────────────────────────────────────
# Create / record
# ─────────────────────────────────────────────────────────────────────────────


def record_intent(
    *,
    account_id: str,
    symbol: str,
    side: OrderSide,
    requested_lots: int,
    intent_at: datetime,
    fill_date: date_type,
    notional: float = 0.0,
    signal_id: str | None = None,
    limit_price: float | None = None,
    broker: str | None = None,
    metadata: dict | None = None,
) -> str:
    """Insert a new INTENT row. Returns generated order_id.

    Called by broker.submit_buy/sell BEFORE invoking the broker API. If
    the process crashes between this call and api.place_order(),
    startup_recovery will find the orphan INTENT.

    Args:
        account_id:     broker account identifier (e.g. 'philip_sim')
        symbol:         TWSE stock code
        side:           OrderSide.BUY or OrderSide.SELL
        requested_lots: lot count (Common lot = SHARES_PER_LOT shares)
        intent_at:      business decision time (T day)
        fill_date:      expected execution date (T+1 trading day)
        notional:       TWD commitment (caller-computed); typically
                        limit_price * requested_lots * SHARES_PER_LOT.
                        Default 0 for pre-contract-lookup intent;
                        update_order_spec sets actual value once
                        limit_price is known.
        signal_id:      upstream signal reference
        limit_price:    TWD per share; None if not yet known
        broker:         broker tag
        metadata:       debug context dict (serialized to JSON)

    v0.1.18: account_id is now a required parameter.

    Returns:
        The generated order_id.
    """
    if requested_lots <= 0:
        raise ValueError(
            f"requested_lots must be positive, got {requested_lots}"
        )
    if limit_price is not None and limit_price <= 0:
        raise ValueError(
            f"limit_price must be positive when set, got {limit_price}"
        )
    if notional < 0:
        raise ValueError(
            f"notional must be non-negative, got {notional}"
        )

    order_id = new_order_id(at=intent_at)
    metadata_json = json.dumps(metadata) if metadata else None

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO orders (
                order_id, account_id, signal_id, symbol, side, requested_lots,
                status, limit_price, notional, broker,
                intent_at, fill_date, metadata,
                created_at, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?,
                'INTENT', ?, ?, ?,
                ?, ?, ?,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """,
            [
                order_id, account_id, signal_id, symbol, side.value,
                requested_lots,
                limit_price, notional, broker,
                intent_at, fill_date, metadata_json,
            ],
        )
    logger.info(
        "order_intent_recorded",
        order_id=order_id, account_id=account_id,
        symbol=symbol, side=side.value,
        requested_lots=requested_lots, fill_date=str(fill_date),
        notional=notional, broker=broker, signal_id=signal_id,
    )
    return order_id


def update_order_spec(
    order_id: str,
    *,
    limit_price: float,
    notional: float,
    account_id: str,
) -> None:
    """Update limit_price and notional after contract lookup.

    Used between record_intent (which knows requested_lots but not
    necessarily price) and pre_trade_guard / place_order. Caller computes
    notional as limit_price * requested_lots * SHARES_PER_LOT.

    Only legal in INTENT or READY_FOR_SUBMISSION state.
    """
    if limit_price <= 0:
        raise ValueError(
            f"limit_price must be positive, got {limit_price}"
        )
    if notional < 0:
        raise ValueError(
            f"notional must be non-negative, got {notional}"
        )

    current = get_for_account(order_id, account_id=account_id)
    _allowed = {OrderStatus.INTENT, OrderStatus.READY_FOR_SUBMISSION}
    if current.status not in _allowed:
        raise InvalidTransition(
            f"update_order_spec requires status in "
            f"{sorted(s.value for s in _allowed)}, got "
            f"{current.status.value} for order_id={order_id}"
        )

    with connect() as conn:
        conn.execute(
            """
            UPDATE orders SET
                limit_price = ?,
                notional = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE order_id = ? AND account_id = ?
            """,
            [limit_price, notional, order_id, account_id],
        )


# ─────────────────────────────────────────────────────────────────────────────
# State transitions
# ─────────────────────────────────────────────────────────────────────────────


def mark_submitted(
    order_id: str,
    *,
    broker_order_id: str | None,
    submitted_at: datetime,
    account_id: str,
) -> None:
    """INTENT → SUBMITTED. Records broker_order_id.

    v2 (K-P1-5): empty-string broker_order_id from sim mode is normalized
    to NULL so reconcile lookup semantics are consistent.
    """
    current = get_for_account(order_id, account_id=account_id)
    _validate_transition(current.status, OrderStatus.SUBMITTED)

    normalized_boi = _normalize_broker_order_id(broker_order_id)

    with connect() as conn:
        conn.execute(
            """
            UPDATE orders SET
                status = 'SUBMITTED',
                broker_order_id = ?,
                submitted_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE order_id = ? AND account_id = ?
            """,
            [normalized_boi, submitted_at, order_id, account_id],
        )
    logger.info(
        "order_submitted",
        order_id=order_id, account_id=account_id,
        broker_order_id=normalized_boi,
    )


def mark_ready_for_submission(
    order_id: str,
    *,
    target_fill_date: date_type,
    account_id: str,
    ready_at: datetime | None = None,
) -> None:
    """INTENT → READY_FOR_SUBMISSION. Sets target_fill_date.

    Called by daily_run at T 16:00 after PreTradeGuard passes. The order
    sits in this state until execution_submitter picks it up at T+1 08:30.
    """
    current = get_for_account(order_id, account_id=account_id)
    _validate_transition(current.status, OrderStatus.READY_FOR_SUBMISSION)

    when = ready_at or datetime.now(tz=TAIPEI_TZ)

    with connect() as conn:
        conn.execute(
            """
            UPDATE orders SET
                status = 'READY_FOR_SUBMISSION',
                target_fill_date = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE order_id = ? AND account_id = ?
            """,
            [target_fill_date, order_id, account_id],
        )
    logger.info(
        "order_ready_for_submission",
        order_id=order_id, account_id=account_id,
        target_fill_date=str(target_fill_date),
    )


def mark_polled(
    order_id: str,
    *,
    polled_at: datetime,
    account_id: str,
    filled_shares: int = 0,
    avg_fill_price: float | None = None,
) -> None:
    """Record a poll of broker status. Does NOT transition status.

    Updates last_polled_at and (optionally) filled_shares / avg_fill_price.
    Used when polling returns SUBMITTED-but-not-yet-filled state.
    """
    current = get_for_account(order_id, account_id=account_id)
    if current.status is not OrderStatus.SUBMITTED:
        raise InvalidTransition(
            f"mark_polled requires status=SUBMITTED, got {current.status.value} "
            f"for order_id={order_id}"
        )
    if current.submitted_at is None:
        raise InvalidTransition(
            f"mark_polled called on order {order_id} with status=SUBMITTED "
            f"but submitted_at=None. Journal inconsistency; investigate "
            f"before continuing."
        )
    if filled_shares == 0 and avg_fill_price is not None:
        raise ValueError(
            f"mark_polled: filled_shares=0 requires avg_fill_price=None, "
            f"got avg_fill_price={avg_fill_price}"
        )
    if filled_shares < 0:
        raise ValueError(
            f"mark_polled: filled_shares must be non-negative, got {filled_shares}"
        )

    with connect() as conn:
        conn.execute(
            """
            UPDATE orders SET
                last_polled_at = ?,
                filled_shares = ?,
                avg_fill_price = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE order_id = ? AND account_id = ?
            """,
            [polled_at, filled_shares, avg_fill_price, order_id, account_id],
        )


def mark_filled(
    order_id: str,
    *,
    filled_shares: int,
    avg_fill_price: float,
    account_id: str,
    commission: float = 0.0,
    tax: float = 0.0,
    finalized_at: datetime | None = None,
) -> None:
    """SUBMITTED → FILLED.

    filled_shares MUST equal requested_lots * SHARES_PER_LOT (DB CHECK
    enforces; this method asserts at application layer for earlier failure).
    """
    from execution.order_types import SHARES_PER_LOT

    current = get_for_account(order_id, account_id=account_id)
    _validate_transition(current.status, OrderStatus.FILLED)

    required_shares = current.requested_lots * SHARES_PER_LOT
    if filled_shares != required_shares:
        raise InvalidTransition(
            f"mark_filled requires filled_shares ({filled_shares}) == "
            f"requested_lots × {SHARES_PER_LOT} ({required_shares}) "
            f"for order_id={order_id}. Use mark_partial for incomplete fills."
        )

    finalized = finalized_at or datetime.now(tz=TAIPEI_TZ)
    with connect() as conn:
        conn.execute(
            """
            UPDATE orders SET
                status = 'FILLED',
                filled_shares = ?,
                avg_fill_price = ?,
                commission = ?,
                tax = ?,
                finalized_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE order_id = ? AND account_id = ?
            """,
            [filled_shares, avg_fill_price, commission, tax, finalized,
             order_id, account_id],
        )
    logger.info(
        "order_filled",
        order_id=order_id, account_id=account_id,
        filled_shares=filled_shares,
        avg_fill_price=avg_fill_price, commission=commission, tax=tax,
    )


def mark_partial(
    order_id: str,
    *,
    filled_shares: int,
    avg_fill_price: float,
    account_id: str,
    commission: float = 0.0,
    tax: float = 0.0,
    finalized_at: datetime | None = None,
) -> None:
    """SUBMITTED → PARTIAL. filled_shares MUST be 0 < x < requested_shares.

    PARTIAL is operationally terminal in v0.1.16 (manual review required).
    Position is NOT opened.
    """
    from execution.order_types import SHARES_PER_LOT

    current = get_for_account(order_id, account_id=account_id)
    _validate_transition(current.status, OrderStatus.PARTIAL)

    required_shares = current.requested_lots * SHARES_PER_LOT
    if not (0 < filled_shares < required_shares):
        raise InvalidTransition(
            f"mark_partial requires 0 < filled_shares ({filled_shares}) < "
            f"requested_shares ({required_shares}; "
            f"= requested_lots {current.requested_lots} × {SHARES_PER_LOT}) "
            f"for order_id={order_id}"
        )

    finalized = finalized_at or datetime.now(tz=TAIPEI_TZ)
    with connect() as conn:
        conn.execute(
            """
            UPDATE orders SET
                status = 'PARTIAL',
                filled_shares = ?,
                avg_fill_price = ?,
                commission = ?,
                tax = ?,
                finalized_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE order_id = ? AND account_id = ?
            """,
            [filled_shares, avg_fill_price, commission, tax, finalized,
             order_id, account_id],
        )
    logger.error(
        "order_partial_filled_manual_review_required",
        order_id=order_id, account_id=account_id,
        filled_shares=filled_shares,
        requested_shares=required_shares,
    )


def mark_failed(
    order_id: str,
    *,
    failure_type: FailureType,
    error_code: str,
    account_id: str,
    error_message: str | None = None,
    finalized_at: datetime | None = None,
) -> None:
    """{INTENT, SUBMITTED} → FAILED. failure_type required.

    For TRANSPORT, requires_broker_verification is set TRUE automatically.
    """
    current = get_for_account(order_id, account_id=account_id)
    _validate_transition(current.status, OrderStatus.FAILED)

    finalized = finalized_at or datetime.now(tz=TAIPEI_TZ)
    requires_verification = failure_type.requires_broker_verification

    with connect() as conn:
        conn.execute(
            """
            UPDATE orders SET
                status = 'FAILED',
                failure_type = ?,
                error_code = ?,
                error_message = ?,
                requires_broker_verification = ?,
                finalized_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE order_id = ? AND account_id = ?
            """,
            [
                failure_type.value, error_code, error_message,
                requires_verification, finalized, order_id, account_id,
            ],
        )
    log_level = "error" if requires_verification else "warning"
    getattr(logger, log_level)(
        "order_failed",
        order_id=order_id, account_id=account_id,
        failure_type=failure_type.value,
        error_code=error_code, error_message=error_message,
        requires_broker_verification=requires_verification,
    )


def mark_cancelled(
    order_id: str,
    *,
    account_id: str,
    reason: str | None = None,
    finalized_at: datetime | None = None,
) -> None:
    """SUBMITTED → CANCELLED."""
    current = get_for_account(order_id, account_id=account_id)
    _validate_transition(current.status, OrderStatus.CANCELLED)

    finalized = finalized_at or datetime.now(tz=TAIPEI_TZ)
    with connect() as conn:
        conn.execute(
            """
            UPDATE orders SET
                status = 'CANCELLED',
                error_message = ?,
                finalized_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE order_id = ? AND account_id = ?
            """,
            [reason, finalized, order_id, account_id],
        )
    logger.info(
        "order_cancelled",
        order_id=order_id, account_id=account_id, reason=reason,
    )


def mark_expired(
    order_id: str,
    *,
    account_id: str,
    reason: str | None = None,
    finalized_at: datetime | None = None,
) -> None:
    """SUBMITTED → EXPIRED. Used by startup_recovery for stale ROD orders."""
    current = get_for_account(order_id, account_id=account_id)
    _validate_transition(current.status, OrderStatus.EXPIRED)

    finalized = finalized_at or datetime.now(tz=TAIPEI_TZ)
    with connect() as conn:
        conn.execute(
            """
            UPDATE orders SET
                status = 'EXPIRED',
                error_message = ?,
                finalized_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE order_id = ? AND account_id = ?
            """,
            [reason, finalized, order_id, account_id],
        )
    logger.info(
        "order_expired",
        order_id=order_id, account_id=account_id, reason=reason,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Reads
# ─────────────────────────────────────────────────────────────────────────────


def find_by_broker_order_id(
    broker_order_id: str | None,
    *,
    account_id: str,
) -> OrderRow | None:
    """Lookup by broker-assigned ID within an account.

    v0.1.18: account_id required — broker_order_id may collide across
    accounts (different brokers can reuse IDs).

    Raises:
        ValueError: if broker_order_id is None or empty string. Passing
            None is a caller bug (not "not found"), because it means the
            caller is searching for an order that never received a broker ID.
            Callers must guard before calling.

    Returns:
        OrderRow if found, None if no match in this account.
    """
    normalized = _normalize_broker_order_id(broker_order_id)
    if normalized is None:
        raise ValueError(
            "find_by_broker_order_id: broker_order_id must be non-empty. "
            "Caller must guard against None/empty before calling."
        )
    with connect(read_only=True) as conn:
        row = conn.execute(
            f"{_SELECT_ALL} WHERE broker_order_id = ? AND account_id = ?",
            [normalized, account_id],
        ).fetchone()
    return OrderRow.from_row(row, _ORDER_COLUMNS) if row else None


def list_orders_by_fill_date(
    fill_date: date_type,
    *,
    account_id: str,
) -> list[OrderRow]:
    """All orders whose fill_date equals the given date for an account.

    PRIMARY API for reconcile_fills.py.
    """
    with connect(read_only=True) as conn:
        rows = conn.execute(
            f"{_SELECT_ALL} WHERE fill_date = ? AND account_id = ? "
            f"ORDER BY intent_at",
            [fill_date, account_id],
        ).fetchall()
    return [OrderRow.from_row(r, _ORDER_COLUMNS) for r in rows]


def list_orders_for_intent_date(
    intent_date: date_type,
    *,
    account_id: str,
) -> list[OrderRow]:
    """All orders whose intent_at date equals the given date for an account.

    Used by reports and audit queries that key on decision date (NOT for
    reconcile — use list_orders_by_fill_date instead).
    """
    with connect(read_only=True) as conn:
        rows = conn.execute(
            f"{_SELECT_ALL} WHERE CAST(intent_at AS DATE) = ? "
            f"AND account_id = ? ORDER BY intent_at",
            [intent_date, account_id],
        ).fetchall()
    return [OrderRow.from_row(r, _ORDER_COLUMNS) for r in rows]


def list_orders_for_date(as_of: date_type) -> list[OrderRow]:
    """DEPRECATED — use list_orders_by_fill_date or list_orders_for_intent_date.

    v0.1.18: raises NotImplementedError. Cannot provide account_id;
    forces caller migration to account-scoped API.
    """
    warnings.warn(
        "list_orders_for_date is deprecated; use list_orders_by_fill_date "
        "for reconcile or list_orders_for_intent_date for audit reports.",
        DeprecationWarning, stacklevel=2,
    )
    raise NotImplementedError(
        "list_orders_for_date removed in v0.1.18. "
        "Use list_orders_by_fill_date(fill_date, account_id=...) or "
        "list_orders_for_intent_date(intent_date, account_id=...)."
    )


def list_by_status(
    status: OrderStatus,
    *,
    account_id: str,
) -> list[OrderRow]:
    """All orders currently in the given status for an account."""
    with connect(read_only=True) as conn:
        rows = conn.execute(
            f"{_SELECT_ALL} WHERE status = ? AND account_id = ? "
            f"ORDER BY intent_at",
            [status.value, account_id],
        ).fetchall()
    return [OrderRow.from_row(r, _ORDER_COLUMNS) for r in rows]


def count_today_orders(
    *,
    account_id: str,
    side: OrderSide | None = None,
    now: datetime | None = None,
    exclude_order_id: str | None = None,
) -> int:
    """Count orders intent'd today for an account (for PreTradeGuard daily cap).

    Counts ALL statuses including FAILED — pre-trade guard caps attempts,
    not just successful submissions, to prevent retry storms.
    """
    when = (now or datetime.now(tz=TAIPEI_TZ))
    if when.tzinfo is None:
        when = when.replace(tzinfo=TAIPEI_TZ)
    else:
        when = when.astimezone(TAIPEI_TZ)
    today = when.date()

    query = (
        "SELECT COUNT(*) FROM orders "
        "WHERE CAST(intent_at AS DATE) = ? AND account_id = ?"
    )
    params: list[Any] = [today, account_id]
    if side is not None:
        query += " AND side = ?"
        params.append(side.value)
    if exclude_order_id is not None:
        query += " AND order_id != ?"
        params.append(exclude_order_id)
    with connect(read_only=True) as conn:
        result = conn.execute(query, params).fetchone()
    return int(result[0]) if result else 0


def sum_today_notional(
    *,
    account_id: str,
    side: OrderSide | None = None,
    now: datetime | None = None,
    exclude_failed: bool = True,
    exclude_order_id: str | None = None,
) -> float:
    """Sum notional of orders intent'd today for an account (for PreTradeGuard).

    Includes SUBMITTED orders by design: SUBMITTED notional is real
    committed capital at the broker (even before fill). Daily cap is
    "total commitment", not "total fills".
    """
    when = (now or datetime.now(tz=TAIPEI_TZ))
    if when.tzinfo is None:
        when = when.replace(tzinfo=TAIPEI_TZ)
    else:
        when = when.astimezone(TAIPEI_TZ)
    today = when.date()

    query = (
        "SELECT COALESCE(SUM(notional), 0) FROM orders "
        "WHERE CAST(intent_at AS DATE) = ? AND account_id = ?"
    )
    params: list[Any] = [today, account_id]
    if side is not None:
        query += " AND side = ?"
        params.append(side.value)
    if exclude_failed:
        query += " AND status != 'FAILED'"
    if exclude_order_id is not None:
        query += " AND order_id != ?"
        params.append(exclude_order_id)
    with connect(read_only=True) as conn:
        result = conn.execute(query, params).fetchone()
    return float(result[0]) if result else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Recovery surfaces
# ─────────────────────────────────────────────────────────────────────────────


def list_orphan_intents(
    *,
    account_id: str,
    older_than: timedelta = timedelta(minutes=10),
    now: datetime | None = None,
) -> list[OrderRow]:
    """INTENT orders older than `older_than` for an account — likely crash-orphans."""
    when = now or datetime.now(tz=TAIPEI_TZ)
    if when.tzinfo is None:
        when = when.replace(tzinfo=TAIPEI_TZ)
    cutoff = when - older_than
    with connect(read_only=True) as conn:
        rows = conn.execute(
            f"{_SELECT_ALL} WHERE status = 'INTENT' AND intent_at < ? "
            f"AND account_id = ? ORDER BY intent_at",
            [cutoff, account_id],
        ).fetchall()
    return [OrderRow.from_row(r, _ORDER_COLUMNS) for r in rows]


def list_stale_submitted_by_fill_date(
    *,
    expired_on_or_before: date_type,
    account_id: str,
    now: datetime | None = None,
) -> list[OrderRow]:
    """SUBMITTED orders whose fill_date has passed without resolution."""
    with connect(read_only=True) as conn:
        rows = conn.execute(
            f"{_SELECT_ALL} WHERE status = 'SUBMITTED' AND fill_date <= ? "
            f"AND account_id = ? ORDER BY fill_date, submitted_at",
            [expired_on_or_before, account_id],
        ).fetchall()
    return [OrderRow.from_row(r, _ORDER_COLUMNS) for r in rows]


def list_ready_for_submission(
    *,
    target_fill_date: date_type,
    account_id: str,
) -> list[OrderRow]:
    """READY_FOR_SUBMISSION orders for a given target fill date and account.

    Primary query for execution_submitter at T+1 08:30.
    """
    with connect(read_only=True) as conn:
        rows = conn.execute(
            f"{_SELECT_ALL} WHERE status = 'READY_FOR_SUBMISSION' "
            f"AND target_fill_date = ? AND account_id = ? ORDER BY intent_at",
            [target_fill_date, account_id],
        ).fetchall()
    return [OrderRow.from_row(r, _ORDER_COLUMNS) for r in rows]


def list_stale_ready_for_submission(
    *,
    expired_on_or_before: date_type,
    account_id: str,
) -> list[OrderRow]:
    """READY_FOR_SUBMISSION orders whose target_fill_date has passed."""
    with connect(read_only=True) as conn:
        rows = conn.execute(
            f"{_SELECT_ALL} WHERE status = 'READY_FOR_SUBMISSION' "
            f"AND target_fill_date <= ? AND account_id = ? "
            f"ORDER BY target_fill_date, intent_at",
            [expired_on_or_before, account_id],
        ).fetchall()
    return [OrderRow.from_row(r, _ORDER_COLUMNS) for r in rows]


def list_orders_requiring_verification(
    *,
    account_id: str,
) -> list[OrderRow]:
    """Orders with requires_broker_verification=TRUE for an account.

    v0.1.18 preserves v0.1.17 semantics: verification currently applies
    only to FAILED/TRANSPORT orders. SUBMITTED two-phase broker
    verification is deferred to #27 (execution-hardening ticket).

    These are FAILED.transport orders where Helios doesn't know if the
    broker actually received the order. Reconcile MUST resolve them.
    """
    with connect(read_only=True) as conn:
        rows = conn.execute(
            f"{_SELECT_ALL} WHERE requires_broker_verification = TRUE "
            f"AND status = 'FAILED' AND account_id = ? ORDER BY finalized_at",
            [account_id],
        ).fetchall()
    return [OrderRow.from_row(r, _ORDER_COLUMNS) for r in rows]


def confirm_submission(
    order_id: str,
    *,
    account_id: str,
    broker_order_id: str | None,
    confirmed_at: datetime | None = None,
) -> None:
    """Confirm broker submission: set broker_order_id and clear verification flag.

    Called by execution_submitter after place_order succeeds and
    broker_order_id is extracted from the trade response.

    v0.1.18: replaces raw SQL in execution_submitter. Validates order
    ownership via get_for_account before UPDATE to prevent cross-account
    contamination and silent 0-row updates.

    Only legal in SUBMITTED state (mark_submitted must have been called first).

    Args:
        order_id: Helios journal order_id.
        account_id: broker account identifier.
        broker_order_id: broker-assigned ID from trade response. None if
            broker did not return an ID (sim mode edge case).
        confirmed_at: confirmation timestamp (default: now in Taipei TZ).
    """
    current = get_for_account(order_id, account_id=account_id)
    if current.status is not OrderStatus.SUBMITTED:
        raise InvalidTransition(
            f"confirm_submission requires status=SUBMITTED, got "
            f"{current.status.value} for order_id={order_id}"
        )

    normalized_boi = _normalize_broker_order_id(broker_order_id)
    when = confirmed_at or datetime.now(tz=TAIPEI_TZ)

    with connect() as conn:
        conn.execute(
            """
            UPDATE orders SET
                broker_order_id = ?,
                requires_broker_verification = FALSE,
                updated_at = ?
            WHERE order_id = ? AND account_id = ?
            """,
            [normalized_boi, when, order_id, account_id],
        )
    logger.info(
        "order_submission_confirmed",
        order_id=order_id, account_id=account_id,
        broker_order_id=normalized_boi,
    )
