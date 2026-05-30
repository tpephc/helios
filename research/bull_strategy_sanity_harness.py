#!/usr/bin/env python3
# research/bull_strategy_sanity_harness.py
"""Bull Strategy Sanity Harness — v0.3.0.

Purpose
-------
Determine whether deployed bull strategies are CLEARLY BROKEN — not whether
they have alpha.  This distinction is load-bearing.

Survivorship bias is confirmed (2026-05-30 audit):
    symbols_leaving               = 0 across all years
    current_top200_coverage_2021  = 94.0%
    universe_type                 = current-constituent replay

Consequence: simulation P&L is upward-biased by an unknown amount.
A POSITIVE result cannot distinguish alpha from bias artifact.
A NEGATIVE result with CI upper < 0 is robust to upward bias — the strategy
fails even when the data is stacked in its favour.

Verdict schema
--------------
    FAIL          n >= min_n_for_ci
                  AND mean_net_return < 0
                  AND ci_upper < 0
                  Strategy loses even in a survivorship-biased universe.
                  Actionable: investigate or disable.

    INCONCLUSIVE  Everything else, including:
                  - n < min_n_for_ci (CI unreliable)
                  - mean < 0 but CI upper >= 0
                  - mean > 0 (cannot certify alpha given unknown bias)
                  Forward return tracker is the only path to alpha evidence.

No PASS verdict exists.  This harness can only rule strategies OUT.

Ranking (mirrors strategies/trend_pullback/screener.py exactly)
---------------------------------------------------------------
Sort key matches production:
    (priority_order ASC, dist_above_ma20_atr ASC, -beta_adj_rs_20d DESC)
    where HIGH=0, NORMAL=1.  No synthetic score.

Execution assumptions
---------------------
entry_price = T+1 adj_open * (1 + entry_slippage_bps / 10000)
This is a best-case assumption.  Actual fills subject to gap risk and
collective auction price.  Sensitivity: re-run with entry_slippage_bps=20
to assess verdict stability.

Cost model (40 bps institutional)
    buy brokerage  ~4–5 bps
    sell brokerage ~4–5 bps
    sell tax        30 bps
    ────────────────────────
    total          ~38–40 bps
Retail cost ~58.5 bps (14.25 + 14.25 + 30).

Holding period convention
-------------------------
FIXED_HORIZON: exit at close of the trading_date at index
    (t1_idx + fixed_horizon_days).  With n=20, T+1 entry exits at T+21
    close — 20 complete holding days measured from entry close.

Usage
-----
    uv run python research/bull_strategy_sanity_harness.py \\
        --start 2021-06-18 --oos-start 2025-01-01 --end 2026-05-29

    uv run python research/bull_strategy_sanity_harness.py \\
        --start 2021-06-18 --oos-start 2025-01-01 --end 2026-05-29 \\
        --exit-mode ma20_reclaim --verbose --output-csv /tmp/sanity_trades.csv
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date as Date
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd

from data.database import connect
from utils.logger import get_logger


logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class ExitMode(str, Enum):
    FIXED_HORIZON = "fixed_horizon"
    MA20_RECLAIM  = "ma20_reclaim_exit"


class PriorityOrder(int, Enum):
    HIGH   = 0
    NORMAL = 1


class Verdict(str, Enum):
    FAIL         = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SanityConfig:
    """All harness parameters in one place.

    Mirrors strategies/trend_pullback/config.py for entry conditions.
    Exit rules are research-provisional unless production exit is defined.
    """

    start_date: Date
    oos_start:  Date
    end_date:   Date

    # Entry thresholds
    rs_tercile_min:      float = 0.6667
    beta_tercile_min:    float = 0.3333
    dist_high_threshold: float = -1.0
    dist_entry_max:      float = 0.0
    blocked_regimes: frozenset[str] = frozenset({"bear"})

    # Budget
    max_positions:   int = 10
    min_universe_size: int = 50   # skip screen if active symbols < this

    # Exit
    exit_mode:          ExitMode = ExitMode.FIXED_HORIZON
    fixed_horizon_days: int      = 20

    # Execution: entry at T+1 adj_open is best-case; slippage adjusts upward
    entry_slippage_bps: float = 5.0

    # Cost: buy ~4-5bps + sell ~4-5bps + sell tax 30bps ≈ 40bps (institutional)
    round_trip_cost_bps: float = 40.0

    # Gap filter: T+1 open / signal close - 1 > threshold → skip entry
    # Mirrors production EXPIRED_DRIFT gate.  One-sided: gap UP only.
    # Set to None to disable.  Default 3% is conservative; tighten if
    # production uses a tighter drift gate.
    max_entry_gap_pct: float = 0.03

    # Statistics
    min_n_for_ci: int = 30   # below this, CI is not computed; verdict = INCONCLUSIVE


# ---------------------------------------------------------------------------
# Trade record
# ---------------------------------------------------------------------------

@dataclass
class TradeRecord:
    symbol:          str
    priority:        PriorityOrder
    regime_at_entry: str
    signal_date:     Date
    entry_date:      Date
    exit_date:       Date
    holding_days:    int
    gross_return:    float
    net_return:      float
    mae:             float   # adj_low based; see note in _compute_mae_mfe
    mfe:             float   # adj_high based
    exit_reason:     str
    is_oos:          bool
    # Entry-time features (for post-hoc analysis)
    dist_at_entry:   float
    rs_at_entry:     float
    beta_at_entry:   float


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

class BullSanityHarness:

    def __init__(self, config: SanityConfig) -> None:
        self.cfg             = config
        self._price:         pd.DataFrame = pd.DataFrame()
        self._features:      pd.DataFrame = pd.DataFrame()
        self._sma20:         pd.Series    = pd.Series(dtype=float)
        self._regime:        pd.Series    = pd.Series(dtype=str)
        self._trading_dates: list[pd.Timestamp] = []

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def load_data(self) -> None:
        logger.info("harness_load_start",
                    start=str(self.cfg.start_date), end=str(self.cfg.end_date))
        with connect(read_only=True) as conn:
            universe = self._load_universe(conn)
            if not universe:
                raise RuntimeError(
                    "universe_snapshot returned no symbols with passed=true"
                )
            sym_list = ", ".join(f"'{s}'" for s in universe)
            logger.warning(
                "survivorship_bias_active",
                note=(
                    "Universe is current-constituent (2026-05-20 snapshot only). "
                    "Simulation results are upward-biased; cannot certify alpha."
                ),
                symbols=len(universe),
            )
            self._price    = self._load_price(conn, sym_list)
            self._features = self._load_features(conn, sym_list)
            self._regime   = self._load_regime(conn)
            if self.cfg.exit_mode == ExitMode.MA20_RECLAIM:
                self._sma20 = self._load_sma20(conn, sym_list)

        self._trading_dates = sorted(
            d for d in self._regime.index
            if pd.Timestamp(self.cfg.start_date) <= d <= pd.Timestamp(self.cfg.end_date)
        )
        logger.info("harness_load_done",
                    trading_days=len(self._trading_dates),
                    symbols=self._price.index.get_level_values(0).nunique())

    @staticmethod
    def _load_universe(conn: Any) -> list[str]:
        rows = conn.execute("""
            SELECT stock_id FROM universe_snapshot
            WHERE passed = true ORDER BY stock_id
        """).fetchall()
        return [r[0] for r in rows]

    def _load_price(self, conn: Any, sym_list: str) -> pd.DataFrame:
        df = conn.execute(f"""
            SELECT stock_id AS symbol, date,
                   adj_open, adj_close, adj_high, adj_low
            FROM daily_price_adj
            WHERE stock_id IN ({sym_list})
              AND date BETWEEN '{self.cfg.start_date}' AND '{self.cfg.end_date}'
            ORDER BY stock_id, date
        """).df()
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index(["symbol", "date"]).sort_index()

    def _load_features(self, conn: Any, sym_list: str) -> pd.DataFrame:
        df = conn.execute(f"""
            SELECT stock_id AS symbol, date,
                   beta_adj_rs_20d,
                   dist_above_ma20_atr,
                   beta_60
            FROM bullish_features
            WHERE stock_id IN ({sym_list})
              AND date BETWEEN '{self.cfg.start_date}' AND '{self.cfg.end_date}'
        """).df()
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index(["symbol", "date"]).sort_index()

    def _load_sma20(self, conn: Any, sym_list: str) -> pd.Series:
        """sma_20 from daily_features for MA20_RECLAIM exit mode.

        MA20_RECLAIM exit (close > sma_20) is research-provisional.
        It is not confirmed as the production exit rule for trend_pullback_v1.
        Results using this exit mode should be labelled 'provisional research'.
        """
        df = conn.execute(f"""
            SELECT stock_id AS symbol, date, sma_20
            FROM daily_features
            WHERE stock_id IN ({sym_list})
              AND date BETWEEN '{self.cfg.start_date}' AND '{self.cfg.end_date}'
        """).df()
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index(["symbol", "date"])["sma_20"]

    def _load_regime(self, conn: Any) -> pd.Series:
        df = conn.execute(f"""
            SELECT date, regime FROM market_regime
            WHERE date BETWEEN '{self.cfg.start_date}' AND '{self.cfg.end_date}'
            ORDER BY date
        """).df()
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date")["regime"]

    # ------------------------------------------------------------------
    # Screening — mirrors screener.py sort key exactly
    # ------------------------------------------------------------------

    def _screen_day(
        self, date: pd.Timestamp, regime: str
    ) -> list[tuple[PriorityOrder, float, float, str, float, float]]:
        """Return sorted candidates as (priority, dist, rs, symbol, dist, beta).

        Sorting matches production strategies/trend_pullback/screener.py:
            (priority_order ASC, dist_above_ma20_atr ASC, -beta_adj_rs_20d ASC)

        Returns empty list if:
            - regime is blocked
            - no data available
            - active symbols < min_universe_size (rank unstable on thin days)
        """
        if regime in self.cfg.blocked_regimes:
            return []

        try:
            day = self._features.xs(date, level="date").copy()
        except KeyError:
            return []
        if len(day) < self.cfg.min_universe_size:
            return []

        day["rs_pctile"]   = day["beta_adj_rs_20d"].rank(pct=True)
        day["beta_pctile"] = day["beta_60"].rank(pct=True)

        mask = (
            (day["rs_pctile"]            >= self.cfg.rs_tercile_min)
            & (day["dist_above_ma20_atr"] <  self.cfg.dist_entry_max)
            & (day["beta_pctile"]         >= self.cfg.beta_tercile_min)
        )
        filtered = day[mask]
        if filtered.empty:
            return []

        candidates = []
        for symbol, row in filtered.iterrows():
            dist  = float(row["dist_above_ma20_atr"])
            rs    = float(row["beta_adj_rs_20d"])
            beta  = float(row["beta_60"])
            priority = (
                PriorityOrder.HIGH
                if dist < self.cfg.dist_high_threshold
                else PriorityOrder.NORMAL
            )
            candidates.append((priority, dist, rs, str(symbol), dist, beta))

        candidates.sort(key=lambda c: (c[0].value, c[1], -c[2]))
        return candidates

    # ------------------------------------------------------------------
    # Exit
    # ------------------------------------------------------------------

    def _find_exit(
        self,
        symbol:       str,
        t1_date:      pd.Timestamp,
        future_dates: list[pd.Timestamp],
    ) -> tuple[pd.Timestamp, float, str]:
        """Return (exit_date, raw_exit_price, reason).

        FIXED_HORIZON: exit at close of self._trading_dates[t1_idx + n].
            This is the Nth trading day after entry, giving n complete
            holding-day closes.  Avoids off-by-one from future_dates slicing.

        MA20_RECLAIM: exit on first close > sma_20 after entry.
            Semantics for pullback strategy: entry is below MA20;
            exit when price reclaims MA20 (close > sma_20 = profit-taking).
            This is NOT a stop-loss; a stop-loss would be close < sma_20.
            Name chosen to make direction explicit: reclaim = moving back above.
            This rule is research-provisional (not confirmed production exit).
        """
        try:
            sym_price = self._price.xs(symbol, level="symbol")
        except KeyError:
            return t1_date, np.nan, "no_price_data"

        if self.cfg.exit_mode == ExitMode.FIXED_HORIZON:
            try:
                t1_idx = self._trading_dates.index(t1_date)
            except ValueError:
                return t1_date, np.nan, "t1_not_in_calendar"
            target_idx = min(
                t1_idx + self.cfg.fixed_horizon_days,
                len(self._trading_dates) - 1,
            )
            exit_date = self._trading_dates[target_idx]
            raw = (
                float(sym_price.loc[exit_date, "adj_close"])
                if exit_date in sym_price.index
                else np.nan
            )
            return exit_date, raw, "fixed_horizon"

        # MA20_RECLAIM: exit when close reclaims MA20 upward
        try:
            sym_sma = self._sma20.xs(symbol, level="symbol")
        except KeyError:
            sym_sma = pd.Series(dtype=float)

        for d in future_dates:
            if d not in sym_price.index:
                continue
            close = float(sym_price.loc[d, "adj_close"])
            sma   = float(sym_sma.loc[d]) if d in sym_sma.index else np.nan
            if not np.isnan(sma) and close > sma:
                return d, close, "ma20_reclaim_exit"

        exit_date = future_dates[-1] if future_dates else t1_date
        raw = (
            float(sym_price.loc[exit_date, "adj_close"])
            if exit_date in sym_price.index
            else np.nan
        )
        return exit_date, raw, "end_of_window"

    def _compute_mae_mfe(
        self,
        symbol:     str,
        raw_entry:  float,
        entry_date: pd.Timestamp,
        exit_date:  pd.Timestamp,
    ) -> tuple[float, float]:
        """MAE and MFE over the holding window using adj_low / adj_high.

        Assumption: raw_entry is T+1 adj_open (entry_slippage already applied
        to the trade record; MAE/MFE use the slippage-adjusted price as
        the basis so excursion is measured from actual cost).
        Corporate action events can produce misleading adj_low/adj_high on
        ex-dividend or ex-rights dates; treat individual extreme values as
        outliers, not confirmed excursions.
        """
        try:
            sym_price = self._price.xs(symbol, level="symbol")
        except KeyError:
            return np.nan, np.nan
        window = sym_price.loc[
            (sym_price.index > entry_date) & (sym_price.index <= exit_date)
        ]
        if window.empty or raw_entry == 0:
            return np.nan, np.nan
        mae = float(window["adj_low"].min()  / raw_entry - 1)
        mfe = float(window["adj_high"].max() / raw_entry - 1)
        return mae, mfe

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------

    def run(self) -> list[TradeRecord]:
        if not self._trading_dates:
            raise RuntimeError("No trading dates.  Call load_data() first.")

        trades: list[TradeRecord] = []
        open_positions: dict[str, dict] = {}

        for i, date in enumerate(self._trading_dates):
            regime = str(self._regime.get(date, "neutral"))

            # 1. Close positions reaching exit date
            to_close = [s for s, p in open_positions.items()
                        if p["exit_date"] <= date]
            for sym in to_close:
                pos = open_positions.pop(sym)
                hold = sum(
                    1 for d in self._trading_dates
                    if pos["entry_date"] < d <= pos["exit_date"]
                )
                raw_exit = pos["raw_exit"]
                cost     = self.cfg.round_trip_cost_bps / 10000
                gross    = (
                    raw_exit / pos["raw_entry_adj"] - 1
                    if not np.isnan(raw_exit) else np.nan
                )
                net = (gross - cost) if not np.isnan(gross) else np.nan
                mae, mfe = self._compute_mae_mfe(
                    sym, pos["raw_entry_adj"],
                    pos["entry_date"], pos["exit_date"],
                )
                trades.append(TradeRecord(
                    symbol=sym,
                    priority=pos["priority"],
                    regime_at_entry=pos["regime"],
                    signal_date=pos["signal_date"].date(),
                    entry_date=pos["entry_date"].date(),
                    exit_date=pos["exit_date"].date(),
                    holding_days=hold,
                    gross_return=float(gross) if not np.isnan(gross) else np.nan,
                    net_return=float(net)     if not np.isnan(net)   else np.nan,
                    mae=float(mae)            if not np.isnan(mae)   else np.nan,
                    mfe=float(mfe)            if not np.isnan(mfe)   else np.nan,
                    exit_reason=pos["exit_reason"],
                    is_oos=pos["signal_date"] >= pd.Timestamp(self.cfg.oos_start),
                    dist_at_entry=pos["dist"],
                    rs_at_entry=pos["rs"],
                    beta_at_entry=pos["beta"],
                ))

            # 2. New entries
            slots = self.cfg.max_positions - len(open_positions)
            if slots <= 0:
                continue
            future = self._trading_dates[i + 1:]
            if not future:
                continue
            t1_date = future[0]

            open_syms  = set(open_positions.keys())
            candidates = self._screen_day(date, regime)

            filled = 0
            for priority, dist, rs, symbol, dist_val, beta_val in candidates:
                if filled >= slots:
                    break
                if symbol in open_syms:
                    continue
                try:
                    raw_open = float(
                        self._price.loc[(symbol, t1_date), "adj_open"]
                    )
                except KeyError:
                    continue

                # Gap filter: skip if T+1 open gaps up too far from signal close.
                # Mirrors production EXPIRED_DRIFT; one-sided (gap up = bad for longs).
                if self.cfg.max_entry_gap_pct is not None:
                    try:
                        signal_close = float(
                            self._price.loc[(symbol, date), "adj_close"]
                        )
                        gap = raw_open / signal_close - 1
                        if gap > self.cfg.max_entry_gap_pct:
                            logger.debug("gap_filter_skip",
                                         symbol=symbol,
                                         gap=round(gap, 4),
                                         max_gap=self.cfg.max_entry_gap_pct)
                            continue
                    except KeyError:
                        pass  # no signal close available; proceed without filter

                # Apply entry slippage (best-case adj_open + slippage bps)
                slippage_factor = 1.0 + self.cfg.entry_slippage_bps / 10000
                raw_entry_adj   = raw_open * slippage_factor

                dates_after_t1  = [d for d in self._trading_dates if d > t1_date]
                exit_date, raw_exit, reason = self._find_exit(
                    symbol, t1_date, dates_after_t1
                )
                open_positions[symbol] = dict(
                    entry_date=t1_date,
                    raw_entry_adj=raw_entry_adj,
                    exit_date=exit_date,
                    raw_exit=raw_exit,
                    exit_reason=reason,
                    priority=priority,
                    regime=regime,
                    signal_date=date,
                    dist=dist_val,
                    rs=rs,
                    beta=beta_val,
                )
                open_syms.add(symbol)
                filled += 1

        # 3. Force-close remaining positions at end of window
        last_date = self._trading_dates[-1]
        for sym, pos in open_positions.items():
            try:
                raw_exit = float(self._price.loc[(sym, last_date), "adj_close"])
            except KeyError:
                raw_exit = np.nan
            hold  = sum(
                1 for d in self._trading_dates
                if pos["entry_date"] < d <= last_date
            )
            cost  = self.cfg.round_trip_cost_bps / 10000
            gross = (
                raw_exit / pos["raw_entry_adj"] - 1
                if not np.isnan(raw_exit) else np.nan
            )
            net = (gross - cost) if not np.isnan(gross) else np.nan
            mae, mfe = self._compute_mae_mfe(
                sym, pos["raw_entry_adj"], pos["entry_date"], last_date
            )
            trades.append(TradeRecord(
                symbol=sym,
                priority=pos["priority"],
                regime_at_entry=pos["regime"],
                signal_date=pos["signal_date"].date(),
                entry_date=pos["entry_date"].date(),
                exit_date=last_date.date(),
                holding_days=hold,
                gross_return=float(gross) if not np.isnan(gross) else np.nan,
                net_return=float(net)     if not np.isnan(net)   else np.nan,
                mae=float(mae)            if not np.isnan(mae)   else np.nan,
                mfe=float(mfe)            if not np.isnan(mfe)   else np.nan,
                exit_reason="end_of_window",
                is_oos=pos["signal_date"] >= pd.Timestamp(self.cfg.oos_start),
                dist_at_entry=pos["dist"],
                rs_at_entry=pos["rs"],
                beta_at_entry=pos["beta"],
            ))

        logger.info("simulation_done",
                    total=len(trades),
                    oos=sum(1 for t in trades if t.is_oos))
        return trades

    # ------------------------------------------------------------------
    # Verdict
    # ------------------------------------------------------------------

    def _ci_upper(self, rets: pd.Series) -> float:
        """95% CI upper bound on mean return (t-distribution).

        Returns nan when:
            n < min_n_for_ci  (unreliable on fat-tailed financial returns)
            std < 1e-12       (degenerate; avoids float-equality pitfall)
            scipy unavailable
        """
        n = len(rets)
        if n < self.cfg.min_n_for_ci:
            return float("nan")
        std = float(rets.std(ddof=1))
        if std < 1e-12 or not np.isfinite(std):
            return float("nan")
        try:
            from scipy import stats as sp
            _, hi = sp.t.interval(
                0.95, df=n - 1,
                loc=float(rets.mean()),
                scale=std / np.sqrt(n),
            )
            return float(hi)
        except ImportError:
            return float("nan")

    def _verdict(
        self,
        rets:      pd.Series,
        by_regime: dict[str, pd.Series],
        label:     str,
    ) -> dict:
        """Compute verdict for a trade subset.

        FAIL requires n >= min_n_for_ci to prevent false positives on
        small samples where CI is unreliable.
        """
        if rets.empty:
            return {"label": label, "verdict": Verdict.INCONCLUSIVE,
                    "n": 0, "note": "no data"}

        n      = len(rets)
        mean_r = float(rets.mean())
        ci_up  = self._ci_upper(rets)
        hit    = float((rets > 0).mean())
        tail   = float(rets.quantile(0.05))

        # FAIL requires sufficient n and CI upper clearly negative
        if (
            n >= self.cfg.min_n_for_ci
            and mean_r < 0
            and not np.isnan(ci_up)
            and ci_up < 0
        ):
            verdict = Verdict.FAIL
        else:
            verdict = Verdict.INCONCLUSIVE

        note = ""
        if n < self.cfg.min_n_for_ci:
            note = f"n={n} < {self.cfg.min_n_for_ci}: CI not computed; FAIL not possible"

        regime_dirs = {
            reg: float(r.mean())
            for reg, r in by_regime.items()
            if len(r) >= 5
        }
        signs = [1 if v > 0 else -1 for v in regime_dirs.values()]
        regime_inconsistent = len(set(signs)) > 1 if len(signs) >= 2 else False

        return {
            "label":               label,
            "verdict":             verdict,
            "n":                   n,
            "note":                note,
            "mean_net_return":     round(mean_r, 4),
            "ci_upper_95":         round(ci_up, 4) if not np.isnan(ci_up) else None,
            "hit_rate":            round(hit, 4),
            "tail_loss_5pct":      round(tail, 4),
            "regime_inconsistent": regime_inconsistent,
            "regime_means":        {k: round(v, 4) for k, v in regime_dirs.items()},
            "small_n":             n < self.cfg.min_n_for_ci,
            "high_bias_caveat":    True,
        }

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def report(self, trades: list[TradeRecord], verbose: bool = False) -> None:
        oos = [t for t in trades if t.is_oos]

        print()
        print("=" * 72)
        print("BULL STRATEGY SANITY HARNESS  v0.3.0")
        print("=" * 72)
        print()
        print("  *** BIAS CAVEAT — READ BEFORE INTERPRETING ***")
        print("  Universe : current-constituent replay (2026-05-20 snapshot)")
        print("  symbols_leaving = 0 across all years; coverage_2021 = 94.0%")
        print("  Upward bias confirmed.  Magnitude unknown.")
        print("  INCONCLUSIVE ≠ alpha is present.")
        print("  FAIL is the only actionable verdict from this harness.")
        print("  Alpha evidence requires forward_return_tracker.py (n>=150).")
        print()
        print(f"  OOS window        : {self.cfg.oos_start} → {self.cfg.end_date}")
        mode_str = (
            f"{self.cfg.exit_mode.value} ({self.cfg.fixed_horizon_days}d)"
            if self.cfg.exit_mode == ExitMode.FIXED_HORIZON
            else f"{self.cfg.exit_mode.value} [provisional research]"
        )
        print(f"  Exit mode         : {mode_str}")
        print(f"  Entry slippage    : {self.cfg.entry_slippage_bps:.0f} bps "
              "(best-case; re-run with 20bps for sensitivity)")
        print(f"  Round-trip cost   : {self.cfg.round_trip_cost_bps:.0f} bps "
              "(institutional; retail ~58bps)")
        print(f"  Max positions     : {self.cfg.max_positions}")
        print(f"  OOS trades total  : {len(oos)}")

        if not oos:
            print("\n  No OOS trades.  Widen date range or check data.")
            return

        oos_df = pd.DataFrame([vars(t) for t in oos]).dropna(subset=["net_return"])
        if oos_df.empty:
            print("\n  All OOS trades have NaN net_return.  Check price data.")
            return

        def _by_regime(df: pd.DataFrame) -> dict[str, pd.Series]:
            return {
                reg: df[df["regime_at_entry"] == reg]["net_return"]
                for reg in ["bull", "neutral", "bear"]
                if (df["regime_at_entry"] == reg).any()
            }

        print()
        print("─" * 72)

        for block_label, sub_df in [
            ("ALL OOS", oos_df),
            *[
                (f"priority={p.name}", oos_df[oos_df["priority"] == p])
                for p in [PriorityOrder.HIGH, PriorityOrder.NORMAL]
                if (oos_df["priority"] == p).any()
            ],
            *[
                (f"regime={r}", oos_df[oos_df["regime_at_entry"] == r])
                for r in ["bull", "neutral", "crisis"]
                if (oos_df["regime_at_entry"] == r).any()
            ],
        ]:
            v = self._verdict(
                sub_df["net_return"], _by_regime(sub_df), block_label
            )
            self._print_verdict_block(v)

        # IS reference: hidden by default (can mislead anchoring to IS performance)
        if verbose:
            is_df = pd.DataFrame(
                [vars(t) for t in trades if not t.is_oos]
            ).dropna(subset=["net_return"])
            if not is_df.empty:
                print()
                print("  IS REFERENCE (--verbose; do NOT use for decisions):")
                print(f"    n={len(is_df)}"
                      f"  mean={is_df['net_return'].mean():+.2%}"
                      f"  hit={(is_df['net_return'] > 0).mean():.1%}")

    @staticmethod
    def _print_verdict_block(v: dict) -> None:
        verdict: Verdict = v["verdict"]
        flag = "🔴 FAIL" if verdict == Verdict.FAIL else "⚪ INCONCLUSIVE"
        print(f"\n  [{flag}]  {v['label']}  (n={v['n']})")
        if v.get("note"):
            print(f"    note              : {v['note']}")
        print(f"    mean net return   : {v['mean_net_return']:>+.2%}")
        ci_str = (
            f"{v['ci_upper_95']:>+.2%}" if v["ci_upper_95"] is not None
            else "n/a (n < min_n_for_ci)"
        )
        print(f"    CI upper (95%)    : {ci_str}")
        print(f"    hit rate          : {v['hit_rate']:.1%}")
        print(f"    tail loss (5pct)  : {v['tail_loss_5pct']:>+.2%}")
        if v.get("regime_inconsistent"):
            means = "  ".join(
                f"{k}: {val:+.2%}" for k, val in v["regime_means"].items()
            )
            print(f"    ⚠ regime_inconsistent: {means}")
        if v.get("small_n"):
            print(f"    ⚠ small_n: FAIL not possible until n >= 30")

    def to_csv(self, trades: list[TradeRecord], path: str) -> None:
        pd.DataFrame([vars(t) for t in trades]).to_csv(path, index=False)
        logger.info("trade_log_written", path=path, n=len(trades))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Bull strategy sanity harness.  "
            "FAIL=actionable; INCONCLUSIVE=expected (cannot certify alpha)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--start",          required=True, type=Date.fromisoformat)
    p.add_argument("--oos-start",      required=True, type=Date.fromisoformat)
    p.add_argument("--end",            required=True, type=Date.fromisoformat)
    p.add_argument("--exit-mode",      default="fixed_horizon",
                   choices=["fixed_horizon", "ma20_reclaim"])
    p.add_argument("--horizon",        type=int,   default=20)
    p.add_argument("--max-positions",  type=int,   default=10)
    p.add_argument("--entry-slippage", type=float, default=5.0,
                   help="Entry slippage in bps (default 5; use 20 for sensitivity).")
    p.add_argument("--max-entry-gap",   type=float, default=0.03,
                   help="Max T+1 gap-up vs signal close (0.03=3%%; 0 to disable).")
    p.add_argument("--cost-bps",       type=float, default=40.0)
    p.add_argument("--verbose",        action="store_true",
                   help="Show IS reference block (use with caution).")
    p.add_argument("--output-csv",     default=None)
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    cfg = SanityConfig(
        start_date=args.start,
        oos_start=args.oos_start,
        end_date=args.end,
        exit_mode=(ExitMode.MA20_RECLAIM if args.exit_mode == "ma20_reclaim" else ExitMode(args.exit_mode)),
        fixed_horizon_days=args.horizon,
        max_positions=args.max_positions,
        entry_slippage_bps=args.entry_slippage,
        max_entry_gap_pct=args.max_entry_gap,
        round_trip_cost_bps=args.cost_bps,
    )
    harness = BullSanityHarness(cfg)
    harness.load_data()
    trades = harness.run()
    harness.report(trades, verbose=args.verbose)
    if args.output_csv:
        harness.to_csv(trades, args.output_csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
