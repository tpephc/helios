# Helios Execution Model — v0.1.16 (v2)

**Status:** active design
**Authors:** DEV C (audit), advisor C / D / K (review)
**Last updated:** 2026-05-24 (post-review v2)

---

## §1 Purpose

This document is the single source of truth for how Helios executes
orders, persists their state, recovers from crashes, and reconciles
with the broker. It supersedes scattered docstrings and ad-hoc Slack
threads.

**Audience:** anyone modifying `execution/`, `storage/order_journal.py`,
`scripts/daily_run.py`, `scripts/startup_recovery.py`, or
`scripts/reconcile_fills.py`.

---

## §2 Truth hierarchy

When state disagrees, the order of authority is:

```
broker  >  orders journal  >  positions table
```

- **Broker** is the only ground truth for what happened in the market.
- **Orders journal** records Helios's perspective of what it tried to
  do and what the broker said in response. Its rows can lag broker
  reality (poll has latency) but must never contradict it after
  reconcile.
- **Positions** is a derived projection of FILLED orders. If positions
  disagrees with journal, positions is wrong.

**Implication:** reconcile is allowed to mutate orders journal based on
broker findings, but is NOT allowed to mutate positions directly. Any
position correction goes through a journal correction first, then a
position rebuild from journal.

---

## §3 Order lifecycle state machine

Seven states, no `PLACED`:

```
   ┌──────────┐
   │  INTENT  │  ← record_intent() inserts here
   └────┬─────┘
        │
        ├─→ SUBMITTED  (place_order accepted; broker_order_id known
        │              or sim-empty normalized to None)
        │
        └─→ FAILED.broker_reject  (place_order's caller-side rejection)
            FAILED.transport      (place_order raised; broker state unknown)

   ┌────────────┐
   │ SUBMITTED  │  ← polling continues until terminal
   └─────┬──────┘
         │
         ├─→ FILLED      (deals fully satisfy requested_lots × SHARES_PER_LOT)
         ├─→ PARTIAL     (deals < requested shares; operationally terminal)
         ├─→ CANCELLED   (broker cancelled; manual or session reset)
         ├─→ EXPIRED     (ROD expired without fill; startup_recovery marker)
         └─→ FAILED      (broker rejected after acceptance; rare)
```

`PARTIAL` is **operationally terminal** in v0.1.16: the operator decides
whether to re-submit the unfilled remainder or close out the partial
position. Helios does NOT auto-retry.

"Submitted but not yet filled" is **NOT** a state — it is encoded as
`status=SUBMITTED, last_polled_at IS NOT NULL, filled_shares=0`. Reasons:

1. Adding PLACED would require a transition rule (PLACED → SUBMITTED
   on... what?) that doesn't correspond to any broker event.
2. Reconcile already needs to handle SUBMITTED-with-poll-data; a
   separate state would duplicate logic.

---

## §UNIT CONVENTION (critical — read before writing any execution code)

The v0.1.16 schema and domain types use **unit-bearing column and field
names** to prevent the K-P0-1 class of bug:

| Name | Unit | Where |
|---|---|---|
| `requested_lots` | Common lot count (1 lot = `SHARES_PER_LOT` shares) | schema, journal API, OrderSubmissionResult |
| `filled_shares` | shares (broker-native; from `deal.quantity`) | schema, journal API, OrderSubmissionResult |
| `requested_shares` | shares (derived = `requested_lots × SHARES_PER_LOT`) | OrderSubmissionResult property |
| `total_deal_shares` | shares (sum of deal.quantity) | local var in live_broker._submit |
| `limit_price` | TWD per share | schema, journal, broker |
| `notional` | TWD total commitment (`limit_price × requested_lots × SHARES_PER_LOT`) | schema, journal, guard |

`SHARES_PER_LOT = 1000` is defined ONCE in `execution/order_types.py`.
All other modules import it. There is no other place this number exists
in the Python code.

### The forbidden pattern

Comparing two quantity values without verifying both are in the same
unit is a banned anti-pattern. Specifically:

