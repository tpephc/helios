#!/usr/bin/env python3
# scripts/run_summary.py
"""5-day operational rollup — v0.1.14.3.

Reads:
  - HISTORY_PATH (`~/.helios_run_history.jsonl`) — last N daily_run records.
    Populated by `execution.shutdown._append_history` since v0.1.14.3.
  - DB (signals / orders / positions) — last N trading days' aggregates.

Produces a one-screen summary that operators can eyeball after a 5-day paper
trading observation window. The goal is to surface *operational scars* that
single-day unit tests can't catch: repeat-failure streaks per symbol, OPEN
positions that aren't moving, no-data symbols accumulating, etc.

Read-only: this script makes no DB writes, no state changes. Safe to run
ad-hoc at any time, including during a paper-trade window.

Usage:
  uv run python scripts/run_summary.py                    # last 5 days
  uv run python scripts/run_summary.py --days 10          # custom window

Version: v0.1.0 (2026-05-17 — v0.1.14.3 stability instrumentation)
"""
from __future__ import annotations

import argparse
import sys
from datetime import date as date_type
from datetime import datetime, timedelta

from data.database import connect
from execution.shutdown import read_history, read_marker

# ─────────────────────────────────────────────────────────────
# Pure aggregation helpers (testable)
# ─────────────────────────────────────────────────────────────


def compute_failure_streaks(history: list[dict]) -> dict[str, int]:
    """Return symbol -> consecutive exit-failure streak ending in the most
    recent successful run.

    Semantics:
      - history is oldest→newest (as read_history returns)
      - declined_preflight / aborted records are skipped (no scan happened,
        so they don't break a real streak)
      - a symbol that appears in exits_failed_symbols of run N but not N+1
        has its streak ended (removed from output)
      - only "still-failing" symbols appear in the returned dict
    """
    streaks: dict[str, int] = {}
    for record in history:
        if record.get("status") != "ok":
            continue
        failed = set(record.get("summary", {}).get("exits_failed_symbols") or [])
        # Drop symbols whose streak ended this run
        for s in list(streaks):
            if s not in failed:
                del streaks[s]
        for sym in failed:
            streaks[sym] = streaks.get(sym, 0) + 1
    return streaks


def query_signal_flow(since: date_type) -> list[tuple]:
    """(signal_date, approval_status, count) rows for signal_date >= since."""
    with connect(read_only=True) as conn:
        rows = conn.execute(
            """
            SELECT signal_date, approval_status, COUNT(*)
            FROM signals
            WHERE signal_date >= ?
            GROUP BY signal_date, approval_status
            ORDER BY signal_date, approval_status
            """,
            [since],
        ).fetchall()
    return [(r[0], r[1], int(r[2])) for r in rows]


def query_order_flow(since: date_type) -> list[tuple]:
    """(date, side, status, count) rows for orders timestamped on/after since."""
    with connect(read_only=True) as conn:
        rows = conn.execute(
            """
            SELECT CAST(timestamp AS DATE) AS d, side, status, COUNT(*)
            FROM orders
            WHERE CAST(timestamp AS DATE) >= ?
            GROUP BY d, side, status
            ORDER BY d, side, status
            """,
            [since],
        ).fetchall()
    return [(r[0], r[1], r[2], int(r[3])) for r in rows]


def query_open_positions(as_of: date_type) -> list[tuple]:
    """(position_id, symbol, entry_date, age_days) for every currently OPEN position."""
    with connect(read_only=True) as conn:
        rows = conn.execute(
            "SELECT position_id, symbol, entry_date FROM positions "
            "WHERE status = 'OPEN' ORDER BY entry_date",
        ).fetchall()
    out = []
    for pid, sym, ent in rows:
        age = (as_of - ent).days if ent else None
        out.append((pid, sym, ent, age))
    return out


# ─────────────────────────────────────────────────────────────
# Rendering (kept separate from aggregation so logic is unit-testable)
# ─────────────────────────────────────────────────────────────


