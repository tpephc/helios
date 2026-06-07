#!/usr/bin/env python3
# scripts/run_phase2b_analysis.py
"""R8 Phase 2B Execution Bridge — v0.1.2.

Translates Phase 2A STABLE gross uplift into execution-adjusted PnL estimates
under realistic cost assumptions.

Research question:
    Does the STABLE bull-regime R8 uplift survive realistic execution friction
    under both high-uplift and low-uplift environments?

Locked constants (per r8_phase2b_spec.md v0.1.2):

    Cost model:
        COMMISSION_ENTRY    = 0.001425   (0.1425%)
        COMMISSION_EXIT     = 0.001425   (0.1425%)
        TAX_EXIT            = 0.003000   (0.3000%)
        COMMISSION_RT       = 0.005850   (round-trip, fixed)

    Slippage ladder (round-trip bps):
        S0 = 0 bps    (Phase 1 bridge, commission-only)
        S1 = 20 bps   (realistic)
        S2 = 50 bps   (moderate stress)
        S3 = 100 bps  (severe stress)

    Position sizing:
        weight = min(1/N, 0.10)
        MAX_POSITIONS = 10
        HOLDING_PERIOD_TD = 20
        OVERFLOW_SEED = 42

    Concentration scenarios (segment date ranges from Phase 2A artifact):
        A — Full Sample    : Seg 1+2+3+4
        B — Low-Uplift     : Seg 2+3
        C — High-Uplift    : Seg 1+4

Panel: Phase 1 clean-panel (commit 4a307e6), read-only DuckDB
Output: data/_storage/r8_phase2b/v0.1.0/

Usage:
    uv run python scripts/run_phase2b_analysis.py                 # dry-run (default)
    uv run python scripts/run_phase2b_analysis.py --allow-write   # persist artifacts
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path setup and Phase 1 helper imports
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.run_r8_phase1_a3 import (  # noqa: E402
    load_panel,
    load_price_series,
    compute_forward_returns,
)

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------

DB_PATH = _REPO_ROOT / "data/_storage/helios.duckdb"
PHASE2A_DIR = _REPO_ROOT / "data/_storage/r8_phase2a/v0.1.0"
OUTPUT_DIR = _REPO_ROOT / "data/_storage/r8_phase2b/v0.1.0"
SPEC_PATH = _REPO_ROOT / "research/r8_phase2b_spec.md"

# ---------------------------------------------------------------------------
# Locked SPEC constants (do not modify without SPEC amendment)
# ---------------------------------------------------------------------------

# Commission and tax (Taiwan equity standard)
COMMISSION_ENTRY: float = 0.001425
COMMISSION_EXIT: float = 0.001425
TAX_EXIT: float = 0.003000
COMMISSION_RT: float = COMMISSION_ENTRY + COMMISSION_EXIT + TAX_EXIT  # 0.005850

# Slippage ladder (D1): round-trip bps expressed as decimals
SLIPPAGE_SCENARIOS: dict[str, float] = {
    "S0": 0.0000,   # 0 bps
    "S1": 0.0020,   # 20 bps
    "S2": 0.0050,   # 50 bps
    "S3": 0.0100,   # 100 bps
}

# Position sizing (D2)
MAX_POSITIONS: int = 10
HOLDING_PERIOD_TD: int = 20
OVERFLOW_SEED: int = 42

# Target cell (inherited from Phase 1 / Phase 2A)
TARGET_REGIME: str = "bull"
TARGET_NLU: int = 0

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("r8_phase2b")


# ---------------------------------------------------------------------------
# Segment boundaries (read from Phase 2A artifact, not hardcoded)
# ---------------------------------------------------------------------------


def load_segment_boundaries() -> dict[int, tuple]:
    """Load Phase 2A segment date boundaries from artifact.

    Returns dict: segment_id -> (date_start, date_end)
    Raises FileNotFoundError if Phase 2A segments artifact is missing.
    """
    seg_path = PHASE2A_DIR / "segments/p2a1_segment_results.parquet"
    if not seg_path.exists():
        raise FileNotFoundError(
            f"Phase 2A segment artifact not found: {seg_path}\n"
            "Run Phase 2A analysis first: scripts/run_phase2a_analysis.py --allow-write"
        )
    df = pd.read_parquet(seg_path)
    boundaries = {}
    for _, row in df[["segment_id", "date_start", "date_end"]].drop_duplicates().iterrows():
        boundaries[int(row["segment_id"])] = (
            pd.Timestamp(row["date_start"]).date(),
            pd.Timestamp(row["date_end"]).date(),
        )
    log.info("Loaded segment boundaries from Phase 2A artifact:")
    for sid, (s, e) in sorted(boundaries.items()):
        log.info("  Segment %d: %s – %s", sid, s, e)
    return boundaries


# ---------------------------------------------------------------------------
# Scenario construction (D3)
# ---------------------------------------------------------------------------


def build_scenario_mask(
    treat: pd.DataFrame,
    base: pd.DataFrame,
    scenario: str,
    segments: dict[int, tuple],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Filter treatment and baseline to a concentration scenario date pool.

    Scenario A — Full Sample  : all segments (1+2+3+4)
    Scenario B — Low-Uplift   : Seg 2+3 (non-contiguous OK; union of date pools)
    Scenario C — High-Uplift  : Seg 1+4 (non-contiguous union)

    Baseline is restricted to the same date pool as treatment (date-anchored
    estimand, preserving Phase 1 counterfactual structure).
    """
    segment_sets = {
        "A": [1, 2, 3, 4],
        "B": [2, 3],
        "C": [1, 4],
    }
    if scenario not in segment_sets:
        raise ValueError(f"Unknown scenario: {scenario}. Must be A, B, or C.")

    # Build union of treatment dates from selected segments
    valid_dates: set = set()
    for sid in segment_sets[scenario]:
        s_start, s_end = segments[sid]
        seg_dates = treat[(treat["date"] >= s_start) & (treat["date"] <= s_end)]["date"]
        valid_dates.update(seg_dates.unique())

    t_scen = treat[treat["date"].isin(valid_dates)].copy()
    b_scen = base[base["date"].isin(valid_dates)].copy()

    log.info(
        "Scenario %s: %d treatment events (%d dates), %d baseline events",
        scenario, len(t_scen), t_scen["date"].nunique(), len(b_scen),
    )
    return t_scen, b_scen


