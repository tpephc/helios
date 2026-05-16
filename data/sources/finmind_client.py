# data/sources/finmind_client.py
"""FinMind v4 API client：rate limit + 退避 + Polars 輸出。

設計要點：
- 免費版每分鐘限速嚴格 → 內建 token-bucket 保證間隔
- 撞到 402 (rate limited) 退避後重試 (tenacity 包裝)
- 輸出統一為 Polars DataFrame，欄位標準化
- 所有 return path 強制 sort("date").unique(subset=...) 保證決定性順序與去重
- 數值欄位用 cast(strict=False) 容忍 API 偶發 null/錯型
- 與 fetcher.py 解耦：本 client 只負責「呼叫 + 轉型 + 衛生」

Version: v0.1.1 (2026-05-16)
Changelog:
  v0.1.1 (2026-05-16): 所有 return path 加 sort+unique 確保時序確定性;
                       cast 改用 strict=False 容忍 API null
  v0.1.0 (2026-05-16): Initial implementation
"""
from __future__ import annotations

import time
from datetime import date
from typing import Any

import httpx
import polars as pl
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config.settings import get_settings
from utils.logger import get_logger

logger = get_logger(__name__)


class FinMindError(Exception):
    """FinMind API 錯誤 (含限速、認證失敗等)。"""


class FinMindRateLimiter:
    """單線程 token bucket。"""

    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._last = 0.0

    def wait(self) -> None:
        elapsed = time.monotonic() - self._last
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last = time.monotonic()


class FinMindClient:
    """FinMind v4 client。免費版友善。"""

    def __init__(self) -> None:
        s = get_settings()
        self.base_url = s.finmind_base_url
        self.token = (
            s.finmind_token.get_secret_value() if s.finmind_token else None
        )
        self._http = httpx.Client(timeout=30.0)
        self._limiter = FinMindRateLimiter(s.finmind_min_interval_sec)
        self._rate_limit_sleep = s.finmind_rate_limit_sleep_sec
        self._max_retries = s.finmind_max_retries

        if not self.token:
            logger.warning("finmind_no_token_anonymous_mode")

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type(
            (httpx.HTTPError, httpx.TimeoutException, FinMindError)
        ),
        reraise=True,
    )
    def _get(self, dataset: str, **params: Any) -> list[dict[str, Any]]:
        self._limiter.wait()
        params["dataset"] = dataset
        if self.token:
            params["token"] = self.token

        r = self._http.get(f"{self.base_url}/data", params=params)

        # 限速:402 → 退避後拋錯讓 tenacity 重試
        if r.status_code == 402:
            logger.warning(
                "finmind_rate_limit_402",
                sleep_s=self._rate_limit_sleep,
            )
            time.sleep(self._rate_limit_sleep)
            raise FinMindError("rate_limited")

        r.raise_for_status()
        payload = r.json()

        if payload.get("status") != 200:
            raise FinMindError(f"FinMind error: {payload.get('msg')}")

        data = payload.get("data", [])
        return list(data) if data else []

    # ── 業務方法 (返回標準化 Polars DataFrame) ─────────────────

    def stock_info(self) -> pl.DataFrame:
        """全市場股票基本資料表。"""
        rows = self._get("TaiwanStockInfo")
        if not rows:
            return pl.DataFrame()
        df = pl.from_dicts(rows)
        # 確定性順序 + 防重複 stock_id
        if "stock_id" in df.columns:
            df = df.unique(subset=["stock_id"]).sort("stock_id")
        return df

    def daily_price(
        self, stock_id: str, start: date, end: date
    ) -> pl.DataFrame:
        """日 K 資料 (open/high/low/close/volume/turnover/transactions/spread)。

        FinMind 偶有重複日 (盤後 rerun) 或亂序，這裡統一 sort+unique 保證下游不需處理。
        """
        rows = self._get(
            "TaiwanStockPrice",
            data_id=stock_id,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
        )
        if not rows:
            return pl.DataFrame()

        df = pl.from_dicts(rows)
        # cast(strict=False): API 偶爾回 null / 空字串時轉成 null 而非炸錯
        df = df.select(
            pl.col("stock_id"),
            pl.col("date").str.to_date(),
            pl.col("open").cast(pl.Float64, strict=False),
            pl.col("max").cast(pl.Float64, strict=False).alias("high"),
            pl.col("min").cast(pl.Float64, strict=False).alias("low"),
            pl.col("close").cast(pl.Float64, strict=False),
            pl.col("Trading_Volume").cast(pl.Int64, strict=False).alias("volume"),
            pl.col("Trading_money").cast(pl.Float64, strict=False).alias("turnover"),
            pl.col("Trading_turnover").cast(pl.Int64, strict=False).alias("transactions"),
            pl.col("spread").cast(pl.Float64, strict=False),
        )
        # 確定性順序 + 防 (stock_id, date) 重複
        return df.unique(subset=["stock_id", "date"]).sort("date")

    def institutional(
        self, stock_id: str, start: date, end: date
    ) -> pl.DataFrame:
        """三大法人買賣超 (raw, 未標準化欄位 — Step 2 處理 mapping)。"""
        rows = self._get(
            "TaiwanStockInstitutionalInvestorsBuySell",
            data_id=stock_id,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
        )
        if not rows:
            return pl.DataFrame()
        df = pl.from_dicts(rows)
        if "date" in df.columns:
            # 三大法人原始資料每天有三筆 (外資/投信/自營)，去重 key 必須含 name
            subset = [c for c in ("stock_id", "date", "name") if c in df.columns]
            df = df.unique(subset=subset).sort([c for c in ("date", "name") if c in df.columns])
        return df

    def monthly_revenue(
        self, stock_id: str, start: date, end: date
    ) -> pl.DataFrame:
        """月營收 (raw, Step 2 處理 mapping)。"""
        rows = self._get(
            "TaiwanStockMonthRevenue",
            data_id=stock_id,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
        )
        if not rows:
            return pl.DataFrame()
        df = pl.from_dicts(rows)
        if "date" in df.columns:
            subset = [c for c in ("stock_id", "date") if c in df.columns]
            df = df.unique(subset=subset).sort("date")
        return df

    def taiex(self, start: date, end: date) -> pl.DataFrame:
        """加權指數 (regime 判斷用)。"""
        rows = self._get(
            "TaiwanStockPrice",
            data_id="TAIEX",
            start_date=start.isoformat(),
            end_date=end.isoformat(),
        )
        if not rows:
            return pl.DataFrame()
        df = pl.from_dicts(rows)
        if "date" in df.columns:
            subset = [c for c in ("stock_id", "date") if c in df.columns]
            df = df.unique(subset=subset).sort("date")
        return df

    # ── lifecycle ─────────────────────────────────────────────

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> FinMindClient:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
