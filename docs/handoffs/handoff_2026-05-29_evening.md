# Helios Session Handoff — 2026-05-29 (Evening)

**Session:** trend_pullback_v1 + pipeline regime/feature compute + TAIEX Shioaji migration
**HEAD:** `59e17d3` (pushed to origin/main)
**Prior HEAD:** `e1fcc00` (start of session)

---

## 1. Commits This Session

| Commit | Content |
|--------|---------|
| `b72c891` | feat: trend_pullback_v1 strategy + daily pipeline regime/feature compute |
| `7fb867e` | fix: daily pipeline regime compute + TAIEX Shioaji backfill |
| `59e17d3` | feat: TAIEX snapshot fetch integrated into shioaji_download_daily |

---

## 2. trend_pullback_v1 Strategy — LIVE

### Files

| File | Lines | Purpose |
|------|-------|---------|
| `strategies/trend_pullback/__init__.py` | 30 | Public API |
| `strategies/trend_pullback/config.py` | 61 | Frozen dataclass, all thresholds |
| `strategies/trend_pullback/types.py` | 68 | PullbackCandidate, PullbackPriority |
| `strategies/trend_pullback/screener.py` | 240 | SQL → tercile → filter → rank |
| `strategies/trend_pullback/signal_generator.py` | 169 | Dedup → conflict resolution → emit |
| `scripts/process_entries.py` | 611 | Dual-pass: breakout + pullback, shared budget |

### Entry Rule (production)

```
IF  beta_adj_rs_20d ∈ RS_T3 (≥ 67th percentile cross-sectional)
AND dist_above_ma20_atr < 0
AND market_regime ≠ "bear"
AND beta_60 ≥ Beta_T2 (≥ 33rd percentile)
THEN signal = trend_pullback_v1
```

### Priority Classification

| Zone | dist range | Hit% (20d) | Priority |
|------|-----------|------------|----------|
| Deep pullback | dist < -1 ATR | 59.3% | HIGH |
| Shallow pullback | -1 ≤ dist < 0 | 55.0% | NORMAL |
| Dead zone | dist ≥ 0 | — | REJECTED |

### Conflict Resolution (breakout vs pullback same symbol)

1. Existing OPEN position → reject new signal
2. Higher score wins
3. Tie → prefer pullback only if dist < -1 AND beta T3

### Verification Results

| Date | Candidates | Symbols |
|------|-----------|---------|
| 2026-05-25 | 1 | 7750 (NORMAL) |
| 2026-05-28 | 2 | 2354 (score 8.24), 8210 (score 10.51) |

8210 matches handoff prediction. Candidates vary by date (expected — stocks cross MA20 daily).

---

## 3. Daily Pipeline — 10 Steps

```
Step 0: prev-run check
Step 1: trading day
Step 2: T+1 fill readiness
Step 3: data freshness
Step 4a: regime recompute (TAIEX → market_regime) ~0.1s
Step 4b: bullish + bearish features recompute ~115s
Step 5: expire stale pending signals
Step 6: exit scan
Step 7: entry pipeline (breakout pass 1 + pullback pass 2)
Step 8: queue entry intents for T+1 submission
Step 9: reconciliation
```

**HELIOS_SKIP_FEATURE_COMPUTE=1** skips Step 4a+4b (for cron where features already computed upstream).

---

## 4. TAIEX Data Pipeline — Migrated to Shioaji

### Problem Solved