# ---------------------------------------------------------------------------
# Position-level PnL simulation
# ---------------------------------------------------------------------------


def simulate_portfolio(
    treat: pd.DataFrame,
    horizon_col: str,
    overflow_method: str,
    rng: random.Random,
) -> pd.DataFrame:
    """Simulate equal-weight portfolio PnL with position constraints.

    For each signal date:
    1. Identify all qualifying R8 signals (treatment rows).
    2. If N > MAX_POSITIONS, apply overflow_method selection.
    3. Assign weight = min(1/N, 0.10) to each selected position.
    4. Portfolio return for the date = sum(weight_i * fwd_return_i).

    Returns DataFrame with columns: [date, n_signals, n_selected,
    overflow_applied, portfolio_gross_return, overflow_method].
    """
    records: list[dict] = []

    for signal_date, group in treat.groupby("date"):
        valid = group[group[horizon_col].notna()]
        n_signals = len(valid)

        if n_signals == 0:
            continue

        overflow_applied = n_signals > MAX_POSITIONS

        if overflow_applied:
            if overflow_method == "first_10":
                selected = valid.sort_values("stock_id").head(MAX_POSITIONS)
            elif overflow_method == "random_10":
                selected = valid.sample(
                    n=MAX_POSITIONS,
                    random_state=rng.randint(0, 2**31 - 1),
                )
            else:
                raise ValueError(f"Unknown overflow_method: {overflow_method}")
        else:
            selected = valid

        n_selected = len(selected)
        weight = min(1.0 / n_selected, 0.10)
        port_return = float((selected[horizon_col] * weight).sum())

        deployed_weight = weight * n_selected  # sum of all position weights

        records.append({
            "date": signal_date,
            "n_signals": n_signals,
            "n_selected": n_selected,
            "overflow_applied": overflow_applied,
            "portfolio_gross_return": port_return,
            "deployed_weight": deployed_weight,
            "overflow_method": overflow_method,
        })

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Cost application
# ---------------------------------------------------------------------------


