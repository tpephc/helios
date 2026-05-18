# execution/__init__.py
"""Execution layer — paper broker + lifecycle orchestration + approvals + expiry.

v0.1.14.2-b modules:
  paper_broker.py    — simulated fills with cost model
  lifecycle.py       — open/close position (combines broker + storage)
  approvals.py       — /approve /reject signal flow
  expiry.py          — timeout + ATR drift expiry
  reconciliation.py  — STUB (v0.1.15 will populate)
  shutdown.py        — graceful shutdown context manager + marker file
                       + PreflightDecline exception (c3)

v0.1.14.2-c3: calendar helpers (is_trading_day, next_trading_day) MOVED
to market/trading_calendar.py per P0-3 (single source of truth for
calendar semantics). Import them from `market` not `execution`.
"""
from execution.paper_broker import (
    DEFAULT_TW_FEES,
    FillResult,
    PaperBroker,
    TransactionFees,
)
from execution.shutdown import (
    PreflightDecline,
    check_data_freshness,
    check_previous_run,
    read_history,
    read_marker,
    shutdown_guard,
)

__all__ = [
    "DEFAULT_TW_FEES",
    "FillResult",
    "PaperBroker",
    "PreflightDecline",
    "TransactionFees",
    "check_data_freshness",
    "check_previous_run",
    "read_history",
    "read_marker",
    "shutdown_guard",
]
