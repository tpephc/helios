# data/sources/__init__.py
"""資料源實作。v0.1 只有 FinMind；Shioaji 行情、yfinance 備援預留 v0.2+。

Version: v0.1.0 (2026-05-16)
Changelog:
  v0.1.0 (2026-05-16): Initial implementation
"""
from data.sources.finmind_client import FinMindClient, FinMindError

__all__ = ["FinMindClient", "FinMindError"]
