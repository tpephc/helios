# R1-U7B Enumeration Boundary Spec

<!-- docs/research/ud_ratio_21d_r1_u7b_enumeration_boundary.md -->
<!-- v0.1.0 — 2026-06-23 -->

**Status:** LOCKED — v0.1.0 (2026-06-23)
**Purpose:** Define enumeration scope for R1-U7B historical anchor audit
            BEFORE enumeration begins, to prevent scope-from-result
            contamination (§15 violation).
**Supersedes:** None
**Referenced by:** `docs/research/ud_ratio_21d_r1_prereg.md` §9.1
                   (DRAFT — NOT LOCKED)
**Will inform:** `docs/research/ud_ratio_21d_r1_u7b_audit.md`
                 (forthcoming, commit 2 of 4)

---

## 1. Lineage Exclusion (cross-reference to prereg §9.1 criterion 5)

U7A criterion (5) — lineage independence — is defined in
`docs/research/ud_ratio_21d_r1_prereg.md` §9.1 (amended 2026-06-23).
This spec enforces it operationally.

Excluded from U7B eligibility under U7A criterion (5):

```text
docs/research/ud_ratio_21d_*.md             (all Track-C Step 2 artifacts)
research/track_c_step1_closeout.md          (Track-C Step 1)
research/ud_ratio_21d/*                     (any future Track-C output)
Any future artifact under Track-C lineage
```

Excluded artifacts MAY still be cited as lineage context elsewhere in
the audit; they cannot serve as anchors.

---

## 2. R8 Phase 6 Inclusion Rule

R8 Phase 6 artifacts ARE included in Phase 1 raw enumeration.

R8 Phase 6 artifacts MAY be rejected at Phase 2 U7A evaluation if
finding-level content fails U7A criterion (1):

```text
Anchor must be an alpha / feature-discovery / signal-validation
finding; risk, exit, capital, or governance findings are not
U7A-eligible.
```

Rejection MUST cite the specific finding identifier
(e.g. `F-P6-01`) and the finding's content, not the phase label.

Rationale: Pre-emptive phase-level exclusion is unverifiable and
risks omitting alpha-adjacent findings that happen to live in a
non-alpha phase report.

---

## 3. Source Type Hierarchy

### 3.1 Primary enumeration source

```text
All *.md files under docs/research/
All *.md files under research/
```

### 3.2 Secondary exhaustiveness check (orphan scan)

```text
All *.py files under research/

Test files (tests/research/*.py) and production scripts
(scripts/*.py) are EXCLUDED from primary enumeration but MAY enter
the secondary orphan scan if their filename or topic suggests a
research conclusion not represented by governance markdown.
```

Examples that qualify for orphan-scan inclusion:

```text
sanity_harness        (e.g. bull_strategy_sanity_harness.py)
diagnostic_harness    (carries INCONCLUSIVE / PASS / FAIL verdict)
adaptive_sim_runner   (e.g. adaptive simulation runners that emit
                       finding-level outputs)
```

Examples that do NOT qualify:

```text
pure unit tests verifying a module's contract
production cron / ingest / submission scripts
test fixtures and helpers
```

### 3.3 Orphan detection rule

For each `*.py` considered, verify a corresponding governance `*.md`
exists that documents its conclusion.

```text
Orphan = *.py with no corresponding governance *.md covering the
         same topic / verdict.
```

### 3.4 Orphan disposition rule

```text
Read orphan script.
Classify as:
  - closed study
  - exploratory tool
  - dead prototype

closed study orphans:
  - MUST be appended to enumeration as appendix entries
  - MUST carry explicit note that conclusion source is script-level,
    not governance-document-level
  - U7A criterion (1) and (4) evaluation must account for the
    weaker governance status

exploratory tool / dead prototype orphans:
  - excluded from enumeration with one-line reason recorded in
    the audit appendix
```

Rationale: `.py`-only studies risk being missed if `.md` is the sole
source; but treating `.py` and `.md` as equivalent dilutes
governance finality. The orphan-scan pattern preserves
exhaustiveness without collapsing the distinction. Test and
production scripts are included in the secondary scan only when they
may carry a verdict (sanity harness etc), not when they merely
verify or operationalise.

