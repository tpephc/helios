# storage/orders.py
"""訂單 event log。

Append-only：訂單從 submitted → filled/partial/cancelled/rejected。
每次狀態變化都 UPDATE 該 row (而非新增)；歷史軌跡靠 timestamp 與 metadata.history 保留。

Version: v0.1.1 (2026-05-16)
Changelog:
  v0.1.1 (2026-05-16): has_duplicate_recent 新增 exclude_order_id 參數，允許事後驗證
  v0.1.0 (2026-05-16): Initial implementation
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from data.database import connect
from utils.logger import get_logger

logger = get_logger(__name__)


OrderSide = Literal["buy", "sell"]
OrderType = Literal["market", "limit"]
OrderStatus = Literal["submitted", "filled", "partial", "rejected", "cancelled"]


@dataclass
class OrderRow:
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
# Create / Update
# ─────────────────────────────────────────────────────────────


def record_order(
    symbol: str,
    side: OrderSide,
    quantity: int,
    *,
    order_type: OrderType = "market",
    price: float | None = None,
    signal_id: str | None = None,
    broker: str = "paper",
    metadata: dict | None = None,
) -> str:
    """建立新訂單 (status=submitted)，回傳 order_id。"""
    order_id = str(uuid.uuid4())
    now = datetime.now()

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO orders (
                order_id, signal_id, timestamp, symbol, side, order_type,
                quantity, price, status, broker, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'submitted', ?, ?)
            """,
            [
                order_id, signal_id, now, symbol, side, order_type,
                quantity, price, broker, json.dumps(metadata or {}, ensure_ascii=False),
            ],
        )

    logger.info(
        "order_submitted",
        order_id=order_id, symbol=symbol, side=side,
        quantity=quantity, broker=broker, signal_id=signal_id,
    )
    return order_id


def update_order_status(
    order_id: str,
    status: OrderStatus,
    *,
    filled_qty: int | None = None,
    avg_price: float | None = None,
    commission: float | None = None,
    tax: float | None = None,
) -> bool:
    """更新訂單狀態 (filled / partial / cancelled / rejected)。"""
    updates = ["status = ?"]
    params: list = [status]

    if filled_qty is not None:
        updates.append("filled_qty = ?")
        params.append(filled_qty)
    if avg_price is not None:
        updates.append("avg_price = ?")
        params.append(avg_price)
    if commission is not None:
        updates.append("commission = ?")
        params.append(commission)
    if tax is not None:
        updates.append("tax = ?")
        params.append(tax)

    params.append(order_id)

    with connect() as conn:
        conn.execute(
            f"UPDATE orders SET {', '.join(updates)} WHERE order_id = ?", params
        )
        row = conn.execute(
            "SELECT status FROM orders WHERE order_id = ?", [order_id]
        ).fetchone()

    if row is None:
        logger.warning("order_update_not_found", order_id=order_id)
        return False

    logger.info(
        "order_status_updated",
        order_id=order_id, status=status,
        filled_qty=filled_qty, avg_price=avg_price,
    )
    return True


# ─────────────────────────────────────────────────────────────
# Read
# ─────────────────────────────────────────────────────────────


def get_order(order_id: str) -> OrderRow | None:
    with connect(read_only=True) as conn:
        row = conn.execute("SELECT * FROM orders WHERE order_id = ?", [order_id]).fetchone()
        cols = [c[0] for c in conn.description]
    if not row:
        return None
    return _row_to_dataclass(dict(zip(cols, row, strict=True)))


def get_open_orders() -> list[OrderRow]:
    """submitted 或 partial 狀態的訂單。"""
    with connect(read_only=True) as conn:
        rows = conn.execute(
            """
            SELECT * FROM orders
            WHERE status IN ('submitted', 'partial')
            ORDER BY timestamp ASC
            """
        ).fetchall()
        cols = [c[0] for c in conn.description]
    return [_row_to_dataclass(dict(zip(cols, r, strict=True))) for r in rows]


