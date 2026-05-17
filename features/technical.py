# features/technical.py
"""Technical indicators (Polars-native, single source of truth).

設計原則 (採納外部 reviewer 建議):
- 單一檔案 (cohesion > abstraction) — v0.1 不過早拆分 trend/momentum/volatility
- LazyFrame-compatible (所有函式都用 pl.col 表達，可以 lazy / streaming)
- Polars 原生 = 透明、可 debug、無第三方依賴
- 自家實作 = 未來 debug strategy edge cases 救自己

v0.1.11 indicator 清單 (reviewer-curated minimalism):
  Trend:      SMA20, SMA50, SMA200, EMA20
  Momentum:   RSI14, ROC20
  Volatility: ATR14 (Wilder smoothed)
  Breakout:   Donchian20 high/low
  Volume:     Volume_MA20, RelativeVolume20

不做 (v0.1 robust minimalism):
  - MACD histogram zoo
  - KD / Stochastic
  - Bollinger Bands (用 ATR + SMA 已涵蓋 volatility 用途)
  - Sector relative strength (排 v0.1.12)

Input 預期: daily_price_adj 一個 symbol, columns:
  stock_id, date, adj_open, adj_high, adj_low, adj_close, raw_close,
  cum_factor, volume

Version: v0.1.0 (2026-05-17)
Changelog:
  v0.1.0 (2026-05-17): Initial — 9 indicators per reviewer-curated list
"""
from __future__ import annotations

import polars as pl

# ─────────────────────────────────────────────────────────────
# Individual indicator helpers (each 加一個 column)
# ─────────────────────────────────────────────────────────────


def add_sma(df: pl.DataFrame, window: int, col: str = "adj_close") -> pl.DataFrame:
    """Simple Moving Average. NaN/null for first (window-1) rows."""
    return df.with_columns(
        pl.col(col).rolling_mean(window).alias(f"sma_{window}")
    )


def add_ema(df: pl.DataFrame, span: int, col: str = "adj_close") -> pl.DataFrame:
    """Exponential Moving Average.

    Using span convention (TA standard): alpha = 2/(span+1).
    adjust=False 是 traditional EMA (跟 TA-Lib / pandas-ta 一致)。
    """
    alpha = 2.0 / (span + 1)
    return df.with_columns(
        pl.col(col).ewm_mean(alpha=alpha, adjust=False).alias(f"ema_{span}")
    )


def add_rsi(df: pl.DataFrame, period: int = 14, col: str = "adj_close") -> pl.DataFrame:
    """Wilder's RSI (smoothed via EWM with alpha = 1/period).

    第一個 valid RSI 值出現在 period+1 那天 (前 period 天因 shift 是 null)。
    Wilder smoothing 跟 Welles Wilder 原始公式一致 (alpha=1/N, adjust=False)。
    """
    delta = pl.col(col) - pl.col(col).shift(1)
    gain = pl.when(delta > 0).then(delta).otherwise(0.0)
    loss = pl.when(delta < 0).then(-delta).otherwise(0.0)

    alpha = 1.0 / period
    avg_gain = gain.ewm_mean(alpha=alpha, adjust=False)
    avg_loss = loss.ewm_mean(alpha=alpha, adjust=False)

    # RS = avg_gain / avg_loss, RSI = 100 - 100/(1+RS)
    # 處理 avg_loss = 0 (全漲)：強制 RSI = 100
    rs = avg_gain / avg_loss
    rsi = pl.when(avg_loss == 0).then(100.0).otherwise(100.0 - 100.0 / (1.0 + rs))
    return df.with_columns(rsi.alias(f"rsi_{period}"))


def add_roc(df: pl.DataFrame, period: int = 20, col: str = "adj_close") -> pl.DataFrame:
    """Rate of Change (%) over `period` days.

    ROC = (close - close[period 前]) / close[period 前] * 100
    """
    return df.with_columns(
        (
            (pl.col(col) / pl.col(col).shift(period) - 1) * 100
        ).alias(f"roc_{period}")
    )


def add_atr(df: pl.DataFrame, period: int = 14) -> pl.DataFrame:
    """Average True Range (Wilder smoothed).

    True Range = max(high-low, |high-prev_close|, |low-prev_close|)
    ATR = EWM smooth of TR with alpha = 1/period

    用 adj_open / adj_high / adj_low / adj_close 確保跨除權息日的 TR 不受 dividend gap 污染。
    """
    prev_close = pl.col("adj_close").shift(1)
    tr = pl.max_horizontal(
        pl.col("adj_high") - pl.col("adj_low"),
        (pl.col("adj_high") - prev_close).abs(),
        (pl.col("adj_low") - prev_close).abs(),
    )
    alpha = 1.0 / period
    return df.with_columns(
        tr.ewm_mean(alpha=alpha, adjust=False).alias(f"atr_{period}")
    )


def add_donchian(df: pl.DataFrame, window: int = 20) -> pl.DataFrame:
    """Donchian Channel: rolling high/low over `window` days.

    Breakout 訊號: close > donchian_high (向上突破) / close < donchian_low (向下跌破)
    """
    return df.with_columns(
        pl.col("adj_high").rolling_max(window).alias(f"donchian_{window}_high"),
        pl.col("adj_low").rolling_min(window).alias(f"donchian_{window}_low"),
    )


def add_volume_indicators(df: pl.DataFrame, window: int = 20) -> pl.DataFrame:
    """Volume MA + Relative Volume.

    RelativeVolume = today_volume / window-day average
      > 1.5 通常是 unusual high volume (可能突破訊號)
      < 0.5 是 unusual low volume (可能盤整)

    注意: volume 不做 dividend adjustment (cash dividend 不影響股數)
    """
    df = df.with_columns(
        pl.col("volume").rolling_mean(window).alias(f"volume_ma_{window}")
    )
    return df.with_columns(
        (pl.col("volume") / pl.col(f"volume_ma_{window}")).alias(f"rel_volume_{window}")
    )


# ─────────────────────────────────────────────────────────────
# 單一真理源 — compute_indicators
# ─────────────────────────────────────────────────────────────


def compute_indicators(df: pl.DataFrame) -> pl.DataFrame:
    """單一 symbol 的 daily_price_adj → daily_features 全部 indicator.

    Input: DataFrame with columns
      stock_id, date, adj_open, adj_high, adj_low, adj_close, volume

    Output: 加 9 個 indicator columns:
      sma_20, sma_50, sma_200, ema_20,
      rsi_14, roc_20, atr_14,
      donchian_20_high, donchian_20_low,
      volume_ma_20, rel_volume_20

    呼叫順序很重要：volume_ma_20 必須在 rel_volume_20 之前計算。
    """
    df = df.sort("date")

    # Trend
    df = add_sma(df, 20)
    df = add_sma(df, 50)
    df = add_sma(df, 200)
    df = add_ema(df, 20)

    # Momentum
    df = add_rsi(df, 14)
    df = add_roc(df, 20)

    # Volatility
    df = add_atr(df, 14)

    # Breakout
    df = add_donchian(df, 20)

    # Volume
    df = add_volume_indicators(df, 20)

    return df
