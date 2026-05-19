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