TAIEX in `daily_price` was stale (only to 2026-05-25) because:
- `shioaji_download_daily.py` excluded TAIEX (daily_quotes API doesn't include index data)
- `download_daily.py` (FinMind) was no longer being run after Shioaji migration

### Solution

| Component | Method | Contract |
|-----------|--------|----------|
| Historical backfill | `backfill_taiex.py` — kbars aggregated to daily | `Indexs.TSE.TSE001` |
| Daily cron | `shioaji_download_daily.py` — snapshot after stock download | `Indexs.TSE.TSE001` |
| daily_run Step 4a | `compute_phase_regime()` — recomputes regime from fresh TAIEX | reads `daily_price` |

### Key Discovery

Shioaji has index contracts under `api.Contracts.Indexs.TSE`:
- TSE001 = 加權指數 (TAIEX)
- Requires `fetch_contract=True` at login (separate from stock daily_quotes which uses `fetch_contract=False`)
- `api.snapshots([contract])` returns today's OHLCV
- `api.kbars(contract, start, end)` returns minute bars for date range

---

## 5. Cron Configuration (Updated)

```
15:30  auto_backup.sh
16:00  shioaji_download_daily.py (stocks + TAIEX snapshot)
       → build_adjusted_prices.py
       → compute_features.py (daily_features + market_regime)
       → compute_bearish_features.py
       → compute_bullish_features.py
       → daily_run.py --as-of prev_trading_day
         (HELIOS_SKIP_FEATURE_COMPUTE=1 — Step 4 skipped, already computed above)
16:05  run_signal_preview.py
16:30  find_bearish_stocks.py
16:35  score_short_candidates.py
16:40  find_bullish_setups.py
19:30  run_evening_digest.py
08:30  execution_submitter.py --mode submit
09:05  execution_submitter.py --mode cancel
09:05-13:50  intraday_monitor.py (every 15 min)
```

**Change this session:** `HELIOS_SKIP_EXIT_SCAN=1` → `HELIOS_SKIP_FEATURE_COMPUTE=1`

---

## 6. v0.1.18 Review Cycle Summary

Multiple review rounds with P0 fixes before merge:

| Round | Key Fix |
|-------|---------|
| 1 | update_order_spec → mark_submitted order (was InvalidTransition) |
| 2 | _shioaji_login takes AccountConfig, not global Settings |
| 3 | raw SQL confirm → order_journal.confirm_submission() |
| 4 | scan_and_exit + lifecycle.py account_id threading |
| 5 | get_position readback → get_position_for_account |
| 6 | expiry.py confirmed NOT a blocker (signals table, pre-execution) |

All 12 callers with positions/order_journal now have account_id threading.

---

## 7. Key File Locations

| Path | Purpose |
|------|---------|
| `strategies/trend_pullback/` | Pullback strategy (5 files) |
| `scripts/process_entries.py` | Dual-pass entry pipeline |
| `scripts/daily_run.py` | 10-step pipeline with regime + features |
| `scripts/backfill_taiex.py` | TAIEX historical backfill via kbars |
| `scripts/shioaji_download_daily.py` | Daily stock + TAIEX ingest |
| `scripts/smoke_test_v0_1_18.py` | v0.1.18 smoke test (27 checks) |

---

## 8. Pending Backlog

### P1 — Next Session

| Item | Type | Notes |
|------|------|-------|
| Phase B bearish research | Research | dist_below refinement, bounce fade, RS_T1 trap |
| execution_submitter --account in cron | Ops | Currently defaults to first account; add explicit --account before 2nd account |

### P2 — Deferred

| Item | Type | Notes |
|------|------|-------|
| #27 two-phase SUBMITTED verification | Production | Broker order state machine |
| #28 broker adapter multi-account | Production | LiveBroker(account_config=...) |
| #29 signals table account_id | Schema | Pre-execution layer, not blocking |
| #21 daily_quotes_partial | Data | Row count < 1500 threshold |
| MBP M2 Max migration | Infra | Hybrid recommended: research on MBP, execution on nexus. Shioaji ARM64 unverified. |

---

## 9. Remote Access

```
Nexus:  ssh tradeagent@nexus → cd ~/projects/helios
Kairos: ssh tradeagent@100.116.99.68 → cd ~/projects/kairos
PATH:   export PATH=/home/tradeagent/.local/bin:$PATH
```
