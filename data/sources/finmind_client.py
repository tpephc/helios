# data/sources/finmind_client.py
"""FinMind v4 API client：rate limit + 退避 + Polars 輸出。

設計要點：
- 免費版每分鐘限速嚴格 → 內建 token-bucket 保證間隔
- 撞到 402 (rate limited) 退避後重試 (tenacity 包裝)
- 輸出統一為 Polars DataFrame，欄位標準化
- 所有 return path 強制 sort("date").unique(subset=...) 保證決定性順序與去重
- 數值欄位用 cast(strict=False) 容忍 API 偶發 null/錯型
- 與 fetcher.py 解耦：本 client 只負責「呼叫 + 轉型 + 衛生」

Version: v0.1.4 (2026-05-16)
Changelog:
  v0.1.4 (2026-05-16): 新增 dividend_result() (TaiwanStockDividendResult, 免費版可用,
                       提供 before/after/factor — adjustment 原料)
  v0.1.3 (2026-05-16): hotfix - revert TaiwanStockPriceAdj → TaiwanStockPrice (Sponsor 限定);
                       adjustment ownership 移到 features layer (v0.1.10)
  v0.1.2 (2026-05-16): daily_price 改用 TaiwanStockPriceAdj (還原權息價);
                       TAIEX 維持 TaiwanStockPrice (指數無 split/dividend)
  v0.1.1 (2026-05-16): 所有 return path 加 sort+unique 確保時序確定性;
                       cast 改用 strict=False 容忍 API null
  v0.1.0 (2026-05-16): Initial implementation
"""
from __future__ import annotations

import re
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


# v0.1.14.3.4 — secret-redaction in URLs that may end up in logs.
# Pre-v0.1.14.3.4 the FinMind ?token=... appeared verbatim in tracebacks
# whenever httpx.HTTPStatusError propagated (helios.log.2026-05-16 incident,
# where 400 responses from data backfill leaked every JWT to disk). The
# redacted form must keep diagnostic context (host, status, dataset, dates)
# while stripping the bearer credential.
_SECRET_PARAMS = re.compile(
    r"(?i)(token|api_key|apikey|secret|password)=[^&\s]+",
)


def _redact_url(url: str) -> str:
    """Strip sensitive query parameters from a URL for safe logging.

    Replaces value of `token=`, `api_key=` / `apikey=`, `secret=`, `password=`
    (case-insensitive) with `***REDACTED***`. Other params and the URL
    structure are preserved so logs remain useful for debugging.

    Pure function — pinned by `tests/invariants/test_semantic_invariants.py`.
    """
    return _SECRET_PARAMS.sub(r"\1=***REDACTED***", url)


