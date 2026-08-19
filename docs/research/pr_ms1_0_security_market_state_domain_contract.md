# PR-MS1.0 — Security Market State Domain Contract
Canonical Path: docs/research/pr_ms1_0_security_market_state_domain_contract.md

Version: v0.1.1
Status: DRAFT — CANONICAL CONTRACT CANDIDATE
Scope: Domain contract only; no classifier implementation, persistence, strategy adoption, `daily_run` integration, or production execution change.
Upstream Semantic Boundary: `docs/research/pr_ms0_repository_semantic_audit_decision_record.md` (`45f8fea39f15778dc097f699ad8333256dcd7a3f`)
Integration Source: `docs/research/pr_ms1_0_security_market_state_domain_contract_governance_addendum.md` v0.3.1 (`56db5b1`)

## 0. Authority, Evidence, and Status

This document is the canonical PR-MS1.0 candidate. PR-MS0 is the locked semantic boundary. The governance addendum is an integration source and remains an immutable review/audit artifact; it is not appended verbatim.

Evidence labels:

- **VERIFIED REPOSITORY FINDING** — supported by source evidence observed at the stated repository baseline.
- **FORMAL DERIVATION** — follows from stated verified mechanics and a stated mathematical contract.
- **PROPOSED DECISION** — normative text pending PR-MS1.0 closure and lock.
- **DEFERRED** — intentionally excluded from this phase.
- **REPOSITORY GAP** — an observed capability absence that restricts an otherwise desirable obligation.
- **INTEGRATOR ADDITION** — a non-ledger normative addition made during canonical integration; it is not closed until its stated follow-up disposition occurs.

No statement labelled VERIFIED is a claim about strategy profitability, alpha, fill quality, or production readiness.

## 1. Purpose and Non-Goals

Security Market State is a deterministic classification of one security's temporally valid market structure at `as_of=t`. It is neither broad market regime, strategy intent, candidate eligibility, portfolio state, execution state, nor account state.

PR-MS1.0 defines the semantic contract that PR-MS1.1 may implement and test. It does not authorise:

- any new strategy entry/add/exit decision;
- production persistence or scheduler integration;
- account, portfolio, order, fill, broker, queue-priority, latency, or slippage logic;
- cross-sectional ranking or universe-membership inputs;
- empirical performance claims.

## 2. Locked Upstream Constraints

The following PR-MS0 constraints are binding.

1. Ownership is within `features`; `strategies/`, `portfolio/`, and `execution/` do not own Market State.
2. The classifier owns no DuckDB, filesystem, network, broker, or Shioaji I/O. Assembly owns data access and temporal validation.
3. The InputDTO contains no account identity, position, exposure, risk budget, order, fill, venue, or strategy-eligibility state.
4. `features/win_rate_21d/` output is forbidden as a V1 classifier input.
5. There is no residual MarketState catch-all. Valid, history-sufficient non-match is `INDETERMINATE`.
6. Operational failure, insufficient history, and rule non-match remain machine-distinguishable.
7. A future strategy that requires Market State must fail closed for risk-increasing action if state is stale or unavailable; risk-reducing action is not blocked. This is a strategy-adoption obligation, not a PR-MS1.1 acceptance test.
8. Price-side rules must obey MS-P3 positive price-scale invariance.
9. Broad market regime is distinct context and is not a required V1 classifier input.

## 3. Q-MS1-00 — Snapshot Model

**PROPOSED DECISION — CLOSED:** V1 is a pure snapshot classifier.

For a valid canonical input and fixed classifier configuration, output depends only on the values in that input. It SHALL NOT accept or retrieve `prior_state`, transition history, persistent classifier state, hidden process state, account state, portfolio state, or strategy state.

```text
classify(input_dto) -> ClassificationResult
```

Transition, hysteresis, debounce, persistence, and origin/cold-start semantics are DEFERRED to a separately governed downstream layer. Q-MS1-05 is thereby closed for V1.

## 4. Domain Types and Ownership

The following is an illustrative contract sketch, not implementation.

```python
from enum import Enum


class MarketState(Enum):
    # Q-MS1-01 owns finite members and positive rules.
    pass


class ClassificationStatus(Enum):
    OK = "OK"
    INDETERMINATE = "INDETERMINATE"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"


class Availability(Enum):
    AVAILABLE = "AVAILABLE"
    OPERATIONAL_FAILURE = "OPERATIONAL_FAILURE"
```

