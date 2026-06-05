# Backlog P2-OBS — healthcheck single-run-gap detection (interval-based)

<!-- docs/backlog/P2-OBS_healthcheck_single_run_gap.md -->
<!-- Observability gap in scripts/intraday_healthcheck.py v0.1.0. Opened 2026-06-01. -->

**Priority:** P2 (observability)
**Opened:** 2026-06-01
**Source:** intraday_healthcheck.py v0.1.0 verification (2026-06-01)

## Problem

`intraday_healthcheck.py` v0.1.0 flags low coverage only below 80%
(`COVERAGE_ALERT_FRACTION`). With 20 expected runs/day, a SINGLE missed run is
19/20 = 95% and passes as HEALTHY. So a single silent run-gap (e.g. a cron fire
that never executed, with no fatal log line) is undetectable by coverage alone.

## Evidence

- 2026-05-28 had exactly one fatal run -> 19/20 = 95% coverage -> would be
  HEALTHY on coverage; it was caught only via the log fatal line.
- A missing run with NO accompanying log entry would slip through entirely.

## Proposed remediation

Add an interval-based gap check independent of the coverage ratio: read today's
`run_at` timestamps, sort, and flag any consecutive gap exceeding the cron cadence
(~15 min) plus tolerance (e.g. > 20 min) within the active window. Report the
specific missing slot(s) rather than just a percentage. This catches single-run
gaps and does not depend on the log.

## Acceptance

- A day with exactly one missing scheduled run (and no fatal log line) is flagged
  with the missing time slot identified.
- No false positive on normal days (cadence gaps all <= tolerance).
- Half-day / holiday handling deferred to v0.2 trading-calendar integration
  (out of scope here; see note).

## Note (related scope, not this item)

v0.1.0 assumes 20 runs/day and is blind to half-day sessions, typhoon closures,
and make-up trading days. Trading-calendar integration (reuse
`utils.trading_dates` / `resolve_as_of`) is a separate v0.2 enhancement.

## Related

- `scripts/intraday_healthcheck.py`, P1-OBS (monitor self-alert).
