# PR-MS1.0 — Q-MS1-03 / Q-MS1-06 Result, API, and Numeric Disposition Draft
Canonical Path: docs/research/pr_ms1_0_q_ms1_03_06_result_api_numeric_disposition.md

Version: v0.1.1
Status: DRAFT — ADVERSARIAL REVIEW REQUIRED
Scope: Q-MS1-03 result/diagnostic representation and Q-MS1-06 DTO/API surface, including canonical numeric representation required by Q-MS1-04. No classifier implementation, persistence, strategy adoption, data-access, or production integration is authorised.
Prerequisite Baseline: Q-MS1-01/02 v0.1.2 and Q-MS1-04 v0.1.2 are closure-ready drafts, pending canonical integration.
Canonical Contract: `docs/research/pr_ms1_0_security_market_state_domain_contract.md` v0.1.1 (`dca8f0b`)
Upstream Semantic Boundary: `docs/research/pr_ms0_repository_semantic_audit_decision_record.md` (`45f8fea`)

## 0. Decision Labels

- **VERIFIED REPOSITORY FINDING** — source evidence observed at the stated baseline.
- **PROPOSED DECISION** — normative candidate requiring review and lock.
- **DEFERRED** — intentionally outside this disposition.

## 1. Boundary and Entry Evidence

**VERIFIED REPOSITORY FINDING:** The current `daily_price_adj` schema stores adjusted OHLC as `DOUBLE`; the observed technical-feature path uses Polars floating-point rolling calculations. `features/dividend_adjustment.py` also constructs adjustment factors and adjusted prices through floating-point values.

**PROPOSED DECISION:** The pure classifier owns only deterministic validation and calculation from `SecurityMarketStateInput`. It owns no DuckDB, filesystem, network, broker, Shioaji, clock, random generator, process-global mutable state, or assembly provenance lookup. Assembly owns all I/O, PIT materialisation, reference-source use, operational-failure capture, and export composition.

No classifier type or API accepts account, position, exposure, risk budget, order, fill, venue, strategy eligibility, precomputed feature, panel snapshot ID, adjustment provenance, or assembly diagnostic as a semantic classifier input.

## 2. Canonical Numeric Representation

### 2.1 Numeric type

**PROPOSED DECISION:** The canonical in-memory numeric representation for adjusted OHLC inputs, classifier-computed SMA/ATR/Donchian primitives, and all V1 comparison operands is IEEE-754 binary64 (`float64`).

This aligns the classifier boundary with the verified `DOUBLE`/Polars source path and avoids an implicit, differently rounded Decimal conversion boundary. A valid numeric input must be finite and strictly positive where the DTO requires a price. NaN, positive/negative infinity, and non-positive price fields are malformed DTO conditions and raise `MarketStateContractViolation`.

Binary64 is a representation decision, not a claim that stored market prices have binary-exact decimal semantics. The indicator algorithm, operation order, window inclusion, and equality policy remain classification semantics and are covered by `rule_set_hash`.

### 2.2 Exact comparison and property-test deadband

**PROPOSED DECISION:** Classifier comparisons use the exact binary64 relational operators stated by the admitted rule; no epsilon, `isclose`, rounding, or tolerance may change a production classification result.

For Q-MS1-04's property-test generator only, set:

```text
epsilon_relative = 1e-10
eligible(x, y) <=> abs(x - y) / max(abs(x), abs(y)) > epsilon_relative
```

All generated rule comparisons in a property fixture must be eligible. This declared exclusion is scale-relative and is part of the classifier configuration/hash. It constrains test sample generation; it does not change the exact-boundary fixtures or the classifier's operational comparison semantics.

`1e-10` is an engineering guard band, not a market, alpha, or calibration parameter. It is approximately `4.5 × 10^5` binary64 machine epsilons (`2^-52 ≈ 2.22e-16`): deliberately several orders of magnitude above unit-scale floating-point rounding noise from the finite declared indicator calculations, while remaining a narrow relative exclusion region. It may be revised only through a governed numeric-policy/rule-set change; no empirical-performance meaning is claimed for this value.

The numerical policy in the fixed classifier configuration SHALL include at least:

```text
numeric_representation = IEEE-754 binary64
epsilon_relative = 1e-10
non_finite_policy = reject as malformed DTO
comparison_policy = exact relational operators
indicator_operation_order = declared canonical algorithm
```

Changing any item creates a new `rule_set_hash` and requires the classifier-version treatment required by the canonical contract.

## 3. Formal Classifier Types

### 3.1 Disjoint enum domains

**PROPOSED DECISION:** The following are distinct non-string `Enum` types. They serialize only at the export boundary by explicit `.value`; no type inherits `str`.

