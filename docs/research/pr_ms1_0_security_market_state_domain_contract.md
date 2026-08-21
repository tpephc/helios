# PR-MS1.0 — Security Market State Domain Contract
Canonical Path: docs/research/pr_ms1_0_security_market_state_domain_contract.md

Version: v0.2.5
Status: LOCKED — PR-MS1.1 AUTHORISED
Scope: Domain contract only; no classifier implementation, persistence, strategy adoption, `daily_run` integration, or production execution change.
Upstream Semantic Boundary: `docs/research/pr_ms0_repository_semantic_audit_decision_record.md` (`45f8fea39f15778dc097f699ad8333256dcd7a3f`)
Integration Source: `docs/research/pr_ms1_0_security_market_state_domain_contract_governance_addendum.md` v0.3.1 (`56db5b1`)
Disposition Inputs: Q-MS1-01/02 v0.1.2; Q-MS1-03/06 v0.1.1; Q-MS1-04 v0.1.4; Q-MS1-02/06 exceptional-bar v0.1.1; Q-MS1-07 v0.1.1; Q-MS1-08 v0.1.1.

## 0. Authority, Evidence, and Status

This document is the canonical PR-MS1.0 candidate. PR-MS0 is the locked semantic boundary. The governance addendum is an integration source and remains an immutable review/audit artifact; it is not appended verbatim.

Evidence labels:

- **VERIFIED REPOSITORY FINDING** — supported by source evidence observed at the stated repository baseline.
- **FORMAL DERIVATION** — follows from stated verified mechanics and a stated mathematical contract.
- **LOCKED DECISION** — normative text pending PR-MS1.0 closure and lock.
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

**LOCKED DECISION:** V1 is a pure snapshot classifier.

For a valid canonical input and fixed classifier configuration, output depends only on the values in that input. It SHALL NOT accept or retrieve `prior_state`, transition history, persistent classifier state, hidden process state, account state, portfolio state, or strategy state.

```text
classify(input_dto) -> ClassificationResult
```

Transition, hysteresis, debounce, persistence, and origin/cold-start semantics are DEFERRED to a separately governed downstream layer. Q-MS1-05 is thereby closed for V1.

## 4. Domain Types, Numeric Policy, and Ownership

The following is a normative contract sketch; it remains implementation-neutral.

```text
MarketState: CONFIRMED_RECLAIM | FAILED_RECLAIM
ClassificationStatus: OK | INDETERMINATE | INSUFFICIENT_HISTORY
Availability: AVAILABLE | OPERATIONAL_FAILURE
ClassifierReasonCode: NO_RULE_MATCH | REQUIRED_HISTORY_NOT_MET
HistoryDiagnosticCode: NATURAL_HISTORY_SHORTFALL | DATA_GAP | DIAGNOSIS_UNAVAILABLE | ZERO_VOLUME_BAR_EXCLUDED
OperationalDiagnosticCode: AS_OF_BAR_MISSING | AS_OF_BAR_INVALID | AS_OF_BAR_ZERO_VOLUME | REFERENCE_BASIS_UNAVAILABLE | UNCLASSIFIED_ASSEMBLY_FAILURE
LimitStatusCoverage: OFFICIAL_STATUS_UNAVAILABLE
```

Every listed domain is a distinct non-string `Enum`; export serialization occurs explicitly through `.value`. The three reason/diagnostic domains have disjoint serialized value spaces. `ClassificationStatus` is wholly classifier-owned. `Availability`, `HistoryDiagnosticCode`, and `OperationalDiagnosticCode` are assembly/composed-pipeline-owned. `OPERATIONAL_FAILURE` SHALL NOT occur in `ClassificationStatus`, `ClassifierReasonCode`, or `ClassificationResult`.

**LOCKED DECISION:** Canonical in-memory adjusted OHLC values, classifier-computed SMA/ATR/Donchian primitives, and V1 comparison operands use IEEE-754 binary64 (`float64`). Required price values are finite and strictly positive. NaN, infinity, and non-positive required price values are malformed DTO conditions.

Classifier comparisons use exact binary64 relational operators; no tolerance changes a production result. Only property-test generation applies the following declared exclusion:

