#!/usr/bin/env python3
# scripts/audit_r8_phase1_cell_adequacy.py
"""R8 Phase 1 cell adequacy audit — v0.1.0. Implements P0-B
r8_phase1_cell_adequacy_spec.md v0.1.1.

Panel construction verified against production schema (2026-06-06):

    listed_market_daily_price_adj  (post-listing gate, adj prices)
        + bullish_features         (RS metric, dist_above_ma20_atr)
        + market_regime            (market-level regime)

R8 event definition from research/r8_event_builder.py (lines 85–95):
    r8_flag = 1  iff  adj_close / prev_adj_close − 1 >= 0.05
                 AND  adj_close > adj_open
                 AND  prev_adj_close IS NOT NULL
                 AND  prev_adj_close > 0

near_limit_up (r8_event_builder.py line 88, ADR-R8P1-002 SD-1):
    adj_close / prev_adj_close − 1 >= 0.095

RS_T3 (r8_event_builder.py line 57, ADR-R8P1-002 §Symbols):
    beta_adj_rs_20d > QUANTILE_CONT(beta_adj_rs_20d, 2/3)
    OVER (PARTITION BY date)   [cross-sectional on anchor date]

Regime (ADR-R8P1-002 D4):
    market_regime.regime lagged by one trading date inside this script
    to produce regime[d−1].  The table contains regime[d]; the lag is
    applied via LAG(regime) OVER (ORDER BY date).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

import duckdb

# ---------------------------------------------------------------------------
# Governance constants — from three locked artifacts.
# ---------------------------------------------------------------------------

AUDIT_SPEC_VERSION: Final[str] = "v0.1.1"
ADR_001_VERSION: Final[str] = "v0.1.0"
ADR_002_VERSION: Final[str] = "v0.1.0"
LIFECYCLE_SPEC_VERSION: Final[str] = "v0.1.2"
SCRIPT_VERSION: Final[str] = "v0.1.0"

# ADR-R8P1-002 D3 + SD-1 β interpretation.
BENCHMARK_2_INTERPRETATION: Final[str] = (
    "beta_symmetric: dist_above_ma20_atr<0 filter applied to both "
    "treatment and baseline rows (ADR-R8P1-002 D3 + SD-1 beta)"
)

# Signal and near-limit-up thresholds — verified from r8_event_builder.py.
SIGNAL_RETURN_THRESHOLD: Final[float] = 0.05
NEAR_LIMIT_UP_THRESHOLD: Final[float] = 0.095
RS_TOP_TERTILE_QUANTILE: Final[float] = 2.0 / 3.0   # PERCENTILE_CONT(2/3)
RS_BOTTOM_TERTILE_QUANTILE: Final[float] = 1.0 / 3.0

# Gate thresholds — P0-B §Gate Definition.
PASS_THRESHOLD: Final[int] = 100
DIRECTIONAL_MIN_THRESHOLD: Final[int] = 30

# Closed enums per AAC-7 and AAC-8.
ALLOWED_BASELINE_UNIVERSES: Final[tuple[str, ...]] = ("Baseline_1", "Baseline_2")
ALLOWED_REASON_VALUES: Final[tuple[str | None, ...]] = (
    None,
    "n_unique_dates<30",
    "30<=n_unique_dates<100",
)
ALLOWED_CLASSIFICATIONS: Final[tuple[str, ...]] = (
    "PASS",
    "DIRECTIONAL_ONLY",
    "INSUFFICIENT",
)

# RS tertile label values — per P0-B D-1 schema and r8_event_builder convention.
RS_T3_LABEL: Final[str] = "RS_T3"
RS_T2_LABEL: Final[str] = "RS_T2"
RS_T1_LABEL: Final[str] = "RS_T1"
RS_LABEL_SET: Final[frozenset[str]] = frozenset({RS_T1_LABEL, RS_T2_LABEL, RS_T3_LABEL})

# Source tables / view — verified from production schema 2026-06-06.
PRICE_VIEW: Final[str] = "listed_market_daily_price_adj"
BULLISH_TABLE: Final[str] = "bullish_features"
MARKET_REGIME_TABLE: Final[str] = "market_regime"

# Column name defaults — confirmed from DESCRIBE output 2026-06-06.
DEFAULT_STOCK_ID_COL: Final[str] = "stock_id"
DEFAULT_DATE_COL: Final[str] = "date"
DEFAULT_ADJ_CLOSE_COL: Final[str] = "adj_close"
DEFAULT_ADJ_OPEN_COL: Final[str] = "adj_open"
DEFAULT_RS_METRIC_COL: Final[str] = "beta_adj_rs_20d"
DEFAULT_DIST_COL: Final[str] = "dist_above_ma20_atr"
DEFAULT_REGIME_COL: Final[str] = "regime"

DEFAULT_OUTPUT_DIR: Final[Path] = Path(
    "data/_storage/r8_phase1_cell_adequacy"
) / AUDIT_SPEC_VERSION
DEFAULT_DB_PATH: Final[Path] = Path("data/_storage/helios.duckdb")

# Expected output column sets — locked from P0-B v0.1.1 §Outputs.
# AAC-6 layer 2: any column set deviation (extra or missing) is a governance failure.
EXPECTED_OUTPUT_COLUMNS: Final[dict[str, tuple[str, ...]]] = {
    "d1_r8_x_rs_tertile": (
        "rs_tertile",
        "r8_flag",
        "n_observations",
        "n_unique_dates",
    ),
    "d2_global_adequacy": (
        "regime",
        "near_limit_up",
        "n_events",
        "n_unique_dates",
        "events_per_date_mean",
        "events_per_date_p95",
        "classification",
        "must_propagate",
        "must_propagate_reason",
    ),
    "d2a_a3_support": (
        "regime",
        "near_limit_up",
        "n_events",
        "n_unique_dates",
        "events_per_date_mean",
        "events_per_date_p95",
        "classification",
        "must_propagate",
        "must_propagate_reason",
    ),
    "d2b_baseline_adequacy": (
        "baseline_universe",
        "regime",
        "near_limit_up",
        "n_observations",
        "n_unique_dates",
        "events_per_date_mean",
        "events_per_date_p95",
        "classification",
        "must_propagate",
        "must_propagate_reason",
    ),
}

# AAC-6 layer 1: forbidden tokens in emitted SQL.
AAC6_FORBIDDEN_TOKENS: Final[tuple[str, ...]] = (
    "forward_return",
    "fwd_return",
    "ret_h",
    "return_h",
    "mean_return",
    "median_return",
    "median(",
    "hit_rate",
    "win_rate",
    "bootstrap",
    "confidence_interval",
    "percentile_ci",
    "stationary_bootstrap",
)

LOGGER: Final[logging.Logger] = logging.getLogger("audit_r8_phase1_cell_adequacy")


# ---------------------------------------------------------------------------
# Error type.
# ---------------------------------------------------------------------------


class AuditError(RuntimeError):
    """Raised when any P0-B v0.1.1 invariant or acceptance criterion fails."""


# ---------------------------------------------------------------------------
# Resolved schema dataclass.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ColumnMap:
    """Resolved source column names across the three production tables.

    Persisted verbatim in the manifest per P0-B Inv #2 and AAC-4.
    """

    # Shared primary key convention (stock_id, date) — same in
    # listed_market_daily_price_adj and bullish_features.
    stock_id: str
    date: str
    # listed_market_daily_price_adj columns.
    adj_close: str
    adj_open: str
    # bullish_features columns.
    # rs_metric is the de-circularised RS column per LA-4 (beta_adj_rs_20d
    # confirmed via correlation check against forward_return_observations
    # on 2026-06-06; diff vs beta_adj_rs_60d was ~0.003 vs ~0.19-0.50).
    rs_metric: str
    dist_above_ma20_atr: str
    # market_regime column.
    regime: str


# ---------------------------------------------------------------------------
# Logging.
# ---------------------------------------------------------------------------


def configure_logging(verbose: bool) -> None:
    """Configure CLI logging at INFO (default) or DEBUG (verbose)."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


