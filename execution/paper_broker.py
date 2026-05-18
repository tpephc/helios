# execution/paper_broker.py
"""PaperBroker — simulated fills with台股 asymmetric cost model.

ARCHITECTURE §6.5 state machine: PaperBroker provides the fill operations
that drive OPENING→OPEN, OPEN/CLOSING→CLOSED transitions.

Per review #2 (2026-05-17): cost model explicit + fill_model configurable.

Fill model (v0.1.14.3):
  FILL_MODEL = "next_open" — signal at close[T], fill at open[T+1].
  Backed by `daily_price_adj.adj_open`, populated by the dividend-adjustment
  pipeline alongside adj_close.

  Prior versions (≤ v0.1.14.2-c3.1) used adj_close[T+1] as a proxy with a
  comment claiming "we don't have open price in DB" — that comment was
  stale; adj_open has been in the schema since v0.1.4. v0.1.14.3 closes
  that gap.

Liquidity sanity (v0.1.14.3):
  MAX_FILL_RATIO = 0.5% of fill-day raw volume. Above that, the fill is
  refused (FillResult(success=False, error="insufficient_liquidity")) on
  the assumption that the actual market impact would exceed our cost
  model's slippage budget. This is a paper-trade safety rail, not a real
  market microstructure model — v0.1.15 broker integration will replace it
  with a proper pre-trade ADV check.

Cost model (asymmetric — Taiwan stocks):
  Buy:
    fill_price = ref_price × (1 + slippage)
    pay: shares × fill_price × (1 + commission)
    commission cost: shares × fill_price × commission
    slippage cost:   shares × ref_price × slippage
  Sell:
    fill_price = ref_price × (1 - slippage)
    receive: shares × fill_price × (1 - commission - tax)
    commission cost: shares × fill_price × commission
    tax cost:        shares × fill_price × tax
    slippage cost:   shares × ref_price × slippage

NOT implemented (deliberately):
  - Order book / partial fills
  - Limit orders (market-on-open assumed)
  - After-hours (台股 no after-hours)
  - Multi-broker reconciliation

Version: v0.1.1 (2026-05-17 — v0.1.14.3 fill realism + liquidity sanity)
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime

from data.database import connect
from utils.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────
# Cost model
# ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TransactionFees:
    """Per-side rates as fractions (not percent).

    永豐金 retail rates (no negotiation):
      commission 0.1425% per side (buy + sell each)
      sell tax   0.3% (證交稅, only sell)

    Slippage assumption: 0.05~0.1% per side for medium-cap TWSE liquid names.
    """
    commission_rate: float = 0.001425
    sell_tax_rate: float = 0.003
    slippage_rate: float = 0.001  # 0.1% per side (conservative)


DEFAULT_TW_FEES = TransactionFees()


# ─────────────────────────────────────────────────────────────
# Result
# ─────────────────────────────────────────────────────────────


@dataclass
class FillResult:
    """Outcome of a submit_buy / submit_sell call."""
    success: bool
    order_id: str | None
    fill_date: date_type
    fill_price: float | None         # post-slippage price actually used
    ref_price: float | None          # pre-slippage reference (the adj_open used)
    shares: int                      # shares actually traded
    notional: float                  # shares × fill_price (gross trade value)
    commission: float
    tax: float                       # 0 for buy, applicable rate for sell
    slippage_cost: float
    total_cost: float                # commission + tax + slippage_cost
    cash_delta: float                # signed: -outflow for buy, +inflow for sell
    error: str | None = None
    # v0.1.14.3.1 — structured operational metadata. The string-only `error`
    # field is sufficient for human reading; these fields are for machine-
    # readable observation (threshold tuning, sizing analysis, regime
    # correlation in run_summary aggregations).
    execution_reason: str = "filled"          # "filled" on success; failure code otherwise
    participation_rate: float | None = None   # shares / fill-day raw volume (None if unknown)


# ─────────────────────────────────────────────────────────────
# Broker
# ─────────────────────────────────────────────────────────────


class PaperBroker:
    """Synchronous paper broker. submit_buy/submit_sell return FillResult.

    Fill model: read adj_open for fill_date from daily_price_adj.
    For v0.1, fill_date should be a known trading day with data present.
    """

    FILL_MODEL = "next_open"
    MAX_FILL_RATIO = 0.005  # v0.1.14.3: refuse fills > 0.5% of fill-day volume

    def __init__(
        self,
        fees: TransactionFees | None = None,
        broker_name: str = "paper",
    ) -> None:
        self.fees = fees if fees is not None else DEFAULT_TW_FEES
        self.broker_name = broker_name

    # ── Public API ─────────────────────────────────────────

    def submit_buy(
        self, *,
        symbol: str,
        target_notional: float,
        fill_date: date_type,
        signal_id: str | None = None,
    ) -> FillResult:
        """Buy as many shares as target_notional affords (in lots of 1).

        台股: integer shares; smallest unit = 1 share for our purposes
        (1 lot = 1000 shares in reality, but we use 1-share resolution
        for paper trade flexibility).
        """
        data = self._lookup_fill_data(symbol, fill_date)
        if data is None:
            return self._fail(symbol, fill_date, "no_price_data", "buy", signal_id)
        ref_price, volume = data
        if ref_price <= 0:
            return self._fail(symbol, fill_date, "invalid_price", "buy", signal_id)

        fill_price = ref_price * (1.0 + self.fees.slippage_rate)
        per_share_buy_cost = fill_price * (1.0 + self.fees.commission_rate)
        if per_share_buy_cost <= 0:
            return self._fail(symbol, fill_date, "invalid_price", "buy", signal_id)
        shares = int(target_notional // per_share_buy_cost)
        if shares <= 0:
            return self._fail(
                symbol, fill_date, "insufficient_notional_for_one_share",
                "buy", signal_id,
            )

        # v0.1.14.3: liquidity sanity gate (after share-count is known)
        liq_err = self._liquidity_check(symbol, fill_date, shares, volume, "buy", signal_id)
        if liq_err is not None:
            return liq_err

        notional = shares * fill_price
        commission = notional * self.fees.commission_rate
        slippage_cost = shares * ref_price * self.fees.slippage_rate
        total_cost = commission + slippage_cost  # no tax on buy
        cash_out = notional + commission  # cash actually leaving account
        participation_rate = shares / volume if volume > 0 else None

        order_id = self._record_order(
            signal_id=signal_id, symbol=symbol, side="buy",
            quantity=shares, price=fill_price, status="filled",
            commission=commission, tax=0.0,
        )

        result = FillResult(
            success=True, order_id=order_id,
            fill_date=fill_date, fill_price=fill_price, ref_price=ref_price,
            shares=shares, notional=notional,
            commission=commission, tax=0.0,
            slippage_cost=slippage_cost, total_cost=total_cost,
            cash_delta=-cash_out,
            execution_reason="filled", participation_rate=participation_rate,
        )
        logger.info(
            "paper_buy_filled", symbol=symbol, shares=shares,
            ref_price=ref_price, fill_price=fill_price,
            commission=commission, slippage=slippage_cost,
            participation_rate=participation_rate, order_id=order_id,
        )
        return result

    def submit_sell(
        self, *,
        symbol: str,
        shares: int,
        fill_date: date_type,
        signal_id: str | None = None,
    ) -> FillResult:
        """Sell exact share count."""
        if shares <= 0:
            return self._fail(symbol, fill_date, "non_positive_shares", "sell", signal_id)
        data = self._lookup_fill_data(symbol, fill_date)
        if data is None:
            return self._fail(symbol, fill_date, "no_price_data", "sell", signal_id)
        ref_price, volume = data
        if ref_price <= 0:
            return self._fail(symbol, fill_date, "invalid_price", "sell", signal_id)

        # v0.1.14.3: liquidity sanity gate (shares known up front for sell)
        liq_err = self._liquidity_check(symbol, fill_date, shares, volume, "sell", signal_id)
        if liq_err is not None:
            return liq_err

        fill_price = ref_price * (1.0 - self.fees.slippage_rate)
        notional = shares * fill_price
        commission = notional * self.fees.commission_rate
        tax = notional * self.fees.sell_tax_rate
        slippage_cost = shares * ref_price * self.fees.slippage_rate
        total_cost = commission + tax + slippage_cost
        cash_in = notional - commission - tax  # cash actually arriving
        participation_rate = shares / volume if volume > 0 else None

        order_id = self._record_order(
            signal_id=signal_id, symbol=symbol, side="sell",
            quantity=shares, price=fill_price, status="filled",
            commission=commission, tax=tax,
        )

        result = FillResult(
            success=True, order_id=order_id,
            fill_date=fill_date, fill_price=fill_price, ref_price=ref_price,
            shares=shares, notional=notional,
            commission=commission, tax=tax,
            slippage_cost=slippage_cost, total_cost=total_cost,
            cash_delta=+cash_in,
            execution_reason="filled", participation_rate=participation_rate,
        )
        logger.info(
            "paper_sell_filled", symbol=symbol, shares=shares,
            ref_price=ref_price, fill_price=fill_price,
            commission=commission, tax=tax, slippage=slippage_cost,
            participation_rate=participation_rate, order_id=order_id,
        )
        return result

    # ── Internals ──────────────────────────────────────────

    def _lookup_fill_data(
        self, symbol: str, d: date_type,
    ) -> tuple[float, int] | None:
        """Return (adj_open, volume) at fill day, or None if either missing.

        v0.1.14.3: switched from adj_close (stale comment fallback) to adj_open,
        the actual next-day-open semantic. Both columns have been populated by
        the dividend-adjustment pipeline since v0.1.4 — there was no schema gap,
        just a query that didn't use the right column.
        """
        with connect(read_only=True) as conn:
            row = conn.execute(
                "SELECT adj_open, volume FROM daily_price_adj "
                "WHERE stock_id = ? AND date = ?",
                [symbol, d],
            ).fetchone()
        if not row:
            return None
        open_px, vol = row
        if open_px is None or vol is None:
            return None
        return float(open_px), int(vol)

    def _liquidity_check(
        self, symbol: str, fill_date: date_type, shares: int, volume: int,
        side: str, signal_id: str | None,
    ) -> FillResult | None:
        """Return FillResult(success=False) if liquidity gate trips, else None.

        v0.1.14.3 paper-trade safety rail: refuse fills that would exceed
        MAX_FILL_RATIO (default 0.5%) of fill-day raw volume. Volume == 0 is
        treated as definitionally insufficient.

        v0.1.14.3.1: on rejection, populate participation_rate in the FillResult
        so run_summary can aggregate breach distributions across the observation
        window (e.g. "5-day median rejected-participation").
        """
        if volume <= 0:
            return self._fail(
                symbol, fill_date, "no_volume_data", side, signal_id,
            )
        ratio = shares / volume
        if ratio > self.MAX_FILL_RATIO:
            logger.warning(
                "paper_fill_blocked_liquidity",
                symbol=symbol, side=side, fill_date=str(fill_date),
                shares=shares, volume=volume, ratio=ratio,
                max_ratio=self.MAX_FILL_RATIO, signal_id=signal_id,
            )
            return self._fail(
                symbol, fill_date, "insufficient_liquidity", side, signal_id,
                participation_rate=ratio,
            )
        return None

    def _record_order(
        self, *,
        signal_id: str | None, symbol: str, side: str,
        quantity: int, price: float, status: str,
        commission: float, tax: float,
    ) -> str:
        order_id = f"ord_{uuid.uuid4().hex[:12]}"
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO orders (
                    order_id, signal_id, timestamp, symbol, side, order_type,
                    quantity, price, status, filled_qty, avg_price,
                    commission, tax, broker
                ) VALUES (?, ?, ?, ?, ?, 'market', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    order_id, signal_id, datetime.now(), symbol, side,
                    quantity, price, status,
                    quantity if status == "filled" else 0,
                    price if status == "filled" else None,
                    commission, tax, self.broker_name,
                ],
            )
        return order_id

    def _fail(
        self, symbol: str, fill_date: date_type, reason: str,
        side: str, signal_id: str | None,
        participation_rate: float | None = None,
    ) -> FillResult:
        logger.warning(
            "paper_fill_failed", symbol=symbol, side=side,
            fill_date=str(fill_date), reason=reason, signal_id=signal_id,
            participation_rate=participation_rate,
        )
        return FillResult(
            success=False, order_id=None,
            fill_date=fill_date, fill_price=None, ref_price=None,
            shares=0, notional=0.0,
            commission=0.0, tax=0.0, slippage_cost=0.0, total_cost=0.0,
            cash_delta=0.0, error=reason,
            execution_reason=reason, participation_rate=participation_rate,
        )