```text
MarketState
  CONFIRMED_RECLAIM
  FAILED_RECLAIM

ClassificationStatus
  OK
  INDETERMINATE
  INSUFFICIENT_HISTORY

Availability
  AVAILABLE
  OPERATIONAL_FAILURE

ClassifierReasonCode
  NO_RULE_MATCH
  REQUIRED_HISTORY_NOT_MET

HistoryDiagnosticCode
  NATURAL_HISTORY_SHORTFALL
  DATA_GAP
  DIAGNOSIS_UNAVAILABLE

OperationalDiagnosticCode
  ASSEMBLY_FAILURE
```

`ClassificationStatus` is wholly classifier-owned. `Availability`, `HistoryDiagnosticCode`, and `OperationalDiagnosticCode` are composed-pipeline/assembly-owned. The three reason/diagnostic enum types SHALL have disjoint serialized value spaces. `OPERATIONAL_FAILURE` SHALL NOT appear in `ClassificationStatus`, `ClassifierReasonCode`, or `ClassificationResult`.

### 3.2 Input and configuration types

```text
AdjustedOhlcBar
  session: TradingSession
  adj_open: float64
  adj_high: float64
  adj_low: float64
  adj_close: float64

SecurityMarketStateInput
  security_id: SecurityId
  as_of: TradingSession
  bars: non-empty ordered sequence[AdjustedOhlcBar]

ClassifierConfiguration
  classifier_version: ClassifierVersion
  rule_set_hash: RuleSetHash
  admitted_rule_definitions: immutable ordered rule set
  numeric_policy: fixed policy from Section 2
```

`SecurityMarketStateInput` contains no configuration object: configuration is fixed when the classifier is constructed or bound, never inferred from I/O or mutable process state. The result echoes only `as_of`; `security_id` remains assembly/export-owned to preserve the classifier result's security-agnostic determinability from its DTO/configuration boundary.

### 3.3 `ClassificationResult`

```text
ClassificationResult
  status: ClassificationStatus
  state: MarketState | None
  matched_rule_id: RuleId | None
  reason_code: ClassifierReasonCode | None
  classifier_version: ClassifierVersion
  rule_set_hash: RuleSetHash
  as_of: TradingSession
```

**PROPOSED DECISION:** For a structurally valid DTO and fixed configuration, every `ClassificationResult` field is determinable solely from that DTO and configuration. It contains no operational status, assembly diagnostic, panel identity, adjustment provenance, wall-clock timestamp, or security identifier.

Required invariants:

| Status | `state` | `matched_rule_id` | `reason_code` |
| --- | --- | --- | --- |
| `OK` | exactly one `MarketState` member | non-null | null |
| `INDETERMINATE` | null | null | `NO_RULE_MATCH` |
| `INSUFFICIENT_HISTORY` | null | null | `REQUIRED_HISTORY_NOT_MET` |

The `OK` row arises only after all admitted rules were evaluated and one or more matched rules were resolved by Q-MS1-04's declared precedence. `INDETERMINATE` arises only after all rules were evaluated and no positive rule matched. `INSUFFICIENT_HISTORY` arises before any rule evaluation when the classifier-owned scalar history test fails.

### 3.4 Typed validation error

**PROPOSED DECISION:** A malformed DTO raises `MarketStateContractViolation`, a typed validation exception. It SHALL NOT produce a `ClassificationResult`, `INDETERMINATE`, `INSUFFICIENT_HISTORY`, `Availability.OPERATIONAL_FAILURE`, or a per-item error envelope.

Malformed conditions include an empty bar sequence; non-ascending sessions; a final session not equal to `as_of`; non-finite/non-positive OHLC values; and invalid OHLC ordering. A shorter-than-required but structurally valid bar sequence is explicitly not malformed: the classifier returns `INSUFFICIENT_HISTORY`.

## 4. Formal Composed-Pipeline Export Type

```text
MarketStateExportRecord
  availability: Availability
  classification: ClassificationResult | None
  security_id: SecurityId
  panel_snapshot_id: PanelSnapshotId
  adjustment_provenance: AdjustmentProvenance
  assembly_schema_version: AssemblySchemaVersion
  history_diagnostics: HistoryDiagnosticCode | None
  operational_diagnostics: OperationalDiagnosticCode | None
  decision_available_at: Timestamp
```

**PROPOSED DECISION:** `MarketStateExportRecord` is produced only by the composed pipeline. It SHALL NOT duplicate `status`, `state`, `matched_rule_id`, `reason_code`, `classifier_version`, `rule_set_hash`, or `as_of` as top-level fields.

**PROPOSED DECISION — explicit supersession on canonical integration:** This disposition supersedes the canonical-contract v0.1.1 §3.2 allowance for an `OK` classification to carry an optional provenance-only `history_diagnostics` value. `HistoryDiagnosticCode` is exclusively a typed explanation of insufficient eligible history; panel and adjustment provenance belong to their dedicated fields, not a history-diagnostic overload. Therefore `OK` and `INDETERMINATE` classifications SHALL carry null `history_diagnostics`.

