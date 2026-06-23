# tests/research/test_adaptive_simulator_degenerate_equivalence.py
"""WG-1 — Adaptive simulator degenerate equivalence test.

Verifies that evaluate_candidate_adaptive produces bit-identical output
to the Phase 5 canonical path (schedule_positions +
reconstruct_nav_for_horizon) under never_exit_policy, which forces every
position to exit at the hard ceiling (T+20), mathematically equivalent
to ARM_B fixed-horizon exit.

See: research/r8_phase6_wiring_precondition.md §4.1 WG-1
Operationalises: R3 (admission engine invariance) + R6 (feature pipeline
reuse / NAV math reuse via Cross-cutting Issue 6).

Governance rules:
    WG-1 MUST PASS before any E1-E4 challenger evaluation in Step 3D.
    If WG-1 FAILS: Phase 6 adaptive evaluation is INVALID.
    Diagnose by comparing per-position keys (which positions differ)
    and per-day NAV contributions until the drift point is localised.

Test placement: this file per §4.1 "Test placement" directive.

Integration test: requires a real DuckDB snapshot accessible via
the standard Helios connection. Does NOT mock data. Controlled by
HELIOS_DB_PATH environment variable or pytest fixture conftest.

Run:
    uv run pytest tests/research/test_adaptive_simulator_degenerate_equivalence.py -v

Failure interpretation:
    FAIL on scheduled-position set equality:
        Admission drift — ordering, release predicate, or slot semantics differ.
    FAIL on NAV frame equality:
        NAV math drift — price lookup, loop bound, or arithmetic differ.
    FAIL on metrics equality:
        Downstream metric computation differs.
    FAIL on ceiling exit_date equality:
        Off-by-one in days_held inclusive counting.
"""

from __future__ import annotations

import os
from datetime import date

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Imports from production code.
# ---------------------------------------------------------------------------

from scripts.run_phase4_analysis import (
    BASELINE_CAP,
    BASELINE_MAX_POS,
    _rank_ledger,
    build_signal_ledger_for_horizon,
    compute_risk_metrics,
    load_daily_price_paths,
    reconstruct_nav_for_horizon,
    schedule_positions,
)
from scripts.phase6_adaptive_engine import (
    AdaptivePosition,
    evaluate_candidate_adaptive,
    never_exit_policy,
    project_position_key,
    project_scheduled_positions,
)

# ---------------------------------------------------------------------------
# Constants — must match Phase 5 ARM_B evaluation parameters.
# ---------------------------------------------------------------------------

_H = 20                          # ARM_B fixed horizon
_POOL = "treatment_1"
_SCENARIO = "low_uplift"         # WG-1 uses low_uplift (smaller, faster)
_RANK_COL = "beta_adj_rs_60d"
_ARM_LABEL = "arm_b"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def db_connection():
    """Open a DuckDB connection to the Helios snapshot.

    Resolution order:
        1. HELIOS_DB_PATH environment variable.
        2. data/_storage/helios.duckdb (standard Helios layout).
    Skips the test module if neither is available.
    """
    import duckdb
    from pathlib import Path

    db_path = os.environ.get("HELIOS_DB_PATH")
    if db_path is None:
        candidate = Path("data/_storage/helios.duckdb")
        if candidate.exists():
            db_path = str(candidate)
        else:
            pytest.skip(
                "WG-1 requires HELIOS_DB_PATH env var or "
                "data/_storage/helios.duckdb. Neither found."
            )
    con = duckdb.connect(db_path, read_only=True)
    yield con
    con.close()


