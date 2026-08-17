# PR-MS0 — Repository Semantic Audit Decision Record
**Canonical Path:** `docs/research/pr_ms0_repository_semantic_audit_decision_record.md`

**Document ID:** `PR-MS0-SEMANTIC-AUDIT`
**Version:** v0.3.4-DRAFT
**Status:** LOCKED — PR-MS1.0 AUTHORISED
**Program:** Market-State Modularization
**Repository:** Helios
**Record class:** COMPACT GOVERNANCE DECISION RECORD
**Repository evidence anchor:** `47dfab4` (historical audit anchor; re-observe current HEAD before lock)
**Created:** 2026-08-17
**Lock reference:** `45f8fea39f15778dc097f699ad8333256dcd7a3f`

---

## 0. Purpose

PR-MS0 determines the minimum semantic boundaries required before Helios
begins Market State domain design.

This record intentionally uses proportional governance. PR-MS0 governs a
research-stage architecture hypothesis; it does not create a production
data contract, persistence schema, strategy migration, or execution
dependency.

The document exists to preserve repository evidence, lock
expensive-to-violate semantic boundaries, lock PIT/data-validity
properties, and bound PR-MS1.0.

Git history is the content-addressed audit trail. PR-MS0 does not
introduce a separate canonical-hash/backfill protocol.

## 1. Authority and Evidence Rule

Evidence precedence:

1.  applicable locked Helios governance / ADRs;
2.  directly observed repository source at the declared audit anchor;
3.  directly observed tests and runtime evidence;
4.  this decision record;
5.  handoff / kickoff assumptions.

> Repository truth \> handoff assumptions.

SHA, test state, clean-tree state, remote-sync state, ADR text,
path/line range, symbol identity, schema identity, and runtime/tool
version SHALL NOT be asserted unless directly observed.

PR-MS0 is a document artifact, not a session transcript. Material
observations required to justify G1/G2/G3 are therefore recorded below.

## 2. Audited Repository Surfaces

Feature/regime: `features/regime.py`, `features/bearish_regime.py`,
`features/bullish_features.py`, `features/technical.py`.

Strategy: `strategies/base.py`, `strategies/trend_breakout.py`,
`strategies/trend_pullback/types.py`,
`strategies/trend_pullback/screener.py`,
`strategies/trend_pullback/signal_generator.py`.

Orchestration: `scripts/daily_run.py`, `scripts/find_bullish_setups.py`,
`scripts/generate_signals.py`.

Adjustment/data: `daily_price`, `daily_price_adj`, `corporate_actions`,
`adjustment_state`.

## 3. Repository Findings

### F-MS0-1 --- Primitive technical indicator layer exists

**Observed surface:** `features/technical.py`

**Observed symbols:**

- `compute_indicators()` — `features/technical.py:145`
- `add_donchian()` — `features/technical.py:112`
- `add_volume_indicators()` — `features/technical.py:123`

The module owns primitive technical-indicator computation from market data.

**Disposition:** KEEP. Market State SHALL NOT be collapsed into the primitive-indicator layer.

### F-MS0-2 --- Temporal feature layer already exists

**Observed surfaces:** `features/bullish_features.py`, `features/bearish_regime.py`.

These modules contain path-dependent / temporal observations used by strategy research and screening.

**Disposition:** KEEP. No large parallel structure hierarchy is justified by PR-MS0 evidence.

### F-MS0-3 --- Broad-market regime is a distinct context

**Observed surface:** `features/regime.py`

**Observed symbol:** `compute_regime()` beginning at `features/regime.py:36`.

The module classifies broad TAIEX market context.

**Disposition:** KEEP.

`BroadMarketRegime ≠ SecurityMarketState`

PR-MS0 does not make Broad Market Regime a required Market State classifier input.

### F-MS0-4 --- Setup is already a distinct strategy semantic layer

**Observed:** `PullbackCandidate`, `find_pullback_candidates()`, and pullback `generate_signals()` in the `strategies/trend_pullback/` surface.

Observed flow:

`Feature / Context → PullbackCandidate → Signal`

Setup/Candidate is therefore distinct from Signal.

### F-MS0-5 --- TrendBreakout currently combines responsibilities

**Observed surface:** `strategies/trend_breakout.py`

**Observed symbols:**

