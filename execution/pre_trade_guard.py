# execution/pre_trade_guard.py
"""Pre-trade safety checks — v0.1.16 (post-review v2).

Sanity layer between caller (LiveBroker._submit) and broker. Refuses
orders that violate operational guard-rails, regardless of strategy or
upstream signal validity.

v2 changes from v1 (per advisor review):
  - check_order accepts notional directly (caller-computed) instead of
    deriving from limit_price * requested_qty (which was unit-buggy and
    factor-of-1000 wrong; see K-P0-1).
  - check_daily_order_count and check_daily_notional accept
    exclude_order_id so they don't count the currently-being-evaluated
    intent against itself (C-P0-2 off-by-one fix).
  - Documented SUBMITTED notional inclusion: cap measures CAPITAL
    COMMITMENT, not just fills. SUBMITTED at broker is committed.

Design:
  - Hard-fail on guard violation (raise + Telegram alert)
  - Configurable thresholds via PreTradeGuard dataclass
  - Reads from order journal for daily aggregates (single source of truth)
  - NO unit conversion here — notional must be passed pre-computed in
    consistent units (TWD)

Version: v0.1.16 (2026-05-24, v2)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from execution.order_types import OrderSide
from storage import order_journal
from utils.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Guard configuration
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PreTradeGuard:
    """Pre-trade sanity check configuration.

    PRODUCTION DEFAULTS — these are the values to use when live trading
    is enabled. For week-1 sim smoke test, use PreTradeGuard.sim_relaxed()
    (see classmethod below).

    All TWD amounts.

    Decision 2 (advisor review): week-1 sim threshold is intentionally
    higher to let smoke test exercise the full execution chain. Without
    relaxation, ANY Common lot order on a typical TWD-priced stock
    (e.g. 2330 @ 600 TWD → 600,000 TWD per lot) would fail the 5,000 TWD
    per-order cap and the test would only validate "guard rejects".
    """

    # Daily caps
    max_daily_orders: int = 3
    max_daily_notional: float = 50_000.0

    # Per-order cap
    max_order_notional: float = 5_000.0

    # Price range (fraction of reference price)
    price_range_min_frac: float = 0.5
    price_range_max_frac: float = 1.5

    @classmethod
    def sim_relaxed(cls) -> "PreTradeGuard":
        """Week-1 sim smoke test thresholds.

        Decision 2: relaxes max_order_notional to 1M and max_daily_notional
        to 3M so typical Common lot orders pass the guard and the full
        execution chain (journal → place_order → poll → reconcile) can be
        exercised end-to-end in sim.

        MUST be reverted to production defaults before live_trading_enabled=True.
        See execution_model.md §6 for production deployment checklist.
        """
        return cls(
            max_daily_orders=20,
            max_daily_notional=15_000_000.0,
            max_order_notional=5_000_000.0,
            price_range_min_frac=0.5,
            price_range_max_frac=1.5,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────────


class GuardViolation(Exception):
    """Raised when a pre-trade check fails. Carries structured reason."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message


# ─────────────────────────────────────────────────────────────────────────────
# Individual checks
# ─────────────────────────────────────────────────────────────────────────────


def check_price_sanity(price: float | None) -> None:
    """Verify price is a finite positive number."""
    if price is None:
        raise GuardViolation(
            "pre_trade_guard_price_none",
            "limit price is None (signal generator did not produce a price)",
        )
    if not math.isfinite(price):
        raise GuardViolation(
            "pre_trade_guard_price_nonfinite",
            f"limit price is not finite: {price}",
        )
    if price <= 0:
        raise GuardViolation(
            "pre_trade_guard_price_nonpositive",
            f"limit price must be positive, got {price}",
        )


def check_price_range(
    price: float,
    *,
    reference_price: float | None,
    guard: PreTradeGuard,
) -> None:
    """Verify price is within [min_frac, max_frac] * reference_price."""
    if reference_price is None or not math.isfinite(reference_price):
        logger.warning(
            "pre_trade_guard_price_range_skipped_no_reference",
            price=price,
        )
        return
    if reference_price <= 0:
        logger.warning(
            "pre_trade_guard_price_range_skipped_invalid_reference",
            price=price, reference=reference_price,
        )
        return

    lo = guard.price_range_min_frac * reference_price
    hi = guard.price_range_max_frac * reference_price
    if not (lo <= price <= hi):
        raise GuardViolation(
            "pre_trade_guard_price_out_of_range",
            f"price {price:.2f} outside sanity range "
            f"[{lo:.2f}, {hi:.2f}] (ref={reference_price:.2f}, "
            f"fracs=[{guard.price_range_min_frac}, {guard.price_range_max_frac}])",
        )


def check_order_notional(
    notional: float,
    *,
    guard: PreTradeGuard,
) -> None:
    """Verify single-order notional within max_order_notional.

    Notional is caller-computed in TWD: limit_price * requested_lots *
    SHARES_PER_LOT. Commission/tax not included by design — those are
    second-order (~0.15%) and not the kind of safety the per-order cap
    addresses.
    """
    if notional > guard.max_order_notional:
        raise GuardViolation(
            "pre_trade_guard_order_notional_exceeded",
            f"order notional {notional:.0f} exceeds per-order cap "
            f"{guard.max_order_notional:.0f}",
        )


