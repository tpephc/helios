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

Version: v0.1.18 (2026-05-28)
Changelog:
  v0.1.18 Batch 2 (2026-05-28): all queries add account_id filter;
    get_position_for_account() scoped getter; open_position requires
    account_id + defensive uniqueness check; all UPDATE-by-PK add
    AND account_id = ? defense-in-depth; _transition gets account_id.
  v0.1.18 Batch 1 (2026-05-28): account_id added to dataclass + schema;
    SELECT * replaced with explicit _POSITION_COLUMNS; _row_to_position
    uses named-column mapping with length guard; is_synthetic/
    bootstrap_batch_id/source_order_id formalized.
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
    account_id: str
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
    # Bootstrap / synthetic fields (formalized in v0.1.18 SCHEMA_SQL)
    is_synthetic: bool = False
    bootstrap_batch_id: str | None = None
    source_order_id: str | None = None

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
# Column mapping (v0.1.18: replaces fragile SELECT * + positional index)
# ─────────────────────────────────────────────────────────────

_POSITION_COLUMNS = [
    "position_id", "account_id",
    "entry_signal_id", "entry_order_id", "exit_signal_id", "exit_order_id",
    "symbol", "strategy",
    "entry_date", "entry_price", "entry_atr", "regime_at_entry",
    "sector", "is_etf",
    "shares", "notional_at_entry", "entry_commission", "entry_slippage_cost",
    "last_close", "last_updated_date",
    "max_close_since_entry", "max_close_date",
    "min_close_since_entry", "min_close_date",
    "exit_date", "exit_price", "exit_reason", "regime_at_exit",
    "exit_commission", "exit_tax", "exit_slippage_cost", "exit_proceeds",
    "status", "created_at", "updated_at",
    "is_synthetic", "bootstrap_batch_id", "source_order_id",
]

_SELECT_POSITIONS = f"SELECT {', '.join(_POSITION_COLUMNS)} FROM positions"


# ─────────────────────────────────────────────────────────────
# Scoped getters
# ─────────────────────────────────────────────────────────────


def get_position(position_id: str) -> Position | None:
    """Single lookup by PK. Returns None if not found.

    PK is globally unique — no account_id filter needed. For
    account-scoped operations, use get_position_for_account().
    """
    with connect(read_only=True) as conn:
        row = conn.execute(
            f"{_SELECT_POSITIONS} WHERE position_id = ?", [position_id]
        ).fetchone()
    if row is None:
        return None
    return _row_to_position(row)


def get_position_for_account(
    position_id: str,
    *,
    account_id: str,
) -> Position:
    """Fetch one position by PK and verify account ownership.

    v0.1.18: all write methods use this to fail-fast on account_id
    mismatch BEFORE executing any UPDATE. Mirrors order_journal's
    get_for_account() pattern.

    Raises:
        ValueError: if position_id does not exist OR belongs to a
            different account (intentionally same exception to avoid
            leaking cross-account existence).
    """
    pos = get_position(position_id)
    if pos is None or pos.account_id != account_id:
        raise ValueError(
            f"position not found: {position_id} "
            f"for account_id={account_id}"
        )
    return pos


# ─────────────────────────────────────────────────────────────
# Write operations
# ─────────────────────────────────────────────────────────────