def get_orders_for_signal(signal_id: str) -> list[OrderRow]:
    with connect(read_only=True) as conn:
        rows = conn.execute(
            "SELECT * FROM orders WHERE signal_id = ? ORDER BY timestamp ASC", [signal_id]
        ).fetchall()
        cols = [c[0] for c in conn.description]
    return [_row_to_dataclass(dict(zip(cols, r, strict=True))) for r in rows]


def get_filled_orders_since(since: datetime) -> list[OrderRow]:
    """從某時間點之後的成交單 (positions 計算用)。"""
    with connect(read_only=True) as conn:
        rows = conn.execute(
            """
            SELECT * FROM orders
            WHERE status IN ('filled', 'partial')
              AND timestamp >= ?
            ORDER BY timestamp ASC
            """,
            [since],
        ).fetchall()
        cols = [c[0] for c in conn.description]
    return [_row_to_dataclass(dict(zip(cols, r, strict=True))) for r in rows]


# ─────────────────────────────────────────────────────────────
# Duplicate detection (per circuit_breaker.duplicate_order_window_sec)
# ─────────────────────────────────────────────────────────────


def has_duplicate_recent(
    symbol: str,
    side: OrderSide,
    window_seconds: int = 10,
    exclude_order_id: str | None = None,
) -> bool:
    """偵測短時間內重複下單（同 symbol + side），用於熔斷防呆。

    Args:
        symbol: 股票代碼
        side: buy / sell
        window_seconds: 偵測窗口
        exclude_order_id: 排除這筆訂單 (通常是剛 record 完想做事後驗證時傳入自己的 order_id，
                          避免把自己當成 duplicate)

    Returns:
        True = 窗口內有另一筆同向訂單存在 (已排除 cancelled / rejected / exclude_order_id)
    """
    from datetime import timedelta
    since = datetime.now() - timedelta(seconds=window_seconds)
    with connect(read_only=True) as conn:
        if exclude_order_id is not None:
            row = conn.execute(
                """
                SELECT COUNT(*) FROM orders
                WHERE symbol = ? AND side = ? AND timestamp >= ?
                  AND status NOT IN ('rejected', 'cancelled')
                  AND order_id != ?
                """,
                [symbol, side, since, exclude_order_id],
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT COUNT(*) FROM orders
                WHERE symbol = ? AND side = ? AND timestamp >= ?
                  AND status NOT IN ('rejected', 'cancelled')
                """,
                [symbol, side, since],
            ).fetchone()
    return bool(row and row[0] > 0)


# ─────────────────────────────────────────────────────────────
# Internals
# ─────────────────────────────────────────────────────────────


def _row_to_dataclass(d: dict) -> OrderRow:
    metadata_raw = d.get("metadata")
    metadata = json.loads(metadata_raw) if isinstance(metadata_raw, str) else (metadata_raw or {})

    return OrderRow(
        order_id=d["order_id"],
        signal_id=d.get("signal_id"),
        timestamp=d["timestamp"],
        symbol=d["symbol"],
        side=d["side"],
        order_type=d["order_type"],
        quantity=d["quantity"],
        price=d.get("price"),
        status=d["status"],
        filled_qty=d.get("filled_qty") or 0,
        avg_price=d.get("avg_price"),
        commission=d.get("commission") or 0.0,
        tax=d.get("tax") or 0.0,
        broker=d.get("broker") or "paper",
        metadata=metadata,
    )


# ─────────────────────────────────────────────────────────────
# Smoke test
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from data.database import init_schema
    init_schema()

    oid = record_order("2330", "buy", 1000, order_type="market", broker="paper")
    print(f"Created order: {oid}")

    update_order_status(
        oid, "filled", filled_qty=1000, avg_price=985.5,
        commission=1404.94, tax=0.0,
    )
    o = get_order(oid)
    print(f"Final: {o.status}, avg_price={o.avg_price}, commission={o.commission}")

    print(f"Open orders: {len(get_open_orders())}")
    print(f"Duplicate? {has_duplicate_recent('2330', 'buy', window_seconds=10)}")
