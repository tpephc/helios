# research/r8_event_builder.py
"""R8 Phase 1 lifecycle event builder — v0.1.1.

Constructs the canonical R8 event table for Phase 1 lifecycle replay.
Each row is one (stock_id, signal_date) event where:
  - daily_return >= +5%  (adj_close / prev_adj_close - 1)
  - adj_close > adj_open

RS_T3 membership is computed as the T-1 de-circularised version
(rs_t3_t_minus_1). The same-day version (rs_t3_flag_same_day) is
retained as a diagnostic column only and must not be used as a
benchmark or filter in Phase 1 analysis.

Governance:
  - SPEC: research/r8_phase1_lifecycle_spec.md v0.1.2 (LA-3, LA-4, LA-8)
  - ADR:  docs/decision_records/r8_phase1_bootstrap_adr.md
  - All outputs are PROVISIONAL pending P1-DATA remediation.

Usage:
  uv run python research/r8_event_builder.py
  uv run python research/r8_event_builder.py --from-date 2022-01-01
  uv run python research/r8_event_builder.py --dry-run
"""

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import date, datetime
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
_OUTPUT_DIR = _REPO_ROOT / "data/_storage/r8_phase1"
_OUTPUT_PARQUET = _OUTPUT_DIR / "r8_events.parquet"
_OUTPUT_CSV = _OUTPUT_DIR / "r8_events.csv"
_OUTPUT_MANIFEST = _OUTPUT_DIR / "r8_events_manifest.json"

SIGNAL_RETURN_THRESHOLD: float = 0.05
NEAR_LIMIT_UP_THRESHOLD: float = 0.095
RS_TOP_TERTILE_QUANTILE: float = 2 / 3  # PERCENTILE_CONT(2/3): top 33.3%

