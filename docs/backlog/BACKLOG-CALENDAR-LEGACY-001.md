# BACKLOG-CALENDAR-LEGACY-001

**Title:** Audit and migrate legacy `utils/trading_calendar.py` consumers
**Status:** OPEN
**Priority:** Medium (no immediate production risk identified; latent
              semantic-drift risk)
**Owner:** TBD (Helios platform, not Track C)
**Created:** 2026-06-22 (via Track C Step 1-0B discovery)
**Track C linkage:** Track C Step 1 enforces Tier 1 only (forbid imports
                     in `ud_ratio_21d`). This backlog covers Tier 2
                     (audit + migrate) and Tier 3 (deprecate + delete).

## Problem

Helios has two co-existing trading-calendar modules:

| Module                         | Status      | Behaviour                              |
| ------------------------------ | ----------- | -------------------------------------- |
| `market/trading_calendar.py`   | Canonical   | v0.2.0; three-layer hybrid (TWSE DB +  |
|                                | (v0.2.0)    | XTAI + static fallback). Honours       |
|                                |             | typhoon closures, CNY, statutory       |
|                                |             | holidays.                              |
| `utils/trading_calendar.py`    | Legacy stub | Weekday-only. Self-described in its    |
|                                |             | own docstring as needing replacement   |
|                                |             | before production use.                 |

At least one production path imports both:

```python
# scripts/daily_run.py
from market.trading_calendar import is_trading_day, next_fillable_day  # line 33
...
from utils.trading_calendar import is_trading_day as _is_trading_day   # line 116
```

## Risk Assessment

- Weekday-only stub returns True for Taiwan holidays → could
  classify a closed day as a trading day
- `scripts/daily_run.py` aliasing ambiguity
- Future contributors may import the legacy stub thinking it is
  canonical (name collision)

No identified P0 production bug at time of writing, but the asymmetry
is a latent semantic-drift hazard.

## Action Plan

### Phase A — Audit (read-only)

1. Inventory all imports of `utils.trading_calendar` across repo
2. Inventory all imports of `utils.trading_dates` (related legacy)
3. For each consumer, classify intent:
   - (a) Wants calendar truth → migrate to `market.trading_calendar`
   - (b) Wants data-availability date → keep
     `utils.trading_dates.resolve_as_of`
   - (c) Only needs weekday filter → still migrate for consistency

### Phase B — Migrate

For each (a)/(c) consumer:
- Replace import path
- Run targeted tests
- Spot-check production cron logs on next holiday

### Phase C — Deprecate

After migration:
- Add `DeprecationWarning` to `utils/trading_calendar.py`
- Run >= 1 month to catch missed consumers

### Phase D — Remove

After deprecation:
- CI lint rule banning legacy imports
- Delete legacy stub
- Update docs

## Track C Boundary

Track C Step 1 (ud_ratio_21d) enforces:
- `features/ud_ratio.py` MUST NOT import either legacy module
- PIT-11 enforces via AST inspection
- Spec v0.1.4 §12.4 lists forbidden imports

Track C does NOT touch this backlog item beyond that defence.

## Acceptance Criteria

- [ ] Phase A audit document in
  `docs/audits/calendar_legacy_audit.md`
- [ ] Phase B: all (a)/(c) consumers migrated
- [ ] Phase C: deprecation warning in place >= 1 month
- [ ] Phase D: legacy stub removed, CI rule active

## References

- `market/trading_calendar.py` v0.2.0 (canonical)
- `utils/trading_calendar.py` (legacy stub)
- `utils/trading_dates.py` (different semantic, may stay)
- `scripts/daily_run.py:116` (illustrative ambiguous import)
- Track C spec §12 (`docs/features/ud_ratio_21d_spec.md` v0.1.4)