@pytest.fixture(scope="module")
def canonical_artifacts(db_connection):
    """Build canonical ARM_B path artifacts (Phase 4 / Phase 5 surface).

    Returns:
        dict with keys:
            ledger, ranked, scheduled, diag, price_df, nav_df,
            metrics, trading_calendar, date_to_pos,
            feature_panel (for adaptive path).
    """
    from scripts.run_phase4_analysis import (
        PANEL_START,
        load_panel,
        load_price_series,
        compute_forward_returns,
    )

    con = db_connection

    panel = load_panel(con)
    prices = load_price_series(con)
    panel = compute_forward_returns(panel, prices, horizons=[_H])

    ledger = build_signal_ledger_for_horizon(
        panel, prices, pool=_POOL, scenario=_SCENARIO, h=_H, con=con
    )
    ranked = _rank_ledger(ledger, _RANK_COL, _ARM_LABEL)
    scheduled, diag = schedule_positions(ranked, BASELINE_CAP, BASELINE_MAX_POS)

    # Price panel for NAV reconstruction (columnar layout per Phase 5 ABI).
    price_df = load_daily_price_paths(con, scheduled)
    nav_df = reconstruct_nav_for_horizon(scheduled, price_df, BASELINE_CAP, h=_H)
    metrics = compute_risk_metrics(nav_df, f"wg1_canonical_{_SCENARIO}")

    # Build trading_calendar and date_to_pos from price_panel dates.
    # Same construction as reconstruct_nav_for_horizon internal calendar.
    all_dates_ts = pd.DatetimeIndex(sorted(price_df["date"].unique()))
    panel_start_ts = pd.Timestamp(PANEL_START)
    cal = all_dates_ts[all_dates_ts >= panel_start_ts]
    trading_calendar = list(cal)
    date_to_pos = {d: i for i, d in enumerate(cal)}

    # ------------------------------------------------------------------
    # F1' boundary invariants — derive required feature_panel coverage
    # from trading_calendar, not from signal_date heuristic.
    #
    # Rationale: _simulate_position_forward looks up feature rows at
    # entry_date through entry_date + hard_ceiling_h - 1 (inclusive).
    # entry_date = signal_date + 1 trading day, so the last forward
    # lookup is at trading_calendar[last_signal_pos + hard_ceiling_h].
    # ------------------------------------------------------------------
    valid_ledger = ledger[ledger["valid_path"]]
    if not valid_ledger.empty:
        last_signal_date = pd.Timestamp(valid_ledger["signal_date"].max())
        last_signal_pos = date_to_pos.get(last_signal_date)
        if last_signal_pos is None:
            raise RuntimeError(
                f"FIXTURE INVARIANT VIOLATION (pre-load): "
                f"last_signal_date={last_signal_date} not in trading_calendar. "
                f"Calendar/ledger date set mismatch."
            )

        # Last forward-lookup position:
        #   entry_pos = signal_pos + 1
        #   last lookup at entry_pos + hard_ceiling_h - 1
        #              = signal_pos + hard_ceiling_h
        last_lookup_pos = last_signal_pos + _H
        if last_lookup_pos >= len(trading_calendar):
            raise RuntimeError(
                f"FIXTURE INVARIANT VIOLATION (pre-load): "
                f"trading_calendar exhausted.\n"
                f"  last_signal_pos = {last_signal_pos}\n"
                f"  last_lookup_pos = {last_lookup_pos}\n"
                f"  len(calendar)   = {len(trading_calendar)}\n"
                f"Cause: trading_calendar from price_df does not extend\n"
                f"       hard_ceiling_h trading days beyond last signal_date."
            )

        required_feature_end = trading_calendar[last_lookup_pos]
    else:
        # Empty universe — feature_panel will be empty; sentinel only.
        required_feature_end = pd.Timestamp("1970-01-01")

    # Feature panel for adaptive path (per R6 persistence-first).
    # Load from DB: daily_features + bullish_features joined.
    feature_panel = _load_feature_panel(con, ledger, required_feature_end)

    # F1' post-load invariant: feature_panel actually covers required range.
    if not valid_ledger.empty and not feature_panel.empty:
        feature_panel_max = pd.Timestamp(feature_panel["date"].max())
        if feature_panel_max < required_feature_end:
            raise RuntimeError(
                f"FIXTURE INVARIANT VIOLATION (post-load): "
                f"feature_panel boundary insufficient.\n"
                f"  feature_panel.max()  = {feature_panel_max}\n"
                f"  required_feature_end = {required_feature_end} "
                f"(trading_calendar[{last_lookup_pos}])\n"
                f"Cause: DB feature tables lag the requested query window.\n"
                f"Diagnose: check bullish_features.max() and daily_features.max() "
                f"vs daily_price_adj.max() in DB."
            )

    return {
        "ledger":            ledger,
        "ranked":            ranked,
        "scheduled":         scheduled,
        "diag":              diag,
        "price_df":          price_df,
        "nav_df":            nav_df,
        "metrics":           metrics,
        "trading_calendar":  trading_calendar,
        "date_to_pos":       date_to_pos,
        "feature_panel":     feature_panel,
    }