- `TrendBreakoutStrategy` — line 67
- `TrendBreakoutStrategy.generate_signals()` — line 70
- `TrendBreakoutStrategy._load_market_regime()` — line 95
- `TrendBreakoutStrategy._load_features_with_history()` — line 112
- `TrendBreakoutStrategy._check_symbol()` — line 161

The observed class surface combines strategy decision responsibilities across structural interpretation, strategy eligibility/scoring, and Signal construction.

Method names `_load_market_regime()` and `_load_features_with_history()` indicate strategy-side data access. The precise access mechanism was not re-inspected during the lock-readiness pass and is therefore not asserted here.

This is legacy repository evidence, not a precedent for Market State. It supports MS-I6: Market State classification SHALL NOT repeat this pattern by owning its own data access.

**Disposition:** existing legacy surface; future separation may be considered under separate governance. PR-MS0 does not authorise that migration.

### F-MS0-6 --- Production orchestration has a derived-data seam

**Observed surface:** `scripts/daily_run.py`

**Observed area:** Step 4 feature/regime build before Step 7 entry generation.

A future derived Market State can therefore be built upstream of strategy entry generation without moving ownership into strategy code. PR-MS0 does not authorise production integration.

### F-MS0-7 --- Derived-feature failure can currently be non-blocking

**Observed surface:** `scripts/daily_run.py`

**Observed area:** Step 4 exception path.

If a future strategy explicitly requires Market State, stale or unavailable Market State must not silently authorise a risk-increasing decision.

### F-MS0-8 --- Adjusted-price history uses multiplicative backward adjustment

**Observed surface:** `features/dividend_adjustment.py`

Observed adjustment semantics:

- `cum_factor[T] = ∏ event_factor[E]` for events with `E.date > T`;
- `adj_close[T] = raw_close[T] * cum_factor[T]`;
- cash-dividend `adjustment_factor = after_price / before_price`;
- adjusted OHLC columns are present in `daily_price_adj`;
- `daily_price_adj.volume` retains raw volume in the current implementation.

Because every price adjustment is multiplicative, restatement between two adjustment vintages acts as a constant positive rescaling over a fixed historical window. A classifier satisfying MS-P3 therefore cannot change solely because of that price rescaling.

The raw-volume policy is an observed current implementation state. If volume adjustment is introduced later, the MS-P3 transform definition SHALL be revisited so that the test continues to replicate the actual restatement transform.

Historical adjusted-price-vintage storage is not required for Market State V1 provided every admitted V1 price-side rule satisfies MS-P3.

## 4. G1 — Market State Ownership

**Evidence:** F-MS0-3, F-MS0-4, F-MS0-5, F-MS0-6.

**Nature:** corrective architecture governance, not a claim that all current strategy code already follows this boundary.

**Disposition:** LOCKED

Security Market State SHALL be owned within the existing `features`
bounded area and SHALL NOT be owned by `strategies/`, `portfolio/`, or
`execution/`.

Security Market State describes an individual security's structural
market condition. It is not strategy intent, portfolio state, or
execution state.

Physical module form is deliberately not locked:

`single module vs package → DEFERRED_TO_PR_MS1.0`

Default: start with a single module until at least two internally
cohesive responsibilities are demonstrated.

## 5. G2 — Structure Ownership

**Evidence:** F-MS0-1, F-MS0-2, F-MS0-5.

**Disposition:** LOCKED — MINIMAL EXTRACTION

Existing feature ownership remains authoritative. PR-MS0 does not
authorise a large `features/structure/` hierarchy.

PR-MS1 MAY introduce only the minimum direction-neutral structural
representation required by the Market State domain.

A broader structure package requires actual shared responsibility or
duplication across multiple consumers.

> Cohesion before abstraction.

## 6. G3 — Semantic Boundary

**Evidence:** F-MS0-4, F-MS0-5.

**Disposition:** LOCKED

Target architecture:

`Feature → [MarketState] → Setup → Signal → Order`

`[MarketState]` is optional conditioning for existing strategies.

Enforceable invariant:

`Feature ≠ MarketState ≠ Setup ≠ Signal ≠ Order`

Feature = deterministic market observation. MarketState = deterministic
description of one security's structural condition. Setup =
strategy-specific candidate/eligibility object. Signal = strategy
decision expressing trade intent. Order = downstream
portfolio/execution-specific instruction or intent.

Market State participation remains optional for existing strategies
until separately governed migration adopts it. No Market State name
alone may imply BUY, SELL, EXIT, ADD, or REDUCE.

