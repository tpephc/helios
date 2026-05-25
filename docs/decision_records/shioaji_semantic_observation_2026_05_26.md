# Shioaji Semantic Observation — Production Parity SSOT

**Owner:** Philip
**Created:** 2026-05-26
**Status:** ACTIVE (Phase A — sim observation)
**Supersedes:** assumptions baked into v0.1.16 v2.1 (`CHANGELOG_v0_1_16_v2_1.md`)
**Successor docs (planned):**
  - `shioaji_production_parity_2026_<TBD>.md` (Phase B)
  - v0.1.17 IntradayOdd / timestamp design (Phase C)

---

## §0  Purpose

This document is the **single source of truth** for empirically
observed Shioaji SDK semantics in the Helios deployment.

It exists because v0.1.16 v2 shipped on **four** assumed semantics
that turned out to be wrong, two of which (lot-vs-share, contract
membership) were only caught in post-deploy sim verification, and
two of which (PARTIAL path execution, callback delivery) are still
**unverified**.

This doc records:

1. **What we observed** (sim env, with raw payload)
2. **What we inferred but did not directly observe**
3. **What is structurally unobservable in sim** (requires prod)
4. **What is still pure assumption** (no evidence at all)

The boundary normalization in v2.1 is correct *given* the assumed
semantics hold. This doc is how we discharge those assumptions.

---

## §1  Evidence type taxonomy (READ THIS FIRST)

Every claim in §3 onward MUST carry one of these tags:

| Tag              | Meaning                                                       | Trust level |
|------------------|---------------------------------------------------------------|-------------|
| `[OBSERVED]`     | Directly seen in sim env with raw payload captured            | High        |
| `[INFERRED]`     | Logically derived from `[OBSERVED]` facts                     | Medium      |
| `[UNOBSERVABLE]` | sim env structurally cannot produce this signal               | None        |
| `[ASSUMED]`      | No evidence; based only on SDK docs or general knowledge      | None        |
| `[PROD-ONLY]`    | Requires production deployment to verify                      | Pending     |

**Rule:** `[ASSUMED]` and `[UNOBSERVABLE]` facts MUST NOT be used as
load-bearing invariants in production code without explicit risk
acknowledgement. v2 shipped because LOTS-vs-SHARES was implicitly
`[ASSUMED]` but treated as `[OBSERVED]`.

---

## §2  sim env limitations (KNOWN STRUCTURAL GAPS)

These are reasons why a "clean" sim observation log does NOT prove
production correctness. Update as discovered.

### §2.1  Fill distribution mismatch

sim env uses `ref_price` LMT, which auto-fills only when marketable
against the sim's reference book. This means:

- **1-lot orders on liquid TSE names**: near-certain FILLED in sim
- **PARTIAL fills**: extremely rare or impossible in sim
  - Production: PARTIAL is a real (if uncommon) state for ≥ 2-lot
    orders, or 1-lot orders on illiquid names
  - **Implication**: PARTIAL classification logic in `LiveBroker._submit`
    is currently `[UNOBSERVABLE]` end-to-end. Unit tests cover the
    classifier; the SDK→classifier handoff is not exercised.

### §2.2  Callback path coverage

Shioaji exposes at least two fill notification mechanisms:

- **Pull**: `api.list_trades()` → `trade.deals` accumulates
- **Push**: `order_cb` / `deal_cb` registered callbacks

`[ASSUMED]` (no evidence yet): sim env exercises *only* the pull
path. If true, any code that depends on push callback ordering,
deduplication, or arrival timing is `[UNOBSERVABLE]` in sim.

**Action item**: §3.5 must record which path actually delivers
`deal.quantity` in sim, including whether `deal_cb` ever fires.

### §2.3  Order rejection paths

sim env's rejection criteria are not documented and may differ from
production (price limits, lot size validation, market hours, T+0
constraints, day-trade tagging). All rejection-handling code is
`[ASSUMED]` until observed in sim AND verified in prod.

### §2.4  Timestamp sources

