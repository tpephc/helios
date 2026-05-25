# CHANGELOG v0.1.16 v2 → v2.1 Hotfix

**Date**: 2026-05-25
**Branch**: feature/v0_1_16_v2_advisor_review
**Predecessor**: v0.1.16 v2 (`a93cafb`)
**Parent doc**: [`CHANGELOG_v0_1_16_v1_to_v2.md`](CHANGELOG_v0_1_16_v1_to_v2.md)

---

## §1 Motivation

The v0.1.16 v2 deploy (2026-05-24, commit `a93cafb`) shipped on the
assumption that Shioaji's Common-path `deal.quantity` was in SHARES.
This assumption was inherited from the v2 advisor review and was not
SDK-verified at the time.

Post-deploy sim verification on 2026-05-25 uncovered four independent
Shioaji semantic mismatches in `LiveBroker`:

| # | Bug | Surface |
|---|-----|---------|
| 1 | `_submit` fill classification assumed SHARES; broker returns LOTS | entry path |
| 2 | `_resolve_stock_contract` used `symbol in tse` (never True) | contract lookup |
| 3 | `fetch_trades` same lot-vs-share assumption as `_submit` | reconcile read |
| 4 | `fetch_holdings` same lot-vs-share assumption | reconcile read |

(1), (3), (4) share the same unit-semantic root cause. (2) is a
separate SDK lookup-path bug uncovered while diagnosing (1).

Without these fixes:
- All Common-path entries via `LiveBroker.submit_buy` / `submit_sell`
  would fail at `_resolve_stock_contract` (#2), producing
  `FAILED.broker_reject(contract_not_found)` regardless of symbol.
- If (2) had not blocked execution, (1) would have caused all
  fully-filled 1-lot Common orders to be classified as PARTIAL
  (broker `deal.quantity=1` × `requested_shares=1000` → `1 >= 1000`
  is False → PARTIAL branch). PARTIAL is operationally terminal per
  backlog #3, so no positions could be opened.
- (3) and (4) would have produced reconcile mismatches against
  helios DB share-equivalent values, though no production cron runs
  reconcile so this would only have surfaced in operator-initiated
  reconciliation.

v2.1 is a hotfix scoped to the Shioaji boundary canonicalization.
IntradayOdd path remains out of scope (reserved for v0.1.17).

---

## §2 Patches

### P-δ-1: `OrderLot` enum in `execution/order_types.py`

Adds `OrderLot(str, Enum)` with `Common = "Common"`. `IntradayOdd` is
present in the docstring as the planned v0.1.17 value but explicitly
commented out at the enum-value site:

```python
class OrderLot(str, Enum):
    Common = "Common"
    # IntradayOdd = "IntradayOdd"  # v0.1.17 — DO NOT uncomment until path is implemented.
```

The commented-out form serves two purposes: (a) reserves the literal
string for future use, (b) signals to future implementers that
enabling IntradayOdd requires implementing the corresponding execution
path, not merely uncommenting the enum value.

**File**: `execution/order_types.py` (+26 lines)
**Verification**: import smoke confirms `OrderLot.Common` accessible
and `OrderLot.IntradayOdd` raises `AttributeError`.

### P-δ-2: `LiveBroker._submit` boundary normalization

7-point patch applied as a single atomic write:

1. **Import**: add `OrderLot` to `from execution.order_types import (...)`.
2. **`submit_buy` signature**: add `order_lot: OrderLot = OrderLot.Common` keyword.
3. **`submit_sell` signature**: symmetric to `submit_buy`.
4. **`_submit` signature**: add `order_lot: OrderLot` keyword.
5. **`record_intent` metadata**: add `"order_lot": order_lot.value` to the metadata dict.
6. **Fill classification block** (the core change):
   - `assert order_lot is OrderLot.Common` guard at boundary.
   - `total_deal_lots_native = sum(d.quantity for d in deals)` (broker-native lot count).
   - `total_deal_shares = total_deal_lots_native * SHARES_PER_LOT` (canonical).
   - VWAP computed using native quantity on both numerator and denominator (unit-agnostic).
   - Downstream `requested_shares = requested_lots * SHARES_PER_LOT` comparison continues unchanged.
7. **Module docstring**: appended v2.1 changelog block explaining the boundary normalization, the corrected unit semantics, and the K-P0-1 share-equivalent invariant preservation.

**File**: `execution/live_broker.py` (+50 lines, single atomic write).
**Verification**: ast.parse + import smoke + 8-marker grep + signature inspection.

### P-δ-2b: `_resolve_stock_contract` lookup fix

Replaces `tse[symbol] if symbol in tse else None` with
`tse.get(symbol)`. Same for OTC namespace. Docstring updated with
diagnostic evidence:

> Shioaji's `StreamMultiContract` namespace does NOT implement
> `__contains__`; Python falls back to `__iter__` linear scan which
> iterates `Stock` objects (not keys), so `"4919" in tse` is permanently
> False regardless of whether 4919 exists. `tse.get(symbol)` uses the
> SDK's intended key-lookup path (returns None on miss, no KeyError).

**File**: `execution/live_broker.py` (+10 lines).
**Verification**: ast.parse + import smoke + 4-marker grep + 2-anti-marker.

### P-δ-2c: `fetch_trades` boundary normalization

`× SHARES_PER_LOT` applied to `sum(d.quantity for d in deals)` to
return canonical share count via the BrokerAdapter Protocol contract.
VWAP retains native unit (lots) on both sides of the division.

**File**: `execution/live_broker.py` (+12 lines).
**Verification**: marker grep + anti-marker check.

### P-δ-2d: `fetch_holdings` boundary normalization

`pos.quantity * SHARES_PER_LOT` returns canonical share count.
Includes a v0.1.17 caveat for IntradayOdd holdings: if such holdings
appear via `list_positions`, the `× SHARES_PER_LOT` would over-count
by 1000×. Not a concern in v2.1 since `LiveBroker` only places
Common orders.

**File**: `execution/live_broker.py` (+13 lines).
**Verification**: marker grep + live sim repro (4919 = 3000 shares,
2890 = 1000 shares).

### P-δ-3: `broker_adapter.py` Protocol docstring update

Replaces the incorrect claim "All quantities in SHARES (broker-native
unit from Shioaji deals)" with the canonical-vs-native distinction.
Documents the design invariant from the consumer side and the
Common/IntradayOdd dichotomy.

