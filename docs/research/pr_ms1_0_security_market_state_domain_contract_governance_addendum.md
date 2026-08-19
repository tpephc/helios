# PR-MS1.0 — Security Market State Domain Contract Governance Addendum
Canonical Path: docs/research/pr_ms1_0_security_market_state_domain_contract_governance_addendum.md

Version: v0.3.1  
Status: DRAFT — ADVISOR-DIRECTED CLOSURE BLOCKER REMEDIATION PROPOSAL  
Append Target: `docs/research/pr_ms1_0_security_market_state_domain_contract.md`  
Governing Anchor: `45f8fea39f15778dc097f699ad8333256dcd7a3f`  
Historical Entry Baseline: `c2fb79f17d97ecd6e75518d84905d551c268ccf5`  
Scope: PR-MS1.0 contract-only; no executable classifier, persistence, production integration, or strategy adoption

## 0. Purpose and Decision Typing

This addendum resolves semantic gaps that would otherwise block PR-MS1.0 closure or permit PR-MS1.1 to implement tests against the wrong architectural boundary. It does not amend the locked PR-MS0 record. Its clauses are proposals until incorporated into, reviewed in, and locked with the PR-MS1.0 canonical contract.

Decision labels used below:

- **VERIFIED FINDING** — supported by repository evidence observed in the current PR-MS1.0 session.
- **ARTIFACT FINDING** — supported by the text of a named governance artifact; not a claim about repository code behaviour.
- **THEORETICAL DERIVATION** — follows from explicitly stated assumptions and must not be presented as repository evidence.
- **PROPOSED DECISION** — normative contract text proposed for PR-MS1.0 closure.
- **REPOSITORY VERIFICATION REQUIRED** — cannot be closed from the kickoff artifact alone.
- **DEFERRED** — intentionally assigned to a later authorised phase without leaving PR-MS1.1 semantic ambiguity.

## 1. Gating Decision — Q-MS1-00 Snapshot Semantics

### 1.1 Dependency finding

**ARTIFACT FINDING — governance dependency:** The kickoff's Q-MS1-01, Q-MS1-03, Q-MS1-04, and Q-MS1-06 decisions depend on whether classification is snapshot-based or stateful. Treating the former Q-MS1-05 as a peer decision permits the vocabulary, result type, precedence, and InputDTO to be specified before their governing state model is known.

### 1.2 Proposed decision

**PROPOSED DECISION — Q-MS1-00:** Security Market State V1 SHALL be a pure snapshot classifier.

For a canonical `SecurityMarketStateInput` and a fixed `classifier_version` / `rule_set_hash`, classification SHALL depend only on the values contained in that input. The classifier SHALL NOT accept or retrieve `prior_state`, classifier-owned persistent state, transition history, account state, portfolio state, strategy eligibility state, or hidden process-local state.

The classifier contract is therefore:

```python
classify(input_dto: SecurityMarketStateInput) -> ClassificationResult
```

and not:

```python
classify(input_dto, prior_state) -> ClassificationResult
```

### 1.3 Transition semantics

State transition observations MAY be derived after classification from an ordered series of successful snapshot outputs:

```text
transition[t] = (state[t - 1], state[t])
```

Hysteresis, debounce, persistence requirements, or transition-conditioned strategy behaviour are not properties of the V1 snapshot classifier. They require a separately governed downstream layer and SHALL NOT be inserted into PR-MS1.1 under the name of classifier implementation.

### 1.4 Consequences

- `prior_state` is forbidden from the canonical InputDTO.
- MS-P2 retains a non-circular definition: identical canonical snapshot inputs plus identical fixed classifier configuration (`classifier_version` and `rule_set_hash`) produce identical results.
- The PIT append tests operate on an `as_of` snapshot rather than an implicit state path.
- Cold-start and origin-state semantics are not V1 classifier concerns.
- The former Q-MS1-05 is closed by Q-MS1-00 and SHALL be retained only as a cross-reference or renumbered mechanically during contract integration.

## 2. Separate Domain Vocabulary from Classification Status

### 2.1 Type separation

**PROPOSED DECISION:** `MarketState` and `ClassificationStatus` SHALL be disjoint enums with distinct semantic ownership.

```python
# Illustrative contract sketch — not implementation.
from enum import Enum


class MarketState(Enum):
    """Finite V1 security-level state vocabulary.

    Every member requires an explicit positive, testable rule. Members are
    fixed by Q-MS1-01; no residual member is permitted.
    """

    # Members are intentionally unresolved until Q-MS1-01 closes.


class ClassificationStatus(Enum):
    """Outcome status; values are not market states."""

    OK = "OK"
    INDETERMINATE = "INDETERMINATE"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"


class Availability(Enum):
    """Composed-pipeline assembly availability; not a classifier outcome."""

    AVAILABLE = "AVAILABLE"
    OPERATIONAL_FAILURE = "OPERATIONAL_FAILURE"
```