# Invariant bounds for RS_T3 same-day coverage (expected ~33.3%)
_RS_T3_COVERAGE_LO: float = 0.30
_RS_T3_COVERAGE_HI: float = 0.36

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------
_EVENT_SQL = """
WITH price_panel AS (
    SELECT
        stock_id,
        date,
        adj_open,
        adj_close,
        LAG(adj_close) OVER (PARTITION BY stock_id ORDER BY date) AS prev_adj_close,
        LAG(date)      OVER (PARTITION BY stock_id ORDER BY date) AS prev_date
    FROM daily_price_adj
),

r8_candidates AS (
    SELECT
        stock_id,
        date                                          AS signal_date,
        adj_open                                      AS signal_adj_open,
        adj_close                                     AS signal_adj_close,
        prev_adj_close,
        adj_close / prev_adj_close - 1.0              AS signal_daily_return,
        (date - prev_date)                            AS calendar_gap_days,
        CASE
            WHEN adj_close / prev_adj_close - 1.0 >= $near_limit_up
            THEN TRUE ELSE FALSE
        END                                           AS near_limit_up_flag
    FROM price_panel
    WHERE prev_adj_close IS NOT NULL
      AND prev_adj_close > 0
      AND adj_close / prev_adj_close - 1.0 >= $signal_threshold
      AND adj_close > adj_open
),

rs_thresholds AS (
    SELECT
        date,
        PERCENTILE_CONT($rs_tertile_quantile)
            WITHIN GROUP (ORDER BY beta_adj_rs_20d)   AS rs_t3_threshold_20d
    FROM bullish_features
    WHERE beta_adj_rs_20d IS NOT NULL
    GROUP BY date
),

rs_tagged AS (
    SELECT
        bf.stock_id,
        bf.date,
        bf.beta_adj_rs_20d                                        AS beta_adj_rs_20d_raw,
        bf.dist_above_ma20_atr,
        bf.beta_60,
        bf.sma20_slope_10d,
        PERCENT_RANK() OVER (
            PARTITION BY bf.date ORDER BY bf.beta_adj_rs_20d
        )                                                         AS rs_rank_pct_same_day,
        CASE
            WHEN bf.beta_adj_rs_20d >= t.rs_t3_threshold_20d THEN 1 ELSE 0
        END                                                       AS rs_t3_flag_same_day
    FROM bullish_features bf
    JOIN rs_thresholds t ON t.date = bf.date
    WHERE bf.beta_adj_rs_20d IS NOT NULL
),

rs_lagged AS (
    SELECT
        stock_id,
        date,
        beta_adj_rs_20d_raw,
        dist_above_ma20_atr,
        beta_60,
        sma20_slope_10d,
        rs_rank_pct_same_day,
        rs_t3_flag_same_day,
        LAG(rs_t3_flag_same_day) OVER (
            PARTITION BY stock_id ORDER BY date
        )                                                         AS rs_t3_t_minus_1,
        LAG(rs_rank_pct_same_day) OVER (
            PARTITION BY stock_id ORDER BY date
        )                                                         AS rs_rank_pct_t_minus_1
    FROM rs_tagged
),

regime_ranked AS (
    SELECT
        date,
        regime,
        ROW_NUMBER() OVER (ORDER BY date) AS rn
    FROM market_regime
),

regime_lagged AS (
    SELECT
        a.date       AS signal_date,
        b.regime     AS regime_t_minus_1,
        b.date IS NULL AS regime_missing
    FROM regime_ranked a
    LEFT JOIN regime_ranked b ON b.rn = a.rn - 1
)

SELECT
    -- event_id computed in Python after fetch (DuckDB encode() is single-arg)
    r.stock_id || '|' || CAST(r.signal_date AS VARCHAR)          AS _event_key,
    r.stock_id,
    r.signal_date,
    r.signal_adj_open,
    r.signal_adj_close,
    r.prev_adj_close,
    r.signal_daily_return,
    r.near_limit_up_flag,
    r.calendar_gap_days,
    -- RS features: T-1 de-circularised (canonical, per SPEC LA-4)
    rs.rs_t3_t_minus_1,
    rs.rs_rank_pct_t_minus_1,
    -- RS features: same-day (CIRCULAR — diagnostic only, not for benchmarks)
    rs.beta_adj_rs_20d_raw,
    rs.rs_rank_pct_same_day,
    rs.rs_t3_flag_same_day,
    -- Pullback / momentum features at T close
    rs.dist_above_ma20_atr,
    rs.beta_60,
    rs.sma20_slope_10d,
    -- Regime (T-1, per SPEC LA-3)
    CASE
        WHEN rl.regime_missing OR rl.regime_t_minus_1 IS NULL THEN 'regime_missing'
        ELSE rl.regime_t_minus_1
    END                                                           AS regime_t_minus_1,
    rl.regime_missing
FROM r8_candidates r
LEFT JOIN rs_lagged rs
    ON rs.stock_id = r.stock_id AND rs.date = r.signal_date
LEFT JOIN regime_lagged rl
    ON rl.signal_date = r.signal_date
ORDER BY r.signal_date, r.stock_id
"""


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
    """Abort if SPEC or ADR are missing (governance chain must be intact)."""
    spec_hash = _file_sha256(_SPEC_PATH)
    adr_hash = _file_sha256(_ADR_PATH)
    if spec_hash == "missing":
        raise FileNotFoundError(f"SPEC not found: {_SPEC_PATH}")
    if adr_hash == "missing":
        raise FileNotFoundError(f"ADR not found: {_ADR_PATH}")
    logger.info(
        "governance_files_verified",
        spec_sha256=spec_hash[:12],
        adr_sha256=adr_hash[:12],
    )


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_events(
    from_date: date | None = None,
    dry_run: bool = False,
) -> pl.DataFrame:
    """Build the canonical R8 Phase 1 event table.

    Parameters
    ----------
    from_date:
        If provided, restrict events to signal_date >= from_date.
    dry_run:
        If True, build and return without writing output files.

    Returns
    -------
    pl.DataFrame
        One row per (stock_id, signal_date) R8 event.
    """
    _assert_governance_files()

    logger.info(
        "r8_event_builder_start",
        version=_BUILDER_VERSION,
        from_date=str(from_date) if from_date else "all",
        dry_run=dry_run,
    )

    with connect(read_only=True) as conn:
        df = conn.execute(
            _EVENT_SQL,
            {
                "signal_threshold": SIGNAL_RETURN_THRESHOLD,
                "near_limit_up": NEAR_LIMIT_UP_THRESHOLD,
                "rs_tertile_quantile": RS_TOP_TERTILE_QUANTILE,
            },
        ).pl()

    # Compute stable event_id from _event_key (SQL sha256/encode not portable)
    import hashlib as _hl
    df = df.with_columns(
        pl.col("_event_key")
        .map_elements(
            lambda k: _hl.sha256(k.encode()).hexdigest(),
            return_dtype=pl.String,
        )
        .alias("event_id")
    ).drop("_event_key")
    # Reorder: event_id first
    df = df.select(["event_id"] + [c for c in df.columns if c != "event_id" and c != "_event_key"])

    if from_date is not None:
        df = df.filter(pl.col("signal_date") >= from_date)

    # ── Invariant: RS_T3 same-day coverage ≈ 33.3% ──────────────────────
    # Must be checked against the full universe (bullish_features), not
    # event rows — R8 events are concentrated in RS_T3 by construction.
    with connect(read_only=True) as conn2:
        rs_t3_coverage = conn2.execute("""
            WITH thresholds AS (
                SELECT date,
                       PERCENTILE_CONT($q) WITHIN GROUP (ORDER BY beta_adj_rs_20d)
                           AS threshold
                FROM bullish_features
                WHERE beta_adj_rs_20d IS NOT NULL
                GROUP BY date
            )
            SELECT AVG(CASE WHEN bf.beta_adj_rs_20d >= t.threshold THEN 1.0 ELSE 0.0 END)
            FROM bullish_features bf
            JOIN thresholds t ON t.date = bf.date
            WHERE bf.beta_adj_rs_20d IS NOT NULL
        """, {"q": RS_TOP_TERTILE_QUANTILE}).fetchone()[0]
    assert rs_t3_coverage is not None
    assert _RS_T3_COVERAGE_LO <= rs_t3_coverage <= _RS_T3_COVERAGE_HI, (
        f"RS_T3 universe coverage={rs_t3_coverage:.3f} outside "
        f"[{_RS_T3_COVERAGE_LO}, {_RS_T3_COVERAGE_HI}] — "
        f"check PERCENTILE_CONT quantile direction"
    )

    n_events = len(df)
    n_dates = df["signal_date"].n_unique()
    n_stocks = df["stock_id"].n_unique()
    n_near_limit_up = int(df["near_limit_up_flag"].sum())
    rs_t3_null_rows = int(df["rs_t3_t_minus_1"].null_count())
    n_regime_missing = int(df["regime_missing"].sum())

    assert n_events > 0, "No R8 events found — check panel date range"

    logger.info(
        "r8_event_builder_stats",
        n_events=n_events,
        n_unique_dates=n_dates,
        n_unique_stocks=n_stocks,
        n_near_limit_up=n_near_limit_up,
        rs_t3_null_rows=rs_t3_null_rows,
        n_regime_missing=n_regime_missing,
        rs_t3_same_day_coverage=round(float(rs_t3_coverage), 4),
    )

    if dry_run:
        logger.info("r8_event_builder_dry_run_complete", n_events=n_events)
        return df

    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.write_parquet(_OUTPUT_PARQUET)
    df.write_csv(_OUTPUT_CSV)

    s = get_settings()
    manifest = {
        "builder_version": _BUILDER_VERSION,
        "built_at": datetime.now().isoformat(),
        "git_commit": _git_commit(),
        "database_path": str(s.db_path),
        "spec_sha256": _file_sha256(_SPEC_PATH),
        "adr_sha256": _file_sha256(_ADR_PATH),
        "n_events": n_events,
        "n_unique_dates": n_dates,
        "n_unique_stocks": n_stocks,
        "n_near_limit_up": n_near_limit_up,
        "near_limit_up_fraction": round(n_near_limit_up / n_events, 4),
        "rs_t3_null_rows": rs_t3_null_rows,
        "rs_t3_same_day_coverage": round(float(rs_t3_coverage), 4),
        "n_regime_missing": n_regime_missing,
        "from_date": str(from_date) if from_date else None,
        "signal_return_threshold": SIGNAL_RETURN_THRESHOLD,
        "near_limit_up_threshold": NEAR_LIMIT_UP_THRESHOLD,
        "rs_top_tertile_quantile": RS_TOP_TERTILE_QUANTILE,
        "provisional": True,
        "provisional_reason": (
            "P1-DATA remediation pending: pre-listing contamination "
            "(18 stocks / 7331 rows), empty stock_info, empty corporate_actions"
        ),
        "output_parquet": str(_OUTPUT_PARQUET),
        "output_csv": str(_OUTPUT_CSV),
    }
    _OUTPUT_MANIFEST.write_text(json.dumps(manifest, indent=2))

    logger.info(
        "r8_event_builder_complete",
        parquet=str(_OUTPUT_PARQUET),
        manifest=str(_OUTPUT_MANIFEST),
    )
    return df


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="R8 Phase 1 event builder")
    p.add_argument(
        "--from-date",
        type=date.fromisoformat,
        default=None,
        help="Restrict to signal_date >= FROM_DATE (YYYY-MM-DD)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Build but do not write output files",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    df = build_events(from_date=args.from_date, dry_run=args.dry_run)
    print(df)
