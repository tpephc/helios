# execution/live_broker.py
"""Shioaji live broker — v0.1.1.

Replaces PaperBroker + listen_for_approvals with auto-execution via
Shioaji API. No operator approval gate; Telegram is notification-only.

Modes (controlled by settings.shioaji_simulation):
  simulation=True  → StockOrderLot.Common (整股), lots=1
  simulation=False → StockOrderLot.IntradayOdd (零股), shares=1
                     max MAX_SHARES_PER_STOCK per position
                     REQUIRES live_trading_enabled=True in settings

Semantics:
  submit_buy() returns FillResult(success=True) when the order is
  *placed* (委託送出), not necessarily *filled* (成交).
  execution_reason="placed"   → order submitted, awaiting fill
  execution_reason="filled"   → confirmed fill within poll window

  Callers must interpret execution_reason to determine position status.
  For EOD batch (16:00), orders placed for next-day open; fill is
  expected but not confirmed until morning reconciliation.

Version: v0.1.1 (2026-05-24 — fix notional, VWAP, lots/shares semantics,
                  broker_order_id, live kill-switch)
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime

from config.settings import get_settings
from execution.paper_broker import DEFAULT_TW_FEES, FillResult, TransactionFees
from utils.logger import get_logger

logger = get_logger(__name__)

MAX_SHARES_PER_STOCK: int = 5    # odd-lot live mode cap per position
_STATUS_POLL_SLEEP: float = 2.0  # seconds before polling fill status


class LiveBrokerError(Exception):
    """Live broker configuration or runtime error."""


class LiveBroker:
    """Shioaji-backed broker.  submit_buy/submit_sell auto-execute and notify.

    Simulation mode (整股):
        broker = LiveBroker(bot=telegram_bot)
        result = broker.submit_buy(symbol="5434", lots=1, fill_date=...)
        # result.execution_reason == "placed" or "filled"

    Live mode (零股):
        # Requires SHIOAJI_SIMULATION=false AND live_trading_enabled=true in .env
        result = broker.submit_buy(symbol="5434", shares=1, fill_date=...)
    """

    def __init__(
        self,
        bot=None,
        fees: TransactionFees | None = None,
    ) -> None:
        cfg = get_settings()
        self._simulation = cfg.shioaji_simulation
        self._api_key = cfg.shioaji_api_key.get_secret_value() if cfg.shioaji_api_key else ""
        self._secret_key = cfg.shioaji_secret_key.get_secret_value() if cfg.shioaji_secret_key else ""
        self._ca_path = cfg.ca_cert_path or ""
        self._ca_passwd = cfg.ca_password.get_secret_value() if cfg.ca_password else ""
        self.fees = fees or DEFAULT_TW_FEES
        self.bot = bot

        # Live trading kill-switch: must be explicitly enabled in .env
        self._live_enabled: bool = getattr(cfg, "live_trading_enabled", False)
        if not self._simulation and not self._live_enabled:
            raise LiveBrokerError(
                "Live trading requires LIVE_TRADING_ENABLED=true in .env. "
                "Set SHIOAJI_SIMULATION=true for simulation mode."
            )

    # ── Public API ─────────────────────────────────────────────────────────────

    def submit_buy(
        self,
        *,
        symbol: str,
        fill_date: date_type,
        signal_id: str | None = None,
        lots: int | None = None,    # simulation=True: number of 整股 lots
        shares: int | None = None,  # simulation=False: number of 零股 shares
    ) -> FillResult:
        """Place a buy order.

        Exactly one of `lots` or `shares` must be provided, matching the
        current simulation mode.

        Args:
            symbol:    TWSE stock code, e.g. "5434".
            fill_date: Expected fill date (T+1 open for EOD signals).
            signal_id: Upstream signal ID for audit trail.
            lots:      Lots to buy (simulation=True only). 1 lot = 1000 shares.
            shares:    Shares to buy (simulation=False only). Capped at MAX_SHARES_PER_STOCK.
        """
        import shioaji as sj
        from shioaji.constant import (
            Action,
            OrderType,
            StockOrderCond,
            StockOrderLot,
            StockPriceType,
        )

        if self._simulation:
            if lots is None:
                raise ValueError("simulation mode requires lots=N (整股)")
            quantity = lots
            order_lot = StockOrderLot.Common
            unit_label = "張（整股）"
            shares_per_unit = 1000
        else:
            if shares is None:
                raise ValueError("live mode requires shares=N (零股)")
            quantity = min(shares, MAX_SHARES_PER_STOCK)
            order_lot = StockOrderLot.IntradayOdd
            unit_label = "股（零股）"
            shares_per_unit = 1

        api = self._login(sj)
        if api is None:
            return self._fail(symbol, fill_date, "login_failed", "buy", signal_id)

        try:
            contract = api.Contracts.Stocks[symbol]
            if contract is None:
                return self._fail(symbol, fill_date, "contract_not_found", "buy", signal_id)

            ref_price = contract.reference
            order = sj.order.StockOrder(
                action=Action.Buy,
                price=ref_price,
                quantity=quantity,
                price_type=StockPriceType.LMT,
                order_type=OrderType.ROD,
                order_lot=order_lot,
                order_cond=StockOrderCond.Cash,
                account=api.stock_account,
            )

            trade = api.place_order(contract, order)
            broker_order_id = trade.order.id if trade else ""

            logger.info(
                "live_buy_placed",
                symbol=symbol, quantity=quantity, price=ref_price,
                simulation=self._simulation, broker_order_id=broker_order_id,
            )

            self._notify(
                f"📤 委託通知\n"
                f"{symbol}｜買入 {quantity}{unit_label}\n"
                f"委託價：{ref_price:.2f}\n"
                f"{'模擬' if self._simulation else '實單'}｜ROD 限價\n"
                f"委託時間：{datetime.now().strftime('%H:%M:%S')}"
            )

            # Poll fill status (synchronous: acceptable for batch architecture)
            time.sleep(_STATUS_POLL_SLEEP)
            api.update_status(api.stock_account)

            deals = list(trade.status.deals) if trade and trade.status.deals else []
            total_deal_qty = sum(d.quantity for d in deals)
            avg_fill_price = (
                sum(d.price * d.quantity for d in deals) / total_deal_qty
                if total_deal_qty > 0 else ref_price
            )

            if total_deal_qty >= quantity:
                exec_reason = "filled"
                fill_status = "filled"
                self._notify(
                    f"✅ 成交回報\n"
                    f"{symbol}｜買入 {total_deal_qty}{unit_label}\n"
                    f"成交均價：{avg_fill_price:.2f}\n"
                    f"成交時間：{datetime.now().strftime('%H:%M:%S')}"
                )
            elif total_deal_qty > 0:
                exec_reason = "partial_filled"
                fill_status = "partial_filled"
                self._notify(
                    f"⚠️ 部分成交\n"
                    f"{symbol}｜成交 {total_deal_qty}/{quantity}{unit_label}\n"
                    f"均價：{avg_fill_price:.2f}"
                )
            else:
                exec_reason = "placed"
                fill_status = "submitted"
                avg_fill_price = ref_price
                total_deal_qty = 0
                self._notify(
                    f"⏳ 委託中\n"
                    f"{symbol}｜{quantity}{unit_label}｜待撮合\n"
                    f"將於下一交易日盤中成交"
                )

            # Notional in TWD (整股: lots × 1000 shares × price)
            actual_qty = total_deal_qty if exec_reason == "filled" else quantity
            notional = actual_qty * shares_per_unit * avg_fill_price
            commission = notional * self.fees.commission_rate

            db_order_id = self._record_order(
                signal_id=signal_id, symbol=symbol, side="buy",
                quantity=quantity, price=ref_price,
                filled_qty=total_deal_qty, avg_price=avg_fill_price,
                status=fill_status,
                commission=commission, tax=0.0,
                broker_order_id=broker_order_id,
            )

            return FillResult(
                success=True,
                order_id=db_order_id,
                fill_date=fill_date,
                fill_price=avg_fill_price,
                ref_price=ref_price,
                shares=actual_qty * shares_per_unit,
                notional=notional,
                commission=commission,
                tax=0.0,
                slippage_cost=0.0,
                total_cost=commission,
                cash_delta=-(notional + commission),
                execution_reason=exec_reason,
                participation_rate=None,
            )

        except Exception as exc:
            logger.error("live_buy_error", symbol=symbol, error=str(exc))
            self._notify(f"❌ 下單失敗\n{symbol} 買入\n{type(exc).__name__}: {exc}")
            return self._fail(symbol, fill_date, type(exc).__name__, "buy", signal_id)
        finally:
            self._logout(api)

    def submit_sell(
        self,
        *,
        symbol: str,
        shares: int,
        fill_date: date_type,
        signal_id: str | None = None,
        lots: int | None = None,
    ) -> FillResult:
        """Place a sell order.

        Args:
            symbol: TWSE stock code.
            shares: For live (零股): shares to sell.
            lots:   For simulation (整股): lots to sell (overrides shares).
            fill_date: Expected fill date.
        """
        import shioaji as sj
        from shioaji.constant import (
            Action,
            OrderType,
            StockOrderCond,
            StockOrderLot,
            StockPriceType,
        )

        if self._simulation:
            quantity = lots if lots is not None else (shares // 1000 or 1)
            order_lot = StockOrderLot.Common
            unit_label = "張（整股）"
            shares_per_unit = 1000
        else:
            if shares <= 0:
                return self._fail(symbol, fill_date, "non_positive_shares", "sell", signal_id)
            quantity = shares
            order_lot = StockOrderLot.IntradayOdd
            unit_label = "股（零股）"
            shares_per_unit = 1

        api = self._login(sj)
        if api is None:
            return self._fail(symbol, fill_date, "login_failed", "sell", signal_id)

        try:
            contract = api.Contracts.Stocks[symbol]
            if contract is None:
                return self._fail(symbol, fill_date, "contract_not_found", "sell", signal_id)

            ref_price = contract.reference
            order = sj.order.StockOrder(
                action=Action.Sell,
                price=ref_price,
                quantity=quantity,
                price_type=StockPriceType.LMT,
                order_type=OrderType.ROD,
                order_lot=order_lot,
                order_cond=StockOrderCond.Cash,
                account=api.stock_account,
            )

            trade = api.place_order(contract, order)
            broker_order_id = trade.order.id if trade else ""

            logger.info(
                "live_sell_placed",
                symbol=symbol, quantity=quantity, price=ref_price,
                simulation=self._simulation, broker_order_id=broker_order_id,
            )

            self._notify(
                f"📤 委託通知\n"
                f"{symbol}｜賣出 {quantity}{unit_label}\n"
                f"委託價：{ref_price:.2f}\n"
                f"{'模擬' if self._simulation else '實單'}｜ROD 限價\n"
                f"委託時間：{datetime.now().strftime('%H:%M:%S')}"
            )

            time.sleep(_STATUS_POLL_SLEEP)
            api.update_status(api.stock_account)

            deals = list(trade.status.deals) if trade and trade.status.deals else []
            total_deal_qty = sum(d.quantity for d in deals)
            avg_fill_price = (
                sum(d.price * d.quantity for d in deals) / total_deal_qty
                if total_deal_qty > 0 else ref_price
            )

            if total_deal_qty >= quantity:
                exec_reason = "filled"
                fill_status = "filled"
                self._notify(
                    f"✅ 成交回報\n"
                    f"{symbol}｜賣出 {total_deal_qty}{unit_label}\n"
                    f"成交均價：{avg_fill_price:.2f}\n"
                    f"成交時間：{datetime.now().strftime('%H:%M:%S')}"
                )
            elif total_deal_qty > 0:
                exec_reason = "partial_filled"
                fill_status = "partial_filled"
                self._notify(
                    f"⚠️ 部分成交\n"
                    f"{symbol}｜成交 {total_deal_qty}/{quantity}{unit_label}\n"
                    f"均價：{avg_fill_price:.2f}"
                )
            else:
                exec_reason = "placed"
                fill_status = "submitted"
                avg_fill_price = ref_price
                total_deal_qty = 0
                self._notify(
                    f"⏳ 委託中\n"
                    f"{symbol}｜{quantity}{unit_label}｜待撮合"
                )

            actual_qty = total_deal_qty if exec_reason == "filled" else quantity
            notional = actual_qty * shares_per_unit * avg_fill_price
            commission = notional * self.fees.commission_rate
            tax = notional * self.fees.sell_tax_rate

            db_order_id = self._record_order(
                signal_id=signal_id, symbol=symbol, side="sell",
                quantity=quantity, price=ref_price,
                filled_qty=total_deal_qty, avg_price=avg_fill_price,
                status=fill_status,
                commission=commission, tax=tax,
                broker_order_id=broker_order_id,
            )

            return FillResult(
                success=True,
                order_id=db_order_id,
                fill_date=fill_date,
                fill_price=avg_fill_price,
                ref_price=ref_price,
                shares=actual_qty * shares_per_unit,
                notional=notional,
                commission=commission,
                tax=tax,
                slippage_cost=0.0,
                total_cost=commission + tax,
                cash_delta=+(notional - commission - tax),
                execution_reason=exec_reason,
                participation_rate=None,
            )

        except Exception as exc:
            logger.error("live_sell_error", symbol=symbol, error=str(exc))
            self._notify(f"❌ 下單失敗\n{symbol} 賣出\n{type(exc).__name__}: {exc}")
            return self._fail(symbol, fill_date, type(exc).__name__, "sell", signal_id)
        finally:
            self._logout(api)

    # ── Private ────────────────────────────────────────────────────────────────

    def _login(self, sj):
        """Login + activate CA.  Returns api or None on failure."""
        try:
            api = sj.Shioaji(simulation=self._simulation)
            api.login(
                api_key=self._api_key,
                secret_key=self._secret_key,
                fetch_contract=True,
                contracts_timeout=30_000,
                subscribe_trade=True,
            )
            api.activate_ca(
                ca_path=self._ca_path,
                ca_passwd=self._ca_passwd,
                person_id=api.stock_account.person_id,
            )
            api.set_default_account(api.stock_account)
            return api
        except Exception as exc:
            logger.error("live_broker_login_failed", error=str(exc))
            return None

    def _logout(self, api) -> None:
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

    def _record_order(
        self,
        *,
        signal_id: str | None,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        filled_qty: int,
        avg_price: float,
        status: str,
        commission: float,
        tax: float,
        broker_order_id: str = "",
    ) -> str:
        from data.database import connect
        order_id = f"live_{uuid.uuid4().hex[:12]}"
        broker_tag = f"shioaji_{'sim' if self._simulation else 'live'}:{broker_order_id}"
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO orders (
                    order_id, signal_id, timestamp, symbol, side, order_type,
                    quantity, price, status, filled_qty, avg_price,
                    commission, tax, broker
                ) VALUES (?, ?, ?, ?, ?, 'limit', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    order_id, signal_id, datetime.now(), symbol, side,
                    quantity, price, status,
                    filled_qty, avg_price if filled_qty > 0 else None,
                    commission, tax, broker_tag,
                ],
            )
        return order_id

    def _fail(
        self,
        symbol: str,
        fill_date: date_type,
        reason: str,
        side: str,
        signal_id: str | None,
    ) -> FillResult:
        logger.warning(
            "live_fill_failed", symbol=symbol, side=side,
            fill_date=str(fill_date), reason=reason, signal_id=signal_id,
        )
        return FillResult(
            success=False, order_id=None,
            fill_date=fill_date, fill_price=None, ref_price=None,
            shares=0, notional=0.0,
            commission=0.0, tax=0.0, slippage_cost=0.0, total_cost=0.0,
            cash_delta=0.0, error=reason,
            execution_reason=reason, participation_rate=None,
        )
