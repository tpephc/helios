#!/usr/bin/env python3
# scripts/download_daily.py
"""下載日 K 資料到 DuckDB (增量更新 + watermark)。

設計：
- 預設從 config/universe.yaml 讀取要下載的 symbols + 強制加 TAIEX
- 用 DataFetcher (走 cache + FinMind)，自動 rate limit
- 寫入 DuckDB daily_price 表 (先刪重疊區間再 INSERT，DuckDB 無 ON CONFLICT REPLACE)
- 兩張紀錄表分工：
    ingest_watermark  → 「我們抓到哪天」(stock_id, dataset, last_date)
    data_quality_log  → 「每次抓的事件」(run_at, status, rows, error_msg)
  下次跑只抓 watermark 之後的日期；歷史軌跡留在 data_quality_log
- 失敗的 symbol 記錄但繼續，最後 summary
- FinMind 免費版限速：fetcher 內建 rate limiter，~30 檔 symbol 全跑可能需要幾分鐘

使用：
  uv run python scripts/download_daily.py                          # 增量 (從 watermark 起)
  uv run python scripts/download_daily.py --full                   # 全部重抓 5 年
  uv run python scripts/download_daily.py --symbols 2330,0050      # 指定 symbols
  uv run python scripts/download_daily.py --start 2020-01-01       # 指定起日

輸出：stdout 進度 + structlog JSON 到 logs/helios.log

Version: v0.1.0 (2026-05-16)
Changelog:
  v0.1.0 (2026-05-16): Initial implementation
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timedelta
from typing import Any

import polars as pl

from config import load_universe
from data.database import connect, init_schema
from data.fetcher import DataFetcher
from utils.logger import get_logger

logger = get_logger(__name__)

# 預設抓 5 年歷史
DEFAULT_HISTORY_DAYS = 365 * 5

DATASET = "daily_price"


# ─────────────────────────────────────────────────────────────
# Universe 解析
# ─────────────────────────────────────────────────────────────


def get_universe_symbols() -> list[str]:
    """從 universe.yaml 拉出全部 symbols + 強制加 TAIEX。

    universe.yaml 結構：
      universes:
        <bucket>:
          include_specific:  ← 我們讀這個 key (寫死的 symbol list)
            - "0050"
            - "2330"
          include_keywords: [...]  ← criteria-based，這裡不解析
          market_cap_min_twd: ...  ← criteria-based
      dynamic_top200:
        symbols: [...]  ← v0.1.15: managed by scripts/sync_universe.py
    """
    universe = load_universe()
    symbols: set[str] = set()
    for _, u_def in universe.get("universes", {}).items():
        for sym in u_def.get("include_specific", []):
            symbols.add(str(sym))
    # v0.1.15: dynamic universe symbols (managed by sync_universe.py)
    for sym in universe.get("dynamic_top200", {}).get("symbols", []):
        symbols.add(str(sym))
    symbols.add("TAIEX")  # 一律加 TAIEX (regime 偵測必須)
    return sorted(symbols)


# ─────────────────────────────────────────────────────────────
# Watermark (where we are)
# ─────────────────────────────────────────────────────────────


def get_watermark(stock_id: str) -> date | None:
    """取得某 symbol 已抓到的最後日期。"""
    with connect(read_only=True) as conn:
        row = conn.execute(
            "SELECT last_date FROM ingest_watermark WHERE stock_id = ? AND dataset = ?",
            [stock_id, DATASET],
        ).fetchone()
    if row is None or row[0] is None:
        return None
    val = row[0]
    return val if isinstance(val, date) else val.date()


def update_watermark(stock_id: str, last_date: date) -> None:
    """更新 watermark (DELETE + INSERT 等同 upsert)。"""
    with connect() as conn:
        conn.execute(
            "DELETE FROM ingest_watermark WHERE stock_id = ? AND dataset = ?",
            [stock_id, DATASET],
        )
        conn.execute(
            "INSERT INTO ingest_watermark (stock_id, dataset, last_date) VALUES (?, ?, ?)",
            [stock_id, DATASET, last_date],
        )


# ─────────────────────────────────────────────────────────────
# Quality log (what happened)
# ─────────────────────────────────────────────────────────────


def log_run(
    stock_id: str, rows: int, status: str,
    error: str | None = None, quality_issues: list[str] | None = None,
) -> None:
    """記錄一次抓取事件到 data_quality_log。

    狀態：ok / empty / error / warn (warn = 抓成功但有 quality_issues)
    """
    msg_parts: list[str] = []
    if error:
        msg_parts.append(error)
    if quality_issues:
        msg_parts.append(f"issues={quality_issues}")
    error_msg = "; ".join(msg_parts) if msg_parts else None

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO data_quality_log (source, dataset, stock_id, rows_fetched, status, error_msg)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ["finmind", DATASET, stock_id, rows, status, error_msg],
        )


# ─────────────────────────────────────────────────────────────
# DuckDB writes
# ─────────────────────────────────────────────────────────────


def insert_daily_prices(df: pl.DataFrame) -> int:
    """把 daily_price DataFrame 寫入 DuckDB。

    策略：每個 (stock_id, 區間) 先 DELETE 後 INSERT，避免 PRIMARY KEY 衝突。
    DuckDB 不支援 ON CONFLICT REPLACE on multi-row insert，所以走 DELETE+INSERT。
    """
    if df.is_empty():
        return 0

    stock_ids = df["stock_id"].unique().to_list()
    min_d = df["date"].min()
    max_d = df["date"].max()

    with connect() as conn:
        # 先刪該 symbol 該區間舊資料
        for sid in stock_ids:
            conn.execute(
                "DELETE FROM daily_price WHERE stock_id = ? AND date BETWEEN ? AND ?",
                [sid, min_d, max_d],
            )
        # 再批次 INSERT (Arrow zero-copy)
        conn.register("df_in", df.to_arrow())
        try:
            conn.execute("INSERT INTO daily_price SELECT * FROM df_in")
        finally:
            conn.unregister("df_in")
    return df.height


# ─────────────────────────────────────────────────────────────
# Per-symbol download
# ─────────────────────────────────────────────────────────────

# daily_price 表的標準欄位順序 (與 schema 對齊)
PRICE_COLUMNS = [
    "stock_id", "date", "open", "high", "low", "close",
    "volume", "turnover", "transactions", "spread",
]


def _normalize_price_df(df: pl.DataFrame, stock_id: str) -> pl.DataFrame:
    """確保欄位齊全、順序對。TAIEX 沒 stock_id → 補上。"""
    if "stock_id" not in df.columns:
        df = df.with_columns(stock_id=pl.lit(stock_id))

    # 補缺欄位 (FinMind 偶爾少回某欄)
    for col in PRICE_COLUMNS:
        if col not in df.columns:
            if col in ("volume", "transactions"):
                df = df.with_columns(pl.lit(None).cast(pl.Int64).alias(col))
            elif col == "stock_id":
                df = df.with_columns(stock_id=pl.lit(stock_id))
            else:
                df = df.with_columns(pl.lit(None).cast(pl.Float64).alias(col))

    return df.select(PRICE_COLUMNS)


def download_one(
    fetcher: DataFetcher, stock_id: str, start: date, end: date
) -> dict[str, Any]:
    """抓單一 symbol 並寫入 DB。回傳 metadata，不丟例外。"""
    logger.info("download_start", stock_id=stock_id, start=str(start), end=str(end))

    if stock_id == "TAIEX":
        result = fetcher.taiex(start, end)
    else:
        result = fetcher.daily_price(stock_id, start, end)

    if not result.success:
        log_run(stock_id, 0, "error", error=result.error)
        return {
            "stock_id": stock_id, "status": "failed",
            "error": result.error, "rows": 0,
        }

    if result.data.is_empty():
        # 成功但空 — 該區間沒交易資料 (常見於剛上市 / 已下市 / 已抓過全部)
        log_run(stock_id, 0, "empty")
        # 不更新 watermark (避免被誤判為已抓到 end)
        return {"stock_id": stock_id, "status": "no_data", "rows": 0}

    df = _normalize_price_df(result.data, stock_id)
    n = insert_daily_prices(df)
    last_date = df["date"].max()
    update_watermark(stock_id, last_date)

    status = "warn" if result.quality_issues else "ok"
    log_run(stock_id, n, status, quality_issues=result.quality_issues)

    return {
        "stock_id": stock_id, "status": "ok", "rows": n,
        "first_date": str(df["date"].min()),
        "last_date": str(last_date),
        "source": result.source,
        "quality_issues": result.quality_issues,
    }


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download daily K data into DuckDB (incremental + watermarked)"
    )
    parser.add_argument(
        "--full", action="store_true",
        help=f"強制重抓最近 {DEFAULT_HISTORY_DAYS // 365} 年 (忽略 watermark)",
    )
    parser.add_argument(
        "--symbols", type=str,
        help="逗號分隔的 symbols；不給就讀 universe.yaml",
    )
    parser.add_argument(
        "--start", type=lambda s: date.fromisoformat(s),
        help="起日 (YYYY-MM-DD)，預設依 watermark / 5 年前",
    )
    parser.add_argument(
        "--end", type=lambda s: date.fromisoformat(s),
        help="迄日 (YYYY-MM-DD)，預設今天",
    )
    args = parser.parse_args()

    # 確保 schema 就緒
    init_schema()

    # 決定 symbols
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = get_universe_symbols()

    # 決定日期範圍
    end = args.end or date.today()
    explicit_start = args.start
    force_full = args.full

    print(f"Helios download_daily — {datetime.now().isoformat(timespec='seconds')}")
    print(f"Symbols: {len(symbols)} → {symbols}")
    print(f"End date: {end}")
    if explicit_start:
        print(f"Start: {explicit_start} (explicit)")
    elif force_full:
        print(f"Start: {end - timedelta(days=DEFAULT_HISTORY_DAYS)} (--full)")
    else:
        print(f"Start: (per-symbol from watermark, falls back to {DEFAULT_HISTORY_DAYS // 365}yr ago)")
    print()

    t0 = time.time()
    results: list[dict[str, Any]] = []

    with DataFetcher() as fetcher:
        for i, sid in enumerate(symbols, 1):
            # 決定該 symbol 的 effective start
            wm: date | None = None
            if explicit_start is not None:
                start = explicit_start
            elif force_full:
                start = end - timedelta(days=DEFAULT_HISTORY_DAYS)
            else:
                wm = get_watermark(sid)
                if wm is None:
                    start = end - timedelta(days=DEFAULT_HISTORY_DAYS)
                else:
                    start = wm + timedelta(days=1)

            if start > end:
                print(f"  [{i:2d}/{len(symbols)}] ─ {sid:8s} already up to date (watermark = {wm})")
                results.append({"stock_id": sid, "status": "skipped", "rows": 0})
                continue

            try:
                r = download_one(fetcher, sid, start, end)
                results.append(r)
                status_icon = {
                    "ok": "✓", "no_data": "○", "failed": "✗",
                    "skipped": "─",
                }.get(r["status"], "?")
                detail = f"{r['rows']} rows"
                if r.get("last_date"):
                    detail += f" → {r['last_date']}"
                if r.get("quality_issues"):
                    detail += f"  ⚠ {r['quality_issues']}"
                print(f"  [{i:2d}/{len(symbols)}] {status_icon} {sid:8s} {detail}")
            except Exception as e:
                logger.exception("download_unexpected_error", stock_id=sid)
                log_run(sid, 0, "error", error=f"{type(e).__name__}: {e}")
                results.append({
                    "stock_id": sid, "status": "error",
                    "error": f"{type(e).__name__}: {e}", "rows": 0,
                })
                print(f"  [{i:2d}/{len(symbols)}] ✗ {sid:8s} ERROR: {e}")

    elapsed = time.time() - t0

    # Summary
    print(f"\n{'='*60}\nSummary ({elapsed:.1f}s)\n{'='*60}")
    by_status: dict[str, int] = {}
    total_rows = 0
    for r in results:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        total_rows += r.get("rows", 0)

    for status in ("ok", "no_data", "skipped", "failed", "error"):
        if status in by_status:
            print(f"  {status:8s}: {by_status[status]}")
    print(f"  total_rows_inserted: {total_rows:,}")

    failed = by_status.get("failed", 0) + by_status.get("error", 0)
    if failed:
        print(f"\n⚠ {failed} symbol(s) failed. Check data_quality_log for details.")
        for r in results:
            if r["status"] in ("failed", "error"):
                print(f"    {r['stock_id']}: {r.get('error', 'unknown')}")
        return 1

    print("\n✓ All symbols processed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
