# PR-MS1.0 — Q-MS1-04 Precedence and Equality Disposition Draft
Canonical Path: docs/research/pr_ms1_0_q_ms1_04_precedence_equality_disposition.md

Version: v0.1.4
Status: DRAFT — ADVERSARIAL REVIEW REQUIRED
Scope: Q-MS1-04 rule precedence, equality semantics, and property-test deadband policy. No classifier implementation, strategy adoption, calibration, persistence, or production integration is authorised.
Prerequisite Baseline: Q-MS1-01/Q-MS1-02 joint disposition v0.1.2 and Q-MS1-03/06 joint disposition v0.1.1 are closure-ready but not yet canonically integrated.
Canonical Contract: `docs/research/pr_ms1_0_security_market_state_domain_contract.md` v0.1.1 (`dca8f0b`)
Upstream Semantic Boundary: `docs/research/pr_ms0_repository_semantic_audit_decision_record.md` (`45f8fea`)

## 0. Decision Labels

- **VERIFIED EXECUTION FINDING** — read-only repository execution supplied at this entry; it must be re-observed against the lock HEAD.
- **FORMAL DERIVATION** — conclusion from the declared rule templates.
- **PROPOSED DECISION** — normative candidate requiring review and lock.
- **OPEN PARAMETER** — a named value not settled by this draft.

## 1. Entry Evidence

### 1.1 Candidate rule set

**PROPOSED DECISION:** V1 admits exactly the following parameterisation of the Q-MS1-01/02 candidate templates:

```text
CONFIRMED_RECLAIM(L, K=3)
FAILED_RECLAIM(L)          # fixed three-session template
L ∈ {20, 50}
```

`K=3` makes confirmation a completed three-session observation rather than a one-bar crossing, and aligns its fixed observation horizon with the existing three-session `FAILED_RECLAIM` event template. This is a semantic V1 choice, not an empirically optimised holding-period, entry, or execution parameter.

**PROPOSED DECISION:** No moving-average lookback other than 20 or 50 is admitted in V1. The bounded domain follows the verified repository finding that existing per-security reclaim/persistence feature functions consume SMA20 and SMA50 primitives. SMA10, SMA100, SMA200, and any other lookback are excluded unless a superseding Q-MS1-01/04 disposition admits them with their own rule IDs, precedence rows, history requirements, and acceptance fixtures.

The four parameterised candidate rule identifiers are:

```text
failed_reclaim_ma50
failed_reclaim_ma20
confirmed_reclaim_ma50_k3
confirmed_reclaim_ma20_k3
```

Their definitions are owned by Q-MS1-01/02. This document neither creates a new MarketState member nor imports a strategy setup threshold.

### 1.2 Observed overlap counts

**VERIFIED EXECUTION FINDING:** A read-only query of `listed_market_daily_price_adj`, using adjusted closes, per-security rolling SMA20/SMA50, and the candidate `K=3` confirmation template, produced:

| Candidate pair | Simultaneous matches |
| --- | ---: |
| `confirmed_ma20 ∩ confirmed_ma50` | 85,365 |
| `failed_ma20 ∩ failed_ma50` | 482 |
| `confirmed_ma20 ∩ failed_ma20` | 0 |
| `confirmed_ma50 ∩ failed_ma50` | 0 |
| `confirmed_ma20 ∩ failed_ma50` | 721 |
| `confirmed_ma50 ∩ failed_ma20` | 1,444 |

| Candidate rule | Matches |
| --- | ---: |
| `confirmed_ma20` | 106,528 |
| `confirmed_ma50` | 118,664 |
| `failed_ma20` | 3,961 |
| `failed_ma50` | 2,430 |

These counts are descriptive overlap evidence only. They are not a backtest, predictive-performance claim, strategy recommendation, or calibration basis. The exact repository HEAD, database snapshot identity, eligible-session policy, and numeric implementation must be recorded when this finding is promoted to lock evidence.

### 1.3 Consequences

**FORMAL DERIVATION:** For one fixed `L`, `CONFIRMED_RECLAIM(L, 3)` requires `adj_close[t] > SMA_L[t]`, whereas `FAILED_RECLAIM(L)` requires `adj_close[t] < SMA_L[t]`; the two are mutually exclusive. The observed zero counts are consistent with that proof.