def _render_history(history: list[dict]) -> str:
    if not history:
        return "  (no run history)"
    out = []
    for r in history:
        as_of = r.get("as_of", "?")
        status = r.get("status", "?")
        summary = r.get("summary", {}) or {}
        if status == "ok":
            failed_syms = summary.get("exits_failed_symbols") or []
            extra = f"  failed_symbols={failed_syms}" if failed_syms else ""
            # v0.1.14.3.2: max_position_days surfaces stuck-OPEN outliers.
            # avg is kept in JSON for downstream query but not rendered here
            # (max is the actionable scar; avg is noisier).
            max_age = summary.get("max_position_days")
            max_age_str = f"  max_open={max_age}d" if max_age is not None else ""
            line = (
                f"  {as_of}  {status:<20s}  "
                f"exits={summary.get('exits', '?')}  "
                f"approved={summary.get('approved', '?')}  "
                f"rejected={summary.get('rejected', '?')}  "
                f"exits_failed={summary.get('exits_failed', 0)}"
                f"{max_age_str}{extra}"
            )
        else:
            reason = summary.get("reason") or summary.get("abort_reason") or ""
            line = f"  {as_of}  {status:<20s}  {reason}"
        out.append(line)
    return "\n".join(out)


def _render_signal_flow(rows: list[tuple]) -> str:
    if not rows:
        return "  (no signals in window)"
    by_date: dict = {}
    statuses: set[str] = set()
    for d, s, n in rows:
        by_date.setdefault(d, {})[s] = n
        statuses.add(s)
    statuses_sorted = sorted(statuses)
    header = "  date          " + "  ".join(f"{s:<14s}" for s in statuses_sorted)
    lines = [header]
    for d in sorted(by_date):
        cells = "  ".join(f"{by_date[d].get(s, 0):<14d}" for s in statuses_sorted)
        lines.append(f"  {d}    {cells}")
    return "\n".join(lines)


def _render_order_flow(rows: list[tuple]) -> str:
    if not rows:
        return "  (no orders in window)"
    lines = []
    for d, side, status, n in rows:
        lines.append(f"  {d}  {side:<6s}  {status:<10s}  {n}")
    return "\n".join(lines)


def _render_open_positions(rows: list[tuple]) -> str:
    if not rows:
        return "  (no open positions)"
    lines = ["  position_id           symbol   entry_date    age_days"]
    for pid, sym, ent, age in rows:
        lines.append(f"  {pid:<22s} {sym:<8s} {ent}    {age}")
    return "\n".join(lines)


def _render_failure_streaks(streaks: dict[str, int]) -> str:
    if not streaks:
        return "  (no repeat-failure scars detected)"
    lines = []
    for sym, n in sorted(streaks.items(), key=lambda x: -x[1]):
        marker = "⚠ " if n >= 2 else "  "
        lines.append(f"  {marker}{sym}: exit failed {n} consecutive run(s)")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="v0.1.14.3 5-day operational rollup",
    )
    parser.add_argument("--days", type=int, default=5,
                        help="window size in calendar days (default 5)")
    parser.add_argument("--as-of", type=str, default=None,
                        help="anchor date (default today) for age computation")
    args = parser.parse_args()

    as_of = (
        date_type.fromisoformat(args.as_of) if args.as_of
        else date_type.today()
    )
    since = as_of - timedelta(days=args.days)

    print(f"Helios run summary — generated {datetime.now().isoformat(timespec='seconds')}")
    print(f"Window: {since} → {as_of}  ({args.days} calendar days)")
    print()

    history = read_history(n=args.days)
    print(f"Run history (last {len(history)}):")
    print(_render_history(history))
    print()

    print("Signal flow:")
    print(_render_signal_flow(query_signal_flow(since)))
    print()

    print("Order flow:")
    print(_render_order_flow(query_order_flow(since)))
    print()

    print("Open positions:")
    print(_render_open_positions(query_open_positions(as_of)))
    print()

    streaks = compute_failure_streaks(history)
    print("Repeat-failure scars:")
    print(_render_failure_streaks(streaks))
    print()

    marker = read_marker()
    if marker:
        print(f"Latest marker: as_of={marker.get('as_of')} status={marker.get('status')}")
    else:
        print("Latest marker: (none)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
