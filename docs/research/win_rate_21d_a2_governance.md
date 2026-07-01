# Gate A2 Governance Note — `win_rate_21d`

**Document ID:** `win_rate_21d_a2_governance`
**Version:** v0.1.0
**Status:** LOCKED
**Owner:** Veronica
**Repository:** Helios (`~/projects/helios`)
**Created:** 2026-06-30
**Gate:** A2

---

## Scope

This note does NOT amend any SPEC_LOCKED artifact.

It documents the governance interpretation adopted for Gate A2
implementation of the `win_rate_21d` feature.

Specifically, this note:

- Does NOT modify `docs/features/win_rate_21d_spec.md` v0.1.0
  (SPEC_LOCKED at `1cf8365`).
- Does NOT modify `docs/research/ud_ratio_21d_r1_prereg.md`
  (LOCKED at `13ed404`).
- Does NOT reopen `docs/research/ud_ratio_21d_r1_pre_execution_audit.md`
  (Gate A1 CLOSED at `89fa08e`).

## Normative status

Unless explicitly stated otherwise, this document is interpretive
rather than normative.

Normative requirements remain those defined by the SPEC_LOCKED
artifacts referenced in Section 4.

---

## 1. Governance Principles

### A2-GOV-1 — Acceptance Criteria vs Required Decisions

Two distinct concepts apply to Gate A2:

| Concept              | Source                                          | Modification rule                                 |
| -------------------- | ----------------------------------------------- | ------------------------------------------------- |
| Acceptance Criteria  | `win_rate_21d_spec.md` §7.2 (8 items)           | Requires spec amendment + version bump.           |
| Required Decisions   | All spec-deferred clauses applicable to A2      | Documented in this note (or successor notes).     |

**Relationship:**

- Required Decisions include all implementation-relevant
  Acceptance Criteria together with additional spec-deferred
  implementation decisions.
- A missing Acceptance Criterion is a SPEC_LOCKED contract violation.
- A missing Required Decision blocks A2 completion but does not
  violate any locked contract.

The Acceptance Criteria text in `win_rate_21d_spec.md` §7.2 is
NOT modified by this note.

### A2-GOV-2 — Section-conflict precedence rule

When two sections of the same SPEC_LOCKED artifact enumerate
overlapping or related items, the following rule applies:

```
Case 1: §X and §Y both list item Z with conflicting values.
        → CONFLICT. When conflicting normative statements
           exist, the section explicitly designated as the
           normative Acceptance Criteria for that artifact
           takes precedence.
        → If implementation requires the other section's value,
           spec amendment with version bump is mandatory.
           Union is FORBIDDEN.

Case 2: §X lists item Z; §Y is silent on Z but defers a related
        implementation decision elsewhere in the artifact.
        → COMPLEMENTARY. Union is permitted for Required
           Decisions only. Acceptance Criteria text is not
           modified.

Case 3: §X and §Y both list item Z with identical values.
        → REDUNDANT. Treat as one item.
```

This rule generalizes beyond `win_rate_21d`. Future Helios
artifacts SHOULD cite this principle (A2-GOV-2) when resolving
analogous section-level enumeration questions. The designated
Acceptance Criteria section may be named differently in other
artifacts (e.g., Validation Criteria, Contract, Normative
Requirements); A2-GOV-2 applies regardless of label.

### A2-GOV-3 — Editorial Remark placement

Editorial Remarks documenting governance interpretation of
SPEC_LOCKED artifacts MUST be placed in a separate governance
note (such as this document), NOT inside the SPEC_LOCKED
artifact itself.

Rationale: a SPEC_LOCKED artifact's contents are governance
state; modifying it to record interpretation would conflate
"what is locked" with "how the lock is read".

### A2-GOV-4 — Required Decisions amendment rule

A new Required Decision MAY be added to the A2 work list during
Gate A2 execution only under the following condition:

```
A new Required Decision may be added only when an existing
SPEC_LOCKED artifact explicitly defers that decision to
Gate A2 (or equivalent wording such as "deferred to A2",
"locked at A2", "implementation-time decision").

Engineering refinements identified during implementation
that are NOT spec-deferred do NOT qualify as Required
Decisions. They belong in PR descriptions or design notes,
not in this governance corpus.
```

**Procedure for valid addition:**

1. Cite the specific spec clause that defers the decision.
2. Document the addition in this note (or a successor note)
   as an extension to the Required Decisions list.
3. Reference the addition in the affected PR's description.

**Examples of non-qualifying additions:**

- "This would be cleaner if we also locked X" (style preference).
- "X should probably be configurable" (engineering judgment).
- "We might as well decide X now" (convenience).

These belong to PR review, not governance.

---

## 2. Editorial Remark

### ER-A2-001 — Spec v0.1.0 §7.2 / §10.1 editorial divergence

Spec v0.1.0 contains an editorial divergence between §7.2 and
§10.1 regarding the enumeration of Gate A2 work items.

§10.1 lists three deferred implementation locks not enumerated
in §7.2:

- Producer table name and storage location (deferred per §5.1
  last sentence).
- Dtype widths (deferred per §6.1 last sentence).
- Floating-point tolerance for I4 self-consistency (deferred
  per §6.2 I4).

Conversely, §10.1 omits three §7.2 items (producer-consumer
query interface documentation, snapshot lineage mechanism,
regeneration-trigger detection mechanism). All three are
nonetheless covered elsewhere in the spec (§5.7, §4.7, §5.5
respectively).

This observation is descriptive only and does not imply that
either section is incomplete in isolation.

No mathematical definition or feature contract is affected.
The two sections diverge only in their enumeration of A2
work items.

