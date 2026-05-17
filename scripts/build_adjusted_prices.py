#!/usr/bin/env python3
# scripts/build_adjusted_prices.py
"""(Re)build daily_price_adj from raw + corporate_actions.

預設使用 freshness check (跳過已經是最新的 symbol)。
`--force` 強制全部重建。

使用：
  uv run python scripts/build_adjusted_prices.py                # 增量
  uv run python scripts/build_adjusted_prices.py --force         # 全量重建
  uv run python scripts/build_adjusted_prices.py --symbols 2330,0050

Version: v0.1.0 (2026-05-16)
Changelog:
  v0.1.0 (2026-05-16): Initial
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime

from data.database import connect, init_schema
from features.dividend_adjustment import (
    build_for_symbol,
    get_freshness_status,
    write_adjusted_to_db,
)
from utils.logger import get_logger

logger = get_logger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build/rebuild daily_price_adj from daily_price + corporate_actions"
    )
    parser.add_argument(
        "--symbols", type=str,
        help="逗號分隔 (限定 symbol)；不給就跑全部 in daily_price",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="忽略 freshness check，全部重建",
    )
    args = parser.parse_args()

    init_schema()
    print(f"Helios build_adjusted_prices — {datetime.now().isoformat(timespec='seconds')}")

    # 決定目標 symbols
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        with connect(read_only=True) as conn:
            rows = conn.execute(
                "SELECT DISTINCT stock_id FROM daily_price "
                "WHERE stock_id != 'TAIEX' ORDER BY stock_id"
            ).fetchall()
        symbols = [r[0] for r in rows]

    if not symbols:
        print("❌ daily_price 內沒任何 symbol，請先跑 download_daily.py")
        return 1

    # Freshness check
    if not args.force:
        status_list = get_freshness_status()
        status_map = {s["stock_id"]: s for s in status_list}
        to_build: list[tuple[str, list[str]]] = []
        fresh: list[str] = []
        for sid in symbols:
            s = status_map.get(sid)
            if s is None or s["stale"]:
                reasons = s["reasons"] if s else ["unknown"]
                to_build.append((sid, reasons))
            else:
                fresh.append(sid)

        if fresh:
            print(f"\n{len(fresh)} symbol(s) already fresh: {', '.join(fresh)}")
        if not to_build:
            print("\n✓ Everything fresh, nothing to rebuild")
            return 0
        print(f"\nBuilding {len(to_build)} symbol(s):")
        for sid, reasons in to_build:
            print(f"  • {sid}: {', '.join(reasons)}")
        symbols_to_build = [t[0] for t in to_build]
    else:
        symbols_to_build = symbols
        print(f"\nForce-rebuilding {len(symbols_to_build)} symbol(s)")
    print()

    n_ok, n_err = 0, 0
    for i, sid in enumerate(symbols_to_build, 1):
        try:
            result = build_for_symbol(sid)
            write_adjusted_to_db(sid, result)
            last_event = result.last_event_date_used or "—"
            print(
                f"  [{i:2d}/{len(symbols_to_build)}] ✓ {sid:8s}  "
                f"rows={result.adjusted.height:4d}  "
                f"events={result.n_events_applied:2d}  "
                f"last_event={last_event}"
            )
            n_ok += 1
        except Exception as e:
            logger.exception("build_adjustment_failed", stock_id=sid)
            print(f"  [{i:2d}/{len(symbols_to_build)}] ✗ {sid:8s}  ERROR: {e}")
            n_err += 1

    print(f"\n{'='*60}\nSummary\n{'='*60}")
    print(f"  Success: {n_ok}")
    if n_err:
        print(f"  Failed:  {n_err}")

    # 全表狀態摘要
    with connect(read_only=True) as conn:
        n_total = conn.execute("SELECT COUNT(*) FROM daily_price_adj").fetchone()[0]
        n_symbols = conn.execute(
            "SELECT COUNT(DISTINCT stock_id) FROM daily_price_adj"
        ).fetchone()[0]
    print(f"  daily_price_adj: {n_total} rows across {n_symbols} symbols")
    print()
    print("💡 跑 scripts/validate_adjustments.py 驗證 abnormal returns 被吸收")
    return 0 if n_err == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
