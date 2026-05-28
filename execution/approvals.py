# execution/approvals.py
"""Approval flow for PENDING entry signals.

ARCHITECTURE §6.5 state machine: PendingApproval → Approved | Rejected | Expired.
ADR-004: every entry requires human approval. This module handles the /approve
and /reject commands received via Telegram (in v0.1.14.2-b) or CLI.

Key invariants (per §6.5 transition rules):
  - /approve received AFTER expiry → REJECT (do not transition)
  - /approve must check ATR drift at approval time (not just at signal generation)
  - /approve transitions PENDING → APPROVED and triggers lifecycle.open_position_from_signal
  - /reject transitions PENDING → REJECTED (terminal)

Returns (success: bool, message: str) tuples so callers (Telegram listener or
CLI) can relay outcome to operator.

Version: v0.1.0 (2026-05-17)
"""
from __future__ import annotations

from datetime import date as date_type
from datetime import datetime

from data.database import connect
from execution.lifecycle import open_position_from_signal
from execution.paper_broker import PaperBroker
from storage.signals import SignalRow, get_pending, get_signal, update_approval
from utils.logger import get_logger

logger = get_logger(__name__)


DEFAULT_DRIFT_MULTIPLIER = 0.5


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────


def approve_signal(
    signal_id_or_prefix: str,
    target_notional: float,
    fill_date: date_type,
    broker: PaperBroker,
    *,
    account_id: str,
    approved_by: str = "telegram",
    drift_multiplier: float = DEFAULT_DRIFT_MULTIPLIER,
) -> tuple[bool, str, str | None]:
    """Handle /approve command.

    v0.1.18: account_id required — passed to open_position_from_signal
    for multi-account isolation.
    """
    sig = _resolve_signal(signal_id_or_prefix)
    if sig is None:
        return False, f"找不到訊號:{signal_id_or_prefix}", None
    sid = sig.signal_id

    if sig.approval_status != "PENDING":
        return False, (
            f"訊號 {sid[:8]} 無法核准(目前狀態:{sig.approval_status})"
        ), None

    if sig.timeout_at and sig.timeout_at < datetime.now():
        # P1-5: late approval after timeout — transition to TIMEOUT inline.
        # Without this, the signal stays PENDING in DB until the next daily_run's
        # expire_by_timeout, creating a stale-state window. Better to close it now.
        update_approval(sid, "TIMEOUT", expired_reason="late_approval_after_timeout")
        return False, (
            f"訊號 {sid[:8]} 已逾時(逾時時間 {sig.timeout_at:%H:%M:%S})"
            f"— 已標記為 TIMEOUT"
        ), None

    # Re-check ATR drift at approval moment (not just signal-gen moment)
    drift_ok, drift_msg = _check_atr_drift(sig, fill_date, drift_multiplier)
    if not drift_ok:
        update_approval(sid, "EXPIRED_DRIFT", expired_reason=drift_msg[:200])
        logger.info(
            "approval_rejected_drift",
            signal_id=sid, message=drift_msg,
        )
        return False, drift_msg, None

    # P1-6: check update_approval return value (atomic, race-safe with WHERE PENDING)
    transitioned = update_approval(sid, "APPROVED", approved_by=approved_by)
    if not transitioned:
        # Another process already changed this signal's status; bail safely.
        return False, (
            f"訊號 {sid[:8]} 已被處理過(race condition)— 目前狀態不明"
        ), None

    # Open the position
    position_id = open_position_from_signal(
        signal_id=sid,
        target_notional=target_notional,
        fill_date=fill_date,
        broker=broker,
        account_id=account_id,
    )
    if position_id is None:
        # Approval succeeded but fill failed. Signal status is APPROVED;
        # no position. Operator gets a clear message.
        return False, (
            f"訊號 {sid[:8]} 已核准但成交失敗(請查 log)"
        ), None

    return True, (
        f"訊號 {sid[:8]} 已核准 → 部位 {position_id} 已開倉"
    ), position_id