`MarketState`, `ClassificationStatus`, and `Availability` SHALL use non-string `Enum`; external storage and serialization SHALL be performed by the assembly/export layer using the explicit `.value` representation. No `StrEnum` is permitted. `ClassificationStatus` contains only classifier outcomes; `OPERATIONAL_FAILURE` is exclusively an `Availability` member. The classifier-result invariant SHALL be:

```text
status == OK      <=> state is a MarketState member
status != OK      <=> state is None
matched_rule_id is not None <=> status == OK
```

`INDETERMINATE` means that the canonical DTO is valid, the required history is sufficient, and no positive V1 state rule matches. It is a status, not a residual state. `NEUTRAL`, `RANGE`, `UNKNOWN`, or equivalent names SHALL NOT be used to conceal residual classification; any such `MarketState` member requires its own positive rule.

### 2.2 Positive testing and the `else` prohibition

The prohibition on `else: STATE` applies to `MarketState`. It does not prohibit returning `ClassificationStatus.INDETERMINATE` after all positive rules have been evaluated and none has matched.

PR-MS1.1 SHALL include:

- at least one positive test per `MarketState` member;
- a constructed valid and history-sufficient DTO that matches no state rule and returns `INDETERMINATE` with `state is None`;
- invariant tests rejecting any result containing both `status != OK` and a non-null state.

These are non-vacuous tests of different semantic surfaces.

### 2.3 Malformed DTOs

Malformed DTOs, invalid enum values, inconsistent timestamps, non-finite required values, impossible window ordering, and other InputDTO contract violations SHALL raise a typed validation/programming error. They SHALL NOT be converted into `INDETERMINATE` or `INSUFFICIENT_HISTORY`.

## 3. Classifier Outcome, Assembly Availability, and Layer Boundary

**PROPOSED DECISION:** Every `ClassificationStatus` member (`OK`, `INDETERMINATE`, and `INSUFFICIENT_HISTORY`) is classifier-owned and may only be emitted by the pure classifier. `Availability` is a distinct composed-pipeline concept owned by the assembly layer: `AVAILABLE` means assembly succeeded and produced a classifier result; `OPERATIONAL_FAILURE` means assembly could not produce one.

The pure classifier SHALL NOT emit `OPERATIONAL_FAILURE`, because it is not a `ClassificationStatus` member and MS-I6 denies the classifier access to the operational mechanisms that generate that condition. The composed pipeline SHALL wrap an assembly failure in the public `MarketStateExportRecord` envelope with `availability=OPERATIONAL_FAILURE`, `classification=None`, and non-null assembly-owned `operational_diagnostics`. Classifier unit tests SHALL NOT mock database or filesystem failures.

### 3.1 Output models and producing layers

**PROPOSED DECISION:** Classifier output and composed-pipeline export are separate contract types. The following is an illustrative contract sketch, not implementation:

```python
# Illustrative contract sketch — not implementation.
class ClassificationResult:
    # Classifier boundary: determinable from a valid DTO plus fixed
    # classifier configuration (classifier_version and rule_set_hash).
    status: ClassificationStatus
    state: MarketState | None
    matched_rule_id: str | None
    reason_code: "ClassifierReasonCode | None"
    classifier_version: str
    rule_set_hash: str
    as_of: "TradingSession"

class MarketStateExportRecord:
    # Composed-pipeline boundary; no duplicated classifier result fields.
    availability: Availability
    classification: ClassificationResult | None
    security_id: str
    panel_snapshot_id: str
    adjustment_provenance: str
    assembly_schema_version: str
    history_diagnostics: "HistoryDiagnostics"
    operational_diagnostics: "OperationalDiagnosticCode | None"
    decision_available_at: "Timestamp"
```

Every `ClassificationResult` field SHALL be determinable from the valid DTO and fixed classifier configuration alone. Any field requiring assembly knowledge belongs only to `MarketStateExportRecord`. `reason_code` is classifier-owned; `NATURAL_HISTORY_SHORTFALL` and `DATA_GAP` belong to assembly-owned `history_diagnostics` and SHALL NOT require reference access by the classifier.

The envelope invariant SHALL be `classification is not None iff availability == AVAILABLE`. When availability is `OPERATIONAL_FAILURE`, `operational_diagnostics` SHALL be non-null; when availability is `AVAILABLE`, it SHALL be null. `availability == AVAILABLE` asserts only that assembly succeeded and a `ClassificationResult` was produced; it does not assert `state is not None`. Callers requiring a market state SHALL additionally check `classification.status == OK`.

### 3.2 Reason-code ownership and nullability

The canonical contract SHALL define `ClassifierReasonCode`, `HistoryDiagnosticCode`, and `OperationalDiagnosticCode` as separate enums. `ClassificationResult.reason_code` is nullable only when `status=OK`; otherwise it SHALL be one allowed classifier-owned reason code. `MarketStateExportRecord.history_diagnostics` carries assembly-owned history coverage reasons independently of classifier status; it SHALL use `DIAGNOSIS_UNAVAILABLE`, not null, when assembly cannot distinguish natural shortfall from data gap.

