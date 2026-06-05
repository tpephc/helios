# Backlog P3-OPS — avoid DuckDB write-lock contention during the trading session

<!-- docs/backlog/P3-OPS_session_write_lock_policy.md -->
<!-- Operational policy gap. Opened 2026-06-01 from intraday monitor fatal analysis. -->

**Priority:** P3 (operations)
**Opened:** 2026-06-01
**Source:** root-cause analysis of intraday_monitor fatals (2026-05-28 / 05-29)

## Problem

DuckDB enforces a single writer per database file. Any process holding a write
lock on `data/_storage/helios.duckdb` during the 09:00-13:30 Taipei trading
session can make the intraday monitor's run fail fatally (observed 2026-05-28 and
2026-05-29 at 09:05). There is currently no policy preventing write-lock
contention during the session.

## Evidence

- Two consecutive fatal runs with "Conflicting lock held by ... PID ..." at 09:05,
  a time outside the monitor's own cadence (:07/:22/:37/:52), implying a different
  job or a manual session held the lock.

## Contributing factors

- Manual analysis runs during market hours. Research tools should open
  `read_only=True` (readers do not block readers), but an accidental write
  connection, or any writer job overlapping 09:00-13:30, will contend.

## Proposed remediation (policy + light enforcement)

1. Policy: no write-lock-holding job scheduled within 09:00-13:30 on trading days;
   schedule writers pre-open (before 09:00) or post-close (after 13:40).
2. Convention: all interactive / research DB access uses `read_only=True`
   (already the standard in research/ma5_momentum_feasibility.py and
   scripts/intraday_healthcheck.py).
3. Optional: a short preflight in writer jobs that aborts if the current time is
   inside the session window, unless an explicit override flag is passed.
4. Pairs with P1-OBS retry/backoff: even with the policy, the monitor should
   survive a transient lock rather than die.

## Acceptance

- No scheduled writer job overlaps the 09:00-13:30 window (cron/systemd audit).
- Documented operator guidance: read-only for in-session manual DB access.
- After P1-OBS, a transient lock no longer produces a silent fatal.

## Related

- P1-OBS (monitor self-alert + retry), P2-OBS (gap detection).
