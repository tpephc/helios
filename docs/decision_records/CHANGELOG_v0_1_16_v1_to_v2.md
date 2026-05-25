# Helios v0.1.16 — Advisor Review Integration Change Log (v1 → v2)

**Date:** 2026-05-24
**Reviewers:** Advisor C, Advisor D, Advisor K
**Integration author:** DEV C
**Decisions taken by:** Veronica (4 decisions locked)

---

## Executive summary

V1 v0.1.16 artifacts received three independent advisor reviews. The
reviews surfaced **11 P0 issues** (consolidated), of which **one
(K-P0-1) was catastrophic-class**: a lots-vs-shares unit-comparison bug
in `LiveBroker._submit` that would have caused permanent broker-vs-Helios
position desync on any partial fill. The bug had correct types, correct
syntax, and would have likely passed full-share fill tests. It was
detectable only by tracing units across the broker SDK boundary.

V2 integrates all accepted advisor findings, applies four locked
decisions, and adds a reviewer checklist to defend against re-occurrence.

---

## Decisions locked (with rationale)

### Decision 1 — Unit-confusion fix path: **A+rename**

- All quantity fields gain unit-bearing names:
  `requested_qty` → `requested_lots` (lots)
  `filled_qty` → `filled_shares` (shares)
- `SHARES_PER_LOT = 1000` defined once in `execution/order_types.py`.
- Comparisons convert explicitly at the boundary; mixed-unit
  comparisons are now banned by reviewer checklist.

Trade-off accepted: when v0.1.17 introduces IntradayOdd (shares-native),
`requested_lots` becomes inapplicable for that path; v0.1.17 will add a
parallel `requested_shares` column at that time.

### Decision 2 — Sim cap conflict: **i + ii combined**

- Week-1 sim uses `PreTradeGuard.sim_relaxed()`: 1M per-order, 3M daily.
- Telegram daily summary shows `guard_mode=sim_relaxed`.
- Pre-live deployment checklist (§6 execution_model.md) MUST verify
  revert to production thresholds.

### Decision 3 — Reconcile broker integration: **a (BrokerAdapter Protocol)**

- New `execution/broker_adapter.py` defines `BrokerAdapter` Protocol.
- LiveBroker implements via public `login_session` (contextmanager),
  `fetch_trades`, `fetch_holdings`.
- `reconcile_fills.py` no longer imports `shioaji` or calls `_login`
  directly.

### Decision 4 (extra) — Reconcile matching key: **ReconcileCandidate (human-review)**

- `broker_order_id` cannot be sole matching key (sim empty / transport
  failure / partial-deal aggregation).
- v0.1.16 surfaces fuzzy-match candidates with: `symbol`, `side`,
  `broker_submitted_date`, `broker_filled_shares`, `broker_avg_price`,
  `helios_intent_at`, `time_distance_seconds`, confidence tier.
- Not auto-merged. v0.1.17 may add policy.

---

## Finding-by-finding resolution table

### P0 (11 items resolved)

