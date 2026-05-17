# data/fetcher.py
"""統一資料抓取入口：來源切換、快取整合、品質驗證。

設計：
- DataFetcher 是門面 (facade)：上層 (features/, strategies/) 只認此介面
- 內部目前只有 FinMind；v0.2 可加 Shioaji 行情 / yfinance 備援
- 每次抓取都回 FetchResult，攜帶來源、快取狀態、品質問題
- FetchResult.success 區分「成功但空資料 (該期間無交易)」與「fetch 失敗」
- 品質檢查內建：缺值、異常漲跌幅、低流動性

Version: v0.1.2 (2026-05-16)
Changelog:
  v0.1.2 (2026-05-16): daily_price 後接 sanity.validate_ohlc 丟壞列 (close<=0 / high<low / 全 null);
                       壞列 count + 原因併入 quality_issues 並 log
  v0.1.1 (2026-05-16): FetchResult 加 success/error 欄位，解決空 DataFrame 語意混淆;
                       daily_price 加 trading_day_aware cache mode
  v0.1.0 (2026-05-16): Initial implementation
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import polars as pl

from data.cache import ParquetCache
from data.sources.finmind_client import FinMindClient, FinMindError
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class FetchResult:
    """抓取結果 + 品質元資料。

    success / error 區分：
      - success=True,  error=None       : 抓取成功 (即使 data 是空的，例如該期間沒交易)
      - success=False, error="..."      : 抓取失敗 (網路 / API error / 認證問題)

    下游應該檢查 success 而非 data.is_empty() 來判斷錯誤。
    """

    data: pl.DataFrame
    source: str                       # cache / finmind / shioaji / yfinance
    rows: int
    cache_hit: bool
    success: bool = True
    error: str | None = None
    quality_issues: list[str] = field(default_factory=list)


class DataFetcher:
    """統一資料抓取門面。"""

    def __init__(self, cache: ParquetCache | None = None):
        self.cache = cache or ParquetCache()
        self._finmind: FinMindClient | None = None

    @property
    def finmind(self) -> FinMindClient:
        """Lazy init: 第一次使用才建立連線。"""
        if self._finmind is None:
            self._finmind = FinMindClient()
        return self._finmind

    # ── 公開抓取方法 ──────────────────────────────────────

    def daily_price(
        self,
        stock_id: str,
        start: date,
        end: date,
        cache_mode: str = "trading_day",  # "trading_day" | "ttl"
        cache_ttl_seconds: int = 3600,
    ) -> FetchResult:
        """日 K 資料，含快取與品質驗證。

        Cache mode:
          - "trading_day" (預設): cache key 含當前最後交易日，跨日自動失效，
                                  下午盤後新資料一進來自動 cache miss
          - "ttl": 傳統時間失效 (legacy)
        """
        key = f"price_{stock_id}_{start}_{end}"

        if cache_mode == "trading_day":
            cached = self.cache.get_for_trading_day(key)
        else:
            cached = self.cache.get(key, ttl_seconds=cache_ttl_seconds)
        if cached is not None:
            return FetchResult(
                cached, "cache", cached.height, cache_hit=True,
                success=True, error=None,
            )

        try:
            df = self.finmind.daily_price(stock_id, start, end)
        except FinMindError as e:
            logger.error("fetch_failed", stock_id=stock_id, error=str(e))
            return FetchResult(
                pl.DataFrame(), "finmind", 0, cache_hit=False,
                success=False, error=f"fetch_error: {e}",
            )

        # v0.1.7: 衛生檢查 — 丟掉 close<=0 / 反轉 high<low / 全 null 等壞列
        from data.sanity import validate_ohlc
        sanity = validate_ohlc(df)
        df = sanity.clean

        issues = self._validate_price(df, stock_id)
        if sanity.dropped_count > 0:
            issues.append(
                f"sanity_dropped:{sanity.dropped_count}_rows ({','.join(sanity.dropped_reasons)})"
            )
            logger.warning(
                "sanity_dropped_rows", stock_id=stock_id,
                dropped=sanity.dropped_count, reasons=sanity.dropped_reasons,
            )

        if df.height > 0:
            if cache_mode == "trading_day":
                self.cache.set_for_trading_day(key, df)
            else:
                self.cache.set(key, df)

        return FetchResult(
            df, "finmind", df.height, cache_hit=False,
            success=True, error=None, quality_issues=issues,
        )

    def stock_info(self, cache_ttl_seconds: int = 86400 * 7) -> FetchResult:
        """股票基本資料表 (預設快取 7 天)。"""
        key = "stock_info_all"
        cached = self.cache.get(key, ttl_seconds=cache_ttl_seconds)
        if cached is not None:
            return FetchResult(
                cached, "cache", cached.height, cache_hit=True,
                success=True, error=None,
            )

        try:
            df = self.finmind.stock_info()
        except FinMindError as e:
            logger.error("stock_info_failed", error=str(e))
            return FetchResult(
                pl.DataFrame(), "finmind", 0, cache_hit=False,
                success=False, error=f"fetch_error: {e}",
            )

        if df.height > 0:
            self.cache.set(key, df)
        return FetchResult(
            df, "finmind", df.height, cache_hit=False,
            success=True, error=None,
        )

    def taiex(
        self,
        start: date,
        end: date,
        cache_mode: str = "trading_day",
        cache_ttl_seconds: int = 3600,
    ) -> FetchResult:
        """加權指數 (regime 偵測用)。"""
        key = f"taiex_{start}_{end}"
        if cache_mode == "trading_day":
            cached = self.cache.get_for_trading_day(key)
        else:
            cached = self.cache.get(key, ttl_seconds=cache_ttl_seconds)
        if cached is not None:
            return FetchResult(
                cached, "cache", cached.height, cache_hit=True,
                success=True, error=None,
            )

        try:
            df = self.finmind.taiex(start, end)
        except FinMindError as e:
            return FetchResult(
                pl.DataFrame(), "finmind", 0, cache_hit=False,
                success=False, error=f"fetch_error: {e}",
            )

        if df.height > 0:
            if cache_mode == "trading_day":
                self.cache.set_for_trading_day(key, df)
            else:
                self.cache.set(key, df)
        return FetchResult(
            df, "finmind", df.height, cache_hit=False,
            success=True, error=None,
        )

    # ── 品質驗證 ─────────────────────────────────────────────

    def _validate_price(self, df: pl.DataFrame, stock_id: str) -> list[str]:
        """價格資料的基本品質檢查。"""
        issues: list[str] = []
        if df.is_empty():
            return issues

        # 1. 缺值
        n_null = df.select(pl.col("close").is_null().sum()).item()
        if n_null > 0:
            issues.append(f"null_close: {n_null}")

        # 2. 異常漲跌幅 (> 10.5% 通常是除權息未調整)
        df_chk = df.sort("date").with_columns(
            pct=(pl.col("close") / pl.col("close").shift() - 1).abs()
        )
        n_anomaly = df_chk.filter(pl.col("pct") > 0.105).height
        if n_anomaly > 0:
            issues.append(f"abnormal_pct_change: {n_anomaly}")

        # 3. 零成交占比過高
        n_zero_vol = df.filter(pl.col("volume") == 0).height
        if n_zero_vol > df.height * 0.1:
            issues.append(
                f"low_liquidity: {n_zero_vol}/{df.height} zero-volume days"
            )

        if issues:
            logger.warning("data_quality", stock_id=stock_id, issues=issues)

        return issues

    # ── lifecycle ─────────────────────────────────────────────

    def close(self) -> None:
        if self._finmind is not None:
            self._finmind.close()

    def __enter__(self) -> DataFetcher:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
