# docs/design/execution_submitter_design.md
"""Execution Submitter — Design Specification v0.1.0.

Decouples EOD signal generation from broker order submission.
"""

# execution/execution_submitter_design.md
# Execution Submitter — Design Specification — v0.1.0

**Status:** DRAFT (2026-05-26)
**Owner:** Philip
**Target version:** v0.1.17
**Supersedes:** daily_run broker submission path (backlog #15)
**Related docs:**
  - `docs/design/execution_model.md` §14 (internal book vs broker truth)
  - `docs/decision_records/CHANGELOG_v0_1_16_v1_to_v2.md` backlog #15
  - `docs/decision_records/shioaji_semantic_observation_2026_05_26.md`

---

## §1  Problem

`daily_run.py` at 16:00 conflates two concerns with incompatible
timing requirements:

```
Concern 1: EOD signal generation
  Correct timing: 16:00 (after close, data is complete and fresh)
  Broker dependency: none

Concern 2: Broker order submission
  Correct timing: T+1 08:30–09:05 (within exchange-valid window)
  Broker dependency: Shioaji login + contract fetch + place_order
```

This coupling causes:

1. **After-hours broker uncertainty** — Shioaji behavior at 16:00
   (reject / accept / queue) is broker-specific and `[ASSUMED]`.
   Strategy correctness must not depend on broker after-hours policy.

2. **Backtest-live timing mismatch** — backtest assumes entry at
   `adj_open[T+1]`. Submitting at 16:00 T may result in a different
   fill distribution (or no fill). This is a causal validity violation.

3. **P-obs-2 blocked** — intraday execution observation (deal.quantity
   unit, FILLED path, callback behavior) cannot be observed while
   submission happens after-hours.

4. **Reconcile gap** — SUBMITTED orders created at 16:00 have no
   natural reconcile window until the following day's startup_recovery.

---

## §2  Non-negotiable invariants

These invariants are FROZEN. Any implementation that violates them
must be rejected at PR review.

### INV-1: Signal and submission are temporally decoupled

```
T 16:00 daily_run  → generates signals, creates ORDER_INTENT only
T+1 08:30          → execution_submitter reads intents, submits to broker
```

`daily_run` MUST NOT call any broker API after this design is
implemented. The broker boundary lives exclusively in
`execution_submitter`.

### INV-2: Backtest entry eligibility == live limit-price eligibility

The gap filter applied in backtesting MUST be identical to the
limit price ceiling applied in live order submission.

```
signal_date   = T
prev_close    = close[T]
next_open     = open[T+1]      # known in backtest; estimated in live
max_gap_pct   = configured per strategy (e.g. 0.03 for 3%)

Backtest rule:
  if next_open > prev_close * (1 + max_gap_pct):
      skip entry  # entry ineligible

Live rule:
  buy_limit_price = prev_close * (1 + max_gap_pct)
  # If open > limit → order does not fill → no position opened
  # This is the SAME outcome as backtest skip
```

Consequence: live non-fill due to gap == backtest skip. Both are
legitimate outcomes, not errors. This prevents backtest-live split
where backtest records a fill that live would never achieve.

**This invariant must be enforced in both:**
- Research / backtest entry filter
- `execution_submitter` limit price calculation

### INV-3: Near-open fill window only — no intraday ROD

Backtest uses `adj_open[T+1]` as entry price. Live execution must
target the same liquidity window: the open auction and the first
minutes of continuous trading.

Allowing ROD to fill at any intraday price produces an entry
distribution that diverges from `adj_open[T+1]`. If intraday fills
are desired, backtest must be redesigned to use VWAP or intraday
simulator — not `adj_open`.

For v0.1.17, the fill window is:

```
09:00  order active (auction participation + open continuous)
09:05  cancel_deadline — any unfilled order is cancelled
       status → EXPIRED (not FAILED; non-fill is a legitimate outcome)
```

`cancel_after_minutes = 5` is the v0.1.17 default. This value is
strategy-configurable but must be documented if changed.

### INV-4: Only FILLED opens a position

```
FILLED        → position_opened = True, write to positions table
PARTIAL       → position_opened = False, manual review required (v0.1.17)
EXPIRED       → position_opened = False, no action
FAILED        → position_opened = False, alert + log
SUBMITTED     → still pending, must be resolved before EOD
```

`PARTIAL` does NOT automatically open a position in v0.1.17.
See §8 (out of scope) for partial position accounting.

---

## §3  T / T+1 timeline

```
T  16:00   daily_run
             step 1: download data, build features
             step 2: signal scan
             step 3: for each signal:
                       create ORDER_INTENT
                       set target_fill_date = next_trading_day(T)
                       set status = READY_FOR_SUBMISSION
                       write to orders journal
             step 4: Telegram: signal summary (no order IDs yet)
             step 5: NO broker API call

T+1 08:30  execution_submitter (new cron job)
             step 1: read orders WHERE status = READY_FOR_SUBMISSION
                     AND target_fill_date = today
             step 2: pre-submission checks (see §6)
             step 3: for each passing intent:
                       compute buy_limit_price (INV-2)
                       call LiveBroker.submit_buy(...)
                       write SUBMITTED to orders journal
             step 4: Telegram: submission summary

T+1 09:00  market opens

T+1 09:05  cancel sweep
             step 1: read orders WHERE status = SUBMITTED
                     AND submitted_at < now - cancel_after_minutes
             step 2: for each stale SUBMITTED:
                       call LiveBroker.cancel_order(...)
                       set status = EXPIRED
             step 3: startup_recovery / reconcile picks up remainder

T+1 16:00  daily_run (next cycle)
             startup_recovery resolves any remaining non-terminal orders
             from T+1 before running T+1 signal scan
```

---

## §4  Backtest-live gap filter equivalence (detail)

This section expands INV-2 with the exact research-side filter that
must mirror the live limit price.

### Research-side (backtest entry filter)

```python
def is_entry_eligible(
    prev_close: float,
    next_open: float,
    max_entry_gap_pct: float,
) -> bool:
    """Return True only if T+1 open is within gap tolerance.

    This filter MUST match the live limit price ceiling exactly.
    Any divergence between this function and execution_submitter's
    limit price computation is a backtest-live split.
    """
    return next_open <= prev_close * (1 + max_entry_gap_pct)
```

### Live-side (execution_submitter limit price)

```python
def compute_buy_limit_price(
    prev_close: float,
    max_entry_gap_pct: float,
) -> float:
    """Compute BUY limit price for T+1 open submission.

    Ceiling is prev_close * (1 + max_entry_gap_pct).
    If T+1 open exceeds this ceiling, order will not fill.
    This is the INTENDED behavior — it mirrors the backtest skip.
    """
    return prev_close * (1 + max_entry_gap_pct)
```

### Shared configuration

`max_entry_gap_pct` must be a single config value shared between
the research pipeline and the execution submitter. It must NOT be
hardcoded in either location. Suggested location:
`config/strategy_params.yaml` or `config/settings.py`.

v0.1.17 initial value: `0.03` (3%). This is a heuristic — no
empirical calibration has been done. Treat as `[ASSUMED]` until
validated against historical open gap distribution for universe.

---

## §5  Near-open execution window (detail)

### Why 09:00–09:05

Taiwan Stock Exchange opens continuous trading at 09:00. The first
5 minutes represent the highest-liquidity window of the day for most
liquid names, and price discovery from the opening auction is
reflected immediately. After 09:05, momentum and intraday factors
begin to diverge from the `adj_open` proxy used in backtesting.

`cancel_after_minutes = 5` is therefore the tightest reasonable
window that still captures opening auction liquidity without
introducing intraday price drift.

### Order type

v0.1.17: **LMT (limit order)** only. No market orders.

Rationale: market orders on TSE during opening minutes can suffer
significant slippage on medium-cap names. LMT with gap ceiling (INV-2)
provides natural slippage control and a deterministic non-fill outcome.

### ROD vs IOC vs FOK

v0.1.17: **ROD** with explicit cancel at 09:05. Not IOC or FOK.

Rationale: IOC/FOK introduce broker-side immediate cancel semantics
that differ across sim vs production Shioaji environments (`[ASSUMED]`
behavior — see SSOT §3). ROD + explicit cancel at 09:05 keeps the
cancel logic in Helios, not in broker, making behavior observable
and reproducible in both sim and production.

---

## §6  Pre-submission checks (T+1 08:30)

Before submitting each READY_FOR_SUBMISSION intent, execution_submitter
must verify:

| Check | Fail action |
|-------|-------------|
| target_fill_date == today | skip (stale intent → EXPIRED) |
| symbol not suspended (停牌) | skip → EXPIRED + alert |
| symbol not at limit-up already | skip → EXPIRED (gap filter will also catch) |
| risk cap: notional within daily limit | skip → FAILED.risk_cap |
| existing open position in symbol | skip → FAILED.duplicate_position |
| prev_close available in DB | fail → FAILED.data_missing |
| Shioaji login success | fail all → FAILED.transport, retry once |

These checks are NOT duplicated from PreTradeGuard. PreTradeGuard
runs at INTENT creation time (T 16:00). Pre-submission checks run
at submission time (T+1 08:30) and cover conditions that may have
changed overnight (suspension, limit-up, capital changes).

---

## §7  Order state transitions

```
SIGNAL_GENERATED
  ↓  (daily_run signal scan passes all filters)
ORDER_INTENT_CREATED
  ↓  (PreTradeGuard passes at T 16:00)
READY_FOR_SUBMISSION
  ↓  (execution_submitter pre-submission checks pass at T+1 08:30)
SUBMITTED
  ↓  (broker API accepts order)
  ├→ FILLED          (deal confirmed, position opened)
  ├→ PARTIAL         (partial deal, manual review, no auto position)
  ├→ EXPIRED         (cancel_after_minutes elapsed, cancelled)
  └→ FAILED          (broker reject / transport / risk cap)

Pre-submission check fail at T+1:
READY_FOR_SUBMISSION → EXPIRED  (stale, suspended, limit-up)
READY_FOR_SUBMISSION → FAILED   (risk cap, duplicate, data missing)
```

`READY_FOR_SUBMISSION` is the queue that `execution_submitter`
processes. It must be empty by market open. Any intent remaining
`READY_FOR_SUBMISSION` after 09:00 is a monitoring alert.

---

## §8  Out of scope for v0.1.17

The following are explicitly deferred. They must NOT be implemented
as part of the execution_submitter v0.1.17 work without a separate
design document.

| Item | Reason for deferral |
|------|---------------------|
| PARTIAL position accounting | cost basis / exit sizing not designed |
| IntradayOdd (零股) execution | broker semantics unobserved (P-obs-2) |
| Multi-lot orders (≥ 2 lots) | PARTIAL risk uncontrolled |
| Exit execution (sell orders) | separate design required |
| Pre-market (盤前) order submission | Shioaji semantics `[ASSUMED]` |
| Intraday signal (非 EOD) | outside current strategy scope |
| Broker-side order amendment | not required for LMT + cancel design |

---

## §9  Open questions

These questions must be answered before v0.1.17 implementation is
considered complete. Answers come from P-obs-2 (intraday observation)
and Shioaji semantic observation SSOT.

| # | Question | Source | Status |
|---|----------|--------|--------|
| Q1 | Does Shioaji sim accept LMT orders at 08:30 (pre-open)? | P-obs-2 | OPEN |
| Q2 | Does `place_order` at 08:30 participate in 09:00 opening auction? | P-obs-2 | OPEN |
| Q3 | What is Shioaji's cancel_order API behavior for unfilled LMT? | P-obs-2 | OPEN |
| Q4 | After-hours (16:00) login success rate on trading days? | P-obs-1 (5/26) | OPEN |
| Q5 | Is `deal.quantity` in LOTS for sim AND production Common path? | P-obs-2 | OPEN (`[OBSERVED]` in sim only) |
| Q6 | What is `max_entry_gap_pct` calibrated from historical open gaps? | Research | OPEN |
| Q7 | Does TSE opening auction price equal `adj_open` in adjusted data? | Research | OPEN |

Q4 will be partially answered by the 5/26 16:00 cron P-obs-1
after-hours observation. Q1–Q3 and Q5 require P-obs-2 which depends
on backlog #15 implementation.

---

## §10  Relationship to existing components

```
daily_run.py (modified)
  - removes: broker submission steps
  - adds: ORDER_INTENT_CREATED / READY_FOR_SUBMISSION state
  - unchanged: signal scan, PreTradeGuard, Telegram signal summary

execution_submitter.py (new)
  - reads: READY_FOR_SUBMISSION intents for target_fill_date = today
  - calls: LiveBroker.submit_buy (same interface, no change to broker adapter)
  - writes: SUBMITTED / FAILED to orders journal
  - cron: 08:30 daily, Mon-Fri

cancel_sweep.py (new, or folded into execution_submitter)
  - reads: SUBMITTED orders older than cancel_after_minutes
  - calls: LiveBroker.cancel_order (not yet implemented)
  - writes: EXPIRED to orders journal
  - cron: 09:05 daily, Mon-Fri (or: execution_submitter step 2)

startup_recovery.py (modified)
  - adds: handle READY_FOR_SUBMISSION from previous day (stale intents)
  - adds: handle SUBMITTED from previous day (missed cancel sweep)

reconcile_fills.py (existing, see G1-G6)
  - unchanged interface; gains importance as the final arbiter of
    SUBMITTED → FILLED / PARTIAL / FAILED resolution
```

Version: v0.1.0 (2026-05-26, initial draft)
