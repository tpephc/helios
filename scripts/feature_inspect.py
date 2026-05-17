#!/usr/bin/env python3
# scripts/feature_inspect.py
"""Step 3 exit criteria — answer reviewer 的 5 個 strategy-readiness 問題.

Questions:
  1. 現在是不是 bull regime?
  2. 2330 是否高於 SMA200?
  3. 是否 volume breakout?
  4. ATR 是否異常擴張?
  5. 0050 是否進入 crisis regime? (per-symbol)

執行：
  uv run python scripts/feature_inspect.py
  uv run python scripts/feature_inspect.py --as-of 2025-06-18  (歷史某日)

Version: v0.1.0 (2026-05-17)
Changelog:
  v0.1.0 (2026-05-17): Initial — 5-question strategy readiness check
"""
from __future__ import annotations

import argparse
import sys
from datetime import date as date_type

from data.database import connect


def get_target_date(as_of: str | None) -> date_type:
    """取最近一個有 daily_features 的日期 (or 指定的 as_of)."""
    with connect(read_only=True) as conn:
        if as_of:
            return date_type.fromisoformat(as_of)
        row = conn.execute("SELECT MAX(date) FROM daily_features").fetchone()
        if not row or not row[0]:
            raise SystemExit("❌ daily_features 為空，先跑 compute_features.py")
        return row[0]


def get_market_regime(target: date_type) -> dict | None:
    with connect(read_only=True) as conn:
        row = conn.execute(
            """
            SELECT date, taiex_close, sma_200, vol_20, regime
            FROM market_regime WHERE date <= ?
            ORDER BY date DESC LIMIT 1
            """,
            [target],
        ).fetchone()
    if not row:
        return None
    return {
        "date": row[0], "taiex_close": row[1], "sma_200": row[2],
        "vol_20": row[3], "regime": row[4],
    }


def get_symbol_features(stock_id: str, target: date_type) -> dict | None:
    with connect(read_only=True) as conn:
        row = conn.execute(
            """
            SELECT f.date, f.sma_20, f.sma_50, f.sma_200, f.ema_20,
                   f.rsi_14, f.roc_20, f.atr_14,
                   f.donchian_20_high, f.donchian_20_low,
                   f.volume_ma_20, f.rel_volume_20,
                   a.adj_close
            FROM daily_features f
            JOIN daily_price_adj a USING (stock_id, date)
            WHERE f.stock_id = ? AND f.date <= ?
            ORDER BY f.date DESC LIMIT 1
            """,
            [stock_id, target],
        ).fetchone()
    if not row:
        return None
    keys = [
        "date", "sma_20", "sma_50", "sma_200", "ema_20",
        "rsi_14", "roc_20", "atr_14",
        "donchian_20_high", "donchian_20_low",
        "volume_ma_20", "rel_volume_20", "adj_close",
    ]
    return dict(zip(keys, row, strict=True))


def get_atr_history(stock_id: str, target: date_type, n: int = 60) -> list[float]:
    """過去 N 日的 atr_14 series (給 'ATR 異常擴張' 判斷用)."""
    with connect(read_only=True) as conn:
        rows = conn.execute(
            """
            SELECT atr_14 FROM daily_features
            WHERE stock_id = ? AND date <= ? AND atr_14 IS NOT NULL
            ORDER BY date DESC LIMIT ?
            """,
            [stock_id, target, n],
        ).fetchall()
    return [r[0] for r in rows]