# ---------------------------------------------------------------------------
# Provenance helpers.
# ---------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    """Return SHA-256 hex digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head_sha() -> str | None:
    """Return current git HEAD SHA, or None if unavailable."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def git_is_dirty() -> bool | None:
    """Return True if working tree has uncommitted changes, else False."""
    try:
        return bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


# ---------------------------------------------------------------------------
# DuckDB helpers.
# ---------------------------------------------------------------------------


def q(identifier: str) -> str:
    """Return a DuckDB-safe double-quoted identifier."""
    return f'"{identifier.replace(chr(34), chr(34) + chr(34))}"'


def lit(value: str) -> str:
    """Return a single-quoted SQL string literal."""
    return f"'{value.replace(chr(39), chr(39) + chr(39))}'"


def fetch_scalar(con: duckdb.DuckDBPyConnection, sql: str) -> Any:
    """Execute a query and return its first scalar value."""
    row = con.execute(sql).fetchone()
    return None if row is None else row[0]


def column_names(
    con: duckdb.DuckDBPyConnection, relation: str
) -> list[str]:
    """Return ordered column names for a DuckDB table or view."""
    return [
        str(r[0])
        for r in con.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = ?
            ORDER BY ordinal_position
            """,
            [relation],
        ).fetchall()
    ]


def relation_exists(
    con: duckdb.DuckDBPyConnection, relation: str
) -> bool:
    """Return True if a table or view exists in the connected DB."""
    row = con.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
        [relation],
    ).fetchone()
    return bool(row and row[0] > 0)


# ---------------------------------------------------------------------------
# Schema discovery and validation.
# ---------------------------------------------------------------------------


def resolve_columns(
    con: duckdb.DuckDBPyConnection,
    args: argparse.Namespace,
) -> ColumnMap:
    """Verify all required tables exist and all requested columns are present.

    Checks three production tables separately; fails on first missing column
    with no fallback resolution.
    """
    required_relations = [PRICE_VIEW, BULLISH_TABLE, MARKET_REGIME_TABLE]
    for rel in required_relations:
        if not relation_exists(con, rel):
            raise AuditError(
                f"Required relation missing: {rel}. "
                "Check that the DuckDB file path is correct and the "
                "upstream ETL has been run."
            )

    price_cols = set(column_names(con, PRICE_VIEW))
    bullish_cols = set(column_names(con, BULLISH_TABLE))
    regime_cols = set(column_names(con, MARKET_REGIME_TABLE))

    requirements: list[tuple[str, str, set[str], str]] = [
        ("stock_id", args.stock_id_col, price_cols & bullish_cols, PRICE_VIEW),
        ("date",     args.date_col,     price_cols & bullish_cols, PRICE_VIEW),
        ("adj_close", args.adj_close_col, price_cols, PRICE_VIEW),
        ("adj_open",  args.adj_open_col,  price_cols, PRICE_VIEW),
        ("rs_metric", args.rs_metric_col, bullish_cols, BULLISH_TABLE),
        ("dist_above_ma20_atr", args.dist_above_ma20_atr_col,
         bullish_cols, BULLISH_TABLE),
        ("regime",   args.regime_col,   regime_cols, MARKET_REGIME_TABLE),
    ]

    missing: list[str] = []
    for label, requested, available, table in requirements:
        if requested not in available:
            missing.append(
                f"{label}: requested {requested!r} not found in {table} "
                f"(available: {sorted(available)})"
            )

    if missing:
        raise AuditError(
            "Schema validation failed — no fallback resolution:\n  - "
            + "\n  - ".join(missing)
            + "\nFix by passing the correct column name via the CLI flag "
            "for the failing field."
        )

    cols = ColumnMap(
        stock_id=args.stock_id_col,
        date=args.date_col,
        adj_close=args.adj_close_col,
        adj_open=args.adj_open_col,
        rs_metric=args.rs_metric_col,
        dist_above_ma20_atr=args.dist_above_ma20_atr_col,
        regime=args.regime_col,
    )
    LOGGER.info("Resolved columns: %s", asdict(cols))
    return cols


def verify_bullish_features_uniqueness(
    con: duckdb.DuckDBPyConnection,
    cols: ColumnMap,
) -> int:
    """Verify (stock_id, date) is unique in bullish_features.

    Per ADR-R8P1-002 D5: dist_above_ma20_atr is one scalar per (date, stock).
    PIT discipline (bullish_features.computed_at) is the upstream pipeline's
    responsibility; this check verifies the downstream invariant it implies.
    """
    dup_count = fetch_scalar(
        con,
        f"""
        SELECT COUNT(*) FROM (
            SELECT {q(cols.stock_id)}, {q(cols.date)}
            FROM {BULLISH_TABLE}
            GROUP BY 1, 2
            HAVING COUNT(*) > 1
        )
        """,
    )
    if dup_count and dup_count > 0:
        raise AuditError(
            f"bullish_features uniqueness violated: {dup_count} duplicate "
            "(stock_id, date) groups. ADR-R8P1-002 D5 requires one scalar "
            "per (date, stock). Investigate bullish_features.computed_at "
            "deduplication in the upstream pipeline."
        )
    return int(dup_count or 0)