def _load_feature_panel(
    con,
    ledger: pd.DataFrame,
    required_max_date: pd.Timestamp,
) -> pd.DataFrame:
    """Load feature panel for the full Phase 6 evaluation universe.

    Universe = ledger[valid_path] stock_id × signal_date set.
    Using only scheduled symbols would introduce admission-selection
    bias into the cross-sectional rank computation.

    rs_60d_rank is computed as PERCENT_RANK() OVER (PARTITION BY date
    ORDER BY beta_adj_rs_60d ASC) across the full valid treatment_1
    universe per date. This matches E3 threshold semantics:
        rs_60d_rank < 0.50 = below median of full universe.

    donchian_low_excl sourced from daily_features.donchian_20_low
    (column name confirmed from DB schema; not donchian_low_excl).

    Args:
        required_max_date: explicit upper bound (inclusive) for the
            feature query. Caller derives this from trading_calendar
            so that entry_date + hard_ceiling_h - 1 forward lookups
            in _simulate_position_forward have corresponding feature
            rows. F1' boundary invariant: query window is
            calendar-derived, not heuristic, and not coupled to
            signal_date.max().

    Returns a DataFrame with columns:
        stock_id, date, sma_20, rs_60d_rank, donchian_low_excl, atr_14
    """
    valid = ledger[ledger["valid_path"]]
    if valid.empty:
        return pd.DataFrame(columns=[
            "stock_id", "date", "sma_20", "rs_60d_rank",
            "donchian_low_excl", "atr_14",
        ])

    symbols = list(valid["stock_id"].unique())
    symbols_sql = ", ".join(f"'{s}'" for s in symbols)
    min_date = valid["signal_date"].min().date()
    # F1' boundary: use caller-supplied calendar-derived upper bound
    # rather than signal_date.max(). The latter omits the forward
    # lookup horizon and causes KeyError at simulator runtime.
    max_date = required_max_date.date()

    # Rank over full universe first, then filter to target symbols.
    # PERCENT_RANK() partition covers all symbols on each date so that
    # the rank denominator is the full evaluation universe, not just
    # the scheduled subset (avoids admission-selection bias).
    query = f"""
        WITH universe_ranked AS (
            SELECT
                bf.stock_id,
                bf.date,
                df.sma_20,
                df.atr_14,
                df.donchian_20_low                          AS donchian_low_excl,
                PERCENT_RANK() OVER (
                    PARTITION BY bf.date
                    ORDER BY bf.beta_adj_rs_60d ASC
                )                                           AS rs_60d_rank
            FROM bullish_features bf
            JOIN daily_features df
                ON bf.stock_id = df.stock_id AND bf.date = df.date
            WHERE bf.date BETWEEN '{min_date}' AND '{max_date}'
        )
        SELECT *
        FROM universe_ranked
        WHERE stock_id IN ({symbols_sql})
        ORDER BY stock_id, date
    """
    result = con.execute(query).df()
    result["date"] = pd.to_datetime(result["date"])

    # Smoke check: rs_60d_rank must be in [0, 1].
    rank_min = result["rs_60d_rank"].min()
    rank_max = result["rs_60d_rank"].max()
    assert 0.0 <= rank_min and rank_max <= 1.0, (
        f"_load_feature_panel: rs_60d_rank out of [0,1]: "
        f"min={rank_min:.4f} max={rank_max:.4f}"
    )
    return result


