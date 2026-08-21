# PR-MS1.0 — Q-MS1-07 Physical Form Disposition Draft
Canonical Path: docs/research/pr_ms1_0_q_ms1_07_physical_form_disposition.md

Version: v0.1.1
Status: DRAFT — ADVERSARIAL REVIEW REQUIRED
Scope: Physical module/package form only. This disposition neither implements Market State nor changes its domain contract, assembly boundary, persistence, strategy adoption, or import graph.
Canonical Contract Target: `docs/research/pr_ms1_0_security_market_state_domain_contract.md` v0.2.3 (controlled integration draft)
Upstream Semantic Boundary: `docs/research/pr_ms0_repository_semantic_audit_decision_record.md` (`45f8fea`)

## 0. Decision Labels

- **VERIFIED REPOSITORY FINDING** — current-source evidence observed at entry.
- **PROPOSED DECISION** — normative candidate requiring review and lock.
- **DEFERRED** — intentionally excluded from this decision.

## 1. Entry Evidence

**VERIFIED REPOSITORY FINDING:** `docs/decision_records/ADR-006-cohesion-over-abstraction.md` is Accepted. Its v0.1 decision is that each major concern lives in one concrete, non-abstract file; refactoring toward abstraction occurs only when complexity demands it.

**VERIFIED REPOSITORY FINDING:** PR-MS0 §4 records the Market State physical form as deliberately deferred to PR-MS1.0 and establishes the default: start with a single module until at least two internally cohesive responsibilities are demonstrated.

**VERIFIED REPOSITORY FINDING:** The observed `features/` surface contains concrete modules such as `technical.py`, `bullish_features.py`, `bearish_regime.py`, and `regime.py`; no existing `market_state.py` module or `market_state/` package exists. No repository evidence demonstrates multiple independently cohesive Market State implementation responsibilities.

## 2. Disposition

**PROPOSED DECISION:** PR-MS1.1 SHALL introduce Market State, if implementation is authorised after contract lock, as one concrete module:

```text
features/market_state.py
```

The module owns the pure classifier implementation surface established by the canonical contract: its immutable configuration, DTO/result types, `MarketStateContractViolation`, deterministic indicator calculation, structural validation, scalar and batch classification, and declared rule evaluation/precedence. `MarketStateContractViolation` is defined and raised at this classifier boundary.

**PROPOSED DECISION — domain vocabulary location:** All Market State enum types are also defined in `features/market_state.py` as one cohesive, dependency-light domain vocabulary: `MarketState`, `ClassificationStatus`, `ClassifierReasonCode`, `Availability`, `HistoryDiagnosticCode`, and `OperationalDiagnosticCode`. Definition location does not alter producing/assignment ownership: only the classifier produces `ClassificationStatus`/`ClassifierReasonCode`/`MarketState`; only assembly/composed pipeline assigns `Availability` and assembly diagnostic values. Assembly may import this vocabulary module, but the pure classifier SHALL NOT import assembly/export code or perform I/O.

This co-locates one domain's stable vocabulary without creating a separate shared-types module, package, or reverse dependency. The module does not own assembly, export composition, persistence, strategy adoption, execution, or account state.

`features/market_state/` package creation, abstract rule-class/plugin systems, and speculative submodules are rejected for V1. The existence of several functions, enum types, or rule templates inside one cohesive pure-classifier module is not by itself evidence for a package split.

## 3. Future Split Trigger

**PROPOSED DECISION:** A future package proposal may be considered only when repository evidence demonstrates at least two internally cohesive Market State responsibilities with distinct public contracts, independent test boundaries, and a concrete reason they cannot remain readable/refactorable in the single module.

The proposal SHALL:

1. re-observe ADR-006 and cite the then-current implementation evidence;
2. identify the exact responsibilities, import boundaries, and test ownership to be split;
3. show why a single concrete module no longer meets cohesion/readability requirements;
4. provide a diff-first migration with no hidden I/O or semantic change; and
5. be governed by a superseding ADR/disposition before package creation.

File length, hypothetical future rules, or desire for generic extensibility are insufficient triggers.

## 4. Closure Criteria

Q-MS1-07 may close only when the canonical contract states:

1. `features/market_state.py` is the V1 physical form;
2. its pure classifier-only implementation boundary, shared domain-vocabulary location, and one-way assembly import direction;
3. package/abstraction non-authorisation in V1; and
4. `MarketStateContractViolation` is defined/raised at the classifier boundary; and
5. the evidence-based future split trigger preserving ADR-006 and PR-MS0 default.

## 5. Session Handoff

### Session Summary

Current ADR-006 and PR-MS0 evidence support a single concrete classifier module. There is no present implementation complexity that justifies a package.

### Decision Record

- V1 physical form: `features/market_state.py`.
- All Market State enums form one vocabulary in that module; assignment ownership remains layer-specific.
- `MarketStateContractViolation` is defined and raised in that module.
- No `features/market_state/` package or plugin architecture.
- Future split requires observed responsibilities and a new governed diff.

### Open Questions

- Q-MS1-08 export/provenance and C-2 remediation remain independent of this physical-form decision.

### Evidence

The ADR-006 and current `features/` inventory must be re-observed at lock HEAD.

### Next Actions

Obtain adversarial review. If accepted, integrate the physical-form clause into the canonical contract without creating the module; actual implementation remains PR-MS1.1 work after contract lock.
