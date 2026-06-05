# Backlog P1-OBS — intraday_monitor self-alert on fatal (root-cause observability)

<!-- docs/backlog/P1-OBS_intraday_monitor_self_alert.md -->
<!-- Observability gap. Opened 2026-06-01 from intraday monitor log review. -->

**Priority:** P1 (observability)
**Opened:** 2026-06-01
**Source:** intraday monitor log review + healthcheck verification (2026-06-01)

## Problem

When `intraday_monitor.py` dies with a fatal error it writes NO row to
`intraday_monitor_runs` and sends NO alert. The failure is therefore silent
until the post-close healthcheck (P2/scripts/intraday_healthcheck.py) catches it
hours later. The operator does not know at the moment of failure.

## Evidence (read-only, confirmed)

- 2026-05-28 09:05 and 2026-05-29 09:05: `intraday_monitor_fatal` in
  `logs/intraday_monitor.log`, detail "IO Error: Could not set lock on
  helios.duckdb: Conflicting lock held by ... PID ...". Both runs died before
  opening the DB.
- `intraday_monitor_runs.system_alert_sent` is 0 on those days (and historically):
  the monitor never self-alerts on fatal.
- On 2026-05-28 only 1 of 20 runs died (DB shows 19/20 = 95% coverage), so a
  coverage-only check would have passed it HEALTHY. The fatal was caught ONLY
  because it left a log line. A fatal that also failed to log would be missed.

## Root cause

DuckDB single-writer lock: any process holding a write lock during the
09:00-13:30 session makes the monitor's DB open fail fatally. Likely contenders:
a 09:xx job overlapping the monitor, or manual read/write DB access during the
session. (See P3-OPS for the contention policy.)

## Proposed remediation

1. Wrap the monitor's DB-open and main loop so a fatal (esp. lock IOException)
   triggers an immediate Telegram alert via the existing communication.telegram
   stack BEFORE exiting, and sets `system_alert_sent = 1` on a sentinel/failed-run
   record.
2. On lock conflict specifically: retry with bounded backoff (e.g. 3 x 5s) before
   declaring fatal — many lock holders are short-lived writers.
3. Record a row even on fatal (status column: completed / fatal / lock_timeout)
   so DB coverage reflects attempts, not just successes.

## Acceptance

- A forced lock conflict during the session produces a Telegram alert within the
  same run, and a fatal-status row in `intraday_monitor_runs`.
- `system_alert_sent = 1` on any fatal run.
- Post-close healthcheck and the live monitor agree on fatal counts for the day.

## Related

- `scripts/intraday_healthcheck.py` (post-close watchdog; complements but does
  not replace self-alerting).
- P2-OBS (single-run-gap detection), P3-OPS (write-lock contention policy).
