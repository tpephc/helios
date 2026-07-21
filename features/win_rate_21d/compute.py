# features/win_rate_21d/compute.py
"""Compute stage for win_rate_21d producer.

The executed SQL must receive its source identifier through the
imported ``CANONICAL_PIT_VIEW_NAME`` constant.  Do not replace that
binding with a raw backing-table identifier or a hard-coded canonical
view name.  Refactors to query construction must remain within the
data-flow patterns supported by PF-B2.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from features.win_rate_21d.build_types import BuildScope, ProducerContext
from features.win_rate_21d.constants import (
    CANONICAL_PIT_VIEW_NAME,
    MIN_CROSS_SECTION_OBS_PER_DATE,
)
from features.win_rate_21d.writer import BuildArtifact

__all__ = ["compute"]


_SQL_MEDIAN_QUERY_TEMPLATE = """
    WITH dates AS (
        SELECT DISTINCT date FROM src.{view_name}
    ),
    returns AS (
        SELECT
            stock_id,
            date,
            adj_close,
            adj_close
                / LAG(adj_close)
                    OVER (PARTITION BY stock_id ORDER BY date)
                - 1.0 AS r,
            LAG(adj_close)
                OVER (PARTITION BY stock_id ORDER BY date)
                AS prev_adj_close
        FROM src.{view_name}
    ),
    valid_returns AS (
        SELECT date, r
        FROM returns
        WHERE r IS NOT NULL
          AND prev_adj_close > 0
          AND adj_close > 0
    ),
    per_date AS (
        SELECT
            date,
            MEDIAN(r) AS median_val,
            COUNT(*) AS n_obs
        FROM valid_returns
        GROUP BY date
    )
    SELECT
        dates.date AS date,
        CASE
            WHEN COALESCE(per_date.n_obs, 0) >= {min_obs}
                THEN per_date.median_val
            ELSE NULL
        END AS median_daily_return,
        COALESCE(per_date.n_obs, 0) AS n_obs_cross_section
    FROM dates
    LEFT JOIN per_date USING (date)
    ORDER BY dates.date
"""

_ATTACH_STATEMENT_TEMPLATE = "ATTACH {path_literal} AS src (READ_ONLY);"


def compute(scope: BuildScope, context: ProducerContext) -> BuildArtifact:
    """Produce the cross-sectional median return artifact."""
    _ = scope

    db_path = Path(context.duckdb_path)
    if not db_path.exists():
        raise FileNotFoundError(
            "DuckDB database not found.\n"
            f"Path: {context.duckdb_path!r}\n"
            "Override ProducerContext.duckdb_path to use a different database."
        )

    escaped_path = str(db_path).replace("'", "''")
    attach_statement = _ATTACH_STATEMENT_TEMPLATE.format(
        path_literal=f"'{escaped_path}'",
    )
    sql = _SQL_MEDIAN_QUERY_TEMPLATE.format(
        view_name=CANONICAL_PIT_VIEW_NAME,
        min_obs=MIN_CROSS_SECTION_OBS_PER_DATE,
    )

    with duckdb.connect(":memory:") as conn:
        conn.execute(attach_statement)
        reader = conn.execute(sql).arrow()
        frame = reader.read_all()

    return BuildArtifact(
        table_name=context.target_table,
        frame=frame,
        row_count=frame.num_rows,
        column_names=tuple(frame.column_names),
    )
