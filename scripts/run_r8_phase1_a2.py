#!/usr/bin/env python3
# scripts/run_r8_phase1_a2.py
"""R8 Phase 1 A-2 RS_T3 + Pullback Benchmark — v0.1.0.

Produces the A-2 descriptive benchmark: delta_obs = theta_treat - theta_base
for Treatment_2 (R8 ∩ RS_T3 ∩ pullback) vs Baseline_2 (non-R8 RS_T3 ∩
pullback), stratified by regime x near_limit_up x horizon.

Governance:
  - Estimand: Δ_A2 = mean(Treatment_2 fwd_return) - mean(Baseline_2 fwd_return).
  - Universe: ADR-R8P1-002 Construction C + symmetric pullback filter.
      Treatment_2 := Treatment_1 where dist_above_ma20_atr < 0
      Baseline_2  := Baseline_1  where dist_above_ma20_atr < 0
  - Mode: DESCRIPTIVE ONLY. No bootstrap, no CI, no p-value, no n_eff.
    Rationale: pre-run cell adequacy audit confirmed 0 PASS cells;
    Treatment_2 n_dates peaks at 38 (bull, nlu=0). Bootstrap inference
    is not warranted; sparsity is itself the substantive Phase 1 finding.
  - Cell gate: inline adequacy computed from Treatment_2 and Baseline_2
    date counts (no external P0-B dependency). Joint = weaker_of(treat, base).
  - DIRECTIONAL_ONLY: theta_treat, theta_base, delta_obs reported; all
    bootstrap fields NULL.
  - INSUFFICIENT: row retained; counts + adequacy only; estimates NULL.
  - No sensitivity grid (no bootstrap → sensitivity has no meaning).

Outputs:
  data/_storage/r8_phase1_a2/v0.1.0/
    a2_primary.parquet
    manifest.json

Status: all findings PROVISIONAL per lifecycle spec AC-6.
Phase 1 A-2 finding: Treatment_2 too sparse for inferential evaluation
under current sample (0 PASS cells, max treatment n_dates = 38).
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
# Constants
# ---------------------------------------------------------------------------

DB_PATH    = Path("data/_storage/helios.duckdb")
OUTPUT_DIR = Path("data/_storage/r8_phase1_a2/v0.1.0")

FORWARD_RETURN_FORMULA = "adj_close[T+h] / adj_open[T+1] - 1"
HORIZONS_TD: list[int] = [1, 5, 10, 20]

ADR_R8P1_002_VERSION = "v0.1.0"
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
# Panel SQL — A-3-identical CTE + pullback filter on both sides (ADR β)
# Returns treatment_2 and baseline_2 rows with universe tag.
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
treatment_1 AS (
    SELECT * FROM r8_events WHERE rs_tertile = 'RS_T3'
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
),
-- Symmetric pullback filter (ADR-R8P1-002 interpretation β):
-- dist_above_ma20_atr < 0 applied independently per row on both sides.
treatment_2 AS (
    SELECT * FROM treatment_1
    WHERE dist_above_ma20_atr < 0
),
baseline_2 AS (
    SELECT * FROM baseline_1
    WHERE dist_above_ma20_atr < 0
)
SELECT
    stock_id,
    date,
    regime,
    near_limit_up,
    CAST(universe AS VARCHAR) AS universe
FROM (
    SELECT *, 'treatment_2' AS universe FROM treatment_2
    WHERE near_limit_up IS NOT NULL
    UNION ALL
    SELECT *, 'baseline_2' AS universe FROM baseline_2
    WHERE near_limit_up IS NOT NULL
)
ORDER BY universe, date, stock_id
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


def load_panel(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Load Treatment_2 and Baseline_2 universe from DuckDB.

    Uses A-3-identical CTE structure with symmetric pullback filter added.

    Returns:
        DataFrame with columns: stock_id, date, regime, near_limit_up, universe.

    Raises:
        RuntimeError: If either universe is empty.
    """
    log.info("Loading Treatment_2 + Baseline_2 panel from DuckDB ...")
    df = con.execute(_PANEL_SQL).fetchdf()
    df["date"] = pd.to_datetime(df["date"]).dt.date

    n_treat = (df["universe"] == "treatment_2").sum()
    n_base  = (df["universe"] == "baseline_2").sum()
    log.info(
        "Panel: %d treatment_2 rows, %d baseline_2 rows, "
        "%d treatment dates, %d baseline dates",
        n_treat, n_base,
        df.loc[df["universe"] == "treatment_2", "date"].nunique(),
        df.loc[df["universe"] == "baseline_2",  "date"].nunique(),
    )

    if n_treat == 0:
        raise RuntimeError(
            "Treatment_2 is empty — check dist_above_ma20_atr availability "
            "and pullback filter."
        )
    if n_base == 0:
        raise RuntimeError("Baseline_2 is empty.")
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
# Forward return — identical dict-lookup method to A-1 / A-3
# ---------------------------------------------------------------------------


