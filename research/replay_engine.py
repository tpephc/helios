#!/usr/bin/env python3
# research/replay_engine.py
"""Minimal Historical Replay Engine — v0.2.3.

Approximate locked-policy replay of the pullback strategy over the
historical panel (~2021-10 to 2026-05).

v0.2.3 changes:
  - CA quarantine uses per-STOCK next-trading-date (ca_pre_gap_days),
    not global market next_date.  Fixes halted-stock gap miss (6919:
    halted 5 days, gap on resumption was invisible to global next_date).
  - Hard DQ assertion: |gross_return| > 50% must be quarantined.
  - Entry screen also blocks stocks on their pre-gap day.

v0.2.2 changes:
  - Regime lagged by 1 day: regime[T] is computed on T+1 (confirmed:
    1220/1221 rows have computed_at > date).  Replay now uses regime[T-1]
    for both entry screening and exit checks, matching production
    run_exit_scan which can only see yesterday's regime at EOD.

v0.2.1 changes:
  - Corporate-action gap quarantine: pre-scans for |adj_close change| > 50%
    between consecutive trading days.  Positions held into a CA gap day are
    force-closed at the prior day's close with exit_reason =
    "corporate_action_quarantine".  This is a DATA-QUALITY guardrail, not a
    tradable signal — it removes rows where adjusted-price continuity is
    known to be broken.
  - Disaster stop: hard -25% drawdown cap as LAST-RESORT risk guard
    (exit_reason = "disaster_stop").  Separate from CA quarantine.
  - Exit reason taxonomy: corporate_action_quarantine / disaster_stop /
    regime_exit / trailing_stop / time_stop / end_of_panel.

Fill: T+1 adj_open for both entry and exit (symmetric, conservative).
Sizing: max_slots (concurrency) × position_pct (per-trade %) — independent.

KNOWN LIMITATIONS:
  - Approximate replay (screening omits some production gates).
  - CA gap exclusion uses full-panel hindsight (data-quality guardrail,
    acceptable for DQ quarantine; NOT a tradable signal).
  - Single-regime in-sample only (no OOS).
  - Current-constituent survivorship bias.
  - corporate_actions table is empty; cum_factor not adjusted for any
    splits/reductions.  DQ-CA-001 backlog ticket required.
  - Results are NOT final until corporate-action sensitivity audit on
    R1/R2/R5/Study B confirms prior conclusions are unaffected.

Standalone, read-only. No DB writes.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date as date_type

import numpy as np
import pandas as pd

DB_PATH = "data/_storage/helios.duckdb"
RS_T3_Q = 2 / 3
BETA_MIN_Q = 1 / 3
WARM_UP_DAYS = 25
CA_GAP_THRESHOLD = 0.50   # |return| > 50% = corporate action
DISASTER_STOP_PCT = -0.25  # -25% hard cap


@dataclass
class ReplayConfig:
    max_slots: int = 5
    position_pct: float = 0.20
    capital: float = 10_000_000.0
    cost_bps: float = 30.0
    atr_mult: float = 2.0
    time_stop_days: int = 20
    dist_high_threshold: float = -1.0
    label: str = "baseline"

    @property
    def position_notional(self) -> float:
        return self.capital * self.position_pct

    @property
    def cost_frac(self) -> float:
        return self.cost_bps / 10_000


@dataclass
class SimTrade:
    stock_id: str
    entry_date: date_type
    entry_price: float
    entry_atr: float
    regime_at_signal: str
    rs_pctile: float
    dist: float
    vol_contraction: float
    notional: float
    max_close: float = 0.0
    min_close: float = 0.0
    holding_days: int = 0
    exit_date: date_type | None = None
    exit_price: float | None = None
    exit_reason: str | None = None
    regime_at_exit: str | None = None

    def __post_init__(self) -> None:
        if self.max_close == 0.0:
            self.max_close = self.entry_price
        if self.min_close == 0.0:
            self.min_close = self.entry_price

    @property
    def gross_return_pct(self) -> float:
        if self.exit_price is None: return 0.0
        return (self.exit_price / self.entry_price - 1.0) * 100.0

    @property
    def mfe_pct(self) -> float:
        return (self.max_close / self.entry_price - 1.0) * 100.0

    @property
    def mae_pct(self) -> float:
        return (self.min_close / self.entry_price - 1.0) * 100.0


# ── data loading ───────────────────────────────────────────────────────

def load_data() -> tuple[pd.DataFrame, dict]:
    import duckdb
    con = duckdb.connect(DB_PATH, read_only=True)
    df_schema = con.execute("PRAGMA table_info('daily_features')").fetchdf()
    atr_candidates = [c for c in df_schema["name"] if "atr" in c.lower()]
    atr_col = "atr_14" if "atr_14" in atr_candidates else (
        atr_candidates[0] if atr_candidates else None)
    if not atr_col:
        print("❌  No ATR column."); sys.exit(1)
    bf_schema = con.execute("PRAGMA table_info('bullish_features')").fetchdf()
    has_vc = "volume_contraction_days_10d" in set(bf_schema["name"])
    vc_sql = ", b.volume_contraction_days_10d" if has_vc else ", 0 AS volume_contraction_days_10d"
    sql = f"""
    SELECT b.date, b.stock_id, b.beta_adj_rs_20d, b.dist_above_ma20_atr,
           b.beta_60, d.adj_close, d.adj_open, f.{atr_col} AS atr_14 {vc_sql}
    FROM bullish_features b
    JOIN daily_price_adj d ON b.stock_id = d.stock_id AND b.date = d.date
    JOIN daily_features f ON b.stock_id = f.stock_id AND b.date = f.date
    WHERE b.beta_adj_rs_20d IS NOT NULL AND b.dist_above_ma20_atr IS NOT NULL
      AND b.beta_60 IS NOT NULL AND d.adj_close > 0 AND d.adj_open > 0
      AND f.{atr_col} IS NOT NULL
    ORDER BY b.date, b.stock_id
    """
    panel = con.execute(sql).fetchdf()
    regime_df = con.execute("SELECT date, regime FROM market_regime ORDER BY date").fetchdf()
    regime_map = dict(zip(regime_df["date"], regime_df["regime"]))
    con.close()
    return panel, regime_map


def assign_rs_and_beta(panel: pd.DataFrame) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for _, g in panel.groupby("date"):
        g = g.copy()
        rs = g["beta_adj_rs_20d"].values
        n = len(rs)
        g["rs_pctile"] = np.array([(rs <= v).sum() / n for v in rs])
        g["rs_t3"] = rs >= float(np.quantile(rs, RS_T3_Q))
        beta = g["beta_60"].values
        g["beta_t2_plus"] = beta >= float(np.quantile(beta, BETA_MIN_Q))
        parts.append(g)
    return pd.concat(parts, ignore_index=True)


def build_ca_gap_days(panel: pd.DataFrame) -> tuple[
    set[tuple[str, object]], set[tuple[str, object]]
]:
    """Pre-scan for corporate-action price discontinuities.

    Returns:
        ca_gap_days:     (stock_id, gap_date) where |Δ adj_close| > threshold.
        ca_pre_gap_days: (stock_id, last_trading_date_before_gap) — the date
                         to force-close on.  Uses per-STOCK trading dates, not
                         global market dates, so halted stocks are handled
                         correctly.
    """
    ca_gap_days: set[tuple[str, object]] = set()
    ca_pre_gap_days: set[tuple[str, object]] = set()
    for stock_id, g in panel.groupby("stock_id"):
        g = g.sort_values("date")
        closes = g["adj_close"].values
        dates = g["date"].values
        for i in range(1, len(closes)):
            if closes[i - 1] > 0 and abs(closes[i] / closes[i - 1] - 1) > CA_GAP_THRESHOLD:
                ca_gap_days.add((stock_id, dates[i]))
                ca_pre_gap_days.add((stock_id, dates[i - 1]))
    return ca_gap_days, ca_pre_gap_days


# ── exit rules ─────────────────────────────────────────────────────────

def check_exits(trade: SimTrade, close: float, regime: str,
                cfg: ReplayConfig) -> str | None:
    # P0: disaster stop (hard drawdown cap, last-resort risk guard)
    if trade.entry_price > 0:
        drawdown = close / trade.entry_price - 1.0
        if drawdown <= DISASTER_STOP_PCT:
            return "disaster_stop"
    # P1: regime exit
    if regime == "bear":
        return "regime_exit"
    # P2: trailing stop
    if trade.entry_atr > 0:
        stop = trade.max_close - cfg.atr_mult * trade.entry_atr
        if close <= stop:
            return f"trailing_stop (stop={stop:.2f})"
    # P3: time stop
    if trade.holding_days >= cfg.time_stop_days:
        return f"time_stop ({trade.holding_days}d)"
    return None


def screen_candidates(day_df: pd.DataFrame, regime: str,
                      held: set[str], cfg: ReplayConfig) -> pd.DataFrame:
    if regime == "bear":
        return day_df.iloc[0:0]
    mask = (day_df["rs_t3"] & day_df["beta_t2_plus"]
            & (day_df["dist_above_ma20_atr"] < 0)
            & (~day_df["stock_id"].isin(held)))
    cands = day_df[mask].copy()
    if cands.empty:
        return cands
    cands["priority"] = np.where(
        cands["dist_above_ma20_atr"] < cfg.dist_high_threshold, 0, 1)
    return cands.sort_values(
        ["priority", "dist_above_ma20_atr", "rs_pctile"],
        ascending=[True, True, False])


# ── simulation ─────────────────────────────────────────────────────────

def run_replay(panel: pd.DataFrame, regime_map: dict,
               ca_gap_days: set[tuple[str, object]],
               ca_pre_gap_days: set[tuple[str, object]],
               cfg: ReplayConfig) -> tuple[list[SimTrade], pd.DataFrame]:
    dates = sorted(panel["date"].unique())
    date_to_ord = {d: i for i, d in enumerate(dates)}
    by_date = {d: g for d, g in panel.groupby("date")}

    open_lookup: dict[tuple[str, object], float] = {}
    close_lookup: dict[tuple[str, object], float] = {}
    for _, row in panel.iterrows():
        key = (row["stock_id"], row["date"])
        open_lookup[key] = row["adj_open"]
        close_lookup[key] = row["adj_close"]

    open_trades: list[SimTrade] = []
    closed_trades: list[SimTrade] = []
    pending_exits: list[tuple[SimTrade, str]] = []
    pending_entries: list[dict] = []
    equity_records: list[dict] = []
    n_dates = len(dates)

    for day_idx in range(WARM_UP_DAYS, n_dates):
        d = dates[day_idx]
        # Regime lagged by 1 day: regime[T] is computed on T+1, so at EOD T
        # only regime[T-1] is available.  Matches production run_exit_scan.
        prev_date = dates[day_idx - 1]
        regime = regime_map.get(prev_date, "unknown")

        # ── 1. FILL pending exits at today's open ──
        for trade, reason in pending_exits:
            fill = open_lookup.get((trade.stock_id, d))
            if fill and fill > 0:
                trade.exit_date = d
                trade.exit_price = fill
            else:
                trade.exit_date = d
                trade.exit_price = trade.max_close
                reason += " (no_open_fallback)"
            trade.exit_reason = reason
            trade.regime_at_exit = regime
            closed_trades.append(trade)
            open_trades = [t for t in open_trades if t is not trade]
        pending_exits = []

        # ── 2. FILL pending entries at today's open ──
        for cand in pending_entries:
            if len(open_trades) >= cfg.max_slots:
                break
            fill = open_lookup.get((cand["stock_id"], d))
            if fill and fill > 0:
                open_trades.append(SimTrade(
                    stock_id=cand["stock_id"], entry_date=d,
                    entry_price=fill, entry_atr=cand["atr"],
                    regime_at_signal=cand["regime_at_signal"],
                    rs_pctile=cand["rs_pctile"], dist=cand["dist"],
                    vol_contraction=cand["vol_contraction"],
                    notional=cfg.position_notional))
        pending_entries = []

        day_df = by_date.get(d)
        if day_df is None:
            continue

        # ── 3. UPDATE running stats ──
        for trade in open_trades:
            close = close_lookup.get((trade.stock_id, d))
            if close is None:
                continue
            trade.holding_days += 1
            if close > trade.max_close:
                trade.max_close = close
            if close < trade.min_close:
                trade.min_close = close

        # ── 4a. CA QUARANTINE: force close if today is the last trading
        #    day before a CA gap for this stock.  Uses per-STOCK dates
        #    (not global market next_date) so halted stocks are caught. ──
        ca_quarantined: set[int] = set()
        for trade in open_trades:
            if (trade.stock_id, d) in ca_pre_gap_days:
                close = close_lookup.get((trade.stock_id, d))
                if close:
                    trade.exit_date = d
                    trade.exit_price = close
                    trade.exit_reason = "corporate_action_quarantine"
                    trade.regime_at_exit = regime
                    closed_trades.append(trade)
                    ca_quarantined.add(id(trade))
        if ca_quarantined:
            open_trades = [t for t in open_trades if id(t) not in ca_quarantined]

        # ── 4b. EXIT CHECK (non-quarantined) → pending T+1 ──
        exit_ids: set[int] = set()
        for trade in open_trades:
            close = close_lookup.get((trade.stock_id, d))
            if close is None:
                continue
            reason = check_exits(trade, close, regime, cfg)
            if reason:
                pending_exits.append((trade, reason))
                exit_ids.add(id(trade))

        # ── 5. ENTRY SCREEN → pending T+1 ──
        n_freeing = len(pending_exits)
        effective_open = len(open_trades) - n_freeing
        slots = max(0, cfg.max_slots - effective_open)
        if slots > 0 and day_idx + 1 < n_dates:
            held = {t.stock_id for t in open_trades}
            cands = screen_candidates(day_df, regime, held, cfg)
            for _, row in cands.head(slots).iterrows():
                sid = row["stock_id"]
                # Don't enter if today is a pre-gap day for this stock,
                # or if the fill date (T+1) is a CA gap day.
                next_date = dates[day_idx + 1] if day_idx + 1 < n_dates else None
                if (sid, d) in ca_pre_gap_days:
                    continue
                if next_date and (sid, next_date) in ca_gap_days:
                    continue
                pending_entries.append({
                    "stock_id": row["stock_id"], "atr": row["atr_14"],
                    "regime_at_signal": regime,
                    "rs_pctile": row["rs_pctile"],
                    "dist": row["dist_above_ma20_atr"],
                    "vol_contraction": row.get("volume_contraction_days_10d", 0) or 0,
                })

        # ── 6. EQUITY / EXPOSURE ──
        unrealized = 0.0
        gross_notional = 0.0
        for trade in open_trades:
            close = close_lookup.get((trade.stock_id, d))
            if close:
                unrealized += trade.notional * (close / trade.entry_price - 1.0)
                gross_notional += trade.notional
        cum_realized = sum(
            t.notional * (t.exit_price / t.entry_price - 1.0) - t.notional * cfg.cost_frac
            for t in closed_trades)
        equity_records.append({
            "date": d,
            "equity": cfg.capital + cum_realized + unrealized,
            "n_open": len(open_trades),
            "gross_exposure": gross_notional / cfg.capital,
            "regime": regime,
        })

    # force-close remaining
    if open_trades:
        last = dates[-1]
        for trade in open_trades:
            close = close_lookup.get((trade.stock_id, last))
            if close:
                trade.exit_date = last; trade.exit_price = close
                trade.exit_reason = "end_of_panel"
                trade.regime_at_exit = regime_map.get(last, "unknown")
                closed_trades.append(trade)

    return closed_trades, pd.DataFrame(equity_records)


# ── summary ────────────────────────────────────────────────────────────

def print_summary(trades: list[SimTrade], eq_df: pd.DataFrame,
                  cfg: ReplayConfig, ca_count: int = 0) -> None:
    n = len(trades)
    if n == 0:
        print("    No trades."); return
    rets_g = np.array([t.gross_return_pct for t in trades])
    rets_n = rets_g - cfg.cost_bps / 100
    winners = rets_n > 0
    holding = np.array([t.holding_days for t in trades])
    maes = np.array([t.mae_pct for t in trades])
    mfes = np.array([t.mfe_pct for t in trades])
    reasons = [t.exit_reason.split(" ")[0] if t.exit_reason else "unknown"
               for t in trades]

    print(f"\n{'=' * 78}")
    print(f"📊  A — Trade Distribution [{cfg.label}]")
    print(f"{'=' * 78}")
    print(f"    n={n}  win={int(winners.sum())}  lose={n - int(winners.sum())}  "
          f"win_rate={winners.mean():.1%}")
    print(f"    gross: mean={rets_g.mean():+.2f}%  med={np.median(rets_g):+.2f}%")
    print(f"    net:   mean={rets_n.mean():+.2f}%  med={np.median(rets_n):+.2f}%")
    print(f"    hold:  mean={holding.mean():.1f}d  med={np.median(holding):.0f}d  "
          f"max={holding.max()}d")
    rc: dict[str, int] = {}
    for r in reasons: rc[r] = rc.get(r, 0) + 1
    print(f"    exits:")
    for r, c in sorted(rc.items(), key=lambda x: -x[1]):
        print(f"      {r:<30s} {c:>4d} ({c/n:.1%})")
    if ca_count:
        print(f"    CA gap days quarantined: {ca_count}")

    print(f"\n{'=' * 78}")
    print(f"📊  B — Risk [{cfg.label}]")
    print(f"{'=' * 78}")
    maeq = np.percentile(maes, [10, 25, 50, 75, 90])
    mfeq = np.percentile(mfes, [10, 25, 50, 75, 90])
    print(f"    MAE: p10={maeq[0]:+.1f}%  p25={maeq[1]:+.1f}%  med={maeq[2]:+.1f}%  "
          f"p75={maeq[3]:+.1f}%  p90={maeq[4]:+.1f}%")
    print(f"    MFE: p10={mfeq[0]:+.1f}%  p25={mfeq[1]:+.1f}%  med={mfeq[2]:+.1f}%  "
          f"p75={mfeq[3]:+.1f}%  p90={mfeq[4]:+.1f}%")
    mae_abs = abs(maes.mean()) if maes.mean() != 0 else 0.001
    print(f"    MFE/|MAE|={mfes.mean()/mae_abs:.2f}  "
          f"worst={rets_n.min():+.2f}%  best={rets_n.max():+.2f}%")

    print(f"\n{'=' * 78}")
    print(f"📊  C — Portfolio [{cfg.label}]")
    print(f"    fill=T+1 open  sizing={cfg.position_pct:.0%}/pos  "
          f"slots={cfg.max_slots}  cost={cfg.cost_bps}bps")
    print(f"{'=' * 78}")
    if len(eq_df) > 0:
        tot = (eq_df["equity"].iloc[-1] / cfg.capital - 1) * 100
        ny = len(eq_df) / 252
        ann = ((1 + tot/100)**(1/ny) - 1)*100 if ny > 0 else 0
        pk = eq_df["equity"].cummax()
        mdd = ((eq_df["equity"] - pk) / pk).min() * 100
        ge = eq_df["gross_exposure"]
        print(f"    total={tot:+.2f}%  ann={ann:+.2f}%  mdd={mdd:+.2f}%")
        print(f"    in_market={((eq_df['n_open']>0).mean()*100):.1f}%  "
              f"avg_pos={eq_df['n_open'].mean():.1f}/{cfg.max_slots}  "
              f"trades/yr={n/ny:.0f}")
        print(f"    exposure: avg={ge.mean():.1%}  max={ge.max():.1%}  "
              f"days>100%={int((ge>1).sum())}")

    print(f"\n{'=' * 78}")
    print(f"📊  D — Regime [{cfg.label}]")
    print(f"{'=' * 78}")
    by_r: dict[str, list] = {}
    for t in trades: by_r.setdefault(t.regime_at_signal, []).append(t)
    print(f"    {'regime':<10s} {'n':>5s} {'win%':>6s} {'mean_net':>9s} {'med_hold':>8s}")
    for r in sorted(by_r):
        ts = by_r[r]
        rt = np.array([t.gross_return_pct - cfg.cost_bps/100 for t in ts])
        h = np.array([t.holding_days for t in ts])
        print(f"    {r:<10s} {len(ts):>5d} {(rt>0).mean()*100:>5.1f}% "
              f"{rt.mean():>+8.2f}% {np.median(h):>7.0f}d")

    print(f"\n{'=' * 78}")
    print(f"📊  E — Volume Contraction [{cfg.label}]")
    print(f"{'=' * 78}")
    bins = [(0,1,"0-1"),(2,3,"2-3"),(4,6,"4-6"),(7,99,"7+")]
    print(f"    {'vc':<6s} {'n':>5s} {'win%':>6s} {'mean_net':>9s} {'med_hold':>8s}")
    for lo,hi,lb in bins:
        ts = [t for t in trades if lo <= (t.vol_contraction or 0) <= hi]
        if not ts: print(f"    {lb:<6s}     0"); continue
        rt = np.array([t.gross_return_pct - cfg.cost_bps/100 for t in ts])
        h = np.array([t.holding_days for t in ts])
        print(f"    {lb:<6s} {len(ts):>5d} {(rt>0).mean()*100:>5.1f}% "
              f"{rt.mean():>+8.2f}% {np.median(h):>7.0f}d")


def _compact(cfg, trades, eq_df):
    n = len(trades)
    if n == 0: print(f"    {cfg.label:<20s}        0"); return
    rt = np.array([t.gross_return_pct - cfg.cost_bps/100 for t in trades])
    h = np.array([t.holding_days for t in trades])
    pk = eq_df["equity"].cummax()
    dd = ((eq_df["equity"]-pk)/pk).min()*100
    tot = (eq_df["equity"].iloc[-1]/cfg.capital-1)*100
    ny = len(eq_df)/252
    ann = ((1+tot/100)**(1/ny)-1)*100 if ny > 0 else 0
    ge = eq_df["gross_exposure"]
    print(f"    {cfg.label:<20s} {n:>8d} {(rt>0).mean()*100:>5.1f}% {rt.mean():>+8.2f}% "
          f"{np.median(h):>8.0f}d {dd:>+7.2f}% {ann:>+7.2f}% {ge.max():>6.0%}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay Engine v0.2.3")
    parser.add_argument("--out", type=str, default="")
    parser.add_argument("--sensitivity", action="store_true")
    args = parser.parse_args()

    print("📥  Loading data ...")
    panel, regime_map = load_data()
    dates = sorted(panel["date"].unique())
    print(f"    rows={len(panel):,d}  stocks={panel['stock_id'].nunique()}  "
          f"dates={len(dates)}")

    print("🧮  RS_T3 + beta_T2 ...")
    panel = assign_rs_and_beta(panel)

    print("🔍  Scanning corporate-action gaps (|Δ| > 50%) ...")
    ca_gap_days, ca_pre_gap_days = build_ca_gap_days(panel)
    print(f"    found {len(ca_gap_days)} CA gap events, {len(ca_pre_gap_days)} pre-gap dates")

    # ═══ BASELINE ═══
    print(f"\n{'═' * 78}")
    print("🚀  BASELINE (approximate locked-policy replay)")
    print(f"{'═' * 78}")
    bcfg = ReplayConfig(label="baseline")
    print(f"    slots={bcfg.max_slots}  sizing={bcfg.position_pct:.0%}  "
          f"atr={bcfg.atr_mult}  time={bcfg.time_stop_days}d  "
          f"cost={bcfg.cost_bps}bps  disaster_stop={DISASTER_STOP_PCT:.0%}")

    trades, eq_df = run_replay(panel, regime_map, ca_gap_days, ca_pre_gap_days, bcfg)
    ca_trades = sum(1 for t in trades if t.exit_reason and "corporate_action" in t.exit_reason)
    print(f"    trades={len(trades)}  (CA quarantined={ca_trades})")

    # ── HARD ASSERTION: no unquarantined CA-scale returns ──
    dq_violations = [
        t for t in trades
        if abs(t.gross_return_pct) > 50
        and (t.exit_reason or "") != "corporate_action_quarantine"
    ]
    if dq_violations:
        print(f"\n❌  DQ ASSERTION FAILED: {len(dq_violations)} trades with "
              f"|return| > 50% not quarantined:")
        for t in dq_violations:
            print(f"    {t.stock_id}  {t.entry_date}→{t.exit_date}  "
                  f"{t.gross_return_pct:+.1f}%  reason={t.exit_reason}")
        print("    Fix CA quarantine before interpreting results.\n")
    else:
        print(f"    ✅  DQ assertion passed: no |return| > 50% outside quarantine")

    print_summary(trades, eq_df, bcfg, ca_trades)

    if args.out:
        rows = [{
            "stock_id": t.stock_id, "entry_date": t.entry_date,
            "exit_date": t.exit_date,
            "entry_price": round(t.entry_price, 2),
            "exit_price": round(t.exit_price, 2) if t.exit_price else None,
            "holding_days": t.holding_days,
            "gross_return_pct": round(t.gross_return_pct, 4),
            "net_return_pct": round(t.gross_return_pct - bcfg.cost_bps/100, 4),
            "exit_reason": t.exit_reason,
            "mfe_pct": round(t.mfe_pct, 4), "mae_pct": round(t.mae_pct, 4),
            "regime_at_signal": t.regime_at_signal,
            "regime_at_exit": t.regime_at_exit,
            "rs_pctile": round(t.rs_pctile, 4), "dist": round(t.dist, 4),
            "vol_contraction": t.vol_contraction,
        } for t in trades]
        pd.DataFrame(rows).to_csv(args.out, index=False)
        print(f"\n📥  Trade log: {args.out}")

    # ═══ SENSITIVITY ═══
    if args.sensitivity:
        print(f"\n{'═' * 78}")
        print("🔬  SENSITIVITY (pre-registered, one-at-a-time)")
        print(f"{'═' * 78}")
        variants = [
            ReplayConfig(time_stop_days=40, label="time=40d"),
            ReplayConfig(time_stop_days=60, label="time=60d"),
            ReplayConfig(atr_mult=1.5, label="atr=1.5"),
            ReplayConfig(atr_mult=3.0, label="atr=3.0"),
            ReplayConfig(max_slots=3, label="slots=3"),
            ReplayConfig(max_slots=99, label="slots=all"),
        ]
        print(f"\n    {'variant':<20s} {'n':>8s} {'win%':>6s} {'mean_net':>9s} "
              f"{'med_hold':>9s} {'mdd':>8s} {'ann':>8s} {'max_exp':>7s}")
        print(f"    {'-' * 75}")
        _compact(bcfg, trades, eq_df)
        for v in variants:
            vt, ve = run_replay(panel, regime_map, ca_gap_days, ca_pre_gap_days, v)
            _compact(v, vt, ve)
        print(f"\n    position_pct={bcfg.position_pct:.0%} fixed across all variants.")

    print(f"\n✅  Done.")


if __name__ == "__main__":
    main()