```text
epsilon_relative = 1e-10
eligible(x, y) <=> abs(x - y) / max(abs(x), abs(y)) > epsilon_relative
```

`1e-10` is an engineering guard band, not a market, alpha, or calibration parameter. It is approximately `4.5 × 10^5` binary64 machine epsilons and prevents unit-scale rounding noise from becoming an invariance fixture; it does not alter exact-boundary rule semantics.

`ClassificationResult` is classifier-owned:

```text
status: ClassificationStatus
state: MarketState | None
matched_rule_id: RuleId | None
reason_code: ClassifierReasonCode | None
classifier_version: ClassifierVersion
rule_set_hash: RuleSetHash
as_of: TradingSession
```

For a structurally valid DTO plus fixed classifier configuration, every result field is determinable solely from those inputs. It contains no security identifier, assembly diagnostic, panel identity, adjustment provenance, or wall-clock timestamp.

| Status | `state` | `matched_rule_id` | `reason_code` |
| --- | --- | --- | --- |
| `OK` | exactly one `MarketState` member | non-null | null |
| `INDETERMINATE` | null | null | `NO_RULE_MATCH` |
| `INSUFFICIENT_HISTORY` | null | null | `REQUIRED_HISTORY_NOT_MET` |

`OK` requires all admitted rules to have been evaluated and any positive multi-match to have been resolved by declared precedence. `INDETERMINATE` requires all admitted rules to have been evaluated with no positive match. `INSUFFICIENT_HISTORY` occurs before rule evaluation.

A malformed DTO raises `MarketStateContractViolation`. It SHALL NOT produce a result, a status value, `Availability.OPERATIONAL_FAILURE`, or a per-item error envelope.

`MarketStateExportRecord` is assembly/composed-pipeline-owned:

```text
availability: Availability
classification: ClassificationResult | None
security_id: SecurityId
panel_snapshot_id: PanelSnapshotId | None
adjustment_provenance: AdjustmentProvenance | None
assembly_schema_version: AssemblySchemaVersion
history_diagnostics: HistoryDiagnosticCode | None
operational_diagnostics: OperationalDiagnosticCode | None
decision_available_at: Timestamp | None
limit_status_coverage: LimitStatusCoverage
```

It SHALL NOT duplicate classifier fields at top level. Its invariants are:

```text
classification is not None <=> availability == AVAILABLE
availability == OPERATIONAL_FAILURE => operational_diagnostics is not None
availability == AVAILABLE           => operational_diagnostics is None
availability == OPERATIONAL_FAILURE => history_diagnostics is None
classification.status == INSUFFICIENT_HISTORY => history_diagnostics is not None
classification.status != INSUFFICIENT_HISTORY => history_diagnostics is None
availability == AVAILABLE => panel_snapshot_id, adjustment_provenance, decision_available_at are non-null
availability == OPERATIONAL_FAILURE => panel_snapshot_id SHALL NOT identify a partial, rejected, or invalid candidate panel
limit_status_coverage is non-null
```

For `Availability.OPERATIONAL_FAILURE`, `panel_snapshot_id`, `adjustment_provenance`, and `decision_available_at` MAY be null only when the preceding failure makes that fact unknowable. A non-null value under failure SHALL describe work fully and independently established before the failure point; it SHALL NOT imply that a rejected candidate panel was classified or replayable.

**LOCKED DECISION — supersession:** This section supersedes v0.1.1 §3.2's allowance for `OK` to carry an optional provenance-only history diagnostic. `HistoryDiagnosticCode` exclusively explains insufficient eligible history; panel and adjustment provenance use their dedicated fields. When assembly cannot distinguish natural shortfall from a data gap, it SHALL emit `DIAGNOSIS_UNAVAILABLE`, never null.

**LOCKED DECISION — controlled supersession of Q-MS1-03/06 v0.1.1:** `ZERO_VOLUME_BAR_EXCLUDED` is an assembly-owned `HistoryDiagnosticCode`, required when an observed zero-volume bar is intentionally excluded and thereby leaves the terminal DTO insufficient. It is neither a MarketState nor a classifier-owned reason/status.