## 7. Classifier Properties

### MS-P1 --- Composed-Pipeline PIT Safety

Classification at `as_of=t` SHALL use only information valid at or before `t`.

Required test boundary:

`raw/reference data → assembly → InputDTO → classifier`

Testing only the classifier against an already-assembled DTO is insufficient for end-to-end PIT safety.

Required test variants:

A. **Future-observation append**

1. assemble and classify for `as_of=t`;
2. append market observations strictly after `t`;
3. reassemble and classify again for the same `as_of=t`;
4. the semantic classification result MUST remain unchanged.

B. **Future-effective reference mutation**

1. assemble and classify for `as_of=t`;
2. modify or replace a reference-data value whose effective date is strictly after `t`;
3. reassemble and classify again for the same `as_of=t`;
4. the semantic classification result MUST remain unchanged.

Variant B is necessary but not sufficient evidence that effective-date filtering is implemented, because an implementation that ignores the reference input entirely can also pass it. Where reference inputs are admitted, PR-MS1.0 SHALL specify a positive-direction test in which a reference change effective at or before `t` MUST be reflected in the assembled canonical input and, where semantically relevant, in classification behavior.

**Supersedes:** earlier draft MS-I1.

### MS-P2 --- Determinism

For identical canonical inputs and classifier version, the semantic classification result SHALL be deterministic.

No randomness, wall-clock dependency, broker state, network state, or hidden mutable external state is permitted.

Exact numeric evidence-comparison mechanics are PR-MS1 test-design details. Canonical input identity is defined by PR-MS1.0; MS-P2 becomes executable only after that contract is locked.

**Supersedes:** earlier draft MS-I2.

### MS-P3 — Price-Scale Invariance

**Supersedes:** earlier draft MS-P4. The provenance requirement previously numbered MS-P3 is relocated to §12 (PR-MS1.0 item 12; PR-MS1.1 item 5).

All V1 structure features and classification rules SHALL be invariant under multiplication of all price-valued inputs by the same positive constant `c > 0`, while non-price inputs such as volume remain unchanged.

Test:

`classify(X, as_of) == classify(T_c(X), as_of)`

where `T_c` multiplies every price-valued field by `c > 0` and leaves non-price fields unchanged.

The discrete state and classification-validity result MUST be identical.

Consequences: absolute-price thresholds are forbidden in V1; multiplicative backward-adjustment restatement cannot alter V1 classification solely through constant historical price rescaling; any future rule violating MS-P3 requires adjustment-vintage governance before admission.

MS-P3 does not replace PIT controls for reference data, constituent membership, lifecycle metadata, rolling-window boundaries, or other temporally varying inputs.

## 8. Input Contract

**Identifier disposition:** earlier-draft MS-I3 (security/account scope) is absorbed into MS-I6 below; earlier-draft MS-I4 (no signal semantics) is absorbed into G3. Identifiers MS-I3 and MS-I4 SHALL NOT be reused.

### MS-I5 --- Directional Fail-Safe

For a strategy explicitly requiring Market State at requested `as_of=t`, `MarketState.as_of == requested_as_of` SHALL hold. Stale Market State from an earlier date SHALL NOT substitute for the required classification.

If required Market State is unavailable:

- risk-increasing actions (`entry`, `add`) fail closed;
- risk-reducing actions (`exit`, `reduce`, `stop`) SHALL NOT be blocked by Market State unavailability.

Existing exit/risk-reduction logic remains outside PR-MS1 scope.

MS-I5 is binding at strategy-adoption phase and is not an executable PR-MS1.1 acceptance test.

### MS-I6 --- Explicit Input / I/O Boundary

The classifier SHALL operate on explicit inputs and SHALL NOT own DuckDB, filesystem, network, broker, or Shioaji I/O.

Input assembly owns data access and temporal validation.

Every dated required dependency SHALL be valid for the requested `as_of`. Nearest-prior substitution is forbidden unless an explicitly governed temporal-validity rule makes it semantically correct.

Reference data without a date column SHALL NOT be assumed historically valid merely because it is the latest available value. Lifecycle, constituent, classification, or similar metadata must have an effective-date range or another explicitly governed temporal-validity contract.

The InputDTO SHALL NOT carry account identity, position size, portfolio exposure, risk budget, order status, fill state, execution venue state, or strategy-specific eligibility state.