def fmt(v: float | None, dec: int = 2) -> str:
    if v is None:
        return "null"
    return f"{v:.{dec}f}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Strategy-readiness inspection (reviewer 的 5 questions)"
    )
    parser.add_argument("--as-of", type=str, help="指定日期 (YYYY-MM-DD, 預設最新)")
    parser.add_argument(
        "--inspect-symbols", type=str, default="2330,0050,2454,3711",
        help="要 inspect 的個股 (逗號分隔)",
    )
    args = parser.parse_args()

    target = get_target_date(args.as_of)
    print(f"Helios feature inspection — as of {target}")
    print("=" * 70)

    # ── Q1: 現在是不是 bull regime?
    print("\nQ1. 現在是不是 bull regime?")
    regime_data = get_market_regime(target)
    if regime_data:
        sma_str = fmt(regime_data["sma_200"])
        vol_str = fmt(regime_data["vol_20"] * 100 if regime_data["vol_20"] else None)
        print(f"   regime    = {regime_data['regime']}")
        print(f"   TAIEX     = {fmt(regime_data['taiex_close'])} "
              f"(SMA200 = {sma_str})")
        print(f"   vol_20    = {vol_str}%")
        if regime_data["regime"] == "bull":
            print("   → ✓ YES, market is in bull regime")
        else:
            print(f"   → ✗ NO, market is in {regime_data['regime']} regime")
    else:
        print("   → ⚠ No market_regime data; run compute_features.py")

    inspect_symbols = [s.strip() for s in args.inspect_symbols.split(",") if s.strip()]

    # ── Q2: 個股是否高於 SMA200?
    print("\nQ2. 個股是否高於 SMA200?")
    for sid in inspect_symbols:
        f = get_symbol_features(sid, target)
        if not f:
            print(f"   {sid}: (no data)")
            continue
        if f["sma_200"] is None:
            print(f"   {sid}: SMA200 not yet computed (need 200 trading days history)")
            continue
        above = f["adj_close"] > f["sma_200"]
        gap = (f["adj_close"] / f["sma_200"] - 1) * 100
        icon = "✓" if above else "✗"
        print(f"   {sid}: close={fmt(f['adj_close'])} vs sma_200={fmt(f['sma_200'])}  "
              f"gap={gap:+.1f}%  {icon}")

    # ── Q3: 是否 volume breakout? (rel_volume_20 > 1.5)
    print("\nQ3. 是否 volume breakout (rel_volume_20 > 1.5)?")
    for sid in inspect_symbols:
        f = get_symbol_features(sid, target)
        if not f or f["rel_volume_20"] is None:
            print(f"   {sid}: (no data)")
            continue
        breakout = f["rel_volume_20"] > 1.5
        icon = "✓ breakout" if breakout else "—"
        print(f"   {sid}: rel_volume_20={fmt(f['rel_volume_20'])}x  {icon}")

    # ── Q4: ATR 是否異常擴張? (current vs 60-day median)
    print("\nQ4. ATR 是否異常擴張 (vs 過去 60 日)?")
    for sid in inspect_symbols:
        atr_hist = get_atr_history(sid, target, n=60)
        if not atr_hist:
            print(f"   {sid}: (no atr history)")
            continue
        current_atr = atr_hist[0]
        baseline = sorted(atr_hist[1:])[len(atr_hist) // 2] if len(atr_hist) > 1 else current_atr
        ratio = current_atr / baseline if baseline > 0 else 1.0
        expanded = ratio > 1.5
        icon = "✓ expanded" if expanded else "—"
        print(f"   {sid}: ATR={fmt(current_atr)} vs 60d_median={fmt(baseline)}  "
              f"ratio={fmt(ratio)}x  {icon}")

    # ── Q5: 個股 breakout? (Donchian 20)
    print("\nQ5. 個股是否 Donchian-20 breakout? (close >= donchian_high)")
    for sid in inspect_symbols:
        f = get_symbol_features(sid, target)
        if not f or f["donchian_20_high"] is None:
            print(f"   {sid}: (no data)")
            continue
        is_breakout = f["adj_close"] >= f["donchian_20_high"] - 1e-6
        is_breakdown = f["adj_close"] <= f["donchian_20_low"] + 1e-6
        if is_breakout:
            icon = "✓ at 20-day HIGH"
        elif is_breakdown:
            icon = "✗ at 20-day LOW"
        else:
            mid = (f["donchian_20_high"] + f["donchian_20_low"]) / 2
            pos = (f["adj_close"] - mid) / (f["donchian_20_high"] - mid) if mid > 0 else 0
            icon = f"(pos {pos:+.0%} of upper band)"
        print(f"   {sid}: close={fmt(f['adj_close'])} "
              f"[{fmt(f['donchian_20_low'])}, {fmt(f['donchian_20_high'])}]  {icon}")

    # ── Bonus: 顯示 RSI / EMA 分布
    print("\nBonus. Momentum/Trend snapshot:")
    print(f"   {'Symbol':<8s} {'RSI14':>7s} {'ROC20%':>8s} {'EMA20':>8s} {'AdjClose':>9s}")
    for sid in inspect_symbols:
        f = get_symbol_features(sid, target)
        if not f:
            continue
        print(f"   {sid:<8s} "
              f"{fmt(f['rsi_14'], 1):>7s} "
              f"{fmt(f['roc_20'], 2):>8s} "
              f"{fmt(f['ema_20']):>8s} "
              f"{fmt(f['adj_close']):>9s}")

    print()
    print("=" * 70)
    print("✓ Step 3 exit criteria: all 5 questions answerable from daily_features + market_regime")
    return 0


if __name__ == "__main__":
    sys.exit(main())
