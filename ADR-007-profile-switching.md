# ADR-007: Regime-conditional Budget Profile Switching

**Status**: **Proposed** (not Accepted; recorded for future re-evaluation)
**Date**: 2026-05-17
**Version**: Idea surfaced in v0.1.14.1.2 budget-sweep experiment

## Context

The v0.1.14.1.2 budget-sweep experiment compared 5 risk-budget configurations on the same backtest. Unexpected result: the CONCENTRATED profile (3 positions × 30%, vs default 5 × 20%) outperformed on every OOS metric:

| | CURRENT (default) | CONCENTRATED |
|---|---|---|
| CAGR | +5.86% | **+7.23%** |
| Max DD | -11.71% | **-9.57%** |
| Profit factor (gross) | 4.13 | **7.08** |
| Win rate | 54.5% | **60.7%** |

This is structurally interesting because concentration normally *increases* drawdown — but here it *reduced* it, implying the selector's score ranking carries genuine information content (forcing it to pick fewer, higher-score signals improves quality).

The natural question: should default config switch to CONCENTRATED?

The natural extension: should config be **regime-conditional**? In high-conviction bull regimes (e.g., strong trend + low vol + broad participation), concentrate. In choppier conditions, stay diversified.

## Reasons NOT to act on this finding now

1. **Sample size**: CONCENTRATED OOS had only 28 trades. PF 7.08 standard error is wide — "true" PF could plausibly fall anywhere from 4 to 9.
2. **CURRENT already passes deployment threshold** (v0.1.14.1 verdict: substantively STRONG PASS). Replacing a validated default with an under-sampled alternative is high-risk / low-value.
3. **Operational complexity**: profile switching introduces regime-dependent execution logic — a violation of ADR-001 minimalism and ADR-006 cohesion (would add at minimum a `regime → profile` lookup, a `profile_active` field in DB, and a daily decision step).
4. **Survivorship bias risk**: backtest covers ~2.4 years of OOS, mostly AI bull regime. CONCENTRATED may simply be exploiting the homogeneity of one favorable regime. Cannot be ruled out from current data.
5. **Operator load**: switching profiles means the operator must mentally track "we're in CONCENTRATED mode this week" — adding cognitive overhead for marginal CAGR improvement.

## Decision (Proposed)

**Do NOT implement profile switching in v0.1.** Keep CURRENT (5 × 20%) as the single default until at least one of these triggers fires:

### Promotion triggers

This ADR moves from **Proposed** to **Accepted** only when:

- **Trigger A**: 3+ months of paper trading data shows CONCENTRATED would have outperformed CURRENT (re-run on actual fills, not just backtest).
- **Trigger B**: A bear regime is observed in paper trading and CURRENT survives but CONCENTRATED would have crashed (showing regime-conditional logic is necessary, not just nice).
- **Trigger C**: Sample size for CONCENTRATED reaches ≥ 60 trades AND PF still >> CURRENT's after costs.

### If promoted, intended design

```python
def select_budget_profile(regime: str, conviction_score: float) -> RiskBudget:
    if regime == 'bull' and conviction_score >= 0.85:
        return CONCENTRATED_BUDGET  # 3 × 30%, etf<40%, sec<30%
    return DEFAULT_BUDGET          # 5 × 20%
```

Where `conviction_score` is a single deterministic number combining regime strength signals (e.g., TAIEX 50-day momentum, vol persistence, sector breadth). To be designed when (if) promoted.

## Consequences if eventually accepted

**Positive (hypothesized)**
- Higher CAGR in strong bull regimes
- Lower max DD (per F experiment)
- Stronger PF (per F experiment)

**Negative**
- More operational complexity (regime → profile lookup, conviction score computation)
- Cognitive overhead for operator (must know which profile is active)
- New failure mode: profile switch at wrong moment (e.g., concentrate just before regime breaks)
- Backward compatibility break for backtest interpretation (old runs use single profile, new runs use switched profiles)

**Risks**
- The whole observation may be sample-size artifact. Real risk that promoting prematurely degrades a working system.

## Alternatives considered

1. **Promote CONCENTRATED to default unconditionally** — rejected. Sample size insufficient; CURRENT already passes; would break working system to chase under-sampled gains.
2. **Profile switching now (Accepted in v0.1)** — rejected. Operational complexity violates ADR-001/006. Premature optimization.
3. **Run more sweeps with different parameters** — rejected. More fitting on the same 5 years; need genuinely new data (paper trading) for confirmation.
4. **Discard the finding** — rejected. The observation is structurally interesting (concentration upgrading quality is rare) and should be preserved for future re-evaluation.

## Forever-rule

Until promoted to **Accepted** (via one of the triggers above), the default `RiskBudget` in `portfolio/risk_budget.py` remains:

```python
RiskBudget(max_positions=5, per_position_pct=0.20, ...)
```

Any change to default sizing or activation of profile switching requires:
1. Either a paper-trading-derived trigger above
2. A new ADR superseding ADR-007

This ADR exists to **prevent the finding from being forgotten** AND to **prevent it from being adopted prematurely**. Both failure modes are real; this ADR records the considered judgment that maintaining the status quo is the right call given current evidence.
