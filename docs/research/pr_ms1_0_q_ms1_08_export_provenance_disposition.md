# PR-MS1.0 — Q-MS1-08 Export and Provenance Disposition
Canonical Path: docs/research/pr_ms1_0_q_ms1_08_export_provenance_disposition.md

Version: v0.1.1
Status: DRAFT — ADVERSARIAL REVIEW REQUIRED
Scope: Resolve the V1 composed-pipeline export/provenance surface, the reference-admission declarations, limit-status coverage representation, and operational diagnostic vocabulary. This document does not implement a classifier, persistence writer, scheduler, or C-2 remediation.
Upstream Canonical Draft: `docs/research/pr_ms1_0_security_market_state_domain_contract.md` v0.2.4
Upstream Boundaries: PR-MS0 (`45f8fea`); Q-MS1-01/02 v0.1.2; Q-MS1-03/06 v0.1.1; Q-MS1-02/06 exceptional-bar v0.1.1; Q-MS1-07 v0.1.1.

## 0. Decision Labels

- **VERIFIED REPOSITORY FINDING** — observed against a named repository baseline; it must be re-observed at the lock candidate HEAD.
- **PROPOSED DECISION** — normative V1 candidate requiring explicit disposition.
- **DEFERRED** — intentionally outside the present acceptance surface, with an owner and prerequisite.
- **REPOSITORY GAP** — a capability absent from the current repository architecture; it is not satisfied by a weaker, similarly named field.

## 1. Entry Evidence and Non-negotiable Boundaries

### 1.1 Carried-forward repository findings

**VERIFIED REPOSITORY FINDING — re-verification required at lock:** `corporate_actions` is keyed by `(date, stock_id, kind)` and historical ingestion uses `DELETE + INSERT`. Earlier factor values are physically destroyed. `ingested_at`, `adjustment_state.last_event_date_used`, and `adjustment_state.n_events_applied` are not immutable adjustment-factor-set revision provenance.

**VERIFIED REPOSITORY FINDING — re-verification required at lock:** The current adjusted panel has no official price-limit-status field. A positive-volume zero-range bar is an official observation but is not a valid proxy for a price-limit lock.

**VERIFIED REPOSITORY FINDING — re-verification required at lock:** `market/trading_calendar.py` and `security_lifecycle` provide assembly-layer reference semantics for expected eligible sessions; the pure classifier DTO contains no such reference fields.

### 1.2 Locked boundary carried into this disposition

- `ClassificationResult` is classifier-owned and contains no panel identity, adjustment provenance, assembly diagnostic, or wall-clock timestamp.
- `MarketStateExportRecord` is composed-pipeline-owned and contains exactly one nullable `classification`, governed by `classification is not None iff availability == AVAILABLE`.
- `history_diagnostics` explains only `INSUFFICIENT_HISTORY`; `operational_diagnostics` explains only `Availability.OPERATIONAL_FAILURE`.
- Variant C-2 remains excluded from PR-MS1.1 acceptance until immutable adjustment-factor-set revision provenance exists. This document SHALL NOT relabel current overwrite metadata as sufficient C-2 provenance.

## 2. Reference-admission Declarations

### 2.1 Formal disposition of the existing integrator addition

**PROPOSED DECISION:**

```text
CLASSIFIER_REFERENCE_INPUTS_ADMITTED = NO
ASSEMBLY_REFERENCE_SOURCES = {calendar, security_lifecycle}
```

The pure classifier consumes only the canonical adjusted-OHLC DTO. It SHALL NOT accept listing date, lifecycle state, holiday calendar, price-limit status, or any other reference field.

Assembly MAY consume the two admitted reference sources only to construct the terminal eligible-session sequence and its history diagnostics/provenance. Every use SHALL be effective-date governed; an undated latest-state lookup is forbidden. Any additional reference source, including an official limit-status feed, requires a superseding Q-MS1-02/Q-MS1-08 disposition before use.