Security Market State describes the condition of a security, not a holder's position in that security and not membership in a strategy-specific candidate set. Given identical market/reference inputs, classification SHALL therefore be reusable across accounts and strategy consumers.

`features/win_rate_21d/` output is forbidden as a Market State V1 classifier input.

## 9. Classification Coverage

V1 SHALL NOT use a residual catch-all state.

If inputs are operationally valid and history is sufficient but no explicit classification rule matches, the result is semantically `INDETERMINATE`.

Therefore `RANGE`, `NEUTRAL`, `UNKNOWN`, or another state SHALL NOT be implemented as `else: <state>` unless that state has a positive, testable classification rule.

This preserves unmatched/`INDETERMINATE` rate as a taxonomy-coverage diagnostic.

Operational failure, insufficient history, and rule non-match (`INDETERMINATE`) SHALL remain machine-distinguishable.

Merging them into a single unavailable result is forbidden, because insufficient-history warm-up would otherwise contaminate the `INDETERMINATE` rate used here as a taxonomy-coverage diagnostic.

Representation and cause-code precedence are deferred to PR-MS1.0.

## 10. Adjustment / Research Interpretation

Helios uses a multiplicative backward-adjusted price series. MS-P3 is
the V1 protection against classification changes caused solely by later
constant multiplicative rescaling of historical prices.

PR-MS0 therefore does not require a queryable historical
adjusted-price-vintage store.

Research integrity rule:

> Historical classifications recomputed from current data SHALL NOT be
> described as historical production observations unless that
> equivalence is separately established.

If all classifier inputs/rules satisfy MS-P1 and MS-P3, adjustment
restatement alone does not invalidate V1 structural classification.

A future non-scale-invariant rule requires adjustment-vintage governance
before production or historical inference.

## 11. Protected Surfaces

PR-MS1.0 does not authorise changes to `features/win_rate_21d/`,
existing strategies, `portfolio/`, `execution/`, order lifecycle, exit
stack, broker integration, account lifecycle, production Market State
persistence, or production `daily_run` integration.

## 12. PR-MS1 Programme — Authorised Scope After PR-MS0 Lock

### PR-MS1.0 — Domain Contract only

PR-MS1.0 SHALL decide and lock:

1. V1 Market State vocabulary;
2. positive semantic rule for every valid state;
3. minimum structural inputs;
4. canonical InputDTO shape;
5. classifier/result API;
6. unavailable/invalid result representation;
7. classification precedence;
8. whether transition semantics are required;
9. classifier version identity;
10. executable-test specifications for MS-P1, MS-P2, MS-P3, and MS-I6; MS-I5 remains a strategy-adoption contract to be tested at the strategy-adoption phase;
11. single-module versus package form, based on demonstrated cohesion;
12. minimum research-export schema, including mandatory `as_of` and `classifier_version` provenance.

PR-MS1.0 SHALL NOT implement the executable classifier, production persistence, production strategy migration, `daily_run` integration, HMM/ML, probabilistic classification, parameter optimisation, predictive-alpha claims, or portfolio/execution changes.

### PR-MS1.1 — Deterministic Classifier and Research Export

Only after PR-MS1.0 is locked, PR-MS1.1 MAY implement:

1. the minimal assembly layer;
2. the deterministic classifier;
3. executable tests for MS-P1, MS-P2, MS-P3, and MS-I6;
4. research export, preferably Parquet;
5. required research provenance, including at minimum `as_of` and `classifier_version`.

PR-MS1.1 SHALL NOT implement production persistence, strategy migration, or `daily_run` integration.

## 13. Deferred Questions

| ID | Question | Destination |
|---|---|---|
| Q-MS1-01 | Final V1 state vocabulary | PR-MS1.0 |
| Q-MS1-02 | Minimum canonical structure inputs | PR-MS1.0 |
| Q-MS1-03 | Result / unavailable representation | PR-MS1.0 |
| Q-MS1-04 | Rule precedence | PR-MS1.0 |
| Q-MS1-05 | Whether state transitions are required | PR-MS1.0 |
| Q-MS1-06 | Classifier API / InputDTO | PR-MS1.0 |
| Q-MS1-07 | Single module vs package | PR-MS1.0 |
| Q-MS1-08 | Research export schema / mandatory provenance | PR-MS1.0 |
| Q-MS2-01 | Research validation / promotion protocol | Post-PR-MS1.1 |
| Q-MS-PROD-01 | Production persistence | Post-validation |
| Q-MS-PROD-02 | Strategy-specific adoption | Post-validation |

