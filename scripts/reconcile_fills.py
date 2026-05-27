#!/usr/bin/env python3
# scripts/reconcile_fills.py
"""T+1 fill reconciliation — v0.1.16 (post-review v2).

Daily three-way reconciliation between Helios order journal, broker
trades, and positions table.

v2 changes from v1 (per advisor review):
  - C-P0-1 / K-P1-4: queries Helios orders by fill_date (not intent_at).
    T+1 morning reconcile passes fill_date=today, capturing orders that
    were intent'd yesterday EOD.
  - D-P0-2 / decision 3a: uses BrokerAdapter protocol via
    LiveBroker.login_session(); no longer reaches into private _login.
    Avoids `import shioaji` at module level.
  - Extra decision: ReconcileCandidate model for fuzzy matching when
    broker_order_id is absent. NOT auto-merged; emits human-review
    candidates only. v0.1.17 may automate.
  - K-P1-3: side normalization centralized in broker adapter (no string
    compare here).
  - K-P2-e: pop guarded against None key.
  - K-P2-f: sim_fallback excludes SUBMITTED from expecting_trades.
  - D-P2-b: --send-telegram CLI flag for critical findings.

Reconcile axes:
  Axis A: Helios orders ↔ broker trades (fill confirmation)
  Axis B: Helios positions ↔ broker holdings (state desync)
  Axis C: requires_broker_verification orders
  Axis D (v2): fuzzy candidate report for orphans without broker_order_id

Reconcile does NOT mutate state. It emits a report; operator decides.

Sim fallback:
  shioaji_sim sometimes returns empty list_trades(). Reconcile detects
  this and degrades to two-way (B only) with a warning.

Usage:
  uv run python scripts/reconcile_fills.py                       # T+1 default
  uv run python scripts/reconcile_fills.py --as-of 2026-05-23
  uv run python scripts/reconcile_fills.py --send-telegram       # on critical

Version: v0.1.16 (v2) — 2026-05-24
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import date as date_type
from datetime import datetime, timedelta

from data.database import connect
from execution.broker_adapter import BrokerAdapter, BrokerAdapterError
from execution.order_types import SHARES_PER_LOT, OrderStatus
from storage import order_journal
from utils.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Report types
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ReconcileFinding:
    """Single reconciliation finding."""

    category: str
    severity: str  # 'info' | 'warning' | 'critical'
    order_id: str | None
    broker_order_id: str | None
    symbol: str
    detail: str


@dataclass
class ReconcileCandidate:
    """Fuzzy-match candidate for orphans without broker_order_id.

    v2 (extra decision): emitted as part of Axis D for human review when:
      - Helios FAILED.transport order has no broker_order_id but broker
        shows a similar trade, OR
      - Helios SUBMITTED/FILLED order has no broker_order_id and a
        broker trade matches (symbol, side, shares, time window).

    NOT auto-merged. v0.1.16 just surfaces these for operator decision.
    v0.1.17 may add policy-driven auto-merge with audit log.

    Why broker_order_id alone cannot be the matching key:
      1. sim mode: Shioaji may return empty string broker_order_id
      2. transport failure: place_order raised before broker_order_id captured
      3. partial deal aggregation: broker may emit deals over multiple
         trade objects with the same logical order; ID semantics depend
         on SDK version
    The candidate model gives the operator a structured tuple
    (symbol, side, submitted_date, filled_shares, avg_price,
    time_distance) to resolve manually.

    Field name notes:
      - broker_submitted_date is the broker trade's date (== fill_date
        from Helios perspective for ROD orders); not the order submission
        timestamp.
      - broker_avg_price is the VWAP from broker deals.
    """

    helios_order_id: str
    broker_trade_index: int   # index in fetched trades list
    symbol: str
    side: str

    # Quantity (always shares-equivalent on both sides — K-P0-1 rules apply)
    helios_requested_shares: int
    broker_filled_shares: int

    # Price (only broker side has meaningful price for fuzzy match;
    # Helios INTENT may have limit_price but FAILED.transport may not)
    broker_avg_price: float | None
    helios_limit_price: float | None

    # Dates / time distance
    helios_intent_at: datetime | None
    broker_submitted_date: date_type | None      # broker trade_date
    time_distance_seconds: float | None

    # Optional identifiers
    broker_order_id: str | None

    # Operator-facing confidence
    confidence: str  # 'high' | 'medium' | 'low'


@dataclass
class ReconcileReport:
    """Aggregate reconcile findings for one as_of date."""

    as_of: date_type
    mode: str  # 'three_way' | 'two_way_sim_fallback' | 'no_broker'
    helios_orders_total: int = 0
    broker_trades_total: int = 0
    broker_holdings_total: int = 0
    helios_positions_total: int = 0
    findings: list[ReconcileFinding] = field(default_factory=list)
    candidates: list[ReconcileCandidate] = field(default_factory=list)

    def add(
        self,
        *,
        category: str,
        severity: str,
        order_id: str | None,
        broker_order_id: str | None,
        symbol: str,
        detail: str,
    ) -> None:
        self.findings.append(ReconcileFinding(
            category=category, severity=severity,
            order_id=order_id, broker_order_id=broker_order_id,
            symbol=symbol, detail=detail,
        ))

    def has_critical(self) -> bool:
        return any(f.severity == "critical" for f in self.findings)

    def to_console(self) -> str:
        lines = []
        lines.append(f"Reconcile report for {self.as_of} (mode={self.mode})")
        lines.append(f"  Helios orders (by fill_date): {self.helios_orders_total}")
        lines.append(f"  Broker trades:                {self.broker_trades_total}")
        lines.append(f"  Helios positions (OPEN):      {self.helios_positions_total}")
        lines.append(f"  Broker holdings:              {self.broker_holdings_total}")
        lines.append(f"  Findings:                     {len(self.findings)}")
        lines.append(f"  Candidates (human review):    {len(self.candidates)}")
        lines.append("")

        for severity_filter, label in [
            ("critical", "CRITICAL"),
            ("warning", "WARNING"),
            ("info", "INFO"),
        ]:
            matching = [f for f in self.findings if f.severity == severity_filter]
            if not matching:
                continue
            lines.append(f"--- {label} ({len(matching)}) ---")
            for f in matching:
                broker_id = f.broker_order_id or "-"
                order_id = f.order_id or "-"
                lines.append(
                    f"  [{f.category}] {f.symbol} "
                    f"helios={order_id} broker={broker_id}\n"
                    f"    {f.detail}"
                )
            lines.append("")

        if self.candidates:
            lines.append(f"--- FUZZY CANDIDATES ({len(self.candidates)}) ---")
            for c in self.candidates:
                price_line = ""
                if c.broker_avg_price is not None or c.helios_limit_price is not None:
                    bp = (
                        f"{c.broker_avg_price:.2f}"
                        if c.broker_avg_price is not None else "?"
                    )
                    hp = (
                        f"{c.helios_limit_price:.2f}"
                        if c.helios_limit_price is not None else "?"
                    )
                    price_line = (
                        f"\n    price: broker_avg={bp} helios_limit={hp}"
                    )
                date_line = (
                    f"\n    submitted_date(broker)={c.broker_submitted_date} "
                    f"intent_at(helios)={c.helios_intent_at}"
                    if c.broker_submitted_date or c.helios_intent_at else ""
                )
                lines.append(
                    f"  [{c.confidence}] {c.symbol} {c.side}\n"
                    f"    helios_order={c.helios_order_id} "
                    f"({c.helios_requested_shares} shares requested)\n"
                    f"    broker_trade={c.broker_order_id or '(no id)'} "
                    f"({c.broker_filled_shares} shares filled)"
                    f"{price_line}"
                    f"{date_line}"
                    f"\n    time_distance={c.time_distance_seconds}s"
                )
            lines.append("")

        return "\n".join(lines)

    def to_telegram(self) -> str:
        """Compact Telegram message for critical findings."""
        if not self.has_critical():
            return f"✅ Reconcile {self.as_of}: no critical findings ({self.mode})"
        crit = [f for f in self.findings if f.severity == "critical"]
        lines = [
            f"🚨 RECONCILE CRITICAL ({self.as_of})",
            f"Mode: {self.mode}",
            f"Critical findings: {len(crit)}",
        ]
        for f in crit[:5]:  # cap at 5 to fit Telegram message limit
            lines.append(
                f"\n• {f.symbol} [{f.category}]"
            )
            lines.append(f"  {f.detail[:200]}")  # truncate long details
        if len(crit) > 5:
            lines.append(f"\n...and {len(crit) - 5} more (see console).")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Helios data fetchers
# ─────────────────────────────────────────────────────────────────────────────


def _fetch_helios_open_positions() -> list[dict]:
    """Fetch Helios OPEN positions snapshot."""
    with connect(read_only=True) as conn:
        rows = conn.execute(
            """
            SELECT position_id, symbol, shares, source_order_id,
                   entry_date, entry_price, status
            FROM positions
            WHERE status = 'OPEN'
            """,
        ).fetchall()
    return [
        {
            "position_id": r[0], "symbol": r[1], "shares": r[2],
            "source_order_id": r[3], "entry_date": r[4],
            "entry_price": r[5], "status": r[6],
        }
        for r in rows
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Reconcile logic
# ─────────────────────────────────────────────────────────────────────────────


def _reconcile_orders_vs_trades(
    helios_orders: list,
    broker_trades: list[dict],
    report: ReconcileReport,
) -> None:
    """Axis A: orders ↔ broker trades."""
    # Build broker_order_id index (skip None keys per K-P2-e)
    broker_by_id: dict[str, dict] = {
        t["broker_order_id"]: t for t in broker_trades
        if t.get("broker_order_id")
    }

    for ho in helios_orders:
        if ho.status in (OrderStatus.CANCELLED, OrderStatus.EXPIRED):
            continue
        # FAILED.broker_reject is terminal; FAILED.transport handled in Axis C
        if ho.status is OrderStatus.FAILED:
            continue

        if ho.status is OrderStatus.INTENT:
            # Shouldn't exist after startup_recovery
            report.add(
                category="orphan_helios_order", severity="critical",
                order_id=ho.order_id, broker_order_id=ho.broker_order_id,
                symbol=ho.symbol,
                detail=(
                    f"Helios order in INTENT state after EOD; "
                    f"startup_recovery should have resolved this. "
                    f"intent_at={ho.intent_at}"
                ),
            )
            continue

        # SUBMITTED / PARTIAL / FILLED expect broker_order_id
        if not ho.broker_order_id:
            report.add(
                category="orphan_helios_order", severity="warning",
                order_id=ho.order_id, broker_order_id=None,
                symbol=ho.symbol,
                detail=(
                    f"Helios order {ho.status.value} without broker_order_id. "
                    f"Cannot reconcile by ID. See fuzzy candidates section."
                ),
            )
            # Try to surface candidates by symbol + side
            _maybe_add_fuzzy_candidate(ho, broker_trades, report)
            continue

        # K-P2-e: guard pop against None key (defensive — broker_order_id
        # may be None despite our filter above due to schema state)
        if ho.broker_order_id is None:
            continue

        match = broker_by_id.pop(ho.broker_order_id, None)
        if match is None:
            if ho.status is OrderStatus.FILLED:
                report.add(
                    category="orphan_helios_order", severity="critical",
                    order_id=ho.order_id, broker_order_id=ho.broker_order_id,
                    symbol=ho.symbol,
                    detail=(
                        f"Helios marks FILLED but broker shows no trade. "
                        f"Possible journal corruption or broker_order_id mismatch."
                    ),
                )
            else:
                report.add(
                    category="orphan_helios_order", severity="warning",
                    order_id=ho.order_id, broker_order_id=ho.broker_order_id,
                    symbol=ho.symbol,
                    detail=(
                        f"Helios {ho.status.value}, broker shows no fill yet. "
                        f"Order likely still pending or expired without fill."
                    ),
                )
        else:
            # Matched: verify qty consistency
            broker_filled = match.get("filled_shares", 0)
            if ho.status is OrderStatus.FILLED:
                if broker_filled == (ho.filled_shares or 0):
                    report.add(
                        category="matched_fill", severity="info",
                        order_id=ho.order_id, broker_order_id=ho.broker_order_id,
                        symbol=ho.symbol,
                        detail=(
                            f"Matched: {ho.filled_shares} shares "
                            f"@ {ho.avg_fill_price}"
                        ),
                    )
                else:
                    report.add(
                        category="matched_fill", severity="critical",
                        order_id=ho.order_id, broker_order_id=ho.broker_order_id,
                        symbol=ho.symbol,
                        detail=(
                            f"Shares mismatch: Helios={ho.filled_shares}, "
                            f"broker={broker_filled}"
                        ),
                    )
            else:
                report.add(
                    category="matched_fill", severity="warning",
                    order_id=ho.order_id, broker_order_id=ho.broker_order_id,
                    symbol=ho.symbol,
                    detail=(
                        f"Helios {ho.status.value} but broker shows "
                        f"filled_shares={broker_filled}. Journal needs "
                        f"manual update."
                    ),
                )

    # Anything left in broker_by_id has no Helios match
    for broker_id, trade in broker_by_id.items():
        report.add(
            category="unexpected_broker_trade", severity="critical",
            order_id=None, broker_order_id=broker_id,
            symbol=trade.get("symbol") or "?",
            detail=(
                f"Broker trade with no Helios order. "
                f"Side={trade.get('side')} filled={trade.get('filled_shares')}. "
                f"Possible manual trade, credential leak, or duplicate session."
            ),
        )


def _maybe_add_fuzzy_candidate(
    helios_order, broker_trades: list[dict], report: ReconcileReport,
) -> None:
    """Surface broker trades that *might* correspond to a Helios order
    without broker_order_id. Human review only.
    """
    helios_shares = (helios_order.requested_lots or 0) * SHARES_PER_LOT

    for idx, trade in enumerate(broker_trades):
        if trade.get("symbol") != helios_order.symbol:
            continue
        if trade.get("side") != (
            helios_order.side.value if helios_order.side else None
        ):
            continue

        # Compute time distance if both timestamps available
        time_distance = None
        if helios_order.intent_at and trade.get("trade_date"):
            # trade_date is a date, intent_at is datetime; use start-of-day
            trade_dt = datetime.combine(trade["trade_date"], datetime.min.time())
            if helios_order.intent_at.tzinfo is not None:
                # Treat trade_dt as same tz for distance computation
                trade_dt = trade_dt.replace(tzinfo=helios_order.intent_at.tzinfo)
            time_distance = abs(
                (helios_order.intent_at - trade_dt).total_seconds()
            )

        # Confidence heuristic
        broker_shares = trade.get("filled_shares", 0)
        if broker_shares == helios_shares:
            confidence = "high"
        elif abs(broker_shares - helios_shares) <= helios_shares * 0.1:
            confidence = "medium"
        else:
            confidence = "low"

        report.candidates.append(ReconcileCandidate(
            helios_order_id=helios_order.order_id,
            broker_trade_index=idx,
            symbol=helios_order.symbol,
            side=helios_order.side.value if helios_order.side else "?",
            helios_requested_shares=helios_shares,
            broker_filled_shares=broker_shares,
            broker_avg_price=trade.get("avg_price"),
            helios_limit_price=helios_order.limit_price,
            helios_intent_at=helios_order.intent_at,
            broker_submitted_date=trade.get("trade_date"),
            time_distance_seconds=time_distance,
            broker_order_id=trade.get("broker_order_id"),
            confidence=confidence,
        ))


def _reconcile_positions_vs_holdings(
    helios_positions: list[dict],
    broker_holdings: list[dict],
    report: ReconcileReport,
) -> None:
    """Axis B: positions ↔ broker holdings."""
    broker_by_symbol: dict[str, dict] = {
        h["symbol"]: h for h in broker_holdings
    }

    for hp in helios_positions:
        symbol = hp["symbol"]
        match = broker_by_symbol.pop(symbol, None)
        if match is None:
            report.add(
                category="desync_helios_position", severity="critical",
                order_id=None, broker_order_id=None,
                symbol=symbol,
                detail=(
                    f"Helios OPEN position ({hp['shares']} shares) but "
                    f"broker holds no shares. Possible position desync."
                ),
            )
        elif match["shares"] != hp["shares"]:
            report.add(
                category="desync_helios_position", severity="warning",
                order_id=None, broker_order_id=None,
                symbol=symbol,
                detail=(
                    f"Share count mismatch: Helios={hp['shares']}, "
                    f"broker={match['shares']}"
                ),
            )

    for symbol, holding in broker_by_symbol.items():
        report.add(
            category="unexpected_broker_holding", severity="critical",
            order_id=None, broker_order_id=None,
            symbol=symbol,
            detail=(
                f"Broker holds {holding['shares']} shares with no "
                f"corresponding Helios OPEN position."
            ),
        )


def _reconcile_transport_verifications(
    report: ReconcileReport,
    broker_trades: list[dict],
) -> None:
    """Axis C: FAILED.transport orders needing broker verification."""
    pending = order_journal.list_orders_requiring_verification()
    if not pending:
        return

    broker_by_id = {
        t["broker_order_id"]: t for t in broker_trades
        if t.get("broker_order_id")
    }

    for order in pending:
        if not order.broker_order_id:
            report.add(
                category="transport_verification_pending", severity="critical",
                order_id=order.order_id, broker_order_id=None,
                symbol=order.symbol,
                detail=(
                    f"FAILED.transport order without broker_order_id. "
                    f"Manual broker check required for symbol={order.symbol} "
                    f"side={order.side.value if order.side else '?'} "
                    f"lots={order.requested_lots} intent_at={order.intent_at}. "
                    f"See fuzzy candidates."
                ),
            )
            _maybe_add_fuzzy_candidate(order, broker_trades, report)
            continue

        match = broker_by_id.get(order.broker_order_id)
        if match:
            report.add(
                category="transport_verification_pending", severity="critical",
                order_id=order.order_id, broker_order_id=order.broker_order_id,
                symbol=order.symbol,
                detail=(
                    f"FAILED.transport order CONFIRMED FILLED at broker. "
                    f"filled_shares={match.get('filled_shares')}. Helios marked "
                    f"FAILED but broker shows fill. Journal correction + "
                    f"position open required."
                ),
            )
        else:
            report.add(
                category="transport_verification_pending", severity="warning",
                order_id=order.order_id, broker_order_id=order.broker_order_id,
                symbol=order.symbol,
                detail=(
                    f"FAILED.transport order verified NOT in broker fills. "
                    f"Safe to clear requires_broker_verification flag."
                ),
            )


# ─────────────────────────────────────────────────────────────────────────────
# Main reconcile entry point
# ─────────────────────────────────────────────────────────────────────────────


def reconcile(
    fill_date: date_type,
    adapter: BrokerAdapter | None = None,
) -> ReconcileReport:
    """Run reconciliation for orders with the given fill_date.

    v2: parameter renamed `as_of` → `fill_date` for clarity. This is the
    expected execution date, NOT the intent date.

    Args:
        fill_date: T+1 trading day to reconcile (orders.fill_date == this)
        adapter: optional broker adapter (default: new LiveBroker())

    Returns:
        ReconcileReport
    """
    # Fetch Helios state (using fill_date semantics; C-P0-1 fix)
    helios_orders = order_journal.list_orders_by_fill_date(fill_date)
    helios_positions = _fetch_helios_open_positions()

    # Initialize broker if not provided
    if adapter is None:
        try:
            from execution.live_broker import LiveBroker
            adapter = LiveBroker()
        except Exception as exc:
            logger.error("reconcile_broker_init_failed", error=str(exc))
            report = ReconcileReport(as_of=fill_date, mode="no_broker")
            report.helios_orders_total = len(helios_orders)
            report.helios_positions_total = len(helios_positions)
            report.add(
                category="reconcile_setup", severity="warning",
                order_id=None, broker_order_id=None, symbol="-",
                detail=f"Broker init failed: {exc}. Degraded to no-broker mode.",
            )
            return report

    # Fetch broker state via adapter
    broker_trades: list[dict] = []
    broker_holdings: list[dict] = []
    broker_unavailable = False
    try:
        with adapter.login_session() as session:
            broker_trades = adapter.fetch_trades(session, fill_date)
            broker_holdings = adapter.fetch_holdings(session)
    except BrokerAdapterError as exc:
        logger.warning("reconcile_broker_login_failed", error=str(exc))
        broker_unavailable = True
    except Exception as exc:  # noqa: BLE001
        logger.error("reconcile_broker_session_failed", error=str(exc))
        broker_unavailable = True

    if broker_unavailable:
        report = ReconcileReport(as_of=fill_date, mode="no_broker")
        report.helios_orders_total = len(helios_orders)
        report.helios_positions_total = len(helios_positions)
        report.add(
            category="reconcile_setup", severity="warning",
            order_id=None, broker_order_id=None, symbol="-",
            detail="Broker login/session failed. Cannot fetch trades/holdings.",
        )
        return report

    # v2 (K-P2-f): sim_fallback only when broker_trades empty AND
    # FILLED/PARTIAL orders exist (NOT SUBMITTED — SUBMITTED with empty
    # broker trades is normal pre-market state).
    is_simulation = (
        hasattr(adapter, "_simulation") and getattr(adapter, "_simulation", False)
    )
    expecting_trades = any(
        o.status in (OrderStatus.FILLED, OrderStatus.PARTIAL)
        for o in helios_orders
    )
    sim_fallback = (
        is_simulation
        and not broker_trades
        and expecting_trades
    )

    report = ReconcileReport(
        as_of=fill_date,
        mode="two_way_sim_fallback" if sim_fallback else "three_way",
    )
    report.helios_orders_total = len(helios_orders)
    report.helios_positions_total = len(helios_positions)
    report.broker_trades_total = len(broker_trades)
    report.broker_holdings_total = len(broker_holdings)

    if sim_fallback:
        n_filled = sum(
            1 for o in helios_orders if o.status is OrderStatus.FILLED
        )
        n_partial = sum(
            1 for o in helios_orders if o.status is OrderStatus.PARTIAL
        )
        report.add(
            category="reconcile_setup", severity="warning",
            order_id=None, broker_order_id=None, symbol="-",
            detail=(
                f"Sim mode returned no broker trades but Helios has "
                f"{n_filled} FILLED and {n_partial} PARTIAL orders for "
                f"fill_date={fill_date}. Skipping Axis A (orders↔trades); "
                f"running Axis B (positions↔holdings) only."
            ),
        )
    else:
        _reconcile_orders_vs_trades(helios_orders, broker_trades, report)
        _reconcile_transport_verifications(report, broker_trades)

    # Axis B always runs
    _reconcile_positions_vs_holdings(helios_positions, broker_holdings, report)

    return report


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


def _send_telegram_alert(report: ReconcileReport) -> None:
    """Send Telegram alert for reconcile result.

    Imports done locally to avoid hard dependency on telegram module at
    module level.
    """
    try:
        from communication.telegram.sender import push_simple
        from communication.telegram.bot import get_bot
        bot = get_bot()
        push_simple(bot, report.to_telegram())
    except Exception as exc:  # noqa: BLE001
        logger.error("reconcile_telegram_send_failed", error=str(exc))


def main() -> int:
    parser = argparse.ArgumentParser(description="v0.1.16 fill reconciliation")
    parser.add_argument(
        "--as-of", type=str, default=None,
        help=(
            "fill_date to reconcile (YYYY-MM-DD). Orders with "
            "fill_date == this are checked. Default = today's date."
        ),
    )
    parser.add_argument(
        "--send-telegram", action="store_true",
        help="Send Telegram alert on critical findings (D-P2-b).",
    )
    args = parser.parse_args()

    fill_date = (
        date_type.fromisoformat(args.as_of) if args.as_of
        else date_type.today()
    )

    print(f"Helios reconcile_fills — {datetime.now().isoformat(timespec='seconds')}")
    print(f"Reconcile fill_date: {fill_date}")
    print()

    report = reconcile(fill_date)
    print(report.to_console())

    if report.has_critical():
        print("⚠️  CRITICAL findings detected — operator review required.")
        if args.send_telegram:
            _send_telegram_alert(report)
        return 1
    if args.send_telegram and report.findings:
        # Non-critical but findings exist — send concise summary
        _send_telegram_alert(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