**Resolution under A2-GOV-2:**

This is a Case-2 complementary divergence (each section omits
items the other lists; no conflicting values), not a Case-1
conflict. Union is permitted for Required Decisions.

Gate A2 implementation proceeds under the union §7.2 ∪ §10.1
∪ other spec-deferred clauses, yielding 11 Required Decisions.
The §7.2 Acceptance Criteria text (8 items) is not modified;
spec remains SPEC_LOCKED at v0.1.0.

A future spec v0.1.1 MAY mirror the Required Decisions list
into §7.2 to eliminate the editorial gap, but only if v0.1.1
is opened for unrelated material reasons. Opening v0.1.1
solely to fix this editorial gap is NOT recommended and is
NOT in scope of any current gate.

---

## 3. Gate A2 Execution Scope (frozen at kickoff)

The following 11 Deliverables and 11 Sub-decisions are frozen
at A2 kickoff. Subsequent additions are governed by A2-GOV-4.

### 3.1 Deliverables (11 items)

| ID     | Item                                                       | Spec anchor              |
| ------ | ---------------------------------------------------------- | ------------------------ |
| A2-D1  | Lock `MIN_CROSS_SECTION_OBS_PER_DATE`                      | §3.7 / §7.2 #1           |
| A2-D2  | Producer build pipeline implemented + tested               | §7.2 #2                  |
| A2-D3  | Consumer feature function implemented + tested             | §7.2 #3                  |
| A2-D4  | 17 PIT tests (PROD-1..6, CONS-1..8, INT-1..3) passing      | §7.2 #4 / §8.2           |
| A2-D5  | Producer-consumer query interface documented               | §5.7 / §7.2 #5           |
| A2-D6  | Snapshot lineage mechanism implemented + documented        | §4.7 / §7.2 #6           |
| A2-D7  | Regeneration-trigger detection mechanism + documented      | §5.5 / §7.2 #7           |
| A2-D8  | Calendar-day buffer constant locked                        | §4.1 / §7.2 #8           |
| A2-D9  | Producer table name + storage location locked              | §5.1 / §10.1             |
| A2-D10 | Dtype widths locked                                        | §6.1 / §10.1             |
| A2-D11 | I4 floating-point tolerance locked                         | §6.2 I4 / §10.1          |

### 3.2 Required Sub-decisions (11 items)

| ID        | Decision                                                       | Maps to        |
| --------- | -------------------------------------------------------------- | -------------- |
| SD-A2-1   | `MIN_CROSS_SECTION_OBS_PER_DATE` value + rationale             | A2-D1          |
| SD-A2-2   | Producer table name + storage location (DuckDB workspace path) | A2-D9          |
| SD-A2-3   | Build orchestration (one-shot full vs incremental)             | implementation |
| SD-A2-4   | Multi-stock cross-sectional fixture strategy                   | A2-D4 fixtures |
| SD-A2-5   | Snapshot lineage mechanism (metadata column / manifest / both) | A2-D6          |
| SD-A2-6   | Calendar-day buffer constant value                             | A2-D8          |
| SD-A2-7   | PR strategy (single PR vs split producer / consumer / tests)   | workflow       |
| SD-A2-8   | Dtype widths (Float64 for ratio; UInt8 vs UInt16 for counts)   | A2-D10         |
| SD-A2-9   | I4 floating-point tolerance EPS value                          | A2-D11         |
| SD-A2-10  | Producer-consumer query interface signature                    | A2-D5          |
| SD-A2-11  | Regeneration-trigger detection mechanism specifics             | A2-D7          |

### 3.3 Out of scope for A2

(Verbatim from Gate A2 kickoff prompt; preserved without
modification per governance discipline.)

- R1 prereg amendment (Gate A3).
- Spec amendment beyond v0.1.0.
- Any modification to spec mathematical contract; if discovered
  necessary, requires a separate governance flow.

---

## 4. Anchor References

| Document                                              | Status         | Commit / Anchor |
| ----------------------------------------------------- | -------------- | --------------- |
| `docs/features/win_rate_21d_spec.md`                  | SPEC_LOCKED    | `1cf8365`       |
| `docs/research/ud_ratio_21d_r1_prereg.md`             | LOCKED         | `13ed404`       |
| `docs/research/ud_ratio_21d_r1_pre_execution_audit.md`| Gate A1 CLOSED | `89fa08e`       |

Anchor md5 hashes (verified at this note's creation):

```
win_rate_21d_spec.md                          3701f2c2a739ca93aa2f1c963d53a63a
ud_ratio_21d_r1_prereg.md                     4fd52fe75c38c6b489ee5311e9f6525b
ud_ratio_21d_r1_pre_execution_audit.md        fafc04b9ee6a5bc9311ea75c884d9ff5
```

Repository HEAD at this note's creation: `89fa08e`.

---

## 5. Sign-off

| Item                            | Status | Date       | Signer   |
| ------------------------------- | ------ | ---------- | -------- |
| Governance interpretation       | LOCKED | 2026-06-30 | Veronica |
| Editorial remark                | LOCKED | 2026-06-30 | Veronica |
| Frozen Required Decisions       | LOCKED | 2026-06-30 | Veronica |
| Document status: DRAFT → LOCKED | LOCKED | 2026-06-30 | Veronica |

---

## 6. Version history

| Version        | Date       | Change                                              |
| -------------- | ---------- | --------------------------------------------------- |
| v0.1.0 (LOCKED)| 2026-06-30 | Initial version. Gate A2 governance note. Sign-off complete. |

*End of v0.1.0 LOCKED.*