def _raise_finmind_http_error(e: httpx.HTTPStatusError) -> None:
    """Convert httpx HTTPStatusError into a FinMindError with redacted URL.

    v0.1.14.3.4 contract: callers MUST route HTTPStatusError through this
    helper rather than letting it propagate. The default `str(e)` includes
    the full request URL — passing it to a logger with `exc_info=True`
    leaks any `?token=...` query parameter into persistent log files.

    Mechanism: build a new FinMindError carrying ONLY the redacted URL and
    status code, then `raise ... from None` so the original HTTPStatusError
    is dropped from both __cause__ and __context__ chains (otherwise the
    full URL would still print via Python's "During handling of the above
    exception" chained-traceback display).

    FinMindError is in tenacity's `retry_if_exception_type` tuple, so retry
    semantics are preserved across the conversion.
    """
    safe_url = _redact_url(str(e.response.url))
    logger.warning(
        "finmind_http_error",
        status=e.response.status_code, url=safe_url,
    )
    raise FinMindError(
        f"HTTP {e.response.status_code} from FinMind ({safe_url})"
    ) from None


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

        # v0.1.14.3.4 — route HTTPStatusError through redacting helper so
        # ?token=... never reaches tracebacks. See _raise_finmind_http_error.
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            _raise_finmind_http_error(e)
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

        【v0.1.7 hotfix】用 `TaiwanStockPrice` (raw)：
        - TaiwanStockPriceAdj 經實測需 FinMind Sponsor 付費版 (免費 register tier 拒絕)
        - 維持 raw 反而符合 "adjustment ownership 在 features layer" 原則
        - 跟 TWSE raw 一致，方便 cross-source validate
        - dividend / split adjustment 由 v0.1.9 的 features/dividend_adjustment.py 處理
          (用 TWSE TWTB4U 已知除權息日 + STOCK_DAY 註記 拆分標記)

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

    def dividend_result(
        self, stock_id: str, start: date, end: date
    ) -> pl.DataFrame:
        """除權除息結果表 (歷史已發生的除權息事件)。

        【v0.1.3】這是免費版可用的 dataset (vs TaiwanStockPriceAdj 需 Sponsor)。
        FinMind 直接給「除息前/後參考價」，比自己算 adjustment factor 更準。

        Schema (FinMind 原生):
          - date:                          除權息交易日 (ISO YYYY-MM-DD)
          - stock_id:                      股票代碼
          - before_price:                  除權息前收盤價
          - after_price:                   除權息參考價 (=after div adjustment)
          - stock_and_cache_dividend:      股利金額 (現金/股票/合計)
          - stock_or_cache_dividend:       類型: "權" / "息" / "權息"
          - max_price/min_price/open_price/reference_price: 除息當日其他價

        Helios 標準化輸出：
          stock_id, date, kind, before_price, after_price,
          dividend_amount, adjustment_factor (= after / before)
        """
        rows = self._get(
            "TaiwanStockDividendResult",
            data_id=stock_id,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
        )
        if not rows:
            return pl.DataFrame()

        df = pl.from_dicts(rows)
        df = df.select(
            pl.col("stock_id"),
            pl.col("date").str.to_date(),
            pl.col("stock_or_cache_dividend").alias("kind"),
            pl.col("before_price").cast(pl.Float64, strict=False),
            pl.col("after_price").cast(pl.Float64, strict=False),
            pl.col("stock_and_cache_dividend").cast(pl.Float64, strict=False)
                .alias("dividend_amount"),
        ).with_columns(
            # adjustment_factor = after / before; 用來把舊資料往下調
            adjustment_factor=(pl.col("after_price") / pl.col("before_price")),
        )
        return df.unique(subset=["stock_id", "date", "kind"]).sort("date")

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

    def market_value_all(self, on_date: date) -> pl.DataFrame:
        """Market cap for ALL listed stocks on a given date.

        Uses TaiwanStockMarketValue without data_id — returns one row per
        listed stock. Suitable for universe construction (rank by market_value).

        v0.1.15: added for sync_universe.py dynamic top-N universe.

        Note: free-tier availability not yet confirmed in production. Script
        falls back gracefully (returns empty DataFrame) if endpoint is
        inaccessible; caller must handle empty case.
        """
        rows = self._get(
            "TaiwanStockMarketValue",
            start_date=on_date.isoformat(),
            end_date=on_date.isoformat(),
        )
        if not rows:
            return pl.DataFrame()
        df = pl.from_dicts(rows)
        required = {"stock_id", "market_value"}
        if not required.issubset(df.columns):
            logger.warning(
                "market_value_all_unexpected_columns",
                got=df.columns,
                expected=list(required),
            )
            return pl.DataFrame()
        df = df.select(
            pl.col("stock_id"),
            pl.col("date").str.to_date() if "date" in df.columns
                else pl.lit(on_date).alias("date"),
            pl.col("market_value").cast(pl.Float64, strict=False),
        )
        return (
            df.drop_nulls(subset=["market_value"])
            .unique(subset=["stock_id"])
            .sort("market_value", descending=True)
        )

    # ── lifecycle ─────────────────────────────────────────────

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> FinMindClient:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