All three are non-string enums. Export serialization occurs explicitly in the assembly/export layer using `.value`. `OPERATIONAL_FAILURE` is exclusively an `Availability` member, never a classifier status.

`ClassificationResult` is classifier-owned and is determinable from a valid DTO plus fixed `classifier_version` and `rule_set_hash`:

```text
status: ClassificationStatus
state: MarketState | None
matched_rule_id: str | None
reason_code: ClassifierReasonCode | None
classifier_version: str
rule_set_hash: str
as_of: TradingSession
```

Invariants:

```text
status == OK      <=> state is a MarketState member
status != OK      <=> state is None
matched_rule_id is not None <=> status == OK
reason_code is None <=> status == OK
```

The candidate `ClassifierReasonCode` mapping is mandatory unless superseded by an explicit Q-MS1-03 disposition:

| `ClassificationStatus` | `ClassifierReasonCode` |
| --- | --- |
| `OK` | `None` |
| `INDETERMINATE` | `NO_RULE_MATCH` |
| `INSUFFICIENT_HISTORY` | `REQUIRED_HISTORY_NOT_MET` |

Malformed DTOs raise a typed contract/validation error. They do not become `INDETERMINATE` or `INSUFFICIENT_HISTORY`.

`MarketStateExportRecord` is assembly/composed-pipeline-owned:

```text
availability: Availability
classification: ClassificationResult | None
security_id: str
panel_snapshot_id: str
adjustment_provenance: str
assembly_schema_version: str
history_diagnostics: HistoryDiagnosticCode | None
operational_diagnostics: OperationalDiagnosticCode | None
decision_available_at: Timestamp
```

Its invariants are:

```text
classification is not None <=> availability == AVAILABLE
availability == OPERATIONAL_FAILURE => operational_diagnostics is not None
availability == AVAILABLE           => operational_diagnostics is None
```

`AVAILABLE` means assembly succeeded and produced a classification. It does not mean `state` is present. A consumer requiring a MarketState must additionally require `classification.status == OK`.

`ClassifierReasonCode`, `HistoryDiagnosticCode`, and `OperationalDiagnosticCode` are separate enum types and have disjoint value spaces. History diagnostics include `NATURAL_HISTORY_SHORTFALL`, `DATA_GAP`, and `DIAGNOSIS_UNAVAILABLE`; the latter is mandatory when assembly cannot distinguish the first two. Operational diagnostics never reuse the history-diagnostic field.

## 5. Temporal Input Contract

### 5.1 `as_of` and availability

**PROPOSED DECISION — Q-MS1-06a:** `as_of=t` is close-inclusive: the complete official bar for trading session `t` is in the canonical window.

```text
window(t, N) = N canonical eligible trading-session observations,
               ordered oldest to newest, ending at and including t
decision_available_at > close_timestamp(t)
```

Strategy consumption timing is DEFERRED. A later contract cannot silently reinterpret this as open-exclusive semantics.

### 5.2 History sufficiency

V1 SHALL declare one scalar:

```text
required_history_sessions = max(window(R) for R in admitted_rules)
```

If a valid DTO has fewer canonical eligible sessions, the classifier returns `INSUFFICIENT_HISTORY` and evaluates no rule. Per-rule partial evaluation is rejected for V1 because it would make `INDETERMINATE` semantically unreliable.

### 5.3 Reference-data boundary

Q-MS1-02 SHALL close both declarations:

```text
CLASSIFIER_REFERENCE_INPUTS_ADMITTED = YES | NO
ASSEMBLY_REFERENCE_SOURCES = {calendar, security_lifecycle, ...}
```

The first governs classifier DTO fields. The second governs assembly-only sources for history diagnostics and provenance. Every admitted reference field or source requires governed effective-date semantics; undated latest-state lookup is forbidden. A calendar/security-lifecycle basis is required to distinguish a natural shortfall from a data gap.

## 6. Rule, Input, and Transform Constraints

V1 is per-security. Cross-sectional ranks, universe percentiles, current-constituent membership, candidate membership, peer aggregates, and any value dependent on another security are forbidden.

Every admitted rule declares its input domain, transform/invariance group, equality policy, and threshold deadband policy. This metadata contributes to `rule_set_hash`.

