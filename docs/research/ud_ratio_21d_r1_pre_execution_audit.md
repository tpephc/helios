# R1 Pre-Execution Audit Memo (ENV-NOTE-002)

**Status:** IN PROGRESS
**Document Type:** Governance Evidence Document
**Trigger Date:** 2026-06-28
**Trigger Event:** R1 §12 Step 1 Pre-flight Discovery
**Repository HEAD at Trigger:** `13ed404`
**Lock State at Trigger:** R1 prereg LOCKED
**Lifecycle:** IN PROGRESS → CLOSED upon Gate A3 completion
**Related Notes:** ENV-NOTE-001 (CLOSED)

---

# 1. Scope

## 1.1 Purpose

This document records the governance evidence collected during the pre-execution verification of R1 immediately before the planned execution of prereg §12 Step 1.

The objective is to:

* preserve the evidence chain leading to execution suspension;
* freeze governance terminology and finding identifiers before technical remediation;
* establish the rationale for introducing Gate 0, Gate A1, Gate A2 and Gate A3;
* provide an immutable evidence anchor for subsequent specification, implementation and prereg amendment work.

## 1.2 This Document IS

* a governance evidence document;
* an audit trail;
* a decision rationale anchor;
* an execution-readiness assessment.

## 1.3 This Document IS NOT

This document is not:

* a feature specification;
* an implementation guide;
* a research report;
* a producer contract;
* a mathematical definition of any feature;
* a replacement for the preregistration document.

Technical definitions are intentionally deferred to the corresponding feature specification documents.

## 1.4 Governance Invariant

This memo freezes governance understanding only.

It does not freeze technical design.

Technical design remains the responsibility of subsequent feature specifications and implementation reviews. This memo may be referenced by such documents, but it does not substitute for them.

---

# 2. Trigger

## 2.1 Background

Following completion of the R1-U7B audit pipeline and LOCK of the R1 preregistration, execution entered the environment verification stage preceding prereg §12 Step 1.

Environment verification confirmed repository integrity and prereg lock status.

Subsequent source discovery identified unresolved questions regarding the production substrate required by the R1 feature contract.

## 2.2 Audit Trigger

The audit was initiated because the canonical execution inputs required by prereg §12 raised unresolved questions during the initial repository inspection.

These questions concerned whether the production substrate for the R1 feature contract was demonstrable at the time of execution preparation. The initial inspection was not exhaustive; subsequent discovery rounds either resolved or formalized these questions on a per-feature basis, as documented in §4.

The objective of the audit therefore shifted from execution to governance verification.

## 2.3 Scope Boundary

This audit evaluates execution readiness only.

It does not re-open:

* the R1-U7B historical anchor audit;
* ZERO-ANCHOR disclosure;
* statistical methodology;
* prereg decision thresholds.

---

# 3. Discovery Method

## 3.1 Method

Evidence was gathered through structured repository inspection rather than execution of statistical analysis.

The discovery process consisted of multiple corroborating rounds including:

* repository state verification;
* prereg inspection;
* feature discovery;
* schema discovery;
* implementation discovery;
* historical Git inspection;
* specification lineage review.

## 3.2 Evidence Sources

Evidence originated from one or more of the following:

* Git history;
* repository file structure;
* preregistration document;
* feature specifications;
* implementation files;
* DuckDB schema inspection;
* command outputs recorded during the session.

No statistical inference was performed during this audit.

No Spearman correlation was computed.

No prereg execution step beyond environment verification was executed.

## 3.3 Methodological Principle

Every governance conclusion recorded in this document shall satisfy the following chain:

Evidence → Interpretation → Classification → Consequence

Evidence is treated as immutable.

Interpretation may change if future evidence emerges. Retracted interpretations are preserved explicitly in §6 rather than discarded, so that future sessions retain visibility of corrected reasoning.

Classification and consequence are derived from interpretation rather than directly from evidence.

## 3.4 Evidence References

To preserve readability of the Findings section, evidence anchors are collected here rather than embedded inline.

