# ADR-006: Cohesion over abstraction in v0.1

**Status**: Accepted
**Date**: 2026-05-17
**Version**: v0.1 (foundational decision)

## Context

When building any non-trivial system, the engineering instinct is to **factor early**:
- "Make indicators pluggable" → strategy interface, plugin registry
- "Make regime classifiers swappable" → ABC + multiple implementations
- "Make backtest engines composable" → event-driven framework

These instincts are not wrong — but in v0.1 they are **premature**.

Forces:
- We have **one** strategy (TrendBreakout). Designing a plugin system around it would optimize for hypothetical future strategies.
- We have **one** regime classifier. Same logic.
- We have **9** indicators. Abstracting each into a class would 10x the LOC.
- Premature abstraction **hides intent**. A 5-line Polars expression is more readable than a 50-line `RSIIndicator` class with `compute()` method.
- Premature abstraction **resists refactoring**. Once a plugin system is in place, removing it costs more than removing concrete code.

Reviewer phrased it:
> "Few robust features 比 many fragile features 更有價值. v0.1 prioritize cohesion: single file per layer, refactor only when complexity DEMANDS it."

## Decision

**In v0.1, each major concern lives in a single file with concrete (non-abstract) functions and dataclasses. Refactor toward abstraction only when complexity demands it.**

Specifically:
- `features/technical.py` — all 9 indicators in one module
- `features/regime.py` — one regime classifier
- `strategies/trend_breakout.py` — one concrete strategy
- `strategies/exit/regime_exit.py` + `trailing_stop.py` — two concrete exits (ABC `ExitRule` exists, but used only because the simulator iterates `for rule in exits`)
- `backtest/round_trip.py` — one backtest engine
- `portfolio/risk_budget.py` — one budget dataclass

Abstractions only exist where they're **mechanically required** (e.g., `Strategy` ABC because the runner needs polymorphism, `ExitRule` ABC because the simulator iterates them).

## Consequences

**Positive**
- Fast to navigate: "where is RSI math?" → `grep rsi features/technical.py` → done
- Fast to read: a layer fits on one screen
- Fast to change: no scaffolding to update
- Easier to onboard: new collaborator reads one file per layer
- Easier to delete: concrete code is removable; abstraction is sticky

**Negative**
- When v0.3 adds a second strategy (e.g., mean-revert), `strategies/` will need a small refactor. **Acceptable** — refactor when 2nd implementation exists, not before.
- Some duplication may emerge across modules. **Acceptable** — duplicate first, abstract on the 3rd occurrence (the "Rule of Three").
- "Architecture" looks less impressive at v0.1. **Acceptable** — we're optimizing for working software, not impressive diagrams.

**Risks**
- Cohesion may make refactor expensive when finally needed. **Mitigation**: deliberate refactor in a dedicated version (e.g., v0.3 strategy refactor) with its own ADR.

## What stays concrete vs. abstract in v0.1

| Concept | Treatment in v0.1 | Justification |
|---|---|---|
| Indicators | Concrete functions in `technical.py` | Math is fixed; no polymorphism needed |
| Regime classifier | Concrete function in `regime.py` | Only one classifier |
| Strategy | ABC + 1 impl | Runner iterates strategies (1 today, 2+ future) |
| Exit rule | ABC + 2 impls | Simulator iterates priority-ordered rules |
| Backtest engine | Concrete class | Only one engine (round_trip / portfolio_simulator) |
| Risk budget | Frozen dataclass | Pure data, no behavior |
| Sector classification | Hardcoded dict | 15 symbols; v0.2 will compute from `company_metadata` |
| Database access | Concrete `connect()` | DuckDB is the choice; no need for "DB abstraction layer" |

## Alternatives considered

1. **Plugin system from day 1** — rejected. Premature; no second implementation exists for most concepts.
2. **Heavy ABC usage for "good OOP"** — rejected. Polymorphism without need is just verbose code.
3. **Wait until v1.0 to refactor** — accepted but tracked. Refactor triggers will be: (a) 2nd strategy added, (b) 2nd regime model added, (c) sector classification proven need to be dynamic.

## Forever-rule

Before adding an abstraction, ask:
1. Does a second concrete implementation **exist today** (not "might in future")?
2. Does the abstraction **simplify** the consumer code, or just relocate the complexity?
3. Will the abstraction be **removable** if the second implementation doesn't materialize?

If the answer to any of these is "no", the abstraction is premature.
