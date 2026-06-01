# research/tracker_digest.py
"""Tracker Digest — v1.0.0.

Builds a Telegram-ready evening digest section for the forward return tracker.
Included in run_evening_digest.py as section 4.

Status code legend (maps signal approval pipeline to exit contract terminology):
  TO  TIMEOUT       — entry window expired (analogous to TimeStop)
  TS  EXPIRED_DRIFT — ATR drift expelled signal (analogous to TrailingStop)
  RE  RegimeExit    — reserved; no current expired_reason maps here
  PD  PENDING       — still in approval window
  AP  APPROVED      — entered portfolio
  RJ  REJECTED      — manually rejected
"""

from __future__ import annotations

from datetime import date as Date

import numpy as np

from data.database import connect

# ---------------------------------------------------------------------------
# Constants — must match forward_return_tracker.py
# ---------------------------------------------------------------------------

_MAX_HOLDING_DAYS: int = 20
_TRACKER_SCHEMA_VERSION: int = 2
_STRATEGIES: tuple[str, ...] = ("trend_pullback_v1", "trend_breakout_v1")
_ROUND_TRIP_COST_BPS: float = 40.0
_ENTRY_SLIPPAGE_BPS: float = 5.0

_STRATEGY_LABELS: dict[str, str] = {
    "trend_breakout_v1": "BREAKOUT",
    "trend_pullback_v1": "PULLBACK",
}

# (approval_status, expired_reason) → abbreviation
# None as expired_reason matches rows where the column is NULL.
_STATUS_MAP: dict[tuple[str, str | None], str] = {
    ("TIMEOUT",       None):        "TO",
    ("TIMEOUT",       "timeout"):   "TO",
    ("EXPIRED_DRIFT", "atr_drift"): "TS",
    ("EXPIRED_DRIFT", "timeout"):   "TO",
    ("EXPIRED_DRIFT", None):        "TS",   # atr_drift is the common case
    ("PENDING",       None):        "PD",
    ("APPROVED",      None):        "AP",
    ("AUTO_APPROVED", None):        "AP",
    ("REJECTED",      None):        "RJ",
}

_SEP: str = "─" * 37


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _status_code(approval_status: str, expired_reason: str | None) -> str:
    key = (approval_status, expired_reason)
    if key in _STATUS_MAP:
        return _STATUS_MAP[key]
    for (status, _), code in _STATUS_MAP.items():
        if status == approval_status:
            return code
    return approval_status[:2].upper()


def _fmt_return(net_return: float | None) -> str:
    if net_return is None:
        return "     —"
    sign = "+" if net_return >= 0 else ""
    return f"{sign}{net_return:.2%}"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_tracker_state(conn) -> list[dict]:
    """Return canonical signal + latest observation state for all strategies.

    Applies the same ROW_NUMBER() dedup as forward_return_tracker._load_signals()
    so this digest is consistent with the evidence the tracker writes.
    """
    rows = conn.execute(
        """
        WITH canonical AS (
            SELECT signal_id, symbol, strategy, signal_date,
                   approval_status, expired_reason
            FROM (
                SELECT *,
                       ROW_NUMBER() OVER (
                           PARTITION BY symbol, strategy, signal_date
                           ORDER BY created_at ASC, signal_id ASC
                       ) AS rn
                FROM signals
                WHERE strategy IN (SELECT unnest($1))
            )
            WHERE rn = 1
        ),
        obs_state AS (
            SELECT
                signal_id,
                MAX(holding_day) AS max_day,
                BOOL_OR(resolved) AS is_resolved
            FROM forward_return_observations
            WHERE tracker_schema_version = $2
            GROUP BY signal_id
        ),
        obs_latest_return AS (
            -- Most recent net return for each signal (highest holding_day row).
            SELECT signal_id, net_return_t1
            FROM forward_return_observations
            WHERE tracker_schema_version = $2
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY signal_id ORDER BY holding_day DESC
            ) = 1
        )
        SELECT
            c.signal_id,
            c.symbol,
            COALESCE(si.short_name, '') AS stock_name,
            c.strategy,
            c.signal_date,
            c.approval_status,
            c.expired_reason,
            COALESCE(os.max_day, -1)        AS max_day,
            olr.net_return_t1,
            COALESCE(os.is_resolved, false)  AS is_resolved
        FROM canonical c
        LEFT JOIN company_metadata   si  ON si.stock_id   = c.symbol
        LEFT JOIN obs_state          os  ON os.signal_id  = c.signal_id
        LEFT JOIN obs_latest_return  olr ON olr.signal_id = c.signal_id
        ORDER BY c.strategy, c.signal_date, c.symbol
        """,
        [list(_STRATEGIES), _TRACKER_SCHEMA_VERSION],
    ).fetchall()

    return [
        {
            "signal_id":       r[0],
            "symbol":          r[1],
            "stock_name":      r[2],
            "strategy":        r[3],
            "signal_date":     r[4],
            "approval_status": r[5],
            "expired_reason":  r[6],
            "max_day":         int(r[7]),
            "net_return":      float(r[8]) if r[8] is not None else None,
            "is_resolved":     bool(r[9]),
        }
        for r in rows
    ]


