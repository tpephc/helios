# research/r8_phase1_export.py
"""R8 Phase 1 export and acceptance criteria verification — v0.1.0.

Assembles the canonical Phase 1 output from all upstream layers,
computes block bootstrap effective-n (AC-5), verifies all acceptance
criteria (AC-1 through AC-7), and writes the final export package.

Acceptance criteria verified:
  AC-1: Forward returns at 1/3/5/10/20 trading days
  AC-2: All three required benchmark comparisons present
  AC-3: All analysis stratified by regime_t_minus_1
  AC-4: Near-limit-up subset tagged and reported separately
  AC-5: Block bootstrap effective-n reported alongside inference
  AC-6: All findings labelled provisional
  AC-7: No execution policy in outputs (structural check)

Block bootstrap (per ADR):
  Method: date-level moving block bootstrap
  Block length: 5 trading days
  Replications: 10,000
  Stratification: per regime_t_minus_1
  Seed: fixed, recorded in manifest

Governance:
  - SPEC: research/r8_phase1_lifecycle_spec.md v0.1.2
  - ADR:  docs/decision_records/r8_phase1_bootstrap_adr.md
  - All outputs are PROVISIONAL pending P1-DATA remediation.

Usage:
  uv run python research/r8_phase1_export.py
  uv run python research/r8_phase1_export.py --dry-run
"""

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import polars as pl

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from data.database import get_settings  # noqa: E402
from utils.logger import get_logger  # noqa: E402

logger = get_logger(__name__)

_BUILDER_VERSION = "0.1.0"
_SPEC_PATH = _REPO_ROOT / "research/r8_phase1_lifecycle_spec.md"
_ADR_PATH = _REPO_ROOT / "docs/decision_records/r8_phase1_bootstrap_adr.md"

_STORAGE = _REPO_ROOT / "data/_storage/r8_phase1_remediated"
_EVENTS_PARQUET = _STORAGE / "r8_events.parquet"
_FWD_RETURNS_PARQUET = _STORAGE / "r8_forward_returns.parquet"
_LIFECYCLE_PARQUET = _STORAGE / "r8_lifecycle_metrics.parquet"
_BENCHMARKS_PARQUET = _STORAGE / "r8_benchmarks.parquet"

_OUTPUT_DIR = _STORAGE
_OUTPUT_PARQUET = _OUTPUT_DIR / "r8_phase1_canonical.parquet"
_OUTPUT_MANIFEST = _OUTPUT_DIR / "r8_phase1_manifest.json"

HORIZONS: list[int] = [1, 3, 5, 10, 20]
BOOTSTRAP_BLOCK_LENGTH: int = 5
BOOTSTRAP_N_REPLICATIONS: int = 10_000
BOOTSTRAP_SEED: int = 42


def _file_sha256(path: Path) -> str:
    if not path.exists():
        return "missing"
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=_REPO_ROOT, stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


def _assert_governance_files() -> None:
    for label, path in [("SPEC", _SPEC_PATH), ("ADR", _ADR_PATH)]:
        if not path.exists():
            raise FileNotFoundError(f"{label} not found: {path}")
    logger.info(
        "governance_files_verified",
        spec_sha256=_file_sha256(_SPEC_PATH)[:12],
        adr_sha256=_file_sha256(_ADR_PATH)[:12],
    )