```python
# FORBIDDEN — this was the K-P0-1 bug in v0.1.16 v1
if total_deal_shares >= requested_lots:    # ← shares vs lots
    mark_filled(...)

# CORRECT — always convert at the boundary
requested_shares = requested_lots * SHARES_PER_LOT
if total_deal_shares >= requested_shares:  # ← shares vs shares
    mark_filled(...)
```

The DB CHECK constraint mirrors this:

```sql
CHECK (
    (status = 'FILLED'  AND filled_shares = requested_lots * 1000)
    OR
    (status = 'PARTIAL' AND filled_shares > 0
                        AND filled_shares < requested_lots * 1000)
    OR
    (status IN ('INTENT', 'SUBMITTED', 'FAILED', 'CANCELLED', 'EXPIRED'))
)
```

### Why this matters (K-P0-1 incident)

The v1 code had `total_deal_shares >= requested_qty` where
`total_deal_qty = sum(d.quantity for d in deals)` (shares) and
`requested_qty = 1` (lots). For a 1-share partial fill:

```
total_deal_shares = 1 (share)
requested_qty     = 1 (lot)
1 >= 1            = True  ← BUG
```

This would mark the order FILLED, open a Helios position for 1000
shares, and later fail to close (broker only has 1 share). Combined
with `lifecycle.py:174`'s synthetic-close fallback, the result was
permanent broker-vs-Helios divergence — an
**execution accounting corruption** class bug.

The DB CHECK constraint and the OrderSubmissionResult invariants both
explicitly multiply by 1000 to defend against re-introduction.

---

## §4 Journal API contract

`storage.order_journal` is the sole entry point for orders table CRUD.
Other modules MUST NOT write `INSERT INTO orders` directly.

Methods:

| Method | Direction | Notes |
|---|---|---|
| `record_intent(...)` | (none) → INTENT | Caller supplies `fill_date` AND `notional` (pre-computed in TWD). |
| `update_order_spec(order_id, limit_price, notional)` | INTENT → INTENT | Updates pre-submission spec after contract lookup. Refuses non-INTENT. |
| `mark_submitted(order_id, broker_order_id, submitted_at)` | INTENT → SUBMITTED | Empty `broker_order_id` is normalized to None. |
| `mark_polled(order_id, polled_at, filled_shares=0, avg_fill_price=None)` | SUBMITTED → SUBMITTED | Does not transition status. `filled_shares=0` requires `avg_fill_price=None`. |
| `mark_filled(order_id, filled_shares, avg_fill_price, ...)` | SUBMITTED → FILLED | `filled_shares` MUST equal `requested_lots × SHARES_PER_LOT`. |
| `mark_partial(...)` | SUBMITTED → PARTIAL | `0 < filled_shares < requested_shares`. Logs at ERROR level. |
| `mark_failed(order_id, failure_type, ...)` | INTENT/SUBMITTED → FAILED | `failure_type` required. TRANSPORT sets `requires_broker_verification=True`. |
| `mark_cancelled(order_id, reason)` | SUBMITTED → CANCELLED | — |
| `mark_expired(order_id, reason)` | SUBMITTED → EXPIRED | startup_recovery uses this. |

Read methods:

| Method | Returns | Used by |
|---|---|---|
| `get(order_id)` | one row | broker, recovery |
| `find_by_broker_order_id(boi)` | optional row | reconcile fuzzy fallback |
| `list_orders_by_fill_date(fill_date)` | list | **reconcile (primary)** |
| `list_orders_for_intent_date(date)` | list | audit reports |
| `list_orders_for_date(date)` | list | **DEPRECATED** — DeprecationWarning |
| `list_by_status(status)` | list | recovery, monitoring |
| `count_today_orders(side=None, exclude_order_id=None)` | int | PreTradeGuard |
| `sum_today_notional(side=None, exclude_failed=True, exclude_order_id=None)` | float | PreTradeGuard |
| `list_orphan_intents(older_than=10min)` | list | startup_recovery |
| `list_stale_submitted_by_fill_date(expired_on_or_before)` | list | startup_recovery |
| `list_orders_requiring_verification()` | list | reconcile axis C |

### Notes on illegal transitions

