# storage/positions.py
"""持倉計算。

ADR-001 原則：positions 不存獨立表，從 orders 即時計算。
但為了查詢效率，snapshots.py 會把當日 EOD positions 序列化到 snapshots.positions JSON。

計算邏輯：
- 從最新 snapshot 開始 (避免從頭重播)
- 套用 snapshot 之後的所有 filled orders
- 平均成本 (avg_cost) 用 weighted average 維護

Version: v0.1.1 (2026-05-16)
Changelog:
  v0.1.1 (2026-05-16): _apply_fill 過量賣出處理：clamp 到實際持有量 + log warning，避免假 realized_pnl
  v0.1.0 (2026-05-16): Initial implementation
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from storage.orders import OrderRow, get_filled_orders_since
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Position:
    symbol: str
    quantity: int         # 持有數量 (張數 × 1000 股；零股以 share 為單位)
    avg_cost: float       # 平均成本
    realized_pnl: float = 0.0  # 已實現損益 (累計)


# ─────────────────────────────────────────────────────────────
# Computation
# ─────────────────────────────────────────────────────────────


def compute_current_positions(
    initial: dict[str, Position] | None = None,
    since: datetime | None = None,
) -> dict[str, Position]:
    """從 orders 計算當前持倉。

    Args:
        initial: 起始狀態 (通常來自最新 snapshot.positions)。None 表示從 epoch 開始。
        since: 只考慮此時間之後的訂單。配合 initial 使用，避免從頭重播。

    Returns:
        symbol → Position 字典。quantity=0 的會被剔除。
    """
    positions: dict[str, Position] = dict(initial or {})

    fills = get_filled_orders_since(since or datetime(1970, 1, 1))
    for o in fills:
        if o.status not in ("filled", "partial"):
            continue
        _apply_fill(positions, o)

    # 清掉 quantity=0 的部位
    return {s: p for s, p in positions.items() if p.quantity != 0}


def compute_positions_from_latest_snapshot() -> dict[str, Position]:
    """從最新 snapshot 出發計算當前 positions。"""
    from storage.snapshots import load_latest
    snap = load_latest()

    if snap is None:
        return compute_current_positions()

    # snapshot.positions 是 JSON: {symbol: {quantity, avg_cost, realized_pnl}}
    initial = {
        sym: Position(
            symbol=sym,
            quantity=data["quantity"],
            avg_cost=data["avg_cost"],
            realized_pnl=data.get("realized_pnl", 0.0),
        )
        for sym, data in (snap.positions or {}).items()
    }
    # 套用 snapshot 之後的 fills
    return compute_current_positions(initial=initial, since=snap.created_at)


# ─────────────────────────────────────────────────────────────
# Internals
# ─────────────────────────────────────────────────────────────


def _apply_fill(positions: dict[str, Position], o: OrderRow) -> None:
    """把一筆成交套用到 positions 字典 (in-place)。

    過量賣出處理：賣的數量超過持有時，會 log warning 並 clamp 到實際持有量。
    realized_pnl 用 clamp 後的數量計算，避免被「假裝賣超」扭曲。
    Storage 層只做記帳，policy 由 risk 模組強制。
    """
    if o.avg_price is None or o.filled_qty <= 0:
        return

    pos = positions.get(o.symbol, Position(symbol=o.symbol, quantity=0, avg_cost=0.0))

    if o.side == "buy":
        # 加倉：更新平均成本
        total_cost = pos.avg_cost * pos.quantity + o.avg_price * o.filled_qty
        new_qty = pos.quantity + o.filled_qty
        pos.avg_cost = total_cost / new_qty if new_qty != 0 else 0.0
        pos.quantity = new_qty
    elif o.side == "sell":
        # 減倉：實現損益 = (賣價 - 成本) × 數量
        if o.filled_qty > pos.quantity:
            logger.warning(
                "oversell_clamped",
                symbol=o.symbol, order_id=o.order_id,
                current_qty=pos.quantity, sell_qty=o.filled_qty,
                clamped_to=pos.quantity,
                note="storage records actual holding; risk layer should have caught this",
            )
            sell_qty = pos.quantity
        else:
            sell_qty = o.filled_qty

        realized = (o.avg_price - pos.avg_cost) * sell_qty
        pos.realized_pnl += realized
        pos.quantity -= sell_qty
        # 全平倉後 avg_cost 重置
        if pos.quantity == 0:
            pos.avg_cost = 0.0

    positions[o.symbol] = pos


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────


def total_exposure(positions: dict[str, Position], current_prices: dict[str, float]) -> float:
    """以當前市價計算總曝險金額。"""
    return sum(
        p.quantity * current_prices.get(p.symbol, p.avg_cost)
        for p in positions.values()
    )


def position_summary(positions: dict[str, Position]) -> str:
    """便利的字串摘要 (CLI / log 用)。"""
    if not positions:
        return "No positions"
    lines = [f"{p.symbol:8s}  qty={p.quantity:>8d}  avg={p.avg_cost:>10.2f}"
             f"  pnl_realized={p.realized_pnl:>+12.2f}"
             for p in sorted(positions.values(), key=lambda x: x.symbol)]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# Smoke test
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from data.database import init_schema
    from storage.orders import record_order, update_order_status

    init_schema()

    # 模擬幾筆成交
    o1 = record_order("2330", "buy", 1000, broker="paper")
    update_order_status(o1, "filled", filled_qty=1000, avg_price=985.0)

    o2 = record_order("0050", "buy", 5000, broker="paper")
    update_order_status(o2, "filled", filled_qty=5000, avg_price=200.5)

    o3 = record_order("2330", "sell", 500, broker="paper")
    update_order_status(o3, "filled", filled_qty=500, avg_price=1020.0)

    positions = compute_current_positions()
    print(position_summary(positions))

    # 用市價算曝險
    market = {"2330": 1020.0, "0050": 205.0}
    print(f"\nTotal exposure: {total_exposure(positions, market):,.0f}")
