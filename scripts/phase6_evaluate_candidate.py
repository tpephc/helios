# scripts/phase6_evaluate_candidate.py
"""Phase 6 Step 3D — evaluate_candidate wiring and helpers.

This module contains the functions that should be applied as patches to
scripts/run_phase6_evaluation.py to implement Step 3D wiring.

Application instructions:
    1. Add to run_phase6_evaluation.py import block (Phase 4 section):
           PANEL_START, _rank_ledger, compute_forward_returns
       Add new import block:
           from scripts.phase6_adaptive_engine import (
               evaluate_candidate_adaptive,
           )
    2. Add _build_trading_calendar() and _load_feature_panel_phase6()
       as module-level helpers in run_phase6_evaluation.py.
    3. Replace evaluate_candidate() NotImplementedError body with
       the implementation below.
    4. Update main() call sites to pass con= explicitly.

Governance constraints enforced:
    - No Phase 5 benchmark modification
    - No admission rule change
    - No capacity redesign
    - ARM_B path uses Phase 4/5 canonical surface without adaptive engine
    - E1–E4 path uses evaluate_candidate_adaptive (Step 3C WG-1 verified)
    - con is caller-owned (Option A per Step 3D decision)
"""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    import duckdb

log = logging.getLogger(__name__)


# =====================================================================
# Helper 1 — trading calendar construction
# =====================================================================


def _build_trading_calendar(
    price_df: pd.DataFrame,
) -> tuple[list[pd.Timestamp], dict[pd.Timestamp, int]]:
    """Build trading calendar and date-to-position index from price panel.

    Mirrors the calendar construction inside reconstruct_nav_for_horizon
    to ensure evaluate_candidate_adaptive uses the same calendar object
    as the canonical NAV path (WG-1 calendar lineage requirement).

    Args:
        price_df: Columnar price panel with a "date" column.

    Returns:
        (trading_calendar, date_to_pos)
        trading_calendar: ordered list[pd.Timestamp] >= PANEL_START
        date_to_pos: {pd.Timestamp: int} inverse index
    """
    from scripts.run_phase4_analysis import PANEL_START

    all_dates = pd.DatetimeIndex(sorted(price_df["date"].unique()))
    cal = all_dates[all_dates >= pd.Timestamp(PANEL_START)]
    trading_calendar = list(cal)
    date_to_pos = {d: i for i, d in enumerate(cal)}
    return trading_calendar, date_to_pos


# =====================================================================
# Helper 2 — feature panel with full-universe rs_60d_rank
# =====================================================================


def _load_feature_panel_phase6(
    con: "duckdb.DuckDBPyConnection",
    ledger: pd.DataFrame,
) -> pd.DataFrame:
    """Load feature panel for Phase 6 evaluation universe.

    E3 rank ABI (Step 3D locked per SPEC §3.4):
        rs_60d_rank = PERCENT_RANK(beta_adj_rs_60d) within the set of
        symbols that appear in ARM_B valid_path=True ledger rows for
        the scenario, evaluated per date across the full simulation
        range. This matches SPEC §3.4:
            "Rank computed over the same trading universe used by
             ARM_B entry ranking."
        Exact daily eligibility reconstruction (per-date eligible set)
        is deferred; approximation = same symbol set across all dates.

    Column mapping (confirmed from DB schema):
        daily_features.donchian_20_low  →  donchian_low_excl
        PERCENT_RANK(beta_adj_rs_60d)   →  rs_60d_rank  [0,1]

    Returns:
        DataFrame with columns:
            stock_id, date, sma_20, atr_14, donchian_low_excl, rs_60d_rank
    """
    valid = ledger[ledger["valid_path"]]
    if valid.empty:
        return pd.DataFrame(columns=[
            "stock_id", "date", "sma_20", "atr_14",
            "donchian_low_excl", "rs_60d_rank",
        ])

    # ARM_B universe: all symbols appearing as valid candidates in this scenario.
    # Per SPEC §3.4, rank is computed within this universe, not full
    # bullish_features. Symbols are consistent across all eval dates
    # (daily eligibility reconstruction deferred per Step 3D ABI lock).
    universe_symbols = list(valid["stock_id"].unique())
    universe_sql = ", ".join(f"'{s}'" for s in universe_symbols)

    # scheduled symbols = subset we need feature rows for (exit eval only).
    # rank is computed over full universe, then filtered to scheduled subset.
    scheduled_symbols = universe_symbols  # same for now; separate if needed
    scheduled_sql = universe_sql

    min_date = valid["signal_date"].min().date()

    # Date upper bound covers full simulation window (P0-BLOCKER-012 fix):
    # adaptive exit evaluation reads features through exit_date, not just
    # signal_date.
    if "exit_date" in valid.columns and valid["exit_date"].notna().any():
        max_date = valid["exit_date"].max().date()
    else:
        max_date = (
            valid["signal_date"].max() + pd.Timedelta(days=60)
        ).date()

    # Register ARM_B universe as temp relation for rank partition.
    # Rank is computed only within universe_symbols per date, then
    # filtered to scheduled_symbols.
    armb_universe = pd.DataFrame({
        "stock_id": universe_symbols,
    })
    con.register("_phase6_armb_universe", armb_universe)

    result = con.execute(f"""
        WITH universe_ranked AS (
            SELECT
                bf.stock_id,
                bf.date,
                df.sma_20,
                df.atr_14,
                df.donchian_20_low                          AS donchian_low_excl,
                PERCENT_RANK() OVER (
                    PARTITION BY bf.date
                    ORDER BY bf.beta_adj_rs_60d ASC
                )                                           AS rs_60d_rank
            FROM _phase6_armb_universe u
            JOIN bullish_features bf ON bf.stock_id = u.stock_id
            JOIN daily_features df
                ON df.stock_id = bf.stock_id AND df.date = bf.date
            WHERE bf.date BETWEEN '{min_date}' AND '{max_date}'
        )
        SELECT * FROM universe_ranked
        WHERE stock_id IN ({scheduled_sql})
        ORDER BY stock_id, date
    """).df()

    con.unregister("_phase6_armb_universe")

    result["date"] = pd.to_datetime(result["date"])

    rank_min = float(result["rs_60d_rank"].min())
    rank_max = float(result["rs_60d_rank"].max())
    if not (0.0 <= rank_min and rank_max <= 1.0):
        raise RuntimeError(
            f"_load_feature_panel_phase6: rs_60d_rank out of [0,1]: "
            f"min={rank_min:.4f} max={rank_max:.4f}"
        )
    log.info(
        "_load_feature_panel_phase6: universe=%d symbols rank_range=[%.3f,%.3f] "
        "date_range=[%s,%s] rows=%d",
        len(universe_symbols), rank_min, rank_max,
        min_date, max_date, len(result),
    )
    return result