# ---------------------------------------------------------------------------
# Pre-run attestations.
# ---------------------------------------------------------------------------


def assert_temporal_attestations(args: argparse.Namespace) -> None:
    """Enforce mandatory attestations about source-column temporal semantics.

    Two facts cannot be inferred from column names alone and require
    explicit confirmation by the operator before running:

    1. RS metric de-circularisation:
       bullish_features.beta_adj_rs_20d at date d is computed with the
       signal-day return EXCLUDED from the rolling RS window (the feature
       pipeline handles this upstream per ADR-R8P1-002 §Symbols / LA-4).
       The audit script joins bullish_features at the same date d as the
       signal row; the T-1 semantic comes from upstream de-circularisation,
       not from a date-shift in this script.

    2. Market regime source:
       market_regime.regime contains regime[d] (today's regime), not
       regime[d-1].  This script applies LAG(regime) OVER (ORDER BY date)
       to derive regime[d-1] per ADR-R8P1-002 D4.  The attestation confirms
       the table contains one row per trading date with the at-date regime
       label, so the LAG operation produces the correct T-1 value.
    """
    missing: list[str] = []
    if not args.rs_decirc_confirmed:
        missing.append(
            "--rs-decirc-confirmed  (bullish_features.{rs_metric} is "
            "de-circularised per LA-4: signal candle excluded from RS "
            "window upstream)"
        )
    if not args.regime_lag_source_confirmed:
        missing.append(
            "--regime-lag-source-confirmed  (market_regime has one row "
            "per trading date with regime[d]; script applies LAG for "
            "regime[d-1] per ADR-R8P1-002 D4)"
        )
    if missing:
        raise AuditError(
            "Temporal-semantics attestations missing:\n  - "
            + "\n  - ".join(missing)
            + "\nThese flags are mandatory. Pass each only after verifying "
            "the stated property in the upstream pipeline."
        )


def collect_r8_event_manifest_provenance(
    path: Path | None,
) -> dict[str, Any]:
    """Collect provenance from the upstream R8 event builder manifest.

    Per ADR-R8P1-002 §Symbols (line 162), the manifest hash and
    R8_events row count should be recorded in the output provenance.
    Optional in P0-B (AAC-4 strictly requires only panel_snapshot_hash),
    but strongly recommended for cross-run reconciliation.
    """
    if path is None:
        return {
            "status": "not_provided",
            "path": None,
            "file_hash": None,
            "row_count": None,
            "raw_keys": None,
        }
    if not path.exists():
        return {
            "status": "missing_file",
            "path": str(path),
            "file_hash": None,
            "row_count": None,
            "raw_keys": None,
        }
    file_hash = sha256_file(path)
    raw_keys: list[str] | None = None
    row_count: int | None = None
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(content, dict):
            raw_keys = sorted(content.keys())
            for key in ("row_count", "n_events", "n_r8_events", "n_rows"):
                val = content.get(key)
                if isinstance(val, int):
                    row_count = val
                    break
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass
    return {
        "status": "provided",
        "path": str(path),
        "file_hash": file_hash,
        "row_count": row_count,
        "raw_keys": raw_keys,
    }


# ---------------------------------------------------------------------------
# SQL helpers.
# ---------------------------------------------------------------------------


def classification_case_sql(unique_dates_expr: str) -> str:
    """Return classification CASE per §Gate Definition."""
    return (
        f"CASE WHEN {unique_dates_expr} >= {PASS_THRESHOLD} THEN 'PASS' "
        f"WHEN {unique_dates_expr} >= {DIRECTIONAL_MIN_THRESHOLD} "
        f"THEN 'DIRECTIONAL_ONLY' "
        f"ELSE 'INSUFFICIENT' END"
    )


def must_propagate_case_sql(unique_dates_expr: str) -> str:
    """Return must_propagate boolean expression."""
    return f"({unique_dates_expr} < {PASS_THRESHOLD})"


def reason_case_sql(unique_dates_expr: str) -> str:
    """Return must_propagate_reason CASE per §Reason Encoding."""
    return (
        f"CASE WHEN {unique_dates_expr} < {DIRECTIONAL_MIN_THRESHOLD} "
        f"THEN 'n_unique_dates<30' "
        f"WHEN {unique_dates_expr} < {PASS_THRESHOLD} "
        f"THEN '30<=n_unique_dates<100' "
        f"ELSE NULL END"
    )


# ---------------------------------------------------------------------------
# Panel CTE — the shared base for all four outputs.
# ---------------------------------------------------------------------------