| Reference | Anchor                                                                    |
|-----------|---------------------------------------------------------------------------|
| ER-1      | `features/ud_ratio.py` (production module)                                |
| ER-2      | `tests/features/test_ud_ratio_schema.py`                                  |
| ER-3      | `tests/features/test_ud_ratio_pit_invariants.py`                          |
| ER-4      | `tests/features/test_ud_ratio_anchored.py`                                |
| ER-5      | Commit `336f3cf` — "Track C Step 1 closeout: ud_ratio_21d implementation complete" |
| ER-6      | `docs/features/ud_ratio_21d_spec.md` v0.1.4 (SPEC_LOCKED)                 |
| ER-7      | `docs/research/ud_ratio_21d_r1_prereg.md` §1, §3, §5, §6                   |
| ER-8      | `docs/research/ud_ratio_21d_r1_prereg.md` LOCKED at commit `13ed404`      |
| ER-9      | `docs/features/ud_ratio_21d_spec.md` §10 R1                               |
| ER-10     | `research/track_c_step1_closeout.md` (R1 comparator references)           |
| ER-11     | `main.bullish_features.beta_adj_rs_60d` (DuckDB column)                   |
| ER-12     | `scripts/run_phase4_analysis.py` (RANK_COLS_MAP rs_60d → beta_adj_rs_60d) |
| ER-13     | `scripts/phase6_evaluate_candidate.py` (rs_60d_rank semantics)            |
| ER-14     | `main.daily_features.roc_20` (DuckDB column)                              |
| ER-15     | `docs/research/ud_ratio_21d_r1_prereg.md` §3 R1-U1 (Universe Contract)    |
| ER-16     | Git history searched across all branches, reflog, and dangling objects for `win_rate` references. No implementation evidence identified during repository discovery. |
| ER-17     | Repository directory scan for `*win_rate*` files. No implementation evidence identified during repository discovery. |
| ER-18     | DuckDB `information_schema.columns` scan for `win` substring. No implementation evidence identified during repository discovery. |

Evidence references are stable identifiers. Findings cite them rather than reproducing path-level detail in narrative.

---

# 4. Findings

## 4.1 F1 — ud_ratio_21d Implementation

### Evidence

Repository inspection confirmed:

* a production implementation module exists [ER-1];
* associated tests exist for schema, PIT invariants, and anchored database fixtures [ER-2, ER-3, ER-4];
* a prior implementation closeout commit is present on `main` [ER-5];
* the corresponding specification is LOCKED at v0.1.4 [ER-6].

### Interpretation

An earlier framing in this session suggested that the `ud_ratio_21d` implementation was missing. That framing was based on an incomplete repository search and is contradicted by the evidence above. The implementation substrate required for this feature exists at the current repository HEAD.

### Classification

**COMPLETE (no gap)**

### Consequence

No remediation work is required for `ud_ratio_21d`.

This finding does not block Gate 0, Gate A1, Gate A2, or Gate A3.

---

## 4.2 F2 — win_rate_21d

### Evidence

Repository inspection established that:

* the feature is referenced in the R1 design lineage at multiple points [ER-7, ER-9, ER-10];
* the feature appears in the prereg feature set with explicit role in the R1 statistic contract [ER-7];
* no production implementation was identified [ER-16, ER-17];
* no producer was identified [ER-17];
* no dedicated specification was identified [ER-17];
* no DuckDB column corresponding to this feature was identified [ER-18];
* historical Git inspection (including all branches, reflog, and dangling objects) found no commit message, diff, or deleted file evidencing prior or in-progress implementation [ER-16].

### Interpretation

The feature exists as a designed component of the R1 feature contract at the specification, closeout, and preregistration layers, but lacks a verified production substrate.

The evidence does not support a "deprecated artifact" or "drafting error" interpretation:

* the design predates the prereg (specification v0.1.0 dated 2026-06-22; prereg draft dated 2026-06-23) [ER-9];
* the specification at LOCK state still references this feature as an R1 comparator [ER-6, ER-9];
* the closeout document explicitly enumerates this feature as part of the R1 statistic set [ER-10].

The current evidence is most consistent with an implementation sequencing problem: the feature was designed before the prereg LOCK occurred, but the corresponding implementation was not delivered before that LOCK.

### Classification

**Implementation Gap**

### Consequence

This finding motivates the introduction of Gate 0 as the documentation freeze preceding remediation, since the audit conclusion itself requires immutable governance recording before technical work begins.

Gate A1 (specification) and Gate A2 (implementation) are subsequently required before R1 execution may proceed.