**Rationale:** the classifier's state is determinable from the DTO and fixed classifier configuration. Calendar/lifecycle knowledge is necessary for the assembly-owned distinction among natural shortfall, data gap, and diagnosis unavailable, but is not classifier semantic input.

## 3. Export Record and Provenance Identity

### 3.1 Required V1 export fields

**PROPOSED DECISION:** The composed pipeline SHALL emit one `MarketStateExportRecord` for every assembly attempt. The record continues to contain the locked fields:

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

`panel_snapshot_id`, `adjustment_provenance`, and `decision_available_at` SHALL be non-null when `availability == AVAILABLE`. For `Availability.OPERATIONAL_FAILURE`, each MAY be null only when the preceding assembly failure makes that fact unknowable; a non-null value SHALL remain truthful to work fully and independently established before the failure point. An `OPERATIONAL_FAILURE` record SHALL NOT populate `panel_snapshot_id` from a partial, rejected, or structurally invalid candidate panel. `limit_status_coverage` is always non-null.

The record SHALL NOT duplicate classifier-owned `status`, `state`, `matched_rule_id`, `reason_code`, `classifier_version`, `rule_set_hash`, or `as_of` at top level.

### 3.2 `PanelSnapshotId` semantics

**PROPOSED DECISION:** `PanelSnapshotId` SHALL be a stable content identity of the exact terminal adjusted-OHLC sequence submitted to the classifier, including:

- `security_id`, `as_of`, and every terminal session identity;
- adjusted OHLC values encoded as canonical binary64 bit patterns, not locale-formatted decimal strings;
- the eligible-session/reference basis identities used to assemble the sequence;
- the adjustment-provenance identity and assembly schema version.

The digest algorithm, canonical field ordering, byte encoding, and digest version SHALL be declared. A changed byte-level canonical input or assembly semantic requires a different `PanelSnapshotId`. A wall-clock assembly timestamp alone is not a snapshot identity.

### 3.3 `AdjustmentProvenance` semantics and C-2 boundary

**PROPOSED DECISION:** `AdjustmentProvenance` SHALL identify the adjustment method/version, the applied corporate-action factor-set content identity, and the source/basis identity used to produce the adjusted OHLC panel. It SHALL identify values actually applied, not merely the time an ingestion job ran.

For a corrected or late action with `ex_date <= as_of`, this field SHALL NOT be represented as immutable revision provenance under the current `DELETE + INSERT` architecture. It may document the current materialized factor set, but cannot support a claim that the same factor revision can be reconstructed later. Variant C-2 remains DEFERRED; no PR-MS1.1 acceptance fixture may treat this field as satisfying that prerequisite.

### 3.4 Assembly/reference provenance

**PROPOSED DECISION:** The export's panel provenance SHALL preserve the versioned/calendar coverage identity and effective-date lifecycle basis used for the terminal-sequence decision. It need not expose a classifier DTO reference field. This information may be a structured component of `PanelSnapshotId`/`AdjustmentProvenance` rather than a duplicated top-level column, provided its canonical decoding is documented.

## 4. Limit-status Coverage

### 4.1 Type and meaning

**PROPOSED DECISION:** Define a distinct non-string `Enum`:

```text
LimitStatusCoverage
  OFFICIAL_STATUS_UNAVAILABLE
```

V1 SHALL emit `OFFICIAL_STATUS_UNAVAILABLE` for every record. It is a coverage/capability declaration, not a claim about the individual session's limit status. For an `OPERATIONAL_FAILURE` record, it additionally asserts that no panel-level official-limit-status resolution path exists, independent of the failure cause; it does not assert that a panel was assembled. It SHALL NOT be used as a classifier input, `MarketState`, `ClassificationStatus`, `HistoryDiagnosticCode`, or `OperationalDiagnosticCode`; zero range SHALL NOT populate or override it.

The marker belongs in `MarketStateExportRecord` because it qualifies the interpretation of the assembled panel and is meaningful to each exported observation. A future official effective-dated source may introduce a new enum member only through a superseding disposition that specifies source PIT semantics, field-to-record mapping, and acceptance fixtures.