**LOCKED DECISION — supersession on canonical integration:** `OperationalDiagnosticCode` is assembly/composed-pipeline-owned. Exactly one code is required for every `Availability.OPERATIONAL_FAILURE`: use `AS_OF_BAR_MISSING`, `AS_OF_BAR_INVALID`, or `AS_OF_BAR_ZERO_VOLUME` for the corresponding `as_of` condition; `REFERENCE_BASIS_UNAVAILABLE` only when no calendar/lifecycle basis exists to construct any terminal eligible-session DTO; otherwise `UNCLASSIFIED_ASSEMBLY_FAILURE`. The last code explicitly communicates non-specific attribution and SHALL NOT be represented as a root cause. This supersedes the single-member `ASSEMBLY_FAILURE` vocabulary.

`REFERENCE_BASIS_UNAVAILABLE` and `DIAGNOSIS_UNAVAILABLE` occupy disjoint pipeline stages. The former prevents DTO construction and classifier invocation. The latter applies only after a valid DTO is classified as `INSUFFICIENT_HISTORY`, when the finer-grained basis needed to distinguish natural shortfall from data gap is unavailable.

`AVAILABLE` means assembly produced a `ClassificationResult`; it does not mean a MarketState is present. A consumer requiring a state must additionally require `classification.status == OK`.

## 5. Temporal Input Contract

### 5.1 `as_of` and availability

**LOCKED DECISION — Q-MS1-06a:** `as_of=t` is close-inclusive: the complete official bar for trading session `t` is in the canonical window.

```text
window(t, N) = N canonical eligible trading-session observations,
               ordered oldest to newest, ending at and including t
decision_available_at > close_timestamp(t)
```

Strategy consumption timing is DEFERRED. A later contract cannot silently reinterpret this as open-exclusive semantics.

### 5.2 History sufficiency

The canonical classifier DTO is:

```text
SecurityMarketStateInput
  security_id: SecurityId
  as_of: TradingSession
  bars: ordered non-empty sequence[AdjustedOhlcBar]

AdjustedOhlcBar
  session: TradingSession
  adj_open, adj_high, adj_low, adj_close: finite positive float64
```

Bars are strictly session-ascending; `bars[-1].session == as_of`; and every bar satisfies:

```text
adj_low <= min(adj_open, adj_close) <= max(adj_open, adj_close) <= adj_high
```

The classifier configuration is immutable and includes `classifier_version`, `rule_set_hash`, admitted ordered rules, and the Section 4 numeric policy. The DTO contains no configuration, precomputed feature, volume, panel snapshot, adjustment provenance, or assembly diagnostic.

For a rule using `SMA_L` over a K-session template:

```text
required_history_sessions(R) = L + K - 1
required_history_sessions = max(required_history_sessions(R) for R in admitted_rules)
rule_bars(R) = bars[-required_history_sessions(R):]
```

Each rule computes indicators only from its trailing `rule_bars(R)`; a longer classifier-level panel SHALL NOT alter a shorter rule window. The classifier, not assembly, compares input length with the scalar. A non-empty structural-valid DTO shorter than the scalar returns `INSUFFICIENT_HISTORY`; no rule is evaluated. It is not malformed, and assembly SHALL NOT pre-filter/reject it by classifier rule-window knowledge.

Assembly constructs the maximal terminal sequence of consecutive eligible sessions ending at `as_of`; it SHALL NOT silently skip an expected session, forward-fill OHLC, or reach across a barrier to borrow older bars. Assembly MAY use the scalar solely as a bounded fetch-depth hint. It SHALL NOT use that scalar to decide whether to construct/send the DTO, preempt classifier invocation, or choose a classifier status.

The formula counts canonical eligible trading sessions, not calendar days. It becomes an operational history requirement only after Section 7 closes the eligible-session treatment.

### 5.3 Reference-data boundary

**LOCKED DECISION — Q-MS1-08:**

```text
CLASSIFIER_REFERENCE_INPUTS_ADMITTED = NO
ASSEMBLY_REFERENCE_SOURCES = {calendar, security_lifecycle}
```

The classifier consumes only the DTO described above. Assembly uses its governed reference sources solely for terminal-sequence construction and history diagnostics/provenance with effective-date semantics. This preserves classifier purity while allowing `NATURAL_HISTORY_SHORTFALL`, `DATA_GAP`, and `DIAGNOSIS_UNAVAILABLE` to be produced at the composed boundary. Any additional source, including an official limit-status feed, requires a superseding Q-MS1-02/Q-MS1-08 disposition.