If a batch API is exposed, it accepts only valid DTOs. Under that all-valid precondition:

```text
batch_classify([dto_1, ..., dto_n])
    == [classify(dto_1), ..., classify(dto_n)]
```

Order is preserved and batch neighbours cannot affect an item's result. A malformed DTO raises a typed contract violation and fails the entire batch call; partial-success and per-item-exception return types are forbidden. Before a universe-scale caller invokes the batch API, assembly validates/filters DTOs and exports excluded-item diagnostics. That assembly containment obligation does not alter classifier fail-fast semantics.

Supported groups are `PRICE_SCALE`, `VOLUME_SHARE_UNIT`, `PRICE_VOLUME_JOINT`, and an explicitly governed `NO_ADMITTED_INVARIANCE` exception. The exception is not self-authorising: it requires a closure-gate disposition, rationale, and test-boundary treatment.

For each `PRICE_SCALE` rule and finite `c > 0` in the governed domain:

```text
R(c * P, non_price_inputs) == R(P, non_price_inputs)
```

Absolute-price thresholds are forbidden. Generated property-test samples must be constructively excluded from each declared threshold deadband. Q-MS1-04 owns the deadband-generation algorithm and strict/non-strict threshold policy; it is not closed by this draft.

For a share-unit rescaling factor `k > 0`:

```text
price' = price / k
volume' = volume * k
```

Every admitted volume or joint rule must declare and pass its appropriate transform. A price-only transform cannot be applied to a joint rule.

## 7. Taiwan-Market Bar Validity

Before range, breakout, extrema, or volume rules are admitted, Q-MS1-02/Q-MS1-06 shall disposition price-limit locked bars, suspension/resumption, zero-volume/no-trade sessions, missing bars, and new-listing history.

Each condition receives exactly one treatment: included; included with governed flag and rule handling; excluded by canonical-panel rule; or unavailable with machine-readable reason. Silent row dropping, forward filling, or ordinary-zero conversion is forbidden unless separately justified and tested.

## 8. PIT Contract

### 8.1 Variant A — future market observation

Appending or mutating observations strictly after `t` shall not change the same security's `as_of=t` classification. Equality includes status, state, `matched_rule_id`, and classifier-derived `as_of` diagnostics; run timestamps are excluded.

### 8.2 Variant B — reference data

For each admitted classifier reference input or assembly reference source, a mutation effective strictly after `t` shall not change the `as_of=t` canonical input, history diagnostic, or classification. An effective-at-or-before-`t` positive-direction fixture is required where that field is classification-relevant.

If no classifier reference input is admitted, classifier-level Variant B is N/A by contract and shall not have a vacuous passing test. If assembly sources are non-empty, assembly/composed-boundary Variant B remains required.

### 8.3 Variant C — future corporate-action restatement

**VERIFIED REPOSITORY FINDING:** `features.dividend_adjustment.compute_adjusted` applies multiplicative backward adjustment. It forms `cum_factor[T]` from event factors whose dates are strictly later than `T`, computes adjusted OHLC as raw OHLC times that factor, and excludes the event on the ex-date bar itself. `corporate_actions.date` is the ex-dividend/ex-rights trading date. Confirmed actions provide adjustment factors; forecast actions do not. `daily_price_adj.volume` is raw volume.

**FORMAL DERIVATION:** For a newly known action with `ex_date > t`, a fixed `as_of=t` adjusted-price window is uniformly rescaled by one positive factor. A `PRICE_SCALE` rule satisfying MS-P3 therefore preserves classification and `matched_rule_id`.

**PROPOSED DECISION:** Variant C is a composed-pipeline acceptance obligation. A real assembly-path fixture introducing an action with `ex_date > t` shall leave status, state, and `matched_rule_id` unchanged.

Adjusted-price/raw-volume mixed primitives, including price-times-volume, dollar volume, turnover proxies, and VWAP-like proxies, are excluded unless an adjustment-consistent joint transform is established and passes the required PIT obligations.

### 8.4 Variant C-2 — late corporate action

**REPOSITORY GAP:** Current `corporate_actions` uses primary key `(date, stock_id, kind)` and historical ingestion uses `DELETE + INSERT`. This physically destroys prior factor values. `ingested_at`, `last_event_date_used`, and `n_events_applied` are not immutable adjustment-factor-set revision provenance.

