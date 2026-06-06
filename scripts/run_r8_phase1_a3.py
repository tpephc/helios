#!/usr/bin/env python3
# scripts/run_r8_phase1_a3.py
"""R8 Phase 1 A-3 Inferential Analysis — v0.1.0.

Compares forward returns of Treatment_1 (R8 ∩ RS_T3) vs Baseline_1
(RS_T3 unconditional, non-R8) using stationary block-bootstrap inference
per ADR-R8P1-001 v0.1.0 and ADR-R8P1-002 v0.1.0.

Locked constants:
    B = 5000 bootstrap replications
    L_primary = 20 trading days (geometric mean block length)
    L_sensitivity = {5, 10, 20, 40}
    CI method = percentile
    p-value method = null_shifted_two_tailed
    Seed = 42
    Horizons = {1, 5, 10, 20} trading days
    Forward return = adj_close[T+h] / adj_open[T+1] - 1

All findings are PROVISIONAL per lifecycle spec AC-6 (IF-2, IF-3 OPEN).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

import duckdb
import numpy as np
import pandas as pd
from arch.bootstrap import StationaryBootstrap

# ---------------------------------------------------------------------------
# Constants (all locked per ADR-R8P1-001 v0.1.0)
# ---------------------------------------------------------------------------

DB_PATH = Path("data/_storage/helios.duckdb")
P0B_DIR = Path("data/_storage/r8_phase1_cell_adequacy/v0.1.1")
OUTPUT_DIR = Path("data/_storage/r8_phase1_a3/v0.1.0")

BOOTSTRAP_REPLICATIONS: int = 5000
BLOCK_LENGTH_PRIMARY: int = 20
BLOCK_LENGTH_SENSITIVITY: list[int] = [5, 10, 20, 40]
SEED: int = 42
HORIZONS_TD: list[int] = [1, 5, 10, 20]
CI_LO_QUANTILE: float = 0.025
CI_HI_QUANTILE: float = 0.975

# Joint adequacy classification thresholds (from cell adequacy spec v0.1.1)
PASS_THRESHOLD: int = 100
DIRECTIONAL_THRESHOLD: int = 30

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("r8_phase1_a3")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class CellKey(NamedTuple):
    """Identifies a (regime, near_limit_up) analysis cell."""

    regime: str
    near_limit_up: int


class BootstrapResult(NamedTuple):
    """Full bootstrap output for a single cell × horizon."""

    delta_obs: float
    se_naive: float
    se_bootstrap: float
    vif: float
    n_eff: float
    ci_lo: float
    ci_hi: float
    p_value: float
    n_bootstrap_used: int


# ---------------------------------------------------------------------------
# Panel construction (mirrors P0-B SQL exactly)
# ---------------------------------------------------------------------------

_PANEL_SQL = """
WITH
price_lagged AS (
    SELECT
        stock_id,
        CAST(date AS DATE)                                  AS date,
        CAST(adj_open AS DOUBLE)                            AS adj_open,
        CAST(adj_close AS DOUBLE)                           AS adj_close,
        LAG(CAST(adj_close AS DOUBLE))
            OVER (PARTITION BY stock_id ORDER BY CAST(date AS DATE))
                                                            AS prev_adj_close
    FROM listed_market_daily_price_adj
),
rs_classified AS (
    SELECT
        stock_id,
        CAST(date AS DATE)                                  AS date,
        CAST(dist_above_ma20_atr AS DOUBLE)                 AS dist_above_ma20_atr,
        CASE
            WHEN beta_adj_rs_20d > quantile_cont(beta_adj_rs_20d, 0.6666666666666666)
                 OVER (PARTITION BY CAST(date AS DATE))
                THEN 'RS_T3'
            WHEN beta_adj_rs_20d > quantile_cont(beta_adj_rs_20d, 0.3333333333333333)
                 OVER (PARTITION BY CAST(date AS DATE))
                THEN 'RS_T2'
            ELSE 'RS_T1'
        END                                                 AS rs_tertile
    FROM bullish_features
    WHERE beta_adj_rs_20d IS NOT NULL
),
regime_tminus1 AS (
    SELECT
        CAST(date AS DATE)                                  AS date,
        LAG(CAST(regime AS VARCHAR))
            OVER (ORDER BY CAST(date AS DATE))              AS regime
    FROM market_regime
    WHERE regime IS NOT NULL
),
panel AS (
    SELECT
        p.stock_id,
        p.date,
        r.regime,
        CASE
            WHEN p.prev_adj_close IS NOT NULL
             AND p.prev_adj_close > 0
             AND p.adj_close / p.prev_adj_close - 1.0 >= 0.05
             AND p.adj_close > p.adj_open
            THEN 1 ELSE 0
        END                                                 AS r8_flag,
        rs.rs_tertile,
        rs.dist_above_ma20_atr,
        CASE
            WHEN p.prev_adj_close IS NULL OR p.prev_adj_close <= 0 THEN NULL
            WHEN p.adj_close / p.prev_adj_close - 1.0 >= 0.095    THEN 1
            ELSE 0
        END                                                 AS near_limit_up
    FROM price_lagged p
    INNER JOIN rs_classified rs
        ON  p.stock_id = rs.stock_id
        AND p.date     = rs.date
    LEFT JOIN regime_tminus1 r
        ON  p.date = r.date
    WHERE p.prev_adj_close IS NOT NULL
      AND p.prev_adj_close > 0
      AND r.regime IS NOT NULL
),
r8_events AS (
    SELECT * FROM panel WHERE r8_flag = 1
),
d_r8 AS (
    SELECT DISTINCT date FROM r8_events
),
rs_t3_on_event_dates AS (
    SELECT p.*
    FROM panel AS p
    INNER JOIN d_r8 USING (date)
    WHERE p.rs_tertile = 'RS_T3'
),
treatment_1 AS (
    SELECT * FROM r8_events WHERE rs_tertile = 'RS_T3'
),
baseline_1 AS (
    SELECT b.*
    FROM rs_t3_on_event_dates AS b
    LEFT JOIN r8_events AS r
        ON  r.stock_id = b.stock_id
        AND r.date     = b.date
    WHERE r.stock_id IS NULL
)
SELECT
    stock_id,
    date,
    regime,
    near_limit_up,
    CAST(universe AS VARCHAR)                               AS universe