Every assembly reference source requires governed effective-date semantics; undated latest-state lookup is forbidden.

## 6. Rule, Input, and Transform Constraints

V1 is per-security. Cross-sectional ranks, universe percentiles, current-constituent membership, candidate membership, peer aggregates, and any value dependent on another security are forbidden.

### 6.1 Admitted V1 rule templates

The finite V1 `MarketState` vocabulary contains exactly `CONFIRMED_RECLAIM` and `FAILED_RECLAIM`; no residual state is permitted. For `L ∈ {20, 50}` and `K=3`:

```text
CONFIRMED_RECLAIM(L, 3):
  adj_close[i] > SMA_L[i] for every i in [t-2, t]

FAILED_RECLAIM(L):
  adj_close[t-2] <  SMA_L[t-2]
  adj_close[t-1] >= SMA_L[t-1]
  adj_close[t]   <  SMA_L[t]
```

`CONFIRMED_RECLAIM` is observable only at close of `t`; it SHALL NOT be backfilled to an earlier crossing. Any `adj_close[i] <= SMA_L[i]` makes its stated window-AND false; no streaming counter or partial credit exists. `FAILED_RECLAIM` is an exactly three-session event and SHALL NOT be assigned to `t-1` or use an unbounded prior-history predicate.

No MA lookback other than 20 or 50 is admitted in V1. The domain follows verified existing SMA20/SMA50 reclaim/persistence primitives; any new lookback requires a superseding disposition with rule ID, precedence, history, and acceptance coverage.

The four rule IDs are ordered for deterministic selection:

```text
failed_reclaim_ma50
failed_reclaim_ma20
confirmed_reclaim_ma50_k3
confirmed_reclaim_ma20_k3
```

Every admitted rule is evaluated after the scalar sufficiency check. The highest-priority positive rule is the sole `matched_rule_id`. Same-lookback confirmed/failed matches are mutually exclusive because their `t` conditions require both `adj_close[t] > SMA_L[t]` and `adj_close[t] < SMA_L[t]`; cross-lookback overlaps are resolved by the declared total order. `INDETERMINATE` denotes zero positive matches and SHALL NOT absorb a multi-match.

The reclaim rules are `PRICE_SCALE`: finite positive rescaling of all adjusted OHLC values rescales SMA identically and preserves their inequalities. ATR, Donchian, volume, and joint price-volume primitives are not admitted V1 rules. Any future Donchian rule must use an explicitly prior boundary; same-bar `adj_close[t] > donchian_high[t]` is self-referential because `donchian_high[t] >= adj_high[t] >= adj_close[t]`.

Every admitted rule declares its input domain, transform/invariance group, equality policy, and threshold deadband policy. This metadata contributes to `rule_set_hash`.

If a batch API is exposed, it is:

```text
classify(dto) -> ClassificationResult
batch_classify(dtos) -> list[ClassificationResult]
```

The empty batch returns an empty list. A non-empty batch SHALL structurally validate every DTO before sufficiency or rule evaluation. Any malformed DTO raises `MarketStateContractViolation` for the whole call; partial-success and per-item-exception return types are forbidden. For an all-valid batch, order is preserved and:

```text
batch_classify([dto_1, ..., dto_n]) == [classify(dto_1), ..., classify(dto_n)]
```

Batch neighbours cannot affect an item's result. Assembly may validate/filter malformed source material before a universe-scale call, but this containment does not alter classifier fail-fast semantics or transfer history-sufficiency authority to assembly.

Supported groups are `PRICE_SCALE`, `VOLUME_SHARE_UNIT`, `PRICE_VOLUME_JOINT`, and an explicitly governed `NO_ADMITTED_INVARIANCE` exception. The exception is not self-authorising: it requires a closure-gate disposition, rationale, and test-boundary treatment.

For each `PRICE_SCALE` rule and finite `c > 0` in the governed domain:

```text
R(c * P, non_price_inputs) == R(P, non_price_inputs)
```

