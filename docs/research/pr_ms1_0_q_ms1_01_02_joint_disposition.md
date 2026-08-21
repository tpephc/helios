# PR-MS1.0 — Q-MS1-01 / Q-MS1-02 Joint Disposition Draft
Canonical Path: docs/research/pr_ms1_0_q_ms1_01_02_joint_disposition.md

Version: v0.1.2
Status: DRAFT — ADVERSARIAL REVIEW REQUIRED
Scope: Q-MS1-01 vocabulary and Q-MS1-02 canonical input contract only. No classifier implementation, rule threshold calibration, precedence decision, persistence, strategy adoption, or production integration is authorised.
Canonical Contract: `docs/research/pr_ms1_0_security_market_state_domain_contract.md` v0.1.1 (`dca8f0b`)
Upstream Semantic Boundary: `docs/research/pr_ms0_repository_semantic_audit_decision_record.md` (`45f8fea`)
Integration Source: `docs/research/pr_ms1_0_security_market_state_domain_contract_governance_addendum.md` v0.3.1 (`56db5b1`)

## 0. Decision Labels

- **VERIFIED REPOSITORY FINDING** — current-source evidence observed at entry.
- **PROPOSED DECISION** — normative candidate requiring review and lock.
- **EXCLUDED** — not admitted to V1 under this disposition.
- **DEFERRED** — intentionally not decided in Q-MS1-01/02.

## 1. Entry Evidence and Boundary

**VERIFIED REPOSITORY FINDING:** Entry `HEAD` and `origin/main` both resolved to `dca8f0bdad63265239f6c3220ec0a87a5cfdb607`; `git status --short` produced no output.

Source observations used by this draft:

- `features/bullish_features.py` and `features/bearish_regime.py` are pure, per-security, close-time feature layers, not state machines or signal generators.
- `features/bullish_features.compute_persistence_features` / `compute_reclaim_features` and `features/bearish_regime.compute_persistence_features` / `compute_failed_reclaim_features` consume SMA20 and SMA50 primitives.
- Their volume thresholds are explicitly `[ASSUMED]` and their volume inputs originate from raw volume.
- `features/technical.py` computes ATR from adjusted OHLC and stores inclusive Donchian channels.
- `strategies/trend_breakout.py` uses `LAG(donchian_20_high, 1)` for its actual breakout boundary.
- `features/dividend_adjustment.py` and the associated schema establish multiplicative backward adjusted OHLC and raw volume.

This disposition does not treat any existing bullish/bearish feature name, setup threshold, or strategy consumer as an authorised MarketState definition.

## 2. Q-MS1-01 — Vocabulary Disposition

### 2.1 Proposed V1 vocabulary

**PROPOSED DECISION:** The finite V1 `MarketState` vocabulary contains exactly:

```text
CONFIRMED_RECLAIM
FAILED_RECLAIM
```

No residual state is permitted. A valid, history-sufficient input matching neither positive rule returns `ClassificationStatus.INDETERMINATE` with `state=None`.

### 2.2 `CONFIRMED_RECLAIM` rule template

For a selected moving-average lookback `L` and confirmation-session count `K`, evaluated at `as_of=t`:

```text
for every i in [t-K+1, t]:
    adj_close[i] > SMA_L[i]
```

The strict `>` boundary is intentional. Any `i` in the stated window with `adj_close[i] <= SMA_L[i]` makes the entire window-AND false; there is no partial credit or streaming counter. The result becomes observable at the close of `t`, when the Kth qualifying bar has completed. It SHALL NOT be backfilled to the earlier crossing bar.

This is a snapshot rule: a later snapshot may independently satisfy the same template, but the classifier shall never assign a confirmation to an earlier `as_of` using bars after that `as_of`.

### 2.3 `FAILED_RECLAIM` rule template

For a selected moving-average lookback `L`, evaluated at `as_of=t`:

```text
adj_close[t-2] <  SMA_L[t-2]
adj_close[t-1] >= SMA_L[t-1]
adj_close[t]   <  SMA_L[t]
```

The finite event window is exactly three sessions. The rule is known only at the close of `t`; it SHALL NOT be assigned to `t-1`. No unbounded "previously" or "ever" history predicate is permitted.

### 2.4 Candidate parameter domain

**VERIFIED REPOSITORY FINDING:** Existing bullish and bearish feature functions consume SMA20 and SMA50 primitives. This draft proposes the parameter domain:

```text
L ∈ {20, 50}
K = governed positive integer
```

Q-MS1-04 owns the final selection of `L`, `K`, all threshold/equality fixtures, and every overlap outcome. This draft does not choose a strategy setup threshold.

### 2.5 Explicit exclusions