### 4.2 Acceptance effect

PR-MS1.1 SHALL test that structurally valid positive-volume zero-range bars are included without a classifier special branch, and that every resulting export record carries `OFFICIAL_STATUS_UNAVAILABLE`. The test SHALL demonstrate that zero range does not infer a price-limit lock.

## 5. Operational Diagnostics

### 5.1 Vocabulary supersession

**PROPOSED DECISION — supersession on canonical integration:** Replace the current single-member `OperationalDiagnosticCode` with:

```text
OperationalDiagnosticCode
  AS_OF_BAR_MISSING
  AS_OF_BAR_INVALID
  AS_OF_BAR_ZERO_VOLUME
  REFERENCE_BASIS_UNAVAILABLE
  UNCLASSIFIED_ASSEMBLY_FAILURE
```

The enum has a serialized value space disjoint from `ClassifierReasonCode` and `HistoryDiagnosticCode`. `ASSEMBLY_FAILURE` is removed; it is too coarse to distinguish normal data exclusions from an unavailable reference basis or a genuinely unclassified failure.

### 5.2 Assignment discipline

**PROPOSED DECISION:** For an assembly failure, exactly one operational diagnostic SHALL be emitted:

| Condition | Required code |
| --- | --- |
| No bar exists at `as_of` after expected-session determination | `AS_OF_BAR_MISSING` |
| The `as_of` bar is present but structurally invalid | `AS_OF_BAR_INVALID` |
| The `as_of` bar is otherwise valid but has zero volume | `AS_OF_BAR_ZERO_VOLUME` |
| The basis required to construct any terminal eligible-session sequence cannot be established | `REFERENCE_BASIS_UNAVAILABLE` |
| No listed condition applies, or the system cannot make the listed distinction truthfully | `UNCLASSIFIED_ASSEMBLY_FAILURE` |

`REFERENCE_BASIS_UNAVAILABLE` applies only when the calendar/lifecycle basis required to construct the terminal eligible-session sequence is unavailable, preventing any DTO from being built or classifier invocation. It is distinct from `HistoryDiagnosticCode.DIAGNOSIS_UNAVAILABLE`: that history diagnostic applies only after assembly successfully constructs a DTO, classifier invocation returns `INSUFFICIENT_HISTORY`, and the finer-grained basis needed to distinguish natural shortfall from data gap is unavailable. The two codes therefore occupy disjoint pipeline stages and remain independently reachable.

`UNCLASSIFIED_ASSEMBLY_FAILURE` explicitly communicates non-specific attribution; it SHALL NOT be formatted or documented as a root cause. An implementation SHALL select a more specific listed code whenever the evidence supports one. This vocabulary does not authorize network, filesystem, or database I/O inside the classifier.

## 6. Acceptance Contract

PR-MS1.1 composed-pipeline/assembly tests SHALL prove:

1. the classifier receives no reference field and `CLASSIFIER_REFERENCE_INPUTS_ADMITTED == NO` remains true;
2. calendar/lifecycle use is effective-date governed and its basis identity appears in export provenance;
3. a successful export has a stable, reproducible `PanelSnapshotId` for byte-identical canonical panel inputs and governed provenance;
4. a changed canonical panel field, adjustment basis/content, reference basis, or assembly schema version changes the snapshot identity;
5. every successful export carries non-null panel and adjustment provenance and a non-null decision-available time;
6. every export carries `OFFICIAL_STATUS_UNAVAILABLE`, and zero range does not assert a limit-lock fact;
7. missing, invalid, and zero-volume `as_of` bars independently produce the corresponding operational diagnostic and `Availability.OPERATIONAL_FAILURE`;
8. a terminal-sequence construction basis failure produces `REFERENCE_BASIS_UNAVAILABLE`, no DTO, no classifier invocation, and no guessed history diagnostic;
9. a separately unavailable finer-grained shortfall-versus-gap basis after successful DTO construction and classifier `INSUFFICIENT_HISTORY` produces `DIAGNOSIS_UNAVAILABLE`, not `REFERENCE_BASIS_UNAVAILABLE`;
10. `UNCLASSIFIED_ASSEMBLY_FAILURE` is used only when no specific code can be established;
11. an `OPERATIONAL_FAILURE` record cannot carry a `panel_snapshot_id` derived from a partial, rejected, or invalid panel;
12. no test claims Variant C-2 replay/auditability until the immutable revision-provenance remediation is separately closed.