Absolute-price thresholds are forbidden. Generated property-test samples must be constructively excluded from each declared threshold deadband under Section 4's relative-deadband policy. Exact equality fixtures remain mandatory.

For a share-unit rescaling factor `k > 0`:

```text
price' = price / k
volume' = volume * k
```

Every admitted volume or joint rule must declare and pass its appropriate transform. A price-only transform cannot be applied to a joint rule.

### 6.2 Q-MS1-07 Physical Form

**LOCKED DECISION:** If PR-MS1.1 implementation is authorised after contract lock, the V1 physical form SHALL be one concrete module:

```text
features/market_state.py
```

It contains the pure classifier implementation surface—immutable configuration, DTO/result types, `MarketStateContractViolation`, deterministic indicator calculation, structural validation, scalar/batch classification, and rule evaluation/precedence—and defines the cohesive Market State domain vocabulary: `MarketState`, `ClassificationStatus`, `ClassifierReasonCode`, `Availability`, `HistoryDiagnosticCode`, `OperationalDiagnosticCode`, and `LimitStatusCoverage`.

Definition location does not alter producing/assignment ownership. The classifier produces `MarketState`, `ClassificationStatus`, and `ClassifierReasonCode`; assembly/composed pipeline assigns `Availability` and diagnostic values. Assembly may import the vocabulary module, but the pure classifier SHALL NOT import assembly/export code or perform I/O. `MarketStateContractViolation` is defined and raised at the classifier boundary.

V1 SHALL NOT create a `features/market_state/` package, rule plugin system, speculative submodule, or separate shared-types module. A future package split requires repository evidence of at least two internally cohesive responsibilities with distinct public/test boundaries, a demonstrated single-module cohesion failure, and a superseding ADR/disposition. File length, hypothetical future rules, or generic extensibility are insufficient triggers.

## 7. Taiwan-Market Exceptional-Bar Validity

An expected session is a governed Taiwan trading session inside the security's governed listed interval. This section applies to every admitted price-comparison, range, breakout, extrema, or volume rule, including SMA reclaim rules.

| Condition at an expected session | Canonical-panel treatment | Consequence |
| --- | --- | --- |
| Before governed `listed_from` | not expected; never padded | `NATURAL_HISTORY_SHORTFALL` when terminal DTO is insufficient |
| Missing bar, invalid OHLC, or invalid OHLC ordering | terminal-sequence barrier; never repair or skip | `DATA_GAP` if a terminal DTO exists but is insufficient; operational failure if this is `as_of` |
| Zero-volume bar with valid OHLC | ineligible terminal-sequence barrier | `ZERO_VOLUME_BAR_EXCLUDED` if terminal DTO is insufficient; operational failure if this is `as_of` |
| Zero-range bar with positive volume and valid OHLC | included | no limit-lock inference or special classifier branch |
| Suspension/halt while listed | missing-bar treatment | no unsupported suspension-versus-source-gap inference |
| Resumption | valid bars begin a new terminal sequence | earlier barriers are never bridged |

No verified source identifies official price-limit-locked sessions. Zero range SHALL NOT serve as a proxy. Every `MarketStateExportRecord` SHALL carry `LimitStatusCoverage.OFFICIAL_STATUS_UNAVAILABLE`. It is a coverage/capability declaration, not a claim about an individual session's limit status, classifier input, MarketState, history diagnostic, operational diagnostic, or OHLC-derived inference. On an `OPERATIONAL_FAILURE` record, it asserts only that no panel-level official-limit-status resolution path exists; it does not assert that a panel was assembled. A future official effective-dated source requires a superseding disposition with PIT semantics, mapping, and acceptance fixtures.

If no eligible bar exists at `as_of`, assembly cannot produce a DTO ending at `as_of`; it SHALL emit `Availability.OPERATIONAL_FAILURE`, the corresponding typed operational diagnostic, no `ClassificationResult`, and shall not invoke the classifier. If calendar/lifecycle basis needed to construct any terminal eligible-session sequence is unavailable, assembly SHALL emit `REFERENCE_BASIS_UNAVAILABLE`, no DTO, and no classifier invocation. `DIAGNOSIS_UNAVAILABLE` instead applies only after classifier `INSUFFICIENT_HISTORY`, when the finer-grained shortfall-versus-gap basis cannot be established.