This finding is the primary execution blocker identified during the audit.

---

## 4.3 F3 — RS_60d Identity

### Evidence

Repository discovery identified multiple references associated with the `RS_60d` naming:

* the prereg uses the name `RS_60d` in §1, §5, and §6 [ER-7];
* the production codebase uses `beta_adj_rs_60d` as the corresponding DuckDB column [ER-11];
* internal Helios scripts reference a `rs_60d` → `beta_adj_rs_60d` mapping in their rank construction logic [ER-12, ER-13];
* no statement formalizing this mapping was identified within the prereg or the `ud_ratio_21d` specification.

### Interpretation

The feature identity is insufficiently explicit for governance purposes.

The evidence does not currently demonstrate that the prereg name and the production column refer to semantically different quantities. Production scripts treat them as the same quantity under different labels. However, the absence of an explicit identity statement at the prereg layer means the identity must be formalized before execution.

This finding is one of incomplete identity clarification, not of demonstrated semantic disagreement.

### Classification

**Identity Ambiguity**

### Consequence

Identity clarification is required during Gate A3 through the prereg amendment process, under the A3 Amendment Scope LOCK defined in §7.4.

No statistical contract changes are implied or permitted by this finding.

---

## 4.4 F4 — ROC_20d Identity

### Evidence

Repository inspection identified:

* the prereg uses the name `ROC_20d` [ER-7];
* an existing production column `roc_20` is present in `main.daily_features` [ER-14];
* prereg terminology differs from implementation column naming by capitalization and suffix.

### Interpretation

The discrepancy is limited to identity mapping. No evidence currently indicates semantic disagreement between the prereg name and the production column.

### Classification

**Identity Ambiguity (Low Severity)**

### Consequence

The mapping shall be documented during the Gate A3 identity clarification amendment alongside F3.

No implementation work is currently indicated for this finding.

---

## 4.5 F5 — R8 Panel Materialization

### Evidence

Prereg §3 R1-U1 specifies the universe contract as "R8 treatment_1 signal-date panel only" [ER-15].

Prereg §3 does not include a requirement that the panel be pre-materialized as a single artifact. No statement requiring an existing materialized panel was identified within the prereg [ER-7].

### Interpretation

Panel reconstruction at execution time remains compatible with the prereg as long as reconstruction preserves the prereg universe and observation contracts. The construction of the panel through join of the R8 universe with feature columns is permissible under the current prereg language.

### Classification

**No Gap**

### Consequence

Panel reconstruction may be formalized during Gate A3 without constituting a substantive prereg modification.

The reconstruction recipe itself becomes part of the Gate A3 amendment, but it formalizes prior implicit understanding rather than introducing new contract semantics.

---

# 5. Non-Findings

This audit does **not** conclude that:

1. the R1 design is invalid;
2. the R1 preregistration is procedurally defective;
3. the R1-U7B audit must be repeated;
4. ZERO-ANCHOR disclosure is affected;
5. `win_rate_21d` should be removed from the R1 design;
6. the `RS_60d` production mapping is semantically incorrect;
7. any statistical threshold requires modification;
8. any prereg execution result is invalid.

---

# 6. Governance Reasoning Chain

## 6.1 Initial Interpretation

Early discovery in this session suggested that the prereg LOCK might have occurred before its execution prerequisites were satisfied. This framing led to the use of the term **"soft mis-lock"** as a tentative characterization of the prereg state.

This framing is **retracted**.

The retraction is recorded explicitly because the audit methodology (§3.3) preserves retracted interpretations rather than discarding them. Future sessions reading this memo should see why this framing was abandoned, not merely see the final answer.

The retraction is justified by D0 evidence (§4.2, §4.3, §4.5): the prereg LOCK procedure was internally consistent, the panel materialization issue dissolved upon reading §3 R1-U1, and the `win_rate_21d` issue resolved to an implementation sequencing problem rather than a prereg defect. None of these findings support a "mis-lock" interpretation.

The retained record of the retracted interpretation serves as an audit artifact rather than an active governance position.

## 6.2 Evidence Expansion

Subsequent discovery demonstrated that:

* the `ud_ratio_21d` implementation already existed (F1);
* panel materialization itself was prereg-compatible (F5);
* the primary unresolved issue concerned `win_rate_21d` (F2);
* feature identity clarification remained incomplete for selected comparators (F3, F4).