| Classifier status | Allowed classifier reason | Assembly/history diagnostic |
| --- | --- | --- |
| `OK` | `None` | optional provenance-only diagnostic |
| `INDETERMINATE` | `NO_RULE_MATCH` | none required |
| `INSUFFICIENT_HISTORY` | `REQUIRED_HISTORY_NOT_MET` | `NATURAL_HISTORY_SHORTFALL`, `DATA_GAP`, or `DIAGNOSIS_UNAVAILABLE` |

`OperationalDiagnosticCode` is required only when `availability=OPERATIONAL_FAILURE`; `HistoryDiagnosticCode` and `OperationalDiagnosticCode` SHALL NOT share a field or an enum value-space.

PR-MS1.1 test boundaries SHALL be separated:

- classifier unit tests: `OK`, `INDETERMINATE`, `INSUFFICIENT_HISTORY`, DTO validation errors, rule precedence, determinism, and invariance properties;
- assembly tests: source read/materialisation failures and canonical DTO construction;
- composed-pipeline tests: PIT invariants, `OPERATIONAL_FAILURE` propagation, and end-to-end result-envelope invariants.

## 4. Explicit `as_of` and Decision-Availability Semantics

### 4.1 Q-MS1-06a

**PROPOSED DECISION — Q-MS1-06a:** `as_of=t` is close-inclusive. It means that the complete official bar for trading session `t` is observable and the classification becomes decision-available only after that bar has closed and passed canonical assembly.

For an `N`-session rule window:

```text
window(t, N) = the N canonical trading-session observations ending at t,
               ordered oldest to newest, inclusive of t
decision_available_at > close_timestamp(t)
```

The result may be consumed only at a downstream decision point after `decision_available_at`; consumption/entry timing is strategy-layer policy and is deferred.

PIT variant A therefore appends or mutates market observations strictly after `t`. If a later contract chooses open-exclusive semantics, it MUST supersede this clause and redefine the window and append boundary; it cannot silently reinterpret `as_of`.

### 4.2 Trading-session history

**PROPOSED DECISION:** History sufficiency SHALL be stated in canonical eligible trading-session observations, not elapsed calendar days. V1 SHALL declare one scalar `required_history_sessions = max(window(R) for R in admitted_rules)`. A valid DTO with fewer canonical sessions than this scalar SHALL return `INSUFFICIENT_HISTORY`; no rule SHALL be evaluated. Partial evaluation based on per-rule sufficiency is explicitly rejected in V1.

Classifier and assembly reference-data admission SHALL be independently governed:

```text
CLASSIFIER_REFERENCE_INPUTS_ADMITTED = YES | NO
ASSEMBLY_REFERENCE_SOURCES = {calendar, security_lifecycle, ...}
```

`CLASSIFIER_REFERENCE_INPUTS_ADMITTED` governs fields present in the classifier DTO and its purity boundary. `ASSEMBLY_REFERENCE_SOURCES` governs temporally valid sources used solely to construct history diagnostics and export provenance. A calendar and security lifecycle source are necessary to distinguish missing expected sessions from naturally unavailable listing history; canonical panel rows alone cannot make that distinction. All assembly reference sources remain subject to effective-date governance and composed-boundary PIT tests.

At minimum, the research export SHALL preserve enough diagnostics to distinguish:

- `NATURAL_HISTORY_SHORTFALL` — the security did not yet have the required eligible trading history; and
- `DATA_GAP` — required history should exist under the selected calendar contract but is missing or invalid.

These are assembly-owned `HistoryDiagnostics` reason codes; they refine export diagnostics and do not create market states or classifier-owned availability statuses.

## 5. PIT Contract — Variants A, B, C, and C-2

### 5.1 Variant A — Future market-observation append invariance

Given a valid canonical dataset assembled for `as_of=t`, append or modify market observations with observation session strictly greater than `t`, rerun assembly, and classify the same security at `as_of=t`.

```text
classification_before(t) == classification_after(t)
```

Equality includes status, state, `matched_rule_id`, and all classifier-derived diagnostics that claim `as_of=t` semantics. Operational metadata such as run timestamp is excluded.

### 5.2 Variant B — Future-effective reference invariance

For every admitted classifier reference input or assembly reference source, mutate or append a reference value whose effective interval begins strictly after `t`. Reassembly and reclassification at `as_of=t` SHALL not change the canonical input, history diagnostic, or classification.

A positive-direction test SHALL also prove that a temporally valid reference mutation with effective time at or before `t` changes the canonical input and, for a fixture where that field is classification-relevant, changes the expected rule outcome.

**Reference admission gates:** Q-MS1-02 SHALL answer both `CLASSIFIER_REFERENCE_INPUTS_ADMITTED` and `ASSEMBLY_REFERENCE_SOURCES`.

- If no classifier reference field is admitted, classifier-level variant B is **N/A by contract** and no trivially-green classifier test SHALL be created.
- Every admitted classifier field and every assembly reference source requires a governed temporal-validity representation; undated current-state lookup is forbidden.
- Assembly reference sources used for history diagnostics require an assembly/composed-boundary variant B test, including a positive-direction effective-at-or-before-`t` fixture where classification-relevant assembly output changes.

