# research/r8_forward_returns.py
"""R8 Phase 1 forward return calculator — v0.1.0.

Computes forward returns for each R8 event at standardised horizons.
Entry anchor is T+1 open (first tradable price after signal day).
All horizons are measured in trading days via price-panel row ordering
(ROW_NUMBER over daily_price_adj), consistent with SPEC LA-8.

Forward return formula (frozen per SPEC):
    ret_{h}d = adj_close[T+h] / adj_open[T+1] - 1
    where h in {1, 3, 5, 10, 20} trading days

Suspension gaps: events with missing horizon prices are retained with
null return values and flagged via *_missing_flag columns. Do not filter
these rows here; filtering belongs in downstream sensitivity layers.

Governance:
  - SPEC: research/r8_phase1_lifecycle_spec.md v0.1.2 (LA-1, LA-8, AC-1)
  - ADR:  docs/decision_records/r8_phase1_bootstrap_adr.md
  - All outputs are PROVISIONAL pending P1-DATA remediation.

Usage:
  uv run python research/r8_forward_returns.py
  uv run python research/r8_forward_returns.py --dry-run
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
_BUILDER_VERSION = "0.1.0"
_SPEC_PATH = _REPO_ROOT / "research/r8_phase1_lifecycle_spec.md"
_ADR_PATH = _REPO_ROOT / "docs/decision_records/r8_phase1_bootstrap_adr.md"
_EVENTS_PARQUET = _REPO_ROOT / "data/_storage/r8_phase1/r8_events.parquet"
_OUTPUT_DIR = _REPO_ROOT / "data/_storage/r8_phase1"
_OUTPUT_PARQUET = _OUTPUT_DIR / "r8_forward_returns.parquet"
_OUTPUT_CSV = _OUTPUT_DIR / "r8_forward_returns.csv"
_OUTPUT_MANIFEST = _OUTPUT_DIR / "r8_forward_returns_manifest.json"

HORIZONS: list[int] = [1, 3, 5, 10, 20]

# ---------------------------------------------------------------------------
# SQL: price panel with trading-day index
# ---------------------------------------------------------------------------
_PRICE_RANKED_SQL = """
SELECT
    stock_id,
    date,
    adj_open,
    adj_close,
    ROW_NUMBER() OVER (PARTITION BY stock_id ORDER BY date) AS td_idx
FROM daily_price_adj
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
# Core builder
# ---------------------------------------------------------------------------