def open_position(
    *,
    account_id: str,
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
    """Insert a new position row. Returns position_id.

    v0.1.18: account_id is now required. Defensive uniqueness check
    prevents duplicate open positions for the same symbol within an
    account (caller bug if this fires).
    """
    if status not in {OPENING, OPEN}:
        raise ValueError(
            f"open_position must start with OPENING or OPEN, got {status}"
        )

    # Defensive uniqueness: prevent duplicate open positions for same
    # symbol in same account. This is a caller-side invariant; the DB
    # has no UNIQUE constraint on (account_id, symbol, status) because
    # CLOSED positions legitimately repeat.
    with connect(read_only=True) as conn:
        existing = conn.execute(
            """
            SELECT COUNT(*) FROM positions
            WHERE account_id = ? AND symbol = ?
              AND status IN ('OPENING', 'OPEN', 'CLOSING')
            """,
            [account_id, symbol],
        ).fetchone()[0]
    if existing > 0:
        raise ValueError(
            f"open_position: account {account_id} already has {existing} "
            f"open position(s) for {symbol}. Close existing before opening new."
        )

    position_id = f"pos_{uuid.uuid4().hex[:12]}"

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO positions (
                position_id, account_id, entry_signal_id, entry_order_id,
                symbol, strategy,
                entry_date, entry_price, entry_atr, regime_at_entry,
                sector, is_etf,
                shares, notional_at_entry, entry_commission, entry_slippage_cost,
                last_close, last_updated_date,
                max_close_since_entry, max_close_date,
                min_close_since_entry, min_close_date,
                status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                position_id, account_id, entry_signal_id, entry_order_id,
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
        position_id=position_id, account_id=account_id,
        symbol=symbol, shares=shares,
        entry_price=entry_price, regime_at_entry=regime_at_entry, status=status,
    )
    return position_id


def mark_position_open(position_id: str, *, account_id: str) -> None:
    """Transition OPENING → OPEN (after fill confirmed)."""
    _transition(
        position_id, expected_from=OPENING, to_status=OPEN,
        account_id=account_id,
    )


def update_running_stats(
    position_id: str,
    *,
    close: float,
    as_of: date_type,
    account_id: str,
) -> None:
    """Daily update of last_close + max/min trackers.

    Called once per trading day for each OPEN position.
    Updates max_close_since_entry only if new close > current max.
    Updates min_close_since_entry only if new close < current min.
    """
    # Verify ownership before touching DB
    pos = get_position_for_account(position_id, account_id=account_id)
    if pos.status != OPEN:
        logger.warning(
            "skip_update_non_open",
            position_id=position_id, account_id=account_id,
            status=pos.status,
        )
        return

    cur_max = pos.max_close_since_entry
    cur_min = pos.min_close_since_entry

    new_max = close if cur_max is None or close > cur_max else cur_max
    new_max_date = as_of if cur_max is None or close > cur_max else None
    new_min = close if cur_min is None or close < cur_min else cur_min
    new_min_date = as_of if cur_min is None or close < cur_min else None

    with connect() as conn:
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
            WHERE position_id = ? AND account_id = ?
            """,
            [close, as_of, new_max, new_max_date, new_min, new_min_date,
             position_id, account_id],
        )


def start_closing(position_id: str, *, account_id: str) -> None:
    """Transition OPEN → CLOSING (sell order submitted, awaiting fill)."""
    _transition(
        position_id, expected_from=OPEN, to_status=CLOSING,
        account_id=account_id,
    )


def mark_position_closed(
    position_id: str, *,
    account_id: str,
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
    pos = get_position_for_account(position_id, account_id=account_id)
    if CLOSED not in ALLOWED_TRANSITIONS.get(pos.status, set()):
        raise ValueError(
            f"invalid transition {pos.status} → CLOSED for {position_id}"
        )

    with connect() as conn:
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
            WHERE position_id = ? AND account_id = ?
            """,
            [
                CLOSED, exit_date, exit_price, exit_reason, regime_at_exit,
                exit_commission, exit_tax, exit_slippage_cost, exit_proceeds,
                exit_signal_id, exit_order_id, position_id, account_id,
            ],
        )

    logger.info(
        "position_closed",
        position_id=position_id, account_id=account_id,
        exit_price=exit_price, exit_reason=exit_reason,
    )


def _transition(
    position_id: str,
    *,
    expected_from: str,
    to_status: str,
    account_id: str,
) -> None:
    """Internal: enforce state machine transition with account ownership check."""
    if to_status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {to_status}")

    pos = get_position_for_account(position_id, account_id=account_id)
    if pos.status != expected_from:
        raise ValueError(
            f"expected status {expected_from}, got {pos.status} for {position_id}"
        )
    if to_status not in ALLOWED_TRANSITIONS[pos.status]:
        raise ValueError(
            f"invalid transition {pos.status} → {to_status} for {position_id}"
        )

    with connect() as conn:
        conn.execute(
            """
            UPDATE positions SET
                status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE position_id = ? AND account_id = ?
            """,
            [to_status, position_id, account_id],
        )

    logger.info(
        "position_state_transition",
        position_id=position_id, account_id=account_id,
        from_status=pos.status, to_status=to_status,
    )


