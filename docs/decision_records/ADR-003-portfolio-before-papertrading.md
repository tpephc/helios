# ADR-003: Portfolio layer before paper trading

**Status**: Accepted
**Date**: 2026-05-17
**Version**: v0.1.14.1

## Context

After v0.1.13.3 round-trip backtest delivered ✓✓ STRONG PASS (OOS net PF 2.50 / mean +1.99%), there were two plausible next steps:

**Path A**: Direct to paper trading
- Build execution layer (paper broker, telegram, daily cron)
- Learn from real signal flow
- Position sizing handled ad-hoc in execution code

**Path B**: Portfolio layer first
- Build risk_budget + selector + constrained backtest
- Re-validate alpha under capital constraints
- Then build execution on top of validated portfolio behavior

User initially preferred Path A (faster to "real" learning). Reviewer pushed back hard:

> "trade-level metrics ≠ portfolio-level deployability. ETF + 金融 已經很明顯, real portfolio drawdown 可能是 trade-level worst 的 2-3 倍. 直接 paper trade 沒有 portfolio brain = unconstrained signal stream 搬到假帳戶, 學到的東西會失真."

The concern was concrete:
- Unconstrained backtest had 132 trades — many overlapping in time
- Top performers ETFs (00878, 006208, 0050) — high mutual correlation
- Financial cluster (2881, 2882, 2891) — known to move together
- Paper trading with naive "equal weight 5 positions" would discover this the hard way

## Decision

**Build the portfolio layer (risk budget, sector cap, ETF cap, cash buffer, constrained backtest) BEFORE paper trading execution.**

Specifically:
- `portfolio/risk_budget.py` — frozen dataclass with constraints
- `portfolio/selector.py` — sector classification + ETF detection
- `backtest/portfolio_simulator.py` — capital-aware lifecycle simulator
- `scripts/run_portfolio_backtest.py` — IS/OOS partition + verdict

Defer paper trading execution to v0.1.14.2.

## Consequences

**Positive**
- Real equity curve max DD measured: -11.01% (only 1.4x trade-level worst -7.73% — far below feared 2-3x)
- Reject distribution revealed strategy character: symbol_already_held 30%, sector caps fire 30%+ — concrete intelligence about which constraints bind
- Surprise discovery: constraints UPGRADED PF (2.50 → 4.13 gross) — they filtered out the lowest-quality concentrated signals
- Conservative profile (29% avg exposure) now known + accepted as design feature, not surprise during paper trade
- Paper trading code can now be written against validated capital allocation behavior

**Negative**
- One extra round (~1 session) before paper trading
- Portfolio layer adds ~400 LOC of complexity (justified by alpha extraction)

**Risks**
- Risk budget defaults (5/20%/40%/30%/10%) chosen by intuition — may need tuning post-paper-trade. **Mitigation**: budget is a `frozen dataclass`, tuning is one parameter file away.

## Empirical validation of the decision

Reviewer's prediction was 100% confirmed:
- 145 of 217 signals (66.8%) rejected
- Biggest rejecter: symbol_already_held (30%), then etf_cap (24%), then sector_cap_financial (16%)
- Without these filters, naive paper trading would have stacked 5 ETFs / 3 financial stocks simultaneously and discovered cluster drawdown the hard way

## Alternatives considered

1. **Direct to paper trading with hardcoded "max 5 positions equal weight"** — rejected. No sector cap = financial cluster risk would manifest in production paper trades.
2. **Skip portfolio backtest, just enforce constraints in execution** — rejected. Without the constrained backtest, we wouldn't know if constraints help or hurt PF. (Answer: they help significantly.)
3. **Full portfolio optimizer (Kelly / HRP)** — rejected (see ADR-005). v0.1 keeps it deterministic.

## Forever-rule

Before moving from "backtest passes" to "deploy", validate the deployment-shaped scenario. Trade-level metrics describe alpha existence. Portfolio-level metrics describe deployability. These are not the same question.