def panel_cte_sql(cols: ColumnMap) -> str:
    """Return the WITH clause that builds the base panel.

    Architecture (three source tables):

        listed_market_daily_price_adj   — post-listing gate, price data
                INNER JOIN
        rs_classified                   — RS_T3/T2/T1 from bullish_features
                LEFT JOIN
        regime_tminus1                  — regime[d-1] from market_regime

    r8_flag definition (verified from r8_event_builder.py lines 85–95):
        adj_close / prev_adj_close − 1 >= SIGNAL_RETURN_THRESHOLD (0.05)
        AND adj_close > adj_open
        AND prev_adj_close IS NOT NULL AND prev_adj_close > 0

    near_limit_up definition (r8_event_builder.py line 88):
        adj_close / prev_adj_close − 1 >= NEAR_LIMIT_UP_THRESHOLD (0.095)

    RS_T3 construction (r8_event_builder.py line 57):
        beta_adj_rs_20d > QUANTILE_CONT(beta_adj_rs_20d, 2/3)
        OVER (PARTITION BY date)

    regime[d-1] construction:
        LAG(regime) OVER (ORDER BY date) in market_regime.
        Rows with NULL regime[d-1] (first date in market_regime) are
        excluded from the panel via the LEFT JOIN semantics — regime IS
        NOT NULL guard applied in panel WHERE clause.

    Panel rows with NULL near_limit_up (first observed trading day per
    stock, where prev_adj_close IS NULL) are included in the panel but
    excluded from D-2, D-2A, D-2B via the per_date CTEs' WHERE clauses.
    Their count is reported in the manifest.
    """
    sid = q(cols.stock_id)
    dt  = q(cols.date)
    ac  = q(cols.adj_close)
    ao  = q(cols.adj_open)
    rs  = q(cols.rs_metric)
    dist = q(cols.dist_above_ma20_atr)
    reg = q(cols.regime)
    qt  = RS_TOP_TERTILE_QUANTILE
    qb  = RS_BOTTOM_TERTILE_QUANTILE
    sig = SIGNAL_RETURN_THRESHOLD
    nlu = NEAR_LIMIT_UP_THRESHOLD

    return f"""
    price_lagged AS (
        SELECT
            {sid}                                          AS stock_id,
            CAST({dt} AS DATE)                             AS date,
            CAST({ao} AS DOUBLE)                           AS adj_open,
            CAST({ac} AS DOUBLE)                           AS adj_close,
            LAG(CAST({ac} AS DOUBLE))
                OVER (PARTITION BY {sid} ORDER BY CAST({dt} AS DATE))
                                                           AS prev_adj_close
        FROM {PRICE_VIEW}
    ),
    rs_classified AS (
        SELECT
            {sid}                                          AS stock_id,
            CAST({dt} AS DATE)                             AS date,
            CAST({dist} AS DOUBLE)                         AS dist_above_ma20_atr,
            CASE
                WHEN {rs} > quantile_cont({rs}, {qt})
                     OVER (PARTITION BY CAST({dt} AS DATE))
                    THEN {lit(RS_T3_LABEL)}
                WHEN {rs} > quantile_cont({rs}, {qb})
                     OVER (PARTITION BY CAST({dt} AS DATE))
                    THEN {lit(RS_T2_LABEL)}
                ELSE {lit(RS_T1_LABEL)}
            END                                            AS rs_tertile
        FROM {BULLISH_TABLE}
        WHERE {rs} IS NOT NULL
    ),
    regime_tminus1 AS (
        SELECT
            CAST({dt} AS DATE)                             AS date,
            LAG(CAST({reg} AS VARCHAR))
                OVER (ORDER BY CAST({dt} AS DATE))         AS regime
        FROM {MARKET_REGIME_TABLE}
        WHERE {reg} IS NOT NULL
    ),
    panel AS (
        SELECT
            p.stock_id,
            p.date,
            r.regime,
            CASE
                WHEN p.prev_adj_close IS NOT NULL
                 AND p.prev_adj_close > 0
                 AND p.adj_close / p.prev_adj_close - 1.0 >= {sig}
                 AND p.adj_close > p.adj_open
                THEN 1 ELSE 0
            END                                            AS r8_flag,
            rs.rs_tertile,
            rs.dist_above_ma20_atr,
            CASE
                WHEN p.prev_adj_close IS NULL
                  OR p.prev_adj_close <= 0
                THEN NULL
                WHEN p.adj_close / p.prev_adj_close - 1.0 >= {nlu}
                THEN 1 ELSE 0
            END                                            AS near_limit_up
        FROM price_lagged p
        INNER JOIN rs_classified rs
            ON  p.stock_id = rs.stock_id
            AND p.date     = rs.date
        LEFT JOIN regime_tminus1 r
            ON  p.date = r.date
        WHERE p.prev_adj_close IS NOT NULL
          AND p.prev_adj_close > 0
          AND r.regime IS NOT NULL
    )
    """


def universe_ctes_sql(cols: ColumnMap) -> str:  # noqa: ARG001
    """Return the full WITH clause for D-2, D-2A, D-2B.

    Universe definitions per ADR-R8P1-002 §Operational Universe Definitions:

        r8_events   = panel WHERE r8_flag = 1
        D_R8        = DISTINCT date FROM r8_events
        Treatment_1 = r8_events WHERE rs_tertile = 'RS_T3'
        Baseline_1  = RS_T3 rows on D_R8 dates, leave-one-out
        Treatment_2 = Treatment_1 WHERE dist_above_ma20_atr < 0  (β symmetric)
        Baseline_2  = Baseline_1 WHERE dist_above_ma20_atr < 0   (β symmetric)
    """
    return f"""
    WITH {panel_cte_sql(cols)},
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
        WHERE p.rs_tertile = {lit(RS_T3_LABEL)}
    ),
    treatment_1 AS (
        SELECT * FROM r8_events
        WHERE rs_tertile = {lit(RS_T3_LABEL)}
    ),
    baseline_1 AS (
        SELECT b.*
        FROM rs_t3_on_event_dates AS b
        LEFT JOIN r8_events AS r
            ON  r.stock_id = b.stock_id
            AND r.date     = b.date
        WHERE r.stock_id IS NULL
    ),
    treatment_2 AS (
        SELECT * FROM treatment_1 WHERE dist_above_ma20_atr < 0
    ),
    baseline_2 AS (
        SELECT * FROM baseline_1 WHERE dist_above_ma20_atr < 0
    )
    """


def panel_cte_with_sql(cols: ColumnMap) -> str:
    """Return the panel CTE wrapped in WITH for D-1."""
    return f"WITH {panel_cte_sql(cols)}"


# ---------------------------------------------------------------------------
# Output SQL builders.
# ---------------------------------------------------------------------------


def d1_sql(cols: ColumnMap) -> str:
    """D-1: R8 × RS_tertile contingency (P0-B §Outputs D-1).

    Audited panel scope: all post-listing (stock_id, date) rows in the
    joined panel (price × bullish_features × market_regime), unrestricted
    by near_limit_up or r8_flag value.

    No classification applied (D-1 is diagnostic).
    """
    return f"""
    {panel_cte_with_sql(cols)}
    SELECT
        rs_tertile,
        r8_flag,
        COUNT(*)::BIGINT                                   AS n_observations,
        COUNT(DISTINCT date)::BIGINT                       AS n_unique_dates
    FROM panel
    WHERE rs_tertile IS NOT NULL
    GROUP BY rs_tertile, r8_flag
    ORDER BY rs_tertile, r8_flag
    """


def _adequacy_select_from_per_date(
    group_cols: str,
    count_col_alias: str,
) -> str:
    """Shared SELECT pattern over a per_date CTE for D-2 / D-2A / D-2B."""
    return f"""
    SELECT
        {group_cols},
        SUM(date_count)::BIGINT                            AS {count_col_alias},
        COUNT(*)::BIGINT                                   AS n_unique_dates,
        SUM(date_count)::DOUBLE / NULLIF(COUNT(*), 0)      AS events_per_date_mean,
        CAST(quantile_cont(date_count, 0.95) AS BIGINT)    AS events_per_date_p95,
        {classification_case_sql("COUNT(*)")}              AS classification,
        {must_propagate_case_sql("COUNT(*)")}              AS must_propagate,
        {reason_case_sql("COUNT(*)")}                      AS must_propagate_reason
    FROM per_date
    GROUP BY {group_cols}
    ORDER BY {group_cols}
    """


