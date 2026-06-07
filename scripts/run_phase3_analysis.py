#!/usr/bin/env python3
# scripts/run_phase3_analysis.py
"""Phase 3 Risk & Capital Efficiency Validation — v0.1.0.

Entry point for R8 Phase 3 analysis per research/r8_phase3_spec.md v0.1.2 (LOCKED).

Tracks:
    A — Risk Metrics (calendar-time NAV, Sharpe, Sortino, Calmar, MaxDD, correlation)
    B — Capital Efficiency (cap sensitivity: 10% / 15% / 20% / 25%)
    C — Illustrative Capacity Analysis (AUM breakeven under linear impact assumption)

Governance invariants:
    - Panel loaded via load_panel() — identical CTE to Phase 1 and Phase 2B.
    - Forward returns via compute_forward_returns() — frozen Phase 1 formula.
    - Signal ledger built before any NAV computation; only valid_path rows used.
    - Phase 2B fingerprint verified before any NAV computation.
      Full-sample S1 net = +1.64% ± 1 bp. Cost scaling matches Phase 2B
      (commission + slippage scaled by deployed_weight, not full NAV).
    - Daily NAV built from simple PnL accounting (weighted sum of simple
      returns per day); daily_log_return derived from NAV path afterwards.
      Forward-return-only step-function NAV is prohibited (D1A).
    - All price paths loaded in one bulk DuckDB query (no per-signal queries).
    - All risk metrics computed on daily log returns (§5.2 frozen convention).
    - TAIEX sourced from market_regime.taiex_close (only available source;
      price proxy, not total return index — documented in artifacts).
    - sector_index_daily: empty table — omitted, documented as data gap.
    - VIX: no table in DuckDB — omitted, documented as data gap.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Repo root and import setup
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import duckdb  # noqa: E402

from scripts.run_r8_phase1_a3 import (  # noqa: E402
    load_panel,
    load_price_series,
    compute_forward_returns,
)

# ---------------------------------------------------------------------------
# Frozen constants
# ---------------------------------------------------------------------------

DB_PATH: Final[Path] = _REPO_ROOT / "data/_storage/helios.duckdb"
ARTIFACT_DIR: Final[Path] = _REPO_ROOT / "data/_storage/r8_phase3/v0.1.0"
SCRIPT_VERSION: Final[str] = "0.1.0"
SPEC_VERSION: Final[str] = "0.1.2"

# Phase 2B fingerprint
P2B_FINGERPRINT_NET_S1: Final[float] = 0.0164     # +1.64%
P2B_FINGERPRINT_TOLERANCE: Final[float] = 0.0001   # ±1 bp

# Phase 1 panel boundaries
PANEL_START: Final[date] = date(2022, 3, 22)
PANEL_END: Final[date] = date(2026, 6, 4)

# Segment date ranges — frozen from Phase 2A SPEC §6.1
SEGMENT_DATES: Final[dict[str, tuple[date, date]]] = {
    "seg1": (date(2022, 3, 22),  date(2023, 10, 20)),
    "seg2": (date(2023, 10, 24), date(2024, 7, 9)),
    "seg3": (date(2024, 7, 10),  date(2025, 8, 8)),
    "seg4": (date(2025, 8, 11),  date(2026, 6, 4)),
}

# Scenario date pools — frozen from Phase 2B SPEC §6.3
SCENARIO_POOLS: Final[dict[str, list[str]]] = {
    "full_sample": ["seg1", "seg2", "seg3", "seg4"],
    "low_uplift":  ["seg2", "seg3"],
    "high_uplift": ["seg1", "seg4"],
}

# Target cell — frozen from Phase 1
TARGET_REGIME: Final[str] = "bull"
TARGET_NLU: Final[int] = 0

# Cost model — frozen from Phase 2B SPEC §4
COMMISSION_RT: Final[float] = 0.00585
SLIPPAGE: Final[dict[str, float]] = {
    "s0": 0.0000, "s1": 0.0020, "s2": 0.0050, "s3": 0.0100,
}

# Position sizing — frozen from Phase 3 SPEC §4.3
CAP_VARIANTS: Final[dict[str, tuple[float, int]]] = {
    "baseline": (0.10, 10),
    "b1":       (0.15, 6),   # floor(1/0.15)=6; max deployed NAV=90%
    "b2":       (0.20, 5),
    "b3":       (0.25, 4),
}
HOLDING_DAYS: Final[int] = 20
TRADING_DAYS_PER_YEAR: Final[int] = 252

# Track C anchors — Phase 2B primary table (first_10, Low-Uplift S3 net)
TRACK_C_IMPACT_BUDGET_PORTFOLIO: Final[float] = 0.0055   # +0.55%
TRACK_C_MEAN_DEPLOYED_WEIGHT: Final[float] = 0.334
TRACK_C_ADV_LEVELS_TWD_M: Final[list[float]] = [50.0, 100.0, 200.0, 500.0]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data gap report
# ---------------------------------------------------------------------------

@dataclass
class DataGapReport:
    """Documents data gaps discovered during schema validation."""

    missing_tables: list[str] = field(default_factory=list)
    empty_tables: list[str] = field(default_factory=list)
    coverage_gaps: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 1. Schema validation
# ---------------------------------------------------------------------------

def validate_schema_and_document_gaps(con: duckdb.DuckDBPyConnection) -> DataGapReport:
    """Validate input availability and document data gaps per SPEC §9.3.

    Confirmed gaps (schema inspection 2026-06-07):
        VIX:                 no table in DuckDB.
        sector_index_daily:  exists but 0 rows.
        TAIEX:               available only via market_regime.taiex_close
                             (price proxy, not total return index).
    """
    gap = DataGapReport()

    existing: set[str] = {
        row[0]
        for row in con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='main'"
        ).fetchall()
    }

    for tbl in ("daily_price_adj", "market_regime", "bullish_features",
                "listed_market_daily_price_adj"):
        if tbl not in existing:
            gap.missing_tables.append(tbl)
            log.error("MISSING required table: %s", tbl)

    if "sector_index_daily" in existing:
        rows = con.execute(
            "SELECT count(*) FROM sector_index_daily"
        ).fetchone()[0]
        if rows == 0:
            gap.empty_tables.append("sector_index_daily")
            log.warning(
                "DATA GAP: sector_index_daily empty — sector correlations omitted."
            )

    if not any("vix" in t.lower() for t in existing):
        gap.missing_tables.append("vix")
        log.warning(
            "DATA GAP: No VIX table — VIX correlation omitted from Track A."
        )

    taiex_rows = con.execute(
        "SELECT count(*) FROM market_regime WHERE taiex_close IS NOT NULL"
    ).fetchone()[0]
    if taiex_rows == 0:
        gap.coverage_gaps["taiex"] = "market_regime.taiex_close all NULL"
        log.error("TAIEX unavailable: market_regime.taiex_close is all NULL.")
    else:
        log.info(
            "TAIEX proxy: %d non-null rows in market_regime.taiex_close "
            "(price index, not total return)",
            taiex_rows,
        )

    return gap


# ---------------------------------------------------------------------------
# 2. Signal ledger construction
# ---------------------------------------------------------------------------

def build_signal_ledger(
    panel: pd.DataFrame,
    prices: pd.DataFrame,
    pool: str,
    scenario: str,
) -> pd.DataFrame:
    """Build canonical signal ledger for one pool × scenario combination.

    The ledger is the single source of truth for all subsequent computations.
    Only rows with valid_path=True are used for NAV reconstruction.

    Args:
        panel:    Full panel from load_panel() with fwd_20td attached.
        prices:   Price series from load_price_series(), indexed (stock_id, date).
        pool:     "treatment_1" or "baseline_1".
        scenario: "full_sample", "low_uplift", or "high_uplift".

    Returns:
        DataFrame with columns:
            stock_id, signal_date, entry_date, exit_date,
            fwd_return_20td, valid_path (bool), segment.
        Only rows within the scenario date pool and target cell are included.
        valid_path=True requires fwd_20td not NaN AND adj_open[T+1] > 0
        AND adj_close[T+20td] > 0.
    """
    # --- Target cell filter ---
    cell = panel[
        (panel["regime"] == TARGET_REGIME)
        & (panel["near_limit_up"] == TARGET_NLU)
        & (panel["universe"] == pool)
    ].copy()

    # --- Scenario date filter ---
    segs = SCENARIO_POOLS[scenario]
    masks = [
        (cell["date"] >= SEGMENT_DATES[seg][0])
        & (cell["date"] <= SEGMENT_DATES[seg][1])
        for seg in segs
    ]
    combined = masks[0]
    for m in masks[1:]:
        combined = combined | m
    cell = cell[combined].copy()

    # --- Trading calendar from price index — unified as pd.Timestamp ---
    # Use Timestamp throughout to avoid date/Timestamp dict lookup misses.
    all_dates_ts = pd.DatetimeIndex(
        sorted(pd.to_datetime(prices.index.get_level_values("date").unique()))
    )
    date_to_pos: dict[pd.Timestamp, int] = {
        d: i for i, d in enumerate(all_dates_ts)
    }

    # Rebuild price lookup keyed by (stock_id, Timestamp) to match all_dates_ts
    adj_open_map:  dict = {
        (s, pd.Timestamp(d)): v
        for (s, d), v in prices["adj_open"].to_dict().items()
    }
    adj_close_map: dict = {
        (s, pd.Timestamp(d)): v
        for (s, d), v in prices["adj_close"].to_dict().items()
    }

    # --- Segment labels (operate on Timestamps, compare with date constants) ---
    def _segment(ts: pd.Timestamp) -> str:
        d = ts.date()
        for seg, (s, e) in SEGMENT_DATES.items():
            if s <= d <= e:
                return seg
        return "unknown"

    records = []
    for _, row in cell.iterrows():
        # Normalise signal_date to pd.Timestamp for consistent dict lookup
        sig_ts = pd.Timestamp(row["date"])
        stock  = row["stock_id"]
        fwd    = row.get("fwd_20td", np.nan)

        pos = date_to_pos.get(sig_ts)
        if pos is None or pos + HOLDING_DAYS >= len(all_dates_ts):
            valid      = False
            entry_date = exit_date = None
        else:
            entry_ts = all_dates_ts[pos + 1]
            exit_ts  = all_dates_ts[pos + HOLDING_DAYS]
            entry_px = adj_open_map.get((stock, entry_ts))
            exit_px  = adj_close_map.get((stock, exit_ts))
            valid = (
                not pd.isna(fwd)
                and entry_px is not None and entry_px > 0
                and exit_px  is not None and exit_px  > 0
            )
            entry_date = entry_ts
            exit_date  = exit_ts

        records.append({
            "stock_id":        stock,
            "signal_date":     sig_ts,
            "entry_date":      entry_date,
            "exit_date":       exit_date,
            "fwd_return_20td": fwd if not pd.isna(fwd) else np.nan,
            "valid_path":      valid,
            "segment":         _segment(sig_ts),
        })

    ledger = pd.DataFrame(records)
    n_valid   = ledger["valid_path"].sum()
    n_invalid = (~ledger["valid_path"]).sum()
    log.info(
        "Signal ledger: pool=%s scenario=%s | total=%d valid=%d invalid=%d",
        pool, scenario, len(ledger), n_valid, n_invalid,
    )
    return ledger


# ---------------------------------------------------------------------------
# 3. Phase 2B fingerprint verification (P3-FP-001: candidate pool lineage)
# ---------------------------------------------------------------------------

@dataclass
class FingerprintResult:
    """Output of P3-FP-001 candidate-pool fingerprint check."""

    gross_mean: float
    net_s1: float
    mean_deployed_weight: float
    n_signal_dates: int
    passed: bool


def verify_phase2b_fingerprint(ledger: pd.DataFrame) -> FingerprintResult:
    """P3-FP-001: verify candidate pool reproduces Phase 2B Full-sample S1 net.

    Verifies that the pre-scheduler candidate ledger is lineage-identical to
    Phase 2B by replicating simulate_portfolio() logic:
        - first_10 overflow (sort by stock_id, take first max_pos)
        - baseline cap (10%, max 10 positions)
        - cost scaling: (commission + slippage) * mean_deployed_weight

    This fingerprint checks pool lineage only. It does NOT require the
    post-scheduler NAV to equal Phase 2B — the capital scheduler is a
    Phase 3 addition that produces different returns by design.

    Returns FingerprintResult written to manifest for auditability.
    Aborts with sys.exit(1) if fingerprint fails.
    """
    cap, max_pos = CAP_VARIANTS["baseline"]
    valid = ledger[ledger["valid_path"]].copy()

    gross_returns: list[float] = []
    deployed_weights: list[float] = []

    for sig_date, group in valid.groupby("signal_date"):
        stocks = group.sort_values("stock_id")
        if len(stocks) > max_pos:
            stocks = stocks.head(max_pos)
        n = len(stocks)
        if n == 0:
            continue
        weight = min(1.0 / n, cap)
        gross_returns.append((stocks["fwd_return_20td"] * weight).sum())
        deployed_weights.append(weight * n)

    gross_mean           = float(np.mean(gross_returns))
    mean_deployed_weight = float(np.mean(deployed_weights))
    cost   = mean_deployed_weight * (COMMISSION_RT + SLIPPAGE["s1"])
    net_s1 = gross_mean - cost
    n_dates = len(gross_returns)

    passed = abs(net_s1 - P2B_FINGERPRINT_NET_S1) <= P2B_FINGERPRINT_TOLERANCE
    result = FingerprintResult(
        gross_mean=gross_mean,
        net_s1=net_s1,
        mean_deployed_weight=mean_deployed_weight,
        n_signal_dates=n_dates,
        passed=passed,
    )

    if not passed:
        log.error(
            "P3-FP-001 FAIL: net_s1=+%.4f%% "
            "(expected +%.4f%% ± %.0f bp) | "
            "gross=%.4f%% mean_deployed=%.3f n_dates=%d",
            net_s1 * 100, P2B_FINGERPRINT_NET_S1 * 100,
            P2B_FINGERPRINT_TOLERANCE * 10_000,
            gross_mean * 100, mean_deployed_weight, n_dates,
        )
        sys.exit(1)

    log.info(
        "P3-FP-001 PASS: net_s1=+%.4f%% | "
        "gross=%.4f%% mean_deployed=%.3f n_dates=%d",
        net_s1 * 100, gross_mean * 100, mean_deployed_weight, n_dates,
    )
    return result


# ---------------------------------------------------------------------------
# 4. Capital scheduler (P3-FP-002: aggregate exposure <= 100%)
# ---------------------------------------------------------------------------

@dataclass
class ScheduledPosition:
    """A single position admitted by the capital scheduler."""

    stock_id: str
    signal_date: pd.Timestamp
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    weight: float
    fwd_return_20td: float


def schedule_positions(
    ledger: pd.DataFrame,
    cap: float,
    max_pos: int,
) -> tuple[list[ScheduledPosition], dict]:
    """Admit positions from candidate ledger subject to capital constraint.

    Scheduler rules (frozen per Phase 3 design decision 2026-06-07):
        1. Process signal_dates in ascending order.
        2. Within each signal_date, sort candidates by stock_id (ascending).
        3. Each candidate target_weight = cap (per-position cap).
        4. Expire positions whose exit_date <= current signal_date before
           evaluating new candidates (capital released on exit day close).
        5. Admit if len(open) < max_pos AND current_exposure + cap <= 100%.
        6. Skip otherwise; record as skipped_capital_constraint.
        7. No re-entry for a stock already in an open position.

    P3-FP-002: max daily gross exposure <= 100% (verified after scheduling).
    Raises RuntimeError if violated (scheduler bug).

    Returns:
        (scheduled_positions, diagnostics_dict)
    """
    valid = (
        ledger[ledger["valid_path"]]
        .sort_values(["signal_date", "stock_id"])
        .reset_index(drop=True)
    )

    # open_positions: stock_id → (exit_date, weight)
    open_positions: dict[str, tuple[pd.Timestamp, float]] = {}
    scheduled: list[ScheduledPosition] = []
    n_skipped_capital = 0
    n_skipped_duplicate = 0

    for sig_date in sorted(valid["signal_date"].unique()):
        sig_ts = pd.Timestamp(sig_date)

        # Release positions whose exit_date <= sig_date (capital available)
        expired = [
            sid for sid, (ex_dt, _) in open_positions.items()
            if ex_dt <= sig_ts
        ]
        for sid in expired:
            del open_positions[sid]

        current_exposure = sum(w for (_, w) in open_positions.values())

        for _, row in valid[valid["signal_date"] == sig_ts].iterrows():
            stock = row["stock_id"]

            if stock in open_positions:
                n_skipped_duplicate += 1
                continue

            if len(open_positions) >= max_pos:
                n_skipped_capital += 1
                continue

            if current_exposure + cap > 1.0 + 1e-9:
                n_skipped_capital += 1
                continue

            open_positions[stock] = (row["exit_date"], cap)
            current_exposure += cap
            scheduled.append(ScheduledPosition(
                stock_id=stock,
                signal_date=sig_ts,
                entry_date=row["entry_date"],
                exit_date=row["exit_date"],
                weight=cap,
                fwd_return_20td=row["fwd_return_20td"],
            ))

    # P3-FP-002: verify max daily gross exposure <= 100%
    if scheduled:
        daily_exp: dict[pd.Timestamp, float] = {}
        for pos in scheduled:
            cur = pos.entry_date
            while cur <= pos.exit_date:
                daily_exp[cur] = daily_exp.get(cur, 0.0) + pos.weight
                cur += pd.Timedelta(days=1)
        max_exp = max(daily_exp.values())
        if max_exp > 1.0 + 1e-6:
            raise RuntimeError(
                f"P3-FP-002 FAIL: max_daily_exposure={max_exp:.4f} > 100%. "
                "Capital scheduler has a bug."
            )
    else:
        max_exp = 0.0

    n_cand = len(valid)
    log.info(
        "P3-FP-002 PASS: max_exposure=%.1f%% | "
        "scheduled=%d/%d skipped_capital=%d skipped_duplicate=%d",
        max_exp * 100, len(scheduled), n_cand,
        n_skipped_capital, n_skipped_duplicate,
    )

    diagnostics = {
        "n_candidates":        n_cand,
        "n_scheduled":         len(scheduled),
        "n_skipped_capital":   n_skipped_capital,
        "n_skipped_duplicate": n_skipped_duplicate,
        "admission_rate":      round(len(scheduled) / max(n_cand, 1), 4),
        "max_daily_exposure":  round(max_exp, 4),
        "fp002_passed":        True,
    }
    return scheduled, diagnostics


# ---------------------------------------------------------------------------
# 5. Bulk daily price path loader (one query, no per-signal round-trips)
# ---------------------------------------------------------------------------

def load_daily_price_paths(
    con: duckdb.DuckDBPyConnection,
    scheduled: list[ScheduledPosition],
) -> pd.DataFrame:
    """Load daily adj_close and adj_open for all scheduled positions in one query.

    Governance: per-signal DuckDB round-trips are prohibited.
    Issues exactly one query regardless of position count.

    Covers from min(entry_date) to max(exit_date) across all positions.

    Returns:
        DataFrame with columns: stock_id, date (datetime64), adj_close, adj_open.
    """
    if not scheduled:
        raise ValueError(
            "load_daily_price_paths: scheduled position list is empty."
        )
    stock_ids = list({p.stock_id for p in scheduled})

    min_date = min(p.entry_date for p in scheduled).date()
    max_date = max(p.exit_date  for p in scheduled).date()

    ids_sql = ", ".join(f"'{s}'" for s in stock_ids)
    query = f"""
        SELECT stock_id, date, adj_close, adj_open
        FROM daily_price_adj
        WHERE stock_id IN ({ids_sql})
          AND date BETWEEN '{min_date}' AND '{max_date}'
        ORDER BY stock_id, date
    """
    df = con.execute(query).fetchdf()
    df["date"] = pd.to_datetime(df["date"])
    log.info(
        "Bulk price load: %d stocks | %s → %s | rows=%d",
        len(stock_ids), min_date, max_date, len(df),
    )
    return df


# ---------------------------------------------------------------------------
# 5. Calendar-time NAV reconstruction — D1A simple PnL (PROHIBITED excluded)
# ---------------------------------------------------------------------------

def reconstruct_nav(
    scheduled: list[ScheduledPosition],
    price_df: pd.DataFrame,
    cap: float,
) -> pd.DataFrame:
    """Reconstruct calendar-time portfolio NAV from scheduled positions.

    D1A implementation (Phase 3 SPEC §4.1):
        Entry:         adj_open[T+1]      (entry_date from ScheduledPosition)
        Holding k=1:   simple_ret = adj_close[T+1] / adj_open[T+1] - 1
        Holding k>1:   simple_ret = adj_close[T+k] / adj_close[T+k-1] - 1
        Exit:          adj_close[T+20td]  (exit_date from ScheduledPosition)
        Non-holding day: portfolio simple return = 0 (cash earns 0%)

    NAV built via simple PnL accounting:
        nav[t] = nav[t-1] * (1 + portfolio_simple_return[t])

    daily_log_return = log(nav[t] / nav[t-1])  — derived from NAV path.

    Aggregate exposure is guaranteed <= 100% by the capital scheduler
    (P3-FP-002). This function does not re-check; it trusts the scheduler.

    PROHIBITED pattern (not used here):
        nav[entry:exit] = 0; nav[exit] += fwd_return_20td  (step-function)

    Args:
        scheduled: Positions admitted by schedule_positions().
        price_df:  Bulk-loaded daily prices from load_daily_price_paths().
        cap:       Per-position weight cap (used for invariant error messages).

    Returns:
        DataFrame: date (datetime64), nav, daily_log_return.
        Covers from PANEL_START to max(exit_date) across all positions.
    """
    if not scheduled:
        raise ValueError("reconstruct_nav: scheduled position list is empty.")

    # Build price lookup: (stock_id, pd.Timestamp) → price
    _keys     = list(zip(price_df["stock_id"], price_df["date"]))
    close_map: dict = dict(zip(_keys, price_df["adj_close"]))
    open_map:  dict = dict(zip(_keys, price_df["adj_open"]))

    # Calendar: all trading dates from price_df, starting at PANEL_START
    all_dates_ts = pd.DatetimeIndex(sorted(price_df["date"].unique()))
    panel_start_ts = pd.Timestamp(PANEL_START)
    cal = all_dates_ts[all_dates_ts >= panel_start_ts]
    date_to_pos: dict[pd.Timestamp, int] = {d: i for i, d in enumerate(cal)}

    port_simple_ret = np.zeros(len(cal), dtype=float)

    for pos in scheduled:
        # entry_date = T+1 (first holding day)
        entry_pos = date_to_pos.get(pos.entry_date)
        if entry_pos is None:
            log.warning(
                "reconstruct_nav: entry_date %s not in calendar for %s — skipped",
                pos.entry_date, pos.stock_id,
            )
            continue

        # Iterate k=1..HOLDING_DAYS using entry_date as k=1
        for k in range(HOLDING_DAYS):
            tk_pos = entry_pos + k
            if tk_pos >= len(cal):
                break
            t_k  = cal[tk_pos]
            t_k1 = cal[tk_pos - 1] if tk_pos > 0 else None

            close_k = close_map.get((pos.stock_id, t_k))
            if close_k is None or close_k <= 0:
                continue

            if k == 0:
                # k=0 in this loop = T+1 in holding window (entry day)
                # Cost basis: adj_open[T+1]
                open_k = open_map.get((pos.stock_id, t_k))
                if open_k is None or open_k <= 0:
                    continue
                day_simple = close_k / open_k - 1.0
            else:
                if t_k1 is None:
                    continue
                close_prev = close_map.get((pos.stock_id, t_k1))
                if close_prev is None or close_prev <= 0:
                    continue
                day_simple = close_k / close_prev - 1.0

            port_simple_ret[tk_pos] += pos.weight * day_simple

    # Build NAV from simple PnL accounting
    nav = np.empty(len(cal), dtype=float)
    nav[0] = 1.0
    for i in range(1, len(cal)):
        nav[i] = nav[i - 1] * (1.0 + port_simple_ret[i])
        if nav[i] <= 0:
            raise RuntimeError(
                f"NAV non-positive at {cal[i].date()} "
                f"(nav={nav[i]:.6f}, port_ret={port_simple_ret[i]:.6f}). "
                f"Inspect price data for splits or data errors (cap={cap:.0%})."
            )

    log_ret = np.empty(len(cal), dtype=float)
    log_ret[0] = 0.0
    log_ret[1:] = np.log(nav[1:] / nav[:-1])

    return pd.DataFrame({
        "date":             cal,
        "nav":              nav,
        "daily_log_return": log_ret,
    })


# ---------------------------------------------------------------------------
# 6. Risk metrics — §5.2 log return convention (frozen)
# ---------------------------------------------------------------------------

def compute_risk_metrics(nav_df: pd.DataFrame, label: str) -> dict:
    """Compute mandatory Track A risk metrics.

    All metrics use daily log returns derived from the NAV path
    (Phase 3 SPEC §5.2 frozen convention). Mixing simple/log returns
    is prohibited.

    Annualised return uses geometric compounding (nav_end / nav_start).
    Volatility, Sharpe, Sortino use std of daily log returns.
    """
    log_rets = nav_df["daily_log_return"].values
    nav      = nav_df["nav"].values
    n        = len(log_rets)

    if n < 2:
        log.error("Insufficient observations: %s (n=%d)", label, n)
        return {"label": label, "error": "insufficient_observations"}

    ann_return = float((nav[-1] / nav[0]) ** (TRADING_DAYS_PER_YEAR / n) - 1.0)
    ann_vol    = float(np.std(log_rets, ddof=1)) * np.sqrt(TRADING_DAYS_PER_YEAR)
    sharpe     = ann_return / ann_vol if ann_vol > 0.0 else np.nan

    downside = log_rets[log_rets < 0.0]
    if len(downside) > 1:
        dd_vol  = float(np.std(downside, ddof=1)) * np.sqrt(TRADING_DAYS_PER_YEAR)
        sortino = ann_return / dd_vol if dd_vol > 0.0 else np.nan
    else:
        sortino = np.nan

    peak      = np.maximum.accumulate(nav)
    dd_series = (peak - nav) / peak
    max_dd    = float(np.max(dd_series))

    # Average drawdown: mean of per-trough depths (one value per contiguous
    # drawdown episode, measured at its lowest point)
    avg_dd = _avg_drawdown_trough(nav)

    max_dd_dur = _max_dd_duration(nav_df["date"].values, nav)
    calmar     = ann_return / max_dd if max_dd > 0.0 else np.nan

    def _f(v: float) -> float | None:
        return round(v, 6) if not np.isnan(v) else None

    log.info(
        "[%s] ann_ret=%.2f%% vol=%.2f%% Sharpe=%.3f MaxDD=%.2f%% Calmar=%.3f",
        label,
        ann_return * 100, ann_vol * 100,
        sharpe if not np.isnan(sharpe) else float("nan"),
        max_dd * 100,
        calmar if not np.isnan(calmar) else float("nan"),
    )

    return {
        "label":                               label,
        "n_calendar_days":                     n,
        "ann_return":                          _f(ann_return),
        "ann_volatility":                      _f(ann_vol),
        "sharpe":                              _f(sharpe),
        "sortino":                             _f(sortino),
        "calmar":                              _f(calmar),
        "max_drawdown":                        _f(max_dd),
        "avg_drawdown_trough":                 _f(avg_dd),
        "max_drawdown_duration_calendar_days": max_dd_dur,
        "return_convention":                   "daily_log_return_from_nav",
        "risk_free_rate":                      0.0,
    }


def _avg_drawdown_trough(nav: np.ndarray) -> float:
    """Mean of per-episode trough drawdown depths.

    One depth value per contiguous drawdown episode, measured at the
    episode's deepest point relative to the preceding peak.
    """
    peak = np.maximum.accumulate(nav)
    dd   = (peak - nav) / peak
    troughs = []
    in_dd   = False
    episode_max = 0.0
    for v in dd:
        if v > 0.0:
            in_dd = True
            episode_max = max(episode_max, v)
        else:
            if in_dd:
                troughs.append(episode_max)
            in_dd = False
            episode_max = 0.0
    if in_dd:
        troughs.append(episode_max)
    return float(np.mean(troughs)) if troughs else 0.0


def _max_dd_duration(dates: np.ndarray, nav: np.ndarray) -> int:
    """Max drawdown duration in calendar days (peak → full recovery)."""
    peak_val  = nav[0]
    peak_date = dates[0]
    dd_start  = None
    max_dur   = 0
    for d, v in zip(dates, nav):
        if v >= peak_val:
            if dd_start is not None:
                dur = (pd.Timestamp(d) - pd.Timestamp(dd_start)).days
                max_dur = max(max_dur, dur)
            peak_val  = v
            peak_date = d
            dd_start  = None
        else:
            if dd_start is None:
                dd_start = peak_date
    if dd_start is not None:
        dur = (pd.Timestamp(dates[-1]) - pd.Timestamp(dd_start)).days
        max_dur = max(max_dur, dur)
    return max_dur


# ---------------------------------------------------------------------------
# 7. Correlation diagnostics — Track A §5.3
# ---------------------------------------------------------------------------

def compute_correlations(
    r8_nav_df: pd.DataFrame,
    rs_t3_nav_df: pd.DataFrame,
    market_regime_df: pd.DataFrame,
) -> dict:
    """Compute Track A correlation diagnostics.

    Available:  TAIEX via market_regime.taiex_close (price proxy, not
                total return index — documented in output).
                Regime column for conditional mean analysis.
    Omitted:    VIX (no table), sector_index_daily (empty).
    """
    r8  = r8_nav_df[["date", "daily_log_return"]].rename(
        columns={"daily_log_return": "r8"})
    rs3 = rs_t3_nav_df[["date", "daily_log_return"]].rename(
        columns={"daily_log_return": "rs_t3"})
    merged = r8.merge(rs3, on="date", how="inner")

    taiex = market_regime_df[["date", "taiex_close", "regime"]].copy()
    taiex["date"] = pd.to_datetime(taiex["date"])
    taiex = taiex.sort_values("date").reset_index(drop=True)
    taiex["taiex_log_ret"] = np.log(
        taiex["taiex_close"] / taiex["taiex_close"].shift(1)
    )
    # Drop first row (NaN from shift) before merge to avoid polluting correlations
    taiex = taiex.dropna(subset=["taiex_log_ret"])
    merged = merged.merge(
        taiex[["date", "taiex_log_ret", "regime"]], on="date", how="left"
    )

    def _pearson(a: str, b: str) -> float | None:
        v = merged[a].corr(merged[b])
        return round(float(v), 4) if pd.notna(v) else None

    regime_means: dict = {}
    for regime, grp in merged.groupby("regime"):
        regime_means[str(regime)] = {
            "mean_daily_log_ret": round(float(grp["r8"].mean()), 6),
            "n_days":             int(len(grp)),
        }

    return {
        "pearson_r8_vs_rs_t3_baseline": _pearson("r8", "rs_t3"),
        "pearson_r8_vs_taiex":          _pearson("r8", "taiex_log_ret"),
        "r8_regime_conditional_mean":   regime_means,
        "data_gaps": {
            "vix":          "No VIX table in DuckDB — correlation omitted",
            "sector_index": "sector_index_daily is empty (0 rows) — omitted",
            "taiex_note":   (
                "TAIEX sourced from market_regime.taiex_close — "
                "price index proxy, not total return index"
            ),
        },
    }


# ---------------------------------------------------------------------------
# 8. Track B — Capital efficiency
# ---------------------------------------------------------------------------

def run_track_b(
    con: duckdb.DuckDBPyConnection,
    ledger: pd.DataFrame,
    scenario: str,
) -> list[dict]:
    """Run cap sensitivity for all variants.

    Per SPEC §4.3 and §6: Full Sample and Low-Uplift scenarios, S1 only.
    All results carry mandatory label: SENSITIVITY — ZERO PRICE IMPACT ASSUMPTION.

    Each variant runs its own capital scheduler, ensuring exposure <= 100%
    under that variant's cap and max_pos constraints.
    """
    results = []
    for name, (cap, max_pos) in CAP_VARIANTS.items():
        log.info(
            "Track B: variant=%s cap=%.0f%% max_pos=%d scenario=%s",
            name, cap * 100, max_pos, scenario,
        )
        scheduled, sched_diag = schedule_positions(ledger, cap, max_pos)
        price_df = load_daily_price_paths(con, scheduled)
        nav_df   = reconstruct_nav(scheduled, price_df, cap)
        metrics  = compute_risk_metrics(nav_df, label=f"track_b_{name}_{scenario}")
        mean_dep = (
            sum(p.weight for p in scheduled) / max(sched_diag["n_candidates"], 1)
            if scheduled else 0.0
        )

        results.append({
            "variant":             name,
            "cap_pct":             cap * 100,
            "max_positions":       max_pos,
            "scenario":            scenario,
            "mean_deployed_nav":   round(mean_dep, 4),
            "n_scheduled":         sched_diag["n_scheduled"],
            "admission_rate":      sched_diag["admission_rate"],
            "max_daily_exposure":  sched_diag["max_daily_exposure"],
            "sensitivity_label":   "SENSITIVITY — ZERO PRICE IMPACT ASSUMPTION",
            **metrics,
        })
    return results


# ---------------------------------------------------------------------------
# 9. Track C — Illustrative Capacity Analysis
# ---------------------------------------------------------------------------

def run_track_c() -> dict:
    """AUM breakeven table per Phase 3 SPEC §7 (illustrative only).

    Impact scaling assumption: impact scales proportionally with deployed NAV;
    all positions treated as perfectly correlated (conservative upper bound;
    no diversification benefit modelled). Per SPEC §4.4 D4 explicit assumption.
    """
    budget_rt = TRACK_C_IMPACT_BUDGET_PORTFOLIO / TRACK_C_MEAN_DEPLOYED_WEIGHT
    budget_ow = budget_rt / 2.0

    table = []
    for cap_label, pos_weight in [("baseline_10pct", 0.10), ("b2_20pct", 0.20)]:
        for adv_m in TRACK_C_ADV_LEVELS_TWD_M:
            adv_twd = adv_m * 1_000_000
            # Inverse linear model (coefficient=1.0):
            # impact = AUM * pos_weight / ADV; set = budget_ow
            # → AUM = budget_ow * ADV / pos_weight
            aum_m = budget_ow * adv_twd / pos_weight / 1_000_000
            table.append({
                "cap_variant":         cap_label,
                "position_weight":     pos_weight,
                "assumed_adv_twd_m":   adv_m,
                "aum_breakeven_twd_m": round(aum_m, 1),
                "illustrative_only":   True,
            })

    return {
        "methodology":              "inverse_linear_impact",
        "impact_coefficient":       1.0,
        "coefficient_interpretation": (
            "impact_coefficient=1.0 means 100% ADV participation = 100% impact. "
            "This is a deliberately conservative (worst-case) assumption."
        ),
        "anchor_low_uplift_s3_net": TRACK_C_IMPACT_BUDGET_PORTFOLIO,
        "mean_deployed_weight":     TRACK_C_MEAN_DEPLOYED_WEIGHT,
        "impact_budget_per_pos_rt": round(budget_rt, 4),
        "impact_budget_per_pos_ow": round(budget_ow, 4),
        "impact_scaling_assumption": (
            "Impact scales proportionally with deployed NAV; all positions "
            "treated as perfectly correlated (conservative upper bound; "
            "diversification benefit not modelled)."
        ),
        "mandatory_limitations": (
            "The AUM breakeven table uses a simplified linear impact model "
            "with assumed coefficient 1.0 (full impact at 100% ADV). "
            "ADV figures are hypothetical; no live ADV data incorporated. "
            "Order-of-magnitude guidance only. Does not establish a "
            "production AUM limit. Must be revisited with empirical ADV "
            "data before any deployment decision."
        ),
        "aum_breakeven_table": table,
    }


# ---------------------------------------------------------------------------
# 10. Artifact writer
# ---------------------------------------------------------------------------

def write_artifacts(
    nav_r8_full: pd.DataFrame,
    nav_rs3_full: pd.DataFrame,
    risk_metrics: list[dict],
    correlation: dict,
    track_b: list[dict],
    track_c: dict,
    gap_report: DataGapReport,
    fp_result: FingerprintResult,
    sched_diags: dict,
) -> None:
    """Write all Phase 3 artifacts to data/_storage/r8_phase3/v0.1.0/."""
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    # p3a_nav_series
    nav_out = (
        nav_r8_full
        .rename(columns={"nav": "nav_r8", "daily_log_return": "log_ret_r8"})
        .merge(
            nav_rs3_full.rename(
                columns={"nav": "nav_rs_t3", "daily_log_return": "log_ret_rs_t3"}
            ),
            on="date", how="outer",
        )
        .sort_values("date")
    )
    nav_out.to_parquet(ARTIFACT_DIR / "p3a_nav_series.parquet", index=False)
    log.info("Wrote p3a_nav_series.parquet (%d rows)", len(nav_out))

    # p3a_risk_metrics
    with open(ARTIFACT_DIR / "p3a_risk_metrics.json", "w") as f:
        json.dump(risk_metrics, f, indent=2, default=str)
    log.info("Wrote p3a_risk_metrics.json (%d entries)", len(risk_metrics))

    # p3a_correlation — daily return pairs for rolling correlation analysis
    corr_pairs = nav_out[["date", "log_ret_r8", "log_ret_rs_t3"]].copy()
    corr_pairs.to_parquet(ARTIFACT_DIR / "p3a_correlation.parquet", index=False)
    with open(ARTIFACT_DIR / "p3a_correlation_metadata.json", "w") as f:
        json.dump(correlation, f, indent=2, default=str)
    log.info("Wrote p3a_correlation artifacts")

    # p3b_cap_sensitivity
    pd.DataFrame(track_b).to_parquet(
        ARTIFACT_DIR / "p3b_cap_sensitivity.parquet", index=False
    )
    log.info("Wrote p3b_cap_sensitivity.parquet (%d rows)", len(track_b))

    # p3c_aum_breakeven
    with open(ARTIFACT_DIR / "p3c_aum_breakeven.json", "w") as f:
        json.dump(track_c, f, indent=2, default=str)
    log.info("Wrote p3c_aum_breakeven.json")

    # manifest
    manifest = {
        "script_version": SCRIPT_VERSION,
        "spec_version":   SPEC_VERSION,
        "generated_at":   pd.Timestamp.now(tz="Asia/Taipei").isoformat(),
        "db_path":        str(DB_PATH),
        "artifact_dir":   str(ARTIFACT_DIR),
        "panel_source":   "load_panel() from run_r8_phase1_a3 — identical CTE",
        "fwd_return_source": "compute_forward_returns() — Phase 1 frozen formula",
        "data_gaps": {
            "missing_tables": gap_report.missing_tables,
            "empty_tables":   gap_report.empty_tables,
            "coverage_gaps":  gap_report.coverage_gaps,
        },
        "artifacts": [
            "p3a_nav_series.parquet",
            "p3a_risk_metrics.json",
            "p3a_correlation.parquet",
            "p3a_correlation_metadata.json",
            "p3b_cap_sensitivity.parquet",
            "p3c_aum_breakeven.json",
            "manifest.json",
        ],
        "governance": {
            "fingerprint_check":     "Phase 2B Full-sample S1 net = +1.64% ± 1 bp",
            "cost_scaling":          "commission + slippage scaled by deployed_weight",
            "nav_source":            "D1A: daily simple PnL from daily_price_adj.adj_close",
            "nav_prohibited":        "forward-return-only step-function NAV prohibited",
            "return_convention":     "daily_log_return derived from NAV path (§5.2)",
            "track_b_label":         "SENSITIVITY — ZERO PRICE IMPACT ASSUMPTION",
            "track_c_label":         "ILLUSTRATIVE CAPACITY ANALYSIS",
            "taiex_note":            "price proxy via market_regime.taiex_close",
            "capital_scheduler":     "Interpretation B: shared capital pool, exposure <= 100%",
        },
        "p3_fp_001": {
            "gross_mean":            fp_result.gross_mean,
            "net_s1":                fp_result.net_s1,
            "mean_deployed_weight":  fp_result.mean_deployed_weight,
            "n_signal_dates":        fp_result.n_signal_dates,
            "passed":                fp_result.passed,
        },
        "scheduler_diagnostics": sched_diags,
    }
    with open(ARTIFACT_DIR / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2, default=str)
    log.info("Wrote manifest.json")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Run Phase 3 analysis end-to-end."""
    log.info("=== Phase 3 runner v%s (SPEC v%s) ===", SCRIPT_VERSION, SPEC_VERSION)

    if not DB_PATH.exists():
        log.error("DuckDB not found: %s", DB_PATH)
        sys.exit(1)

    with duckdb.connect(str(DB_PATH), read_only=True) as con:

        # Schema validation
        gap_report = validate_schema_and_document_gaps(con)
        if "daily_price_adj" in gap_report.missing_tables:
            log.error("Cannot proceed: daily_price_adj missing (D1A source).")
            sys.exit(1)

        # Market regime (TAIEX proxy + regime column)
        market_regime_df = con.execute(
            "SELECT date, taiex_close, regime FROM market_regime ORDER BY date"
        ).fetchdf()
        market_regime_df["date"] = pd.to_datetime(market_regime_df["date"])

        # Load full panel via Phase 1 CTE (identical to Phase 1 and Phase 2B)
        panel = load_panel(con)

        # Load price series and attach forward returns (Phase 1 frozen formula)
        prices = load_price_series(con)
        panel  = compute_forward_returns(panel, prices, horizons=[HOLDING_DAYS])
        # compute_forward_returns uses fwd_{h}td naming convention
        panel  = panel.rename(columns={f"fwd_{HOLDING_DAYS}td": "fwd_20td"})

        log.info(
            "Panel with fwd_20td: %d rows | treatment=%d baseline=%d | "
            "fwd_20td valid=%d",
            len(panel),
            (panel["universe"] == "treatment_1").sum(),
            (panel["universe"] == "baseline_1").sum(),
            panel["fwd_20td"].notna().sum(),
        )

        # P3-FP-001: verify candidate pool lineage against Phase 2B
        ledger_full_t = build_signal_ledger(panel, prices, "treatment_1", "full_sample")
        fp_result = verify_phase2b_fingerprint(ledger_full_t)

        # ----------------------------------------------------------------
        # Track A — risk metrics (all three scenarios)
        # ----------------------------------------------------------------
        all_risk_metrics: list[dict] = []
        nav_r8_full: pd.DataFrame | None = None
        nav_rs3_full: pd.DataFrame | None = None
        correlation_results: dict = {}

        cap_base, max_pos_base = CAP_VARIANTS["baseline"]
        sched_diags: dict = {}  # scenario → scheduler diagnostics (for manifest)

        for scenario in ("full_sample", "low_uplift", "high_uplift"):
            log.info("--- Track A: scenario=%s ---", scenario)

            ledger_t = (
                ledger_full_t if scenario == "full_sample"
                else build_signal_ledger(panel, prices, "treatment_1", scenario)
            )
            ledger_b = build_signal_ledger(panel, prices, "baseline_1", scenario)

            # Capital scheduler: admit positions with exposure <= 100%
            sched_t, diag_t = schedule_positions(ledger_t, cap_base, max_pos_base)
            sched_b, diag_b = schedule_positions(ledger_b, cap_base, max_pos_base)
            sched_diags[f"{scenario}_treatment"] = diag_t
            sched_diags[f"{scenario}_baseline"]  = diag_b

            price_t = load_daily_price_paths(con, sched_t)
            price_b = load_daily_price_paths(con, sched_b)

            nav_r8    = reconstruct_nav(sched_t, price_t, cap_base)
            nav_rs_t3 = reconstruct_nav(sched_b, price_b, cap_base)

            all_risk_metrics.append(
                compute_risk_metrics(nav_r8,    f"r8_{scenario}_baseline_cap")
            )
            all_risk_metrics.append(
                compute_risk_metrics(nav_rs_t3, f"rs_t3_{scenario}_baseline_cap")
            )

            if scenario == "full_sample":
                nav_r8_full  = nav_r8
                nav_rs3_full = nav_rs_t3
                correlation_results = compute_correlations(
                    nav_r8, nav_rs_t3, market_regime_df
                )

        # ----------------------------------------------------------------
        # Track B — capital efficiency (full_sample + low_uplift, S1)
        # ----------------------------------------------------------------
        all_track_b_results: list[dict] = []
        for scenario in ("full_sample", "low_uplift"):
            log.info("--- Track B: scenario=%s ---", scenario)
            ledger_b_t = (
                ledger_full_t if scenario == "full_sample"
                else build_signal_ledger(panel, prices, "treatment_1", scenario)
            )
            all_track_b_results.extend(run_track_b(con, ledger_b_t, scenario))

        # ----------------------------------------------------------------
        # Track C — illustrative capacity analysis
        # ----------------------------------------------------------------
        log.info("--- Track C ---")
        track_c_results = run_track_c()

        # ----------------------------------------------------------------
        # Write artifacts
        # ----------------------------------------------------------------
        write_artifacts(
            nav_r8_full=nav_r8_full,
            nav_rs3_full=nav_rs3_full,
            risk_metrics=all_risk_metrics,
            correlation=correlation_results,
            track_b=all_track_b_results,
            track_c=track_c_results,
            gap_report=gap_report,
            fp_result=fp_result,
            sched_diags=sched_diags,
        )

    log.info("=== Phase 3 complete. Artifacts: %s ===", ARTIFACT_DIR)


if __name__ == "__main__":
    main()