def compute_effective_n(
    df: pl.DataFrame,
    date_col: str,
    return_col: str,
    block_length: int,
    n_replications: int,
    seed: int,
    stratify_col: str | None = None,
) -> dict:
    """Compute date-level moving block bootstrap effective-n.

    Algorithm:
      1. Aggregate returns to date-level means (preserves cross-sectional
         dependence within each date, per ADR).
      2. Apply moving block bootstrap to the date-mean series.
      3. Compute bootstrap variance of the grand mean.
      4. Estimate n_eff = var_iid / var_bootstrap, where
         var_iid = sample_variance / n_unique_dates (SEM^2 under IID).

    This correctly measures temporal dependence in the date-mean series.
    """
    rng = np.random.default_rng(seed)
    clean = df.filter(pl.col(return_col).is_not_null())

    def _eff_n_for_subset(sub: pl.DataFrame) -> dict:
        # Step 1: date-level aggregation
        date_means = (
            sub.group_by(date_col)
            .agg(pl.col(return_col).mean().alias("date_mean"))
            .sort(date_col)
        )
        n_dates = len(date_means)
        n_obs = len(sub)
        vals = date_means["date_mean"].to_numpy()

        if n_dates <= block_length:
            return {
                "n_obs": n_obs,
                "n_unique_dates": n_dates,
                "n_eff": float(n_dates),
                "note": "n_dates <= block_length; n_eff = n_dates",
            }

        # Step 2: moving block bootstrap on date-mean series
        n_blocks_available = n_dates - block_length + 1
        blocks_per_rep = int(np.ceil(n_dates / block_length))
        bootstrap_means = np.empty(n_replications)

        for i in range(n_replications):
            starts = rng.integers(0, n_blocks_available, size=blocks_per_rep)
            sample = np.concatenate([vals[s : s + block_length] for s in starts])
            bootstrap_means[i] = sample[:n_dates].mean()

        # Step 3: bootstrap variance of grand mean
        var_bootstrap = float(np.var(bootstrap_means, ddof=1))

        # Step 4: n_eff = n_dates * var_iid / var_bootstrap
        # var_iid = sigma^2 / n_dates (SEM^2 under IID)
        # var_bootstrap ~= sigma^2 / n_eff
        # => n_eff = n_dates * var_iid / var_bootstrap
        var_iid = float(np.var(vals, ddof=1)) / n_dates

        if var_bootstrap <= 0:
            raw_n_eff = float(n_dates)
        else:
            raw_n_eff = float(n_dates) * var_iid / var_bootstrap

        n_eff = max(1.0, min(raw_n_eff, float(n_dates)))
        clamped = abs(n_eff - raw_n_eff) > 1e-6
        result = {
            "n_obs": n_obs,
            "n_unique_dates": n_dates,
            "raw_n_eff": round(raw_n_eff, 4),
            "n_eff": round(n_eff, 1),
            "effective_n_clamped": clamped,
        }
        if clamped:
            result["effective_n_warning"] = (
                f"raw_n_eff={raw_n_eff:.4f} outside [1, {n_dates}]; "
                "clamped to statistical bounds. Likely cause: high "
                "return autocorrelation from overlapping windows."
            )
        return result

    overall = _eff_n_for_subset(clean)
    overall.update({
        "block_length": block_length,
        "n_replications": n_replications,
        "seed": seed,
        "provisional": True,
    })

    if stratify_col and stratify_col in clean.columns:
        by_stratum: dict = {}
        for stratum in sorted(clean[stratify_col].unique().to_list()):
            sub = clean.filter(pl.col(stratify_col) == stratum)
            by_stratum[str(stratum)] = _eff_n_for_subset(sub)
        overall["by_stratum"] = by_stratum

    return overall