| # | Finding | Source | Severity | Resolution |
|---|---|---|---|---|
| 1 | `total_deal_qty >= requested_qty` mixed units → 1-share fill marks FILLED | **K-P0-1** ★ | catastrophic | `live_broker.py:469-472` — explicit `requested_shares = requested_lots * SHARES_PER_LOT`; share-vs-share comparison. DB CHECK + result `__post_init__` invariants mirror. Reviewer checklist §11 codifies prevention. |
| 2 | PARTIAL `__post_init__` invariant `0 < x < 1` empty in integers | **K-P0-2** | P0 | `order_types.py:308` — invariant now `0 < filled_shares < requested_shares` (share-equivalent). |
| 3 | Schema missing `fill_date`; reconcile uses `intent_at` (always misses T+1 orders) | **C-P0-1** / K-P1-4 / D-P0-3 | P0 | Migration adds `fill_date DATE NOT NULL`. New `list_orders_by_fill_date`. Old `list_orders_for_date` deprecated with `DeprecationWarning`. reconcile uses fill_date. |
| 4 | PreTradeGuard daily-count off-by-one (record_intent before check, self-counted) | **C-P0-2** | P0 | `count_today_orders` / `sum_today_notional` accept `exclude_order_id`. PreTradeGuard `check_order(exclude_order_id=...)`. LiveBroker passes `exclude_order_id=order_id`. |
| 5 | `record_intent` writes `notional=0` (limit_price=None at intent time); daily notional cap broken | **C-P0-3** + D-P1-4 + K-P0-1 | P0 | `record_intent` takes caller-computed `notional`. New `update_order_spec` writes `(limit_price, notional)` after contract lookup, before guard. Guard uses real notional. |
| 6 | Common lot ~600K TWD vs `max_order_notional=5000`; smoke test impossible | **C-P0-4** | P0 | `PreTradeGuard.sim_relaxed()` classmethod (1M/3M). `daily_run` auto-selects via `cfg.shioaji_simulation`. Production checklist in execution_model.md §6. |
| 7 | `startup_recovery` 16-hr wall-clock stale detection misfires across weekends | **C-P0-5** | P0 | `list_stale_submitted_by_fill_date(expired_on_or_before=last_trading_day)`. `_last_completed_trading_day(as_of, is_trading_day)` walks backward. `utils/trading_calendar.py` stub. |
| 8 | `mark_polled` doesn't check `submitted_at IS NOT NULL` (allows corruption) | **D-P0-1** | P0 | `order_journal.mark_polled` raises `InvalidTransition` when `submitted_at is None` despite `status=SUBMITTED` (journal-corruption guard). |
| 9 | `reconcile_fills.py` calls `LiveBroker._login()` (private); rate-limit risk; `import shioaji` leak | **D-P0-2** | P0 | New `BrokerAdapter` Protocol (`execution/broker_adapter.py`). LiveBroker implements with public `login_session` / `fetch_trades` / `fetch_holdings`. reconcile no longer touches shioaji. |
| 10 | Reconcile `action == "Buy"` against Shioaji enum → always False; all sides → SELL | **K-P1-3** | P0 (broken side classification = P0 in reconcile) | `_normalize_action_to_side` uses `is Action.Buy` identity with str-text fallback. Applied in adapter `fetch_trades`. |
| 11 | `broker_order_id` empty string from sim → reconcile match impossible | **K-P1-5** | P0 (silent reconcile failure) | `_normalize_broker_order_id` in journal: empty string → None. `find_by_broker_order_id(None)` returns None. `mark_submitted` normalizes on write. |

### P1 (8 items resolved)

| # | Finding | Source | Resolution |
|---|---|---|---|
| 12 | `api.Contracts.Stocks[symbol]` unstable for OTC | C-P1-6 | `_resolve_stock_contract` tries TSE then OTC; logs failure. |
| 13 | Lots/shares unit fields ambiguous | C-P1-7 | Decision 1: rename (folded into K-P0-1 fix; no separate v2 task). |
| 14 | reconcile needs fuzzy candidate report | C-P1-8 / K extra | `ReconcileCandidate` dataclass; `_maybe_add_fuzzy_candidate`; `to_console` renders. |
| 15 | startup_recovery per-order Telegram → alert fatigue | D-P1-7 | Single consolidated summary at end of recovery; per-order details to logger only. |
| 16 | `mark_partial` log level was warning | D-P2-a (treated as P1) | `logger.error` for operator-action signal. |
| 17 | `new_order_id` uses naive `datetime.now()` → wrong date in UTC envs | K-P2-a (treated as P1) | `ZoneInfo("Asia/Taipei")` everywhere (journal, live_broker, recovery). |
| 18 | `mark_polled` allows `filled_shares=0` with non-None `avg_fill_price` | K-P2-b | `mark_polled` validates `filled_shares=0 → avg_fill_price IS NULL`. |
| 19 | sim_fallback includes SUBMITTED in `expecting_trades` (false positive) | K-P2-f | `expecting_trades` only counts FILLED+PARTIAL. |

### P2 (3 items resolved)

| # | Finding | Source | Resolution |
|---|---|---|---|
| 20 | Migration legacy backup no `IF EXISTS` guard | K-P2-d | `DROP TABLE IF EXISTS orders_legacy_pre_v0_1_16` added. |
| 21 | reconcile `broker_by_id.pop(None, None)` semantically odd | K-P2-e | Build broker_by_id index filters out None keys; `pop` guarded. |
| 22 | `_STATUS_POLL_SLEEP=2s` too short for Shioaji deal propagation | D-P2-e | `poll_sleep_sec` constructor parameter; default raised to 5.0s. |

### P3 (2 items resolved)