Calling e.g. `mark_filled` on a row with `status=FILLED` raises
`InvalidTransition`. This is deliberate: it surfaces application-layer
state corruption rather than silently re-running terminal transitions.

---

## §5 OrderSubmissionResult contract

The result type returned by `LiveBroker.submit_buy/sell`. The
**only** field callers should check to mutate positions is
`position_opened`:

```python
result = broker.submit_buy(...)

if result.position_opened:
    # mutate positions, log entry, etc.
    ...
elif result.is_pending:
    # SUBMITTED-but-unfilled; reconcile will resolve
    ...
else:
    # FAILED / PARTIAL / CANCELLED / EXPIRED — no position
    ...
```

**`result.success` means "API call did not raise."** It is NOT a fill
confirmation. A successful API call that returns SUBMITTED-but-unfilled
still has `success=True`. Using `result.success` to decide whether to
open a position is a known v1 anti-pattern (`paper_broker` callers in
`run_entry_scan.py`).

`position_opened` is True iff:

```python
status is OrderStatus.FILLED
and filled_shares == requested_lots * SHARES_PER_LOT
and filled_shares > 0
```

---

## §6 PreTradeGuard contract

The guard sits between `record_intent`/`update_order_spec` and
`api.place_order`. It refuses orders that violate operational guard-rails
regardless of strategy validity.

### Production thresholds (`PreTradeGuard()`)

| Check | Default |
|---|---|
| `max_daily_orders` | 3 |
| `max_daily_notional` | 50,000 TWD |
| `max_order_notional` | 5,000 TWD |
| Price range | [0.5×, 1.5×] reference |

### Week-1 sim thresholds (`PreTradeGuard.sim_relaxed()`)

| Check | sim_relaxed |
|---|---|
| `max_daily_orders` | 3 |
| `max_daily_notional` | 3,000,000 TWD |
| `max_order_notional` | 1,000,000 TWD |
| Price range | [0.5×, 1.5×] reference |

**Why sim_relaxed exists:** typical TWSE Common lot (e.g. 2330 @ 600
TWD → 600,000 TWD per lot) exceeds the production `max_order_notional`
of 5,000 TWD. Without relaxation, the week-1 sim smoke test would only
validate "guard rejects everything" instead of the full journal →
place_order → poll → reconcile chain.

`daily_run.py` selects sim_relaxed automatically when
`cfg.shioaji_simulation=True`. The Telegram daily summary surfaces
`guard_mode=sim_relaxed` so operators see the relaxation.

### Production deployment checklist (revert sim_relaxed)

Before `live_trading_enabled=True`:

1. Verify `daily_run.py` Step 7 selects `PreTradeGuard()` (not
   `sim_relaxed`) when `cfg.shioaji_simulation=False`.
2. Verify Telegram summary's `guard_mode` field shows `production`.
3. Tighten signal generator to emit only signals whose intended
   notional fits the production cap (or accept that some signals will
   be guard-rejected by design).
4. Document the change in the v0.1.17 release notes.

### Why SUBMITTED notional counts toward the daily cap

The daily notional cap measures **committed capital**, not fills.
SUBMITTED orders have reserved buying power at the broker; if a
SUBMITTED order is not yet filled but is still active (ROD), the
broker has earmarked the funds. Excluding SUBMITTED would let the
operator commit unlimited buying power across the day by simply not
waiting for fills.

FAILED orders are excluded (no commitment).

### exclude_order_id rationale (C-P0-2 off-by-one fix)

The execution flow is:

```
record_intent (writes order row with status=INTENT)
   ↓
update_order_spec (writes notional)
   ↓
run_pre_trade_checks (reads back today's orders for caps)
   ↓
api.place_order
```

The order being evaluated is already in the journal when its own
check runs. Without exclusion, the 3rd legitimate order (count cap=3)
would fail because it sees itself: count=3 ≥ 3 → block. Passing
`exclude_order_id=order_id` removes the self-count.

---

## §7 Crash recovery (startup_recovery)

`scripts/startup_recovery.py` runs as `daily_run.py` Step 0a, BEFORE
`shutdown_guard`. It resolves two classes of orphans:

