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

   **Status: SUPERSEDED 2026-05-25 by item #13.**

   *Root cause re-analysis (2026-05-25, v2.1 hotfix diagnosis):*
   The original assumption that 6139 might be an ETF / index / warrant
   in a non-stock namespace was **incorrect**. Direct Shioaji SDK
   verification 2026-05-25 confirmed 6139 (`亞翔`) is a regular TSE
   stock, found via `api.Contracts.Stocks.TSE.get('6139')`. The same
   verification against 4919, 2890, 2330, 2412 — all returned correct
   `Contract` objects via `.get()`.

   *Actual root cause (see #13):* `_resolve_stock_contract` used
   `symbol in tse` membership check. Shioaji's `StreamMultiContract`
   namespace does NOT implement `__contains__`; Python falls back to
   `__iter__` linear scan which iterates `Stock` objects (not keys),
   so `"6139" in tse` is permanently False regardless of whether 6139
   exists. All `submit_buy`/`submit_sell` calls produced
   `FAILED.broker_reject(contract_not_found)`.

   *Lesson for future archaeology:* this item is preserved as evidence
   of a hand-wavy causal explanation made without SDK-level verification.
   The fix in #13 was identified by direct `dir()` + `__contains__`
   protocol inspection. Always validate before assuming SDK semantics.



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

12. **Shioaji Common-path quantity unit mismatch (v0.1.16 v2 bug).**
    **Status: RESOLVED 2026-05-25 by v2.1 hotfix (P-δ-2 / 2c / 2d).**

    *Discovery (2026-05-25):* During sim post-deploy verification,
    raw Shioaji SDK calls confirmed that `deal.quantity` for Common
    `order_lot` is in LOTS, not SHARES. Two independent repros:
    1-lot order returned `deal.quantity=1`; 2-lot order returned two
    `Deal` objects of `quantity=1` each. Sinotrade docs sample
    (`api.place_order` example) corroborates lot-unit convention.

    *Impact in v0.1.16 v2 (pre-fix):* `LiveBroker._submit` line ~463
    computed `total_deal_shares = sum(d.quantity for d in deals)`
    assuming SHARES, then compared against
    `requested_shares = requested_lots * SHARES_PER_LOT`. For a fully
    filled 1-lot Common order, the comparison was `1 >= 1000` → False
    → entered PARTIAL branch → DB row written with status=PARTIAL,
    filled_shares=1. K-P0-1 DB CHECK permitted this (0 < 1 < 1000),
    but the semantic was wrong: broker had FILLED, helios marked
    PARTIAL (terminal per backlog #3). All Common entries would have
    failed to open positions.

    Same bug class affected `fetch_trades` (P-δ-2c) and `fetch_holdings`
    (P-δ-2d) at the BrokerAdapter Protocol boundary.

    *Root cause:* the `live_broker.py` module docstring and code
    comments claimed `deal.quantity` was SHARES (broker-native). This
    was an assumption made during v2 advisor review without SDK-level
    verification.

    *Fix (v2.1 hotfix):*
    - P-δ-2: `_submit` boundary normalization — `× SHARES_PER_LOT`
      after summing `deal.quantity`, with `assert order_lot is
      OrderLot.Common` guard.
    - P-δ-2c: `fetch_trades` same normalization.
    - P-δ-2d: `fetch_holdings` same normalization on `pos.quantity`.
    - P-δ-1: `OrderLot` enum added with Common only (IntradayOdd
      commented out); reserved for v0.1.17.

    *Design invariant (FROZEN, post-fix):*
    "Broker adapters may expose broker-native quantity semantics, but
    all persisted execution accounting inside Helios must use canonical
    share-equivalent units." K-P0-1 share-equivalent comparison and DB
    CHECK invariant remain intact; v2.1 only changes the boundary.

    *Verification (2026-05-25):*
    - Arithmetic unit-level test: 4 scenarios (1-lot full, 2-lot split,
      empty deals, IntradayOdd assertion) all pass.
    - `mark_filled(filled_shares=1000, requested_lots=1)` against DB
      CHECK: passed.
    - `fetch_holdings` post-patch: 4919 returns shares=3000 (3 lots ×
      1000), 2890 returns shares=1000 (1 lot × 1000). Both match
      expected canonical values.

    End-to-end LiveBroker → real-broker → DB FILLED row writing has
    not been verified yet (sim env defaults to ref_price LMT which
    rarely auto-fills within poll window). First real opportunity is
    5/26 16:00 cron if a marketable entry signal lands.

    See `CHANGELOG_v0_1_16_v2_1.md` for full patch chronology.

13. **`_resolve_stock_contract` symbol-in-namespace lookup bug.**
    **Status: RESOLVED 2026-05-25 by v2.1 hotfix (P-δ-2b).**

    Supersedes item #8.

    *Discovery (2026-05-25):* During P-δ-2 verification, LiveBroker
    `submit_buy` against 4919 returned `FAILED.broker_reject` with
    error_code=`contract_not_found` — same error pattern as the
    5/24 smoke test 6139 case. Raw Shioaji SDK calls 2026-05-25 against
    4919, 6139, 2890, 2330, 2412 all returned valid TSE contracts via
    `tse.get(symbol)`, contradicting the original #8 hypothesis that
    6139 was in a non-stock namespace.

    *Root cause:* `_resolve_stock_contract` used `symbol in tse`
    membership check. Diagnostic 2026-05-25:
    `Has __contains__: False` — Shioaji's `StreamMultiContract`
    namespace does not implement `__contains__`, so Python falls
    back to `__iter__` linear scan which iterates `Stock` objects
    (not keys). The string `"4919"` is compared against `Stock`
    instances and never matches → `'4919' in tse` returns False
    permanently. The bug was masked because `tse[symbol]` and
    `tse.get(symbol)` both work — only the `in` short-circuit
    returned None.

    *Fix (P-δ-2b):* changed `_resolve_stock_contract` from
    `tse[symbol] if symbol in tse else None` to `tse.get(symbol)`.
    Same for OTC namespace. Docstring updated with diagnostic
    evidence and verified symbol list.

    *Verification (2026-05-25 11:24):* LiveBroker driver against
    4919 1-lot returned `broker_order_id=103BCC, status=SUBMITTED`
    instead of `FAILED.broker_reject`. Contract resolution path
    confirmed functional.

    *Implication for v0.1.16 v2 main deployment:* the
    `helios_20260524_d5f22d6e` row recorded during 5/24 smoke test
    (6139 FAILED.broker_reject) was misdiagnosed at the time as a
    namespace issue and attributed to backlog #8. Actual cause was
    this `in` operator bug. #8 is preserved as evidence of
    hand-wavy causal reasoning; this entry corrects the record.

14. **`LiveBroker.fetch_trades` timestamp semantics (v0.1.17).**
    **Status: OPEN — known issue, deferred.**

    LiveBroker.fetch_trades() skips sim trades because
    `trade.status.modified_time` is None and `trade.ts` is absent.
    Sim trades expose `status.order_datetime` and `deal.ts` instead.
    Reconcile read path needs explicit timestamp semantics:
    `order_ts` for submitted orders, `fill_ts` from `deal.ts` for
    filled/partial orders, and `broker_status_ts` only if verified
    in production. Do not patch by blindly substituting one field
    for another.

    Why this is deferred to v0.1.17 (not v2.1 hotfix):
    - v2.1 scope is Shioaji unit boundary canonicalization for the
      entry path; reconcile read path has no production cron and
      is not 5/26 critical.
    - Production Shioaji `modified_time` behavior is unverified
      (sim returns None; production may set it). Patching by
      substitution without production evidence risks introducing
      the wrong fallback order.
    - Correct fix likely splits the single `trade_dt` extraction
      into dual `order_ts` / `fill_ts` semantics, which is a
      reconcile-interface design change, not a hotfix.

    v0.1.17 must: (1) verify production timestamp behavior with
    real Shioaji session, (2) redesign `fetch_trades` to return
    explicit `order_ts` and `fill_ts`, (3) update `BrokerAdapter`
    Protocol contract accordingly, (4) update `reconcile_fills`
    consumers.

---

## Sign-off

| Owner | Sign-off requirement |
|---|---|
| Implementer | Apply migration on dev/sim DB; smoke test passes Q1/Q2/Q3. |
| Reviewer | Tick reviewer checklist §11 for execution PR. |
| Operator | Verify Telegram surfaces sim_relaxed and recovery summary correctly. |
| Pre-live | Verify Step 7 uses production guard; trading_calendar replaced. |

---

**v2.1 hotfix (2026-05-25)**: See [`CHANGELOG_v0_1_16_v2_1.md`](CHANGELOG_v0_1_16_v2_1.md) for Shioaji boundary normalization patches addressing backlog items #12, #13, and #14.

## Backlog #15 OPEN — Decouple signal generation from broker submission window

**Identified:** 2026-05-25
**Priority:** v0.1.17 P0
**Status:** OPEN

**Problem:**
Current `daily_run` at 16:00 combines two concerns with incompatible
timing requirements:
  1. EOD signal generation (correct at 16:00 — data is fresh)
  2. Broker order submission (wrong at 16:00 — Shioaji may reject
     after-hours orders; intraday execution observation impossible)

This conflation was acceptable for paper T+1 modeling but is
structurally invalid for:
  - Shioaji sim/live semantic observation (P-obs-1 / P-obs-2)
  - Production live broker submission
  - Any strategy requiring intraday execution timing

**Required design:**

    16:00 daily_run
      → EOD signal scan
      → create order intent / candidate (no broker submission)
      → write INTENT to orders journal

    09:00-13:30 execution_submitter (new component)
      → read approved / pending intents
      → submit to Shioaji during broker-valid window
      → journal SUBMITTED / FILLED / PARTIAL / FAILED

This preserves research timing (EOD) while aligning broker
submission with exchange-valid hours.

**Implication for P-obs-1:**
P-obs-1 (2026-05-26 16:00 cron) is NOT a full execution observation
window. It is an after-hours broker availability observation only.

Observable at 16:00:
  [OBSERVED] trading-day after-hours Shioaji login behavior
  [OBSERVED] after-hours place_order path, if reached
  [OBSERVED] after-hours broker reject type (broker_reject vs transport)
  [OBSERVED] order_journal INTENT -> FAILED/SUBMITTED transition

NOT observable at 16:00 (requires P-obs-2 intraday):
  [UNOBSERVABLE] deal.quantity unit on actual fill
  [UNOBSERVABLE] FILLED / PARTIAL path end-to-end
  [UNOBSERVABLE] callback behavior
  [UNOBSERVABLE] fetch_trades filled payload

**Successor:** P-obs-2 intraday broker submission observation
(planned for v0.1.17, requires backlog #15 implementation)

## Backlog #16 OPEN — Historical open-gap calibration for INV-2

**Identified:** 2026-05-26
**Priority:** v0.1.17 P1 (blocks production unlock of INV-2)
**Status:** OPEN

**Problem:**
`max_entry_gap_pct = 0.03` in execution_submitter_design.md §4 is
currently `[ASSUMED]`. It is not a cosmetic parameter — it is an
execution feasibility prior that directly affects:
  - fill rate (too tight → high opportunity loss)
  - realized slippage (too loose → chasing gaps)
  - turnover and compounding
  - regime sensitivity (bull gaps differ from bear gaps)

Using an uncalibrated value violates INV-2 (backtest-live gap filter
equivalence): if the live limit ceiling is wrong, the backtest skip
rule is also wrong, and the two diverge silently.

**Required research:**
Compute historical T+1 open gap distribution:

    gap[T] = open[T+1] / close[T] - 1

Analysis dimensions:
  - Unconditional: median, p75, p90, p95, p99 across full universe
  - Conditional on signal score (high-score signals may cluster in
    momentum names with larger gaps)
  - Conditional on market regime (bull / neutral / bear / crisis)
  - Conditional on liquidity bucket (volume tercile or market cap)
  - Conditional on gap direction (upward gaps only, for BUY signals)

Output:
  - Recommended max_entry_gap_pct with empirical justification
  - Expected fill rate at chosen threshold
  - Sensitivity table: fill_rate vs gap_pct at p90/p95 of universe

This research must be completed before execution_submitter goes to
production. The output updates execution_submitter_design.md §4 and
config/strategy_params (or equivalent).

**Acceptance criterion:**
max_entry_gap_pct is tagged [OBSERVED] with a reference to the
calibration study, not [ASSUMED].


## Backlog #17 OPEN — READY_FOR_SUBMISSION schema migration + submitter queue

**Identified:** 2026-05-26
**Priority:** v0.1.17 P0 (blocks execution_submitter implementation)
**Status:** OPEN

**Problem:**
Current v0.1.16 architecture conflates three distinct lifecycle stages:
  1. Signal confirmation       (strategy decision)
  2. Submission readiness      (pre-submission checks passed)
  3. Broker submission         (broker API called)

The current orders table state machine reflects this conflation:
  INTENT -> SUBMITTED -> FILLED / PARTIAL / FAILED

INTENT currently implies "immediately submittable", which is only
valid when daily_run and broker submission are in the same process
at the same time. v0.1.17 breaks this assumption by decoupling
signal generation (T 16:00) from broker submission (T+1 08:30).

Without an explicit READY_FOR_SUBMISSION state:
  - execution_submitter has no reliable queue to read
  - daily_run cannot record "intent created, not yet submitted"
    without ambiguity with "submitted but not yet filled"
  - startup_recovery cannot distinguish stale intents (never
    submitted) from stale submissions (submitted, fill unknown)

**Required changes:**

1. orders table schema migration:
   Add READY_FOR_SUBMISSION as a valid status value.
   Add target_fill_date column (date the submitter should process).
   Add intent_confirmed_at timestamp (when daily_run created intent).

2. daily_run modification:
   Replace direct broker submission with:
     order_journal.mark_ready_for_submission(
         order_id, target_fill_date=next_trading_day(as_of)
     )

3. execution_submitter (new component):
   SELECT orders WHERE status = READY_FOR_SUBMISSION
   AND target_fill_date = today

4. startup_recovery modification:
   Handle stale READY_FOR_SUBMISSION (target_fill_date < today):
     -> mark EXPIRED + alert (missed submission window)

5. DB migration script:
   migration_NNNN_add_ready_for_submission_state.sql

**State machine (v0.1.17 target):**

    INTENT (created at T 16:00 by daily_run)
      -> READY_FOR_SUBMISSION (after PreTradeGuard passes)
         target_fill_date = next_trading_day(T)
      -> SUBMITTED (at T+1 08:30 by execution_submitter)
      -> FILLED / PARTIAL / EXPIRED / FAILED

**Acceptance criterion:**
daily_run no longer calls any broker API.
execution_submitter successfully reads READY_FOR_SUBMISSION queue
and submits to Shioaji sim during intraday window.
EXPIRED path fires correctly for stale intents in startup_recovery.

## Backlog #18 OPEN — Bearish feature outcome study (before any classifier)

**Identified:** 2026-05-26
**Priority:** v0.2 prerequisite (must precede any bearish scoring/classifier)
**Status:** OPEN

**Constraint:**
Do NOT build a weighted bearish score or BearishRegimeStateMachine before
this study is complete. Building a classifier without outcome validation
produces hardcoded heuristics that look sophisticated but have no empirical
basis. This is the same principle as backlog #16 (max_entry_gap_pct
calibration) applied to the bearish feature layer.

**Required research (research/bearish_feature_outcomes.py):**

For each feature in bearish_features, compute:
  - Feature quantile distribution (what values are typical vs extreme?)
  - forward_return_20d distribution by feature quantile bucket
  - forward_return_60d distribution by feature quantile bucket
  - Max adverse excursion by feature quantile
  - Hit rate: P(forward_return_20d < -5% | feature >= threshold)
  - Persistence: how long does an elevated feature reading persist?

Conditional interaction study:
  - Does high_vol_down_days_5d AND failed_ma20_reclaim_5d provide
    additive information, or do they both observe the same latent
    deterioration process?
  - Quantify: mutual information / conditional entropy between feature
    pairs and forward drawdown
  - This determines whether a weighted sum double-counts the same signal

**Why this matters:**
Features from the same family (below_ma20_streak, failed_ma20_reclaim_5d,
new_low_after_rebound_5d) partially observe the same latent deterioration
process. A classifier that weights them independently will double-count.
The outcome study reveals which features are actually orthogonal.

**Output:**
  - Recommended feature weights (or evidence that equal weighting is adequate)
  - Threshold calibration for each feature (replacing [ASSUMED] values)
  - Evidence-based decision on whether a state machine adds value over
    a simple score threshold
  - Tag each threshold as [CALIBRATED] with dataset reference

**Acceptance criterion:**
At least the following thresholds tagged [CALIBRATED]:
  - high_vol_down_days_5d threshold for "elevated distribution activity"
  - failed_ma20_reclaim_5d threshold for "persistent rejection"
  - atr_expansion_ratio threshold (currently [ASSUMED] 1.5)
  - beta_adj_rs_20d threshold for "meaningful underperformance"

**Dataset:**
  2020-2024 Taiwan TWSE top-200 (available in current helios DB).
  Use walk-forward validation, not full-sample optimization.
  Minimum: 3 out-of-sample windows.

**Implementation reference (Advisor E, 2026-05-26):**

  P1-3 fix — geometric vs arithmetic cumulative return:

  Current code (arithmetic — wrong for volatile regimes):
    total_s = sum(s_rets)   # percentage sum, not compounded
    total_t = sum(t_rets)

  Correct (geometric):
    # Convert pct to multipliers, compound, convert back
    cum_s = (prod(1 + r/100 for r in s_rets) - 1) * 100
    cum_t = (prod(1 + r/100 for r in t_rets) - 1) * 100
    rs_vals[i] = cum_s - beta * cum_t

  Example of arithmetic error:
    Day 1: +10%, Day 2: -10%
    Arithmetic: 0%  (wrong)
    Geometric:  (1.1 * 0.9 - 1) * 100 = -1%  (correct)

  P1-2 fix — Polars vectorized rolling beta (Advisor E reference):

    merged = merged.with_columns([
        (pl.col("adj_close").pct_change() * 100).alias("s_ret"),
        (pl.col("taiex_close").pct_change() * 100).alias("t_ret"),
    ])
    merged = merged.with_columns(
        (pl.rolling_cov(pl.col("s_ret"), pl.col("t_ret"), window_size=60) /
         pl.rolling_var(pl.col("t_ret"), window_size=60)).alias("beta_60")
    )

  Note: verify Polars rolling_cov / rolling_var API signature before
  implementing — API may differ by Polars version.

## Backlog #19 OPEN — bullish_features temporal layer (Phase 3)

**Identified:** 2026-05-26
**Priority:** v0.2 (after backlog #18 bearish outcome study)
**Status:** OPEN

**Framing:**
Bullish features are NOT the inverse of bearish features.

  bearish_features = downside deterioration process detection
  bullish_features = accumulation / breakout quality + timing

The distinction matters because:
  - bearish regime is primarily about detection (is distribution happening?)
  - bullish entry is about timing + confirmation (is this breakout valid?)

A close > MA20 > MA50 is a snapshot. The valuable signal is the
temporal sequence: prolonged compression → volume return → breakout
→ successful retest → relative strength leadership.
This is the accumulation → markup transition.

**Target architecture:**

  daily_features      universal indicators (unchanged)
  bearish_features    downside temporal observations  [built 2026-05-26]
  bullish_features    upside temporal observations    [this backlog]
  ──────────────────────────────────────────────────────────────────
  entry_classifier    consume bullish_features + market_regime  [v0.2+]
  risk_filter         consume bearish_features + market_regime  [v0.2+]

**Proposed bullish_features columns:**

  Family 1: Persistence
    above_ma20_streak           consecutive days close > MA20
    above_ma50_streak           consecutive days close > MA50

  Family 2: Reclaim confirmation (accumulation base)
    ma20_reclaim_confirmed      close > MA20 sustained N days after crossing
    ma50_reclaim_confirmed      same for MA50

  Family 3: Breakout quality
    volume_breakout_days_5d     high-vol up days in past 5 bars
    volume_contraction_days_10d days with rel_vol < 0.7x in past 10 bars
                                (accumulation: price-compression + vol-compression)
    tight_range_days_10d        low-ATR consolidation bars (base formation)
    failed_breakdown_count_10d  times price tested below MA20 but closed above
                                (demand absorption — inverse of failed reclaim)

  Family 4: Relative strength
    beta_adj_rs_20d             shared with bearish_features (reuse computation)
    beta_adj_rs_60d             same

  Family 5: Volatility structure
    atr_compression_ratio       current ATR / 60d mean (low = base formation)
    atr_compression_days_10d    days in past 10 with atr_ratio < 0.8x (base persistence)

**REMOVED from initial schema (lookahead risk):**
  breakout_followthrough_5d: requires close[t+1..t+5] — lookahead leakage.
    Correct location: research/bullish_feature_outcomes.py (forward outcome calc).
  atr_expansion_after_breakout: definition ambiguous without strict temporal
    boundary. Deferred until "breakout event" is cleanly defined at t,
    not requiring forward confirmation. Initial version uses
    atr_compression_ratio + atr_compression_days_10d instead.

**Design constraints (same as bearish_features):**
  - Pure Polars transforms, no I/O, no scoring, no labels
  - Separate table (bullish_features), NOT added to daily_features
  - No bullish_score or entry_label in feature layer
  - No entry classifier until backlog #18 outcome study complete
  - Failed breakdowns assigned to t+1 (same lookahead discipline as
    failed_reclaim in bearish_regime.py — lesson from P0-2 fix)

**Prerequisite ordering:**
  1. bearish_features Phase 2 COMPLETE (2026-05-26) ✅
  2. backlog #18: bearish feature outcome study (validates methodology)
  3. backlog #19: bullish_features.py pure layer
  4. forward outcome study for bullish features
  5. entry_classifier design (v0.2+)

Do NOT modify existing trend_breakout_v1 signal logic until steps 3-4
are complete. The existing screener continues as the operational signal
generator; bullish_features is a parallel research layer.

## Backlog #20 OPEN — Notification layer abstraction (v0.2)

**Identified:** 2026-05-26
**Priority:** v0.2 (non-blocking for v0.1.17)
**Status:** OPEN

**Current state:**
Strategy pipeline directly calls Telegram. This conflates:
  signal generation → notification transport → execution approval

**Target architecture:**

  class NotificationSink(Protocol):
      def send(self, event: SignalEvent) -> None: ...

  implementations: TelegramSink, DiscordSink, EmailSink, WebhookSink

Strategy knows nothing about Telegram/Discord. Clean layering.

**Recommended stack (phased):**

  v0.1 (current): Telegram + CSV exports
  v0.2:           FastAPI + Streamlit dashboard + Telegram alerts
  v0.3+:          FastAPI + React + Discord/Slack + AI agent interface

**Notification tier design (from Advisor C):**

  Info     (daily signals)   → Discord / Slack (channel separation)
  Warning  (risk threshold)  → Telegram / Discord
  Critical (circuit breaker) → SMS / Email
  Audit    (all records)     → Webhook + Google Sheet / DB

**Key invariant:**
  Signal generation = pure deterministic pipeline
  Notification      = fan-out transport layer (NOT approval gate)
  Approval/execution= separate governance layer (already designed in
                      execution_submitter_design.md INV-1)

**Dashboard scope (Streamlit v0.2):**
  - Market regime (BULL/STRESSED/CRISIS)
  - Bullish candidates (from bullish_features)
  - Bearish deterioration (from bearish_features)
  - Portfolio state + risk exposure
  - Signal lifecycle

This is "state representation", not "event stream" (what chat apps
are). Both are needed; they serve different cognitive functions.

**Prerequisite:** v0.1.17 execution_submitter must complete first,
because the approval layer needs to be cleanly separated before
the notification layer is refactored.

## Backlog #21 OPEN — Shioaji daily_quotes as primary OHLCV source (v0.2)

**Identified:** 2026-05-26 (exploration during session)
**Priority:** v0.2
**Status:** OPEN — data availability timing unconfirmed

**Finding:**
api.daily_quotes(date=d) returns full-market OHLCV in one call:
  - 1975 rows for 2026-05-25 (full TWSE universe)
  - Fields: Date, Code, Open, High, Low, Close, Volume, Transaction, Amount
  - Today's data (2026-05-26) was NOT available at 14:06 TST
  - Previous day data confirmed: 2330 close=2310 matches FinMind

**Required observation:**
Poll daily_quotes(date=today) at 14:30, 15:00, 15:30, 16:00 to find
exactly when today's data appears. This determines the new cron time.

**If data appears by 14:30:**
  New cron: 14:30 (vs current 16:00)
  Benefit: daily_run INTENT created 90 min earlier
  Execution_submitter (backlog #15) still runs at T+1 08:30 —
  the earlier signal generation has no impact on execution timing,
  but it does eliminate the backlog #9 class of bugs entirely
  (cron always runs on a confirmed trading day, not 'yesterday').

**Architecture change required:**
  Replace download_daily.py (FinMind) with shioaji_download_daily.py
  corporate_actions table still needs periodic FinMind sync (monthly
  or on ex-dividend events only — not daily).
  build_adjusted_prices.py unchanged.

**Raw price comparison VERIFIED (2026-05-26):**
  Shioaji daily_quotes close == FinMind raw close for 5/5 symbols
  on 2026-05-25: 2330=2310, 2317=261, 2454=4245, 0050=100.8, 2412=136.5.
  Shioaji daily_quotes is confirmed unadjusted raw price. [OBSERVED]

  snapshots() also verified: ts=13:30:00 CST on trading days,
  data available immediately after close. [OBSERVED]

  Remaining verification needed:
  - Ex-dividend date: confirm Shioaji close matches FinMind raw close
    on ex-date (raw, not adjusted) for at least 1 symbol.
  - OTC symbols: confirm daily_quotes includes OTC (not TSE only).

**Prerequisite:** execution_submitter (backlog #15) should be
implemented first — changing the data pipeline timing only matters
once the submission timing is also decoupled.

## Backlog #22 OPEN — daily_price source provenance (v0.2)

**Identified:** 2026-05-26
**Priority:** v0.2 P0 (must precede any cross-source audit or dispute resolution)
**Status:** OPEN

**Decision (2026-05-26):**
  v0.1.0: shared daily_price watermark is acceptable
  v0.1.1: source provenance must be added
  Long-term: provider consistency audit

**Problem:**
With two ingestion sources (FinMind historical + Shioaji daily_quotes),
the same (stock_id, date) row may be written by different providers.
Without source provenance, data disputes cannot be attributed:

  FinMind close = 100.0
  Shioaji close = 100.5
  → which row is in daily_price? written by whom? when?

verify_shioaji_vs_finmind.py validates provider equivalence rate but
does NOT provide row-level provenance. Both are necessary.

**Required schema extension:**

  ALTER TABLE daily_price ADD COLUMN source VARCHAR;
  ALTER TABLE daily_price ADD COLUMN source_version VARCHAR;
  ALTER TABLE daily_price ADD COLUMN ingested_at TIMESTAMP;

**Source values:**
  FinMind historical backfill:  source = 'finmind'
  Shioaji daily incremental:    source = 'shioaji_daily_quotes'

**Invariant to enforce (after migration):**
  Both sources must guarantee identical semantics:
    - raw unadjusted OHLCV (not pre-adjusted)
    - same volume unit (shares, not lots)
    - same ex-dividend semantics (raw price on ex-date)
    - same stock_id/date key semantics

**Implementation:**
  1. Migration: add columns with DEFAULT NULL (backward compatible)
  2. download_daily.py: populate source='finmind' on insert
  3. shioaji_download_daily.py: populate source='shioaji_daily_quotes'
  4. build_adjusted_prices.py: no change (reads daily_price, ignores source)
  5. data_quality_log: add source field for audit trail
  6. verify_shioaji_vs_finmind.py: compare by source on same (stock_id, date)

**Provenance is for dispute resolution, not query performance.**
Do not add source to indexes unless query patterns require it.

## Backlog #9 ADDENDUM — cron time updated to 14:50 (2026-05-26)

**Original fix (791cf0f):** replaced $(date --date=yesterday) with
previous_trading_day(date.today()) — prevents Monday non-trading-day decline.

**This addendum:** cron time changed from 16:00 to 14:50 following
Shioaji daily_quotes availability observation:

  14:33 TST: 0 rows (not yet available)
  14:43 TST: 0 rows
  14:49 TST: 1089 rows ✅ (data appeared between 14:43 and 14:49)

New cron time 14:50 provides ~1 minute buffer after data appears.
This also decouples daily pipeline from the 16:00 P-obs-1
observation window.

**Also updated in this cron change:**
  - download_daily.py → shioaji_download_daily.py (backlog #21)
  - Added compute_bearish_features.py
  - Added compute_bullish_features.py

## Backlog #23 OPEN — Multi-account execution architecture (v0.1.17-A/B, v0.1.18)

**Identified:** 2026-05-26
**Priority:** v0.1.17-A (config + routing) → v0.1.17-B (runtime isolation) → v0.1.18 (DB)
**Status:** OPEN — design frozen, implementation pending

**Core framing:**
The correct entity is `account`, not `user`.
An account = broker credentials + CA cert + execution authority + notification routing.
One person can have multiple accounts (philip_live, philip_paper, family_account).

**accounts.yaml schema:**

  accounts:
    - account_id: philip_live
      owner: Philip
      broker: shioaji
      environment: live
      telegram_chat_id: "123456789"
      ca_cert_path: certs/Sinopac_philip.pfx
      enabled: true

**Secret loading convention (YAML != secret provider):**

  env_prefix = account_id.upper()  # e.g. PHILIP_LIVE
  api_key = os.getenv(f"{env_prefix}_SHIOAJI_API_KEY")
  secret  = os.getenv(f"{env_prefix}_SHIOAJI_SECRET_KEY")
  ca_pass = os.getenv(f"{env_prefix}_CA_PASSWORD")

YAML contains configuration. ENV contains secrets. Never mix.

**CLI convention:**
  --account philip_live   (not --user)

**Phase plan:**

v0.1.17-A — Notification / credential routing only (no DB changes)
  Correct scope: AccountConfig routes credentials and notifications.
  This is NOT multi-account execution isolation.

  Allowed in v0.1.17-A:
    - Sequential dry-run per account (--account <id> --dry-run)
    - Notification routing (each account -> its telegram_chat_id)
    - Credential routing (each account -> its Shioaji API key)
    - account_id in logs, markers, approval routing

  NOT allowed in v0.1.17-A (DB has no account_id column):
    - Concurrent multi-account execution writing to orders/positions
    - --account all with live execution (would cause silent DB collision)

  Hard gate in daily_run.py:
    if len(accounts) > 1 and any execution steps enabled:
        raise RuntimeError(
            "Multi-account live execution requires DB account_id columns. "
            "Complete backlog #23 v0.1.18 before running --account all "
            "with execution enabled."
        )

  Files:
    - config/accounts.yaml
    - config/account_config.py: AccountConfig dataclass + loader
    - daily_run.py: --account flag, single-account execution guard
    - All logs: account_id field added

v0.1.17-B — Runtime isolation
  - account_id in all log events
  - account_id in run markers
  - account_id in approval routing
  - Separate LiveBroker instance per account

v0.1.18 — DB isolation
  - orders: add account_id column + PRIMARY KEY(account_id, order_id)
  - positions: add account_id + PRIMARY KEY(account_id, symbol)
  - signals: add account_id
  - approvals: add account_id
  - Migration script required

**Key invariants:**
  INV-A1: account_id must appear in every structured log event
          that touches execution, orders, positions, or fills
  INV-A2: No shared mutable state between accounts
          (separate LiveBroker, separate DB rows via account_id)
  INV-A3: Notification routing is account-scoped, never broadcast
          across accounts without explicit config

**DB isolation prerequisite:**
  G1-G6 live unlock gates (execution_model.md §14) must be completed
  before multi-account live trading. Specifically G2 (reconcile handles
  SUBMITTED) must account for per-account isolation.

**Current schema gap (confirmed 2026-05-26):**
  orders table:    no account_id column
  positions table: no account_id column

  Required migrations (v0.1.18):
    ALTER TABLE orders    ADD COLUMN account_id VARCHAR DEFAULT 'default';
    ALTER TABLE positions ADD COLUMN account_id VARCHAR DEFAULT 'default';

  DEFAULT 'default' allows backward compatibility — existing rows
  are attributed to the implicit single account.

  Long-term PRIMARY KEY changes:
    orders:    PRIMARY KEY (account_id, order_id)
    positions: PRIMARY KEY (account_id, position_id)
               UNIQUE (account_id, symbol) WHERE status='OPEN'

**Relationship to other backlogs:**
  - Backlog #15 (execution_submitter): submitter must be account-aware
  - Backlog #20 (notification abstraction): NotificationSink should be
    account-scoped
  - Backlog #17 (READY_FOR_SUBMISSION schema): must include account_id

## Backlog #24 OPEN — MACD + Lower-Highs-Lows feature layer expansion (v0.2)

**Identified:** 2026-05-26
**Priority:** v0.2 (after backlog #18 outcome study)
**Status:** OPEN

**Background:**
find_bearish_stocks.py has a stale comment "MACD / Lower-Highs-Lows → v0.1.16 補上"
that was never implemented. features/technical.py explicitly excluded MACD in v0.1
("MACD histogram zoo" — reviewer-curated minimalism decision).

**Required work:**

  MACD:
    1. Add add_macd() to features/technical.py
       Standard params: fast=12, slow=26, signal=9
       Output: macd_line, macd_signal, macd_histogram
    2. Add to FEATURE_COLUMNS in compute_features.py
    3. Re-run compute_features.py (full recompute, 205 symbols)
    4. Add MACD cross / histogram scoring to find_bearish_stocks.py
       Suggested: macd_histogram < 0 and declining = +10pts

  Lower-Highs-Lows:
    Belongs in bearish_features layer (multi-bar, path-dependent).
    Definition: lower_high = high[t] < high[t-N] for N in lookback
                lower_low  = low[t]  < low[t-N]
    Suggested column: lower_highs_lows_5d (count of LH+LL days in 5d window)
    Add to bearish_regime.py after backlog #18 outcome study.

**Prerequisite ordering:**
  1. backlog #18 outcome study must complete first
  2. Confirm MACD and LH-LL add incremental information
     (not just correlated with existing RSI/ROC20/MA features)
  3. Only then add to scoring with evidence-based weights

**Design constraint:**
  Do not add scoring weights without outcome evidence.
  Both features should go through the same calibration process
  as other bearish_features (forward return study by feature quantile).
