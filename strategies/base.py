# strategies/base.py
"""Strategy abstract base class + Signal dataclass.

Reviewer-driven design (v0.1.12):
- 每個 strategy 是 deterministic 的 (same inputs → same outputs)
- 每個 signal 必須帶 decision context (reason + metadata) 給 Telegram / AI filter consume
- 不做 portfolio sizing / risk budgeting (v0.1 不該進這層)

Version: v0.1.0 (2026-05-17)
Changelog:
  v0.1.0 (2026-05-17): Initial — Strategy ABC + Signal dataclass
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date as date_type
from typing import Any


@dataclass
class Signal:
    """單一 trade signal + decision context.

    與 storage/signals.py 的 SignalRow 對應 — 但比 SignalRow 多 metadata 結構化資訊
    (storage 寫成 JSON 後丟進 signals.metadata 欄位)。
    """
    stock_id: str
    signal_date: date_type
    strategy: str
    side: str               # 'buy' / 'sell' / 'exit'
    entry_price: float
    entry_atr: float
    regime: str             # market context: bull/bear/crisis/neutral
    score: float            # 0.0-1.0 conviction
    reason: list[str]       # human-readable, for Telegram preview
    metadata: dict[str, Any] = field(default_factory=dict)  # structured for audit / AI

    def __post_init__(self) -> None:
        if not (0.0 <= self.score <= 1.0):
            raise ValueError(f"score must be in [0,1], got {self.score}")
        if self.side not in ("buy", "sell", "exit"):
            raise ValueError(f"side must be buy/sell/exit, got {self.side}")


class Strategy(ABC):
    """Strategy 抽象基類.

    Subclass 要做兩件事:
      1. 設定 class attribute `name` (跟 storage 區分 strategy 用)
      2. 實作 generate_signals(as_of, symbols) -> list[Signal]

    對 deterministic 的要求:
      - 相同的 (as_of, symbols, DB 狀態) 必須產生完全相同的 signals
      - 不能有隨機性 (no random init, no clock dependency 除了 as_of 本身)
    """

    name: str  # subclass 要 override

    @abstractmethod
    def generate_signals(
        self,
        as_of: date_type,
        symbols: list[str] | None = None,
    ) -> list[Signal]:
        """Generate signals for given trading date.

        Args:
            as_of: Trading date to evaluate (typically today or for replay/backtest)
            symbols: Optional limit to specific symbols; None = all in daily_features

        Returns:
            List of Signal objects (empty if no signals fired)
        """
        raise NotImplementedError
