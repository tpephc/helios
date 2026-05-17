#!/usr/bin/env python3
# scripts/oos_validation.py
"""Out-of-sample validation — split 2021-2023 (IS) vs 2024-2026 (OOS).

Reviewer 觀察 (v0.1.12 audit 後):
  - 2023-2025 是 AI mega trend, breakout strategy 天然吃這波
  - 最大風險不是「沒 exit」, 而是「太早相信 alpha」
  - 需要 OOS sanity check: strategy 在 in-sample 設計, 在 OOS 是否還有 edge?

決定 (簡單 split, 非 ML train/test):
  - In-sample (IS):  2021-2023 (~3 years)
  - Out-sample (OS): 2024-2026 (~2.4 years)

**不調 strategy parameters**. Strategy 條件保持 v0.1.12 完全不變.

Verdict thresholds (reviewer 提的 §32 標準):
  ✓ IS hit_20 > 55% AND OOS hit_20 > 55%       → 真實 alpha
  ○ IS > 55% AND OOS 50-55%                    → 邊緣, 需更多時間
  ⚠ IS > 60% AND OOS < 50%                     → over-fit / 吃 AI bull noise
  ⚠ Crisis 在 OOS 漏進 signals                  → gate 沒撐住

執行:
  uv run python scripts/oos_validation.py

Version: v0.1.0 (2026-05-17)
Changelog:
  v0.1.0 (2026-05-17): Initial — IS/OOS split + side-by-side comparison
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

# OOS 切分點 (reviewer §31 建議)
IS_END_DATE = date_type(2023, 12, 31)


# ─────────────────────────────────────────────────────────────
# Data loading (reuse pattern from signal_audit.py)
# ─────────────────────────────────────────────────────────────


def get_trading_dates() -> list[date_type]:
    with connect(read_only=True) as conn:
        rows = conn.execute(
            "SELECT DISTINCT date FROM daily_features ORDER BY date"
        ).fetchall()
    return [r[0] for r in rows]


def load_all_adj_prices() -> dict[str, pl.DataFrame]:
    with connect(read_only=True) as conn:
        arrow = conn.execute(
            "SELECT stock_id, date, adj_close FROM daily_price_adj ORDER BY stock_id, date"
        ).to_arrow_table()
    df = pl.from_arrow(arrow)
    return {
        sid: df.filter(pl.col("stock_id") == sid).sort("date")
        for sid in df["stock_id"].unique().to_list()
    }


def forward_return(adj_df: pl.DataFrame, signal_date: date_type, n: int) -> float | None:
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


# ─────────────────────────────────────────────────────────────
# Metrics computation per partition
# ─────────────────────────────────────────────────────────────


def compute_partition_metrics(
    signals: list,
    adj_prices: dict[str, pl.DataFrame],
    n_trading_days: int,
) -> dict:
    """Compute audit metrics for one partition (IS or OOS)."""
    horizons = [5, 10, 20]
    fwd_returns: dict[int, list[float]] = {h: [] for h in horizons}
    for sig in signals:
        adj_df = adj_prices.get(sig.stock_id)
        if adj_df is None:
            continue
        for h in horizons:
            r = forward_return(adj_df, sig.signal_date, h)
            if r is not None:
                fwd_returns[h].append(r)

    metrics: dict = {
        "n_signals": len(signals),
        "n_trading_days": n_trading_days,
        "years": n_trading_days / 250.0,
        "rate_per_year": len(signals) / (n_trading_days / 250.0) if n_trading_days > 0 else 0,
        "regime_dist": dict(Counter(s.regime for s in signals)),
        "symbol_dist": dict(Counter(s.stock_id for s in signals)),
        "horizons": {},
    }

    for h in horizons:
        vals = fwd_returns[h]
        if not vals:
            metrics["horizons"][h] = None
            continue
        vals_sorted = sorted(vals)
        metrics["horizons"][h] = {
            "n": len(vals),
            "median": vals_sorted[len(vals_sorted) // 2],
            "mean": sum(vals) / len(vals),
            "hit_rate": sum(1 for v in vals if v > 0) / len(vals) * 100,
            "best": max(vals),
            "worst": min(vals),
        }
    return metrics


def fmt_metric(m: dict | None, key: str, suffix: str = "", dec: int = 2) -> str:
    if m is None or m.get(key) is None:
        return "—"
    v = m[key]
    return f"{v:+.{dec}f}{suffix}" if "mean" in key or "median" in key or "best" in key or "worst" in key else f"{v:.{dec}f}{suffix}"


def print_side_by_side(is_metrics: dict, oos_metrics: dict) -> None:
    print("\n" + "=" * 90)
    print(f"  {'Metric':<35s} {'In-Sample (2021-2023)':>25s} {'Out-Sample (2024-2026)':>25s}")
    print("=" * 90)

    print(f"  {'Period years':<35s} "
          f"{is_metrics['years']:>22.1f} y  {oos_metrics['years']:>22.1f} y")
    print(f"  {'Trading days':<35s} "
          f"{is_metrics['n_trading_days']:>24d}  {oos_metrics['n_trading_days']:>24d}")
    print(f"  {'Total signals':<35s} "
          f"{is_metrics['n_signals']:>24d}  {oos_metrics['n_signals']:>24d}")
    print(f"  {'Signals per year':<35s} "
          f"{is_metrics['rate_per_year']:>23.0f}/y  {oos_metrics['rate_per_year']:>23.0f}/y")

    print("-" * 90)
    # Regime distribution
    is_bull = is_metrics["regime_dist"].get("bull", 0)
    oos_bull = oos_metrics["regime_dist"].get("bull", 0)
    is_bull_pct = is_bull / max(is_metrics["n_signals"], 1) * 100
    oos_bull_pct = oos_bull / max(oos_metrics["n_signals"], 1) * 100
    print(f"  {'Bull regime %':<35s} "
          f"{is_bull_pct:>23.1f}%  {oos_bull_pct:>23.1f}%")
    is_crisis = is_metrics["regime_dist"].get("crisis", 0)
    oos_crisis = oos_metrics["regime_dist"].get("crisis", 0)
    print(f"  {'Crisis signals (must be 0)':<35s} "
          f"{is_crisis:>24d}  {oos_crisis:>24d}")

    print("-" * 90)
    # Forward returns
    for h in [5, 10, 20]:
        is_h = is_metrics["horizons"].get(h)
        oos_h = oos_metrics["horizons"].get(h)
        if is_h is None or oos_h is None:
            continue
        print(f"  {f'{h}-day  hit_rate':<35s} "
              f"{is_h['hit_rate']:>23.1f}%  {oos_h['hit_rate']:>23.1f}%")
        print(f"  {f'{h}-day  median return':<35s} "
              f"{is_h['median']:>+22.2f}%  {oos_h['median']:>+22.2f}%")
        print(f"  {f'{h}-day  mean return':<35s} "
              f"{is_h['mean']:>+22.2f}%  {oos_h['mean']:>+22.2f}%")
        print(f"  {f'{h}-day  best / worst':<35s} "
              f"{is_h['best']:>+11.1f}% / {is_h['worst']:>+8.1f}% "
              f" {oos_h['best']:>+10.1f}% / {oos_h['worst']:>+7.1f}%")
        print("-" * 90)


def verdict(is_metrics: dict, oos_metrics: dict) -> tuple[str, list[str]]:
    """Reviewer's §32 + §33 verdict logic."""
    notes: list[str] = []

    is_h20 = is_metrics["horizons"].get(20)
    oos_h20 = oos_metrics["horizons"].get(20)
    if is_h20 is None or oos_h20 is None:
        return "⚠ INSUFFICIENT DATA", ["20-day forward returns 不夠"]

    is_hit = is_h20["hit_rate"]
    oos_hit = oos_h20["hit_rate"]
    is_mean = is_h20["mean"]
    oos_mean = oos_h20["mean"]

    # Crisis gate
    oos_crisis = oos_metrics["regime_dist"].get("crisis", 0)
    if oos_crisis > 0:
        notes.append(f"⚠ OOS 有 {oos_crisis} 訊號在 crisis (gate 在 OOS 沒撐住)")

    # Signal frequency
    is_rate = is_metrics["rate_per_year"]
    oos_rate = oos_metrics["rate_per_year"]
    if is_rate > 0 and oos_rate > 0:
        ratio = oos_rate / is_rate
        if ratio > 2.0 or ratio < 0.5:
            notes.append(
                f"⚠ Signal frequency 跨期變化大 (IS {is_rate:.0f}/y → OOS {oos_rate:.0f}/y, "
                f"ratio {ratio:.2f})"
            )

    # Hit rate stability (the main test)
    if is_hit > 55 and oos_hit > 55:
        notes.append(f"✓ Hit rate 跨期穩定 (IS {is_hit:.0f}% / OOS {oos_hit:.0f}%)")
        result = "✓ REAL ALPHA"
    elif is_hit > 55 and 50 <= oos_hit <= 55:
        notes.append(f"○ OOS hit rate 邊緣 (IS {is_hit:.0f}% → OOS {oos_hit:.0f}%)")
        result = "○ MARGINAL — 需要更多 OOS 時間"
    elif is_hit > 60 and oos_hit < 50:
        notes.append(f"⚠ OOS hit rate 崩潰 (IS {is_hit:.0f}% → OOS {oos_hit:.0f}%)")
        notes.append("⚠ 可能 over-fit AI bull 期間, alpha 不真實")
        result = "⚠ OVERFIT WARNING"
    else:
        notes.append(f"○ Hit rate: IS {is_hit:.0f}% / OOS {oos_hit:.0f}%")
        result = "○ UNCLEAR"

    # Mean return sign
    if is_mean > 0 and oos_mean > 0:
        notes.append(f"✓ Mean return 跨期都正 (IS +{is_mean:.2f}% / OOS +{oos_mean:.2f}%)")
    elif is_mean > 0 and oos_mean <= 0:
        notes.append(f"⚠ OOS mean return 翻負 (IS +{is_mean:.2f}% → OOS {oos_mean:+.2f}%)")

    return result, notes


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Out-of-sample validation for v0.1.12 trend_breakout strategy"
    )
    parser.add_argument(
        "--is-end", type=str, default=IS_END_DATE.isoformat(),
        help=f"In-sample 結束日 (預設 {IS_END_DATE})",
    )
    args = parser.parse_args()
    is_end = date_type.fromisoformat(args.is_end)

    init_schema()
    print(f"Helios oos_validation — {datetime.now().isoformat(timespec='seconds')}")
    print("Strategy: trend_breakout_v1 (unchanged from v0.1.12)")
    print(f"Split: IS ≤ {is_end} < OOS")

    dates = get_trading_dates()
    if len(dates) < 250:
        print(f"❌ Only {len(dates)} trading days; need more history")
        return 1

    # SMA200 warmup: skip first 200 days
    dates = dates[200:]

    is_dates = [d for d in dates if d <= is_end]
    oos_dates = [d for d in dates if d > is_end]
    print(f"  IS:  {is_dates[0]} ~ {is_dates[-1]} ({len(is_dates)} days)")
    print(f"  OOS: {oos_dates[0]} ~ {oos_dates[-1]} ({len(oos_dates)} days)")

    strategy = TrendBreakoutStrategy()

    # Run on IS
    print("\nRunning strategy on IN-SAMPLE...")
    t0 = datetime.now()
    is_signals = []
    for d in is_dates:
        is_signals.extend(strategy.generate_signals(as_of=d))
    print(f"  → {len(is_signals)} signals  ({(datetime.now()-t0).total_seconds():.1f}s)")

    # Run on OOS
    print("\nRunning strategy on OUT-OF-SAMPLE...")
    t0 = datetime.now()
    oos_signals = []
    for d in oos_dates:
        oos_signals.extend(strategy.generate_signals(as_of=d))
    print(f"  → {len(oos_signals)} signals  ({(datetime.now()-t0).total_seconds():.1f}s)")

    # Load price data once
    print("\nLoading price history for forward-return calc...")
    adj_prices = load_all_adj_prices()

    # Compute metrics
    is_metrics = compute_partition_metrics(is_signals, adj_prices, len(is_dates))
    oos_metrics = compute_partition_metrics(oos_signals, adj_prices, len(oos_dates))

    # Side-by-side
    print_side_by_side(is_metrics, oos_metrics)

    # Verdict
    result, notes = verdict(is_metrics, oos_metrics)
    print(f"\n{'='*90}")
    print(f"VERDICT: {result}")
    print(f"{'='*90}")
    for note in notes:
        print(f"  {note}")

    # Symbol distribution comparison (top 5 of each)
    print(f"\n{'─'*90}")
    print("Top symbols by signal count (IS | OOS):")
    is_top = Counter(is_metrics["symbol_dist"]).most_common(5)
    oos_top = Counter(oos_metrics["symbol_dist"]).most_common(5)
    print(f"  {'IS':<30s} | {'OOS':<30s}")
    max_len = max(len(is_top), len(oos_top))
    for i in range(max_len):
        is_row = f"{is_top[i][0]}: {is_top[i][1]}" if i < len(is_top) else ""
        oos_row = f"{oos_top[i][0]}: {oos_top[i][1]}" if i < len(oos_top) else ""
        print(f"  {is_row:<30s} | {oos_row:<30s}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