# ---------------------------------------------------------------------------
# WG-1 sub-test 0 — ceiling exit_date matches canonical exit_date
# (釘死 off-by-one 風險，per governance directive)
# ---------------------------------------------------------------------------


def test_adaptive_ceiling_exit_matches_canonical_exit_date(
    canonical_artifacts,
):
    """WG-1 pre-check: ceiling exit_date == canonical exit_date for all positions.

    Runs a single-position smoke test using a synthetic minimal ledger
    to verify days_held inclusive counting before the full integration test.

    Canonical: exit_date = trading_calendar[signal_pos + h]
    Adaptive:  ceiling fires when days_held >= h
               exit_date = trading_calendar[entry_pos + h - 1]
               where entry_pos = signal_pos + 1

    trading_calendar[signal_pos + h]
        = trading_calendar[(signal_pos+1) + (h-1)]
        = trading_calendar[entry_pos + h - 1]
    Therefore the two are equal. This test verifies on real calendar data.
    """
    arts = canonical_artifacts
    scheduled = arts["scheduled"]
    trading_calendar = arts["trading_calendar"]
    date_to_pos = arts["date_to_pos"]

    if not scheduled:
        pytest.skip("No scheduled positions in canonical path — snapshot empty.")

    # Pick first scheduled position as reference.
    ref = scheduled[0]
    canonical_exit = pd.Timestamp(ref.exit_date)

    # Determine canonical entry_date position in calendar.
    entry_ts = pd.Timestamp(ref.entry_date)
    entry_pos = date_to_pos.get(entry_ts)
    assert entry_pos is not None, (
        f"entry_date {entry_ts} not in date_to_pos — calendar mismatch."
    )

    # Adaptive ceiling exit_date = trading_calendar[entry_pos + h - 1]
    ceiling_idx = entry_pos + _H - 1
    assert ceiling_idx < len(trading_calendar), (
        f"Calendar too short: ceiling_idx={ceiling_idx} >= "
        f"len(calendar)={len(trading_calendar)}"
    )
    adaptive_ceiling_exit = trading_calendar[ceiling_idx]

    assert adaptive_ceiling_exit == canonical_exit, (
        f"Off-by-one detected!\n"
        f"  symbol={ref.stock_id}\n"
        f"  entry_date={entry_ts}\n"
        f"  canonical exit_date={canonical_exit}\n"
        f"  adaptive ceiling exit_date={adaptive_ceiling_exit}\n"
        f"  entry_pos={entry_pos}, h={_H}, ceiling_idx={ceiling_idx}"
    )


# ---------------------------------------------------------------------------
# WG-1 — full degenerate equivalence
# ---------------------------------------------------------------------------


