#!/usr/bin/env python3
# research/rs_persistence_decay.py
"""RS Persistence Decay — v0.1.4. Study A: does RS_T3 membership *age* predict forward return, beyond mechanical 20-day-window persistence?

Standalone, read-only analysis. No schema changes. Static report to stdout (+ optional Parquet).

v0.1.4 changelog (review fixes):
  - Forward-return alignment HARDENED: the ratio is computed within the merged frame
    (no cross-frame positional assumption), with always-on invariants asserting unique target
    keys (row count preserved) and that every matched target sits EXACTLY h trading days ahead
    (target_ord - source_ord == h > 0). Direction verified: close[t+h] / close[t] - 1.
  - Block bootstrap block length now equals EACH horizon (block_len = h), matching the ~h-day
    overlap dependence, instead of a single max-horizon block for all (overridable via --block-len).
  - The permutation p-value is renamed ``local_null_p`` and labelled a LOCAL DIAGNOSTIC (not a
    formal significance level), since the within-spell null under-controls serial autocorrelation.
  - Section A adds a spell-duration survival curve P(spell >= d) for d in {5,10,20,40,60}.
  - Section C states explicitly that bands are CONDITIONAL slices on rs_pctile (correlated with
    age); cross-band effect sizes are not independent estimates.

v0.1.3 changelog (review fixes):
  - band_a_strategy lower bound is now the tercile floor (rs_tercile_pct), giving the band clean
    operating-band semantics. Members below the ECDF floor (rs_t3 True but rs_pctile <
    rs_tercile_pct, a boundary-convention artifact) are NOT folded into band_a and NOT dropped:
    they are reported in a separate ``band_subfloor`` cell with an explicit count.
  - Corrected the mechanical-persistence null wording: a within-spell shuffle preserves spell
    length and the within-spell return *distribution*, but NOT the temporal return
    autocorrelation. Limitation added: it therefore UNDER-controls the overlapping-window serial
    dependence and is mildly anti-conservative; a within-spell block/circular permutation is the
    proper control (v0.2.0).
  - Limitations expanded: explicit suspension / missing-target-at-T+h exclusion, and the absence
    of any multiple-testing adjustment across horizons and bands.

v0.1.2 changelog (merge of reviewed alternatives):
  - MERGED IN: Section A spell-length distribution (answers whether a long-age "Stale" group
    even exists, and at what sample size) — adapted from version K.
  - MERGED IN: band-stratified age effect on the strategy's operating band (Section C) — the
    intent from versions C and K — but with CORRECT inference (rank statistic on RAW return,
    multiplicity-preserving block bootstrap, within-spell permutation null per band).
  - REJECTED from version K: read-write DB open (here strictly read-only); positional forward
    returns that bridge calendar gaps (here global trading-day ordinal); the i.i.d. OLS slope
    p-value driving verdicts; the np.isin cluster bootstrap that drops draw multiplicity; the
    prescriptive "strategy implications / position sizing" engine (a research script reports
    estimates + uncertainty, it does NOT emit sizing rules from single-regime exploratory data).
  - REJECTED from version C: a Spearman computed on the NET return (rank-invariant to a constant
    cost shift => identical to RAW; reporting it as distinct is misleading). NET appears here
    ONLY as a descriptive level column in the band table, clearly flagged as a flat-cost,
    non-executable approximation that is NOT verified against the tracker's net formula.

DESIGN (see session handoff 2026-05-31, R1):
  - RS_T3 membership uses the LIVE definition: per-day cross-sectional top tercile of
    ``beta_adj_rs_20d``. The threshold is taken from the live screener helper
    ``strategies.trend_pullback.screener._compute_tercile_thresholds`` (numpy-linear quantile
    at ``rs_tercile_pct = 0.6667``). Single source of truth; not reimplemented. If that import
    fails, the documented fallback is ``numpy.quantile(values, pct)`` (the live helper docstring
    guarantees numpy-linear interpolation), which is identical for the continuous case.
  - The per-day universe replicates the pullback screener Step-2 query: ``bullish_features``
    joined to ``daily_price_adj`` with the SAME non-null / validity gates
    (``beta_adj_rs_20d``, ``dist_above_ma20_atr``, ``beta_60`` non-null; ``adj_close > 0``), so
    the daily tercile threshold matches live. Membership is computed UNCONDITIONALLY on regime
    (regime conditioning is R3) and is NOT restricted to pullback-setup days (the dist/beta
    gates) — Study A isolates the RS-age effect.
  - Age = consecutive trading days of uninterrupted RS_T3 membership ending at T (age == 1 on
    the first T3 day). Computed on the panel's own trading-day axis via a global date ordinal;
    a missing day for a stock (suspension / warm-up) or a drop below T3 resets the streak (it
    does NOT bridge across gaps).
  - Forward return: RAW adjusted-close return over {20, 40, 60} trading days from T, aligned by
    global trading-day ordinal = the MARKET's h-th trading day ahead (matching the tracker's
    "elapsed trading days" semantics), NOT the stock's h-th traded day. A stock with no row at
    exactly market-day T+h (suspended on that day, or delisted) yields NaN and is EXCLUDED for
    that horizon; this missing-target exclusion can bias results (see limitations).
  - Primary statistic: Spearman rank correlation between age and forward return (non-parametric;
    robust to the heavy tails of raw returns; no linear-decay assumption). A negative coefficient
    that survives the null is consistent with persistence decay.
  - Inference: circular moving-block bootstrap over ordered unique dates, block length = the
    forward horizon (per-horizon; matches the ~h-day overlap dependence), resampling WHOLE dates
    (cross-sectional dependence) in contiguous blocks (overlapping-window serial dependence), WITH
    draw multiplicity preserved. NOTE: reconcile with research/forward_return_tracker.py before
    citing alongside go-live evidence.
  - Mechanical-persistence null: WITHIN each membership spell, permute the forward-return values
    across the spell's days while holding the age sequence fixed. This breaks the age->return
    mapping while preserving spell length and the within-spell return *distribution*, but NOT the
    temporal return autocorrelation. It therefore tests whether the age-ORDERED returns differ
    from an arbitrary reordering of the same spell's returns; it does NOT reproduce the serial
    autocorrelation induced by the 20-day overlapping windows, so it UNDER-controls that
    dependence and is mildly anti-conservative. The observed Spearman must lie outside this null
    to be read as signal. (A within-spell block/circular permutation, which preserves serial
    autocorrelation, is the proper control and is deferred to v0.2.0.)

KNOWN LIMITATIONS — DO NOT OVERSTATE RESULTS:
  - SURVIVORSHIP: the ~205-name panel is largely *current* constituents. The long-age ("stale")
    group is double-conditioned on having stayed in-universe; RAW forward return also suffers
    delisting attrition (names that delist within the window drop out, biasing returns upward).
    Documented, NOT corrected. Point-in-time ``universe_snapshot`` reconstruction is a v0.2.0
    robustness check.
  - EFFECTIVE SAMPLE / REGIME: daily overlapping windows => effective N << row count. Even a
    multi-year span may cover few regimes. Treat findings as SUGGESTIVE and regime-contingent.
  - RAW LHS conflates the age effect with the market-beta exposure of persistent high-RS names.
    Beta-adjusted / market-excess LHS is DEFERRED to v0.2.0 (needs the benchmark index series
    used by the original ``beta_adj_rs`` construction).
  - SUSPENSION / MISSING TARGET: the forward return uses the market's h-th trading day ahead; a
    stock with no row at exactly T+h (suspended that day, or delisted) is EXCLUDED for that
    horizon. This is on top of the survivorship point above and can bias the estimates.
  - NULL UNDER-CONTROLS SERIAL DEPENDENCE: the within-spell shuffle preserves the return
    distribution but not the temporal autocorrelation of overlapping 20-day windows, so its
    p-values are mildly anti-conservative. A within-spell block/circular permutation is the
    proper control (v0.2.0).
  - BAND COMPARISON: Section C bands are conditional slices on rs_pctile, which correlates with
    age; cross-band effect sizes are NOT independent estimates and must not be compared directly.
  - NO MULTIPLE-TESTING ADJUSTMENT: results span {overall, subfloor, band_a, band_b, band_c} x
    {20, 40, 60}d. The per-cell CIs and permutation p-values carry NO family-wise / FDR
    correction; read them accordingly.
  - BAND CONVENTION: bands are defined on the live ECDF percentile (count<=/N), whereas
    membership is defined on ``value >= threshold`` (numpy-linear quantile). The two conventions
    differ at boundary ties; band_subfloor (rs_pctile < rs_tercile_pct) isolates and reports the
    affected member rows so none are folded into band_a or silently dropped.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

import numpy as np
import pandas as pd

try:  # single source of truth for the RS_T3 threshold
    from strategies.trend_pullback.screener import (  # type: ignore[import-not-found]
        _compute_tercile_thresholds as _live_tercile_thresholds,
    )
except Exception:  # noqa: BLE001 - fall back to the documented numpy-linear equivalent
    _live_tercile_thresholds = None

try:  # single source of truth for the tercile fraction
    from strategies.trend_pullback.config import (  # type: ignore[import-not-found]
        TrendPullbackConfig,
    )

    _DEFAULT_RS_TERCILE_PCT: float = float(TrendPullbackConfig().rs_tercile_pct)
except Exception:  # noqa: BLE001
    _DEFAULT_RS_TERCILE_PCT = 0.6667

try:
    from scipy.stats import spearmanr  # type: ignore[import-not-found]

    _HAVE_SCIPY = True
except Exception:  # noqa: BLE001
    _HAVE_SCIPY = False

# Live read-only connection. Verify this import path matches the codebase
# (handoff: ``data.database.connect`` reads from ``get_settings().db_path``).
from data.database import connect  # type: ignore[import-not-found]  # noqa: E402


# ── 0. Configuration ─────────────────────────────────────────────────────────
@dataclass(frozen=True)
class StudyConfig:
    """Immutable configuration for the RS persistence decay study.

    Attributes:
        rs_tercile_pct: Cross-sectional fraction defining the RS top tercile (T3).
        horizons: Forward-return horizons in trading days.
        age_bins: Descriptive (secondary) age bins ``(label, lo, hi)``, inclusive on both ends.
            For communication only; the primary analysis treats age as continuous.
        bands: Operating-band strata on the live ECDF percentile, ``(label, lo, hi)`` with
            ``lo`` inclusive and ``hi`` exclusive. ``band_subfloor`` (rs_pctile < rs_tercile_pct)
            isolates members below the ECDF floor so they are neither folded into band_a nor
            dropped; ``band_a_strategy`` = [rs_tercile_pct, 0.75) is the clean strategy band. The
            band lower bound 0.6667 is coupled to ``rs_tercile_pct`` (update both together).
        n_boot: Number of block-bootstrap resamples for the CI.
        block_len: Block length (trading days) for the circular moving-block bootstrap.
            ``None`` => use each horizon ``h`` (block matched to that horizon's overlap dependence).
        n_perm: Number of within-spell permutations for the mechanical-persistence null.
        ci_level: Two-sided confidence level for bootstrap intervals.
        min_n: Minimum sample size to attempt inference for a (band, horizon) cell.
        entry_slippage_bps: One-way entry slippage; copied from the tracker constant.
        round_trip_cost_bps: Round-trip cost; copied from the tracker constant.
        seed: RNG seed for reproducibility.
    """

    rs_tercile_pct: float = _DEFAULT_RS_TERCILE_PCT
    horizons: tuple[int, ...] = (20, 40, 60)
    age_bins: tuple[tuple[str, int, int], ...] = (
        ("fresh", 1, 5),
        ("mature", 6, 20),
        ("stale", 60, 10_000),
    )
    bands: tuple[tuple[str, float, float], ...] = (
        # band_subfloor isolates rs_t3 members whose ECDF percentile falls below the tercile
        # floor (a boundary-convention artifact); keep the lower bound coupled to rs_tercile_pct.
        ("band_subfloor", 0.0000, 0.6667),
        ("band_a_strategy", 0.6667, 0.7500),   # strategy operating band (entries cluster ~0.70)
        ("band_b_higher", 0.7500, 0.9000),     # higher RS
        ("band_c_extreme", 0.9000, 1.0000001),  # strongest RS (upper bound includes 1.0)
    )
    n_boot: int = 1_000
    block_len: int | None = None
    n_perm: int = 500
    ci_level: float = 0.95
    min_n: int = 100
    entry_slippage_bps: float = 5.0
    round_trip_cost_bps: float = 40.0
    seed: int = 20260531

    @property
    def total_friction(self) -> float:
        """Flat round-trip friction as a decimal return (NOT verified against tracker net)."""
        return (self.entry_slippage_bps + self.round_trip_cost_bps) / 10_000.0


# ── 1. RS_T3 threshold (live definition) ─────────────────────────────────────
def rs_t3_threshold(values: np.ndarray, pct: float) -> float:
    """Return the RS top-tercile threshold for one day's cross-section.

    Prefers the live screener helper so membership is identical by construction;
    falls back to the documented numpy-linear quantile if that import is unavailable.

    Args:
        values: Non-null ``beta_adj_rs_20d`` values for the day's universe.
        pct: Tercile fraction (e.g. 0.6667).

    Returns:
        The threshold ``thr`` such that a stock is in T3 iff ``value >= thr``.
    """
    if values.size == 0:
        return float("inf")
    if _live_tercile_thresholds is not None:
        _, upper = _live_tercile_thresholds(values.tolist(), lower_pct=pct, upper_pct=pct)
        return float(upper)
    return float(np.quantile(values, pct))  # numpy default == linear interpolation


# ── 2. Data loading (read-only; replicates screener Step-2 universe) ──────────
def load_panel() -> pd.DataFrame:
    """Load the RS feature panel across full history under the live Step-2 gates.

    Returns:
        DataFrame with columns ``stock_id``, ``date`` (datetime64), ``beta_adj_rs_20d``,
        ``adj_close``, sorted by (stock_id, date).
    """
    query = """
        SELECT
            bf.stock_id,
            bf.date,
            bf.beta_adj_rs_20d,
            dp.adj_close
        FROM bullish_features bf
        JOIN daily_price_adj dp
            ON dp.stock_id = bf.stock_id AND dp.date = bf.date
        WHERE bf.beta_adj_rs_20d      IS NOT NULL
            AND bf.dist_above_ma20_atr IS NOT NULL
            AND bf.beta_60             IS NOT NULL
            AND dp.adj_close           IS NOT NULL
            AND dp.adj_close > 0
        ORDER BY bf.stock_id, bf.date
    """
    print("📥  Loading bullish_features ⋈ daily_price_adj (read-only, Step-2 gates) ...")
    with connect(read_only=True) as conn:
        df = conn.execute(query).fetch_df()

    df["date"] = pd.to_datetime(df["date"])
    df["beta_adj_rs_20d"] = df["beta_adj_rs_20d"].astype(float)
    df["adj_close"] = df["adj_close"].astype(float)
    print(
        f"    rows={len(df):,}  stocks={df['stock_id'].nunique():,}  "
        f"dates={df['date'].nunique():,}  "
        f"span={df['date'].min().date()}..{df['date'].max().date()}"
    )
    return df


# ── 3. Membership, age, spells, forward returns ──────────────────────────────
def assign_membership(df: pd.DataFrame, cfg: StudyConfig) -> pd.DataFrame:
    """Add the global trading-day ordinal and the daily RS_T3 membership flag.

    Adds ``date_ord`` (int), ``rs_pctile`` (count<=/N, the live diagnostic convention, [0, 1])
    and ``rs_t3`` (bool). The threshold is recomputed per day over that day's universe.
    """
    print("🧮  Computing per-day RS_T3 thresholds and membership ...")
    ordered_dates = np.sort(df["date"].unique())
    date_to_ord = {d: i for i, d in enumerate(ordered_dates)}
    df = df.copy()
    df["date_ord"] = df["date"].map(date_to_ord).astype(int)

    rs_pctile = np.empty(len(df), dtype=float)
    rs_t3 = np.empty(len(df), dtype=bool)

    for _, idx in df.groupby("date_ord").groups.items():
        block = df.loc[idx, "beta_adj_rs_20d"].to_numpy()
        thr = rs_t3_threshold(block, cfg.rs_tercile_pct)
        # Live diagnostic percentile convention: count(v <= value) / N via weak ECDF.
        sorted_block = np.sort(block, kind="mergesort")
        counts_le = np.searchsorted(sorted_block, block, side="right")
        loc = df.index.get_indexer(idx)
        rs_pctile[loc] = counts_le / block.size
        rs_t3[loc] = block >= thr

    df["rs_pctile"] = rs_pctile
    df["rs_t3"] = rs_t3
    print(f"    T3 member-rows={int(df['rs_t3'].sum()):,} / {len(df):,}")
    return df


def assign_age_and_spells(df: pd.DataFrame) -> pd.DataFrame:
    """Add ``age`` (consecutive T3 trading days ending at T) and ``spell_id``.

    A streak continues only across contiguous trading days (``date_ord`` increment of 1) for the
    same stock while membership holds; any gap or non-membership resets it. ``age`` is 0 on
    non-member rows. ``spell_id`` is unique per contiguous member spell (-1 on non-member rows).
    """
    print("🧮  Computing membership age and spell ids ...")
    df = df.sort_values(["stock_id", "date_ord"], kind="mergesort").reset_index(drop=True)
    sid = df["stock_id"].to_numpy()
    ordn = df["date_ord"].to_numpy()
    member = df["rs_t3"].to_numpy()

    n = len(df)
    age = np.zeros(n, dtype=int)
    spell = np.full(n, -1, dtype=int)
    next_spell = 0
    for i in range(n):
        if not member[i]:
            continue
        continues = (
            i > 0
            and member[i - 1]
            and sid[i] == sid[i - 1]
            and ordn[i] - ordn[i - 1] == 1
        )
        if continues:
            age[i] = age[i - 1] + 1
            spell[i] = spell[i - 1]
        else:
            age[i] = 1
            spell[i] = next_spell
            next_spell += 1

    df["age"] = age
    df["spell_id"] = spell
    print(f"    spells={next_spell:,}  max_age={int(age.max()) if n else 0}")
    return df


def add_forward_returns(df: pd.DataFrame, cfg: StudyConfig) -> pd.DataFrame:
    """Add raw forward returns ``fwd_ret_{h}`` (gross) and ``net_fwd_ret_{h}`` (flat-cost).

    ``fwd_ret_h`` at (stock, date_ord) = adj_close[ord + h] / adj_close[ord] - 1, using the SAME
    stock's row exactly ``h`` trading days ahead on the global axis. Missing target rows yield NaN.

    ``net_fwd_ret_h`` = ``fwd_ret_h`` - ``cfg.total_friction``. NET is a flat-cost, NON-executable
    approximation used ONLY for descriptive band levels; it is NOT verified against the tracker's
    net formula and, being a constant shift, does NOT change any rank-based statistic.
    """
    horizons = cfg.horizons
    print(f"🧮  Computing raw/net forward returns for horizons {horizons} ...")
    base = df[["stock_id", "date_ord", "adj_close"]].copy()
    for h in horizons:
        # tgt carries each row's true ordinal (_tgt_ord) and close (_tgt_close); the join key
        # date_ord = _tgt_ord - h, so a df row at ordinal D matches the target at D + h.
        tgt = base.rename(columns={"adj_close": "_tgt_close"})
        tgt["_tgt_ord"] = tgt["date_ord"]
        tgt["date_ord"] = tgt["date_ord"] - h
        merged = df.merge(
            tgt[["stock_id", "date_ord", "_tgt_close", "_tgt_ord"]],
            on=["stock_id", "date_ord"],
            how="left",
        )
        # Load-bearing invariants: unique target keys keep row count/order, and every matched
        # target sits EXACTLY h trading days AHEAD of its source row (target_ord - source_ord == h).
        assert len(merged) == len(df), "forward-return merge changed row count (duplicate keys?)"
        matched = merged["_tgt_ord"].notna()
        gap = (merged.loc[matched, "_tgt_ord"] - merged.loc[matched, "date_ord"]).to_numpy()
        assert gap.size == 0 or (np.all(gap == h) and np.all(gap > 0)), \
            "forward-return target is not exactly +h ahead"
        # Ratio computed entirely within `merged` (no cross-frame positional assumption):
        # fwd_ret = close[t+h] / close[t] - 1.
        df[f"fwd_ret_{h}"] = (merged["_tgt_close"] / merged["adj_close"] - 1.0).to_numpy()
        df[f"net_fwd_ret_{h}"] = df[f"fwd_ret_{h}"] - cfg.total_friction
        n_ok = int(np.isfinite(df[f"fwd_ret_{h}"]).sum())
        print(f"    h={h:>3}: non-null forward returns = {n_ok:,}  "
              f"(invariant target==source+{h} verified; flat friction "
              f"{cfg.total_friction:.4%}, descriptive only)")
    return df


# ── 4. Inference primitives ──────────────────────────────────────────────────
def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    """Spearman rank correlation; NaN if degenerate."""
    if x.size < 3 or np.all(x == x[0]) or np.all(y == y[0]):
        return float("nan")
    if _HAVE_SCIPY:
        rho, _ = spearmanr(x, y)
        return float(rho)
    xr = pd.Series(x).rank().to_numpy()
    yr = pd.Series(y).rank().to_numpy()
    return float(np.corrcoef(xr, yr)[0, 1])


def _groups_by_key(key: np.ndarray, min_size: int = 1) -> list[np.ndarray]:
    """Return positional-index arrays grouped by ``key`` (O(n log n), built once)."""
    order = np.argsort(key, kind="mergesort")
    sorted_key = key[order]
    _, starts = np.unique(sorted_key, return_index=True)
    bounds = np.append(starts, len(sorted_key))
    return [
        order[bounds[k]:bounds[k + 1]]
        for k in range(len(bounds) - 1)
        if bounds[k + 1] - bounds[k] >= min_size
    ]


def block_bootstrap_ci(
    age: np.ndarray,
    val: np.ndarray,
    date_ord: np.ndarray,
    cfg: StudyConfig,
    block_len: int,
) -> tuple[float, float, float]:
    """Circular moving-block bootstrap CI for Spearman(age, val), grouped by date.

    Whole dates are resampled together (cross-sectional dependence) in contiguous blocks
    (overlapping-window serial dependence) WITH draw multiplicity preserved (a date drawn k
    times contributes its rows k times). Returns (point, ci_low, ci_high).
    """
    point = _spearman(age, val)
    uniq = np.unique(date_ord)
    n_dates = uniq.size
    if n_dates < block_len * 2:
        return point, float("nan"), float("nan")

    # date-rank space + positions per date (built once)
    rank_of = {d: r for r, d in enumerate(uniq)}
    date_rank = np.fromiter((rank_of[d] for d in date_ord), dtype=int, count=date_ord.size)
    groups = [np.empty(0, dtype=int)] * n_dates
    for grp in _groups_by_key(date_rank):
        groups[date_rank[grp[0]]] = grp

    rng = np.random.default_rng(cfg.seed)
    n_blocks = int(np.ceil(n_dates / block_len))
    estimates = np.empty(cfg.n_boot, dtype=float)
    for b in range(cfg.n_boot):
        starts = rng.integers(0, n_dates, size=n_blocks)
        parts = [groups[(s + k) % n_dates] for s in starts for k in range(block_len)]
        sel = np.concatenate(parts)
        estimates[b] = _spearman(age[sel], val[sel])

    estimates = estimates[np.isfinite(estimates)]
    if estimates.size == 0:
        return point, float("nan"), float("nan")
    alpha = 1.0 - cfg.ci_level
    return point, float(np.quantile(estimates, alpha / 2)), float(np.quantile(estimates, 1 - alpha / 2))


def within_spell_perm_p(
    age: np.ndarray,
    val: np.ndarray,
    spell_id: np.ndarray,
    cfg: StudyConfig,
) -> float:
    """Two-sided permutation p-value under within-spell forward-return shuffling.

    Within each spell, forward returns are permuted across the spell's days while age is held
    fixed. This preserves spell length and the within-spell return distribution, but NOT the
    temporal return autocorrelation; it therefore under-controls the overlapping-window serial
    dependence and is mildly anti-conservative (see header limitations). Returns
    ``(count(|null| >= |observed|) + 1) / (n_perm + 1)``.
    """
    observed = abs(_spearman(age, val))
    if not np.isfinite(observed):
        return float("nan")
    spell_groups = _groups_by_key(spell_id, min_size=2)
    rng = np.random.default_rng(cfg.seed + 1)
    ge = 0
    for _ in range(cfg.n_perm):
        permuted = val.copy()
        for grp in spell_groups:
            permuted[grp] = rng.permutation(permuted[grp])
        stat = abs(_spearman(age, permuted))
        if np.isfinite(stat) and stat >= observed:
            ge += 1
    return (ge + 1) / (cfg.n_perm + 1)


def _verdict(ci_low: float, ci_high: float, perm_p: float, cfg: StudyConfig) -> str:
    """Descriptive verdict; no prescriptions."""
    ci_excludes_zero = np.isfinite(ci_low) and np.isfinite(ci_high) and (ci_low > 0 or ci_high < 0)
    beats_null = np.isfinite(perm_p) and perm_p < (1 - cfg.ci_level)
    if ci_excludes_zero and beats_null:
        return "exceeds mechanical-persistence null"
    return "NOT separable from mechanical persistence"


def analyze_cell(sub: pd.DataFrame, col: str, cfg: StudyConfig, block_len: int) -> dict[str, object]:
    """Run the age-effect inference for one subset and one return column.

    ``local_null_p`` is the within-spell permutation p-value; it is a LOCAL DIAGNOSTIC, not a
    formal significance level (the null under-controls serial autocorrelation — see header).
    """
    sub = sub.dropna(subset=[col, "age", "spell_id"])
    age = sub["age"].to_numpy()
    val = sub[col].to_numpy()
    if age.size < cfg.min_n:
        return {"n": int(age.size), "spearman": float("nan"), "ci_low": float("nan"),
                "ci_high": float("nan"), "local_null_p": float("nan"), "verdict": "insufficient n"}
    point, lo, hi = block_bootstrap_ci(age, val, sub["date_ord"].to_numpy(), cfg, block_len)
    local_null_p = within_spell_perm_p(age, val, sub["spell_id"].to_numpy(), cfg)
    return {"n": int(age.size), "spearman": point, "ci_low": lo, "ci_high": hi,
            "local_null_p": local_null_p, "verdict": _verdict(lo, hi, local_null_p, cfg)}


# ── 5. Section A: RS_T3 spell distribution ───────────────────────────────────
def section_a_spells(member: pd.DataFrame) -> dict[str, object]:
    """Print and return the RS_T3 spell-length distribution (feasibility of long-age groups)."""
    print("\n" + "=" * 78)
    print("📊  SECTION A — RS_T3 spell-length distribution")
    print("=" * 78)
    if member.empty:
        print("    no T3 member rows.")
        return {"n_spells": 0}

    by_spell = member.groupby("spell_id")
    lengths = by_spell.size().to_numpy()
    per_stock = member.groupby("stock_id")["spell_id"].nunique()

    print(f"    spells={lengths.size:,}  spell-days={int(lengths.sum()):,}  "
          f"mean_dur={lengths.mean():.1f}  median_dur={np.median(lengths):.1f}")
    print("    duration percentiles (trading days):")
    for p in (50, 75, 90, 95, 99, 100):
        label = "MAX" if p == 100 else f"P{p}"
        print(f"      {label:<4} {np.percentile(lengths, p):>6.0f}")
    print(f"    stocks with >=1 spell={per_stock.size:,}  "
          f"avg_spells/stock={per_stock.mean():.2f}  "
          f"spells>=60d={int((lengths >= 60).sum()):,}")
    # Survival curve P(spell >= d): how rare are long-lived RS spells? (feeds R2 / RS-acceleration)
    survival = {}
    print("    spell-duration survival  P(spell >= d):")
    for d in (5, 10, 20, 40, 60):
        s = float(np.mean(lengths >= d))
        survival[d] = s
        print(f"      d>={d:>3}: P={s:.3f}  (spells={int((lengths >= d).sum()):,})")
    return {"n_spells": int(lengths.size), "lengths": lengths, "survival": survival}


# ── 6. Section B: overall age -> forward return ──────────────────────────────
def descriptive_age_bins(sub: pd.DataFrame, col: str, cfg: StudyConfig) -> pd.DataFrame:
    """Secondary descriptive table: mean/median forward return by named age bin."""
    rows = []
    for label, lo, hi in cfg.age_bins:
        vals = sub.loc[(sub["age"] >= lo) & (sub["age"] <= hi), col].dropna().to_numpy()
        rows.append({
            "age_bin": label, "age_lo": lo, "age_hi": hi, "n": int(vals.size),
            "mean": float(np.mean(vals)) if vals.size else float("nan"),
            "median": float(np.median(vals)) if vals.size else float("nan"),
        })
    return pd.DataFrame(rows)


def section_b_overall(member: pd.DataFrame, cfg: StudyConfig) -> dict[int, dict[str, object]]:
    """Print and return the overall (all-T3) age effect per horizon."""
    print("\n" + "=" * 78)
    print("📊  SECTION B — age vs forward return (all RS_T3 members)")
    print(f"    Spearman(age, fwd_ret) | block_len = horizon (overridable) | n_boot={cfg.n_boot} | "
          f"n_perm={cfg.n_perm}")
    print("=" * 78)

    out: dict[int, dict[str, object]] = {}
    for h in cfg.horizons:
        col = f"fwd_ret_{h}"
        block_len = cfg.block_len or h  # match block length to the horizon's overlap dependence
        res = analyze_cell(member, col, cfg, block_len)
        bins = descriptive_age_bins(member.dropna(subset=[col]), col, cfg)
        out[h] = {**res, "bins": bins}

        print(f"\n  ── horizon = {h} trading days ──  (n={res['n']:,}, block_len={block_len})")
        print(f"     Spearman(age, fwd_ret_{h}) = {res['spearman']:+.4f}  "
              f"[{cfg.ci_level:.0%} block-CI: {res['ci_low']:+.4f}, {res['ci_high']:+.4f}]")
        print(f"     local_null_p (within-spell diagnostic, NOT formal significance) = "
              f"{res['local_null_p']:.4f}")
        print(f"     interpretation: {res['verdict']}")
        print("     descriptive age bins (secondary, raw):")
        for _, r in bins.iterrows():
            print(f"       {r['age_bin']:<7} age[{int(r['age_lo']):>2}..{int(r['age_hi']):>2}]  "
                  f"n={int(r['n']):>6,}  mean={r['mean']:+.4f}  median={r['median']:+.4f}")
    return out


# ── 7. Section C: band-stratified age effect ─────────────────────────────────
def section_c_bands(member: pd.DataFrame, cfg: StudyConfig) -> dict[str, object]:
    """Print and return the age effect within operating-band strata of the live ECDF percentile."""
    print("\n" + "=" * 78)
    print("📊  SECTION C — band-stratified age effect (operating bands on rs_pctile)")
    print("    rank statistic on RAW return; NET shown as descriptive level only "
          "(flat-cost, non-executable)")
    print("    NOTE: bands are CONDITIONAL slices on rs_pctile (which correlates with age); "
          "cross-band effect sizes are NOT independent estimates — do not compare directly.")
    print("=" * 78)

    out: dict[str, object] = {}

    # Convention-gap diagnostic: members below the ECDF tercile floor (rs_t3 True by the
    # value>=threshold rule, but rs_pctile < rs_tercile_pct). Surfaced, never silently folded.
    n_subfloor = int((member["rs_pctile"] < cfg.rs_tercile_pct).sum())
    frac = n_subfloor / len(member) if len(member) else 0.0
    flag = "  ⚠️ non-trivial" if frac > 0.01 else ""
    print(f"    convention-gap (rs_t3 True & rs_pctile < {cfg.rs_tercile_pct:.4f}): "
          f"{n_subfloor:,} member-rows ({frac:.2%}){flag} — reported as band_subfloor below")

    for label, lo, hi in cfg.bands:
        band = member[(member["rs_pctile"] >= lo) & (member["rs_pctile"] < hi)]
        print(f"\n  ── band {label}  rs_pctile[{lo:.4f}, {hi:.4f})  (member-rows={len(band):,}) ──")
        band_out: dict[int, dict[str, object]] = {}
        for h in cfg.horizons:
            col, net = f"fwd_ret_{h}", f"net_fwd_ret_{h}"
            block_len = cfg.block_len or h  # match block length to the horizon's overlap dependence
            res = analyze_cell(band, col, cfg, block_len)
            vals = band[col].dropna()
            raw_mean = float(vals.mean()) if not vals.empty else float("nan")
            raw_med = float(vals.median()) if not vals.empty else float("nan")
            net_mean = raw_mean - cfg.total_friction
            net_med = raw_med - cfg.total_friction
            band_out[h] = {**res, "raw_mean": raw_mean, "net_mean": net_mean}
            print(f"     h={h:>3}: n={res['n']:>6,}  "
                  f"rho(age,raw)={res['spearman']:+.4f} "
                  f"CI[{res['ci_low']:+.4f},{res['ci_high']:+.4f}] "
                  f"local_null_p={res['local_null_p']:.4f}  | {res['verdict']}")
            print(f"            level: raw_mean={raw_mean:+.4f} raw_med={raw_med:+.4f}  "
                  f"net_mean={net_mean:+.4f} net_med={net_med:+.4f}")
        out[label] = band_out
    return out


# ── 8. Entry point ───────────────────────────────────────────────────────────
def main() -> int:
    """Parse arguments, run Sections A/B/C, optionally persist the analysis frame."""
    parser = argparse.ArgumentParser(description="RS Persistence Decay — Study A (v0.1.4)")
    parser.add_argument("--horizons", type=int, nargs="+", default=[20, 40, 60])
    parser.add_argument("--n-boot", type=int, default=1_000)
    parser.add_argument("--n-perm", type=int, default=500)
    parser.add_argument("--block-len", type=int, default=None,
                        help="Bootstrap block length in trading days (default: equal to each horizon).")
    parser.add_argument("--seed", type=int, default=20260531)
    parser.add_argument("--out", type=str, default=None,
                        help="Optional Parquet path for the per-row analysis frame.")
    args = parser.parse_args()

    cfg = StudyConfig(
        horizons=tuple(args.horizons),
        n_boot=args.n_boot,
        n_perm=args.n_perm,
        block_len=args.block_len,
        seed=args.seed,
    )

    df = load_panel()
    if df.empty:
        print("[error] no rows loaded.")
        return 1
    df = assign_membership(df, cfg)
    df = assign_age_and_spells(df)
    df = add_forward_returns(df, cfg)

    member = df[df["rs_t3"]].copy()
    section_a_spells(member)
    section_b_overall(member, cfg)
    section_c_bands(member, cfg)

    print("\n⚠️   Limitations (see header): survivorship in the current-constituent panel "
          "(stale double-conditioned; RAW LHS has delisting attrition); suspension / missing "
          "target at T+h is excluded and can bias estimates; low effective N from overlapping "
          "windows / few regimes; RAW LHS confounded with market beta; the within-spell null "
          "under-controls serial autocorrelation (mildly anti-conservative); NO multiple-testing "
          "adjustment across horizons/bands. Findings are suggestive and regime-contingent; any "
          "strategy change must pass bull_strategy_sanity_harness.py.")

    if args.out:
        keep = ["stock_id", "date", "date_ord", "beta_adj_rs_20d", "rs_pctile",
                "rs_t3", "age", "spell_id"]
        keep += [f"fwd_ret_{h}" for h in cfg.horizons]
        keep += [f"net_fwd_ret_{h}" for h in cfg.horizons]
        df[keep].to_parquet(args.out, index=False)
        print(f"\n✅  Analysis frame written to {args.out}")
    else:
        print("\n✅  Done (no Parquet written; pass --out to persist the analysis frame).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
