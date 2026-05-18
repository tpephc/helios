# execution/reconciliation.py
"""Position reconciliation between internal state and broker truth.

v0.1.14.2-b: STUB. Paper broker IS our DB by definition — no external state to
reconcile against. Returns empty report; logs no-op.

v0.1.15: real implementation. Will query Shioaji for positions, cash, and pending
orders; compare against `positions`/`orders` tables; report drift.

Why even a stub now (rather than nothing):
- v0.1.14.2-b daily_run.py treats reconciliation as a required step. The call
  site exists. When v0.1.15 promotes this to real impl, the call site needs no
  change.
- §0.5 Simplicity Doctrine: stub is the minimum viable representation that
  preserves the call-site contract without paying full implementation cost.

Version: v0.1.0 (2026-05-17)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_type

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ReconciliationReport:
    """v0.1.15 will populate; v0.1.14.2 stub returns empty.

    Fields shape per v0.1.15 plan (commit to API now to avoid call-site churn).
    """
    as_of: date_type
    paper_only_positions: list[str] = field(default_factory=list)   # symbols in DB not at broker
    broker_only_positions: list[str] = field(default_factory=list)  # symbols at broker not in DB
    qty_mismatches: list[tuple[str, int, int]] = field(default_factory=list)  # (sym, ours, theirs)
    cash_mismatch_ntd: float | None = None  # ours - theirs (None = not checked)
    skipped: bool = False
    skip_reason: str | None = None

    @property
    def is_clean(self) -> bool:
        return (
            not self.paper_only_positions
            and not self.broker_only_positions
            and not self.qty_mismatches
            and (self.cash_mismatch_ntd is None or abs(self.cash_mismatch_ntd) < 1.0)
        )


def reconcile(as_of: date_type) -> ReconciliationReport:
    """v0.1.14.2 stub — paper broker, no external truth to compare.

    Always returns clean+skipped report. Call site (daily_run.py Step 7) treats
    this as "nothing to reconcile, continue".

    v0.1.15 will: query broker.list_positions / .get_cash; compare against
    storage.positions.get_open_positions; populate fields above; alert on drift.
    """
    report = ReconciliationReport(
        as_of=as_of,
        skipped=True,
        skip_reason="paper_broker_no_external_state_v0.1.14.2",
    )
    logger.info(
        "reconciliation_skipped",
        as_of=str(as_of),
        reason=report.skip_reason,
    )
    return report