def d2_sql(cols: ColumnMap) -> str:
    """D-2: global R8 event panel adequacy by (regime, near_limit_up).

    Audited panel: all R8 events (r8_flag = 1) with non-null near_limit_up.
    """
    return f"""
    {universe_ctes_sql(cols)},
    per_date AS (
        SELECT
            regime,
            near_limit_up,
            date,
            COUNT(*)::BIGINT AS date_count
        FROM r8_events
        WHERE near_limit_up IS NOT NULL
        GROUP BY 1, 2, 3
    )
    {_adequacy_select_from_per_date("regime, near_limit_up", "n_events")}
    """


def d2a_sql(cols: ColumnMap) -> str:
    """D-2A: A-3 treatment support audit by (regime, near_limit_up).

    Audited panel: Treatment_1 = R8 ∩ RS_T3 with non-null near_limit_up.
    """
    return f"""
    {universe_ctes_sql(cols)},
    per_date AS (
        SELECT
            regime,
            near_limit_up,
            date,
            COUNT(*)::BIGINT AS date_count
        FROM treatment_1
        WHERE near_limit_up IS NOT NULL
        GROUP BY 1, 2, 3
    )
    {_adequacy_select_from_per_date("regime, near_limit_up", "n_events")}
    """


def d2b_sql(cols: ColumnMap) -> str:
    """D-2B: baseline adequacy by (baseline_universe, regime, near_limit_up).

    Audited panel: Baseline_1 ∪ Baseline_2 with non-null near_limit_up.
    Cardinality column is n_observations (not n_events) per AAC-3.
    """
    return f"""
    {universe_ctes_sql(cols)},
    union_panel AS (
        SELECT 'Baseline_1' AS baseline_universe, * FROM baseline_1
        UNION ALL
        SELECT 'Baseline_2' AS baseline_universe, * FROM baseline_2
    ),
    per_date AS (
        SELECT
            baseline_universe,
            regime,
            near_limit_up,
            date,
            COUNT(*)::BIGINT AS date_count
        FROM union_panel
        WHERE near_limit_up IS NOT NULL
        GROUP BY 1, 2, 3, 4
    )
    {_adequacy_select_from_per_date(
        "baseline_universe, regime, near_limit_up", "n_observations"
    )}
    """


# ---------------------------------------------------------------------------
# AAC-6: two-layer enforcement.
# ---------------------------------------------------------------------------


def assert_no_forbidden_sql_tokens(sql_map: Mapping[str, str]) -> None:
    """AAC-6 layer 1: check emitted SQL for forbidden outcome tokens."""
    violations: list[str] = []
    for name, sql in sql_map.items():
        normalised = " ".join(sql.lower().split())
        hits = [t for t in AAC6_FORBIDDEN_TOKENS if t in normalised]
        if hits:
            violations.append(f"{name}: {hits}")
    if violations:
        raise AuditError(
            "AAC-6 SQL token guard failed:\n  - " + "\n  - ".join(violations)
        )


def assert_output_schema_contract(
    con: duckdb.DuckDBPyConnection,
    output_paths: Mapping[str, Path],
) -> None:
    """AAC-6 layer 2: verify each emitted parquet has exactly the expected
    column set (P0-B v0.1.1 §Outputs).  Extra or missing columns abort."""
    violations: list[str] = []
    for name, path in output_paths.items():
        rows = con.execute(
            f"DESCRIBE SELECT * FROM read_parquet({lit(path.as_posix())})"
        ).fetchall()
        observed = {str(r[0]) for r in rows}
        expected = set(EXPECTED_OUTPUT_COLUMNS[name])
        extra   = observed - expected
        missing = expected - observed
        if extra or missing:
            violations.append(
                f"{name}: extra={sorted(extra)}, missing={sorted(missing)}"
            )
    if violations:
        raise AuditError(
            "AAC-6 output schema contract failed:\n  - "
            + "\n  - ".join(violations)
        )


# ---------------------------------------------------------------------------
# Invariant verification.
# ---------------------------------------------------------------------------