def apply_costs(
    gross_return: float,
    slippage_rt: float,
    deployed_weight: float,
) -> dict[str, float]:
    """Decompose net return into Gross / Commission / Slippage / Net.

    Costs are scaled by deployed_weight (sum of position weights on the date).
    Per SPEC §5.1 partial-NAV model: N=3 → deployed_weight=0.30; costs are
    applied only to the deployed fraction, not to the full NAV.

    Args:
        gross_return: Portfolio gross return (NAV-weighted sum of position returns).
        slippage_rt: Round-trip slippage rate for the scenario.
        deployed_weight: Sum of position weights on this signal date (≤ 1.0).

    Returns dict with all four components (Commission and Slippage negative).
    """
    commission = -deployed_weight * COMMISSION_RT
    slippage = -deployed_weight * slippage_rt
    net = gross_return + commission + slippage
    return {
        "gross": gross_return,
        "commission": commission,
        "slippage": slippage,
        "net": net,
        "deployed_weight": deployed_weight,
    }


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------


def run_phase2b(
    treat_full: pd.DataFrame,
    base_full: pd.DataFrame,
    segments: dict[int, tuple],
) -> list[dict]:
    """Run all 3 scenarios × 4 slippage levels × 2 overflow methods.

    Returns list of result dicts for the primary output table plus
    supplementary overflow diagnostics.
    """
    horizon_col = f"fwd_{HOLDING_PERIOD_TD}td"
    results: list[dict] = []
    overflow_diagnostics: list[dict] = []

    rng_base = random.Random(OVERFLOW_SEED)

    for scenario in ["A", "B", "C"]:
        t_scen, b_scen = build_scenario_mask(
            treat_full, base_full, scenario, segments
        )

        # Gross return: mean event-level forward return (no position sizing)
        # Used as the Gross column in the primary output table.
        valid_t = t_scen[t_scen[horizon_col].notna()][horizon_col]
        gross_mean = float(valid_t.mean()) if len(valid_t) > 0 else float("nan")

        for overflow_method in ["first_10", "random_10"]:
            rng = random.Random(rng_base.randint(0, 2**31 - 1))

            port_df = simulate_portfolio(t_scen, horizon_col, overflow_method, rng)

            if len(port_df) == 0:
                log.warning("Scenario %s / %s: no portfolio dates", scenario, overflow_method)
                continue

            # Mean portfolio gross return and mean deployed weight across signal dates
            port_gross = float(port_df["portfolio_gross_return"].mean())
            mean_deployed_weight = float(port_df["deployed_weight"].mean())

            # Overflow summary
            n_overflow = int(port_df["overflow_applied"].sum())
            overflow_diagnostics.append({
                "scenario": scenario,
                "overflow_method": overflow_method,
                "total_signal_dates": len(port_df),
                "overflow_dates": n_overflow,
                "overflow_fraction": n_overflow / len(port_df) if len(port_df) > 0 else 0,
                "mean_n_signals": float(port_df["n_signals"].mean()),
                "max_n_signals": int(port_df["n_signals"].max()),
                "mean_deployed_weight": mean_deployed_weight,
            })

            for slippage_label, slippage_rt in SLIPPAGE_SCENARIOS.items():
                costs = apply_costs(port_gross, slippage_rt, mean_deployed_weight)

                scenario_labels = {"A": "Full Sample", "B": "Low-Uplift", "C": "High-Uplift"}
                results.append({
                    "scenario": scenario,
                    "environment": scenario_labels[scenario],
                    "slippage_scenario": slippage_label,
                    "overflow_method": overflow_method,
                    "n_signal_dates": len(port_df),
                    "n_overflow_dates": n_overflow,
                    "event_gross_mean": gross_mean,         # pre-portfolio, for reference
                    "portfolio_gross": costs["gross"],
                    "commission": costs["commission"],      # scaled by mean_deployed_weight
                    "slippage": costs["slippage"],          # scaled by mean_deployed_weight
                    "net": costs["net"],
                    "mean_deployed_weight": mean_deployed_weight,
                    "total_cost_rt_unscaled": COMMISSION_RT + slippage_rt,
                    "total_cost_rt_scaled": (COMMISSION_RT + slippage_rt) * mean_deployed_weight,
                    "net_positive": costs["net"] > 0,
                })

                log.info(
                    "Scenario %s (%s) | %s | overflow=%s: "
                    "gross=%.4f, commission=%.4f, slippage=%.4f, net=%.4f",
                    scenario, scenario_labels[scenario], slippage_label,
                    overflow_method,
                    costs["gross"], costs["commission"],
                    costs["slippage"], costs["net"],
                )

    return results, overflow_diagnostics


# ---------------------------------------------------------------------------
# Verdict determination
# ---------------------------------------------------------------------------


