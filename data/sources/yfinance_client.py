# data/sources/yfinance_client.py
"""yfinance client - 用於 cross-source validation (5 年隨意抓)。

定位：
- 角色 = cross-validation / 最後 fallback
- yfinance 對台股代號是 `2330.TW` 格式
- TAIEX 代號是 `^TWII`
- 提供 raw OHLC 和 Adj Close (Yahoo 自己的還原權息)
  → 是我們驗證自己 dividend_adjustment 邏輯的「第三方參考」

重要限制：
- Yahoo 反爬偶爾擋 (429 / empty response)
- 對台股 Adj Close 演算法不一定跟 TWSE 一致
- 不適合 daily ops 主力，只做抽樣 / fallback

Version: v0.1.0 (2026-05-16)
Changelog:
  v0.1.0 (2026-05-16): Initial — daily_price + taiex，回傳含 adj_close 欄位
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import polars as pl

from utils.logger import get_logger

logger = get_logger(__name__)


class YFinanceError(Exception):
    """yfinance 抓取失敗。"""


def _stock_id_to_yf_ticker(stock_id: str) -> str:
    """Helios stock_id → yfinance ticker。

    Helios 內部用 4 碼 (如 "2330", "0050") 或 "TAIEX"。
    yfinance 台股是 `2330.TW`，TAIEX 是 `^TWII`。
    """
    if stock_id == "TAIEX":
        return "^TWII"
    # 已經是 yfinance 格式則原樣返回
    if "." in stock_id or stock_id.startswith("^"):
        return stock_id
    return f"{stock_id}.TW"


class YFinanceClient:
    """yfinance wrapper，輸出 Polars。"""

    def __init__(self) -> None:
        # Lazy import yfinance — Yahoo 偶爾抓不到，import 太早會 noisy
        try:
            import yfinance as yf
            self._yf = yf
        except ImportError as e:
            raise YFinanceError(
                "yfinance not installed; run 'uv sync' to get it"
            ) from e

    def daily_price(
        self, stock_id: str, start: date, end: date
    ) -> pl.DataFrame:
        """日 K 資料 (raw OHLC + Adj Close)。

        Returns:
            Columns: stock_id, date, open, high, low, close, adj_close, volume
            stock_id 維持 Helios 內部格式 (不是 yfinance ticker)
        """
        ticker = _stock_id_to_yf_ticker(stock_id)
        logger.info("yf_fetch_start", stock_id=stock_id, ticker=ticker,
                    start=str(start), end=str(end))

        try:
            yt = self._yf.Ticker(ticker)
            # yfinance end is exclusive → +1 day
            df_pd = yt.history(
                start=start.isoformat(),
                end=(end + timedelta(days=1)).isoformat(),
                auto_adjust=False,  # 我們要 raw + Adj Close 兩個都拿
            )
        except Exception as e:
            raise YFinanceError(f"yfinance fetch failed for {ticker}: {e}") from e

        if df_pd.empty:
            return pl.DataFrame()

        # df_pd 的 index 是 DatetimeIndex；reset 後拿到 Date 欄
        df_pd = df_pd.reset_index()

        # 統一欄名 (yfinance 可能用 'Date' or 'Datetime')
        date_col = "Date" if "Date" in df_pd.columns else "Datetime"

        df = pl.from_pandas(df_pd)

        # 處理 Adj Close 可能不存在的情況 (auto_adjust=True 時)
        cols: list[Any] = [
            pl.lit(stock_id).alias("stock_id"),
            pl.col(date_col).dt.date().alias("date"),
            pl.col("Open").cast(pl.Float64).alias("open"),
            pl.col("High").cast(pl.Float64).alias("high"),
            pl.col("Low").cast(pl.Float64).alias("low"),
            pl.col("Close").cast(pl.Float64).alias("close"),
        ]
        if "Adj Close" in df.columns:
            cols.append(pl.col("Adj Close").cast(pl.Float64).alias("adj_close"))
        else:
            cols.append(pl.lit(None).cast(pl.Float64).alias("adj_close"))
        cols.append(pl.col("Volume").cast(pl.Int64, strict=False).alias("volume"))

        return df.select(cols).sort("date")

    def taiex(self, start: date, end: date) -> pl.DataFrame:
        """加權指數 (^TWII)。

        Note: yfinance 對指數通常沒有 Adj Close (跟原 Close 相同) 也沒有 Volume。
        """
        return self.daily_price("TAIEX", start, end)
