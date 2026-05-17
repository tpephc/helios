# data/cache.py
"""Parquet 本地快取 (TTL + trading-day aware + 自動 schema 失效)。

用途：
- 避免重複呼叫 FinMind (免費版限速嚴格)
- 中間特徵結果暫存
- 回測重複資料載入

設計：
- key 經 SHA256 hash 避免特殊字元；保留前 30 字元可讀性 + hash 唯一性
- CACHE_SCHEMA_VERSION 嵌入 key，未來欄位變動時舊 cache 自然失效，無需手動 clear
- 兩種失效機制：
  1) TTL: 通用快取 (`.get(key, ttl_seconds=...)`)
  2) Trading-day: market data 用 (`.get_for_trading_day(key)`)
     以「最後一個 trading day」為失效錨點：跨日且過盤後即失效，
     比 TTL 更貼合 market data 性質 (盤後 14:00 之前抓的可能不完整)

Version: v0.1.2 (2026-05-16)
Changelog:
  v0.1.2 (2026-05-16): CACHE_SCHEMA_VERSION 1 → 2 (邏輯: daily_price 改抓還原權息，
                       舊的 raw price cache 必須失效，避免新舊資料混雜)
  v0.1.1 (2026-05-16): 加 CACHE_SCHEMA_VERSION 避免 schema drift; 加 trading-day-aware 模式
  v0.1.0 (2026-05-16): Initial implementation
"""
from __future__ import annotations

import hashlib
import time
from datetime import date, datetime
from datetime import time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import polars as pl

from config.settings import get_settings
from utils.logger import get_logger

logger = get_logger(__name__)


# Cache schema version: 任何欄位語意/單位/型別變動時 bump 一次，舊 cache 自動失效
# - v1: 初版 (2026-05-16)
CACHE_SCHEMA_VERSION = 2

# 台股盤後資料 typical 公佈時間 (FinMind 約於收盤後 14:30 開始有當日資料)
_MARKET_DATA_AVAILABLE_AFTER = dtime(14, 30)


def _current_trading_day_anchor() -> date:
    """回傳當前「最後一個可靠的 trading_day」。

    邏輯：
    - 若今天是 trading day 且時間已過盤後資料公佈時間 → 今天
    - 否則 → 上一個 trading day

    這個 anchor 用來當 cache key 的一部分，跨 trading day 自然 invalidation。
    """
    from market.trading_calendar import is_trading_day, previous_trading_day

    tz = ZoneInfo(get_settings().timezone)
    now = datetime.now(tz=tz)
    today = now.date()

    if is_trading_day(today) and now.time() >= _MARKET_DATA_AVAILABLE_AFTER:
        return today
    # 否則用前一個 trading day 當 anchor
    prev = previous_trading_day(today)
    return prev if prev is not None else today


class ParquetCache:
    """key → Parquet 檔案的本地快取。"""

    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir or get_settings().cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        """key → 檔名。安全字元 + hash 確保唯一; 含 CACHE_SCHEMA_VERSION 避免 schema drift。"""
        versioned = f"v{CACHE_SCHEMA_VERSION}|{key}"
        h = hashlib.sha256(versioned.encode("utf-8")).hexdigest()[:16]
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key[:30])
        return self.cache_dir / f"v{CACHE_SCHEMA_VERSION}_{safe}_{h}.parquet"

    # ── TTL 模式 (通用) ─────────────────────────────────────────

    def get(self, key: str, ttl_seconds: int | None = None) -> pl.DataFrame | None:
        """取得快取。過期回傳 None (不刪檔，方便 debug)。"""
        p = self._path(key)
        if not p.exists():
            return None

        if ttl_seconds is not None:
            age = time.time() - p.stat().st_mtime
            if age > ttl_seconds:
                logger.debug("cache_expired", key=key, age_s=round(age, 1))
                return None

        try:
            return pl.read_parquet(p)
        except Exception as e:
            logger.warning("cache_read_failed", key=key, error=str(e))
            return None

    def set(self, key: str, df: pl.DataFrame) -> None:
        """寫入快取。空 DataFrame 不寫。"""
        if df.is_empty():
            return
        p = self._path(key)
        df.write_parquet(p, compression="zstd")
        logger.debug("cache_written", key=key, rows=df.height)

    # ── Trading-day 模式 (market data 專用) ────────────────────

    def get_for_trading_day(
        self, key: str, trading_day: date | None = None
    ) -> pl.DataFrame | None:
        """取得 trading-day-keyed 快取。

        key 內部會自動含 trading_day anchor。跨 trading day 後同一個 key
        會 hash 到不同檔案 → 自動 cache miss、強制 refresh。

        Args:
            key: 業務 key (e.g., "price_2330_2020-01-01_2025-12-31")
            trading_day: 指定錨點。預設用 `_current_trading_day_anchor()`
        """
        anchor = trading_day or _current_trading_day_anchor()
        td_key = f"{key}|td={anchor.isoformat()}"
        p = self._path(td_key)
        if not p.exists():
            return None
        try:
            return pl.read_parquet(p)
        except Exception as e:
            logger.warning("cache_read_failed", key=td_key, error=str(e))
            return None

    def set_for_trading_day(
        self, key: str, df: pl.DataFrame, trading_day: date | None = None
    ) -> None:
        """寫入 trading-day-keyed 快取。"""
        if df.is_empty():
            return
        anchor = trading_day or _current_trading_day_anchor()
        td_key = f"{key}|td={anchor.isoformat()}"
        p = self._path(td_key)
        df.write_parquet(p, compression="zstd")
        logger.debug("cache_written_td", key=td_key, anchor=str(anchor), rows=df.height)

    # ── 管理 ─────────────────────────────────────────────────

    def delete(self, key: str) -> bool:
        p = self._path(key)
        if p.exists():
            p.unlink()
            return True
        return False

    def clear(self, prefix: str | None = None) -> int:
        """清除所有快取，或符合 prefix 的快取。"""
        n = 0
        for f in self.cache_dir.glob("*.parquet"):
            if prefix is None or f.name.startswith(prefix):
                f.unlink()
                n += 1
        logger.info("cache_cleared", n=n, prefix=prefix)
        return n

    def clear_old_schema_versions(self) -> int:
        """清除非當前 CACHE_SCHEMA_VERSION 的快取檔。

        當 CACHE_SCHEMA_VERSION bump 後可呼叫一次，刪掉孤兒檔案。
        """
        current_prefix = f"v{CACHE_SCHEMA_VERSION}_"
        n = 0
        for f in self.cache_dir.glob("v*_*.parquet"):
            if not f.name.startswith(current_prefix):
                f.unlink()
                n += 1
        logger.info("cache_cleared_old_schema", n=n, current_version=CACHE_SCHEMA_VERSION)
        return n
