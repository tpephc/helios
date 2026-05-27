# Helios Backtest Fill Semantics Audit Report

**Audit ID:** v0.1.16 P0 #1
**Date:** 2026-05-24
**Auditor:** DEV C
**Scope:** Determine whether Helios backtest / paper_broker / exit_scan fill
semantics align with live execution path (Common lot + ROD + T+1 open) for
v0.1.17 unlock decision.

---

## Verdict

**Branch A — T+1 open aligned.** ✅

Helios backtest, paper broker, and exit scan all execute at `adj_open[T+1]`
for signals decided at `close[T]`. The live broker (Shioaji ROD) places EOD
orders that fill at next-day open. Semantics are aligned.

**v0.1.17 implication:** The Common lot + ROD live path **does not require
backtest engine modification**. Migration to real broker can proceed once
v0.1.16 order journal, reconcile, and operational safeguards are in place.

---

## Evidence

### 1. PaperBroker — explicit T+1 open fill

`execution/paper_broker.py:32`:
```
FILL_MODEL = "next_open" — signal at close[T], fill at open[T+1].
Backed by `daily_price_adj.adj_open`, populated by the dividend-adjustment
pipeline alongside adj_close.
```

`execution/paper_broker.py:147`: class attribute `FILL_MODEL = "next_open"`

`execution/paper_broker.py:282-303` (`_lookup_fill_data`):
```python
def _lookup_fill_data(self, symbol, d) -> tuple[float, int] | None:
    """Return (adj_open, volume) at fill day, or None if either missing."""
    with connect(read_only=True) as conn:
        row = conn.execute(
            "SELECT adj_open, volume FROM daily_price_adj "
            "WHERE stock_id = ? AND date = ?",
            [symbol, d],
        ).fetchone()
```

The fill price source is unambiguous: `adj_open` of fill_date (= T+1 trading
day), not `adj_close`.

### 2. Backtest engine — same semantics, documented

`scripts/backtest_ma5_strategy.py:26`:
```
All state transitions are decided at close[T] but EXECUTED at open[T+1].
Overnight risk between T and T+1 always reflects the PRE-transition position.
```

`scripts/backtest_ma5_strategy.py:215-216`:
```
Key invariant: position changes happen at open[T+1], not at close[T].
Between close[T] and open[T+1], the position is still the PRE-signal size.
```

Backtest reads `adj_open` for execution (line 276: `today_open = row["adj_open"]`).
Same data column, same semantic alignment as paper_broker.

### 3. daily_run.py — Step 2 enforces T+1 readiness

`scripts/daily_run.py:67-73`:
```python
# ── Step 2: T+1 fill readiness ────────────────────
fill_date = next_fillable_day(as_of)
if fill_date is None:
    raise PreflightDecline(
        f"t_plus_1_fill_unavailable: as_of={as_of} "
        f"(next trading day's data not yet ingested)"
    )
```

System-level invariant: daily_run cannot proceed without T+1 data ingested.
Confirms T+1 fill is a first-class architectural assumption, not a paper-
broker quirk.

### 4. run_exit_scan.py — same fill semantics

`scripts/run_exit_scan.py:104-107`:
```
Decision date is `as_of` (day-T close used for rule evaluation + running
stats update). Fill date is `fill_date` (T+1 fill day per v0.1.14.2-c
P0-2; under v0.1.14.3 this fills at adj_open[fill_date], not adj_close).
```

Exit scan is symmetric with entry: decision at T close, fill at T+1 open.

### 5. Unit test enforces invariant

From `02_fill_grep.txt`:
```
./tests/test_state_machine.py:538:def test_fill_uses_adj_open_not_adj_close
```

The T+1 open invariant is locked by a regression test. Any drift back to
T-close fill would fail CI.

### 6. LiveBroker — naturally aligned with ROD semantics

`execution/live_broker.py:524-533` places orders with:
- `price_type=StockPriceType.LMT`
- `order_type=OrderType.ROD`

ROD (Rest Of Day) orders submitted at EOD (16:00 daily_run) carry over to
next trading day. They will be matched against the morning auction or
intraday flow, depending on broker behavior. **In simulation mode, behavior
must be verified Monday 08:00** (see "Open questions" below).

---

## Discrepancies and Risks Found

### Risk 1 (Yellow flag): `lifecycle.py:174` silent fallback

`execution/lifecycle.py:174`:
```python
exit_price=fill.fill_price or pos.last_close or pos.entry_price,
```

**Failure mode:** When broker returns `FillResult(success=False, fill_price=None)`,
this falls back to `pos.last_close` (= T-close, not T+1 open) and writes it
into `positions.exit_price` as if a fill had occurred at that price.

**Impact in v0.1.16 (simulation only):** Minor. Paper broker rarely fails
in fully-stocked test data; if it does, the fallback masks the failure
silently.

**Impact in v0.1.17 (real Shioaji live):** Critical. If Shioaji returns
`success=False` for a sell order, `lifecycle.close_position_for_exit` will
write a fabricated `exit_price` and mark the position CLOSED. The position
is gone from the system's view, but **the broker may still hold the
shares**. This is a position desynchronization vector.

