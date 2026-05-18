# Helios Review Archive

> Preserved external reviews of Helios's design and implementation.

## Why this directory exists

Throughout v0.1 development, Helios received multiple rounds of external review.
These reviews shaped key architectural decisions (portfolio layer before paper
trading, Simplicity Doctrine, Failure Modes section, state machine specification, etc.).

This directory **preserves the review record** so future maintainers (including
future-you) can reconstruct *why* the system looks the way it does — not just
*what* it looks like.

## canonical/ vs archive/

Per implementer feedback (v0.1.14.2-b confirmation): not all reviews are equally
load-bearing for the active mental model. Split:

- **`canonical/`** — reviews that establish or modify the current architecture / philosophy
  - Read these to understand Helios's design tenets
  - These remain consulted as design references going forward
  - Examples: portfolio-cluster warning, A-/A architecture reviews, decision confirmations

- **`archive/`** — older reviews, intermediate thinking, superseded recommendations
  - Read these for historical context / decision archaeology
  - Not part of active mental model
  - Examples: early backtest results, exploratory plans that got refined

## Convention

Filenames: `YYYY-MM-DD_vX.Y.Z[.W]_<slug>.md`

Each review file should have a brief frontmatter:
```yaml
---
date: 2026-05-17
version: v0.1.14.1.3
status: canonical | archive
rating: A- | etc. (if given)
key_decisions:
  - decision 1
  - decision 2
---
```

Then preserve the review content (synthesized or quoted as appropriate; full text
not required — preserve the load-bearing insights).

## What NOT to put here

- Slack conversations / chat history
- Daily standup notes
- Personal observations / journal entries (those go in `RESEARCH_JOURNAL.md`)
- Code review comments (those live in PR discussions)

This directory is for **external architectural feedback** that shaped the system.