# =====================================================================
# evaluate_candidate — Step 3D wiring
# =====================================================================



def _build_candidate_metrics(
    candidate: "Candidate",
    scenario_label: str,
    metrics_raw: dict,
    diag: dict,
    mean_holding_days: float,
    ceiling_h: int,
) -> "CandidateMetrics":
    """Construct CandidateMetrics from raw metric dict and diag.

    Centralises CandidateMetrics assembly to avoid duplication between
    ARM_B and E1-E4 paths (P1-015).
    """
    from scripts.run_phase6_evaluation import CandidateMetrics  # noqa: PLC0415
    return CandidateMetrics(
        candidate=candidate,
        scenario=scenario_label,
        sharpe=float(metrics_raw.get("sharpe", float("nan"))),
        ann_return=float(metrics_raw.get("ann_return", float("nan"))),
        ann_vol=float(metrics_raw.get("ann_vol", float("nan"))),
        max_dd=float(metrics_raw.get("max_drawdown", float("nan"))),
        calmar=float(metrics_raw.get("calmar", float("nan"))),
        admission_rate=float(diag["admission_rate"]),
        scheduled_count=int(diag["n_scheduled"]),
        candidates_count=int(diag["n_candidates"]),
        mean_holding_days=mean_holding_days,
        mean_holding_pct_of_ceiling=mean_holding_days / ceiling_h,
    )

