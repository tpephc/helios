# storage/positions.py
"""Positions storage — first-class state machine for v0.1.14.2 paper trading.

ARCHITECTURE.md §6.5 State Machine: OPENING → OPEN → CLOSING → CLOSED.

Replaces the previous event-sourced derive-from-orders approach because
v0.1.14.2 needs stateful per-position fields (max_close_since_entry,
regime_at_entry, MFE/MAE) that cannot cleanly come from orders alone.

State transitions:
  open_position()                  -> creates row, status=OPENING (or OPEN for instant paper fills)
  mark_position_open(position_id)  -> OPENING → OPEN (after fill confirmed)
  update_running_stats(...)        -> daily update of last_close, max/min_close, dates
  start_closing(position_id)       -> OPEN → CLOSING (sell submitted)
  mark_position_closed(...)        -> CLOSING → CLOSED (with exit fields)

Per review #1 (2026-05-17): adds regime_at_entry column. max_drawdown_pct is
computed (not stored) from last_close vs max_close_since_entry.

Version: v0.2.0 (2026-05-17)
Changelog:
  v0.2.0 (2026-05-17): Full rewrite for v0.1.14.2 paper trading state machine
  v0.1.x (2026-05-16): Legacy event-sourced (replaced)
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime
from typing import Any

from data.database import connect
from utils.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────
# State enum (kept as strings for DB simplicity)
# ─────────────────────────────────────────────────────────────

OPENING = "OPENING"
OPEN = "OPEN"
CLOSING = "CLOSING"
CLOSED = "CLOSED"

VALID_STATUSES = {OPENING, OPEN, CLOSING, CLOSED}


# Allowed transitions (per ARCHITECTURE §6.5 state machine)
ALLOWED_TRANSITIONS = {
    OPENING: {OPEN},                # buy fill confirmed
    OPEN:    {CLOSING, CLOSED},     # exit triggered (CLOSING for live broker; instant CLOSED for paper)
    CLOSING: {CLOSED},              # sell fill confirmed
    CLOSED:  set(),                 # terminal
}


# ─────────────────────────────────────────────────────────────
# Position dataclass (read model)
# ─────────────────────────────────────────────────────────────


@dataclass
class Position:
    position_id: str
    entry_signal_id: str | None
    entry_order_id: str | None
    exit_signal_id: str | None
    exit_order_id: str | None

    symbol: str
    strategy: str

    # Entry context
    entry_date: date_type
    entry_price: float
    entry_atr: float
    regime_at_entry: str
    sector: str
    is_etf: bool

    # Sizing
    shares: int
    notional_at_entry: float
    entry_commission: float
    entry_slippage_cost: float

    # Running stats
    last_close: float | None
    last_updated_date: date_type | None
    max_close_since_entry: float | None
    max_close_date: date_type | None
    min_close_since_entry: float | None
    min_close_date: date_type | None

    # Exit fields
    exit_date: date_type | None
    exit_price: float | None
    exit_reason: str | None
    regime_at_exit: str | None
    exit_commission: float
    exit_tax: float
    exit_slippage_cost: float
    exit_proceeds: float | None

    status: str
    created_at: datetime
    updated_at: datetime

    # ── Computed properties ──────────────────────────────────

    @property
    def mfe_pct(self) -> float | None:
        if self.max_close_since_entry is None or self.entry_price <= 0:
            return None
        return (self.max_close_since_entry / self.entry_price - 1) * 100

    @property
    def mae_pct(self) -> float | None:
        if self.min_close_since_entry is None or self.entry_price <= 0:
            return None
        return (self.min_close_since_entry / self.entry_price - 1) * 100

    @property
    def current_drawdown_pct(self) -> float | None:
        """Per review #1: max drawdown from peak (for circuit breaker)."""
        if (self.last_close is None or self.max_close_since_entry is None
                or self.max_close_since_entry <= 0):
            return None
        return (self.last_close / self.max_close_since_entry - 1) * 100

    @property
    def unrealized_pnl_ntd(self) -> float | None:
        if self.last_close is None:
            return None
        return self.shares * (self.last_close - self.entry_price)

    @property
    def unrealized_pnl_pct(self) -> float | None:
        if self.last_close is None or self.entry_price <= 0:
            return None
        return (self.last_close / self.entry_price - 1) * 100

    @property
    def gross_return_pct(self) -> float | None:
        """For CLOSED positions: (exit-entry)/entry, gross (no costs)."""
        if self.exit_price is None or self.entry_price <= 0:
            return None
        return (self.exit_price / self.entry_price - 1) * 100

    @property
    def net_pnl_ntd(self) -> float | None:
        """For CLOSED positions: proceeds - notional_at_entry - all costs."""
        if self.exit_proceeds is None:
            return None
        gross_cost = self.notional_at_entry + self.entry_commission + self.entry_slippage_cost
        return self.exit_proceeds - gross_cost

    @property
    def holding_days(self) -> int | None:
        if self.exit_date is None:
            return None
        return (self.exit_date - self.entry_date).days

    @property
    def is_open(self) -> bool:
        return self.status in {OPENING, OPEN, CLOSING}


