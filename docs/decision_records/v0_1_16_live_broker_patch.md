# LiveBroker v0.1.2 Patch Notes — v0.1.16 (v2)

**Target:** `execution/live_broker.py`
**Base:** v0.1.1 (returns `FillResult`, no journal integration)
**Target:** v0.1.2 (returns `OrderSubmissionResult`, journal-integrated, BrokerAdapter)

---

## Summary

LiveBroker v0.1.2 is a near-complete rewrite of the submission flow. It:

1. **Returns `OrderSubmissionResult`** (not `FillResult`). Callers must use
   `result.position_opened`, NOT `result.success`, to decide whether to
   open a Helios position.
2. **Persists every state transition to the orders journal** via the new
   `storage.order_journal` repository. Provides crash-safe recovery.
3. **Runs `PreTradeGuard`** before invoking `api.place_order`. Refused
   orders are persisted as `FAILED.broker_reject`.
4. **Classifies failures into TRANSPORT / BROKER_REJECT.** TRANSPORT
   failures set `requires_broker_verification=True` so reconcile knows
   to query the broker.
5. **Disables real-broker submission** (`simulation=False` raises
   `NotImplementedError`). Live exposure is gated on v0.1.17 (post
   backtest alignment).
6. **Implements `BrokerAdapter` protocol** via public `login_session` /
   `fetch_trades` / `fetch_holdings`. Replaces the v1 anti-pattern
   where `reconcile_fills.py` reached into private `_login` / `_logout`.

---

## Changes by advisor finding