## 8. PIT Contract

### 8.1 Variant A — future market observation

Appending or mutating observations strictly after `t` shall not change the same security's `as_of=t` classification. Equality includes status, state, `matched_rule_id`, and classifier-derived `as_of` diagnostics; run timestamps are excluded.

### 8.2 Variant B — reference data

For each admitted classifier reference input or assembly reference source, a mutation effective strictly after `t` shall not change the `as_of=t` canonical input, history diagnostic, or classification. An effective-at-or-before-`t` positive-direction fixture is required where that field is classification-relevant.

If no classifier reference input is admitted, classifier-level Variant B is N/A by contract and shall not have a vacuous passing test. If assembly sources are non-empty, assembly/composed-boundary Variant B remains required.

### 8.3 Variant C — future corporate-action restatement

**VERIFIED REPOSITORY FINDING:** `features.dividend_adjustment.compute_adjusted` applies multiplicative backward adjustment. It forms `cum_factor[T]` from event factors whose dates are strictly later than `T`, computes adjusted OHLC as raw OHLC times that factor, and excludes the event on the ex-date bar itself. `corporate_actions.date` is the ex-dividend/ex-rights trading date. Confirmed actions provide adjustment factors; forecast actions do not. `daily_price_adj.volume` is raw volume.

**FORMAL DERIVATION:** For a newly known action with `ex_date > t`, a fixed `as_of=t` adjusted-price window is uniformly rescaled by one positive factor. A `PRICE_SCALE` rule satisfying MS-P3 therefore preserves classification and `matched_rule_id`.

**LOCKED DECISION:** Variant C is a composed-pipeline acceptance obligation. A real assembly-path fixture introducing an action with `ex_date > t` shall leave status, state, and `matched_rule_id` unchanged.

Adjusted-price/raw-volume mixed primitives, including price-times-volume, dollar volume, turnover proxies, and VWAP-like proxies, are excluded unless an adjustment-consistent joint transform is established and passes the required PIT obligations.

### 8.4 Variant C-2 — late corporate action

**REPOSITORY GAP:** Current `corporate_actions` uses primary key `(date, stock_id, kind)` and historical ingestion uses `DELETE + INSERT`. This physically destroys prior factor values. `ingested_at`, `last_event_date_used`, and `n_events_applied` are not immutable adjustment-factor-set revision provenance.

Until immutable adjustment-factor-set revision provenance exists, late-arriving or corrected actions with `ex_date <= as_of` are excluded from PR-MS1.1 composed-pipeline acceptance. Existing `ingested_at`, `last_event_date_used`, and `n_events_applied` SHALL NOT be represented as sufficient C-2 provenance. Such an action invalidates replay/audit claims for affected prior adjusted-panel classifications and requires separately governed remediation before C-2 acceptance is enabled.

This C-2 gap applies to the complete derived chain: affected adjusted OHLC panel → classifier-computed SMA/ATR/prior Donchian → rule evaluation and `ClassificationResult` → export/replay/audit claim.

Variant C-2 is therefore DEFERRED, not a passing PR-MS1.1 acceptance test. A remediation must preserve factor-set revisions through an append-only history/audit model or an equivalent immutable snapshot identity.

## 9. Versioning, Provenance, and Exports

Every classification/export carries `classifier_version` and `rule_set_hash`. The hash covers rule definitions and IDs, precedence, parameter values, vocabulary identity, transform group, equality policy, binary64 numeric policy, relative-deadband formula/value, source fields/adjustment basis, each admitted indicator's algorithm/lookback/window semantics, and missing/non-finite policy.

Declarative canonical rule data is the default hash source. A rule proven to require imperative expression may use a governed AST-normalized representation only if Q-MS1-01/Q-MS1-08 records the escape hatch, canonical digest procedure, and a formatting/comment-insensitivity fixture.

**INTEGRATOR ADDITION — pending separate ledger disposition:** vocabulary changes require a major classifier-version bump; predicate or threshold changes require at least a minor bump.