**Constraint on Q-MS1-02 — volume-derived primitives**

If any volume-derived primitive is admitted into the Market State V1 input contract, PR-MS1.0 SHALL determine its corporate-action semantics explicitly.

Such a primitive SHALL either:

1. use adjustment-consistent volume; or
2. explicitly document and test discontinuity across relevant corporate-action dates.

A volume-derived primitive SHALL NOT be admitted merely because the price-side MS-P3 scale-invariance property passes.

If PR-MS1.0 chooses stateful transition semantics, series-origin/cold-start/prior-state initialisation semantics must be defined before implementation, and MS-P2 must be extended to require identical output for identical `(origin, canonical input, classifier_version)`.

## 14. Minimal Continuation Conventions

### GC-1 --- Repository Truth

Repository truth overrides handoff assumptions.

### GC-2 --- Observation over Inference

Do not invent repository identifiers, symbols, schema, test state, SHA,
ADR text, or line anchors.

### GC-3 --- PIT / Leakage Discipline

Future observations, future-confirmed labels, latest-only reference
metadata, or research outcomes SHALL NOT enter historical Market State
input unless temporal validity is established.

### GC-4 --- Semantic Separation

Do not collapse Feature, Market State, Setup, Signal, portfolio
decision, or Order for implementation convenience.

### GC-5 --- Proportional Governance

Governance weight should increase with irreversibility, production
coupling, and capital-at-risk impact. Research-stage reversible details
remain reversible unless correctness requires an earlier lock.

## 15. Closure Review

PR-MS0 may move from `DRAFT — CLOSURE REVIEW` to
`LOCKED — PR-MS1.0 AUTHORISED` when reviewer confirms:

1.  F-MS0-1..8 contain no invented repository facts or symbol identities;
2.  G1/G2/G3 match observed architecture;
3.  MS-P1 tests the composed PIT boundary;
4.  MS-P3 matches directly observed Helios adjustment semantics: corporate-action price adjustment is multiplicative, cash-dividend `adjustment_factor` is `after_price / before_price`, adjusted OHLC columns are present in `daily_price_adj`, and the current volume policy retains raw volume;
5.  MS-I6 prevents temporally invalid reference data;
6.  no residual catch-all state or cause-merging path can hide taxonomy coverage failure; operational failure, insufficient history, and rule non-match remain machine-distinguishable;
7.  PR-MS1.0 is contract-only, PR-MS1.1 owns classifier/tests/research export, and neither silently authorises production integration;
8.  current repository HEAD and clean-tree state are re-observed before
    commit.

No canonical-hash ceremony is required. The lock commit SHA is the
immutable content-addressed anchor.

A LOCKED PR-MS0 record SHALL NOT be edited in place. Any semantic amendment requires a later superseding governance record.

## 16. Decision Summary

| Decision | v0.3.4 disposition |
|---|---|
| G1 | Market State owned in `features`; not strategies/portfolio/execution |
| Physical form | Deferred; default single module |
| G2 | Minimal extraction |
| G3 | `Feature ≠ MarketState ≠ Setup ≠ Signal ≠ Order` |
| Existing strategies | Market State optional |
| Broad Market Regime | Distinct context; not required classifier input |
| PIT | Composed assembly + classifier boundary |
| Adjustment | Positive price-scale invariance required |
| Reference metadata | Explicit temporal validity required |
| Stale required state | Cannot authorise entry/add |
| Exit/reduce/stop | Cannot be blocked by unavailable Market State |
| Residual catch-all | Forbidden |
| `win_rate_21d` | Forbidden as V1 classifier input |
| PR-MS1.0 | Domain Contract only |
| PR-MS1.1 | Deterministic classifier + tests + research export |
| Production persistence/integration | Deferred |
| Hash/backfill ceremony | Not required for PR-MS0 |

## 17. Next Phase

After PR-MS0 LOCK:

`PR-MS1.0 — Security Market State Domain Contract`

PR-MS1.0 SHALL begin with repository entry verification and SHALL treat
this record as a semantic boundary, not as a predetermined classifier
implementation.

First question:

> What is the smallest explicit input and result contract capable of
> representing a deterministic, PIT-safe, price-scale-invariant Security
> Market State without leaking strategy intent into the feature domain?