# ─────────────────────────────────────────────────────────────
# Read operations
# ─────────────────────────────────────────────────────────────


def get_open_positions(
    *,
    account_id: str,
    symbol: str | None = None,
) -> list[Position]:
    """All currently open positions for an account (status in OPENING/OPEN/CLOSING)."""
    with connect(read_only=True) as conn:
        if symbol:
            rows = conn.execute(
                f"""
                {_SELECT_POSITIONS}
                WHERE status IN ('OPENING', 'OPEN', 'CLOSING')
                  AND account_id = ?
                  AND symbol = ?
                ORDER BY entry_date, position_id
                """,
                [account_id, symbol],
            ).fetchall()
        else:
            rows = conn.execute(
                f"""
                {_SELECT_POSITIONS}
                WHERE status IN ('OPENING', 'OPEN', 'CLOSING')
                  AND account_id = ?
                ORDER BY entry_date, position_id
                """,
                [account_id],
            ).fetchall()
    return [_row_to_position(r) for r in rows]


def get_closed_positions(
    *,
    account_id: str,
    limit: int | None = None,
) -> list[Position]:
    """Historical closed positions for an account (newest first)."""
    sql = f"""
        {_SELECT_POSITIONS} WHERE status = 'CLOSED'
          AND account_id = ?
        ORDER BY exit_date DESC, position_id
    """
    params: list[Any] = [account_id]
    if limit:
        sql += f" LIMIT {int(limit)}"
    with connect(read_only=True) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_position(r) for r in rows]


def has_open_position(
    symbol: str,
    *,
    account_id: str,
) -> bool:
    """Quick check — used by selector to enforce symbol_already_held within an account."""
    with connect(read_only=True) as conn:
        n = conn.execute(
            """
            SELECT COUNT(*) FROM positions
            WHERE status IN ('OPENING', 'OPEN', 'CLOSING')
              AND symbol = ?
              AND account_id = ?
            """,
            [symbol, account_id],
        ).fetchone()[0]
    return n > 0


def _row_to_position(row: tuple[Any, ...]) -> Position:
    """Map a positions row to Position dataclass using named columns.

    v0.1.18: replaced fragile positional indexing (SELECT * + row[N])
    with explicit column list (_POSITION_COLUMNS) for robustness.
    """
    if len(row) != len(_POSITION_COLUMNS):
        raise ValueError(
            f"_row_to_position: expected {len(_POSITION_COLUMNS)} columns, "
            f"got {len(row)}. Schema drift detected — check "
            f"_POSITION_COLUMNS vs DB schema."
        )
    d = dict(zip(_POSITION_COLUMNS, row))
    return Position(
        position_id=d["position_id"],
        account_id=d["account_id"],
        entry_signal_id=d["entry_signal_id"],
        entry_order_id=d["entry_order_id"],
        exit_signal_id=d["exit_signal_id"],
        exit_order_id=d["exit_order_id"],
        symbol=d["symbol"],
        strategy=d["strategy"],
        entry_date=d["entry_date"],
        entry_price=d["entry_price"],
        entry_atr=d["entry_atr"],
        regime_at_entry=d["regime_at_entry"],
        sector=d["sector"],
        is_etf=d["is_etf"],
        shares=d["shares"],
        notional_at_entry=d["notional_at_entry"],
        entry_commission=d["entry_commission"],
        entry_slippage_cost=d["entry_slippage_cost"],
        last_close=d["last_close"],
        last_updated_date=d["last_updated_date"],
        max_close_since_entry=d["max_close_since_entry"],
        max_close_date=d["max_close_date"],
        min_close_since_entry=d["min_close_since_entry"],
        min_close_date=d["min_close_date"],
        exit_date=d["exit_date"],
        exit_price=d["exit_price"],
        exit_reason=d["exit_reason"],
        regime_at_exit=d["regime_at_exit"],
        exit_commission=d["exit_commission"],
        exit_tax=d["exit_tax"],
        exit_slippage_cost=d["exit_slippage_cost"],
        exit_proceeds=d["exit_proceeds"],
        status=d["status"],
        created_at=d["created_at"],
        updated_at=d["updated_at"],
        is_synthetic=bool(d["is_synthetic"]),
        bootstrap_batch_id=d["bootstrap_batch_id"],
        source_order_id=d["source_order_id"],
    )