`PanelSnapshotId` SHALL be a stable content identity of the exact terminal adjusted-OHLC sequence submitted to the classifier. Its canonical input contains security/as-of/session identities, adjusted OHLC binary64 bit patterns, eligible-session/reference basis identities, adjustment-provenance identity, and assembly schema version. Its digest algorithm, field ordering, byte encoding, and digest version are declared; any semantic canonical-input change produces a different ID. Wall-clock time alone is insufficient.

`AdjustmentProvenance` SHALL identify adjustment method/version, the applied corporate-action factor-set content identity, and the relevant source/basis identity. It identifies applied values, not merely ingestion time. Under the current overwrite architecture it SHALL NOT be represented as immutable adjustment-factor revision provenance; C-2 remains deferred.

The export record retains panel identity, adjustment provenance, assembly schema version, history diagnostics, availability, classifier result, decision-availability time, and limit-status coverage. Assembly/reference provenance preserves the governed calendar coverage/version and effective-date lifecycle basis used for terminal-sequence construction; it may be a documented component of the snapshot/provenance identity rather than duplicated top-level columns.

## 10. Decision Matrix

| ID | Required closure output | Current state |
| --- | --- | --- |
| Q-MS1-00 | Snapshot/stateful model | CLOSED: pure snapshot |
| Q-MS1-01 | Finite vocabulary and positive rules | CLOSED: integrated v0.1.2 |
| Q-MS1-02 | Canonical inputs, reference admission, volume admission, bar treatment | CLOSED: integrated v0.1.2, exceptional-bar v0.1.1, and Q-MS1-08 reference declarations |
| Q-MS1-03 | Final result/diagnostic representation | CLOSED: integrated v0.1.1 |
| Q-MS1-04 | Rule precedence, equality/deadband algorithm | CLOSED: integrated v0.1.4 |
| Q-MS1-05 | Transition semantics | CLOSED by Q-MS1-00 |
| Q-MS1-06 | DTO/API and batch surface | CLOSED: integrated v0.1.1 |
| Q-MS1-06a | Close-inclusive `as_of` | CLOSED |
| Q-MS1-07 | Single module or package based on ADR-006 evidence | CLOSED: `features/market_state.py` |
| Q-MS1-08 | Export/provenance schema | CLOSED: integrated v0.1.1 |

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
17. Version/hash derivation, canonical panel identity, adjustment provenance, reference provenance, and limit-status coverage are explicit.
18. Q-MS1-07 cites current ADR-006 evidence and establishes the one-module form, vocabulary ownership separation, and evidence-based future split trigger.
19. Acceptance tests are assigned to classifier, assembly, or composed-pipeline boundaries without vacuous tests.
20. Repository baseline, evidence anchors, canonical path, internal references, and staged diff are re-verified immediately before lock.
21. Numeric representation, `epsilon_relative`, rule IDs/parameters, total precedence, and exact-boundary fixtures are explicit and covered by `rule_set_hash`.
22. `history_diagnostics` is non-null only for `INSUFFICIENT_HISTORY`; `DIAGNOSIS_UNAVAILABLE` replaces silent ambiguity.
23. Exceptional bars use the terminal-sequence policy; zero-volume exclusion, no-bridge behavior, limit-status coverage, and the distinct history/operational diagnostic stages are tested.

## 12. PR-MS1.1 Acceptance-Test Contract

Classifier boundary:

- one positive fixture per MarketState;
- valid sufficient non-match → `INDETERMINATE`;
- insufficient history → `INSUFFICIENT_HISTORY` and no rule evaluation;
- malformed DTO → typed exception;
- declared precedence and exact threshold fixtures;
- exact equality, immediately-below, and immediately-above fixtures for every rule comparison;
- deterministic same DTO plus fixed configuration;
- declared transform-group property tests and deadband-safe generation;
- scalar/batch equivalence for all-valid DTO batches.
- malformed DTO in a batch → typed exception and whole-call failure; no partial-success result.
- all-rule evaluation before precedence selection, including a lower-priority positive match fixture.

Assembly boundary:

