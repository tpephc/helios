# execution/expiry.py
"""Signal expiry logic — timeout + ATR drift.

ARCHITECTURE §6.5: PendingApproval → Expired transitions.
ARCHITECTURE §9 Escalation Policy: "missed signal > wrong trade" — when in doubt,
do not trade.

Two expiry mechanisms (run independently each daily_run):

1. **Timeout expiry** — signal.timeout_at < now
   Default 30 min from signal generation.

2. **ATR drift expiry** — |current_price - signal_price| > 0.5 × signal.entry_atr
   Price moved too much for the original setup to still be valid.
   Checked even if within timeout window.

3. **Shutdown expiry** (graceful shutdown helper) — mark all PENDING as Expired
   on process abort. Operator can manually re-issue if desired.

Each function returns the list of signal_ids it expired, for logging / telegram
notification.

Version: v0.1.0 (2026-05-17)
"""
from __future__ import annotations

from datetime import date as date_type
from datetime import datetime

from data.database import connect
from storage.signals import expire_drifted, expire_timed_out
from utils.logger import get_logger

logger = get_logger(__name__)


# ATR drift threshold per ADR-004 / ARCHITECTURE §6.5
DEFAULT_DRIFT_MULTIPLIER = 0.5


def expire_by_timeout(now: datetime | None = None) -> int:
    """Expire signals where timeout_at < now (default 30min from creation).

    Returns count of signals transitioned to TIMEOUT status.
    Delegates to storage.signals.expire_timed_out (existing implementation).
    """
    now = now or datetime.now()
    n = expire_timed_out(now=now)
    if n > 0:
        logger.info("expiry_timeout_run", count=n, now=now.isoformat(timespec="seconds"))
    return n


def expire_by_drift(
    as_of: date_type,
    drift_multiplier: float = DEFAULT_DRIFT_MULTIPLIER,
) -> list[str]:
    """Expire signals where current adj_close has drifted > drift_multiplier × entry_atr
    from the signal's original price.

    Reads PENDING signals, builds a current-price dict from daily_price_adj for
    each unique symbol, and delegates to storage.signals.expire_drifted.

    Returns list of signal_ids that were expired (best-effort log; storage helper
    returns count not ids, so we reconstruct from a pre-snapshot).
    """
    # 1. Snapshot which signals are currently PENDING (for diffing after)
    with connect(read_only=True) as conn:
        pending_before = {row[0] for row in conn.execute(
            "SELECT signal_id FROM signals WHERE approval_status = 'PENDING'"
        ).fetchall()}
        symbols = [row[0] for row in conn.execute(
            "SELECT DISTINCT symbol FROM signals WHERE approval_status = 'PENDING'"
        ).fetchall()]

    if not symbols:
        return []

    # 2. Build current_prices dict for these symbols
    current_prices: dict[str, float] = {}
    with connect(read_only=True) as conn:
        for sym in symbols:
            row = conn.execute(
                "SELECT adj_close FROM daily_price_adj WHERE stock_id = ? AND date = ?",
                [sym, as_of],
            ).fetchone()
            if row and row[0] is not None:
                current_prices[sym] = float(row[0])

    if not current_prices:
        logger.info("expiry_drift_no_prices", as_of=str(as_of))
        return []

    # 3. Delegate to storage helper
    n = expire_drifted(
        current_prices=current_prices,
        max_drift_atr=drift_multiplier,
    )

    # 4. Diff: what was PENDING and is now EXPIRED_DRIFT
    with connect(read_only=True) as conn:
        still_pending = {row[0] for row in conn.execute(
            "SELECT signal_id FROM signals WHERE approval_status = 'PENDING'"
        ).fetchall()}
    expired = sorted(pending_before - still_pending)

    logger.info(
        "expiry_drift_run",
        as_of=str(as_of), drift_multiplier=drift_multiplier,
        count=n, signal_ids=expired,
    )
    return expired


def expire_all_pending(reason: str = "manual") -> list[str]:
    """Graceful-shutdown helper: mark ALL currently PENDING signals as EXPIRED.

    Used when daily_run aborts unexpectedly — better to expire and force operator
    to re-evaluate than leave half-processed state.

    Returns list of expired signal_ids.
    """
    expired: list[str] = []
    with connect() as conn:
        pending_ids = [row[0] for row in conn.execute(
            "SELECT signal_id FROM signals WHERE approval_status = 'PENDING'"
        ).fetchall()]
        if not pending_ids:
            return []
        conn.execute(
            """
            UPDATE signals
            SET approval_status = 'TIMEOUT',
                expired_reason = ?
            WHERE approval_status = 'PENDING'
            """,
            [f"shutdown:{reason}"],
        )
        expired = pending_ids

    logger.warning(
        "expiry_shutdown_all_pending",
        count=len(expired), reason=reason, signal_ids=expired,
    )
    return expired


# ─────────────────────────────────────────────────────────────
# (No internal helpers needed — storage layer carries the SQL)
# ─────────────────────────────────────────────────────────────