### 5.3 Variant C — Future corporate-action restatement invariance

**THEORETICAL DERIVATION — conditional on repository verification:** Assume `features/dividend_adjustment.py` applies multiplicative backward adjustment. At snapshot `S`, for raw price `p(d)`:

```text
adj_S(d) = p(d) * product(f_e for ex_date(e) in (d, S])
```

For `S' > S`, if a newly known corporate action has `ex_date=e > t`, then all prices in a fixed `as_of=t` window are multiplied by the same positive factor. Under MS-P3, a correctly scale-invariant price rule must therefore preserve the `as_of=t` result.

**PROPOSED DECISION — PIT variant C:** Introduce a corporate action with `ex_date > t`, rebuild the adjusted panel using the real assembly path, and reclassify `as_of=t`. Status, state, and `matched_rule_id` SHALL remain unchanged.

This is not equivalent to appending a future bar. It tests restatement of historical adjusted values and therefore SHALL be an independent composed-pipeline acceptance test if the repository verification confirms that later corporate actions can restate the panel used by Market State assembly.

### 5.4 Required repository verification for variant C

Before locking the clause as an implementation obligation, PR-MS1.0 SHALL record file-and-symbol evidence for:

- the adjustment transform in `features/dividend_adjustment.py`;
- whether adjustment factors are multiplicative and backward-applied;
- the assembly/storage path used to populate adjusted OHLC;
- whether `daily_price_adj.volume` is raw, adjusted, or independently sourced.

The derivation SHALL remain labelled conditional until those facts are observed in the current repository. The repository verification SHALL also state whether the ex-date bar itself is adjusted; the interval convention in the factor product SHALL not be left implicit.

If verification does not confirm multiplicative backward adjustment, the canonical contract SHALL supply an alternative rationale for the locked MS-P3 requirement; it SHALL NOT leave MS-P3 as an unmotivated clause.

### 5.5 Variant C-2 — Late-arriving corporate action auditability

For a newly known or vendor-corrected action with `ex_date <= t`, classification at `as_of=t` MAY change. No invariance claim is made because the window's relative adjusted-price shape may legitimately change. Instead, the composed export SHALL contain provenance sufficient to attribute the change to a specific adjustment-factor-set revision. A classification change with identical adjustment provenance is a contract violation.

## 6. Price/Volume Transform Invariants

### 6.1 Price-side invariant

Every admitted rule SHALL declare its input domain and transform/invariance group as canonical rule metadata. At minimum, the vocabulary distinguishes `PRICE_SCALE`, `VOLUME_SHARE_UNIT`, `PRICE_VOLUME_JOINT`, and an explicitly justified `NO_ADMITTED_INVARIANCE` exception. The declaration, equality policy, deadband policy, and transform group SHALL contribute to `rule_set_hash`. A `NO_ADMITTED_INVARIANCE` declaration is not self-authorising: it requires an explicit closure-gate disposition and test-boundary rationale.

For every rule declared `PRICE_SCALE`, every valid price window `P`, and every finite positive constant `c` in the governed test domain:

```text
R(c * P, non_price_inputs) == R(P, non_price_inputs)
```

Absolute-price thresholds are forbidden. Equality-boundary semantics (`>`, `>=`, `<`, `<=`) SHALL be stated for every thresholded rule.

PR-MS1.1 SHALL use property-based tests over a bounded positive factor domain, proposed default `c in [0.01, 100]`. Generated samples SHALL be constructively excluded from every declared threshold deadband; tolerance-based assertions SHALL NOT be used to mask a classification flip. The deadband-generation algorithm (absolute epsilon, relative epsilon, or governed maximum) SHALL close with Q-MS1-04's threshold-equality decision and is not closed by this addendum. Exact-threshold, immediately-below, and immediately-above fixtures SHALL independently verify the declared strict/non-strict equality policy. The final factor domain must exclude overflow/underflow artefacts for the selected numeric type.

### 6.2 Hard constraint on mixed adjusted-price/raw-volume primitives

**PROPOSED DECISION:** A primitive that combines backward-adjusted price with unadjusted raw volume — including price-times-volume, dollar volume, turnover proxies, or VWAP-like proxies — SHALL NOT be admitted into V1 unless the contract supplies and verifies an adjustment-consistent joint transform that passes PIT variant C.

Documenting a discontinuity is insufficient. This is a PIT correctness constraint, not merely a data-quality caveat.

### 6.3 Volume-side invariant

If Q-MS1-02 admits volume-derived primitives, the contract SHALL define the applicable corporate-action/share-count transform and require invariance under economically equivalent share-unit rescaling. In abstract form, for a split factor `k > 0`:

```text
price'  = price / k
volume' = volume * k
```

Every admitted `VOLUME_SHARE_UNIT` or `PRICE_VOLUME_JOINT` rule must declare which quantities remain invariant and prove the rule respects its transform. A price-only transform SHALL NOT be applied to a joint rule. A raw rolling-volume comparison across a split boundary SHALL NOT be assumed valid without such a contract.