These findings materially altered the governance interpretation away from the retracted framing in §6.1.

## 6.3 Final Interpretation

The evidence supports the following governance conclusion:

The prereg LOCK procedure remained internally consistent.

The repository state indicates an implementation sequencing gap between the intended feature contract and the available production substrate.

This is not classified as a prereg procedural defect.

This is not classified as a governance incident.

The appropriate remediation path is to complete the missing implementation and identity clarification before initiating prereg §12 execution.

## 6.4 Governance Outcome

The final governance position adopted by this audit is:

* execution suspended before prereg §12 Step 1;
* historical R1-U7B audit remains valid;
* ZERO-ANCHOR disclosure remains valid;
* Path A remediation adopted;
* Gate 0 introduced as a documentation freeze preceding technical remediation.

---

# 7. Remediation Plan

This section defines the four-gate remediation path adopted by this audit. Gates are numbered sequentially. Each gate has explicit inputs, deliverables, and exit criteria. Gates may not begin until prior gates have closed.

## 7.1 Gate 0 — Documentation Freeze

### Purpose

Freeze the governance understanding produced by this audit before any technical remediation work begins. Gate 0 ensures that subsequent specification, implementation, and amendment work proceeds against an immutable governance anchor.

### Inputs

* All five Findings (F1–F5) in §4;
* All Non-Findings in §5;
* The Governance Reasoning Chain in §6;
* Locked Decisions D-001 through D-N in §9;
* ENV-NOTE-001 (closed) as historical context for environment verification methodology.

### Deliverables

* This memo, committed to the repository at `docs/research/ud_ratio_21d_r1_pre_execution_audit.md` with status `IN PROGRESS`;
* Status block, scope, findings, non-findings, reasoning chain, remediation plan, decision dependencies, decision log, open items, known unknowns, and amendment log all populated and internally consistent.

### Exit Criteria

Gate 0 closes if and only if all of the following are satisfied:

| ID     | Criterion                                                            |
|--------|----------------------------------------------------------------------|
| G0-C1  | Findings F1–F5 frozen (IDs assigned, scope locked, no merge/split)   |
| G0-C2  | Terminology frozen (governance labels enumerated in §6.3 final form) |
| G0-C3  | Classifications frozen per §4                                        |
| G0-C4  | Non-findings frozen per §5                                           |
| G0-C5  | Decision dependency graph frozen per §8                              |
| G0-C6  | Remediation path frozen (Path A, four gates)                         |
| G0-C7  | Open items enumerated per §10                                        |
| G0-C8  | Known unknowns enumerated per §11                                    |
| G0-C9  | Decision Log §9 populated with all session decisions                 |
| G0-C10 | Memo reviewed by governance reviewer                                 |
| G0-C11 | Memo committed to repository; repository history serves as the canonical record of the initial commit; status remains IN PROGRESS |

Gate A1 may not begin until G0-C1 through G0-C11 are all satisfied.

## 7.2 Gate A1 — `win_rate_21d` Specification Lock

### Purpose

Produce and lock a specification for `win_rate_21d` sufficient to support implementation under deterministic and reproducible conditions. The specification is the design contract that Gate A2 implements against.

### Inputs

* Gate 0 closed;
* F2 (implementation gap) and F3 (identity ambiguity) as primary motivating findings;
* D-001 (`win_rate_21d` Definition E, recorded in §9);
* The existing `ud_ratio_21d` specification at v0.1.4 as a structural template [ER-6];
* The R8 panel universe contract as documented in prereg §3 [ER-15].

### Deliverables

* `docs/features/win_rate_21d_spec.md` at version v0.1.0;
* Specification covering ten sections (Scope, Identity, Mathematical Definition, PIT Contract, Producer Contract, Output Schema, Acceptance Criteria, Test Strategy, Governance, Future Extensions);
* Specification status set to LOCKED upon Gate A1 closure;
* Specification committed to the repository.

### Exit Criteria