def verify_invariants(
    con: duckdb.DuckDBPyConnection,
    cols: ColumnMap,
    output_paths: Mapping[str, Path],
) -> dict[str, Any]:
    """Verify all P0-B and ADR-R8P1-002 hard invariants.

    Coverage:
      - bullish_features (stock_id, date) uniqueness (ADR-002 D5)
      - rs_tertile label set (P0-B D-1 schema line 149)
      - Disjointness T1∩B1=∅, T2∩B2=∅ (P0-B Inv #10, ADR-002 Val#1)
      - DROPPED_NO_BASELINE dates (ADR-002 Val#2)
      - Stratification sum-up: Σ cells = universe total (ADR-002 Val#3)
      - Pullback filter symmetry: no T2/B2 row has dist >= 0 (ADR-002 Val#5)
      - Closed enums: baseline_universe (AAC-7), must_propagate_reason (AAC-8)
      - Classification values in ALLOWED_CLASSIFICATIONS
    """
    report: dict[str, Any] = {}

    # ---- bullish_features uniqueness (ADR-002 D5) ----
    report["bullish_features_duplicate_groups"] = (
        verify_bullish_features_uniqueness(con, cols)
    )

    # ---- RS tertile label set (P0-B D-1 schema) ----
    universes = universe_ctes_sql(cols)
    observed_rs = {
        str(r[0])
        for r in con.execute(
            f"""
            WITH {panel_cte_sql(cols)}
            SELECT DISTINCT rs_tertile FROM panel WHERE rs_tertile IS NOT NULL
            """
        ).fetchall()
    }
    unknown_rs = observed_rs - RS_LABEL_SET
    if unknown_rs:
        raise AuditError(
            f"RS tertile label set violated: unknown values {sorted(unknown_rs)}. "
            f"Expected subset of {sorted(RS_LABEL_SET)}."
        )
    if RS_T3_LABEL not in observed_rs:
        raise AuditError(
            f"No '{RS_T3_LABEL}' observations found in panel. "
            "Check rs_metric column and its values."
        )
    report["rs_tertile_labels_observed"] = sorted(observed_rs)

    # ---- Disjointness (P0-B Inv #10, ADR-002 Val#1) ----
    overlap_1 = fetch_scalar(
        con,
        f"{universes} SELECT COUNT(*) FROM treatment_1 t "
        "INNER JOIN baseline_1 b USING (stock_id, date)",
    )
    overlap_2 = fetch_scalar(
        con,
        f"{universes} SELECT COUNT(*) FROM treatment_2 t "
        "INNER JOIN baseline_2 b USING (stock_id, date)",
    )
    report["treatment_1_baseline_1_overlap"] = int(overlap_1 or 0)
    report["treatment_2_baseline_2_overlap"] = int(overlap_2 or 0)
    if overlap_1 or overlap_2:
        raise AuditError(
            "Disjointness invariant violated: "
            f"T1∩B1={overlap_1}, T2∩B2={overlap_2}."
        )

    # ---- DROPPED_NO_BASELINE dates (ADR-002 Val#2) ----
    dropped_b1 = con.execute(
        f"""
        {universes}
        SELECT d.date FROM (SELECT DISTINCT date FROM r8_events) d
        LEFT JOIN (SELECT DISTINCT date FROM baseline_1) b USING (date)
        WHERE b.date IS NULL ORDER BY d.date
        """
    ).fetchall()
    dropped_b2 = con.execute(
        f"""
        {universes}
        SELECT d.date FROM (SELECT DISTINCT date FROM r8_events) d
        LEFT JOIN (SELECT DISTINCT date FROM baseline_2) b USING (date)
        WHERE b.date IS NULL ORDER BY d.date
        """
    ).fetchall()
    report["dropped_no_baseline_1_dates"] = [str(r[0]) for r in dropped_b1]
    report["dropped_no_baseline_2_dates"] = [str(r[0]) for r in dropped_b2]

    # ---- Pullback filter symmetry (ADR-002 Val#5) ----
    bad_t2 = fetch_scalar(
        con,
        f"{universes} SELECT COUNT(*) FROM treatment_2 "
        "WHERE dist_above_ma20_atr IS NULL OR dist_above_ma20_atr >= 0",
    )
    bad_b2 = fetch_scalar(
        con,
        f"{universes} SELECT COUNT(*) FROM baseline_2 "
        "WHERE dist_above_ma20_atr IS NULL OR dist_above_ma20_atr >= 0",
    )
    report["pullback_filter_violations_t2"] = int(bad_t2 or 0)
    report["pullback_filter_violations_b2"] = int(bad_b2 or 0)
    if bad_t2 or bad_b2:
        raise AuditError(
            f"Pullback filter symmetry violated: T2={bad_t2}, B2={bad_b2}."
        )

    # ---- Side row totals (excluding NULL near_limit_up) ----
    side_row = con.execute(
        f"""
        {universes}
        SELECT
            (SELECT COUNT(*) FROM r8_events  WHERE near_limit_up IS NOT NULL),
            (SELECT COUNT(*) FROM treatment_1 WHERE near_limit_up IS NOT NULL),
            (SELECT COUNT(*) FROM baseline_1  WHERE near_limit_up IS NOT NULL),
            (SELECT COUNT(*) FROM baseline_2  WHERE near_limit_up IS NOT NULL),
            (SELECT COUNT(*) FROM r8_events  WHERE near_limit_up IS NULL),
            (SELECT COUNT(*) FROM treatment_1 WHERE near_limit_up IS NULL),
            (SELECT COUNT(*) FROM baseline_1  WHERE near_limit_up IS NULL),
            (SELECT COUNT(*) FROM baseline_2  WHERE near_limit_up IS NULL)
        """
    ).fetchone()
    if side_row is None:
        raise AuditError("Unexpected NULL result from side_row query.")
    (
        r8_total, t1_total, b1_total, b2_total,
        r8_excl, t1_excl, b1_excl, b2_excl,
    ) = (int(v) for v in side_row)

    report["side_totals_post_nlu_exclusion"] = {
        "r8_events": r8_total, "treatment_1": t1_total,
        "baseline_1": b1_total, "baseline_2": b2_total,
    }
    report["excluded_null_near_limit_up"] = {
        "r8_events": r8_excl, "treatment_1": t1_excl,
        "baseline_1": b1_excl, "baseline_2": b2_excl,
    }

    # ---- Stratification sum-up (ADR-002 Val#3) ----
    def parquet_sum(name: str, col: str, where: str = "") -> int:
        path_str = lit(output_paths[name].as_posix())
        w = f"WHERE {where}" if where else ""
        return int(
            fetch_scalar(
                con,
                f"SELECT SUM({col}) FROM read_parquet({path_str}) {w}",
            )
            or 0
        )

    strat_sums = {
        "d2_n_events":                    parquet_sum("d2_global_adequacy",    "n_events"),
        "d2a_n_events":                   parquet_sum("d2a_a3_support",        "n_events"),
        "d2b_baseline_1_n_observations":  parquet_sum("d2b_baseline_adequacy", "n_observations", "baseline_universe = 'Baseline_1'"),
        "d2b_baseline_2_n_observations":  parquet_sum("d2b_baseline_adequacy", "n_observations", "baseline_universe = 'Baseline_2'"),
    }
    expected_sums = {
        "d2_n_events":                   r8_total,
        "d2a_n_events":                  t1_total,
        "d2b_baseline_1_n_observations": b1_total,
        "d2b_baseline_2_n_observations": b2_total,
    }
    mismatches = [
        f"{k}: got {strat_sums[k]}, expected {expected_sums[k]}"
        for k in strat_sums if strat_sums[k] != expected_sums[k]
    ]
    if mismatches:
        raise AuditError(
            "Stratification sum-up failed:\n  - " + "\n  - ".join(mismatches)
        )
    report["stratified_sum_totals"] = strat_sums

    # ---- Closed enum checks (AAC-7, AAC-8) ----
    bad_bu = con.execute(
        f"""
        SELECT DISTINCT baseline_universe FROM read_parquet(
            {lit(output_paths['d2b_baseline_adequacy'].as_posix())}
        ) WHERE baseline_universe NOT IN ('Baseline_1', 'Baseline_2')
        """
    ).fetchall()
    if bad_bu:
        raise AuditError(
            f"AAC-7 violated: unknown baseline_universe values {[r[0] for r in bad_bu]}"
        )

    for name in ("d2_global_adequacy", "d2a_a3_support", "d2b_baseline_adequacy"):
        path_str = lit(output_paths[name].as_posix())
        reasons = {
            r[0] for r in con.execute(
                f"SELECT DISTINCT must_propagate_reason "
                f"FROM read_parquet({path_str})"
            ).fetchall()
        }
        if not reasons.issubset(set(ALLOWED_REASON_VALUES)):
            raise AuditError(
                f"AAC-8 violated in {name}: "
                f"{sorted(str(v) for v in reasons)}"
            )
        classes = {
            str(r[0]) for r in con.execute(
                f"SELECT DISTINCT classification FROM read_parquet({path_str})"
            ).fetchall()
        }
        if not classes.issubset(set(ALLOWED_CLASSIFICATIONS)):
            raise AuditError(
                f"Classification enum violated in {name}: {sorted(classes)}"
            )

    return report


# ---------------------------------------------------------------------------
# Parquet write helpers.
# ---------------------------------------------------------------------------