If repository evidence cannot establish an adjustment-consistent volume series in PR-MS1.0, all volume-derived primitives SHALL be excluded from Market State V1 and explicitly deferred.

## 7. Per-Security Boundary and Cross-Sectional Exclusion

**PROPOSED DECISION:** V1 classification is per-security. Canonical InputDTO fields SHALL describe one security and its temporally valid input window only. Cross-sectional ranks, universe percentiles, current-constituent membership, candidate-set membership, peer-group aggregates, and any field whose value depends on other securities are forbidden V1 inputs.

This exclusion prevents universe-membership survivorship leakage and preserves the bounded PIT test surface. It also reinforces G3: strategy candidate membership is not Market State evidence.

If PR-MS1.1 exposes a batch API, it SHALL require every DTO to be valid. Under that all-valid precondition, it SHALL satisfy:

```text
batch_classify([dto_1, ..., dto_n])
    == [classify(dto_1), ..., classify(dto_n)]
```

including order preservation. A malformed DTO SHALL raise a typed contract violation and fail the whole `batch_classify` call; partial-success or per-item-exception return types are out of scope. Before a universe-scale caller invokes `batch_classify`, the assembly layer SHALL validate/filter DTOs and export any excluded-item operational diagnostics. The assembly validation/filtering design is an explicit open assembly-boundary item; it does not change fail-fast batch semantics. Batch execution is an optimisation only; it SHALL NOT introduce cross-security coupling or change classification semantics.

## 8. Taiwan-Market Bar Validity

Q-MS1-02/Q-MS1-06 SHALL explicitly disposition the following observations before rules using range, breakout, rolling extrema, or volume are admitted:

- price-limit locked sessions, including zero-range or one-price bars;
- trading suspensions and resumptions;
- zero-volume or effectively no-trade sessions;
- structurally missing bars;
- newly listed securities with naturally short histories.

For each condition, the contract SHALL state exactly one treatment:

1. valid observation included in the rule window;
2. valid session represented with a governed sentinel/flag and rule-specific handling;
3. excluded from the rule window under an explicit canonical-panel rule; or
4. unavailable result with a machine-readable reason.

Silently dropping such rows, forward-filling prices, or converting them to ordinary zero values is forbidden unless separately justified and tested. PR-MS1.0 makes no empirical claim about which treatment produces alpha.

## 9. Rule Identity, Versioning, and Replay Provenance

### 9.1 Dual identity

**PROPOSED DECISION:** Classification output and research export SHALL carry both:

- `classifier_version`: human-readable semantic version for the public classifier contract; and
- `rule_set_hash`: deterministic digest of the canonical rule definition, precedence, threshold values, numeric policy, and vocabulary identity.

Any semantic change to vocabulary, rule predicates, precedence, threshold equality, required history, canonical input meaning, or numeric comparison policy requires a `classifier_version` bump and a new `rule_set_hash`. A packaging-only or comment-only change may preserve both if canonical rule material is byte-for-byte/structurally unchanged under the governed hash procedure.

V1 rules SHALL normally be representable as declarative rule data with canonical serialization before PR-MS1.1 implementation. If a specifically admitted rule is demonstrated to require imperative expression, an explicit, governed escape hatch MAY use an AST-normalized canonical representation with a documented digest procedure and a fixture proving comment/formatting changes do not alter the digest. The escape hatch must be recorded by Q-MS1-01/Q-MS1-08 before implementation; it cannot be introduced ad hoc.

**INTEGRATOR ADDITION — pending separate ledger disposition:** The hash is not a substitute for version review; it is a guard against an omitted version bump. A vocabulary change requires a major `classifier_version` bump; a threshold or predicate change requires at least a minor bump. The contract SHALL define the applicable semver treatment for other semantic changes before PR-MS1.1 implementation.

### 9.2 Input provenance

`as_of + classifier_version` is insufficient to reproduce a classification when historical adjusted prices may be restated. `MarketStateExportRecord`, not `ClassificationResult`, SHALL include at minimum:

- security identifier;
- `as_of` session and decision-availability timestamp or policy identifier;
- availability, nullable `classification`, and classifier status/state/reason code within a present classification;
- assembly-owned history diagnostics and typed operational diagnostics as separate fields;
- `classifier_version`;
- `rule_set_hash`;
- matched rule identifier within `ClassificationResult`, nullable when classifier status is not `OK`;
- canonical input-panel snapshot identity or equivalent immutable provenance;
- adjustment-factor-set/corporate-action provenance sufficient to identify the adjusted values used;
- assembly/schema version;
- history coverage diagnostics required by Section 4.2.

The exact storage fields are Q-MS1-08's responsibility, but the above replay properties are mandatory. Wall-clock run timestamps alone do not satisfy snapshot identity.

## 10. Naming Discipline

The token `regime` SHALL be reserved for the broad-market layer represented by `features/regime.py`. Security-level enum, result, module, and rule names SHALL use `market_state` / `MarketState` terminology and SHALL NOT redefine broad regime semantics.

