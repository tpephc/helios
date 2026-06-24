# R1-U7B Enumeration Boundary Spec

<!-- docs/research/ud_ratio_21d_r1_u7b_enumeration_boundary.md -->
<!-- v0.1.1 — 2026-06-24 -->

**Status:** LOCKED — v0.1.1 (2026-06-24)
**Supersedes:** v0.1.0 (LOCKED 2026-06-23) §3.1, §4, §5.5
**Purpose:** Define enumeration scope for R1-U7B historical anchor audit
            BEFORE enumeration begins, to prevent scope-from-result
            contamination (§15 violation).
**Referenced by:** `docs/research/ud_ratio_21d_r1_prereg.md` §9.1
                   (DRAFT — NOT LOCKED)
**Will inform:** `docs/research/ud_ratio_21d_r1_u7b_audit.md`
                 (forthcoming, commit 3 of 5)

---

## v0.1.1 Amendment Notice

v0.1.0 §3.1 specified the primary enumeration source as
`docs/research/*.md` and `research/*.md` literally. Inspection of
the repository on 2026-06-24 revealed that finding-bearing
artifacts also exist outside these two directories:

```text
docs/RESEARCH_JOURNAL.md       (structural findings under v0.1.14.1.2)
docs/JOURNAL.md                (PF / drawdown / win-rate findings)
docs/decision_records/r8_phase1_governance.md
                                (Phase 0 facts asserted as basis)
docs/handoffs/*.md             (some handoffs are primary closeout
                                records — e.g. IF-3A complete handoff)
research/adr/*.md              (methodological ADRs, not findings,
                                but referenced by finding evidence)
```

v0.1.0 source universe was underspecified relative to actual repo
layout. v0.1.1 supersedes §3.1, §4, and §5.5 before enumeration
begins.

```text
No candidate enumeration, U7A evaluation, Spearman query, or result
inspection occurred before this amendment. This is a retroactive
correction, not a spec drift.
```

v0.1.0 §1 (lineage exclusion), §2 (R8 Phase 6 inclusion rule),
§3.2-§3.4 (orphan scan), §5.1-§5.4 (enumeration process binding),
§6 (locked decisions record), §7 (spec status) are retained
unchanged in semantics; section numbers shift only in §5.5 to
accommodate the 5-commit pipeline.

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

## 3. Source Type Hierarchy (v0.1.1 — supersedes v0.1.0 §3.1)

### 3.1 Primary enumeration scope — intent

Primary enumeration source is the set of **finding-bearing reviewable
artifacts**, not merely directory membership. Directory membership is
a *seed* for discovery; the *test* is content-based.

### 3.2 Primary enumeration scope — seed locations

The following locations are seeded into the enumeration scan. Every
`*.md` file within these locations (subject to §3.5 depth limits)
must be evaluated against the §3.3 operational test:

```text
docs/research/**/*.md        (maxdepth 3)
research/**/*.md             (maxdepth 3, includes research/adr/)
docs/RESEARCH_JOURNAL.md     (single file)
docs/JOURNAL.md              (single file)
docs/decision_records/**/*.md  (maxdepth 2)
docs/handoffs/**/*.md        (maxdepth 2)
```

The following locations are NOT blanket-included. Files within
these locations enter enumeration only if explicitly referenced as
finding sources by a file already included under §3.2 seed
locations (per §3.3 test (c)):

```text
docs/features/*.md
docs/design/*.md
docs/operations/*.md
docs/reviews/*.md
docs/backlog/*.md
top-level docs/*.md (excluding RESEARCH_JOURNAL.md, JOURNAL.md)
```

### 3.3 Primary enumeration — operational test (evidence-based)

For each file in §3.2 seed scope, apply the following test. The
test is evidence-based: classifications must be derivable from
textual signals that any reviewer can grep, not from intent
judgments.

```text
INCLUDE in primary enumeration if ANY of:

  (a) file contains an explicit verdict statement matching one of:
        "PASS", "FAIL", "CONFIRMED", "CLOSED",
        "REJECTED", "RESEARCH_FINDING", "FINDING",
        "STATUS: ACCEPTED" (in research scope context)
      — verdict must apply to a research / study result, not
        merely to an architectural / operational decision

  (b) file contains at least one quantified empirical claim with
      units (rho, p-value, Sharpe, drawdown %, return %, win rate,
      CAGR, profit factor, etc.) AND the claim is presented as a
      study conclusion or structural finding, not as illustration,
      background context, or a target / hypothesis

  (c) file is referenced by name from any file already INCLUDED
      under (a) or (b) as that file's "finding source", "evidence
      base", "Phase X reference", or equivalent

EXCLUDE from primary enumeration if:

  (d) file satisfies none of (a)-(c)

  (e) file is explicitly methodological / architectural (e.g.
      ADR-001 no-HFT, ADR-002 polars-native-indicators,
      ADR-006 cohesion-over-abstraction) AND contains no
      finding-bearing content. Methodological ADRs that lock a
      research method (e.g. ADR-R8P1-001 block-bootstrap method)
      are EXCLUDED from U7B eligibility but ARE retained in §A.2
      as "methodology-locking artifact referenced by finding files"

  (f) file is in §1 lineage exclusion list

  (g) file is in §4 out-of-scope category
```

