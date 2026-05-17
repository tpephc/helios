# ADR-001: No HFT / intraday infrastructure

**Status**: Accepted
**Date**: 2026-05-17
**Version**: v0.1 (foundational decision)

## Context

The world of quantitative trading divides roughly into two camps:
1. **HFT / microstructure**: alpha from sub-second execution, order-book modeling, latency arbitrage. Requires co-location, websockets, custom async runtime, kernel-bypass networking.
2. **Medium / low frequency**: alpha from multi-day persistence, regime, factor exposure. Requires daily-batch data, deterministic indicators, position management.

Helios's hypothesized alpha source is **trend persistence + regime filtering** with ~26-day average holding period. The question is whether to architect for (1) or (2).

The temptation to "future-proof" by building HFT-style infra is real:
- "What if we want to scale into intraday later?"
- "Websockets feel more modern"
- "Async is the proper way to handle I/O"

But every HFT-style component carries operational cost:
- Streaming engines need backpressure handling
- Websockets disconnect and need reconnect logic
- Async code is harder to debug than sync
- Real-time consumers need monitoring
- Sub-second decisions can't be human-approved

## Decision

**Helios is a daily-batch system. We commit to architecting the entire stack around the assumption that nothing happens faster than once per day.**

Specifically:
- One cron per day (~09:00 Asia/Taipei) runs the full pipeline
- All data access is `SELECT ... FROM table` (no streaming)
- All indicators compute on the full daily series (no incremental state)
- All exits decided at daily close
- All entries require human approval (Telegram)
- Fill model: paper trade at open[T+1] after close[T] signal

## Consequences

**Positive**
- Single cron entry point — trivial to monitor, debug, restart
- Sync code path everywhere — stack traces tell the truth
- Failure recovery is just "re-run the cron"
- Human-in-the-loop is feasible (1 review per day, not 1 per second)
- Backtests reflect production behavior 1-to-1 (no async race conditions)
- Operational footprint: one machine, one database file, one log stream

**Negative**
- Cannot capitalize on intraday breakouts (most likely noise anyway)
- Cannot react to mid-day news (regulator events, earnings surprises)
- Fill price differs from signal price (open[T+1] vs close[T] slippage)
- If TWSE has a half-day, our cron still fires the same way

**Risks**
- If alpha source turns out to require intraday (it doesn't, per backtest), we'd need a rewrite. Acceptable because backtest proves daily-batch is sufficient.
- Operator must remember Helios is not real-time — checking phone during market hours is wrong mental model.

## Alternatives considered

1. **Async event-driven framework (FastAPI + asyncio + websocket)** — rejected. Adds 2000+ lines of infra for zero alpha gain.
2. **Streaming engine (Kafka / Redis Streams)** — rejected. No streaming alpha source. Would be infrastructure-for-its-own-sake.
3. **Hybrid (daily-batch + intraday alerts)** — rejected. Forces dual codepaths, doubles failure modes, blurs identity.

## Forever-rule

If a future feature proposes intraday data, real-time market subscription, or sub-daily decision making, it requires a new ADR that supersedes ADR-001 with explicit justification of where the alpha lives that requires sub-daily resolution.

Until then: **slowness is a feature, not a bug**.