Additional naming constraints:

- MAD-, ATR-, z-score-, or fixed-multiple thresholds SHALL NOT be named `percentile` unless they are computed from an empirical quantile definition;
- `INDETERMINATE` SHALL NOT be renamed `NEUTRAL`;
- availability/status terminology SHALL NOT be embedded as a `MarketState` member;
- rule identifiers SHALL be stable, explicit, and exportable for replay.

## 11. Evidence Table Correction

`strategies/trend_breakout.py` SHALL be removed from the verified repository-evidence table unless the current session re-observes its symbols and access mechanisms. It MAY be retained in an `Unverified / Deferred Adoption Surfaces` appendix with this label:

> Historical anchor only. Strategy adoption is outside PR-MS1.0 scope; precise access mechanism and current line anchors have not been re-verified.

Line numbers from a prior audit SHALL NOT be reused as current evidence without re-derivation. File-and-symbol identity is the minimum provenance for material behavioural claims.

## 12. Revised Decision Matrix

| ID | Decision | Required closure output |
| --- | --- | --- |
| Q-MS1-00 | Snapshot vs stateful | **Proposed CLOSED: snapshot classifier**; no prior state or hidden state. |
| Q-MS1-01 | V1 state vocabulary | Finite `MarketState`; every member has a positive rule; no status-like members. |
| Q-MS1-02 | Canonical inputs | Minimum per-security inputs; classifier/assembly reference admission; volume admission; bar-validity disposition; scalar required history. |
| Q-MS1-03 | Result representation | Non-string `MarketState`/`ClassificationStatus`/`Availability` enums, result/export separation, availability and nullability invariants, typed diagnostic ownership, malformed-DTO exception policy, and layer ownership. |
| Q-MS1-04 | Precedence | Deterministic precedence or mechanically proven mutual exclusivity; equality-boundary policy. |
| Q-MS1-05 | Transition requirement | Closed by Q-MS1-00; transitions are derived downstream and deferred. |
| Q-MS1-06 | API/InputDTO | Pure snapshot API, no `prior_state`, per-security DTO, all-valid batch equivalence, no hidden I/O. |
| Q-MS1-06a | `as_of` semantics | Close-inclusive window ending at `t`; available only after close/canonical assembly. |
| Q-MS1-07 | Physical form | Module/package decision based on re-observed ADR-006 cohesion evidence. |
| Q-MS1-08 | Export/provenance | `classifier_version`/`rule_set_hash` identity, canonical serialization/escape hatch, immutable panel/adjustment provenance, and history diagnostics. |

## 13. Revised PR-MS1.0 Closure Gate

PR-MS1.0 SHALL NOT close unless every item below is satisfied by the canonical contract or explicitly deferred without leaving PR-MS1.1 semantic ambiguity.

