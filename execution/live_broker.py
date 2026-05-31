# execution/live_broker.py
"""Shioaji live broker — v0.1.2 (post-review v2).

Changes from v0.1.1 (v0.1.16):
  - Returns OrderSubmissionResult (not FillResult).
  - Persists every state transition to orders journal (crash-safe).
  - Applies PreTradeGuard before placing orders.
  - simulation=False + IntradayOdd path is intentionally disabled.
  - Classifies failures as transport vs broker_reject.
  - Implements BrokerAdapter protocol (for reconcile).

Changes from v2-draft (post-advisor-review v2):
  - K-P0-1 fix: fill comparison uses share-equivalent units consistently.
    requested_lots (lot count) and total_deal_shares (share count from
    deals) are NEVER compared directly. Conversion via SHARES_PER_LOT
    is explicit at the comparison point.
  - C-P0-3 fix: notional is computed once after contract lookup and
    written to journal via update_order_spec; PreTradeGuard receives
    pre-computed notional.
  - C-P0-2 fix: PreTradeGuard receives exclude_order_id so the
    just-recorded INTENT doesn't count against itself.
  - C-P1-6 fix: contract lookup tries TSE and OTC explicitly via
    resolve_stock_contract; previously assumed unqualified access path.
  - K-P1-3 fix (reconcile-side, but adapter shares helpers): side
    normalized via Action enum identity, not string compare.
  - K-P1-5 fix: broker_order_id empty string normalized to None at
    the journal boundary (in order_journal.mark_submitted).

Changes in v0.1.16 v2.1 (2026-05-25 hotfix):
  - Boundary normalization: Shioaji Common-path deal.quantity is LOTS
    (confirmed via Sinotrade docs + live sim repro), not SHARES.
    LiveBroker._submit now × SHARES_PER_LOT at the fill classification
    boundary to convert broker-native lot count into the canonical
    share-equivalent unit used by storage / reconcile / accounting.
  - submit_buy / submit_sell signatures gain `order_lot: OrderLot`
    parameter (default Common). _submit asserts order_lot is Common at
    the boundary, preventing v0.1.17 IntradayOdd path from silently
    over-counting fills by SHARES_PER_LOT.
  - K-P0-1 share-equivalent invariant (filled_shares vs requested_shares)
    remains intact — boundary normalization preserves the share-equivalent
    comparison semantics throughout the function.
  - D-P0-2 / decision 3a: implements BrokerAdapter protocol via public
    login_session, fetch_trades, fetch_holdings methods. reconcile no
    longer calls _login directly.
  - D-P2-e: _STATUS_POLL_SLEEP configurable (default raised to 5.0s).

Changes in v0.1.16 v2.1 + P-obs-1 (2026-05-26):
  - Adds info-level raw payload observation logging at 3 Shioaji SDK
    boundary sites (_submit, fetch_trades, fetch_holdings) to
    discharge [ASSUMED] semantic invariants documented in
    docs/decision_records/shioaji_semantic_observation_2026_05_26.md.
  - Dual-logging strategy on semantic-critical fields (price /
    quantity / ts): raw value + _safe_repr + _safe_type. Raw exposes
    structlog's runtime serialization behavior (Decimal? numpy
    scalar? SDK wrapper?); repr+type are evidence fallback if raw
    serialization surprises.
  - Non-critical fields (trade.status, trade.order, full deal repr)
    use _safe_repr only — these are container objects whose internal
    structure is observed via the critical fields they contain.
  - Local instrumentation helpers (_safe_repr / _safe_getattr /
    _safe_type) are deliberately NOT promoted to utils/ — single-use,
    underscore-prefixed, scope-bounded to the 5/26 observation window.
  - Lifecycle: TEMPORARY. Target horizon 5–10 trading days. Removal
    or env-var gating once §5 invariant table in the SSOT doc closes
    the relevant assumed invariants.
  - _resolve_stock_contract NOT instrumented — its [ASSUMED] →
    [OBSERVED] transition completed by v2.1 sim repro across 5
    symbols (§5 SSOT row 2).

UNIT CONVENTION:
  requested_lots: int, Common lot count (1 lot = SHARES_PER_LOT shares)
  total_deal_shares: int, sum of deal.quantity from Shioaji (SHARES)
  Conversion: requested_shares = requested_lots * SHARES_PER_LOT
  Comparisons MUST use share-equivalents.

Version: v0.1.2 (2026-05-26, v2 + P-obs-1)
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import date as date_type
from datetime import datetime
from typing import Any, Iterator
from zoneinfo import ZoneInfo

from config.settings import get_settings
from execution.broker_adapter import BrokerAdapter, BrokerAdapterError
from execution.order_types import (
    OrderLot,
    SHARES_PER_LOT,
    FailureType,
    OrderSide,
    OrderStatus,
    OrderSubmissionResult,
)
from execution.paper_broker import DEFAULT_TW_FEES, TransactionFees
from execution.pre_trade_guard import (
    GuardViolation,
    PreTradeGuard,
    check_order as run_pre_trade_checks,
    format_violation_alert,
)
from storage import order_journal
from utils.logger import get_logger

logger = get_logger(__name__)

TAIPEI_TZ = ZoneInfo("Asia/Taipei")


# ─── P-obs-1 local instrumentation helpers ─────────────────────────────
# Lifecycle: TEMPORARY. Tied to the 5/26 observation window. See
# docs/decision_records/shioaji_semantic_observation_2026_05_26.md.
#
# Underscore prefix is deliberate — these are NOT reusable infra; do
# not import out of this module. If a second observation site appears
# elsewhere, copy-paste rather than promote to utils/, until v0.1.17
# logging pipeline refactor decides the right home.
#
# Discipline: observation logging is being added to a live execution
# path that already had two semantic bugs (v2 → v2.1). Any exception
# escaping these helpers and killing _submit / fetch_trades /
# fetch_holdings would be strictly worse than no logging. Hence the
# bare-except defensive layer.


def _safe_repr(obj: object) -> str:
    """repr() that never raises. Returns sentinel on failure."""
    try:
        return repr(obj)
    except Exception as exc:  # defensive logging only
        return f"<repr_failed:{type(exc).__name__}>"


def _safe_type(obj: object) -> str:
    """type(obj).__name__ that never raises."""
    try:
        return type(obj).__name__
    except Exception:  # defensive logging only
        return "<unknown>"


def _safe_getattr(obj: object, attr: str, default: object = None) -> object:
    """getattr that never raises (some SDK objects have __getattr__
    that can raise on missing fields)."""
    try:
        return getattr(obj, attr, default)
    except Exception:  # defensive logging only
        return default


class LiveBrokerError(Exception):
    """Live broker configuration or runtime error."""


def _resolve_stock_contract(api: Any, symbol: str) -> Any:
    """Resolve a Shioaji contract for a TWSE/OTC symbol.

    v2 (C-P1-6): explicitly tries TSE first then OTC. Previously used
    bare `api.Contracts.Stocks[symbol]` which works for some symbols
    but is unreliable for OTC (上櫃) and certain ETFs.

    v2.1 (2026-05-25, hotfix): switched from ``symbol in tse`` membership
    check to ``tse.get(symbol)`` lookup. Shioaji's StreamMultiContract
    namespace does NOT implement ``__contains__``; Python falls back to
    ``__iter__`` linear scan which iterates ``Stock`` objects (not keys),
    so ``"4919" in tse`` is permanently False regardless of whether 4919
    exists. ``tse.get(symbol)`` uses the SDK's intended key-lookup path
    (returns None on miss, no KeyError). Verified via repro 2026-05-25
    against 5 symbols (6139, 4919, 2890, 2330, 2412): all return correct
    Contract via ``.get()`` but ``in`` returns False for all.

    Returns the contract or None if not found in either market.
    """
    try:
        tse = api.Contracts.Stocks.TSE
        contract = tse.get(symbol)
        if contract is not None:
            return contract
    except Exception as exc:  # noqa: BLE001 - SDK-level call surface unknown
        logger.warning(
            "contract_lookup_tse_failed", symbol=symbol, error=str(exc),
        )
    try:
        otc = api.Contracts.Stocks.OTC
        contract = otc.get(symbol)
        if contract is not None:
            return contract
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "contract_lookup_otc_failed", symbol=symbol, error=str(exc),
        )
    return None


def _normalize_action_to_side(action: Any) -> str:
    """Normalize Shioaji Action enum (or string) to canonical 'BUY'/'SELL'.

    v2 (K-P1-3): Shioaji's action field can be the Action enum
    (Action.Buy / Action.Sell) or its string representation depending on
    SDK version. Using `is Action.Buy` is most robust when Action is
    importable; fall back to string compare on the enum's value.
    """
    try:
        from shioaji.constant import Action
        if action is Action.Buy:
            return "BUY"
        if action is Action.Sell:
            return "SELL"
    except ImportError:
        pass

    # Fallback: string representation comparison
    text = str(action)
    if "Buy" in text:
        return "BUY"
    if "Sell" in text:
        return "SELL"
    # Unknown action — log and default to BUY (caller should detect
    # via reconcile axis)
    logger.error("unknown_broker_action", action=repr(action))
    return "BUY"


class LiveBroker:
    """Shioaji-backed broker. submit_buy/sell auto-execute and notify.

    Implements BrokerAdapter protocol (login_session / fetch_trades /
    fetch_holdings) for reconcile use.

    v0.1.16: Common lot only. IntradayOdd path is explicitly disabled.
    """

    BROKER_PAPER = "paper"
    BROKER_SIM = "shioaji_sim"
    BROKER_LIVE = "shioaji_live"

    # v2 (D-P2-e): status poll sleep is configurable; default 5s
    # (was 2s in v1, which is too short — Shioaji sometimes takes 3-4s
    # to populate deals after place_order).
    DEFAULT_POLL_SLEEP_SEC: float = 5.0

    def __init__(
        self,
        bot: Any = None,
        fees: TransactionFees | None = None,
        guard: PreTradeGuard | None = None,
        whitelist: frozenset[str] | None = None,
        poll_sleep_sec: float | None = None,
    ) -> None:
        cfg = get_settings()
        self._simulation = cfg.shioaji_simulation
        self._api_key = (
            cfg.shioaji_api_key.get_secret_value() if cfg.shioaji_api_key else ""
        )
        self._secret_key = (
            cfg.shioaji_secret_key.get_secret_value()
            if cfg.shioaji_secret_key else ""
        )
        self._ca_path = cfg.ca_cert_path or ""
        self._ca_passwd = (
            cfg.ca_password.get_secret_value() if cfg.ca_password else ""
        )
        self.fees = fees or DEFAULT_TW_FEES
        self.bot = bot
        if guard is not None:
            self.guard = guard
        elif self._simulation:
            self.guard = PreTradeGuard.sim_relaxed()
        else:
            self.guard = PreTradeGuard()
        self.whitelist = whitelist
        self.poll_sleep_sec = (
            poll_sleep_sec if poll_sleep_sec is not None
            else self.DEFAULT_POLL_SLEEP_SEC
        )

        # Live trading kill-switch
        self._live_enabled: bool = getattr(cfg, "live_trading_enabled", False)
        if not self._simulation and not self._live_enabled:
            raise LiveBrokerError(
                "Live trading requires LIVE_TRADING_ENABLED=true in .env. "
                "Set SHIOAJI_SIMULATION=true for simulation mode."
            )

        self._broker_tag = self.BROKER_SIM if self._simulation else self.BROKER_LIVE

    # ── Public Submit API ──────────────────────────────────────────────────

    def submit_buy(
        self,
        *,
        symbol: str,
        fill_date: date_type,
        signal_id: str | None = None,
        lots: int = 1,
        order_lot: OrderLot = OrderLot.Common,
    ) -> OrderSubmissionResult:
        """Place a Common-lot buy order. lots is in 整股 units (1 lot = 1000 shares).

        v0.1.16 v2.1: order_lot is reserved for v0.1.17 IntradayOdd expansion.
        Only OrderLot.Common is currently supported; other values trigger
        the boundary-normalization assertion inside _submit.
        """
        return self._submit(
            side=OrderSide.BUY, symbol=symbol, fill_date=fill_date,
            signal_id=signal_id, lots=lots, order_lot=order_lot,
        )

    def submit_sell(
        self,
        *,
        symbol: str,
        fill_date: date_type,
        signal_id: str | None = None,
        lots: int = 1,
        order_lot: OrderLot = OrderLot.Common,
    ) -> OrderSubmissionResult:
        """Place a Common-lot sell order.

        See submit_buy docstring for order_lot semantics.
        """
        return self._submit(
            side=OrderSide.SELL, symbol=symbol, fill_date=fill_date,
            signal_id=signal_id, lots=lots, order_lot=order_lot,
        )

    # ── Core submission flow ───────────────────────────────────────────────

    def _submit(
        self,
        *,
        side: OrderSide,
        symbol: str,
        fill_date: date_type,
        signal_id: str | None,
        lots: int,
        order_lot: OrderLot,
    ) -> OrderSubmissionResult:
        """Unified submission flow (shared between buy and sell).

        v0.1.16 invariant: simulation=False + IntradayOdd is rejected.

        Unit handling (v2 K-P0-1 fix):
          - lots (requested_lots) stays in lot units throughout
          - notional computed once as limit_price * lots * SHARES_PER_LOT
          - filled comparison uses requested_lots * SHARES_PER_LOT vs
            total_deal_shares
        """
        # ── Step 0: kill-switch check ─────────────────────────────────────
        if not self._simulation:
            raise NotImplementedError(
                "Real broker execution is disabled in v0.1.16. "
                "IntradayOdd live execution path is intentionally rejected. "
                "v0.1.17 target: Common lot + ROD after backtest alignment "
                "(see docs/decision_records/v0_1_16_backtest_audit_report.md)."
            )

        requested_lots = lots
        intent_at = datetime.now(tz=TAIPEI_TZ)

        # ── Step 1: record INTENT (notional=0; updated after contract lookup) ──
        order_id = order_journal.record_intent(
            symbol=symbol,
            side=side,
            requested_lots=requested_lots,
            intent_at=intent_at,
            fill_date=fill_date,
            notional=0.0,
            signal_id=signal_id,
            limit_price=None,
            broker=self._broker_tag,
            metadata={
                "lots": requested_lots,
                "shares_per_lot": SHARES_PER_LOT,
                "order_lot": order_lot.value,
            },
        )

        # ── Step 2: shioaji import ────────────────────────────────────────
        try:
            import shioaji as sj
            from shioaji.constant import (
                Action, OrderType, StockOrderCond, StockOrderLot, StockPriceType,
            )
        except ImportError as exc:
            order_journal.mark_failed(
                order_id=order_id,
                failure_type=FailureType.BROKER_REJECT,
                error_code="shioaji_import_failed",
                error_message=str(exc),
            )
            return self._build_failed_result(
                order_id=order_id, symbol=symbol, side=side,
                requested_lots=requested_lots, fill_date=fill_date,
                signal_id=signal_id,
                failure_type=FailureType.BROKER_REJECT,
                error_code="shioaji_import_failed",
                error_message=str(exc),
            )

        # ── Step 3: login (broker call) ───────────────────────────────────
        api = self._login(sj)
        if api is None:
            order_journal.mark_failed(
                order_id=order_id,
                failure_type=FailureType.TRANSPORT,
                error_code="login_failed",
                error_message="Shioaji login returned None",
            )
            return self._build_failed_result(
                order_id=order_id, symbol=symbol, side=side,
                requested_lots=requested_lots, fill_date=fill_date,
                signal_id=signal_id,
                failure_type=FailureType.TRANSPORT,
                error_code="login_failed",
                error_message="Shioaji login returned None",
            )

        try:
            # ── Step 4: resolve contract (broker call) ────────────────────
            contract = _resolve_stock_contract(api, symbol)
            if contract is None:
                order_journal.mark_failed(
                    order_id=order_id,
                    failure_type=FailureType.BROKER_REJECT,
                    error_code="contract_not_found",
                    error_message=(
                        f"no contract for symbol {symbol!r} in TSE or OTC"
                    ),
                )
                return self._build_failed_result(
                    order_id=order_id, symbol=symbol, side=side,
                    requested_lots=requested_lots, fill_date=fill_date,
                    signal_id=signal_id,
                    failure_type=FailureType.BROKER_REJECT,
                    error_code="contract_not_found",
                    error_message=f"no contract for symbol {symbol!r}",
                )

            ref_price = contract.reference

            # ── Step 5: compute notional and write spec to journal ────────
            notional = ref_price * requested_lots * SHARES_PER_LOT
            order_journal.update_order_spec(
                order_id=order_id,
                limit_price=ref_price,
                notional=notional,
            )

            # ── Step 6: pre-trade guard (with self-exclusion) ─────────────
            try:
                run_pre_trade_checks(
                    symbol=symbol, side=side,
                    limit_price=ref_price,
                    notional=notional,
                    reference_price=ref_price,
                    guard=self.guard,
                    whitelist=self.whitelist,
                    exclude_order_id=order_id,
                )
            except GuardViolation as violation:
                self._notify(format_violation_alert(
                    violation,
                    symbol=symbol, side=side,
                    limit_price=ref_price,
                    requested_lots=requested_lots,
                ))
                order_journal.mark_failed(
                    order_id=order_id,
                    failure_type=FailureType.BROKER_REJECT,
                    error_code=violation.error_code,
                    error_message=violation.message,
                )
                return self._build_failed_result(
                    order_id=order_id, symbol=symbol, side=side,
                    requested_lots=requested_lots, fill_date=fill_date,
                    signal_id=signal_id, limit_price=ref_price,
                    notional=notional,
                    failure_type=FailureType.BROKER_REJECT,
                    error_code=violation.error_code,
                    error_message=violation.message,
                )

            # ── Step 7: place_order (broker call) ─────────────────────────
            action = Action.Buy if side is OrderSide.BUY else Action.Sell
            order = sj.order.StockOrder(
                action=action,
                price=ref_price,
                quantity=requested_lots,           # Common lot: quantity = lot count
                price_type=StockPriceType.LMT,
                order_type=OrderType.ROD,
                order_lot=StockOrderLot.Common,
                order_cond=StockOrderCond.Cash,
                account=api.stock_account,
            )

            try:
                trade = api.place_order(contract, order)
            except Exception as exc:
                order_journal.mark_failed(
                    order_id=order_id,
                    failure_type=FailureType.TRANSPORT,
                    error_code="place_order_raised",
                    error_message=f"{type(exc).__name__}: {exc}",
                )
                self._notify(
                    f"❌ 委託送出失敗 (TRANSPORT)\n{symbol} {side.value}\n"
                    f"{type(exc).__name__}: {exc}\n"
                    f"⚠️ 需 reconcile 確認券商端是否收單"
                )
                return self._build_failed_result(
                    order_id=order_id, symbol=symbol, side=side,
                    requested_lots=requested_lots, fill_date=fill_date,
                    signal_id=signal_id, limit_price=ref_price,
                    notional=notional,
                    failure_type=FailureType.TRANSPORT,
                    error_code="place_order_raised",
                    error_message=f"{type(exc).__name__}: {exc}",
                )

            # Normalize broker_order_id (empty string → None handled by journal)
            broker_order_id = (
                trade.order.id if trade and trade.order and trade.order.id
                else None
            )
            submitted_at = datetime.now(tz=TAIPEI_TZ)
            order_journal.mark_submitted(
                order_id=order_id,
                broker_order_id=broker_order_id,
                submitted_at=submitted_at,
            )

            self._notify(
                f"📤 委託送出\n"
                f"{symbol}｜{side.value} {requested_lots} 張（整股）\n"
                f"委託價：{ref_price:.2f}\n"
                f"{'模擬' if self._simulation else '實單'}｜ROD 限價\n"
                f"委託時間：{submitted_at.strftime('%H:%M:%S')}"
            )

            # ── Step 8: poll for fill ─────────────────────────────────────
            time.sleep(self.poll_sleep_sec)
            try:
                api.update_status(api.stock_account)
                polled_at = datetime.now(tz=TAIPEI_TZ)
            except Exception as exc:
                # update_status failed: order is in flight, status unknown.
                # Leave as SUBMITTED for reconcile (do NOT mark FAILED).
                logger.warning(
                    "live_update_status_failed",
                    order_id=order_id, error=str(exc),
                )
                return self._build_submitted_unpolled_result(
                    order_id=order_id, symbol=symbol, side=side,
                    requested_lots=requested_lots, fill_date=fill_date,
                    signal_id=signal_id, limit_price=ref_price,
                    notional=notional,
                    broker_order_id=broker_order_id,
                    submitted_at=submitted_at,
                )

            # ─── P-obs-1: raw payload observation ────────────────────────
            # Dump BOTH trade.status.deals (current code path) AND
            # trade.deals (alternate SDK path that may exist) so we can
            # observe whether they agree. v2.1 only reads status.deals;
            # if SDK populates trade.deals differently we want to know
            # before relying on either invariant.
            #
            # Dual-logging on semantic-critical fields (price / quantity
            # / ts): raw + _safe_repr + _safe_type. Raw exposes
            # structlog's runtime serialization behavior; repr+type are
            # evidence fallback if raw serialization fails or surprises.
            _obs_status = _safe_getattr(trade, "status", None)
            _obs_status_deals = _safe_getattr(_obs_status, "deals", None) or []
            _obs_trade_deals = _safe_getattr(trade, "deals", None) or []
            logger.info(
                "shioaji_raw_submit_observation",
                order_id=order_id,
                broker_order_id=_safe_getattr(
                    _safe_getattr(trade, "order", None), "id", None,
                ),
                trade_repr=_safe_repr(trade),
                trade_type=_safe_type(trade),
                status_repr=_safe_repr(_obs_status),
                status_type=_safe_type(_obs_status),
                status_status_repr=_safe_repr(
                    _safe_getattr(_obs_status, "status", None),
                ),
                status_status_type=_safe_type(
                    _safe_getattr(_obs_status, "status", None),
                ),
                status_deals_count=len(_obs_status_deals),
                trade_deals_count=len(_obs_trade_deals),
                deals_paths_agree=(
                    len(_obs_status_deals) == len(_obs_trade_deals)
                ),
                status_deals_raw=[
                    {
                        "repr": _safe_repr(d),
                        # price: dual-log (raw + repr + type)
                        "price_raw": _safe_getattr(d, "price", None),
                        "price_repr": _safe_repr(
                            _safe_getattr(d, "price", None),
                        ),
                        "price_type": _safe_type(
                            _safe_getattr(d, "price", None),
                        ),
                        # quantity: dual-log (raw + repr + type)
                        "quantity_raw": _safe_getattr(d, "quantity", None),
                        "quantity_repr": _safe_repr(
                            _safe_getattr(d, "quantity", None),
                        ),
                        "quantity_type": _safe_type(
                            _safe_getattr(d, "quantity", None),
                        ),
                        # ts: dual-log (raw + repr + type)
                        "ts_raw": _safe_getattr(d, "ts", None),
                        "ts_repr": _safe_repr(_safe_getattr(d, "ts", None)),
                        "ts_type": _safe_type(_safe_getattr(d, "ts", None)),
                    }
                    for d in _obs_status_deals
                ],
            )
            # ─── end P-obs-1 ─────────────────────────────────────────────

            deals = (
                list(trade.status.deals)
                if trade and trade.status and trade.status.deals else []
            )
            # ── Boundary normalization (v0.1.16 v2.1) ────────────────────
            # Shioaji StockOrderLot semantics (confirmed via Sinotrade docs
            # 2026-05-25 and live sim repro):
            #   Common:      deal.quantity is in LOTS — × SHARES_PER_LOT here
            #   IntradayOdd: deal.quantity is in SHARES — pass-through (v0.1.17)
            #
            # Design invariant (FROZEN):
            #   "Broker adapters may expose broker-native quantity semantics,
            #    but all persisted execution accounting inside Helios must
            #    use canonical share-equivalent units."
            #
            # The assertion below is the contractual boundary preventing
            # future IntradayOdd expansion from silently × SHARES_PER_LOT.
            # K-P0-1 share-equivalent invariant remains intact: post-normalization
            # total_deal_shares is compared against requested_shares throughout.
            assert order_lot is OrderLot.Common, (
                f"v0.1.16 v2.1 supports only OrderLot.Common at the boundary "
                f"normalization step; got {order_lot}. IntradayOdd path is "
                "reserved for v0.1.17 and requires path-specific handling."
            )
            total_deal_lots_native = sum(d.quantity for d in deals)
            # × SHARES_PER_LOT: broker-native (lot) → canonical (share)
            total_deal_shares = total_deal_lots_native * SHARES_PER_LOT
            # VWAP is unit-agnostic: sum(price × q) / sum(q) using native
            # unit on both numerator and denominator yields correct mean.
            avg_fill_price = (
                sum(d.price * d.quantity for d in deals) / total_deal_lots_native
                if total_deal_lots_native > 0 else None
            )

            requested_shares = requested_lots * SHARES_PER_LOT

            # ── Step 9: classify and persist fill state ───────────────────
            if total_deal_shares >= requested_shares:
                # Fully filled (or over-filled; latter shouldn't happen but
                # we treat == as the fully-filled case; >= is defensive).
                # If broker over-fills, we still mark FILLED — surplus is
                # a reconcile anomaly handled out-of-band.
                fill_shares_to_record = requested_shares  # cap at requested
                fill_notional = fill_shares_to_record * avg_fill_price
                commission = fill_notional * self.fees.commission_rate
                tax = (
                    fill_notional * self.fees.sell_tax_rate
                    if side is OrderSide.SELL else 0.0
                )
                order_journal.mark_filled(
                    order_id=order_id,
                    filled_shares=fill_shares_to_record,
                    avg_fill_price=avg_fill_price,
                    commission=commission,
                    tax=tax,
                    finalized_at=polled_at,
                )
                self._notify(
                    f"✅ 成交回報\n"
                    f"{symbol}｜{side.value} {requested_lots} 張（{fill_shares_to_record} 股）\n"
                    f"成交均價：{avg_fill_price:.2f}\n"
                    f"成交時間：{polled_at.strftime('%H:%M:%S')}"
                )
                return OrderSubmissionResult(
                    success=True, order_id=order_id, status=OrderStatus.FILLED,
                    side=side, symbol=symbol, requested_lots=requested_lots,
                    filled_shares=fill_shares_to_record,
                    avg_fill_price=avg_fill_price,
                    limit_price=ref_price, notional=fill_notional,
                    commission=commission, tax=tax,
                    fill_date=fill_date, signal_id=signal_id,
                    broker=self._broker_tag, broker_order_id=broker_order_id,
                    submitted_at=submitted_at, polled_at=polled_at,
                )

            if total_deal_shares > 0:
                # Partial fill (between 1 share and requested_shares-1)
                fill_notional = total_deal_shares * avg_fill_price
                commission = fill_notional * self.fees.commission_rate
                tax = (
                    fill_notional * self.fees.sell_tax_rate
                    if side is OrderSide.SELL else 0.0
                )
                order_journal.mark_partial(
                    order_id=order_id,
                    filled_shares=total_deal_shares,
                    avg_fill_price=avg_fill_price,
                    commission=commission,
                    tax=tax,
                    finalized_at=polled_at,
                )
                self._notify(
                    f"🚨 部分成交（需人工確認）\n"
                    f"{symbol}｜{side.value} {total_deal_shares}/{requested_shares} 股\n"
                    f"均價：{avg_fill_price:.2f}\n"
                    f"⚠️ v0.1.16 不自動處理部分成交，請至券商 app 確認"
                )
                return OrderSubmissionResult(
                    success=True, order_id=order_id, status=OrderStatus.PARTIAL,
                    side=side, symbol=symbol, requested_lots=requested_lots,
                    filled_shares=total_deal_shares,
                    avg_fill_price=avg_fill_price,
                    limit_price=ref_price, notional=fill_notional,
                    commission=commission, tax=tax,
                    fill_date=fill_date, signal_id=signal_id,
                    broker=self._broker_tag, broker_order_id=broker_order_id,
                    submitted_at=submitted_at, polled_at=polled_at,
                )

            # No deals: submitted-but-unfilled
            order_journal.mark_polled(
                order_id=order_id,
                polled_at=polled_at,
                filled_shares=0,
                avg_fill_price=None,
            )
            self._notify(
                f"⏳ 委託中\n"
                f"{symbol}｜{side.value} {requested_lots} 張｜待撮合\n"
                f"將於下一交易日盤中成交（reconcile 對帳）"
            )
            return OrderSubmissionResult(
                success=True, order_id=order_id, status=OrderStatus.SUBMITTED,
                side=side, symbol=symbol, requested_lots=requested_lots,
                filled_shares=0, avg_fill_price=None,
                limit_price=ref_price, notional=notional,
                commission=0.0, tax=0.0,
                fill_date=fill_date, signal_id=signal_id,
                broker=self._broker_tag, broker_order_id=broker_order_id,
                submitted_at=submitted_at, polled_at=polled_at,
            )

        finally:
            self._logout(api)

    # ── Failure helpers ────────────────────────────────────────────────────

    def _build_failed_result(
        self,
        *,
        order_id: str,
        symbol: str,
        side: OrderSide,
        requested_lots: int,
        fill_date: date_type,
        signal_id: str | None,
        failure_type: FailureType,
        error_code: str,
        error_message: str,
        limit_price: float | None = None,
        notional: float = 0.0,
    ) -> OrderSubmissionResult:
        """Build FAILED result. success=False."""
        return OrderSubmissionResult(
            success=False, order_id=order_id, status=OrderStatus.FAILED,
            side=side, symbol=symbol, requested_lots=requested_lots,
            filled_shares=0, avg_fill_price=None,
            limit_price=limit_price, notional=notional,
            commission=0.0, tax=0.0,
            fill_date=fill_date, signal_id=signal_id,
            broker=self._broker_tag, broker_order_id=None,
            failure_type=failure_type,
            error_code=error_code, error_message=error_message,
        )

    def _build_submitted_unpolled_result(
        self,
        *,
        order_id: str,
        symbol: str,
        side: OrderSide,
        requested_lots: int,
        fill_date: date_type,
        signal_id: str | None,
        limit_price: float,
        notional: float,
        broker_order_id: str | None,
        submitted_at: datetime,
    ) -> OrderSubmissionResult:
        """Build SUBMITTED-but-poll-failed result. success=True (place_order
        succeeded; we just don't know fill state yet)."""
        return OrderSubmissionResult(
            success=True, order_id=order_id, status=OrderStatus.SUBMITTED,
            side=side, symbol=symbol, requested_lots=requested_lots,
            filled_shares=0, avg_fill_price=None,
            limit_price=limit_price, notional=notional,
            commission=0.0, tax=0.0,
            fill_date=fill_date, signal_id=signal_id,
            broker=self._broker_tag, broker_order_id=broker_order_id,
            submitted_at=submitted_at, polled_at=None,
        )

    # ── BrokerAdapter protocol implementation ──────────────────────────────

    @contextmanager
    def login_session(self) -> Iterator[Any]:
        """Context manager for broker session. Yields Shioaji api handle.

        v2 (D-P0-2, decision 3a): public API replacing direct reconcile
        calls into _login/_logout.

        Usage:
            broker = LiveBroker()
            with broker.login_session() as api:
                trades = broker.fetch_trades(api, as_of)
                holdings = broker.fetch_holdings(api)
        """
        import shioaji as sj
        api = self._login(sj)
        if api is None:
            raise BrokerAdapterError("Shioaji login failed")
        try:
            yield api
        finally:
            self._logout(api)

    def fetch_trades(
        self, session: Any, as_of: date_type,
    ) -> list[dict]:
        """Fetch broker-confirmed trades for as_of date.

        Returns normalized dicts (see BrokerAdapter protocol docstring).
        Empty list if no trades or fetch failed.

        v2 (K-P1-3): action enum normalized via _normalize_action_to_side.
        """
        api = session
        try:
            raw = api.list_trades()
        except Exception as exc:
            logger.warning("broker_list_trades_failed", error=str(exc))
            return []

        if not raw:
            return []

        # ─── P-obs-1: raw payload observation ────────────────────────────
        # Cap sample at 5 — fetch_trades may be called once per cron but
        # the trade list grows linearly over the trading day. Full dump
        # would be O(N) per call. The deal_qty_types field per-trade is
        # the single highest-value observation: directly discharges the
        # Common-path LOTS-vs-SHARES assumption across the full trade
        # population without dumping every deal.
        #
        # Dual-logging is NOT applied here for per-deal price/qty —
        # _submit already captures full deal-level dual-log on the
        # submission path. This site's purpose is poll-path coverage:
        # confirm that list_trades returns the same shape as
        # place_order's trade.status.deals across the trading day.
        logger.info(
            "shioaji_raw_fetch_trades_observation",
            as_of=as_of.isoformat(),
            trades_count=len(raw),
            trades_truncated=len(raw) > 5,
            trades_sample=[
                {
                    "repr": _safe_repr(t),
                    "status_repr": _safe_repr(
                        _safe_getattr(t, "status", None),
                    ),
                    "status_type": _safe_type(
                        _safe_getattr(t, "status", None),
                    ),
                    "order_id": _safe_getattr(
                        _safe_getattr(t, "order", None), "id", None,
                    ),
                    "status_deals_count": len(
                        _safe_getattr(
                            _safe_getattr(t, "status", None), "deals", None,
                        ) or []
                    ),
                    "deal_qty_types": [
                        _safe_type(_safe_getattr(d, "quantity", None))
                        for d in (
                            _safe_getattr(
                                _safe_getattr(t, "status", None),
                                "deals", None,
                            ) or []
                        )
                    ],
                }
                for t in raw[:5]
            ],
        )
        # ─── end P-obs-1 ────────────────────────────────────────────────

        out: list[dict] = []
        for trade in raw:
            try:
                # Determine trade date — prefer status.modified_time
                trade_dt = (
                    getattr(trade.status, "modified_time", None)
                    if trade.status else None
                )
                if trade_dt is None:
                    trade_dt = getattr(trade, "ts", None)
                if trade_dt is None:
                    continue
                trade_date = (
                    trade_dt.date() if hasattr(trade_dt, "date") else None
                )
                if trade_date != as_of:
                    continue

                # Sum deals — boundary normalization (v0.1.16 v2.1).
                # Shioaji Common-path deal.quantity is in LOTS (confirmed via
                # Sinotrade docs + live sim repro 2026-05-25). Convert to
                # canonical share count here so downstream reconcile compares
                # broker filled_shares against helios DB filled_shares on the
                # same share-equivalent scale. IntradayOdd would be SHARES
                # natively (v0.1.17); for v2.1, only Common is supported and
                # this branch silently assumes all trades are Common — safe
                # given LiveBroker.submit_buy / submit_sell only place Common.
                deals = (
                    list(trade.status.deals)
                    if trade.status and trade.status.deals else []
                )
                total_deal_lots_native = sum(d.quantity for d in deals)
                # × SHARES_PER_LOT: broker-native (lot) → canonical (share)
                filled_shares = total_deal_lots_native * SHARES_PER_LOT
                # VWAP unit-agnostic: sum(price × q) / sum(q) using native
                # unit on both sides yields correct mean price.
                avg_price = (
                    sum(d.price * d.quantity for d in deals) / total_deal_lots_native
                    if total_deal_lots_native > 0 else None
                )

                broker_order_id = (
                    trade.order.id
                    if trade.order and trade.order.id else None
                )
                # Normalize empty string → None
                if broker_order_id == "":
                    broker_order_id = None

                symbol = (
                    trade.contract.code if trade.contract else None
                )
                side = _normalize_action_to_side(
                    trade.order.action if trade.order else None
                )

                out.append({
                    "broker_order_id": broker_order_id,
                    "symbol": symbol,
                    "side": side,
                    "filled_shares": filled_shares,
                    "avg_price": avg_price,
                    "trade_date": trade_date,
                    "raw_status": (
                        str(trade.status.status) if trade.status else "unknown"
                    ),
                })
            except Exception as exc:
                logger.warning("broker_trade_normalize_failed", error=str(exc))
        return out

    def fetch_holdings(self, session: Any) -> list[dict]:
        """Fetch broker-held positions snapshot.

        Returns normalized dicts (see BrokerAdapter protocol docstring).
        """
        api = session
        try:
            raw = api.list_positions(api.stock_account)
        except Exception as exc:
            logger.warning("broker_list_positions_failed", error=str(exc))
            return []
        if not raw:
            return []

        # ─── P-obs-1: raw payload observation ────────────────────────────
        # Cap sample at 20 — portfolio size bounded by strategy, but
        # observation here is mainly about per-position field types, not
        # population statistics. 20 is enough to cover any plausible
        # Helios holding count for the observation window.
        #
        # Dual-logging on quantity (raw + repr + type): same rationale as
        # _submit. quantity is the load-bearing field for the
        # × SHARES_PER_LOT boundary normalization — must observe
        # structlog's serialization behavior directly.
        #
        # OPEN QUESTION (per §5 SSOT): if Helios ever holds both Common
        # and IntradayOdd in same symbol, does list_positions return
        # them as separate records (one per order_lot) or as one merged
        # record? quantity_type per position is the key signal.
        logger.info(
            "shioaji_raw_fetch_holdings_observation",
            positions_count=len(raw),
            positions_truncated=len(raw) > 20,
            positions_raw=[
                {
                    "repr": _safe_repr(p),
                    "code": _safe_getattr(p, "code", None),
                    # quantity: dual-log
                    "quantity_raw": _safe_getattr(p, "quantity", None),
                    "quantity_repr": _safe_repr(
                        _safe_getattr(p, "quantity", None),
                    ),
                    "quantity_type": _safe_type(
                        _safe_getattr(p, "quantity", None),
                    ),
                    # price: dual-log
                    "price_raw": _safe_getattr(p, "price", None),
                    "price_repr": _safe_repr(
                        _safe_getattr(p, "price", None),
                    ),
                    "price_type": _safe_type(
                        _safe_getattr(p, "price", None),
                    ),
                    "direction_repr": _safe_repr(
                        _safe_getattr(p, "direction", None),
                    ),
                }
                for p in raw[:20]
            ],
        )
        # ─── end P-obs-1 ────────────────────────────────────────────────

        out: list[dict] = []
        for pos in raw:
            try:
                # Boundary normalization (v0.1.16 v2.1):
                # Shioaji list_positions.quantity is in LOTS for Common stock
                # holdings (verified 2026-05-25: 4919 cumulative 3 lots returned
                # pos.quantity=3, not 3000). Convert to canonical share count
                # for downstream reconcile vs helios positions.shares (which
                # stores share-equivalent BIGINT).
                #
                # v0.1.17 caveat: if IntradayOdd holdings appear in
                # list_positions, this × SHARES_PER_LOT will over-count by
                # 1000x. fetch_holdings will need to inspect a per-position
                # order_lot attribute (if Shioaji exposes one) before
                # converting. Not a concern in v2.1 — LiveBroker only places
                # Common orders.
                out.append({
                    "symbol": pos.code,
                    "shares": pos.quantity * SHARES_PER_LOT,
                    "avg_cost": pos.price,
                })
            except Exception as exc:
                logger.warning("broker_holding_normalize_failed", error=str(exc))
        return out

    # ── Login / logout / notify (internals, unchanged from v1) ─────────────

    def _login(self, sj: Any) -> Any:
        """Login + activate CA. Returns api or None on failure.

        Kept as private; external consumers use login_session() instead.
        """
        try:
            api = sj.Shioaji(simulation=self._simulation)
            api.login(
                api_key=self._api_key, secret_key=self._secret_key,
                fetch_contract=True, contracts_timeout=30_000,
                subscribe_trade=True,
            )
            api.activate_ca(
                ca_path=self._ca_path, ca_passwd=self._ca_passwd,
                person_id=api.stock_account.person_id,
            )
            api.set_default_account(api.stock_account)
            return api
        except Exception as exc:
            logger.error("live_broker_login_failed", error=str(exc))
            return None

    def _logout(self, api: Any) -> None:
        if api is None:
            return
        try:
            api.logout()
        except Exception as exc:
            logger.warning("live_broker_logout_error", error=str(exc))

    def _notify(self, message: str) -> None:
        if self.bot is None:
            logger.info("live_broker_notify_no_bot", message=message)
            return
        try:
            from communication.telegram.sender import push_simple
            push_simple(self.bot, message)
        except Exception as exc:
            logger.warning("live_broker_notify_failed", error=str(exc))


# Confirm LiveBroker satisfies BrokerAdapter protocol structurally.
# isinstance check would happen at runtime; this is a static reminder.
_: type[BrokerAdapter] = LiveBroker  # type: ignore[type-abstract]