The following are not V1 states under Q-MS1-01:

| Surface | Disposition | Reason |
| --- | --- | --- |
| MA persistence | primitive only | May support a later positive rule; not itself a state in this vocabulary. |
| ATR compression | primitive only | Allowed only as a self-normalised price quantity; threshold remains uncalibrated. |
| Donchian breakout/breakdown | primitive only | Requires an explicit prior-window boundary; not a state in this vocabulary. |
| Accumulation/base | EXCLUDED | Current definition depends on raw volume. |
| Breakout quality | EXCLUDED | Current definition depends on raw volume. |
| Distribution sequence | EXCLUDED | Current definition depends on raw volume. |
| Relative strength/weakness vs TAIEX | DEFERRED | External benchmark context is not admitted by this disposition. |
| Broad `regime` | EXCLUDED | TAIEX broad-market context is not security Market State. |

`INDETERMINATE` coverage is a research diagnostic, not a target to optimise. No residual state may be created merely to increase coverage.

## 3. Q-MS1-02 — Canonical Input Disposition

### 3.1 Input ownership

**PROPOSED DECISION:** Input assembly owns PIT-valid data access and creates an ordered, single-security canonical adjusted-OHLC panel. The pure classifier owns deterministic calculation of its admitted SMA, ATR, and prior-window Donchian primitives from that panel.

The classifier SHALL NOT depend on precomputed `daily_features`, bullish/bearish feature tables, feature-schema version, database access, filesystem access, network access, or strategy setup output.

### 3.2 DTO minimum shape

```text
SecurityMarketStateInput
  security_id: SecurityId
  as_of: TradingSession
  bars: ordered non-empty sequence[AdjustedOhlcBar]

AdjustedOhlcBar
  session: TradingSession
  adj_open: finite positive decimal
  adj_high: finite positive decimal
  adj_low: finite positive decimal
  adj_close: finite positive decimal
```

Required invariants:

```text
bars are strictly session-ascending
bars[-1].session == as_of
adj_low <= min(adj_open, adj_close) <= max(adj_open, adj_close) <= adj_high
all required values are finite
len(bars) >= 1
```

`volume` is not an admitted V1 classifier input. `panel_snapshot_id`, adjustment provenance, assembly schema version, and history/operational diagnostics belong to `MarketStateExportRecord`, not this pure classifier DTO.

For each rule `R` after sufficiency has been established, classifier calculation SHALL consume the trailing rule-local slice:

```text
rule_bars(R) = bars[-required_history_sessions(R):]
```

Each rule computes its indicators only from `rule_bars(R)`. The longer classifier-level panel SHALL NOT alter a shorter rule's indicator window.

### 3.3 Indicator calculation is part of classifier identity

**PROPOSED DECISION:** `rule_set_hash` and `classifier_version` cover every classification-relevant indicator specification:

- source fields and bar-adjustment basis;
- indicator algorithm and lookback;
- inclusive/exclusive window semantics;
- true-range definition, smoothing method, and parameters for ATR;
- missing-value and finite-value policy;
- numeric, rounding, equality, and threshold/deadband policy.

A semantic change to any listed item requires a new `rule_set_hash` and classifier-version treatment under the canonical contract. A pure refactor may preserve identity only when it is governed as numerically equivalent for the stated policy.

### 3.4 Required history

For a rule using `SMA_L` over a K-session confirmation/event template:

```text
required_history_sessions(R) = L + K - 1
```

For `FAILED_RECLAIM`, `K=3`, hence `required_history_sessions(R)=L+2`.

The classifier-level scalar is:

```text
required_history_sessions = max(required_history_sessions(R)
                                for R in admitted_rules)
```

The classifier, not assembly, compares `len(bars)` with this scalar. If the DTO has fewer sessions than the scalar, the classifier returns `INSUFFICIENT_HISTORY`; no rule is evaluated. Insufficient length is a valid classifier input condition, not a structural DTO violation and not a typed validation exception. Assembly SHALL NOT pre-filter/reject a structurally valid DTO by applying classifier rule-window knowledge. Assembly may additionally emit `NATURAL_HISTORY_SHORTFALL`, `DATA_GAP`, or `DIAGNOSIS_UNAVAILABLE` through export diagnostics.

The formula counts canonical eligible trading sessions, not calendar days. Its actual eligibility basis depends on the still-open Taiwan-market exceptional-bar disposition. Price-limit locked sessions, suspension/resumption, zero-volume sessions, and missing bars SHALL be resolved before this formula is treated as a final operational history requirement.

### 3.5 Scale-invariance classification