**VERIFIED EXECUTION FINDING:** Same-state cross-lookback and cross-state cross-lookback matches occur. Therefore mutual exclusivity cannot establish one unique `matched_rule_id` for the admitted four-rule set. A total deterministic precedence is required.

`INDETERMINATE` SHALL NOT be used for any positive multi-match because its locked meaning is zero positive-rule matches.

## 2. Precedence Disposition

### 2.1 Proposed total order

**PROPOSED DECISION:** Evaluate every admitted rule against the same valid, history-sufficient DTO. Collect all positive matches, then select exactly one `matched_rule_id` by this descending total priority:

```text
1. failed_reclaim_ma50
2. failed_reclaim_ma20
3. confirmed_reclaim_ma50_k3
4. confirmed_reclaim_ma20_k3
```

The result state is the state owned by the selected rule. The classifier SHALL evaluate no rule only when history is insufficient; it SHALL return `INDETERMINATE` only when the positive-match set is empty.

### 2.2 Rationale and non-rationale

**PROPOSED DECISION:** A `FAILED_RECLAIM` match has precedence over a `CONFIRMED_RECLAIM` match when different lookbacks produce both matches at the same `as_of`. This prevents a short- or long-window reclaim from concealing an admitted failure pattern that is simultaneously present in the canonical panel.

Within one state template, MA50 has precedence over MA20 because it uses the longer declared structural lookback. This is a deterministic identity-selection rule, not an assertion that MA50 is more profitable, safer, more predictive, or suitable for any strategy action.

### 2.3 Complete overlap matrix

| Positive matches at one `as_of` | Required output | Basis |
| --- | --- | --- |
| none | `INDETERMINATE`, `state=None`, `matched_rule_id=None` | locked zero-match semantics |
| only `confirmed_reclaim_ma20_k3` | `CONFIRMED_RECLAIM`, that rule ID | single match |
| only `confirmed_reclaim_ma50_k3` | `CONFIRMED_RECLAIM`, that rule ID | single match |
| both confirmed rules | `CONFIRMED_RECLAIM`, `confirmed_reclaim_ma50_k3` | total order |
| only `failed_reclaim_ma20` | `FAILED_RECLAIM`, that rule ID | single match |
| only `failed_reclaim_ma50` | `FAILED_RECLAIM`, that rule ID | single match |
| both failed rules | `FAILED_RECLAIM`, `failed_reclaim_ma50` | total order |
| any failed rule and any confirmed rule | `FAILED_RECLAIM`, highest-priority matching failed rule | total order |

The last row covers every cross-lookback and higher-order combination. Same-lookback confirmed/failed combinations are formally impossible under Section 1.3; their appearance in an implementation is a contract violation, not an alternate precedence case.

### 2.4 Research interpretation note

**VERIFIED EXECUTION FINDING:** In the Section 1.2 entry sample, the raw confirmed-match union is `139,827` rows:

```text
106,528 + 118,664 - 85,365 = 139,827
```

The two mutually disjoint cross-lookback failure overrides total `2,165` rows (`721 + 1,444`), or approximately `1.55%` of that raw confirmed-match union. In this particular observed sample, the final `CONFIRMED_RECLAIM` output count is therefore `1.55%` smaller than the raw confirmed-rule union count would be under the hypothetical absence of a precedence policy.

This is an expected consequence of deterministic state selection, not a data-quality exception and not a stable population estimate. Research that needs raw rule-trigger frequencies SHALL not infer them from final `MarketState` counts alone; it must use a separately governed rule-evaluation trace or reproduce the rule evaluation from immutable panel provenance. Q-MS1-08 owns any decision to export such trace data.

### 2.5 Evaluation discipline

**PROPOSED DECISION:** Precedence selects an output only after all admitted rules have been evaluated. It SHALL NOT short-circuit rule evaluation merely because a higher-priority rule matched: Q-MS1-04 acceptance tests must be able to establish that a lower-priority positive match was resolved by declared precedence, not hidden by skipped evaluation.

The rule-set hash SHALL include the ordered rule identifiers and this total precedence order. Changing the ordering is a semantic rule-set change.

## 3. Equality Policy

### 3.1 Canonical comparison operators

**PROPOSED DECISION:** Rule equality semantics are exact over the canonical numeric representation selected by Q-MS1-03/06:

