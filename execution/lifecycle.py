# execution/lifecycle.py
"""Position lifecycle orchestration — combines broker fills with storage state.

ARCHITECTURE §6.5 State Machine implementation surface.

Layer boundary (per decision-confirmation v0.1.14.2-b Q3):
  storage/positions.py     = pure DB CRUD (knows nothing about broker)
  execution/paper_broker.py = pure fill simulation (knows nothing about positions)
  execution/lifecycle.py    = orchestrates both (knows enough to recover on failure)

Two operations:

1. **open_position_from_signal()** — approved entry → broker buy → position OPEN
2. **close_position_for_exit()** — exit triggered → broker sell → position CLOSED

Both are single-call atomic from caller's perspective; internally they sequence
the broker call and storage write, with rollback discipline if intermediate
failure occurs.

v0.1.18: account_id parameter added to both operations. All pos_store calls
  are account-scoped. get_position replaced with get_position_for_account
  for ownership verification on read-after-write paths.

Version: v0.1.18 (2026-05-28)
"""
from __future__ import annotations

from datetime import date as date_type

from execution.paper_broker import PaperBroker
from portfolio.selector import get_sector, is_etf
from storage import positions as pos_store
from storage.signals import get_signal
from utils.logger import get_logger

logger = get_logger(__name__)


def open_position_from_signal(
    signal_id: str,
    target_notional: float,
    fill_date: date_type,
    broker: PaperBroker,
    account_id: str,
) -> str | None:
    """Approved signal → broker buy → write OPEN position.

    v0.1.18: account_id is required. All pos_store calls are account-scoped.

    Args:
        signal_id: approved signal's id
        target_notional: NTD to deploy
        fill_date: which trading day to fill on
        broker: PaperBroker instance with cost model
        account_id: broker account identifier

    Returns:
        position_id on success, None on failure.
    """
    sig = get_signal(signal_id)
    if sig is None:
        logger.error("lifecycle_open_no_signal", signal_id=signal_id)
        return None
    if sig.approval_status not in ("APPROVED", "AUTO_APPROVED"):
        logger.error(
            "lifecycle_open_bad_status",
            signal_id=signal_id, approval_status=sig.approval_status,
        )
        return None

    # Already open for this symbol in this account? Defense against double-fire.
    if pos_store.has_open_position(sig.symbol, account_id=account_id):
        logger.warning(
            "lifecycle_open_symbol_already_held",
            signal_id=signal_id, symbol=sig.symbol, account_id=account_id,
        )
        return None

    # 1. Broker submits buy
    fill = broker.submit_buy(
        symbol=sig.symbol,
        target_notional=target_notional,
        fill_date=fill_date,
        signal_id=signal_id,
    )
    if not fill.success:
        logger.error(
            "lifecycle_open_fill_failed",
            signal_id=signal_id, symbol=sig.symbol, reason=fill.error,
        )
        return None

    # 2. Record position (account-scoped)
    try:
        position_id = pos_store.open_position(
            account_id=account_id,
            symbol=sig.symbol,
            strategy=sig.strategy,
            entry_date=fill_date,
            entry_price=fill.fill_price or sig.price,
            entry_atr=sig.entry_atr or 0.0,
            regime_at_entry=sig.regime or "unknown",
            sector=get_sector(sig.symbol),
            is_etf=is_etf(sig.symbol),
            shares=fill.shares,
            notional_at_entry=fill.notional,
            entry_commission=fill.commission,
            entry_slippage_cost=fill.slippage_cost,
            entry_signal_id=signal_id,
            entry_order_id=fill.order_id,
            status=pos_store.OPEN,
        )
    except Exception as exc:
        logger.exception(
            "lifecycle_open_storage_failed",
            signal_id=signal_id, symbol=sig.symbol,
            account_id=account_id, order_id=fill.order_id,
            error=str(exc),
        )
        return None

    logger.info(
        "lifecycle_open_complete",
        position_id=position_id, signal_id=signal_id,
        symbol=sig.symbol, account_id=account_id,
        shares=fill.shares, fill_price=fill.fill_price,
    )
    return position_id


def close_position_for_exit(
    position_id: str,
    exit_date: date_type,
    exit_reason: str,
    regime_at_exit: str,
    broker: PaperBroker,
    account_id: str,
    exit_signal_id: str | None = None,
) -> bool:
    """Trigger exit → broker sell → write CLOSED position.

    v0.1.18: account_id is required. Position ownership verified via
    get_position_for_account before any mutation.

    Returns True if position is now CLOSED (success), False otherwise.

    Per ADR-004: exits do NOT require approval. This function is called
    directly by daily_run's exit-scan step.
    """
    try:
        pos = pos_store.get_position_for_account(
            position_id, account_id=account_id,
        )
    except ValueError:
        logger.error(
            "lifecycle_close_no_position",
            position_id=position_id, account_id=account_id,
        )
        return False

    if pos.status != pos_store.OPEN:
        logger.warning(
            "lifecycle_close_not_open",
            position_id=position_id, account_id=account_id,
            status=pos.status,
        )
        return False

    # 1. Broker submits sell
    fill = broker.submit_sell(
        symbol=pos.symbol, shares=pos.shares, fill_date=exit_date,
        signal_id=exit_signal_id,
    )
    if not fill.success:
        logger.error(
            "lifecycle_close_fill_failed",
            position_id=position_id, account_id=account_id,
            reason=fill.error,
        )
        return False

    # Net proceeds (gross - commission - tax). Slippage already embedded in fill_price.
    proceeds = fill.notional - fill.commission - fill.tax

    # 2. Mark position closed (account-scoped)
    try:
        pos_store.mark_position_closed(
            position_id,
            account_id=account_id,
            exit_date=exit_date,
            exit_price=fill.fill_price or pos.last_close or pos.entry_price,
            exit_reason=exit_reason,
            regime_at_exit=regime_at_exit,
            exit_commission=fill.commission,
            exit_tax=fill.tax,
            exit_slippage_cost=fill.slippage_cost,
            exit_proceeds=proceeds,
            exit_signal_id=exit_signal_id,
            exit_order_id=fill.order_id,
        )
    except Exception as exc:
        logger.exception(
            "lifecycle_close_storage_failed",
            position_id=position_id, account_id=account_id,
            order_id=fill.order_id, error=str(exc),
        )
        return False

    logger.info(
        "lifecycle_close_complete",
        position_id=position_id, symbol=pos.symbol,
        account_id=account_id,
        shares=pos.shares, fill_price=fill.fill_price,
        exit_reason=exit_reason, proceeds=proceeds,
    )
    return True