`CONFIRMED_RECLAIM` and `FAILED_RECLAIM` are `PRICE_SCALE` rules: multiplying all adjusted OHLC prices by any finite positive constant multiplies the SMA by the same constant and preserves every stated inequality.

ATR compression, if admitted later as a primitive, shall be self-normalised, for example:

```text
ATR[t] / mean(ATR[t-N : t-1])
```

Raw ATR compared against an absolute price threshold is forbidden.

### 3.6 Donchian boundary

The existing `donchian_high[t]` / `donchian_low[t]` includes bar `t`. Testing `adj_close[t] > donchian_high[t]` is self-referential and almost never satisfiable because:

```text
donchian_high[t] >= adj_high[t] >= adj_close[t]
```

This is a rule-design defect, not future-information leakage. Any future V1 Donchian rule must instead define a prior boundary explicitly:

```text
prior_donchian_high[t] = donchian_high[t-1]
prior_donchian_low[t]  = donchian_low[t-1]
```

Donchian is not an admitted Q-MS1-01 state and this draft authorises no technical-feature code change.

## 4. Adjustment and PIT Consequences

### 4.1 Variant C remains enabled

The adjusted OHLC input inherits the verified multiplicative backward-adjustment mechanics. For future action `ex_date > as_of`, every adjusted price in a fixed panel window undergoes common positive rescaling. `PRICE_SCALE` reclaim rules must preserve status, state, and `matched_rule_id` under the Variant C composed-pipeline test.

### 4.2 Variant C-2 impact radius

**PROPOSED DECISION:** The current immutable-provenance gap applies to the complete derived chain:

```text
affected adjusted-OHLC panel
→ classifier-computed SMA / ATR / prior Donchian
→ all derived rule evaluations and ClassificationResult
→ associated export, replay, and audit claim
```

Until immutable adjustment-factor-set revision provenance exists, a late or corrected action with `ex_date <= as_of` invalidates replay/audit claims for every affected derived-indicator classification. Variant C-2 remains DEFERRED and excluded from PR-MS1.1 composed-pipeline acceptance.

## 5. Q-MS1-04 Handoff Boundary

Q-MS1-04 shall enumerate, not merely describe, every candidate overlap for `L ∈ {20, 50}` and both state templates:

| Pair category | Required treatment |
| --- | --- |
| same state, MA20 vs MA50 | precedence or mechanically proven equivalence/mutual exclusivity |
| `CONFIRMED_RECLAIM` vs `FAILED_RECLAIM` on the same MA | precedence or mechanically proven mutual exclusivity |
| `CONFIRMED_RECLAIM` vs `FAILED_RECLAIM` across MA20/MA50 | precedence or mechanically proven mutual exclusivity |
| multiple parameterised matches of any kind | deterministic single `matched_rule_id` outcome |

`INDETERMINATE` SHALL NOT absorb a multi-match conflict because it denotes zero positive-rule matches.

## 6. Closure Criteria

Q-MS1-01/02 may close only when the canonical contract contains all of the following:

1. the exact finite vocabulary and no-residual rule;
2. positive reclaim/failed-reclaim templates with equality and `as_of` semantics;
3. the canonical adjusted-OHLC DTO and its invariants;
4. no precomputed feature table or raw volume as a V1 classifier dependency;
5. classifier-owned indicator calculation and hash/version coverage;
6. the classifier-owned scalar history comparison and no-partial-evaluation policy; insufficient history is a status outcome, not a DTO invariant violation;
7. explicit Donchian prior-boundary restriction;
8. Variant C price-scale obligation and C-2 derived-indicator impact/deferred boundary;
9. Q-MS1-04 handoff covering every overlap category.
10. The canonical eligible-session definition and Taiwan-market exceptional-bar treatment are closed; only then may the history formula be treated as an operational requirement.

## 7. Session Handoff

### Session Summary

This draft proposes a minimal, price-only MarketState vocabulary and a pure canonical adjusted-OHLC input. It intentionally refuses strategy setup thresholds, raw-volume features, external benchmark context, and a residual state.

### Decision Record

- Candidate states: `CONFIRMED_RECLAIM`, `FAILED_RECLAIM`.
- Classifier input: canonical adjusted OHLC; indicators are computed inside the pure classifier.
- C-2 affects all derived indicators and remains deferred.

### Open Questions

- Q-MS1-04: MA parameter selection, `K`, complete overlap matrix, and threshold/deadband policy.
- Q-MS1-03/06/07/08 remain outside this disposition.

### Evidence

All repository statements in this draft derive from the entry evidence cited in Section 1 and must be re-observed before lock.

### Next Actions

Obtain adversarial review. If accepted, integrate the closed clauses into the canonical contract in a separate documentation commit, then begin Q-MS1-04.
