#!/usr/bin/env python3
# scripts/intraday_healthcheck.py
"""Intraday monitor healthcheck — v0.1.0. Post-close watchdog over the intraday monitor.

WHY THIS EXISTS:
  intraday_monitor.py runs on cron (7,22,37,52 9-13 * * 1-5). When it dies with a
  fatal error (observed 2026-05-28/05-29: DuckDB lock conflict), the failed run
  writes NOTHING to intraday_monitor_runs and sends NO alert — the monitor can be
  silently down and nobody knows. This script is the monitor-of-the-monitor: a
  read-only, post-close check that reconciles expected vs actual runs and scans
  the log for fatals/skips, alerting via Telegram only on real problems.

DESIGN DECISIONS (all explicit; change in CONFIG, not in code paths):
  - Expected runs/day = 20 (cron fires at :07/:22/:37/:52 across hours 9..13 =
    5 hours x 4). The 13:37 and 13:52 fires occur AFTER the 13:30 close; the
    monitor still records a run row for them, so they count toward the expected
    20. Coverage = actual_db_runs / expected; below COVERAGE_ALERT_FRACTION
    (0.80) triggers an alert.
  - FATAL detection is LOG-ONLY by necessity: a fatal run fails before opening
    the DB, so it leaves no DB row. The DB undercount and the log fatals are two
    independent views; both are reported.
  - SKIP (stale/invalid quote, e.g. 2026-05-27 Shioaji login failure) is reported
    but does NOT by itself trigger Telegram — it is expected graceful degradation.
    It escalates to alert only if skips exceed SKIP_ALERT_COUNT in one day.
  - TIMEZONE: DB run_at is UTC; log timestamps are Taipei (+08:00). The two are
    matched on their OWN calendar day (UTC day for DB, Taipei day for log). On a
    normal trading day these coincide for the 09:00-13:30 window; the split is
    only to avoid midnight-boundary misclassification.

READ-ONLY GUARANTEE:
  Opens the DuckDB strictly read_only=True. This is also why it is safe to run
  during/after other jobs: it never takes a write lock (the very failure mode it
  watches for). Telegram send is suppressed under --dry-run.

Usage:
  uv run python scripts/intraday_healthcheck.py                 # check today, send TG on problem
  uv run python scripts/intraday_healthcheck.py --dry-run       # print only, never send
  uv run python scripts/intraday_healthcheck.py --date 2026-05-28   # check a past day
  uv run python scripts/intraday_healthcheck.py --expected-runs 18  # exclude post-close fires

Exit codes: 0 = healthy, 1 = problem detected (alert raised or would-be-raised
under --dry-run), 2 = healthcheck itself failed (could not read DB/log).

Version: v0.1.0 (2026-06-01)
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import duckdb

# --------------------------------------------------------------------------- #
# Configuration                                                                 #
# --------------------------------------------------------------------------- #
DB_PATH = Path("data/_storage/helios.duckdb")
LOG_PATH = Path("logs/intraday_monitor.log")
RUNS_TABLE = "intraday_monitor_runs"
RUN_TS_COL = "run_at"          # UTC timestamp column in intraday_monitor_runs
ALERTS_COL = "alerts_sent"
SYS_ALERT_COL = "system_alert_sent"

EXPECTED_RUNS_PER_DAY = 20            # :07/:22/:37/:52 over hours 9..13
COVERAGE_ALERT_FRACTION = 0.80        # alert if actual/expected < this
SKIP_ALERT_COUNT = 3                  # skips above this escalate to a TG alert

TAIPEI = ZoneInfo("Asia/Taipei")
UTC = ZoneInfo("UTC")

# Log line markers (intraday_monitor.py structured events).
_RE_FATAL = re.compile(r"intraday_monitor_fatal")
_RE_SKIP = re.compile(r"intraday_monitor_skip_invalid_quote")
_RE_LOGIN_FAIL = re.compile(r"shioaji_quote_source_login_failed")
# Taipei-local timestamp inside the structured log lines, e.g.
# "timestamp": "2026-06-01T09:52:03+08:00"  OR  loguru "2026-06-01 09:52:01.778"
_RE_TS_ISO = re.compile(r"(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}:\d{2}")
_RE_TS_LOGURU = re.compile(r"^(\d{4}-\d{2}-\d{2})\s\d{2}:\d{2}:\d{2}")


@dataclass
class HealthReport:
    check_date_utc: dt.date
    check_date_taipei: dt.date
    db_runs: int = 0
    expected_runs: int = EXPECTED_RUNS_PER_DAY
    last_run_at: Optional[str] = None
    total_alerts_sent: int = 0
    fatal_count: int = 0
    skip_count: int = 0
    login_fail_count: int = 0
    log_found: bool = True
    problems: list[str] = field(default_factory=list)

    @property
    def coverage(self) -> float:
        return self.db_runs / self.expected_runs if self.expected_runs else float("nan")

    @property
    def healthy(self) -> bool:
        return not self.problems


# --------------------------------------------------------------------------- #
# Checks                                                                         #
# --------------------------------------------------------------------------- #
def check_db_runs(con: duckdb.DuckDBPyConnection, day_utc: dt.date) -> tuple[int, Optional[str], int]:
    """Return (run_count_today_utc, last_run_at_iso, total_alerts_sent_today)."""
    row = con.execute(
        f"SELECT COUNT(*) AS n, MAX({RUN_TS_COL}) AS last_ts, "
        f"COALESCE(SUM({ALERTS_COL}), 0) AS alerts "
        f"FROM {RUNS_TABLE} WHERE CAST({RUN_TS_COL} AS DATE) = CAST(? AS DATE)",
        [day_utc.isoformat()],
    ).fetchone()
    last = str(row[1]) if row[1] is not None else None
    return int(row[0]), last, int(row[2])


def _log_line_date(line: str) -> Optional[dt.date]:
    m = _RE_TS_ISO.search(line) or _RE_TS_LOGURU.search(line)
    if not m:
        return None
    try:
        return dt.date.fromisoformat(m.group(1))
    except ValueError:
        return None


def scan_log(log_path: Path, day_taipei: dt.date) -> tuple[int, int, int, bool]:
    """Scan the monitor log for today's fatals / skips / login failures.

    Returns (fatal_count, skip_count, login_fail_count, log_found). Counts only
    lines whose embedded Taipei-local date matches day_taipei. Lines without a
    parseable date are ignored (cannot be attributed to a day safely).
    """
    if not log_path.exists():
        return 0, 0, 0, False
    fatal = skip = login = 0
    with log_path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not (_RE_FATAL.search(line) or _RE_SKIP.search(line)
                    or _RE_LOGIN_FAIL.search(line)):
                continue
            d = _log_line_date(line)
            if d != day_taipei:
                continue
            if _RE_FATAL.search(line):
                fatal += 1
            elif _RE_SKIP.search(line):
                skip += 1
            elif _RE_LOGIN_FAIL.search(line):
                login += 1
    return fatal, skip, login, True


def evaluate(report: HealthReport) -> None:
    """Populate report.problems per the alerting policy."""
    if report.fatal_count > 0:
        report.problems.append(
            f"FATAL: {report.fatal_count} fatal run(s) in log "
            f"(silent — these leave no DB row; e.g. DuckDB lock conflict)")
    if report.coverage < COVERAGE_ALERT_FRACTION:
        report.problems.append(
            f"LOW COVERAGE: {report.db_runs}/{report.expected_runs} runs "
            f"({report.coverage:.0%} < {COVERAGE_ALERT_FRACTION:.0%})")
    if report.skip_count > SKIP_ALERT_COUNT:
        report.problems.append(
            f"EXCESSIVE SKIPS: {report.skip_count} invalid-quote skips "
            f"(> {SKIP_ALERT_COUNT}); intraday coverage has holes")
    if not report.log_found:
        report.problems.append(
            f"LOG MISSING: {LOG_PATH} not found — cannot verify fatals/skips")


# --------------------------------------------------------------------------- #
# Reporting                                                                     #
# --------------------------------------------------------------------------- #
def format_report(r: HealthReport) -> str:
    status = "HEALTHY" if r.healthy else "PROBLEM"
    lines = [
        f"Intraday monitor healthcheck — {status}",
        f"  date (UTC/Taipei): {r.check_date_utc} / {r.check_date_taipei}",
        f"  DB runs: {r.db_runs}/{r.expected_runs} (coverage {r.coverage:.0%})",
        f"  last run_at (UTC): {r.last_run_at or 'none'}",
        f"  alerts_sent today: {r.total_alerts_sent}",
        f"  log: fatal={r.fatal_count} skip={r.skip_count} login_fail={r.login_fail_count}"
        f"{'' if r.log_found else ' [LOG NOT FOUND]'}",
    ]
    if r.problems:
        lines.append("  problems:")
        lines.extend(f"    - {p}" for p in r.problems)
    return "\n".join(lines)


def build_telegram_message(r: HealthReport) -> str:
    head = "🚨 Intraday monitor healthcheck: PROBLEM"
    body = [head, f"date {r.check_date_taipei} (Taipei)",
            f"runs {r.db_runs}/{r.expected_runs} ({r.coverage:.0%})",
            f"fatal={r.fatal_count} skip={r.skip_count} login_fail={r.login_fail_count}"]
    body += [f"• {p}" for p in r.problems]
    return "\n".join(body)


def send_telegram(message: str) -> bool:
    """Send via the existing communication.telegram stack. Returns True if sent."""
    try:
        from communication.telegram import TelegramBot, TelegramConfig
        from communication.telegram.sender import push_simple
    except Exception as exc:  # noqa: BLE001 - import path is the thing we report
        print(f"[telegram] import failed, not sent: {exc}", file=sys.stderr)
        return False
    cfg = TelegramConfig.from_env()
    if not cfg:
        print("[telegram] from_env() returned falsy (env not set); not sent.", file=sys.stderr)
        return False
    bot = TelegramBot(cfg)
    push_simple(bot, message)
    return True


# --------------------------------------------------------------------------- #
# Orchestration                                                                 #
# --------------------------------------------------------------------------- #
def run_healthcheck(
    db_path: Path,
    log_path: Path,
    target_date: Optional[dt.date],
    expected_runs: int,
) -> HealthReport:
    now_tp = dt.datetime.now(tz=TAIPEI)
    day_taipei = target_date or now_tp.date()
    # DB day to query: the UTC calendar day overlapping the Taipei trading session.
    # The 09:00-13:30 Taipei session maps to 01:00-05:30 UTC of the SAME date,
    # so the UTC date equals the Taipei date for all monitor runs.
    day_utc = day_taipei

    report = HealthReport(check_date_utc=day_utc, check_date_taipei=day_taipei,
                          expected_runs=expected_runs)

    if not db_path.exists():
        report.problems.append(f"DB not found: {db_path}")
        report.log_found = log_path.exists()
        return report

    con = duckdb.connect(database=str(db_path), read_only=True)
    try:
        report.db_runs, report.last_run_at, report.total_alerts_sent = check_db_runs(con, day_utc)
    finally:
        con.close()

    report.fatal_count, report.skip_count, report.login_fail_count, report.log_found = \
        scan_log(log_path, day_taipei)

    evaluate(report)
    return report


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Intraday monitor post-close healthcheck.")
    ap.add_argument("--db", type=Path, default=DB_PATH)
    ap.add_argument("--log", type=Path, default=LOG_PATH)
    ap.add_argument("--date", type=str, default=None,
                    help="Taipei date YYYY-MM-DD to check (default: today)")
    ap.add_argument("--expected-runs", type=int, default=EXPECTED_RUNS_PER_DAY,
                    help="expected monitor runs for the day (default 20; use 18 to "
                         "exclude the two post-close fires)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print report only, never send Telegram")
    return ap.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    target = dt.date.fromisoformat(args.date) if args.date else None

    try:
        report = run_healthcheck(args.db, args.log, target, args.expected_runs)
    except Exception as exc:  # noqa: BLE001 - healthcheck failure is itself a signal
        print(f"healthcheck FAILED to run: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    print(format_report(report))

    if report.problems and not args.dry_run:
        sent = send_telegram(build_telegram_message(report))
        print(f"[telegram] alert {'sent' if sent else 'NOT sent'}")

    return 0 if report.healthy else 1


if __name__ == "__main__":
    sys.exit(main())