| # | Finding | Source | Resolution |
|---|---|---|---|
| 23 | execution_model.md §9.1 references undefined `PositionCloseError` | K-P3-a | Marked pseudo-code with "to be defined in v0.1.17" annotation. |
| 24 | "grandfathered" misleading for active code path | K-P3-b | Replaced with "active known risk, monitored" (§9.1, §10.5). |

### CLI feature

| # | Finding | Source | Resolution |
|---|---|---|---|
| 25 | reconcile_fills needs `--send-telegram` flag | D-P2-b | Added; sends `report.to_telegram()` (top 5 critical findings) when set. |

---

## Push-backs (advisor findings NOT adopted)

| Finding | Source | Rationale |
|---|---|---|
| Per-order session-level notional race | D-P1-5 | Resolved by C-P0-2 `exclude_order_id` fix; DuckDB `with connect()` auto-commits, no separate race remains. |
| `__post_init__` PARTIAL too strict | D-P1-6 | D acknowledged "目前沒問題"; v2 fix is unit-aware so concern is moot. |
| pre_trade_guard circular import | D-P2-c | Verified dependency is unidirectional (`pre_trade_guard → order_journal → order_types`); no reverse. |
| metadata stored as TEXT not JSON type | D-P2-d | DuckDB JSON column is structurally equivalent to TEXT + `CHECK json_valid(metadata)`; no functional gain from change. |
| `check_order_notional` should include commission | K-P2-c | Commission is ~0.15% scale; not the kind of safety per-order cap addresses. Adding it muddies cap's semantic. |
| SUBMITTED `notional` should not count toward daily cap | K-P1-6 | The cap is **committed capital**, not **fills**. SUBMITTED at broker has reserved buying power; excluding it would let operator commit unlimited capital across the day. Design intent documented in `pre_trade_guard.py:sum_today_notional` docstring. |

---

## Reviewer checklist (mandatory going forward)

Added to `docs/execution_model.md` §11. Every PR touching `execution/`
MUST tick:

```
QUANTITY UNITS:
[ ] Is the quantity unit normalization boundary explicit?
[ ] Is the broker quantity unit documented at the import boundary?
[ ] Do all quantity comparisons in the diff use the same unit on both sides?
[ ] Are derived quantities centralized in ONE place?

STATE MACHINE:
[ ] Do all journal mutations go through storage.order_journal?
[ ] Are state transitions allowed by _LEGITIMATE_TRANSITIONS?
[ ] Are terminal-state checks consistent (use OrderStatus.is_terminal)?

EXECUTION REALISM:
[ ] Does code distinguish API-call-success from fill-success?
[ ] Are SUBMITTED-but-unfilled orders handled (not assumed FILLED)?

OPERATIONAL:
[ ] Is the change safe under restart (startup_recovery handles it)?
[ ] Are critical findings surfaced via Telegram (not just logged)?

UNIT CONFIDENCE:
[ ] If I wrote a 1-share PARTIAL fill test against this code path,
    would it pass?
```

The last item is the **K-P0-1 regression test**. It would have caught
v1's catastrophic bug.

---

## Files changed (v1 → v2)

| Path | Δ lines (approx) | Nature |
|---|---|---|
| `migrations/0002_orders_journal_v0_1_16.sql` | +30 | fill_date column, rename, idempotent backup |
| `execution/order_types.py` | +50 | SHARES_PER_LOT constant, rename, derived `requested_shares`, unit-aware invariants |
| `storage/order_journal.py` | +120 | fill_date threading, caller-computed notional, `update_order_spec`, `list_orders_by_fill_date`, `list_stale_submitted_by_fill_date`, ZoneInfo, defensive checks |
| `execution/pre_trade_guard.py` | +80 | `sim_relaxed` classmethod, `exclude_order_id` plumbing, caller-computed notional, SUBMITTED-inclusion docstring |
| `execution/broker_adapter.py` | +130 (new file) | BrokerAdapter Protocol, normalized dict shapes |
| `execution/live_broker.py` | +200 | K-P0-1 unit fix, C-P0-3 notional flow, C-P1-6 contract lookup, BrokerAdapter implementation, configurable poll sleep |
| `scripts/startup_recovery.py` | +60 | trading-calendar-based stale detection, consolidated Telegram summary |
| `scripts/reconcile_fills.py` | +180 | fill_date semantics, BrokerAdapter usage, ReconcileCandidate model, fuzzy match, `--send-telegram` |
| `scripts/daily_run_v0_1_16_patch.md` | +40 | Step 0a passes as_of+is_trading_day, Step 7 sim_relaxed wiring, summary block updates |
| `docs/execution_model.md` | +250 (full rewrite of relevant sections) | UNIT CONVENTION section, sim_relaxed docs, BrokerAdapter docs, ReconcileCandidate docs, §11 reviewer checklist |
| `execution/live_broker_v0_1_2_patch.md` | +200 | v2 test plan with K-P0-1 regression test, BrokerAdapter verification, Q1/Q2/Q3 |