def write_parquet_atomic(
    con: duckdb.DuckDBPyConnection,
    sql: str,
    final_path: Path,
    staging_dir: Path,
) -> None:
    """Write a query to a staging parquet; caller promotes to final."""
    staging_dir.mkdir(parents=True, exist_ok=True)
    staging_path = staging_dir / final_path.name
    con.execute(
        f"COPY ({sql}) TO {lit(staging_path.as_posix())} "
        "(FORMAT PARQUET, COMPRESSION ZSTD)"
    )


def promote_staging_to_final(
    staging_dir: Path,
    final_dir: Path,
    filenames: Sequence[str],
) -> None:
    """Move staged files to the final directory, overwriting if needed."""
    final_dir.mkdir(parents=True, exist_ok=True)
    for name in filenames:
        src = staging_dir / name
        dst = final_dir / name
        if dst.exists():
            dst.unlink()
        shutil.move(str(src), str(dst))


# ---------------------------------------------------------------------------
# Regime labels and manifest.
# ---------------------------------------------------------------------------


def discover_regime_labels(
    con: duckdb.DuckDBPyConnection,
    cols: ColumnMap,
) -> list[str]:
    """Return distinct non-null regime labels from market_regime verbatim."""
    return [
        str(r[0])
        for r in con.execute(
            f"SELECT DISTINCT CAST({q(cols.regime)} AS VARCHAR) "
            f"FROM {MARKET_REGIME_TABLE} "
            f"WHERE {q(cols.regime)} IS NOT NULL ORDER BY 1"
        ).fetchall()
    ]


def build_manifest(
    *,
    db_path: Path,
    output_paths: Mapping[str, Path],
    sql_map: Mapping[str, str],
    cols: ColumnMap,
    regime_labels: Sequence[str],
    invariant_report: Mapping[str, Any],
    row_counts: Mapping[str, int],
    seed: int | None,
    started_at: str,
    finished_at: str,
    r8_event_manifest_provenance: Mapping[str, Any],
    temporal_attestations: Mapping[str, Any],
    reproducibility_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Assemble the audit manifest per AAC-4 and P0-B Inv #9."""
    return {
        "audit_spec_version":       AUDIT_SPEC_VERSION,
        "adr_001_version":          ADR_001_VERSION,
        "adr_002_version":          ADR_002_VERSION,
        "lifecycle_spec_version":   LIFECYCLE_SPEC_VERSION,
        "script_version":           SCRIPT_VERSION,
        "started_at_utc":           started_at,
        "finished_at_utc":          finished_at,
        "git_head":                 git_head_sha(),
        "git_dirty":                git_is_dirty(),
        "panel_snapshot_hash":      sha256_file(db_path),
        "panel_snapshot_path":      str(db_path),
        # Upstream R8 event manifest (ADR-R8P1-002 §Symbols line 162).
        "r8_event_manifest":        dict(r8_event_manifest_provenance),
        "benchmark_2_interpretation": BENCHMARK_2_INTERPRETATION,
        # Derivation parameters (records exactly what thresholds were used).
        "derivation_parameters": {
            "signal_return_threshold":   SIGNAL_RETURN_THRESHOLD,
            "near_limit_up_threshold":   NEAR_LIMIT_UP_THRESHOLD,
            "rs_top_tertile_quantile":   RS_TOP_TERTILE_QUANTILE,
            "rs_bottom_tertile_quantile": RS_BOTTOM_TERTILE_QUANTILE,
            "source_tables": {
                "price_view":      PRICE_VIEW,
                "bullish_table":   BULLISH_TABLE,
                "regime_table":    MARKET_REGIME_TABLE,
            },
        },
        "temporal_semantics_attestation": dict(temporal_attestations),
        "regime_labels":            list(regime_labels),
        "gate_thresholds": {
            "pass":             PASS_THRESHOLD,
            "directional_min":  DIRECTIONAL_MIN_THRESHOLD,
        },
        "seed":                     seed,
        "resolved_columns":         asdict(cols),
        "query_sql":                dict(sql_map),
        "outputs":           {k: str(v)          for k, v in output_paths.items()},
        "output_hashes":     {k: sha256_file(v)  for k, v in output_paths.items()},
        "row_counts":               dict(row_counts),
        "hard_invariants":          dict(invariant_report),
        "reproducibility":          dict(reproducibility_report),
    }


def write_manifest(manifest: dict[str, Any], path: Path) -> None:
    """Write manifest as sorted-key JSON."""
    path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Reproducibility check (P0-B Inv #6, within-process).
# ---------------------------------------------------------------------------


def verify_bit_identical_rerun(
    con: duckdb.DuckDBPyConnection,
    sql_map: Mapping[str, str],
    reference_hashes: Mapping[str, str],
) -> dict[str, str]:
    """Run each query a second time and compare parquet hashes.

    Demonstrates within-process query determinism (catches non-deterministic
    plan output ordering).  Full Inv #6 cross-invocation check is a CI
    responsibility; see reproducibility.note in the manifest.
    """
    rerun: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="audit_rerun_") as tmp:
        tmp_dir = Path(tmp)
        for name, sql in sql_map.items():
            tmp_path = tmp_dir / f"{name}.parquet"
            con.execute(
                f"COPY ({sql}) TO {lit(tmp_path.as_posix())} "
                "(FORMAT PARQUET, COMPRESSION ZSTD)"
            )
            rerun[name] = sha256_file(tmp_path)
    mismatches = [n for n, h in rerun.items() if h != reference_hashes.get(n)]
    if mismatches:
        raise AuditError(
            f"P0-B Inv #6 within-process reproducibility failed: {mismatches}. "
            f"reference={reference_hashes}, rerun={rerun}."
        )
    return rerun


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "R8 Phase 1 P0-B v0.1.1 cell adequacy audit. "
            "Emits four governance artefacts + manifest."
        )
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--r8-event-manifest", type=Path, default=None,
        help="Upstream r8_event_builder manifest path (optional but recommended).",
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="No sampling in P0-B; recorded in manifest for completeness.",
    )
    parser.add_argument("--force", action="store_true",
                        help="Overwrite non-empty output directory.")
    parser.add_argument("--skip-rerun-check", action="store_true",
                        help="Skip within-process reproducibility check.")
    parser.add_argument("--verbose", action="store_true")

    # Column name overrides (all have verified defaults).
    parser.add_argument("--stock-id-col",           default=DEFAULT_STOCK_ID_COL)
    parser.add_argument("--date-col",               default=DEFAULT_DATE_COL)
    parser.add_argument("--adj-close-col",          default=DEFAULT_ADJ_CLOSE_COL)
    parser.add_argument("--adj-open-col",           default=DEFAULT_ADJ_OPEN_COL)
    parser.add_argument("--rs-metric-col",          default=DEFAULT_RS_METRIC_COL,
                        help="De-circularised RS metric column in bullish_features. "
                             "Default: beta_adj_rs_20d (verified 2026-06-06).")
    parser.add_argument("--dist-above-ma20-atr-col", default=DEFAULT_DIST_COL)
    parser.add_argument("--regime-col",             default=DEFAULT_REGIME_COL)

    # Mandatory temporal-semantics attestations.
    parser.add_argument(
        "--rs-decirc-confirmed", action="store_true",
        help=(
            "REQUIRED. Confirm that the column passed as --rs-metric-col "
            "is de-circularised per LA-4 (the feature pipeline excludes the "
            "signal-day return from the RS rolling window). "
            "This script joins bullish_features at signal date d; the T-1 "
            "semantic is guaranteed by upstream de-circularisation."
        ),
    )
    parser.add_argument(
        "--regime-lag-source-confirmed", action="store_true",
        help=(
            "REQUIRED. Confirm that market_regime contains regime[d] "
            "(one row per trading date). This script applies "
            "LAG(regime) OVER (ORDER BY date) to derive regime[d-1] "
            "per ADR-R8P1-002 D4."
        ),
    )
    return parser.parse_args(argv)