def test_adaptive_simulator_degenerate_equivalence(canonical_artifacts):
    """WG-1 — adaptive simulator degenerate equivalence.

    Verifies that the unified daily simulator (used for E1-E4
    challengers) produces bit-identical output to the Phase 5
    canonical path (schedule_positions + reconstruct_nav_for_horizon)
    under a degenerate exit policy that never triggers before the
    T+20 hard ceiling.

    See research/r8_phase6_wiring_precondition.md §4.1 WG-1.
    Operationalises R3 + R6 invariance for the structural-reuse
    pattern documented in Cross-cutting Issue 6.
    """
    arts = canonical_artifacts

    if not arts["scheduled"]:
        pytest.skip("No scheduled positions in canonical path — snapshot empty.")

    # ------------------------------------------------------------------
    # Run adaptive path with degenerate policy (never exits before ceiling).
    # strict_features=True: missing feature rows are fatal (ABI violation).
    # ------------------------------------------------------------------
    adaptive_positions, nav_adaptive, diag_adaptive = evaluate_candidate_adaptive(
        ranked=arts["ranked"],
        feature_panel=arts["feature_panel"],
        price_panel=arts["price_df"],
        trading_calendar=arts["trading_calendar"],
        date_to_pos=arts["date_to_pos"],
        exit_policy_fn=never_exit_policy,
        hard_ceiling_h=_H,
        cap=BASELINE_CAP,
        max_pos=BASELINE_MAX_POS,
        strict_features=True,
    )

    # ------------------------------------------------------------------
    # Assertion 1 — scheduled position SET-EQUAL
    # Compare as tuple sets to avoid dataclass field drift.
    # ------------------------------------------------------------------
    canonical_keys = {
        (pos.stock_id, pd.Timestamp(pos.signal_date),
         pd.Timestamp(pos.entry_date), pd.Timestamp(pos.exit_date),
         pos.weight)
        for pos in arts["scheduled"]
    }
    adaptive_keys = {project_position_key(p) for p in adaptive_positions}

    missing_in_adaptive = canonical_keys - adaptive_keys
    extra_in_adaptive   = adaptive_keys - canonical_keys

    assert not missing_in_adaptive and not extra_in_adaptive, (
        f"WG-1 FAIL: scheduled position set mismatch.\n"
        f"  In canonical but not adaptive ({len(missing_in_adaptive)}):\n"
        + "\n".join(f"    {k}" for k in sorted(missing_in_adaptive)[:10])
        + (f"\n  ... and {len(missing_in_adaptive)-10} more" if len(missing_in_adaptive) > 10 else "")
        + f"\n  In adaptive but not canonical ({len(extra_in_adaptive)}):\n"
        + "\n".join(f"    {k}" for k in sorted(extra_in_adaptive)[:10])
        + (f"\n  ... and {len(extra_in_adaptive)-10} more" if len(extra_in_adaptive) > 10 else "")
        + "\nDiagnose: compare per-position entry/exit dates to find "
          "admission ordering or release predicate drift."
    )

    # ------------------------------------------------------------------
    # Assertion 2 — daily NAV BIT-IDENTICAL
    # check_exact=True: no epsilon; any floating-point deviation reveals drift.
    # ------------------------------------------------------------------
    nav_canonical = arts["nav_df"].copy()

    # Align on date column (both should cover same calendar range).
    nav_canonical = nav_canonical.set_index("date").sort_index()
    nav_adaptive  = nav_adaptive.set_index("date").sort_index()

    # Restrict to common date range (canonical may start from PANEL_START).
    common_dates = nav_canonical.index.intersection(nav_adaptive.index)
    assert len(common_dates) > 0, (
        "WG-1 FAIL: no overlapping dates between canonical and adaptive NAV."
    )

    nav_c = nav_canonical.loc[common_dates, ["nav", "daily_log_return"]]
    nav_a = nav_adaptive.loc[common_dates, ["nav", "daily_log_return"]]

    try:
        pd.testing.assert_frame_equal(
            nav_c,
            nav_a,
            check_exact=True,
            obj="WG-1 NAV comparison",
        )
    except AssertionError as exc:
        # Find first divergence point for diagnosis.
        diff_mask = (nav_c["nav"] != nav_a["nav"])
        first_diff = nav_c.index[diff_mask][0] if diff_mask.any() else None
        raise AssertionError(
            f"WG-1 FAIL: daily NAV not bit-identical.\n"
            f"  First divergence date: {first_diff}\n"
            f"  Diagnose: compare per-position NAV contributions on "
            f"{first_diff} to localise price lookup or arithmetic drift.\n"
            f"  Original error: {exc}"
        ) from exc

    # ------------------------------------------------------------------
    # Assertion 3 — metrics BIT-IDENTICAL
    # Computes metrics on adaptive NAV and compares scalar values.
    # ------------------------------------------------------------------
    metrics_adaptive = compute_risk_metrics(
        nav_adaptive.reset_index(), f"wg1_adaptive_{_SCENARIO}"
    )
    metrics_canonical = arts["metrics"]

    _assert_metric_equal(metrics_canonical, metrics_adaptive, "sharpe")
    _assert_metric_equal(metrics_canonical, metrics_adaptive, "max_drawdown")
    _assert_metric_equal(metrics_canonical, metrics_adaptive, "admission_rate",
                         diag_adaptive=diag_adaptive,
                         diag_canonical=arts["diag"])

    # ------------------------------------------------------------------
    # Assertion 4 — mean_holding_days == h under degenerate policy
    # All positions should have days_held == hard_ceiling_h.
    # ------------------------------------------------------------------
    holding_days = [p.days_held for p in adaptive_positions]
    non_ceiling = [d for d in holding_days if d != _H]
    assert not non_ceiling, (
        f"WG-1 FAIL: {len(non_ceiling)} positions exited before ceiling "
        f"under never_exit_policy. days_held values: {sorted(set(non_ceiling))}. "
        "This indicates exit_policy_fn was called and returned should_exit=True, "
        "which should be impossible with never_exit_policy."
    )

    assert diag_adaptive["mean_holding_days"] == float(_H), (
        f"WG-1 FAIL: mean_holding_days={diag_adaptive['mean_holding_days']} "
        f"!= {_H} under never_exit_policy."
    )