---

## Open items (deferred to v0.1.17)

1. **`lifecycle.py:174` synthetic exit price fallback** (active known
   risk, monitored). v0.1.17 P1: source exit_price from order journal.
2. **PaperBroker lowercase side strings** (`'buy'`/`'sell'`). v0.1.17
   aligns to `OrderSide` enum.
3. **PARTIAL auto-retry policy** — currently operationally terminal.
4. **Reconcile auto-merge policy** for ReconcileCandidate fuzzy
   matches. v0.1.17 may add.
5. **Trading calendar with Taiwan public holidays.** v0.1.16
   `utils/trading_calendar.py` is weekday-only stub; operator MUST
   replace before `live_trading_enabled=True`.
6. **Comprehensive unit tests** for all journal state transitions and
   K-P0-1 partial-fill scenarios. v0.1.16 ships with the smoke-test
   plan in `live_broker_v0_1_2_patch.md`; full test suite is v0.1.17.

7. **`daily_run` Step 7 should expire signal on broker FAILED.**
   Discovered during v0.1.16 v2 smoke test (2026-05-24): when LiveBroker
   returns FAILED (e.g. `contract_not_found` for OTC symbols Shioaji sim
   does not recognize), `exec_summary["failed"]` increments but the
   underlying PENDING signal remains active until `timeout_at` (30 min
   later) or next daily_run Step 4 expiry. Risk: 30-min dirty-state
   window where the approval listener could process a signal whose order
   already FAILED. Fix: in daily_run Step 7's failed branch, also call
   `storage.signals.update_approval(signal_id, "TIMEOUT",
   expired_reason=f"broker_failed:{result.error_code}")`. Single-line
   addition; deferred to v0.1.17 to keep v0.1.16 v2 scope tight.

8. **LiveBroker `_resolve_stock_contract` may need ETF / non-stock
   contract sources.** Discovered during v0.1.16 v2 smoke test
   (2026-05-24): symbol `6139` failed contract lookup in both
   `Contracts.Stocks.TSE` and `Contracts.Stocks.OTC` (FAILED.broker_reject,
   error_code=`contract_not_found`). Need to determine whether 6139 is
   an ETF / index / warrant living under a different Shioaji namespace
   (e.g. `Contracts.ETFs.TSE`, `Contracts.Indices.TSE`,
   `Contracts.Warrants.TSE`). Fix: extend `_resolve_stock_contract` to
   probe additional namespaces. Until fixed, strategies may emit signals
   for symbols LiveBroker cannot resolve, surfacing as FAILED rather
   than executed. Also possible root cause: Shioaji sim contract
   universe is narrower than production — verify against live broker
   before deploying production thresholds.



9. **`daily_run` cron `--as-of yesterday` vs last-trading-day**:
   Cron uses `$(date --date=yesterday +%Y-%m-%d)`, which on Monday
   produces Sunday. v2 Step 1 (`is_trading_day`) correctly declines,
   writing `last_run.json status=declined_preflight`. Acceptable safety
   behavior but creates one declined_preflight run per week (Monday).
   v0.1.17 could replace with a `--as-of last_trading_day` helper
   that consults `utils.trading_calendar`. Low priority; not on
   critical path.