Until immutable adjustment-factor-set revision provenance exists, late-arriving or corrected actions with `ex_date <= as_of` are excluded from PR-MS1.1 composed-pipeline acceptance. Existing `ingested_at`, `last_event_date_used`, and `n_events_applied` SHALL NOT be represented as sufficient C-2 provenance. Such an action invalidates replay/audit claims for affected prior adjusted-panel classifications and requires separately governed remediation before C-2 acceptance is enabled.

Variant C-2 is therefore DEFERRED, not a passing PR-MS1.1 acceptance test. A remediation must preserve factor-set revisions through an append-only history/audit model or an equivalent immutable snapshot identity.

## 9. Versioning, Provenance, and Exports

Every classification/export carries `classifier_version` and `rule_set_hash`. The hash covers rule definitions, precedence, threshold values, numerical/equality policy, transform group, deadband policy, and vocabulary identity.

Declarative canonical rule data is the default hash source. A rule proven to require imperative expression may use a governed AST-normalized representation only if Q-MS1-01/Q-MS1-08 records the escape hatch, canonical digest procedure, and a formatting/comment-insensitivity fixture.

**INTEGRATOR ADDITION — pending separate ledger disposition:** vocabulary changes require a major classifier-version bump; predicate or threshold changes require at least a minor bump.

The export record must retain immutable panel identity, adjustment provenance, assembly schema version, history diagnostics, availability, classifier result, and decision-availability time. Wall-clock run time alone is insufficient provenance.

## 10. Decision Matrix

| ID | Required closure output | Current state |
| --- | --- | --- |
| Q-MS1-00 | Snapshot/stateful model | CLOSED: pure snapshot |
| Q-MS1-01 | Finite vocabulary and positive rules | OPEN |
| Q-MS1-02 | Canonical inputs, reference admission, volume admission, bar treatment | OPEN |
| Q-MS1-03 | Final result/diagnostic representation | OPEN; this draft supplies candidate constraints, including reason-code mapping |
| Q-MS1-04 | Rule precedence, equality/deadband algorithm | OPEN |
| Q-MS1-05 | Transition semantics | CLOSED by Q-MS1-00 |
| Q-MS1-06 | DTO/API and batch surface | OPEN only for remaining DTO/API detail; all-valid, fail-fast batch semantics are already locked |
| Q-MS1-06a | Close-inclusive `as_of` | PROPOSED |
| Q-MS1-07 | Single module or package based on ADR-006 evidence | OPEN |
| Q-MS1-08 | Export/provenance schema | OPEN |

## 11. Closure Gate

PR-MS1.0 cannot lock until every applicable item is closed or explicitly deferred without ambiguity.

1. Q-MS1-00 is closed before vocabulary, result, precedence, and API are finalised.
2. `MarketState`, `ClassificationStatus`, and `Availability` are distinct non-string enums; no residual MarketState exists.
3. Classifier result nullability, `matched_rule_id`, and per-status `reason_code` invariants are explicit.
4. Assembly availability and classifier outcomes remain distinct; envelope nullability and typed operational diagnostics are explicit.
5. Malformed DTO exception policy is explicit.
6. DTO fields, ordering, `as_of`, and scalar history requirement are explicit.
7. `window[-1].session == as_of` is required for a close-inclusive DTO.
8. Classifier-reference admission and assembly sources are separately closed; every admitted source has temporal-validity semantics.
9. PIT A is testable at the composed boundary.
10. PIT B is testable for every admitted classifier field and non-empty assembly source; N/A applies only to absent classifier reference inputs.
11. Verified Variant C mechanics and its real assembly-path test obligation are retained.
12. Variant C-2 is recorded as DEFERRED with the immutable-revision-provenance remediation prerequisite; it is not counted as a passing PR-MS1.1 test.
13. Rule transform groups, deadbands, `NO_ADMITTED_INVARIANCE` exceptions, and Q-MS1-04 equality policy are closed.
14. Any volume/joint primitive has an adjustment-consistent transform or is excluded.
15. Taiwan-market exceptional bars and history diagnostics have explicit treatment.
16. Per-security/cross-sectional exclusion and all-valid batch semantics are explicit; assembly pre-validation/filtering is specified before universe-scale batch use.
17. Version/hash derivation and export provenance are explicit.
18. Q-MS1-07 cites current ADR-006 evidence.
19. Acceptance tests are assigned to classifier, assembly, or composed-pipeline boundaries without vacuous tests.
20. Repository baseline, evidence anchors, canonical path, internal references, and staged diff are re-verified immediately before lock.

