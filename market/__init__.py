# market/__init__.py
"""台股市場資訊層：交易日曆、特殊交易日。

v0.1 只實作 trading_calendar.py。
v0.2+ 預留 sessions.py (盤中/盤後/零股時段)、holidays.py。

註：模組命名為 `trading_calendar` 而非 `calendar` 是為了避開 stdlib `calendar` 衝突。

Version: v0.1.0 (2026-05-16)
Changelog:
  v0.1.0 (2026-05-16): Initial implementation
"""
from market.trading_calendar import (
    get_trading_days,
    is_trading_day,
    next_trading_day,
    previous_trading_day,
    trading_days_between,
)

__all__ = [
    "get_trading_days",
    "is_trading_day",
    "next_trading_day",
    "previous_trading_day",
    "trading_days_between",
]