| ID      | Criterion                                                                            |
|---------|--------------------------------------------------------------------------------------|
| A1-C1   | Specification covers the ten sections enumerated in Deliverables                     |
| A1-C2   | All design landmines surfaced during this session (recorded as D-001 components) have explicit resolution in the specification |
| A1-C3   | Deterministic reproducibility contract for any cross-sectional aggregate producer is explicit |
| A1-C4   | PIT contract enumerates required test identifiers, even where test bodies defer to Gate A2 |
| A1-C5   | Acceptance criteria separate Gate A1 (specification) from Gate A2 (implementation)   |
| A1-C6   | No numerical thresholds are locked beyond minimum-observation and window-length constants |
| A1-C7   | Producer dependency surface is explicit                                              |
| A1-C8   | Specification reviewed and approved                                                  |
| A1-C9   | Specification committed to the repository; repository history serves as the canonical record of the lock commit; status set to LOCKED |

### Closure

Gate A1 CLOSED at commit `1cf8365` (2026-06-30).
All exit criteria A1-C1 through A1-C9 satisfied; specification
`docs/features/win_rate_21d_spec.md` v0.1.0 LOCKED at the same commit.

Gate A2 may not begin until A1-C1 through A1-C9 are all satisfied.

## 7.3 Gate A2 — Implementation and Producer Substrate

### Purpose

Deliver the production implementation of `win_rate_21d` and any required upstream producer, with point-in-time invariant tests demonstrably green. Gate A2 closes the implementation gap identified in F2.

### Inputs

* Gate A1 closed;
* The `win_rate_21d` specification at v0.1.0 LOCKED;
* The existing `ud_ratio_21d` implementation pattern as an architectural reference for module structure and test discipline [ER-1, ER-2, ER-3, ER-4].

### Deliverables

* The `win_rate_21d` feature module implementing the specification;
* Any required upstream producer module or table identified by the specification;
* Point-in-time invariant tests covering the test identifiers enumerated in the specification;
* All tests passing on the current repository HEAD.

### Exit Criteria

| ID      | Criterion                                                                          |
|---------|------------------------------------------------------------------------------------|
| A2-C1   | Feature module exists at the path declared in the specification                    |
| A2-C2   | Required producer substrate exists where the specification mandates one            |
| A2-C3   | Test suite for `win_rate_21d` is green on the current HEAD                         |
| A2-C4   | Test suite covers every test identifier enumerated in the specification            |
| A2-C5   | Implementation does not introduce new forbidden imports or break repository-wide invariants |
| A2-C6   | Implementation committed to the repository. The repository history provides the implementation commit reference required by Gate A3 for identity clarification. No commit hash is recorded within this memo. |

Gate A3 may not begin until A2-C1 through A2-C6 are all satisfied.

## 7.4 Gate A3 — Identity Clarification Amendment and R1 Execution Kickoff

### Purpose

Issue a prereg amendment that clarifies feature identity for `RS_60d`, `ROC_20d`, and `win_rate_21d` against their production substrates, and formalize the R1 panel reconstruction recipe. Upon amendment commit, R1 execution per prereg §12 Step 1 may begin.

### Inputs

* Gate A2 closed;
* The `win_rate_21d` specification (v0.1.0 LOCKED) and implementation commit hash from Gate A2;
* The R1 preregistration LOCKED at commit `13ed404` [ER-8];
* F3 and F4 identity ambiguity findings (§4.3, §4.4);
* F5 panel reconstruction permissibility finding (§4.5);
* The R1-U7B audit document as a historical governance dependency (referenced for confirming ZERO-ANCHOR disclosure remains intact under this amendment).

### Deliverables

* Prereg amendment entry R1-amend-001 appended to the prereg amendment log;
* Amendment commit on the repository with a commit message explicitly tagged as identity clarification only;
* R1 panel reconstruction recipe documented as part of the amendment;
* R1 execution per prereg §12 Step 1 initiated.

### A3 Amendment Scope LOCK

The A3 amendment is constrained to identity clarification and panel reconstruction documentation only. The following are explicitly allowed and explicitly forbidden:

**Allowed in A3 amendment:**

* Statement of identity: `RS_60d` is the prereg name for the column `beta_adj_rs_60d` in `main.bullish_features`;
* Statement of identity: `ROC_20d` is the prereg name for the column `roc_20` in `main.daily_features`;
* Statement of identity: `win_rate_21d` is the feature produced by the module declared in the specification, at the implementation commit hash from Gate A2;
* Panel reconstruction recipe describing how to assemble the R1 panel by joining the R8 `treatment_1` universe with the four feature columns at signal dates;
* Cross-reference to this memo (ENV-NOTE-002).

