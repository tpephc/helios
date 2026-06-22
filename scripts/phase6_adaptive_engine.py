# scripts/phase6_adaptive_engine.py
"""Phase 6 Step 3C — Adaptive release engine.

Implements evaluate_candidate_adaptive: a unified daily simulator that
structurally reuses Phase 4 schedule_positions admission logic and
Phase 4 reconstruct_nav_for_horizon NAV math, while substituting the
exit-trigger mechanism with per-candidate exit policy functions.

Structural reuse discipline (per CCI-7 / Step 3 Entry Note):
    Code-block copy-with-modification, not function-call reuse.
    Admission block: Phase 4 schedule_positions, conservative row-by-
    row iteration to preserve bit-identical ordering (P0-BLOCK-007).
    NAV block: Phase 4 reconstruct_nav_for_horizon; only modification
    is loop bound per-position days_held instead of scalar h.
    Coverage invariant check retained from Phase 4 (structural fidelity).

WG-1 degenerate equivalence invariant:
    Under never_exit_policy, evaluate_candidate_adaptive must produce:
    1. Scheduled positions SET-EQUAL to Phase 4 schedule_positions output.
    2. Daily NAV BIT-IDENTICAL to Phase 4 reconstruct_nav_for_horizon.
    3. Metrics BIT-IDENTICAL (Sharpe, MaxDD, admission_rate,
       mean_holding_days).

Hard ceiling semantics:
    Ceiling exits use same-day release for all candidates.
    T+1 release applies ONLY to policy-trigger exits before ceiling.

Type convention:
    All internal dates are pd.Timestamp.
    PositionState.entry_date / MarketSnapshot.as_of are Python date;
    conversion happens only at the API boundary when constructing them.

Calendar lineage:
    trading_calendar and date_to_pos are owned and passed in by the
    caller. This ensures canonical path and adaptive path use the
    identical calendar object, a pre-condition for WG-1 bit-identical
    assertion. The caller must build calendar from the same source as
    build_signal_ledger_for_horizon (typically price_panel["date"]
    filtered by PANEL_START).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from scripts.run_phase6_evaluation import (
    ExitDecision,
    MarketSnapshot,
    PositionState,
)

log = logging.getLogger(__name__)


# =====================================================================
# AdaptiveScheduledPosition — WG-1 canonical comparison surface
# =====================================================================


@dataclass(frozen=True)
class AdaptiveScheduledPosition:
    """Canonical projection of an admitted position for WG-1 set-equality.

    Fields match Phase 4 ScheduledPosition:
        stock_id, signal_date, entry_date, exit_date, weight

    WG-1 asserts:
        project_scheduled_positions(adaptive_positions)
        == {ScheduledPosition(...) for pos in canonical_sched}
    as sets under field-wise equality.
    """

    stock_id: str
    signal_date: pd.Timestamp
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    weight: float


def project_scheduled_positions(
    adaptive_positions: list[AdaptivePosition],
) -> set[AdaptiveScheduledPosition]:
    """Project adaptive positions to canonical comparison surface.

    Convenience helper for WG-1 set-equality assertion.
    Raises ValueError if any position has exit_date=None.
    """
    result = set()
    for pos in adaptive_positions:
        if pos.exit_date is None:
            raise ValueError(
                f"project_scheduled_positions: exit_date is None for "
                f"symbol={pos.symbol!r}. All positions must be fully "
                "simulated before projection."
            )
        result.add(pos.to_scheduled())
    return result


def project_position_key(
    pos: AdaptivePosition,
) -> tuple[str, pd.Timestamp, pd.Timestamp, pd.Timestamp, float]:
    """Return a tuple key for WG-1 set comparison.

    Avoids dataclass equality fragility when fields are added or renamed.
    Tuple fields match AdaptiveScheduledPosition:
        (stock_id, signal_date, entry_date, exit_date, weight)

    Usage in WG-1:
        adaptive_keys  = {project_position_key(p) for p in adaptive_positions}
        canonical_keys = {
            (p.stock_id, p.signal_date, p.entry_date, p.exit_date, p.weight)
            for p in canonical_scheduled
        }
        assert adaptive_keys == canonical_keys
    """
    if pos.exit_date is None:
        raise ValueError(
            f"project_position_key: exit_date is None for "
            f"symbol={pos.symbol!r}."
        )
    return (
        pos.symbol,
        pos.signal_date,
        pos.entry_date,
        pos.exit_date,
        pos.weight,
    )


# =====================================================================
# AdaptivePosition — internal simulator state and result
# =====================================================================


@dataclass
class AdaptivePosition:
    """Simulator state and result for one admitted position.

    Internal simulator output; stable enough for WG-1 tests,
    not exported outside Phase 6 evaluation.

    exit_date / release_date semantics:
        ceiling exit:
            exit_date    = trading_calendar[entry_pos + hard_ceiling_h - 1]
                         = canonical ScheduledPosition.exit_date (WG-1)
            release_date = exit_date      (same-day, all candidates)
        policy-trigger exit on decision_date t:
            exit_date    = _next_calendar_day(t)   (T+1)
            release_date = exit_date

    days_held is inclusive: entry_date = 1.
    """

    symbol: str
    signal_date: pd.Timestamp
    entry_date: pd.Timestamp
    entry_price: float                      # adj_open at entry_date
    entry_atr: float                        # atr_14 at signal_date, frozen
    weight: float                           # = cap
    fwd_return_20td: float                  # pass-through from ledger row

    # Updated per bar
    max_close_since_entry: float
    days_held: int                          # inclusive: entry_date = 1

    # Set on exit
    exit_date: pd.Timestamp | None = None
    release_date: pd.Timestamp | None = None
    exit_reason: str = ""
    exit_metadata: dict = field(default_factory=dict)

    def to_scheduled(self) -> AdaptiveScheduledPosition:
        """Project to WG-1 canonical comparison surface."""
        if self.exit_date is None:
            raise ValueError(
                f"to_scheduled: exit_date is None for symbol={self.symbol!r}."
            )
        return AdaptiveScheduledPosition(
            stock_id=self.symbol,
            signal_date=self.signal_date,
            entry_date=self.entry_date,
            exit_date=self.exit_date,
            weight=self.weight,
        )


# =====================================================================
# Degenerate exit policy (WG-1 test fixture)
# =====================================================================


def never_exit_policy(
    pos: PositionState,
    mkt: MarketSnapshot,
) -> ExitDecision:
    """Degenerate exit policy: never trigger before ceiling.

    WG-1 fixture. Under this policy every position holds to
    hard_ceiling_h, producing bit-identical output to Phase 5
    canonical path.
    """
    return ExitDecision(should_exit=False, reason="", metadata={})


# =====================================================================
# Calendar helper
# =====================================================================


def _next_calendar_day(
    trading_calendar: list[pd.Timestamp],
    date_to_pos: dict[pd.Timestamp, int],
    current: pd.Timestamp,
) -> pd.Timestamp:
    """Return the next trading day after current.

    Raises RuntimeError if current is not in calendar or is last day.
    No DB I/O. Bit-identical with build_signal_ledger_for_horizon.
    """
    idx = date_to_pos.get(current)
    if idx is None:
        raise RuntimeError(
            f"_next_calendar_day: {current!r} not found in date_to_pos."
        )
    next_idx = idx + 1
    if next_idx >= len(trading_calendar):
        raise RuntimeError(
            f"_next_calendar_day: {current!r} is the last day in calendar. "
            "Calendar must extend at least one day beyond the last "
            "possible exit decision date."
        )
    return trading_calendar[next_idx]


# =====================================================================
# Per-position forward simulation
# =====================================================================


def _simulate_position_forward(
    pos: AdaptivePosition,
    trading_calendar: list[pd.Timestamp],
    date_to_pos: dict[pd.Timestamp, int],
    close_map: dict[tuple[str, pd.Timestamp], float],
    feature_idx: pd.DataFrame,
    exit_policy_fn: Callable[[PositionState, MarketSnapshot], ExitDecision],
    hard_ceiling_h: int,
    strict_features: bool = False,
) -> AdaptivePosition:
    """Simulate pos forward from entry_date; populate exit fields.

    open_map is intentionally excluded: entry-day NAV return (close/open)
    is computed in _reconstruct_nav_adaptive, not here. This function
    only needs close prices to track max_close and evaluate exit policy.

    Args:
        strict_features: If True, raise RuntimeError on missing feature
            rows instead of continuing. Set True for WG-1 to catch
            ABI violations as fatal errors.

    days_held inclusive (entry_date = 1). On bar k (0-indexed):
        trading_day = trading_calendar[entry_pos + k]
        days_held   = k + 1

    Ceiling exit (days_held == hard_ceiling_h):
        exit_date    = trading_day = trading_calendar[entry_pos + h - 1]
                     = canonical ScheduledPosition.exit_date  ← WG-1
        release_date = exit_date  (same-day, all candidates)

    Policy-trigger exit on trading_day t:
        exit_date    = _next_calendar_day(t)   (T+1)
        release_date = exit_date
    """
    entry_pos = date_to_pos.get(pos.entry_date)
    if entry_pos is None:
        raise RuntimeError(
            f"_simulate_position_forward: entry_date={pos.entry_date!r} "
            f"not in date_to_pos for symbol={pos.symbol!r}. "
            "Calendar must cover entry_date."
        )

    max_close = pos.max_close_since_entry
    final_days_held = 1
    result_exit_date: pd.Timestamp | None = None
    result_release_date: pd.Timestamp | None = None
    result_reason = ""
    result_metadata: dict = {}

    for k in range(hard_ceiling_h):
        cal_idx = entry_pos + k
        if cal_idx >= len(trading_calendar):
            raise RuntimeError(
                f"_simulate_position_forward: calendar exhausted at k={k} "
                f"(entry_pos={entry_pos}, hard_ceiling_h={hard_ceiling_h}) "
                f"for symbol={pos.symbol!r} entry_date={pos.entry_date!r}. "
                "This is a fatal data integrity error; calendar must cover "
                "entry_date + hard_ceiling_h trading days."
            )

        trading_day = trading_calendar[cal_idx]
        days_held = k + 1  # inclusive

        close_t = close_map.get((pos.symbol, trading_day))
        if close_t is None or close_t <= 0:
            log.warning(
                "_simulate_position_forward: missing/zero close for "
                "symbol=%s date=%s; skipping bar.", pos.symbol, trading_day,
            )
            final_days_held = days_held
            continue

        max_close = max(max_close, close_t)
        final_days_held = days_held

        # Ceiling check — same-day release, all candidates.
        if days_held >= hard_ceiling_h:
            result_exit_date = trading_day
            result_release_date = trading_day
            result_reason = "ceiling"
            break

        # Previous bar for close_prev / ma20_prev.
        prev_cal_idx = cal_idx - 1
        if prev_cal_idx < 0:
            continue
        prev_day = trading_calendar[prev_cal_idx]

        close_prev = close_map.get((pos.symbol, prev_day))
        if close_prev is None or close_prev <= 0:
            continue

        # Feature lookup.
        try:
            row_t    = feature_idx.loc[(pos.symbol, trading_day)]
            row_prev = feature_idx.loc[(pos.symbol, prev_day)]
        except KeyError as exc:
            msg = (
                f"_simulate_position_forward: missing feature row for "
                f"symbol={pos.symbol!r} date={trading_day!r} or "
                f"{prev_day!r}: {exc}"
            )
            if strict_features:
                raise RuntimeError(msg) from exc
            log.warning("%s; skipping policy evaluation.", msg)
            continue

        pos_state = PositionState(
            symbol=pos.symbol,
            entry_date=pos.entry_date.date(),
            entry_price=pos.entry_price,
            entry_atr=pos.entry_atr,
            max_close_since_entry=max_close,
            days_held=days_held,
        )
        mkt = MarketSnapshot(
            as_of=trading_day.date(),
            close=float(close_t),
            close_prev=float(close_prev),
            ma20=float(row_t["sma_20"]),
            ma20_prev=float(row_prev["sma_20"]),
            rs_60d_rank=float(row_t["rs_60d_rank"]),
            donchian_low_excl=float(row_t["donchian_low_excl"]),
        )

        decision = exit_policy_fn(pos_state, mkt)
        if decision.should_exit:
            next_day = _next_calendar_day(
                trading_calendar, date_to_pos, trading_day
            )
            result_exit_date = next_day
            result_release_date = next_day
            result_reason = decision.reason
            result_metadata = dict(decision.metadata)
            break

    else:
        # Loop exhausted without break. Should not happen: ceiling fires
        # on the last bar. Log as error; use last bar as fallback.
        last_idx = min(entry_pos + hard_ceiling_h - 1,
                       len(trading_calendar) - 1)
        last_day = trading_calendar[last_idx]
        result_exit_date = last_day
        result_release_date = last_day
        result_reason = "ceiling_loop_exhausted"
        log.error(
            "_simulate_position_forward: loop exhausted without break "
            "for symbol=%s entry_date=%s. Ceiling should have fired.",
            pos.symbol, pos.entry_date,
        )

    return AdaptivePosition(
        symbol=pos.symbol,
        signal_date=pos.signal_date,
        entry_date=pos.entry_date,
        entry_price=pos.entry_price,
        entry_atr=pos.entry_atr,
        weight=pos.weight,
        fwd_return_20td=pos.fwd_return_20td,
        max_close_since_entry=max_close,
        days_held=final_days_held,
        exit_date=result_exit_date,
        release_date=result_release_date,
        exit_reason=result_reason,
        exit_metadata=result_metadata,
    )


# =====================================================================
# NAV reconstruction
# Phase 4 reconstruct_nav_for_horizon copy-block.
# Only modifications:
#   1. pos.symbol instead of pos.stock_id (field name)
#   2. loop bound: pos.days_held (per-position) instead of scalar h
#   3. cal / date_to_pos passed in (pre-built, same lineage as admission)
#   4. Coverage check adapted for variable h (retained for structural fidelity)
# =====================================================================


def _reconstruct_nav_adaptive(
    adaptive_positions: list[AdaptivePosition],
    close_map: dict[tuple[str, pd.Timestamp], float],
    open_map: dict[tuple[str, pd.Timestamp], float],
    cal: pd.DatetimeIndex,
    date_to_pos: dict[pd.Timestamp, int],
) -> pd.DataFrame:
    """Reconstruct NAV for adaptive positions with variable holding periods.

    Phase 4 reconstruct_nav_for_horizon copy-block.
    For WG-1 degenerate path (all pos.days_held == hard_ceiling_h),
    produces bit-identical output to reconstruct_nav_for_horizon(h=h).

    Differences from Phase 4 (exhaustive):
        - pos.symbol instead of pos.stock_id
        - for k in range(pos.days_held) instead of range(h)
        - cal and date_to_pos are pre-built and passed in
        - error message omits scalar h parameter (not available)
        - coverage check uses mean(pos.days_held) as expected h
    """
    if not adaptive_positions:
        raise ValueError("_reconstruct_nav_adaptive: empty position list.")

    port_simple_ret = np.zeros(len(cal), dtype=float)

    for pos in adaptive_positions:
        entry_pos = date_to_pos.get(pos.entry_date)
        if entry_pos is None:
            log.warning(
                "_reconstruct_nav_adaptive: entry_date %s not in calendar "
                "for %s — skipped", pos.entry_date, pos.symbol,
            )
            continue

        # Per-position loop bound (only modification to NAV math).
        h_pos = pos.days_held

        for k in range(h_pos):          # k=0 → entry day, k=h_pos-1 → exit day
            tk_pos = entry_pos + k
            if tk_pos >= len(cal):
                break
            t_k  = cal[tk_pos]
            t_k1 = cal[tk_pos - 1] if tk_pos > 0 else None

            close_k = close_map.get((pos.symbol, t_k))
            if close_k is None or close_k <= 0:
                continue

            if k == 0:
                open_k = open_map.get((pos.symbol, t_k))
                if open_k is None or open_k <= 0:
                    continue
                day_simple = close_k / open_k - 1.0
            else:
                if t_k1 is None:
                    continue
                close_prev = close_map.get((pos.symbol, t_k1))
                if close_prev is None or close_prev <= 0:
                    continue
                day_simple = close_k / close_prev - 1.0

            port_simple_ret[tk_pos] += pos.weight * day_simple

    nav = np.empty(len(cal), dtype=float)
    nav[0] = 1.0
    for i in range(1, len(cal)):
        nav[i] = nav[i - 1] * (1.0 + port_simple_ret[i])
        if nav[i] <= 0:
            raise RuntimeError(
                f"NAV non-positive at {cal[i].date()} "
                f"(nav={nav[i]:.6f}, ret={port_simple_ret[i]:.6f})."
            )

    log_ret = np.empty(len(cal), dtype=float)
    log_ret[0] = 0.0
    log_ret[1:] = np.log(nav[1:] / nav[:-1])

    # Adaptive analogue of Phase 4 coverage invariant.
    # Phase 4 uses scalar h; adaptive uses mean(days_held) as proxy.
    # Mathematical definition differs: do not compare thresholds across
    # the two versions. Retained for observability only.
    n_positions = len(adaptive_positions)
    if n_positions > 0:
        total_nonzero = int(np.count_nonzero(port_simple_ret))
        coverage_pct = 100.0 * total_nonzero / max(n_positions, 1)
        mean_h = sum(p.days_held for p in adaptive_positions) / n_positions
        if coverage_pct < 50.0:
            log.warning(
                "_reconstruct_nav_adaptive: mean_h=%.1f coverage=%.1f%% "
                "(non-zero days=%d, n_positions=%d). "
                "Some positions may have zero price coverage.",
                mean_h, coverage_pct, total_nonzero, n_positions,
            )
        else:
            log.info(
                "_reconstruct_nav_adaptive: mean_h=%.1f coverage=%.1f%% ✓",
                mean_h, coverage_pct,
            )

    return pd.DataFrame({
        "date":             cal,
        "nav":              nav,
        "daily_log_return": log_ret,
    })


# =====================================================================
# Main engine
# =====================================================================


def evaluate_candidate_adaptive(
    ranked: pd.DataFrame,
    feature_panel: pd.DataFrame,
    price_panel: pd.DataFrame,
    trading_calendar: list[pd.Timestamp],
    date_to_pos: dict[pd.Timestamp, int],
    exit_policy_fn: Callable[[PositionState, MarketSnapshot], ExitDecision],
    hard_ceiling_h: int,
    cap: float,
    max_pos: int,
    strict_features: bool = False,
) -> tuple[list[AdaptivePosition], pd.DataFrame, dict]:
    """Unified daily simulator for Phase 6 adaptive exit evaluation.

    Args:
        ranked:           Signal ledger with rank_order column (ARM_B)
                          or without (FIFO). Must have valid_path,
                          stock_id, signal_date, entry_date,
                          fwd_return_20td, atr_14 columns.
        feature_panel:    Pre-loaded features with columns: stock_id,
                          date, sma_20, rs_60d_rank, donchian_low_excl,
                          atr_14. MultiIndex or flat; will be indexed
                          internally.
        price_panel:      Columnar [stock_id, date, adj_close, adj_open].
                          Per Phase 5 load_daily_price_paths ABI.
        trading_calendar: Ordered list[pd.Timestamp] covering the full
                          simulation window. Same object used by
                          build_signal_ledger_for_horizon.
        date_to_pos:      {pd.Timestamp: int} inverse of trading_calendar.
        exit_policy_fn:   Callable[[PositionState, MarketSnapshot],
                          ExitDecision]. Use never_exit_policy for WG-1.
        hard_ceiling_h:   Maximum inclusive holding days (20 for WG-1).
        cap:              Per-position capital weight (e.g. 0.10).
        max_pos:          Maximum concurrent open positions.
        strict_features:  If True, missing feature rows raise RuntimeError.
                          Set True for WG-1 to catch ABI violations fatally.

    Returns:
        (adaptive_positions, nav_df, diag)
        adaptive_positions: list[AdaptivePosition] with all exit fields set.
        nav_df: pd.DataFrame [date, nav, daily_log_return].
        diag: same keys as Phase 4 schedule_positions diag +
              mean_holding_days.

    Admission invariants (Phase 4 copy-block, 10 invariants):
        1.  valid_path rows only
        2.  sort: [signal_date, rank_order, stock_id] if rank_order present
                  else [signal_date, stock_id]
        3.  release before same-day admission
        4.  release predicate: release_date <= sig_ts (unchanged)
        5.  duplicate stock skip
        6.  max_pos cap before exposure cap
        7.  exposure cap: current_exposure + cap <= 1.0 + 1e-9
        8.  position fields preserved
        9.  P3-FP-002 retained
        10. diag keys retained
    """
    # ------------------------------------------------------------------
    # Pre-build price maps (Phase 4 pattern: dict keyed by (stock_id, date))
    # ------------------------------------------------------------------
    _keys     = list(zip(price_panel["stock_id"], price_panel["date"]))
    close_map: dict[tuple[str, pd.Timestamp], float] = dict(
        zip(_keys, price_panel["adj_close"])
    )
    open_map: dict[tuple[str, pd.Timestamp], float] = dict(
        zip(_keys, price_panel["adj_open"])
    )

    # Feature panel: set_index for O(log N) .loc access.
    if isinstance(feature_panel.index, pd.MultiIndex):
        feature_idx = feature_panel
    else:
        feature_idx = feature_panel.set_index(["stock_id", "date"])

    cal = pd.DatetimeIndex(trading_calendar)

    # ------------------------------------------------------------------
    # Block A — sort (bit-identical to Phase 4)
    # ------------------------------------------------------------------
    sort_cols = (
        ["signal_date", "rank_order", "stock_id"]
        if "rank_order" in ranked.columns
        else ["signal_date", "stock_id"]
    )
    valid = (
        ranked[ranked["valid_path"]]
        .sort_values(sort_cols)
        .reset_index(drop=True)
    )

    if valid.empty:
        raise ValueError(
            "evaluate_candidate_adaptive: no valid_path rows in ranked "
            f"(total={len(ranked)})."
        )

    # ------------------------------------------------------------------
    # Block B — signal_date-driven admission loop
    # Structural copy of Phase 4 schedule_positions admission block.
    # Source: scripts/run_phase4_analysis.py schedule_positions() lines ~386–500.
    # Conservative row-by-row iteration (P0-BLOCK-007) preserves
    # Phase 4 ordering bit-identically. Any future patch to Phase 4
    # admission logic must be mirrored here and WG-1 re-run.
    # open_positions: {stock_id: (release_date, weight)}
    # ------------------------------------------------------------------
    open_positions: dict[str, tuple[pd.Timestamp, float]] = {}
    adaptive_positions: list[AdaptivePosition] = []
    n_skipped_capital = 0
    n_skipped_duplicate = 0

    for sig_date in sorted(valid["signal_date"].unique()):
        sig_ts = pd.Timestamp(sig_date)

        # B1 — release: predicate bit-identical to Phase 4.
        # release_date = canonical exit_date for ceiling / degenerate.
        # release_date = T+1 for policy-trigger exits.
        expired = [
            sid for sid, (rel_dt, _) in open_positions.items()
            if rel_dt <= sig_ts
        ]
        for sid in expired:
            del open_positions[sid]

        # B2 — current exposure
        current_exposure = sum(w for (_, w) in open_positions.values())

        # B3 — candidates in Phase 4 sort order
        for _, row in valid[valid["signal_date"] == sig_ts].iterrows():
            stock = row["stock_id"]

            # Phase 4 order: duplicate → max_pos → exposure
            if stock in open_positions:
                n_skipped_duplicate += 1
                continue
            if len(open_positions) >= max_pos:
                n_skipped_capital += 1
                continue
            if current_exposure + cap > 1.0 + 1e-9:
                n_skipped_capital += 1
                continue

            entry_date_ts = pd.Timestamp(row["entry_date"])

            entry_price = open_map.get((stock, entry_date_ts))
            if entry_price is None or entry_price <= 0:
                log.warning(
                    "evaluate_candidate_adaptive: missing adj_open for "
                    "symbol=%s entry_date=%s; skipping.", stock, entry_date_ts,
                )
                n_skipped_capital += 1
                continue

            try:
                entry_atr = float(feature_idx.loc[(stock, sig_ts), "atr_14"])
            except KeyError:
                if strict_features:
                    raise RuntimeError(
                        f"evaluate_candidate_adaptive: missing atr_14 for "
                        f"symbol={stock!r} signal_date={sig_ts!r} "
                        "(strict_features=True)."
                    )
                log.warning(
                    "evaluate_candidate_adaptive: missing atr_14 for "
                    "symbol=%s signal_date=%s; using 0.0.", stock, sig_ts,
                )
                entry_atr = 0.0

            entry_close = close_map.get((stock, entry_date_ts), entry_price)

            pos_stub = AdaptivePosition(
                symbol=stock,
                signal_date=sig_ts,
                entry_date=entry_date_ts,
                entry_price=entry_price,
                entry_atr=entry_atr,
                weight=cap,
                fwd_return_20td=float(row.get("fwd_return_20td", float("nan"))),
                max_close_since_entry=entry_close,
                days_held=0,
            )

            # On-demand forward simulation (Option II).
            completed = _simulate_position_forward(
                pos=pos_stub,
                trading_calendar=trading_calendar,
                date_to_pos=date_to_pos,
                close_map=close_map,
                feature_idx=feature_idx,
                exit_policy_fn=exit_policy_fn,
                hard_ceiling_h=hard_ceiling_h,
                strict_features=strict_features,
            )

            if completed.release_date is None:
                log.error(
                    "evaluate_candidate_adaptive: None release_date for "
                    "symbol=%s; skipping.", stock,
                )
                n_skipped_capital += 1
                continue

            open_positions[stock] = (completed.release_date, cap)
            current_exposure += cap
            adaptive_positions.append(completed)

    # ------------------------------------------------------------------
    # Block C — P3-FP-002 exposure invariant (retained from Phase 4)
    # ------------------------------------------------------------------
    if adaptive_positions:
        daily_exp: dict[pd.Timestamp, float] = {}
        for pos in adaptive_positions:
            if pos.exit_date is None:
                continue
            ep = date_to_pos.get(pos.entry_date)
            xp = date_to_pos.get(pos.exit_date)
            if ep is None or xp is None:
                continue
            for idx in range(ep, xp + 1):
                if idx >= len(trading_calendar):
                    break
                d = trading_calendar[idx]
                daily_exp[d] = daily_exp.get(d, 0.0) + pos.weight
        max_exp = max(daily_exp.values()) if daily_exp else 0.0
        if max_exp > 1.0 + 1e-6:
            raise RuntimeError(
                f"P3-FP-002 FAIL: max_daily_exposure={max_exp:.4f} > 100%."
            )
    else:
        max_exp = 0.0

    # ------------------------------------------------------------------
    # NAV reconstruction (Phase 4 copy-block, variable holding days)
    # ------------------------------------------------------------------
    nav_df = _reconstruct_nav_adaptive(
        adaptive_positions=adaptive_positions,
        close_map=close_map,
        open_map=open_map,
        cal=cal,
        date_to_pos=date_to_pos,
    )

    # ------------------------------------------------------------------
    # Block E — diagnostics (Phase 4 keys + mean_holding_days)
    # ------------------------------------------------------------------
    n_cand  = len(valid)
    n_sched = len(adaptive_positions)

    holding_days_list = []
    for pos in adaptive_positions:
        if pos.exit_date is not None:
            ep = date_to_pos.get(pos.entry_date)
            xp = date_to_pos.get(pos.exit_date)
            if ep is not None and xp is not None:
                holding_days_list.append(xp - ep + 1)

    mean_holding_days = (
        sum(holding_days_list) / len(holding_days_list)
        if holding_days_list else 0.0
    )

    log.info(
        "P3-FP-002 PASS: max_exposure=%.1f%% | scheduled=%d/%d "
        "skipped_capital=%d skipped_duplicate=%d mean_holding_days=%.1f",
        max_exp * 100, n_sched, n_cand,
        n_skipped_capital, n_skipped_duplicate, mean_holding_days,
    )

    diag = {
        "n_candidates":        n_cand,
        "n_scheduled":         n_sched,
        "n_skipped_capital":   n_skipped_capital,
        "n_skipped_duplicate": n_skipped_duplicate,
        "admission_rate":      round(n_sched / max(n_cand, 1), 4),
        "max_daily_exposure":  round(max_exp, 4),
        "fp002_passed":        True,
        "mean_holding_days":   round(mean_holding_days, 4),
    }
    return adaptive_positions, nav_df, diag