### Orphan INTENT (`status=INTENT`, `intent_at > 10min ago`)

The previous process recorded intent but did not transition to
SUBMITTED. The broker may or may not have received the order.

Resolution: `mark_failed(failure_type=TRANSPORT, ...)`. Sets
`requires_broker_verification=True`. **reconcile MUST query the broker**.

The 10-minute threshold is wall-clock because INTENT → SUBMITTED is
sub-second in normal operation; 10 minutes is unambiguously a crash
signal regardless of market state.

### Stale SUBMITTED (`status=SUBMITTED`, `fill_date <= last_trading_day`)

A ROD order whose expected execution date has passed. v0.1.16 v2 uses
**trading-calendar-aware** stale detection (NOT wall-clock 16h), so
Friday 16:00 → Monday 09:00 does not falsely mark Friday's
fill_date=Monday orders as stale.

`_last_completed_trading_day(as_of, is_trading_day)` walks backward
from `as_of - 1 day`, calling the `is_trading_day` predicate. The
predicate defaults to weekday-only; production MUST replace with a
Taiwan holiday-aware calendar (see `utils/trading_calendar.py`).

Resolution: `mark_expired(reason=...)`. If reconcile later finds a
corresponding broker fill, the EXPIRED row is corrected and flagged
as anomaly.

### Notification

v2 (D-P1-7): startup_recovery emits ONE consolidated Telegram summary
at the end (not per-order). Format:

```
🔧 啟動修復摘要
孤兒 INTENT: N 筆 (需 reconcile 查券商)
過期 SUBMITTED: M 筆
[⚠️ 修復失敗: K 筆 (查 log)]
```

Per-order details go to logger only. This avoids alert fatigue when a
crashed process leaves many orphans.

---

## §8 Reconcile (`scripts/reconcile_fills.py`)

T+1 morning script. Runs three+1 axes of comparison:

### Axis A: orders ↔ broker trades (matched by broker_order_id)

- Query: `order_journal.list_orders_by_fill_date(today)` — orders
  expected to settle today regardless of when intent was recorded.
- For each, look up matching broker trade by `broker_order_id`.
- Mismatches in fill quantity or status raise findings.

### Axis B: positions ↔ broker holdings

- Query: Helios `OPEN` positions vs broker's `list_positions`.
- Symbol/share mismatches raise findings. This catches desync from
  Axis A failures or legacy lifecycle bugs.

### Axis C: `requires_broker_verification` orders

- FAILED.transport orders where Helios doesn't know if the broker got
  the order.
- For each, check broker fills. If found → critical (Helios said FAILED
  but broker filled → journal correction + position open needed). If
  not found → safe to clear the flag.

### Axis D: fuzzy candidates (v2 addition)

When `broker_order_id` is empty/None on the Helios side (sim mode,
transport failure, partial-deal aggregation), Axis A cannot match.

Axis D emits **ReconcileCandidate** records for human review. Each
candidate has:

| Field | Source |
|---|---|
| `symbol` | both |
| `side` | both |
| `helios_requested_shares` | helios (lots × SHARES_PER_LOT) |
| `broker_filled_shares` | broker |
| `helios_limit_price` | helios |
| `broker_avg_price` | broker (VWAP from deals) |
| `helios_intent_at` | helios |
| `broker_submitted_date` | broker (trade_date) |
| `time_distance_seconds` | abs(helios_intent_at − broker_trade_date) |
| `confidence` | high / medium / low based on share-count proximity |

**Not auto-merged.** v0.1.16 surfaces these to the operator only.
v0.1.17 may add policy-driven auto-merge with audit logging.

The rationale for not relying on `broker_order_id` alone:

1. **sim mode:** Shioaji can return empty string
2. **transport failure:** `place_order` raised; ID not captured
3. **partial deal aggregation:** SDK version may emit deals across
   multiple trade objects whose ID linkage varies

### Sim fallback

When `broker._simulation=True` and `list_trades()` returns empty AND
the journal has FILLED/PARTIAL orders for fill_date:

