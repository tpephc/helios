#!/usr/bin/env python3
# research/mae_atr_study.py
"""Maximum Adverse Excursion (MAE) study for ATR stop multiplier calibration.

研究問題：
  trend_breakout_v1 進場後，最大回撤是 ATR 的幾倍？
  → 用來校準 intraday_monitor 的停損倍數（目前 [ASSUMED] 2×ATR）

方法：
  1. 對所有歷史日期重跑 TrendBreakoutStrategy 信號生成
  2. 對每個信號追蹤進場後 N 天的 MAE（Maximum Adverse Excursion）
     MAE = max(entry_price - low[t+1..t+N]) / entry_atr
  3. 計算 MAE/ATR 的分布統計
  4. 輸出 P10/P25/P50/P75/P90 的倍數建議

注意：
  - 這是回測研究，不是實盤信號
  - 使用 adj_close 計算（已還原權值）
  - 信號生成本身不含 lookahead（所有條件都用當天或之前的資料）
  - MAE 計算使用進場後的 adj_low（未來資料），這是研究用途，不是信號

使用：
  uv run python research/mae_atr_study.py
  uv run python research/mae_atr_study.py --lookback-days 20
  uv run python research/mae_atr_study.py --start 2022-01-01 --end 2024-12-31

Version: v0.1.0 (2026-05-27)
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import polars as pl

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.database import connect
from market.trading_calendar import is_trading_day
from strategies.trend_breakout import TrendBreakoutStrategy
from utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_MAE_WINDOW = 20   # trading days after entry to track MAE
_DEFAULT_START = date(2022, 1, 1)
_DEFAULT_END = date(2026, 5, 25)


def get_trading_dates(start: date, end: date) -> list[date]:
    """Return all trading days in [start, end] range."""
    with connect(read_only=True) as conn:
        rows = conn.execute("""
            SELECT DISTINCT date FROM market_regime
            WHERE date >= ? AND date <= ?
              AND regime IS NOT NULL
            ORDER BY date
        """, [start, end]).fetchall()
    return [r[0] for r in rows]


def load_forward_lows(
    stock_id: str,
    entry_date: date,
    window: int,
) -> list[float | None]:
    """Load adj_low for window trading days after entry_date."""
    with connect(read_only=True) as conn:
        rows = conn.execute("""
            SELECT date, adj_low
            FROM daily_price_adj
            WHERE stock_id = ?
              AND date > ?
            ORDER BY date
            LIMIT ?
        """, [stock_id, entry_date, window]).fetchall()
    return [r[1] for r in rows]


def compute_mae_study(
    start: date,
    end: date,
    mae_window: int,
) -> pl.DataFrame:
    """Run MAE study over all historical signals.

    Returns DataFrame with one row per signal, columns:
        signal_date, stock_id, entry_price, entry_atr,
        mae_abs, mae_atr_multiple, holding_days,
        max_favorable_close, mfe_atr_multiple
    """
    strategy = TrendBreakoutStrategy()
    trading_dates = get_trading_dates(start, end)

    print(f"Trading dates to scan: {len(trading_dates)}")
    print(f"MAE window: {mae_window} days after entry")
    print(f"Range: {start} → {end}\n")

    records = []
    n_signals = 0
    n_no_forward_data = 0

    for i, as_of in enumerate(trading_dates):
        if i % 50 == 0:
            print(f"  Scanning {as_of} ({i+1}/{len(trading_dates)})...")

        signals = strategy.generate_signals(as_of=as_of)
        if not signals:
            continue

        for sig in signals:
            n_signals += 1

            # Load forward price data
            forward_lows = load_forward_lows(sig.stock_id, as_of, mae_window)

            if not forward_lows or all(v is None for v in forward_lows):
                n_no_forward_data += 1
                continue

            valid_lows = [v for v in forward_lows if v is not None]
            if not valid_lows:
                continue

            # MAE: maximum adverse excursion (worst intraday low vs entry price)
            min_low = min(valid_lows)
            mae_abs = max(0.0, sig.entry_price - min_low)
            mae_atr = mae_abs / sig.entry_atr if sig.entry_atr > 0 else None

            # MFE: maximum favorable excursion (load forward closes)
            with connect(read_only=True) as conn:
                rows = conn.execute("""
                    SELECT adj_close FROM daily_price_adj
                    WHERE stock_id = ? AND date > ?
                    ORDER BY date LIMIT ?
                """, [sig.stock_id, as_of, mae_window]).fetchall()
            forward_closes = [r[0] for r in rows if r[0] is not None]
            max_close = max(forward_closes) if forward_closes else sig.entry_price
            mfe_abs = max(0.0, max_close - sig.entry_price)
            mfe_atr = mfe_abs / sig.entry_atr if sig.entry_atr > 0 else None

            records.append({
                "signal_date": as_of,
                "stock_id": sig.stock_id,
                "entry_price": sig.entry_price,
                "entry_atr": sig.entry_atr,
                "score": sig.score,
                "mae_abs": mae_abs,
                "mae_atr_multiple": mae_atr,
                "mfe_abs": mfe_abs,
                "mfe_atr_multiple": mfe_atr,
                "holding_days": len(valid_lows),
                "min_low": min_low,
                "max_close": max_close,
            })

    print(f"\nTotal signals generated: {n_signals}")
    print(f"No forward data (near end of dataset): {n_no_forward_data}")
    print(f"Analysable signals: {len(records)}")

    if not records:
        print("No signals found. Check date range and DB data.")
        return pl.DataFrame()

    return pl.DataFrame(records)


def print_results(df: pl.DataFrame) -> None:
    """Print MAE/ATR distribution analysis."""
    if df.is_empty():
        print("No data to analyse.")
        return

    mae_col = df["mae_atr_multiple"].drop_nulls()
    mfe_col = df["mfe_atr_multiple"].drop_nulls()

    print("\n" + "=" * 60)
    print("MAE / ATR DISTRIBUTION ANALYSIS")
    print("=" * 60)
    print(f"Total signals analysed: {len(df)}")
    print(f"Date range: {df['signal_date'].min()} → {df['signal_date'].max()}")
    print(f"Unique symbols: {df['stock_id'].n_unique()}")

    print("\n── MAE (Maximum Adverse Excursion) / ATR ──")
    percentiles = [10, 25, 50, 75, 90, 95]
    for p in percentiles:
        val = mae_col.quantile(p / 100)
        print(f"  P{p:2d}: {val:.2f}x ATR")

    print(f"\n  Mean:   {mae_col.mean():.2f}x ATR")
    print(f"  Std:    {mae_col.std():.2f}x ATR")
    print(f"  Max:    {mae_col.max():.2f}x ATR")

    print("\n── Stop Loss Survival Rate ──")
    print("  (% of signals that would NOT be stopped out)")
    for mult in [1.0, 1.5, 2.0, 2.5, 3.0]:
        survival = (mae_col <= mult).sum() / len(mae_col) * 100
        print(f"  Stop at {mult:.1f}×ATR: {survival:.1f}% survival rate")

    print("\n── MFE (Maximum Favorable Excursion) / ATR ──")
    for p in [25, 50, 75, 90]:
        val = mfe_col.quantile(p / 100)
        print(f"  P{p:2d}: {val:.2f}x ATR")

    print("\n── Risk/Reward by ATR Multiple ──")
    print("  Stop × ATR | Survival | Median MFE | E[R/R]")
    print("  " + "─" * 48)
    for mult in [1.0, 1.5, 2.0, 2.5, 3.0]:
        survival = (mae_col <= mult).sum() / len(mae_col)
        # Survivors: those not stopped out
        survivors = df.filter(pl.col("mae_atr_multiple") <= mult)
        if len(survivors) > 0:
            median_mfe = survivors["mfe_atr_multiple"].drop_nulls().median()
            rr = (median_mfe / mult) if mult > 0 else 0
            print(f"  {mult:.1f}×ATR      | {survival*100:5.1f}%   | {median_mfe:8.2f}×   | {rr:.2f}")

    print("\n── Current Setting Assessment ──")
    current_mult = 2.0
    current_survival = (mae_col <= current_mult).sum() / len(mae_col) * 100
    p50_mae = mae_col.quantile(0.50)
    p75_mae = mae_col.quantile(0.75)
    print(f"  Current stop: {current_mult}×ATR [ASSUMED]")
    print(f"  Survival rate at 2×ATR: {current_survival:.1f}%")
    print(f"  Median MAE: {p50_mae:.2f}×ATR")
    print(f"  P75 MAE:    {p75_mae:.2f}×ATR")

    if p50_mae < 1.0:
        print(f"\n  ⚠️  Median MAE < 1×ATR — 2×ATR stop may be too wide")
        print(f"     Consider: 1.5×ATR stop for tighter risk control")
    elif p75_mae > 2.5:
        print(f"\n  ⚠️  P75 MAE > 2.5×ATR — 2×ATR stop too tight for 25% of signals")
        print(f"     Consider: 2.5×ATR or 3×ATR to reduce premature stops")
    else:
        print(f"\n  ✓  2×ATR appears reasonable given this dataset")
        print(f"     [ASSUMED] → [CALIBRATED] pending out-of-sample validation")

    print("\n⚠️  IMPORTANT CAVEATS:")
    print("  - This uses adj_low (forward data) — research only, not signals")
    print("  - Survivorship bias: only symbols in current universe")
    print("  - No slippage or spread modelling")
    print("  - Bull regime only (strategy gate)")
    print("  - Results require out-of-sample validation before production use")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="MAE/ATR study for stop loss calibration"
    )
    parser.add_argument("--start", type=str,
                        default=str(_DEFAULT_START))
    parser.add_argument("--end", type=str,
                        default=str(_DEFAULT_END))
    parser.add_argument("--lookback-days", type=int,
                        default=_DEFAULT_MAE_WINDOW,
                        help=f"Trading days to track after entry (default {_DEFAULT_MAE_WINDOW})")
    parser.add_argument("--output", type=str, default=None,
                        help="Save raw results to CSV (optional)")
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    print(f"MAE/ATR Study — trend_breakout_v1")
    print(f"{'=' * 60}")

    df = compute_mae_study(start=start, end=end, mae_window=args.lookback_days)

    if df.is_empty():
        return 1

    print_results(df)

    if args.output:
        df.write_csv(args.output)
        print(f"\nRaw results saved to: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