**Forbidden in A3 amendment:**

* Any change to the R1-U4 statistic contract;
* Any change to the R1-U4a cross-section adequacy constant;
* Any change to the R1-U5 regime conditioning contract or its constants;
* Any change to the R1-U6 escalation threshold sequencing rule;
* Any change to the R1-U7A, R1-U7B, or R1-U7C contracts;
* Any change to the ZERO-ANCHOR disclosure path established by the R1-U7B audit;
* Addition or removal of any feature comparator;
* Any change to the universe definition in §3 R1-U1;
* Any change to the observation date contract in §4 R1-U2;
* Any change to the missing-value policy in §5 R1-U3;
* Any threshold value change anywhere in the prereg.

### Procedural Constraints

* The amendment does not change the prereg `Status: LOCKED` block. The amendment is appended to the prereg `Amendment Log` section as a new entry with identifier `R1-amend-001`.
* The amendment commit message must explicitly contain the phrase "identity clarification only, no substantive R1 contract change".
* If during Gate A2 or Gate A3 any evidence emerges that necessitates a substantive change to R1 contract semantics, the amendment plan is withdrawn and the situation is escalated to a new prereg version under the full LOCK procedure. Substantive changes are not absorbed into A3.

### Exit Criteria

| ID      | Criterion                                                                           |
|---------|-------------------------------------------------------------------------------------|
| A3-C1   | Amendment R1-amend-001 appended to prereg amendment log                             |
| A3-C2   | Amendment scope strictly within the allowed list above                              |
| A3-C3   | Amendment commit message explicitly tagged as identity clarification only           |
| A3-C4   | Panel reconstruction recipe documented and reviewable                               |
| A3-C5   | R1-U7B audit ZERO-ANCHOR disclosure confirmed unaffected by the amendment           |
| A3-C6   | Memo lifecycle transitioned from IN PROGRESS to CLOSED through an append-only amendment entry in §12, with the transition recorded in repository history |
| A3-C7   | R1 execution per prereg §12 Step 1 initiated                                        |

Upon A3-C7, this memo's lifecycle transitions to CLOSED.

---

# 8. Decision Dependencies

This section records the dependency graph between gates, findings, and decisions. The graph is directed and acyclic. Finding identifiers and Decision identifiers occupy separate namespaces per Adjustment 7 in §9.

## 8.1 Gate-Level Dependencies

```text
Gate 0
    Prerequisites:  (none)

Gate A1
    Prerequisites:  Gate 0 closed (G0-C1 through G0-C11)

Gate A2
    Prerequisites:  Gate A1 closed (A1-C1 through A1-C9)

Gate A3
    Prerequisites:  Gate A2 closed (A2-C1 through A2-C6)
```

The chain is strictly linear. No gate has parallel predecessors. No gate has cyclic dependencies.

## 8.2 Finding-to-Gate Mapping

```text
Gate 0
    Findings addressed:    F1, F2, F3, F4, F5
    (Gate 0 freezes the governance position on all findings;
     none are resolved at Gate 0, but all are anchored.)

Gate A1
    Findings addressed:    F2 (implementation gap, specification phase),
                            F3 (identity ambiguity, deferred to Gate A3
                                but referenced in spec lineage)
    Findings not addressed: F1 (already COMPLETE),
                             F4 (deferred to Gate A3),
                             F5 (deferred to Gate A3)

Gate A2
    Findings addressed:    F2 (implementation gap, implementation phase)
    Findings not addressed: F1, F3, F4, F5

Gate A3
    Findings addressed:    F2 (identity formalization for the
                                implemented feature),
                            F3 (RS_60d identity formalization),
                            F4 (ROC_20d identity formalization),
                            F5 (panel reconstruction formalization)
    Findings not addressed: F1 (already COMPLETE)
```

F1 reaches `COMPLETE` status outside the remediation chain because no gap was identified.

## 8.3 Decision-to-Gate Mapping