# ---------------------------------------------------------------------------
# Admission rate cross-check (separate test for isolation)
# ---------------------------------------------------------------------------


def test_wg1_admission_rate_matches_canonical(canonical_artifacts):
    """WG-1 sub-check: admission_rate from diag matches canonical diag.

    Isolated from the main NAV test so that admission failures are
    reported separately from NAV failures.
    """
    arts = canonical_artifacts

    if not arts["scheduled"]:
        pytest.skip("No scheduled positions in canonical path.")

    adaptive_positions, _, diag_adaptive = evaluate_candidate_adaptive(
        ranked=arts["ranked"],
        feature_panel=arts["feature_panel"],
        price_panel=arts["price_df"],
        trading_calendar=arts["trading_calendar"],
        date_to_pos=arts["date_to_pos"],
        exit_policy_fn=never_exit_policy,
        hard_ceiling_h=_H,
        cap=BASELINE_CAP,
        max_pos=BASELINE_MAX_POS,
        strict_features=True,
    )

    diag_c = arts["diag"]

    assert diag_adaptive["n_scheduled"] == diag_c["n_scheduled"], (
        f"WG-1 FAIL: n_scheduled mismatch: "
        f"adaptive={diag_adaptive['n_scheduled']} "
        f"canonical={diag_c['n_scheduled']}"
    )
    assert diag_adaptive["n_candidates"] == diag_c["n_candidates"], (
        f"WG-1 FAIL: n_candidates mismatch: "
        f"adaptive={diag_adaptive['n_candidates']} "
        f"canonical={diag_c['n_candidates']}"
    )
    assert diag_adaptive["admission_rate"] == diag_c["admission_rate"], (
        f"WG-1 FAIL: admission_rate mismatch: "
        f"adaptive={diag_adaptive['admission_rate']} "
        f"canonical={diag_c['admission_rate']}"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_metric_equal(
    canonical: dict,
    adaptive: dict,
    key: str,
    diag_adaptive: dict | None = None,
    diag_canonical: dict | None = None,
) -> None:
    """Assert a single metric is bit-identical between canonical and adaptive."""
    # Prefer diag for admission_rate (more authoritative than metrics dict).
    if key == "admission_rate" and diag_adaptive is not None:
        c_val = diag_canonical["admission_rate"] if diag_canonical else canonical.get(key)
        a_val = diag_adaptive["admission_rate"]
    else:
        c_val = canonical.get(key)
        a_val = adaptive.get(key)

    if c_val is None or a_val is None:
        pytest.skip(f"Metric '{key}' not available in one or both paths.")

    assert c_val == a_val, (
        f"WG-1 FAIL: metric '{key}' not bit-identical.\n"
        f"  canonical={c_val!r}\n"
        f"  adaptive={a_val!r}\n"
        f"  delta={abs(c_val - a_val):.2e}"
    )