def check_daily_order_count(
    *,
    guard: PreTradeGuard,
    now: datetime | None = None,
    exclude_order_id: str | None = None,
) -> None:
    """Verify today's order count below daily cap.

    Counts ALL orders (including FAILED) to prevent retry storms.

    v2 (C-P0-2): exclude_order_id excludes the currently-evaluating order
    so the check is "would this PUSH us over" rather than "are we already
    at or over". Without this, with cap=3:
      - Order 1: count=0, record_intent → count=1, check passes (1 <= 3)
      - Order 2: count=1, record_intent → count=2, check passes (2 <= 3)
      - Order 3: count=2, record_intent → count=3, check FAILS (3 > 3) ❌
    With this fix:
      - Order 3: count=3 inclusive, exclude self → count=2, check passes (2 < 3)
    """
    today_count = order_journal.count_today_orders(
        now=now, exclude_order_id=exclude_order_id,
    )
    if today_count >= guard.max_daily_orders:
        raise GuardViolation(
            "pre_trade_guard_daily_order_cap_exceeded",
            f"daily order count {today_count} (excluding current) >= "
            f"cap {guard.max_daily_orders}",
        )


def check_daily_notional(
    notional: float,
    *,
    guard: PreTradeGuard,
    now: datetime | None = None,
    exclude_order_id: str | None = None,
) -> None:
    """Verify today's notional + new order's notional within daily cap.

    Excludes FAILED orders (no committed capital). INCLUDES SUBMITTED
    orders — the cap is on COMMITTED CAPITAL, not fills. A SUBMITTED
    order has reserved buying power at the broker.

    v2 (C-P0-2): exclude_order_id excludes the currently-evaluating order
    from the running sum (symmetric with check_daily_order_count).
    """
    today_notional = order_journal.sum_today_notional(
        now=now, exclude_failed=True, exclude_order_id=exclude_order_id,
    )
    if today_notional + notional > guard.max_daily_notional:
        raise GuardViolation(
            "pre_trade_guard_daily_notional_exceeded",
            f"daily notional {today_notional:.0f} (excl current) + "
            f"new {notional:.0f} = {today_notional + notional:.0f} "
            f"exceeds cap {guard.max_daily_notional:.0f}",
        )


def check_symbol_whitelist(
    symbol: str,
    *,
    whitelist: frozenset[str] | None,
) -> None:
    """Verify symbol in whitelist (if configured)."""
    if whitelist is None:
        return
    if symbol not in whitelist:
        raise GuardViolation(
            "pre_trade_guard_symbol_not_whitelisted",
            f"symbol {symbol!r} not in pre-trade whitelist",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Composite check (called from broker._submit)
# ─────────────────────────────────────────────────────────────────────────────


def check_order(
    *,
    symbol: str,
    side: OrderSide,
    limit_price: float | None,
    notional: float,
    reference_price: float | None,
    guard: PreTradeGuard,
    whitelist: frozenset[str] | None = None,
    now: datetime | None = None,
    exclude_order_id: str | None = None,
) -> None:
    """Run all pre-trade checks in order. Raises GuardViolation on first failure.

    v2 changes:
      - notional is now a parameter (caller pre-computes in TWD), not
        derived from limit_price * requested_qty. This decouples the
        guard from quantity-unit conventions.
      - exclude_order_id passed through to daily count/notional checks.

    Args:
        symbol:        TWSE stock code
        side:          OrderSide
        limit_price:   TWD per share
        notional:      pre-computed total notional in TWD
                       (= limit_price * requested_lots * SHARES_PER_LOT)
        reference_price: prev_close or similar reference for price range check
        guard:         configuration
        whitelist:     optional set of allowed symbols
        now:           reference time for daily aggregates
        exclude_order_id: order to exclude from daily aggregates (the
                          currently-evaluating intent's own row)

    Order of checks (cheap/localized first):
      symbol → price sanity → price range → order notional → daily count
      → daily notional
    """
    # Cheap, localized checks first
    check_symbol_whitelist(symbol, whitelist=whitelist)
    check_price_sanity(limit_price)
    assert limit_price is not None  # type narrowing after check_price_sanity
    check_price_range(limit_price, reference_price=reference_price, guard=guard)

    check_order_notional(notional, guard=guard)

    # Daily aggregates (DB queries) — last because most expensive
    check_daily_order_count(
        guard=guard, now=now, exclude_order_id=exclude_order_id,
    )
    check_daily_notional(
        notional, guard=guard, now=now, exclude_order_id=exclude_order_id,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Formatting helper for Telegram alerts
# ─────────────────────────────────────────────────────────────────────────────


def format_violation_alert(
    violation: GuardViolation,
    *,
    symbol: str,
    side: OrderSide,
    limit_price: float | None,
    requested_lots: int,
) -> str:
    """Format guard violation as Telegram critical alert.

    v2: parameter renamed requested_qty → requested_lots for unit clarity.
    """
    return (
        f"🚨🚨🚨 PRE-TRADE GUARD BLOCKED 🚨🚨🚨\n"
        f"Symbol: {symbol}\n"
        f"Side: {side.value}\n"
        f"Lots: {requested_lots}\n"
        f"Price: {limit_price if limit_price is not None else 'N/A'}\n"
        f"Code: {violation.error_code}\n"
        f"Detail: {violation.message}"
    )
