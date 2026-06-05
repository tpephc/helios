# research/r8_benchmarks.py
"""R8 Phase 1 benchmark comparisons — v0.1.1.

Computes the three Required Comparisons mandated by SPEC (AC-2):

  Benchmark A — RS_T3 Hold:
    All rs_t3_t_minus_1=1 stocks at T+1 open; hold to each horizon.

  Benchmark B — RS_T3 + Pullback:
    Same as A but dist_above_ma20_atr < 0 at T.

  Benchmark C — R8 within RS_T3 vs RS_T3 unconditional:
    R8 events with rs_t3_t_minus_1=1, compared against RS_T3 Hold
    restricted to the same signal dates (date-aligned).

All summaries are stratified by regime_t_minus_1 (SPEC AC-3).
Near-limit-up subset (near_limit_up_flag=True) is reported
separately (SPEC AC-4).

Governance:
  - SPEC: research/r8_phase1_lifecycle_spec.md v0.1.2
  - ADR:  docs/decision_records/r8_phase1_bootstrap_adr.md
  - All outputs are PROVISIONAL pending P1-DATA remediation.

Usage:
  uv run python research/r8_benchmarks.py
  uv run python research/r8_benchmarks.py --dry-run
"""

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import polars as pl

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from data.database import connect, get_settings  # noqa: E402
from utils.logger import get_logger  # noqa: E402

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_BUILDER_VERSION = "0.1.1"
_SPEC_PATH = _REPO_ROOT / "research/r8_phase1_lifecycle_spec.md"
_ADR_PATH = _REPO_ROOT / "docs/decision_records/r8_phase1_bootstrap_adr.md"
_EVENTS_PARQUET = _REPO_ROOT / "data/_storage/r8_phase1/r8_events.parquet"
_FWD_RETURNS_PARQUET = _REPO_ROOT / "data/_storage/r8_phase1/r8_forward_returns.parquet"
_OUTPUT_DIR = _REPO_ROOT / "data/_storage/r8_phase1_remediated"
_OUTPUT_PARQUET = _OUTPUT_DIR / "r8_benchmarks.parquet"
_OUTPUT_MANIFEST = _OUTPUT_DIR / "r8_benchmarks_manifest.json"

HORIZONS: list[int] = [1, 3, 5, 10, 20]
_BF_EFFECTIVE_START = "2021-07-16"

