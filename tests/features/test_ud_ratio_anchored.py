# tests/features/test_ud_ratio_anchored.py
"""PIT anchored-real tests for ud_ratio_21d — Phase 1D.

This module is gated by the `requires_db` pytest marker because every
test requires `data/_storage/helios.duckdb` to be present and
readable. Synthetic PIT tests live in test_ud_ratio_pit_invariants.py
and remain DB-free.

Phase 1D scope:
    PIT-7   EMERGING-period exclusion via view (anchor: 6831)
    PIT-8   Fixture provenance (raw vs view divergence + corp-action
            existence at 2540 / 2022-09-19)
    PIT-10  SQL parity bit-exact vs r8_event_builder daily_simple_return
            recipe (20 deterministic anchors from r8_events.parquet)

Sandbox note:
    This file is NOT executed in sandbox (no helios.duckdb). Sandbox
    runs only AST / syntax validation. Nexus is the authoritative
    green/red gate for Phase 1D.

Spec reference: docs/features/ud_ratio_21d_spec.md (v0.1.4)
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import polars as pl
import pytest

from features.ud_ratio import (
    MIN_OBS,
    WINDOW,
    add_ud_ratio_21d,
)


pytestmark = pytest.mark.requires_db


# ─────────────────────────────────────────────────────────────────────
# Module-level anchor constants
# ─────────────────────────────────────────────────────────────────────

# Repo-root absolute path. Tests live at
# <repo>/tests/features/test_ud_ratio_anchored.py, so two parents up.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DB_PATH = _REPO_ROOT / "data" / "_storage" / "helios.duckdb"
_R8_EVENTS_PARQUET = (
    _REPO_ROOT / "data" / "_storage" / "r8_phase1_remediated" / "r8_events.parquet"
)

# PIT-7 anchor (spec §13.2; verified by discovery 2026-06-23):
#   6831 mainboard transition 2025-11-25 (EMERGING → TWSE).
#   View through 2025-12-15 returns exactly 15 rows (14 daily returns).
#   Hence n_obs_21d at 2025-12-15 ∈ [13, 14] (defensive band per
#   Phase 1D Design A sign-off).
_PIT7_STOCK_ID:     str  = "6831"
_PIT7_SIGNAL_DATE:  date = date(2025, 12, 15)
_PIT7_MAINBOARD:    date = date(2025, 11, 25)
_PIT7_EXPECTED_N_OBS_MIN: int = 13
_PIT7_EXPECTED_N_OBS_MAX: int = 14

# PIT-8 anchor (spec §13.2):
#   2540 / 2022-09-19 has at least one corporate_actions row with
#   |adj_factor - 1.0| > 0.2. Multi-source rows are acknowledged
#   (BACKLOG-CORP-ACTIONS-MULTI-SOURCE-001) and not adjudicated here.
_PIT8_STOCK_ID:        str  = "2540"
_PIT8_CORP_ACTION_DATE: date = date(2022, 9, 19)

# PIT-10 anchor sample (per Design B sign-off, revised in v2):
#   Up to 4 years × 5 anchors, deterministic
#     ORDER BY signal_date, stock_id
#     ROW_NUMBER per year <= 5
#   Actual count may be lower if a year has fewer events. PIT-10
#   asserts a LOWER BOUND, not the exact 20, because PIT-10 tests
#   parity behaviour and must not be brittle to r8_events.parquet
#   rebuilds, per-year event-count fluctuation, or future PIT
#   remediation. The lower bound is set high enough to retain
#   meaningful coverage across years.
_PIT10_ANCHOR_START: date = date(2022, 1, 1)
_PIT10_ANCHOR_END:   date = date(2025, 12, 31)
_PIT10_ANCHORS_PER_YEAR: int = 5
_PIT10_MIN_TOTAL_ANCHORS: int = 12  # >= 60% of the nominal 4×5 = 20


# ─────────────────────────────────────────────────────────────────────
# DuckDB connection fixture (module-scope, read-only)
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def helios_db() -> duckdb.DuckDBPyConnection:
    """Module-scope read-only handle to helios.duckdb.

    Skip the entire module if the DB is absent (allows running the
    full test suite in environments where Phase 1D anchored tests
    cannot execute, e.g. CI workers without the data volume).
    """
    if not _DB_PATH.exists():
        pytest.skip(f"helios.duckdb not present at {_DB_PATH}")
    con = duckdb.connect(str(_DB_PATH), read_only=True)
    try:
        yield con
    finally:
        con.close()


# ─────────────────────────────────────────────────────────────────────
# PIT-7 — EMERGING-period exclusion (spec §4.4, §13.2)
# ─────────────────────────────────────────────────────────────────────


class TestPIT7EmergingExclusion:
    """Spec §4.4: listed_market_daily_price_adj view excludes
    EMERGING-period rows via security_lifecycle filter. Consequence:
    a stock with a recent mainboard transition has very few view rows
    in the post-transition period, so ud_ratio_21d MUST be null per
    spec §4.3 (n_obs_21d < MIN_OBS).

    Anchor: 6831 / 2025-12-15 (mainboard 2025-11-25).
    Defensive band: 13 <= n_obs_21d <= 14 per Phase 1D Design A.
    """

    def _load_view_panel(
        self, con: duckdb.DuckDBPyConnection, stock_id: str, end_date: date
    ) -> pl.DataFrame:
        """Load (stock_id, date, adj_close) panel from the canonical
        view, sorted ascending by (stock_id, date)."""
        df_pd = con.execute(
            """
            SELECT stock_id, date, adj_close
            FROM listed_market_daily_price_adj
            WHERE stock_id = ? AND date <= ?
            ORDER BY stock_id, date
            """,
            [stock_id, end_date],
        ).fetchdf()
        return pl.from_pandas(df_pd).with_columns(
            pl.col("date").cast(pl.Date),
            pl.col("adj_close").cast(pl.Float64),
        )

    def test_anchor_sanity_security_lifecycle(
        self, helios_db: duckdb.DuckDBPyConnection
    ) -> None:
        """Anchor precondition: 6831 has a mainboard listing record
        whose listed_from is on or near 2025-11-25, with no later
        delisting (listed_to is NULL)."""
        rows = helios_db.execute(
            """
            SELECT market, listed_from, listed_to
            FROM security_lifecycle
            WHERE stock_id = ?
              AND market IN ('TWSE', 'TPEx')
            ORDER BY listed_from
            """,
            [_PIT7_STOCK_ID],
        ).fetchall()
        if not rows:
            pytest.fail(
                f"PIT-7 anchor {_PIT7_STOCK_ID} has no mainboard "
                f"record in security_lifecycle. Update PIT-7 anchor "
                f"per spec §13.2."
            )
        # Find the mainboard record (any TWSE/TPEx); listed_from should
        # be at or before _PIT7_MAINBOARD.
        mainboard_dates = [r[1] for r in rows]
        if _PIT7_MAINBOARD not in mainboard_dates:
            pytest.fail(
                f"PIT-7 anchor {_PIT7_STOCK_ID} mainboard date drift: "
                f"expected {_PIT7_MAINBOARD}, got {mainboard_dates}. "
                f"Update PIT-7 anchor per spec §13.2."
            )

    def test_anchor_sanity_view_row_count(
        self, helios_db: duckdb.DuckDBPyConnection
    ) -> None:
        """Anchor precondition: view returns rows in the band that
        makes n_obs_21d fall into the defensive band [13, 14]."""
        (n_rows,) = helios_db.execute(
            """
            SELECT COUNT(*) FROM listed_market_daily_price_adj
            WHERE stock_id = ? AND date <= ?
            """,
            [_PIT7_STOCK_ID, _PIT7_SIGNAL_DATE],
        ).fetchone()
        # 14 daily returns possible from 15 rows; 13 if one validity-fail
        expected_min_rows = _PIT7_EXPECTED_N_OBS_MIN + 1
        expected_max_rows = _PIT7_EXPECTED_N_OBS_MAX + 1
        if not (expected_min_rows <= n_rows <= expected_max_rows):
            pytest.fail(
                f"PIT-7 anchor {_PIT7_STOCK_ID} view row count drift: "
                f"expected {expected_min_rows}..{expected_max_rows} "
                f"rows through {_PIT7_SIGNAL_DATE}, got {n_rows}.\n"
                f"Possible causes:\n"
                f"  - IF-1 filter regression "
                f"(EMERGING-period rows leaking into view)\n"
                f"  - security_lifecycle rebuild changed mainboard "
                f"transition date\n"
                f"  - PIT-7 anchor drift (stock_id 6831 transition "
                f"history modified)\n"
                f"Diagnose by inspecting security_lifecycle for "
                f"{_PIT7_STOCK_ID}, then update PIT-7 anchor per "
                f"spec §13.2 if appropriate."
            )

    def test_anchor_sanity_raw_has_pre_mainboard_rows(
        self, helios_db: duckdb.DuckDBPyConnection
    ) -> None:
        """Anchor precondition: the RAW daily_price_adj table contains
        pre-mainboard rows that the view excludes. Without this, PIT-7
        would tautologically pass on any low-data stock."""
        (raw_rows,) = helios_db.execute(
            """
            SELECT COUNT(*) FROM daily_price_adj
            WHERE stock_id = ? AND date <= ?
            """,
            [_PIT7_STOCK_ID, _PIT7_SIGNAL_DATE],
        ).fetchone()
        (view_rows,) = helios_db.execute(
            """
            SELECT COUNT(*) FROM listed_market_daily_price_adj
            WHERE stock_id = ? AND date <= ?
            """,
            [_PIT7_STOCK_ID, _PIT7_SIGNAL_DATE],
        ).fetchone()
        excluded = raw_rows - view_rows
        if excluded <= 0:
            pytest.fail(
                f"PIT-7 anchor {_PIT7_STOCK_ID}: raw and view return "
                f"the same row count ({raw_rows}); IF-1 filter appears "
                f"inactive OR anchor has no EMERGING history. Update "
                f"PIT-7 anchor per spec §13.2."
            )

    def test_anchor_signal_date_is_trading_day_in_view(
        self, helios_db: duckdb.DuckDBPyConnection
    ) -> None:
        """Anchor precondition: signal_date appears in the view for
        the anchor stock_id (i.e. it's a trading day with a row)."""
        (n,) = helios_db.execute(
            """
            SELECT COUNT(*) FROM listed_market_daily_price_adj
            WHERE stock_id = ? AND date = ?
            """,
            [_PIT7_STOCK_ID, _PIT7_SIGNAL_DATE],
        ).fetchone()
        if n != 1:
            pytest.fail(
                f"PIT-7 anchor signal_date {_PIT7_SIGNAL_DATE} for "
                f"{_PIT7_STOCK_ID} returns {n} view rows (expected 1). "
                f"Update PIT-7 anchor per spec §13.2."
            )

    def test_emerging_exclusion_yields_null_ratio(
        self, helios_db: duckdb.DuckDBPyConnection
    ) -> None:
        """Main PIT-7 assertion."""
        panel = self._load_view_panel(
            helios_db, _PIT7_STOCK_ID, _PIT7_SIGNAL_DATE
        )
        out = add_ud_ratio_21d(panel)
        signal_row = out.filter(pl.col("date") == _PIT7_SIGNAL_DATE)
        assert signal_row.height == 1, (
            f"signal_date row missing in output (got {signal_row.height})"
        )
        row = signal_row.to_dicts()[0]

        # Defensive band assertions (Design A)
        assert (
            _PIT7_EXPECTED_N_OBS_MIN
            <= row["n_obs_21d"]
            <= _PIT7_EXPECTED_N_OBS_MAX
        ), (
            f"n_obs_21d = {row['n_obs_21d']} outside defensive band "
            f"[{_PIT7_EXPECTED_N_OBS_MIN}, {_PIT7_EXPECTED_N_OBS_MAX}].\n"
            f"Possible causes:\n"
            f"  - IF-1 filter regression (EMERGING-period rows in view)\n"
            f"  - security_lifecycle rebuild altered transition date\n"
            f"  - PIT-7 anchor drift\n"
            f"  - validity predicate change (more daily returns "
            f"invalidated than expected, lowering n_obs)"
        )
        # Hard requirement on null ratio (regardless of exact n_obs value)
        assert row["n_obs_21d"] < MIN_OBS
        assert row["ud_ratio_21d"] is None


# ─────────────────────────────────────────────────────────────────────
# PIT-8 — Fixture provenance (spec §11.2, §13.2)
# ─────────────────────────────────────────────────────────────────────


class TestPIT8FixtureProvenance:
    """Spec §11.2: since add_ud_ratio_21d is pure Polars (no SQL
    string to inspect), PIT-8 verifies data-source provenance —
    the input DataFrame must have been loaded from
    listed_market_daily_price_adj (not raw daily_price_adj), and the
    raw vs view divergence is demonstrable on the PIT-7 anchor.

    PIT-8 also performs kind-agnostic existence check on the
    PIT-8 corp-action anchor (2540 / 2022-09-19). Multi-source
    rows on the same (stock_id, date) are acknowledged but not
    adjudicated (BACKLOG-CORP-ACTIONS-MULTI-SOURCE-001).
    """

    def test_view_excludes_emerging_period_rows(
        self, helios_db: duckdb.DuckDBPyConnection
    ) -> None:
        """The view MUST exclude rows that raw daily_price_adj has
        for the 6831 EMERGING period. Demonstrates IF-1 filter is
        active (the structural defence behind PIT-8 provenance)."""
        (raw_count,) = helios_db.execute(
            """
            SELECT COUNT(*) FROM daily_price_adj
            WHERE stock_id = ? AND date <= ?
            """,
            [_PIT7_STOCK_ID, _PIT7_SIGNAL_DATE],
        ).fetchone()
        (view_count,) = helios_db.execute(
            """
            SELECT COUNT(*) FROM listed_market_daily_price_adj
            WHERE stock_id = ? AND date <= ?
            """,
            [_PIT7_STOCK_ID, _PIT7_SIGNAL_DATE],
        ).fetchone()
        # View MUST be a strict subset
        assert view_count < raw_count, (
            f"view ({view_count}) is not strictly smaller than raw "
            f"({raw_count}) for {_PIT7_STOCK_ID} — IF-1 filter "
            f"appears inactive."
        )

    def test_view_excludes_lifecycle_emerging_period(
        self, helios_db: duckdb.DuckDBPyConnection
    ) -> None:
        """Stronger PIT-8: every row in raw daily_price_adj that is
        STRICTLY WITHIN the EMERGING period (per security_lifecycle)
        MUST be absent from the view. This is the structural
        guarantee that downstream features inheriting from the view
        never see EMERGING-period data.

        Interval convention:
            security_lifecycle uses half-open intervals
            [listed_from, listed_to). On the transition day
            (date == listed_to of EMERGING row), the EMERGING
            interval has ALREADY ended; the same day is
            listed_from of the next (mainboard) row, meaning the
            stock is mainboard on that day. The view correctly
            shows the transition day as mainboard.

            Diagnosed in Phase 1D v2 -> v3: a closed-closed
            BETWEEN ... AND ... predicate falsely flagged 17
            transition-day rows as 'EMERGING leak'. The half-open
            predicate below is the correct lineage check.
        """
        leakage = helios_db.execute(
            """
            SELECT COUNT(*) AS leak_count
            FROM daily_price_adj AS d
            JOIN security_lifecycle AS s
              ON d.stock_id = s.stock_id
             AND d.date >= s.listed_from
             AND d.date <  COALESCE(s.listed_to, DATE '9999-12-31')
             AND s.market = 'EMERGING'
            JOIN listed_market_daily_price_adj AS v
              ON v.stock_id = d.stock_id
             AND v.date = d.date
            """
        ).fetchone()[0]
        assert leakage == 0, (
            f"PIT-8 leak: {leakage} EMERGING-period rows (strictly "
            f"within [listed_from, listed_to)) appear in the view. "
            f"This indicates a real IF-1 filter regression — "
            f"transition-day boundary ambiguity has been ruled out "
            f"by the half-open predicate."
        )

    def test_corp_action_anchor_exists_kind_agnostic(
        self, helios_db: duckdb.DuckDBPyConnection
    ) -> None:
        """Spec §13.2 PIT-8 anchor: 2540 / 2022-09-19 has at least
        one corporate_actions row with |adjustment_factor - 1.0| > 0.2.
        Multi-source rows are an acknowledged data condition and do
        not invalidate the anchor (kind-agnostic existence)."""
        rows = helios_db.execute(
            """
            SELECT kind, adjustment_factor, source
            FROM corporate_actions
            WHERE stock_id = ? AND date = ?
            """,
            [_PIT8_STOCK_ID, _PIT8_CORP_ACTION_DATE],
        ).fetchall()
        if not rows:
            pytest.fail(
                f"PIT-8 anchor {_PIT8_STOCK_ID} / "
                f"{_PIT8_CORP_ACTION_DATE} has no corporate_actions "
                f"row. Update PIT-8 anchor per spec §13.2."
            )
        # Kind-agnostic: at least one row's |adj_factor - 1.0| > 0.2
        large_adj_rows = [
            (kind, factor, source)
            for (kind, factor, source) in rows
            if abs(factor - 1.0) > 0.2
        ]
        if not large_adj_rows:
            pytest.fail(
                f"PIT-8 anchor {_PIT8_STOCK_ID} / "
                f"{_PIT8_CORP_ACTION_DATE}: no row with "
                f"|adj_factor - 1.0| > 0.2. Got: {rows}. Update "
                f"PIT-8 anchor per spec §13.2."
            )

    def test_view_panel_around_corp_action_is_computable(
        self, helios_db: duckdb.DuckDBPyConnection
    ) -> None:
        """Sanity: load a view panel spanning the 2540 corp-action
        date, and run add_ud_ratio_21d to confirm no runtime error
        is triggered by adjusted-price discontinuities. This is the
        operational counterpart to the abstract 'fixture provenance'
        invariant: the function consumes view rows without crashing
        on real adjusted-price data."""
        # Range straddles the corp-action date with adequate lookback
        # for at least one row to have n_obs_21d >= MIN_OBS
        end_date = date(2022, 10, 31)
        df_pd = helios_db.execute(
            """
            SELECT stock_id, date, adj_close
            FROM listed_market_daily_price_adj
            WHERE stock_id = ? AND date <= ?
            ORDER BY stock_id, date
            """,
            [_PIT8_STOCK_ID, end_date],
        ).fetchdf()
        panel = pl.from_pandas(df_pd).with_columns(
            pl.col("date").cast(pl.Date),
            pl.col("adj_close").cast(pl.Float64),
        )
        # Must execute without raising
        out = add_ud_ratio_21d(panel)
        # And produce a non-null ratio at the end (adequate history)
        last_row = out.tail(1).to_dicts()[0]
        assert last_row["n_obs_21d"] >= MIN_OBS, (
            f"PIT-8 anchor lookback insufficient: n_obs_21d at "
            f"{end_date} = {last_row['n_obs_21d']} < {MIN_OBS}."
        )
        assert last_row["ud_ratio_21d"] is not None


# ─────────────────────────────────────────────────────────────────────
# PIT-10 — SQL parity vs r8_event_builder daily_simple_return recipe
# ─────────────────────────────────────────────────────────────────────


class TestPIT10SQLParity:
    """Spec §11.1: ud_ratio_21d's daily-return computation MUST be
    semantically equivalent to research/r8_event_builder.py
    price_panel CTE recipe. Test enforces this with bit-exact
    parity on the aggregated counts.

    Per Phase 1D Design B + Lock 5(a) sign-off:
        Path A: add_ud_ratio_21d() output (actual implementation)
        Path B: DuckDB SQL recipe aggregates EXPECTED n_obs_21d,
                n_up_21d, ud_ratio_21d over a 21-row trailing
                window ending at signal_date.
        Compare bit-exact on n_obs / n_up; ratio first bit-exact,
        and only fall back to a tight tolerance if nexus surfaces
        ULP-level drift (with spec note required).
    """

    @pytest.fixture(scope="class")
    def anchors(
        self, helios_db: duckdb.DuckDBPyConnection
    ) -> list[tuple[str, date]]:
        """Deterministic 4-year × 5-anchor sample from r8_events.parquet.

        Returns a list of (stock_id, signal_date) tuples sorted by
        signal_date then stock_id.
        """
        if not _R8_EVENTS_PARQUET.exists():
            pytest.skip(
                f"r8_events.parquet not present at {_R8_EVENTS_PARQUET}"
            )
        # Use the module's helios_db connection to query parquet via
        # DuckDB's parquet reader (no separate Polars dependency for
        # the sampling step).
        rows = helios_db.execute(
            """
            WITH ranked AS (
                SELECT
                    signal_date,
                    stock_id,
                    EXTRACT(year FROM signal_date) AS yr,
                    ROW_NUMBER() OVER (
                        PARTITION BY EXTRACT(year FROM signal_date)
                        ORDER BY signal_date, stock_id
                    ) AS rn
                FROM read_parquet(?)
                WHERE signal_date >= ? AND signal_date <= ?
            )
            SELECT signal_date, stock_id
            FROM ranked
            WHERE rn <= ?
            ORDER BY signal_date, stock_id
            """,
            [
                str(_R8_EVENTS_PARQUET),
                _PIT10_ANCHOR_START,
                _PIT10_ANCHOR_END,
                _PIT10_ANCHORS_PER_YEAR,
            ],
        ).fetchall()
        # Validate: lower-bound check (v2 revision). PIT-10 tests
        # parity, so it should not be brittle to anchor-count drift.
        # If a year yields fewer than 5 events (parquet rebuild, PIT
        # remediation, etc.), proceed as long as the total is at or
        # above the lower bound.
        if len(rows) < _PIT10_MIN_TOTAL_ANCHORS:
            pytest.fail(
                f"PIT-10 anchor sample yielded {len(rows)} rows, "
                f"below minimum {_PIT10_MIN_TOTAL_ANCHORS}. Possible "
                f"causes: r8_events.parquet rebuild reduced event "
                f"counts in early years; PIT-10 anchor window "
                f"[{_PIT10_ANCHOR_START}, {_PIT10_ANCHOR_END}] no "
                f"longer overlaps event history. Review PIT-10 "
                f"anchor strategy per spec §13.2."
            )
        # Log the actual count for visibility in CI output.
        print(
            f"\n[PIT-10] using {len(rows)} anchors "
            f"(nominal max = {4 * _PIT10_ANCHORS_PER_YEAR})"
        )
        return [(stock_id, sig_date) for (sig_date, stock_id) in rows]

    def _load_panel_for_anchor(
        self,
        con: duckdb.DuckDBPyConnection,
        stock_id: str,
        signal_date: date,
    ) -> pl.DataFrame:
        """Load a view panel for the anchor, with enough lookback
        for a full 21-row window. Take WINDOW + buffer days back."""
        df_pd = con.execute(
            """
            SELECT stock_id, date, adj_close
            FROM listed_market_daily_price_adj
            WHERE stock_id = ? AND date <= ?
            ORDER BY stock_id, date
            """,
            [stock_id, signal_date],
        ).fetchdf()
        return pl.from_pandas(df_pd).with_columns(
            pl.col("date").cast(pl.Date),
            pl.col("adj_close").cast(pl.Float64),
        )

    def _compute_expected_via_sql(
        self,
        con: duckdb.DuckDBPyConnection,
        stock_id: str,
        signal_date: date,
    ) -> tuple[int, int, float | None]:
        """Compute EXPECTED (n_obs_21d, n_up_21d, ud_ratio_21d) at
        signal_date using the canonical SQL recipe (spec §4.1) and a
        genuine per-row rolling window (SQL window function, NOT
        a last-21-rows aggregate).

        Why a true rolling window: add_ud_ratio_21d builds a rolling
        result for EVERY row, then we read the signal_date row. A
        naive "last 21 rows summed" expected oracle gives the same
        answer in happy paths but would silently agree with an
        off-by-one regression in the actual implementation. The
        rolling SQL below matches the implementation's structure
        row-for-row.

        The recipe is re-derived inline; it does NOT depend on any
        specific implementation symbol from r8_event_builder.py
        (spec §11.1 contract is on SEMANTIC parity).

        Note on rolling-window framing:
            Polars `rolling_sum(window_size=21, min_samples=1).over(
            'stock_id')` yields a per-row sum over the trailing 21
            rows including the current row. The SQL equivalent is
            `SUM(...) OVER (PARTITION BY stock_id ORDER BY date
            ROWS BETWEEN 20 PRECEDING AND CURRENT ROW)`. The two
            framings have identical semantics on a sorted
            single-row-per-day panel.
        """
        # Step 1: price_panel CTE — daily_simple_return with
        #         validity predicate per §4.2.
        # Step 2: flagged — is_valid, is_up indicators (Int).
        # Step 3: rolling — per-row rolling sums via SQL window
        #         function, structurally matching the implementation.
        # Step 4: gate — n_obs_21d >= MIN_OBS produces ratio else NULL.
        # Step 5: pick the signal_date row.
        row = con.execute(
            """
            WITH price_panel AS (
                SELECT
                    stock_id,
                    date,
                    adj_close,
                    LAG(adj_close) OVER (
                        PARTITION BY stock_id ORDER BY date
                    ) AS prev_adj_close
                FROM listed_market_daily_price_adj
                WHERE stock_id = ?
            ),
            returns AS (
                SELECT
                    stock_id,
                    date,
                    CASE
                        WHEN prev_adj_close IS NOT NULL
                         AND prev_adj_close > 0
                         AND adj_close IS NOT NULL
                         AND adj_close > 0
                        THEN adj_close / prev_adj_close - 1.0
                        ELSE NULL
                    END AS daily_simple_return
                FROM price_panel
            ),
            flagged AS (
                SELECT
                    stock_id,
                    date,
                    CASE WHEN daily_simple_return IS NOT NULL
                         THEN 1 ELSE 0 END AS is_valid,
                    CASE WHEN daily_simple_return IS NOT NULL
                          AND daily_simple_return > 0
                         THEN 1 ELSE 0 END AS is_up
                FROM returns
            ),
            rolling AS (
                SELECT
                    stock_id,
                    date,
                    SUM(is_valid) OVER (
                        PARTITION BY stock_id
                        ORDER BY date
                        ROWS BETWEEN 20 PRECEDING AND CURRENT ROW
                    ) AS n_obs_21d,
                    SUM(is_up) OVER (
                        PARTITION BY stock_id
                        ORDER BY date
                        ROWS BETWEEN 20 PRECEDING AND CURRENT ROW
                    ) AS n_up_21d
                FROM flagged
            )
            SELECT
                n_obs_21d,
                n_up_21d,
                CASE
                    WHEN n_obs_21d >= ?
                    THEN CAST(n_up_21d AS DOUBLE) / CAST(n_obs_21d AS DOUBLE)
                    ELSE NULL
                END AS ud_ratio_21d
            FROM rolling
            WHERE date = ?
            """,
            [stock_id, MIN_OBS, signal_date],
        ).fetchone()
        if row is None:
            # signal_date has no view row for this stock_id — anchor
            # is invalid. PIT-10 caller treats this as a mismatch.
            return -1, -1, None
        n_obs = int(row[0])
        n_up = int(row[1])
        ratio = float(row[2]) if row[2] is not None else None
        return n_obs, n_up, ratio

    def test_parity_per_anchor(
        self,
        helios_db: duckdb.DuckDBPyConnection,
        anchors: list[tuple[str, date]],
    ) -> None:
        """For each anchor: assert bit-exact equality between
        add_ud_ratio_21d output and the SQL-computed expected values.

        Aggregated under one test (not parameterised) to surface
        ALL anchor mismatches in a single run rather than fail-fast
        on the first, which speeds debugging of systemic drift.
        """
        mismatches: list[str] = []
        for stock_id, signal_date in anchors:
            panel = self._load_panel_for_anchor(
                helios_db, stock_id, signal_date
            )
            if panel.is_empty():
                mismatches.append(
                    f"{stock_id} / {signal_date}: empty view panel "
                    f"(anchor outside view date range?)"
                )
                continue

            out = add_ud_ratio_21d(panel)
            row = out.filter(pl.col("date") == signal_date)
            if row.height != 1:
                mismatches.append(
                    f"{stock_id} / {signal_date}: signal row absent "
                    f"in output (height={row.height})"
                )
                continue
            actual = row.to_dicts()[0]

            n_obs_exp, n_up_exp, ratio_exp = self._compute_expected_via_sql(
                helios_db, stock_id, signal_date
            )

            # Bit-exact on counts (UInt8 vs Int — coerce for comparison)
            if int(actual["n_obs_21d"]) != n_obs_exp:
                mismatches.append(
                    f"{stock_id} / {signal_date}: n_obs_21d "
                    f"actual={actual['n_obs_21d']} expected={n_obs_exp}"
                )
                continue
            if int(actual["n_up_21d"]) != n_up_exp:
                mismatches.append(
                    f"{stock_id} / {signal_date}: n_up_21d "
                    f"actual={actual['n_up_21d']} expected={n_up_exp}"
                )
                continue

            # Ratio: bit-exact first. If empirical evidence on nexus
            # shows ULP drift between Polars f64 division and DuckDB
            # DOUBLE division, fall back to a 1e-15 tolerance and
            # ADD A SPEC §11.1 NOTE. Until that evidence exists, use
            # exact equality.
            actual_ratio = actual["ud_ratio_21d"]
            if (actual_ratio is None) != (ratio_exp is None):
                mismatches.append(
                    f"{stock_id} / {signal_date}: ratio null mismatch "
                    f"actual={actual_ratio} expected={ratio_exp}"
                )
                continue
            if actual_ratio is not None and ratio_exp is not None:
                if actual_ratio != ratio_exp:
                    mismatches.append(
                        f"{stock_id} / {signal_date}: ud_ratio_21d "
                        f"actual={actual_ratio!r} expected={ratio_exp!r} "
                        f"(diff={actual_ratio - ratio_exp:.3e})"
                    )

        if mismatches:
            pytest.fail(
                f"PIT-10 SQL parity failed for {len(mismatches)} of "
                f"{len(anchors)} anchors:\n"
                + "\n".join(f"  - {m}" for m in mismatches)
            )
