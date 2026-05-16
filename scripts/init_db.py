# scripts/init_db.py
"""初始化 Helios 資料庫。

執行流程：
  1. 建立所有 DuckDB tables (schema 來自 data/database.py)
  2. 從 FinMind 拉股票基本資料寫入 stock_info
  3. 顯示 summary

Usage:
    uv run python scripts/init_db.py

Idempotent：可重複執行，不會破壞既有資料。

Version: v0.1.0 (2026-05-16)
Changelog:
  v0.1.0 (2026-05-16): Initial implementation
"""
from __future__ import annotations

import sys

from data.database import connect, init_schema, list_tables
from data.fetcher import DataFetcher
from utils.logger import get_logger

logger = get_logger(__name__)


def load_stock_info() -> int:
    """從 FinMind 抓全市場股票基本資料寫入 DB。"""
    with DataFetcher() as fetcher:
        result = fetcher.stock_info()

    if result.data.is_empty():
        logger.error("stock_info_empty")
        return 0

    df = result.data
    logger.info(
        "stock_info_fetched",
        rows=df.height,
        source=result.source,
        cache_hit=result.cache_hit,
    )

    # 用 SQL INSERT OR REPLACE 進 DB
    with connect() as conn:
        conn.register("info_df", df.to_pandas())
        conn.execute(
            """
            INSERT OR REPLACE INTO stock_info
                (stock_id, stock_name, industry, market, is_etf, updated_at)
            SELECT
                stock_id,
                stock_name,
                industry_category AS industry,
                type AS market,
                CASE WHEN industry_category = 'ETF' THEN TRUE ELSE FALSE END,
                CURRENT_TIMESTAMP
            FROM info_df
            WHERE stock_id IS NOT NULL
            """
        )
        n = conn.execute("SELECT COUNT(*) FROM stock_info").fetchone()[0]
        n_etf = conn.execute(
            "SELECT COUNT(*) FROM stock_info WHERE is_etf = TRUE"
        ).fetchone()[0]

    logger.info("stock_info_loaded", total=n, etfs=n_etf)
    return n


def main() -> int:
    logger.info("init_db_start")

    init_schema()
    tables = list_tables()
    logger.info("schema_tables", count=len(tables), tables=tables)

    n = load_stock_info()
    if n == 0:
        logger.error("init_db_failed_no_stocks")
        return 1

    logger.info("init_db_complete", stocks=n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
