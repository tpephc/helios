# Helios Development Roadmap

Last updated: 2026-05-19

## Current Status — v0.1.14.3.post8

5-day paper-trade observation window (EOD mode).
Goal: zero-failure run of EOD pipeline, DuckDB state machine, and risk controls
before any infrastructure expansion.

Open positions: 2330 (DEV-TEST-006), 0050 (DEV-TEST-008).

---

## Phase 1 — v0.1.15.x: Infrastructure Layer

Goal: establish a real-time data feed without triggering any trades.

- Shioaji read-only API integration (broker layer)
- Intraday tick/minute-bar subscription and cleaning module
- Data pipeline capable of receiving real-time quotes during market hours
  (09:00–13:30 TST)
- No strategy logic, no order submission, no approval flow changes

Prerequisite: 5-day paper-trade window completed without errors.

---

## Phase 2 — v0.1.16.x: Intraday Scan Pilot (Scheme A)

Goal: validate intraday signal quality before touching the execution path.

- Feature branch `feature/intraday-scan`
- 15–30 minute bar scan during market hours
- Signals trigger Telegram notifications ONLY — no approval flow, no fills
- Collect at minimum 2 weeks of signal data
- Validate: signal hit rate, timing vs EOD signal, slippage estimate vs actual

Constraint: intraday strategy logic must be independently validated before
reuse of EOD-designed features. EOD ATR, regime labels, and entry criteria
are not directly transferable to intraday bars without re-verification.

---

## Phase 3 — v0.3.0+: Event-Driven Transition (Scheme B)

Goal: full intraday execution capability.

- Lifecycle refactor for intraday fill model (vs current next-open assumption)
- Approval timeout reduced from 10 min to 1–2 min
- Full-auto or rapid-approval mode
- Upgraded risk controls for intraday position sizing and drawdown management

Prerequisite: Phase 2 signal validation complete; Shioaji paper-order tested.

---

## v0.2.0 — TWT49U + Corporate Actions Confidence Engine

Scope unchanged from original CHANGELOG commitment.
Runs in parallel to Phase 1–2; not blocked by intraday work.

---

## What Is NOT in Scope (deliberately deferred)

- Real-money live trading before v0.3.0
- Intraday strategy parameter reuse from EOD models without validation
- Full-auto approval before intraday signal quality is verified

---

## v0.1.15 Addendum — Dynamic Universe (2026-05-20)

### Design Decision
Data source: TWSE via FinMind `TaiwanStockMarketValue` (authoritative,
existing token, free). MSCI Taiwan excluded — licensing restrictions
prevent programmatic access. MSCI is a subset of TWSE top-cap anyway.

### Update Policy
- Frequency: monthly, first trading day of each month
- Rebalance: top 200 by market cap (TWSE-listed only; exclude OTC, TDR, KY)
- Position protection: stocks removed from universe with open positions
  stay in `protected_symbols` list — no new buy signals generated, but
  existing positions held until natural exit (trailing stop / strategy exit)

### New Component: `scripts/sync_universe.py`
sync_universe.py
├── Fetch TaiwanStockMarketValue from FinMind
├── Filter: TWSE listed, exclude TDR/DR/KY
├── Rank top 200 by market cap
├── Diff against current universe.yaml
├── Added symbols  → download_daily --symbols [new] → build_adj → compute_features
└── Removed symbols → check positions:
OPEN position → add to protected_symbols (scan exits, no new entries)
no position   → remove from universe.yaml
### New DB Table: `universe_log`
Records each monthly rebalance diff for audit:
- `rebalance_date`, `symbol`, `action` (added/removed/protected), `market_cap_rank`

### Cron Addition (after sync_universe.py is built)
0 9 1-7 * 1   # First Monday of each month, 09:00 TST
cd ~/projects/helios && uv run python scripts/sync_universe.py >> logs/universe_sync.log 2>&1
