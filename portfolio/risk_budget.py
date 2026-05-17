# portfolio/risk_budget.py
"""Portfolio risk budget — capital allocation rules.

v0.1.14.1 defaults (per user spec):
  max_positions       = 5
  per_position_pct    = 20%  of current equity at entry
  max_etf_exposure    = 40%  of current equity (ETF cluster cap)
  max_sector_exposure = 30%  of current equity (sector concentration cap)
  cash_buffer         = 10%  of current equity (always reserve)

注意 cash_buffer + per_position 互動:
  - 4 個 position × 20% = 80% deployed, 20% cash → 滿足 buffer ✓
  - 5 個 position × 20% = 100% deployed, 0% cash → 違反 buffer ✗
  - 所以實際 effective max ≈ 4 positions (cash_buffer 比 max_positions 更早 binding)
  - 這是 feature 不是 bug: cash_buffer 在 stress 時保命

Version: v0.1.0 (2026-05-17)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskBudget:
    """Constraints applied at signal-entry time. Frozen = immutable per run."""
    max_positions: int = 5
    per_position_pct: float = 0.20         # 20% of equity per position
    max_etf_exposure_pct: float = 0.40     # 40% total ETF exposure
    max_sector_exposure_pct: float = 0.30  # 30% per single sector
    cash_buffer_pct: float = 0.10          # 10% min cash always

    def describe(self) -> str:
        return (
            f"max_pos={self.max_positions}, "
            f"per_pos={self.per_position_pct*100:.0f}%, "
            f"etf_cap={self.max_etf_exposure_pct*100:.0f}%, "
            f"sector_cap={self.max_sector_exposure_pct*100:.0f}%, "
            f"cash_buffer={self.cash_buffer_pct*100:.0f}%"
        )


DEFAULT_RISK_BUDGET = RiskBudget()