**Each file's classification MUST be recorded in audit §A.2 with
the matching test letter ((a), (b), (c), (d), (e), (f), or (g)).**

This is not optional. It exists so that a future reviewer can grep
the classification record, verify the textual signal cited, and
either confirm or challenge the classification without re-running
Phase 1 from scratch.

### 3.4 Secondary exhaustiveness check (orphan scan, .py files)

All `*.py` files under `research/` enter the orphan scan.

Test files (`tests/research/*.py`) and production scripts
(`scripts/*.py`) are EXCLUDED from primary enumeration but MAY
enter the secondary orphan scan if their filename or topic
suggests a verdict-carrying artifact:

```text
sanity_harness         (e.g. bull_strategy_sanity_harness.py)
diagnostic_harness     (carries INCONCLUSIVE / PASS / FAIL verdict)
adaptive_sim_runner    (adaptive simulation runners emitting
                        finding-level outputs)
```

Examples that do NOT qualify:

```text
pure unit tests verifying a module's contract
production cron / ingest / submission scripts
test fixtures and helpers
```

For each `*.py` considered, verify a corresponding governance
`*.md` exists. Orphan detection uses **grep + human confirmation**
(per Q3, 2026-06-24):

```text
Grep is the first-pass filter (filename topic keyword vs *.md inventory).
Human confirmation verifies:
  - whether the .py is verdict-carrying
  - whether a corresponding governance .md exists
  - whether it should appear in §B.3 orphan appendix

Human confirmation is NOT permitted to apply U7A pass/fail logic.
```

Orphan disposition rule:

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

### 3.5 Depth limits

Depth limits are part of the audit boundary. Files deeper than the
specified maxdepth are out of scope for v0.1.1 unless explicitly
referenced by an included file as a finding source (per §3.3 test
(c)).

```text
docs/research/             maxdepth 3
research/                  maxdepth 3
docs/decision_records/     maxdepth 2
docs/handoffs/             maxdepth 2
```

Future subdirectory expansion does not silently change enumeration
universe. New subdirectories beyond these depths require a v0.1.2
amendment.

---

## 4. Out of Scope (v0.1.1 — supersedes v0.1.0 §4)

The following are NOT enumeration sources, by design:

```text
DuckDB query outputs                (data, not research artifacts)
Pure unit tests                     (verify module contract,
                                     not research conclusion)
Pure operational scripts            (cron, ingest, submission)
Notebook files (.ipynb)             (typically ephemeral)
Git commit messages alone           (must point to a *.md or *.py
                                     artifact)
Architectural ADRs                  (ADR-001 no-HFT, ADR-002
                                     polars-native, ADR-006
                                     cohesion-over-abstraction,
                                     and similar — purely
                                     architectural decisions
                                     without finding-bearing content)
Methodological ADRs                 (ADR-R8P1-001 block-bootstrap,
                                     ADR-R8P1-002 baseline benchmark
                                     construction — lock METHOD,
                                     do not assert findings.
                                     Recorded in audit §A.2 as
                                     methodology-locking artifacts
                                     for reproducibility-chain
                                     traceability, but ineligible
                                     as U7B anchors)
```

Rationale: enumeration source must be a stable, reviewable artifact
that ASSERTS a research conclusion. Transient outputs, operational
code, architectural decisions, and methodological locks are
out-of-scope by design. The §3.3 evidence-based test enforces this
boundary at file-by-file granularity.

---

## 5. Enumeration Process Binding

### 5.1 Phase 1 — Raw enumeration

```text
Source:  §3.2 seed locations, filtered through §3.3 operational test
Output:  candidate list with the following fields per row:
           - case name / short identifier
           - source file path
           - file_first_commit_sha
           - file_first_commit_date
           - governance_state_commit_sha
             (TBD_PHASE2 if not mechanically determinable)
           - governance_state_commit_date
             (TBD_PHASE2 if not mechanically determinable)
           - one-line description (no verdict assertion)
           - §3.3 classification letter ((a) / (b) / (c) etc.)
Forbidden:
           - U7A evaluation
           - verdict
           - exclusion based on guessed U7A outcome
           - filtering by perceived relevance to ud_ratio_21d
```

