#!/usr/bin/env python3
# scripts/validate_adjustments.py
"""驗證 daily_price_adj 確實吸收了已知 dividend/split events.

v0.1.10.1 改進 (採納外部 reviewer 建議):
- Per-type threshold (stock 0.105 vs ETF 0.20)
- 不只看 count，還顯示 max |pct| residual

對照 docs/data_behavior_notes.md §9 的 golden cases:
  0050 2025-06-18 split / 2454 2022-06-23 / 2454 2023-06-20 / 3711 2022-06-29

使用：
  uv run python scripts/validate_adjustments.py
  uv run python scripts/validate_adjustments.py --symbols 2454,3711

Version: v0.1.1 (2026-05-16)
Changelog:
  v0.1.1 (2026-05-16): per-type threshold (ETF 0.20 / stock 0.105);
                       max residual abs(pct) display (reviewer 建議 #4 #5)
  v0.1.0 (2026-05-16): Initial
"""
from __future__ import annotations

import argparse
import sys

import polars as pl

from data.database import connect

# v0.1.10.1: per-type threshold
THRESHOLD_STOCK = 0.105  # 台股 ±10% 漲跌停 + 0.5% buffer
THRESHOLD_ETF = 0.20     # ETF 無漲跌停限制


def is_etf(stock_id: str) -> bool:
    """ETF 簡易判斷：4-6 碼以 0 開頭 (Helios v0.1 universe 100% 適用)。"""
    return stock_id.startswith("0")


def threshold_for(stock_id: str) -> float:
    return THRESHOLD_ETF if is_etf(stock_id) else THRESHOLD_STOCK