# ─────────────────────────────────────────────────────────────
# Write operations
# ─────────────────────────────────────────────────────────────


def open_position(
    *,
    symbol: str,
    strategy: str,
    entry_date: date_type,
    entry_price: float,
    entry_atr: float,
    regime_at_entry: str,
    sector: str,
    is_etf: bool,
    shares: int,
    notional_at_entry: float,
    entry_commission: float = 0.0,
    entry_slippage_cost: float = 0.0,
    entry_signal_id: str | None = None,
    entry_order_id: str | None = None,
    status: str = OPEN,             # paper broker fills instantly; default OPEN
) -> str:
    """Insert a new position row. Returns position_id."""
    if status not in {OPENING, OPEN}:
        raise ValueError(
            f"open_position must start with OPENING or OPEN, got {status}"
        )
    position_id = f"pos_{uuid.uuid4().hex[:12]}"

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO positions (
                position_id, entry_signal_id, entry_order_id,
                symbol, strategy,
                entry_date, entry_price, entry_atr, regime_at_entry,
                sector, is_etf,
                shares, notional_at_entry, entry_commission, entry_slippage_cost,
                last_close, last_updated_date,
                max_close_since_entry, max_close_date,
                min_close_since_entry, min_close_date,
                status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                position_id, entry_signal_id, entry_order_id,
                symbol, strategy,
                entry_date, entry_price, entry_atr, regime_at_entry,
                sector, is_etf,
                shares, notional_at_entry, entry_commission, entry_slippage_cost,
                # running stats initialized to entry values
                entry_price, entry_date,
                entry_price, entry_date,
                entry_price, entry_date,
                status,
            ],
        )

    logger.info(
        "position_opened",
        position_id=position_id, symbol=symbol, shares=shares,
        entry_price=entry_price, regime_at_entry=regime_at_entry, status=status,
    )
    return position_id


def mark_position_open(position_id: str) -> None:
    """Transition OPENING → OPEN (after fill confirmed)."""
    _transition(position_id, expected_from=OPENING, to_status=OPEN)


def update_running_stats(
    position_id: str, *, close: float, as_of: date_type
) -> None:
    """Daily update of last_close + max/min trackers.

    Called once per trading day for each OPEN position.
    Updates max_close_since_entry only if new close > current max.
    Updates min_close_since_entry only if new close < current min.
    """
    with connect() as conn:
        # Read current state
        row = conn.execute(
            """
            SELECT max_close_since_entry, min_close_since_entry, status
            FROM positions WHERE position_id = ?
            """,
            [position_id],
        ).fetchone()
        if row is None:
            raise ValueError(f"position not found: {position_id}")
        cur_max, cur_min, status = row
        if status != OPEN:
            logger.warning(
                "skip_update_non_open",
                position_id=position_id, status=status,
            )
            return

        new_max = close if cur_max is None or close > cur_max else cur_max
        new_max_date = as_of if cur_max is None or close > cur_max else None
        new_min = close if cur_min is None or close < cur_min else cur_min
        new_min_date = as_of if cur_min is None or close < cur_min else None

        # Conditional update — only touch max_close_date if max changed
        conn.execute(
            """
            UPDATE positions SET
                last_close = ?,
                last_updated_date = ?,
                max_close_since_entry = ?,
                max_close_date = COALESCE(?, max_close_date),
                min_close_since_entry = ?,
                min_close_date = COALESCE(?, min_close_date),
                updated_at = CURRENT_TIMESTAMP
            WHERE position_id = ?
            """,
            [close, as_of, new_max, new_max_date, new_min, new_min_date, position_id],
        )


def start_closing(position_id: str) -> None:
    """Transition OPEN → CLOSING (sell order submitted, awaiting fill)."""
    _transition(position_id, expected_from=OPEN, to_status=CLOSING)


