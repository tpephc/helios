# features/dividend_adjustment.py
"""Dividend / split 還原權息 — Helios 自家 adjustment layer.

設計原則:
- FinMind 免費版只給 raw price + dividend events，不給 adjusted；
  我們用 events.adjustment_factor 自己算，**完全可解釋**
- 演算法：canonical backward adjustment
- volume: 暫不調整 (cash dividend 不影響股數，純 split 才需要)
- 純函數 + DB wrapper 分離，便於 unit test

演算法 (給定 stock_id 的 raw daily_price + events with factor):

  cum_factor[T] = ∏ event_factor[E]  for all events E where E.date > T
  adj_close[T]  = raw_close[T] * cum_factor[T]
  (open / high / low 同邏輯)

  關鍵：除權息日「當天」的 raw close 已經是除息後價，所以該日的
  cum_factor 不再乘上自己這個 event (只乘**未來的** events)。

Polars 實作 trick:
  sort by date DESC, shift event_factor by 1 (fill 1.0), cum_prod()
  → 索引 i 的 cum_factor = product of factors at indices 0..i-1
  → 索引 i 對應 date 之後的所有 event factor 累積

Version: v0.1.0 (2026-05-16)
Changelog:
  v0.1.0 (2026-05-16): Initial — canonical backward adjustment
                       + freshness state + DB read/write helpers
"""
from __future__ import annotations

from datetime import date, datetime
from typing import NamedTuple

import polars as pl

from data.database import connect
from utils.logger import get_logger

logger = get_logger(__name__)


class AdjustmentResult(NamedTuple):
    """compute_adjusted 的回傳結果."""
    adjusted: pl.DataFrame              # daily_price_adj 表 schema
    n_events_applied: int               # 用了幾個 event
    last_event_date_used: date | None   # 最晚 event date (給 freshness 用)
    first_date: date | None             # raw 的第一天
    last_date: date | None              # raw 的最後一天


# ─────────────────────────────────────────────────────────────
# 純函數 — compute_adjusted (給 raw + events, 回傳 adjusted)
# ─────────────────────────────────────────────────────────────


def compute_adjusted(
    df_raw: pl.DataFrame,
    df_events: pl.DataFrame,
) -> AdjustmentResult:
    """純函數：raw price + events → adjusted price.

    Args:
        df_raw: columns = stock_id, date, open, high, low, close, volume
        df_events: columns = date, adjustment_factor
                   (factor < 1.0 表示除權息往下調)

    Returns:
        AdjustmentResult with `adjusted` DataFrame having
        columns: stock_id, date, adj_open, adj_high, adj_low, adj_close,
                 raw_close, cum_factor, volume
    """
    if df_raw.is_empty():
        return AdjustmentResult(
            adjusted=pl.DataFrame(),
            n_events_applied=0,
            last_event_date_used=None,
            first_date=None,
            last_date=None,
        )

    df = df_raw.sort("date")
    first_d = df["date"].min()
    last_d = df["date"].max()

    if df_events.is_empty():
        # 沒事件 → adj 直接等於 raw, cum_factor 全部 1.0
        df_out = df.with_columns(
            adj_open=pl.col("open"),
            adj_high=pl.col("high"),
            adj_low=pl.col("low"),
            adj_close=pl.col("close"),
            raw_close=pl.col("close"),
            cum_factor=pl.lit(1.0),
        ).select([
            "stock_id", "date", "adj_open", "adj_high", "adj_low", "adj_close",
            "raw_close", "cum_factor", "volume",
        ])
        return AdjustmentResult(
            adjusted=df_out,
            n_events_applied=0,
            last_event_date_used=None,
            first_date=first_d,
            last_date=last_d,
        )

    # 防禦：同 (stock_id, date) 多筆 event (如同日 權+息) → 把 factor product 合併
    events = (
        df_events.select(["date", "adjustment_factor"])
        .filter(pl.col("adjustment_factor").is_not_null())
        .group_by("date")
        .agg(event_factor=pl.col("adjustment_factor").product())
    )

    # 把 event factor join 到 raw, 沒事件的日子 factor = 1.0
    df_j = df.join(events, on="date", how="left").with_columns(
        pl.col("event_factor").fill_null(1.0)
    )

    # 演算法核心：sort DESC + shift(1) + cum_prod
    # ───────────────────────────────────────────────
    # 索引 0 (最晚一天) 的 cum_factor 應該是 1.0 (沒有「之後」的 event)
    # 索引 1 的 cum_factor = event_factor[0] (索引 0 的 event)
    # 索引 i 的 cum_factor = ∏ event_factor[0..i-1]
    # 對應到 chronological 順序：cum_factor[T] = ∏ factor at dates > T
    df_j = df_j.sort("date", descending=True).with_columns(
        cum_factor=pl.col("event_factor").shift(1, fill_value=1.0).cum_prod()
    ).sort("date")  # 還原時序

    df_out = df_j.with_columns(
        adj_open=pl.col("open") * pl.col("cum_factor"),
        adj_high=pl.col("high") * pl.col("cum_factor"),
        adj_low=pl.col("low") * pl.col("cum_factor"),
        adj_close=pl.col("close") * pl.col("cum_factor"),
        raw_close=pl.col("close"),
    ).select([
        "stock_id", "date", "adj_open", "adj_high", "adj_low", "adj_close",
        "raw_close", "cum_factor", "volume",
    ])

    n_events = events.height
    last_event = events["date"].max() if n_events > 0 else None

    return AdjustmentResult(
        adjusted=df_out,
        n_events_applied=n_events,
        last_event_date_used=last_event,
        first_date=first_d,
        last_date=last_d,
    )


