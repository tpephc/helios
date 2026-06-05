#!/usr/bin/env python3
# research/ma5_momentum_feasibility.py
"""R8 MA5 Momentum Feasibility Audit — v0.1.2. Phase 0 entry-population, tradability, clustering, and overlap gate.

Research-only tool. Read-only against DuckDB. NOT used by production workflows
(no ETL, no feature generation, no signal generation, no execution). All outputs
(data/_storage/r8_feasibility/*.csv) are derived research artifacts, not
version-controlled and not consumed by any production job.

Phase 0 conclusion (recorded after the v0.1.0 gate run):
    The v0.1.0 gate technically PASSes, but the pass is fragile. R8 is strongly
    concentrated in RS60 top-tertile names (contemporaneous enrichment = 1.94),
    and therefore cannot yet be treated as orthogonal alpha. v0.1.1 (this file)
    adds the decisive de-circularised T-1 RS test plus clustering, DQ-dump,
    sector repair, and a production-candidate-overlap hook. A lifecycle replay
    SPEC must NOT be written until these are reviewed.

Scope (Phase 0 ONLY — deliberately narrow):
    This script answers a single question: is the R8 entry population
    (large bullish candle, daily_return >= +5% AND close > open) large enough,
    tradable enough, and distinct enough to justify building an R8 lifecycle
    replay engine. It does NOT evaluate strategy performance.

Explicitly OUT OF SCOPE (deferred to Phase 1+):
    - partial exit / sell-half / buy-back logic
    - MA5 reclaim / break exit conditions
    - position sizing
    - any forward-return or PnL metric
    - effective-sample-size estimation via block bootstrap

Frozen Phase-0 conventions (documented here so Phase 1 inherits them):
    - signal day = T. SMA5_T (when later used) uses data through T close only.
    - earliest tradable entry = T+1 open. The post-signal "does not break MA5"
      condition must be evaluated on T+1, T+2, ...; T must NEVER count as
      evidence of "not breaking MA5". (Phase 0 does NOT compute this condition;
      this note exists purely to pin the convention for Phase 1.)
    - regime attached to a signal on day T is regime[T - REGIME_LAG_DAYS],
      matching the production / replay-v0.2.3 convention that regime[T] is
      computed at T+1 and is therefore NOT available at T close.

Taiwan microstructure assumptions (REVIEW if data predates 2015-06):
    - TWSE daily price limit is +/-10% (since 2015-06-01). Limit-proximity
      proxies below assume +/-10%. Realized limit-up returns are typically
      slightly below 10% because the limit price is rounded to the tick grid,
      so 9.5% / 9.8% are PROXIES for "at / near limit-up", not exact bounds.
    - Limit applies to RAW (unadjusted) prices. This script computes returns
      from the configured close column. While cum_factor == 1.0 for all stocks
      (per DQ-CA-001) adjusted == raw, so the proxy is valid. If CA adjustments
      are ever applied, the limit proxy MUST switch to raw close.

Data-quality guard:
    - The 5 known corporate-action stock-dates (cum_factor == 1.0, unadjusted;
      see DQ-CA-001) are EXCLUDED from the signal population, because a stock
      dividend / rights issue (e.g. 2603 2022-09-19, +109%) would otherwise
      enter as a spurious giant "return" and pollute Section B. The count of
      removed rows is reported.

Statistical refinements added beyond the original Phase-0 spec (flagged for review):
    [R1] Section B also reports the LARGE-DOWN-GAP share of T+1 opens, not only
         the near-limit-up share. A momentum-continuation entry that gaps down
         hard at T+1 open is an adverse-selection / fading-signal tradability
         problem in the opposite direction, and is equally relevant to the gate.
    [R2] The ret_1d >= 10.0% bucket is labelled a DATA-QUALITY detector, not a
         tradability metric: a non-CA Taiwan stock-date cannot legitimately
         exceed the +10% limit close-to-close, so any such rows are almost
         certainly CA artifacts or bad data.
    [R3] Section D reports a BASE-RATE ENRICHMENT RATIO
         P(RS_T3 | R8 signal) / P(RS_T3 | all stock-dates), not just the raw
         conditional share. A raw overlap share is uninterpretable without the
         universe base rate; enrichment ~1.0 means "no association".

Run:
    uv run python research/ma5_momentum_feasibility.py \\
        --db data/_storage/helios.duckdb --out-dir data/_storage/r8_feasibility

The DuckDB file is opened read-only; this script never writes to the database.
All outputs are written as CSV to --out-dir and summarised to stdout.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd

logger = logging.getLogger("r8_feasibility")

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


# --------------------------------------------------------------------------- #
# Schema configuration — ASSUMPTIONS TO VERIFY against the actual helios.duckdb #
# --------------------------------------------------------------------------- #
# Every name below is a best-guess placeholder. The preflight step prints the
# real columns of each table and FAILS LOUDLY on any missing required column,
# so a wrong guess surfaces immediately rather than producing silent garbage.
# Correct names here in ONE place; do not scatter overrides through the code.
@dataclass(frozen=True)
class SchemaConfig:
    # --- Required: daily adjusted price panel ---
    price_table: str = "daily_price_adj"
    symbol_col: str = "stock_id"
    date_col: str = "date"
    open_col: str = "adj_open"
    close_col: str = "adj_close"
    volume_col: str = "volume"
    # Optional intraday range (used only for reporting availability in Phase 0).
    high_col: Optional[str] = "adj_high"
    low_col: Optional[str] = "adj_low"

    # --- Optional: market-wide regime (one row per trading day) ---
    # If absent, regime breakdowns are skipped (regime -> 'unknown').
    regime_table: Optional[str] = "market_regime"
    regime_date_col: str = "date"
    regime_value_col: str = "regime"

    # --- Feature table for Section D overlap (confirmed: bullish_features) ---
    # RS_T3 is NOT a stored tier. It is reconstructed as a PROXY: the per-date
    # top cross-sectional tertile of a continuous beta-adjusted RS column. The
    # production tier (find_bullish_setups.py) may differ; true candidate-set
    # overlap is deferred to v0.1.1.
    feature_table: Optional[str] = "bullish_features"
    feature_symbol_col: str = "stock_id"
    feature_date_col: str = "date"
    rs_value_cols: tuple[str, ...] = ("beta_adj_rs_20d", "beta_adj_rs_60d")
    rs_top_tier_fraction: float = 2.0 / 3.0   # top tertile (> 2/3 quantile) -> "T3"
    # Pullback-zone proxy = production feature dist_above_ma20_atr < 0.
    pullback_dist_col: Optional[str] = "dist_above_ma20_atr"
    # v0.1.2 #4: D2 reconstructs the find_bullish_setups.py screener candidate
    # set directly from bullish_features (three [ASSUMED]-threshold profiles).
    # This optional field can OVERRIDE with a single custom SQL boolean over
    # bullish_features (alias 'b'); normally left None so the built-in profile
    # logic is used. Renamed from production_pullback_predicate: the screener is
    # observational and uncalibrated, NOT production / not pullback.
    screener_candidate_predicate: Optional[str] = None

    # --- Stock -> sector mapping (stock_info is EMPTY; use company_metadata) ---
    sector_table: Optional[str] = "company_metadata"
    sector_symbol_col: str = "stock_id"
    sector_value_col: str = "industry_code"

    def required_identifiers(self) -> list[str]:
        ids = [
            self.price_table, self.symbol_col, self.date_col,
            self.open_col, self.close_col, self.volume_col,
        ]
        return ids

    def validate_identifiers(self) -> None:
        """Reject any non-identifier name to prevent SQL injection via config."""
        candidates = [
            self.price_table, self.symbol_col, self.date_col, self.open_col,
            self.close_col, self.volume_col, self.high_col, self.low_col,
            self.regime_table, self.regime_date_col, self.regime_value_col,
            self.feature_table, self.feature_symbol_col, self.feature_date_col,
            *self.rs_value_cols, self.pullback_dist_col,
            self.sector_table, self.sector_symbol_col, self.sector_value_col,
        ]
        for name in candidates:
            if name is not None and not _IDENTIFIER_RE.match(name):
                raise ValueError(f"Unsafe / invalid SQL identifier in schema config: {name!r}")


# --------------------------------------------------------------------------- #
# Analysis parameters (the R8 entry definition + microstructure proxies)        #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AuditParams:
    min_signal_return: float = 0.05          # daily_return >= +5%
    require_close_gt_open: bool = True        # close > open (true bullish candle)

    # Limit-proximity proxies on the SIGNAL day (close-to-close return).
    near_limit_signal_thresholds: tuple[float, ...] = (0.095, 0.098, 0.10)

    # T+1 open tradability proxies (next_open vs signal-day close).
    near_limit_open_threshold: float = 0.095   # open near limit-up -> hard to fill
    large_down_gap_threshold: float = -0.03    # [R1] big down-gap -> fading signal

    # Regime alignment: regime[T - lag] to match production (regime[T] is T+1).
    regime_lag_days: int = 1

    # Known CA stock-dates to exclude (DQ-CA-001). (stock_id, 'YYYY-MM-DD').
    known_ca_events: tuple[tuple[str, str], ...] = (
        ("6415", "2022-07-13"),
        ("2603", "2022-09-19"),
        ("0050", "2025-06-18"),
        ("6919", "2025-07-21"),
        ("2327", "2025-08-25"),
    )


# --------------------------------------------------------------------------- #
# find_bullish_setups.py profile thresholds — VERBATIM MIRROR, [ASSUMED]        #
# --------------------------------------------------------------------------- #
# These mirror scripts/find_bullish_setups.py v0.1.0 _THRESHOLDS exactly. They
# are [ASSUMED] / uncalibrated (pending backlog #18 outcome study) and the
# screener author explicitly states they are NOT entry signals. If
# find_bullish_setups.py is ever recalibrated, update these in lockstep, or D2
# will silently diverge from the live screener.
@dataclass(frozen=True)
class ScreenerProfiles:
    # Shared precondition (SQL WHERE in the screener): above_ma20_streak >= 3.
    min_above_ma20_streak: int = 3
    # COMPRESSION (base formation)
    comp_above_ma20_streak_min: int = 3
    comp_volume_contraction_days_10d_min: int = 4
    comp_tight_range_days_10d_min: int = 4
    comp_atr_compression_ratio_max: float = 0.85
    # RECLAIM (MA reclaim after a dip)
    rec_ma20_reclaim_confirmed_min: int = 1
    rec_above_ma20_streak_min: int = 3
    rec_failed_breakdown_count_10d_min: int = 1
    # MOMENTUM (breakout with volume)
    mom_above_ma20_streak_min: int = 5
    mom_volume_breakout_days_5d_min: int = 2
    mom_above_ma50_streak_min: int = 3# --------------------------------------------------------------------------- #
# Decision-gate thresholds — HEURISTIC, NOT empirically derived                 #
# --------------------------------------------------------------------------- #
# These are operator judgement values, not statistical results. They encode
# "how concentrated / illiquid / redundant is too much". Set them deliberately;
# in particular min_clean_tradable_events should scale with the eventual R8
# lifecycle parameter count (more free parameters -> more events required).
@dataclass(frozen=True)
class GateThresholds:
    max_single_year_share: float = 0.40        # criterion 1
    max_near_limit_signal_share: float = 0.30  # criterion 2
    max_near_limit_open_share: float = 0.30    # criterion 3
    max_rs_t3_enrichment: float = 2.0          # criterion 4 (vs base rate)
    min_clean_tradable_events: int = 150        # criterion 5 (placeholder)


# --------------------------------------------------------------------------- #
# DB helpers                                                                    #
# --------------------------------------------------------------------------- #
def connect_readonly(db_path: Path) -> duckdb.DuckDBPyConnection:
    """Open the Helios DuckDB strictly read-only."""
    if not db_path.exists():
        raise FileNotFoundError(f"DuckDB not found: {db_path}")
    logger.info("Opening DuckDB read-only: %s", db_path)
    return duckdb.connect(database=str(db_path), read_only=True)


def _table_exists(con: duckdb.DuckDBPyConnection, table: str) -> bool:
    row = con.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
        [table],
    ).fetchone()
    return bool(row and row[0] > 0)


def _columns_of(con: duckdb.DuckDBPyConnection, table: str) -> set[str]:
    df = con.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
        [table],
    ).df()
    return set(df["column_name"].astype(str))


def _row_count(con: duckdb.DuckDBPyConnection, table: str) -> int:
    return int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def preflight_schema(
    con: duckdb.DuckDBPyConnection, schema: SchemaConfig
) -> tuple[dict[str, bool], list[str]]:
    """Verify required tables/columns exist; report optional-feature availability.

    Returns (capability map, list of present RS columns). Raises RuntimeError if
    any REQUIRED column is missing, printing the price table columns to ease fixing.
    """
    schema.validate_identifiers()

    if not _table_exists(con, schema.price_table):
        raise RuntimeError(f"Required price table {schema.price_table!r} not found.")
    price_cols = _columns_of(con, schema.price_table)
    required = [
        schema.symbol_col, schema.date_col, schema.open_col,
        schema.close_col, schema.volume_col,
    ]
    missing = [c for c in required if c not in price_cols]
    if missing:
        raise RuntimeError(
            f"Price table {schema.price_table!r} is missing required columns "
            f"{missing}. Actual columns: {sorted(price_cols)}"
        )

    caps = {"has_high_low": False, "has_regime": False, "has_features": False, "has_sector": False}

    if schema.high_col and schema.low_col:
        caps["has_high_low"] = {schema.high_col, schema.low_col}.issubset(price_cols)

    if schema.regime_table and _table_exists(con, schema.regime_table):
        rc = _columns_of(con, schema.regime_table)
        caps["has_regime"] = {schema.regime_date_col, schema.regime_value_col}.issubset(rc)
        if not caps["has_regime"]:
            logger.warning("Regime table present but expected columns missing; regime breakdown disabled.")

    rs_cols_present: list[str] = []
    if schema.feature_table and _table_exists(con, schema.feature_table):
        fc = _columns_of(con, schema.feature_table)
        needed = {schema.feature_symbol_col, schema.feature_date_col}
        rs_cols_present = [c for c in schema.rs_value_cols if c in fc]
        has_pullback = bool(schema.pullback_dist_col and schema.pullback_dist_col in fc)
        caps["has_features"] = needed.issubset(fc) and (bool(rs_cols_present) or has_pullback)
        if not caps["has_features"]:
            logger.warning("Feature table present but RS/pullback columns unconfirmed; Section D disabled.")

    if schema.sector_table and _table_exists(con, schema.sector_table):
        sc = _columns_of(con, schema.sector_table)
        cols_ok = {schema.sector_symbol_col, schema.sector_value_col}.issubset(sc)
        non_empty = cols_ok and _row_count(con, schema.sector_table) > 0
        caps["has_sector"] = non_empty
        if cols_ok and not non_empty:
            logger.warning("Sector table %s has the right columns but is EMPTY; "
                           "sector breakdown disabled.", schema.sector_table)

    logger.info("Preflight capabilities: %s | rs_cols_present=%s", caps, rs_cols_present)
    return caps, rs_cols_present


# --------------------------------------------------------------------------- #
# Core signal population (built once as a TEMP VIEW, reused by all sections)     #
# --------------------------------------------------------------------------- #
def build_signal_view(
    con: duckdb.DuckDBPyConnection,
    schema: SchemaConfig,
    params: AuditParams,
    caps: dict[str, bool],
    start: Optional[str],
    end: Optional[str],
) -> None:
    """Create TEMP VIEW r8_signals: the R8 entry population with derived fields.

    Columns: symbol, dt (DATE), open_px, close_px, volume, prev_close, next_open,
    ret_1d, next_open_ret, has_next_open, regime.
    CA stock-dates are excluded. Regime is attached lagged (regime[T - lag]).
    """
    s, p = schema, params

    ca_values = ", ".join(f"('{sym}', DATE '{dt}')" for sym, dt in p.known_ca_events)
    date_filter = []
    if start:
        date_filter.append(f"dt >= DATE '{start}'")
    if end:
        date_filter.append(f"dt <= DATE '{end}'")
    extra_where = (" AND " + " AND ".join(date_filter)) if date_filter else ""

    # Regime CTEs: rank regime dates, then look back `lag` trading days.
    if caps["has_regime"]:
        regime_cte = f"""
        regime_ranked AS (
            SELECT CAST({s.regime_date_col} AS DATE) AS rdt,
                   {s.regime_value_col}              AS regime,
                   ROW_NUMBER() OVER (ORDER BY CAST({s.regime_date_col} AS DATE)) AS rn
            FROM {s.regime_table}
        ),
        regime_lagged AS (
            SELECT a.rdt AS as_of_date, b.regime AS regime_lagged
            FROM regime_ranked a
            LEFT JOIN regime_ranked b ON b.rn = a.rn - {p.regime_lag_days}
        ),
        """
        regime_select = "COALESCE(rl.regime_lagged, 'unknown') AS regime"
        regime_join = "LEFT JOIN regime_lagged rl ON rl.as_of_date = e.dt"
    else:
        regime_cte = ""
        regime_select = "'unknown' AS regime"
        regime_join = ""

    close_gt_open = "AND e.close_px > e.open_px" if p.require_close_gt_open else ""

    sql = f"""
    CREATE OR REPLACE TEMP VIEW r8_signals AS
    WITH base AS (
        SELECT
            CAST({s.symbol_col} AS VARCHAR) AS symbol,
            CAST({s.date_col} AS DATE)      AS dt,
            CAST({s.open_col} AS DOUBLE)    AS open_px,
            CAST({s.close_col} AS DOUBLE)   AS close_px,
            CAST({s.volume_col} AS DOUBLE)  AS volume
        FROM {s.price_table}
    ),
    ordered AS (
        SELECT
            symbol, dt, open_px, close_px, volume,
            LAG(close_px) OVER (PARTITION BY symbol ORDER BY dt)  AS prev_close,
            LEAD(open_px) OVER (PARTITION BY symbol ORDER BY dt)  AS next_open
        FROM base
    ),
    enriched AS (
        SELECT
            symbol, dt, open_px, close_px, volume, prev_close, next_open,
            CASE WHEN prev_close IS NOT NULL AND prev_close > 0
                 THEN close_px / prev_close - 1.0 END AS ret_1d,
            CASE WHEN next_open IS NOT NULL AND close_px > 0
                 THEN next_open / close_px - 1.0 END AS next_open_ret,
            (next_open IS NOT NULL)                   AS has_next_open
        FROM ordered
    ),
    ca_events(ca_symbol, ca_dt) AS (VALUES {ca_values}),
    {regime_cte}
    filtered AS (
        SELECT e.*, {regime_select}
        FROM enriched e
        {regime_join}
        WHERE e.ret_1d >= {p.min_signal_return}
          {close_gt_open}
          {extra_where}
          AND NOT EXISTS (
              SELECT 1 FROM ca_events c
              WHERE c.ca_symbol = e.symbol AND c.ca_dt = e.dt
          )
    )
    SELECT * FROM filtered
    """
    con.execute(sql)
    n = con.execute("SELECT COUNT(*) FROM r8_signals").fetchone()[0]
    logger.info("r8_signals built: %d rows (CA-excluded, regime-lagged).", n)


def load_universe_symbols(yaml_path: Path) -> list[str]:
    """Load dynamic_top200.symbols from the screener's universe.yaml.

    The screener applies this static snapshot to ALL as_of dates, so using it to
    reconstruct historical candidates faithfully reproduces the screener's own
    survivorship / look-ahead. Returns validated stock-code strings.
    """
    import yaml  # local import: only needed when --universe-yaml is supplied

    with yaml_path.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    raw = cfg["dynamic_top200"]["symbols"]
    syms: list[str] = []
    for s in raw:
        s = str(s)
        if not re.match(r"^[0-9A-Za-z]+$", s):   # stock codes incl. TDR ids (e.g. 910322)
            raise ValueError(f"Unsafe symbol in universe.yaml: {s!r}")
        syms.append(s)
    if not syms:
        raise ValueError("dynamic_top200.symbols is empty")
    return syms


def register_universe(con: duckdb.DuckDBPyConnection, symbols: Optional[list[str]]) -> bool:
    """Register TEMP VIEW universe_syms(stock_id) from a validated symbol list.

    Returns True if a universe filter is active. Uses a DataFrame registration
    (injection-proof) rather than string interpolation.
    """
    if not symbols:
        return False
    df = pd.DataFrame({"stock_id": symbols})
    con.register("_universe_df", df)
    con.execute("CREATE OR REPLACE TEMP VIEW universe_syms AS "
                "SELECT DISTINCT CAST(stock_id AS VARCHAR) AS stock_id FROM _universe_df")
    return True


def _screener_profile_sql(prof: ScreenerProfiles) -> dict[str, str]:
    """Return {profile_name: SQL boolean over bullish_features alias 'b'}.

    Mirrors find_bullish_setups.py _classify_profiles, including its None->False
    semantics: integer count columns use COALESCE(col, 0); the float ratio uses
    an explicit IS NOT NULL guard (COALESCE to a passing value would be wrong).
    The shared 'above_ma20_streak >= min' WHERE precondition is folded into each.
    """
    pre = f"COALESCE(b.above_ma20_streak, 0) >= {prof.min_above_ma20_streak}"
    compression = (
        f"({pre} "
        f"AND COALESCE(b.above_ma20_streak, 0) >= {prof.comp_above_ma20_streak_min} "
        f"AND COALESCE(b.volume_contraction_days_10d, 0) >= {prof.comp_volume_contraction_days_10d_min} "
        f"AND COALESCE(b.tight_range_days_10d, 0) >= {prof.comp_tight_range_days_10d_min} "
        f"AND b.atr_compression_ratio IS NOT NULL "
        f"AND b.atr_compression_ratio <= {prof.comp_atr_compression_ratio_max})")
    reclaim = (
        f"({pre} "
        f"AND COALESCE(b.ma20_reclaim_confirmed, 0) >= {prof.rec_ma20_reclaim_confirmed_min} "
        f"AND COALESCE(b.above_ma20_streak, 0) >= {prof.rec_above_ma20_streak_min} "
        f"AND COALESCE(b.failed_breakdown_count_10d, 0) >= {prof.rec_failed_breakdown_count_10d_min})")
    momentum = (
        f"({pre} "
        f"AND COALESCE(b.above_ma20_streak, 0) >= {prof.mom_above_ma20_streak_min} "
        f"AND COALESCE(b.volume_breakout_days_5d, 0) >= {prof.mom_volume_breakout_days_5d_min} "
        f"AND COALESCE(b.above_ma50_streak, 0) >= {prof.mom_above_ma50_streak_min})")
    profiles = {"COMPRESSION": compression, "RECLAIM": reclaim, "MOMENTUM": momentum}
    profiles["ANY"] = "(" + " OR ".join(profiles.values()) + ")"
    return profiles


def build_overlap_views(
    con: duckdb.DuckDBPyConnection,
    schema: SchemaConfig,
    caps: dict[str, bool],
    rs_cols_present: list[str],
) -> None:
    """Create TEMP VIEW bf_tagged: per (stock_id, dt) RS-top-tertile / below-MA20 flags.

    RS_T3 is reconstructed as a PROXY: a stock-date is 'top tertile' if its
    beta-adjusted RS strictly exceeds the per-date cross-sectional
    rs_top_tier_fraction quantile, computed over the FULL bullish_features
    universe with NaN/NULL excluded. This is NOT the production
    find_bullish_setups.py tier; true candidate-set overlap is deferred to v0.1.1.

    CIRCULARITY: a short-horizon RS window (e.g. 20d) includes the signal-day
    +5% candle, so RS-top-tertile membership is partly mechanical for R8. The
    longer horizon is less contaminated. A de-circularised RS measured as-of T-1
    is deferred to v0.1.1.
    """
    if not caps["has_features"]:
        return
    s = schema
    frac = float(s.rs_top_tier_fraction)

    thr_terms = ", ".join(
        f"quantile_cont({c}, {frac}) "
        f"FILTER (WHERE {c} IS NOT NULL AND NOT isnan({c})) AS thr_{c}"
        for c in rs_cols_present
    ) or "NULL AS _no_rs"
    con.execute(f"""
        CREATE OR REPLACE TEMP VIEW rs_thresholds AS
        SELECT CAST({s.feature_date_col} AS DATE) AS dt, {thr_terms}
        FROM {s.feature_table}
        GROUP BY CAST({s.feature_date_col} AS DATE)
    """)

    tag_terms: list[str] = []
    for c in rs_cols_present:
        tag_terms.append(
            f"CASE WHEN b.{c} IS NOT NULL AND NOT isnan(b.{c}) AND b.{c} > t.thr_{c} "
            f"THEN 1 ELSE 0 END AS is_top_{c}")
        tag_terms.append(f"(b.{c} IS NOT NULL AND NOT isnan(b.{c})) AS def_{c}")
    tag_select = ", ".join(tag_terms) if tag_terms else "1 AS _noop"

    pullback_terms = ""
    if s.pullback_dist_col:
        pullback_terms = (
            f", CASE WHEN b.{s.pullback_dist_col} IS NOT NULL AND b.{s.pullback_dist_col} < 0 "
            f"THEN 1 ELSE 0 END AS is_below_ma20, "
            f"(b.{s.pullback_dist_col} IS NOT NULL) AS def_ma20")

    lag_terms: list[str] = []
    for c in rs_cols_present:
        lag_terms.append(f"LAG(is_top_{c}) OVER w AS is_top_{c}_lag")
        lag_terms.append(f"LAG(def_{c}) OVER w AS def_{c}_lag")

    inner = f"""
        WITH tagged AS (
            SELECT CAST(b.{s.feature_symbol_col} AS VARCHAR) AS stock_id,
                   CAST(b.{s.feature_date_col} AS DATE)      AS dt,
                   {tag_select}{pullback_terms}
            FROM {s.feature_table} b
            JOIN rs_thresholds t ON t.dt = CAST(b.{s.feature_date_col} AS DATE)
        )
    """
    if lag_terms:
        body = (f"SELECT *, {', '.join(lag_terms)} FROM tagged "
                f"WINDOW w AS (PARTITION BY stock_id ORDER BY dt)")
    else:
        body = "SELECT * FROM tagged"
    con.execute(f"CREATE OR REPLACE TEMP VIEW bf_tagged AS {inner} {body}")
    n = con.execute("SELECT COUNT(*) FROM bf_tagged").fetchone()[0]
    logger.info("bf_tagged built: %d universe rows tagged (RS tertile, T-1 lag, below-MA20).", n)


# --------------------------------------------------------------------------- #
# Sections                                                                      #
# --------------------------------------------------------------------------- #
def _print_df(title: str, df: pd.DataFrame) -> None:
    print(f"\n--- {title} ---")
    if df.empty:
        print("(no rows)")
    else:
        print(df.to_string(index=False))


def section_a(con: duckdb.DuckDBPyConnection, schema: SchemaConfig,
              caps: dict[str, bool], rs_col: Optional[str],
              out: dict[str, pd.DataFrame]) -> None:
    print("\n========== SECTION A: ENTRY POPULATION ==========")
    by_year = con.execute(
        "SELECT EXTRACT(year FROM dt) AS year, COUNT(*) AS n_events "
        "FROM r8_signals GROUP BY 1 ORDER BY 1"
    ).df()
    _print_df("A1. events by year", by_year)
    out["a_by_year"] = by_year

    by_regime = con.execute(
        "SELECT regime, COUNT(*) AS n_events FROM r8_signals "
        "GROUP BY 1 ORDER BY n_events DESC"
    ).df()
    _print_df("A2. events by regime (regime[T-lag])", by_regime)
    out["a_by_regime"] = by_regime

    if caps["has_sector"]:
        by_sector = con.execute(f"""
            SELECT m.{schema.sector_value_col} AS sector, COUNT(*) AS n_events
            FROM r8_signals r
            LEFT JOIN {schema.sector_table} m
              ON CAST(m.{schema.sector_symbol_col} AS VARCHAR) = r.symbol
            GROUP BY 1 ORDER BY n_events DESC
        """).df()
        _print_df("A3. events by sector", by_sector)
        out["a_by_sector"] = by_sector
    else:
        print("\n--- A3. events by sector --- SKIPPED (sector schema unconfirmed)")

    if caps["has_features"] and rs_col:
        rs_split = con.execute(f"""
            SELECT CASE WHEN t.is_top_{rs_col} = 1
                        THEN 'RS_T3_proxy (top tertile)' ELSE 'rest' END AS rs_bucket,
                   COUNT(*) AS n_events
            FROM r8_signals r
            JOIN bf_tagged t ON t.stock_id = r.symbol AND t.dt = r.dt
            WHERE t.def_{rs_col}
            GROUP BY 1 ORDER BY n_events DESC
        """).df()
        _print_df(f"A4. RS_T3 proxy split (top tertile of {rs_col}; see Section D circularity note)",
                  rs_split)
        out["a_rs_split"] = rs_split
    else:
        print("\n--- A4. RS split --- SKIPPED (feature schema unconfirmed)")


def section_b(con: duckdb.DuckDBPyConnection, params: AuditParams,
              out: dict[str, pd.DataFrame]) -> dict[str, float]:
    print("\n========== SECTION B: LIMIT PROXIMITY & T+1 TRADABILITY ==========")
    total = con.execute("SELECT COUNT(*) FROM r8_signals").fetchone()[0]
    metrics: dict[str, float] = {"total": float(total)}

    # B1. Signal-day limit proximity (close-to-close).
    rows = []
    for thr in params.near_limit_signal_thresholds:
        n = con.execute("SELECT COUNT(*) FROM r8_signals WHERE ret_1d >= ?", [thr]).fetchone()[0]
        share = n / total if total else float("nan")
        label = "ret_1d >= 10.0% [DQ DETECTOR: CA artifact / bad row]" if thr >= 0.10 \
            else f"ret_1d >= {thr*100:.1f}% [near limit-up]"
        rows.append({"bucket": label, "n": n, "share": round(share, 4)})
        if abs(thr - 0.095) < 1e-9:
            metrics["near_limit_signal_share"] = share
    b1 = pd.DataFrame(rows)
    _print_df("B1. signal-day limit proximity", b1)
    out["b_signal_limit"] = b1

    # B2. T+1 open tradability proxy (next_open vs signal close).
    n_has_next = con.execute("SELECT COUNT(*) FROM r8_signals WHERE has_next_open").fetchone()[0]
    n_near_up = con.execute(
        "SELECT COUNT(*) FROM r8_signals WHERE has_next_open AND next_open_ret >= ?",
        [params.near_limit_open_threshold],
    ).fetchone()[0]
    n_down_gap = con.execute(  # [R1] opposite-tail adverse selection
        "SELECT COUNT(*) FROM r8_signals WHERE has_next_open AND next_open_ret <= ?",
        [params.large_down_gap_threshold],
    ).fetchone()[0]
    q = con.execute(
        "SELECT quantile_cont(next_open_ret, 0.05) AS p05, "
        "quantile_cont(next_open_ret, 0.50) AS p50, "
        "quantile_cont(next_open_ret, 0.95) AS p95 "
        "FROM r8_signals WHERE has_next_open"
    ).df()
    near_up_share = n_near_up / n_has_next if n_has_next else float("nan")
    down_gap_share = n_down_gap / n_has_next if n_has_next else float("nan")
    metrics["near_limit_open_share"] = near_up_share

    b2 = pd.DataFrame([
        {"metric": "signals with a T+1 bar (has_next_open)", "value": n_has_next},
        {"metric": "missing T+1 bar (edge / most-recent)", "value": total - n_has_next},
        {"metric": f"T+1 open >= +{params.near_limit_open_threshold*100:.1f}% (near limit-up open)",
         "value": f"{n_near_up} ({near_up_share:.2%})"},
        {"metric": f"T+1 open <= {params.large_down_gap_threshold*100:.1f}% (large down-gap) [R1]",
         "value": f"{n_down_gap} ({down_gap_share:.2%})"},
        {"metric": "next_open_ret p05 / p50 / p95",
         "value": f"{q.p05[0]:.4f} / {q.p50[0]:.4f} / {q.p95[0]:.4f}"},
    ])
    _print_df("B2. T+1 open tradability proxy", b2)
    out["b_open_tradability"] = b2

    # B3. "Clean tradable" events: not at signal limit, not at open limit, not a big fade.
    n_clean = con.execute(
        "SELECT COUNT(*) FROM r8_signals "
        "WHERE has_next_open AND ret_1d < ? AND next_open_ret < ? AND next_open_ret > ?",
        [params.near_limit_open_threshold, params.near_limit_open_threshold,
         params.large_down_gap_threshold],
    ).fetchone()[0]
    metrics["clean_tradable_events"] = float(n_clean)
    print(f"\n--- B3. clean tradable events --- {n_clean} "
          f"({(n_clean/total if total else float('nan')):.2%} of population)")
    return metrics


def section_c(con: duckdb.DuckDBPyConnection, schema: SchemaConfig,
              caps: dict[str, bool], top_n: int,
              out: dict[str, pd.DataFrame]) -> dict[str, float]:
    print("\n========== SECTION C: EVENT CLUSTERING ==========")
    metrics: dict[str, float] = {}

    by_month = con.execute(
        "SELECT strftime(dt, '%Y-%m') AS month, COUNT(*) AS n_events "
        "FROM r8_signals GROUP BY 1 ORDER BY 1"
    ).df()
    out["c_by_month"] = by_month

    total = float(by_month["n_events"].sum()) if not by_month.empty else 0.0
    if total > 0:
        shares = by_month["n_events"] / total
        herfindahl = float((shares ** 2).sum())          # monthly concentration (HHI)
        top_month_share = float(shares.max())
        by_year = con.execute(
            "SELECT EXTRACT(year FROM dt) AS year, COUNT(*) AS n FROM r8_signals GROUP BY 1"
        ).df()
        max_year_share = float((by_year["n"] / by_year["n"].sum()).max())
    else:
        herfindahl = top_month_share = max_year_share = float("nan")
    metrics["monthly_herfindahl_index"] = herfindahl
    metrics["top_month_share"] = top_month_share
    metrics["max_single_year_share"] = max_year_share

    per_day = con.execute(
        "SELECT dt, COUNT(*) AS n FROM r8_signals GROUP BY dt ORDER BY n DESC"
    ).df()
    max_per_day = int(per_day["n"].iloc[0]) if not per_day.empty else 0
    metrics["max_events_per_day"] = float(max_per_day)

    print(f"\nmonthly_herfindahl_index = {herfindahl:.4f}  "
          f"(1.0 = all in one month, ->0 = evenly spread)")
    print(f"top_month_share          = {top_month_share:.2%}")
    print(f"max_single_year_share    = {max_year_share:.2%}")
    print(f"max_events_per_day       = {max_per_day}")
    print("NOTE: effective (de-clustered) sample size is NOT estimated here; "
          "block-bootstrap effective-n is deferred to Phase 1.")

    _print_df(f"C1. top {top_n} single days by event count", per_day.head(top_n))
    out["c_top_days"] = per_day.head(top_n)

    if caps["has_sector"]:
        top_sectors = con.execute(f"""
            SELECT m.{schema.sector_value_col} AS sector, COUNT(*) AS n_events
            FROM r8_signals r
            LEFT JOIN {schema.sector_table} m
              ON CAST(m.{schema.sector_symbol_col} AS VARCHAR) = r.symbol
            GROUP BY 1 ORDER BY n_events DESC
        """).df()
        _print_df(f"C2. top {top_n} sectors", top_sectors.head(top_n))
        out["c_top_sectors"] = top_sectors.head(top_n)
    else:
        print(f"\n--- C2. top sectors --- SKIPPED (sector schema unconfirmed)")

    # C3. Same-day cross-sectional clustering (effective-independence proxy).
    # A day with many simultaneous +5% signals is largely ONE market-beta move,
    # not that many independent stock signals. Report the share of events on
    # multi-name days for several thresholds K, plus the per-day distribution.
    n_event_days = int(len(per_day))
    cluster_rows = []
    for k in (10, 20, 30):
        ev = int(per_day.loc[per_day["n"] >= k, "n"].sum())
        cluster_rows.append({
            "threshold_k": k,
            "events_on_days_with_ge_k_signals": ev,
            "share_of_all_events": round(ev / total, 4) if total else float("nan"),
        })
    c3 = pd.DataFrame(cluster_rows)
    qd = con.execute(
        "WITH d AS (SELECT dt, COUNT(*) AS n FROM r8_signals GROUP BY dt) "
        "SELECT AVG(n) AS mean_per_day, quantile_cont(n, 0.5) AS p50, "
        "quantile_cont(n, 0.95) AS p95, MAX(n) AS max_per_day FROM d"
    ).df()
    print("\n--- C3. same-day clustering (effective-independence proxy) ---")
    print(f"event_days = {n_event_days}; per-day mean/p50/p95/max = "
          f"{qd.mean_per_day[0]:.2f} / {qd.p50[0]:.1f} / {qd.p95[0]:.1f} / {int(qd.max_per_day[0])}")
    print(c3.to_string(index=False))
    print("NOTE: a high share on multi-name days means the effective independent "
          "sample is far below the raw event count (gate criterion 5 caveat). A "
          "block bootstrap for a true effective-n is still deferred to Phase 1.")
    out["c3_clustering"] = c3
    metrics["share_events_on_ge20_days"] = float(
        c3.loc[c3["threshold_k"] == 20, "share_of_all_events"].iloc[0])
    return metrics


def section_d(con: duckdb.DuckDBPyConnection, schema: SchemaConfig,
              caps: dict[str, bool], rs_cols_present: list[str],
              profiles: "ScreenerProfiles", universe_active: bool,
              out: dict[str, pd.DataFrame]) -> dict[str, float]:
    print("\n========== SECTION D: OVERLAP WITH RS_T3 / PULLBACK (PRELIMINARY) ==========")
    if not caps["has_features"]:
        print("SKIPPED: feature schema (RS / dist_above_ma20_atr) unconfirmed.")
        print("Set SchemaConfig.feature_table / rs_value_cols / pullback_dist_col, then re-run.")
        return {}

    metrics: dict[str, float] = {}
    rows: list[dict[str, object]] = []

    # Universe base rates are restricted to the signal date span (default: full panel)
    # so they are comparable to the conditional (which is over signal dates).
    span = con.execute("SELECT MIN(dt), MAX(dt) FROM r8_signals").fetchone()
    lo, hi = span[0], span[1]
    span_sql = f"dt BETWEEN DATE '{lo}' AND DATE '{hi}'"

    n_total = con.execute("SELECT COUNT(*) FROM r8_signals").fetchone()[0]
    n_matched = con.execute(
        "SELECT COUNT(*) FROM r8_signals r JOIN bf_tagged t "
        "ON t.stock_id = r.symbol AND t.dt = r.dt").fetchone()[0]
    print(f"R8 signals matched to feature universe: {n_matched}/{n_total} "
          f"({(n_matched / n_total if n_total else float('nan')):.2%})")

    for c in rs_cols_present:
        base = con.execute(
            f"SELECT AVG(is_top_{c}) FROM bf_tagged WHERE def_{c} AND {span_sql}"
        ).fetchone()[0]
        cond = con.execute(
            f"SELECT AVG(t.is_top_{c}) FROM r8_signals r "
            f"JOIN bf_tagged t ON t.stock_id = r.symbol AND t.dt = r.dt "
            f"WHERE t.def_{c}"
        ).fetchone()[0]
        if base and cond is not None:
            enr = cond / base
            metrics[f"rs_top_{c}_enrichment"] = float(enr)
            flag = "CIRCULAR: signal day inside RS window" if "20d" in c else "less circular"
            rows.append({"axis": f"RS top-tertile [{c}] ({flag})",
                         "P(.|R8)": round(cond, 4), "base_rate": round(base, 4),
                         "enrichment": round(enr, 3)})

    # #1 De-circularised T-1 RS: tertile membership as of the PREVIOUS trading
    # day, so the +5% signal candle is excluded from the RS window entirely.
    # This is the decisive test of whether the contemporaneous RS overlap is real.
    for c in rs_cols_present:
        base_l = con.execute(
            f"SELECT AVG(is_top_{c}_lag) FROM bf_tagged WHERE def_{c}_lag AND {span_sql}"
        ).fetchone()[0]
        cond_l = con.execute(
            f"SELECT AVG(t.is_top_{c}_lag) FROM r8_signals r "
            f"JOIN bf_tagged t ON t.stock_id = r.symbol AND t.dt = r.dt "
            f"WHERE t.def_{c}_lag"
        ).fetchone()[0]
        if base_l and cond_l is not None:
            enr_l = cond_l / base_l
            metrics[f"rs_top_{c}_lag_enrichment"] = float(enr_l)
            rows.append({"axis": f"RS top-tertile [{c}] as-of T-1 (de-circularised)",
                         "P(.|R8)": round(cond_l, 4), "base_rate": round(base_l, 4),
                         "enrichment": round(enr_l, 3)})

    # Gate metric: prefer the de-circularised (T-1), longest-horizon estimate.
    chosen_key: Optional[str] = None
    for key in ("rs_top_beta_adj_rs_60d_lag_enrichment",
                "rs_top_beta_adj_rs_20d_lag_enrichment",
                "rs_top_beta_adj_rs_60d_enrichment",
                "rs_top_beta_adj_rs_20d_enrichment"):
        if key in metrics:
            metrics["rs_t3_enrichment"] = metrics[key]
            chosen_key = key
            break
    if chosen_key:
        print(f"\nGATE RS metric = {chosen_key} = {metrics['rs_t3_enrichment']:.3f}")

    if schema.pullback_dist_col:
        base_pb = con.execute(
            f"SELECT AVG(is_below_ma20) FROM bf_tagged WHERE def_ma20 AND {span_sql}"
        ).fetchone()[0]
        cond_pb = con.execute(
            "SELECT AVG(t.is_below_ma20) FROM r8_signals r "
            "JOIN bf_tagged t ON t.stock_id = r.symbol AND t.dt = r.dt "
            "WHERE t.def_ma20"
        ).fetchone()[0]
        if base_pb and cond_pb is not None:
            enr_pb = cond_pb / base_pb
            metrics["pullback_enrichment"] = float(enr_pb)
            rows.append({"axis": "pullback proxy (dist_above_ma20_atr < 0)",
                         "P(.|R8)": round(cond_pb, 4), "base_rate": round(base_pb, 4),
                         "enrichment": round(enr_pb, 3)})

    # #4 Screener-candidate overlap. Reconstructs find_bullish_setups.py
    # candidates (3 [ASSUMED] profiles). The screener is OBSERVATIONAL and
    # UNCALIBRATED, NOT a validated entry strategy. Restricted to the screener
    # universe when --universe-yaml is supplied; otherwise the full panel.
    print("\n--- D2. screener-candidate overlap (#4) ---")
    print("  [ASSUMED] uncalibrated thresholds (pending backlog #18); NOT entry signals")
    if universe_active:
        u_total = con.execute("SELECT COUNT(*) FROM universe_syms").fetchone()[0]
        in_u = con.execute(
            "SELECT COUNT(*) FROM r8_signals r "
            "WHERE r.symbol IN (SELECT stock_id FROM universe_syms)").fetchone()[0]
        print(f"  UNIVERSE: restricted to dynamic_top200 snapshot ({u_total} symbols). "
              f"R8 signals in-universe = {in_u}/{n_total} "
              f"({(in_u / n_total if n_total else float('nan')):.2%}); out-of-universe "
              "signals can NEVER be screener candidates and are excluded from D2.")
        print("  NOTE: snapshot membership applied to all history => survivorship/")
        print("  look-ahead is the SCREENER'S OWN (reproduced faithfully, not added).")
        uni_join = "JOIN universe_syms u ON u.stock_id = b.stock_id"
        uni_sig = "AND r.symbol IN (SELECT stock_id FROM universe_syms)"
    else:
        print("  *** UNIVERSE MISMATCH *** computed over the FULL 205-stock panel, NOT")
        print("  the dynamic_top200 snapshot the screener actually uses. Pass")
        print("  --universe-yaml config/universe.yaml for the faithful overlap.")
        uni_join = ""
        uni_sig = ""

    prof_sql = _screener_profile_sql(profiles)
    d2_rows: list[dict[str, object]] = []
    fdate = f"CAST(b.{schema.feature_date_col} AS DATE)"
    fsym = f"CAST(b.{schema.feature_symbol_col} AS VARCHAR)"
    for name, pred in prof_sql.items():
        base_c = con.execute(
            f"SELECT AVG(CASE WHEN {pred} THEN 1.0 ELSE 0.0 END) "
            f"FROM {schema.feature_table} b {uni_join} "
            f"WHERE {fdate} BETWEEN DATE '{lo}' AND DATE '{hi}'"
        ).fetchone()[0]
        cond_c = con.execute(
            f"SELECT AVG(CASE WHEN {pred} THEN 1.0 ELSE 0.0 END) "
            f"FROM r8_signals r JOIN {schema.feature_table} b "
            f"ON {fsym} = r.symbol AND {fdate} = r.dt {uni_sig}"
        ).fetchone()[0]
        if base_c and cond_c is not None:
            enr_c = cond_c / base_c
            metrics[f"screener_{name}_enrichment"] = float(enr_c)
            d2_rows.append({"profile (ASSUMED)": name, "P(.|R8)": round(cond_c, 4),
                            "base_rate": round(base_c, 4), "enrichment": round(enr_c, 3)})
    d2 = pd.DataFrame(d2_rows)
    _print_df("D2. R8 vs find_bullish_setups profiles (descriptive overlap only)", d2)
    out["d2_screener_overlap"] = d2

    print("\nINTERPRETATION:")
    print("- DECISIVE metric is the de-circularised T-1 RS row (D1): it excludes the")
    print("  +5% signal day from the RS window. If it stays well above 1.0, R8")
    print("  genuinely lives in already-strong (high-RS) names, independent of the pop.")
    print("- tertile-based RS has a mechanical ceiling near 3.0 (base ~1/3); read")
    print("  every RS enrichment against that ceiling, not against infinity.")
    print("- D2 is DESCRIPTIVE overlap with an OBSERVATIONAL, UNCALIBRATED screener,")
    print("  NOT a comparison vs validated production alpha. It cannot overturn the RS")
    print("  finding; it only adds detail on which screener profile R8 resembles.")
    return metrics


def section_e(metrics: dict[str, float], caps: dict[str, bool],
              thr: GateThresholds) -> None:
    print("\n========== SECTION E: DECISION GATE (operator aid, NOT a test) ==========")
    print("Thresholds below are HEURISTIC operator judgements, not empirical results.\n")

    @dataclass
    class Criterion:
        name: str
        value: float
        threshold: float
        passed: Optional[bool]   # None == INDETERMINATE
        note: str = ""

    crits: list[Criterion] = []

    msy = metrics.get("max_single_year_share", float("nan"))
    crits.append(Criterion("1. annual distribution not over-concentrated",
                           msy, thr.max_single_year_share, msy <= thr.max_single_year_share))

    nls = metrics.get("near_limit_signal_share", float("nan"))
    crits.append(Criterion("2. signal-day near-limit-up share acceptable",
                           nls, thr.max_near_limit_signal_share, nls <= thr.max_near_limit_signal_share))

    nlo = metrics.get("near_limit_open_share", float("nan"))
    crits.append(Criterion("3. T+1 open tradability not deteriorating",
                           nlo, thr.max_near_limit_open_share, nlo <= thr.max_near_limit_open_share))

    if "rs_t3_enrichment" in metrics:
        enr = metrics["rs_t3_enrichment"]
        crits.append(Criterion("4. R8 not merely an RS re-expression (de-circ. T-1 RS tertile)",
                               enr, thr.max_rs_t3_enrichment, enr <= thr.max_rs_t3_enrichment))
    else:
        crits.append(Criterion("4. R8 not merely an RS re-expression (de-circ. T-1 RS tertile)",
                               float("nan"), thr.max_rs_t3_enrichment, None,
                               "feature schema unconfirmed"))

    cte = metrics.get("clean_tradable_events", float("nan"))
    crits.append(Criterion("5. enough clean tradable events",
                           cte, thr.min_clean_tradable_events, cte >= thr.min_clean_tradable_events))

    for c in crits:
        status = "INDETERMINATE" if c.passed is None else ("PASS" if c.passed else "FAIL")
        val = "n/a" if c.value != c.value else f"{c.value:.4f}"  # NaN check
        extra = f"  [{c.note}]" if c.note else ""
        print(f"[{status:13s}] {c.name}: value={val} threshold={c.threshold}{extra}")

    determinate = [c for c in crits if c.passed is not None]
    if any(c.passed is None for c in crits):
        verdict = "INDETERMINATE (resolve unconfirmed schema before deciding)"
    elif all(c.passed for c in determinate):
        verdict = "PASS -> proceed to R8 lifecycle replay SPEC (not yet build)"
    else:
        verdict = "FAIL -> do NOT build R8 lifecycle engine yet"
    print(f"\nGATE VERDICT: {verdict}")
    print("Reminder: a PASS authorises writing a lifecycle-replay SPEC, not a "
          "production rule. Phase 1 (simple baseline, no buy-back) comes next.")
    return verdict


# --------------------------------------------------------------------------- #
# Orchestration                                                                 #
# --------------------------------------------------------------------------- #
def write_outputs(out: dict[str, pd.DataFrame], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in out.items():
        path = out_dir / f"{name}.csv"
        df.to_csv(path, index=False)
        logger.info("Wrote %s (%d rows)", path, len(df))


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="R8 MA5 momentum Phase-0 feasibility audit.")
    ap.add_argument("--db", type=Path, default=Path("data/_storage/helios.duckdb"))
    ap.add_argument("--out-dir", type=Path, default=Path("data/_storage/r8_feasibility"))
    ap.add_argument("--start", type=str, default=None, help="signal-date lower bound YYYY-MM-DD")
    ap.add_argument("--end", type=str, default=None, help="signal-date upper bound YYYY-MM-DD")
    ap.add_argument("--top-n", type=int, default=15)
    ap.add_argument("--universe-yaml", type=Path, default=None,
                    help="path to config/universe.yaml; restricts D2 screener overlap "
                         "to the dynamic_top200 snapshot (faithful to find_bullish_setups.py)")
    ap.add_argument("--dump-dq", action="store_true",
                    help="dump signal rows with ret_1d >= +10%% (CA / halt / no-limit suspects) to CSV")
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero if the decision gate does not PASS")
    return ap.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args(argv)

    schema = SchemaConfig()
    params = AuditParams()
    thresholds = GateThresholds()
    profiles = ScreenerProfiles()

    con = connect_readonly(args.db)
    try:
        caps, rs_cols_present = preflight_schema(con, schema)
        build_signal_view(con, schema, params, caps, args.start, args.end)
        build_overlap_views(con, schema, caps, rs_cols_present)

        universe_symbols: Optional[list[str]] = None
        if args.universe_yaml is not None:
            universe_symbols = load_universe_symbols(args.universe_yaml)
            logger.info("Universe filter: %d symbols from %s",
                        len(universe_symbols), args.universe_yaml)
        universe_active = register_universe(con, universe_symbols)

        gate_rs_col = next(
            (c for c in ("beta_adj_rs_60d", "beta_adj_rs_20d") if c in rs_cols_present),
            (rs_cols_present[0] if rs_cols_present else None),
        )

        outputs: dict[str, pd.DataFrame] = {}
        metrics: dict[str, float] = {}

        section_a(con, schema, caps, gate_rs_col, outputs)
        metrics.update(section_b(con, params, outputs))
        metrics.update(section_c(con, schema, caps, args.top_n, outputs))
        metrics.update(section_d(con, schema, caps, rs_cols_present,
                                 profiles, universe_active, outputs))
        verdict = section_e(metrics, caps, thresholds)

        if args.dump_dq:
            # ret_1d >= +10% on a non-CA Taiwan stock-date is structurally
            # impossible (limit), so these rows are CA / halt-resumption /
            # no-limit (IPO / disposition) suspects. Eyeball to classify.
            dq = con.execute(
                "SELECT symbol, dt, ret_1d, prev_close, close_px, open_px, "
                "next_open, has_next_open, regime "
                "FROM r8_signals WHERE ret_1d >= 0.10 ORDER BY ret_1d DESC"
            ).df()
            outputs["dq_ret_ge_10pct"] = dq
            logger.info("DQ dump: %d rows with ret_1d >= +10%% flagged.", len(dq))

        write_outputs(outputs, args.out_dir)
    finally:
        con.close()

    if args.strict and not verdict.startswith("PASS"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