10. **Shioaji sim API key lacked `place_order` permission.**
    **Status: RESOLVED 2026-05-25 (same-day rollover).**

    *Symptom (2026-05-25 08:32, simulation_test.sh + 08:35 minimal repro):*
    `api.login` succeeded (`Session up`), `api.stock_account.signed`
    returned `False` (sim env does not implement CA signing, expected
    sim limitation), `api.place_order` raised
    `TokenError: StatusCode 401, Detail: Token doesn't have permission`.
    Reproducible with raw SDK call without helios involvement; confirmed
    that `signed: False` itself is NOT the cause — skipping `activate_ca`
    still produced 401.

    *Root cause:* the API key in `.env` at that time had been issued
    without sim trading scope. Re-issued key (`.env` updated
    2026-05-25 08:43) included the required scope.

    *Verification (2026-05-25 08:48):* minimal repro with new key
    returned `OrderState.StockOrder ordno='00014D' status=Status.Submitted`,
    confirming sim trading path is functional end-to-end (login → contract
    lookup → place_order → status poll). `signed: False` persists (sim
    limitation; orthogonal to trading authorization).

    *Original concern:* without trading scope, v0.1.16 v2 LiveBroker
    would route every entry signal through Step 7 to FAILED.broker_reject
    (token_error) and block production validation, despite v2 schema /
    journal / state machine / K-P0-1 defense / sim_relaxed guard being
    structurally correct. Concern dismissed by verification above.

    *Lessons for future archaeology:*
    - `signed: False` in sim mode is normal and should NOT be treated as
      a blocker. LiveBroker should not gate behavior on
      `stock_account.signed` in sim mode (current code does not, by
      design; preserve this).
    - Shioaji `TokenError 401` on `place_order` is a permission-scope
      issue, not a CA/activation issue. When the symptom appears, first
      confirm the API key has the required trading scope (check Shioaji
      dashboard or re-issue key) before debugging CA flow.
    - The test order placed during verification (Shioaji sim ordno
      00014D, 2890 永豐金 1 lot LMT @29.1, trade_date 2026-05-25) lives
      only on the Shioaji sim platform; helios reconcile filters by
      `trade_date == fill_date`, so this trade is permanently invisible
      to v2 reconcile pipeline.

11. **`intraday_monitor` cron `PATH` bug (pre-existing).**
    **Status: RESOLVED 2026-05-25 09:34.**

    *Discovery:* during 2026-05-25 follow-up after v2 deploy, found
    `logs/intraday_monitor.log` Birth date was 2026-05-25 09:05 (today)
    with content `/bin/sh: 1: uv: not found`. Compared with other cron
    lines that use absolute path `/home/tradeagent/.local/bin/uv`, the
    intraday_monitor cron line used bare `uv` which is not on cron's
    default `$PATH` (`/usr/bin:/bin`).

    *Root cause:* the cron line `5,20,35,50 9-13 * * 1-5 cd
    ~/projects/helios && uv run python scripts/intraday_monitor.py ...`
    was authored without absolute-path awareness. Bug pre-dates v0.1.16
    deployment — v2 restore preserved the original (broken) form
    verbatim. Implication: intraday_monitor has likely never executed
    successfully in production cron environment; trailing stop monitoring
    has been silently inactive since the cron was first installed.

    *Fix (2026-05-25 09:34):* updated cron line to use absolute paths,
    matching other cron entries:
    `5,20,35,50 9-13 * * 1-5 cd /home/tradeagent/projects/helios &&
    /home/tradeagent/.local/bin/uv run python scripts/intraday_monitor.py
    >> logs/intraday_monitor.log 2>&1`.

    *Verification (2026-05-25 09:35):* first post-fix cron triggered
    correctly. `logs/intraday_monitor.log` recorded 3 structlog events
    (start / no_open_positions / complete). `intraday_monitor_runs` DB
    row written. Duration 2ms. Lock file created at `.lock/intraday_monitor.lock`
    and released.

    *Pre-existing log artifact:* `logs/intraday_monitor.log.pre_path_fix_*`
    preserved as 52-byte evidence of the failure mode.

    *Lessons:*
    - All cron jobs invoking project tools must use absolute paths
      (`/home/tradeagent/.local/bin/uv`, etc.). Relative names rely on
      shell `$PATH` which cron does not populate.
    - Lack of `OPEN` positions during the bug's lifetime masked the
      failure — silent dependency on rare states is a monitoring blind
      spot. v0.1.17 should add a smoke test that asserts each cron job
      writes an expected log entry within N seconds of trigger.

---

## Sign-off

| Owner | Sign-off requirement |
|---|---|
| Implementer | Apply migration on dev/sim DB; smoke test passes Q1/Q2/Q3. |
| Reviewer | Tick reviewer checklist §11 for execution PR. |
| Operator | Verify Telegram surfaces sim_relaxed and recovery summary correctly. |
| Pre-live | Verify Step 7 uses production guard; trading_calendar replaced. |