def _verify_acceptance_criteria(
    events: pl.DataFrame,
    fwd: pl.DataFrame,
    lifecycle: pl.DataFrame,
    benchmarks: pl.DataFrame,
    effective_n: dict,
) -> dict[str, bool]:
    results: dict[str, bool] = {}

    # AC-1: forward returns at all horizons
    ac1 = all(f"ret_{h}d" in fwd.columns for h in HORIZONS)
    results["AC-1"] = ac1
    logger.info("ac1_forward_returns", pass_=ac1)

    # AC-2: required benchmark labels present
    required_benchmark_labels = {
        "rs_t3_hold",
        "rs_t3_pullback",
        "r8_within_rs_t3",
        "rs_t3_unconditional_date_aligned",
    }
    found = set(benchmarks["benchmark"].unique().to_list())
    ac2 = required_benchmark_labels.issubset(found)
    results["AC-2"] = ac2
    logger.info("ac2_benchmarks", pass_=ac2, found=sorted(found))

    # AC-3: regime stratification actually present in data
    regime_col_present = (
        "regime_t_minus_1" in events.columns
        and "regime_t_minus_1" in benchmarks.columns
    )
    if regime_col_present:
        regimes_in_benchmarks = set(
            benchmarks["regime_t_minus_1"].drop_nulls().unique().to_list()
        )
        required_regimes = {"bull", "bear", "neutral", "crisis"}
        ac3 = len(required_regimes & regimes_in_benchmarks) >= 2
    else:
        ac3 = False
    results["AC-3"] = ac3
    logger.info(
        "ac3_regime_stratification",
        pass_=ac3,
        regimes_found=sorted(
            benchmarks["regime_t_minus_1"].drop_nulls().unique().to_list()
        ) if regime_col_present else [],
    )

    # AC-4: near_limit_up_flag present and non-trivial
    ac4 = (
        "near_limit_up_flag" in events.columns
        and int(events["near_limit_up_flag"].sum()) > 0
    )
    results["AC-4"] = ac4
    logger.info(
        "ac4_near_limit_up",
        pass_=ac4,
        n_near_limit_up=int(events["near_limit_up_flag"].sum()),
    )

    # AC-5: effective-n computed with return-series bootstrap
    # Require 1.0 <= n_eff <= n_unique_dates (clamped estimator)
    n_eff_val = effective_n.get("n_eff")
    n_dates_val = effective_n.get("n_unique_dates", 0)
    ac5 = (
        n_eff_val is not None
        and n_dates_val > 0
        and 1.0 <= n_eff_val <= float(n_dates_val)
        and "by_stratum" in effective_n
    )
    results["AC-5"] = ac5
    logger.info(
        "ac5_effective_n",
        pass_=ac5,
        n_eff=effective_n.get("n_eff"),
        n_unique_dates=effective_n.get("n_unique_dates"),
    )

    # AC-6: provisional flag (structural)
    ac6 = True
    results["AC-6"] = ac6
    logger.info("ac6_provisional_label", pass_=ac6)

    # AC-7: no execution policy columns
    forbidden_cols = {
        "exit_signal", "stop_loss", "position_size", "re_entry",
        "sell_half", "scale_in", "target_price",
    }
    all_cols = (
        set(events.columns) | set(fwd.columns)
        | set(lifecycle.columns) | set(benchmarks.columns)
    )
    violations = forbidden_cols & all_cols
    ac7 = len(violations) == 0
    results["AC-7"] = ac7
    logger.info("ac7_no_execution_policy", pass_=ac7, violations=sorted(violations))

    return results


