# research/p1_data_contamination_audit.py
"""P1-DATA contamination impact audit — v0.1.0.

Step 3 of P1-DATA remediation: quantify the blast radius of IF-1
pre-listing contamination before and after remediation.

Produces:
    data/_storage/r8_phase1/p1_data_contamination_impact.json

Hard gates (regression-safe):
    total_excluded_rows  == 7331
    affected_r8_events   == 463

Re-run this script before Step 4 (R8 Phase 1 rerun) to confirm that
the contamination baseline has not changed.

Governance
----------
SPEC : docs/decision_records/p1_data_remediation_spec.md v1.0.0
AC-4 : Contamination impact report produced (Step 3 output)

Usage
-----
    uv run python research/p1_data_contamination_audit.py
"""

import datetime
import json
from pathlib import Path

import duckdb
import structlog

# ---------------------------------------------------------------------------
# Paths and baselines
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "data" / "_storage" / "helios.duckdb"
R8_EVENTS_PATH = REPO_ROOT / "data" / "_storage" / "r8_phase1" / "r8_events.parquet"
OUT_PATH = REPO_ROOT / "data" / "_storage" / "r8_phase1" / "p1_data_contamination_impact.json"

SEED_SHA256 = "6a0989936f2ab382b42a505d4cdd936a08a186709c11b1b29d74bb2647c4625a"

# Baselines established during Step 3 audit (2026-06-04).
# These are hard gates: deviation indicates either a data change or a
# remediation error and must be investigated before proceeding to Step 4.
BASELINE_EXCLUDED_ROWS = 7331
BASELINE_AFFECTED_R8_EVENTS = 463

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

_EXCLUDED_BY_STOCK_SQL = """
    SELECT
        p.stock_id,
        CAST(s.mainboard_date AS VARCHAR)   AS mainboard_date,
        COUNT(*)                            AS excluded_rows,
        CAST(MIN(p.date) AS VARCHAR)        AS first_excluded,
        CAST(MAX(p.date) AS VARCHAR)        AS last_excluded
    FROM daily_price_adj p
    JOIN security_lifecycle s ON p.stock_id = s.stock_id
    WHERE p.date < s.mainboard_date
    GROUP BY p.stock_id, s.mainboard_date
    ORDER BY excluded_rows DESC
"""

_AFFECTED_EVENTS_SQL = """
    SELECT
        e.stock_id,
        COUNT(*)                              AS affected_events,
        CAST(MIN(e.signal_date) AS VARCHAR)   AS first_event,
        CAST(MAX(e.signal_date) AS VARCHAR)   AS last_event
    FROM read_parquet('{r8_events}') e
    JOIN security_lifecycle s ON e.stock_id = s.stock_id
    WHERE e.signal_date < s.mainboard_date
    GROUP BY e.stock_id
    ORDER BY affected_events DESC
"""

_TOTAL_EVENTS_SQL = "SELECT COUNT(*) FROM read_parquet('{r8_events}')"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Run contamination impact audit and write JSON report."""
    log.info("audit_start", db=str(DB_PATH), r8_events=str(R8_EVENTS_PATH))

    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        # --- Query A: excluded rows by stock ---
        excluded_by_stock = con.execute(_EXCLUDED_BY_STOCK_SQL).fetchall()
        total_excluded = sum(r[2] for r in excluded_by_stock)

        log.info(
            "excluded_rows_computed",
            total=total_excluded,
            stocks=len(excluded_by_stock),
        )

        # --- Query B: affected R8 events by stock ---
        r8_path = str(R8_EVENTS_PATH)
        affected_events = con.execute(
            _AFFECTED_EVENTS_SQL.format(r8_events=r8_path)
        ).fetchall()
        total_events = con.execute(
            _TOTAL_EVENTS_SQL.format(r8_events=r8_path)
        ).fetchone()[0]
        total_affected = sum(r[1] for r in affected_events)

    log.info(
        "affected_events_computed",
        total_r8_events=total_events,
        affected=total_affected,
        affected_stocks=len(affected_events),
        affected_fraction_pct=round(total_affected / total_events * 100, 2),
    )

    # --- Build report ---
    report = {
        "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "spec_version": "1.0.0",
        "seed_sha256": SEED_SHA256,
        "summary": {
            "total_excluded_rows": total_excluded,
            "stocks_with_exclusions": len(excluded_by_stock),
            "total_r8_events": total_events,
            "affected_r8_events": total_affected,
            "affected_r8_stocks": len(affected_events),
            "affected_fraction_pct": round(total_affected / total_events * 100, 2),
        },
        "excluded_rows_by_stock": [
            {
                "stock_id": r[0],
                "mainboard_date": r[1],
                "excluded_rows": r[2],
                "first_excluded": r[3],
                "last_excluded": r[4],
            }
            for r in excluded_by_stock
        ],
        "affected_r8_events_by_stock": [
            {
                "stock_id": r[0],
                "affected_events": r[1],
                "first_event": r[2],
                "last_event": r[3],
            }
            for r in affected_events
        ],
        "residual_risks": [
            "SUSPENSION_GAP: 203 rows, 90 stocks; deferred pending halt/suspension dataset",
            "Transfer-board post-listing anomalies: 4583, 6770, 6789; tracked as P1-DATA-TB",
            "corporate_actions empty: cum_factor=1.0 for all stocks; DQ-CA-001",
        ],
        "ac4_status": "PASS",
    }

    # --- Hard gates: fail before writing if baselines deviate ---
    summary = report["summary"]
    if summary["total_excluded_rows"] != BASELINE_EXCLUDED_ROWS:
        raise RuntimeError(
            f"AC-4 FAIL: expected {BASELINE_EXCLUDED_ROWS} excluded rows, "
            f"got {summary['total_excluded_rows']}. "
            "Investigate before proceeding to Step 4."
        )
    if summary["affected_r8_events"] != BASELINE_AFFECTED_R8_EVENTS:
        raise RuntimeError(
            f"AC-4 FAIL: expected {BASELINE_AFFECTED_R8_EVENTS} affected R8 events, "
            f"got {summary['affected_r8_events']}. "
            "Investigate before proceeding to Step 4."
        )

    OUT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    log.info(
        "ac4_pass",
        output=str(OUT_PATH),
        total_excluded_rows=summary["total_excluded_rows"],
        affected_r8_events=summary["affected_r8_events"],
        affected_fraction_pct=summary["affected_fraction_pct"],
    )

    print("\nAC-4 PASS")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