## 12. PR-MS1.1 Acceptance-Test Contract

Classifier boundary:

- one positive fixture per MarketState;
- valid sufficient non-match → `INDETERMINATE`;
- insufficient history → `INSUFFICIENT_HISTORY` and no rule evaluation;
- malformed DTO → typed exception;
- declared precedence and exact threshold fixtures;
- deterministic same DTO plus fixed configuration;
- declared transform-group property tests and deadband-safe generation;
- scalar/batch equivalence for all-valid DTO batches.
- malformed DTO in a batch → typed exception and whole-call failure; no partial-success result.

Assembly boundary:

- close-inclusive canonical-window construction;
- governed history diagnostics and `DIAGNOSIS_UNAVAILABLE`;
- effective-date filtering for every admitted source;
- exceptional-bar representation;
- typed operational failure without invoking the classifier;
- DTO validation/filtering and excluded-item diagnostics before universe-scale batch invocation.

Composed-pipeline boundary:

- PIT Variant A;
- PIT Variant B where applicable;
- verified Variant C future-action restatement invariance;
- availability/classification/operational-diagnostic envelope invariants;
- export provenance identifying exact classifier configuration and input panel.

Variant C-2 is DEFERRED and is excluded from this PR-MS1.1 acceptance contract until its remediation prerequisite is closed.

## 13. Deferred Items

- final V1 MarketState vocabulary and rule thresholds;
- state transition persistence, hysteresis, debounce, and state-store design;
- broad-regime or cross-sectional models;
- production persistence, scheduler integration, strategy adoption, and execution/risk logic;
- C-2 immutable factor-revision provenance remediation;
- `ClassifierStatus` split as a separate diff-first governance item.

## 14. Evidence Record

Repository source evidence observed during the PR-MS1.0 entry work:

- `features/dividend_adjustment.py: compute_adjusted`, `build_for_symbol`, and `write_adjusted_to_db`;
- `data/database.py: corporate_actions`, `daily_price_adj`, and `adjustment_state` schema;
- `scripts/ingest_dividends.py: ingest_historical` and forecast ingestion;
- `scripts/build_adjusted_prices.py: main` rebuild orchestration;
- `scripts/ingest_splits.py` split factor ingestion.

The observed evidence supports Variant C mechanics and raw-volume exclusion. It also establishes the C-2 revision-provenance gap. Before lock, re-observe file/symbol anchors at the actual candidate HEAD and record them in the lock record.

## 15. Integration and Lock Procedure

1. Review this draft against PR-MS0 and addendum v0.3.1; do not alter those upstream artifacts.
2. Resolve Q-MS1-01 through Q-MS1-08 as applicable and record explicit defer decisions.
3. Re-verify repository evidence at the candidate HEAD.
4. Run a cross-reference, duplicate-clause, and closure-gate numbering audit.
5. Review the focused staged diff and confirm no code or production-surface change is included.
6. Apply the repository's established canonical lock/hash/backfill ceremony only after semantic closure.

## 16. Session Handoff

### Session Summary

PR-MS1.0 canonical contract did not previously exist in the repository. This draft establishes its candidate baseline from locked PR-MS0 constraints, reviewed addendum decisions, and verified adjustment-source evidence.

### Decision Record

- V1 is a pure, per-security snapshot classifier.
- Adjustment mechanics confirm backward multiplicative OHLC adjustment and raw volume.
- Variant C is enabled as a future-action composed-pipeline obligation for price-scale rules.
- Variant C-2 is deferred pending immutable factor-set revision provenance.

### Open Questions

Q-MS1-01, Q-MS1-02, Q-MS1-03, Q-MS1-04, Q-MS1-06, Q-MS1-07, and Q-MS1-08 remain to be closed. Q-MS1-05 is closed by snapshot semantics.

### Evidence

The evidence record in Section 14 is source-level repository evidence, not a production validation or historical replay guarantee.

### Next Actions

Review this canonical draft, then place it in the repository under its Canonical Path as a separate documentation commit. Do not lock until all applicable closure-gate items are resolved.