def check_output_dir_empty_or_force(output_dir: Path, force: bool) -> None:
    """Refuse to overwrite a non-empty output dir unless --force."""
    if not output_dir.exists():
        return
    if not output_dir.is_dir():
        raise AuditError(f"Output path exists but is not a directory: {output_dir}")
    if any(output_dir.iterdir()) and not force:
        raise AuditError(
            f"Output directory not empty: {output_dir}. "
            "Pass --force to overwrite."
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the P0-B v0.1.1 cell adequacy audit."""
    args = parse_args(list(argv) if argv is not None else sys.argv[1:])
    configure_logging(args.verbose)

    if not args.db.exists():
        raise AuditError(f"DuckDB file does not exist: {args.db}")
    check_output_dir_empty_or_force(args.output_dir, args.force)
    assert_temporal_attestations(args)

    r8_prov = collect_r8_event_manifest_provenance(args.r8_event_manifest)
    if r8_prov["status"] != "provided":
        LOGGER.warning(
            "R8 event manifest: status=%s. "
            "Pass --r8-event-manifest for full ADR-R8P1-002 §Symbols provenance.",
            r8_prov["status"],
        )

    temporal_attestations = {
        "rs_decirc": {
            "confirmed_by_cli": True,
            "claim": "beta_adj_rs_20d is de-circularised per LA-4 (upstream)",
            "applies_to_column": args.rs_metric_col,
            "applies_to_table": BULLISH_TABLE,
        },
        "regime_lag_source": {
            "confirmed_by_cli": True,
            "claim": (
                "market_regime.regime contains regime[d]; "
                "script applies LAG internally for regime[d-1]"
            ),
            "applies_to_column": args.regime_col,
            "applies_to_table": MARKET_REGIME_TABLE,
        },
    }

    started_at = datetime.now(UTC).isoformat()
    LOGGER.info("Starting P0-B v0.1.1 audit — %s", started_at)

    output_paths = {
        "d1_r8_x_rs_tertile":  args.output_dir / "d1_r8_x_rs_tertile.parquet",
        "d2_global_adequacy":  args.output_dir / "d2_global_adequacy.parquet",
        "d2a_a3_support":      args.output_dir / "d2a_a3_support.parquet",
        "d2b_baseline_adequacy": args.output_dir / "d2b_baseline_adequacy.parquet",
    }

    repro: dict[str, Any] = {
        "scope": "within_process_only",
        "note": (
            "Records that two executions within a single DuckDB connection "
            "produced bit-identical outputs. Does NOT satisfy P0-B Inv #6 "
            "in full. Cross-invocation verification on the same panel "
            "snapshot is a CI responsibility."
        ),
        "within_process_check_performed": not args.skip_rerun_check,
        "first_run_hashes": None,
        "within_process_rerun_hashes": None,
    }

    with duckdb.connect(str(args.db), read_only=True) as con:
        cols = resolve_columns(con, args)
        regime_labels = discover_regime_labels(con, cols)
        LOGGER.info("Regime labels: %s", regime_labels)

        sql_map = {
            "d1_r8_x_rs_tertile":    d1_sql(cols),
            "d2_global_adequacy":    d2_sql(cols),
            "d2a_a3_support":        d2a_sql(cols),
            "d2b_baseline_adequacy": d2b_sql(cols),
        }
        assert_no_forbidden_sql_tokens(sql_map)

        with tempfile.TemporaryDirectory(prefix="audit_staging_") as staging:
            staging_dir = Path(staging)
            for key, sql in sql_map.items():
                LOGGER.info("Emitting %s", key)
                write_parquet_atomic(con, sql, output_paths[key], staging_dir)

            staged = {k: staging_dir / p.name for k, p in output_paths.items()}
            assert_output_schema_contract(con, staged)

            invariant_report = verify_invariants(con, cols, staged)

            staged_hashes = {k: sha256_file(p) for k, p in staged.items()}
            repro["first_run_hashes"] = staged_hashes
            if not args.skip_rerun_check:
                LOGGER.info("Running within-process reproducibility check")
                repro["within_process_rerun_hashes"] = (
                    verify_bit_identical_rerun(con, sql_map, staged_hashes)
                )
            else:
                LOGGER.warning("Skipping rerun check (--skip-rerun-check)")

            row_counts = {
                k: int(fetch_scalar(
                    con,
                    f"SELECT COUNT(*) FROM read_parquet({lit(p.as_posix())})"
                ) or 0)
                for k, p in staged.items()
            }
            promote_staging_to_final(
                staging_dir,
                args.output_dir,
                [p.name for p in output_paths.values()],
            )

    finished_at = datetime.now(UTC).isoformat()
    manifest = build_manifest(
        db_path=args.db,
        output_paths=output_paths,
        sql_map=sql_map,
        cols=cols,
        regime_labels=regime_labels,
        invariant_report=invariant_report,
        row_counts=row_counts,
        seed=args.seed,
        started_at=started_at,
        finished_at=finished_at,
        r8_event_manifest_provenance=r8_prov,
        temporal_attestations=temporal_attestations,
        reproducibility_report=repro,
    )
    manifest_path = args.output_dir / "manifest.json"
    write_manifest(manifest, manifest_path)
    LOGGER.info("Audit complete → %s", args.output_dir)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AuditError as exc:
        LOGGER.error("Audit failed: %s", exc)
        sys.exit(2)