`[ASSUMED]`: which of {exchange ts, deal ts, callback receipt ts,
local wall clock} populates each Shioaji field. This is exactly
backlog #14. See §3.6.

---

## §3  Observation log

Format for each entry:

```
### §3.N  <event class>
**Date:**           YYYY-MM-DD HH:MM TZ
**Env:**            sim | prod
**Tag:**            [OBSERVED] / [INFERRED] / ...
**Order ref:**      <internal_order_id> / <broker_order_id>
**Raw payload:**    <attach or inline>
**Normalized:**     <what LiveBroker produced after boundary conv>
**Invariant check:** PASS / FAIL / N/A
**Notes:**          ...
```

### §3.1  Order submission — SUBMITTED state

_(populate from first cron after 2026-05-26 with marketable signal)_

### §3.2  Single full fill — Common path, 1 lot

_(this is the v2.1 critical path; PARTIAL misclassification bug
lived here)_

### §3.3  Multi-lot fill — Common path, ≥ 2 lots

`[UNOBSERVABLE in current strategy]` — confirm whether Helios ever
submits ≥ 2-lot Common orders in sim. If not, this row stays empty
until prod or until strategy parameters change.

### §3.4  PARTIAL fill

Likely `[UNOBSERVABLE]` in sim per §2.1. If observed, this is
extremely high-value evidence — capture full payload + timing.

### §3.5  Callback path identification

Goal: determine which of `list_trades` poll vs `deal_cb` push
actually delivers the `deal.quantity` value used in
`LiveBroker._submit`. Log:

- whether `deal_cb` is registered and fires
- timing: `deal_cb` arrival vs next `list_trades` poll
- whether `trade.deals` is populated synchronously after `place_order`
  return, or only after a tick

### §3.6  Timestamp semantics

For each timestamped field observed in §3.1–§3.4, record:

- field name
- value
- nearest available reference timestamp (local wall clock at capture)
- offset

This is the empirical basis for resolving backlog #14.

### §3.7  Holdings reconciliation

Capture `fetch_holdings` output vs Helios's internal position state
at end of each trading day. Mismatches go in §4.

### §3.8  Contract resolution

`[OBSERVED 2026-05-25]`: `_resolve_stock_contract` `.get()` path
returns valid contract for 4919, 2890. Confirm same path works for
any new symbol introduced.

---

## §4  Anomalies / mismatches

Every observation that violates §3 expectations gets a numbered
entry here with full payload. These are the seeds of the next
backlog item.

_(empty)_

---

## §5  Resolved-by-observation invariants

When an `[ASSUMED]` or `[UNOBSERVABLE]` claim becomes `[OBSERVED]`,
move it here with the observation that resolved it. This is the
"semantic freeze" log.

| Invariant | Was | Now | Evidence |
|-----------|-----|-----|----------|
| Common path `deal.quantity` unit | `[ASSUMED]` SHARES (v2) | `[OBSERVED]` LOTS (sim 2026-05-25) | v2.1 hotfix sim repro |
| `_resolve_stock_contract` lookup | `[ASSUMED]` `in` works | `[OBSERVED]` `.get()` required | v2.1 hotfix sim repro |

---

## §6  Open questions feeding v0.1.17 design

- IntradayOdd `deal.quantity` unit: `[ASSUMED]` SHARES per SDK docs,
  no observation yet
- IntradayOdd `pos.quantity` unit: same
- Mixed Common + IntradayOdd holdings reconciliation
- Timestamp semantics (backlog #14)
- PARTIAL state machine (backlog #?)

---

## §7  Observation discipline

When capturing a new entry:

1. Use `repr()` and `type()` on every payload field, not just `str()`
2. Capture **before** boundary normalization (raw SDK object) AND
   **after** (Helios canonical)
3. Note local wall clock at capture
4. If unsure whether a fact is `[OBSERVED]` or `[INFERRED]`,
   it's `[INFERRED]`
5. If unsure whether a fact is `[INFERRED]` or `[ASSUMED]`,
   it's `[ASSUMED]`
6. `[OBSERVED]` requires raw payload attached or referenced by hash
