#!/usr/bin/env python3
# scripts/run_r8_phase1_a1.py
"""R8 Phase 1 A-1 RS_T3 Hold Benchmark — v0.1.0.

Produces the A-1 descriptive anchor benchmark: theta_base = mean forward
return of Baseline_1 (RS_T3 non-R8 stocks on R8 event dates), stratified
by regime x near_limit_up x horizon.

Governance:
  - Estimand: theta_base only (descriptive uncertainty, no hypothesis test,
    no p-value).
  - Universe: ADR-R8P1-002 Construction C, Baseline_1.
  - Panel SQL: identical CTE structure to run_r8_phase1_a3.py; baseline_1
    rows selected only.
  - Forward return: adj_close[T+h] / adj_open[T+1] - 1, computed via
    Python dict-lookup on trading calendar (same method as A-3).
  - Inference: stationary date-level block bootstrap, Option X
    (pure Baseline_1 date pool per cell x horizon; no joint resampling).
  - Cell gate: joint adequacy = weaker_of(D-2A, D-2B Baseline_1).
  - Cross-check: A-1 theta_base_mean must be within 1e-9 of A-3
    baseline_mean_return for matching cells (same panel snapshot).

Outputs:
  data/_storage/r8_phase1_a1/v0.1.0/
    a1_primary.parquet            (all cells x horizons, L=20)
    a1_sensitivity_block.parquet  (PASS cells, L={5,10,20,40})
    manifest.json

Status: all findings PROVISIONAL per lifecycle spec AC-6.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants — locked per ADR-R8P1-002, lifecycle spec, session decisions
# ---------------------------------------------------------------------------

DB_PATH    = Path("data/_storage/helios.duckdb")
P0B_DIR    = Path("data/_storage/r8_phase1_cell_adequacy/v0.1.1")
A3_DIR     = Path("data/_storage/r8_phase1_a3/v0.1.0")
OUTPUT_DIR = Path("data/_storage/r8_phase1_a1/v0.1.0")

FORWARD_RETURN_FORMULA = "adj_close[T+h] / adj_open[T+1] - 1"
HORIZONS_TD: list[int] = [1, 5, 10, 20]

BOOTSTRAP_REPLICATIONS: int  = 5_000
BLOCK_LENGTH_PRIMARY: int    = 20
BLOCK_LENGTHS_SENSITIVITY: list[int] = [5, 10, 20, 40]
BOOTSTRAP_SEED: int          = 42
CI_ALPHA: float              = 0.05   # 95% CI

ADR_R8P1_002_VERSION = "v0.1.0"
P0B_SPEC_VERSION     = "v0.1.1"
SCRIPT_VERSION       = "v0.1.0"

PASS_THRESHOLD        = 100
DIRECTIONAL_THRESHOLD = 30

PASS             = "PASS"
DIRECTIONAL_ONLY = "DIRECTIONAL_ONLY"
INSUFFICIENT     = "INSUFFICIENT"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Panel SQL — identical CTE structure to run_r8_phase1_a3.py
# Final SELECT returns baseline_1 rows only.
# ---------------------------------------------------------------------------

_PANEL_SQL = """
WITH
price_lagged AS (
    SELECT
        stock_id,
        CAST(date AS DATE)                                  AS date,
        CAST(adj_open  AS DOUBLE)                           AS adj_open,
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
    near_limit_up
FROM baseline_1
WHERE near_limit_up IS NOT NULL
ORDER BY date, stock_id
"""

_FORWARD_PRICE_SQL = """
SELECT
    stock_id,
    CAST(date AS DATE)        AS date,
    CAST(adj_open  AS DOUBLE) AS adj_open,
    CAST(adj_close AS DOUBLE) AS adj_close
FROM listed_market_daily_price_adj
"""

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_baseline_panel(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Load Baseline_1 universe from DuckDB using A-3-identical CTE structure.

    Returns:
        DataFrame with columns: stock_id, date, regime, near_limit_up.

    Raises:
        RuntimeError: If result is empty.
    """
    log.info("Loading Baseline_1 panel from DuckDB ...")
    df = con.execute(_PANEL_SQL).fetchdf()
    df["date"] = pd.to_datetime(df["date"]).dt.date

    if df.empty:
        raise RuntimeError(
            "Baseline_1 panel query returned empty DataFrame. "
            "Check that D_R8 is non-empty and bullish_features is populated."
        )
    log.info(
        "Baseline_1 panel: %d rows, %d unique dates, %d unique stocks",
        len(df), df["date"].nunique(), df["stock_id"].nunique(),
    )
    return df


def load_price_series(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Load full adj_open and adj_close series for forward return calculation.

    Returns:
        DataFrame indexed by (stock_id, date).
    """
    log.info("Loading price series ...")
    df = con.execute(_FORWARD_PRICE_SQL).fetchdf()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df.set_index(["stock_id", "date"]).sort_index()


# ---------------------------------------------------------------------------
# Forward return — same dict-lookup method as run_r8_phase1_a3.py
# ---------------------------------------------------------------------------


def compute_forward_returns(
    panel: pd.DataFrame,
    prices: pd.DataFrame,
    horizons: list[int],
) -> pd.DataFrame:
    """Attach forward returns for each horizon to the panel.

    Formula (locked per lifecycle spec):
        forward_return[T+h] = adj_close[T+h] / adj_open[T+1] - 1

    Implementation is identical to run_r8_phase1_a3.py to ensure
    bit-identical point estimates on the same panel snapshot.
    Column names: fwd_{h}td (e.g. fwd_10td).

    Args:
        panel: Baseline_1 rows with columns [stock_id, date, ...].
        prices: Price series indexed by (stock_id, date).
        horizons: Forward return horizons in trading days.

    Returns:
        panel with added columns fwd_{h}td for each h in horizons.
    """
    log.info("Building sorted trading calendar ...")
    all_dates = np.array(
        sorted(prices.index.get_level_values("date").unique())
    )
    n_cal = len(all_dates)
    date_to_pos: dict = {d: i for i, d in enumerate(all_dates)}

    adj_open_lookup:  dict = prices["adj_open"].to_dict()
    adj_close_lookup: dict = prices["adj_close"].to_dict()

    result = panel.copy()
    signal_positions = result["date"].map(date_to_pos)

    for h in horizons:
        col    = f"fwd_{h}td"
        t1_pos = signal_positions + 1
        th_pos = signal_positions + h
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
            stock     = stocks[i]
            open_val  = adj_open_lookup.get((stock, t1_dates[i]))
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
# Adequacy helpers
# ---------------------------------------------------------------------------


def _classify(n_unique_dates: int) -> str:
    """Map n_unique_dates to adequacy classification string."""
    if n_unique_dates >= PASS_THRESHOLD:
        return PASS
    if n_unique_dates >= DIRECTIONAL_THRESHOLD:
        return DIRECTIONAL_ONLY
    return INSUFFICIENT


def _weaker_of(a: str, b: str) -> str:
    """Return the weaker of two adequacy classification strings."""
    rank = {PASS: 2, DIRECTIONAL_ONLY: 1, INSUFFICIENT: 0}
    return a if rank.get(a, -1) <= rank.get(b, -1) else b


def _propagate_reason(cls: str) -> str | None:
    """Return locked must_propagate_reason per P0-B §Reason Encoding."""
    if cls == INSUFFICIENT:
        return "n_unique_dates<30"
    if cls == DIRECTIONAL_ONLY:
        return "30<=n_unique_dates<100"
    return None


def load_joint_adequacy(
    p0b_dir: Path,
) -> dict[tuple[str, int], dict[str, Any]]:
    """Build (regime, nlu) -> joint adequacy metadata from P0-B parquets.

    Joint classification = weaker_of(D-2A treatment-side, D-2B Baseline_1).
    Classification is recomputed from n_unique_dates (authoritative over
    stored string), consistent with A-3 derive_joint_adequacy().

    Args:
        p0b_dir: P0-B v0.1.1 output directory.

    Returns:
        Dict keyed by (regime, near_limit_up).

    Raises:
        RuntimeError: If required P0-B files are missing or D-2B is empty.
    """
    d2a_path = p0b_dir / "d2a_a3_support.parquet"
    d2b_path = p0b_dir / "d2b_baseline_adequacy.parquet"
    for p in (d2a_path, d2b_path):
        if not p.exists():
            raise RuntimeError(f"Required P0-B output not found: {p}")

    d2a     = pd.read_parquet(d2a_path)
    d2b_all = pd.read_parquet(d2b_path)
    d2b     = d2b_all[d2b_all["baseline_universe"] == "Baseline_1"].copy()

    if d2b.empty:
        raise RuntimeError("D-2B has no rows with baseline_universe='Baseline_1'.")

    # Recompute from n_unique_dates — authoritative, matches A-3 convention
    d2a["_cls"] = d2a["n_unique_dates"].apply(_classify)
    d2b["_cls"] = d2b["n_unique_dates"].apply(_classify)

    d2a_map = {
        (row["regime"], int(row["near_limit_up"])): row["_cls"]
        for _, row in d2a.iterrows()
    }
    d2b_map = {
        (row["regime"], int(row["near_limit_up"])): row["_cls"]
        for _, row in d2b.iterrows()
    }

    all_keys = set(d2a_map) | set(d2b_map)
    result: dict[tuple[str, int], dict[str, Any]] = {}
    for key in all_keys:
        cls_a = d2a_map.get(key, INSUFFICIENT)
        cls_b = d2b_map.get(key, INSUFFICIENT)
        joint  = _weaker_of(cls_a, cls_b)
        reason = _propagate_reason(joint)
        result[key] = {
            "d2a_classification":    cls_a,
            "d2b_classification":    cls_b,
            "joint_adequacy":        joint,
            "must_propagate":        joint != PASS,
            "must_propagate_reason": reason,
        }

    log.info("Joint adequacy map: %d cells", len(result))
    for (regime, nlu), info in sorted(result.items()):
        log.info(
            "  (%s, nlu=%d): D-2A=%s D-2B=%s joint=%s",
            regime, nlu,
            info["d2a_classification"],
            info["d2b_classification"],
            info["joint_adequacy"],
        )
    return result


# ---------------------------------------------------------------------------
# Bootstrap — stationary block, Option X (baseline_1 date pool only)
# ---------------------------------------------------------------------------


def _stationary_bootstrap_obs_weighted(
    unique_dates: np.ndarray,
    date_to_returns: dict[Any, np.ndarray],
    block_length: float,
    n_replications: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Return bootstrap distribution of observation-weighted means (Politis-Romano).

    Resampling unit: date (preserves intra-date clustering).
    Replicate statistic: mean(all observations on resampled dates).

    This matches the ADR-R8P1-002 D6 event-level estimand and is consistent
    with A-3's _delta_stat() which uses mean(all baseline observations) without
    date-level grouping. Using date-means as the replicate statistic would
    produce a date-weighted estimand inconsistent with theta_base_mean.

    Args:
        unique_dates: Sorted array of distinct dates in this cell x horizon.
        date_to_returns: Mapping from date to array of all returns on that date.
        block_length: Mean block length L (geometric distribution).
        n_replications: B.
        rng: Pre-seeded NumPy Generator.

    Returns:
        Array of shape (n_replications,) — bootstrap distribution of theta_base.
    """
    n_dates = len(unique_dates)
    p_end = 1.0 / block_length
    boot_means = np.empty(n_replications, dtype=np.float64)

    for b in range(n_replications):
        # Resample date indices via stationary (geometric) block bootstrap
        date_indices = np.empty(n_dates, dtype=np.int32)
        idx = 0
        while idx < n_dates:
            start   = int(rng.integers(0, n_dates))
            geo_len = int(rng.geometric(p_end))
            for k in range(geo_len):
                if idx >= n_dates:
                    break
                date_indices[idx] = (start + k) % n_dates
                idx += 1

        # Expand all observations on the resampled dates
        sampled_returns = np.concatenate(
            [date_to_returns[unique_dates[i]] for i in date_indices]
        )
        boot_means[b] = sampled_returns.mean()

    return boot_means


def bootstrap_theta_base(
    cell_df: pd.DataFrame,
    horizon_col: str,
    block_length: int,
    n_replications: int,
    rng: np.random.Generator,
) -> dict[str, float]:
    """Compute bootstrap SE, percentile CI, n_eff for one cell x horizon.

    Estimand: observation-weighted theta_base = mean(all Baseline_1 returns),
    consistent with ADR-R8P1-002 D6 and A-3 baseline_mean_return.

    Resampling: date-level stationary block bootstrap (Option X — pure
    Baseline_1 date pool). Each replicate expands all observations on
    resampled dates before taking the mean, preserving estimand consistency.

    n_eff = n_dates / VIF; VIF = (bootstrap_se / naive_se)^2.
    naive_se uses per-date means as the base unit (date-clustered SE),
    which is conservative relative to IID SE and appropriate given the
    date-level resampling structure.

    Args:
        cell_df: Rows for this cell with valid (non-NaN) forward returns.
        horizon_col: Column name for this horizon (e.g. 'fwd_10td').
        block_length: L.
        n_replications: B.
        rng: Generator.

    Returns:
        Dict with keys: bootstrap_se, ci_lower_95, ci_upper_95, n_eff.
    """
    dates   = cell_df["date"].values
    returns = cell_df[horizon_col].values.astype(np.float64)

    unique_dates = np.sort(np.unique(dates))
    n_dates = len(unique_dates)

    # Pre-build date -> returns mapping once; reused across bootstrap loop
    date_to_returns: dict[Any, np.ndarray] = {
        d: returns[dates == d] for d in unique_dates
    }

    boot_dist    = _stationary_bootstrap_obs_weighted(
        unique_dates, date_to_returns, block_length, n_replications, rng
    )
    bootstrap_se = float(boot_dist.std(ddof=1))
    ci_lower     = float(np.percentile(boot_dist, 100 * CI_ALPHA / 2))
    ci_upper     = float(np.percentile(boot_dist, 100 * (1 - CI_ALPHA / 2)))

    # naive_se: date-clustered (conservative); used only for VIF/n_eff
    date_means = np.array([v.mean() for v in date_to_returns.values()], dtype=np.float64)
    naive_se = (
        float(date_means.std(ddof=1) / np.sqrt(n_dates))
        if n_dates > 1 else 0.0
    )
    if naive_se > 0 and bootstrap_se > 0:
        vif   = (bootstrap_se / naive_se) ** 2
        n_eff = float(n_dates) / vif
    else:
        n_eff = float(n_dates)

    return {
        "bootstrap_se": bootstrap_se,
        "ci_lower_95":  ci_lower,
        "ci_upper_95":  ci_upper,
        "n_eff":        n_eff,
    }


# ---------------------------------------------------------------------------
# Core analysis loop
# ---------------------------------------------------------------------------


def run_analysis(
    panel: pd.DataFrame,
    joint_adequacy_map: dict[tuple[str, int], dict[str, Any]],
    block_lengths: list[int],
    n_replications: int,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run A-1 analysis across all cells x horizons x block lengths.

    Args:
        panel: Baseline_1 rows with forward return columns fwd_{h}td.
        joint_adequacy_map: From load_joint_adequacy().
        block_lengths: Deduplicated list; first element = primary.
        n_replications: B.
        seed: RNG seed (deterministic).

    Returns:
        Tuple (primary_df, sensitivity_df).
        primary_df: All cells x horizons at block_lengths[0].
        sensitivity_df: PASS cells x horizons x all block_lengths.
    """
    rng_primary     = np.random.default_rng(seed)
    rng_sensitivity = np.random.default_rng(seed + 1)

    primary_rows: list[dict[str, Any]]     = []
    sensitivity_rows: list[dict[str, Any]] = []

    for (regime, nlu), adequacy_info in sorted(joint_adequacy_map.items()):
        joint     = adequacy_info["joint_adequacy"]
        cell_mask = (
            (panel["regime"] == regime) & (panel["near_limit_up"] == nlu)
        )
        cell_base = panel[cell_mask]

        for h in HORIZONS_TD:
            horizon_col = f"fwd_{h}td"
            if horizon_col not in cell_base.columns:
                log.warning(
                    "Column %s missing — skipping (%s, nlu=%d, h=%d)",
                    horizon_col, regime, nlu, h,
                )
                continue

            cell_h = cell_base.dropna(subset=[horizon_col])
            if cell_h.empty:
                log.warning(
                    "No valid returns: regime=%s nlu=%d horizon=%dtd — skipped.",
                    regime, nlu, h,
                )
                continue

            returns      = cell_h[horizon_col].values.astype(np.float64)
            unique_dates = np.unique(cell_h["date"].values)

            # INSUFFICIENT: row retained for artifact shape and propagation;
            # all estimates NULL — n_unique_dates < 30 is too sparse to
            # report any interpretable statistic (locked spec Option 1B).
            is_insufficient = joint == INSUFFICIENT
            row: dict[str, Any] = {
                "regime":                regime,
                "near_limit_up":         nlu,
                "horizon_td":            h,
                "n_observations":        len(returns),
                "n_dates":               len(unique_dates),
                "theta_base_mean":       None if is_insufficient else float(returns.mean()),
                "theta_base_median":     None if is_insufficient else float(np.median(returns)),
                "hit_rate":              None if is_insufficient else float((returns > 0).mean()),
                "joint_adequacy":        joint,
                "d2a_classification":    adequacy_info["d2a_classification"],
                "d2b_classification":    adequacy_info["d2b_classification"],
                "must_propagate":        adequacy_info["must_propagate"],
                "must_propagate_reason": adequacy_info["must_propagate_reason"],
                "block_length_primary":  block_lengths[0],
                "bootstrap_se":          None,
                "ci_lower_95":           None,
                "ci_upper_95":           None,
                "n_eff":                 None,
            }

            if joint == PASS:
                boot = bootstrap_theta_base(
                    cell_h, horizon_col,
                    block_lengths[0], n_replications, rng_primary,
                )
                row.update(boot)
            # DIRECTIONAL_ONLY and INSUFFICIENT: no bootstrap run.
            # Per locked spec: DIRECTIONAL_ONLY outputs point estimates only
            # (mean/median/hit_rate). bootstrap_se, n_eff, CI all remain None.
            # Inference claims are PROHIBITED for these cells.

            primary_rows.append(row)

            # Sensitivity: PASS cells only, all block lengths
            if joint == PASS:
                for bl in block_lengths:
                    s_boot = bootstrap_theta_base(
                        cell_h, horizon_col, bl, n_replications, rng_sensitivity,
                    )
                    sensitivity_rows.append({
                        "regime":            regime,
                        "near_limit_up":     nlu,
                        "horizon_td":        h,
                        "block_length":      bl,
                        "n_observations":    len(returns),
                        "n_dates":           len(unique_dates),
                        "theta_base_mean":   float(returns.mean()),
                        "theta_base_median": float(np.median(returns)),
                        "hit_rate":          float((returns > 0).mean()),
                        "joint_adequacy":    joint,
                        **s_boot,
                    })

    primary_df     = pd.DataFrame(primary_rows)
    sensitivity_df = pd.DataFrame(sensitivity_rows)

    primary_cols = [
        "regime", "near_limit_up", "horizon_td",
        "n_observations", "n_dates",
        "theta_base_mean", "theta_base_median", "hit_rate",
        "bootstrap_se", "ci_lower_95", "ci_upper_95", "n_eff",
        "joint_adequacy", "d2a_classification", "d2b_classification",
        "must_propagate", "must_propagate_reason",
        "block_length_primary",
    ]
    sensitivity_cols = [
        "regime", "near_limit_up", "horizon_td", "block_length",
        "n_observations", "n_dates",
        "theta_base_mean", "theta_base_median", "hit_rate",
        "bootstrap_se", "ci_lower_95", "ci_upper_95", "n_eff",
        "joint_adequacy",
    ]
    primary_df = primary_df[
        [c for c in primary_cols if c in primary_df.columns]
    ]
    if not sensitivity_df.empty:
        sensitivity_df = sensitivity_df[
            [c for c in sensitivity_cols if c in sensitivity_df.columns]
        ]
    return primary_df, sensitivity_df


# ---------------------------------------------------------------------------
# Output invariants
# ---------------------------------------------------------------------------


def check_output_invariants(primary_df: pd.DataFrame) -> None:
    """Verify output invariants before writing to disk.

    INV-1: Each (regime, near_limit_up, horizon_td) appears exactly once.
    INV-2: PASS rows have non-null CI fields.
    INV-3: INSUFFICIENT rows have null CI fields.
    INV-4: n_eff > 0 for non-INSUFFICIENT rows where n_eff is not null.
    INV-5: hit_rate in [0, 1].
    INV-6: n_observations >= 1.

    Raises:
        RuntimeError: On any invariant violation.
    """
    key_cols = ["regime", "near_limit_up", "horizon_td"]

    if primary_df.duplicated(subset=key_cols).sum() > 0:
        raise RuntimeError("INV-1 FAILED: duplicate (regime, nlu, horizon) rows.")

    pass_rows  = primary_df[primary_df["joint_adequacy"] == PASS]
    insuf_rows = primary_df[primary_df["joint_adequacy"] == INSUFFICIENT]

    if not pass_rows.empty:
        ci_null = pass_rows[["ci_lower_95", "ci_upper_95"]].isnull().any(axis=1)
        if ci_null.any():
            raise RuntimeError(
                f"INV-2 FAILED: {ci_null.sum()} PASS rows with null CI."
            )

    if not insuf_rows.empty:
        ci_nn = insuf_rows[["ci_lower_95", "ci_upper_95"]].notnull().any(axis=1)
        if ci_nn.any():
            raise RuntimeError(
                f"INV-3 FAILED: {ci_nn.sum()} INSUFFICIENT rows with non-null CI."
            )

    # INV-3b: INSUFFICIENT rows must have null values for all estimate columns.
    # Retained for artifact shape only; any non-null estimate is a governance
    # violation (locked spec Option 1B).
    _insufficient_value_cols = [
        "theta_base_mean", "theta_base_median", "hit_rate",
        "bootstrap_se", "ci_lower_95", "ci_upper_95", "n_eff",
    ]
    if not insuf_rows.empty:
        present_cols = [c for c in _insufficient_value_cols if c in insuf_rows.columns]
        if insuf_rows[present_cols].notnull().any(axis=None):
            raise RuntimeError(
                "INV-3b FAILED: INSUFFICIENT rows must not expose any estimates "
                "(theta_base_mean / median / hit_rate / bootstrap_se / CI / n_eff)."
            )

    # INV-4: n_eff must be positive for PASS rows only.
    # DIRECTIONAL_ONLY rows have n_eff=None per locked spec (Option A).
    if "n_eff" in pass_rows.columns:
        bad = pass_rows["n_eff"].dropna()
        if (bad <= 0).any():
            raise RuntimeError("INV-4 FAILED: n_eff <= 0 in PASS rows.")

    # INV-4b: DIRECTIONAL_ONLY rows must have null n_eff (enforce Option A).
    do_rows = primary_df[primary_df["joint_adequacy"] == DIRECTIONAL_ONLY]
    if not do_rows.empty and "n_eff" in do_rows.columns:
        if do_rows["n_eff"].notnull().any():
            raise RuntimeError(
                "INV-4b FAILED: DIRECTIONAL_ONLY rows have non-null n_eff "
                "(violates Option A spec)."
            )

    valid_hit = primary_df["hit_rate"].dropna()
    if ((valid_hit < 0) | (valid_hit > 1)).any():
        raise RuntimeError("INV-5 FAILED: hit_rate outside [0, 1] (non-null rows).")

    if (primary_df["n_observations"] < 1).any():
        raise RuntimeError("INV-6 FAILED: n_observations < 1.")

    log.info("Output invariants INV-1 through INV-6: PASS.")


# ---------------------------------------------------------------------------
# Cross-check against A-3
# ---------------------------------------------------------------------------


def crosscheck_against_a3(
    primary_df: pd.DataFrame,
    a3_dir: Path,
    tolerance: float = 1e-9,
) -> str:
    """Assert A-1 theta_base_mean == A-3 baseline_mean_return for common cells.

    Checks point estimate identity only (not bootstrap distribution).
    Bit-identity requires both scripts to have used the same panel snapshot.

    Args:
        primary_df: A-1 primary output.
        a3_dir: Directory containing a3_primary_inference.parquet.
        tolerance: Maximum allowed absolute difference.

    Returns:
        Status string: one of
          "PASSED"
          "SKIPPED_A3_NOT_FOUND"
          "SKIPPED_COLUMN_MISSING"
          "SKIPPED_NO_COMMON_CELLS"

    Raises:
        RuntimeError: If any matching cell x horizon pair fails the check.
    """
    a3_path = a3_dir / "a3_primary_inference.parquet"
    if not a3_path.exists():
        log.warning(
            "A-3 artifact not found at %s — skipping cross-check.", a3_path
        )
        return "SKIPPED_A3_NOT_FOUND"

    a3 = pd.read_parquet(a3_path)
    if "baseline_mean_return" not in a3.columns:
        log.warning(
            "A-3 parquet missing 'baseline_mean_return' — skipping cross-check."
        )
        return "SKIPPED_COLUMN_MISSING"

    merge_keys = ["regime", "near_limit_up", "horizon_td"]
    merged = primary_df.merge(
        a3[merge_keys + ["baseline_mean_return"]],
        on=merge_keys,
        how="inner",
    )
    if merged.empty:
        log.warning("No common cells between A-1 and A-3 for cross-check.")
        return "SKIPPED_NO_COMMON_CELLS"

    # Exclude INSUFFICIENT rows: theta_base_mean is null by spec (Option 1B).
    # NaN - float = NaN, which silently passes diff > tolerance; these rows
    # carry no point estimate and must not be included in the check.
    merged = merged[merged["theta_base_mean"].notnull()]
    if merged.empty:
        log.warning(
            "All common cells have null theta_base_mean (all INSUFFICIENT) "
            "— no comparable rows for cross-check."
        )
        return "SKIPPED_NO_COMPARABLE_ROWS"

    diff       = (merged["theta_base_mean"] - merged["baseline_mean_return"]).abs()
    violations = merged[diff > tolerance]
    if not violations.empty:
        raise RuntimeError(
            f"A-1/A-3 cross-check FAILED: {len(violations)} cell x horizon pairs "
            f"exceed tolerance {tolerance}.\n"
            + violations[
                merge_keys + ["theta_base_mean", "baseline_mean_return"]
            ].to_string()
        )
    log.info(
        "A-1/A-3 cross-check PASSED: %d matching cells within tolerance %s.",
        len(merged), tolerance,
    )
    return "PASSED"


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    """Return SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(
    primary_path: Path,
    sensitivity_path: Path,
    p0b_dir: Path,
    baseline_n_rows: int,
    baseline_n_dates: int,
    run_timestamp: str,
    crosscheck_status: str,
) -> dict[str, Any]:
    """Build A-1 manifest per ADR-R8P1-001 provenance discipline.

    Args:
        primary_path: Written a1_primary.parquet.
        sensitivity_path: Written a1_sensitivity_block.parquet.
        p0b_dir: P0-B output directory (for snapshot hash).
        baseline_n_rows: Total Baseline_1 observation count.
        baseline_n_dates: Unique dates in Baseline_1.
        run_timestamp: ISO-8601 UTC run timestamp.
        crosscheck_status: Result of A-1/A-3 cross-check
            (PASSED / SKIPPED_* / SKIPPED_BY_FLAG).

    Returns:
        Manifest dict.
    """
    p0b_snapshot_hash = "UNKNOWN"
    p0b_manifest_path = p0b_dir / "manifest.json"
    if p0b_manifest_path.exists():
        with open(p0b_manifest_path) as f:
            p0b_manifest = json.load(f)
        p0b_snapshot_hash = p0b_manifest.get(
            "p0b_panel_snapshot_hash",
            p0b_manifest.get("panel_snapshot_hash", "UNKNOWN"),
        )

    return {
        "script":                  "scripts/run_r8_phase1_a1.py",
        "script_version":          SCRIPT_VERSION,
        "run_timestamp_utc":       run_timestamp,
        "estimand":                "theta_base_only",
        "inference_type":          "descriptive_uncertainty",
        "bootstrap_method":        "stationary",
        "resampling_unit":         "trading_date",
        "resampling_pool":         "baseline_1_date_pool",
        "joint_resample":          False,
        "block_length_primary":    BLOCK_LENGTH_PRIMARY,
        "block_length_sensitivity": BLOCK_LENGTHS_SENSITIVITY,
        "replications":            BOOTSTRAP_REPLICATIONS,
        "ci_method":               "percentile",
        "p_value":                 "none",
        "n_eff_reference_unit":    "baseline_1_date_pool",
        "seed":                    BOOTSTRAP_SEED,
        "regime_stratified":       True,
        "horizons_td":             HORIZONS_TD,
        "forward_return_formula":  FORWARD_RETURN_FORMULA,
        "universe":                "Baseline_1",
        "adr_r8p1_002_version":    ADR_R8P1_002_VERSION,
        "p0b_spec_version":        P0B_SPEC_VERSION,
        "p0b_panel_snapshot_hash": p0b_snapshot_hash,
        "baseline_n_observations": baseline_n_rows,
        "baseline_n_dates":        baseline_n_dates,
        "findings_status":         "PROVISIONAL",
        "crosscheck_a3_status":    crosscheck_status,
        "output_files": {
            "a1_primary":            str(primary_path),
            "a1_sensitivity_block":  str(sensitivity_path),
            "a1_primary_sha256":     _sha256(primary_path),
            "a1_sensitivity_sha256": _sha256(sensitivity_path),
        },
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="R8 Phase 1 A-1 RS_T3 Hold Benchmark."
    )
    parser.add_argument(
        "--db", type=Path, default=DB_PATH,
        help="DuckDB path (default: %(default)s).",
    )
    parser.add_argument(
        "--p0b-dir", type=Path, default=P0B_DIR,
        help="P0-B v0.1.1 output directory.",
    )
    parser.add_argument(
        "--a3-dir", type=Path, default=A3_DIR,
        help="A-3 output directory for cross-check.",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=OUTPUT_DIR,
        help="Output directory for A-1 artifacts.",
    )
    parser.add_argument(
        "--replications", type=int, default=BOOTSTRAP_REPLICATIONS,
        help="Bootstrap replications (default: %(default)d).",
    )
    parser.add_argument(
        "--skip-crosscheck", action="store_true",
        help="Skip A-1/A-3 cross-check (use if A-3 artifact unavailable).",
    )
    return parser.parse_args()


def main() -> None:
    """Run A-1 RS_T3 Hold Benchmark analysis."""
    args = parse_args()
    run_timestamp = datetime.now(timezone.utc).isoformat()

    log.info("=== R8 Phase 1 A-1 RS_T3 Hold Benchmark %s ===", SCRIPT_VERSION)
    log.info("DB: %s", args.db)
    log.info("P0-B dir: %s", args.p0b_dir)
    log.info("Output dir: %s", args.output_dir)

    # --- Adequacy ---
    joint_adequacy_map = load_joint_adequacy(args.p0b_dir)

    # --- Load data ---
    if not args.db.exists():
        raise RuntimeError(f"DuckDB not found: {args.db}")

    con = duckdb.connect(str(args.db), read_only=True)
    try:
        panel  = load_baseline_panel(con)
        prices = load_price_series(con)
    finally:
        con.close()

    panel = compute_forward_returns(panel, prices, HORIZONS_TD)

    baseline_n_rows  = len(panel)
    baseline_n_dates = panel["date"].nunique()

    # --- Bootstrap ---
    log.info(
        "Running bootstrap: B=%d, L_primary=%d, seed=%d",
        args.replications, BLOCK_LENGTH_PRIMARY, BOOTSTRAP_SEED,
    )
    seen: set[int] = set()
    ordered_bls: list[int] = []
    for bl in [BLOCK_LENGTH_PRIMARY] + BLOCK_LENGTHS_SENSITIVITY:
        if bl not in seen:
            ordered_bls.append(bl)
            seen.add(bl)

    primary_df, sensitivity_df = run_analysis(
        panel=panel,
        joint_adequacy_map=joint_adequacy_map,
        block_lengths=ordered_bls,
        n_replications=args.replications,
        seed=BOOTSTRAP_SEED,
    )
    log.info("Primary output: %d rows", len(primary_df))
    log.info("Sensitivity output: %d rows", len(sensitivity_df))

    # --- Invariants ---
    check_output_invariants(primary_df)

    # --- Cross-check ---
    if not args.skip_crosscheck:
        crosscheck_status = crosscheck_against_a3(primary_df, args.a3_dir)
    else:
        crosscheck_status = "SKIPPED_BY_FLAG"
        log.warning("A-1/A-3 cross-check skipped via --skip-crosscheck flag.")

    # --- Write outputs (guard against silent overwrite) ---
    args.output_dir.mkdir(parents=True, exist_ok=True)

    primary_path     = args.output_dir / "a1_primary.parquet"
    sensitivity_path = args.output_dir / "a1_sensitivity_block.parquet"
    manifest_path    = args.output_dir / "manifest.json"

    for p in (primary_path, sensitivity_path, manifest_path):
        if p.exists():
            raise RuntimeError(
                f"Output already exists: {p}. "
                "Delete manually or use a new version directory to re-run."
            )

    primary_df.to_parquet(primary_path, index=False)
    sensitivity_df.to_parquet(sensitivity_path, index=False)
    log.info("Written: %s", primary_path)
    log.info("Written: %s", sensitivity_path)

    manifest = build_manifest(
        primary_path=primary_path,
        sensitivity_path=sensitivity_path,
        p0b_dir=args.p0b_dir,
        baseline_n_rows=baseline_n_rows,
        baseline_n_dates=baseline_n_dates,
        run_timestamp=run_timestamp,
        crosscheck_status=crosscheck_status,
    )
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    log.info("Written: %s", manifest_path)

    log.info("=== A-1 complete. Findings status: PROVISIONAL (AC-6 binding) ===")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log.error("Fatal error: %s", exc, exc_info=True)
        sys.exit(1)