def _upstream_dup_line(conn) -> str | None:
    """Return a one-line upstream duplicate warning, or None if no duplicates."""
    row = conn.execute(
        """
        SELECT
            SUM(cnt)          AS raw_total,
            COUNT(*)          AS dedup_total,
            SUM(cnt) - COUNT(*) AS dup_rows
        FROM (
            SELECT COUNT(*) AS cnt
            FROM signals
            WHERE strategy IN (SELECT unnest($1))
            GROUP BY symbol, strategy, signal_date
        )
        """,
        [list(_STRATEGIES)],
    ).fetchone()

    if not row or row[2] == 0:
        return None
    return f"⚠️  upstream dup: raw {row[0]} → dedup {row[1]} (-{row[2]})"


# ---------------------------------------------------------------------------
# Resolved gate summary
# ---------------------------------------------------------------------------

def _resolved_summary_lines(resolved: list[dict]) -> list[str]:
    """Build top-of-message resolved gate summary, grouped by strategy."""
    lines: list[str] = []
    for strat in _STRATEGIES:
        strat_res = [s for s in resolved if s["strategy"] == strat]
        if not strat_res:
            continue
        label = _STRATEGY_LABELS.get(strat, strat)
        n = len(strat_res)
        rets = [s["net_return"] for s in strat_res if s["net_return"] is not None]
        if not rets:
            lines.append(f"✅ RESOLVED: {label.lower()} {n} signals  (returns pending)")
            continue
        mean_r = float(np.mean(rets))
        hit = float(np.mean([r > 0 for r in rets]))
        gate_n = "✓ n≥150" if n >= 150 else f"✗ n={n}/150"
        lines.append(f"✅ RESOLVED: {label.lower()} {n} signals")
        lines.append(f"   mean {mean_r:>+.2%}  hit {hit:.0%}  gate [{gate_n}]")
    return lines


# ---------------------------------------------------------------------------
# Signal table
# ---------------------------------------------------------------------------

def _signal_table(signals: list[dict]) -> str:
    """Format a monospace signal table for one strategy."""
    rows = []
    for s in signals:
        symbol   = str(s["symbol"])
        name     = str(s.get("stock_name", ""))[:5]
        date_s   = str(s["signal_date"])[5:10]   # MM-DD
        max_day  = s["max_day"]
        day_num  = max_day + 1 if max_day >= 0 else 0
        prog     = f"D{day_num}/{_MAX_HOLDING_DAYS}"
        ret_s    = _fmt_return(s["net_return"])
        status   = _status_code(s["approval_status"], s["expired_reason"])
        mark     = " ✅" if s["is_resolved"] else ""
        rows.append(f" {symbol} {name}  {date_s}  {prog:<7} {ret_s:>7}  {status}{mark}")
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def build_tracker_message(as_of: Date | None = None) -> str | None:
    """Build the tracker section for the evening digest.

    Returns None if the observation table does not exist or has no signals.
    Failure-safe: the caller should wrap in try/except.
    """
    try:
        with connect() as conn:
            # Verify table exists before querying.
            tables = {
                r[0] for r in conn.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'main'"
                ).fetchall()
            }
            if "forward_return_observations" not in tables:
                return None

            signals = _load_tracker_state(conn)
            dup_line = _upstream_dup_line(conn)
    except Exception:
        return None

    if not signals:
        return None

    resolved   = [s for s in signals if s["is_resolved"]]
    inprogress = [s for s in signals if not s["is_resolved"]]

    date_s = str(as_of) if as_of else ""
    lines: list[str] = [f"📊 Forward Return Tracker  {date_s}"]

    # --- Upstream duplicate warning ---
    if dup_line:
        lines.append("")
        lines.append(dup_line)

    # --- Resolved summary at top ---
    lines.append("")
    if resolved:
        lines.extend(_resolved_summary_lines(resolved))
    else:
        lines.append(f"⏳ No resolved signals yet (need {_MAX_HOLDING_DAYS}d elapsed)")

    # --- Per-strategy signal tables ---
    for strat in _STRATEGIES:
        strat_sigs = [s for s in signals if s["strategy"] == strat]
        if not strat_sigs:
            continue
        label  = _STRATEGY_LABELS.get(strat, strat)
        n_res  = sum(1 for s in strat_sigs if s["is_resolved"])
        n_prog = len(strat_sigs) - n_res
        count  = (
            f"resolved {n_res} / in-progress {n_prog}"
            if n_res else f"{n_prog} signals in progress"
        )
        lines.append("")
        lines.append(_SEP)
        lines.append(f"{label}  {count}")
        lines.append(_SEP)
        lines.append(_signal_table(strat_sigs))

    lines.append(_SEP)
    lines.append("TO=TimeStop  TS=TrailingStop  RE=RegimeExit")
    lines.append("PD=Pending   AP=Approved      RJ=Rejected")
    cost = _ROUND_TRIP_COST_BPS + _ENTRY_SLIPPAGE_BPS
    lines.append(f"淨報酬 = net_return_t1（已扣除 {cost:.0f}bps 成本）")

    return "\n".join(lines)