def compute_forward_returns(
    panel: pd.DataFrame,
    prices: pd.DataFrame,
    horizons: list[int],
) -> pd.DataFrame:
    """Attach forward returns for each horizon to the panel.

    Formula (locked per lifecycle spec):
        forward_return[T+h] = adj_close[T+h] / adj_open[T+1] - 1

    Column names: fwd_{h}td — matching A-1 / A-3 convention.

    Args:
        panel: Treatment_2 + Baseline_2 rows.
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
        n_treat_valid = result.loc[
            result["universe"] == "treatment_2", col
        ].notna().sum()
        n_base_valid = result.loc[
            result["universe"] == "baseline_2", col
        ].notna().sum()
        log.info(
            "Horizon %dtd: treatment_2=%d valid, baseline_2=%d valid",
            h, n_treat_valid, n_base_valid,
        )
    return result


# ---------------------------------------------------------------------------
# Adequacy — inline compute, no external P0-B dependency
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
    """Return locked must_propagate_reason string."""
    if cls == INSUFFICIENT:
        return "n_unique_dates<30"
    if cls == DIRECTIONAL_ONLY:
        return "30<=n_unique_dates<100"
    return None


def build_adequacy_map(
    panel: pd.DataFrame,
) -> dict[tuple[str, int], dict[str, Any]]:
    """Compute inline cell adequacy from Treatment_2 and Baseline_2 date counts.

    Joint adequacy is the weaker of Treatment_2 and Baseline_2 classifications.
    Both sides contribute: a baseline-side shortfall degrades the joint
    classification even if treatment-side dates are sufficient.

    Args:
        panel: Combined Treatment_2 + Baseline_2 rows.

    Returns:
        Dict keyed by (regime, near_limit_up) with adequacy metadata.
    """
    treat = panel[panel["universe"] == "treatment_2"]
    base  = panel[panel["universe"] == "baseline_2"]

    # Count unique dates per cell
    treat_dates = (
        treat.groupby(["regime", "near_limit_up"])["date"]
        .nunique().rename("treat_n_dates")
    )
    base_dates = (
        base.groupby(["regime", "near_limit_up"])["date"]
        .nunique().rename("base_n_dates")
    )

    all_keys: set[tuple[str, int]] = set()
    for regime, nlu in treat.groupby(["regime", "near_limit_up"]).groups:
        all_keys.add((regime, int(nlu)))
    for regime, nlu in base.groupby(["regime", "near_limit_up"]).groups:
        all_keys.add((regime, int(nlu)))

    result: dict[tuple[str, int], dict[str, Any]] = {}
    for key in all_keys:
        regime, nlu = key
        t_dates = int(treat_dates.get((regime, nlu), 0))
        b_dates = int(base_dates.get((regime, nlu), 0))
        cls_t   = _classify(t_dates)
        cls_b   = _classify(b_dates)
        joint   = _weaker_of(cls_t, cls_b)
        reason  = _propagate_reason(joint)
        result[key] = {
            "treat_n_dates":         t_dates,
            "base_n_dates":          b_dates,
            "treat_adequacy":        cls_t,
            "base_adequacy":         cls_b,
            "joint_adequacy":        joint,
            "must_propagate":        joint != PASS,
            "must_propagate_reason": reason,
        }

    log.info("A-2 inline adequacy map: %d cells", len(result))
    for (regime, nlu), info in sorted(result.items()):
        log.info(
            "  (%s, nlu=%d): treat_n_dates=%d (%s)  base_n_dates=%d (%s)  joint=%s",
            regime, nlu,
            info["treat_n_dates"], info["treat_adequacy"],
            info["base_n_dates"],  info["base_adequacy"],
            info["joint_adequacy"],
        )
    return result


# ---------------------------------------------------------------------------
# Core analysis — descriptive only, no bootstrap
# ---------------------------------------------------------------------------


def run_analysis(
    panel: pd.DataFrame,
    adequacy_map: dict[tuple[str, int], dict[str, Any]],
) -> pd.DataFrame:
    """Compute A-2 descriptive statistics across all cells x horizons.

    No bootstrap. Output contract:
      PASS           : full fields (expected count = 0 under current sample)
      DIRECTIONAL_ONLY: theta_treat, theta_base, delta_obs; bootstrap fields NULL
      INSUFFICIENT   : counts + adequacy only; all estimates NULL

    Args:
        panel: Treatment_2 + Baseline_2 rows with fwd_{h}td columns.
        adequacy_map: From build_adequacy_map().

    Returns:
        primary_df with one row per (regime, near_limit_up, horizon_td).
    """
    treat_panel = panel[panel["universe"] == "treatment_2"]
    base_panel  = panel[panel["universe"] == "baseline_2"]

    rows: list[dict[str, Any]] = []

    for (regime, nlu), adequacy_info in sorted(adequacy_map.items()):
        joint = adequacy_info["joint_adequacy"]

        treat_mask = (
            (treat_panel["regime"] == regime)
            & (treat_panel["near_limit_up"] == nlu)
        )
        base_mask = (
            (base_panel["regime"] == regime)
            & (base_panel["near_limit_up"] == nlu)
        )
        cell_treat = treat_panel[treat_mask]
        cell_base  = base_panel[base_mask]

        for h in HORIZONS_TD:
            horizon_col = f"fwd_{h}td"

            treat_h = (
                cell_treat.dropna(subset=[horizon_col])
                if horizon_col in cell_treat.columns else cell_treat.iloc[0:0]
            )
            base_h = (
                cell_base.dropna(subset=[horizon_col])
                if horizon_col in cell_base.columns else cell_base.iloc[0:0]
            )

            is_insufficient = joint == INSUFFICIENT

            row: dict[str, Any] = {
                "regime":                regime,
                "near_limit_up":         nlu,
                "horizon_td":            h,
                # Counts always reported
                "treatment_n_observations": len(treat_h),
                "treatment_n_dates":     adequacy_info["treat_n_dates"],
                "baseline_n_observations": len(base_h),
                "baseline_n_dates":      adequacy_info["base_n_dates"],
                # Adequacy metadata always reported
                "treat_adequacy":        adequacy_info["treat_adequacy"],
                "base_adequacy":         adequacy_info["base_adequacy"],
                "joint_adequacy":        joint,
                "must_propagate":        adequacy_info["must_propagate"],
                "must_propagate_reason": adequacy_info["must_propagate_reason"],
                # Estimates — NULL for INSUFFICIENT
                "theta_treat":   None,
                "theta_base":    None,
                "delta_obs":     None,
                "treat_hit_rate": None,
                "base_hit_rate":  None,
                # Bootstrap fields — always NULL (descriptive-only mode)
                "bootstrap_se":  None,
                "ci_lower_95":   None,
                "ci_upper_95":   None,
                "bootstrap_p":   None,
                "n_eff":         None,
            }

            if not is_insufficient and not treat_h.empty and not base_h.empty:
                t_ret = treat_h[horizon_col].values.astype(np.float64)
                b_ret = base_h[horizon_col].values.astype(np.float64)
                theta_treat = float(t_ret.mean())
                theta_base  = float(b_ret.mean())
                row["theta_treat"]    = theta_treat
                row["theta_base"]     = theta_base
                row["delta_obs"]      = theta_treat - theta_base
                row["treat_hit_rate"] = float((t_ret > 0).mean())
                row["base_hit_rate"]  = float((b_ret > 0).mean())

            rows.append(row)

    df = pd.DataFrame(rows)

    col_order = [
        "regime", "near_limit_up", "horizon_td",
        "treatment_n_observations", "treatment_n_dates",
        "baseline_n_observations",  "baseline_n_dates",
        "theta_treat", "theta_base", "delta_obs",
        "treat_hit_rate", "base_hit_rate",
        "bootstrap_se", "ci_lower_95", "ci_upper_95",
        "bootstrap_p", "n_eff",
        "joint_adequacy", "treat_adequacy", "base_adequacy",
        "must_propagate", "must_propagate_reason",
    ]
    return df[[c for c in col_order if c in df.columns]]


# ---------------------------------------------------------------------------
# Output invariants
# ---------------------------------------------------------------------------


def check_output_invariants(df: pd.DataFrame) -> None:
    """Verify output invariants before writing.

    INV-1: Each (regime, near_limit_up, horizon_td) appears exactly once.
    INV-2: INSUFFICIENT rows have null estimates.
    INV-3: Bootstrap fields are null for all rows (descriptive-only mode).
    INV-4: DIRECTIONAL_ONLY rows have non-null delta_obs when observations exist.
    INV-5: treat_hit_rate / base_hit_rate in [0, 1] (non-null only).

    Raises:
        RuntimeError: On any violation.
    """
    key_cols = ["regime", "near_limit_up", "horizon_td"]

    if df.duplicated(subset=key_cols).sum() > 0:
        raise RuntimeError("INV-1 FAILED: duplicate (regime, nlu, horizon) rows.")

    insuf = df[df["joint_adequacy"] == INSUFFICIENT]
    estimate_cols = [
        "theta_treat", "theta_base", "delta_obs",
        "treat_hit_rate", "base_hit_rate",
    ]
    if not insuf.empty:
        present = [c for c in estimate_cols if c in insuf.columns]
        if insuf[present].notnull().any(axis=None):
            raise RuntimeError(
                "INV-2 FAILED: INSUFFICIENT rows must not expose estimates."
            )

    boot_cols = ["bootstrap_se", "ci_lower_95", "ci_upper_95", "bootstrap_p", "n_eff"]
    present_boot = [c for c in boot_cols if c in df.columns]
    if df[present_boot].notnull().any(axis=None):
        raise RuntimeError(
            "INV-3 FAILED: bootstrap fields must be null in descriptive-only mode."
        )

    do_rows = df[
        (df["joint_adequacy"] == DIRECTIONAL_ONLY)
        & (df["treatment_n_observations"] > 0)
        & (df["baseline_n_observations"] > 0)
    ]
    if not do_rows.empty and do_rows["delta_obs"].isnull().any():
        raise RuntimeError(
            "INV-4 FAILED: DIRECTIONAL_ONLY rows with observations must have "
            "non-null delta_obs."
        )

    for col in ["treat_hit_rate", "base_hit_rate"]:
        if col in df.columns:
            valid = df[col].dropna()
            if ((valid < 0) | (valid > 1)).any():
                raise RuntimeError(f"INV-5 FAILED: {col} outside [0, 1].")

    # INV-6: output must contain exactly 8 cells × 4 horizons = 32 rows.
    # A-2 retains all cells (including INSUFFICIENT) for artifact shape
    # consistency. Any deviation indicates a panel or adequacy map gap.
    expected_rows = 8 * len(HORIZONS_TD)
    if len(df) != expected_rows:
        raise RuntimeError(
            f"INV-6 FAILED: expected {expected_rows} rows "
            f"(8 cells × {len(HORIZONS_TD)} horizons), got {len(df)}."
        )

    log.info("Output invariants INV-1 through INV-6: PASS.")


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


def _adequacy_table_sha256(adequacy_map: dict[tuple[str, int], dict[str, Any]]) -> str:
    """Return SHA-256 of the adequacy table for provenance tracking.

    Hashes a canonical JSON representation of the regime x near_limit_up
    cell adequacy table (treat_n_dates, base_n_dates, joint_adequacy).
    Allows downstream verification that the 0-PASS / 2-DIRECTIONAL_ONLY /
    6-INSUFFICIENT result came from the same panel snapshot.
    """
    rows = []
    for (regime, nlu), info in sorted(adequacy_map.items()):
        rows.append({
            "regime":          regime,
            "near_limit_up":   nlu,
            "treat_n_dates":   info["treat_n_dates"],
            "base_n_dates":    info["base_n_dates"],
            "joint_adequacy":  info["joint_adequacy"],
        })
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def build_manifest(
    primary_path: Path,
    panel_summary: dict[str, int],
    adequacy_summary: dict[str, int],
    adequacy_map: dict[tuple[str, int], dict[str, Any]],
    run_timestamp: str,
) -> dict[str, Any]:
    """Build A-2 manifest per ADR-R8P1-001 provenance discipline.

    Args:
        primary_path: Written a2_primary.parquet.
        panel_summary: Counts of treatment_2 / baseline_2 rows and dates.
        adequacy_summary: Count of cells by joint_adequacy classification.
        adequacy_map: Full adequacy map for SHA-256 provenance hash.
        run_timestamp: ISO-8601 UTC run timestamp.

    Returns:
        Manifest dict.
    """
    return {
        "script":                    "scripts/run_r8_phase1_a2.py",
        "script_version":            SCRIPT_VERSION,
        "run_timestamp_utc":         run_timestamp,
        "estimand":                  "delta_obs_descriptive",
        "inference_type":            "descriptive_only",
        "bootstrap":                 False,
        "bootstrap_rationale":       (
            "0 PASS cells under Treatment_2 adequacy audit; "
            "max treatment_2 n_dates = 38 (bull, nlu=0). "
            "Sparsity is the substantive Phase 1 finding."
        ),
        "pullback_filter":           "dist_above_ma20_atr < 0",
        "pullback_filter_symmetry":  "beta (symmetric — ADR-R8P1-002 locked)",
        "forward_return_formula":    FORWARD_RETURN_FORMULA,
        "horizons_td":               HORIZONS_TD,
        "adequacy_method":           "inline_from_date_counts",
        "adequacy_thresholds":       {
            "PASS":             PASS_THRESHOLD,
            "DIRECTIONAL_ONLY": DIRECTIONAL_THRESHOLD,
        },
        "adequacy_table_sha256":     _adequacy_table_sha256(adequacy_map),
        "adr_r8p1_002_version":      ADR_R8P1_002_VERSION,
        "findings_status":           "PROVISIONAL",
        "phase1_a2_finding":         (
            "Treatment_2 too sparse for inferential evaluation under current "
            "sample. No PASS cells. AC-2 satisfied via adequacy outcome: "
            "Δ_A2 cannot be estimated with sufficient date support."
        ),
        "panel_summary":             panel_summary,
        "adequacy_summary":          adequacy_summary,
        "output_files": {
            "a2_primary":          str(primary_path),
            "a2_primary_sha256":   _sha256(primary_path),
        },
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="R8 Phase 1 A-2 RS_T3 + Pullback Benchmark (descriptive only)."
    )
    parser.add_argument(
        "--db", type=Path, default=DB_PATH,
        help="DuckDB path (default: %(default)s).",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=OUTPUT_DIR,
        help="Output directory for A-2 artifacts.",
    )
    return parser.parse_args()


def main() -> None:
    """Run A-2 RS_T3 + Pullback Benchmark analysis (descriptive only)."""
    args = parse_args()
    run_timestamp = datetime.now(timezone.utc).isoformat()

    log.info(
        "=== R8 Phase 1 A-2 RS_T3 + Pullback Benchmark %s (descriptive only) ===",
        SCRIPT_VERSION,
    )
    log.info("DB: %s", args.db)
    log.info("Output dir: %s", args.output_dir)

    if not args.db.exists():
        raise RuntimeError(f"DuckDB not found: {args.db}")

    con = duckdb.connect(str(args.db), read_only=True)
    try:
        panel  = load_panel(con)
        prices = load_price_series(con)
    finally:
        con.close()

    panel = compute_forward_returns(panel, prices, HORIZONS_TD)

    # Adequacy — inline, no external dependency
    adequacy_map = build_adequacy_map(panel)

    # Panel summary for manifest
    panel_summary = {
        "treatment_2_n_obs":   int((panel["universe"] == "treatment_2").sum()),
        "treatment_2_n_dates": int(
            panel.loc[panel["universe"] == "treatment_2", "date"].nunique()
        ),
        "baseline_2_n_obs":    int((panel["universe"] == "baseline_2").sum()),
        "baseline_2_n_dates":  int(
            panel.loc[panel["universe"] == "baseline_2", "date"].nunique()
        ),
    }

    # Run descriptive analysis
    primary_df = run_analysis(panel, adequacy_map)
    log.info("Primary output: %d rows", len(primary_df))

    # Adequacy summary for manifest
    adequacy_summary = primary_df.groupby("joint_adequacy")["horizon_td"].count().to_dict()
    # Divide by 4 horizons to get cell counts
    adequacy_cell_counts = {
        k: v // len(HORIZONS_TD) for k, v in adequacy_summary.items()
    }
    log.info("Joint adequacy cell counts: %s", adequacy_cell_counts)

    # Invariants
    check_output_invariants(primary_df)

    # Write outputs — guard against silent overwrite
    args.output_dir.mkdir(parents=True, exist_ok=True)

    primary_path  = args.output_dir / "a2_primary.parquet"
    manifest_path = args.output_dir / "manifest.json"

    for p in (primary_path, manifest_path):
        if p.exists():
            raise RuntimeError(
                f"Output already exists: {p}. "
                "Delete manually or use a new version directory to re-run."
            )

    primary_df.to_parquet(primary_path, index=False)
    log.info("Written: %s", primary_path)

    manifest = build_manifest(
        primary_path=primary_path,
        panel_summary=panel_summary,
        adequacy_summary=adequacy_cell_counts,
        adequacy_map=adequacy_map,
        run_timestamp=run_timestamp,
    )
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    log.info("Written: %s", manifest_path)

    log.info(
        "=== A-2 complete. Mode: DESCRIPTIVE ONLY. "
        "Findings status: PROVISIONAL (AC-6 binding) ==="
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log.error("Fatal error: %s", exc, exc_info=True)
        sys.exit(1)