1. Q-MS1-00 is closed before Q-MS1-01/03/04/06; V1 is explicitly snapshot-based or a superseding, fully specified stateful contract exists.
2. `MarketState`, `ClassificationStatus`, and `Availability` are distinct non-string `Enum` types. `ClassificationStatus` contains classifier outcomes only; `Availability.OPERATIONAL_FAILURE` is not a classifier status. Every state has a positive, testable rule; no state is a residual catch-all.
3. `ClassificationResult.status == OK` iff `state` is non-null; non-OK status implies `state is None`; `matched_rule_id` is non-null iff `status == OK`.
4. `INDETERMINATE` is a classifier status for valid, sufficient, non-matching input, not a market state.
5. Malformed DTOs raise a typed contract/validation error and are not converted into availability status.
6. Ownership is fixed: classifier owns every `ClassificationStatus` outcome; assembly/composed pipeline owns `Availability` and SHALL emit its public export envelope. `classification is not None iff availability == AVAILABLE`; an operational failure requires non-null typed `operational_diagnostics`.
7. InputDTO fields, types, window shape, session ordering, `window[-1].session == as_of`, scalar required-history requirement, and `as_of` decision-availability semantics are explicit.
8. `as_of=t` states whether bar `t` is included. Under the proposed contract it is close-inclusive and unavailable for decisions before the completed `t` bar is assembled.
9. Classifier-reference admission and assembly-reference sources are separately explicit. Classifier-level variant B is documented N/A only where no classifier reference field is admitted; every assembly reference source remains effectively dated and testable at the assembly/composed boundary.
10. PIT variant A is implementable at the composed-pipeline boundary.
11. If classifier reference input is admitted, classifier-level PIT variant B and its positive-direction test are implementable with governed effective-date semantics. If `ASSEMBLY_REFERENCE_SOURCES` is non-empty, assembly/composed-boundary PIT variant B and its positive-direction test are independently implementable with governed effective-date semantics.
12. The real corporate-action assembly path has been inspected. Variant C invariance for `ex_date > t` and C-2 auditability for `ex_date <= t` are independently implementable; if backward-multiplicative adjustment is not verified, a substitute MS-P3 rationale is recorded.
13. Every admitted rule declares a transform/invariance group, equality policy, and threshold deadband. Price-scale rules use constructive deadband exclusion plus exact-boundary tests.
13a. Any `NO_ADMITTED_INVARIANCE` rule has an explicit closure-gate disposition, architecture rationale, and test-boundary treatment; rule metadata alone is insufficient.
13b. The threshold-deadband generation algorithm is closed under Q-MS1-04; until then, the property-test sampling policy is not closure-complete.
14. Any volume or joint price-volume primitive has an adjustment-consistent declared transform and volume/share-unit invariant; otherwise it is excluded from V1.
15. Price-limit locked bars, suspension/resumption, zero-volume sessions, missing bars, and natural listing-history shortfall each have an explicit canonical treatment.
16. V1 inputs are per-security. Cross-sectional ranks, universe membership, candidate membership, and peer aggregates are forbidden.
17. If a batch API exists, it requires all DTOs valid; batch/scalar semantic equivalence and order preservation are acceptance requirements, while malformed inputs fail the whole call.
17a. The assembly boundary specifies validation/filtering and excluded-item diagnostics before universe-scale `batch_classify` invocation; this operational containment does not alter classifier batch semantics.
18. Rule overlap resolution is deterministic, including exact-threshold equality.
19. Classifier API is pure and deterministic with no DuckDB/filesystem/network/broker I/O and no account/portfolio/execution/strategy leakage.
20. `classifier_version` bump rules, declarative canonical `rule_set_hash` derivation, and any AST-normalized escape hatch are specified.
21. `ClassificationResult` contains only DTO-plus-fixed-configuration determinable fields; `MarketStateExportRecord` contains availability, typed operational/history diagnostics, and immutable input-panel and adjustment provenance sufficient to replay restated historical inputs.
22. The physical module/package decision cites current ADR-006 evidence; ADR content is not inferred from its filename.
23. Unverified strategy anchors are moved out of verified evidence or re-observed with file-and-symbol provenance.
24. PR-MS1.1 acceptance tests are enumerated at their correct unit, assembly, or composed-pipeline boundaries; no trivially-green tests are accepted.
25. The staged diff remains governance-only; repository HEAD, origin relationship, working tree, lock anchor, and focused diff are re-observed immediately before lock.

## 14. Revised First Commands

```bash
git rev-parse HEAD
git rev-parse origin/main
git status
git branch -vv
git log --oneline --decorate -5
git diff --stat
git diff --cached --stat

grep -nE '^(##|###) |Q-MS1-|MS-P[123]|MS-I[56]|G[123]' \
  docs/research/pr_ms0_repository_semantic_audit_decision_record.md

# Re-derive symbol anchors; do not inherit historical line numbers.
grep -nE 'def (compute_indicators|add_donchian|add_volume_indicators)' \
  features/technical.py
grep -nE 'def compute_regime' features/regime.py

# ADR-006 is required for Q-MS1-07. Resolve the real path before reading it.
find docs/adr -maxdepth 1 -type f -iname '*006*' -print
# Then read the resolved path, for example:
# sed -n '1,240p' docs/adr/<resolved-adr-006-filename>

# Verify the adjustment mechanism supporting MS-P3 and PIT variant C.
grep -nE 'def |factor|cumprod|adjust' features/dividend_adjustment.py

# Confirm the adjusted-OHLC/raw-volume claim and locate its assembly path.
grep -RIn 'daily_price_adj' \
  --include='*.py' --include='*.sql' . | head -40

# Inspect strategy code only if needed to correct evidence classification;
# strategy adoption remains outside PR-MS1.0 scope.
grep -nE 'class |def ' strategies/trend_breakout.py
```

Any missing path or symbol is an observation to record, not permission to invent a replacement. `find` output must be resolved to one actual ADR-006 file before its contents are cited.

## 15. PR-MS1.1 Acceptance-Test Contract

The canonical contract SHALL enumerate at least the following tests without implementing the classifier in PR-MS1.0.

### 15.1 Classifier unit boundary

- one positive fixture per `MarketState`;
- valid, sufficient, non-matching fixture → `INDETERMINATE`, `state=None`;
- insufficient window of fewer than `required_history_sessions` → `INSUFFICIENT_HISTORY`, `state=None`, with a spy/assertion that no rule was evaluated;
- malformed DTO → typed exception;
- overlapping positive rules → declared precedence;
- exact-threshold equality → declared result;
- identical DTO + version/hash → identical result;
- price-scale property test over governed `c` domain with constructively excluded threshold deadbands; exact threshold fixtures remain separate;
- admitted volume/share-unit transform property test;
- mandatory transform-group declaration and an explicit closure disposition for any `NO_ADMITTED_INVARIANCE` rule;
- scalar/batch equivalence for all-valid DTO batches if batch API exists;
- test asserting that per-item output is independent of batch neighbours and batch order.

### 15.2 Assembly boundary

