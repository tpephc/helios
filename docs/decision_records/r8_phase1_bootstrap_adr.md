# ADR: R8 Phase 1 Effective-N Bootstrap Method

<!-- docs/decision_records/r8_phase1_bootstrap_adr.md -->
<!-- v1.0 — 2026-06-02 -->

## Status

Accepted.

## Decision

R8 Phase 1 uses date-level moving block bootstrap for effective-n estimation.

- Resampling unit: trading date
- Block length: 5 trading days
- Block type: overlapping moving blocks
- Sampling target: date blocks, not individual events
- Within-date events: preserved as an inseparable cluster
- Number of bootstrap replications: 10,000 by default
- Random seed: fixed and recorded in run metadata
- Stratification: bootstrap is performed separately within each `regime[T-1]`
- Reported output:
  - observed event rows
  - number of unique event dates
  - bootstrap effective-n estimate
  - block length
  - resampling unit
  - seed
  - provisional finding disclaimer

## Rationale

Phase 0 identified same-day clustering as the dominant dependence structure.
Because many R8 events can occur on the same trading date, treating individual
events as independent would overstate statistical precision.

Date-level resampling preserves cross-sectional dependence among stocks that
trigger on the same date. A 5 trading-day moving block also preserves short
regime autocorrelation without introducing unnecessary model complexity.

## Rejected Alternatives

### Event-level block bootstrap

Rejected because it samples individual events and can break same-day
cross-sectional dependence. This risks overstating effective sample size.

### Stock-level cluster bootstrap

Rejected because it preserves within-stock serial dependence but does not
directly address market-wide same-day clustering, which is the primary observed
dependence source in Phase 0.

## Governance Constraint

This bootstrap method is an inference-support mechanism only. It does not
validate alpha, execution viability, or production deployment. All Phase 1
findings remain provisional pending P1-DATA remediation.
