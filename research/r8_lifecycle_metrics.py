# research/r8_lifecycle_metrics.py
"""R8 Phase 1 lifecycle metrics — v0.1.1.

Computes post-entry observational MA5 telemetry and lifecycle state
metrics for each R8 event. All metrics are descriptive only.

Governance (Observation vs Execution Boundary, per SPEC):
  These metrics record what happened after entry.
  They do NOT authorise any execution policy derived from MA5 state.

Metric definitions (canonical, locked for Phase 1):

  baseline_20d_high:
    max(adj_close[T-19 : T]) inclusive, computed as rolling_max(20)
    at signal_date via SQL window. Point-in-time as-of T close.
    Events where signal_idx < 19 (fewer than 20 prior trading rows)
    are flagged insufficient_history_flag=True; new_high_flag=None.

  new_high_flag:
    True if any adj_close in T+1..T+20 > baseline_20d_high.
    Baseline is fixed at T and does not update within the window.

  min_return_from_entry:
    min(adj_close[T+1..T+20]) / adj_open[T+1] - 1.
    Entry-to-trough return (NOT classical peak-to-trough drawdown).

  ma5_reclaim_count:
    Number of below->above MA5 transitions AFTER a prior break.
    A transition from below to above MA5 on day 1 (without a prior
    break) does not count as a reclaim.

  measurement_window_complete_flag:
    True if measurement_days == MEASUREMENT_WINDOW (20 trading days
    of data observed). False for recent events or suspended stocks.

Governance:
  - SPEC: research/r8_phase1_lifecycle_spec.md v0.1.2
  - ADR:  docs/decision_records/r8_phase1_bootstrap_adr.md
  - All outputs are PROVISIONAL pending P1-DATA remediation.

Usage:
  uv run python research/r8_lifecycle_metrics.py
  uv run python research/r8_lifecycle_metrics.py --dry-run
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
_OUTPUT_DIR = _REPO_ROOT / "data/_storage/r8_phase1"
_OUTPUT_PARQUET = _OUTPUT_DIR / "r8_lifecycle_metrics.parquet"
_OUTPUT_CSV = _OUTPUT_DIR / "r8_lifecycle_metrics.csv"
_OUTPUT_MANIFEST = _OUTPUT_DIR / "r8_lifecycle_metrics_manifest.json"

MA5_WINDOW: int = 5
BASELINE_HIGH_WINDOW: int = 20
MEASUREMENT_WINDOW: int = 20


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
# Price panel builder
# ---------------------------------------------------------------------------

def _build_price_panel() -> pl.DataFrame:
    """Load price panel with MA5, rolling_20d_high, and td_idx from SQL.

    td_idx is 0-based per stock (ROW_NUMBER - 1).
    rolling_20d_high uses Polars rolling_max(20) to match SQL semantics:
    includes current row, uses available rows at boundaries (min_periods=1).
    MA5 uses rolling_mean(5), null for first 4 rows per stock.

    Returns
    -------
    pl.DataFrame
        Columns: stock_id, date, adj_open, adj_close, td_idx,
                 ma5, rolling_20d_high.
    """
    with connect(read_only=True) as conn:
        price = conn.execute("""
            SELECT
                stock_id,
                date,
                adj_open,
                adj_close,
                ROW_NUMBER() OVER (
                    PARTITION BY stock_id ORDER BY date
                ) - 1 AS td_idx
            FROM listed_market_daily_price_adj
            ORDER BY stock_id, date
        """).pl()

    price = price.with_columns([
        pl.col("adj_close")
          .rolling_mean(MA5_WINDOW)
          .over("stock_id")
          .alias("ma5"),
        pl.col("adj_close")
          .rolling_max(BASELINE_HIGH_WINDOW)
          .over("stock_id")
          .alias("rolling_20d_high"),
    ])
    return price


# ---------------------------------------------------------------------------
# Per-event lifecycle metrics
# ---------------------------------------------------------------------------

def _compute_event_metrics(
    event_id: str,
    stock_id: str,
    signal_date: object,
    entry_adj_open: float | None,
    price_stock: pl.DataFrame,
    date_to_idx: dict,
) -> dict:
    """Compute lifecycle metrics for a single event.

    Parameters
    ----------
    event_id:
        Stable event identifier.
    stock_id:
        Stock identifier.
    signal_date:
        Signal day T.
    entry_adj_open:
        T+1 open price. None if entry is missing.
    price_stock:
        Price panel for this stock, sorted by date.
    date_to_idx:
        Pre-built {date: row_position} lookup for O(1) access.

    Returns
    -------
    dict
        Lifecycle metric row.
    """
    base: dict = {
        "event_id": event_id,
        "stock_id": stock_id,
        "signal_date": signal_date,
        "days_above_ma5": None,
        "first_ma5_break_date": None,
        "ma5_reclaim_count": None,
        "ma5_initially_above": None,
        "ma5_never_below": None,
        "pct_time_above_ma5": None,
        "min_return_from_entry": None,
        "new_high_flag": None,
        "baseline_20d_high": None,
        "insufficient_history_flag": False,
        "measurement_days": None,
        "measurement_window_complete_flag": False,
        "metrics_missing_flag": True,
    }

    if entry_adj_open is None or entry_adj_open <= 0:
        return base

    signal_idx = date_to_idx.get(signal_date)
    if signal_idx is None:
        return base

    # Insufficient history: fewer than BASELINE_HIGH_WINDOW prior rows
    if signal_idx < BASELINE_HIGH_WINDOW - 1:
        base["insufficient_history_flag"] = True
        base["metrics_missing_flag"] = False
        # Still compute MA5 metrics even with insufficient baseline history
        # Only new_high_flag is suppressed (None)

    # baseline_20d_high from precomputed rolling_20d_high at signal row
    baseline_20d_high = price_stock["rolling_20d_high"][signal_idx]

    # Measurement window: T+1 .. T+MEASUREMENT_WINDOW (inclusive)
    window_start = signal_idx + 1
    window_end = signal_idx + MEASUREMENT_WINDOW + 1
    window = price_stock[window_start:window_end]
    n = len(window)

    if n == 0:
        base["metrics_missing_flag"] = False
        return base

    closes = window["adj_close"].to_list()
    ma5s = window["ma5"].to_list()
    w_dates = window["date"].to_list()

    # MA5 states (only where both close and ma5 are non-null)
    above_ma5 = [
        c > m
        for c, m in zip(closes, ma5s)
        if c is not None and m is not None
    ]
    valid_days = len(above_ma5)
    days_above = sum(above_ma5)

    # first_ma5_break_date
    first_break_date = None
    for c, m, d in zip(closes, ma5s, w_dates):
        if c is not None and m is not None and c < m:
            first_break_date = d
            break

    # ma5_reclaim_count: below->above transitions AFTER a prior break
    # A transition on day 1 without prior break does not count.
    reclaim_count = 0
    seen_break = False
    for state in above_ma5:
        if not state:
            seen_break = True
        elif seen_break:
            reclaim_count += 1
            seen_break = False

    ma5_initially_above = above_ma5[0] if above_ma5 else None
    ma5_never_below = all(above_ma5) if above_ma5 else None

    # min_return_from_entry (entry-to-trough, NOT peak-to-trough)
    valid_closes = [c for c in closes if c is not None]
    min_return = (
        min(valid_closes) / entry_adj_open - 1.0
        if valid_closes else None
    )

    # new_high_flag
    if base["insufficient_history_flag"] or baseline_20d_high is None:
        new_high = None
    else:
        new_high = any(
            c > baseline_20d_high for c in closes if c is not None
        )

    base.update({
        "days_above_ma5": days_above,
        "first_ma5_break_date": first_break_date,
        "ma5_reclaim_count": reclaim_count,
        "ma5_initially_above": ma5_initially_above,
        "ma5_never_below": ma5_never_below,
        "pct_time_above_ma5": days_above / valid_days if valid_days > 0 else None,
        "min_return_from_entry": min_return,
        "new_high_flag": new_high,
        "baseline_20d_high": baseline_20d_high,
        "measurement_days": n,
        "measurement_window_complete_flag": n == MEASUREMENT_WINDOW,
        "metrics_missing_flag": False,
    })
    return base


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_lifecycle_metrics(dry_run: bool = False) -> pl.DataFrame:
    """Compute MA5 lifecycle metrics for all R8 events.

    Parameters
    ----------
    dry_run:
        If True, compute and return without writing output files.

    Returns
    -------
    pl.DataFrame
        One row per R8 event with lifecycle telemetry.
    """
    _assert_governance_files()

    for label, path in [
        ("events", _EVENTS_PARQUET),
        ("forward_returns", _FWD_RETURNS_PARQUET),
    ]:
        if not path.exists():
            raise FileNotFoundError(
                f"{label} parquet not found: {path}\n"
                "Run r8_event_builder.py and r8_forward_returns.py first."
            )

    logger.info(
        "r8_lifecycle_metrics_start",
        version=_BUILDER_VERSION,
        dry_run=dry_run,
    )

    events = pl.read_parquet(_EVENTS_PARQUET)
    fwd = pl.read_parquet(_FWD_RETURNS_PARQUET)

    events = events.join(
        fwd.select(["event_id", "entry_adj_open", "entry_missing_flag"]),
        on="event_id",
        how="left",
    )

    logger.info("building_price_panel")
    price = _build_price_panel()

    results = []
    stocks = events["stock_id"].unique().to_list()
    logger.info("processing_events", n_stocks=len(stocks))

    for stock_id in stocks:
        price_stock = price.filter(
            pl.col("stock_id") == stock_id
        ).sort("date")

        # O(1) date lookup
        date_to_idx = {
            d: i for i, d in enumerate(price_stock["date"].to_list())
        }

        ev_stock = events.filter(pl.col("stock_id") == stock_id)

        for row in ev_stock.iter_rows(named=True):
            metrics = _compute_event_metrics(
                event_id=row["event_id"],
                stock_id=stock_id,
                signal_date=row["signal_date"],
                entry_adj_open=row.get("entry_adj_open"),
                price_stock=price_stock,
                date_to_idx=date_to_idx,
            )
            results.append(metrics)

    df = pl.DataFrame(results)

    n_missing = int(df["metrics_missing_flag"].sum())
    n_insufficient = int(df["insufficient_history_flag"].sum())
    n_new_high = int(df["new_high_flag"].drop_nulls().sum())
    n_complete = int(df["measurement_window_complete_flag"].sum())
    avg_days_above = df["days_above_ma5"].drop_nulls().mean()

    logger.info(
        "r8_lifecycle_metrics_stats",
        n_events=len(df),
        n_metrics_missing=n_missing,
        n_insufficient_history=n_insufficient,
        n_new_high_flag=n_new_high,
        n_window_complete=n_complete,
        avg_days_above_ma5=(
            round(float(avg_days_above), 2) if avg_days_above else None
        ),
    )

    if dry_run:
        logger.info(
            "r8_lifecycle_metrics_dry_run_complete",
            n_events=len(df),
        )
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
        "n_events": len(df),
        "n_metrics_missing": n_missing,
        "n_insufficient_history": n_insufficient,
        "n_new_high_flag": n_new_high,
        "n_window_complete": n_complete,
        "ma5_window": MA5_WINDOW,
        "baseline_high_window": BASELINE_HIGH_WINDOW,
        "measurement_window": MEASUREMENT_WINDOW,
        "metric_definitions": {
            "new_high_flag": (
                "baseline_20d_high = rolling_max(adj_close, 20) at signal date T; "
                "new_high_flag = any close in T+1..T+20 > baseline_20d_high; "
                "None if insufficient_history_flag=True"
            ),
            "min_return_from_entry": (
                "min(adj_close[T+1..T+20]) / adj_open[T+1] - 1; "
                "entry-to-trough; NOT classical peak-to-trough drawdown"
            ),
            "ma5_reclaim_count": (
                "below->above MA5 transitions after a prior break; "
                "day-1 above without prior break does not count; "
                "counts episodes, not total crossings"
            ),
            "ma5_initially_above": (
                "MA5 state on first valid MA5 observation day (may be T+4 "
                "if MA5 is null on T+1 through T+3 due to insufficient history)"
            ),
            "baseline_20d_high_note": (
                "baseline_20d_high may be populated even when "
                "insufficient_history_flag=True (rolling_max uses available rows); "
                "new_high_flag is suppressed (None) in that case"
            ),
        },
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
        "r8_lifecycle_metrics_complete",
        parquet=str(_OUTPUT_PARQUET),
        manifest=str(_OUTPUT_MANIFEST),
    )
    return df


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="R8 Phase 1 lifecycle metrics")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute but do not write output files",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    df = build_lifecycle_metrics(dry_run=args.dry_run)
    print(df.select([
        "event_id", "stock_id", "signal_date",
        "days_above_ma5", "pct_time_above_ma5",
        "first_ma5_break_date", "ma5_reclaim_count",
        "ma5_initially_above", "ma5_never_below",
        "min_return_from_entry", "new_high_flag",
        "baseline_20d_high", "measurement_days",
        "measurement_window_complete_flag",
        "insufficient_history_flag",
    ]).head(10))
