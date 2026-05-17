# features/regime.py
"""TAIEX-based market regime classifier (deterministic, v0.1).

採納 reviewer 建議：
- 先 deterministic, **不**上 HMM (latent state estimation)
- v0.1 需要的是 "market intuition encoding"，不是 statistical model
- breadth_ratio (broader market) 延後到 v0.1.12 (要計算全市場 SMA50/symbol)

Regime 規則:
  crisis:  vol_20 > 0.020  (TAIEX 20-day return stdev 大於 2% = 恐慌等級)
  bull:    close > sma_200  AND vol_20 <= 0.020  (順趨勢上升, 波動正常)
  bear:    close < sma_200  AND vol_20 <= 0.020  (順趨勢下行, 波動正常)
  neutral: 其他 (跨越 SMA200 的過渡時期)

閾值 0.020 的根據:
  TAIEX 常態日波動 ~0.7-1.5% (daily stdev)
  歷史 crisis events (COVID-2020, 2022 升息, 2024 八月套利交易回補) 都見 vol_20 > 2%
  v0.2 可以改 expanding window quantile，但 v0.1 用固定閾值更可解釋

Input: daily_price (raw, TAIEX 用 stock_id='TAIEX'), columns: date, close
Output: date, taiex_close, sma_200, vol_20, regime

Version: v0.1.0 (2026-05-17)
Changelog:
  v0.1.0 (2026-05-17): Initial — 4-state deterministic regime
                       (bull / bear / crisis / neutral)
"""
from __future__ import annotations

import polars as pl

# Regime thresholds (v0.1 hardcoded, v0.2 可考慮 expanding window quantile)
CRISIS_VOL_THRESHOLD = 0.020   # 20-day return stdev (~2%/day = 年化 ~32%)


def compute_regime(
    taiex_df: pl.DataFrame,
    crisis_vol: float = CRISIS_VOL_THRESHOLD,
) -> pl.DataFrame:
    """Compute daily regime classification from TAIEX close series.

    Args:
        taiex_df: DataFrame with columns (date, close); should be TAIEX raw.
        crisis_vol: vol_20 threshold for "crisis" regime (default 0.020).

    Returns:
        DataFrame with columns: date, taiex_close, sma_200, vol_20, regime
    """
    df = taiex_df.sort("date").select(["date", "close"])

    df = df.with_columns(
        sma_200=pl.col("close").rolling_mean(200),
        daily_ret=(pl.col("close") / pl.col("close").shift(1) - 1),
    )

    df = df.with_columns(
        vol_20=pl.col("daily_ret").rolling_std(20),
    )

    df = df.with_columns(
        regime=(
            pl.when(pl.col("vol_20") > crisis_vol)
            .then(pl.lit("crisis"))
            .when(
                (pl.col("close") > pl.col("sma_200"))
                & (pl.col("vol_20") <= crisis_vol)
            )
            .then(pl.lit("bull"))
            .when(
                (pl.col("close") < pl.col("sma_200"))
                & (pl.col("vol_20") <= crisis_vol)
            )
            .then(pl.lit("bear"))
            .otherwise(pl.lit("neutral"))
        ),
    )

    return df.select([
        pl.col("date"),
        pl.col("close").alias("taiex_close"),
        pl.col("sma_200"),
        pl.col("vol_20"),
        pl.col("regime"),
    ])
