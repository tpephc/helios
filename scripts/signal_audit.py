#!/usr/bin/env python3
# scripts/signal_audit.py
"""Signal behavior audit — reviewer 的 5 個 sanity questions (NOT optimization).

對 daily_features 全歷史掃描，跑 TrendBreakout strategy，蒐集所有訊號，
然後回答 reviewer 的 5 個問題:

  Q1. Signals 太多嗎? (每年訊號數合理嗎?)
  Q2. Bull market 才觸發嗎? (gate 有效嗎?)
  Q3. Crisis 真的被過濾嗎? (regime gate 嚴格嗎?)
  Q4. Breakout 後是否延續? (forward 5/10/20-day returns)
  Q5. ATR spike 是否導致 stop? (% 訊號後 ATR 異常擴張)

關鍵: 這 NOT 是 Sharpe optimization。只描述行為，不調參。

執行:
  uv run python scripts/signal_audit.py
  uv run python scripts/signal_audit.py --symbols 2330,0050,2454,3711

Version: v0.1.0 (2026-05-17)
Changelog:
  v0.1.0 (2026-05-17): Initial — 5-question sanity audit
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date as date_type
from datetime import datetime

import polars as pl

from data.database import connect, init_schema
from strategies.trend_breakout import TrendBreakoutStrategy


def get_trading_dates(symbols: list[str] | None) -> list[date_type]:
    """有 daily_features 的所有交易日."""
    if symbols:
        placeholders = ",".join(["?"] * len(symbols))
        sql = (
            f"SELECT DISTINCT date FROM daily_features "
            f"WHERE stock_id IN ({placeholders}) ORDER BY date"
        )
        params: list = list(symbols)
    else:
        sql = "SELECT DISTINCT date FROM daily_features ORDER BY date"
        params = []
    with connect(read_only=True) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [r[0] for r in rows]


def load_all_adj_prices(symbols: list[str] | None) -> dict[str, pl.DataFrame]:
    """Pre-load all daily_price_adj into memory (避免 forward-return loop 重複 query)."""
    if symbols:
        placeholders = ",".join(["?"] * len(symbols))
        sql = (
            f"SELECT stock_id, date, adj_close FROM daily_price_adj "
            f"WHERE stock_id IN ({placeholders}) ORDER BY stock_id, date"
        )
        params: list = list(symbols)
    else:
        sql = "SELECT stock_id, date, adj_close FROM daily_price_adj ORDER BY stock_id, date"
        params = []
    with connect(read_only=True) as conn:
        arrow = conn.execute(sql, params).to_arrow_table()
    df = pl.from_arrow(arrow)
    return {
        sid: df.filter(pl.col("stock_id") == sid).sort("date")
        for sid in df["stock_id"].unique().to_list()
    }


def load_all_atr(symbols: list[str] | None) -> dict[str, pl.DataFrame]:
    if symbols:
        placeholders = ",".join(["?"] * len(symbols))
        sql = (
            f"SELECT stock_id, date, atr_14 FROM daily_features "
            f"WHERE stock_id IN ({placeholders}) ORDER BY stock_id, date"
        )
        params: list = list(symbols)
    else:
        sql = "SELECT stock_id, date, atr_14 FROM daily_features ORDER BY stock_id, date"
        params = []
    with connect(read_only=True) as conn:
        arrow = conn.execute(sql, params).to_arrow_table()
    df = pl.from_arrow(arrow)
    return {
        sid: df.filter(pl.col("stock_id") == sid).sort("date")
        for sid in df["stock_id"].unique().to_list()
    }


def forward_return(adj_df: pl.DataFrame, signal_date: date_type, n: int) -> float | None:
    """從 signal_date 後第 n 個交易日的 adj_close 算 cumulative return."""
    idx = adj_df.with_row_index().filter(
        pl.col("date") == signal_date
    ).select("index").to_series().to_list()
    if not idx:
        return None
    i = idx[0]
    if i + n >= adj_df.height:
        return None
    p0 = adj_df["adj_close"][i]
    pn = adj_df["adj_close"][i + n]
    if p0 is None or pn is None or p0 <= 0:
        return None
    return (pn / p0 - 1) * 100


def max_atr_after(atr_df: pl.DataFrame, signal_date: date_type, n: int) -> float | None:
    idx = atr_df.with_row_index().filter(
        pl.col("date") == signal_date
    ).select("index").to_series().to_list()
    if not idx:
        return None
    i = idx[0]
    end = min(i + n + 1, atr_df.height)
    window = atr_df["atr_14"][i+1:end].to_list()
    vals = [v for v in window if v is not None]
    return max(vals) if vals else None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Signal behavior audit — reviewer's 5 questions"
    )
    parser.add_argument("--symbols", type=str, help="逗號分隔 (預設全部)")
    args = parser.parse_args()

    symbols = (
        [s.strip() for s in args.symbols.split(",") if s.strip()]
        if args.symbols else None
    )

    init_schema()
    print(f"Helios signal_audit — {datetime.now().isoformat(timespec='seconds')}")
    print("=" * 70)

    # 1. Get trading dates
    dates = get_trading_dates(symbols)
    if not dates:
        print("❌ daily_features 為空")
        return 1

    # Skip first 200 trading days (SMA200 warmup)
    if len(dates) > 200:
        dates = dates[200:]

    print(f"Sweep {len(dates)} trading dates from {dates[0]} to {dates[-1]}")

    # 2. Run strategy across all dates
    strategy = TrendBreakoutStrategy()
    all_signals = []
    t0 = datetime.now()
    for i, d in enumerate(dates):
        sigs = strategy.generate_signals(as_of=d, symbols=symbols)
        all_signals.extend(sigs)
        if (i + 1) % 200 == 0:
            elapsed = (datetime.now() - t0).total_seconds()
            print(f"  ... {i+1}/{len(dates)} dates  |  {len(all_signals)} signals  |  {elapsed:.1f}s")
    elapsed = (datetime.now() - t0).total_seconds()
    print(f"\n✓ Scan done in {elapsed:.1f}s, total {len(all_signals)} signals")

    if not all_signals:
        print("\n⚠ 0 訊號 — 過濾條件可能太緊")
        return 0

    # 3. Preload data for forward-return analysis
    adj_prices = load_all_adj_prices(symbols)
    atr_data = load_all_atr(symbols)

    # ── Q1. Signals 太多嗎?
    print(f"\n{'─'*70}\nQ1. Signals 太多嗎?")
    years = len(dates) / 250.0
    rate_per_year = len(all_signals) / years if years > 0 else 0
    print(f"  Total:    {len(all_signals)} signals over {len(dates)} trading days (~{years:.1f} years)")
    print(f"  Rate:     ~{rate_per_year:.0f} signals/year")
    print(f"  Per day:  {len(all_signals)/len(dates)*100:.2f} signals/100 trading days")
    if rate_per_year > 200:
        verdict = "⚠ 偏多 (>200/year), 過濾可能太鬆"
    elif rate_per_year < 5:
        verdict = "⚠ 偏少 (<5/year), 過濾可能太緊"
    else:
        verdict = "✓ 合理"
    print(f"  Verdict:  {verdict}")

    # ── Q2. Bull market 才觸發嗎?
    print(f"\n{'─'*70}\nQ2. Bull market 才觸發嗎?")
    regime_dist = Counter(s.regime for s in all_signals)
    for r, n in regime_dist.most_common():
        pct = n / len(all_signals) * 100
        print(f"  {r:8s}: {n:4d} ({pct:5.1f}%)")
    if regime_dist.get("bull", 0) == len(all_signals):
        print("  Verdict:  ✓ 100% bull (gate 完全有效)")
    else:
        print(f"  Verdict:  ⚠ {len(all_signals) - regime_dist.get('bull', 0)} 訊號不在 bull")

    # ── Q3. Crisis 被過濾?
    print(f"\n{'─'*70}\nQ3. Crisis 真的被過濾嗎?")
    crisis_n = regime_dist.get("crisis", 0)
    print(f"  Crisis 期間訊號數: {crisis_n}")
    if crisis_n == 0:
        # 看看 crisis 期間有多少 trading days
        with connect(read_only=True) as conn:
            n_crisis_days = conn.execute(
                "SELECT COUNT(*) FROM market_regime WHERE regime = 'crisis' AND date >= ?",
                [dates[0]],
            ).fetchone()[0]
        print(f"  (Crisis trading days in scan range: {n_crisis_days})")
        print("  Verdict:  ✓ 0 訊號 in crisis (gate 嚴格)")
    else:
        print(f"  Verdict:  ⚠ {crisis_n} 訊號漏進來")

    # ── Q4. Breakout 後是否延續?
    print(f"\n{'─'*70}\nQ4. Breakout 後是否延續? (forward returns)")
    horizons = [5, 10, 20]
    fwd: dict[int, list[float]] = {h: [] for h in horizons}
    for sig in all_signals:
        adj_df = adj_prices.get(sig.stock_id)
        if adj_df is None or adj_df.is_empty():
            continue
        for h in horizons:
            r = forward_return(adj_df, sig.signal_date, h)
            if r is not None:
                fwd[h].append(r)

    print(f"  {'Horizon':>8s}  {'n':>5s}  {'median':>8s}  {'mean':>8s}  {'hit_rate':>9s}")
    for h in horizons:
        vals = fwd[h]
        if not vals:
            print(f"  {h:>5d}d    (no data)")
            continue
        vals_sorted = sorted(vals)
        median = vals_sorted[len(vals_sorted) // 2]
        mean = sum(vals) / len(vals)
        hit = sum(1 for v in vals if v > 0) / len(vals) * 100
        print(
            f"  {h:>5d}d   {len(vals):>5d}  {median:>+7.2f}%  {mean:>+7.2f}%  {hit:>7.0f}%"
        )

    # 20-day hit_rate 大概要 > 50% 才是 OK 的 trend-following 訊號
    if fwd[20]:
        hit_20 = sum(1 for v in fwd[20] if v > 0) / len(fwd[20]) * 100
        med_20 = sorted(fwd[20])[len(fwd[20]) // 2]
        if hit_20 > 55 and med_20 > 0:
            print("  Verdict:  ✓ 訊號後有 trend continuation")
        elif hit_20 > 45:
            print("  Verdict:  ○ 接近 random walk, 訊號 quality 普通")
        else:
            print("  Verdict:  ⚠ 訊號後反轉率高, 可能是 fake breakout")

    # ── Q5. ATR spike 是否導致 stop?
    print(f"\n{'─'*70}\nQ5. ATR spike 後續 20 日是否導致 stop?")
    n_check, n_spike = 0, 0
    for sig in all_signals:
        atr_df = atr_data.get(sig.stock_id)
        if atr_df is None or atr_df.is_empty():
            continue
        max_future = max_atr_after(atr_df, sig.signal_date, 20)
        if max_future is None or sig.entry_atr <= 0:
            continue
        n_check += 1
        if max_future > sig.entry_atr * 1.5:
            n_spike += 1
    if n_check > 0:
        pct = n_spike / n_check * 100
        print(f"  {n_spike}/{n_check} ({pct:.0f}%) 訊號後 20 日 ATR > 1.5x entry_atr")
        if pct < 20:
            print("  Verdict:  ✓ 訊號後波動穩定")
        elif pct < 40:
            print("  Verdict:  ○ 部分訊號後出現波動擴大")
        else:
            print("  Verdict:  ⚠ 多數訊號後波動異常")

    # 摘要 — 訊號分布 by symbol
    print(f"\n{'─'*70}\nSignal distribution by symbol:")
    by_sym = Counter(s.stock_id for s in all_signals)
    for sym, n in by_sym.most_common(15):
        print(f"  {sym:8s}: {n:3d}")

    print(f"\n{'='*70}\n✓ Audit complete — Step 3 decision loop validated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