OVERFLOW_SENSITIVITY_THRESHOLD: float = 0.005  # 0.5pp


def determine_verdict(results: list[dict]) -> dict:
    """Determine FEASIBLE / CONDITIONAL / NOT FEASIBLE verdict.

    Per SPEC §7.3:
    FEASIBLE     : net positive under S1 in Scenario A AND Scenario B
    CONDITIONAL  : net positive under S1 in Scenario A, negative in Scenario B
    NOT FEASIBLE : net negative under S1 in Scenario A

    Primary verdict uses first_10 (deterministic). Overflow sensitivity flag
    is set when |first_10_net - random_10_net| > OVERFLOW_SENSITIVITY_THRESHOLD
    in any scenario × S1 combination.

    Returns dict with verdict string and diagnostics.
    """
    def net_s1(scenario: str, overflow: str) -> float | None:
        for r in results:
            if (r["scenario"] == scenario
                    and r["slippage_scenario"] == "S1"
                    and r["overflow_method"] == overflow):
                return r["net"]
        return None

    # Primary verdict uses first_10 (deterministic)
    net_a = net_s1("A", "first_10")
    net_b = net_s1("B", "first_10")

    if net_a is None:
        return {"verdict": "INDETERMINATE (missing Scenario A S1 result)", "overflow_sensitive": False}

    if net_a <= 0:
        verdict = "NOT FEASIBLE"
    elif net_b is not None and net_b > 0:
        verdict = "FEASIBLE"
    else:
        verdict = "CONDITIONAL"

    # Overflow sensitivity flag
    overflow_sensitive = False
    sensitivity_details: list[str] = []
    for scen in ["A", "B", "C"]:
        n1 = net_s1(scen, "first_10")
        n2 = net_s1(scen, "random_10")
        if n1 is not None and n2 is not None:
            diff = abs(n1 - n2)
            if diff > OVERFLOW_SENSITIVITY_THRESHOLD:
                overflow_sensitive = True
                sensitivity_details.append(
                    f"Scenario {scen}: first_10={n1:.4f}, random_10={n2:.4f}, diff={diff:.4f}"
                )

    if overflow_sensitive:
        log.warning(
            "Overflow method sensitivity exceeds %.1f pp in: %s",
            OVERFLOW_SENSITIVITY_THRESHOLD * 100,
            "; ".join(sensitivity_details),
        )

    return {
        "verdict": verdict,
        "overflow_sensitive": overflow_sensitive,
        "overflow_sensitivity_details": sensitivity_details,
        "net_a_s1_first10": net_a,
        "net_b_s1_first10": net_b,
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _sha256_file(path: Path) -> str:
    if not path.exists():
        return "missing"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_artifacts(
    results: list[dict],
    overflow_diagnostics: list[dict],
    verdict_doc: dict,
    started_at: datetime,
) -> None:
    """Write Phase 2B artifacts to output directory."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Primary output table
    primary_path = OUTPUT_DIR / "p2b_primary_results.parquet"
    pd.DataFrame(results).to_parquet(primary_path, index=False)

    # Overflow diagnostics
    overflow_path = OUTPUT_DIR / "p2b_overflow_diagnostics.parquet"
    pd.DataFrame(overflow_diagnostics).to_parquet(overflow_path, index=False)

    # Verdict JSON
    verdict_path = OUTPUT_DIR / "p2b_verdict.json"
    full_verdict = {
        **verdict_doc,
        "verdict_basis": "first_10 overflow method, S1 slippage, Scenarios A and B",
        "determined_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    verdict_path.write_text(json.dumps(full_verdict, indent=2, default=str))

    # Human-readable primary table (CSV)
    csv_path = OUTPUT_DIR / "p2b_primary_results.csv"
    pd.DataFrame(results).to_csv(csv_path, index=False, float_format="%.6f")

    # Manifest
    manifest = {
        "spec_version": "r8_phase2b_spec.md v0.1.2",
        "script_version": "v0.1.2",
        "artifact_namespace": "v0.1.0",
        "phase1_panel_commit": "4a307e6",
        "phase2a_segments_source": str(PHASE2A_DIR / "segments/p2a1_segment_results.parquet"),
        "commission_rt": COMMISSION_RT,
        "commission_entry": COMMISSION_ENTRY,
        "commission_exit": COMMISSION_EXIT,
        "tax_exit": TAX_EXIT,
        "slippage_scenarios": SLIPPAGE_SCENARIOS,
        "max_positions": MAX_POSITIONS,
        "holding_period_td": HOLDING_PERIOD_TD,
        "overflow_seed": OVERFLOW_SEED,
        "target_regime": TARGET_REGIME,
        "target_nlu": TARGET_NLU,
        "verdict": verdict_doc["verdict"],
        "overflow_sensitive": verdict_doc["overflow_sensitive"],
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "outputs": {
            "primary": str(primary_path),
            "overflow": str(overflow_path),
            "verdict": str(verdict_path),
            "csv": str(csv_path),
        },
        "output_hashes": {
            "primary": _sha256_file(primary_path),
            "overflow": _sha256_file(overflow_path),
            "verdict": _sha256_file(verdict_path),
        },
    }
    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    log.info("Artifacts written to: %s", OUTPUT_DIR)


def print_summary_table(results: list[dict]) -> None:
    """Print the primary 12-row output matrix to stdout."""
    print()
    print("=" * 90)
    print("Phase 2B Primary Output Table (first_10 overflow method)")
    print("=" * 90)
    print(f"{'Environment':<14} {'Scen':>5} {'Gross':>8} {'Comm':>8} {'Slip':>8} {'Net':>8}  {'Net>0':>6}")
    print("-" * 90)

    for r in results:
        if r["overflow_method"] != "first_10":
            continue
        marker = "✓" if r["net_positive"] else "✗"
        print(
            f"{r['environment']:<14} {r['slippage_scenario']:>5} "
            f"{r['portfolio_gross']:>8.4f} "
            f"{r['commission']:>8.4f} "
            f"{r['slippage']:>8.4f} "
            f"{r['net']:>8.4f}  {marker:>6}"
        )
        if r["slippage_scenario"] == "S3":
            print("-" * 90)

    print("=" * 90)
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="R8 Phase 2B execution bridge v0.1.2")
    p.add_argument(
        "--allow-write", action="store_true",
        help="Write artifacts to output directory (default: dry-run only)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    started_at = datetime.now(timezone.utc)

    log.info(
        "R8 Phase 2B v0.1.2 starting — spec=r8_phase2b_spec.md v0.1.2, "
        "allow_write=%s",
        args.allow_write,
    )

    if not SPEC_PATH.exists():
        log.error("SPEC not found: %s — governance chain broken", SPEC_PATH)
        sys.exit(1)

    # Load Phase 2A segment boundaries (not hardcoded)
    segments = load_segment_boundaries()

    # Load panel (reuses Phase 1 helpers)
    log.info("Connecting to DuckDB (read-only): %s", DB_PATH)
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        panel = load_panel(con)
        prices = load_price_series(con)
    finally:
        con.close()

    panel = compute_forward_returns(panel, prices, horizons=[HOLDING_PERIOD_TD])

    # Filter to target cell
    mask = (panel["regime"] == TARGET_REGIME) & (panel["near_limit_up"] == TARGET_NLU)
    cell = panel[mask].copy()
    treat = cell[cell["universe"] == "treatment_1"].copy()
    base = cell[cell["universe"] == "baseline_1"].copy()

    log.info(
        "Target cell (bull/nlu=0): %d treatment rows (%d dates), "
        "%d baseline rows (%d dates)",
        len(treat), treat["date"].nunique(),
        len(base), base["date"].nunique(),
    )

    # Run analysis
    results, overflow_diagnostics = run_phase2b(treat, base, segments)

    # Print summary
    print_summary_table(results)

    # Determine verdict
    verdict_doc = determine_verdict(results)
    verdict = verdict_doc["verdict"]
    log.info("Phase 2B verdict: %s", verdict)
    if verdict_doc["overflow_sensitive"]:
        log.warning("OVERFLOW SENSITIVE: results differ by >%.1f pp across overflow methods", OVERFLOW_SENSITIVITY_THRESHOLD * 100)
    print(f"Verdict: {verdict}")
    if verdict_doc["overflow_sensitive"]:
        print("WARNING: overflow method sensitivity flag set — review overflow diagnostics")
    print()

    if args.allow_write:
        save_artifacts(results, overflow_diagnostics, verdict_doc, started_at)
    else:
        log.info(
            "Dry-run mode (default) — no files written. "
            "Use --allow-write to persist artifacts."
        )

    log.info("Phase 2B complete.")


if __name__ == "__main__":
    main()
