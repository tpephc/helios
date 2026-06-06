# Helios Session Handoff — 2026-05-31

**Session:** Tracker v2 migration + canonical dedup + evening digest integration
**HEAD:** 4 commits pushed this session (exit contract + tracker v2 + digest + handoffs)
**Prior HEAD:** `cd951c6`

---

## 1. Files Changed This Session

| File | Change |
|------|--------|
| `research/forward_return_tracker.py` | v0.3.6: canonical dedup, cluster bootstrap CI, forced resolution, calendar integrity gate |
| `research/tracker_digest.py` | v1.0.0: new — evening digest section 4 |
| `scripts/run_evening_digest.py` | section 4 added (tracker summary, lazy import) |
| `scripts/check_benchmark_calendar_gap.py` | v1.2.0: new — runbook Phase A gate |
| `scripts/migrate_tracker_v2.py` | v1.1.0: new — schema DDL migration tool |
| `pyproject.toml` | added `exchange_calendars` dependency |
| `strategies/exit/time_stop.py` | v0.1.0: new — 20 trading day max holding |
| `strategies/exit/regime_exit.py` | v0.2.0: bear-only exit |
| `strategies/exit/trailing_stop.py` | v0.2.0: entry_atr fixed stop |
| `strategies/exit/base.py` | v0.2.0: holding_trading_days field |
| `scripts/run_exit_scan.py` | v0.2.0: exit contract integration |
| `docs/operations/tracker_v2_migration.md` | v1.0.1: production migration runbook |

---

## 2. Tracker v2 Migration — Completed

### What was done
- Schema migration (ALTER TABLE + 5 new columns) executed on production DB
- All v1 + v2 rows deleted; full rebuild under v0.3.6

### Final observation state
```
forward_return_observations
  schema_version : 2 (all rows)
  breakout       : 11 canonical signals in progress
  pullback       : 3 canonical signals in progress
  resolved       : 0 (need 20 elapsed trading days)
```

### Upstream duplicate issue (Layer 2 fixed, Layer 1 pending)
```
signals table: trend_breakout_v1 raw=25, dedup=11 (14 duplicate rows)
```
`_load_signals()` now uses ROW_NUMBER() CTE dedup. Layer 1 fix
(`find_bullish_setups.py` pre-insert existence check) is P1 backlog.

---

## 3. Key Design Decisions

### Canonical signal set
`_load_signals()` → `canonical_ids = frozenset(signals_df["signal_id"].astype(str))`

Single source of truth. `_load_signal_progress()`, `resolved_df`,
`inprogress`, `_find_stuck_signals()` all filter to this set.
No separate query — no race condition.

### Tracker v2 invariants (frozen)
```python
# LONG_ONLY_INVARIANT — do not inherit for Phase B
# case-3 terminal: net_return_t1 = -1.0, gross_return_t1 = -1.0
# entry_slippage_bps = 5.0, cost_bps = 40.0 (stored per row)
# resolution trigger: elapsed TWSE trading days >= 20 (not price count)
```

### Evening digest
- Tracker section added as section 4 in `run_evening_digest.py` (19:30)
- Import is lazy (inside try block) due to `research` not in pyproject packages
- `tracker_digest.py` uses same canonical dedup as tracker

---

## 4. Operational Fixes This Session

### Cron timing conflict (fixed)
```
# Before: both at 09:05
5 9  * * 1-5  execution_submitter --mode cancel
5,20,35,50 9-13 * * 1-5  intraday_monitor

# After: intraday_monitor shifted +2 min
5 9  * * 1-5  execution_submitter --mode cancel
7,22,37,52 9-13 * * 1-5  intraday_monitor
```

### Position last_close manual fix (2026-05-29)
```
4919 新唐: last_close 188.5 → 191.5, last_updated_date → 2026-05-29
2891:      last_close  59.3 →  59.3  (already correct date, confirmed)
```

---

## 5. Backlog

### P1 — Near-term