**File**: `execution/broker_adapter.py` (+18 lines).
**Verification**: import smoke + 5-marker grep + 1-anti-marker.

### P-δ-4: `docs/design/execution_model.md` §13 + changelog row

Adds a new "§13 Boundary normalization (v2.1)" section after
§12 Changelog, containing the FROZEN design invariant, the
broker→canonical diagram, IntradayOdd path placeholder, and the
exhaustive 4-method boundary point list. §12 Changelog table gains
a v2.1 row referencing this hotfix doc.

**File**: `docs/design/execution_model.md` (+91 lines).
**Verification**: marker grep + section-order check.

### P-δ-5: Backlog updates (`CHANGELOG_v0_1_16_v1_to_v2.md`)

- #8 marked **SUPERSEDED** with root-cause re-analysis pointing to #13.
- #12 added **RESOLVED** (Shioaji Common-path unit mismatch).
- #13 added **RESOLVED** (`_resolve_stock_contract` `in` operator bug).
- #14 added **OPEN** (`fetch_trades` timestamp semantics, deferred to v0.1.17).
- Cross-ref line appended after Sign-off table pointing to this file.

**File**: `docs/decision_records/CHANGELOG_v0_1_16_v1_to_v2.md` (+158 lines).

---

## §3 Design Invariant (FROZEN, v0.1.16 v2.1)

> Broker adapters may expose broker-native quantity semantics, but
> all persisted execution accounting inside Helios must use canonical
> share-equivalent units.

Concretely:
Shioaji SDK boundary             Helios canonical (internal)
─────────────────────            ────────────────────────────
deal.quantity   (LOT, Common)    filled_shares      (SHARE)
× SHARES_PER_LOT  ────────→
pos.quantity    (LOT, Common)    holdings.shares    (SHARE)
× SHARES_PER_LOT  ────────→
deal.quantity   (SHARE, IntradayOdd)  filled_shares (SHARE)
pass-through      ────────→        [v0.1.17]
K-P0-1 share-equivalent invariant in `OrderSubmissionResult` and DB
CHECK constraints remain intact. The boundary is the only place
broker-native units exist; everywhere else operates on canonical
shares.

`LiveBroker._submit` asserts `order_lot is OrderLot.Common` at the
boundary, the closest thing to a compile-time check enforcing the
invariant.

---

## §4 Backlog Updates

| Entry | Action | Detail |
|---|---|---|
| #8 | SUPERSEDED | Original "ETF namespace" hypothesis disproved; real cause = `in` operator. Preserved as audit evidence of hand-wavy reasoning. See #13. |
| #12 | RESOLVED | Common-path unit mismatch — fixed by P-δ-2 + P-δ-2c + P-δ-2d + P-δ-1 guard. |
| #13 | RESOLVED | `_resolve_stock_contract` `symbol in tse` bug — fixed by P-δ-2b. Supersedes #8. |
| #14 | OPEN (v0.1.17) | `fetch_trades` timestamp semantics; sim returns `modified_time=None`. Production behavior unverified. Patch deferred — needs dual `order_ts` / `fill_ts` redesign, not a single-field substitution. |