```text
Gate 0
    Decisions:  D-001, D-002, D-003, D-004, D-005, D-006, D-007,
                D-008, D-009, D-010, D-011
    (All session-locked decisions are recorded at Gate 0; they
     constrain subsequent gates but are not produced by them.)

Gate A1
    Decisions consumed:    D-001, D-002, D-003, D-008, D-009
    Decisions produced:    (none at the memo level; the
                            specification itself produces design
                            decisions internal to the specification)

Gate A2
    Decisions consumed:    D-001 (Definition E), D-002 (gate sequencing)
    Decisions produced:    (none at the memo level)

Gate A3
    Decisions consumed:    D-004 (A3 Amendment Scope LOCK),
                            D-005 (panel reconstruction permissibility),
                            D-007 (memo path)
    Decisions produced:    (none at the memo level)
```

## 8.4 Historical Governance Dependencies

The following are not findings or decisions but are governance artifacts on which this remediation plan implicitly relies:

* **R1 preregistration LOCKED at commit `13ed404`** — provides the contract that Gate A3 amends;
* **R1-U7B audit document** at `docs/research/ud_ratio_21d_r1_u7b_audit.md` — establishes the ZERO-ANCHOR disclosure path that Gate A3 must preserve;
* **`ud_ratio_21d` specification at v0.1.4 LOCKED** — provides the structural template for Gate A1. This dependency is architectural, not semantic: the specification is referenced as a structural template for section organization and contract discipline, not as a source of semantic equivalence between `ud_ratio_21d` and `win_rate_21d`.

These dependencies are observed, not amended, by this remediation plan.

## 8.5 Acyclicity Statement

The dependency graph above is verified acyclic by inspection:

* Gates form a strict linear chain (0 → A1 → A2 → A3);
* Findings are inputs to gates; gates do not retroactively modify findings;
* Decisions are inputs to gates; gates do not retroactively modify decisions;
* Historical governance dependencies are observed only, not modified.

No back-edges exist in the graph.

---

# 9. Locked Decisions

This section enumerates decisions reached during the session that produced this memo. Each decision is identified by a stable identifier in the `D-NNN` namespace, distinct from the Finding `F1`–`F5` namespace and the Amendment `AM-NNN` namespace. Decisions in this section are immutable after Gate 0 closure; subsequent supersession is recorded in §12 Amendment Log, not by editing this section.

Decision identifiers are intentionally non-sequential with respect to Findings and Amendments, and Decision identifiers themselves are stable: if a future amendment supersedes a decision, the superseded decision retains its original identifier and the supersession is recorded in §12 Amendment Log. Identifier stability takes precedence over compact numbering.

| ID    | Decision                                                                      | Rationale                                                                                                   | Locked at        |
|-------|-------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------|------------------|
| D-001 | Adopt Definition E as the canonical design direction for `win_rate_21d`: a relative-outperformance frequency feature, as opposed to alternatives based on absolute return sign (rejected as too close to `ud_ratio_21d`), forward returns (rejected for PIT violation), or scalar benchmark comparison (rejected as primarily a beta proxy). Technical semantics are defined by the corresponding specification at Gate A1. | Q4 critique rejected alternative definitions on grounds of self-correlation, PIT violation, or insufficient incremental information; Definition E preserves R1 falsification power | Session, pre-Gate 0 |
| D-002 | Adopt Path A as remediation, with four gates: Gate 0 (documentation freeze), Gate A1 (specification lock), Gate A2 (implementation), Gate A3 (identity clarification amendment plus R1 execution kickoff) | Q5 + Gate 0 reviewer input; sequentially separates governance work, design work, implementation work, and amendment work | Session, pre-Gate 0 |
| D-003 | Adopt audit-memo-first sequencing: this memo is drafted and committed before the `win_rate_21d` specification is drafted | Q7; the specification will reference this memo as rationale anchor, requiring the memo to exist first | Session, pre-Gate 0 |
| D-004 | Adopt A3 Amendment Scope LOCK as defined in §7.4: amendment is restricted to identity clarification and panel reconstruction documentation; substantive R1 contract changes are forbidden and trigger withdrawal of the amendment plan | Adjustment 2; prevents amendment from absorbing scope creep and preserves R1-U7B audit validity | Session, pre-Gate 0 |
| D-005 | Panel reconstruction at R1 execution time is compatible with prereg §3 R1-U1 and does not constitute a substantive prereg modification when documented as part of A3 | F5 interpretation; prereg does not require pre-materialized panel | Session, pre-Gate 0 |
| D-006 | Adopt Finding template v2: every finding follows Evidence → Interpretation → Classification → Consequence, with classification drawn from a closed set | Adjustment 4; enforces evidence discipline and isolates immutable evidence from mutable interpretation | Session, pre-Gate 0 |
| D-007 | Adopt `docs/research/ud_ratio_21d_r1_pre_execution_audit.md` as the memo path | Q6 session decision; co-locates governance audit with prereg and R1-U7B audit | Session, pre-Gate 0 |
| D-008 | Adopt `win_rate_21d` specification version v0.1.0 with ten sections at approximately seventy to eighty percent completeness; remaining sections deferred to v0.1.1 post-implementation | Q8; avoids placeholder churn and aligns with deterministic-after-evidence Helios practice | Session, pre-Gate 0 |
| D-009 | Adopt the deterministic reproducibility contract requirement for any cross-sectional aggregate producer required by `win_rate_21d` | Adjustment 1; cross-sectional aggregation introduces an additional reduction step beyond row-level computation and requires explicit determinism guarantees in the specification | Session, pre-Gate 0 |
| D-010 | Adopt §9 Decision Log and §12 Amendment Log as separate sections with distinct schemas: Decision Log is immutable; Amendment Log records post-commit changes | Adjustment 5; prevents historical decisions and lifecycle changes from overwriting each other | Session, pre-Gate 0 |
| D-011 | Adopt Finding-Decision-Amendment namespace separation in §8 Decision Dependencies: gates have separate Inputs for Findings and Decisions | Adjustment 7; reclassification of a finding does not implicitly ripple into design decisions | Session, pre-Gate 0 |

