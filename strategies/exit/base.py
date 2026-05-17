# strategies/exit/base.py
"""Exit framework abstractions.

Per reviewer §40: exit signal 必須帶 exit_reason / stop_price / MFE / MAE
                  / holding_days / regime_at_exit (揭露 strategy risk profile)

設計:
- Position dataclass — mutable lifecycle 物件 (entry → 持倉 → exit)
- ExitDecision dataclass — exit rule 回傳的判斷結果
- ExitRule ABC — 每個 rule 一個 class, 透過 priority 排序

Priority 越小越優先 (reviewer §43: regime_exit > trailing_stop).

Version: v0.1.0 (2026-05-17)
Changelog:
  v0.1.0 (2026-05-17): Initial — ExitRule + Position + ExitDecision
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date as date_type
from typing import Any

# ─────────────────────────────────────────────────────────────
# Position lifecycle dataclass
# ─────────────────────────────────────────────────────────────


@dataclass
class Position:
    """單一 trade lifecycle (entry → 持倉 → exit), 包含完整 audit 欄位.

    Mutable: max/min_close 跟隨每日收盤更新.
    Reviewer §40 必需欄位都在.
    """
    # Entry (immutable after open)
    stock_id: str
    entry_date: date_type
    entry_price: float
    entry_atr: float
    regime_at_entry: str
    strategy: str
    score: float
    signal_id: str | None = None  # 對應 signals.signal_id (若有)

    # 持倉中 running stats (每天 update)
    max_close_since_entry: float = 0.0
    max_close_date: date_type | None = None
    min_close_since_entry: float = 0.0
    min_close_date: date_type | None = None

    # Exit (None 表示還開倉中)
    exit_date: date_type | None = None
    exit_price: float | None = None
    exit_reason: str | None = None
    regime_at_exit: str | None = None
    exit_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Initialize running stats from entry
        if self.max_close_since_entry == 0.0:
            self.max_close_since_entry = self.entry_price
            self.max_close_date = self.entry_date
        if self.min_close_since_entry == 0.0:
            self.min_close_since_entry = self.entry_price
            self.min_close_date = self.entry_date

    @property
    def is_open(self) -> bool:
        return self.exit_date is None

    @property
    def holding_days(self) -> int | None:
        """Calendar days from entry → exit (不是 trading days)."""
        if self.exit_date is None:
            return None
        return (self.exit_date - self.entry_date).days

    @property
    def gross_return_pct(self) -> float | None:
        if self.exit_price is None or self.entry_price <= 0:
            return None
        return (self.exit_price / self.entry_price - 1.0) * 100.0

    @property
    def mfe_pct(self) -> float:
        """Max Favorable Excursion — 最大未實現獲利% (reviewer §40)."""
        if self.entry_price <= 0:
            return 0.0
        return (self.max_close_since_entry / self.entry_price - 1.0) * 100.0

    @property
    def mae_pct(self) -> float:
        """Max Adverse Excursion — 最大未實現虧損% (reviewer §40, 通常為負)."""
        if self.entry_price <= 0:
            return 0.0
        return (self.min_close_since_entry / self.entry_price - 1.0) * 100.0

    def update_running_stats(self, close: float, d: date_type) -> None:
        """每日收盤後 update max/min close."""
        if close > self.max_close_since_entry:
            self.max_close_since_entry = close
            self.max_close_date = d
        if close < self.min_close_since_entry:
            self.min_close_since_entry = close
            self.min_close_date = d


# ─────────────────────────────────────────────────────────────
# Exit decision
# ─────────────────────────────────────────────────────────────


@dataclass
class ExitDecision:
    """Single exit rule 的判斷結果."""
    should_exit: bool
    reason: str               # human-readable, 例: 'trailing_stop (close=98 < stop=99.5)'
    metadata: dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────
# Exit rule abstract base
# ─────────────────────────────────────────────────────────────


class ExitRule(ABC):
    """Exit rule 抽象基類.

    子類必須設定:
      - name: rule 識別 (寫進 exit_reason)
      - priority: int, 越小越優先 (reviewer §43: regime_exit < trailing_stop)
    """
    name: str
    priority: int = 999  # default 最低優先

    @abstractmethod
    def check(
        self,
        position: Position,
        as_of: date_type,
        close: float,
        atr: float | None,
        regime: str,
    ) -> ExitDecision:
        """檢查是否應該 exit 這個 position.

        Args:
            position: 開倉部位 (running stats 已 update 至 as_of)
            as_of: today 的日期
            close: today 的 adj_close
            atr: today 的 atr_14 (可能 None)
            regime: today 的 market_regime

        Returns:
            ExitDecision (should_exit + reason + metadata)
        """
        raise NotImplementedError