FROM (
    SELECT *, 'treatment_1' AS universe FROM treatment_1
    WHERE near_limit_up IS NOT NULL
    UNION ALL
    SELECT *, 'baseline_1' AS universe FROM baseline_1
    WHERE near_limit_up IS NOT NULL
)
ORDER BY universe, date, stock_id
"""

_FORWARD_PRICE_SQL = """
SELECT
    stock_id,
    CAST(date AS DATE)      AS date,
    CAST(adj_open AS DOUBLE) AS adj_open,
    CAST(adj_close AS DOUBLE) AS adj_close
FROM listed_market_daily_price_adj
"""


def load_panel(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Load treatment_1 and baseline_1 universe assignments from DuckDB.

    Returns a DataFrame with columns:
        stock_id, date, regime, near_limit_up, universe
    """
    log.info("Loading base panel (treatment_1 + baseline_1) from DuckDB ...")
    df = con.execute(_PANEL_SQL).fetchdf()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    log.info("Base panel: %d rows (%d treatment, %d baseline)",
             len(df),
             (df["universe"] == "treatment_1").sum(),
             (df["universe"] == "baseline_1").sum())
    return df


def load_price_series(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Load full adj_open and adj_close series for forward return calculation.

    Returns a DataFrame indexed by (stock_id, date).
    """
    log.info("Loading price series ...")
    df = con.execute(_FORWARD_PRICE_SQL).fetchdf()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.set_index(["stock_id", "date"]).sort_index()
    return df


# ---------------------------------------------------------------------------
# Forward return calculation
# ---------------------------------------------------------------------------

def compute_forward_returns(
    panel: pd.DataFrame,
    prices: pd.DataFrame,
    horizons: list[int],
) -> pd.DataFrame:
    """Attach forward returns for each horizon to the panel.

    Formula (locked per lifecycle spec v0.1.2):
        forward_return[T+h] = adj_close[T+h] / adj_open[T+1] - 1

    T   = signal date (r8_flag = 1 for treatment; RS_T3 non-R8 for baseline)
    T+1 = next trading day adj_open  (entry)
    T+h = h trading days after T adj_close  (exit)

    Observations where T+1 or T+h is missing are set to NaN for that horizon;
    they are excluded from that horizon's calculations only.

    Uses dict-based O(1) lookup for performance (~70k panel rows × 4 horizons).

    Args:
        panel: Base panel with columns [stock_id, date, regime,
               near_limit_up, universe].
        prices: Price series indexed by (stock_id, date).
        horizons: List of forward return horizons in trading days.

    Returns:
        panel with added columns `fwd_{h}td` for each h in horizons.
    """
    log.info("Building sorted trading calendar ...")
    all_dates = np.array(
        sorted(prices.index.get_level_values("date").unique())
    )
    n_cal = len(all_dates)
    date_to_pos: dict = {d: i for i, d in enumerate(all_dates)}

    # Flat dict lookups: (stock_id, date) -> float
    adj_open_lookup: dict = prices["adj_open"].to_dict()
    adj_close_lookup: dict = prices["adj_close"].to_dict()

    result = panel.copy()
    signal_positions = result["date"].map(date_to_pos)  # NaN if date not in calendar

    for h in horizons:
        col = f"fwd_{h}td"

        t1_pos = signal_positions + 1
        th_pos = signal_positions + h

        # Horizon is infeasible if either offset falls outside the calendar
        feasible = (t1_pos < n_cal) & (th_pos < n_cal) & signal_positions.notna()

        t1_dates = np.where(
            feasible,
            all_dates[np.clip(t1_pos.fillna(0).astype(int), 0, n_cal - 1)],
            None,
        )
        th_dates = np.where(
            feasible,
            all_dates[np.clip(th_pos.fillna(0).astype(int), 0, n_cal - 1)],
            None,
        )

        fwd_returns: list[float | None] = []
        stocks = result["stock_id"].to_numpy()

        for i in range(len(result)):
            if not feasible.iloc[i]:
                fwd_returns.append(None)
                continue

            stock = stocks[i]
            open_val = adj_open_lookup.get((stock, t1_dates[i]))
            close_val = adj_close_lookup.get((stock, th_dates[i]))

            if open_val is None or open_val <= 0 or close_val is None:
                fwd_returns.append(None)
                continue

            fwd_returns.append(float(close_val) / float(open_val) - 1.0)

        result[col] = fwd_returns
        n_valid = result[col].notna().sum()
        log.info(
            "Horizon %dtd: %d / %d observations have valid forward returns",
            h, n_valid, len(result),
        )

    return result


# ---------------------------------------------------------------------------
# Joint adequacy derivation
# ---------------------------------------------------------------------------

def _classify(n_unique_dates: int) -> str:
    """Map n_unique_dates to adequacy classification."""
    if n_unique_dates >= PASS_THRESHOLD:
        return "PASS"
    if n_unique_dates >= DIRECTIONAL_THRESHOLD:
        return "DIRECTIONAL_ONLY"
    return "INSUFFICIENT"


def _weaker_of_two(a: str, b: str) -> str:
    """Return the weaker adequacy classification of two."""
    rank = {"PASS": 2, "DIRECTIONAL_ONLY": 1, "INSUFFICIENT": 0}
    return a if rank[a] <= rank[b] else b


def derive_joint_adequacy(p0b_dir: Path) -> dict[CellKey, str]:
    """Compute joint adequacy (weaker-of-two D-2A ∩ D-2B) from P0-B parquets.

    Joint adequacy = min(D-2A classification, D-2B Baseline_1 classification)
    using the ordering PASS > DIRECTIONAL_ONLY > INSUFFICIENT.

    Args:
        p0b_dir: Path to the P0-B output directory.

    Returns:
        Mapping from CellKey to joint adequacy string.
    """
    d2a = pd.read_parquet(p0b_dir / "d2a_a3_support.parquet")
    d2b = pd.read_parquet(p0b_dir / "d2b_baseline_adequacy.parquet")

    d2b_b1 = d2b[d2b["baseline_universe"] == "Baseline_1"].copy()

    # Recompute classifications from n_unique_dates (authoritative over stored string)
    d2a["_cls"] = d2a["n_unique_dates"].apply(_classify)
    d2b_b1 = d2b_b1.copy()
    d2b_b1["_cls"] = d2b_b1["n_unique_dates"].apply(_classify)

    joint: dict[CellKey, str] = {}

    for _, row_a in d2a.iterrows():
        key = CellKey(regime=row_a["regime"], near_limit_up=int(row_a["near_limit_up"]))
        cls_a = row_a["_cls"]

        match_b = d2b_b1[
            (d2b_b1["regime"] == key.regime) &
            (d2b_b1["near_limit_up"] == key.near_limit_up)
        ]

        if len(match_b) == 0:
            # No baseline data for this cell — treat as INSUFFICIENT
            cls_b = "INSUFFICIENT"
        elif len(match_b) == 1:
            cls_b = match_b.iloc[0]["_cls"]
        else:
            raise RuntimeError(
                f"Duplicate D-2B rows for cell {key}: {len(match_b)} rows found"
            )

        joint[key] = _weaker_of_two(cls_a, cls_b)

    log.info("Joint adequacy map:")
    for k, v in sorted(joint.items()):
        log.info("  (%s, nlu=%d) -> %s", k.regime, k.near_limit_up, v)

    return joint


# ---------------------------------------------------------------------------
# Stationary block-bootstrap (date-level, joint resample)
# ---------------------------------------------------------------------------

def _stationary_bootstrap_dates(
    dates: np.ndarray,
    block_length: int,
    n_replications: int,
    seed: int,
) -> list[np.ndarray]:
    """Draw n_replications stationary bootstrap samples of the date index.

    Uses arch.bootstrap.StationaryBootstrap with geometric block lengths.
    The resampling unit is the integer index into `dates`; callers map
    back to actual dates.

    Args:
        dates: Sorted array of unique trading dates in the regime.
        block_length: Mean block length L (geometric distribution).
        n_replications: Number of bootstrap replications B.
        seed: Random seed for reproducibility.

    Returns:
        List of length n_replications; each element is an array of
        date indices (with replacement, length == len(dates)).
    """
    n = len(dates)
    bs = StationaryBootstrap(block_length, np.arange(n), seed=seed)
    samples: list[np.ndarray] = []
    for data, _ in bs.bootstrap(n_replications):
        # data is a tuple; first element is the resampled index array
        samples.append(data[0].flatten().astype(int))
    return samples


def _delta_stat(
    treatment_returns: np.ndarray,
    baseline_returns: np.ndarray,
) -> float:
    """Compute observed delta statistic: mean(treatment) - mean(baseline).

    Returns nan if either side is empty.
    """
    if len(treatment_returns) == 0 or len(baseline_returns) == 0:
        return float("nan")
    return float(np.mean(treatment_returns)) - float(np.mean(baseline_returns))


def run_bootstrap(
    treatment_df: pd.DataFrame,
    baseline_df: pd.DataFrame,
    fwd_col: str,
    block_length: int,
    n_replications: int,
    seed: int,
) -> BootstrapResult:
    """Run joint stationary bootstrap for a single cell × horizon × block length.

    Joint resample per ADR-R8P1-001 D5: the same date resample is applied
    to both treatment and baseline in each replication.

    p-value method: null_shifted_two_tailed
        delta_star_centered = delta_star - mean(delta_star)
        p = mean(|delta_star_centered| >= |delta_obs|)

    Args:
        treatment_df: Rows from treatment_1 with valid fwd_col values.
        baseline_df: Rows from baseline_1 with valid fwd_col values.
        fwd_col: Name of the forward return column.
        block_length: Mean geometric block length L.
        n_replications: Number of bootstrap replications B.
        seed: Random seed.

    Returns:
        BootstrapResult with all inference quantities.
    """
    # --- Observed statistic ---
    t_returns = treatment_df[fwd_col].to_numpy(dtype=float)
    b_returns = baseline_df[fwd_col].to_numpy(dtype=float)
    delta_obs = _delta_stat(t_returns, b_returns)

    # --- Naive SE (i.i.d. pooled, for VIF denominator) ---
    # Treat the joint sample as: delta_hat ~ N(0, Var(T)/n_T + Var(B)/n_B)
    var_t = np.var(t_returns, ddof=1) if len(t_returns) > 1 else 0.0
    var_b = np.var(b_returns, ddof=1) if len(b_returns) > 1 else 0.0
    se_naive = float(np.sqrt(var_t / len(t_returns) + var_b / len(b_returns)))

    # --- Date pool: treatment dates only (ADR D1 + D5) ---
    # Baseline_1 is defined as RS_T3 on D_R8 dates; P0-B invariant
    # dropped_no_baseline_1_dates=[] guarantees every treatment date has
    # baseline coverage.  Using union would introduce baseline-only dates
    # that yield empty treatment draws in some replications.
    all_dates = np.array(sorted(set(treatment_df["date"].tolist())))
    n_dates = len(all_dates)
    date_to_idx = {d: i for i, d in enumerate(all_dates)}

    treatment_df = treatment_df.copy()
    baseline_df = baseline_df.copy()
    treatment_df["_date_idx"] = treatment_df["date"].map(date_to_idx)
    baseline_df["_date_idx"] = baseline_df["date"].map(date_to_idx)

    # INV-POOL-1: every treatment date must resolve to a known index
    # (guards against treatment dates absent from the sorted date pool)
    if treatment_df["_date_idx"].isna().any():
        missing = treatment_df.loc[treatment_df["_date_idx"].isna(), "date"].unique()
        raise RuntimeError(
            f"INV-POOL-1 violated: {len(missing)} treatment dates not in date pool: "
            f"{sorted(missing)[:5]}{'...' if len(missing) > 5 else ''}"
        )

    # INV-POOL-2: every baseline date must be a subset of the treatment date pool.
    # Baseline_1 is defined on D_R8 dates; P0-B invariant dropped_no_baseline_1_dates=[]
    # guarantees this.  Any violation signals upstream SQL drift.
    t_date_idx_set = set(treatment_df["_date_idx"].tolist())
    b_date_idx_extra = (
        set(baseline_df["_date_idx"].dropna().astype(int).tolist()) - t_date_idx_set
    )
    if b_date_idx_extra:
        extra_dates = [all_dates[i] for i in sorted(b_date_idx_extra)]
        raise RuntimeError(
            f"INV-POOL-2 violated: {len(b_date_idx_extra)} baseline dates not in "
            f"treatment date pool (dropped_no_baseline_1_dates invariant broken). "
            f"First offenders: {extra_dates[:5]}"
        )

    # Pre-group by date index for O(1) lookup per replication
    t_by_date: dict[int, np.ndarray] = {
        idx: grp[fwd_col].to_numpy(dtype=float)
        for idx, grp in treatment_df.groupby("_date_idx")
    }
    b_by_date: dict[int, np.ndarray] = {
        idx: grp[fwd_col].to_numpy(dtype=float)
        for idx, grp in baseline_df.groupby("_date_idx")
    }

    # --- Bootstrap replications ---
    date_index_samples = _stationary_bootstrap_dates(
        all_dates, block_length, n_replications, seed
    )

    delta_star: list[float] = []
    used = 0

    for sampled_idx in date_index_samples:
        t_boot: list[np.ndarray] = [t_by_date[i] for i in sampled_idx if i in t_by_date]
        b_boot: list[np.ndarray] = [b_by_date[i] for i in sampled_idx if i in b_by_date]

        if not t_boot or not b_boot:
            continue

        t_arr = np.concatenate(t_boot)
        b_arr = np.concatenate(b_boot)
        d = _delta_stat(t_arr, b_arr)
        if not np.isnan(d):
            delta_star.append(d)
            used += 1

    if used < 100:
        log.warning(
            "Only %d valid bootstrap replications for %s (block_length=%d)",
            used, fwd_col, block_length,
        )

    delta_star_arr = np.array(delta_star)

    # --- SE and VIF ---
    se_bootstrap = float(np.std(delta_star_arr, ddof=1))
    vif = float((se_bootstrap / se_naive) ** 2) if se_naive > 0 else float("nan")
    # n_eff reference unit = treatment date pool (ADR D1/D6).
    # The resampling unit is R8 event dates; n_raw is the treatment-side
    # date count, not the baseline date count or the union.
    n_raw_dates = float(n_dates)  # len(treatment date pool)
    n_eff = n_raw_dates / vif if (vif > 0 and not np.isnan(vif)) else float("nan")

    # --- Percentile CI ---
    ci_lo = float(np.quantile(delta_star_arr, CI_LO_QUANTILE))
    ci_hi = float(np.quantile(delta_star_arr, CI_HI_QUANTILE))

    # --- p-value: null-shifted two-tailed ---
    # Shift bootstrap distribution to null (delta = 0)
    delta_star_centered = delta_star_arr - np.mean(delta_star_arr)
    p_value = float(np.mean(np.abs(delta_star_centered) >= abs(delta_obs)))

    return BootstrapResult(
        delta_obs=delta_obs,
        se_naive=se_naive,
        se_bootstrap=se_bootstrap,
        vif=vif,
        n_eff=n_eff,
        ci_lo=ci_lo,
        ci_hi=ci_hi,
        p_value=p_value,
        n_bootstrap_used=used,
    )


# ---------------------------------------------------------------------------
# Main analysis loop
# ---------------------------------------------------------------------------

def run_analysis(
    panel_with_returns: pd.DataFrame,
    joint_adequacy: dict[CellKey, str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run A-3 analysis across all cells × horizons.

    Returns:
        primary_df: Primary inference results (L=20) as DataFrame.
        sensitivity_df: Sensitivity results across all block lengths.
    """
    primary_rows: list[dict] = []
    sensitivity_rows: list[dict] = []

    cells = sorted(joint_adequacy.keys())

    for cell in cells:
        adequacy = joint_adequacy[cell]
        inference_status = adequacy  # PASS -> FULL below

        log.info("Cell (%s, nlu=%d): joint_adequacy=%s",
                 cell.regime, cell.near_limit_up, adequacy)

        cell_mask = (
            (panel_with_returns["regime"] == cell.regime) &
            (panel_with_returns["near_limit_up"] == cell.near_limit_up)
        )
        t_cell = panel_with_returns[cell_mask & (panel_with_returns["universe"] == "treatment_1")]
        b_cell = panel_with_returns[cell_mask & (panel_with_returns["universe"] == "baseline_1")]

        for h in HORIZONS_TD:
            fwd_col = f"fwd_{h}td"

            t_valid = t_cell[t_cell[fwd_col].notna()].copy()
            b_valid = b_cell[b_cell[fwd_col].notna()].copy()

            t_n = len(t_valid)
            b_n = len(b_valid)
            t_n_dates = int(t_valid["date"].nunique())
            b_n_dates = int(b_valid["date"].nunique())

            t_mean = float(t_valid[fwd_col].mean()) if t_n > 0 else float("nan")
            b_mean = float(b_valid[fwd_col].mean()) if b_n > 0 else float("nan")
            delta_obs_raw = (t_mean - b_mean) if (t_n > 0 and b_n > 0) else float("nan")

            base_row: dict = {
                "regime": cell.regime,
                "near_limit_up": cell.near_limit_up,
                "horizon_td": h,
                "joint_adequacy": adequacy,
                "inference_status": "FULL" if adequacy == "PASS" else adequacy,
                "treatment_n_events": t_n,
                "baseline_n_events": b_n,
                "treatment_n_dates": t_n_dates,
                "baseline_n_dates": b_n_dates,
                "treatment_mean_return": t_mean,
                "baseline_mean_return": b_mean,
                "delta_obs": delta_obs_raw,
            }

            if adequacy == "PASS" and t_n > 0 and b_n > 0:
                log.info(
                    "  Horizon %dtd: running bootstrap (t_n=%d, b_n=%d, t_dates=%d) ...",
                    h, t_n, b_n, t_n_dates,
                )
                result = run_bootstrap(
                    t_valid, b_valid, fwd_col,
                    block_length=BLOCK_LENGTH_PRIMARY,
                    n_replications=BOOTSTRAP_REPLICATIONS,
                    seed=SEED,
                )
                primary_row = {
                    **base_row,
                    "se_naive": result.se_naive,
                    "se_bootstrap": result.se_bootstrap,
                    "vif": result.vif,
                    "n_eff": result.n_eff,
                    "ci_lo": result.ci_lo,
                    "ci_hi": result.ci_hi,
                    "bootstrap_p_value": result.p_value,
                    "block_length_primary": BLOCK_LENGTH_PRIMARY,
                    "n_bootstrap_used": result.n_bootstrap_used,
                }

                # Sensitivity runs
                for L in BLOCK_LENGTH_SENSITIVITY:
                    sens_result = run_bootstrap(
                        t_valid, b_valid, fwd_col,
                        block_length=L,
                        n_replications=BOOTSTRAP_REPLICATIONS,
                        seed=SEED,
                    )
                    sensitivity_rows.append({
                        "regime": cell.regime,
                        "near_limit_up": cell.near_limit_up,
                        "horizon_td": h,
                        "block_length": L,
                        "is_primary": (L == BLOCK_LENGTH_PRIMARY),
                        "diagnostic_only": (L in {5, 10}),
                        "delta_obs": delta_obs_raw,
                        "se_bootstrap": sens_result.se_bootstrap,
                        "vif": sens_result.vif,
                        "n_eff": sens_result.n_eff,
                        "ci_lo": sens_result.ci_lo,
                        "ci_hi": sens_result.ci_hi,
                        "bootstrap_p_value": sens_result.p_value,
                        "n_bootstrap_used": sens_result.n_bootstrap_used,
                    })

            else:
                # DIRECTIONAL_ONLY: point estimate only; no bootstrap quantities
                # INSUFFICIENT: all NaN
                if adequacy == "INSUFFICIENT":
                    base_row["treatment_mean_return"] = float("nan")
                    base_row["baseline_mean_return"] = float("nan")
                    base_row["delta_obs"] = float("nan")

                primary_row = {
                    **base_row,
                    "se_naive": float("nan"),
                    "se_bootstrap": float("nan"),
                    "vif": float("nan"),
                    "n_eff": float("nan"),
                    "ci_lo": float("nan"),
                    "ci_hi": float("nan"),
                    "bootstrap_p_value": float("nan"),
                    "block_length_primary": BLOCK_LENGTH_PRIMARY,
                    "n_bootstrap_used": 0,
                }

            primary_rows.append(primary_row)
            log.info(
                "  Horizon %dtd: delta_obs=%.4f, status=%s",
                h, primary_row["delta_obs"], primary_row["inference_status"],
            )

    primary_df = pd.DataFrame(primary_rows)
    sensitivity_df = pd.DataFrame(sensitivity_rows) if sensitivity_rows else pd.DataFrame()

    return primary_df, sensitivity_df


# ---------------------------------------------------------------------------
# Invariant checks
# ---------------------------------------------------------------------------

def check_output_invariants(
    primary_df: pd.DataFrame,
    joint_adequacy: dict[CellKey, str],
) -> None:
    """Validate output invariants before writing.

    Raises:
        RuntimeError: If any invariant is violated.
    """
    # INV-1: Every (cell, horizon) combination must be present
    expected_cells = list(joint_adequacy.keys())
    for cell in expected_cells:
        for h in HORIZONS_TD:
            mask = (
                (primary_df["regime"] == cell.regime) &
                (primary_df["near_limit_up"] == cell.near_limit_up) &
                (primary_df["horizon_td"] == h)
            )
            n = mask.sum()
            if n != 1:
                raise RuntimeError(
                    f"INV-1 violated: cell ({cell.regime}, nlu={cell.near_limit_up}), "
                    f"horizon={h}td has {n} rows (expected 1)"
                )

    # INV-2: FULL rows must have non-NaN bootstrap quantities
    full_rows = primary_df[primary_df["inference_status"] == "FULL"]
    bootstrap_cols = ["se_naive", "se_bootstrap", "vif", "n_eff",
                      "ci_lo", "ci_hi", "bootstrap_p_value"]
    for col in bootstrap_cols:
        if full_rows[col].isna().any():
            bad = full_rows[full_rows[col].isna()][
                ["regime", "near_limit_up", "horizon_td"]
            ]
            raise RuntimeError(
                f"INV-2 violated: FULL rows have NaN in '{col}':\n{bad}"
            )

    # INV-3: INSUFFICIENT rows must have NaN delta_obs
    insuf_rows = primary_df[primary_df["inference_status"] == "INSUFFICIENT"]
    if insuf_rows["delta_obs"].notna().any():
        raise RuntimeError(
            "INV-3 violated: INSUFFICIENT rows have non-NaN delta_obs"
        )

    # INV-4: FULL rows must pass PASS adequacy
    full_cells = set(
        zip(
            full_rows["regime"].tolist(),
            full_rows["near_limit_up"].tolist(),
        )
    )
    for regime, nlu in full_cells:
        k = CellKey(regime=regime, near_limit_up=nlu)
        if joint_adequacy.get(k) != "PASS":
            raise RuntimeError(
                f"INV-4 violated: FULL inference for non-PASS cell {k}"
            )

    # INV-5: p-values must be in [0, 1] for FULL rows
    p_vals = full_rows["bootstrap_p_value"]
    if ((p_vals < 0) | (p_vals > 1)).any():
        raise RuntimeError("INV-5 violated: p-values outside [0, 1]")

    # INV-6: n_bootstrap_used >= 100 for all FULL rows
    if (full_rows["n_bootstrap_used"] < 100).any():
        bad = full_rows[full_rows["n_bootstrap_used"] < 100][
            ["regime", "near_limit_up", "horizon_td", "n_bootstrap_used"]
        ]
        raise RuntimeError(f"INV-6 violated: fewer than 100 valid replications:\n{bad}")

    log.info("All output invariants passed.")


# ---------------------------------------------------------------------------
# Manifest construction
# ---------------------------------------------------------------------------

def _sha256_parquet(path: Path) -> str:
    """Compute SHA-256 hex digest of a parquet file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(
    primary_path: Path,
    sensitivity_path: Path | None,
    joint_adequacy: dict[CellKey, str],
    p0b_manifest: dict,
    started_at: datetime,
    git_head: str | None,
) -> dict:
    """Build the A-3 output manifest.

    Args:
        primary_path: Path to the primary inference parquet.
        sensitivity_path: Path to the sensitivity parquet (or None).
        joint_adequacy: The computed joint adequacy map.
        p0b_manifest: Loaded P0-B manifest dict.
        started_at: UTC datetime when script started.
        git_head: Git HEAD SHA if available.

    Returns:
        Manifest dict ready for JSON serialisation.
    """
    output_hashes: dict[str, str] = {
        "a3_primary_inference": _sha256_parquet(primary_path),
    }
    if sensitivity_path and sensitivity_path.exists():
        output_hashes["a3_sensitivity_block_length"] = _sha256_parquet(sensitivity_path)

    joint_adequacy_serialisable = {
        f"{k.regime}_nlu{k.near_limit_up}": v
        for k, v in joint_adequacy.items()
    }

    return {
        # Method spec
        "bootstrap_method": "stationary",
        "resampling_unit": "trading_date",
        "joint_resample": True,
        "block_length_primary": BLOCK_LENGTH_PRIMARY,
        "block_length_sensitivity": BLOCK_LENGTH_SENSITIVITY,
        "replications": BOOTSTRAP_REPLICATIONS,
        "ci_method": "percentile",
        "regime_stratified": True,
        "seed": SEED,
        "n_eff_reference_unit": "treatment_date_pool",
        "adr_version": "ADR-R8P1-001 v0.1.0",
        "p_value_method": "null_shifted_two_tailed",
        "forward_return_formula": "adj_close[T+h] / adj_open[T+1] - 1",
        "horizons_td": HORIZONS_TD,
        # Provenance
        "lifecycle_spec_version": "v0.1.2",
        "p0b_audit_version": "v0.1.1",
        "p0b_panel_snapshot_hash": p0b_manifest.get("panel_snapshot_hash"),
        "p0b_output_hashes": p0b_manifest.get("output_hashes"),
        "p0b_git_head": p0b_manifest.get("git_head"),
        # Findings status
        "findings_status": "PROVISIONAL",
        "provisional_reason": "AC-6: IF-2 (empty stock_info) and IF-3 (empty corporate_actions, DQ-CA-001) remain OPEN",
        # Adequacy
        "joint_adequacy": joint_adequacy_serialisable,
        "full_inference_cells": [
            f"{k.regime}_nlu{k.near_limit_up}"
            for k, v in joint_adequacy.items()
            if v == "PASS"
        ],
        # Run metadata
        "script_version": "v0.1.0",
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "git_head": git_head,
        # Output
        "outputs": {
            "a3_primary_inference": str(primary_path),
            **({"a3_sensitivity_block_length": str(sensitivity_path)}
               if sensitivity_path else {}),
        },
        "output_hashes": output_hashes,
        # Sensitivity diagnostic note (locked)
        "sensitivity_note": (
            "L in {5, 10} are diagnostic only per ADR-R8P1-001 D3. "
            "Primary inference must use L=20. "
            "L={5,10} results must not be used as inferential statements."
        ),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run R8 Phase 1 A-3 inferential analysis."""
    started_at = datetime.now(tz=timezone.utc)
    log.info("=== R8 Phase 1 A-3 started at %s ===", started_at.isoformat())

    # --- Git HEAD ---
    git_head: str | None = None
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        git_head = result.stdout.strip()
    except Exception:
        pass

    # --- Output directory ---
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    log.info("Output directory: %s", OUTPUT_DIR)

    # --- Load P0-B manifest ---
    p0b_manifest_path = P0B_DIR / "manifest.json"
    if not p0b_manifest_path.exists():
        raise RuntimeError(f"P0-B manifest not found: {p0b_manifest_path}")
    with open(p0b_manifest_path) as f:
        p0b_manifest = json.load(f)
    log.info("P0-B panel_snapshot_hash: %s", p0b_manifest.get("panel_snapshot_hash"))

    # --- Joint adequacy ---
    joint_adequacy = derive_joint_adequacy(P0B_DIR)

    # --- Load panel and prices from DuckDB ---
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        panel = load_panel(con)
        prices = load_price_series(con)
    finally:
        con.close()

    # --- Forward returns ---
    panel_with_returns = compute_forward_returns(panel, prices, HORIZONS_TD)

    # --- Analysis ---
    primary_df, sensitivity_df = run_analysis(panel_with_returns, joint_adequacy)

    # --- Invariant checks ---
    check_output_invariants(primary_df, joint_adequacy)

    # --- Write outputs ---
    primary_path = OUTPUT_DIR / "a3_primary_inference.parquet"
    primary_df.to_parquet(primary_path, index=False)
    log.info("Written: %s (%d rows)", primary_path, len(primary_df))

    sensitivity_path: Path | None = None
    if not sensitivity_df.empty:
        sensitivity_path = OUTPUT_DIR / "a3_sensitivity_block_length.parquet"
        sensitivity_df.to_parquet(sensitivity_path, index=False)
        log.info("Written: %s (%d rows)", sensitivity_path, len(sensitivity_df))

    # --- Manifest ---
    manifest = build_manifest(
        primary_path=primary_path,
        sensitivity_path=sensitivity_path,
        joint_adequacy=joint_adequacy,
        p0b_manifest=p0b_manifest,
        started_at=started_at,
        git_head=git_head,
    )
    manifest_path = OUTPUT_DIR / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    log.info("Written: %s", manifest_path)

    # --- Summary ---
    log.info("=== A-3 complete ===")
    log.info("Full inference cells: %s", manifest["full_inference_cells"])
    full_rows = primary_df[primary_df["inference_status"] == "FULL"]
    if not full_rows.empty:
        log.info("\n%s", full_rows[
            ["regime", "near_limit_up", "horizon_td",
             "delta_obs", "ci_lo", "ci_hi", "bootstrap_p_value", "n_eff"]
        ].to_string(index=False))


if __name__ == "__main__":
    main()