**Mitigation:**
- v0.1.16: Document this as known limitation in `execution_model.md`.
- v0.1.17: Refactor `close_position_for_exit` to refuse to close on
  `fill.success == False`. Failed exits should remain `OPEN` with a
  `last_exit_attempt_at` timestamp for retry / manual intervention.

### Risk 2 (Yellow flag): Backtest data_end edge case

`scripts/backtest_ma5_strategy.py:338-340`:
```python
# End of data — force close at today's close
_close_trade(today, close, "data_end")
```

Backtest force-closes any open position at T-close when data ends. This is
the only place a same-bar `close` is used as fill price.

**Impact:** Inflates backtest returns slightly (avoids overnight gap risk
on final positions). Materially affects only backtests where final
positions are large fraction of portfolio.

**Acceptable for v0.1.16 scope.** Flag for v0.1.17 backtest reform: should
use T+1 open of the next available bar, or exclude positions still open at
data_end from return calculation.

### Risk 3 (Confirmed P0): orders table schema does not support v0.1.16 decision

`data/database.py` `orders` table (current):
```sql
CREATE TABLE IF NOT EXISTS orders (
    order_id    VARCHAR PRIMARY KEY,
    signal_id   VARCHAR,
    timestamp   TIMESTAMP NOT NULL,
    symbol      VARCHAR NOT NULL,
    side        VARCHAR NOT NULL,           -- buy / sell  (lowercase!)
    order_type  VARCHAR NOT NULL,           -- market / limit
    quantity    INTEGER NOT NULL,
    price       DOUBLE,
    status      VARCHAR NOT NULL,           -- submitted / filled / partial / rejected / cancelled
    filled_qty  INTEGER DEFAULT 0,
    avg_price   DOUBLE,
    commission  DOUBLE DEFAULT 0,
    tax         DOUBLE DEFAULT 0,
    broker      VARCHAR,
    metadata    JSON
);
```

**Gap vs v0.1.16 locked schema:**

| v0.1.16 required | Current orders table | Status |
|---|---|---|
| `status IN (INTENT, SUBMITTED, FILLED, PARTIAL, FAILED, CANCELLED, EXPIRED)` | `submitted / filled / partial / rejected / cancelled` (lowercase, no INTENT, no EXPIRED, no FAILED) | ❌ Differs |
| `failure_type` column | Not present | ❌ Missing |
| `error_code` column | Not present | ❌ Missing |
| `error_message` column | Not present | ❌ Missing |
| `requires_broker_verification` column | Not present | ❌ Missing |
| `broker_order_id` column | Embedded in `broker` field as `shioaji_sim:{id}` | ❌ Misplaced |
| `intent_at` column | Not present (only `timestamp`) | ❌ Missing |
| `submitted_at` column | Not present | ❌ Missing |
| `last_polled_at` column | Not present | ❌ Missing |
| `finalized_at` column | Not present | ❌ Missing |
| `requested_qty` semantic | `quantity` column | ✅ Rename only |
| `notional` column | Not present | ❌ Missing |
| `CHECK constraints` on status/qty invariants | None | ❌ Missing |
| `side IN (BUY, SELL)` uppercase | `buy / sell` lowercase | ❌ Case mismatch |

**Migration strategy implication:** ALTER alone is insufficient. The
correct approach for v0.1.16:

1. Confirm `orders` table contains no production data (per handoff:
   `dev_bootstrap` synthetic positions were cleaned, OPEN positions = 0).
2. **DROP TABLE orders; CREATE TABLE orders (new schema)**.
3. Add `positions.source_order_id` via ALTER.

This is acceptable because:
- v0.1.16 has not yet started real-broker recording.
- DuckDB is single-process, so DROP is safe with daily_run halted.
- Backfill is unnecessary (no historical orders to preserve).

**Decision:** Migration #1 = DROP + CREATE orders (new schema). Documented
in execution_model.md.

### Risk 4 (Operational): paper_broker._record_order uses lowercase 'buy'/'sell'

`execution/paper_broker.py:354`:
```python
[..., side, ...]
```
where `side` is the literal `"buy"` or `"sell"` passed in.

Both paper_broker and live_broker write lowercase. New schema's CHECK
constraint must use uppercase `BUY/SELL`. **Caller code (paper_broker,
live_broker) must be updated to uppercase along with migration**, otherwise
all writes will fail CHECK constraint.

This is straightforward but easily missed. Added to Migration checklist.

---

## Architecture observations (informational)

### `execution/lifecycle.py` is the closure single source of truth

`scripts/run_exit_scan.py` delegates to `execution.lifecycle.close_position_for_exit`,
documented as "the SAME code path that v0.1.15 will swap for live Shioaji (P1-7)".

**Implication for v0.1.17 P1 #6:** "`run_exit_scan.py` 改用 `LiveBroker.submit_sell()`"
should NOT modify `run_exit_scan.py` itself. Instead, modify
`execution/lifecycle.py` `close_position_for_exit()` to accept a broker
parameter and dispatch to LiveBroker. This is a smaller, more contained
change.