- canonical close-inclusive window construction;
- trading-session/history diagnostics derived from governed calendar/security-lifecycle sources;
- reference effective-date filtering for every admitted assembly reference source and classifier reference input;
- Taiwan-market exceptional-bar representation;
- adjusted OHLC and volume provenance construction;
- operational source failure captured without invoking classifier, with typed `operational_diagnostics`.
- DTO validation/filtering and excluded-item operational diagnostics before universe-scale batch invocation.

### 15.3 Composed-pipeline boundary

- PIT variant A future-observation append invariance;
- PIT variant B future-effective reference invariance and positive-direction mutation, if admitted;
- PIT variant C future corporate-action restatement invariance, if applicable;
- PIT variant C-2 late-action auditability: `ex_date <= t` may change classification only with attributable adjustment-factor-set revision provenance;
- assembly failure → `availability=OPERATIONAL_FAILURE`, `classification=None`, and non-null typed `operational_diagnostics`;
- successful assembly → `availability=AVAILABLE`, non-null `classification`; `AVAILABLE` with `INDETERMINATE` or `INSUFFICIENT_HISTORY` is explicitly valid;
- output provenance identifies classifier rule set and exact canonical input snapshot.

## 16. Deferred Items

The following remain outside PR-MS1.0 and PR-MS1.1 unless separately authorised:

- transition persistence, hysteresis, debounce, and state-store design;
- broad-market regime as a required classifier input;
- cross-sectional Market State models;
- strategy adoption and same-day/specific-entry policy;
- production DuckDB persistence and `daily_run` integration;
- execution, portfolio, risk, order, fill, slippage, queue, or partial-fill logic;
- empirical alpha, Sharpe, win-rate, or expected-return claims.

Deferral does not permit placeholder fields for these concerns in the V1 DTO.

## 17. Integration Instructions

This addendum is structured for semantic integration rather than blind file concatenation. When merging into the canonical contract:

1. insert Q-MS1-00 before the existing Q-MS1-01 decision sequence;
2. replace the existing availability section with Sections 2 and 3 of this addendum;
3. split `as_of` into Q-MS1-06a and incorporate Section 4;
4. replace PIT/corporate-action clauses with Sections 5 and 6 after repository verification;
5. add the per-security, Taiwan-bar, provenance, and naming constraints;
6. replace the closure gate and first-command blocks with Sections 13 and 14;
7. retain evidence labels, especially the conditional status of the restatement derivation until source verification completes;
8. renumber into the canonical 0–15 structure, including closure gate and test references; do not preserve this addendum's local section numbers, duplicate clauses, or contradictory clauses.

## 18. Session Handoff

### Session Summary

The advisor-directed v0.3 remediation covers Q-MS1-00 snapshot semantics; non-string state/status/availability typing; classifier versus export output ownership; scalar required history; per-layer reference admission; future and late corporate-action handling; declared rule transform groups; declarative hashing with a governed escape hatch; and fail-fast all-valid batch semantics with assembly-side containment.

### Decision Record

- Proposed V1 model: pure per-security snapshot classifier.
- Proposed result model: non-string `MarketState`, `ClassificationStatus`, and assembly-owned `Availability`; `ClassificationResult` at the pure classifier boundary; `MarketStateExportRecord` with typed history/operational diagnostics at the composed-pipeline boundary.
- Proposed temporal model: close-inclusive `as_of=t`, decision-available only after the completed bar is assembled.
- Proposed PIT model: variants A/B/C, with layer-specific B admission, C future-action invariance, and C-2 late-action auditability; C's derivation remains conditional on source verification.
- Proposed version model: `classifier_version` plus deterministic `rule_set_hash` and immutable input provenance.

### Open Questions

- Final positive-rule `MarketState` vocabulary.
- Minimum canonical primitives, admitted rules, and `required_history_sessions`.
- Classifier reference admission, assembly reference sources, and whether any volume-derived input is admitted in V1.
- Exact Taiwan-market exceptional-bar treatments.
- Canonical rule-set serialisation/hash algorithm.
- Q-MS1-04 deadband-generation algorithm and any `NO_ADMITTED_INVARIANCE` exception disposition.
- Assembly validation/filtering policy for universe-scale batch invocation.
- Current ADR-006 content and resulting module/package decision.
- Exact panel snapshot / adjustment provenance available in the repository.

### Evidence

- Governing PR-MS0 anchor: `45f8fea39f15778dc097f699ad8333256dcd7a3f`.
- Historical entry baseline: `c2fb79f17d97ecd6e75518d84905d551c268ccf5`; it is not asserted as current HEAD.
- The kickoff records `features/dividend_adjustment.py` as multiplicative backward adjustment and `daily_price_adj.volume` as raw, but this addendum deliberately marks the stronger behavioural derivation as requiring current source verification.

### Next Actions

1. Run the revised entry and source-verification commands.
2. Record Q-MS1-00 before deciding vocabulary, result, precedence, or DTO shape.
3. Close reference/volume admission gates and exceptional-bar semantics.
4. Integrate this addendum semantically into the canonical contract.
5. Perform internal consistency, test-boundary, and staged-diff review before proposing the PR-MS1.0 lock candidate.