| Rule | Session condition | Operator |
| --- | --- | --- |
| `confirmed_reclaim_ma{L}_k3` | each of `t-2`, `t-1`, `t` | `adj_close > SMA_L` |
| `failed_reclaim_ma{L}` | `t-2` | `adj_close < SMA_L` |
| `failed_reclaim_ma{L}` | `t-1` | `adj_close >= SMA_L` |
| `failed_reclaim_ma{L}` | `t` | `adj_close < SMA_L` |

No implementation tolerance may alter a classifier comparison. A value equal to its SMA is non-qualifying for `CONFIRMED_RECLAIM`; it is qualifying only for the middle session of `FAILED_RECLAIM`.

### 3.2 Exact-boundary fixtures

**PROPOSED DECISION:** PR-MS1.1 shall supply fixtures for exact equality, immediately below, and immediately above each stated comparison boundary. Fixtures must independently verify both the rule result and final precedence-selected `matched_rule_id` when another rule also matches.

## 4. Property-Test Deadband Policy

### 4.1 Proposed sampling rule

**PROPOSED DECISION:** Transform-invariance property tests SHALL use declarative exclusion, never tolerance-based success assertions. A generated panel is eligible only when every tested rule comparison is farther from its boundary than its declared scale-relative deadband:

```text
abs(adj_close[i] - SMA_L[i])
    / max(abs(adj_close[i]), abs(SMA_L[i]))
    > epsilon_relative
```

`epsilon_relative` is an **OPEN PARAMETER** that must be fixed together with the canonical numeric representation before Q-MS1-04 can close. The same value and formula must be part of `rule_set_hash` coverage. Because adjusted prices and SMA values are positive, the denominator is non-zero.

This deadband restricts property-test sample construction only; it SHALL NOT change the exact classifier comparison semantics in Section 3.

### 4.2 Required property assertions

For each eligible panel `P` and finite positive scale factor `c`, PR-MS1.1 shall assert:

```text
classify(c * P).status          == classify(P).status
classify(c * P).state           == classify(P).state
classify(c * P).matched_rule_id == classify(P).matched_rule_id
```

Factors and panels that overflow, underflow, become non-finite, or enter a declared deadband are excluded constructively. Equality fixtures in Section 3.2 remain mandatory and are not replaced by property tests.

## 5. Closure Criteria

Q-MS1-04 may close only when:

1. Q-MS1-01/02 is canonically integrated or locked as the exact rule-template baseline;
2. the exact admissible rule IDs, `L` domain, and `K` value are closed;
3. the total precedence order is accepted or replaced by a fully enumerated deterministic order;
4. every overlap row, including higher-order multi-match combinations, maps to exactly one `matched_rule_id`;
5. same-lookback cross-state mutual exclusion has a mechanical proof and implementation fixture;
6. exact equality operators and boundary fixtures are fixed;
7. the canonical numeric representation and `epsilon_relative` value are fixed, with the deadband formula in `rule_set_hash` coverage. Q-MS1-03/06 v0.1.1 fixes binary64 and `epsilon_relative = 1e-10`; this item is satisfiable when those clauses are jointly integrated into the canonical contract;
8. declared-exclusion property tests cover every `PRICE_SCALE` rule and assert status, state, and `matched_rule_id` invariance.

## 6. Session Handoff

### Session Summary

Repository execution shows that the proposed MA20/MA50 reclaim rules have material same-state and cross-lookback overlap. A precedence decision is therefore an implementation precondition, not optional documentation.

### Decision Record

- Same-lookback confirmed/failed rules are formally mutually exclusive.
- Cross-lookback and same-state overlaps occur in repository data.
- This draft proposes a total priority order rather than redefining `INDETERMINATE`.

### Open Questions

- Accept, modify, or reject the proposed total order.
- Re-observe overlap evidence with recorded repository HEAD and database/panel snapshot identity.

### Pending Integration Actions

- Canonically integrate the fixed binary64 numeric policy and `epsilon_relative = 1e-10` from Q-MS1-03/06 v0.1.1.

### Evidence

The Section 1.2 counts came from a supplied read-only execution. They require reproducible lock evidence before canonical integration.

### Next Actions

Obtain adversarial review of the total order and deadband proposal. On acceptance, run a reproducible evidence command that records HEAD, database identity, and the full positive-match bitmask distribution before canonical integration.