## 7. Closure Criteria

Q-MS1-08 is closure-ready only when all of the following hold:

1. the reference-admission declarations in Section 2 are explicitly accepted, modified, or rejected;
2. `PanelSnapshotId` canonical encoding and `AdjustmentProvenance` content schema are specified with a digest/version procedure;
3. the record-level `LimitStatusCoverage` representation is accepted, modified, or rejected;
4. the operational diagnostic supersession and its per-condition assignment rules are accepted, modified, or rejected;
5. the Section 6 fixtures are assigned to assembly/composed-pipeline boundaries;
6. C-2 remains explicitly deferred, without an accidental weak-provenance substitution;
7. repository evidence is re-observed at the candidate lock HEAD and the canonical diff identifies every superseded type/field clause.

## 8. Session Summary

Q-MS1-08 separates four concerns that must not be conflated: classifier purity, panel identity, coverage disclosure, and operational root-cause attribution. It formalizes the existing reference-gate inference as a reviewable decision, proposes record-level disclosure of the absent official limit-status capability, and replaces a misleading single operational-failure label with typed, assignment-governed causes. It also separates a terminal-sequence construction failure from a post-classifier insufficient-history explanation, preserving reachability of both diagnostic domains. It does not close C-2.

## 9. Decision Record

| Item | Proposed disposition | Scope boundary |
| --- | --- | --- |
| Classifier reference inputs | `NO` | classifier stays reference-free |
| Assembly reference sources | `{calendar, security_lifecycle}` | effective-date terminal-sequence/provenance only |
| Panel identity | canonical content digest | complete terminal classifier input |
| Adjustment provenance | method + applied factor-set content identity | not immutable revision provenance |
| Limit status | record-level `OFFICIAL_STATUS_UNAVAILABLE` | coverage marker only |
| Operational diagnostics | five typed codes | assembly/composed pipeline only |
| C-2 | DEFERRED | immutable revision provenance remediation required |

## 10. Open Questions

- What exact canonical serialization and digest algorithm/version will form `PanelSnapshotId` and the applied factor-set content identity?
- Should `AdjustmentProvenance` be a structured nested value or a versioned opaque identifier with a documented resolver?
- Does the candidate repository expose enough immutable source/version identity for calendar and lifecycle provenance, or is an additional persistence capability required?
- Which separately governed design will provide append-only adjustment-factor revision provenance for C-2?

## 11. Evidence

- PR-MS0 lock record (`45f8fea`): pure snapshot/classifier boundary and C-2 governance constraint.
- Q-MS1-01/02 v0.1.2: raw adjusted-OHLC DTO, indicator identity, and C-2 derived-chain impact.
- Q-MS1-02/06 exceptional-bar v0.1.1: terminal-sequence treatment, official-limit-status absence, and operational-diagnostic gap.
- Q-MS1 canonical v0.2.4: current export fields and deferred Q-MS1-08 ownership.

## 12. Next Actions

1. Obtain adversarial review of Sections 2–6, with particular attention to whether the proposed root-cause vocabulary is sufficiently precise without asserting false causality.
2. Re-run the cited repository evidence at the actual candidate HEAD and record concrete file/symbol anchors.
3. If accepted, integrate the controlled supersessions into canonical contract text and renumber closure gates only during the final lock procedure.
4. Keep C-2 remediation as a separate diff-first design; do not fold writer/audit-model changes into PR-MS1.1.
