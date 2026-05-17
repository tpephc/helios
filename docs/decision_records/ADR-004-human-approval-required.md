# ADR-004: Human Telegram approval required for entries

**Status**: Accepted
**Date**: 2026-05-17
**Version**: v0.1 (foundational decision)

## Context

The strategy is deterministic. Given the same input data, it produces the same signals. In principle, the system could auto-submit orders to a broker without human intervention.

But "deterministic" is not the same as "correct". Things that can go wrong even with deterministic logic:
- Data quality issues (corporate action mishandled, price spike from data error)
- Regime classification edge cases (TAIEX itself had a corporate action / index restructuring)
- Stale data (FinMind / TWSE feed delay → trading on outdated price)
- Pre-market news that changes context (e.g., earnings revision overnight)
- A bug shipped recently that no test caught

In each case, the right response is "human looks at the signal and goes 'wait, that's weird'". Automated systems can't notice "weird" — that's a uniquely human capability.

A second consideration: **operator engagement**. A system that the operator doesn't touch becomes a system the operator doesn't understand. The Telegram approval flow forces daily engagement, which is good for both safety and learning.

Forces against approval:
- Approval introduces a human into a low-latency path (mitigated: our system is daily-batch, latency is fine)
- If operator is offline, signal expires (acceptable for medium-frequency)
- Requires Telegram bot infra (one-time setup cost)

## Decision

**Every entry signal requires explicit operator approval via Telegram before any broker submission. Exit signals execute automatically (capital protection priority).**

Specifically:
- Entry: `signal generated → Telegram push → wait for /approve → submit order` (with 30-min timeout + ATR drift expiry)
- Exit: `exit signal generated → submit order immediately → Telegram notify`
- No autopilot mode. No "trust the algorithm" override. The contract is: human sees every entry before money moves.

## Consequences

**Positive**
- Catches anomalies (data bugs, weird gaps, unexpected market conditions)
- Operator learns the system through daily exposure to its signals
- Failure modes are bounded: if operator offline, nothing happens (vs. unbounded mis-trading in autopilot)
- Trust is built incrementally (approve → see outcome → understand → approve more confidently)
- Compliance-friendly (every trade has explicit human accountability)

**Negative**
- Cannot trade if operator is unreachable (travel, illness, etc.)
- Signal frequency must stay low enough to be human-reviewable (currently 0-3/day — easy)
- Adds ~30 min latency between signal and fill (acceptable for medium-frequency trends)

**Risks**
- Operator approval fatigue if signal frequency grows (acceptable up to ~5/day; beyond that, revisit ADR)
- Approval skipped under pressure ("just approve, I trust the algo") — partly mitigated by ATR drift expiry forcing re-evaluation

## Why exits auto-execute

Exit signals are protective — they fire when:
- Regime degraded (`regime != bull`)
- Trailing stop hit (close < max_close - 2*ATR)

The cost of waiting for approval on these is downside risk to capital. The cost of auto-execution on a false exit is missing some upside (correctable next signal). Asymmetric cost → bias toward automation for exits.

## Alternatives considered

1. **Full autopilot** — rejected. Even deterministic logic has bug surface area; human review is cheap insurance.
2. **Approval threshold (auto-trade signals with score > 0.9)** — rejected. Adds branch logic; "score > 0.9" is not a proven autopilot threshold.
3. **Daily approval batch (one approval covers the day's signals)** — rejected. Defeats per-signal anomaly detection.
4. **Web UI approval instead of Telegram** — rejected. Telegram is push (operator gets notified); web UI is pull (operator must check). Push wins for a daily-batch system.

## Forever-rule

If a future feature proposes automated entry submission, it requires a new ADR superseding ADR-004 with explicit reasoning for why human anomaly detection is no longer valuable. The bar is high: "automation is faster" is not sufficient — "automation is correct in cases we cannot anticipate" must be argued.

Until then: **the operator is not optional**.