---

# 10. Open Items (Gate A1 Only)

This section enumerates work items that must be completed before the next gate (Gate A1) may close. Items required for Gate A2 or Gate A3 are not listed here; they are stated in the respective gate Exit Criteria in §7.

## 10.1 Gate A1 Deliverables

* Draft `docs/features/win_rate_21d_spec.md` at version v0.1.0 covering the ten sections enumerated in §7.2;
* Submit the draft specification for review;
* Lock the specification upon review approval and commit.

(Note: substantive specification content requirements, including resolution of design landmines and enumeration of point-in-time test identifiers, are stated as Gate A1 Exit Criteria A1-C1 through A1-C7 in §7.2.)

## 10.2 Gate A1 Review Items (for the reviewer)

* Verify that the specification covers the ten enumerated sections;
* Verify that the deterministic reproducibility contract is explicit;
* Verify that no numerical thresholds beyond minimum-observation and window-length constants are locked;
* Verify that the specification does not invade the territory of this memo (no governance audit content in the specification);
* Verify that the specification does not pre-commit to implementation choices that should remain in Gate A2.

Gate A1 closure requires both 10.1 and 10.2 satisfied.

---

# 11. Known Unknowns

This section enumerates governance uncertainties that cannot be resolved during Gate 0 and which are flagged for awareness during subsequent gates. Items in this section are not implicit work assignments; they are documented uncertainties.

1. Whether `win_rate_21d` implementation under Gate A2 will surface design questions not anticipated during Gate A1. If it does, Gate A1 may need iteration before Gate A2 can complete.
2. Whether the cross-sectional median producer required by `win_rate_21d` will exhibit deterministic behavior across all anticipated input distributions, including degenerate cases (universe size below a threshold on specific historical dates). The specification's deterministic reproducibility contract will encode the expected handling, but empirical confirmation occurs only during Gate A2 testing.
3. Whether the R1 panel reconstruction recipe formalized during Gate A3 will reveal previously-implicit assumptions in prereg §3 R1-U1 about universe membership at signal dates. If so, Gate A3 may require additional documentation work, but it remains within A3 Amendment Scope LOCK provided no substantive R1 contract change is introduced.
4. This audit is intentionally scoped to repository-observable evidence. External discussions, unpublished work products, or commitments made outside the repository are outside the scope of this audit by design. This is a scope boundary, not an uncertainty about repository trust.

---

# 12. Amendment Log

This section records changes to this memo after its first commit. The log is append-only. Each entry records what was amended, why, and the approving authority.

At first commit, this log is empty.

| ID    | Affected Section | Reason | Impact | Approved by | Approved at |
|-------|------------------|--------|--------|-------------|-------------|
| (none at first commit) | | | | | |
