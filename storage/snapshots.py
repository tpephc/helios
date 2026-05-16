# storage/snapshots.py
"""每日狀態快照。

用途：
- 系統重啟後快速恢復狀態 (不必從頭重播所有 orders)
- 績效報表的時間序列基礎
- Drawdown / 回撤計算

設計：每日一筆 (PRIMARY KEY date)，包含當日 EOD 整體投資組合快照。

Version: v0.1.0 (2026-05-16)
Changelog:
  v0.1.0 (2026-05-16): Initial implementation
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime

from data.database import connect
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SnapshotRow:
    snapshot_date: date
    portfolio_value: float
    cash: float
    total_exposure: float
    positions: dict             # {symbol: {quantity, avg_cost, realized_pnl}}
    regime: str | None
    drawdown: float | None
    pending_approvals: int
    created_at: datetime


# ─────────────────────────────────────────────────────────────
# Write
# ─────────────────────────────────────────────────────────────


def save_snapshot(
    snapshot_date: date,
    portfolio_value: float,
    cash: float,
    total_exposure: float,
    positions: dict,
    *,
    regime: str | None = None,
    drawdown: float | None = None,
    pending_approvals: int = 0,
) -> None:
    """寫入 (或覆寫) 某日快照。同日重複寫入會 REPLACE。"""
    with connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO snapshots (
                snapshot_date, portfolio_value, cash, total_exposure,
                positions, regime, drawdown, pending_approvals, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            [
                snapshot_date, portfolio_value, cash, total_exposure,
                json.dumps(positions, ensure_ascii=False),
                regime, drawdown, pending_approvals,
            ],
        )

    logger.info(
        "snapshot_saved",
        date=str(snapshot_date),
        portfolio_value=portfolio_value,
        exposure=total_exposure,
        positions_count=len(positions),
        regime=regime,
    )


# ─────────────────────────────────────────────────────────────
# Read
# ─────────────────────────────────────────────────────────────


def load_latest() -> SnapshotRow | None:
    """最新一筆 snapshot (用於系統恢復)。"""
    with connect(read_only=True) as conn:
        row = conn.execute(
            "SELECT * FROM snapshots ORDER BY snapshot_date DESC LIMIT 1"
        ).fetchone()
        cols = [c[0] for c in conn.description]
    if not row:
        return None
    return _row_to_dataclass(dict(zip(cols, row, strict=True)))


def load_for_date(d: date) -> SnapshotRow | None:
    with connect(read_only=True) as conn:
        row = conn.execute(
            "SELECT * FROM snapshots WHERE snapshot_date = ?", [d]
        ).fetchone()
        cols = [c[0] for c in conn.description]
    if not row:
        return None
    return _row_to_dataclass(dict(zip(cols, row, strict=True)))


def load_range(start: date, end: date) -> list[SnapshotRow]:
    """區間 snapshot 序列 (報表 / drawdown 計算用)。"""
    with connect(read_only=True) as conn:
        rows = conn.execute(
            """
            SELECT * FROM snapshots
            WHERE snapshot_date BETWEEN ? AND ?
            ORDER BY snapshot_date ASC
            """,
            [start, end],
        ).fetchall()
        cols = [c[0] for c in conn.description]
    return [_row_to_dataclass(dict(zip(cols, r, strict=True))) for r in rows]


# ─────────────────────────────────────────────────────────────
# Derived metrics
# ─────────────────────────────────────────────────────────────


def compute_drawdown_from_peak(end_date: date | None = None) -> float:
    """從歷史最高點計算目前回撤百分比 (0.0 ~ 1.0)。"""
    end_date = end_date or date.today()
    with connect(read_only=True) as conn:
        row = conn.execute(
            """
            WITH series AS (
                SELECT snapshot_date, portfolio_value,
                       MAX(portfolio_value) OVER (
                           ORDER BY snapshot_date
                           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                       ) AS running_peak
                FROM snapshots
                WHERE snapshot_date <= ?
            )
            SELECT portfolio_value, running_peak
            FROM series
            ORDER BY snapshot_date DESC
            LIMIT 1
            """,
            [end_date],
        ).fetchone()

    if not row:
        return 0.0
    current, peak = row
    if not peak or peak <= 0:
        return 0.0
    return max(0.0, (peak - current) / peak)


# ─────────────────────────────────────────────────────────────
# Internals
# ─────────────────────────────────────────────────────────────


def _row_to_dataclass(d: dict) -> SnapshotRow:
    positions_raw = d.get("positions")
    positions = json.loads(positions_raw) if isinstance(positions_raw, str) else (positions_raw or {})

    return SnapshotRow(
        snapshot_date=d["snapshot_date"],
        portfolio_value=d["portfolio_value"],
        cash=d["cash"],
        total_exposure=d["total_exposure"],
        positions=positions,
        regime=d.get("regime"),
        drawdown=d.get("drawdown"),
        pending_approvals=d.get("pending_approvals") or 0,
        created_at=d["created_at"],
    )


# ─────────────────────────────────────────────────────────────
# Smoke test
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from data.database import init_schema
    init_schema()

    save_snapshot(
        snapshot_date=date.today(),
        portfolio_value=520_000,
        cash=380_000,
        total_exposure=140_000,
        positions={
            "0050": {"quantity": 700, "avg_cost": 200.0, "realized_pnl": 0.0},
        },
        regime="strong_bull",
        drawdown=0.0,
        pending_approvals=0,
    )

    snap = load_latest()
    print(f"Latest snapshot: {snap.snapshot_date}")
    print(f"  Portfolio: {snap.portfolio_value:,}")
    print(f"  Positions: {snap.positions}")
    print(f"  Regime: {snap.regime}")
    print(f"\nDrawdown from peak: {compute_drawdown_from_peak() * 100:.2f}%")
