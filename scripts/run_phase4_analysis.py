#!/usr/bin/env python3
# scripts/run_phase4_analysis.py
"""Phase 4 Capital Utilisation Optimisation — v0.1.0.

Entry point for R8 Phase 4 analysis per research/r8_phase4_spec.md v0.1.1 (LOCKED).

Tracks:
    A — Holding Period Study (5td / 10td / 15td vs 20td baseline)
    B — Signal Prioritisation (RS-rank, RS-60d-rank, uplift-proxy vs FIFO)
    C — NOT IMPLEMENTED (raises NotImplementedError)

Governance invariants:
    - Panel loaded via load_panel() — identical CTE to Phase 1/2B/3.
    - Forward returns via compute_forward_returns(horizons=[5,10,15,20]).
    - P3-FP-001 fingerprint re-verified: full-sample 20td net_s1 = +1.64% ± 1bp.
      Fingerprint checks gross_mean / net_s1 / mean_deployed / n_dates,
      NOT Sharpe (per Phase 4 review finding MAJOR-5).
    - build_signal_ledger_for_horizon(h): calculates exit_date = pos+h,
      not pos+20. This correctly changes both NAV path and capital release
      schedule. (Blocker 1 + 2 fix.)
    - schedule_positions used unchanged from Phase 3; exit_date in ledger
      drives capital release naturally (no holding_days_override needed).
    - Bootstrap uses two-sample stationary block bootstrap: both treatment
      and baseline resampled jointly. (Blocker 4 fix.)
    - Block length: L = max(5, h) per SPEC §5.3 (frozen).
    - Track C raises NotImplementedError — stub results prohibited.
      (Blocker 3 fix.)
    - Track B admission rate invariant: deviation from FIFO admission rate
      must be < 5% or is explicitly logged. (MAJOR-6 fix.)
    - Score-rank replaced by RS-60d-rank: bullish_features.score absent
      (confirmed 2026-06-07; SPEC §6.2 fallback applied).
    - dist_above_ma20_atr is labelled 'uplift_proxy', not 'momentum strength'.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Repo root and imports
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
from scripts.run_phase3_analysis import (  # noqa: E402
    COMMISSION_RT,
    SLIPPAGE,
    DataGapReport,
    FingerprintResult,
    ScheduledPosition,
    compute_risk_metrics,
    load_daily_price_paths,
    reconstruct_nav,
    validate_schema_and_document_gaps,
)

# ---------------------------------------------------------------------------
# Frozen constants
# ---------------------------------------------------------------------------

DB_PATH: Final[Path] = _REPO_ROOT / "data/_storage/helios.duckdb"
ARTIFACT_DIR: Final[Path] = _REPO_ROOT / "data/_storage/r8_phase4/v0.1.0"
SCRIPT_VERSION: Final[str] = "0.1.0"
SPEC_VERSION: Final[str] = "0.1.1"

P3_FINGERPRINT_NET_S1: Final[float] = 0.0164
P3_FINGERPRINT_TOLERANCE: Final[float] = 0.0001

PANEL_START: Final[date] = date(2022, 3, 22)
PANEL_END: Final[date] = date(2026, 6, 4)

SEGMENT_DATES: Final[dict[str, tuple[date, date]]] = {
    "seg1": (date(2022, 3, 22),  date(2023, 10, 20)),
    "seg2": (date(2023, 10, 24), date(2024, 7, 9)),
    "seg3": (date(2024, 7, 10),  date(2025, 8, 8)),
    "seg4": (date(2025, 8, 11),  date(2026, 6, 4)),
}

SCENARIO_POOLS: Final[dict[str, list[str]]] = {
    "full_sample": ["seg1", "seg2", "seg3", "seg4"],
    "low_uplift":  ["seg2", "seg3"],
}

TARGET_REGIME: Final[str] = "bull"
TARGET_NLU: Final[int] = 0
BASELINE_CAP: Final[float] = 0.10
BASELINE_MAX_POS: Final[int] = 10

# D1 — four horizons (frozen per SPEC §3)
HORIZONS: Final[list[int]] = [5, 10, 15, 20]

# Track B ranking variants
# Score-rank → RS-60d-rank (SPEC §6.2 fallback; score absent from bullish_features)
RANKING_VARIANTS: Final[dict[str, str | None]] = {
    "fifo":         None,
    "rs_20d":       "beta_adj_rs_20d",
    "rs_60d":       "beta_adj_rs_60d",
    "uplift_proxy": "dist_above_ma20_atr",
}

BOOTSTRAP_B: Final[int] = 5_000

TRADING_DAYS_PER_YEAR: Final[int] = 252

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
# Bootstrap block length — SPEC §5.3 frozen formula
# ---------------------------------------------------------------------------

def bootstrap_block_length(h: int) -> int:
    """Return block length for stationary bootstrap at horizon h.

    Formula frozen per Phase 4 SPEC §5.3: L = max(5, h).
    Must not be modified without a SPEC amendment.
    """
    return max(5, h)


# ---------------------------------------------------------------------------
# 1. Forward return matrix (D1 — four horizons)
# ---------------------------------------------------------------------------

def build_forward_return_matrix(
    panel: pd.DataFrame,
    prices: pd.DataFrame,
) -> pd.DataFrame:
    """Compute forward returns at all four horizons for all panel rows.

    Formula (frozen, extends Phase 1): fwd_return[T+h] = adj_close[T+h] /
    adj_open[T+1] - 1, for h ∈ {5, 10, 15, 20}. Entry price adj_open[T+1]
    unchanged from Phase 1.

    Returns panel with added columns fwd_5td, fwd_10td, fwd_15td, fwd_20td.
    """
    panel = compute_forward_returns(panel, prices, horizons=HORIZONS)
    valid_counts = {f"fwd_{h}td": int(panel[f"fwd_{h}td"].notna().sum())
                    for h in HORIZONS}
    log.info("Forward return matrix valid counts: %s", valid_counts)
    return panel


# ---------------------------------------------------------------------------
# 2. Signal ledger for arbitrary horizon h (Blocker 1 + 2 fix)
# ---------------------------------------------------------------------------

def build_signal_ledger_for_horizon(
    panel: pd.DataFrame,
    prices: pd.DataFrame,
    pool: str,
    scenario: str,
    h: int,
    con: duckdb.DuckDBPyConnection | None = None,
) -> pd.DataFrame:
    """Build canonical signal ledger for one pool × scenario × horizon.

    Critical difference from Phase 3 build_signal_ledger:
        exit_date = trading_calendar[pos + h]  (NOT pos + 20)

    This means both the NAV reconstruction path AND the capital release
    schedule use the correct horizon-specific exit date. The Phase 3
    build_signal_ledger hardcodes exit_date = pos + HOLDING_DAYS (= 20);
    using it for h=5/10/15 would give incorrect capital release timing
    and wrong admission rates. (Blockers 1 + 2.)

    Args:
        panel:    Full panel from load_panel() with fwd_{h}td attached.
        prices:   Price series from load_price_series().
        pool:     "treatment_1" or "baseline_1".
        scenario: "full_sample" or "low_uplift".
        h:        Holding period in trading days.

    Returns:
        DataFrame with columns: stock_id, signal_date, entry_date, exit_date,
        fwd_return_h (the h-day forward return), valid_path (bool), segment.
    """
    fwd_col = f"fwd_{h}td"

    # Target cell + scenario filter
    cell = panel[
        (panel["regime"] == TARGET_REGIME)
        & (panel["near_limit_up"] == TARGET_NLU)
        & (panel["universe"] == pool)
    ].copy()

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

    # Trading calendar unified as pd.Timestamp
    all_dates_ts = pd.DatetimeIndex(
        sorted(pd.to_datetime(prices.index.get_level_values("date").unique()))
    )
    date_to_pos: dict[pd.Timestamp, int] = {d: i for i, d in enumerate(all_dates_ts)}

    adj_open_map:  dict = {
        (s, pd.Timestamp(d)): v
        for (s, d), v in prices["adj_open"].to_dict().items()
    }
    adj_close_map: dict = {
        (s, pd.Timestamp(d)): v
        for (s, d), v in prices["adj_close"].to_dict().items()
    }

    def _segment(ts: pd.Timestamp) -> str:
        d = ts.date()
        for seg, (s, e) in SEGMENT_DATES.items():
            if s <= d <= e:
                return seg
        return "unknown"

    # --- Ranking columns for Track B ---
    # load_panel() final SELECT only includes: stock_id, date, regime,
    # near_limit_up, universe. bullish_features feature columns are used
    # in the CTE to compute r8_flag/rs_tertile but are NOT carried into the
    # final output. We must join them directly from bullish_features here.
    #
    # Confirmed 2026-06-07: load_panel() CTE does not expose feature columns.
    RANK_COLS = ["beta_adj_rs_20d", "beta_adj_rs_60d", "dist_above_ma20_atr"]

    rank_df: pd.DataFrame | None = None
    if prices is not None and hasattr(prices, 'index'):
        # `prices` is from load_price_series() — not useful for feature join.
        # We need a DuckDB connection. Pass `con` as optional parameter.
        pass

    # Check if ranking columns already in cell (would mean panel was enriched)
    missing_rank_cols = [c for c in RANK_COLS if c not in cell.columns]
    if missing_rank_cols:
        log.info(
            "build_signal_ledger_for_horizon: ranking columns %s not in panel "
            "(expected — load_panel() CTE does not expose bullish_features). "
            "Pass con=... parameter to enable Track B ranking join.",
            missing_rank_cols,
        )
    else:
        for col in RANK_COLS:
            pct = 100.0 * cell[col].notna().sum() / max(len(cell), 1)
            if pct < 60.0:
                log.warning(
                    "build_signal_ledger_for_horizon: %s non-null=%.1f%% "
                    "(<60%%) in %s/%s.",
                    col, pct, pool, scenario,
                )

    records = []
    for _, row in cell.iterrows():
        sig_ts = pd.Timestamp(row["date"])
        stock  = row["stock_id"]
        fwd    = row.get(fwd_col, np.nan)

        pos = date_to_pos.get(sig_ts)
        if pos is None or pos + h >= len(all_dates_ts):
            valid      = False
            entry_date = exit_date = None
        else:
            entry_ts = all_dates_ts[pos + 1]
            exit_ts  = all_dates_ts[pos + h]       # ← horizon-specific exit
            entry_px = adj_open_map.get((stock, entry_ts))
            exit_px  = adj_close_map.get((stock, exit_ts))
            valid = (
                not pd.isna(fwd)
                and entry_px is not None and entry_px > 0
                and exit_px  is not None and exit_px  > 0
            )
            entry_date = entry_ts
            exit_date  = exit_ts

        record = {
            "stock_id":        stock,
            "signal_date":     sig_ts,
            "entry_date":      entry_date,
            "exit_date":       exit_date,
            "fwd_return_20td": fwd if not pd.isna(fwd) else np.nan,
            "fwd_return_h":    fwd if not pd.isna(fwd) else np.nan,
            "holding_days":    h,
            "valid_path":      valid,
            "segment":         _segment(sig_ts),
        }
        # Attach ranking columns — will be NaN if not in cell (see bulk join below)
        for col in RANK_COLS:
            record[col] = row.get(col, np.nan)

        records.append(record)

    ledger = pd.DataFrame(records)

    # --- Bulk join ranking columns from bullish_features if con provided ---
    # load_panel() does not expose bullish_features feature columns.
    # Track B requires a direct DuckDB join. Pass con=<connection> to enable.
    if con is not None:
        missing = [c for c in RANK_COLS if ledger[c].isna().all()]
        if missing:
            log.info(
                "build_signal_ledger_for_horizon: joining %s from "
                "bullish_features (con provided, %d rows)",
                missing, len(ledger),
            )
            stock_ids = ledger["stock_id"].unique().tolist()
            min_date  = ledger["signal_date"].min().date()
            max_date  = ledger["signal_date"].max().date()
            ids_sql   = ", ".join(f"'{s}'" for s in stock_ids)
            cols_sql  = ", ".join(missing)
            bf_df = con.execute(f"""
                SELECT stock_id,
                       CAST(date AS DATE) AS signal_date,
                       {cols_sql}
                FROM bullish_features
                WHERE stock_id IN ({ids_sql})
                  AND date BETWEEN '{min_date}' AND '{max_date}'
            """).fetchdf()
            bf_df["signal_date"] = pd.to_datetime(bf_df["signal_date"])

            # Drop existing all-NaN rank cols before merge to avoid _x/_y suffix
            ledger = ledger.drop(columns=missing, errors="ignore")
            ledger = ledger.merge(bf_df, on=["stock_id", "signal_date"], how="left")

            for col in missing:
                if col in ledger.columns:
                    pct = 100.0 * ledger[col].notna().sum() / max(len(ledger), 1)
                    log.info(
                        "Post-join %s: %.1f%% non-null (%d/%d rows)",
                        col, pct, int(ledger[col].notna().sum()), len(ledger),
                    )
                    if pct < 60.0:
                        log.warning(
                            "%s non-null=%.1f%% (<60%%). "
                            "Track B ranking for this column may be unreliable.",
                            col, pct,
                        )
    elif any(col in ledger.columns and ledger[col].isna().all() for col in RANK_COLS):
        log.warning(
            "build_signal_ledger_for_horizon: ranking columns all-NaN and "
            "con=None — Track B will fall back to FIFO. "
            "Pass con=<DuckDBPyConnection> to enable ranking.",
        )

    n_valid   = ledger["valid_path"].sum()
    n_invalid = (~ledger["valid_path"]).sum()
    log.info(
        "Ledger [h=%dtd pool=%s scenario=%s]: total=%d valid=%d invalid=%d",
        h, pool, scenario, len(ledger), n_valid, n_invalid,
    )
    return ledger


# ---------------------------------------------------------------------------
# 3. Capital scheduler (reused from Phase 3, no modification needed)
# ---------------------------------------------------------------------------

def schedule_positions(
    ledger: pd.DataFrame,
    cap: float,
    max_pos: int,
) -> tuple[list[ScheduledPosition], dict]:
    """Admit positions from ledger subject to capital constraint.

    Identical logic to Phase 3 schedule_positions. Works correctly for any
    horizon because exit_date in the ledger already reflects the correct
    horizon (set by build_signal_ledger_for_horizon). Capital is released
    when exit_date <= current signal_date, so shorter horizons naturally
    release capital earlier, improving admission rates.

    Rules (frozen per Phase 3 design decision 2026-06-07):
        1. Process signal_dates ascending; within date, sort by stock_id.
        2. Release positions whose exit_date <= current signal_date.
        3. Admit if len(open) < max_pos AND current_exposure + cap <= 100%.
        4. Skip otherwise (skipped_capital_constraint).
        5. No re-entry for a stock already in an open position.
    """
    # Sort order respects rank_order if present (stamped by _rank_ledger for
    # Track B quality variants). Without rank_order, falls back to FIFO order.
    # This ensures the scheduler admits candidates in the intended priority
    # sequence rather than overriding it with a stock_id sort.
    sort_cols = (
        ["signal_date", "rank_order", "stock_id"]
        if "rank_order" in ledger.columns
        else ["signal_date", "stock_id"]
    )
    valid = (
        ledger[ledger["valid_path"]]
        .sort_values(sort_cols)
        .reset_index(drop=True)
    )

    if valid.empty:
        raise ValueError(
            f"schedule_positions: no valid_path rows in ledger "
            f"(total={len(ledger)})."
        )

    open_positions: dict[str, tuple[pd.Timestamp, float]] = {}
    scheduled: list[ScheduledPosition] = []
    n_skipped_capital = 0
    n_skipped_duplicate = 0

    for sig_date in sorted(valid["signal_date"].unique()):
        sig_ts = pd.Timestamp(sig_date)

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

    # P3-FP-002 exposure invariant
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
                f"P3-FP-002 FAIL: max_daily_exposure={max_exp:.4f} > 100%."
            )
    else:
        max_exp = 0.0

    n_cand = len(valid)
    log.info(
        "P3-FP-002 PASS: max_exposure=%.1f%% | scheduled=%d/%d "
        "skipped_capital=%d skipped_duplicate=%d",
        max_exp * 100, len(scheduled), n_cand,
        n_skipped_capital, n_skipped_duplicate,
    )

    diag = {
        "n_candidates":        n_cand,
        "n_scheduled":         len(scheduled),
        "n_skipped_capital":   n_skipped_capital,
        "n_skipped_duplicate": n_skipped_duplicate,
        "admission_rate":      round(len(scheduled) / max(n_cand, 1), 4),
        "max_daily_exposure":  round(max_exp, 4),
        "fp002_passed":        True,
    }
    return scheduled, diag


# ---------------------------------------------------------------------------
# 4. NAV reconstruction for arbitrary horizon h
# ---------------------------------------------------------------------------

def reconstruct_nav_for_horizon(
    scheduled: list[ScheduledPosition],
    price_df: pd.DataFrame,
    cap: float,
    h: int,
) -> pd.DataFrame:
    """Reconstruct calendar-time MTM NAV for holding period h.

    D1A implementation: entry basis adj_open[T+1]; holding window T+1..T+h;
    daily log return derived from NAV path. Identical to Phase 3
    reconstruct_nav but loop bound = h (not 20).

    For h=20, delegates to Phase 3 reconstruct_nav (no behavioural change).
    """
    if h == 20:
        return reconstruct_nav(scheduled, price_df, cap)

    if not scheduled:
        raise ValueError("reconstruct_nav_for_horizon: empty scheduled list.")

    _keys     = list(zip(price_df["stock_id"], price_df["date"]))
    close_map = dict(zip(_keys, price_df["adj_close"]))
    open_map  = dict(zip(_keys, price_df["adj_open"]))

    all_dates_ts   = pd.DatetimeIndex(sorted(price_df["date"].unique()))
    panel_start_ts = pd.Timestamp(PANEL_START)
    cal            = all_dates_ts[all_dates_ts >= panel_start_ts]
    date_to_pos    = {d: i for i, d in enumerate(cal)}

    port_simple_ret = np.zeros(len(cal), dtype=float)

    for pos in scheduled:
        entry_pos = date_to_pos.get(pos.entry_date)
        if entry_pos is None:
            log.warning(
                "reconstruct_nav_for_horizon: entry_date %s not in calendar "
                "for %s — skipped", pos.entry_date, pos.stock_id,
            )
            continue

        for k in range(h):           # k=0 → T+1 (entry day), k=h-1 → T+h
            tk_pos = entry_pos + k
            if tk_pos >= len(cal):
                break
            t_k  = cal[tk_pos]
            t_k1 = cal[tk_pos - 1] if tk_pos > 0 else None

            close_k = close_map.get((pos.stock_id, t_k))
            if close_k is None or close_k <= 0:
                continue

            if k == 0:
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

    nav = np.empty(len(cal), dtype=float)
    nav[0] = 1.0
    for i in range(1, len(cal)):
        nav[i] = nav[i - 1] * (1.0 + port_simple_ret[i])
        if nav[i] <= 0:
            raise RuntimeError(
                f"NAV non-positive at {cal[i].date()} (h={h}td, "
                f"nav={nav[i]:.6f}, ret={port_simple_ret[i]:.6f})."
            )

    log_ret = np.empty(len(cal), dtype=float)
    log_ret[0] = 0.0
    log_ret[1:] = np.log(nav[1:] / nav[:-1])

    # Holding period invariant: verify NAV contributions cover approximately
    # h days per position. A large shortfall indicates data gaps or an
    # off-by-one in loop bounds.
    # Note: coverage_pct will naturally be low (~10-15%) because multiple
    # positions overlap in calendar time, so total non-zero slots <<
    # n_positions × h. The 50% threshold is intentionally conservative —
    # it catches genuine zero-coverage failures (e.g., price lookup miss),
    # not the expected multi-position overlap compression.
    n_positions = len(scheduled)
    if n_positions > 0:
        total_nonzero = int(np.count_nonzero(port_simple_ret))
        # Expected lower bound: at minimum each position should contribute
        # at least 1 non-zero day (not zero for all h days).
        # Use n_positions as the lower bound, not n_positions * h.
        coverage_pct = 100.0 * total_nonzero / max(n_positions, 1)
        if coverage_pct < 50.0:
            log.warning(
                "reconstruct_nav_for_horizon: h=%d coverage=%.1f%% "
                "(non-zero days=%d, n_positions=%d). "
                "Some positions may have zero price coverage. "
                "Inspect price availability for scheduled positions.",
                h, coverage_pct, total_nonzero, n_positions,
            )
        else:
            log.info(
                "reconstruct_nav_for_horizon: h=%d coverage=%.1f%% ✓",
                h, coverage_pct,
            )

    return pd.DataFrame({
        "date":             cal,
        "nav":              nav,
        "daily_log_return": log_ret,
    })


# ---------------------------------------------------------------------------
# 5. Fingerprint verification (MAJOR-5 fix: checks net_s1 not Sharpe)
# ---------------------------------------------------------------------------

def verify_p3_fingerprint(
    panel: pd.DataFrame,
    prices: pd.DataFrame,
    con: duckdb.DuckDBPyConnection | None = None,
) -> FingerprintResult:
    """P3-FP-001: verify 20td full-sample candidate pool lineage.

    Replicates Phase 2B simulate_portfolio() using fwd_20td, baseline cap,
    first_10 overflow. Checks gross_mean, net_s1, mean_deployed_weight,
    n_signal_dates — NOT Sharpe (Sharpe is not a frozen fingerprint value).

    Aborts with sys.exit(1) if net_s1 deviates > 1 bp from +1.64%.
    """
    cap, max_pos = BASELINE_CAP, BASELINE_MAX_POS
    ledger = build_signal_ledger_for_horizon(
        panel, prices, "treatment_1", "full_sample", h=20, con=con
    )
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

    passed = abs(net_s1 - P3_FINGERPRINT_NET_S1) <= P3_FINGERPRINT_TOLERANCE
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
            net_s1 * 100, P3_FINGERPRINT_NET_S1 * 100,
            P3_FINGERPRINT_TOLERANCE * 10_000,
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
# 6. Track A — Holding period study
# ---------------------------------------------------------------------------

@dataclass
class HorizonResult:
    horizon: int
    scenario: str
    n_candidates: int
    n_scheduled: int
    admission_rate: float
    risk_metrics_r8: dict
    risk_metrics_rs_t3: dict
    bootstrap_delta: dict


def run_track_a(
    panel: pd.DataFrame,
    prices: pd.DataFrame,
    con: duckdb.DuckDBPyConnection,
) -> list[HorizonResult]:
    """Run holding period study for h ∈ {5, 10, 15, 20}.

    For each horizon h and scenario (full_sample, low_uplift):
        1. Build signal ledger with exit_date = pos+h (Blocker 1+2 fix).
        2. Schedule positions — capital released at pos+h, not pos+20.
        3. Reconstruct MTM NAV over k=0..h-1 holding days.
        4. Compute Phase 3 Track A risk metrics.
        5. Compute two-sample bootstrap Δ_A3[h].

    Admission rate for h < 20 is expected to be higher than Phase 3 baseline
    (16.3%) because positions release capital sooner. If h=20 deviates from
    Phase 3 admission rate (16.3%) by more than 1pp, logged as WARNING.
    """
    results = []

    for h in HORIZONS:
        for scenario in ("full_sample", "low_uplift"):
            log.info("--- Track A: h=%dtd scenario=%s ---", h, scenario)

            ledger_t = build_signal_ledger_for_horizon(
                panel, prices, "treatment_1", scenario, h, con=con
            )
            ledger_b = build_signal_ledger_for_horizon(
                panel, prices, "baseline_1", scenario, h, con=con
            )

            sched_t, diag_t = schedule_positions(ledger_t, BASELINE_CAP, BASELINE_MAX_POS)
            sched_b, diag_b = schedule_positions(ledger_b, BASELINE_CAP, BASELINE_MAX_POS)

            price_t = load_daily_price_paths(con, sched_t)
            price_b = load_daily_price_paths(con, sched_b)

            nav_t = reconstruct_nav_for_horizon(sched_t, price_t, BASELINE_CAP, h)
            nav_b = reconstruct_nav_for_horizon(sched_b, price_b, BASELINE_CAP, h)

            metrics_t = compute_risk_metrics(nav_t, f"r8_h{h}_{scenario}")
            metrics_b = compute_risk_metrics(nav_b, f"rs_t3_h{h}_{scenario}")

            # Lineage check: h=20 full_sample admission rate vs Phase 3 (16.3%)
            if h == 20 and scenario == "full_sample":
                p3_admission = 0.163
                delta = abs(diag_t["admission_rate"] - p3_admission)
                if delta > 0.01:
                    log.warning(
                        "Track A lineage check: h=20 full_sample admission "
                        "rate = %.3f (Phase 3 = %.3f, deviation %.3f > 0.01). "
                        "Panel may have changed.",
                        diag_t["admission_rate"], p3_admission, delta,
                    )
                else:
                    log.info(
                        "Track A lineage check: h=20 full_sample admission "
                        "rate = %.3f ✓", diag_t["admission_rate"],
                    )

            # Two-sample bootstrap Δ_A3[h] (Blocker 4 fix)
            delta = _bootstrap_delta_a3_two_sample(ledger_t, ledger_b, h)

            results.append(HorizonResult(
                horizon=h,
                scenario=scenario,
                n_candidates=diag_t["n_candidates"],
                n_scheduled=diag_t["n_scheduled"],
                admission_rate=diag_t["admission_rate"],
                risk_metrics_r8=metrics_t,
                risk_metrics_rs_t3=metrics_b,
                bootstrap_delta=delta,
            ))

    return results


def _bootstrap_delta_a3_two_sample(
    ledger_t: pd.DataFrame,
    ledger_b: pd.DataFrame,
    h: int,
) -> dict:
    """Two-sample stationary block bootstrap for Δ_A3[h].

    Both treatment AND baseline are resampled independently (Blocker 4 fix).
    Previous version only resampled treatment; this produced artificially
    narrow CIs.

    CI = percentile(bootstrap Δ* distribution, [2.5%, 97.5%]).
    Block length: L = max(5, h) per SPEC §5.3 (frozen).
    """
    from arch.bootstrap import StationaryBootstrap

    treat_vals = (
        ledger_t[ledger_t["valid_path"]]["fwd_return_20td"].dropna().values
    )
    base_vals  = (
        ledger_b[ledger_b["valid_path"]]["fwd_return_20td"].dropna().values
    )

    if len(treat_vals) < 20 or len(base_vals) < 20:
        log.warning(
            "Insufficient obs for bootstrap h=%d (treat=%d base=%d) — NaN",
            h, len(treat_vals), len(base_vals),
        )
        return {
            "h": h, "delta_obs": np.nan, "ci_lo": np.nan, "ci_hi": np.nan,
            "n_treat": len(treat_vals), "n_base": len(base_vals),
            "B": BOOTSTRAP_B, "block_length": bootstrap_block_length(h),
            "method": "two_sample_stationary_block",
        }

    L = bootstrap_block_length(h)
    delta_obs = float(np.mean(treat_vals) - np.mean(base_vals))

    bs_treat = StationaryBootstrap(L, treat_vals)
    bs_base  = StationaryBootstrap(L, base_vals)

    rng = np.random.default_rng(42)
    deltas = []
    for (t_data, _), (b_data, _) in zip(
        bs_treat.bootstrap(BOOTSTRAP_B),
        bs_base.bootstrap(BOOTSTRAP_B),
    ):
        deltas.append(float(np.mean(t_data[0]) - np.mean(b_data[0])))

    ci_lo = float(np.percentile(deltas, 2.5))
    ci_hi = float(np.percentile(deltas, 97.5))

    log.info(
        "Bootstrap Δ_A3[%dtd]: obs=+%.4f%% CI=[%.4f%%, %.4f%%] L=%d B=%d",
        h, delta_obs * 100, ci_lo * 100, ci_hi * 100, L, BOOTSTRAP_B,
    )
    return {
        "h": h, "delta_obs": delta_obs, "ci_lo": ci_lo, "ci_hi": ci_hi,
        "n_treat": len(treat_vals), "n_base": len(base_vals),
        "B": BOOTSTRAP_B, "block_length": L,
        "method": "two_sample_stationary_block",
    }


# ---------------------------------------------------------------------------
# 7. Track B — Signal prioritisation
# ---------------------------------------------------------------------------

def run_track_b(
    panel: pd.DataFrame,
    prices: pd.DataFrame,
    con: duckdb.DuckDBPyConnection,
) -> list[dict]:
    """Run signal prioritisation variants for full_sample and low_uplift.

    Uses 20td holding period throughout (baseline). Ranking affects which
    positions are admitted; capital constraint is unchanged.

    Admission rate invariant (MAJOR-6 fix): for each quality-ranked variant,
    if |admission_rate_variant - admission_rate_fifo| >= 0.05, log WARNING.
    A deviation < 5pp is expected due to duplicate-symbol filtering order
    effects; > 5pp indicates an unexpected scheduling artefact.

    Score-rank replaced by RS-60d-rank per SPEC §6.2 fallback.
    dist_above_ma20_atr labelled 'uplift_proxy' (extension metric, not
    momentum strength).
    """
    results = []
    fifo_admission: dict[str, float] = {}   # scenario → FIFO admission rate

    for scenario in ("full_sample", "low_uplift"):
        log.info("--- Track B: scenario=%s ---", scenario)

        # Base ledger (20td, no ranking) — built once per scenario
        base_ledger = build_signal_ledger_for_horizon(
            panel, prices, "treatment_1", scenario, h=20, con=con
        )

        for variant_name, rank_col in RANKING_VARIANTS.items():
            log.info("Track B: variant=%s scenario=%s", variant_name, scenario)

            ranked = _rank_ledger(base_ledger, rank_col, variant_name)
            sched, diag = schedule_positions(
                ranked, BASELINE_CAP, BASELINE_MAX_POS
            )

            # Admission rate invariant check
            if variant_name == "fifo":
                fifo_admission[scenario] = diag["admission_rate"]
            else:
                fifo_rate = fifo_admission.get(scenario)
                if fifo_rate is not None:
                    delta = abs(diag["admission_rate"] - fifo_rate)
                    if delta >= 0.05:
                        log.warning(
                            "Track B admission invariant: variant=%s scenario=%s "
                            "admission_rate=%.3f FIFO=%.3f delta=%.3f >= 0.05. "
                            "Unexpected scheduling effect.",
                            variant_name, scenario,
                            diag["admission_rate"], fifo_rate, delta,
                        )
                    else:
                        log.info(
                            "Track B admission invariant OK: variant=%s "
                            "delta=%.3f < 0.05", variant_name, delta,
                        )

            price_df = load_daily_price_paths(con, sched)
            nav_df   = reconstruct_nav(sched, price_df, BASELINE_CAP)
            metrics  = compute_risk_metrics(
                nav_df, f"track_b_{variant_name}_{scenario}"
            )

            results.append({
                "variant":            variant_name,
                "rank_column":        rank_col,
                "scenario":           scenario,
                "n_candidates":       diag["n_candidates"],
                "n_scheduled":        diag["n_scheduled"],
                "admission_rate":     diag["admission_rate"],
                "max_daily_exposure": diag["max_daily_exposure"],
                "sensitivity_label":  "SENSITIVITY — ZERO PRICE IMPACT ASSUMPTION",
                **metrics,
            })

    # Track B exercised invariant: verify at least one quality variant
    # produced different Sharpe from FIFO (proxy for effective ranking).
    # Identical Sharpes indicate ranking columns were not applied.
    for scenario_check in ("full_sample", "low_uplift"):
        fifo_rows    = [r for r in results
                        if r["variant"] == "fifo" and r["scenario"] == scenario_check]
        non_fifo_rows = [r for r in results
                         if r["variant"] != "fifo"
                         and r["scenario"] == scenario_check]
        if not fifo_rows or not non_fifo_rows:
            continue
        fifo_sharpe = fifo_rows[0].get("sharpe")
        all_sharpe_same = all(
            abs((r.get("sharpe") or 0.0) - (fifo_sharpe or 0.0)) < 0.001
            for r in non_fifo_rows
        )
        if all_sharpe_same and fifo_sharpe is not None:
            log.error(
                "Track B exercised invariant FAIL: scenario=%s — all quality "
                "variants produced identical Sharpe as FIFO (%.4f). "
                "Ranking columns may not have been applied correctly. "
                "Inspect rank_col non-null coverage in ledger.",
                scenario_check, fifo_sharpe,
            )
        else:
            log.info(
                "Track B exercised invariant OK: scenario=%s — at least one "
                "quality variant differs from FIFO.", scenario_check,
            )

    return results


def _rank_ledger(
    ledger: pd.DataFrame,
    rank_col: str | None,
    variant_name: str,
) -> pd.DataFrame:
    """Sort candidates within each signal_date by rank_col descending.

    FIFO (rank_col=None): (signal_date ASC, stock_id ASC) — Phase 3 order.
    Quality variants: within each signal_date, sort by rank_col DESC
    (higher = better), ties broken by stock_id ASC.
    NaN rank values go to end (na_position='last').

    A `rank_order` column is stamped (0-indexed within each signal_date)
    so the scheduler can sort by (signal_date, rank_order, stock_id) and
    preserve the intended admission priority order. Without rank_order,
    the scheduler's internal sort_values would override this ranking.
    """
    if rank_col is None:
        ranked = ledger.sort_values(
            ["signal_date", "stock_id"]
        ).reset_index(drop=True)
    elif rank_col not in ledger.columns:
        log.warning(
            "_rank_ledger: %r not in ledger for variant=%s — falling back to FIFO",
            rank_col, variant_name,
        )
        ranked = ledger.sort_values(
            ["signal_date", "stock_id"]
        ).reset_index(drop=True)
    else:
        ranked = (
            ledger
            .sort_values(
                ["signal_date", rank_col, "stock_id"],
                ascending=[True, False, True],
                na_position="last",
            )
            .reset_index(drop=True)
        )

    # Stamp rank_order: 0-indexed position within each signal_date group.
    # Scheduler uses this to preserve quality ranking during admission.
    ranked["rank_order"] = ranked.groupby("signal_date").cumcount()
    return ranked


# ---------------------------------------------------------------------------
# 8. Track C — NOT IMPLEMENTED (Blocker 3 fix)
# ---------------------------------------------------------------------------

def run_track_c(*args, **kwargs) -> None:
    """Track C early exit rules — not yet implemented.

    Raises NotImplementedError to prevent silent stub results.

    Full implementation requires:
        1. ATR-trailing: compare daily drawdown vs entry-day ATR × multiplier.
        2. MA20-failure: 3 consecutive closes below daily_features.sma_20.
        3. RS-deterioration: beta_adj_rs_20d < 0 assessed every 5td from
           bullish_features, with capital re-release on trigger day + 1.

    All three rules require path-dependent feature evaluation within the
    holding window. This is the most technically complex track and must be
    implemented separately after Track A and B are validated.

    Do NOT stub with 20td NAV results — this would produce artifacts that
    appear complete but reflect the baseline rather than the exit rules.
    """
    raise NotImplementedError(
        "Track C (early exit rules) is not implemented in v0.1.0. "
        "Implement after Track A and B are validated. "
        "See run_phase4_analysis.py docstring for requirements."
    )


# ---------------------------------------------------------------------------
# 9. Artifact writer
# ---------------------------------------------------------------------------

def write_artifacts(
    panel: pd.DataFrame,
    track_a: list[HorizonResult],
    track_b: list[dict],
    gap_report: DataGapReport,
    fp_result: FingerprintResult,
) -> None:
    """Write Phase 4 Track A and B artifacts to data/_storage/r8_phase4/v0.1.0/."""
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    # Forward return matrix
    fwd_cols = (
        ["stock_id", "date", "universe", "regime", "near_limit_up"]
        + [f"fwd_{h}td" for h in HORIZONS if f"fwd_{h}td" in panel.columns]
    )
    panel[fwd_cols].to_parquet(
        ARTIFACT_DIR / "forward_return_matrix.parquet", index=False
    )
    log.info("Wrote forward_return_matrix.parquet (%d rows)", len(panel))

    # Track A
    track_a_rows = []
    bootstrap_rows = []
    for r in track_a:
        row = {
            "horizon":         r.horizon,
            "scenario":        r.scenario,
            "n_candidates":    r.n_candidates,
            "n_scheduled":     r.n_scheduled,
            "admission_rate":  r.admission_rate,
        }
        for k, v in r.risk_metrics_r8.items():
            row[f"r8_{k}"] = v
        for k, v in r.risk_metrics_rs_t3.items():
            row[f"rs_t3_{k}"] = v
        track_a_rows.append(row)
        bootstrap_rows.append(r.bootstrap_delta)

    pd.DataFrame(track_a_rows).to_parquet(
        ARTIFACT_DIR / "p4a_holding_period.parquet", index=False
    )
    pd.DataFrame(bootstrap_rows).to_parquet(
        ARTIFACT_DIR / "p4a_bootstrap.parquet", index=False
    )
    log.info(
        "Wrote p4a_holding_period.parquet (%d rows) + p4a_bootstrap.parquet",
        len(track_a_rows),
    )

    # Track B
    pd.DataFrame(track_b).to_parquet(
        ARTIFACT_DIR / "p4b_prioritisation.parquet", index=False
    )
    log.info("Wrote p4b_prioritisation.parquet (%d rows)", len(track_b))

    # Manifest
    manifest = {
        "script_version":    SCRIPT_VERSION,
        "spec_version":      SPEC_VERSION,
        "generated_at":      pd.Timestamp.now(tz="Asia/Taipei").isoformat(),
        "db_path":           str(DB_PATH),
        "artifact_dir":      str(ARTIFACT_DIR),
        "panel_source":      "load_panel() from run_r8_phase1_a3 — identical CTE",
        "fwd_return_source": "compute_forward_returns(horizons=[5,10,15,20])",
        "track_c_status":    "NOT IMPLEMENTED in v0.1.0 — raises NotImplementedError",
        "data_gaps": {
            "missing_tables": gap_report.missing_tables,
            "empty_tables":   gap_report.empty_tables,
            "coverage_gaps":  gap_report.coverage_gaps,
        },
        "track_b_notes": {
            "score_rank_fallback": (
                "Score-rank replaced by RS-60d-rank: bullish_features.score "
                "absent (confirmed 2026-06-07). SPEC §6.2 fallback applied."
            ),
            "uplift_proxy_note": (
                "dist_above_ma20_atr is an extension metric (price above MA20 "
                "normalised by ATR), not a direct momentum strength measure."
            ),
        },
        "governance": {
            "fingerprint_check":  "P3-FP-001: net_s1 = +1.64% ± 1bp (not Sharpe)",
            "bootstrap_formula":  "two_sample_stationary_block, L=max(5,h), B=5000",
            "bootstrap_note":     (
                "Both treatment and baseline resampled independently via "
                "separate StationaryBootstrap instances with the same L. "
                "The two streams are not co-seeded — standard independent "
                "bootstrap, not a paired bootstrap. CI reflects estimation "
                "uncertainty of both sample means."
            ),
            "exit_date_formula":  "exit_date = trading_calendar[pos + h] (not pos+20)",
            "nav_source":         "D1A: daily simple PnL from daily_price_adj.adj_close",
            "return_convention":  "daily_log_return derived from NAV path (§5.2)",
            "capital_scheduler":  "Interpretation B: shared pool, exposure <= 100%",
        },
        "p3_fp_001": {
            "gross_mean":           fp_result.gross_mean,
            "net_s1":               fp_result.net_s1,
            "mean_deployed_weight": fp_result.mean_deployed_weight,
            "n_signal_dates":       fp_result.n_signal_dates,
            "passed":               fp_result.passed,
        },
        "artifacts": [
            "forward_return_matrix.parquet",
            "p4a_holding_period.parquet",
            "p4a_bootstrap.parquet",
            "p4b_prioritisation.parquet",
            "manifest.json",
        ],
    }
    with open(ARTIFACT_DIR / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2, default=str)
    log.info("Wrote manifest.json")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Run Phase 4 Track A and B analysis."""
    log.info("=== Phase 4 runner v%s (SPEC v%s) ===", SCRIPT_VERSION, SPEC_VERSION)
    log.info("Track C: NOT IMPLEMENTED (raises NotImplementedError if called)")

    if not DB_PATH.exists():
        log.error("DuckDB not found: %s", DB_PATH)
        sys.exit(1)

    with duckdb.connect(str(DB_PATH), read_only=True) as con:

        gap_report = validate_schema_and_document_gaps(con)
        if "daily_price_adj" in gap_report.missing_tables:
            log.error("Cannot proceed: daily_price_adj missing.")
            sys.exit(1)

        # Load panel and compute full forward return matrix
        log.info("Loading panel and computing forward return matrix...")
        panel  = load_panel(con)
        prices = load_price_series(con)
        panel  = build_forward_return_matrix(panel, prices)

        # P3-FP-001: verify 20td full-sample lineage (checks net_s1, not Sharpe)
        fp_result = verify_p3_fingerprint(panel, prices, con=con)

        # Track A: holding period study (5/10/15/20td)
        log.info("=== Track A: Holding Period Study ===")
        track_a_results = run_track_a(panel, prices, con)

        # Track B: signal prioritisation
        log.info("=== Track B: Signal Prioritisation ===")
        track_b_results = run_track_b(panel, prices, con)

        # Track C: not implemented — do not call
        # run_track_c() would raise NotImplementedError

        # Write artifacts (Track A + B only)
        write_artifacts(
            panel=panel,
            track_a=track_a_results,
            track_b=track_b_results,
            gap_report=gap_report,
            fp_result=fp_result,
        )

    log.info("=== Phase 4 (Tracks A+B) complete. Artifacts: %s ===", ARTIFACT_DIR)


if __name__ == "__main__":
    main()