def evaluate_candidate(
    con: "duckdb.DuckDBPyConnection",
    candidate: "Candidate",
    scenario_start: date,
    scenario_end: date,
    lineage_anchor_label: str,
) -> tuple["CandidateMetrics", pd.DataFrame]:
    """Evaluate one candidate over one scenario window.

    Step 3D wiring implementation. Replaces NotImplementedError stub
    in scripts/run_phase6_evaluation.py.

    ARM_B path (canonical — Phase 4/5 surface, no adaptive engine):
        build_signal_ledger_for_horizon
        → _rank_ledger(beta_adj_rs_60d, arm_b)
        → schedule_positions
        → load_daily_price_paths
        → reconstruct_nav_for_horizon(h=20)
        → compute_risk_metrics

    E1–E4 path (adaptive — Step 3C WG-1-verified engine):
        same ledger + ranked as ARM_B
        → _load_feature_panel_phase6 (full-universe rs_60d_rank)
        → load_daily_price_paths
        → _build_trading_calendar
        → evaluate_candidate_adaptive(EXIT_FUNCTIONS[candidate])
        → compute_risk_metrics

    Governance constraints (Step 3 Entry Note explicit non-goals):
        No Phase 5 benchmark modification.
        No admission rule change.
        No capacity redesign.

    TODO(3D): apply scenario_start / scenario_end date window filter
        to panel before ledger build. Currently evaluates full snapshot.

    Args:
        con: DuckDB connection. Caller-owned; read_only recommended.
        candidate: Which exit policy to evaluate.
        scenario_start: Inclusive evaluation window start (unused until TODO).
        scenario_end: Inclusive evaluation window end (unused until TODO).
        lineage_anchor_label: Label for provenance and metric tagging.

    Returns:
        (CandidateMetrics, nav_df)
        nav_df: pd.DataFrame with columns [date, nav, daily_log_return].
    """
    from scripts.run_phase4_analysis import (
        BASELINE_CAP,
        BASELINE_MAX_POS,
        _rank_ledger,
        build_signal_ledger_for_horizon,
        compute_forward_returns,
        reconstruct_nav_for_horizon,
        schedule_positions,
    )
    from scripts.run_phase3_analysis import (
        compute_risk_metrics,
        load_daily_price_paths,
    )
    from scripts.run_r8_phase1_a3 import load_panel, load_price_series
    from scripts.run_phase6_evaluation import (
        Candidate,
        CandidateMetrics,
        EXIT_FUNCTIONS,
        HOLD_CEILING_DAYS as _H,
    )
    from scripts.phase6_adaptive_engine import evaluate_candidate_adaptive

    log.info(
        "evaluate_candidate: candidate=%s scenario=%s..%s anchor=%s",
        candidate.value, scenario_start, scenario_end, lineage_anchor_label,
    )

    # ── Step 1: Build signal ledger (shared by all candidates) ───────────────
    panel = load_panel(con)
    prices = load_price_series(con)
    # load_panel() returns 5 columns, no forward-return columns.
    # compute_forward_returns is required (not redundant recomputation).
    # Confirmed: load_panel(con).columns has no fwd_* prefix.
    if f"fwd_{_H}td" not in panel.columns:
        panel = compute_forward_returns(panel, prices, horizons=[_H])

    ledger = build_signal_ledger_for_horizon(
        panel, prices,
        pool="treatment_1",
        scenario="low_uplift",    # TODO(3D): parameterise via scenario_start/end
        h=_H,
        con=con,
    )
    ranked = _rank_ledger(ledger, "beta_adj_rs_60d", "arm_b")

    # ── Step 2: ARM_B canonical path ─────────────────────────────────────────
    if candidate == Candidate.ARM_B:
        scheduled, diag = schedule_positions(ranked, BASELINE_CAP, BASELINE_MAX_POS)

        if not scheduled:
            raise RuntimeError(
                f"evaluate_candidate(ARM_B): schedule_positions returned empty "
                f"list for anchor={lineage_anchor_label!r}."
            )

        price_df = load_daily_price_paths(con, scheduled)
        nav_df = reconstruct_nav_for_horizon(
            scheduled, price_df, BASELINE_CAP, h=_H
        )
        metrics_raw = compute_risk_metrics(
            nav_df, f"{candidate.value}_{lineage_anchor_label}"
        )

        # mean_holding_days for ARM_B = H for all positions (fixed horizon).
        mean_hd = float(_H)

        return _build_candidate_metrics(
            candidate=candidate,
            scenario_label=lineage_anchor_label,
            metrics_raw=metrics_raw,
            diag=diag,
            mean_holding_days=mean_hd,
            ceiling_h=_H,
        ), nav_df

    # ── Step 3: E1–E4 adaptive path ──────────────────────────────────────────
    if candidate not in EXIT_FUNCTIONS:
        raise ValueError(
            f"evaluate_candidate: unknown candidate {candidate!r}. "
            f"Registered: {sorted(k.value for k in EXIT_FUNCTIONS)}"
        )

    exit_fn = EXIT_FUNCTIONS[candidate]

    # Feature panel with correct rs_60d_rank semantics (Step 3D P1).
    feature_panel = _load_feature_panel_phase6(con, ledger)

    # Price panel: full valid-path universe to cover all simulation bars.
    # Build minimal ScheduledPosition stubs covering the full date range
    # so load_daily_price_paths fetches all required (symbol, date) pairs.
    from scripts.run_phase4_analysis import ScheduledPosition as _SP
    price_fetch_stubs = [
        _SP(
            stock_id=str(row["stock_id"]),
            signal_date=pd.Timestamp(row["signal_date"]),
            entry_date=pd.Timestamp(row["entry_date"]),
            exit_date=pd.Timestamp(row["exit_date"]),
            weight=BASELINE_CAP,
            fwd_return_20td=float(row.get(f"fwd_{_H}td", 0.0)),
        )
        for _, row in ranked[ranked["valid_path"]].iterrows()
    ]
    price_df = load_daily_price_paths(con, price_fetch_stubs)

    trading_calendar, date_to_pos = _build_trading_calendar(price_df)

    adaptive_positions, nav_df, diag = evaluate_candidate_adaptive(
        ranked=ranked,
        feature_panel=feature_panel,
        price_panel=price_df,
        trading_calendar=trading_calendar,
        date_to_pos=date_to_pos,
        exit_policy_fn=exit_fn,
        hard_ceiling_h=_H,
        cap=BASELINE_CAP,
        max_pos=BASELINE_MAX_POS,
        strict_features=True,   # P0-BLOCKER-011: fail-fast on missing feature rows
    )

    metrics_raw = compute_risk_metrics(
        nav_df, f"{candidate.value}_{lineage_anchor_label}"
    )
    mean_hd = float(diag["mean_holding_days"])

    return _build_candidate_metrics(
        candidate=candidate,
        scenario_label=lineage_anchor_label,
        metrics_raw=metrics_raw,
        diag=diag,
        mean_holding_days=mean_hd,
        ceiling_h=_H,
    ), nav_df