### Step 7 has the success-conflation bug live in production code

`scripts/daily_run.py:128-139`:
```python
result = broker.submit_buy(
    symbol=symbol, lots=1, fill_date=fill_date, signal_id=signal_id,
)
if result.success:
    exec_summary["executed"].append(symbol)
    logger.info("daily_run_entry_executed", ...)
else:
    exec_summary["failed"].append(symbol)
```

`result.success` is True even when `execution_reason == "placed"` (unfilled).
This will cause incorrect "executed" count and misleading Telegram summaries
on the very first day a real order is placed late (16:00) and doesn't fill
intraday.

**This is the exact bug pattern that motivated v0.1.16 P0 #1
(placed != filled != position_opened).** The fix lands in the caller-level
guard (P0 #6).

### shutdown_guard already provides crash-safety harness

`scripts/daily_run.py:54`: `with shutdown_guard(as_of, telegram_notify=...) as guard:`

The startup_recovery (Step 0) we're adding can leverage this existing
infrastructure. Pattern: before entering the main `with` block, run
`startup_recovery(as_of)` which scans for orphan INTENT and stale SUBMITTED
orders. This makes the recovery itself protected by shutdown_guard too.

---

## Open questions (Monday 08:00 validation required)

These are not blockers for v0.1.16 implementation but **must be verified**
before any real-broker exposure.

### Q1: Common lot in Shioaji sim — fill timing

Does `simulation=True + StockOrderLot.Common + OrderType.ROD` fill
immediately during sim, or does it queue until next market open?

This determines whether Monday's smoke test can observe `deals` populated
within `_STATUS_POLL_SLEEP=2.0` seconds. If sim is also queue-based,
v0.1.16 reconcile validation will only see `execution_reason="placed"`
results — useful but limited.

**Test procedure (Monday 08:00, before market open):**
```python
import shioaji as sj
api = sj.Shioaji(simulation=True)
api.login(...)
api.activate_ca(...)
contract = api.Contracts.Stocks.TSE['2890']
order = sj.order.StockOrder(
    action=Action.Buy, price=contract.reference, quantity=1,
    price_type=StockPriceType.LMT, order_type=OrderType.ROD,
    order_lot=StockOrderLot.Common, account=api.stock_account,
)
trade = api.place_order(contract, order)
time.sleep(2)
api.update_status(api.stock_account)
print("status:", trade.status.status)
print("deals:", list(trade.status.deals))
```

Expected outcomes:
- `deals` non-empty → sim fills immediately; v0.1.16 can validate full
  state machine.
- `deals` empty → sim queues until market open (09:00); v0.1.16 can only
  validate `placed` state transition.

### Q2: `api.list_trades()` and `api.list_orders()` in sim mode

Do these APIs return sim orders/trades for reconcile validation? If they
return empty in sim, the three-way reconcile in v0.1.16 can only validate
two ways (orders ↔ positions); the broker ↔ orders side will be
unverifiable until v0.1.17 real-broker switch.

**Test procedure (Monday 08:30, after placing test order from Q1):**
```python
print(api.list_orders(date=date.today()))
print(api.list_trades(date=date.today()))
```

### Q3: Shioaji `trade.order.id` populated in sim mode?

Per code review, `broker_order_id = trade.order.id if trade else ""` can
yield empty string in sim. Confirmed value matters for v0.1.16 reconcile
match key.

**Test procedure:** Same test as Q1, additionally print `trade.order.id`
immediately after `place_order()` and after `update_status()`.

---

## Recommendation: proceed with v0.1.16 implementation

Branch A confirmed. No backtest engine changes required for v0.1.17 unlock.

**v0.1.16 implementation can proceed in parallel with Monday 08:00 sim
validation.** Locked schema, OrderSubmissionResult, OrderJournal,
LiveBroker patch, daily_run guard, and reconcile_fills can all be built
without depending on Q1–Q3 outcomes.

Q1–Q3 results will inform:
- Whether Monday's smoke test can validate the full state machine or only
  the `placed` path.
- Whether v0.1.16 reconcile starts as two-way or three-way.
- Whether v0.1.17 needs additional handling for Shioaji `order.id` absence.

None of these block v0.1.16 schema, code structure, or invariants.

---

## Next steps (DEV C executing)

1. ✅ This audit report (P0 #1) — complete.
2. → P0 #2: Migration SQL (DROP + CREATE orders, ALTER positions).
3. → P0 #3: OrderStatus enum + OrderSubmissionResult dataclass.
4. → P0 #4: OrderJournal repository.
5. → P0 #5: LiveBroker minimum patch.
6. → P0 #6: daily_run Step 0 startup_recovery + Step 7 guard.
7. → P0 #7: reconcile_fills.py v0.1.
8. → P0 #8: execution_model.md.

Total estimated remaining effort: ~7–8 hours of implementation +
operator review.