| Finding | Severity | Location | Resolution |
|---|---|---|---|
| **K-P0-1** | P0 ★★★ catastrophic | `_submit` step 9 | `total_deal_shares` (sum of deal.quantity, in SHARES) compared against `requested_lots * SHARES_PER_LOT` (the share-equivalent of the request). Explicit unit conversion at the comparison boundary; comments mark the unit at every line. **This was the single most dangerous bug in v1**: any 1-share fill would have triggered `position_opened=True`, opening a 1000-share Helios position against 1 broker share, causing permanent desync. |
| **K-P0-2** | P0 | `_submit` step 9 (partial branch) | PARTIAL invariant in `OrderSubmissionResult.__post_init__` now compares against `requested_shares` (share-equivalent), preventing the `0 < x < 1` integer-empty-set bug when `requested_lots=1`. |
| **C-P0-2** | P0 | `_submit` step 6 | `run_pre_trade_checks(... exclude_order_id=order_id)`. Without this, with `max_daily_orders=3`, the 3rd legitimate order would fail because INTENT was recorded BEFORE the check. |
| **C-P0-3** | P0 | `_submit` step 5 | `notional = ref_price * requested_lots * SHARES_PER_LOT` computed AFTER contract lookup, written via `order_journal.update_order_spec` BEFORE PreTradeGuard. Without this, daily notional cap was effectively bypassed (record_intent's `notional=0` placeholder was never replaced). |
| **C-P1-6** | P1 | `_resolve_stock_contract` | Explicit TSE-then-OTC contract lookup. v1 relied on `api.Contracts.Stocks[symbol]` which is unreliable for OTC and certain ETFs. |
| **K-P1-3** | P1 | `_normalize_action_to_side`, `fetch_trades` | Action enum identity comparison (`is Action.Buy`) with string-text fallback. v1's `action == "Buy"` against the Shioaji enum always returned False, causing all sides to be misclassified. |
| **K-P1-5** | P1 | `mark_submitted` boundary | Empty string `broker_order_id` normalized to None at the journal boundary (`order_journal._normalize_broker_order_id`). |
| **D-P0-2 / decision 3a** | P0 | Public adapter methods | `login_session()` (contextmanager), `fetch_trades(session, as_of)`, `fetch_holdings(session)`. LiveBroker now structurally satisfies `BrokerAdapter` protocol. reconcile no longer imports shioaji or calls `_login` directly. |
| **D-P2-e** | P2 | `__init__` | `poll_sleep_sec` is a configurable constructor parameter; default raised to 5.0s. v1 hardcoded 2s, which was too short for Shioaji's deal propagation latency. |
| **decision 2** | — | Constructor call | `PreTradeGuard.sim_relaxed()` classmethod is the week-1 sim threshold profile (1M/order, 3M/day). Production defaults remain in `PreTradeGuard()`. Caller (daily_run) selects based on `cfg.shioaji_simulation`. |

---

## Field rename (v2 unit-bearing API)

All public API surfaces use the new names:

| Old (v1) | New (v2) | Unit |
|---|---|---|
| `requested_qty` | `requested_lots` | lots (1 = SHARES_PER_LOT shares) |
| `filled_qty` | `filled_shares` | shares (broker-native) |

`OrderSubmissionResult.requested_shares` is a derived property
(`requested_lots * SHARES_PER_LOT`). Callers use this whenever a
share-equivalent comparison is needed.

---

## Critical comparison rule

Anywhere in `live_broker.py` (or downstream) where a quantity comparison
occurs, the unit MUST be the same on both sides. The conversion belongs at
the comparison point, with an inline comment naming both units:

```python
# CRITICAL UNIT NOTE (K-P0-1):
#   deal.quantity is in SHARES (not lots).
#   total_deal_shares accumulates in SHARES.
#   To compare with requested_lots, convert via SHARES_PER_LOT.
total_deal_shares = sum(d.quantity for d in deals)
requested_shares = requested_lots * SHARES_PER_LOT
if total_deal_shares >= requested_shares:
    ...
```

The pattern `total_deal_shares >= requested_lots` (mixing units) is now
explicitly forbidden by the reviewer checklist (see
`docs/design/execution_model.md` §10).

---

## Step-by-step submission flow (v0.1.2)

| Step | Action | Persists | Failure mode |
|---|---|---|---|
| 0 | Kill-switch (`simulation=False` → NotImplementedError) | — | raises |
| 1 | `record_intent(notional=0)` → returns order_id | INTENT | — |
| 2 | `import shioaji` | — | → mark_failed BROKER_REJECT |
| 3 | `_login()` | — | → mark_failed TRANSPORT |
| 4 | `_resolve_stock_contract(api, symbol)` (TSE→OTC) | — | → mark_failed BROKER_REJECT |
| 5 | Compute `notional` + `update_order_spec` | — | InvalidTransition if not INTENT |
| 6 | `run_pre_trade_checks(exclude_order_id=order_id)` | — | → mark_failed BROKER_REJECT |
| 7 | `api.place_order` | — | → mark_failed TRANSPORT |
| 7b | `mark_submitted(broker_order_id, submitted_at)` | INTENT → SUBMITTED | — |
| 8 | `time.sleep(poll_sleep_sec)` + `api.update_status` | — | leaves status=SUBMITTED |
| 9 | Classify fill outcome based on `total_deal_shares` vs `requested_shares` | SUBMITTED → FILLED / PARTIAL / (polled) | — |

`logout()` runs in `finally`, always.

---

## Test plan

### Unit tests (no broker calls)

Run from the repo root with `uv run pytest tests/execution/test_live_broker.py`.

```python
# tests/execution/test_live_broker.py

import pytest
from datetime import date, datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from execution.live_broker import LiveBroker, _normalize_action_to_side
from execution.order_types import SHARES_PER_LOT, OrderStatus, OrderSide
from execution.pre_trade_guard import PreTradeGuard


# K-P0-1: PARTIAL fill of 1 share must NOT register as fully filled
def test_partial_one_share_fill_not_marked_filled(monkeypatch):
    """K-P0-1: 1 share fill on 1-lot request must be PARTIAL, not FILLED.

    This is the test that would have caught the v1 catastrophic bug.
    """
    # ... setup mock api ...
    fake_deals = [MagicMock(quantity=1, price=600.0)]  # 1 share
    fake_trade = MagicMock()
    fake_trade.status.deals = fake_deals
    fake_trade.order.id = "broker_abc"
    # ... mock api.place_order to return fake_trade ...

    broker = LiveBroker(guard=PreTradeGuard.sim_relaxed(), poll_sleep_sec=0.0)
    # ... mock _login, contract lookup, update_status ...
    result = broker.submit_buy(
        symbol="2330", lots=1, fill_date=date(2026, 5, 26), signal_id="s1",
    )

    # Must be PARTIAL, NOT FILLED
    assert result.status is OrderStatus.PARTIAL, (
        f"K-P0-1 regression: 1-share fill on 1-lot request was "
        f"misclassified as {result.status}. Must be PARTIAL."
    )
    assert result.filled_shares == 1
    assert result.requested_lots == 1
    assert result.position_opened is False  # MUST NOT open position


# K-P0-1: full fill (1000 shares) → FILLED, position_opened=True
def test_full_fill_marked_filled_position_opened(monkeypatch):
    fake_deals = [MagicMock(quantity=1000, price=600.0)]
    # ... setup as above ...
    result = broker.submit_buy(
        symbol="2330", lots=1, fill_date=date(2026, 5, 26),
    )
    assert result.status is OrderStatus.FILLED
    assert result.filled_shares == 1000
    assert result.position_opened is True


# K-P0-1: partial mid-way (500 shares of 1000 requested) → PARTIAL
def test_partial_mid_fill_recorded(monkeypatch):
    fake_deals = [MagicMock(quantity=500, price=600.0)]
    # ... setup ...
    result = broker.submit_buy(symbol="2330", lots=1, fill_date=date(2026, 5, 26))
    assert result.status is OrderStatus.PARTIAL
    assert result.filled_shares == 500
    assert result.position_opened is False


# K-P0-1: multi-lot full fill (2 lots = 2000 shares, broker returns 2000)
def test_multilot_full_fill(monkeypatch):
    fake_deals = [
        MagicMock(quantity=1000, price=600.0),
        MagicMock(quantity=1000, price=601.0),
    ]
    # ... setup ...
    result = broker.submit_buy(symbol="2330", lots=2, fill_date=date(2026, 5, 26))
    assert result.status is OrderStatus.FILLED
    assert result.filled_shares == 2000
    assert result.requested_lots == 2
    # Notional should be sum of (qty * price) for each deal
    assert abs(result.notional - (1000 * 600 + 1000 * 601)) < 0.01


# C-P0-3: notional written to journal BEFORE pre-trade guard
def test_notional_written_before_guard(monkeypatch):
    # ... mock contract.reference = 1500.0 ...
    # ... mock guard.max_order_notional = 1_400_000 (strict, below 1.5M) ...
    # Expect GuardViolation → FAILED.broker_reject
    result = broker.submit_buy(symbol="X", lots=1, fill_date=...)
    assert result.status is OrderStatus.FAILED
    assert result.failure_type.value == "broker_reject"
    # Verify journal has the order with notional=1_500_000 (not 0)


# C-P1-6: TSE-then-OTC contract lookup
def test_contract_lookup_tries_tse_then_otc(monkeypatch):
    api = MagicMock()
    api.Contracts.Stocks.TSE = {}  # symbol not in TSE
    api.Contracts.Stocks.OTC = {"6488": MagicMock(reference=100.0)}
    contract = _resolve_stock_contract(api, "6488")
    assert contract is not None
    assert contract.reference == 100.0


# K-P1-3: side normalization via enum identity
def test_normalize_action_to_side_with_enum():
    from shioaji.constant import Action
    assert _normalize_action_to_side(Action.Buy) == "BUY"
    assert _normalize_action_to_side(Action.Sell) == "SELL"


# K-P1-5: empty broker_order_id normalized to None
def test_empty_broker_order_id_normalized(monkeypatch):
    fake_trade = MagicMock()
    fake_trade.order.id = ""  # empty string from sim
    # ... setup so submission reaches mark_submitted ...
    result = broker.submit_buy(...)
    # Verify journal row has broker_order_id IS NULL (not empty string)
```

### Integration smoke test (week-1 Monday 08:00, sim mode)

```bash
# Prerequisites:
#   - Shioaji simulation account active
#   - .env has SHIOAJI_SIMULATION=true, LIVE_TRADING_ENABLED=false
#   - DB migrated to v0.1.16 schema
#   - PreTradeGuard.sim_relaxed() in effect (daily_run auto-selects)

cd ~/projects/helios

# Generate a single test signal (low-priced symbol if available)
uv run python -c "
from datetime import date
from execution.live_broker import LiveBroker
from execution.pre_trade_guard import PreTradeGuard

broker = LiveBroker(guard=PreTradeGuard.sim_relaxed())
result = broker.submit_buy(
    symbol='2330',
    lots=1,
    fill_date=date.today(),
    signal_id='smoke_test_001',
)
print(f'Status: {result.status.value}')
print(f'Order ID: {result.order_id}')
print(f'Broker order ID: {result.broker_order_id}')
print(f'Filled shares: {result.filled_shares}')
print(f'Requested shares: {result.requested_shares}')
print(f'Position opened: {result.position_opened}')
print(f'Notional: {result.notional}')
"

# Expected outcomes:
#   - Status: SUBMITTED (pre-market, no fill yet) OR FILLED if mid-session
#   - Order ID: helios_YYYYMMDD_xxxxxxxx
#   - Broker order ID: non-empty string (sim may return short IDs)
#   - Notional: ~600,000 (1500 * 1 * 1000) — passes sim_relaxed cap
#   - Telegram: "🧪 SIM MODE — guard thresholds relaxed for smoke test" tag
```

### Q1/Q2/Q3 validation checklist

These remain open from the v0.1.16 audit and MUST be answered during
Monday smoke test before proceeding to v0.1.17:

- **Q1:** Does `sj.order.StockOrder(quantity=1, order_lot=Common)` mean
  "1 lot = 1000 shares" or "1 share"? Confirm by submitting 1-lot order
  and checking broker app shows 1000-share order.
- **Q2:** Does sim mode populate `trade.status.deals` after `update_status`?
  If not, sim_fallback kicks in for reconcile.
- **Q3:** Does sim mode populate `trade.order.id` with non-empty string?
  If empty, K-P1-5 normalization activates and reconcile uses
  ReconcileCandidate fuzzy match.

### BrokerAdapter protocol verification

```python
# Smoke test for protocol structural conformance
from execution.live_broker import LiveBroker
from execution.broker_adapter import BrokerAdapter

assert isinstance(LiveBroker(), BrokerAdapter), (
    "LiveBroker must structurally satisfy BrokerAdapter"
)

# Usage check
broker = LiveBroker()
with broker.login_session() as session:
    trades = broker.fetch_trades(session, date.today())
    holdings = broker.fetch_holdings(session)
print(f"trades: {len(trades)}, holdings: {len(holdings)}")
```

---

## Known limitations carried into v0.1.16

1. **`paper_broker.py` still uses lowercase `'buy'/'sell'`.** Callers
   that emit to both PaperBroker and LiveBroker must normalize. v0.1.17
   will align PaperBroker. See `docs/design/execution_model.md` §9.4.
2. **`lifecycle.py:174` silent fallback** (`exit_price=fill.fill_price or
   pos.last_close`) is still active in `run_exit_scan.py`. Documented as
   "active known risk, monitored" — v0.1.17 P1.
3. **PARTIAL is operationally terminal.** Operator must manually mark
   the order's resolution. v0.1.16 will not auto-retry the unfilled
   remainder. v0.1.17 may add a policy.
4. **`_login` is still called from `login_session()`** (just behind a
   public surface). The internal Shioaji import remains; a true
   broker-agnostic factory is v0.1.17 scope.
