# data/sanity.py
"""OHLC 資料衛生檢查 (row-level validation)。

用途：FinMind 偶爾回明顯錯誤的資料 (如 2317 在 2025-07-30 close=0)。
這些 bad rows 如果直接寫入 DuckDB 會污染後續 indicator/return 計算。
本模組提供統一的 filter，並回報被丟掉的行數供 quality_log 記錄。

設計原則：
- 不修改價格 (沒有 imputation)；錯的就丟，留下 audit trail
- 同一個 (stock_id, date) 全丟，不允許部分欄位有效部分無效
- 回傳 (clean_df, dropped_count, dropped_reasons) 讓 caller 決定怎麼記錄

Version: v0.1.0 (2026-05-16)
Changelog:
  v0.1.0 (2026-05-16): Initial implementation (v0.1.7 data layer hardening)
"""
from __future__ import annotations

from typing import NamedTuple

import polars as pl


class SanityResult(NamedTuple):
    """衛生檢查結果。"""

    clean: pl.DataFrame
    dropped_count: int
    dropped_reasons: list[str]  # human-readable summary of why rows were dropped


def validate_ohlc(df: pl.DataFrame) -> SanityResult:
    """檢查 OHLC 列，丟掉明顯錯誤的，回傳 SanityResult。

    判斷壞列的規則 (任一觸發即丟)：
    - close <= 0 (任何成交日 close 不可能 0 或負)
    - open <= 0
    - high <= 0 或 low <= 0
    - high < low (價區反轉)
    - 全部 OHLC 都是 null

    註：volume == 0 不算壞列 (盤整日 / 停牌日 / 流動性低 都可能 0)。
    """
    if df.is_empty():
        return SanityResult(df, 0, [])

    required_cols = {"open", "high", "low", "close"}
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        # 沒有必要欄位 → 沒辦法檢查，原樣返回
        return SanityResult(df, 0, [f"sanity_skipped_missing_cols={sorted(missing_cols)}"])

    original_n = df.height

    # 用一個 boolean expression 標記壞列
    bad_mask = (
        (pl.col("close") <= 0)
        | (pl.col("open") <= 0)
        | (pl.col("high") <= 0)
        | (pl.col("low") <= 0)
        | (pl.col("high") < pl.col("low"))
        | (
            pl.col("open").is_null()
            & pl.col("high").is_null()
            & pl.col("low").is_null()
            & pl.col("close").is_null()
        )
    )

    bad_rows = df.filter(bad_mask)
    clean = df.filter(~bad_mask)
    dropped_n = original_n - clean.height

    reasons: list[str] = []
    if dropped_n > 0:
        # 統計每個原因觸發了幾筆 (供 quality_log 記錄)
        n_zero_close = df.filter(pl.col("close") <= 0).height
        n_zero_open = df.filter(pl.col("open") <= 0).height
        n_inverted = df.filter(pl.col("high") < pl.col("low")).height
        n_all_null = df.filter(
            pl.col("open").is_null()
            & pl.col("high").is_null()
            & pl.col("low").is_null()
            & pl.col("close").is_null()
        ).height

        if n_zero_close > 0:
            reasons.append(f"close<=0:{n_zero_close}")
        if n_zero_open > 0:
            reasons.append(f"open<=0:{n_zero_open}")
        if n_inverted > 0:
            reasons.append(f"high<low:{n_inverted}")
        if n_all_null > 0:
            reasons.append(f"all_ohlc_null:{n_all_null}")

        # 把實際被丟的 (stock_id, date) 取最多 3 筆做 sample
        sample_cols = [c for c in ("stock_id", "date") if c in bad_rows.columns]
        if sample_cols:
            samples = bad_rows.select(sample_cols).head(3).to_dicts()
            reasons.append(f"samples={samples}")

    return SanityResult(clean, dropped_n, reasons)
