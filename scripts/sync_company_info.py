#!/usr/bin/env python3
# scripts/sync_company_info.py
"""同步 TWSE 上市公司基本資訊到 company_metadata 表。

來源：TWSE openapi `/opendata/t187ap03_L` (~1000+ 家上市公司)
目的：給 universe management 提供權威的「上市日 + 產業分類 + 股本」資料

設計：
- 全量重寫（每次跑刪掉重灌，因為 t187ap03_L 一次回全市場）
- 不影響 stock_info (FinMind 來源，當 fallback 用)
- 每次跑 < 10 秒

使用：
  uv run python scripts/sync_company_info.py

Version: v0.1.0 (2026-05-16)
Changelog:
  v0.1.0 (2026-05-16): Initial — TWSE t187ap03_L → company_metadata
"""
from __future__ import annotations

import sys
from datetime import datetime

from data.database import connect, init_schema
from data.sources.twse_client import TwseClient
from utils.logger import get_logger

logger = get_logger(__name__)


def main() -> int:
    init_schema()

    print(f"Helios sync_company_info — {datetime.now().isoformat(timespec='seconds')}")
    print("Source: TWSE openapi /opendata/t187ap03_L")
    print()

    with TwseClient(sleep_between_calls=1.0) as twse:
        df = twse.company_info()

    if df.is_empty():
        print("❌ TWSE 沒回任何 company info — 端點可能異常")
        logger.error("twse_company_info_empty")
        return 1

    n = df.height
    print(f"Fetched {n} companies from TWSE")

    # 統計產業分布 (給人讀)
    industry_counts = (
        df.group_by("industry_code")
        .len()
        .sort("len", descending=True)
        .head(8)
    )
    print("Top 8 industries:")
    for r in industry_counts.iter_rows(named=True):
        print(f"  industry_code={r['industry_code']:>4s}  n={r['len']}")

    # 寫入 (DuckDB 沒 upsert，全量重寫)
    now = datetime.now()
    df = df.with_columns(last_synced_at=now)

    with connect() as conn:
        conn.execute("DELETE FROM company_metadata")
        conn.register("inp", df.to_arrow())
        try:
            conn.execute("""
                INSERT INTO company_metadata
                (stock_id, company_name, short_name, industry_code, listing_date,
                 paid_in_capital, issued_shares, last_synced_at)
                SELECT stock_id, company_name, short_name, industry_code, listing_date,
                       paid_in_capital, issued_shares, last_synced_at
                FROM inp
            """)
        finally:
            conn.unregister("inp")

        # 確認寫入
        row = conn.execute("SELECT COUNT(*) FROM company_metadata").fetchone()
        confirmed_n = row[0] if row else 0

    print(f"\n✓ company_metadata: {confirmed_n} rows written")

    # 範例查詢
    with connect(read_only=True) as conn:
        sample = conn.execute("""
            SELECT stock_id, short_name, industry_code, listing_date,
                   paid_in_capital, issued_shares
            FROM company_metadata
            WHERE stock_id IN ('2330', '2317', '0050', '2882')
            ORDER BY stock_id
        """).fetchall()
        if sample:
            print("\nSample (核心權值股):")
            for r in sample:
                cap_billion = f"{r[4]/1e9:.1f}B" if r[4] else "—"
                shares_billion = f"{r[5]/1e9:.2f}B" if r[5] else "—"
                print(f"  {r[0]:7s} {r[1]:8s} ind={r[2]:>4s}  listed={r[3]}  cap={cap_billion}  shares={shares_billion}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