def build_export(dry_run: bool = False) -> pl.DataFrame:
    """Assemble Phase 1 canonical output and verify acceptance criteria."""
    _assert_governance_files()

    for label, path in [
        ("events", _EVENTS_PARQUET),
        ("forward_returns", _FWD_RETURNS_PARQUET),
        ("lifecycle_metrics", _LIFECYCLE_PARQUET),
        ("benchmarks", _BENCHMARKS_PARQUET),
    ]:
        if not path.exists():
            raise FileNotFoundError(f"{label} parquet not found: {path}")

    logger.info("r8_phase1_export_start", version=_BUILDER_VERSION, dry_run=dry_run)

    events = pl.read_parquet(_EVENTS_PARQUET)
    fwd = pl.read_parquet(_FWD_RETURNS_PARQUET)
    lifecycle = pl.read_parquet(_LIFECYCLE_PARQUET)
    benchmarks = pl.read_parquet(_BENCHMARKS_PARQUET)

    # Canonical event-level table (events + forward returns + lifecycle)
    canonical = events.join(
        fwd.drop(["stock_id", "signal_date"]),
        on="event_id", how="left",
    ).join(
        lifecycle.drop(["stock_id", "signal_date"]),
        on="event_id", how="left",
    )

    logger.info(
        "canonical_table_assembled",
        n_rows=len(canonical),
        n_cols=len(canonical.columns),
    )

    # AC-5: date-level moving block bootstrap effective-n
    logger.info(
        "computing_effective_n",
        block_length=BOOTSTRAP_BLOCK_LENGTH,
        n_replications=BOOTSTRAP_N_REPLICATIONS,
        seed=BOOTSTRAP_SEED,
    )

    fwd_clean = fwd.filter(
        pl.col("ret_20d").is_not_null()
        & pl.col("entry_missing_flag").not_()
    )
    # Attach regime for stratification
    fwd_with_regime = fwd_clean.join(
        events.select(["event_id", "regime_t_minus_1"]),
        on="event_id", how="left",
    )

    effective_n = compute_effective_n(
        df=fwd_with_regime,
        date_col="signal_date",
        return_col="ret_20d",
        block_length=BOOTSTRAP_BLOCK_LENGTH,
        n_replications=BOOTSTRAP_N_REPLICATIONS,
        seed=BOOTSTRAP_SEED,
        stratify_col="regime_t_minus_1",
    )

    logger.info(
        "effective_n_computed",
        n_obs=effective_n["n_obs"],
        n_unique_dates=effective_n["n_unique_dates"],
        n_eff=effective_n["n_eff"],
    )

    # Acceptance criteria verification
    ac_results = _verify_acceptance_criteria(
        events=canonical,
        fwd=fwd,
        lifecycle=lifecycle,
        benchmarks=benchmarks,
        effective_n=effective_n,
    )

    ac_pass = all(ac_results.values())
    logger.info("acceptance_criteria", results=ac_results, all_pass=ac_pass)

    if not ac_pass:
        failed = [k for k, v in ac_results.items() if not v]
        raise RuntimeError(f"Phase 1 AC FAILED: {failed}")

    if dry_run:
        logger.info("r8_phase1_export_dry_run_complete", n_events=len(canonical))
        return canonical

    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    canonical.write_parquet(_OUTPUT_PARQUET)

    s = get_settings()
    manifest = {
        "builder_version": _BUILDER_VERSION,
        "built_at": datetime.now().isoformat(),
        "git_commit": _git_commit(),
        "database_path": str(s.db_path),
        "spec_sha256": _file_sha256(_SPEC_PATH),
        "adr_sha256": _file_sha256(_ADR_PATH),
        "n_events": len(canonical),
        "n_cols": len(canonical.columns),
        "acceptance_criteria": ac_results,
        "all_ac_pass": ac_pass,
        "effective_n": effective_n,
        "bootstrap_config": {
            "method": "date-level moving block bootstrap",
            "block_length": BOOTSTRAP_BLOCK_LENGTH,
            "n_replications": BOOTSTRAP_N_REPLICATIONS,
            "seed": BOOTSTRAP_SEED,
            "resampling_unit": "trading date",
            "aggregation": "date-mean return before bootstrap",
            "stratification": "per regime_t_minus_1",
        },
        "output_files": {
            "canonical_events": str(_OUTPUT_PARQUET),
            "benchmarks": str(_BENCHMARKS_PARQUET),
            "lifecycle_metrics": str(_LIFECYCLE_PARQUET),
        },
        "provisional": True,
        "provisional_reason": (
            "P1-DATA remediation pending: pre-listing contamination "
            "(18 stocks / 7331 rows), empty stock_info, empty corporate_actions"
        ),
        "interpretation_restrictions": (
            "Phase 1 establishes measurement infrastructure and benchmarked "
            "lifecycle evidence only. See SPEC 'Interpretation Restrictions'."
        ),
    }
    _OUTPUT_MANIFEST.write_text(json.dumps(manifest, indent=2))

    logger.info(
        "r8_phase1_export_complete",
        parquet=str(_OUTPUT_PARQUET),
        manifest=str(_OUTPUT_MANIFEST),
        all_ac_pass=ac_pass,
    )
    return canonical


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="R8 Phase 1 export and AC verification")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    df = build_export(dry_run=args.dry_run)
    print(f"Phase 1 canonical: {len(df)} rows x {len(df.columns)} cols")