---

## 4. Out of Scope

The following are NOT enumeration sources, by design:

```text
DuckDB query outputs                (data, not research artifacts)
Pure unit tests                     (verify module contract,
                                     not research conclusion)
Pure operational scripts            (cron, ingest, submission)
Notebook files (.ipynb)             (typically ephemeral)
Git commit messages alone           (must point to a *.md or *.py
                                     artifact)
```

Rationale: enumeration source must be a stable, reviewable artifact
that asserts a research conclusion. Transient outputs and operational
code do not qualify. The boundary between "operational" and
"verdict-carrying" scripts is enforced via §3.2 orphan-scan
eligibility test, not via blanket exclusion.

---

## 5. Enumeration Process Binding

### 5.1 Phase 1 — Raw enumeration

```text
Source:  §3.1 primary
Output:  candidate list with the following fields per row:
           - case name / short identifier
           - source file path
           - earliest git commit (SHA + date) where the case
             reached its current governance state
           - one-line description (no verdict)
Forbidden:
           - U7A evaluation
           - verdict
           - exclusion based on guessed U7A outcome
           - filtering by perceived relevance to ud_ratio_21d
```

### 5.2 Phase 1b — Orphan scan

```text
Source:  §3.2 secondary
Output:  orphan disposition per §3.4
Appended to Phase 1 candidate list as appendix.
```

### 5.3 Phase 2 — U7A evaluation

```text
Apply U7A criteria (1)-(5) per candidate.
Evidence-driven verdict: each criterion evaluated against concrete
                          evidence (commit, content quote, statistic).
Per-criterion record:    pass/fail for each criterion individually,
                          not aggregate.
A candidate is eligible only if ALL five criteria pass.
```

### 5.4 Phase 3 — Synthesis

```text
Compute pass count.
Determine disclosure path:
  - multi-anchor   (>= 2 eligible candidates with at least one
                    collapse + one orthogonal)
  - single-anchor  (1 eligible candidate, or eligible candidates
                    only on collapse side)
  - zero-anchor    (no eligible candidate, apply §9.2 single-anchor
                    disclosure with explicit zero-eligible note)
```

### 5.5 Commit boundary

```text
commit 1:  this spec + prereg §9.1 amendment
           (BEFORE Phase 1 begins)
commit 2:  Phase 1 + Phase 1b output
           (raw enumeration + orphan scan, no U7A verdict)
commit 3:  Phase 2 output
           (U7A evaluation, per-criterion per-candidate)
commit 4:  Phase 3 synthesis
           (may bundle with R1 prereg LOCK, including
            N_MIN_CROSS_SECTION and N_MIN_REGIME_DATES
            finalisation)
```

Rationale for four-commit boundary: each commit reflects a single
governance act. Enumeration honesty, evaluation honesty, and
synthesis honesty are independently verifiable in git history. A
collapsed commit would make scope-from-result contamination
indistinguishable from honest sequencing.

---

## 6. Locked Decisions Record

| Decision | Source | Date |
|---|---|---|
| Lineage exclusion (U7A criterion 5) | User confirmation | 2026-06-23 |
| R8 Phase 6 inclusion + finding-level evaluation | User confirmation | 2026-06-23 |
| `.md` primary + `.py` orphan scan (option C) | User confirmation | 2026-06-23 |
| Test/production scripts eligible via verdict-carrying test | User confirmation | 2026-06-23 |
| Four-commit boundary | User confirmation | 2026-06-23 |
| U7A criterion (5) written to prereg §9.1, cross-referenced here | User confirmation | 2026-06-23 |

---

## 7. Spec Status

```text
Status:                LOCKED — v0.1.0
Locked at:             2026-06-23
Locked before:         R1-U7B enumeration begins
Modifications allowed: NONE without version bump and explicit
                        amendment record
```

Any future amendment to this spec must:

```text
1. occur BEFORE the audit phase it governs
2. carry a version bump (v0.1.0 -> v0.1.1 or v0.2.0)
3. include explicit rationale in an Amendment Log section
4. be committed independently of audit output
```

---

*End of spec.*
