#!/usr/bin/env python3
# research/audit_universe_survivorship.py
"""Universe Survivorship Audit — v0.2.0.

Quantifies survivorship and lookahead bias in the bullish_features universe
before any backtesting or alpha validation is attempted.

Problem
-------
universe_snapshot contains only a single snapshot (2026-05-20).  Any
simulation using this universe applied retroactively over multi-year history
is a current-constituent replay, not a point-in-time backtest.

This script measures the degree of contamination by asking:
    1. How stable is the symbol set over time?
    2. What fraction of each year's active symbols are in current top-200?
    3. Are symbols entering / leaving the sample, or is it a frozen list?
    4. What is the missingness pattern (gaps within a symbol's active period)?
    5. Does the evidence suggest delisted / dropped stocks are absent?

Verdict thresholds (documented here, not enforced in code)
----------------------------------------------------------
current_top200_coverage
    > 0.90   mild;     top-200 highly stable, bias modest
    0.80–0.90 moderate; directional sanity check only
    0.60–0.80 severe;   simulation results unreliable
    < 0.60   unusable; current-constituent replay, discard

Output
------
Prints a structured report to stdout.
Writes two CSV files:
    /tmp/survivorship_annual.csv    — per-year aggregate stats
    /tmp/survivorship_symbols.csv   — per-symbol first/last date + flags

Usage
-----
    uv run python research/audit_universe_survivorship.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date as Date
from pathlib import Path

import pandas as pd

from data.database import connect


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_symbol_dates(conn) -> pd.DataFrame:
    """One row per (stock_id, year) — count of feature rows available."""
    return conn.execute("""
        SELECT
            stock_id,
            YEAR(date)      AS yr,
            MIN(date)       AS first_date,
            MAX(date)       AS last_date,
            COUNT(*)        AS row_count,
            COUNT(DISTINCT date) AS trading_days
        FROM bullish_features
        GROUP BY stock_id, YEAR(date)
        ORDER BY stock_id, yr
    """).df()


def _load_symbol_lifetime(conn) -> pd.DataFrame:
    """Global first/last date per symbol across full history."""
    return conn.execute("""
        SELECT
            stock_id,
            MIN(date)       AS global_first,
            MAX(date)       AS global_last,
            COUNT(DISTINCT date) AS total_days
        FROM bullish_features
        GROUP BY stock_id
        ORDER BY stock_id
    """).df()


def _load_current_top200(conn) -> set[str]:
    rows = conn.execute("""
        SELECT stock_id FROM universe_snapshot
        WHERE passed = true
    """).fetchall()
    return {r[0] for r in rows}


def _load_trading_calendar(conn) -> pd.DataFrame:
    """Distinct dates in bullish_features — proxy for trading calendar."""
    return conn.execute("""
        SELECT DISTINCT date, YEAR(date) AS yr
        FROM bullish_features
        ORDER BY date
    """).df()


# ---------------------------------------------------------------------------
# Annual statistics
# ---------------------------------------------------------------------------

@dataclass
class AnnualStats:
    yr: int
    active_symbols: int          # symbols with >= 1 row this year
    current_top200_in_sample: int  # active symbols that are in current top-200
    current_top200_coverage: float # current_top200_in_sample / 200
    symbols_with_full_year: int  # symbols present for >= 90% of trading days
    symbols_entering: int        # symbols whose global_first falls in this year
    symbols_leaving: int         # symbols whose global_last falls in this year
    total_trading_days: int      # distinct dates in this year
    avg_symbols_per_day: float   # mean daily symbol count
    sample_density_gap: float    # 1 - (avg_per_day / active_symbols); measures sparsity, not true missingness


def compute_annual_stats(
    sym_yr: pd.DataFrame,
    sym_life: pd.DataFrame,
    cal: pd.DataFrame,
    current_top200: set[str],
) -> list[AnnualStats]:
    stats: list[AnnualStats] = []
    years = sorted(sym_yr["yr"].unique())

    for yr in years:
        yr_data = sym_yr[sym_yr["yr"] == yr]
        active = set(yr_data["stock_id"].unique())
        cal_yr = cal[cal["yr"] == yr]
        total_days = len(cal_yr)

        # Current top-200 overlap
        overlap = active & current_top200
        coverage = len(overlap) / 200 if current_top200 else 0.0

        # Full-year symbols: present >= 90% of trading days
        if total_days > 0:
            full_year = yr_data[
                yr_data["trading_days"] >= 0.9 * total_days
            ]["stock_id"].nunique()
        else:
            full_year = 0

        # Entering: global_first in this year
        entering = sym_life[
            sym_life["global_first"].apply(lambda d: d.year) == yr
        ]["stock_id"].nunique()

        # Leaving: global_last in this year (and not the final year in data)
        final_yr = max(years)
        if yr < final_yr:
            leaving = sym_life[
                sym_life["global_last"].apply(lambda d: d.year) == yr
            ]["stock_id"].nunique()
        else:
            leaving = 0  # current year — can't distinguish "left" from "not yet updated"

        # Average symbols per day (proxy: total row_count / trading_days)
        total_rows = int(yr_data["row_count"].sum())
        avg_per_day = total_rows / total_days if total_days > 0 else 0.0

        miss = 1.0 - (avg_per_day / len(active)) if active else 0.0

        stats.append(AnnualStats(
            yr=yr,
            active_symbols=len(active),
            current_top200_in_sample=len(overlap),
            current_top200_coverage=round(coverage, 4),
            symbols_with_full_year=full_year,
            symbols_entering=entering,
            symbols_leaving=leaving,
            total_trading_days=total_days,
            avg_symbols_per_day=round(avg_per_day, 1),
            sample_density_gap=round(miss, 4),
        ))
    return stats


# ---------------------------------------------------------------------------
# Symbol-level flags
# ---------------------------------------------------------------------------

def flag_symbols(
    sym_life: pd.DataFrame,
    current_top200: set[str],
    all_years: list[int],
) -> pd.DataFrame:
    """Per-symbol flags relevant to survivorship bias assessment."""
    first_yr = min(all_years)
    last_yr = max(all_years)

    df = sym_life.copy()
    df["in_current_top200"] = df["stock_id"].isin(current_top200)

    # Joined late: first appearance is > 1 year after the data start
    df["joined_late"] = df["global_first"].apply(
        lambda d: d.year > first_yr + 1
    )

    # Left early: last appearance is > 1 year before data end
    # Candidates: may have been delisted or dropped from universe
    df["left_early"] = df["global_last"].apply(
        lambda d: d.year < last_yr - 1
    )

    # Suspect survivor: in current top-200 AND has full history (no early exit)
    df["full_history_survivor"] = (
        df["in_current_top200"] & ~df["left_early"]
    )

    return df.sort_values("global_first")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _coverage_label(cov: float) -> str:
    """Classify survivorship bias severity by current_top200_coverage.

    Thresholds are conservative: even 20 stocks different from true PIT
    universe (10% of 200) represents a meaningful survivor tilt.
    """
    if cov > 0.90:
        return "MILD       (top-200 composition highly stable)"
    if cov >= 0.80:
        return "MODERATE   (directional sanity check only)"
    if cov >= 0.60:
        return "SEVERE     (simulation results unreliable)"
    return "UNUSABLE   (current-constituent replay; discard)"


def print_report(stats: list[AnnualStats], sym_flags: pd.DataFrame) -> None:
    print()
    print("=" * 72)
    print("UNIVERSE SURVIVORSHIP AUDIT")
    print("=" * 72)

    # --- Annual table ---
    hdr = (
        f"{'Year':<6} {'Active':>7} {'Top200↓':>8} {'Coverage':>9} "
        f"{'FullYr':>7} {'Enter':>6} {'Leave':>6} "
        f"{'TrdDays':>8} {'AvgPD':>7} {'Miss%':>6}"
    )
    print()
    print(hdr)
    print("-" * 72)
    for s in stats:
        print(
            f"{s.yr:<6} {s.active_symbols:>7} "
            f"{s.current_top200_in_sample:>8} "
            f"{s.current_top200_coverage:>9.1%} "
            f"{s.symbols_with_full_year:>7} "
            f"{s.symbols_entering:>6} "
            f"{s.symbols_leaving:>6} "
            f"{s.total_trading_days:>8} "
            f"{s.avg_symbols_per_day:>7.1f} "
            f"{s.sample_density_gap:>6.1%}"
        )

    # --- Coverage summary ---
    coverages = [s.current_top200_coverage for s in stats]
    mean_cov = sum(coverages) / len(coverages) if coverages else 0.0
    min_cov = min(coverages) if coverages else 0.0

    print()
    print("COVERAGE SUMMARY")
    print(f"  Mean current_top200_coverage : {mean_cov:.1%}")
    print(f"  Min  current_top200_coverage : {min_cov:.1%}")
    print(f"  Verdict                      : {_coverage_label(min_cov)}")

    # Key diagnostic: how many of the current top-200 existed at the
    # very start of the data window?  This directly measures how much
    # of the simulation is a hindsight replay of today's survivors.
    first_yr = min(s.yr for s in stats)
    first_yr_stats = next((s for s in stats if s.yr == first_yr), None)
    if first_yr_stats:
        n_existing = first_yr_stats.current_top200_in_sample
        n_top200 = len([s for s in stats if True])  # use current_top200 size
        # recompute directly from sym_flags passed via closure — not available here;
        # print the first-year overlap as a direct readable number instead
        print(f"  current_top200 present in {first_yr}  : {n_existing} / 200"
              f"  ({n_existing/200:.1%})")
        print(f"  Interpretation: {n_existing}/200 of today's top-200 were already"
              f" present at data start.")
        print(f"  Simulation is {n_existing/200:.0%} current-constituent replay"
              f" from year one.")

    # --- Symbol lifecycle ---
    n_total = len(sym_flags)
    n_in_top200 = sym_flags["in_current_top200"].sum()
    n_late = sym_flags["joined_late"].sum()
    n_early = sym_flags["left_early"].sum()
    n_survivors = sym_flags["full_history_survivor"].sum()

    print()
    print("SYMBOL LIFECYCLE")
    print(f"  Total distinct symbols in bullish_features : {n_total}")
    print(f"  Symbols in current top-200                 : {n_in_top200}")
    print(f"  Symbols NOT in current top-200             : {n_total - n_in_top200}")
    print(f"  Symbols that joined late (> yr+1)          : {n_late}")
    print(f"  Symbols that left early  (< yr_end-1)      : {n_early}")
    print(f"  Full-history current survivors             : {n_survivors}")

    # --- Early-exit symbols (likely delisted / dropped) ---
    early_exit = sym_flags[sym_flags["left_early"]].sort_values("global_last")
    if not early_exit.empty:
        print()
        print(f"SYMBOLS WITH EARLY EXIT (n={len(early_exit)}) — possible delisted/dropped:")
        print(f"  {'stock_id':<12} {'global_first':<14} {'global_last':<14} "
              f"{'total_days':>10} {'in_top200':>9}")
        for _, row in early_exit.iterrows():
            print(
                f"  {row['stock_id']:<12} {str(row['global_first']):<14} "
                f"{str(row['global_last']):<14} "
                f"{int(row['total_days']):>10} "
                f"{'YES' if row['in_current_top200'] else 'no':>9}"
            )

    # --- Interpretation guide ---
    print()
    print("INTERPRETATION GUIDE")
    print("  If active_symbols is near-constant across years AND")
    print("  symbols_entering ≈ symbols_leaving ≈ 0 AND")
    print("  coverage is consistently > 80% →")
    print("    universe is effectively a frozen current-constituent list.")
    print("    Simulation = survivorship-biased current-constituent replay.")
    print("    Alpha figures will be upward-biased by an unknown amount.")
    print()
    print("  If symbols_leaving > 0 AND those symbols are NOT in current")
    print("  top-200 → some delisted/dropped stocks were included historically.")
    print("  This is a partial PIT signal; estimate bias direction carefully.")
    print()
    print("  Rule: do NOT interpret backtest P&L as go-live alpha evidence")
    print("  until either (a) historical universe snapshots are available, or")
    print("  (b) survivorship bias is bounded and deemed acceptable for the")
    print("  decision being made.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    annual_csv = Path("/tmp/survivorship_annual.csv")
    symbols_csv = Path("/tmp/survivorship_symbols.csv")

    with connect(read_only=True) as conn:
        sym_yr = _load_symbol_dates(conn)
        sym_life = _load_symbol_lifetime(conn)
        current_top200 = _load_current_top200(conn)
        cal = _load_trading_calendar(conn)

    all_years = sorted(sym_yr["yr"].unique())
    annual = compute_annual_stats(sym_yr, sym_life, cal, current_top200)
    sym_flags = flag_symbols(sym_life, current_top200, all_years)

    print_report(annual, sym_flags)

    # --- Write CSVs ---
    pd.DataFrame([vars(s) for s in annual]).to_csv(annual_csv, index=False)
    sym_flags.to_csv(symbols_csv, index=False)
    print()
    print(f"Annual stats  → {annual_csv}")
    print(f"Symbol detail → {symbols_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