def reject_signal(
    signal_id_or_prefix: str, *, rejected_by: str = "telegram",
) -> tuple[bool, str]:
    """Handle /reject command. Terminal transition."""
    sig = _resolve_signal(signal_id_or_prefix)
    if sig is None:
        return False, f"找不到訊號:{signal_id_or_prefix}"
    if sig.approval_status != "PENDING":
        return False, (
            f"訊號 {sig.signal_id[:8]} 無法拒絕"
            f"(目前狀態:{sig.approval_status})"
        )
    # P1-6: check atomic update result
    ok = update_approval(sig.signal_id, "REJECTED", approved_by=rejected_by)
    if not ok:
        return False, (
            f"訊號 {sig.signal_id[:8]} 已被處理過(race condition)"
        )
    logger.info("approval_rejected", signal_id=sig.signal_id, by=rejected_by)
    return True, f"訊號 {sig.signal_id[:8]} 已拒絕"


def list_pending_for_display() -> list[SignalRow]:
    """Currently PENDING signals — used by Telegram /status command."""
    return get_pending()


# ─────────────────────────────────────────────────────────────
# Internals
# ─────────────────────────────────────────────────────────────


def _resolve_signal(id_or_prefix: str) -> SignalRow | None:
    """Allow short prefix lookup for Telegram convenience.

    /approve abc123 — match signal_id LIKE 'abc123%'
    Unique prefix required; ambiguous → returns None with warning log.
    """
    sig = get_signal(id_or_prefix)
    if sig is not None:
        return sig
    # Try prefix
    with connect(read_only=True) as conn:
        matches = conn.execute(
            "SELECT signal_id FROM signals WHERE signal_id LIKE ? LIMIT 2",
            [f"{id_or_prefix}%"],
        ).fetchall()
    if len(matches) == 1:
        return get_signal(matches[0][0])
    if len(matches) > 1:
        logger.warning("approval_ambiguous_prefix", prefix=id_or_prefix)
    return None


def _check_atr_drift(
    sig: SignalRow, fill_date: date_type, multiplier: float,
) -> tuple[bool, str]:
    """Return (ok, message). False with drift_exceeded message if breach.

    v0.1.14.3: reads `adj_open[fill_date]` (not adj_close) because that is the
    actual price the fill will use under the FILL_MODEL="next_open" semantic.
    Drift is now `|adj_open[fill_date] - signal.price|`, i.e. the gap between
    signal-time close and would-be fill-time open — the operationally relevant
    distance. Note: `expire_by_drift` (in execution.expiry, runs at daily_run
    Step 4) still uses adj_close for general staleness; that's a separate
    pre-approval coarse filter and is intentionally not coupled to fill price
    here (deferred to a follow-up if reviewer wants full consistency).

    v0.1.14.3.7: the no-price-data path now returns (True, "...跳過...") to
    match the no-ATR-data path (line 187-188). Both are "cannot verify"
    conditions and must be handled symmetrically — previously, no-price
    bailed to EXPIRED_DRIFT while no-ATR proceeded, an asymmetry that
    nuked every approval issued before EOD price sync. The companion
    `execution.expiry.expire_by_drift` already takes the permissive path
    in the same condition (skips when current_prices is empty); aligning
    here closes that cross-layer semantic split.
    """
    if not sig.entry_atr or sig.entry_atr <= 0:
        return True, "無 ATR 資料,跳過漂移檢查"

    with connect(read_only=True) as conn:
        row = conn.execute(
            "SELECT adj_open FROM daily_price_adj WHERE stock_id = ? AND date = ?",
            [sig.symbol, fill_date],
        ).fetchone()
    if not row or row[0] is None:
        # v0.1.14.3.7: cannot verify ⇒ permit (symmetric with no-ATR path
        # above and with execution.expiry.expire_by_drift's no-price branch).
        # The approval proceeds; the operator is informed via the returned
        # message which the caller logs. Downstream fill will either succeed
        # at next available price or fail safely via PaperBroker.
        logger.info(
            "approval_drift_check_skipped_no_price",
            signal_id=sig.signal_id, symbol=sig.symbol, fill_date=str(fill_date),
        )
        return True, (
            f"{sig.symbol} 在 {fill_date} 無價格資料,跳過漂移檢查"
        )
    current = float(row[0])
    drift = abs(current - sig.price)
    threshold = multiplier * sig.entry_atr
    if drift > threshold:
        return False, (
            f"價格偏離 {drift:.2f} > {multiplier}×ATR={threshold:.2f} "
            f"({sig.symbol}:訊號價 {sig.price:.2f} → 開盤價 {current:.2f})"
        )
    return True, f"漂移檢查通過({drift:.2f} ≤ {threshold:.2f})"