def get_returns_with_threshold(
    table: str, stock_id: str
) -> tuple[pl.DataFrame, float | None]:
    """Compute daily pct change. Return (abnormal_rows, max_abs_pct)."""
    close_col = "close" if table == "daily_price" else "adj_close"
    threshold = threshold_for(stock_id)
    with connect(read_only=True) as conn:
        arrow = conn.execute(
            f"SELECT date, {close_col} AS close FROM {table} "
            f"WHERE stock_id = ? ORDER BY date",
            [stock_id],
        ).to_arrow_table()
    df = pl.from_arrow(arrow)
    if df.is_empty():
        return pl.DataFrame(), None
    df = df.filter(pl.col("close") > 0).with_columns(
        pct=(pl.col("close") / pl.col("close").shift(1) - 1)
    ).filter(pl.col("pct").is_not_null())
    if df.is_empty():
        return pl.DataFrame(), None
    max_abs = df.select(pl.col("pct").abs().max()).item()
    abnormal = df.filter(
        pl.col("pct").abs() > threshold
    ).select(["date", "close", "pct"])
    return abnormal, max_abs


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate daily_price_adj absorbs known dividend/split events"
    )
    parser.add_argument(
        "--symbols", type=str,
        help="逗號分隔 (預設掃 daily_price_adj 全部)",
    )
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        with connect(read_only=True) as conn:
            rows = conn.execute(
                "SELECT DISTINCT stock_id FROM daily_price_adj ORDER BY stock_id"
            ).fetchall()
        symbols = [r[0] for r in rows]

    if not symbols:
        print("❌ daily_price_adj 為空，請先跑 scripts/build_adjusted_prices.py")
        return 1

    print(
        f"Validating {len(symbols)} symbols "
        f"(threshold stock={THRESHOLD_STOCK*100:.1f}%, ETF={THRESHOLD_ETF*100:.0f}%)"
    )
    print()
    print(
        f"  {'Symbol':<8s} {'Type':<5s} {'Raw#':>4s} {'Adj#':>4s} {'Δ':>4s}  "
        f"{'RawMax%':>8s} {'AdjMax%':>8s}  {'Status'}"
    )
    print(
        f"  {'-'*8} {'-'*5} {'-'*4} {'-'*4} {'-'*4}  "
        f"{'-'*8} {'-'*8}  {'-'*20}"
    )

    overall_raw = 0
    overall_adj = 0
    remaining_details: list[dict] = []
    overall_max_adj = 0.0

    for sid in symbols:
        raw_abn, raw_max = get_returns_with_threshold("daily_price", sid)
        adj_abn, adj_max = get_returns_with_threshold("daily_price_adj", sid)
        n_raw = raw_abn.height
        n_adj = adj_abn.height
        overall_raw += n_raw
        overall_adj += n_adj
        if adj_max is not None and adj_max > overall_max_adj:
            overall_max_adj = adj_max
        delta = n_adj - n_raw
        sym_type = "ETF" if is_etf(sid) else "stk"

        if n_raw == 0 and n_adj == 0:
            status = "—"
        elif n_adj == 0 and n_raw > 0:
            status = "✓ all absorbed"
        elif n_adj < n_raw:
            status = "✓ improved"
        elif n_adj == n_raw and n_raw > 0:
            status = "⚠ no change"
        else:
            status = "⚠ worse"

        raw_max_str = f"{raw_max*100:+.2f}" if raw_max is not None else "—"
        adj_max_str = f"{adj_max*100:+.2f}" if adj_max is not None else "—"
        print(
            f"  {sid:<8s} {sym_type:<5s} {n_raw:>4d} {n_adj:>4d} {delta:+4d}  "
            f"{raw_max_str:>8s} {adj_max_str:>8s}  {status}"
        )

        if n_adj > 0:
            for row in adj_abn.iter_rows(named=True):
                remaining_details.append({
                    "stock_id": sid,
                    "date": str(row["date"]),
                    "adj_close": row["close"],
                    "pct": row["pct"],
                })

    print()
    print(f"{'='*70}\nOverall\n{'='*70}")
    print(f"  Raw abnormal returns:      {overall_raw}")
    print(f"  Adjusted abnormal returns: {overall_adj}")
    print(f"  Absorbed by adjustment:    {overall_raw - overall_adj}")
    if overall_raw > 0:
        absorption_rate = (overall_raw - overall_adj) / overall_raw * 100
        print(f"  Absorption rate:           {absorption_rate:.1f}%")
    print(f"  Max |pct| across all adj:  {overall_max_adj*100:.2f}%")

    if remaining_details:
        print(
            f"\nRemaining abnormal in adjusted "
            f"(前 {min(10, len(remaining_details))} 筆):"
        )
        for r in remaining_details[:10]:
            print(
                f"  {r['stock_id']:8s} {r['date']}  "
                f"pct={r['pct']*100:+7.2f}%  adj_close={r['adj_close']:.2f}"
            )
        print()
        print("💡 殘留 abnormal 可能是：")
        print("   (1) 真實市場極端事件 (非除權息) — OK")
        print("   (2) Split event 沒進 corporate_actions — 跑 ingest_splits.py")
        print("   (3) FinMind before/after 跟實際 raw close 對不齊 — 看 §12 筆記")

    # Sanity check: 對 0050 的 split 日做專門驗證
    print()
    print(f"{'='*70}\nGolden case: 0050 split (2025-06-18)\n{'='*70}")
    with connect(read_only=True) as conn:
        row = conn.execute("""
            SELECT date, raw_close, adj_close, cum_factor
            FROM daily_price_adj
            WHERE stock_id = '0050' AND date BETWEEN '2025-06-10' AND '2025-06-25'
            ORDER BY date
        """).fetchall()
    if row:
        print(f"  {'Date':<12s} {'Raw':>8s} {'Adj':>8s} {'Factor':>8s}")
        for r in row:
            print(f"  {r[0]!s:<12s} {r[1]:>8.2f} {r[2]:>8.2f} {r[3]:>8.5f}")
        print()
        print("  期待跑完 ingest_splits.py 後:")
        print("    factor 在 2025-06-18 之前 應該 ≈ 0.25 × (dividend factors)")
        print("    cross-day pct(2025-06-17→2025-06-18) ≈ 0%")
    else:
        print("  (0050 沒在 daily_price_adj 裡 — 跑 build_adjusted_prices.py)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