Required envelope invariants:

```text
classification is not None <=> availability == AVAILABLE
availability == OPERATIONAL_FAILURE => operational_diagnostics is not None
availability == AVAILABLE           => operational_diagnostics is None
availability == OPERATIONAL_FAILURE => history_diagnostics is None
classification.status == INSUFFICIENT_HISTORY => history_diagnostics is not None
classification.status != INSUFFICIENT_HISTORY => history_diagnostics is None
```

For an insufficient-history classification, assembly SHALL emit exactly one typed history diagnostic. If it cannot distinguish natural listing shortfall from a data gap, it SHALL emit `DIAGNOSIS_UNAVAILABLE`, never a silent null. `availability == AVAILABLE` asserts that assembly successfully produced a `ClassificationResult`; it does not assert `classification.state is not None`. A consumer requiring an actionable MarketState must additionally require `classification.status == OK`.

`OPERATIONAL_FAILURE` is a composed-pipeline condition. The pure classifier never produces it. It is emitted when assembly cannot create/validate the canonical DTO or cannot complete the composed pipeline, subject to the existing assembly failure propagation requirement.

## 5. Q-MS1-06 API and Batch Semantics

### 5.1 Scalar API

**PROPOSED DECISION:** The classifier surface is conceptually:

```text
classify(dto: SecurityMarketStateInput) -> ClassificationResult
```

The classifier has fixed `ClassifierConfiguration`; it performs no I/O and does not read hidden state. Structural validation occurs before sufficiency and rule evaluation. The classifier itself compares `len(dto.bars)` with configuration-owned `required_history_sessions`; assembly SHALL NOT pre-filter a structurally valid DTO by classifier rule-window knowledge.

### 5.2 Batch API

**PROPOSED DECISION:** If exposed, batch classification is conceptually:

```text
batch_classify(dtos: Sequence[SecurityMarketStateInput]) -> list[ClassificationResult]
```

The empty input sequence returns an empty list. For a non-empty batch, the classifier SHALL validate every DTO structurally before beginning sufficiency or rule evaluation. If any DTO is malformed, the whole call raises `MarketStateContractViolation`; it returns no partial-success collection and no `ClassificationResult | Exception` union.

When every DTO is structurally valid, `batch_classify` preserves input order and is observationally equivalent to scalar invocation with the same fixed configuration:

```text
batch_classify([d_1, ..., d_n]) == [classify(d_1), ..., classify(d_n)]
```

This equivalence includes `INSUFFICIENT_HISTORY` results for short but structurally valid DTOs. It is not asserted for malformed batches because the batch call raises.

Assembly may validate/filter malformed source material before a universe-scale batch call to prevent containment blast radius, but that containment neither changes classifier semantics nor transfers the classifier-owned history-sufficiency decision to assembly.

## 6. Acceptance and Closure Criteria

Q-MS1-03/06 may close only when the canonical contract contains:

1. the formal non-string enum domains and disjoint reason/diagnostic ownership;
2. binary64 numeric representation, exact comparison policy, and `epsilon_relative = 1e-10` property-test exclusion;
3. a fixed-configuration pure classifier boundary with no hidden I/O/state;
4. every `ClassificationResult` field, per-status nullability/reason mapping, and typed malformed-DTO exception;
5. the non-duplicating export record and availability/nullability/diagnostic invariants;
6. classifier-owned insufficiency determination; short valid DTOs return `INSUFFICIENT_HISTORY` with no rule evaluation;
7. scalar API and all-valid, validate-first, fail-fast batch semantics including order-preserving scalar equivalence;
8. Q-MS1-04's `rule_set_hash` coverage explicitly includes the numeric policy and deadband formula/value;
9. classifier, assembly, and composed-pipeline acceptance tests are separated by their ownership boundary.

## 7. Session Handoff

### Session Summary

This draft makes output ownership and batch error containment explicit while selecting binary64 as the canonical computation representation required to close Q-MS1-04's property-test deadband.

### Decision Record

- Classifier output remains free of assembly provenance and operational failure.
- `Availability` represents composed-pipeline success/failure independently of classifier status.
- Short structural-valid history is a classifier status; malformed input is an exception.
- Batch classification is validate-first and fail-fast, never partial success.

### Open Questions

- Q-MS1-02 reference admission declarations and exceptional-bar eligibility remain outside this disposition.
- Q-MS1-07 physical module/package form and Q-MS1-08 final provenance/export details remain open.

### Evidence

The binary64 proposal relies on the entry repository representation finding and must be re-observed at canonical lock HEAD.

### Next Actions

Obtain adversarial review. If accepted, update Q-MS1-04 item 7 from externally dependent to satisfiable, then integrate Q-MS1-03/06 and Q-MS1-04 clauses through a controlled canonical diff.