REGIME_ORDER: list[str] = ["bull", "neutral", "bear", "crisis", "unknown",
                            "regime_missing"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _file_sha256(path: Path) -> str:
    """Return hex SHA-256 of a file, or 'missing' if not found."""
    if not path.exists():
        return "missing"
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _git_commit() -> str:
    """Return current HEAD commit hash, or 'unknown' on failure."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=_REPO_ROOT,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


def _assert_governance_files() -> None:
    """Abort if SPEC or ADR are missing."""
    for label, path in [("SPEC", _SPEC_PATH), ("ADR", _ADR_PATH)]:
        if not path.exists():
            raise FileNotFoundError(f"{label} not found: {path}")
    logger.info(
        "governance_files_verified",
        spec_sha256=_file_sha256(_SPEC_PATH)[:12],
        adr_sha256=_file_sha256(_ADR_PATH)[:12],
    )


# ---------------------------------------------------------------------------
# Universe builder
# ---------------------------------------------------------------------------

def _build_rs_t3_universe() -> pl.DataFrame:
    """Build daily RS_T3 universe with T-1 de-circularised membership.

    Returns
    -------
    pl.DataFrame
        Columns: stock_id, date, rs_t3_t_minus_1, dist_above_ma20_atr,
                 regime_t_minus_1.
    """
    with connect(read_only=True) as conn:
        universe = conn.execute("""
            WITH rs_thresholds AS (
                SELECT date,
                       PERCENTILE_CONT(0.6667)
                           WITHIN GROUP (ORDER BY beta_adj_rs_20d)
                           AS rs_t3_threshold
                FROM bullish_features
                WHERE beta_adj_rs_20d IS NOT NULL
                GROUP BY date
            ),
            tagged AS (
                SELECT bf.stock_id,
                       bf.date,
                       bf.dist_above_ma20_atr,
                       CASE
                           WHEN bf.beta_adj_rs_20d >= t.rs_t3_threshold
                           THEN 1 ELSE 0
                       END AS rs_t3_flag_same_day
                FROM bullish_features bf
                JOIN rs_thresholds t ON t.date = bf.date
                WHERE bf.beta_adj_rs_20d IS NOT NULL
            ),
            lagged AS (
                SELECT stock_id, date, dist_above_ma20_atr,
                       LAG(rs_t3_flag_same_day)
                           OVER (PARTITION BY stock_id ORDER BY date)
                           AS rs_t3_t_minus_1
                FROM tagged
            ),
            regime_ranked AS (
                SELECT date, regime,
                       ROW_NUMBER() OVER (ORDER BY date) AS rn
                FROM market_regime
            ),
            regime_lagged AS (
                SELECT a.date AS signal_date,
                       CASE
                           WHEN b.regime IS NULL THEN 'regime_missing'
                           ELSE b.regime
                       END AS regime_t_minus_1
                FROM regime_ranked a
                LEFT JOIN regime_ranked b ON b.rn = a.rn - 1
            )
            SELECT l.stock_id,
                   l.date,
                   l.dist_above_ma20_atr,
                   l.rs_t3_t_minus_1,
                   COALESCE(r.regime_t_minus_1, 'regime_missing')
                       AS regime_t_minus_1
            FROM lagged l
            LEFT JOIN regime_lagged r ON r.signal_date = l.date
            WHERE l.date >= $bf_start
            ORDER BY l.date, l.stock_id
        """, {"bf_start": _BF_EFFECTIVE_START}).pl()
    return universe


# ---------------------------------------------------------------------------
# Forward returns for benchmark universe
# ---------------------------------------------------------------------------

def _compute_benchmark_forward_returns(
    universe: pl.DataFrame,
    benchmark_name: str,
) -> pl.DataFrame:
    """Compute T+1 entry forward returns for a benchmark universe.

    Parameters
    ----------
    universe:
        DataFrame with at minimum: stock_id, date, regime_t_minus_1.
    benchmark_name:
        Label for the benchmark column.

    Returns
    -------
    pl.DataFrame
        One row per (stock_id, date) with forward returns and metadata.
    """
    with connect(read_only=True) as conn:
        price = conn.execute("""
            SELECT stock_id, date, adj_open, adj_close,
                   ROW_NUMBER() OVER (
                       PARTITION BY stock_id ORDER BY date
                   ) - 1 AS td_idx
            FROM listed_market_daily_price_adj
        """).pl()

    df = universe.join(
        price.select(["stock_id", "date", "td_idx"]),
        on=["stock_id", "date"],
        how="left",
    )

    entry_price = price.select(["stock_id", "td_idx", "adj_open"]).rename(
        {"td_idx": "entry_td_idx", "adj_open": "entry_adj_open"}
    )
    df = df.with_columns(
        (pl.col("td_idx") + 1).alias("entry_td_idx")
    ).join(entry_price, on=["stock_id", "entry_td_idx"], how="left")

    df = df.with_columns(
        pl.col("entry_adj_open").is_null().alias("entry_missing_flag")
    )

    for h in HORIZONS:
        horizon_price = price.select(
            ["stock_id", "td_idx", "adj_close"]
        ).rename({
            "td_idx": f"h{h}_td_idx",
            "adj_close": f"adj_close_t{h}d",
        })
        df = df.with_columns(
            (pl.col("td_idx") + h).alias(f"h{h}_td_idx")
        ).join(horizon_price, on=["stock_id", f"h{h}_td_idx"], how="left")
        df = df.with_columns(
            (pl.col(f"adj_close_t{h}d") / pl.col("entry_adj_open") - 1.0)
            .alias(f"ret_{h}d"),
            pl.col(f"adj_close_t{h}d").is_null().alias(f"ret_{h}d_missing_flag"),
        ).drop([f"h{h}_td_idx", f"adj_close_t{h}d"])

    df = df.drop(["entry_td_idx", "td_idx"]).with_columns(
        pl.lit(benchmark_name).alias("benchmark")
    )
    return df


# ---------------------------------------------------------------------------
# Summary statistics: regime-stratified + near-limit-up
# ---------------------------------------------------------------------------

def _horizon_stats(series: pl.Series) -> dict:
    """Return n / mean / median for a return series."""
    clean = series.drop_nulls()
    n = len(clean)
    return {
        "n": n,
        "mean": round(float(clean.mean()), 6) if n > 0 else None,
        "median": round(float(clean.median()), 6) if n > 0 else None,
    }


def _benchmark_summary(
    df: pl.DataFrame,
    label: str,
    near_limit_up_col: str | None = None,
) -> dict:
    """Compute regime-stratified forward return summary.

    Parameters
    ----------
    df:
        Benchmark DataFrame with ret_{h}d columns and regime_t_minus_1.
    label:
        Benchmark name.
    near_limit_up_col:
        If provided, also compute near-limit-up subset stats.
    """
    valid = df.filter(~pl.col("entry_missing_flag"))
    summary: dict = {
        "benchmark": label,
        "n_total": len(valid),
        "pooled": {},
        "by_regime": {},
        "near_limit_up": {},
    }

    # Pooled
    for h in HORIZONS:
        ret_col = f"ret_{h}d"
        sub = valid.filter(~pl.col(f"ret_{h}d_missing_flag"))
        summary["pooled"][f"{h}d"] = _horizon_stats(sub[ret_col])

    # Regime-stratified (SPEC AC-3)
    regimes = valid["regime_t_minus_1"].unique().to_list()
    for regime in sorted(regimes):
        regime_df = valid.filter(pl.col("regime_t_minus_1") == regime)
        summary["by_regime"][regime] = {}
        for h in HORIZONS:
            ret_col = f"ret_{h}d"
            sub = regime_df.filter(~pl.col(f"ret_{h}d_missing_flag"))
            summary["by_regime"][regime][f"{h}d"] = _horizon_stats(sub[ret_col])

    # Near-limit-up subset (SPEC AC-4)
    if near_limit_up_col and near_limit_up_col in valid.columns:
        nlu = valid.filter(pl.col(near_limit_up_col))
        non_nlu = valid.filter(~pl.col(near_limit_up_col))
        for subset_label, subset_df in [
            ("near_limit_up_true", nlu),
            ("near_limit_up_false", non_nlu),
        ]:
            summary["near_limit_up"][subset_label] = {}
            for h in HORIZONS:
                ret_col = f"ret_{h}d"
                sub = subset_df.filter(~pl.col(f"ret_{h}d_missing_flag"))
                summary["near_limit_up"][subset_label][f"{h}d"] = (
                    _horizon_stats(sub[ret_col])
                )

    return summary


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_benchmarks(dry_run: bool = False) -> dict[str, pl.DataFrame]:
    """Compute all three SPEC-required benchmark comparisons.

    Returns
    -------
    dict[str, pl.DataFrame]
        Keys: 'rs_t3_hold', 'rs_t3_pullback', 'r8_within_rs_t3',
              'rs_t3_unconditional_date_aligned'.
    """
    _assert_governance_files()

    for label, path in [
        ("events", _EVENTS_PARQUET),
        ("forward_returns", _FWD_RETURNS_PARQUET),
    ]:
        if not path.exists():
            raise FileNotFoundError(
                f"{label} parquet not found: {path}"
            )

    logger.info("r8_benchmarks_start", version=_BUILDER_VERSION, dry_run=dry_run)

    # ── Universe ─────────────────────────────────────────────────────────
    logger.info("building_rs_t3_universe")
    universe = _build_rs_t3_universe()

    bm_a_universe = universe.filter(pl.col("rs_t3_t_minus_1") == 1)
    bm_b_universe = bm_a_universe.filter(
        pl.col("dist_above_ma20_atr").is_not_null()
        & (pl.col("dist_above_ma20_atr") < 0)
    )
    logger.info(
        "universe_built",
        n_bm_a=len(bm_a_universe),
        n_bm_b=len(bm_b_universe),
    )

    # ── Benchmark A ───────────────────────────────────────────────────────
    logger.info("computing_benchmark_a")
    bm_a = _compute_benchmark_forward_returns(
        bm_a_universe.select(["stock_id", "date", "regime_t_minus_1"]),
        "rs_t3_hold",
    )

    # ── Benchmark B ───────────────────────────────────────────────────────
    logger.info("computing_benchmark_b")
    bm_b = _compute_benchmark_forward_returns(
        bm_b_universe.select(["stock_id", "date", "regime_t_minus_1"]),
        "rs_t3_pullback",
    )

    # ── Benchmark C ───────────────────────────────────────────────────────
    events = pl.read_parquet(_EVENTS_PARQUET)
    fwd = pl.read_parquet(_FWD_RETURNS_PARQUET)
    r8_fwd = events.join(fwd.drop(["stock_id", "signal_date"]),
                         on="event_id", how="left")

    # Tag benchmark_universe_missing
    bf_dates = universe.select("date").unique()
    r8_fwd = r8_fwd.with_columns(
        (~pl.col("signal_date").is_in(bf_dates["date"].to_list()))
        .alias("benchmark_universe_missing")
    )

    n_excluded = int(r8_fwd["benchmark_universe_missing"].sum())
    excluded_pct = n_excluded / len(r8_fwd)
    assert excluded_pct < 0.05, (
        f"benchmark_universe_missing={excluded_pct:.1%} exceeds 5% threshold"
    )

    # R8 within RS_T3
    r8_rs_t3 = r8_fwd.filter(
        (pl.col("rs_t3_t_minus_1") == 1)
        & (~pl.col("benchmark_universe_missing"))
    ).with_columns(pl.lit("r8_within_rs_t3").alias("benchmark"))

    logger.info(
        "benchmark_c_r8_subset",
        n_r8_rs_t3=len(r8_rs_t3),
        n_excluded=n_excluded,
        excluded_pct=round(excluded_pct, 4),
    )

    # RS_T3 unconditional restricted to same signal dates as R8 (date-aligned)
    r8_signal_dates = r8_rs_t3.select("signal_date").unique()
    bm_a_date_aligned = bm_a.join(
        r8_signal_dates.rename({"signal_date": "date"}),
        on="date",
        how="inner",
    ).with_columns(pl.lit("rs_t3_unconditional_date_aligned").alias("benchmark"))

    logger.info(
        "benchmark_c_unconditional_aligned",
        n_bm_a_aligned=len(bm_a_date_aligned),
    )

    # ── Summaries ─────────────────────────────────────────────────────────
    summary_a = _benchmark_summary(bm_a, "rs_t3_hold")
    summary_b = _benchmark_summary(bm_b, "rs_t3_pullback")
    summary_c_r8 = _benchmark_summary(
        r8_rs_t3.rename({"signal_date": "date"}),
        "r8_within_rs_t3",
        near_limit_up_col="near_limit_up_flag",
    )
    summary_c_bm = _benchmark_summary(
        bm_a_date_aligned, "rs_t3_unconditional_date_aligned"
    )

    for s in [summary_a, summary_b, summary_c_r8, summary_c_bm]:
        logger.info(
            "benchmark_summary",
            benchmark=s["benchmark"],
            n_total=s["n_total"],
            ret_20d_pooled=s["pooled"].get("20d"),
        )

    results = {
        "rs_t3_hold": bm_a,
        "rs_t3_pullback": bm_b,
        "r8_within_rs_t3": r8_rs_t3,
        "rs_t3_unconditional_date_aligned": bm_a_date_aligned,
    }

    if dry_run:
        logger.info("r8_benchmarks_dry_run_complete")
        return results

    # ── Write outputs ─────────────────────────────────────────────────────
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    ret_cols = [f"ret_{h}d" for h in HORIZONS]
    miss_cols = [f"ret_{h}d_missing_flag" for h in HORIZONS]
    base_cols = ["stock_id", "date", "benchmark",
                 "regime_t_minus_1", "entry_missing_flag"]

    def _safe_select(df: pl.DataFrame, want: list[str]) -> pl.DataFrame:
        return df.select([c for c in want if c in df.columns])

    combined = pl.concat([
        _safe_select(bm_a, base_cols + ret_cols + miss_cols),
        _safe_select(bm_b, base_cols + ret_cols + miss_cols),
        _safe_select(
            r8_rs_t3.rename({"signal_date": "date"}),
            base_cols + ret_cols + miss_cols + ["near_limit_up_flag",
                                                 "benchmark_universe_missing"],
        ),
        _safe_select(bm_a_date_aligned, base_cols + ret_cols + miss_cols),
    ], how="diagonal")

    combined.write_parquet(_OUTPUT_PARQUET)

    s = get_settings()
    manifest = {
        "builder_version": _BUILDER_VERSION,
        "built_at": datetime.now().isoformat(),
        "git_commit": _git_commit(),
        "database_path": str(s.db_path),
        "spec_sha256": _file_sha256(_SPEC_PATH),
        "adr_sha256": _file_sha256(_ADR_PATH),
        "bf_effective_start": _BF_EFFECTIVE_START,
        "n_bm_a": len(bm_a),
        "n_bm_b": len(bm_b),
        "n_r8_rs_t3": len(r8_rs_t3),
        "n_bm_a_date_aligned": len(bm_a_date_aligned),
        "n_excluded_benchmark_universe_missing": n_excluded,
        "summary": {
            "rs_t3_hold": summary_a,
            "rs_t3_pullback": summary_b,
            "r8_within_rs_t3": summary_c_r8,
            "rs_t3_unconditional_date_aligned": summary_c_bm,
        },
        "provisional": True,
        "provisional_reason": (
            "P1-DATA remediation pending: pre-listing contamination "
            "(18 stocks / 7331 rows), empty stock_info, empty corporate_actions"
        ),
        "output_parquet": str(_OUTPUT_PARQUET),
    }
    _OUTPUT_MANIFEST.write_text(json.dumps(manifest, indent=2))

    logger.info(
        "r8_benchmarks_complete",
        parquet=str(_OUTPUT_PARQUET),
        manifest=str(_OUTPUT_MANIFEST),
    )
    return results


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="R8 Phase 1 benchmark comparisons")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    results = build_benchmarks(dry_run=args.dry_run)
    for name, df in results.items():
        n = len(df)
        ret20_mean = None
        if "ret_20d" in df.columns:
            ret20_mean = df["ret_20d"].drop_nulls().mean()
        print(f"{name}: n={n}, ret_20d_mean={ret20_mean:.4f}" if ret20_mean else f"{name}: n={n}")
