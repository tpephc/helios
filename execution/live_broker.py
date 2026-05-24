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
  - D-P0-2 / decision 3a: implements BrokerAdapter protocol via public
    login_session, fetch_trades, fetch_holdings methods. reconcile no
    longer calls _login directly.
  - D-P2-e: _STATUS_POLL_SLEEP configurable (default raised to 5.0s).

UNIT CONVENTION:
  requested_lots: int, Common lot count (1 lot = SHARES_PER_LOT shares)
  total_deal_shares: int, sum of deal.quantity from Shioaji (SHARES)
  Conversion: requested_shares = requested_lots * SHARES_PER_LOT
  Comparisons MUST use share-equivalents.

Version: v0.1.2 (2026-05-24, v2)
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


class LiveBrokerError(Exception):
    """Live broker configuration or runtime error."""


def _resolve_stock_contract(api: Any, symbol: str) -> Any:
    """Resolve a Shioaji contract for a TWSE/OTC symbol.

    v2 (C-P1-6): explicitly tries TSE first then OTC. Previously used
    bare `api.Contracts.Stocks[symbol]` which works for some symbols
    but is unreliable for OTC (上櫃) and certain ETFs.

    Returns the contract or None if not found in either market.
    """
    try:
        tse = api.Contracts.Stocks.TSE
        contract = tse[symbol] if symbol in tse else None
        if contract is not None:
            return contract
    except Exception as exc:  # noqa: BLE001 - SDK-level call surface unknown
        logger.warning(
            "contract_lookup_tse_failed", symbol=symbol, error=str(exc),
        )
    try:
        otc = api.Contracts.Stocks.OTC
        contract = otc[symbol] if symbol in otc else None
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
        self.guard = guard or PreTradeGuard()
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
    ) -> OrderSubmissionResult:
        """Place a Common-lot buy order. lots is in 整股 units (1 lot = 1000 shares)."""
        return self._submit(
            side=OrderSide.BUY, symbol=symbol, fill_date=fill_date,
            signal_id=signal_id, lots=lots,
        )

    def submit_sell(
        self,
        *,
        symbol: str,
        fill_date: date_type,
        signal_id: str | None = None,
        lots: int = 1,
    ) -> OrderSubmissionResult:
        """Place a Common-lot sell order."""
        return self._submit(
            side=OrderSide.SELL, symbol=symbol, fill_date=fill_date,
            signal_id=signal_id, lots=lots,
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
            metadata={"lots": requested_lots, "shares_per_lot": SHARES_PER_LOT},
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

            deals = (
                list(trade.status.deals)
                if trade and trade.status and trade.status.deals else []
            )
            # CRITICAL UNIT NOTE (K-P0-1):
            #   deal.quantity is in SHARES (not lots).
            #   total_deal_shares accumulates in SHARES.
            #   To compare with requested_lots, convert via SHARES_PER_LOT.
            total_deal_shares = sum(d.quantity for d in deals)
            avg_fill_price = (
                sum(d.price * d.quantity for d in deals) / total_deal_shares
                if total_deal_shares > 0 else None
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

                # Sum deals (each deal is in SHARES)
                deals = (
                    list(trade.status.deals)
                    if trade.status and trade.status.deals else []
                )
                filled_shares = sum(d.quantity for d in deals)
                avg_price = (
                    sum(d.price * d.quantity for d in deals) / filled_shares
                    if filled_shares > 0 else None
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

        out: list[dict] = []
        for pos in raw:
            try:
                out.append({
                    "symbol": pos.code,
                    "shares": pos.quantity,
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
