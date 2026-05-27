#!/usr/bin/env python3
# research/open_gap_study.py
"""Open-gap calibration study — v0.1.17 (#16).

Computes the distribution of overnight gaps:
  gap_pct = (adj_open[T+1] - adj_close[T]) / adj_close[T]

Purpose: calibrate max_entry_gap_pct from [ASSUMED] 0.03 to [CALIBRATED].
This value is used by both:
  - Backtest entry filter (is_entry_eligible)
  - execution_submitter limit price ceiling (INV-2)

Output: percentile table + recommendation.

Version: v0.1.17 (2026-05-27)
"""
from __future__ import annotations

import sys
from datetime import date as date_type

import duckdb
import numpy as np


def run_study(
    db_path: str = "data/_storage/helios.duckdb",
    min_date: str = "2022-01-01",
    max_date: str = "2026-05-27",
) -> dict:
    conn = duckdb.connect(db_path, read_only=True)

    # Self-join: T and T+1 for same stock_id
    # T+1 = next row by date per stock (not calendar — handles holidays)
    df = conn.execute(f"""
        WITH ordered AS (
            SELECT
                stock_id, date,
                adj_close,
                adj_open,
                LEAD(adj_open) OVER (PARTITION BY stock_id ORDER BY date) AS next_open,
                LEAD(date) OVER (PARTITION BY stock_id ORDER BY date) AS next_date
            FROM daily_price_adj
            WHERE date >= '{min_date}' AND date <= '{max_date}'
              AND adj_close > 0 AND adj_open > 0
        )
        SELECT
            stock_id, date, next_date, adj_close, next_open,
            (next_open - adj_close) / adj_close AS gap_pct
        FROM ordered
        WHERE next_open IS NOT NULL
          AND next_open > 0
          AND adj_close > 0
    """).fetchnumpy()

    conn.close()

    gaps = df["gap_pct"]
    abs_gaps = np.abs(gaps)

    # Buy-side only: positive gaps (open above close) are the risk
    # for limit-price ceiling
    positive_gaps = gaps[gaps > 0]

    percentiles = [50, 75, 90, 95, 97.5, 99, 99.5, 99.9]
    results = {
        "total_observations": len(gaps),
        "date_range": f"{min_date} to {max_date}",
        "positive_gap_count": len(positive_gaps),
        "positive_gap_pct": len(positive_gaps) / len(gaps) * 100,
    }

    print(f"Open-gap calibration study")
    print(f"  Date range: {min_date} to {max_date}")
    print(f"  Observations: {len(gaps):,}")
    print(f"  Positive gaps (open > prev close): {len(positive_gaps):,} "
          f"({results['positive_gap_pct']:.1f}%)")
    print()

    # All gaps (absolute)
    print("Absolute gap distribution:")
    print(f"  {'Pctl':>6}  {'Value':>8}  {'Meaning':>30}")
    print(f"  {'─'*6}  {'─'*8}  {'─'*30}")
    for p in percentiles:
        v = np.percentile(abs_gaps, p)
        results[f"abs_p{p}"] = v
        print(f"  {p:>5.1f}%  {v:>7.4f}  {v*100:.2f}% gap covers {p}% of days")

    print()

    # Positive gaps only (buy-side risk)
    print("Positive gap distribution (buy-side risk):")
    print(f"  {'Pctl':>6}  {'Value':>8}  {'Meaning':>30}")
    print(f"  {'─'*6}  {'─'*8}  {'─'*30}")
    for p in percentiles:
        v = np.percentile(positive_gaps, p)
        results[f"pos_p{p}"] = v
        print(f"  {p:>5.1f}%  {v:>7.4f}  {v*100:.2f}% gap covers {p}% of up-gaps")

    print()

    # Recommendation
    p95_pos = np.percentile(positive_gaps, 95)
    p99_pos = np.percentile(positive_gaps, 99)
    current = 0.03

    print("Recommendation:")
    print(f"  Current [ASSUMED]: {current*100:.1f}%")
    print(f"  P95 positive gap:  {p95_pos*100:.2f}%")
    print(f"  P99 positive gap:  {p99_pos*100:.2f}%")
    print()

    if current >= p95_pos:
        print(f"  → Current 3% covers ≥95% of positive gaps. Conservative enough.")
        print(f"  → Recommend: keep 0.03, mark as [CALIBRATED].")
        results["recommendation"] = 0.03
        results["calibration_note"] = "3% covers >=P95; conservative"
    elif current >= p90_pos:
        p90_pos = np.percentile(positive_gaps, 90)
        print(f"  → Current 3% covers ≥90% but <95% of positive gaps.")
        print(f"  → Consider widening to {p95_pos:.4f} for P95 coverage.")
        results["recommendation"] = round(p95_pos, 4)
        results["calibration_note"] = f"widen to P95={p95_pos:.4f}"
    else:
        print(f"  → Current 3% is too tight (<P90). Many valid entries would be skipped.")
        print(f"  → Recommend: {p95_pos:.4f} (P95) or {p99_pos:.4f} (P99).")
        results["recommendation"] = round(p95_pos, 4)
        results["calibration_note"] = f"too tight; recommend P95={p95_pos:.4f}"

    # How many entries would be skipped at various thresholds
    print()
    print("Skip rate at various thresholds (positive gaps only):")
    for threshold in [0.01, 0.02, 0.03, 0.04, 0.05, 0.07, 0.10]:
        skip_rate = np.mean(positive_gaps > threshold) * 100
        print(f"  {threshold*100:.0f}%: {skip_rate:.2f}% of up-gap entries skipped")

    return results


if __name__ == "__main__":
    run_study()