### 5.2 Phase 1b — Orphan scan

```text
Source:  §3.4 secondary
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

### 5.5 Commit boundary (v0.1.1 — supersedes v0.1.0 §5.5)

```text
commit 1:  boundary spec v0.1.0 + prereg §9.1 amendment
           [DONE, 63f275f, 2026-06-23]
commit 2:  boundary spec v0.1.1 — scope amendment
           [THIS COMMIT]
commit 3:  audit skeleton + Phase 1 enumeration + Phase 1b orphan scan
commit 4:  Phase 2 U7A evaluation
           (per-candidate per-criterion record)
commit 5:  Phase 3 synthesis
           (may bundle with R1 prereg LOCK, including
            N_MIN_CROSS_SECTION and N_MIN_REGIME_DATES finalisation)
```

Rationale for five-commit boundary (v0.1.0 had four): scope
amendment is itself a governance act and must be independently
verifiable in git history. Collapsing scope amendment into the
enumeration commit would make scope-from-result contamination
indistinguishable from honest sequencing — the same failure mode
the four-commit boundary was designed to prevent.

---

## 6. Locked Decisions Record

| Decision | Source | Date | Spec Version |
|---|---|---|---|
| Lineage exclusion (U7A criterion 5) | User confirmation | 2026-06-23 | v0.1.0 |
| R8 Phase 6 inclusion + finding-level evaluation | User confirmation | 2026-06-23 | v0.1.0 |
| `.md` primary + `.py` orphan scan (option C) | User confirmation | 2026-06-23 | v0.1.0 |
| Test/production scripts eligible via verdict-carrying test | User confirmation | 2026-06-23 | v0.1.0 |
| Four-commit boundary | User confirmation | 2026-06-23 | v0.1.0 |
| U7A criterion (5) written to prereg §9.1 | User confirmation | 2026-06-23 | v0.1.0 |
| Evidence-based operational test (a)-(g) | User confirmation | 2026-06-24 | v0.1.1 |
| Seed locations include JOURNAL, RESEARCH_JOURNAL, decision_records, handoffs | User confirmation | 2026-06-24 | v0.1.1 |
| Handoffs full operational-test pass (option α) | User confirmation | 2026-06-24 | v0.1.1 |
| Depth limits as audit boundary | User confirmation | 2026-06-24 | v0.1.1 |
| Architectural and methodological ADRs explicitly out of scope | User confirmation | 2026-06-24 | v0.1.1 |
| Five-commit boundary (supersedes four) | User confirmation | 2026-06-24 | v0.1.1 |

---

## 7. Spec Status

```text
Status:                LOCKED — v0.1.1
Locked at:             2026-06-24
Locked before:         R1-U7B enumeration begins
Modifications allowed: NONE without version bump and explicit
                        amendment record
```

Any future amendment to this spec must:

```text
1. occur BEFORE the audit phase it governs
2. carry a version bump
3. include explicit rationale in §8 Amendment Log
4. be committed independently of audit output
```

---

## 8. Amendment Log

```text
v0.1.0  2026-06-23  Initial lock.
                    §1 lineage exclusion, §2 Phase 6 inclusion,
                    §3 source hierarchy (.md + .py), §4 out of scope,
                    §5 enumeration process binding (4-commit pipeline).

v0.1.1  2026-06-24  Scope amendment, BEFORE enumeration begins.
                    Trigger: 2026-06-24 repo layout inspection
                    revealed v0.1.0 §3.1 source universe was
                    underspecified relative to actual finding-
                    bearing artifact locations.

                    Supersedes:
                      §3.1 source hierarchy → §3.1-§3.5 with
                            evidence-based operational test
                      §4   out of scope → expanded to cover
                            architectural and methodological ADRs
                      §5.5 commit boundary → 4 commits → 5 commits

                    Retained unchanged:
                      §1 lineage exclusion
                      §2 R8 Phase 6 inclusion rule
                      §3.2-§3.4 of v0.1.0 → renumbered to §3.4
                            (orphan scan logic semantically unchanged)
                      §5.1-§5.4 enumeration process binding

                    No candidate enumeration, U7A evaluation,
                    Spearman query, or result inspection occurred
                    before this amendment. Retroactive correction,
                    not spec drift.
```

---

*End of spec.*