---

## §5 Verification Summary

### Unit-level (deterministic arithmetic)
=== Scenario 1: 1 lot fully filled ===
✓ 1-lot scenario: FILLED with filled_shares=1000
=== Scenario 2: 2 lots fully filled (split deals) ===
✓ 2-lot scenario: FILLED with filled_shares=2000
=== Scenario 3: empty deals (e.g. ref_price LMT not yet matched) ===
✓ empty-deals scenario: SUBMITTED (matches 11:24 driver run)
=== Scenario 4: assertion guard against IntradayOdd ===
✓ assertion fired correctly
### DB CHECK regression (real journal API + real DB)
TEST_SIGNAL_ID: V2_1_HOTFIX_DB_TEST_20260525_113130
Step 1: record_intent      ✓  helios_20260525_5fd5c0da
Step 2: mark_submitted     ✓
Step 3: mark_filled         ✓  filled_shares=1000 vs requested_lots=1
DB CHECK (filled_shares = requested_lots × 1000) passed
Step 4: DB row              status=FILLED, filled_shares=1000, avg_fill_price=208.0
K-P0-1 invariant intact under real DB CHECK.
### Live sim repro
=== fetch_holdings (post P-δ-2d) ===
symbol=2890  shares=1000  avg_cost=29.1   (1 lot equivalent)   ✓
symbol=4919  shares=3000  avg_cost=208.0  (3 lots equivalent)  ✓
=== LiveBroker.submit_buy (post P-δ-2b) ===
4919 1-lot → broker_order_id=103BCC, status=SUBMITTED  ✓
(no longer FAILED.broker_reject contract_not_found)
All test artifacts in the orders table were cleaned up post-verify
(`DELETE WHERE signal_id LIKE 'V2_1_HOTFIX_%'`, 3 rows removed).

---

## §6 What was NOT done

Explicit scope exclusions for v0.1.16 v2.1, to prevent future
archaeology from mistaking this hotfix for a complete remediation:

1. **End-to-end FILLED row through LiveBroker → real broker → DB CHECK
   has not been verified.** The Shioaji sim environment defaults to
   ref_price LMT which rarely auto-fills within the LiveBroker poll
   window. Driver tests on 2026-05-25 reached SUBMITTED but not FILLED.
   First real opportunity to observe the full FILLED path is 5/26 16:00
   cron with a marketable entry signal. Unit-level verification covers
   the arithmetic; the DB CHECK passes for synthetic FILLED writes; but
   the real end-to-end has yet to occur.

2. **IntradayOdd path is NOT implemented.** `OrderLot.IntradayOdd` is
   commented out in the enum. `LiveBroker` only handles Common.
   `fetch_holdings` × SHARES_PER_LOT would over-count IntradayOdd
   holdings — currently impossible because there are none.

3. **`fetch_trades` timestamp semantics are NOT fixed.** Backlog #14
   tracks this. Sim returns `modified_time=None`, production behavior
   unverified, fix requires dual `order_ts` / `fill_ts` semantics and
   a BrokerAdapter Protocol contract change. Scoped to v0.1.17.

4. **Production Shioaji semantic verification has NOT been done.**
   All evidence is from the sim environment. Sinotrade docs were
   consulted but only for Common-path lot semantics. Production may
   differ in: `modified_time` behavior, `pos.quantity` unit for
   IntradayOdd, fill timing, etc. v2.1 fixes the known sim
   discrepancies; production parity is a v0.1.17 verification task.

5. **Migration 0003 not introduced.** No schema change in v2.1; all
   fixes are at the LiveBroker boundary. The `filled_shares` column
   name and DB CHECK constraints (`filled_shares = requested_lots ×
   1000`) remain as v2 defined.

---

## §7 Cross-Reference

- Parent: [`CHANGELOG_v0_1_16_v1_to_v2.md`](CHANGELOG_v0_1_16_v1_to_v2.md)
- Design: [`../design/execution_model.md`](../design/execution_model.md), §13 Boundary normalization.
- Protocol contract: `execution/broker_adapter.py` module docstring.
- Backlog items: #8 (SUPERSEDED), #12 (RESOLVED), #13 (RESOLVED), #14 (OPEN) in parent doc.