- Skip Axis A (cannot validate; sim is degenerate).
- Run Axis B normally.
- Mode in report: `two_way_sim_fallback`.

v2 fix (K-P2-f): SUBMITTED orders are NOT counted in
`expecting_trades`. SUBMITTED with no broker trades is normal
pre-market state.

### BrokerAdapter (v2, decision 3a)

Reconcile no longer imports `shioaji`. It receives or constructs a
`BrokerAdapter`-conforming object (default: `LiveBroker`) and uses:

```python
with adapter.login_session() as session:
    broker_trades = adapter.fetch_trades(session, fill_date)
    broker_holdings = adapter.fetch_holdings(session)
```

The adapter normalizes all broker-specific types (Shioaji `Trade`,
`Action`, etc.) to plain dicts. Side normalization uses Action enum
identity (see `_normalize_action_to_side`).

### CLI

```bash
uv run python scripts/reconcile_fills.py                       # today
uv run python scripts/reconcile_fills.py --as-of 2026-05-23   # specific date
uv run python scripts/reconcile_fills.py --send-telegram      # alert on critical
```

`--send-telegram` (v2, D-P2-b): when critical findings exist, sends a
compact Telegram message with the first 5. Without the flag, critical
findings only go to console + logs.

---

## §9 Known limitations carried into v0.1.16

These are explicit risk acceptances. Each is documented because hiding
them is more dangerous than admitting them.

### §9.1 Lifecycle position-close uses synthetic exit price (active known risk, monitored)

In `execution/lifecycle.py:174`:

```python
# v0.1.16: active known risk, monitored
exit_price = fill.fill_price or pos.last_close or pos.entry_price
```

This fallback chain executes every day in the exit-scan path (not just
edge cases). If the fill object has no `fill_price`, Helios uses
`last_close` (from market data) or as last resort the entry price.
The PNL written to the closed position is therefore not always the
broker-reported exit fill price.

