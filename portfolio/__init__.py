# portfolio/__init__.py
"""Portfolio layer — capital allocation + risk budget + selector.

v0.1.14.1 (per reviewer §43-46):
  risk_budget.py  — RiskBudget config dataclass
  selector.py     — sector classification + multi-signal selection logic

不做 (reviewer §45):
  - HRP / risk parity / Kelly / covariance optimization
v0.1 keep deterministic simple rules.
"""
from portfolio.risk_budget import DEFAULT_RISK_BUDGET, RiskBudget
from portfolio.selector import SECTOR_MAP, get_sector, is_etf

__all__ = [
    "DEFAULT_RISK_BUDGET",
    "SECTOR_MAP",
    "RiskBudget",
    "get_sector",
    "is_etf",
]