# ─────────────────────────────────────────────────────────────
# DB wrappers
# ─────────────────────────────────────────────────────────────


def build_for_symbol(stock_id: str) -> AdjustmentResult:
    """從 DB 讀 raw + events，跑 compute_adjusted (不寫回 DB)."""
    with connect(read_only=True) as conn:
        raw_arrow = conn.execute(
            """
            SELECT stock_id, date, open, high, low, close, volume
            FROM daily_price
            WHERE stock_id = ?
            ORDER BY date
            """,
            [stock_id],
        ).to_arrow_table()

        events_arrow = conn.execute(
            """
            SELECT date, adjustment_factor
            FROM corporate_actions
            WHERE stock_id = ?
              AND confirmed = TRUE
              AND adjustment_factor IS NOT NULL
            ORDER BY date
            """,
            [stock_id],
        ).to_arrow_table()

    raw_df = pl.from_arrow(raw_arrow)
    events_df = pl.from_arrow(events_arrow)
    return compute_adjusted(raw_df, events_df)


def write_adjusted_to_db(stock_id: str, result: AdjustmentResult) -> None:
    """把 AdjustmentResult 寫進 daily_price_adj + 更新 adjustment_state."""
    if result.adjusted.is_empty():
        logger.info("write_adjusted_skipped_empty", stock_id=stock_id)
        return

    with connect() as conn:
        # daily_price_adj: delete + insert (避免 PK 衝突)
        conn.execute(
            "DELETE FROM daily_price_adj WHERE stock_id = ?", [stock_id]
        )
        conn.register("inp", result.adjusted.to_arrow())
        try:
            conn.execute("INSERT INTO daily_price_adj SELECT * FROM inp")
        finally:
            conn.unregister("inp")

        # adjustment_state: upsert (DELETE + INSERT)
        conn.execute(
            "DELETE FROM adjustment_state WHERE stock_id = ?", [stock_id]
        )
        conn.execute(
            """
            INSERT INTO adjustment_state
            (stock_id, last_built_at, last_event_date_used, n_events_applied,
             raw_first_date, raw_last_date)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                stock_id,
                datetime.now(),
                result.last_event_date_used,
                result.n_events_applied,
                result.first_date,
                result.last_date,
            ],
        )


# ─────────────────────────────────────────────────────────────
# Freshness check
# ─────────────────────────────────────────────────────────────


def get_freshness_status() -> list[dict]:
    """比對 raw + events 跟 adjustment_state，找出該重建的 symbol.

    Returns:
        list of {stock_id, stale, reasons[], raw_latest, event_latest, state_*}
    """
    with connect(read_only=True) as conn:
        rows = conn.execute("""
            SELECT
                dp.stock_id,
                MAX(dp.date) AS raw_latest,
                (
                    SELECT MAX(ca.date) FROM corporate_actions ca
                    WHERE ca.stock_id = dp.stock_id
                      AND ca.confirmed = TRUE
                      AND ca.adjustment_factor IS NOT NULL
                ) AS event_latest,
                MAX(ad.last_event_date_used) AS state_event,
                MAX(ad.raw_last_date) AS state_raw_last,
                MAX(ad.last_built_at) AS built_at
            FROM daily_price dp
            LEFT JOIN adjustment_state ad ON ad.stock_id = dp.stock_id
            WHERE dp.stock_id != 'TAIEX'
            GROUP BY dp.stock_id
            ORDER BY dp.stock_id
        """).fetchall()

    result: list[dict] = []
    for r in rows:
        stock_id, raw_latest, event_latest, state_event, state_raw, built_at = r
        reasons: list[str] = []

        if built_at is None:
            reasons.append("never_built")
        else:
            if state_raw != raw_latest:
                reasons.append(f"raw_drift state={state_raw} actual={raw_latest}")
            # event_latest 可能是 None (該檔沒有 dividend event 過); 兩邊都 None 算 fresh
            if (state_event or None) != (event_latest or None):
                reasons.append(
                    f"event_drift state={state_event} actual={event_latest}"
                )

        result.append({
            "stock_id": stock_id,
            "stale": bool(reasons),
            "reasons": reasons,
            "raw_latest": raw_latest,
            "event_latest": event_latest,
            "state_event": state_event,
            "built_at": built_at,
        })
    return result