**Why it's not fixed in v0.1.16:** the LiveBroker rewrite is already at
scope limit. Fixing this requires either (a) routing all closes through
the broker (v0.1.17 P1 item #6) or (b) integrating reconcile's broker
fill data into the lifecycle close — itself a non-trivial change.

**Mitigation:** reconcile Axis A surfaces any synthetic-vs-real
divergence as a critical finding. v0.1.17 will fix lifecycle to source
exit price from the order journal (which has avg_fill_price from broker
deals).

**Mitigation snippet (pseudo-code for the v0.1.17 fix):**

```python
# v0.1.17 target — pseudo-code, PositionCloseError defined in v0.1.17
order = order_journal.find_by_broker_order_id(boi)
if order is None or order.avg_fill_price is None:
    raise PositionCloseError(  # to be defined in v0.1.17
        f"Cannot close position without broker-confirmed fill price; "
        f"order_id={order.order_id if order else 'unknown'}"
    )
exit_price = order.avg_fill_price
```

### §9.2 `paper_broker.py` legacy lowercase side

PaperBroker emits `side='buy'/'sell'` (lowercase). The orders table
CHECK constraint requires uppercase. Callers that route to PaperBroker
must normalize at the boundary. v0.1.17 will align PaperBroker to use
`OrderSide` enum.

### §9.3 PARTIAL is operationally terminal

The unfilled remainder of a partial-fill order is NOT auto-retried.
Operator decides whether to re-submit. v0.1.17 may add a configurable
policy.

### §9.4 IntradayOdd disabled

`simulation=False` raises `NotImplementedError`. The v0.1.16 backtest
audit confirmed Branch A (T+1 open execution) is the aligned model;
IntradayOdd execution remains in code for v0.1.18+ but is gated.

---

## §10 Forbidden patterns (reviewer checklist)

These patterns are explicitly banned. Code review MUST reject PRs
introducing them.

### §10.1 Comparing quantities across units (lots vs shares)

```python
# FORBIDDEN
if total_deal_shares >= requested_lots:        # mixed units
# CORRECT
if total_deal_shares >= requested_lots * SHARES_PER_LOT:
```

This is the K-P0-1 class. Reviewers MUST verify every quantity
comparison uses the same unit on both sides. See the reviewer checklist
at the bottom of this document.

### §10.2 Lowercase side strings

```python
# FORBIDDEN
side = "buy"                                   # fails CHECK constraint
# CORRECT
side = OrderSide.BUY                           # serialized as "BUY"
```

### §10.3 Using `result.success` for position decisions

```python
# FORBIDDEN
if result.success:
    open_position(...)
# CORRECT
if result.position_opened:
    open_position(...)
```

### §10.4 Comparing OrderStatus with `is`

```python
# OK in v0.1.16 because OrderStatus is a singleton Enum, BUT
if status is OrderStatus.FILLED:   # works
# PREFERRED for safety and string comparison defense
if status == OrderStatus.FILLED:   # works for both Enum and str sources
```

This is a soft rule — the codebase uses `is` in some places. The
reviewer checklist prioritizes the unit-comparison rule.

### §10.5 Synthetic fill prices

Outside of the documented `lifecycle.py:174` fallback (active known
risk, monitored), no new code may invent fill prices when broker data
is unavailable. Raise instead.

### §10.6 Direct `INSERT INTO orders`

All journal writes go through `storage.order_journal`. Direct SQL
bypasses transition validation.

### §10.7 Importing `shioaji` outside `execution/live_broker.py`

Reconcile, daily_run, recovery, and any other module imports the
`BrokerAdapter` protocol from `execution.broker_adapter`, not `shioaji`
directly. The only allowed `import shioaji` lives in `live_broker.py`.

---

## §11 Reviewer checklist (mandatory for any `execution/` PR)

Adopted post-K-P0-1 incident review. Every reviewer of any PR touching
execution code MUST tick these boxes before approval:

```
QUANTITY UNITS:
[ ] Is the quantity unit normalization boundary explicit?
    (Where does broker-native unit → Helios unit? Is the conversion at
    that exact line with a comment?)
[ ] Is the broker quantity unit documented at the import boundary?
    (E.g. "Shioaji deal.quantity is SHARES, not lots")
[ ] Do all quantity comparisons in the diff use the same unit on both
    sides? Are mixed-unit comparisons (lots vs shares) absent?
[ ] Are derived quantities (e.g. requested_shares) centralized in ONE
    place? Or are there multiple ad-hoc computations?

STATE MACHINE:
[ ] Do all journal mutations go through storage.order_journal?
[ ] Are state transitions allowed by _LEGITIMATE_TRANSITIONS?
[ ] Are terminal-state checks consistent (use OrderStatus.is_terminal)?

EXECUTION REALISM:
[ ] Does the code distinguish API-call-success from fill-success?
    (i.e., uses result.position_opened, not result.success)
[ ] Are SUBMITTED-but-unfilled orders handled (not assumed FILLED)?

OPERATIONAL:
[ ] Is the change safe under restart? (i.e., startup_recovery can
    resolve mid-flight state from this code path)
[ ] Are critical findings surfaced via Telegram (not just logged)?

UNIT CONFIDENCE:
[ ] If I (the reviewer) wrote a 1-share PARTIAL fill test against
    this code path, would it pass?
```

These checks are added because the K-P0-1 bug had: **correct types,
correct syntax, possibly-passing tests** (if they used 1000-share
fills only). The bug only fires on PARTIAL or odd-share fills, which
v0.1.1 didn't test. The checklist is a defense-in-depth against this
exact failure mode.

---

## §12 Changelog

| Version | Date | Change |
|---|---|---|
| v0.1.16 (v1) | 2026-05-24 (initial) | Initial post-audit design |
| v0.1.16 (v2) | 2026-05-24 (post-review) | Advisor C/D/K review integration: K-P0-1 unit fix, C-P0-1/3/5 / D-P0-1/2 / K-P0-2 fixes, BrokerAdapter protocol, ReconcileCandidate, reviewer checklist |
| v0.1.16 (v2.1) | 2026-05-25 (hotfix) | Shioaji boundary normalization: LiveBroker `_submit` / `fetch_trades` / `fetch_holdings` × SHARES_PER_LOT for Common lot; `_resolve_stock_contract` `.get()` lookup; OrderLot enum + assertion guard. See `CHANGELOG_v0_1_16_v2_1.md`. |
---

## §13 Boundary normalization (v2.1, 2026-05-25)

### Motivation

During post-deploy sim verification (2026-05-25), four independent
Shioaji semantic mismatches were discovered in `LiveBroker`:

1. `_submit` fill classification assumed `deal.quantity` is in SHARES;
   Shioaji Common path actually returns LOTS.
2. `_resolve_stock_contract` used `symbol in tse` membership check;
   Shioaji `StreamMultiContract` does not implement `__contains__`,
   so this expression is permanently False, causing every order to
   fail with `contract_not_found`.
3. `fetch_trades` same lot-vs-share assumption as `_submit`.
4. `fetch_holdings` same lot-vs-share assumption.

(1), (3), (4) are unit semantics. (2) is a separate SDK lookup-path
bug uncovered while diagnosing (1). All four were resolved in v2.1
(see `CHANGELOG_v0_1_16_v2_1.md`).

### Design invariant (FROZEN)

> Broker adapters may expose broker-native quantity semantics, but
> all persisted execution accounting inside Helios must use canonical
> share-equivalent units.

This means:

- **At the LiveBroker boundary** (where SDK objects cross into Helios
  domain types): conversion happens once, explicitly.
- **Everywhere else** (storage, journal, reconcile, accounting): code
  may assume canonical share-equivalent without further conversion.

The K-P0-1 share-equivalent invariant in `OrderSubmissionResult` and
the DB CHECK constraints in `migrations/0002` are correct *given* this
invariant is upheld at boundary. v2.1 added boundary normalization
without changing any downstream code, so all share-equivalent
comparisons (filled_shares vs requested_shares, CHECK constraints,
reconcile fuzzy match) continue to operate correctly.

### Common path normalization

```
Shioaji SDK boundary             Helios canonical (internal)
─────────────────────            ────────────────────────────
deal.quantity   (LOT)            filled_shares      (SHARE)
  × SHARES_PER_LOT  ────────→
pos.quantity    (LOT)            holdings.shares    (SHARE)
  × SHARES_PER_LOT  ────────→
```

VWAP computations stay correct under either unit because
`sum(price × qty) / sum(qty)` is unit-agnostic — numerator and
denominator both scale by SHARES_PER_LOT, ratio unchanged. The
boundary normalization happens after VWAP for clarity.

### IntradayOdd path (NOT IMPLEMENTED, v0.1.17)

For IntradayOdd (盤中零股), Shioaji returns `deal.quantity` and
`pos.quantity` directly in SHARES (1–999, < 1 lot). There is no
conversion at the boundary; pass-through.

v2.1 does not implement IntradayOdd. `OrderLot.IntradayOdd` is
explicitly commented out in `execution/order_types.py`, and
`LiveBroker._submit` asserts `order_lot is OrderLot.Common` at the
boundary normalization step, preventing accidental SHARES_PER_LOT
over-multiplication if a future commit enables IntradayOdd without
implementing the corresponding path.

### LiveBroker boundary points (v2.1 exhaustive list)

| Method | Type | Action |
|---|---|---|
| `_submit` (fill classification) | unit | `× SHARES_PER_LOT` on `deal.quantity` |
| `fetch_trades` | unit | `× SHARES_PER_LOT` on `deal.quantity` |
| `fetch_holdings` | unit | `× SHARES_PER_LOT` on `pos.quantity` |
| `_resolve_stock_contract` | lookup | use `.get()` not `in` (orthogonal to unit, same v2.1 fix wave) |

Any future LiveBroker method that consumes Shioaji `deal` or `pos`
objects MUST follow the same convention. The `OrderLot` enum guard
in `_submit` is the closest thing to a compile-time check; reviewers
should treat it as the canonical pattern.

### Cross-references

- `BrokerAdapter` Protocol docstring (`execution/broker_adapter.py`)
  documents the canonical unit guarantee from the consumer side.
- `CHANGELOG_v0_1_16_v2_1.md` records the patch chronology and
  per-patch verification evidence.
- Backlog `#8` (SUPERSEDED), `#12` (RESOLVED), `#13` (RESOLVED),
  `#14` (OPEN) in `CHANGELOG_v0_1_16_v1_to_v2.md`.


---

## §14 Internal book vs broker truth — operational model (2026-05-25)

### Framing

The phrase "Helios DB is SSOT" is **incorrect and must not be used**.

The correct model is:

    Broker fills       = external execution truth
    Orders journal     = internal operational book (projection of known fills)
    Positions table    = derived projection from orders journal
    Reconcile          = truth synchronization boundary

The internal book is authoritative for *operational decisions* (signal
gating, exit sizing, notional limits). It is NOT authoritative for
*fill truth*. Fill truth lives only at the broker.

Corollary: the system is correct only if reconcile continuously proves
that the internal book matches broker truth. A clean internal book
without a passing reconcile is an unverified claim, not a guarantee.

This distinction matters because v0.1.16 v2 shipped with an incorrect
assumption about Shioaji `deal.quantity` units. The internal book
recorded wrong `filled_shares` values. Because reconcile was skipped,
no automated check caught the divergence. v2.1 fixed the boundary
normalization; the lesson is that reconcile is a load-bearing
architectural component, not an optional audit step.

### Live unlock gating (G1-G6)

The following gates MUST all be green before any live (non-paper,
non-sim) trading is permitted. They are not aspirational -- they are
hard prerequisites.

| Gate | Requirement | Status |
|------|-------------|--------|
| G1 | reconcile_fills.py can query broker trades and holdings | OPEN |
| G2 | Reconcile handles SUBMITTED non-terminal orders (confirm fill / expire / flag) | OPEN |
| G3 | daily_run does not treat SUBMITTED as executed; startup_recovery covers stale SUBMITTED | OPEN |
| G4 | Immediate post-submit poll is documented as best-effort snapshot only; final state determined by reconcile | OPEN |
| G5 | PARTIAL fill policy locked: one of (a) prohibit paths that can produce PARTIAL, (b) manual review gate, (c) full partial position accounting implemented | OPEN |
| G6 | Reconcile detects and flags manual broker-side activity (broker holding without Helios position; broker trade without Helios order; Helios position without broker holding) | OPEN |

Gates G1-G4 must be satisfied before the *first real fill* occurs,
not after. Once a real fill happens without reconcile, audit trail
reconstruction is lossy.

Gate G5 note: 1-lot Common orders on liquid names are unlikely to
produce PARTIAL fills in practice, but "unlikely" is not a production
gate. A policy decision must be made and recorded explicitly.

### Reconcile skip policy

reconciliation_skipped with reason paper_broker_no_external_state_*
is acceptable ONLY when broker == paper. For any Shioaji sim or live
deployment, this reason code MUST NOT appear in production logs.

The correct gate in daily_run / reconcile_fills.py:

    if broker_mode == "paper":
        # skip is acceptable
        pass
    else:
        # reconcile MUST run; skip is a hard error
        raise ReconcileRequiredError(...)

### SUBMITTED state policy

SUBMITTED is NOT a terminal state. It means:

    order was accepted by broker API
    fill status is unknown

Every SUBMITTED order requires a deterministic follow-up path:

1. Next cron: startup_recovery scans stale SUBMITTED orders
2. For each stale SUBMITTED: call fetch_trades / fetch_holdings
3. Outcome must be one of:
   - Confirmed fill -> mark_filled
   - Confirmed no fill + order expired -> mark_expired
   - Cannot confirm -> mark_failed(requires_broker_verification=True)

There must be no path where a SUBMITTED order remains SUBMITTED
indefinitely without human notification.

### Cross-references

- CHANGELOG_v0_1_16_v2_1.md §6: out-of-scope items feeding G1-G6
- shioaji_semantic_observation_2026_05_26.md: empirical basis for
  broker semantic assumptions; must be consulted before any reconcile
  implementation
- §8 Reconcile: existing reconcile design (to be updated when G1-G6
  are implemented)
- §13 Boundary normalization: broker unit semantics at LiveBroker
  boundary
