# execution/order_types.py
"""Order lifecycle domain types — v0.1.17.

v2 changes from v1:
  - Renamed OrderSubmissionResult.requested_qty → requested_lots (unit: lots)
  - Renamed OrderSubmissionResult.filled_qty → filled_shares (unit: shares)
  - position_opened and __post_init__ invariants now use share-equivalent
    comparison (requested_lots * SHARES_PER_LOT vs filled_shares).
  - Added SHARES_PER_LOT module constant.

These changes fix K-P0-1 / K-P0-2: the v1 design compared `requested_qty`
(in lots) directly to `filled_qty` (in shares from Shioaji deals), causing
any partial fill to register as fully filled.

UNIT CONVENTION (read carefully — violations cause silent position desync):
  requested_lots: integer count of Common lots (1 lot = SHARES_PER_LOT shares).
                  Taiwan stock: SHARES_PER_LOT = 1000.
  filled_shares:  integer count of shares actually filled
                  (broker-native unit from Shioaji deal.quantity).
  Comparing the two directly is a bug. Always convert:
      requested_shares = requested_lots * SHARES_PER_LOT

Design references:
  - docs/decision_records/v0_1_16_decision_lock.md
  - docs/design/execution_model.md
  - Advisor review: K-P0-1, K-P0-2

Version: v0.1.17 (2026-05-27)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_type
from datetime import datetime
from enum import Enum


# ─────────────────────────────────────────────────────────────────────────────
# Unit conversion constant
# ─────────────────────────────────────────────────────────────────────────────


# Taiwan stock market: Common lot = 1000 shares. This constant is the SINGLE
# place this number lives in the domain layer. If it ever changes (it won't
# for TWSE), all converters update here. Repository / broker / reconcile
# must import this, not redefine it.
SHARES_PER_LOT: int = 1000


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────


class OrderStatus(str, Enum):
    """Order lifecycle states — v0.1.17.

    State transitions (legitimate only):

        INTENT                → READY_FOR_SUBMISSION  (daily_run T 16:00)
        INTENT                → SUBMITTED             (direct submit, legacy)
        INTENT                → FAILED                (pre-trade guard fail)
        READY_FOR_SUBMISSION  → SUBMITTED             (execution_submitter T+1 08:30)
        READY_FOR_SUBMISSION  → EXPIRED               (stale / suspended / limit-up)
        READY_FOR_SUBMISSION  → FAILED                (risk cap / data missing)
        SUBMITTED             → FILLED                (deals confirmed)
        SUBMITTED             → PARTIAL               (deals < requested)
        SUBMITTED             → CANCELLED             (broker cancelled)
        SUBMITTED             → EXPIRED               (ROD expired / cancel sweep)
        SUBMITTED             → FAILED                (broker reject post-accept)

    Terminal: FILLED, FAILED, CANCELLED, EXPIRED.
    PARTIAL is operationally terminal in v0.1.17 (manual review required).

    No PLACED state. "Submitted but not yet filled" = SUBMITTED with
    last_polled_at set and filled_shares=0.
    """

    INTENT = "INTENT"
    READY_FOR_SUBMISSION = "READY_FOR_SUBMISSION"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"

    @property
    def is_terminal(self) -> bool:
        return self in {
            OrderStatus.FILLED,
            OrderStatus.PARTIAL,
            OrderStatus.FAILED,
            OrderStatus.CANCELLED,
            OrderStatus.EXPIRED,
        }

    @property
    def is_in_flight(self) -> bool:
        return self in {
            OrderStatus.INTENT,
            OrderStatus.READY_FOR_SUBMISSION,
            OrderStatus.SUBMITTED,
        }


class OrderSide(str, Enum):
    """Canonical side representation.

    Uppercase per financial system convention (FIX protocol, broker APIs).
    All Helios callers MUST use these constants; lowercase string literals
    will fail the orders.side CHECK constraint at the DB layer.

    Repository layer does NOT normalize side strings. Caller-side enum use
    is enforced by domain boundary contract.
    """

    BUY = "BUY"
    SELL = "SELL"


class FailureType(str, Enum):
    """Classification of FAILED orders for reconcile strategy.

    TRANSPORT: broker reachability unknown. Order MAY have been received
        despite client-side error. requires_broker_verification=True.

    BROKER_REJECT: broker explicitly rejected (insufficient balance,
        invalid symbol, market closed, pre-trade validation, etc.).
        Terminal; no verification needed.
    """

    TRANSPORT = "transport"
    BROKER_REJECT = "broker_reject"

    @property
    def requires_broker_verification(self) -> bool:
        return self is FailureType.TRANSPORT


# ─────────────────────────────────────────────────────────────────────────────
# Result type
# ─────────────────────────────────────────────────────────────────────────────


class OrderLot(str, Enum):
    """Stock order lot type (Shioaji StockOrderLot proxy).

    Common: 整股 (1 lot = SHARES_PER_LOT shares).
        Broker deal.quantity unit: LOTS.
        LiveBroker boundary normalization: × SHARES_PER_LOT to convert
        to canonical share-equivalent for internal accounting.
    IntradayOdd: 盤中零股 (1-999 shares, < 1 lot).
        Broker deal.quantity unit: SHARES.
        LiveBroker boundary normalization: pass-through.
        Reserved for v0.1.17; NOT IMPLEMENTED in v0.1.16 v2.1.

    Design invariant (FROZEN, v0.1.16 v2.1):
        "Broker adapters may expose broker-native quantity semantics,
         but all persisted execution accounting inside Helios must use
         canonical share-equivalent units."

    LiveBroker._submit asserts order_lot is Common at the boundary
    normalization step. Adding IntradayOdd here without implementing
    the corresponding path will trigger the assertion at runtime.
    """

    Common = "Common"
    # IntradayOdd = "IntradayOdd"  # v0.1.17 — DO NOT uncomment until path is implemented.


@dataclass
class OrderSubmissionResult:
    """Outcome of a single submit_buy / submit_sell call.

    REPLACES FillResult (deprecated in v0.1.16).

    UNIT-BEARING FIELD NAMES (read before using):
      requested_lots: lot count (1 lot = SHARES_PER_LOT shares)
      filled_shares: actual share count from broker deals

    `success` means "API call did not raise". It is NOT a fill confirmation.
    `position_opened` is the ONLY signal callers should use to mutate positions.
    `is_pending` indicates in-flight (reconcile will resolve).

    PARTIAL fills do NOT open positions in v0.1.16 (operator review).
    position_opened is False for PARTIAL.

    Fields:
      success:        API call did not raise
      order_id:       Helios journal order_id (always present)
      status:         current state (OrderStatus)
      side:           OrderSide
      requested_lots: lots submitted (Common lot units)
      filled_shares:  shares actually filled (0 for placed-but-unfilled)
      avg_fill_price: VWAP of fills; None if no fills observed
      limit_price:    TWD per share submitted; None for pre-guard-fail orders
      notional:       limit_price * requested_lots * SHARES_PER_LOT (TWD)
      commission:     transaction cost (TWD); 0 if no fills
      tax:            sell tax (TWD); 0 for buy or no fills
      fill_date:      expected execution date (T+1 trading day)
      signal_id:      upstream signal reference
      broker:         broker tag
      broker_order_id: broker-assigned ID; None until accepted (empty
                      string from broker is normalized to None)
      failure_type:   set iff status=FAILED
      error_code:     structured failure code
      error_message:  human-readable detail
      submitted_at:   set when status reaches SUBMITTED
      polled_at:      set when update_status was called
    """

    # Required (always populated, even for failures)
    success: bool
    order_id: str
    status: OrderStatus
    side: OrderSide
    symbol: str
    requested_lots: int                   # UNIT: lots
    fill_date: date_type

    # Fill state
    filled_shares: int = 0                # UNIT: shares (NOT lots)
    avg_fill_price: float | None = None

    # Trade specification
    limit_price: float | None = None
    notional: float = 0.0                  # TWD: limit_price × requested_lots × SHARES_PER_LOT
    commission: float = 0.0
    tax: float = 0.0

    # Audit / reconcile
    signal_id: str | None = None
    broker: str | None = None
    broker_order_id: str | None = None

    # Failure metadata
    failure_type: FailureType | None = None
    error_code: str | None = None
    error_message: str | None = None

    # Operational timestamps
    submitted_at: datetime | None = None
    polled_at: datetime | None = None

    # Optional extras for forward compat (not persisted as columns)
    metadata: dict = field(default_factory=dict)

    # ── Derived properties — caller-facing API for decisions ────────────────

    @property
    def requested_shares(self) -> int:
        """Helper: requested_lots converted to shares.

        Use this whenever comparing against filled_shares to avoid unit
        confusion. Equivalent to `requested_lots * SHARES_PER_LOT`.
        """
        return self.requested_lots * SHARES_PER_LOT

    @property
    def position_opened(self) -> bool:
        """Whether this submission should result in a position record.

        v0.1.16 policy: only fully-filled orders open positions.

          - FILLED with filled_shares == requested_shares → True
          - PARTIAL → False (operator review required)
          - INTENT / SUBMITTED / FAILED / CANCELLED / EXPIRED → False

        This is the ONLY property callers should check before writing
        positions. Do not reimplement.

        v2 fix (K-P0-1): comparison uses share-equivalent unit. Previously
        compared filled_qty (shares) against requested_qty (lots), which
        triggered position_opened=True for any single-share fill.
        """
        return (
            self.status is OrderStatus.FILLED
            and self.filled_shares == self.requested_shares
            and self.filled_shares > 0
        )

    @property
    def is_pending(self) -> bool:
        """Whether the order is in-flight (not yet terminal)."""
        return self.status.is_in_flight

    @property
    def is_polled_but_unfilled(self) -> bool:
        """Equivalent to legacy 'placed' semantic. SUBMITTED + polled +
        no fills observed. For Telegram messaging only."""
        return (
            self.status is OrderStatus.SUBMITTED
            and self.polled_at is not None
            and self.filled_shares == 0
        )

    @property
    def requires_broker_verification(self) -> bool:
        """Whether reconcile must query broker to resolve this order
        (typically FAILED.transport)."""
        return (
            self.status is OrderStatus.FAILED
            and self.failure_type is FailureType.TRANSPORT
        )

    # ── Validation ─────────────────────────────────────────────────────────

    def __post_init__(self) -> None:
        """Validate domain invariants at construction.

        Mirrors DB CHECK constraints so application-layer bugs fail at
        result construction rather than at INSERT time.

        v2 fix (K-P0-2): PARTIAL invariant now compares filled_shares
        against requested_shares (share-equivalent), not against
        requested_lots directly.
        """
        # Invariant 1: requested_lots positive
        if self.requested_lots <= 0:
            raise ValueError(
                f"OrderSubmissionResult invariant: requested_lots must be "
                f"positive, got {self.requested_lots}"
            )

        # Invariant 2: filled_shares non-negative
        if self.filled_shares < 0:
            raise ValueError(
                f"OrderSubmissionResult invariant: filled_shares must be "
                f"non-negative, got {self.filled_shares}"
            )

        # Invariant 3: status/fill consistency (UNIT-AWARE)
        if self.status is OrderStatus.FILLED:
            if self.filled_shares != self.requested_shares:
                raise ValueError(
                    f"OrderSubmissionResult invariant: FILLED requires "
                    f"filled_shares ({self.filled_shares}) == "
                    f"requested_shares ({self.requested_shares}; "
                    f"= requested_lots {self.requested_lots} × {SHARES_PER_LOT})"
                )
        elif self.status is OrderStatus.PARTIAL:
            if not (0 < self.filled_shares < self.requested_shares):
                raise ValueError(
                    f"OrderSubmissionResult invariant: PARTIAL requires "
                    f"0 < filled_shares ({self.filled_shares}) < "
                    f"requested_shares ({self.requested_shares}; "
                    f"= requested_lots {self.requested_lots} × {SHARES_PER_LOT})"
                )

        # Invariant 4: FAILED <=> failure_type set
        if self.status is OrderStatus.FAILED:
            if self.failure_type is None:
                raise ValueError(
                    "OrderSubmissionResult invariant: FAILED requires "
                    "failure_type to be set"
                )
        else:
            if self.failure_type is not None:
                raise ValueError(
                    f"OrderSubmissionResult invariant: failure_type set "
                    f"({self.failure_type}) but status is {self.status} "
                    f"(must be FAILED)"
                )