def mark_position_closed(
    position_id: str, *,
    exit_date: date_type,
    exit_price: float,
    exit_reason: str,
    regime_at_exit: str,
    exit_commission: float = 0.0,
    exit_tax: float = 0.0,
    exit_slippage_cost: float = 0.0,
    exit_proceeds: float = 0.0,
    exit_signal_id: str | None = None,
    exit_order_id: str | None = None,
) -> None:
    """Transition (OPEN | CLOSING) → CLOSED with exit fields populated.

    Paper broker fills instantly so OPEN → CLOSED is allowed (skipping CLOSING).
    """
    with connect() as conn:
        row = conn.execute(
            "SELECT status FROM positions WHERE position_id = ?",
            [position_id],
        ).fetchone()
        if row is None:
            raise ValueError(f"position not found: {position_id}")
        current = row[0]
        if CLOSED not in ALLOWED_TRANSITIONS.get(current, set()):
            raise ValueError(
                f"invalid transition {current} → CLOSED for {position_id}"
            )

        conn.execute(
            """
            UPDATE positions SET
                status = ?,
                exit_date = ?, exit_price = ?, exit_reason = ?,
                regime_at_exit = ?,
                exit_commission = ?, exit_tax = ?, exit_slippage_cost = ?,
                exit_proceeds = ?,
                exit_signal_id = COALESCE(?, exit_signal_id),
                exit_order_id  = COALESCE(?, exit_order_id),
                updated_at = CURRENT_TIMESTAMP
            WHERE position_id = ?
            """,
            [
                CLOSED, exit_date, exit_price, exit_reason, regime_at_exit,
                exit_commission, exit_tax, exit_slippage_cost, exit_proceeds,
                exit_signal_id, exit_order_id, position_id,
            ],
        )

    logger.info(
        "position_closed",
        position_id=position_id, exit_price=exit_price, exit_reason=exit_reason,
    )


def _transition(position_id: str, *, expected_from: str, to_status: str) -> None:
    """Internal: enforce state machine transition."""
    if to_status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {to_status}")
    with connect() as conn:
        row = conn.execute(
            "SELECT status FROM positions WHERE position_id = ?",
            [position_id],
        ).fetchone()
        if row is None:
            raise ValueError(f"position not found: {position_id}")
        current = row[0]
        if current != expected_from:
            raise ValueError(
                f"expected status {expected_from}, got {current} for {position_id}"
            )
        if to_status not in ALLOWED_TRANSITIONS[current]:
            raise ValueError(
                f"invalid transition {current} → {to_status} for {position_id}"
            )
        conn.execute(
            "UPDATE positions SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE position_id = ?",
            [to_status, position_id],
        )

    logger.info(
        "position_state_transition",
        position_id=position_id, from_status=current, to_status=to_status,
    )


# ─────────────────────────────────────────────────────────────
# Read operations
# ─────────────────────────────────────────────────────────────


def get_position(position_id: str) -> Position | None:
    """Single lookup."""
    with connect(read_only=True) as conn:
        row = conn.execute(
            "SELECT * FROM positions WHERE position_id = ?", [position_id]
        ).fetchone()
    if row is None:
        return None
    return _row_to_position(row)


def get_open_positions(symbol: str | None = None) -> list[Position]:
    """All currently open positions (status in OPENING/OPEN/CLOSING)."""
    with connect(read_only=True) as conn:
        if symbol:
            rows = conn.execute(
                """
                SELECT * FROM positions
                WHERE status IN ('OPENING', 'OPEN', 'CLOSING')
                  AND symbol = ?
                ORDER BY entry_date, position_id
                """,
                [symbol],
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM positions
                WHERE status IN ('OPENING', 'OPEN', 'CLOSING')
                ORDER BY entry_date, position_id
                """
            ).fetchall()
    return [_row_to_position(r) for r in rows]


def get_closed_positions(limit: int | None = None) -> list[Position]:
    """Historical closed positions (newest first)."""
    sql = """
        SELECT * FROM positions WHERE status = 'CLOSED'
        ORDER BY exit_date DESC, position_id
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    with connect(read_only=True) as conn:
        rows = conn.execute(sql).fetchall()
    return [_row_to_position(r) for r in rows]


def has_open_position(symbol: str) -> bool:
    """Quick check — used by selector to enforce symbol_already_held."""
    with connect(read_only=True) as conn:
        n = conn.execute(
            """
            SELECT COUNT(*) FROM positions
            WHERE status IN ('OPENING', 'OPEN', 'CLOSING') AND symbol = ?
            """,
            [symbol],
        ).fetchone()[0]
    return n > 0


def _row_to_position(row: tuple[Any, ...]) -> Position:
    """Map a positions row (full SELECT *) to Position dataclass."""
    return Position(
        position_id=row[0],
        entry_signal_id=row[1],
        entry_order_id=row[2],
        exit_signal_id=row[3],
        exit_order_id=row[4],
        symbol=row[5],
        strategy=row[6],
        entry_date=row[7],
        entry_price=row[8],
        entry_atr=row[9],
        regime_at_entry=row[10],
        sector=row[11],
        is_etf=row[12],
        shares=row[13],
        notional_at_entry=row[14],
        entry_commission=row[15],
        entry_slippage_cost=row[16],
        last_close=row[17],
        last_updated_date=row[18],
        max_close_since_entry=row[19],
        max_close_date=row[20],
        min_close_since_entry=row[21],
        min_close_date=row[22],
        exit_date=row[23],
        exit_price=row[24],
        exit_reason=row[25],
        regime_at_exit=row[26],
        exit_commission=row[27],
        exit_tax=row[28],
        exit_slippage_cost=row[29],
        exit_proceeds=row[30],
        status=row[31],
        created_at=row[32],
        updated_at=row[33],
    )
