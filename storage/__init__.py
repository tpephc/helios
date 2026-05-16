# storage/__init__.py
"""持久化層：functional SQL wrappers，無 ORM。

每個檔案對應一張或一組相關表：
- signals.py   - 訊號 event log (含 approval flow)
- orders.py    - 訂單 event log
- snapshots.py - 每日狀態快照
- positions.py - 持倉 (從 orders 即時計算，非獨立表)

Version: v0.1.0 (2026-05-16)
Changelog:
  v0.1.0 (2026-05-16): Initial implementation
"""
from storage import orders, positions, signals, snapshots

__all__ = ["orders", "positions", "signals", "snapshots"]
