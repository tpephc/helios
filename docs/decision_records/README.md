# Architecture Decision Records

This directory contains **ADRs** (Architecture Decision Records) for Helios.

ADRs record decisions that:
- Have **long-term architectural impact**
- Close off entire **complexity vectors**
- Are non-obvious enough that future maintainers (including future-you) will ask "why did we do this?"

## Format

Each ADR follows the Michael Nygard format (lightly adapted):

```markdown
# ADR-NNN: Short title in present tense

**Status**: Accepted | Proposed | Deprecated | Superseded by ADR-XXX
**Date**: YYYY-MM-DD
**Version**: First versioned release where this applies

## Context
What forces are at play? What's the situation that demands a decision?

## Decision
What did we decide, stated as a verb in present tense?

## Consequences
**Positive** — what we gain
**Negative** — what we trade away
**Risks** — what could go wrong

## Alternatives considered
What other options were on the table, and why were they rejected?
```

## When to write a new ADR

Before any of these:
- Adding a new layer to the system (e.g., "live feeds layer")
- Adding a new dependency (e.g., "switch from DuckDB to Postgres")
- Reversing an existing decision (this writes a "Supersedes" ADR)
- Adding a non-trivial abstraction (e.g., "plugin system for strategies")

> **Test**: if you can't write the ADR cleanly, the change probably doesn't belong in Helios.

## Index

| # | Title | Status | Closes off |
|---|---|---|---|
| 001 | No HFT / intraday infrastructure | Accepted | websocket, async, streaming, sub-second execution |
| 002 | Polars-native indicators | Accepted | TA-Lib, pandas-ta, indicator-as-a-service deps |
| 003 | Portfolio layer before paper trading | Accepted | "deploy first, learn later" anti-pattern |
| 004 | Human Telegram approval for entries | Accepted | autopilot, kill-switch ladders, real-time alerts |
| 005 | Deterministic regime over HMM/ML | Accepted | latent-state estimation, sklearn deps, regime model overfit |
| 006 | Cohesion over abstraction in v0.1 | Accepted | premature plugin systems, class hierarchies |
