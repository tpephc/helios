# portfolio/__init__.py
"""Portfolio layer — capital allocation + risk budget + selector.

v0.1.14.1 (per reviewer §43-46):
  risk_budget.py  — RiskBudget config dataclass
  selector.py     — sector classification + multi-signal selection logic

v0.2.0 (2026-06-01):
  selector.py     — SECTOR_MAP removed; sector now derived dynamically from
                    company_metadata.industry_code via INDUSTRY_SECTOR_MAP.

不做 (reviewer §45):
  - HRP / risk parity / Kelly / covariance optimization
v0.1 keep deterministic simple rules.
"""
from portfolio.risk_budget import DEFAULT_RISK_BUDGET, RiskBudget
from portfolio.selector import INDUSTRY_SECTOR_MAP, get_sector, is_etf

__all__ = [
    "DEFAULT_RISK_BUDGET",
    "INDUSTRY_SECTOR_MAP",
    "RiskBudget",
    "get_sector",
    "is_etf",
]