def build_forward_returns(dry_run: bool = False) -> pl.DataFrame:
    """Compute forward returns for all R8 events.

    Parameters
    ----------
    dry_run:
        If True, compute and return without writing output files.

    Returns
    -------
    pl.DataFrame
        One row per R8 event with forward returns at each horizon.
    """
    _assert_governance_files()

    if not _EVENTS_PARQUET.exists():
        raise FileNotFoundError(
            f"Event table not found: {_EVENTS_PARQUET}\n"
            "Run r8_event_builder.py first."
        )

    logger.info(
        "r8_forward_returns_start",
        version=_BUILDER_VERSION,
        dry_run=dry_run,
    )

    # Load event table
    events = pl.read_parquet(_EVENTS_PARQUET)
    n_events = len(events)
    logger.info("events_loaded", n_events=n_events)

    # Load price panel with trading-day index
    with connect(read_only=True) as conn:
        price = conn.execute(_PRICE_RANKED_SQL).pl()

    # Build lookup: (stock_id, date) -> (td_idx, adj_open, adj_close)
    # Use join strategy: merge events with price on signal_date to get td_idx
    events_with_idx = events.select(
        ["event_id", "stock_id", "signal_date"]
    ).join(
        price.select(["stock_id", "date", "td_idx"]).rename({"date": "signal_date"}),
        on=["stock_id", "signal_date"],
        how="left",
    )

    # For each event, compute T+1 open and forward closes
    # Strategy: join price panel at td_idx + 1 for entry, td_idx + h for each horizon
    # Entry: T+1 open
    entry = price.select(["stock_id", "td_idx", "adj_open"]).rename(
        {"td_idx": "entry_td_idx", "adj_open": "entry_adj_open"}
    )

    df = events_with_idx.with_columns(
        (pl.col("td_idx") + 1).alias("entry_td_idx")
    ).join(
        entry,
        on=["stock_id", "entry_td_idx"],
        how="left",
    )

    # entry_missing_flag
    df = df.with_columns(
        pl.col("entry_adj_open").is_null().alias("entry_missing_flag")
    )

    # Forward closes at each horizon
    for h in HORIZONS:
        horizon_price = price.select(
            ["stock_id", "td_idx", "adj_close", "date"]
        ).rename({
            "td_idx": f"h{h}_td_idx",
            "adj_close": f"adj_close_t{h}d",
            "date": f"date_t{h}d",
        })

        df = df.with_columns(
            (pl.col("td_idx") + h).alias(f"h{h}_td_idx")
        ).join(
            horizon_price,
            on=["stock_id", f"h{h}_td_idx"],
            how="left",
        )

        # Forward return: adj_close[T+h] / adj_open[T+1] - 1
        df = df.with_columns(
            (pl.col(f"adj_close_t{h}d") / pl.col("entry_adj_open") - 1.0)
            .alias(f"ret_{h}d"),
            pl.col(f"adj_close_t{h}d").is_null().alias(f"ret_{h}d_missing_flag"),
        )

        # Calendar gap: calendar days from signal_date to horizon date
        df = df.with_columns(
            (pl.col(f"date_t{h}d") - pl.col("signal_date"))
            .dt.total_days()
            .alias(f"calendar_gap_t_to_{h}d")
        )

        # Drop intermediate columns
        df = df.drop([f"h{h}_td_idx", f"adj_close_t{h}d"])

    # Drop td_idx (internal index, not needed downstream)
    df = df.drop(["entry_td_idx", "td_idx"])

    # Reattach core event columns from events table
    core_cols = [
        "event_id", "stock_id", "signal_date", "regime_t_minus_1",
        "near_limit_up_flag", "rs_t3_t_minus_1", "rs_rank_pct_t_minus_1",
        "signal_daily_return", "calendar_gap_days",
    ]
    result = events.select(
        [c for c in core_cols if c in events.columns]
    ).join(
        df.drop(["stock_id", "signal_date"]),
        on="event_id",
        how="left",
    )

    # ── Stats ────────────────────────────────────────────────────────────
    null_entry = int(result["entry_missing_flag"].sum())
    null_horizons = {
        str(h): int(result[f"ret_{h}d_missing_flag"].sum())
        for h in HORIZONS
    }
    max_gaps = {}
    for h in HORIZONS:
        col = f"calendar_gap_t_to_{h}d"
        val = result[col].drop_nulls().max()
        max_gaps[str(h)] = int(val) if val is not None else None

    logger.info(
        "r8_forward_returns_stats",
        n_events=len(result),
        null_entry_rows=null_entry,
        null_horizon_rows=null_horizons,
        max_calendar_gap_by_horizon=max_gaps,
    )

    if dry_run:
        logger.info("r8_forward_returns_dry_run_complete", n_events=len(result))
        return result

    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result.write_parquet(_OUTPUT_PARQUET)
    result.write_csv(_OUTPUT_CSV)

    s = get_settings()
    manifest = {
        "builder_version": _BUILDER_VERSION,
        "built_at": datetime.now().isoformat(),
        "git_commit": _git_commit(),
        "database_path": str(s.db_path),
        "events_parquet": str(_EVENTS_PARQUET),
        "spec_sha256": _file_sha256(_SPEC_PATH),
        "adr_sha256": _file_sha256(_ADR_PATH),
        "n_events": len(result),
        "horizons": HORIZONS,
        "null_entry_rows": null_entry,
        "null_horizon_rows": null_horizons,
        "max_calendar_gap_by_horizon": max_gaps,
        "forward_return_formula": "adj_close[T+h] / adj_open[T+1] - 1",
        "horizon_definition": "trading days via price-panel ROW_NUMBER",
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
        "r8_forward_returns_complete",
        parquet=str(_OUTPUT_PARQUET),
        manifest=str(_OUTPUT_MANIFEST),
    )
    return result


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="R8 Phase 1 forward return calculator")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute but do not write output files",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    df = build_forward_returns(dry_run=args.dry_run)
    print(df.select([
        "event_id", "stock_id", "signal_date",
        "entry_adj_open", "entry_missing_flag",
        "ret_1d", "ret_5d", "ret_20d",
        "ret_20d_missing_flag",
    ]))