| Item | Notes |
|------|-------|
| `find_bullish_setups.py` pre-insert existence check (Layer 1) | Prevents signals table duplicate inflation |
| EOD position price update gap | `positions.last_close` not updated by EOD pipeline after market close; only intraday_monitor (live) updates it |

### P2 — Deferred

| Item | Notes |
|------|-------|
| Constants centralization (`config/constants.py`) | `MAX_HOLDING_DAYS`, `ROUND_TRIP_COST_BPS`, `ENTRY_SLIPPAGE_BPS` duplicated across tracker/digest/harness |
| Strategy Gate attribution report | Zero real closed positions; build framework when first positions close |
| `tracker_digest.py` Chinese header alignment | `wcwidth` fix for monospace column alignment with CJK chars |

### P3 — Research queue (ordered by executability × value)

| Phase | Research | Status |
|-------|----------|--------|
| R1 | RS Persistence Decay | **Next session — start immediately** |
| R2 | Failed Breakdown Quality (prototype, no schema change) | After R1 |
| R3 | Regime-Conditioned Entry | After resolved n≥30 |
| R4 | Signal-Exit Interaction | After real closed positions exist |
| R5 | Pullback Timing Alpha | Feature engineering required |
| R6 | Bearish Phase B | Gate: breakout resolved n≥30 AND first signal-gate report |

---

## 6. Next Session Scope — RS Persistence Decay

### Pre-check before starting
```python
# Confirm daily_features history depth
SELECT MIN(date), MAX(date), COUNT(DISTINCT date), COUNT(DISTINCT stock_id)
FROM daily_features
WHERE rs_percentile IS NOT NULL
```
Need ≥ 60 trading days for stale group to exist.

### Research questions

**Study A — RS age effect**
```
Fresh:  RS_T3 持續 ≤ 5d  (recently entered Q5)
Mature: RS_T3 持續 6-20d
Stale:  RS_T3 持續 60d+

Compare: 20d / 40d / 60d forward return by age group
```

Definition of "age": consecutive days with RS percentile ≥ 80.
Operationalize with window function on `daily_features.rs_percentile`.

**Study B — RS acceleration**
```
Improving: RS percentile 80→95 (rising momentum)
vs
Plateau:   RS percentile 95→95 (already strong)

Hypothesis: improving > plateau for 20d forward return
```

### Output target
`research/rs_persistence_decay.py` — standalone analysis script.
Output: static report (print or Parquet). No schema changes required.

---

## 7. Evidence Pipeline Status

```
signal → tracker (canonical dedup) → bootstrap CI → digest
```

All stages operational. Evidence accumulation in progress.

**Next milestone:** ~2026-06-16, first batch of breakout signals reaches
20 elapsed trading days → first resolved observations → first real CI.

---

## 8. System State

### Cron (current)
```
08:30  execution_submitter --mode submit
09:05  execution_submitter --mode cancel
07,22,37,52 9-13  intraday_monitor (every 15 min, shifted +2 from 09:07)
15:30  auto_backup.sh
16:00  shioaji_download_daily → build_adjusted_prices → compute_features
       → daily_run (Step 6: run_exit_scan, Step 7: process_entries)
16:05  run_signal_preview
16:10  forward_return_tracker (v0.3.6)
16:30  find_bearish_stocks
16:35  score_short_candidates
16:40  find_bullish_setups
19:30  run_evening_digest (4 sections: signal preview + breach + approach + tracker)
```

### Remote access
```
Nexus:  ssh tradeagent@nexus → cd ~/projects/helios
Kairos: ssh tradeagent@100.116.99.68 → cd ~/projects/kairos
PATH:   export PATH=/home/tradeagent/.local/bin:$PATH
```

### DB path
```
/home/tradeagent/projects/helios/data/_storage/helios.duckdb
```
Note: `data.database.connect()` reads from `get_settings().db_path`.
`HELIOS_DB_PATH` env var has no effect on this codebase.
Dry-run requires modifying the settings config directly.