- close-inclusive canonical-window construction;
- governed history diagnostics and `DIAGNOSIS_UNAVAILABLE`;
- effective-date filtering for every admitted source;
- exceptional-bar representation;
- typed operational failure without invoking the classifier;
- DTO validation/filtering and excluded-item diagnostics before universe-scale batch invocation.
- terminal-sequence barriers for missing/invalid/zero-volume bars; positive-volume zero-range inclusion; no bridge on resumption.
- a missing or invalid bar at `as_of` → operational failure, typed operational diagnostic, no `ClassificationResult`, and no classifier invocation.
- a zero-volume bar exactly at `as_of` → operational failure, typed operational diagnostic, no `ClassificationResult`, and no classifier invocation; this SHALL be a fixture distinct from the missing/invalid-bar-at-`as_of` fixture.
- a terminal-sequence construction basis failure → `REFERENCE_BASIS_UNAVAILABLE`, no DTO, no classifier invocation, and no guessed history diagnostic.
- a successful DTO plus classifier `INSUFFICIENT_HISTORY` where shortfall-versus-gap basis is unavailable → `DIAGNOSIS_UNAVAILABLE`, not `REFERENCE_BASIS_UNAVAILABLE`.
- an operational-failure record cannot use a partial, rejected, or invalid panel as `panel_snapshot_id`.

Composed-pipeline boundary:

- PIT Variant A;
- PIT Variant B where applicable;
- verified Variant C future-action restatement invariance;
- availability/classification/operational-diagnostic envelope invariants;
- reproducible canonical panel identity and adjustment/reference provenance identifying exact classifier configuration and input panel;
- non-null `OFFICIAL_STATUS_UNAVAILABLE` coverage marker on every record, including operational failures, with zero range never inferring an official limit lock.

Variant C-2 is DEFERRED and is excluded from this PR-MS1.1 acceptance contract until its remediation prerequisite is closed.

## 13. Deferred Items

- state transition persistence, hysteresis, debounce, and state-store design;
- broad-regime or cross-sectional models;
- production persistence, scheduler integration, strategy adoption, and execution/risk logic;
- C-2 immutable factor-revision provenance remediation;
- official price-limit-status source/admission beyond `OFFICIAL_STATUS_UNAVAILABLE`;
- `ClassifierStatus` split as a separate diff-first governance item.

## 14. Evidence Record

Repository source evidence observed during the PR-MS1.0 entry work:

- `features/dividend_adjustment.py: compute_adjusted`, `build_for_symbol`, and `write_adjusted_to_db`;
- `data/database.py: corporate_actions`, `daily_price_adj`, and `adjustment_state` schema;
- `scripts/ingest_dividends.py: ingest_historical` and forecast ingestion;
- `scripts/build_adjusted_prices.py: main` rebuild orchestration;
- `scripts/ingest_splits.py` split factor ingestion.

The observed evidence supports Variant C mechanics and raw-volume exclusion. It also establishes the C-2 revision-provenance gap. Candidate-HEAD re-observation is a source-level repository audit; it does not establish production validation or C-2 replayability.

## 15. Integration, Lock, and Session Handoff

1. Review the candidate contract against PR-MS0 and addendum v0.3.1; do not alter those upstream artifacts.
2. Resolve Q-MS1-01 through Q-MS1-08 as applicable and record explicit defer decisions.
3. Re-verify repository evidence at the candidate HEAD.
4. Run a cross-reference, duplicate-clause, and closure-gate numbering audit.
5. Review the focused staged diff and confirm no code or production-surface change is included.
6. Apply the repository's established canonical lock/hash/backfill ceremony only after semantic closure.


### Session Summary

PR-MS1.0 is LOCKED as the canonical contract for PR-MS1.1, bounded by PR-MS0, the six reviewed dispositions, and candidate-HEAD repository evidence.

### Decision Record

- V1 is a pure, per-security snapshot classifier.
- Adjustment mechanics confirm backward multiplicative OHLC adjustment and raw volume.
- Variant C is enabled as a future-action composed-pipeline obligation for price-scale rules.
- Variant C-2 is deferred pending immutable factor-set revision provenance.

### Open Questions

No unresolved PR-MS1.0 contract decision remains. Variant C-2 immutable adjustment-factor revision provenance remains explicitly DEFERRED.

### Evidence

The evidence record in Section 14 is source-level repository evidence, not a production validation or historical replay guarantee.

### Next Actions

PR-MS1.1 may implement only this locked contract. Variant C-2 remediation, official limit-status-source admission, and `ClassifierStatus` redesign require separate diff-first governance.
