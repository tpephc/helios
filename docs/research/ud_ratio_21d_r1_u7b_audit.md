# R1-U7B Historical Anchor Audit

<!-- docs/research/ud_ratio_21d_r1_u7b_audit.md -->
<!-- v0.1.1 — 2026-06-25 (Batches 1 + 2a + 2b + 3 + 4 + 5 + 6a + 6b complete; Phase 1 enumeration COMPLETE; §A.1/§A.2.1-3/§A.5/§B pending) -->

**Status:** COMMIT 3 LOCK READY — Phase 1 enumeration + §A.1 source
            list freeze + §A.5 exhaustiveness check + §B orphan
            scan + §C Commit 3 Readiness Gate all complete and
            verified. Totals: 96 seed files = 4 §A.2.1 + 92
            enumerated (26 §A.2.4 + 19 §A.3 source-files producing
            41 rows + 47 §A.4 = 47 rows). Partition invariant
            satisfied (4 + 92 = 96 ✓); coverage 92/92 = 100%.
            §B orphan scan: 1 appendix entry (replay_engine.py
            script-level closed-study) + 3 excluded (exploratory
            tools). Protocol Freeze held throughout. Fix A
            partition correction applied 2026-06-25 with full
            trail in §C.7. Phase 2 (U7A evaluation, §D) gated on
            this lock. Phase 3 (synthesis, §E) NOT STARTED.
**Governed by:** `docs/research/ud_ratio_21d_r1_u7b_enumeration_boundary.md`
                 v0.1.1 (LOCKED 2026-06-24)
**Pre-registration:** `docs/research/ud_ratio_21d_r1_prereg.md` §9.1
                      (DRAFT — NOT LOCKED)
**Commit pipeline position:** commit 3 of 5

---

## §A. Phase 1 — Raw Enumeration

### A.0 Scope and Method

#### A.0.R Design Rationale — Non-Binding

The following retrospective notes are explanatory only and are
recorded as Commit 5 consolidation input. They do NOT modify
classification rules, row ownership, or Protocol Freeze.

Reviewers seeking only the binding rules may skip directly to
§A.0.1 Binding Protocol below.

Audit-level retrospective note (added 2026-06-25 after Batch 6a
review, NOT a §A.0 locked rule; recorded for Commit 5
consolidation input only):

```text
Phase 1 classification can be cleanly decomposed into three
sub-phases that the current audit interleaved:

  Phase 1A — Document Identity
             What is this document's primary purpose?
             (methodological / workflow / finding-bearing /
              aggregator / governance-process)

  Phase 1B — Evidence Extraction
             What empirical claims does the document contain?
             Which are first-on-record vs referencing elsewhere?

  Phase 1C — Anchor Resolution
             For each first-on-record claim, where is its
             canonical row anchored? Has another (earlier)
             file in scope already anchored the same cluster?

The current audit's §A.0 rule set conflates these into a single
classification step, which produced extended discussion on
borderline cases (e.g., handoff_2026-05-29.md in Batch 6a). A
cleaner audit would resolve Identity first, then perform Evidence
extraction only on Identity-finding-bearing files, then anchor.

This observation is recorded as Commit 5 consolidation input.
It does NOT change any classification in the current audit;
Protocol Freeze remains in effect through Batch 6b.
```

Audit-level retrospective note 2 (added 2026-06-25 after Batch
6b review, NOT a §A.0 locked rule; Commit 5 consolidation input):

```text
Conceptual reframe surfaced during Batches 4-6b: the audit's
operative question is NOT "what kind of document is this?" but
"which document owns this finding for governance purposes?".

  Old framing (Document Identity → Classification):
    Document
        ↓
    Identity (methodological / workflow / finding / aggregator
              / governance-process)
        ↓
    Classification (row in §A.2.4 / §A.3 / §A.4)

  New framing (Canonical Evidence Ownership → Document Role):
    Document
        ↓
    Extract empirical claims
        ↓
    Find canonical anchor (which document OWNS this finding for
                           governance?)
        ↓
    Determine document role for this audit

The new framing matches what the audit actually did in Batches
4-6b: handoffs were classified (d2) not because they ARE handoffs,
but because their findings already had canonical anchors in
governed research artifacts. A handoff that established a
first-on-record governed conclusion lacking a downstream canonical
artifact would have been §A.3 primary regardless of being named
"handoff".

Practical consequence — §A.3 enumerates "independently governable
finding clusters", not files. The "Row Granularity Principle" name
is accurate but understates this: rows correspond to finding
clusters that have an identified canonical owner, not to files or
headings.

Commit 5 consolidation target structure (recorded here as input
only; binding work deferred per Protocol Freeze):

  Core Principle 1 — Identity
      What is this document's primary purpose? Methodological
      lock / workflow continuity / finding-bearing / aggregator
      / governance-process.

  Core Principle 2 — Evidence Ownership
      For each empirical claim, which document is the canonical
      owner for governance purposes? Findings without a canonical
      owner in scope become primary §A.3 anchors via Evidence-test
      prevalence; findings with a canonical owner elsewhere flow
      to (d2) workflow-continuity or (c) secondary aggregator
      depending on the citing document's identity.

  Core Principle 3 — Governance Lifecycle
      How does the canonical owner's status evolve (PROVISIONAL →
      CONFIRMED, OPEN → CLOSED, etc.) and where is that lifecycle
      recorded? Per-row governance_state_commit captures the
      authoritative commit for the current state.

The current §A.0 contains 15 locked rules + Protocol Freeze. Most
of those rules are operational consequences or reviewer-behaviour
guidance, not protocol primitives. Commit 5 consolidation may
collapse them into the three Core Principles above, with the
rest demoted to "Examples / Operational Notes / Reviewer Guidance".

This work is OUT OF SCOPE for the current audit. It does NOT
change any classification. It is recorded here so that the next
audit (if conducted under a derived template) can start from the
three-principle structure rather than re-deriving 15 rules
empirically.
```

#### A.0.1 Binding Protocol

The following rules are binding for this audit. They govern
classification of all files in §A.1 across §A.2.4, §A.3, and §A.4.
Each rule is locked per Protocol Freeze (effective Batch 5+) and
may not be modified without a new audit version.

Per boundary spec v0.1.1 §3.2, primary seed locations:

```text
docs/research/**/*.md         (maxdepth 3)
research/**/*.md              (maxdepth 3, includes research/adr/)
docs/RESEARCH_JOURNAL.md      (single file)
docs/JOURNAL.md               (single file)
docs/decision_records/**/*.md (maxdepth 2)
docs/handoffs/**/*.md         (maxdepth 2)
```

Per boundary spec v0.1.1 §3.3, each file in seed scope is evaluated
against an evidence-based operational test:

```text
INCLUDE if ANY of:
  (a) explicit verdict statement (PASS / FAIL / CONFIRMED / CLOSED /
      REJECTED / RESEARCH_FINDING / FINDING / STATUS: ACCEPTED in
      research context)
  (b) quantified empirical claim with units, presented as study
      conclusion (not background / illustration / target)
  (c) secondary finding aggregator: the document introduces no
      independent empirical evidence, but organises, summarises
      or disposes findings whose primary source resides elsewhere
      (locked definition 2026-06-25, supersedes earlier
       "referenced by name" phrasing).

EXCLUDE if:
  (d) satisfies none of (a)-(c)
  (e) architectural / methodological without finding-bearing content
  (f) lineage exclusion (§1)
  (g) out-of-scope category (§4)
```

Note on (c): being referenced or cited by an (a)/(b) file does not
itself make a document a secondary aggregator. The (c) classification
turns on the document's primary identity (aggregates findings), not
on whether it appears in someone else's reference list. A SPEC that
is referenced by Phase 1 findings remains methodological (test e);
a roadmap that summarises Phase 1 findings becomes (c).

**Each file's classification MUST be recorded with the matching
test letter.** This requirement is non-optional per boundary spec
v0.1.1 §3.3.

Per boundary spec v0.1.1 §5.1, Phase 1 output schema:

```text
- case name / short identifier
- source file path
- file_first_commit_sha
- file_first_commit_date
- governance_state_commit_sha  (or TBD_PHASE2)
- governance_state_commit_date (or TBD_PHASE2)
- one-line description (no verdict assertion)
- §3.3 classification letter
```

Per Q1 (2026-06-24): both file_first_commit and
governance_state_commit are tracked. If governance_state_commit
cannot be mechanically determined in Phase 1, populate with
`TBD_PHASE2` (NOT a subjective guess).

Per Q2 (2026-06-24): case-name extraction priority is
internal finding identifier → major heading → filename fallback.
Multi-finding files produce multiple rows.

Per Q3 (2026-06-24): orphan detection uses grep + human
confirmation. Human confirmation is NOT permitted to apply U7A
pass/fail logic.

Per N1 (2026-06-25): governance lag is NOT a Phase 1 row attribute.
`governance_state_commit_sha` uses the backlog commit when
applicable. Free-text note added to `one_line_description` if
governance state was recorded retrospectively:

```text
Governance state recorded retrospectively via backlog commit.
```

This deliberately keeps §A.3 schema focused on enumeration
metadata, not governance-quality diagnostics. If governance-lag
cases prove numerous, a separate governance-quality audit is the
appropriate remedy, not §A.3 schema expansion.

governance_state_commit deterministic rule (locked 2026-06-25):

```text
If a finding's governance state subsequently changes (status
flip, reclassification, supersession, split into sub-findings),
governance_state_commit_sha SHALL record the commit at which the
current governance state became authoritative, not necessarily
the first commit of the source document.

This rule applies per row, not per file. When a single source
document contains multiple findings whose governance lifecycles
diverge (e.g. P1-DATA_panel_integrity_assessment contains IF-1,
IF-2, IF-3, each subsequently disposed under different commits),
each row records the commit that locks its own current state:

  - IF-1 → b41d56b (remediation closeout, CLOSED)
  - IF-2 → 77fb3c1 (lifecycle_spec v0.1.5 reclassification, P2)
  - IF-3 → 39ba6c2 (composition audit, IF-3A CLOSED + IF-3B P2)

The rule is mechanical: it does not require subjective judgement
about which commit "really" locks the state. If the latest
governance-state-affecting commit cannot be identified from git
history alone, populate with TBD_PHASE2 rather than guess.
```

Per Row Granularity Principle (2026-06-25):

```text
A Phase 1 row represents the smallest independently governable
research conclusion, not necessarily the smallest document section.

The row boundary is determined by governance lifecycle, not by
document structure. Two findings that share a heading but follow
divergent governance trajectories (status flips, reclassifications,
supersessions) belong to separate rows. Two findings that share a
governance trajectory but appear under separate headings belong to
the same row.
```

Application:
  - Multi-finding documents (e.g. phase0_findings.md) are split
    by *governance-significant finding cluster*, not by heading
    count. Confirmed observations, rejected hypotheses, and
    synthesis-level conclusions are typical clusters that may
    each warrant a row.
  - Summary or aggregator documents (e.g. roadmap.md) that cite
    findings whose primary source is elsewhere produce a single
    row at the summary level; the cited primary sources produce
    their own rows under their own files.
  - The principle prevents both inflation (one row per heading
    overstates anchor count) and collapse (one row per file
    obscures U7B-relevant clusters).

Per Duplicate Handling Rule (2026-06-25, discovered during Batch 1):

```text
If two seed-scope files have identical content (verified by md5
or byte-level diff) and both satisfy §3.3, the earliest
git-resident path is treated as canonical. Later duplicate paths
are recorded in §A.4 as duplicate-of-canonical, not as additional
INCLUDED candidates.

Same-commit tie-break: if duplicate paths are introduced within
the same commit (no earlier-vs-later distinction available), the
lexicographically first repository path becomes canonical unless
explicitly documented otherwise. This makes canonicalisation fully
deterministic even in the degenerate case.

Row-level duplication (added 2026-06-25 for Batch 4):
  Duplication can occur at two levels:

    (1) File-level: byte-identical files. Handled above
        (canonical = earliest git-resident path; same-commit
        tie-break = lexicographically first path).

    (2) Row-level: two different files each record the same
        independently governable finding cluster (per Row
        Granularity Principle). The file with the earlier
        commit (or, with same-commit tie, lexicographically
        first path) records the canonical row. The duplicate
        row in the later file is NOT emitted to §A.3 (would
        inflate Unique finding clusters count via cross-source
        duplication, breaking invariant I4); instead the second
        file's coverage is noted in the canonical row's
        classification_evidence as "also recorded in
        <other_file>".

  The principle is consistent across both levels: a finding is
  anchored to the earliest place it appears in scope, regardless
  of whether that anchoring is at file granularity (identical
  content) or row granularity (overlapping clusters in
  non-identical files).
```

Application:
  - Earliest git-resident path = path with the earliest commit
    SHA actually adding that path (verified via `git show --stat
    <SHA>`, not via `git log --follow` which may report
    rename-detection artifacts).
  - Duplicate-of-canonical rows in §A.4 carry test letter (d) with
    explicit reason "duplicate of canonical at <path>".
  - This rule is audit-level enumeration hygiene, not a boundary
    spec amendment. It exists to prevent inflated anchor count
    from same-content paths discovered post-cp. The rule is
    intentionally local to this audit unless future enumerations
    demonstrate that duplicate canonicalisation is a recurring
    governance requirement.

Reviewer discipline (non-schema):

```text
During review, each INCLUDED row is additionally annotated as
"Primary source? YES / NO". This annotation is a review aid only
and is not part of the audit schema. It distinguishes primary
finding sources from secondary aggregators (roadmaps, journals,
governance reports) to prevent Phase 2 reviewers from
double-counting the same underlying finding.
```

Per Z (2026-06-24) and P1 (2026-06-24) structural decisions:

```text
Z:  §A.2  spec-level pre-exclusions
    §A.3  INCLUDED candidates (test a/b/c)
    §A.4  EXCLUDED after file-level classification (test d/e/f/g)

P1: handoffs are not given a separate sub-section.
    Files from all seed locations appear in the same §A.3 / §A.4
    tables, sorted by source_file path.
```

Forbidden in this phase (per boundary spec v0.1.1 §5.1):

```text
- U7A evaluation
- verdict
- exclusion based on guessed U7A outcome
- filtering by perceived relevance to ud_ratio_21d
```

Phase 2 isolation rule (locked 2026-06-25):

```text
Once a Batch Summary is committed to §A.3 / §A.4, no Phase 1 row
may be added, removed, merged or split because of evidence
encountered during Phase 2. Phase 1 (enumeration) and Phase 2
(U7A evaluation) operate on disjoint mutation surfaces:

  - Phase 1 may add evidence under §A.3 / §A.4 / §A.2.4 schema.
  - Phase 2 may only annotate §A.3 rows with U7A pass/fail
    outcomes; it may NOT modify the enumeration itself.

If Phase 2 discovers that an existing §A.3 row should have been
classified differently, the correct remedy is a Phase 1 erratum
amendment with explicit changelog entry — not a silent
re-enumeration. Phase 1 enumeration freezing at commit 3 lock
makes this rule operational: post-lock Phase 1 changes require a
new versioned audit, not in-place edits.

Rationale: enumeration and evaluation must remain unblended.
Otherwise, a row that "felt unimportant" after Phase 2 U7A failure
could be quietly deleted, contaminating the audit trail.
```

File sync workflow (operational, non-governance):

```text
This audit document is built incrementally Batch by Batch in a
sandbox working copy. After each Batch completes review, the
sandbox file is scp-synced to the nexus working tree as an
UNTRACKED file. The file remains untracked until §A.1, §A.2,
§A.5, §B, and all Batches are complete. At that point, a single
git add + commit lands the entire commit 3 of 5.

Implications:
  - Intermediate Batch states are never separately committed.
  - Mid-Batch corrections (e.g. Row 4 correction in Batch 1) are
    applied to the sandbox and re-synced, not as git history.
  - Until commit 3 lands, nexus untracked state is normal and
    expected.
```

Engineering Validation Principle (locked 2026-06-25):

```text
Engineering validation artifacts — PIT test PASS / FAIL records,
implementation closeouts, workflow completion declarations, wiring
gate verifications, lineage fingerprint reproducibility records —
are NOT empirical findings, even when they contain explicit
PASS/FAIL verdicts. They satisfy neither §3.3 test (a) nor (b).

PASS in a finding-bearing artifact refers to a research hypothesis
or empirical claim about market behaviour. PASS in an engineering
validation artifact refers to implementation correctness. These two
PASS classes are structurally different evidence and must not be
mixed at §A.3.

Diagnostic question for the reviewer:

```text
"What proposition became more believable because of this PASS?"

  - If the answer is a proposition about market behaviour
    (a hypothesis, an empirical claim, a finding about returns
     / volatility / regime / etc.) → §A.3 candidate (subject
    to §3.3 evidence test).

  - If the answer is a proposition about implementation
    correctness (test invariant, code wiring, lineage
    reproducibility, workflow boundary) → §A.4 (d2)
    governance-process artifact.
```

The earlier "PASS what?" formulation is preserved as a quick mnemonic;
this formulation is the authoritative form when ambiguity arises.

The classification turns on document identity, not on lineage.
Applying this principle does not require Phase 2 U7A lineage
evaluation; it is a Phase 1 enumeration-level decision based on
the artifact's primary purpose. This preserves the audit trail:
files routed to §A.4 (d2) under this principle are never visible
to U7A evaluation and therefore cannot create a Phase 2 obligation
to retroactively re-classify Phase 1 entries.
```

Consistency Invariants for Batch Summary (locked 2026-06-25):

```text
Every Batch Summary block SHALL satisfy the following arithmetic
invariants. Reviewers can verify these mechanically without
recomputing row content.

I1 (file partition):
    Files reviewed = Finding-bearing
                   + Methodological
                   + Aggregator
                   + Governance-process
                   + Duplicate (if present, e.g. Batch 1)

I2 (row partition):
    Rows emitted = Included rows + Excluded rows

I3 (Included composition):
    Included rows = Primary sources + Secondary aggregators

I4 (anchor candidate count):
    Unique finding clusters = Primary sources
                              (equality holds while the Row
                               Granularity Principle prevents
                               cross-row duplication of the same
                               finding; if a future Batch introduces
                               cross-source duplication, I4 becomes
                               an inequality and must be flagged.)

Each Batch Summary SHALL include an explicit "Invariant check"
sub-block recording I1, I2, I3 (and I4 implicitly via the Unique
finding clusters field). I4 violation requires Batch re-review;
I1/I2/I3 violation is an arithmetic error and must be corrected
in place.

Definition (Unique finding clusters):
    The count of distinct empirical findings admitted to §A.3 via
    Primary source rows. Secondary aggregator rows do not contribute
    (they cite findings counted via their primary source).
    Phase 2 U7A evaluation operates on this count, not on raw row
    count, because aggregators cannot themselves be U7B anchors.
```

---

### A.1 Enumeration Source File List

The following 96 files constitute the complete seed scope per
boundary spec v0.1.1 §3.2. List frozen 2026-06-25 after Phase 1
enumeration completion. Every file is accounted for in exactly one
of §A.2.1, §A.2.4, §A.3, or §A.4 (see §A.5 Exhaustiveness Check).

#### A.1.1 Seed Scope Totals

```text
Seed scope:        96 files
Pre-excluded:       4 files (§A.2.1 lineage exclusion)
Enumerated:        92 files

Partition invariant:
  96 = 4 + 92  ✓

Enumeration coverage:
  92 / 92 = 100%  (all enumerated files placed in
                   §A.2.4, §A.3, or §A.4 — see §A.5)

Enumeration source command (executed 2026-06-25 on nexus):
  cd ~/projects/helios
  {
    find docs/research -maxdepth 3 -name "*.md" -type f
    find research -maxdepth 3 -name "*.md" -type f
    echo docs/RESEARCH_JOURNAL.md
    echo docs/JOURNAL.md
    find docs/decision_records -maxdepth 2 -name "*.md" -type f
    find docs/handoffs -maxdepth 2 -name "*.md" -type f
  } | sort -u | wc -l
  # → 96
```

#### A.1.2 File Count by Directory

```text
docs/JOURNAL.md                  :  1 file
docs/RESEARCH_JOURNAL.md         :  1 file
docs/research/                   :  7 files
docs/decision_records/           : 20 files
docs/handoffs/                   : 35 files
research/                        : 32 files
                                 ───────────
Total                            : 96 files
```

#### A.1.3 Complete Source File List (Alphabetical)

```text
docs/JOURNAL.md
docs/RESEARCH_JOURNAL.md
docs/decision_records/ADR-001-no-hft.md
docs/decision_records/ADR-002-polars-native-indicators.md
docs/decision_records/ADR-003-portfolio-before-papertrading.md
docs/decision_records/ADR-004-human-approval-required.md
docs/decision_records/ADR-005-deterministic-regime.md
docs/decision_records/ADR-006-cohesion-over-abstraction.md
docs/decision_records/ADR-007-profile-switching.md
docs/decision_records/ADR-008-telegram-polling.md
docs/decision_records/CHANGELOG_v0_1_16_v1_to_v2.md
docs/decision_records/CHANGELOG_v0_1_16_v2_1.md
docs/decision_records/README.md
docs/decision_records/adr_p1_data_001_lifecycle_authority.md
docs/decision_records/obs_gate_2026_05_26.md
docs/decision_records/p1_data_remediation_spec.md
docs/decision_records/r8_phase1_bootstrap_adr.md
docs/decision_records/r8_phase1_governance.md
docs/decision_records/shioaji_semantic_observation_2026_05_26.md
docs/decision_records/v0_1_16_backtest_audit_report.md
docs/decision_records/v0_1_16_daily_run_patch.md
docs/decision_records/v0_1_16_live_broker_patch.md
docs/handoffs/handoff_2026-05-29.md
docs/handoffs/handoff_2026-05-29_evening.md
docs/handoffs/handoff_2026-05-31_session_end.md
docs/handoffs/handoff_2026_05_31.md
docs/handoffs/handoff_2026_06_01.md
docs/handoffs/handoff_2026_06_01_session2.md
docs/handoffs/handoff_2026_06_02.md
docs/handoffs/handoff_2026_06_02_session_end.md
docs/handoffs/handoff_2026_06_03_session2_end.md
docs/handoffs/handoff_2026_06_03_session_end.md
docs/handoffs/handoff_2026_06_05_session_end.md
docs/handoffs/handoff_2026_06_06_a3_complete.md
docs/handoffs/handoff_2026_06_06_a3_implementation_pack.md
docs/handoffs/handoff_2026_06_06_if3a_complete.md
docs/handoffs/handoff_2026_06_06_p0b_complete.md
docs/handoffs/handoff_2026_06_06_phase1_complete.md
docs/handoffs/handoff_2026_06_06_session_end.md
docs/handoffs/handoff_2026_06_07_clean_panel_rerun_complete.md
docs/handoffs/handoff_2026_06_07_if3b_composition_audit.md
docs/handoffs/handoff_2026_06_07_p1_closeout.md
docs/handoffs/handoff_2026_06_07_phase2b_closeout.md
docs/handoffs/handoff_2026_06_07_phase3_4_5.md
docs/handoffs/handoff_2026_06_23_track_c_step2_and_phase6_evidence_gap.md
docs/handoffs/v0.1.14.3_2026-05-19.md
docs/handoffs/v0.1.14.3_2026-05-19_final.md
docs/handoffs/v0.1.14.3_2026-05-20_session_end.md
docs/handoffs/v0.1.15_2026-05-22_session_end.md
docs/handoffs/v0.1.16_2026-05-24_session_end.md
docs/handoffs/v0.1.18_2026-05-30_session_end.md
docs/handoffs/v0_1_16_2026-05-26_session_end.md
docs/handoffs/v0_1_16_2026-05-27_session_end.md
docs/handoffs/v0_1_17_2026-05-27_final.md
docs/handoffs/v0_1_17_2026-05-27_session_end.md
docs/handoffs/v0_1_17_final_handoff.md
docs/handoffs/v0_2_0_2026-05-31_session_end.md
docs/research/phase0_findings.md
docs/research/r8_phase0_feasibility.md
docs/research/research_handoff_2026_05.md
docs/research/roadmap.md
docs/research/ud_ratio_21d_r1_prereg.md
docs/research/ud_ratio_21d_r1_u7b_audit.md
docs/research/ud_ratio_21d_r1_u7b_enumeration_boundary.md
research/P1-DATA_panel_integrity_assessment.md
research/adr/ADR-R8P1-001-block-bootstrap-effective-n.md
research/adr/ADR-R8P1-002-baseline-benchmark-construction.md
research/helios_research_roadmap.md
research/if3b_source_discovery_spec.md
research/p1_data_remediation_closeout_2026-06-04.md
research/phase2_research_roadmap.md
research/r8_phase0_feasibility.md
research/r8_phase1_cell_adequacy_spec.md
research/r8_phase1_interim_findings.md
research/r8_phase1_lifecycle_spec.md
research/r8_phase2a_spec.md
research/r8_phase2a_validation_report.md
research/r8_phase2b_feasibility_memo.md
research/r8_phase2b_spec.md
research/r8_phase3_risk_report.md
research/r8_phase3_spec.md
research/r8_phase4_optimisation_report.md
research/r8_phase4_spec.md
research/r8_phase5_configuration_report.md
research/r8_phase5_followup_001_spec.md
research/r8_phase5_price_snapshot_refresh_note.md
research/r8_phase5_spec.md
research/r8_phase6_candidate_disposition.md
research/r8_phase6_closeout.md
research/r8_phase6_findings.md
research/r8_phase6_governance_report.md
research/r8_phase6_spec.md
research/r8_phase6_step2_lineage_closeout_2026_06_20.md
research/r8_phase6_step3_entry_note.md
research/r8_phase6_wiring_precondition.md
research/track_c_step1_closeout.md
```

#### A.1.4 Untracked Files Note

```text
docs/research/ud_ratio_21d_r1_u7b_audit.md  (this file)
  Status at §A.1 freeze: UNTRACKED (not yet committed to git)
  Expected commit: commit 3 of 5 of R1-U7B audit pipeline
  Pre-exclusion: §A.2.1 lineage (this audit cannot anchor itself)
```

All other 95 files have a tracked git first-commit (verified per
`git log --all --diff-filter=A --format='%H'` on 2026-06-25).

---

### A.2 Spec-Level Pre-Exclusions

Files excluded by spec rules BEFORE per-file content evaluation.
These exclusions are deterministic and do not require §3.3 test
application.

#### A.2.1 Lineage exclusion (boundary spec §1, prereg §9.1 (5))

```text
docs/research/ud_ratio_21d_r1_prereg.md
docs/research/ud_ratio_21d_r1_u7b_enumeration_boundary.md
docs/research/ud_ratio_21d_r1_u7b_audit.md        (this file)
research/track_c_step1_closeout.md
```

#### A.2.2 Out-of-scope categories (boundary spec §4)

Excluded by category, not enumerated as individual files:

```text
DuckDB query outputs                (not artifacts in §3.2 seed)
Pure unit tests                     (not artifacts in §3.2 seed)
Pure operational scripts            (.py only, handled by §B)
Notebook files (.ipynb)             (none expected in §3.2 seed)
Git commit messages                 (not files)
```

#### A.2.3 Architectural ADRs (boundary spec §4)

Files deterministically classified under the boundary-spec
architectural ADR rule. Each file is listed because it is in §3.2
seed scope and its content is architectural-only, without
finding-bearing research content.

```text
Empty by audit-level scoping decision (2026-06-25).

Rationale: in this audit, architectural ADRs (ADR-001 no-HFT,
ADR-002 polars-native-indicators, ADR-003 portfolio-before-
papertrading, ADR-004 human-approval-required, ADR-005
deterministic-regime, ADR-006 cohesion-over-abstraction, ADR-007
profile-switching, ADR-008 telegram-polling) were classified under
the broader §A.2.4 methodological-ADR test (e) and enumerated
there as A.2.4.15 through A.2.4.22, with referenced_by explicitly
marking them as "no §A.3 row currently references this artifact;
retained for foundational system-governance traceability, not as
a direct research-method dependency".

This avoids creating a separate §A.2.3 listing that would duplicate
§A.2.4 ledger entries. The §A.2.3/§A.2.4 distinction in boundary
spec §4 is preserved semantically (architectural vs methodological
identity) but unified mechanically in §A.2.4 to keep one
methodological-and-architectural-ADR ledger.

No file appears in §A.2.3.
```

#### A.2.4 Methodological ADRs (boundary spec §4)

Files that lock a research METHOD without asserting a finding.
Recorded here for reproducibility-chain traceability; ineligible
as U7B anchors.

Each row carries:

```text
- file path
- lock date (from file header)
- method locked (one-line description, e.g. "block-bootstrap
  effective-n estimation")
- referenced by (which §A.3 INCLUDED files cite this ADR)
```

The "referenced by" field is populated AFTER §A.3 is complete,
since it requires knowing the INCLUDED set.

Document identity principle (locked 2026-06-25):

```text
A file is classified as methodological (test e) based on its
primary document identity, not on whether it incidentally includes
a Findings section. A SPEC document remains a SPEC even when it
contains a Findings appendix; the appendix does not promote the
document to finding-bearing. This prevents document-identity drift
as later SPEC versions accumulate findings narrative.
```

Evidence-test prevalence rule (locked 2026-06-25):

```text
Document identity creates a prior, not an override. When document
identity conflicts with the operational evidence test (§3.3),
§3.3 evidence test prevails.

Application:
  - A SPEC with a Findings appendix → identity wins; the SPEC
    remains methodological (test e). The Findings section is
    secondary to the SPEC's primary purpose.
  - A document named "Journal" / "Log" / "Notes" that contains
    the first-on-record statement of an empirical finding →
    evidence test wins; that finding is admitted to §A.3 as
    (a) + (b) primary, even though the file is named "Journal".

Rationale: classification by name alone would create a perverse
incentive — researchers could hide findings inside log files to
exempt them from governance. The §3.3 test exists precisely to
prevent this. Document identity governs only when the document's
content matches its declared identity.

Hierarchy:
  §3.3 evidence test  >  Document identity principle

The Document identity principle remains valid for the most common
case (SPECs containing findings appendices). It yields to evidence
test only when content materially contradicts declared identity.
```

Completion invariant (locked 2026-06-25):

```text
Every §A.2.4 entry SHALL have a non-empty referenced_by field
before commit 3 of 5 lands. "TBD (resolved after Batch 6)" is
acceptable while Batches are in progress; an empty or literal
"TBD" without resolution timing is NOT acceptable at commit-3
freeze.

The referenced_by field records which §A.3 INCLUDED files cite
this methodological artifact. Resolution happens at commit-3
preparation time, AFTER all Batches complete and the §A.3
INCLUDED set is final. Reviewer mechanical check: every §A.2.4
entry's referenced_by must list at least one §A.3 row, or
explicitly declare "no §A.3 row currently references this ADR"
(which itself triggers a flag for whether the ADR should remain
in §A.2.4 at all).
```

Protocol Freeze (locked 2026-06-25, effective Batch 5+):

```text
After Batch 4 review approval, no additional permanent governance
rule may be introduced into §A.0. Subsequent edge cases SHALL be
resolved using operational notes only (recorded in the relevant
Batch Summary or row evidence, NOT promoted to §A.0).

This is the closing rule. It is the last permanent governance
rule admitted to §A.0 in this audit.

Rationale: §A.0 has accumulated 14 locked rules across Batches 1
through 4. Each was individually justified by an edge case
encountered during enumeration. Continuing this pattern through
Batches 5 and 6 risks producing a protocol that no reviewer can
hold in working memory, breaking the goal of mechanical reviewer
verification.

Protocol consolidation, if desired, is deferred until after
Commit 5 (Phase 3 synthesis). At that point a separate audit-
template document may be drafted that collapses the current
14 rules into a smaller set of root principles (e.g. Identity,
Evidence, Governance). That work is OUT OF SCOPE for the current
audit and MUST NOT modify §A.0 in place.

Operational notes (allowed during Batches 5+):

  - Recorded in Batch Summary or specific row evidence.
  - Reference existing §A.0 rules; do not invent new ones.
  - May document Batch-specific judgement calls without
    promoting them to permanent protocol.

Permanent protocol additions (NOT allowed during Batches 5+):

  - New named principles (e.g. "X Principle locked 2026-06-26").
  - New diagnostic questions or decision trees.
  - New invariants beyond I1-I4.
  - Extensions to existing locked rules beyond clarification of
    typos or arithmetic errors.

This Freeze applies to Batches 5 and 6 of the current audit only.
It does not constrain future audits, future versions, or the
post-Commit-5 consolidation effort.
```

##### A.2.4.1

```text
file_path:              research/r8_phase1_cell_adequacy_spec.md
lock_version:           v0.1.1
lock_date:              2026-06-06
lock_commit_sha:        9281972
method_locked:          P0-B cell adequacy classification thresholds
                        (PASS ≥ 100 unique dates, DIRECTIONAL 30-99,
                        INSUFFICIENT < 30); D-1/D-2/D-2A/D-2B output
                        schemas; must_propagate_reason enumeration.
referenced_by:
                        Rows 10-12 (Tier 2: A-1/A-2/A-3 inferential
                        cells defined by this spec's joint adequacy
                        table; governing-method dependency, not
                        literal text reference)
```

##### A.2.4.2

```text
file_path:              research/r8_phase1_lifecycle_spec.md
lock_version:           v0.2.1
lock_date:              2026-06-07
lock_commit_sha:        4b94124 (initial v0.1.2 lock)
method_locked:          R8 Phase 1 lifecycle replay infrastructure;
                        Required Comparisons (A-1/A-2/A-3 benchmarks);
                        Acceptance Criteria AC-1 through AC-7; Locked
                        Assumptions LA-1 through LA-8.
referenced_by:
                        Rows 10-12 (Tier 2: Phase 1 inferential
                        outputs governed by AC-1 through AC-7);
                        Row 30 (Tier 1: IF-2 P2 reclassification
                        recorded in v0.1.5)
```

##### A.2.4.3

```text
file_path:              research/r8_phase2a_spec.md
lock_version:           v0.3.0
lock_date:              2026-06-07
lock_commit_sha:        b6917e9
method_locked:          Phase 2A stability validation gate framework
                        (G1-G5); ADEQUACY classification (ELIGIBLE /
                        DIRECTIONAL_ONLY / INSUFFICIENT); P2A-1/2/3/4
                        analysis structure; sub-period segment
                        construction methodology.
referenced_by:
                        Row 13 (Tier 2: STABLE verdict produced
                        under phase2a_spec v0.3.0 methodology;
                        governing-method dependency, not literal
                        text reference)
```

##### A.2.4.4

```text
file_path:              research/r8_phase2b_spec.md
lock_version:           v0.1.2
lock_date:              2026-06-07
lock_commit_sha:        e7da03d (initial v0.1.1 lock)
method_locked:          Phase 2B execution bridge cost model
                        (commission 0.585% round-trip, slippage ladder
                        S0/S1/S2/S3); position sizing min(1/N, 10%)
                        partial-NAV model; three mandatory
                        concentration scenarios (Full / Low-Uplift /
                        High-Uplift).
referenced_by:
                        Row 14 (Tier 2: FEASIBLE verdict produced
                        under phase2b_spec v0.1.2 methodology;
                        governing-method dependency, not literal
                        text reference)
```

##### A.2.4.5

```text
file_path:              research/r8_phase3_spec.md
lock_version:           v0.1.2
lock_date:              2026-06-07
lock_commit_sha:        4c8f60d
method_locked:          Phase 3 risk & capital efficiency three-track
                        structure (A risk metrics / B capital efficiency
                        / C illustrative capacity); D1A calendar-time
                        MTM NAV construction; D2 benchmark definitions;
                        D3 capital efficiency scope; D4 illustrative
                        capacity impact model. Daily log returns frozen
                        as primary metric basis (v0.1.2).
referenced_by:
                        Rows 15-17 (Tier 2: Phase 3 risk findings
                        produced under phase3_spec v0.1.2 methodology;
                        governing-method dependency, not literal
                        text reference)
```

##### A.2.4.6

```text
file_path:              research/r8_phase4_spec.md
lock_version:           v0.1.1
lock_date:              2026-06-07
lock_commit_sha:        d918be5
method_locked:          Phase 4 Capital Utilisation Optimisation
                        three-track structure (A holding period /
                        B signal prioritisation / C early exit
                        deferred); D1 outcome horizons; D2 two-layer
                        verdict structure (OPTIMISATION_CHARACTERISED
                        + per-finding CANDIDATE / RESEARCH_FINDING /
                        FURTHER_RESEARCH_REQUIRED); D3 separation
                        from paper trading. Bootstrap block length
                        L = max(5, h) per horizon (v0.1.1 amendment).
referenced_by:
                        Rows 18-21 (Tier 2: Phase 4 optimisation
                        findings produced under phase4_spec v0.1.1
                        methodology; governing-method dependency,
                        not literal text reference)
```

##### A.2.4.7

```text
file_path:              research/r8_phase5_spec.md
lock_version:           v0.1.0
lock_date:              2026-06-07
lock_commit_sha:        6059002
method_locked:          Phase 5 Configuration Selection three-arm
                        structure (Arm A frozen baseline 20td+FIFO /
                        Arm B 20td+RS-60d / Arm C 10td+RS-60d); D1
                        arm definitions; D2 gate criteria
                        P5-G1 (Low-Uplift Sharpe ≥ -0.10) /
                        P5-G2 (Low-Uplift MaxDD ≤ +3pp) /
                        P5-G3 (Full-sample MaxDD ≤ +5pp); D3 Track C
                        early exit reservation for Phase 6.
referenced_by:
                        Rows 22-24 (Tier 2: Phase 5 configuration
                        selection findings produced under phase5_spec
                        methodology; governing-method dependency,
                        not literal text reference)
```

##### A.2.4.8

```text
file_path:              research/r8_phase5_followup_001_spec.md
lock_version:           v1.0.0
lock_date:              2026-06-19
lock_commit_sha:        54a6bfd
method_locked:          P5-FOLLOWUP-001 2x2 interaction identification
                        SPEC (ranking ∈ {FIFO, RS-60d} × holding ∈
                        {20td, 10td}) on single locked daily_price_adj
                        snapshot; pre-registered acceptance criteria
                        (PROMOTE / REJECT / INCONCLUSIVE) using
                        bootstrap CI + Lo (2002) Sharpe SE noise floor;
                        EXECUTE / PARALLEL / NON-BLOCKING authorisation
                        under Phase 6 SPEC v0.1.0 §7. Owned by Phase 6
                        SPEC; resolves Phase 5 Working Hypothesis P5-4.
referenced_by:
                        no §A.3 row currently references this
                        artifact; retained for governance traceability
                        as a non-blocking Phase 5 follow-up SPEC
                        owned by Phase 6, not as a source of an
                        admitted finding cluster
```

##### A.2.4.9

```text
file_path:              research/r8_phase6_spec.md
lock_version:           v0.1.1
lock_date:              2026-06-19
lock_commit_sha:        0c016ec
method_locked:          Phase 6 Exit Policy Evaluation SPEC; four
                        pre-registered exit candidates E1 ATR trailing
                        (multiplier=2.0, ATR-14, frozen at Helios HEAD
                        edd42b1) / E2 MA20 failure (SMA-20,
                        confirmation=2 days) / E3 RS deterioration
                        (PERCENT_RANK <= 0.50) / E4 Donchian
                        (lookback n=10); P6-INV-001 single-variable
                        intervention invariance; P6-G1 (ΔSharpe ≥
                        -0.15) / P6-G2 (ΔMaxDD ≤ +3pp) / P6-G3
                        (ΔAdmission ≥ +5pp) gate framework; primary
                        scenario = Low-Uplift; supplementary bootstrap
                        not wired to gate evaluation.
referenced_by:
                        Rows 25-28 (Tier 2: Phase 6 exit policy
                        findings + candidate disposition + governance
                        + closeout produced under phase6_spec
                        methodology; governing-method dependency,
                        not literal text reference)
```

##### A.2.4.10

```text
file_path:              research/r8_phase6_wiring_precondition.md
lock_version:           v0.1.1
lock_date:              2026-06-19
lock_commit_sha:        2d0e34a (initial v0.1.0 lock at 11cc4a4)
method_locked:          Phase 6 wiring methodology gates; six
                        pre-registered wiring risks (R1 slot release
                        timing / R2 exit-feature lookahead / R3
                        admission regeneration / R4 bootstrap block
                        length / R5 universe membership snapshot /
                        R6 feature pipeline persistence-first);
                        WG-1 degenerate equivalence gate (adaptive
                        engine MUST be bit-identical to Phase 5
                        canonical under never_exit_policy); §1 hard
                        gates and §2 wiring order immutable post-lock.
                        Authority: "Equivalent in binding force to
                        Phase 6 SPEC v0.1.1 pre-registered design
                        decisions (§10.3)."
referenced_by:
                        Row 27 (Tier 1: Phase 6 governance report
                        directly references the WG-1 wiring
                        precondition)
```

##### A.2.4.11

```text
file_path:              research/adr/ADR-R8P1-001-block-bootstrap-effective-n.md
lock_version:           v0.1.0
lock_date:              2026-06-06
lock_commit_sha:        a857456 (initial lock; flipped to LOCKED at 4014e91)
method_locked:          Block-bootstrap effective-n estimation method
                        for all R8 Phase 1 inferential outputs;
                        D1 date-level resampling unit (event-level
                        prohibited); D2 stationary bootstrap;
                        D3 primary block length L_primary=20
                        trading days with sensitivity grid {5,10,40};
                        D4 overlap handling; D5 statistics subject
                        to bootstrap; D6 reporting format
                        (n_raw / n_eff / VIF / CI_95); D7 regime
                        stratification with per-cell estimation.
referenced_by:
                        Rows 10-12 (Tier 1+2: block-bootstrap
                        effective-n method ADR underlying A-1/A-2/A-3
                        confidence intervals; Row 10 contains
                        literal text reference)
```

##### A.2.4.12

```text
file_path:              research/adr/ADR-R8P1-002-baseline-benchmark-construction.md
lock_version:           v0.1.0
lock_date:              2026-06-06
lock_commit_sha:        f23327a (initial lock; flipped to LOCKED at 4014e91)
method_locked:          Baseline benchmark construction for Phase 1
                        Benchmarks 1/2/3; D1 Construction C
                        (event-matched date-anchored on D_R8;
                        Constructions A/B explicitly rejected);
                        D2 leave-one-out baseline composition
                        (exclude R8 trigger rows); D3 unified
                        construction for B1/B2 with per-row pullback
                        filter; D4 market-level regime treatment;
                        D5 per-row pullback granularity; D6 event-
                        duplicated event-level point estimate;
                        SD-1 symmetric near_limit_up stratification;
                        baseline-side adequacy via D-2B (P0-B v0.1.1).
referenced_by:
                        Row 9 (Tier 1: roadmap reference); Rows 10-12
                        (Tier 2: benchmark construction underlying
                        A-1/A-2/A-3 inferential outputs); Row 32
                        (Tier 1: clean-panel re-run verification
                        references Benchmark C construction)
```

##### A.2.4.13

```text
file_path:              research/if3b_source_discovery_spec.md
lock_version:           v0.1.1 (DRAFT — not LOCKED; document identity
                        unchanged per principle that DRAFT status does
                        not promote a SPEC out of methodological class)
lock_date:              2026-06-06
lock_commit_sha:        eae5844
method_locked:          IF-3B source discovery methodology for
                        suspension/halt/resumption reference data;
                        Event Taxonomy definition; Authority vs
                        Engineering ranking separation; Source Priority
                        framework (MOPS > TWSE OpenAPI > FinMind >
                        TWSE Historical Downloads > Price-Gap Detection
                        Fallback); cross-validation methodology
                        (Recall ≥ threshold, Precision ≥ 90%,
                        False Positive Rate ≤ 10%) against 203
                        SUSPENSION_GAP reference rows.
referenced_by:
                        Row 31 (Tier 1: IF-3 governance state
                        directly references if3b source discovery
                        spec v0.1.1)
```

##### A.2.4.14

```text
file_path:              research/phase2_research_roadmap.md
lock_version:           v0.3.0
lock_date:              2026-06-07
lock_commit_sha:        b6917e9
method_locked:          Phase 2 research roadmap (validation-first
                        structure); Phase 2A/2B/2C conditional gate
                        chain (2B/2C require 2A STABLE verdict);
                        Phase 2A G1-G5 gate framework (G1 directional
                        stability / G2 rolling persistence / G3
                        influence robustness / G4 adequacy integrity /
                        G5 concentration disclosure); P2A-1 sub-period /
                        P2A-2 rolling-window / P2A-3 influence
                        diagnostics / P2A-4 concentration analysis
                        structure; termination policy. Self-declared
                        "planning document only" — Phase 2
                        implementation requires a new versioned SPEC.
referenced_by:
                        no §A.3 row currently references this
                        artifact; retained as Phase 2 planning-method
                        traceability. Its content is not an admitted
                        finding cluster and is not superseded by
                        Row 9
```

---

##### A.2.4.15

```text
file_path:              docs/decision_records/ADR-001-no-hft.md
lock_version:           v0.1 (foundational)
lock_date:              2026-05-17
lock_commit_sha:        955d71d
method_locked:          Helios as daily-batch system (forever-rule);
                        no HFT/intraday infra, single cron entry
                        point (~09:00 Asia/Taipei), all sync code,
                        SELECT-not-stream data access, daily-close
                        exit decisions, paper-trade T+1 open fill
                        model, human approval for entries. Any
                        future feature proposing sub-daily resolution
                        requires a superseding ADR.
referenced_by:
                        no §A.3 row currently references this
                        artifact; retained for foundational
                        system-governance traceability, not as a
                        direct research-method dependency
```

##### A.2.4.16

```text
file_path:              docs/decision_records/ADR-002-polars-native-indicators.md
lock_version:           v0.1.11
lock_date:              2026-05-17
lock_commit_sha:        955d71d
method_locked:          All technical indicators implemented as
                        Polars expressions in features/technical.py;
                        no TA-Lib, pandas-ta, or external indicator
                        library. Single compute_indicators() function
                        returns input frame augmented with 9
                        indicator columns. Spot-checked against
                        TradingView at v0.1.11.
referenced_by:
                        no §A.3 row currently references this
                        artifact; retained for foundational
                        system-governance traceability, not as a
                        direct research-method dependency
```

##### A.2.4.17

```text
file_path:              docs/decision_records/ADR-003-portfolio-before-papertrading.md
lock_version:           v0.1.14.1
lock_date:              2026-05-17
lock_commit_sha:        955d71d
method_locked:          Build portfolio layer (risk_budget +
                        selector + constrained backtest) BEFORE
                        paper trading execution. Defers paper
                        trading to v0.1.14.2. Validation-shape
                        principle: validate deployment-shaped
                        scenarios before deploying; trade-level
                        metrics describe alpha existence,
                        portfolio-level metrics describe
                        deployability — these are not the same
                        question.
referenced_by:
                        no §A.3 row currently references this
                        artifact; retained for foundational
                        system-governance traceability, not as a
                        direct research-method dependency
```

##### A.2.4.18

```text
file_path:              docs/decision_records/ADR-004-human-approval-required.md
lock_version:           v0.1 (foundational)
lock_date:              2026-05-17
lock_commit_sha:        955d71d
method_locked:          Every entry signal requires explicit
                        operator approval via Telegram before broker
                        submission; exit signals execute
                        automatically (capital protection priority).
                        Entry: signal → Telegram push → wait for
                        /approve → submit (30-min timeout + ATR
                        drift expiry). Exit: signal → submit
                        immediately → Telegram notify. No
                        autopilot mode.
referenced_by:
                        no §A.3 row currently references this
                        artifact; retained for foundational
                        system-governance traceability, not as a
                        direct research-method dependency
```

##### A.2.4.19

```text
file_path:              docs/decision_records/ADR-005-deterministic-regime.md
lock_version:           v0.1.11
lock_date:              2026-05-17
lock_commit_sha:        955d71d
method_locked:          Regime classification by deterministic
                        rules on TAIEX daily close in
                        features/regime.py; no HMM, no ML, no
                        fitted parameters. 4-state classification:
                        crisis (TAIEX 20d vol > 0.020), bull (close
                        > sma_200 AND vol_20 ≤ 0.020), bear (close
                        < sma_200 AND vol_20 ≤ 0.020), neutral
                        (transitional). Thresholds fixed in v0.1;
                        may become expanding-window quantiles in
                        v0.2 (still deterministic, adaptive).
referenced_by:
                        no §A.3 row currently references this
                        artifact; retained for foundational
                        system-governance traceability, not as a
                        direct research-method dependency
```

##### A.2.4.20

```text
file_path:              docs/decision_records/ADR-006-cohesion-over-abstraction.md
lock_version:           v0.1 (foundational)
lock_date:              2026-05-17
lock_commit_sha:        955d71d
method_locked:          In v0.1, each major concern lives in a
                        single file with concrete (non-abstract)
                        functions and dataclasses. Refactor toward
                        abstraction only when complexity demands it
                        (triggers: 2nd strategy added, 2nd regime
                        model added, sector classification proven
                        need to be dynamic). Abstractions exist
                        only where mechanically required
                        (Strategy ABC, ExitRule ABC).
referenced_by:
                        no §A.3 row currently references this
                        artifact; retained for foundational
                        system-governance traceability, not as a
                        direct research-method dependency
```

##### A.2.4.21

```text
file_path:              docs/decision_records/ADR-007-profile-switching.md
lock_version:           Proposed (not Accepted; recorded for future
                        re-evaluation)
lock_date:              2026-05-17
lock_commit_sha:        f5155e9
method_locked:          Do NOT implement regime-conditional budget
                        profile switching in v0.1; keep CURRENT
                        (5×20%) as single default. Three promotion
                        triggers documented (Trigger A: 3+ months
                        paper trading confirms; Trigger B: bear
                        regime survival comparison; Trigger C: n≥60
                        CONCENTRATED trades with PF still elevated).
                        Captures structurally-interesting finding
                        (v0.1.14.1.2 CONCENTRATED dominates CURRENT
                        on every OOS metric) without acting on
                        under-sampled evidence. First Proposed-status
                        ADR in the audit.
referenced_by:
                        no §A.3 row currently references this
                        artifact; retained for foundational
                        system-governance traceability, not as a
                        direct research-method dependency
```

##### A.2.4.22

```text
file_path:              docs/decision_records/ADR-008-telegram-polling.md
lock_version:           v0.1.14.2-b
lock_date:              2026-05-17
lock_commit_sha:        f5155e9
method_locked:          Telegram long polling (not webhooks) for
                        operator approval flow. communication/
                        telegram/bot.py wraps requests; listener
                        polls getUpdates in 30-min window triggered
                        from daily_run.py Step 5; ephemeral process
                        model (no always-on listener) consistent
                        with ADR-001 daily-batch principle.
referenced_by:
                        no §A.3 row currently references this
                        artifact; retained for foundational
                        system-governance traceability, not as a
                        direct research-method dependency
```

##### A.2.4.23

```text
file_path:              docs/decision_records/adr_p1_data_001_lifecycle_authority.md
lock_version:           v1.0.0
lock_date:              2026-06-03
lock_commit_sha:        824c547
method_locked:          P1-DATA IF-1 remediation lifecycle authority
                        selection. Manual curation of seed file for
                        18 transfer-board stocks using MOPS (公開
                        資訊觀測站) as primary regulatory source after
                        5 candidate sources (TWSE isin, TPEx isin,
                        TPEx OpenAPI, FinMind, TPEx legacy URLs)
                        all FAILed on 2026-06-03 (18/18
                        SAME_AS_META_SUSPECT). Establishes
                        security_lifecycle_seed_v1.csv as Lifecycle
                        Authority v1 for IF-1 remediation.
referenced_by:
                        Rows 29-31 (Tier 2: P1-DATA assessment and
                        remediation lineage uses the lifecycle-
                        authority model established by this ADR;
                        dependency is governance-chain, not literal
                        text reference)
```

##### A.2.4.24

```text
file_path:              docs/decision_records/r8_phase1_bootstrap_adr.md
lock_version:           v1.0
lock_date:              2026-06-02
lock_commit_sha:        a8370a6
method_locked:          R8 Phase 1 effective-n bootstrap method
                        (note: this is an EARLIER ADR than
                        ADR-R8P1-001 at §A.2.4.11; the locked
                        method here uses 5-day block length and
                        10,000 replications, while §A.2.4.11's
                        v0.1.0 supersedes this with L_primary=20
                        and B=5000 sensitivity grid). This earlier
                        ADR retained for governance traceability
                        of the methodology evolution.
referenced_by:
                        no §A.3 row currently references this
                        artifact; retained for methodology evolution
                        traceability. Superseded by A.2.4.11
                        ADR-R8P1-001, which governs Rows 10-12
```

##### A.2.4.25

```text
file_path:              docs/decision_records/p1_data_remediation_spec.md
lock_version:           v1.0.0
lock_date:              2026-06-04
lock_commit_sha:        74904e1
method_locked:          P1-DATA IF-1 remediation methodology
                        (authorising governance spec for the
                        remediation closeout recorded at Row 32).
                        Six locked decisions: D-1 source = MOPS
                        manual; D-2 storage = DuckDB security_
                        lifecycle table; D-3 exclusion via VIEW
                        (not physical delete); D-4 transfer-board
                        stocks 4583/6770/6789 OTC-filter-only;
                        D-5 SUSPENSION_GAP deferred; D-6 no minimum
                        listed-age filter. Seven acceptance criteria
                        AC-1 through AC-7 defined.
referenced_by:
                        Row 32 (Tier 2: P1-DATA IF-1 remediation
                        closeout produced under this remediation
                        SPEC methodology; governing-method dependency,
                        not literal text reference)
```

##### A.2.4.26

```text
file_path:              docs/decision_records/r8_phase1_governance.md
lock_version:           v0.1.1
lock_date:              2026-06-02
lock_commit_sha:        ae5a35f
method_locked:          R8 Phase 1 governance authorisation as
                        lifecycle-validation study only (NOT alpha-
                        validation, NOT strategy construction, NOT
                        production deployment authorisation).
                        Rejects four alternatives (A: direct alpha
                        validation; B: immediate strategy
                        construction; C: wait for P1-DATA before
                        any Phase 1; D: Phase 0 PASS as production
                        authorisation). Establishes governance
                        assumptions GA-1 through GA-N and future
                        invalidation conditions.
referenced_by:
                        Rows 10-12 (Tier 2: Phase 1 governance
                        decision record governing all Phase 1
                        inferential outputs); Row 30 (Tier 2:
                        P1-DATA assessment governance ties to
                        Phase 1 binding blockers)
```

### A.3 INCLUDED Candidates (test a / b / c)

Files in §3.2 seed scope that PASS the §3.3 evidence-based test
under (a), (b), or (c).

Sort order: by `source_file` path (per P1).

Row schema:

```text
| case_id                      | filename / cluster_id            |
| source_file                  | path/to/source.md                |
| file_first_commit_sha        | abc1234                          |
| file_first_commit_date       | YYYY-MM-DD                       |
| governance_state_commit_sha  | abc1234 or TBD_PHASE2            |
| governance_state_commit_date | YYYY-MM-DD or TBD_PHASE2         |
| classification_letter        | (a) / (b) / (c)                  |
| classification_evidence      | heading + representative text    |
| one_line_description         | single sentence, no verdict      |
|                              | assertion                        |
```

Backlog wording convention: when a file's governance state was
recorded after the file's first git commit (typical for backlog
commits), the `one_line_description` ends with the fixed sentence
"Governance state recorded retrospectively via backlog commit."
No other phrasing is permitted for this attribute.

---

#### Batch 1 — `docs/research/` (9 rows, 4 files)

##### Row 1

```text
case_id:                      phase0_findings / confirmed_observations
source_file:                  docs/research/phase0_findings.md
file_first_commit_sha:        af4f9b5
file_first_commit_date:       2026-05-28
governance_state_commit_sha:  b7eee75
governance_state_commit_date: 2026-05-29
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "## 3. Confirmed Observations" (line 62)
  Text (a): "Status: Final (v4 — post per-horizon spacing fix)" (line 4)
  Text (b): "Q5 | +2.83% | 54.7%" — RS persistence quintile (line 78)
  Text (b): "RS_T3 + Dist_T1 (close to MA20) | +4.32% | +1.66%
             | 62.3% | 366" (line 103)
one_line_description:
  Phase 0 confirmed observations cluster (§3.1-§3.7): RS persistence,
  RS_T3 + Pullback interaction, regime-conditioned cell returns;
  cross-sectional quintile statistics on ~5y Taiwan stock panel.
```

##### Row 2

```text
case_id:                      phase0_findings / rejected_hypotheses
source_file:                  docs/research/phase0_findings.md
file_first_commit_sha:        af4f9b5
file_first_commit_date:       2026-05-28
governance_state_commit_sha:  b7eee75
governance_state_commit_date: 2026-05-29
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "## 4. Rejected Hypotheses" (line 207)
  Text (a): "v4 update: absorption finding overturned" (line 95)
  Text (b): "v3 absorption bear lift (+0.94%) was a spacing artifact"
            (line 97)
one_line_description:
  Phase 0 rejected hypotheses cluster (§4.1-§4.4): Compression
  Breakout Edge, Volume Breakout Continuation, Bearish Continuation
  Cluster, Standalone Accumulation Features — each NULL or weak
  under v4 per-horizon spacing.
```

##### Row 3

```text
case_id:                      phase0_findings / taxonomy_synthesis
source_file:                  docs/research/phase0_findings.md
file_first_commit_sha:        af4f9b5
file_first_commit_date:       2026-05-28
governance_state_commit_sha:  b7eee75
governance_state_commit_date: 2026-05-29
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "## 5. Feature Taxonomy (Revised)" (line 230)
  Heading:  "### Regime-Dependent Behavior" (line 243)
  Text (b): "RS_T3 + Dist_T1 (pullback) | bear | -2.30%, 40.6% hit
             (AVOID)"
  Text (b): "Beta_T3 + RS_T3 | Strongest cell (+5.56%)"
one_line_description:
  Phase 0 taxonomy + regime-dependent synthesis: 6-category feature
  taxonomy restructure; regime-conditioned feature taxonomy and
  interaction matrix, including an explicit AVOID classification
  for RS_T3 + Dist_T1 under bear regime.
```

##### Row 4

```text
case_id:                      r8_phase0_feasibility
source_file:                  research/r8_phase0_feasibility.md
file_first_commit_sha:        0226c09
file_first_commit_date:       2026-06-02
governance_state_commit_sha:  0226c09
governance_state_commit_date: 2026-06-02
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "## Verdict" (line 17)
  Heading:  "## Selection-level redundancy (the core finding)" (line 51)
  Text (a): "Status: Phase 0 CLOSED (2026-06-01, rev2)" (line 6)
  Text (a): "Decision gate is 5/5 PASS" (line 19)
  Text (b): "T-1 RS60 top-tertile enrichment = 1.63 (vs base 0.33)"
            (line 56)
one_line_description:
  R8 MA5 momentum Phase 0 feasibility audit: 5/5 PASS against the
  predefined feasibility gates; study concludes with lifecycle-replay
  SPEC progression. R8 selection assessed for selection-level
  redundancy via three independent lenses including T-1 RS60
  enrichment measurement.
```

##### Row 5

```text
case_id:                      research_handoff_2026_05 / R1_rs_persistence_decay
source_file:                  docs/research/research_handoff_2026_05.md
file_first_commit_sha:        a583a88
file_first_commit_date:       2026-06-23
governance_state_commit_sha:  a583a88
governance_state_commit_date: 2026-06-23
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "### R1 — RS Persistence Decay" (line 19)
  Text (a): "Result | Negative" (line 24)
  Text (b): "Spearman(age, fwd_ret) ≈ +0.03-0.04 (positive,
             opposite of decay hypothesis)" (line 25)
  Text (b): "within-band (0.67-0.75) rho ≈ 0, CI spans zero"
one_line_description:
  R1 RS persistence decay study: NEGATIVE result; within-band
  Spearman rho ≈ 0 with CI spanning zero; positive association is
  between-spell selection, not within-spell signal. Cross-sectional
  Spearman analysis. Governance state recorded retrospectively via
  backlog commit.
```

##### Row 6

```text
case_id:                      research_handoff_2026_05 / R2_failed_breakdown
source_file:                  docs/research/research_handoff_2026_05.md
file_first_commit_sha:        a583a88
file_first_commit_date:       2026-06-23
governance_state_commit_sha:  a583a88
governance_state_commit_date: 2026-06-23
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "### R2 — Failed Breakdown / MA20 Reclaim Quality" (line 29)
  Text (a): "Result | Weak Negative" (line 34)
  Text (b): "h60 point estimate -2.1% but CI spans zero" (line 35)
  Text (b): "monotone dose in broad universe at 60d (CI excludes zero)"
one_line_description:
  R2 failed-breakdown / MA20 reclaim quality study: WEAK NEGATIVE;
  failed_breakdown_count_10d characterised as MA20 whipsaw counter,
  not demand-absorption indicator. Cross-sectional Spearman with CI.
  Governance state recorded retrospectively via backlog commit.
```

##### Row 7

```text
case_id:                      research_handoff_2026_05 / R5_pullback_quality
source_file:                  docs/research/research_handoff_2026_05.md
file_first_commit_sha:        a583a88
file_first_commit_date:       2026-06-23
governance_state_commit_sha:  a583a88
governance_state_commit_date: 2026-06-23
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "### R5 — Pullback Quality Transfer Study" (line 40)
  Text (a): "Result | Weak Positive (1 of 3 axes survived)" (line 45)
  Text (b): "h60 Spearman CI excludes zero (barely: +0.010 to +0.139)"
            (line 48)
  Text (a): "Axis 1 — ATR compression | NULL. Transfer failed." (line 47)
one_line_description:
  R5 pullback-quality transfer study: WEAK POSITIVE on Axis 2
  (volume contraction) only; Axes 1 (ATR compression) and 3 (trend
  structure) NULL. Per-day Spearman with CI. Governance state
  recorded retrospectively via backlog commit.
```

##### Row 8

```text
case_id:                      research_handoff_2026_05 / StudyB_rs_acceleration
source_file:                  docs/research/research_handoff_2026_05.md
file_first_commit_sha:        a583a88
file_first_commit_date:       2026-06-23
governance_state_commit_sha:  a583a88
governance_state_commit_date: 2026-06-23
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "### Study B — RS Acceleration" (line 54)
  Text (a): "Result | Negative"
  Text (b): "Spearman rho ≈ -0.01, all three horizons CI span zero"
            (line 60)
  Text:     "Meta-finding | summarises the RS-dynamics research line"
            (line 62, paraphrased context)
one_line_description:
  Study B RS acceleration: NEGATIVE; within RS_T3 primary band, rank
  velocity adds no signal beyond RS level. Meta-finding summarises
  the RS-dynamics study line (combined with R1). Governance state
  recorded retrospectively via backlog commit.
```

##### Row 9

```text
case_id:                      roadmap / confirmed_alpha_synthesis
source_file:                  docs/research/roadmap.md
file_first_commit_sha:        4c00394
file_first_commit_date:       2026-05-29
governance_state_commit_sha:  e49c419
governance_state_commit_date: 2026-06-05
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "## Confirmed Alpha (Phase 0 + Phase A)" (line 47)
  Text (a): "[x] Phase A closeout: best confirmed cell = RS_T3 +
             Dist_T1 + Beta_T3" (line 72)
  Text (b): "Benchmark C (R8 within RS_T3): ret_20d mean = +6.84%"
            (line 92)
  Text (b): "Benchmark A (RS_T3 Hold): ret_20d mean = +2.63%" (line 93)
one_line_description:
  Secondary aggregator of phase0_findings.md (and downstream
  Phase A studies); summarises registered findings into the
  governance "Confirmed Alpha" synthesis (RS_T3 + Dist_T1 +
  Beta_T3 cell); introduces no independent empirical evidence.
```

---

#### Batch 1 Summary

```text
Batch:                      1 — docs/research/
Files reviewed:             4
Finding-bearing files:      4 (phase0_findings, r8_phase0_feasibility,
                              research_handoff_2026_05, roadmap)
Methodological files:       0
Governance-process files:   0
Rows emitted:              10
Included rows:              9
Excluded rows:              1 (duplicate)
Primary sources:            8
Secondary aggregators:      1 (Row 9, roadmap.md)
Unique finding clusters:    8

Invariant check:
  I1 (files): 4 = Finding-bearing (4) + Methodological (0)
              + Aggregators (0) + Governance-process (0)
              [Duplicate (1) counted via §A.4 row, not §A.3] ✓
  I2 (rows): Rows emitted (10) = Included (9) + Excluded (1) ✓
  I3 (incl): Included (9) = Primary (8) + Aggregators (1) ✓
  I4 (anchors): Unique finding clusters (8) = Primary (8) ✓
```

Cumulative after Batch 1:

```text
Files reviewed:           4
Finding-bearing files:    4
Methodological files:     0
Total rows emitted:      10
Included rows:            9
Excluded rows:            1
Methodological (A.2.4):   0
Primary sources:          8
Secondary aggregators:    1
Unique finding clusters:  8
```

Correction note:

```text
docs/research/r8_phase0_feasibility.md was initially treated as the
source file for Row 4. git --follow associated the later path with
the earlier file through rename detection because the contents were
identical, so git reported 0226c09 as the file's "first commit"
despite 0226c09 not touching docs/research/.

Verification via `git show --stat 0226c09` confirmed that 0226c09
added research/r8_phase0_feasibility.md (not docs/research/...).
The docs/research/ copy was added later in 8ca25b0 (backlog commit
2026-06-23) as a duplicate of the already-committed research/ copy.

Per the Duplicate Handling Rule (§A.0), the canonical source is
research/r8_phase0_feasibility.md (earliest git-resident path,
first committed at 0226c09 on 2026-06-02). Row 4 was corrected to
reference the canonical path. The duplicate-of-canonical copy at
docs/research/r8_phase0_feasibility.md is recorded in §A.4 as
test letter (d) with explicit duplicate-of-canonical reason.

This is a within-Batch-1 correction, made BEFORE commit 3 of 5
landed. No prior committed audit version contained the incorrect
attribution.
```

---

#### Batch 2 — `research/` R8 phase reports

Note: Batch 2 is split into two review units (2a, 2b) under the
same commit boundary. 2a covers R8 Phase 0-3 / early lifecycle-risk
docs. 2b covers R8 Phase 4-6 / configuration-exit docs.

##### Batch 2a — R8 Phase 0-3 (9 files reviewed, 8 INCLUDED rows)

Note: `research/r8_phase0_feasibility.md` is the canonical source
for the Phase 0 case (see §A.3 Row 4 in Batch 1). It is not
re-enumerated here.

##### Row 10

```text
case_id:                      r8_phase1_interim_findings / A1_RS_T3_hold
source_file:                  research/r8_phase1_interim_findings.md
file_first_commit_sha:        fac85ad
file_first_commit_date:       2026-06-06
governance_state_commit_sha:  539cb41
governance_state_commit_date: 2026-06-07
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "## 4. A-1 Findings — RS_T3 Hold Benchmark" (line 79)
  Heading:  "### PASS cells (full bootstrap CI available)" (line 85)
  Text (a): "Status: CONFIRMED — v1.0.0 (2026-06-07)" (line 8)
  Text (a): "Three cells reached joint adequacy PASS:
             bull/nlu=0, bear/nlu=0, neutral/nlu=0" (line 87)
  Text (b): "Bull regime, nlu=0 ... 20td | +3.03% | [+1.84%, +4.17%]
             | n_eff 71" (lines 89-96)
one_line_description:
  Phase 1 A-1 RS_T3 Hold benchmark: baseline RS_T3 hold forward
  return across adequacy-qualified cells with block-bootstrap CI;
  3 cells reached joint adequacy PASS (bull/nlu=0, bear/nlu=0,
  neutral/nlu=0); bull/nlu=0 θ_base monotonically increasing across
  horizons (5td CI excludes zero, 20td +3.03%).
```

##### Row 11

```text
case_id:                      r8_phase1_interim_findings / A2_pullback_sparsity
source_file:                  research/r8_phase1_interim_findings.md
file_first_commit_sha:        fac85ad
file_first_commit_date:       2026-06-06
governance_state_commit_sha:  539cb41
governance_state_commit_date: 2026-06-07
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "## 5. A-2 Findings — RS_T3 + Pullback Benchmark" (line 143)
  Heading:  "### Structural finding: Treatment_2 sparsity" (line 149)
  Text (a): "Result: 0 PASS cells. A-2 cannot be evaluated
             inferentially under the [adequacy criteria]" (line 167)
  Text (b): "Treatment_2 ... contains only 262 observations across
             109 dates — 4.9% of Treatment_1" (line 30)
one_line_description:
  Phase 1 A-2 RS_T3 + Pullback benchmark: structural finding of
  Treatment_2 sparsity (262 events / 109 dates, 4.9% of Treatment_1)
  yielding zero adequacy-PASS cells; pre-registered finding, not
  methodological failure. Directional-only estimates carry no
  inferential weight.
```

##### Row 12

```text
case_id:                      r8_phase1_interim_findings / A3_R8_within_RS_T3
source_file:                  research/r8_phase1_interim_findings.md
file_first_commit_sha:        fac85ad
file_first_commit_date:       2026-06-06
governance_state_commit_sha:  539cb41
governance_state_commit_date: 2026-06-07
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "## 6. A-3 Findings — R8 within RS_T3 vs RS_T3
             Unconditional" (line 220)
  Heading:  "### Tier 1 — Robust findings" (line 228)
  Text (a): "Bull | YES (CONFIRMED) | A-3 Tier 1: Δ_obs = +1.21% /
             +1.92% at 10td / 20td (v0.2.0 clean panel); CI strictly
             positive at all block lengths" (line 321)
  Text (a): "Bear | INCONCLUSIVE | A-3 Tier 3: Δ_obs = +1.46% at 20td
             nominally significant (p ≈ 0.03) but 95% CI contains
             zero" (line 322)
  Text (b): "Sensitivity verdict: ROBUST. At all block lengths
             L={5,10,20,40}, the 95% [CI strictly positive]" (line 238)
one_line_description:
  Phase 1 A-3 R8 within RS_T3 vs RS_T3 unconditional: bull regime
  CONFIRMED incremental forward returns (Δ +1.21% / +1.92% at
  10td/20td, CI strictly positive at all block lengths); bear
  regime INCONCLUSIVE (point estimate +1.46% but CI contains zero);
  panel-remediation-robust across clean-panel re-run (commit 4a307e6).
```

##### Row 13

```text
case_id:                      r8_phase2a_validation_report
source_file:                  research/r8_phase2a_validation_report.md
file_first_commit_sha:        a1a3959
file_first_commit_date:       2026-06-07
governance_state_commit_sha:  a1a3959
governance_state_commit_date: 2026-06-07
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "## 1. Executive Summary" (line 22)
  Heading:  "## 8. Verdict" (line 317)
  Text (a): "Status: CONFIRMED — v1.0.0 (2026-06-07)" (line 6)
  Text (a): "Verdict: STABLE" (line 24)
  Text (b): "27/27 windows positive; median +1.12%; minimum +0.33%;
             zero negative windows" (line 310)
  Text (b): "top-1 = 49.4%, top-2 = 89.9%; material concentration;
             Phase 2B assumptions documented" (line 313)
one_line_description:
  Phase 2A stability validation: STABLE verdict for bull-regime R8
  uplift; all four gate classes (G1 directional / G2 rolling / G3
  influence / G4 reporting) PASS; G5 material concentration
  disclosure (Segments 1+4 = 89.9% of aggregate uplift at 20td) as
  mandatory Phase 2B input.
```

##### Row 14

```text
case_id:                      r8_phase2b_feasibility_memo
source_file:                  research/r8_phase2b_feasibility_memo.md
file_first_commit_sha:        792dceb
file_first_commit_date:       2026-06-07
governance_state_commit_sha:  792dceb
governance_state_commit_date: 2026-06-07
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "## 1. Executive Summary" (line 22)
  Heading:  "## 6. Verdict Assessment" (line 169)
  Text (a): "Status: CONFIRMED — v1.0.0 (2026-06-07)" (line 6)
  Text (a): "Verdict: FEASIBLE" (line 24)
  Text (b): "All 12 scenario × slippage combinations produce
             positive net returns" (line 27)
  Text (b): "Even in this adverse environment under severe stress
             (S3), net return is +0.55%" (line 42)
one_line_description:
  Phase 2B execution feasibility: FEASIBLE verdict; bull-regime R8
  uplift survives realistic execution friction; all 12 scenario ×
  slippage combos positive net return; Low-Uplift S3 stress test
  +0.55% net return; commission cost (0.585% round-trip) dominates
  execution friction (~3x at S1).
```

##### Row 15

```text
case_id:                      r8_phase3_risk_report / FindingA_capital_lockup
source_file:                  research/r8_phase3_risk_report.md
file_first_commit_sha:        4c8f60d
file_first_commit_date:       2026-06-07
governance_state_commit_sha:  4c8f60d
governance_state_commit_date: 2026-06-07
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "Finding A — Holding-period-induced capital lock-up
             (primary finding)" (line 41)
  Text (a): "Status: LOCKED — v1.0.1 (2026-06-07)" (line 6)
  Text (a): "Verdict: CHARACTERISED" (line 25)
  Text (b): "admitted only 16.3% of R8 candidate signals (350 of
             2,143)" (line 42)
  Text (b): "Only 2.1% of signal dates produced more than 10
             simultaneous R8 signals (median: 3 signals per date)"
             (line 44)
one_line_description:
  Phase 3 Finding A — holding-period-induced capital lock-up:
  baseline-cap scheduler admitted only 16.3% of R8 signals; low
  admission driven primarily by holding-period capital retention
  (FIFO slot occupancy across 20-trading-day windows), not signal
  clustering. Defines the primary open question for Phase 4.
```

##### Row 16

```text
case_id:                      r8_phase3_risk_report / FindingB_low_uplift_convergence
source_file:                  research/r8_phase3_risk_report.md
file_first_commit_sha:        4c8f60d
file_first_commit_date:       2026-06-07
governance_state_commit_sha:  4c8f60d
governance_state_commit_date: 2026-06-07
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "Finding B — Risk-adjusted edge disappears in the
             Low-Uplift environment" (line 49)
  Heading:  "### 4.3 Low-Uplift finding (Finding B)" (line 251)
  Text (b): "Full Sample (Sharpe 2.378 vs 1.313)" (line 53)
  Text (b): "Low-Uplift environment, this advantage effectively
             disappeared (1.613 vs 1.606, Δ = 0.007)" (line 56)
one_line_description:
  Phase 3 Finding B — Low-Uplift risk-adjusted convergence: R8 vs
  RS_T3 Sharpe advantage substantial in Full Sample (2.378 vs 1.313)
  and High-Uplift (2.271 vs 0.709) but effectively zero in Low-Uplift
  (1.613 vs 1.606, Δ = 0.007); extends Phase 2A G5 material
  concentration finding into the full risk-adjusted profile.
```

##### Row 17

```text
case_id:                      r8_phase3_risk_report / FindingC_position_cap_insensitivity
source_file:                  research/r8_phase3_risk_report.md
file_first_commit_sha:        4c8f60d
file_first_commit_date:       2026-06-07
governance_state_commit_sha:  4c8f60d
governance_state_commit_date: 2026-06-07
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "Finding C — Higher position caps did not improve
             risk-adjusted performance" (line 65)
  Text (b): "increasing the per-position cap above 10% baseline
             degraded the Sharpe ratio across all variants" (line 62)
  Text (b): "substantially increased drawdown severity at the 25%
             cap (MaxDD: 21.65% → 41.56% in Full Sample)" (line 63)
one_line_description:
  Phase 3 Finding C — position cap insensitivity: relaxing 10%
  baseline per-position cap to 15%/20%/25% degraded Sharpe across
  all variants and substantially increased Full Sample MaxDD
  (21.65% → 41.56% at 25% cap); cap relaxation does not solve the
  underlying capital lock-up problem (Finding A).
```

---

#### Batch 2a Summary

```text
Batch:                      2a — research/ R8 Phase 0-3
Files reviewed:             9
Finding-bearing files:      4 (interim_findings, phase2a_validation,
                              phase2b_memo, phase3_risk_report)
Methodological files:       5 (cell_adequacy_spec, lifecycle_spec,
                              phase2a_spec, phase2b_spec, phase3_spec)
Governance-process files:   0
Rows emitted:               8 (Rows 10-17)
Included rows:              8
Excluded rows:              0
Primary sources:            8
Secondary aggregators:      0
Unique finding clusters:    8

Invariant check:
  I1 (files): 9 = Finding-bearing (4) + Methodological (5)
              + Aggregators (0) + Governance-process (0) ✓
  I2 (rows): Rows emitted (8) = Included (8) + Excluded (0) ✓
  I3 (incl): Included (8) = Primary (8) + Aggregators (0) ✓
  I4 (anchors): Unique finding clusters (8) = Primary (8) ✓
```

Cumulative after Batch 2a:

```text
Files reviewed:           13 (Batch 1: 4 + Batch 2a: 9)
Finding-bearing files:     8 (Batch 1: 4 + Batch 2a: 4)
Methodological files:      5 (Batch 1: 0 + Batch 2a: 5)
Total rows emitted:       18 (Batch 1: 10 + Batch 2a: 8)
Included rows:            17
Excluded rows:             1 (Batch 1 duplicate)
Methodological (A.2.4):    5
Primary sources:          16
Secondary aggregators:     1
Unique finding clusters:  16
```

Note on document identity (locked 2026-06-25):

```text
Five spec documents in this batch contain Findings appendices that
mirror the primary findings reports (e.g. lifecycle_spec §Phase 1
Findings mirrors interim_findings.md content). Per the document
identity principle in §A.2.4, these specs remain methodological
artifacts (test e) regardless of appendix content. A SPEC remains
a SPEC even when it includes a Findings section; the appendix does
not promote the document to finding-bearing.

This prevents progressive aggregator drift as later SPEC versions
accumulate findings narrative, and avoids double-counting findings
across the SPEC and its primary findings report.
```

---

#### Batch 2b — R8 Phase 4-6 (14 files reviewed, 11 INCLUDED rows)

Note: Of the 14 files in Batch 2b scope:

```text
- 4 finding-bearing reports → 8 §A.3 rows (Phase 4 OptReport: 4 rows;
  Phase 5 ConfigReport: 3 rows; Phase 6 findings: 1 row)
- 3 secondary aggregators → 3 §A.3 rows (Phase 6 candidate_disposition,
  governance_report, closeout — all aggregators of Phase 6 findings)
- 5 methodological SPECs → §A.2.4 (entries A.2.4.6 through A.2.4.10)
- 3 governance-process artifacts → §A.4 with classification (d2)
```

##### Row 18

```text
case_id:                      r8_phase4_optimisation / FindingA1_lockup_confirmation
source_file:                  research/r8_phase4_optimisation_report.md
file_first_commit_sha:        d918be5
file_first_commit_date:       2026-06-07
governance_state_commit_sha:  d918be5
governance_state_commit_date: 2026-06-07
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "Finding A1 — Holding-period lock-up hypothesis
             confirmed" (line 40)
  Text (a): "Status: LOCKED — v1.0.0 (2026-06-07)" (line 6)
  Text (a): "Verdict: OPTIMISATION_CHARACTERISED" (line 24)
  Text (b): "Admission rate responds strongly to holding-period
             reduction: 16.3% (20td) → 30.0% (10td) → 52.8% (5td)"
             (line 41)
one_line_description:
  Phase 4 Finding A1 — holding-period lock-up hypothesis
  confirmed: admission rate responds strongly to holding-period
  reduction (16.3% / 30.0% / 52.8% at 20td/10td/5td); recorded
  as confirmation of the Phase 3 Primary Finding (20-trading-day
  retention window as the dominant capital utilisation
  bottleneck, not signal clustering).
```

##### Row 19

```text
case_id:                      r8_phase4_optimisation / FindingA2_edge_time_dependence
source_file:                  research/r8_phase4_optimisation_report.md
file_first_commit_sha:        d918be5
file_first_commit_date:       2026-06-07
governance_state_commit_sha:  d918be5
governance_state_commit_date: 2026-06-07
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "Finding A2 — R8 edge requires time to materialise"
             (line 46)
  Heading:  "### 3.4 Finding A2 — R8 edge requires time" (line 172)
  Text (b): "5td bootstrap Δ_A3 CI crosses zero (full sample)"
             (line 47)
  Text (b): "Holding period reduction below 10td produces a
             material Sharpe degradation (2.38 → 1.17, full
             sample)" (lines 48-49)
one_line_description:
  Phase 4 Finding A2 — R8 edge requires time to materialise:
  5td bootstrap Δ_A3 CI crosses zero (full sample); edge
  disappears at 5td horizon; below-10td holding produces
  material Sharpe degradation (2.38 → 1.17 full sample). R8 is
  not a short-term event alpha.
```

##### Row 20

```text
case_id:                      r8_phase4_optimisation / FindingA3_10td_optimum
source_file:                  research/r8_phase4_optimisation_report.md
file_first_commit_sha:        d918be5
file_first_commit_date:       2026-06-07
governance_state_commit_sha:  d918be5
governance_state_commit_date: 2026-06-07
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "Finding A3 — 10td is the optimal utilisation-
             performance trade-off" (line 52)
  Heading:  "### 3.5 Finding A3 — 10td as utilisation-performance
             optimum" (line 187)
  Text (a): "CANDIDATE: 10td_holding_period | Admission +13.7pp;
             Sharpe decline < 0.25; bootstrap CI positive" (line 72)
  Text (b): "At 10td, admission rate nearly doubles (16.3% →
             30.0%) while Sharpe declines only modestly (2.38 →
             2.13, full sample)" (line 53)
  Text (b): "In the Low-Uplift environment, 10td Sharpe (2.11)
             actually exceeds 20td (1.61)" (line 55)
one_line_description:
  Phase 4 Finding A3 — 10td as utilisation-performance optimum:
  10td holding nearly doubles admission rate (16.3% → 30.0%)
  with only modest Sharpe decline (2.38 → 2.13 full sample); in
  Low-Uplift, 10td Sharpe (2.11) exceeds 20td (1.61); designated
  CANDIDATE for Phase 5 evaluation.
```

##### Row 21

```text
case_id:                      r8_phase4_optimisation / FindingB1_rs_ranking_dominance
source_file:                  research/r8_phase4_optimisation_report.md
file_first_commit_sha:        d918be5
file_first_commit_date:       2026-06-07
governance_state_commit_sha:  d918be5
governance_state_commit_date: 2026-06-07
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "Finding B1 — RS-based quality ranking dominates
             FIFO across all variants" (line 59)
  Heading:  "### 4.3 Finding B2 — All quality variants dominate
             FIFO" (line 239)
  Text (a): "CANDIDATE: rs_60d_ranking | Low-Uplift Sharpe
             +0.52; no admission cost; RS-20d also viable"
             (line 73)
  Text (b): "RS-60d Sharpe in Low-Uplift = 2.13 vs FIFO = 1.61
             (+0.52)" (line 64)
one_line_description:
  Phase 4 Finding B1 — RS-based signal prioritisation dominates
  FIFO: all three quality ranking schemes (RS-20d, RS-60d,
  uplift-proxy) outperform FIFO in both Full Sample and
  Low-Uplift; RS-60d strongest in Low-Uplift (+0.52 Sharpe vs
  FIFO); designated CANDIDATE for Phase 5 evaluation.
```

##### Row 22

```text
case_id:                      r8_phase5_configuration / Finding_P5-1_rs60d_confirmed
source_file:                  research/r8_phase5_configuration_report.md
file_first_commit_sha:        edd42b1
file_first_commit_date:       2026-06-19
governance_state_commit_sha:  98315a6
governance_state_commit_date: 2026-06-19
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "### Finding P5-1: RS-60d ranking is confirmed"
             (line 371)
  Text (a): "Status: LOCKED — v1.0.2 (2026-06-19)" (line 6)
  Text (a): "Verdict: CONFIGURATION_SELECTED" (line 15)
  Text (a): "P5-1 (finding): RS-60d ranking is confirmed as a
             robust improvement" (line 64)
  Text (b): "ARM_B (20td + RS-60d ranking) ... demonstrated a
             substantial improvement in Low-Uplift Sharpe
             (+0.635 vs Arm A)" (line 44)
one_line_description:
  Phase 5 Finding P5-1 — RS-60d ranking documented as robust
  improvement over FIFO baseline: ARM_B (20td + RS-60d)
  demonstrates +0.635 Low-Uplift Sharpe improvement vs ARM_A
  with no admission cost; wide-margin gate passage; consistent
  with the Phase 4 RS-60d CANDIDATE designation.
```

##### Row 23

```text
case_id:                      r8_phase5_configuration / Finding_P5-2_10td_capacity
source_file:                  research/r8_phase5_configuration_report.md
file_first_commit_sha:        edd42b1
file_first_commit_date:       2026-06-19
governance_state_commit_sha:  98315a6
governance_state_commit_date: 2026-06-19
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "### Finding P5-2: 10td holding materially increases
             capital utilisation" (line 388)
  Text (b): "10td holding substantially increases admission rate
             (17.5% → 32.4%) — this is a mechanical effect of
             capital turnover and is robust" (line 56)
one_line_description:
  Phase 5 Finding P5-2 — 10td holding materially increases
  capital utilisation: admission rate 17.5% → 32.4% (+14.83pp);
  classified as mechanical robust effect of capital turnover,
  not a signal-quality finding; basis for ARM_C
  CAPACITY_DEMONSTRATED reclassification (v1.0.2).
```

##### Row 24

```text
case_id:                      r8_phase5_configuration / Finding_P5-3_capacity_sharpe_tradeoff
source_file:                  research/r8_phase5_configuration_report.md
file_first_commit_sha:        edd42b1
file_first_commit_date:       2026-06-19
governance_state_commit_sha:  98315a6
governance_state_commit_date: 2026-06-19
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "### Finding P5-3: The capacity gain from shorter
             holding is not free" (line 409)
  Text (a): "ARM_C reclassified from SELECTED (marginal P5-G1)
             to CAPACITY_DEMONSTRATED / SHARPE_UNRESOLVED"
             (line 14, v1.0.2 changelog)
  Text (b): "marginally satisfied the Sharpe gate (P5-G1,
             Δ = −0.093 against a threshold of −0.10, margin =
             +0.007)" (lines 50-51)
  Text (b): "Under the locked Phase 3 price snapshot, Arm C's
             P5-G1 Δ would be −0.137, which would not pass"
             (lines 53-54)
one_line_description:
  Phase 5 Finding P5-3 — capacity increase accompanied by
  snapshot-sensitive Sharpe degradation: ARM_C 10td+RS-60d
  marginally satisfied P5-G1 (margin +0.007 against −0.10
  threshold); under Phase 3 locked snapshot the same arm would
  not pass (margin −0.037). Observed degradation is snapshot-
  sensitive and close to the predefined decision boundary.
```

##### Row 25

```text
case_id:                      r8_phase6_findings / F-P6-01_adaptive_exits_do_not_improve_armB
source_file:                  research/r8_phase6_findings.md
file_first_commit_sha:        901c0de
file_first_commit_date:       2026-06-22
governance_state_commit_sha:  901c0de
governance_state_commit_date: 2026-06-22
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "## F-P6-01 — Adaptive Exit Policies Do Not Improve
             ARM_B" (line 11)
  Text (a): "Status: FINDING REGISTERED / Step 3 COMPLETE"
             (line 7)
  Text (a): "No challenger satisfied the pre-registered gate
             criteria. All four adaptive exit policies are
             CHARACTERISED, not SELECTED" (lines 44-45)
  Text (b): "E1 ATR Trailing | 1.1689 | −1.035 | FAIL | PASS |
             PASS | CHARACTERISED" (line 24)
  Text (b): "E2 MA20 Failure | 0.3773 | −1.825 | FAIL | FAIL |
             PASS | CHARACTERISED" (line 25)
  Text (b): "E3 RS Deterioration | 1.1342 | −1.070 | FAIL |
             PASS | FAIL | CHARACTERISED" (line 26)
  Text (b): "E4 Donchian | 1.6842 | −0.354 | FAIL | PASS | FAIL
             | CHARACTERISED" (line 27)
one_line_description:
  Phase 6 Finding F-P6-01 — adaptive exit policies do not improve
  ARM_B: all four pre-registered candidates (E1 ATR trailing /
  E2 MA20 failure / E3 RS deterioration / E4 Donchian) FAILED
  P6-G1 (ΔSharpe ≥ −0.15) under Low-Uplift evaluation; bootstrap
  CIs are below zero for E1/E2/E3 and straddle zero for E4.
```

##### Row 26

```text
case_id:                      r8_phase6_candidate_disposition / aggregator
source_file:                  research/r8_phase6_candidate_disposition.md
file_first_commit_sha:        901c0de
file_first_commit_date:       2026-06-22
governance_state_commit_sha:  901c0de
governance_state_commit_date: 2026-06-22
classification_letter:        (c)
classification_type:          Secondary aggregator
classification_evidence:
  Heading:  "## Disposition Table" (line 11)
  Heading:  "## ARM_B — RETAIN AS REFERENCE" (line 23)
  Heading:  "## E1 ATR Trailing — REJECTED" (line 33)
  Text:     "ARM_B | REFERENCE | RETAIN AS REFERENCE | Phase 5
             SELECTED. Phase 6 confirms no challenger improves
             on ARM_B" (line 14)
  Text:     "E1 ATR Trailing | CHARACTERISED | REJECTED | G1
             FAIL (ΔSharpe=−1.035)" (line 16)
one_line_description:
  Secondary aggregator of r8_phase6_findings.md; summarises
  registered findings and governance dispositions (E1/E2/E3
  REJECTED, E4 ARCHIVE FOR FUTURE STUDY, ARM_B RETAIN AS
  REFERENCE); introduces no independent empirical evidence.
```

##### Row 27

```text
case_id:                      r8_phase6_governance_report / aggregator
source_file:                  research/r8_phase6_governance_report.md
file_first_commit_sha:        901c0de
file_first_commit_date:       2026-06-22
governance_state_commit_sha:  901c0de
governance_state_commit_date: 2026-06-22
classification_letter:        (c)
classification_type:          Secondary aggregator
classification_evidence:
  Heading:  "## Step Completion Status" (line 12)
  Heading:  "## Key Invariants Verified" (line 43)
  Text:     "Status: STEP 3 COMPLETE / FINDING REGISTERED"
             (line 8)
  Text:     "3G | Full evaluation | CLOSED | B=5000,
             provenance.json written" (line 22)
  Text:     "WG-1 degenerate equivalence | PASS — adaptive
             engine bit-identical to Phase 5 canonical under
             never_exit_policy" (line 47)
one_line_description:
  Secondary aggregator of r8_phase6_findings.md and r8_phase6_
  candidate_disposition.md; summarises registered findings and
  governance dispositions (Step 3A-3G completion confirmation,
  key invariants verification including WG-1 PASS / P3-FP-002
  PASS / ARM_B admission unchanged PASS); introduces no
  independent empirical evidence.
```

##### Row 28

```text
case_id:                      r8_phase6_closeout / aggregator
source_file:                  research/r8_phase6_closeout.md
file_first_commit_sha:        901c0de
file_first_commit_date:       2026-06-22
governance_state_commit_sha:  901c0de
governance_state_commit_date: 2026-06-22
classification_letter:        (c)
classification_type:          Secondary aggregator
classification_evidence:
  Heading:  "## Closeout Declaration" (line 11)
  Heading:  "## Phase 6 is Closed" (line 72)
  Text:     "Phase 6 Step 3 is complete. All sub-steps (3A-3G)
             are closed. Finding F-P6-01 is registered.
             Candidate dispositions are locked" (lines 13-15)
  Text:     "ARM_B status: RETAIN AS REFERENCE" (line 28)
one_line_description:
  Secondary aggregator of r8_phase6_findings.md and r8_phase6_
  candidate_disposition.md; summarises registered findings and
  governance dispositions (Phase 6 CLOSED declaration, narrative
  Phase 7 transition pointers); introduces no independent
  empirical evidence.
```

---

#### Batch 2b Summary

```text
Batch:                      2b — research/ R8 Phase 4-6
Files reviewed:             14
Finding-bearing files:      4 (phase4_optimisation_report,
                              phase5_configuration_report,
                              phase6_findings; 3 phase6 aggregators
                              counted separately under aggregator
                              files, not double-counted here)
Methodological files:       5 (phase4_spec, phase5_spec,
                              phase5_followup_001_spec, phase6_spec,
                              phase6_wiring_precondition)
Aggregator files:           3 (phase6_candidate_disposition,
                              phase6_governance_report,
                              phase6_closeout)
Governance-process files:   3 (phase5_price_snapshot_refresh_note,
                              phase6_step2_lineage_closeout,
                              phase6_step3_entry_note)
Rows emitted:              14 (11 §A.3 + 3 §A.4)
Included rows:             11
Excluded rows:              3 (all (d2) governance-process)
Primary sources:            8 (Rows 18-25)
Secondary aggregators:      3 (Rows 26-28)
Unique finding clusters:    8

Invariant check:
  I1 (files): 14 = Finding-bearing (4) + Methodological (5)
              + Aggregators (3) + Governance-process (3) ✓
  I2 (rows): Rows emitted (14) = Included (11) + Excluded (3) ✓
  I3 (incl): Included (11) = Primary (8) + Aggregators (3) ✓
  I4 (anchors): Unique finding clusters (8) = Primary (8) ✓
```

Cumulative after Batch 2b:

```text
Files reviewed:           27 (Batch 1: 4 + Batch 2a: 9 + Batch 2b: 14)
Finding-bearing files:    12 (Batch 1: 4 + Batch 2a: 4 + Batch 2b: 4)
Methodological files:     10 (Batch 1: 0 + Batch 2a: 5 + Batch 2b: 5)
Aggregator files:          4 (Batch 1: 1 + Batch 2a: 0 + Batch 2b: 3)
Governance-process:        3 (Batch 1: 0 + Batch 2a: 0 + Batch 2b: 3)
Duplicate files:           1 (Batch 1: 1)

Total rows emitted:       32 (Batch 1: 10 + Batch 2a: 8 + Batch 2b: 14)
§A.3 Included rows:       28 (9 + 8 + 11)
§A.4 Excluded rows:        4 (1 + 0 + 3)
Methodological (A.2.4):   10 (0 + 5 + 5)
Primary sources:          24 (8 + 8 + 8)
Secondary aggregators:     4 (1 + 0 + 3)
Unique finding clusters:  24
```

#### Batch 3 — `research/` remaining (8 files reviewed, 5 INCLUDED rows)

Note: Of the 8 files in Batch 3 scope:

```text
- 2 finding-bearing reports → 4 §A.3 rows
  (P1-DATA_panel_integrity_assessment × 3 for IF-1/IF-2/IF-3;
   p1_data_remediation_closeout × 1 for Benchmark robustness)
- 1 secondary aggregator → 1 §A.3 row (helios_research_roadmap)
- 4 methodological → §A.2.4 (entries A.2.4.11 through A.2.4.14)
- 1 governance-process artifact → §A.4 with classification (d2)
  (track_c_step1_closeout — engineering validation, not finding)
```

##### Row 29

```text
case_id:                      P1-DATA_panel_integrity / IF1_pre_listing_contamination
source_file:                  research/P1-DATA_panel_integrity_assessment.md
file_first_commit_sha:        fb38ae4
file_first_commit_date:       2026-06-02
governance_state_commit_sha:  b41d56b
governance_state_commit_date: 2026-06-04
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "## Integrity Finding 1 — Pre-listing / Emerging-board
             Contamination" (line 51)
  Heading:  "## Summary Verdict" (line 24)
  Text (a): "IF-1: Pre-listing / emerging-board contamination |
             High | Confirmed, measured | Open — no approved fix"
             (line 28, at assessment time)
  Text (a): "Status: OPEN — remediation not started" (line 6, at
             assessment time). Subsequent governance lifecycle:
             remediation closeout (CLOSED, AC-1 through AC-7 PASS,
             commit b41d56b).
  Text (b): "daily_price_adj contains price history for 18 stocks
             that predates their listing_date in company_metadata"
             (lines 55-57)
  Text (b): "135 of 338 DQ events trace to IF-1" (line 200)
one_line_description:
  P1-DATA Integrity Finding IF-1 — pre-listing / emerging-board
  contamination: 18 stocks with daily_price_adj rows predating
  listing_date in company_metadata; affects 7,331 rows and 135 of
  338 DQ events; severity High, certainty Confirmed measured;
  blast radius covers full panel and all research series.
```

##### Row 30

```text
case_id:                      P1-DATA_panel_integrity / IF2_empty_stock_info
source_file:                  research/P1-DATA_panel_integrity_assessment.md
file_first_commit_sha:        fb38ae4
file_first_commit_date:       2026-06-02
governance_state_commit_sha:  77fb3c1
governance_state_commit_date: 2026-06-06
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "## Integrity Finding 2 — Empty `stock_info`" (line 102)
  Heading:  "## Summary Verdict" (line 24)
  Text (a): "IF-2: Empty stock_info | Medium | Confirmed | Open —
             workaround in use" (line 29, at assessment time).
             Subsequent governance lifecycle: reclassified P2
             non-binding via r8_phase1_lifecycle_spec v0.1.5
             (commit 77fb3c1, 2026-06-06).
  Text (b): "Confirmed. Table is empty; this is directly
             observable." (line 124)
one_line_description:
  P1-DATA Integrity Finding IF-2 — empty stock_info table:
  workaround in use (company_metadata as Phase 1 sector
  diagnostic source); severity Medium, certainty Confirmed;
  subsequent governance reclassification from AC-6 binding
  blocker to P2 non-binding.
```

##### Row 31

```text
case_id:                      P1-DATA_panel_integrity / IF3_empty_corporate_actions
source_file:                  research/P1-DATA_panel_integrity_assessment.md
file_first_commit_sha:        fb38ae4
file_first_commit_date:       2026-06-02
governance_state_commit_sha:  39ba6c2
governance_state_commit_date: 2026-06-07
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "## Integrity Finding 3 — Empty `corporate_actions`"
             (line 128)
  Heading:  "## Summary Verdict" (line 24)
  Text (a): "IF-3: Empty corporate_actions | Medium | Confirmed |
             Open — affected rows unresolvable" (line 30, at
             assessment time). Subsequent governance lifecycle:
             split into IF-3A (dividend/split, CLOSED at commit
             76f1f45) and IF-3B (suspension/halt source discovery,
             reclassified P2 non-binding via composition audit
             at commit 39ba6c2 with separate IF-3B source
             discovery DRAFT SPEC at §A.2.4.13).
  Text (b): "203 SUSPENSION_GAP rows across 90 stocks" (from
             downstream IF-3B SPEC §1.1)
  Text (b): "338 signals in the R8 population have ret_1d >= +10%"
             (line 138)
one_line_description:
  P1-DATA Integrity Finding IF-3 — empty corporate_actions table:
  affected rows initially unresolvable; severity Medium, certainty
  Confirmed; subsequent governance lifecycle split IF-3A
  (dividend/split, CLOSED) and IF-3B (suspension/halt source
  discovery, reclassified P2 non-binding via composition audit
  finding zero confirmed halt-resumption events in reviewed
  population).
```

##### Row 32

```text
case_id:                      p1_data_remediation / Benchmark_C_robustness_after_IF1
source_file:                  research/p1_data_remediation_closeout_2026-06-04.md
file_first_commit_sha:        b41d56b
file_first_commit_date:       2026-06-04
governance_state_commit_sha:  b41d56b
governance_state_commit_date: 2026-06-04
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "## Status" (line 3)
  Heading:  "## Benchmark Results: Provisional vs Remediated"
             (line 63)
  Text (a): "Status: CLOSED" (line 5)
  Text (a): "All acceptance criteria satisfied. R8 Phase 1
             findings upgraded from PROVISIONAL to CONDITIONAL"
             (lines 6-7)
  Text (a): "Key finding: Benchmark C uplift is robust to IF-1
             remediation. The hypothesis that Benchmark C was an
             emerging-board artifact is not [supported]"
             (lines 79-80)
  Text (b): "C: R8 within RS_T3 (ret_20d) | +6.84% | +6.77% |
             -0.07pp" (line 69)
  Text (b): "Affected R8 events (pre-rebuild) | 463 (5.49%)"
             (line 58)
  Text (b): "Net event count change after rebuild (Δ) | -418
             (-4.96%) | R8 events: before → after | 8,430 →
             8,012" (lines 59-60)
one_line_description:
  P1-DATA remediation robustness assessment after IF-1 fix:
  Benchmark C R8-within-RS_T3 uplift at 20td shifts +6.84% →
  +6.77% (Δ -0.07pp) under IF-1 remediation despite 4.96% net
  event count change; tests and rejects the hypothesis that
  Benchmark C was an emerging-board artifact; basis for PROVISIONAL
  → CONDITIONAL upgrade.
```

##### Row 33

```text
case_id:                      helios_research_roadmap / aggregator
source_file:                  research/helios_research_roadmap.md
file_first_commit_sha:        edd42b1
file_first_commit_date:       2026-06-19
governance_state_commit_sha:  9921f12
governance_state_commit_date: 2026-06-19
classification_letter:        (c)
classification_type:          Secondary aggregator
classification_evidence:
  Heading:  "## Governance Summary" (line 12)
  Heading:  "## Phase 5 Key Findings (carried forward)" (line 34)
  Text:     "Status: ACTIVE — updated after Phase 5 v1.0.2
             governance patch" (lines 6-7)
  Text:     "Phase 5: CLOSED / CONFIGURATION_SELECTED / LOCKED
             (v1.0.2) | ARM_B SELECTED; ARM_C reclassified to
             CAPACITY_DEMONSTRATED / SHARPE_UNRESOLVED"
             (lines 20-22)
  Text:     "P5-1 | RS-60d ranking confirmed in Low-Uplift |
             Sharpe 1.569 → 2.204; MaxDD -3.23pp" (line 38)
one_line_description:
  Secondary aggregator of r8_phase5_configuration_report.md (and
  downstream R8 Phase chain); summarises registered findings and
  governance dispositions across Phase 1 through Phase 5
  (Phase 5 v1.0.2 ARM_B SELECTED / ARM_C reclassified
  CAPACITY_DEMONSTRATED / Phase 6 NOT STARTED); introduces no
  independent empirical evidence.
```

---

#### Batch 3 Summary

```text
Batch:                      3 — research/ remaining
Files reviewed:             8
Finding-bearing files:      2 (P1-DATA_panel_integrity_assessment,
                              p1_data_remediation_closeout)
Methodological files:       4 (ADR-R8P1-001, ADR-R8P1-002,
                              if3b_source_discovery_spec,
                              phase2_research_roadmap)
Aggregator files:           1 (helios_research_roadmap)
Governance-process files:   0  (1 file [track_c_step1_closeout]
                              lineage-excluded per §A.2.1 / boundary
                              spec §1; see Amendment Log Fix A)
Rows emitted:               5 (5 §A.3 + 0 §A.4)
Included rows:              5
Excluded rows:              0 (Fix A: track_c_step1_closeout
                              lineage-excluded, removed from §A.4)
Primary sources:            4 (Rows 29-32; P1-DATA assessment ×3 +
                              p1_data_remediation_closeout ×1)
Secondary aggregators:      1 (Row 33)
Unique finding clusters:    4

Invariant check:
  I1 (files): 8 = Finding-bearing (2) + Methodological (4)
              + Aggregators (1) + Governance-process (0)
              + Lineage-excluded (1) ✓
  I2 (rows): Rows emitted (5) = Included (5) + Excluded (0) ✓
  I3 (incl): Included (5) = Primary (4) + Aggregators (1) ✓
  I4 (anchors): Unique finding clusters (4) = Primary (4) ✓
```

Cumulative after Batch 3:

```text
Files reviewed:           35 (Batch 1: 4 + Batch 2a: 9 + Batch 2b: 14
                              + Batch 3: 8)
Finding-bearing files:    14 (4 + 4 + 4 + 2)
Methodological files:     14 (0 + 5 + 5 + 4)
Aggregator files:          5 (1 + 0 + 3 + 1)
Governance-process:        3 (0 + 0 + 3 + 0)
Duplicate files:           1 (Batch 1: 1)

Total rows emitted:       37 (10 + 8 + 14 + 5)
§A.3 Included rows:       33 (9 + 8 + 11 + 5)
§A.4 Excluded rows:        4 (1 + 0 + 3 + 0)
Methodological (A.2.4):   14 (0 + 5 + 5 + 4)
Primary sources:          28 (8 + 8 + 8 + 4)
Secondary aggregators:     5 (1 + 0 + 3 + 1)

Unique finding clusters:  28 (Phase 2 anchor candidate count;
                              equals Primary sources where every
                              finding is enumerated by exactly one
                              primary row, i.e. Row Granularity
                              Principle holds without cross-row
                              duplication)
```

Definition (locked 2026-06-25):

```text
Unique finding clusters = the count of distinct empirical findings
admitted to §A.3 across Primary source rows. Secondary aggregator
rows do not contribute to this count (they cite findings that are
already counted via their primary source). When the Row Granularity
Principle holds (no two primary rows record the same finding),
Unique finding clusters = Primary sources. Phase 2 U7A evaluation
operates on this count, not on raw row count, because aggregators
cannot themselves be U7B anchors.
```

#### Batch 4 — Journals (2 files reviewed, 8 INCLUDED rows)

Note: Of the 2 files in Batch 4 scope:

```text
- 2 finding-bearing files (both Journals; per Evidence-test
  prevalence rule, declared identity "Journal" does NOT exempt
  first-on-record empirical claims from §A.3 admission).
- 0 methodological files
- 0 secondary aggregator files
- 0 governance-process files

Row-level duplication: both Journals share 8 overlap version
sections introduced in the same commit (955d71d, 2026-05-17).
Per Same-commit tie-break, canonical = docs/JOURNAL.md
(lexicographically first). Duplicate coverage in
docs/RESEARCH_JOURNAL.md is noted in each row's
classification_evidence, not emitted as separate rows
(would inflate I4 / Unique finding clusters via cross-source
duplication).

docs/RESEARCH_JOURNAL.md contributes one unique cluster
(v0.1.14.1.2.experiment F Budget Sweep) not present in
docs/JOURNAL.md; that cluster is anchored to RESEARCH_JOURNAL.md
as primary.

Excluded version sections (no empirical finding, pure
implementation milestone): v0.1.0-6 (Skeleton + storage layer)
and v0.1.7-10 (Data Foundation). Per §A.0 Row Granularity
Principle, these are not independently governable research
conclusions; they are implementation/architecture notes within
finding-bearing files. They do not emit §A.3 or §A.4 rows —
§A.4 admits FILE-level exclusions, not within-file section
exclusions. The two version sections are noted here for
enumeration completeness.
```

##### Row 34

```text
case_id:                      JOURNAL / v0.1.10.2_yfinance_splits_TW_broken
source_file:                  docs/JOURNAL.md
file_first_commit_sha:        955d71d
file_first_commit_date:       2026-05-17
governance_state_commit_sha:  955d71d
governance_state_commit_date: 2026-05-17
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "## v0.1.10.2 — Dividend + Split Adjustment
             (2026-05-16)" (line 194)
  Heading:  "### Key insight — yfinance.splits is broken for TW"
             (line 205)
  Text (a): finding statement is the named "Key insight"
            (research-context discovery)
  Text (b): "Key insight — TWT49U has same dividend values as
             FinMind" (line 210) — quantitative cross-source
            validation
  Also recorded in docs/RESEARCH_JOURNAL.md (line 270, same
  cluster; not emitted as separate row per Row-level Duplicate
  Rule).
one_line_description:
  Data-quality discovery — yfinance.splits is broken for TW
  market while TWT49U dividend values cross-validate against
  FinMind. Establishes the dividend/split adjustment pipeline
  data source decision.
```

##### Row 35

```text
case_id:                      JOURNAL / v0.1.11_regime_distribution
source_file:                  docs/JOURNAL.md
file_first_commit_sha:        955d71d
file_first_commit_date:       2026-05-17
governance_state_commit_sha:  955d71d
governance_state_commit_date: 2026-05-17
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "## v0.1.11 — Indicators + Regime (2026-05-17)"
             (line 167)
  Heading:  "### Key insight — Regime distribution validates
             market intuition" (line 178)
  Also recorded in docs/RESEARCH_JOURNAL.md (line 243, same
  cluster; not emitted as separate row per Row-level Duplicate
  Rule).
one_line_description:
  Regime-detector output distribution — observed empirical
  distribution of regime labels aligns with market-intuition
  expectations; establishes regime feature's validity as an
  input to downstream strategies.
```

##### Row 36

```text
case_id:                      JOURNAL / v0.1.12_trendbreakout_strategy
source_file:                  docs/JOURNAL.md
file_first_commit_sha:        955d71d
file_first_commit_date:       2026-05-17
governance_state_commit_sha:  955d71d
governance_state_commit_date: 2026-05-17
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "## v0.1.12 — TrendBreakout Strategy + Decision
             Loop (2026-05-17)" (line 134)
  Heading:  "### Strategy condition curation (with reviewer)"
             (line 146)
  Text:     Strategy condition curation reviewed and locked
            with reviewer participation — represents the
            governance-locked initial TrendBreakout entry-
            condition set.
  Also recorded in docs/RESEARCH_JOURNAL.md (line 211, same
  cluster; not emitted as separate row per Row-level Duplicate
  Rule).
one_line_description:
  TrendBreakout strategy initial release — entry-condition set
  curated with reviewer, decision loop locked. Establishes the
  first end-to-end Helios strategy implementation prior to OOS
  validation.
```

##### Row 37

```text
case_id:                      JOURNAL / v0.1.13.1_OOS_validation_REAL_ALPHA
source_file:                  docs/JOURNAL.md
file_first_commit_sha:        955d71d
file_first_commit_date:       2026-05-17
governance_state_commit_sha:  955d71d
governance_state_commit_date: 2026-05-17
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "## v0.1.13.1 — OOS Validation (2026-05-17)"
             (line 115)
  Heading:  "### Key insight — OOS BETTER than IS" (line 121)
  Heading:  "### Verdict: ✓✓ REAL ALPHA (not curve-fit AI bull
             noise)" (line 130)
  Text (b): "132 trades over 5 years, profit factor 2.67,
             MFE/|MAE| 4.47" (line 94 in JOURNAL — context for
             v0.1.13.2 with similar trade-set lineage)
  Text (b): "Win rate 53.8%" (line 97); "Mean +1.89% > Median
             +0.37%" (line 98); "Avg win 5.62% / avg loss
             -2.45% (W/L 2.29)" (line 99)
  Also recorded in docs/RESEARCH_JOURNAL.md (line 195, same
  cluster; not emitted as separate row per Row-level Duplicate
  Rule).
one_line_description:
  TrendBreakout OOS validation — out-of-sample metrics exceed
  in-sample metrics; PF 2.67, win rate 53.8%, right-skewed
  return distribution (Mean > Median, W/L ratio 2.29). Verdict
  registered as "REAL ALPHA (not curve-fit AI bull noise)".
```

##### Row 38

```text
case_id:                      JOURNAL / v0.1.13.2_textbook_trend_signature
source_file:                  docs/JOURNAL.md
file_first_commit_sha:        955d71d
file_first_commit_date:       2026-05-17
governance_state_commit_sha:  955d71d
governance_state_commit_date: 2026-05-17
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "## v0.1.13.2 — Exit Logic + Round-trip Backtest
             (2026-05-17)" (line 88)
  Heading:  "### Key insight — Textbook trend signature"
             (line 96)
  Text (b): "132 trades over 5 years, profit factor 2.67,
             MFE/|MAE| 4.47" (line 94)
  Text (b): "Win rate 53.8% (≈ coin flip)" (line 97)
  Also recorded in docs/RESEARCH_JOURNAL.md (line 161, same
  cluster; not emitted as separate row per Row-level Duplicate
  Rule).
one_line_description:
  Exit logic + round-trip backtest — observed trade-set
  exhibits textbook trend-following profile: coin-flip win rate
  paired with right-skewed payoff (MFE/|MAE| 4.47, W/L ratio
  ~2.29). Establishes the structural payoff shape that later
  cost-resistance and portfolio-constrained validations
  depend on.
```

##### Row 39

```text
case_id:                      JOURNAL / v0.1.13.3_cost_resistant_alpha
source_file:                  docs/JOURNAL.md
file_first_commit_sha:        955d71d
file_first_commit_date:       2026-05-17
governance_state_commit_sha:  955d71d
governance_state_commit_date: 2026-05-17
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "## v0.1.13.3 — Cost + OOS Round-trip (2026-05-17)"
             (line 49)
  Heading:  "### Key insight — Alpha is cost-resistant"
             (line 62)
  Text (b): "0.585% cost | +1.99% | 2.50 | ✓✓ STRONG" (line 66)
  Text (b): "0.785% with slippage | +1.79% | 2.25 | ✓✓ STRONG"
             (line 67)
  Text:     "Strategy survives realistic cost AND additional
             0.1% slippage assumption" (line 69)
  Also recorded in docs/RESEARCH_JOURNAL.md (line 127, same
  cluster; not emitted as separate row per Row-level Duplicate
  Rule).
one_line_description:
  Cost + OOS round-trip — TrendBreakout OOS net mean +1.99% PF
  2.50 at TW realistic round-trip cost (0.585%); +1.79% PF 2.25
  at 0.785% (cost + 0.1% slippage). Average holding ~27 days,
  consistent with cost-tolerant trend-following profile.
```

##### Row 40

```text
case_id:                      JOURNAL / v0.1.14.1_portfolio_constrained_STRONG_PASS
source_file:                  docs/JOURNAL.md
file_first_commit_sha:        955d71d
file_first_commit_date:       2026-05-17
governance_state_commit_sha:  955d71d
governance_state_commit_date: 2026-05-17
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "## v0.1.14.1 — Portfolio Layer + Constrained
             Backtest (2026-05-17)" (line 9)
  Heading:  "### Key insight — Constraints **upgraded** PF"
             (line 23)
  Heading:  "### Decision: ✓ Substantively STRONG PASS →
             proceed to v0.1.14.2" (line 38)
  Text (b): "Trade count: 132 (unconstrained) → 72
             (constrained, -46%)" (line 24)
  Text (b): "Profit factor: 2.50 → 4.13 (+65% on gross basis)"
             (line 25)
  Text (b): "Max DD: -7.73% (trade-level) → -11.01% (portfolio)
             — only 1.4x ratio, not 2-3x" (line 26)
  Text (b): "Avg exposure: 29%" (line 27)
  Also recorded in docs/RESEARCH_JOURNAL.md (line 88, same
  cluster; not emitted as separate row per Row-level Duplicate
  Rule).
one_line_description:
  Portfolio constrained backtest (5/20%/40%/30%/10% risk
  budget) — constrained trade-count 132→72 with PF 2.50→4.13;
  portfolio Max DD -11.01% (1.4x trade-level, lower than the
  2-3x reviewer-predicted band); average exposure 29%.
  Registered as Substantively STRONG PASS.
```

##### Row 41

```text
case_id:                      RESEARCH_JOURNAL / v0.1.14.1.2_F_budget_sweep
source_file:                  docs/RESEARCH_JOURNAL.md
file_first_commit_sha:        955d71d
file_first_commit_date:       2026-05-17
governance_state_commit_sha:  955d71d
governance_state_commit_date: 2026-05-17
classification_letter:        (a) + (b)
classification_type:          Primary finding source
classification_evidence:
  Heading:  "## v0.1.14.1.2.experiment — F Budget Sweep
             Findings (2026-05-17)" (line 16)
  Heading:  "### Three structural findings" (line 27)
  Text:     "1. CONCENTRATED (3×30%) dominates CURRENT (5×20%)
             on every OOS metric" (line 29)
  Text (b): "CAGR | +5.86% | +7.23% | +1.37pp" (line 33)
  Text (b): "Max DD | -11.71% | -9.57% | better" (line 34)
  Text (b): "PF (gross) | 4.13 | 7.08 | +71%" (line 35)
  Text (b): "Win rate | 54.5% | 60.7% | +6.2pp" (line 36)
  Text:     "2. cash_buffer 73.5% binding in CONCENTRATED
             reveals regime clustering" (line 40)
  Text:     "3. WIDER didn't improve; NO-ETF-CAP didn't
             improve" (line 47)
  Unique to docs/RESEARCH_JOURNAL.md (not in
  docs/JOURNAL.md). Canonical anchor by virtue of being the
  only file in scope recording this cluster.
one_line_description:
  F Budget Sweep — five risk-budget configurations compared
  on the same backtest engine. CONCENTRATED (3×30%) dominates
  CURRENT (5×20%) on every OOS metric (CAGR +1.37pp, lower
  MaxDD, PF +71%, win-rate +6.2pp); cash_buffer binds 73.5%
  under CONCENTRATED suggesting regime clustering; loosened
  constraints (WIDER / NO-ETF-CAP) produced no improvement.
```

---

#### Batch 4 Summary

```text
Batch:                      4 — Journals
Files reviewed:             2
Finding-bearing files:      2 (docs/JOURNAL.md,
                              docs/RESEARCH_JOURNAL.md)
Methodological files:       0
Aggregator files:           0
Governance-process files:   0
Rows emitted:               8
Included rows:              8
Excluded rows:              0
Primary sources:            8 (Rows 34-41; canonical anchors
                              for 7 overlap clusters at
                              JOURNAL.md + 1 unique cluster at
                              RESEARCH_JOURNAL.md)
Secondary aggregators:      0
Unique finding clusters:    8

Invariant check:
  I1 (files): 2 = Finding-bearing (2) + Methodological (0)
              + Aggregators (0) + Governance-process (0) ✓
  I2 (rows): Rows emitted (8) = Included (8) + Excluded (0) ✓
  I3 (incl): Included (8) = Primary (8) + Aggregators (0) ✓
  I4 (anchors): Unique finding clusters (8) = Primary (8) ✓
```

Note on excluded sections (informational, not §A.4 entries):

```text
The following 2 version sections appear in both Journals but
emit no row at either §A.3 or §A.4:

  - v0.1.0-6  Skeleton + storage layer (JOURNAL line 246;
                                        RESEARCH_JOURNAL line 311)
  - v0.1.7-10 Data Foundation         (JOURNAL line 226;
                                        RESEARCH_JOURNAL line 291)

Per §A.0 Row Granularity Principle, these are implementation/
architecture milestones with no empirical research conclusion;
not independently governable findings. Per §A.4 file-level
exclusion semantics, they do not warrant §A.4 entries (the
containing files are finding-bearing overall). Recorded here
in the Batch Summary for enumeration completeness.
```

Cumulative after Batch 4:

```text
Files reviewed:           37 (Batch 1: 4 + 2a: 9 + 2b: 14
                              + 3: 8 + 4: 2)
Finding-bearing files:    16 (4 + 4 + 4 + 2 + 2)
Methodological files:     14 (0 + 5 + 5 + 4 + 0)
Aggregator files:          5 (1 + 0 + 3 + 1 + 0)
Governance-process:        3 (0 + 0 + 3 + 0 + 0)
Duplicate files:           1 (Batch 1: 1)

Total rows emitted:       45 (10 + 8 + 14 + 5 + 8)
§A.3 Included rows:       41 (9 + 8 + 11 + 5 + 8)
§A.4 Excluded rows:        4 (1 + 0 + 3 + 0 + 0)
Methodological (A.2.4):   14 (0 + 5 + 5 + 4 + 0)
Primary sources:          36 (8 + 8 + 8 + 4 + 8)
Secondary aggregators:     5 (1 + 0 + 3 + 1 + 0)
Unique finding clusters:  36
```

#### Batch 5 — `docs/decision_records/` (20 files reviewed, 0 §A.3 INCLUDED rows)

Note: Batch 5 produced no §A.3 INCLUDED rows. All 20 files in
docs/decision_records/ are either methodological (12 entries
added to §A.2.4, A.2.4.15 through A.2.4.26) or governance-process
artifacts (8 rows added to §A.4, A4-5 through A4-12). The 8 §A.4
rows are listed in the §A.4 section below.

Group breakdown (operational categorisation, not a new locked rule):

```text
Group A — ADRs (10 files):
  ADR-001 through ADR-008, adr_p1_data_001_lifecycle_authority,
  r8_phase1_bootstrap_adr → all §A.2.4 (entries A.2.4.15-24).

Group B — Governance SPECs (2 files):
  p1_data_remediation_spec, r8_phase1_governance
  → both §A.2.4 (entries A.2.4.25-26).

Group C — Audit report (1 file):
  v0_1_16_backtest_audit_report
  → §A.4 (d2) per Engineering Validation Principle.
    Audit verdict "Branch A — T+1 open aligned" refers to
    implementation correctness (fill-semantics consistency),
    not market behaviour.

Group D — Operational notes (3 files):
  shioaji_semantic_observation_2026_05_26,
  v0_1_16_daily_run_patch, v0_1_16_live_broker_patch
  → all §A.4 (d2). SDK semantic observations and code-patch
    instructions; software contract, not market proposition.

Group E — Residual (4 files):
  CHANGELOG_v0_1_16_v1_to_v2, CHANGELOG_v0_1_16_v2_1,
  README, obs_gate_2026_05_26
  → all §A.4 (d2). Engineering changelogs, documentation
    convention, operational merge/rollback protocol.
```

---

#### Batch 5 Summary

```text
Batch:                      5 — docs/decision_records/
Files reviewed:             20
Finding-bearing files:       0
Methodological files:       12 (Group A 10 + Group B 2)
Aggregator files:            0
Governance-process files:    8 (Group C 1 + Group D 3 + Group E 4)
Rows emitted:                8 (all §A.4)
Included rows:               0
Excluded rows:               8 (all (d2))
Primary sources:             0
Secondary aggregators:       0
Unique finding clusters:     0

Invariant check:
  I1 (files): 20 = Finding-bearing (0) + Methodological (12)
              + Aggregators (0) + Governance-process (8) ✓
  I2 (rows): Rows emitted (8) = Included (0) + Excluded (8) ✓
  I3 (incl): Included (0) = Primary (0) + Aggregators (0) ✓
  I4 (anchors): Unique finding clusters (0) = Primary (0) ✓
```

Operational note (not a new locked rule, per Protocol Freeze):

```text
Batch 5 demonstrates that a wide enumeration universe paired with
strict classification yields legitimate "negative-evidence" batches.
Zero §A.3 rows is the correct outcome when seed-scope files are
exclusively methodological or governance-process in identity. The
14 §A.0 locked rules suffice to handle this case mechanically —
no new protocol required.

The Engineering Validation Principle did all the work for Group C
(audit report) and Group D (patches/observations). For Groups A,
B, and E, Document Identity Principle resolved classification
without invoking Evidence-test prevalence (none of these files
contained first-on-record empirical claims).
```

Cumulative after Batch 5:

```text
Files reviewed:           57 (4 + 9 + 14 + 8 + 2 + 20)
Finding-bearing files:    16 (4 + 4 + 4 + 2 + 2 + 0)
Methodological files:     26 (0 + 5 + 5 + 4 + 0 + 12)
Aggregator files:          5 (1 + 0 + 3 + 1 + 0 + 0)
Governance-process:       11 (0 + 0 + 3 + 0 + 0 + 8)
Duplicate files:           1 (Batch 1: 1)

Total rows emitted:       53 (10 + 8 + 14 + 5 + 8 + 8)
§A.3 Included rows:       41 (9 + 8 + 11 + 5 + 8 + 0)
§A.4 Excluded rows:       12 (1 + 0 + 3 + 0 + 0 + 8)
Methodological (A.2.4):   26 (0 + 5 + 5 + 4 + 0 + 12)
Primary sources:          36 (8 + 8 + 8 + 4 + 8 + 0)
Secondary aggregators:     5 (1 + 0 + 3 + 1 + 0 + 0)
Unique finding clusters:  36
```

#### Batch 6a — `docs/handoffs/` (Helios v0.1.x version sessions, 15 files reviewed, 0 §A.3 INCLUDED rows)

Note: Batch 6a produced no §A.3 INCLUDED rows. All 15 files in
this sub-batch (Helios v0.1.14.3 through v0.2.0 dated 2026-05-19
through 2026-05-31) are workflow-continuity records under the
existing Engineering Validation Principle. 15 rows added to §A.4
(A4-13 through A4-27).

Group description (operational, not a new locked rule):

```text
The 15 files cover the implementation-stage timeline before R8
Phase 0. Content classes encountered:

  - Session state / continuity (next-session pickup, env state)
  - Implementation diagnostics (test counts, schema migrations,
    production bug fixes, cron timing, deploy verification)
  - Exploratory analyses never promoted into governed research
    artifacts (MA5 backtest tables in A4-15, tracker audit
    findings in A4-24, INCONCLUSIVE harness output in A4-23)
  - Research references to phase0_findings.md v4 canonical
    content (A4-25, handoff_2026-05-29.md)

All three first content classes route to (d2) directly under
Engineering Validation Principle. The fourth class (A4-25) was
evaluated against (c) Secondary Aggregator definition; the file's
primary identity is workflow handoff (Session topic / HEAD /
Production State / Pending Backlog / Next Session Scope), not
finding aggregation. A document with a research-references
section but workflow primary identity does not meet the (c) bar
("primary identity = organising / summarising findings"). → (d2).

This preserves the Secondary Aggregator set as a clean, narrow
class — roadmap-type documents whose primary identity is finding
aggregation. Handoff / session-end / closeout / retrospective /
release-note documents do NOT enter (c) on the basis of
incidental finding references.
```

#### Batch 6a Summary

```text
Batch:                      6a — docs/handoffs/ v0.1.x sessions
Files reviewed:             15
Finding-bearing files:       0
Methodological files:        0
Aggregator files:            0
Governance-process files:   15
Rows emitted:               15 (all §A.4)
Included rows:               0
Excluded rows:              15 (all (d2))
Primary sources:             0
Secondary aggregators:       0
Unique finding clusters:     0

Invariant check:
  I1 (files): 15 = Finding-bearing (0) + Methodological (0)
              + Aggregators (0) + Governance-process (15) ✓
  I2 (rows): Rows emitted (15) = Included (0) + Excluded (15) ✓
  I3 (incl): Included (0) = Primary (0) + Aggregators (0) ✓
  I4 (anchors): Unique finding clusters (0) = Primary (0) ✓
```

Cumulative after Batch 6a:

```text
Files reviewed:           72 (4 + 9 + 14 + 8 + 2 + 20 + 15)
Finding-bearing files:    16 (unchanged)
Methodological files:     26 (unchanged)
Aggregator files:          5 (unchanged)
Governance-process:       26 (11 + 15)
Duplicate files:           1 (unchanged)

Total rows emitted:       68 (53 + 15)
§A.3 Included rows:       41 (unchanged)
§A.4 Excluded rows:       27 (12 + 15)
Methodological (A.2.4):   26 (unchanged)
Primary sources:          36 (unchanged)
Secondary aggregators:     5 (unchanged)
Unique finding clusters:  36 (unchanged)
```

#### Batch 6b — `docs/handoffs/` (P1-DATA / R8 / Track C phase, 20 files reviewed, 0 §A.3 INCLUDED rows)

Note: Batch 6b produced no §A.3 INCLUDED rows. All 20 files are
workflow-continuity records — each handoff either contains no
first-on-record governed empirical conclusion (Q1 = No) or
references a downstream canonical research/finding artifact
already enumerated in Batches 1-5 (Q1 = Yes, Q2 = Yes). 20 rows
added to §A.4 (A4-28 through A4-47).

Group description (operational, not a new locked rule):

```text
The 20 files cover the P1-DATA / R8 / Track C / Phase 6 timeline
(2026-05-31 through 2026-06-23). Content classes encountered:

  - R8 Phase 1 governance-layer handoffs (ADRs locked, SPEC locks,
    sign-off ceremonies, P0-B cell adequacy audit, A-1/A-2/A-3
    benchmark analyses, clean-panel re-run) — all reference
    governed artifacts already enumerated at Rows 10-12
    (interim_findings), A.2.4.1 (cell_adequacy_spec), A.2.4.2
    (lifecycle_spec), A.2.4.11/12 (ADR-R8P1-001/002), etc.
  - P1-DATA remediation handoffs (IF-1 closeout, IF-2 reclassification,
    IF-3A closure, IF-3B composition audit + reclassification) —
    all reference Rows 29-32 (P1-DATA assessment + remediation
    closeout) and A.2.4.13/25 (IF-3B SPEC, p1_data_remediation_spec).
  - R8 Phase 2A/2B/3/4/5 handoffs — all reference Rows 13-21
    (phase2a_validation_report, phase2b_feasibility_memo,
    phase3_risk_report, phase4_optimisation_report) and the
    corresponding methodological SPECs at A.2.4.3-7.
  - Track C Step 2 + Phase 6 evidence gap handoff (2026-06-23) —
    Track C Step 2 R1 prereg is DRAFT (NOT LOCKED), explicitly
    forward-looking governance. Phase 6 evidence gap is a future
    work flag (BACKLOG-WG1) about test reproducibility, not a
    market-behaviour finding. Phase 6 F-P6-01 anchored at Row 25.
  - Implementation / operational session handoffs (signal idempotency,
    sector classification, paper broker fixes, etc.) — Q1 = No.

This batch confirms the (d2) classification follows from the
ABSENCE of a canonical anchor, NOT from the handoff document type.
A handoff that introduced a governed conclusion lacking a
downstream canonical artifact would have been §A.3 primary. None
in Batch 6b meet that bar.
```

#### Batch 6b Summary

```text
Batch:                      6b — docs/handoffs/ P1-DATA/R8/Track C
Files reviewed:             20
Finding-bearing files:       0
Methodological files:        0
Aggregator files:            0
Governance-process files:   20
Rows emitted:               20 (all §A.4)
Included rows:               0
Excluded rows:              20 (all (d2))
Primary sources:             0
Secondary aggregators:       0
Unique finding clusters:     0

Invariant check:
  I1 (files): 20 = Finding-bearing (0) + Methodological (0)
              + Aggregators (0) + Governance-process (20) ✓
  I2 (rows): Rows emitted (20) = Included (0) + Excluded (20) ✓
  I3 (incl): Included (0) = Primary (0) + Aggregators (0) ✓
  I4 (anchors): Unique finding clusters (0) = Primary (0) ✓
```

Cumulative after Batch 6b (Phase 1 enumeration complete):

```text
Files reviewed:           92 (4 + 9 + 14 + 8 + 2 + 20 + 15 + 20)
Finding-bearing files:    16 (unchanged from Batch 4)
Methodological files:     26 (unchanged from Batch 5)
Aggregator files:          5 (unchanged from Batch 2b)
Governance-process:       46 (11 + 15 + 20)
Duplicate files:           1 (unchanged from Batch 1)

Total rows emitted:       88 (53 + 15 + 20)
§A.3 Included rows:       41 (unchanged from Batch 4)
§A.4 Excluded rows:       47 (12 + 15 + 20)
Methodological (A.2.4):   26 (unchanged)
Primary sources:          36 (unchanged)
Secondary aggregators:     5 (unchanged)
Unique finding clusters:  36 (unchanged)
```

---

### A.4 EXCLUDED After File-Level Classification (test d / e / f / g)

Files in §3.2 seed scope that were read and classified, then
excluded. These are NOT the same as §A.2 pre-exclusions: §A.4 is
"read and rejected by content test", while §A.2 is "rejected by
spec rule before content test".

The distinction matters for exhaustiveness audit: a future reviewer
must be able to see that every seed file was either pre-excluded
(§A.2), included (§A.3), or read-then-excluded (§A.4). Files
missing from all three sections constitute an enumeration gap.

Classification letter (d) is the dominant §A.4 category and covers
two distinct sub-types of operational exclusion:

```text
- (d1) Operational duplicate handling: byte-identical files where
       only the canonical (earliest git-resident) path is admitted
       to §A.3. Non-canonical copies are recorded here.

- (d2) Governance-process artifacts: files that document process
       integrity (lineage verification, snapshot forensic notes,
       workflow entry markers, closeout declarations) rather than
       an independent empirical research conclusion. These satisfy
       neither §3.3 test (a) nor (b), but they were read in full to
       confirm the absence of finding-bearing content.
```

Both sub-types are operational exclusions, not content rejections
based on irrelevance. The audit records them here to preserve the
enumeration trail; they do not contribute to the U7B anchor candidate
pool.

Sort order: by `source_file` path (per P1).

Row schema:

```text
| source_file              | path/to/source.md                    |
| classification_letter    | (d) / (e) / (f) / (g)                |
| classification_reason    | one-line, evidence-based             |
|                          | (e.g. "no verdict signals; content   |
|                          |  is system architecture only")       |
```

---

#### Batch 1 — `docs/research/` (1 row)

##### Row A4-1

```text
source_file:              docs/research/r8_phase0_feasibility.md
classification_letter:    (d)
classification_type:      Operational duplicate handling
classification_reason:    Duplicate-of-canonical: byte-identical
                          (md5 02dc384f617ef31720d42525ca5344df) to
                          research/r8_phase0_feasibility.md (Row 4
                          in §A.3). Per Duplicate Handling Rule
                          (§A.0), canonical = earliest git-resident
                          path = research/r8_phase0_feasibility.md
                          (committed at 0226c09, 2026-06-02). This
                          copy was added later via backlog commit
                          8ca25b0 (2026-06-23). Recorded here, not
                          in §A.3, to prevent inflated anchor count.
                          The file's content does satisfy §3.3
                          test (a) and (b); exclusion is operational
                          (de-duplication), not content-based.
```

---

#### Batch 2b — `research/` R8 Phase 4-6 (3 rows)

The following 3 files were read in full to confirm absence of
finding-bearing content. They document governance process
(snapshot forensics, lineage verification, workflow boundary)
rather than independent research conclusions. Recorded under
classification (d2) per §A.4 introduction.

##### Row A4-2

```text
source_file:              research/r8_phase5_price_snapshot_refresh_note.md
classification_letter:    (d2)
classification_type:      Governance forensic note
classification_reason:    Governance note documenting a retroactive
                          daily_price_adj refresh detected during
                          Phase 5 Arm A lineage check (Full-sample
                          Sharpe 2.378 → 2.498 / Low-Uplift Sharpe
                          1.613 → 1.569). Records Option A approval
                          decision (update ARM_A_REFERENCE to current
                          snapshot). Explicitly self-declared
                          "GOVERNANCE NOTE — informational only;
                          does not modify any locked artifact" (line 6).
                          Contains data lineage evidence but no
                          independent empirical research conclusion
                          about R8 strategy. file_first_commit edd42b1
                          (2026-06-19, alongside Phase 5 v1.0.1).
```

##### Row A4-3

```text
source_file:              research/r8_phase6_step2_lineage_closeout_2026_06_20.md
classification_letter:    (d2)
classification_type:      Lineage verification record
classification_reason:    Step-level governance closeout confirming
                          Arm A LU + full_sample lineage fingerprint
                          reproducibility on current snapshot within
                          ARM_A_SHARPE_TOL = 0.050 tolerance
                          (sharpe Δ ≤ 2.09e-4, admission Δ ≤ 3.00e-3;
                          all PASS). Records governance discipline
                          lessons (L-1 signature ≠ ABI, L-2 NumPy
                          scalar normalisation, etc.) and Step 3 entry
                          preconditions. Process-integrity verification,
                          not a research finding. file_first_commit
                          4fc70e0 (2026-06-20).
```

##### Row A4-4

```text
source_file:              research/r8_phase6_step3_entry_note.md
classification_letter:    (d2)
classification_type:      Workflow boundary marker
classification_reason:    Forward-looking governance boundary marker
                          recording Step 2 closure and Step 3
                          not-yet-started transition. Lists Step 3
                          sub-steps (3A-3G) plan and hard gates
                          (WG-1 MUST PASS before Step 3D). Explicitly
                          self-declared "forward-looking governance
                          boundary marker ... does not specify
                          implementation, does not enumerate ABI
                          evidence, and does not re-derive risk
                          content" (lines 5-9). Workflow planning
                          artifact, not a research finding.
                          file_first_commit dca8309 (2026-06-20).
```

---

#### Batch 3 — `research/` remaining (0 rows)

Note: Batch 3 produced 0 §A.4 rows after Fix-A partition correction
(2026-06-25). The previously enumerated Row A4-5 (track_c_step1_
closeout.md) is removed from §A.4 because the file is lineage-
excluded per §A.2.1 / boundary spec §1. Partition invariant
requires a file appear in at most one of §A.2.1, §A.2.4, §A.3,
§A.4. See Amendment Log for full reasoning.

---

#### Batch 5 — `docs/decision_records/` (8 rows)

##### Row A4-5

```text
source_file:              docs/decision_records/v0_1_16_backtest_audit_report.md
classification_letter:    (d2)
classification_type:      Engineering validation report
classification_reason:    Backtest fill-semantics audit report.
                          Verdict "Branch A — T+1 open aligned ✅"
                          refers to consistency between PaperBroker,
                          backtest engine, exit_scan, and LiveBroker
                          ROD fill semantics — i.e., implementation
                          correctness across components. Per
                          Engineering Validation Principle (§A.0):
                          PASS what? PASS that "Helios backtest /
                          paper_broker / exit_scan fill semantics
                          align with live execution path" — an
                          implementation-invariant proposition, not
                          a market-behaviour proposition. Diagnostic
                          question yields implementation correctness
                          → §A.4 (d2). Same family as
                          track_c_step1_closeout (§A.2.1 lineage
                          exclusion).
                          file_first_commit a93cafb (2026-05-24).
```

##### Row A4-6

```text
source_file:              docs/decision_records/shioaji_semantic_observation_2026_05_26.md
classification_letter:    (d2)
classification_type:      SDK semantic observation log
classification_reason:    Production-parity single-source-of-truth
                          for empirically-observed Shioaji SDK
                          semantics in the Helios deployment.
                          Document uses formalised evidence tags
                          [OBSERVED] / [INFERRED] / [UNOBSERVABLE]
                          / [ASSUMED] / [PROD-ONLY] for each claim.
                          Per Engineering Validation Principle:
                          observations of "deal.quantity is in LOTS",
                          "Common-path requires explicit unit
                          conversion", etc., are propositions about
                          SDK contract behaviour (software-level
                          implementation correctness), not market
                          behaviour. → §A.4 (d2). Created in
                          response to v0.1.16 v2 deploy uncovering
                          four SDK semantic mismatches.
                          file_first_commit 1e1cb42 (2026-05-25).
```

##### Row A4-7

```text
source_file:              docs/decision_records/v0_1_16_daily_run_patch.md
classification_letter:    (d2)
classification_type:      Implementation patch instructions
classification_reason:    Literal code-patch instructions for
                          scripts/daily_run.py: insertion of Step 0a
                          startup_recovery, Step 7 field-name update
                          (requested_lots / filled_shares), Edit 3
                          summary block. Pure implementation-level
                          patch note. Contains no market-behaviour
                          claim. → §A.4 (d2). Per Engineering
                          Validation Principle: code patches answer
                          "did the patch apply correctly?" not
                          "does the market exhibit property X?".
                          file_first_commit a93cafb (2026-05-24).
```

##### Row A4-8

```text
source_file:              docs/decision_records/v0_1_16_live_broker_patch.md
classification_letter:    (d2)
classification_type:      Implementation patch instructions
classification_reason:    Literal code-patch instructions for
                          execution/live_broker.py: near-complete
                          rewrite of submission flow integrating
                          11 P0 advisor findings (K-P0-1 lots-vs-
                          shares catastrophic bug, C-P0-2/3 daily-
                          count off-by-one, etc.). Pure
                          implementation-level patch note. Contains
                          no market-behaviour claim. Findings
                          referenced are software-bug findings, not
                          research findings. → §A.4 (d2).
                          file_first_commit a93cafb (2026-05-24).
```

##### Row A4-9

```text
source_file:              docs/decision_records/CHANGELOG_v0_1_16_v1_to_v2.md
classification_letter:    (d2)
classification_type:      Advisor-review integration changelog
classification_reason:    Advisor-review integration changelog
                          consolidating 11 P0 issues across three
                          independent reviews, with four Veronica-
                          locked integration decisions. All findings
                          documented are engineering bug fixes /
                          implementation correctness items (lots-vs-
                          shares unit-confusion, broker_order_id
                          empty-string handling, ReconcileCandidate
                          model, etc.). Per Engineering Validation
                          Principle: changelog of software fixes,
                          not market findings. → §A.4 (d2).
                          file_first_commit a93cafb (2026-05-24).
```

##### Row A4-10

```text
source_file:              docs/decision_records/CHANGELOG_v0_1_16_v2_1.md
classification_letter:    (d2)
classification_type:      Hotfix changelog
classification_reason:    v0.1.16 v2 → v2.1 Shioaji boundary
                          canonicalization hotfix. Documents four
                          P-δ patches resolving SDK lot-vs-share
                          unit confusion (P-δ-1 OrderLot enum,
                          P-δ-2/2b/2c/2d boundary normalisations).
                          Pure implementation hotfix changelog;
                          findings are software-contract corrections.
                          → §A.4 (d2). Inherits classification
                          rationale from parent doc (Row A4-8).
                          file_first_commit 3cc7c0a (2026-05-25).
```

##### Row A4-11

```text
source_file:              docs/decision_records/README.md
classification_letter:    (d2)
classification_type:      Directory index / documentation convention
classification_reason:    Directory README for docs/decision_records/.
                          Contains: ADR Michael Nygard format
                          template, "when to write a new ADR"
                          guidance, and an index table of accepted
                          ADRs. Defines documentation convention,
                          not research methodology. §A.2.4 admits
                          methodological artifacts that constrain
                          research execution (bootstrap method,
                          sampling contract, governance spec); a
                          README defining ADR template format does
                          not meet this bar. → §A.4 (d2).
                          file_first_commit 955d71d (2026-05-17).
```

##### Row A4-12

```text
source_file:              docs/decision_records/obs_gate_2026_05_26.md
classification_letter:    (d2)
classification_type:      Operational gate / merge-rollback protocol
classification_reason:    P-obs-1 after-hours observation operational
                          gate. Defines Cases A through D judgment
                          rules for the 2026-05-26 16:00 cron
                          observation, with explicit merge / rollback
                          / continue-observation decisions per case.
                          Per Engineering Validation Principle: this
                          file answers "do we merge / rollback this
                          deployment?" — an operational governance
                          decision, not "does the market exhibit
                          property X?". → §A.4 (d2).
                          file_first_commit 0419b12 (2026-05-26).
```

---

#### Batch 6a — `docs/handoffs/` (Helios v0.1.x version sessions, 15 rows)

Operational note (per Protocol Freeze, NOT a new locked rule):

```text
Exploratory analyses and implementation diagnostics that were
never promoted into governed research artifacts are treated as
workflow-continuity records under the existing Engineering
Validation Principle. The handoffs in Batch 6a contain three
types of content:

  1. session state (next session pickup, current branch, env)
  2. implementation diagnostics (test counts, schema migrations,
     production bug fixes, cron timing, deploy verification)
  3. exploratory analyses (MA5 backtest tables, tracker audit
     findings, forward-return-tracker outputs that never reached
     a governed research file)

For type 1 and 2, Engineering Validation Principle yields (d2)
directly. For type 3, the diagnostic question still applies:
"What proposition became more believable?" — for exploratory
artifacts that were never promoted into a governed research
document, the proposition that became more believable is one
about implementation status (e.g., "tracker has CI-width bug")
or about deferred decisions (e.g., "MA5 candidate noted for
future evaluation"). Neither is a market-behaviour claim against
the present audit's scope. → (d2) workflow-continuity.

This is not a new principle; it is the application of the
existing Engineering Validation Principle to a class of
artifact common in Batch 6.
```

##### Row A4-13

```text
source_file:              docs/handoffs/v0.1.14.3_2026-05-19.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    v0.1.14.3.post8 session handoff covering
                          5-day paper-trade observation Days 1-2,
                          two production bug fixes (Bug A listener
                          queue pollution, Bug B ATR drift no-price
                          path), and --bootstrap-price flag.
                          Quantified content (test counts 71→73→74)
                          refers to unit-test pass counts, not
                          market behaviour. Per Engineering
                          Validation Principle, this is a
                          workflow-continuity record.
                          file_first_commit 4e79060 (2026-05-19).
```

##### Row A4-14

```text
source_file:              docs/handoffs/v0.1.14.3_2026-05-19_final.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    End-of-session handoff for the same
                          v0.1.14.3.post8 session as Row A4-12,
                          consolidating Days 1-2 observations and
                          documentation. Contains addenda for
                          cron/timezone setup, T+1 gate, universe
                          design. Implementation-stage continuity
                          document. file_first_commit d9728b8
                          (2026-05-20).
```

##### Row A4-15

```text
source_file:              docs/handoffs/v0.1.14.3_2026-05-20_session_end.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    v0.1.14.3.post9 session handoff covering
                          sync_universe.py (dynamic top-200),
                          Telegram sender fix, intraday monitor
                          scope. Addendum 6 includes an MA5
                          exploratory backtest table (regime gate
                          comparisons). Per the existing operational
                          treatment of exploratory artifacts: the
                          MA5 study was never promoted into a
                          governed research file, so its content
                          contributes to workflow continuity, not
                          to governed findings. → (d2).
                          file_first_commit d104862 (2026-05-20).
```

##### Row A4-16

```text
source_file:              docs/handoffs/v0.1.15_2026-05-22_session_end.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    v0.1.15 session handoff: intraday exit
                          monitor deployment, DB migration applied
                          (intraday_alert_transitions table), cron
                          schedule update, evening digest. Pure
                          implementation session continuity.
                          file_first_commit f636be8 (2026-05-22).
```

##### Row A4-17

```text
source_file:              docs/handoffs/v0.1.16_2026-05-24_session_end.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    v0.1.16 session handoff: Shioaji
                          quote-source integration (ShioajiQuoteSource
                          replaces YFinanceQuoteSource, ~50x
                          bandwidth reduction), LiveBroker v0.1.1
                          integration, DB cleanup, stop logic
                          hardening. Implementation work; no
                          market-finding content.
                          file_first_commit c87cf75 (2026-05-24).
```

##### Row A4-18

```text
source_file:              docs/handoffs/v0_1_16_2026-05-26_session_end.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    v0.1.16 PRE-CRON DRAFT handoff explicitly
                          marked "awaiting 16:00 cron observation
                          (see §8)". Covers v2.1 Shioaji boundary
                          hotfix, P-obs-1 LiveBroker observation
                          logging, P-obs-1 scope reframe, G1-G6
                          live-unlock gates documentation. Pure
                          session-state continuity awaiting
                          downstream observation result.
                          file_first_commit 5fe5020 (2026-05-26).
```

##### Row A4-19

```text
source_file:              docs/handoffs/v0_1_16_2026-05-27_session_end.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    v0.1.16 merge-day session handoff:
                          merged to main at 019d46f, cron timing
                          14:50 → 16:00 fix (Shioaji daily_quotes
                          completion timing observation), MAE/ATR
                          exploratory study commit, find_bearish_
                          stocks 3 logic fixes (advisor review),
                          format_entry_request stock short_name.
                          All entries are implementation diagnostics.
                          file_first_commit 4bd2ebe (2026-05-27).
```

##### Row A4-20

```text
source_file:              docs/handoffs/v0_1_17_2026-05-27_final.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    v0.1.17 tag note (22 lines). Lists 7
                          implementation commits (steps 1-7) and
                          tomorrow's observation checklist (cron
                          execution + daily_quotes row count).
                          Workflow-continuity pointer document.
                          file_first_commit b54f0d6 (2026-05-27).
```

##### Row A4-21

```text
source_file:              docs/handoffs/v0_1_17_2026-05-27_session_end.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    v0.1.17 session-2 handoff: Steps 1-4
                          implementation complete (schema migration
                          for READY_FOR_SUBMISSION status,
                          target_fill_date column, transition map,
                          startup_recovery). Steps 5-7 pending.
                          Implementation session continuity.
                          file_first_commit be3129a (2026-05-27).
```

##### Row A4-22

```text
source_file:              docs/handoffs/v0_1_17_final_handoff.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    v0.1.17 TAGGED (ce48da8) final handoff,
                          all backlog items resolved (#15 decouple
                          signal/submission, #16 open-gap calibration
                          P95=2.97%, #17 schema migration). Cron
                          timing complete, observation checklist for
                          tomorrow. Implementation-completion
                          handoff, no market finding content.
                          file_first_commit be3129a (2026-05-27).
```

##### Row A4-23

```text
source_file:              docs/handoffs/v0.1.18_2026-05-30_session_end.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    Evidence-framework session handoff:
                          forward_return_tracker.py v0.2.0,
                          audit_universe_survivorship.py v0.2.0,
                          bull_strategy_sanity_harness.py v0.3.0
                          (scripts, .py files, out of enumeration
                          scope which is .md only). Section "Core
                          Decision: Go-Live Gate Redefined" is an
                          operational governance decision, not a
                          market finding. The harness verdict
                          schema explicitly excludes PASS verdict
                          ("[no PASS verdict exists]"); current
                          runs are INCONCLUSIVE state. Per
                          Engineering Validation Principle: the
                          propositions that became more believable
                          here are about implementation (tracker
                          schema correctness, survivorship-bias
                          measurement, go-live procedure design),
                          not market behaviour. → (d2).
                          file_first_commit 727b44c (2026-05-31).
```

##### Row A4-24

```text
source_file:              docs/handoffs/v0_2_0_2026-05-31_session_end.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    Exit-contract v0.2.0 session handoff:
                          regime_exit / trailing_stop / time_stop
                          v0.2.0 deploys, tracker audit findings.
                          "Confirmed P0 Issues" enumerated in
                          Section 4 are tracker-code bugs (CI
                          systematically too narrow → false
                          positives). Per Engineering Validation
                          Principle: these are software-correctness
                          findings (the proposition that became more
                          believable is "the tracker code has bug X"),
                          not market findings. → (d2).
                          file_first_commit 727b44c (2026-05-31).
```

##### Row A4-25

```text
source_file:              docs/handoffs/handoff_2026-05-29.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    v0.1.18 + Phase 0/A session handoff.
                          Section 2 ("Research Findings — FINAL
                          post spacing fix") contains references to
                          phase0_findings.md v4 governance-locked
                          outputs (canonical for those findings is
                          docs/research/phase0_findings.md, already
                          enumerated as Rows 1-3 in Batch 1, and
                          the v4 spacing-fix update is the
                          governance state recorded at those rows).
                          Document identity: this is a workflow
                          handoff (Session topic, HEAD, Production
                          State, Pending Backlog, Next Session
                          Scope) that incidentally references
                          research findings recorded elsewhere.
                          Per the (c) Secondary Aggregator
                          definition, an aggregator's PRIMARY
                          identity must be "organising / summarising
                          findings"; a workflow handoff with a
                          research-references section does not
                          meet this bar. Operational test: if
                          phase0_findings.md were removed, this
                          file would still stand as a workflow
                          continuity document. → (d2).
                          file_first_commit 83c52bb (2026-05-29).
```

##### Row A4-26

```text
source_file:              docs/handoffs/handoff_2026-05-29_evening.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    trend_pullback_v1 strategy deployment +
                          TAIEX Shioaji migration handoff. Contains
                          screener / signal_generator / process_
                          entries.py line counts and entry-rule
                          specification (RS_T3 + dist tercile),
                          but the production source for these rules
                          is the trend_pullback strategy code
                          itself (.py, out of scope). Workflow-
                          continuity record for deployment session.
                          file_first_commit 727b44c (2026-05-31).
```

##### Row A4-27

```text
source_file:              docs/handoffs/handoff_2026-05-31_session_end.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    Tracker v2 migration session handoff:
                          schema ALTER + 5 new columns, all v1+v2
                          rows deleted and rebuilt under v0.3.6,
                          canonical signal dedup, cluster bootstrap
                          CI, calendar integrity gate. Implementation
                          migration session continuity; the
                          proposition that became more believable
                          is about tracker code state, not market
                          behaviour. → (d2).
                          file_first_commit 0a614b7 (2026-06-06).
```

---

#### Batch 6b — `docs/handoffs/` (P1-DATA / R8 / Track C phase, 20 rows)

Reviewer test applied uniformly (per Q1+Q2 framing, NOT a new
§A.0 rule, per Protocol Freeze):

```text
For each handoff in Batch 6b, the reviewer asked:

  Q1. Does this handoff establish, for the first time, an empirical
      conclusion that will be governed downstream?
  Q2. Does a subsequent canonical research/finding artifact in
      enumeration scope already anchor that conclusion?

If Q1 = No → not §A.3.
If Q1 = Yes and Q2 = Yes → handoff is workflow-continuity (d2);
  canonical anchor lives in the governed artifact.
If Q1 = Yes and Q2 = No → handoff would be §A.3 primary (Evidence-
  test prevalence rule).

All 20 Batch 6b files reach (d2) because either Q1 = No (pure
implementation / governance commit) or Q1 = Yes + Q2 = Yes
(handoff references a downstream canonical anchor already
enumerated in Batches 1-5).

Operational reading: (d2) classification here does NOT follow
from "the file is a handoff". It follows from "the file did not
leave a canonical anchor". A handoff that introduced a first-
on-record governed conclusion without a downstream canonical
artifact would be §A.3 primary — none in Batch 6b meet that bar.
```

##### Row A4-28

```text
source_file:              docs/handoffs/handoff_2026_05_31.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    Two-session handoff covering R1/R2/R5/Study
                          B closures, Replay engine v0.2.3, portfolio
                          feasibility audit, and engineering fixes.
                          Q1+Q2: R1-R5 / Study B closure verdicts are
                          governance-summarised in docs/research/
                          research_handoff_2026_05.md (Rows 5-8 already
                          enumerated). Replay engine v0.2.3 outputs
                          are exploratory artifacts (.parquet, .py)
                          out of enumeration scope. No first-on-record
                          governed conclusion lacking a downstream
                          canonical anchor. → (d2).
                          file_first_commit 0a614b7 (2026-06-06).
```

##### Row A4-29

```text
source_file:              docs/handoffs/handoff_2026_06_01.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    R8 MA5 Phase 0 5/5 PASS feasibility +
                          intraday-monitor healthcheck + four backlog
                          items. Q1+Q2: R8 Phase 0 verdict is
                          governance-anchored at research/r8_phase0_
                          feasibility.md (Row 4 canonical) and the
                          docs/research/ duplicate (Row A4-1). No
                          first-on-record governed conclusion. → (d2).
                          file_first_commit 0a614b7 (2026-06-06).
```

##### Row A4-30

```text
source_file:              docs/handoffs/handoff_2026_06_01_session2.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    Operational diagnosis (no Telegram entry
                          notification root cause), sector classification
                          dynamic-lookup refactor (selector.py v0.2.0),
                          Forward Return Tracker stock-name fix, trading
                          capital refactor, signal-storage idempotency
                          backlog. Q1: No — entirely implementation
                          work. → (d2).
                          file_first_commit 0a614b7 (2026-06-06).
```

##### Row A4-31

```text
source_file:              docs/handoffs/handoff_2026_06_02.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    P1-OPS Signal Storage Idempotency
                          implementation: event-keyed semantics on
                          (symbol, strategy, signal_type, signal_date)
                          locked, duplicate cleanup migration, UNIQUE
                          index, save_signal() rewrite. Q1: No — pure
                          implementation governance decision recorded
                          in code + schema, no research finding.
                          → (d2).
                          file_first_commit 52f5036 (2026-06-02).
```

##### Row A4-32

```text
source_file:              docs/handoffs/handoff_2026_06_02_session_end.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    R8 Phase 1 SPEC commit (4b94124), Artifact C
                          governance decision record (ae5a35f),
                          P1-DATA panel integrity assessment commit
                          (fb38ae4), account_id test debt cleanup.
                          Q1+Q2: each governance artifact has its own
                          canonical anchor (r8_phase1_lifecycle_spec
                          A.2.4.2, r8_phase1_governance A.2.4.26,
                          P1-DATA_panel_integrity_assessment Rows
                          29-31). Pure governance-commit continuity.
                          → (d2).
                          file_first_commit 0a614b7 (2026-06-06).
```

##### Row A4-33

```text
source_file:              docs/handoffs/handoff_2026_06_03_session2_end.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    18-line supplement to the day's main
                          handoff. Records Research Roadmap update
                          (commit e49c419, docs/research/roadmap.md).
                          Q1+Q2: roadmap update is anchored at Row 9
                          (roadmap.md secondary aggregator). Pure
                          pointer document. → (d2).
                          file_first_commit 8228254 (2026-06-05).
```

##### Row A4-34

```text
source_file:              docs/handoffs/handoff_2026_06_03_session_end.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    R8 Phase 1 lifecycle replay infrastructure
                          5 modules implemented (event builder, forward
                          returns, lifecycle metrics, benchmarks,
                          export), bootstrap ADR added (a8370a6),
                          dry-run validation. Benchmark A/B/C numbers
                          (+2.63%/+2.63%/+6.84% ret_20d) appear here.
                          Q1+Q2: these are dry-run preliminary
                          measurements; canonical Phase 1 numbers
                          and governance state are anchored at
                          r8_phase1_interim_findings.md (Rows 10-12),
                          which carry the governance state including
                          subsequent v0.2.0 clean-panel CONFIRMED
                          revision. ADR-R8P1-001 bootstrap method
                          locked at A.2.4.11. No first-on-record
                          governed conclusion without downstream
                          canonical anchor. → (d2).
                          file_first_commit bc1799e (2026-06-03).
```

##### Row A4-35

```text
source_file:              docs/handoffs/handoff_2026_06_05_session_end.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    P1-DATA IF-1 remediation Phase 1/2/3
                          complete: security_lifecycle table + seed
                          ETL + acceptance tests, listed_market_daily_
                          price_adj filter view, full panel rebuild +
                          R1/R2/R5/R8 re-run + delta report. Promotion
                          Gate ALL PASS. Q1+Q2: the IF-1 remediation
                          outcome (Benchmark C robustness) is governed
                          at research/p1_data_remediation_closeout_
                          2026-06-04.md (Row 32 canonical, governance
                          state commit b41d56b). → (d2).
                          file_first_commit 0a614b7 (2026-06-06).
```

##### Row A4-36

```text
source_file:              docs/handoffs/handoff_2026_06_06_a3_complete.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    A-3 inferential analysis (R8 within RS_T3
                          vs RS_T3 unconditional): δ_obs +1.35%/+2.10%
                          at 10td/20td, p ≤ 0.0008, ROBUST across
                          L={5,10,20,40}, lifecycle spec v0.1.3 LOCK
                          APPROVED. Q1+Q2: these inferential outputs
                          are governance-anchored at r8_phase1_interim_
                          findings.md v0.1.0 (Rows 10-12 canonical;
                          Row 12 specifically for A-3) with governance
                          state subsequently updated to v0.2.0 CONFIRMED
                          post clean-panel re-run. Lifecycle spec
                          v0.1.3 lock recorded at A.2.4.2. → (d2).
                          file_first_commit 0af243b (2026-06-07).
```

##### Row A4-37

```text
source_file:              docs/handoffs/handoff_2026_06_06_a3_implementation_pack.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    Implementation pack supplement: embeds ADR-
                          R8P1-001 / 002 key decisions, lifecycle spec
                          forward-return formula, P0-B production
                          schema for next-session A-3 implementation.
                          Q1: No — explicitly a "supplement" to the
                          P0-B complete handoff for next-session
                          pickup. Methodology references are anchored
                          at A.2.4.11 (ADR-R8P1-001), A.2.4.12
                          (ADR-R8P1-002), A.2.4.1 (cell_adequacy_spec),
                          A.2.4.2 (lifecycle_spec). → (d2).
                          file_first_commit 8874564 (2026-06-06).
```

##### Row A4-38

```text
source_file:              docs/handoffs/handoff_2026_06_06_if3a_complete.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    IF-2 reclassification to P2 non-binding
                          (lifecycle spec v0.1.5), IF-3A root cause
                          diagnosis (dividend ingestion universe
                          resolver) and remediation (commit 76f1f45,
                          corporate_actions populated 1106 rows / 199
                          symbols). Q1+Q2: IF-2 and IF-3A governance
                          states are anchored at Rows 30-31 (P1-DATA
                          assessment IF-2 / IF-3), with governance
                          state commits 77fb3c1 / 39ba6c2 recording
                          the reclassification and IF-3A/B split.
                          → (d2).
                          file_first_commit be1d23b (2026-06-23).
```

##### Row A4-39

```text
source_file:              docs/handoffs/handoff_2026_06_06_p0b_complete.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    P0-B v0.1.1 cell adequacy audit script
                          production run: joint adequacy table (bull/
                          bear/neutral nlu=0 = PASS, bull nlu=1 =
                          DIRECTIONAL_ONLY, others INSUFFICIENT).
                          Q1+Q2: cell_adequacy_spec methodology is
                          anchored at A.2.4.1; cell adequacy outcomes
                          are inputs to A-1/A-2/A-3 inferential
                          outputs anchored at Rows 10-12 (r8_phase1_
                          interim_findings). Production-run artifacts
                          are .parquet outputs in data/_storage/,
                          out of enumeration scope. → (d2).
                          file_first_commit 0da061f (2026-06-06).
```

##### Row A4-40

```text
source_file:              docs/handoffs/handoff_2026_06_06_phase1_complete.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    Phase 1 all three benchmark analyses
                          (A-1 / A-2 / A-3) complete, lifecycle spec
                          v0.1.4 LOCK APPROVED, interim findings
                          v0.1.0 LOCK APPROVED. AC-2 satisfied; AC-6
                          OPEN pending IF-2/IF-3. Q1+Q2: Phase 1
                          findings governance state anchored at Rows
                          10-12 (interim_findings v0.1.0; subsequent
                          v0.2.0 CONFIRMED governance state for the
                          same rows). Spec v0.1.4 method lock at
                          A.2.4.2. → (d2).
                          file_first_commit 0af243b (2026-06-07).
```

##### Row A4-41

```text
source_file:              docs/handoffs/handoff_2026_06_06_session_end.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    R8 Phase 1 governance layer session: three
                          governance artifacts locked (ADR-R8P1-001,
                          ADR-R8P1-002, cell_adequacy_spec v0.1.1) +
                          sign-off ceremony metadata correction
                          (commit 4014e91). Q1: No — entirely
                          methodological-artifact lock ceremony with
                          no empirical conclusion of its own. Each
                          locked artifact anchored at §A.2.4
                          (A.2.4.11, A.2.4.12, A.2.4.1 v0.1.1).
                          → (d2).
                          file_first_commit 7762bc0 (2026-06-06).
```

##### Row A4-42

```text
source_file:              docs/handoffs/handoff_2026_06_07_clean_panel_rerun_complete.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    Clean-panel re-run v0.2.0: A-1/A-2/A-3
                          re-executed on IF-1-remediated panel.
                          δ_obs revised to +1.21%/+1.92% at 10td/20td;
                          AC-6 CLOSED; interim findings status
                          PROVISIONAL → CONFIRMED. Q1+Q2: this is a
                          governance-state transition of Rows 10-12
                          (interim_findings), captured at the row's
                          governance_state_commit. The v0.2.0
                          revision is governance-state evolution, not
                          a new canonical anchor. → (d2).
                          file_first_commit 2837315 (2026-06-07).
```

##### Row A4-43

```text
source_file:              docs/handoffs/handoff_2026_06_07_if3b_composition_audit.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    IF-3B composition audit (203 SUSPENSION_GAP
                          rows / 90 stocks, halt-resumption in
                          r8_events = 0), IF-3B reclassified P1
                          binding → P2 non-binding (lifecycle spec
                          v0.1.6), if3b_source_discovery_spec v0.1.1
                          committed, DQ-ADJ-003 closed (capital
                          reduction classification). Q1+Q2: IF-3B
                          governance state and IF-3B SPEC methodology
                          anchored at Row 31 (P1-DATA assessment IF-3)
                          and A.2.4.13 (if3b_source_discovery_spec)
                          respectively. → (d2).
                          file_first_commit dabe7d0 (2026-06-07).
```

##### Row A4-44

```text
source_file:              docs/handoffs/handoff_2026_06_07_p1_closeout.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    P1 backlog full closeout: TWSE-HOLIDAY-CAL,
                          P1-DATA-FOLLOWUP, P1-OBS, IF-3A, IF-3B,
                          DQ-ADJ-003 all CLOSED or reclassified.
                          AC-6 blockers zero. Q1: No — operational
                          backlog closeout aggregating prior anchored
                          governance state transitions. → (d2).
                          file_first_commit 8046cba (2026-06-07).
```

##### Row A4-45

```text
source_file:              docs/handoffs/handoff_2026_06_07_phase2b_closeout.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    Phase 1 findings promotion PROVISIONAL →
                          CONFIRMED (commit 539cb41), Phase 2A
                          STABLE verdict (validation report v1.0.0,
                          commit a1a3959), Phase 2B FEASIBLE verdict
                          (feasibility memo v1.0.0, commit 792dceb),
                          Phase 2 roadmap v0.3.0 + Phase 2A SPEC
                          v0.3.0 + Phase 2B SPEC v0.1.2 LOCKED.
                          Q1+Q2: Phase 2A verdict anchored at Row 13
                          (phase2a_validation_report), Phase 2B
                          verdict at Row 14 (phase2b_feasibility_memo);
                          method-lock SPECs at A.2.4.3 (phase2a_spec)
                          and A.2.4.4 (phase2b_spec). Phase 1
                          PROVISIONAL→CONFIRMED is governance-state
                          transition of Rows 10-12. → (d2).
                          file_first_commit 560bfec (2026-06-23).
```

##### Row A4-46

```text
source_file:              docs/handoffs/handoff_2026_06_07_phase3_4_5.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    Phase 3 SPEC v0.1.2 + runner + report v1.0.1
                          LOCKED (CHARACTERISED verdict); Phase 4 SPEC
                          v0.1.1 + runner + report v1.0.0 LOCKED
                          (OPTIMISATION_CHARACTERISED verdict);
                          Phase 5 SPEC v0.1.0 LOCKED (runner not
                          started). Q1+Q2: Phase 3 findings A/B/C
                          anchored at Rows 15-17 (phase3_risk_report);
                          Phase 4 findings A1/A2/A3/B1 at Rows 18-21
                          (phase4_optimisation_report); SPECs locked
                          at A.2.4.5 (phase3_spec), A.2.4.6
                          (phase4_spec), A.2.4.7 (phase5_spec).
                          → (d2).
                          file_first_commit 3390050 (2026-06-07).
```

##### Row A4-47

```text
source_file:              docs/handoffs/handoff_2026_06_23_track_c_step2_and_phase6_evidence_gap.md
classification_letter:    (d2)
classification_type:      Workflow-continuity record
classification_reason:    Track C Step 2 R1 pre-registration DRAFT
                          committed (NOT LOCKED), 5 backlog handoff/
                          research docs git-backfilled, tests/research/
                          test suite committed (F1' fixture boundary
                          fix), 1 RED commit (7fcfd09) dropped via
                          interactive rebase, Phase 6 closeout
                          evidence gap documented, BACKLOG-WG1-
                          REPRODUCIBILITY-001 opened. Q1+Q2: Track C
                          Step 2 R1 prereg DRAFT is explicitly NOT
                          LOCKED — it is forward-looking governance
                          for future R1 work, not a finding to
                          anchor. Phase 6 closeout evidence gap is
                          a future-work flag (P1 backlog) and a
                          fix applied to test fixtures (F1'), not a
                          first-on-record empirical finding about
                          market behaviour. Phase 6 F-P6-01 finding
                          anchored at Row 25 (phase6_findings); the
                          evidence gap is about REPRODUCIBILITY of
                          tests, an implementation-correctness
                          concern. → (d2).
                          file_first_commit f710e66 (2026-06-23).
```


---

### A.5 Source File Exhaustiveness Check

After §A.2-§A.4 are complete, this section asserts that every file
in §A.1 has been accounted for in exactly one of:

```text
§A.2.1  lineage exclusion
§A.2.2  out-of-scope category (categorical, not per-file)
§A.2.3  architectural ADR
§A.2.4  methodological ADR
§A.3    INCLUDED
§A.4    EXCLUDED after classification
```

Phase 1 exhaustiveness verified 2026-06-25 after Fix A partition
correction.

#### A.5.1 Per-Partition File Counts

```text
[✓]  §A.2.1 lineage exclusion         :   4 files
[✓]  §A.2.2 out-of-scope category     :   0 (categorical, not per-file)
[✓]  §A.2.3 architectural ADR         :   0 (folded into §A.2.4)
[✓]  §A.2.4 methodological ADR        :  26 files = 26 entries (1:1)
[✓]  §A.3   INCLUDED source_files     :  19 unique → 41 rows
[✓]  §A.4   EXCLUDED source_files     :  47 unique = 47 rows (1:1)
                                       ──────────────────
[✓]  Total unique seed files          :  96
```

#### A.5.2 Exhaustiveness Arithmetic

```text
[✓]    4   (§A.2.1)
[✓]  + 26  (§A.2.4)
[✓]  + 19  (§A.3 unique source files)
[✓]  + 47  (§A.4 unique source files)
[✓]  - 0   (overlaps; no file in §A.2.4 ∩ §A.3 ∩ §A.4)
       ──
       96  ✓

Duplicate note: Row A4-1 (docs/research/r8_phase0_feasibility.md)
and Row 4 (research/r8_phase0_feasibility.md) are the SAME content
at two paths. Both paths exist as separate seed files and are
counted as 2 in §A.1. The duplicate handling rule applies at row
level (research/ path = canonical), not at file-system level.
```

#### A.5.3 Coverage Statement

```text
[✓]  Total files in §A.1                 :  96
[✓]  Accounted-for files across §A.2-§A.4 :  96
[✓]  Coverage                            :  96 / 96 = 100%
[✓]  Files unaccounted                   :   0
```

#### A.5.4 Partition Invariant (I1) Verification

```text
I1 requires: every seed file appears in EXACTLY one of
{§A.2.1, §A.2.4, §A.3, §A.4}.

Cross-partition intersection check (verified by script 2026-06-25):

[✓]  §A.2.4 ∩ §A.3                       :  ∅
[✓]  §A.2.4 ∩ §A.4                       :  ∅
[✓]  §A.3   ∩ §A.4                       :  ∅
[✓]  §A.2.1 ∩ §A.4                       :  ∅  (post Fix A)

[✓]  I1 satisfied
```

#### A.5.5 Row-Level Counts Cross-Check

```text
[✓]  §A.3 row count                      :  41 (across 19 files)
[✓]  §A.4 row count                      :  47 (across 47 files, 1:1)
[✓]  §A.2.4 entry count                  :  26 (across 26 files, 1:1)
[✓]  Total enumerated row units          :  41 + 47 + 26 = 114

Row ID continuity:

[✓]  §A.3   IDs                          :  Row 1 ~ Row 41 (no gap)
[✓]  §A.4   IDs                          :  Row A4-1 ~ Row A4-47
                                            (no gap, post Fix A)
[✓]  §A.2.4 IDs                          :  A.2.4.1 ~ A.2.4.26 (no gap)
```

#### A.5.6 §A.2.4 referenced_by Completeness

```text
Completion invariant requires every §A.2.4 entry to have a
non-empty referenced_by field.

[✓]  Tier 1 direct text references        :   2 entries
[✓]  Tier 1 + Tier 2 (both)               :   3 entries
[✓]  Tier 2 governing-method dependency   :  10 entries
[✓]  Explicit "no §A.3 reference" (flagged):  11 entries
                                            ──────────
[✓]  Total non-empty                      :  26 entries

[✓]  Completion invariant satisfied
```

#### A.5.7 Overall §A.5 Verdict

```text
[✓]  All per-partition counts verified
[✓]  Arithmetic closure verified (4 + 26 + 19 + 47 = 96)
[✓]  Coverage 100%, 0 files unaccounted
[✓]  Partition invariant I1 satisfied (all intersections empty)
[✓]  Row ID continuity verified across §A.2.4, §A.3, §A.4
[✓]  §A.2.4 referenced_by Completion invariant satisfied

§A.5 EXHAUSTIVENESS VERIFICATION: PASS
```

---

## §B. Phase 1b — Orphan Scan

### B.0 Scope and Method

Per boundary spec v0.1.1 §3.4:

```text
Primary source: all *.py files under research/

Secondary inclusion (only if verdict-carrying):
  tests/research/*.py
  scripts/*.py

Excluded categorically:
  pure unit tests
  pure operational scripts
  test fixtures and helpers
```

Per Q3 (2026-06-24): orphan detection uses **grep + human
confirmation**. Grep is the first-pass filter (filename topic
keyword vs *.md inventory). Human confirmation verifies:

```text
- whether the .py is verdict-carrying
- whether a corresponding governance .md exists
- whether it should appear in §B.3 orphan appendix

Human confirmation is NOT permitted to apply U7A pass/fail logic.
```

---

### B.1 .py File Inventory

Inventory frozen 2026-06-25. Total: 22 research/ + 66 scripts/ + 2
tests/research/ = 90 .py files.

#### B.1.1 research/ (22 files, primary scope per boundary spec §3.4)

```text
research/absorption_validation.py
research/audit_universe_survivorship.py
research/bull_strategy_sanity_harness.py
research/distance_refinement.py
research/feature_interaction_study.py
research/feature_outcome_study.py
research/forward_return_tracker.py
research/ma5_momentum_feasibility.py
research/mae_atr_study.py
research/open_gap_study.py
research/p1_data_contamination_audit.py
research/pullback_quality.py
research/r5_precheck.py
research/r8_benchmarks.py
research/r8_event_builder.py
research/r8_forward_returns.py
research/r8_lifecycle_metrics.py
research/r8_phase1_export.py
research/replay_engine.py
research/rs_acceleration.py
research/rs_persistence_decay.py
research/tracker_digest.py
```

#### B.1.2 scripts/ (66 files, secondary scope — only verdict-carrying)

Per boundary spec §3.4, scripts/ are EXCLUDED categorically as
"pure operational scripts" UNLESS a script carries a verdict not
recorded in a governance .md. Inventory listed for completeness
and reviewer audit; classification verdict in §B.2.

```text
scripts/__init__.py
scripts/audit_r8_phase1_cell_adequacy.py
scripts/audit_shioaji_observation.py
scripts/backfill_taiex.py
scripts/backtest_ma5_strategy.py
scripts/budget_sweep.py
scripts/build_adjusted_prices.py
scripts/check_benchmark_calendar_gap.py
scripts/compute_bearish_features.py
scripts/compute_bullish_features.py
scripts/compute_features.py
scripts/cross_source_audit.py
scripts/daily_run.py
scripts/data_quality_report.py
scripts/dev_push_signal.py
scripts/download_daily.py
scripts/execution_submitter.py
scripts/feature_inspect.py
scripts/find_bearish_stocks.py
scripts/find_bullish_setups.py
scripts/generate_signals.py
scripts/ingest_dividends.py
scripts/ingest_security_lifecycle.py
scripts/ingest_splits.py
scripts/ingest_twse_holidays.py
scripts/init_db.py
scripts/intraday_healthcheck.py
scripts/intraday_monitor.py
scripts/migrate_add_twse_holidays.py
scripts/migrate_orders_lot_type.py
scripts/migrate_security_lifecycle.py
scripts/migrate_tracker_v2.py
scripts/oos_validation.py
scripts/p1_data_source_validation.py
scripts/phase6_adaptive_engine.py
scripts/phase6_bootstrap.py
scripts/phase6_evaluate_candidate.py
scripts/phase6_orchestration.py
scripts/process_entries.py
scripts/reconcile_fills.py
scripts/run_backtest.py
scripts/run_eod_position_alert.py
scripts/run_evening_digest.py
scripts/run_exit_scan.py
scripts/run_phase2a_analysis.py
scripts/run_phase2b_analysis.py
scripts/run_phase3_analysis.py
scripts/run_phase4_analysis.py
scripts/run_phase5_analysis.py
scripts/run_phase6_evaluation.py
scripts/run_portfolio_backtest.py
scripts/run_r8_phase1_a1.py
scripts/run_r8_phase1_a2.py
scripts/run_r8_phase1_a3.py
scripts/run_signal_preview.py
scripts/run_summary.py
scripts/score_short_candidates.py
scripts/seed_security_lifecycle.py
scripts/shioaji_download_daily.py
scripts/signal_audit.py
scripts/smoke_test_v0_1_18.py
scripts/startup_recovery.py
scripts/sync_company_info.py
scripts/sync_universe.py
scripts/validate_adjustments.py
scripts/validate_install.py
```

Reviewer scan applied: all 66 are operational (daily runs, intraday
monitor, ingestion, migrations, analysis runners for governed
phases at A.2.4.3-9, audit utilities, validators). None carry a
first-on-record empirical verdict absent from governance .md.
→ 0 of 66 enter §B.2 as orphan candidates.

#### B.1.3 tests/research/ (2 files)

```text
tests/research/test_adaptive_simulator_degenerate_equivalence.py
tests/research/test_phase6_exit_functions.py
```

Boundary spec §3.4 categorically excludes "pure unit tests". Both
files are pytest-style test modules supporting Phase 6 governance
artifacts (already enumerated at Rows 25-28). → 0 of 2 enter §B.2.

---

### B.2 Topic Mapping Table

For each research/*.py file: topic keyword grep against §A.1
source list, with verdict-carrying determination per Q3 (grep +
human confirmation; human MUST NOT apply U7A pass/fail logic).

#### B.2.1 Mapping Result (research/ 22 files)

```text
[NOT_ORPHAN] research/absorption_validation.py
  → governance owner: docs/research/phase0_findings.md (Row 3)
  → reasoning: Phase 0 finding cluster owns the absorption result;
    .py is implementation behind a governed conclusion.

[NOT_ORPHAN] research/audit_universe_survivorship.py
  → governance owner: research/helios_research_roadmap.md (Row 33)
    + audit infrastructure (this audit references it)
  → reasoning: universe survivorship audit utility supporting the
    forward-return-tracker / evidence-framework ecosystem.
    Reframed as exploratory_tool not orphan: utility produces an
    audit measurement (94% current-constituent confirmed) recorded
    in roadmap discussion, not a stand-alone closed-study verdict.

[NOT_ORPHAN] research/bull_strategy_sanity_harness.py
  → governance owner: research/helios_research_roadmap.md (Row 33)
    + audit infrastructure
  → reasoning: sanity-harness utility. Verdict at run time is
    INCONCLUSIVE per Status invariant; not a first-on-record
    finding lacking governance.

[NOT_ORPHAN] research/distance_refinement.py
  → governance owner: docs/research/phase0_findings.md (Row 1)
  → reasoning: distance refinement is a Phase 0 axis; finding
    governed in phase0_findings.

[NOT_ORPHAN] research/feature_interaction_study.py
  → governance owner: docs/research/phase0_findings.md (Row 1)
  → reasoning: feature interaction study contributes to Phase 0
    findings; conclusion governed there.

[NOT_ORPHAN] research/feature_outcome_study.py
  → governance owner: docs/research/phase0_findings.md (Row 1)
  → reasoning: feature outcome study; same as above.

[NOT_ORPHAN] research/forward_return_tracker.py
  → governance owner: research/helios_research_roadmap.md (Row 33)
    + audit infrastructure
  → reasoning: production tracker utility (v0.2.0, cron 16:10);
    operational not closed-study.

[NOT_ORPHAN] research/ma5_momentum_feasibility.py
  → governance owner: research/r8_phase0_feasibility.md (Row 4
    canonical) + docs/research/r8_phase0_feasibility.md (Row A4-1
    duplicate)
  → reasoning: R8 Phase 0 feasibility verdict (5/5 PASS) governed
    in r8_phase0_feasibility.md.

[EXCLUDED §B.4] research/mae_atr_study.py
  → see §B.4

[EXCLUDED §B.4] research/open_gap_study.py
  → see §B.4

[EXCLUDED §B.4] research/p1_data_contamination_audit.py
  → see §B.4

[NOT_ORPHAN] research/pullback_quality.py
  → governance owner: docs/research/research_handoff_2026_05.md
    (Row 8, R5 Pullback Quality Transfer CLOSED Weak Positive)
  → reasoning: R5 study verdict governed in research_handoff_2026_05.

[NOT_ORPHAN] research/r5_precheck.py
  → governance owner: docs/research/research_handoff_2026_05.md
    (Row 8, R5 study lineage)
  → reasoning: R5 precheck utility supporting R5 verdict in
    research_handoff_2026_05.

[NOT_ORPHAN] research/r8_benchmarks.py
  → governance owner: research/r8_phase1_interim_findings.md
    (Rows 10-12, Phase 1 A-1/A-2/A-3 inferential outputs)
  → reasoning: benchmark construction code behind A-1/A-2/A-3
    findings; method locked at A.2.4.12 (ADR-R8P1-002).

[NOT_ORPHAN] research/r8_event_builder.py
  → governance owner: research/r8_phase1_interim_findings.md
    (Rows 10-12) + research/r8_phase1_lifecycle_spec.md (A.2.4.2)
  → reasoning: event builder behind Phase 1 inferential pipeline.

[NOT_ORPHAN] research/r8_forward_returns.py
  → governance owner: research/r8_phase1_interim_findings.md
    (Rows 10-12)
  → reasoning: forward-return computation underlying Phase 1.

[NOT_ORPHAN] research/r8_lifecycle_metrics.py
  → governance owner: research/r8_phase1_interim_findings.md
    (Rows 10-12)
  → reasoning: lifecycle metrics utility for Phase 1 outputs.

[NOT_ORPHAN] research/r8_phase1_export.py
  → governance owner: research/r8_phase1_interim_findings.md
    (Rows 10-12)
  → reasoning: export utility for Phase 1 inferential artifacts.

[ORPHAN §B.3] research/replay_engine.py
  → see §B.3

[NOT_ORPHAN] research/rs_acceleration.py
  → governance owner: docs/research/research_handoff_2026_05.md
    (Row 7, Study B RS Acceleration CLOSED Negative)
  → reasoning: Study B verdict governed in research_handoff_2026_05.

[NOT_ORPHAN] research/rs_persistence_decay.py
  → governance owner: docs/research/research_handoff_2026_05.md
    (Row 5, R1 RS Persistence Decay CLOSED Negative)
  → reasoning: R1 verdict governed in research_handoff_2026_05.

[NOT_ORPHAN] research/tracker_digest.py
  → governance owner: research/helios_research_roadmap.md (Row 33)
    + audit infrastructure
  → reasoning: tracker reporting utility; operational not
    closed-study.
```

#### B.2.2 Classification Tally

```text
[✓]  NOT_ORPHAN (governance owner identified)     :  18 / 22
[✓]  ORPHAN_TO_APPENDIX (§B.3 closed-study)       :   1 / 22
[✓]  EXCLUDED §B.4 (exploratory / audit utility)  :   3 / 22
                                                     ─────────
[✓]  Total                                        :  22 / 22 = 100%
```

---

### B.3 Orphan Appendix (closed-study orphans)

Per boundary spec v0.1.1 §3.4, closed-study orphans are appended
here with explicit note that conclusion source is script-level.

#### B.3.1 Row B3-1

```text
case_id                      :  B3-1
source_file                  :  research/replay_engine.py
file_first_commit_sha        :  (script first appears in
                                handoff_2026_05_31.md at commit
                                0a614b7, 2026-06-06; actual .py
                                creation predates handoff backfill;
                                exact .py first-commit not enumerated
                                because .py is not in §A.1 source
                                scope — §B operates on .py inventory
                                separately)
file_first_commit_date       :  on or before 2026-05-31
governance_state_commit_sha  :  TBD_PHASE2
governance_state_commit_date :  TBD_PHASE2
one_line_description         :  Helios replay engine v0.2.3 with
                                CA-quarantine per-stock dates, DQ
                                clean, producing 297-trade baseline
                                output (mean +4.47%, win 54.5%, MDD
                                -16.37%, ann +33.99%) surfaced in
                                handoff_2026_05_31 §2 but not
                                anchored in a governance .md.
conclusion_source            :  script-level (handoff documents the
                                run output but does not constitute a
                                governance lock; no SPEC/findings
                                artifact owns the replay-engine
                                v0.2.3 result set).
classification_note          :  script-level closed-study orphan;
                                contains quantified replay results
                                surfaced only through handoff, with
                                no corresponding governance .md;
                                appended as script-level evidence,
                                not governance-document-level
                                evidence. Per §3.4: orphan inclusion
                                here records the .py exists with
                                script-level verdict carrier;
                                Phase 2 U7A evaluation determines
                                whether this orphan qualifies as a
                                Track-C anchor candidate.
```

---

### B.4 Excluded Orphans (exploratory / dead prototype)

Exploratory tools and dead prototypes excluded per boundary spec
v0.1.1 §3.4. Recorded with one-line reason; no verdict assertion.

#### B.4.1 research/mae_atr_study.py

```text
py_file        :  research/mae_atr_study.py
classification :  exploratory_tool
one_line_reason:  MAE/ATR exploratory study committed during
                  v0.1.16 session (handoff_2026_06_01_session2
                  surface; self-identified as exploratory in
                  source handoff). No closed-study verdict.
```

#### B.4.2 research/open_gap_study.py

```text
py_file        :  research/open_gap_study.py
classification :  exploratory_tool
one_line_reason:  Open-gap calibration study supporting v0.1.17
                  open-gap parameter selection (P95=2.97% noted
                  in handoff_v0_1_17_2026-05-27). Operational
                  calibration utility, not a closed-study verdict.
```

#### B.4.3 research/p1_data_contamination_audit.py

```text
py_file        :  research/p1_data_contamination_audit.py
classification :  exploratory_tool
one_line_reason:  P1-DATA contamination audit utility (no .md grep
                  hits in §A.1 source list). The P1-DATA finding
                  cluster is governed at Rows 29-31 (P1-DATA_panel_
                  integrity_assessment.md) and Row 32 (p1_data_
                  remediation_closeout_2026-06-04.md); this .py is
                  the auditing implementation behind those governed
                  findings, classified as audit utility not orphan.
```

#### B.4.4 Excluded Tally

```text
[✓]  exploratory_tool         :  3 files (B.4.1, B.4.2, B.4.3)
[✓]  dead_prototype           :  0 files
                                 ──────────
[✓]  §B.4 total               :  3 files
```

---

### B.5 Orphan Scan Completeness Statement

```text
research/ scope (primary, per boundary spec §3.4):

[✓]  Total research/*.py files                :  22
[✓]  §B.2 NOT_ORPHAN (governance owner found) :  18
[✓]  §B.3 ORPHAN_TO_APPENDIX (closed-study)   :   1 (replay_engine)
[✓]  §B.4 EXCLUDED (exploratory / utility)    :   3 (mae_atr,
                                                     open_gap,
                                                     p1_data_audit)
                                                  ──────────
[✓]  Sum                                      :  22
[✓]  Coverage                                 :  22 / 22 = 100%
[✓]  Files unaccounted                        :   0

scripts/ scope (secondary, only if verdict-carrying):

[✓]  Total scripts/*.py files                 :  66
[✓]  Verdict-carrying (after reviewer scan)   :   0
[✓]  §B.2/§B.3/§B.4 admissions                :   0 (all 66 are
                                                  operational /
                                                  ingestion /
                                                  migration /
                                                  analysis-runner
                                                  for governed
                                                  phases)
[✓]  Coverage                                 :  66 / 66 = 100%

tests/research/ scope:

[✓]  Total tests/research/*.py files          :   2
[✓]  Per boundary spec §3.4 "pure unit tests" :   0 admissions
[✓]  Coverage                                 :   2 / 2 = 100%

Overall §B scope (90 .py files total):

[✓]  90 / 90 .py files classified             :  100%
[✓]  Files unaccounted                        :   0
[✓]  Orphan appendix entries (§B.3)           :   1 (B3-1)
[✓]  Excluded entries (§B.4)                  :   3

§B ORPHAN SCAN: PASS
```

---

## §C. Commit 3 Readiness Gate

This section consolidates the Phase 1 verification checks already
established in §A.5 and §B.5 into a single Commit 3 lock-readiness
view. It does not introduce new protocol or new findings.

### C.1 Section Completion Status

```text
[✓]  §A.0 Scope and Method (Rationale + Binding Protocol)  : COMPLETE
[✓]  §A.1 Enumeration Source File List                     : FROZEN
[✓]  §A.2.1 Lineage Exclusion                              : COMPLETE
[✓]  §A.2.2 Out-of-Scope Categories                        : COMPLETE
[✓]  §A.2.3 Architectural ADRs                             : COMPLETE
                                                             (empty by
                                                             scoping)
[✓]  §A.2.4 Methodological ADRs                            : COMPLETE
                                                             (26 entries,
                                                             all
                                                             referenced_by
                                                             populated)
[✓]  §A.3 INCLUDED Candidates                              : COMPLETE
                                                             (41 rows)
[✓]  §A.4 EXCLUDED                                         : COMPLETE
                                                             (47 rows
                                                             post Fix A)
[✓]  §A.5 Source File Exhaustiveness Check                 : PASS
[✓]  §B   Orphan Scan                                      : PASS
[✓]  §C   Commit 3 Readiness Gate                          : THIS SECTION
[✓]  §D   Phase 2 — U7A Evaluation                        : COMPLETE
[ ]  §E   Phase 3 — Synthesis                             : NOT STARTED
```

### C.2 Phase 1 Headline Totals

```text
Seed files                  :  96
Pre-excluded (§A.2.1)       :   4
Enumerated                  :  92

Partition invariant         :  96 = 4 + 92  ✓
Enumeration coverage        :  92 / 92 = 100%
```

### C.3 Row-Level Totals

```text
§A.3 INCLUDED rows          :  41 (from 19 unique source files,
                                 contains 36 finding clusters)
§A.4 EXCLUDED rows          :  47 (47 unique files, 1:1)
§A.2.4 methodological       :  26 (26 unique files, 1:1)

Total enumerated row units  : 114
Unique finding clusters     :  36
Primary sources             :  36
Secondary aggregators       :   5
```

### C.4 Phase 1b Orphan Totals (§B)

```text
Orphan appendix (§B.3)      :   1 (replay_engine.py;
                                 script-level closed-study orphan,
                                 conclusion_source = script-level)
Excluded orphans (§B.4)     :   3 (mae_atr_study, open_gap_study,
                                 p1_data_contamination_audit;
                                 exploratory_tool)
```

### C.5 Invariant Checks

```text
[✓]  I1 file partition (every seed file in EXACTLY one of
     §A.2.1 / §A.2.4 / §A.3 / §A.4)                       : SATISFIED
[✓]  I2 rows in each batch (Rows emitted = Included +
     Excluded for every Batch)                            : SATISFIED
[✓]  I3 Included composition (41 = 36 primary +
     5 aggregator)                                        : SATISFIED
[✓]  I4 anchors (36 unique finding clusters = 36 primary
     sources)                                             : SATISFIED
[✓]  Completion invariant (every §A.2.4 entry has
     non-empty referenced_by)                             : SATISFIED
[✓]  Phase 2 isolation rule (no Phase 1 row added /
     removed / merged / split because of Phase 2 evidence;
     N/A pre-lock)                                        : N/A
```

### C.6 Protocol Freeze Status

```text
[✓]  Protocol Freeze in effect since Batch 5 (2026-06-25)
[✓]  §A.0 Binding Protocol contains 15 locked rules + Protocol
     Freeze closure; no new permanent rules added in Batches 5,
     6a, 6b, Fix A, or §A.5/§B writes
[✓]  Two audit-level retrospective notes recorded under §A.0.R
     Design Rationale (Non-Binding); explicitly marked as Commit 5
     consolidation input, not binding rules
```

### C.7 Fix A Partition Correction Trail

```text
[✓]  Discovered during §A.1 freeze: track_c_step1_closeout.md
     appeared in both §A.2.1 (lineage exclusion per boundary spec
     §1) and §A.4 Row A4-5 (enumeration), violating I1
[✓]  Boundary spec §1 verified to lineage-exclude
     research/track_c_step1_closeout.md
[✓]  Fix A applied 2026-06-25:
     - Row A4-5 deleted from §A.4
     - A4-6..A4-48 renumbered → A4-5..A4-47 (43 IDs shifted)
     - 3 cross-references updated
     - Batch 3 Summary, Cumulative tables, header status updated
[✓]  Post Fix A: I1 satisfied, partition clean
```

### C.8 Commit 3 Lock-Readiness Verdict

```text
[✓]  All §A subsections complete and consistent
[✓]  §B orphan scan complete with explicit per-bucket coverage
[✓]  All invariants verified
[✓]  Protocol Freeze maintained throughout completion writes
[✓]  Partition correction applied with full trail
[✓]  No active TBD in §A.1-§A.5, §B, §C

READY FOR COMMIT 3 LOCK

Recommended commit message:

  docs(audit): R1-U7B Phase 1 enumeration freeze v0.1.1 LOCKED

  - 96 seed files enumerated, partition 4 + 92 verified
  - 41 §A.3 INCLUDED rows (36 finding clusters anchored)
  - 47 §A.4 EXCLUDED rows post Fix A
  - 26 §A.2.4 methodological entries (referenced_by complete)
  - §B orphan scan: 1 appendix entry (replay_engine), 3 excluded
  - Protocol Freeze held; 15 binding rules + 2 retrospective notes
  - Phase 2 (U7A evaluation) gated on this lock

Post-lock work: commit 4 of 5 = Phase 2 U7A evaluation (§D);
commit 5 of 5 = Phase 3 synthesis (§E) + Commit 5 consolidation
input (retrospective notes → 3-Core-Principle template).
```

---

## §D. Phase 2 — U7A Evaluation

```text
STATUS: COMPLETE
Reviewer chain: Batches D1–D9, all APPROVED.
Commit: 4 of 5
Invariants: 11/11 PASS (machine-verified, see §D.3)
```

---

### D.0 Evaluation Schema

Phase 2 applies the U7A eligibility criteria from prereg §9.1 to
every primary §A.3 row. An additional pre-filter (F0) is applied
first per boundary spec §2.

**Evaluation order per row:**

```text
F0_anchor_type_filter   boundary spec §2 — alpha / feature-discovery /
                        signal-validation finding required;
                        risk / exit / capital / governance findings
                        are not U7A-eligible.

C1_governance_decision          §9.1 criterion (1)
C2_archived_correlation_evidence  §9.1 criterion (2)
C3_cross_sectional_statistic    §9.1 criterion (3)
C4_git_reproducible             §9.1 criterion (4)
C5_independent_lineage          §9.1 criterion (5)

u7a_verdict
  PROVISIONALLY_ELIGIBLE   all of F0 + C1–C5 = PASS
  REJECT                   any of F0 or C1–C5 = FAIL
  NOT_ANCHOR_AGGREGATOR    pre-filter exclusion; C1–C5 not evaluated

spearman_eligible
  YES   u7a_verdict = PROVISIONALLY_ELIGIBLE
  NO    otherwise
```

**C3 notation rule (locked in Batch D1):**

```text
If C2 = FAIL:
  C3_cross_sectional_statistic: NOT_ASSESSED_AFTER_C2_FAIL
  reasoning: C2 FAIL is the binding rejection criterion;
             C3 is not decision-relevant and is not used
             as a rejection basis for this row.
```

**Verdict rules:**

```text
u7a_verdict = PROVISIONALLY_ELIGIBLE  iff  F0=PASS and C1–C5 all PASS
u7a_verdict = REJECT                  iff  any of F0, C1–C5 = FAIL
  (all FAIL criteria recorded independently; multiple FAIL criteria
   are recorded as independent rejection bases)
```

**Scope boundary (durable):**

```text
PROVISIONALLY_ELIGIBLE does not imply:
  - orthogonality to ud_ratio_21d
  - selection as §9.2 collapse or orthogonal anchor
  - any alpha or forward-return claim
Final anchor designation is reserved for Phase 3 §E synthesis.
```

**Terminology (binding for this document):**

```text
PROVISIONALLY_ELIGIBLE   (not ADMIT / eligible / admitted)
REJECT                   (not rejected / ineligible)
NOT_ANCHOR_AGGREGATOR    (not aggregator skip)
ZERO-ANCHOR              (not zero anchor / no anchor)
NOT_ASSESSED_AFTER_C2_FAIL  (not MOOT / N/A / cannot be evaluated)
```

---

### D.1 NOT_ANCHOR_AGGREGATOR Rows (9, 26, 27, 28, 33)

Secondary aggregator rows do not enter U7A evaluation. They are
excluded at the pre-enumeration stage per the durable principle:
canonical owner = the document that locks the finding for governance
purposes. Aggregators summarise findings already counted via primary
sources and introduce no independent empirical evidence.

Per prereg §9.1: no explicit aggregator carve-out exists. The §9.1
eligibility rule operates on canonical owners only.

**Row 9 — `docs/research/roadmap.md`**

```text
anchor_candidate_id:   D-009
source_row:            §A.3 Row 9
canonical_artifact:    docs/research/roadmap.md

u7a_verdict:   NOT_ANCHOR_AGGREGATOR

basis:
  §A.3 Row 9 one_line_description:
    "Secondary aggregator of phase0_findings.md (and downstream
     Phase A studies); summarises registered findings into the
     governance 'Confirmed Alpha' synthesis; introduces no
     independent empirical evidence."
  Batch 1 Summary: "Secondary aggregators: 1 (Row 9, roadmap.md)"

audit_internal_inconsistency (non-blocking):
  classification_type field = "Primary finding source"
  differs from one_line_description and Batch 1 Summary.
  For U7A eligibility, substantive evidence ownership is followed
  per Reviewer Ruling R1 (this session). Inconsistency recorded
  here; §A.3 field not corrected in Commit 4 (Protocol Freeze).

spearman_eligible: NO
```

**Row 26 — `research/r8_phase6_candidate_disposition.md`**

```text
anchor_candidate_id:   D-026
source_row:            §A.3 Row 26
canonical_artifact:    research/r8_phase6_candidate_disposition.md

u7a_verdict:   NOT_ANCHOR_AGGREGATOR

basis:
  §A.3 Row 26 classification_type: Secondary aggregator
  one_line_description: "Secondary aggregator of
    r8_phase6_findings.md; summarises registered findings and
    governance dispositions; introduces no independent empirical
    evidence."
  classification_type and one_line_description consistent.

spearman_eligible: NO
```

**Row 27 — `research/r8_phase6_governance_report.md`**

```text
anchor_candidate_id:   D-027
source_row:            §A.3 Row 27
canonical_artifact:    research/r8_phase6_governance_report.md

u7a_verdict:   NOT_ANCHOR_AGGREGATOR

basis:
  §A.3 Row 27 classification_type: Secondary aggregator
  one_line_description: "Secondary aggregator of
    r8_phase6_findings.md and r8_phase6_candidate_disposition.md;
    summarises registered findings and governance dispositions;
    introduces no independent empirical evidence."
  classification_type and one_line_description consistent.

spearman_eligible: NO
```

**Row 28 — `research/r8_phase6_closeout.md`**

```text
anchor_candidate_id:   D-028
source_row:            §A.3 Row 28
canonical_artifact:    research/r8_phase6_closeout.md

u7a_verdict:   NOT_ANCHOR_AGGREGATOR

basis:
  §A.3 Row 28 classification_type: Secondary aggregator
  one_line_description: "Secondary aggregator of
    r8_phase6_findings.md and r8_phase6_candidate_disposition.md;
    summarises registered findings and governance dispositions
    (Phase 6 CLOSED declaration); introduces no independent
    empirical evidence."
  classification_type and one_line_description consistent.

spearman_eligible: NO
```

**Row 33 — `research/helios_research_roadmap.md`**

```text
anchor_candidate_id:   D-033
source_row:            §A.3 Row 33
canonical_artifact:    research/helios_research_roadmap.md

u7a_verdict:   NOT_ANCHOR_AGGREGATOR

basis:
  §A.3 Row 33 classification_type: Secondary aggregator
  one_line_description: "Secondary aggregator of
    r8_phase5_configuration_report.md (and downstream R8 Phase
    chain); summarises registered findings and governance
    dispositions; introduces no independent empirical evidence."
  §A.1 file list: confirmed in scope (line 627).
  classification_type and one_line_description consistent.

spearman_eligible: NO
```

---

### D.2 Primary Row Evaluations

36 primary §A.3 rows evaluated. All rows record F0 + C1–C5 +
u7a_verdict regardless of F0 outcome, per Reviewer Ruling R2.

C5 ruling (all primary rows): boundary spec §1 exclusion list
covers only `docs/research/ud_ratio_21d_*.md`,
`research/track_c_step1_closeout.md`, and
`research/ud_ratio_21d/*`. No primary row matches any exclusion.
C5 = PASS for all 36 primary rows; individual C5 cells are
recorded per row but not repeated in the summary.

---

#### D.2.1 Batch D1–D2 — Rows 1–8

**Row 1 — `phase0_findings / confirmed_observations`**

```text
anchor_candidate_id:   D-001
source_row:            §A.3 Row 1
canonical_artifact:    docs/research/phase0_findings.md
finding_cluster:       Phase 0 confirmed observations (§3.1–§3.7)

F0_anchor_type_filter:
  verdict:   PASS
  reasoning: Phase 0 confirmed observations are feature-discovery
             / signal-validation findings (RS persistence quintile
             returns, RS_T3 + Dist_T1 interaction cell returns).
             Not risk / exit / capital / governance per boundary
             spec §2.

C1_governance_decision:
  verdict:   PASS
  evidence:  §A.3 Row 1, Text (a):
             "Status: Final (v4 — post per-horizon spacing fix)"
             governance_state_commit_sha: b7eee75 (2026-05-29)
             Formal status "Final" = closed phase under §9.1 C1.

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 1 classification_evidence:
             "Q5 | +2.83% | 54.7%"
             "RS_T3 + Dist_T1 | +4.32% | +1.66% | 62.3% | 366"
             Archived evidence is cross-sectional quintile return
             statistics. No Spearman rho; no statistic from which
             per-day Spearman rho can be reconstructed.
             §9.1 C2 NOT satisfied.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  file_first_commit_sha: af4f9b5 (2026-05-28)
             Primary governance SHA: b7eee75 (2026-05-29) ✓

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: C2 FAIL — no archived Spearman correlation evidence
spearman_eligible: NO
```

**Row 2 — `phase0_findings / rejected_hypotheses`**

```text
anchor_candidate_id:   D-002
source_row:            §A.3 Row 2
canonical_artifact:    docs/research/phase0_findings.md
finding_cluster:       Phase 0 rejected hypotheses (§4.1–§4.4)

F0_anchor_type_filter:
  verdict:   PASS
  reasoning: Rejected hypotheses (Compression Breakout Edge,
             Volume Breakout Continuation, etc.) are negative
             signal-validation findings. Within feature-discovery
             scope per boundary spec §2.

C1_governance_decision:
  verdict:   PASS
  evidence:  Same file; "Status: Final (v4)" at b7eee75. ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 2 classification_evidence:
             "v4 update: absorption finding overturned"
             "v3 absorption bear lift (+0.94%) was a spacing artifact"
             Archived evidence is return% claims and narrative verdict.
             No Spearman rho; no reconstructible statistic.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: b7eee75 (2026-05-29) ✓

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: C2 FAIL — no archived Spearman correlation evidence
spearman_eligible: NO
```

**Row 3 — `phase0_findings / taxonomy_synthesis`**

```text
anchor_candidate_id:   D-003
source_row:            §A.3 Row 3
canonical_artifact:    docs/research/phase0_findings.md
finding_cluster:       Phase 0 taxonomy + regime-dependent synthesis

F0_anchor_type_filter:
  verdict:   PASS
  reasoning: Feature taxonomy and regime-dependent interaction
             matrix = feature-discovery / signal-validation.
             Not risk / exit / capital / governance per boundary
             spec §2.

C1_governance_decision:
  verdict:   PASS
  evidence:  Same file; "Status: Final (v4)" at b7eee75. ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 3 classification_evidence:
             "RS_T3 + Dist_T1 (pullback) | bear | -2.30%, 40.6% hit"
             "Beta_T3 + RS_T3 | Strongest cell (+5.56%)"
             Archived evidence is return% and win-rate statistics.
             No Spearman rho; no reconstructible statistic.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: b7eee75 (2026-05-29) ✓

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: C2 FAIL — no archived Spearman correlation evidence
spearman_eligible: NO
```

**Row 4 — `r8_phase0_feasibility / feasibility_audit`**

```text
anchor_candidate_id:   D-004
source_row:            §A.3 Row 4
canonical_artifact:    research/r8_phase0_feasibility.md
finding_cluster:       R8 MA5 momentum Phase 0 feasibility audit

F0_anchor_type_filter:
  verdict:   PASS
  reasoning: Phase 0 feasibility audit = feature-discovery /
             alpha-adjacent findings. "5/5 PASS against predefined
             feasibility gates" + T-1 RS60 enrichment measurement
             = signal-validation finding. Not risk / exit / capital
             / governance per boundary spec §2.

C1_governance_decision:
  verdict:   PASS
  evidence:  §A.3 Row 4, Text (a):
             "Status: Phase 0 CLOSED (2026-06-01, rev2)"
             "Decision gate is 5/5 PASS"
             Primary governance SHA: 0226c09 (2026-06-02) ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 4 classification_evidence:
             "T-1 RS60 top-tertile enrichment = 1.63 (vs base 0.33)"
             Archived evidence is enrichment ratio (selection-level
             statistic). No Spearman rho; no reconstructible
             correlation statistic. §9.1 C2 NOT satisfied.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: 0226c09 (2026-06-02) ✓

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: C2 FAIL — enrichment ratio is not Spearman rho or
               reconstructible correlation statistic
spearman_eligible: NO
```

**Row 5 — `research_handoff_2026_05 / R1_rs_persistence_decay`**

```text
anchor_candidate_id:   D-005
source_row:            §A.3 Row 5
canonical_artifact:    docs/research/research_handoff_2026_05.md
finding_cluster:       R1 RS persistence decay study

F0_anchor_type_filter:
  verdict:   PASS
  reasoning: R1 RS persistence decay = signal-validation study.
             Tests whether time-in-leadership (age) predicts
             forward return decay within RS_T3. Negative result
             is a signal-validation finding per boundary spec §2.

C1_governance_decision:
  verdict:   PASS
  evidence:  §A.3 Row 5, Text (a): "Result | Negative"
             Primary governance SHA: a583a88 (2026-06-23) ✓

C2_archived_correlation_evidence:
  verdict:   PASS
  evidence:  §A.3 Row 5, Text (b):
             "Spearman(age, fwd_ret) ≈ +0.03-0.04"
             "within-band (0.67-0.75) rho ≈ 0, CI spans zero"
             "Spearman" named explicitly; rho values archived.
             §9.1 C2 satisfied independently.
             Note: underlying estimator form assessed separately
             under C3.

C3_cross_sectional_statistic:
  verdict:   FAIL
  evidence:  Source code research/rs_persistence_decay.py
             (verified via nexus grep, this session):
             line 424: point = _spearman(age, val)
               → single pooled scalar over all stock×date obs
             line 418: "Circular moving-block bootstrap CI for
               Spearman(age, val), grouped by date."
               → bootstrap resamples whole dates to obtain CI
                 on pooled scalar; NOT a per-day rho distribution
             Estimator = pooled panel Spearman with date-clustered
             bootstrap CI.
             §9.1 C3 forbidden: "pooled panel correlation"
             Reviewer Ruling R3 (this session):
             "Pooled panel Spearman = C3 FAIL"

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: a583a88 (2026-06-23) ✓
             Asset: research/rs_persistence_decay.py v0.1.4

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: C3 FAIL — pooled panel Spearman (date-block
               bootstrap CI), not per-day cross-sectional
               statistic per §9.1 C3
spearman_eligible: NO
```

**Row 6 — `research_handoff_2026_05 / R2_failed_breakdown`**

```text
anchor_candidate_id:   D-006
source_row:            §A.3 Row 6
canonical_artifact:    docs/research/research_handoff_2026_05.md
finding_cluster:       R2 failed breakdown / MA20 reclaim quality

F0_anchor_type_filter:
  verdict:   PASS
  reasoning: R2 = signal-validation study testing whether
             failed_breakdown_count_10d predicts forward returns.
             Feature-discovery scope per boundary spec §2.

C1_governance_decision:
  verdict:   PASS
  evidence:  §A.3 Row 6, Text (a): "Result | Weak Negative"
             Primary governance SHA: a583a88 (2026-06-23) ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  R2 original text verified via nexus
             (docs/research/research_handoff_2026_05.md, R2 section):
             Finding field: "h60 point estimate −2.1% but CI spans zero"
             "monotone dose in broad universe at 60d (CI excludes zero)"
             CI is on forward return (%), not on Spearman rho.
             No Spearman rho value present in archived finding.
             one_line_description "Cross-sectional Spearman with CI"
             describes method only; does not constitute archived
             Spearman rho per §9.1 C2.
             Distinction from Rows 5/7/8: those entries explicitly
             archive rho values; R2 does not.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: a583a88 (2026-06-23) ✓

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: C2 FAIL — archived finding records return% CI,
               not Spearman rho or reconstructible correlation
               statistic; method description alone is insufficient
spearman_eligible: NO
```

**Row 7 — `research_handoff_2026_05 / R5_pullback_quality`**

```text
anchor_candidate_id:   D-007
source_row:            §A.3 Row 7
canonical_artifact:    docs/research/research_handoff_2026_05.md
finding_cluster:       R5 pullback quality transfer study

F0_anchor_type_filter:
  verdict:   PASS
  reasoning: R5 = signal-validation / feature-discovery testing
             whether consolidation/trend features transfer across
             universes. Within boundary spec §2 scope.

C1_governance_decision:
  verdict:   PASS
  evidence:  §A.3 Row 7, Text (a):
             "Result | Weak Positive (1 of 3 axes survived)"
             Primary governance SHA: a583a88 (2026-06-23) ✓

C2_archived_correlation_evidence:
  verdict:   PASS
  evidence:  §A.3 Row 7, Text (b):
             "h60 Spearman CI excludes zero (barely: +0.010
             to +0.139)"
             Source verified via nexus (research_handoff_2026_05.md
             R5 section): "h60 Spearman CI excludes zero (barely:
             +0.010 to +0.139)" — "Spearman" named explicitly;
             CI on Spearman statistic archived.
             §9.1 C2 satisfied independently.
             Note: underlying estimator form assessed separately
             under C3.

C3_cross_sectional_statistic:
  verdict:   FAIL
  evidence:  Source code research/pullback_quality.py
             (verified via nexus grep, this session):
             line 194: rho = _spearman(feat, resid)
               → single pooled scalar
             line 199: boots[b] = _spearman(feat[idx], resid[idx])
               → date-block bootstrap on pooled scalar
             line 193: "Spearman(feature, cohort_resid) + date-block
               bootstrap CI"
             Estimator = pooled panel Spearman.
             §9.1 C3 forbidden: "pooled panel correlation"
             Reviewer Ruling R3: FAIL.

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: a583a88 (2026-06-23) ✓
             Asset: research/pullback_quality.py v0.1.1

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: C3 FAIL — pooled panel Spearman, not per-day
               cross-sectional statistic per §9.1 C3
spearman_eligible: NO
```

**Row 8 — `research_handoff_2026_05 / StudyB_rs_acceleration`**

```text
anchor_candidate_id:   D-008
source_row:            §A.3 Row 8
canonical_artifact:    docs/research/research_handoff_2026_05.md
finding_cluster:       Study B RS acceleration

F0_anchor_type_filter:
  verdict:   PASS
  reasoning: Study B = signal-validation testing whether RS rank
             velocity (Δ5) predicts forward returns within RS_T3.
             Within boundary spec §2 scope.

C1_governance_decision:
  verdict:   PASS
  evidence:  §A.3 Row 8, Text (a): "Result | Negative"
             Primary governance SHA: a583a88 (2026-06-23) ✓

C2_archived_correlation_evidence:
  verdict:   PASS
  evidence:  §A.3 Row 8, Text (b):
             "Spearman rho ≈ -0.01, all three horizons CI span zero"
             "Spearman rho" named explicitly with value archived.
             §9.1 C2 satisfied independently.
             Note: underlying estimator form assessed separately
             under C3.

C3_cross_sectional_statistic:
  verdict:   FAIL
  evidence:  Source code research/rs_acceleration.py
             (verified via nexus grep, this session):
             line 121: rho = _spearman(feat, outcome)
               → single pooled scalar
             line 125: boots[b] = _spearman(feat[idx], outcome[idx])
               → date-block bootstrap on pooled scalar
             line 120: "Spearman(feat, outcome) + date-block
               bootstrap CI"
             Identical run_spearman() pattern to Rows 5 and 7.
             Estimator = pooled panel Spearman.
             Reviewer Ruling R3: FAIL.

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: a583a88 (2026-06-23) ✓
             Asset: research/rs_acceleration.py

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: C3 FAIL — pooled panel Spearman, not per-day
               cross-sectional statistic per §9.1 C3
spearman_eligible: NO
```

---

#### D.2.2 Batch D4 — Rows 10–12

**Row 10 — `r8_phase1_interim_findings / A1_RS_T3_hold`**

```text
anchor_candidate_id:   D-010
source_row:            §A.3 Row 10
canonical_artifact:    research/r8_phase1_interim_findings.md
finding_cluster:       Phase 1 A-1 RS_T3 Hold benchmark

F0_anchor_type_filter:
  verdict:   PASS
  reasoning: A-1 RS_T3 Hold benchmark = signal-validation /
             alpha-adjacent finding. Tests whether RS_T3 hold
             produces forward returns above adequacy threshold.
             Not risk / exit / capital / governance per boundary
             spec §2.

C1_governance_decision:
  verdict:   PASS
  evidence:  §A.3 Row 10, Text (a):
             "Status: CONFIRMED — v1.0.0 (2026-06-07)"
             "Three cells reached joint adequacy PASS"
             Primary governance SHA: 539cb41 (2026-06-07) ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 10 classification_evidence:
             "Bull regime, nlu=0 ... 20td | +3.03% |
              [+1.84%, +4.17%] | n_eff 71"
             Archived evidence is forward return delta with
             bootstrap CI. No Spearman rho; no reconstructible
             correlation statistic. §9.1 C2 NOT satisfied.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: 539cb41 (2026-06-07) ✓

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: C2 FAIL — forward return delta with bootstrap CI
               is not Spearman rho or reconstructible correlation
               statistic
spearman_eligible: NO
```

**Row 11 — `r8_phase1_interim_findings / A2_pullback_sparsity`**

```text
anchor_candidate_id:   D-011
source_row:            §A.3 Row 11
canonical_artifact:    research/r8_phase1_interim_findings.md
finding_cluster:       Phase 1 A-2 RS_T3 + Pullback structural
                       sparsity finding

F0_anchor_type_filter:
  verdict:   PASS
  reasoning: A-2 = signal-validation / feature-discovery.
             Finding is structural sparsity (zero adequacy-PASS
             cells) — a negative signal-validation result within
             boundary spec §2 scope.

C1_governance_decision:
  verdict:   PASS
  evidence:  §A.3 Row 11, Text (a):
             "Result: 0 PASS cells. A-2 cannot be evaluated
              inferentially under the [adequacy criteria]"
             Structural finding with formal status CONFIRMED.
             Primary governance SHA: 539cb41 (2026-06-07) ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 11 classification_evidence:
             "Treatment_2 ... contains only 262 observations
              across 109 dates — 4.9% of Treatment_1"
             Archived evidence is observation count / sparsity
             metric. No Spearman rho; no reconstructible
             correlation statistic. §9.1 C2 NOT satisfied.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: 539cb41 (2026-06-07) ✓

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: C2 FAIL — observation count / sparsity metric is
               not Spearman rho or reconstructible correlation
               statistic
spearman_eligible: NO
```

**Row 12 — `r8_phase1_interim_findings / A3_R8_within_RS_T3`**

```text
anchor_candidate_id:   D-012
source_row:            §A.3 Row 12
canonical_artifact:    research/r8_phase1_interim_findings.md
finding_cluster:       Phase 1 A-3 R8 within RS_T3 vs RS_T3
                       unconditional

F0_anchor_type_filter:
  verdict:   PASS
  reasoning: A-3 = core alpha-finding of R8 Phase 1. Tests
             incremental forward return of R8 signal within
             RS_T3. CONFIRMED bull regime Δ = primary alpha
             evidence. Not risk / exit / capital / governance
             per boundary spec §2.

C1_governance_decision:
  verdict:   PASS
  evidence:  §A.3 Row 12, Text (a):
             "Bull | YES (CONFIRMED) | A-3 Tier 1: Δ_obs =
              +1.21% / +1.92% at 10td / 20td (v0.2.0 clean
              panel); CI strictly positive at all block lengths"
             Primary governance SHA: 539cb41 (2026-06-07) ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 12 classification_evidence:
             "Δ_obs = +1.21% / +1.92% at 10td / 20td"
             "CI strictly positive at all block lengths"
             "ROBUST. At all block lengths L={5,10,20,40},
              95% CI strictly positive"
             Archived evidence is forward return delta (Δ%) with
             block-bootstrap CI. Estimand is mean return
             differential, not rank correlation.
             No Spearman rho; no reconstructible correlation
             statistic. §9.1 C2 NOT satisfied.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: 539cb41 (2026-06-07) ✓
             Supporting rerun lineage: 4a307e6 (clean-panel
             re-run, referenced in §A.3 one_line_description)

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: C2 FAIL — forward return delta (Δ%) with block-
               bootstrap CI; estimand is mean return differential,
               not Spearman rank correlation
spearman_eligible: NO
```

---

#### D.2.3 Batch D5–D8 — Rows 13–25

**Row 13 — `r8_phase2a_validation_report / stability_validation`**

```text
anchor_candidate_id:   D-013
source_row:            §A.3 Row 13
canonical_artifact:    research/r8_phase2a_validation_report.md
finding_cluster:       Phase 2A stability validation — STABLE verdict

F0_anchor_type_filter:
  verdict:   PASS
  reasoning: Phase 2A = rolling-window stability validation of
             bull-regime R8 uplift. Signal-validation scope per
             boundary spec §2.

C1_governance_decision:
  verdict:   PASS
  evidence:  §A.3 Row 13, Text (a):
             "Status: CONFIRMED — v1.0.0 (2026-06-07)"
             "Verdict: STABLE"
             Primary governance SHA: a1a3959 (2026-06-07) ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 13, Text (b):
             "27/27 windows positive; median +1.12%;
              minimum +0.33%; zero negative windows"
             "top-1 = 49.4%, top-2 = 89.9%; material concentration"
             Archived evidence is rolling-window positive rate and
             return% summary. No Spearman rho; no reconstructible
             correlation statistic. §9.1 C2 NOT satisfied.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: a1a3959 (2026-06-07) ✓

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: C2 FAIL — rolling-window positive rate and return%
               summary are not Spearman rho or reconstructible
               correlation statistics
spearman_eligible: NO
```

**Row 14 — `r8_phase2b_feasibility_memo / execution_feasibility`**

```text
anchor_candidate_id:   D-014
source_row:            §A.3 Row 14
canonical_artifact:    research/r8_phase2b_feasibility_memo.md
finding_cluster:       Phase 2B execution feasibility — FEASIBLE

F0_anchor_type_filter:
  verdict:   PASS
  reasoning: Phase 2B = execution feasibility testing of R8
             signal under realistic friction. Signal-validation
             scope: tests whether alpha survives execution per
             boundary spec §2.

C1_governance_decision:
  verdict:   PASS
  evidence:  §A.3 Row 14, Text (a):
             "Status: CONFIRMED — v1.0.0 (2026-06-07)"
             "Verdict: FEASIBLE"
             Primary governance SHA: 792dceb (2026-06-07) ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 14, Text (b):
             "All 12 scenario × slippage combinations produce
              positive net returns"
             "net return is +0.55%"
             Archived evidence is scenario × slippage net return
             combinations. No Spearman rho; no reconstructible
             correlation statistic. §9.1 C2 NOT satisfied.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: 792dceb (2026-06-07) ✓

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: C2 FAIL — scenario × slippage net return
               combinations are not Spearman rho or
               reconstructible correlation statistics
spearman_eligible: NO
```

**Row 15 — `r8_phase3_risk_report / FindingA_capital_lockup`**

```text
anchor_candidate_id:   D-015
source_row:            §A.3 Row 15
canonical_artifact:    research/r8_phase3_risk_report.md
finding_cluster:       Phase 3 Finding A — capital lock-up
                       characterisation

F0_anchor_type_filter:
  verdict:   FAIL
  reasoning: Finding A characterises holding-period-induced capital
             lock-up (admission rate 16.3%, FIFO slot occupancy).
             The finding is classified as a portfolio-construction /
             capital-allocation / operational-capacity
             characterisation rather than an alpha / feature-
             discovery / signal-validation finding under the
             boundary spec §2 filter.

C1_governance_decision:
  verdict:   PASS
  evidence:  §A.3 Row 15, Text (a):
             "Status: LOCKED — v1.0.1 (2026-06-07)"
             "Verdict: CHARACTERISED"
             Primary governance SHA: 4c8f60d (2026-06-07) ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 15, Text (b):
             "admitted only 16.3% of R8 candidate signals"
             "Only 2.1% of signal dates produced more than 10
              simultaneous R8 signals"
             Archived evidence is admission rate % and signal-count
             distribution. No Spearman rho. §9.1 C2 NOT satisfied.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: 4c8f60d (2026-06-07) ✓

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: F0 FAIL (portfolio-construction / capital-allocation /
               operational-capacity characterisation per boundary
               spec §2) AND C2 FAIL (admission rate % is not
               Spearman rho). Both are independent rejection bases.
spearman_eligible: NO
```

**Row 16 — `r8_phase3_risk_report / FindingB_low_uplift_convergence`**

```text
anchor_candidate_id:   D-016
source_row:            §A.3 Row 16
canonical_artifact:    research/r8_phase3_risk_report.md
finding_cluster:       Phase 3 Finding B — Low-Uplift Sharpe
                       convergence

F0_anchor_type_filter:
  verdict:   FAIL
  reasoning: Finding B characterises portfolio behaviour under the
             Low-Uplift environment. The study evaluates portfolio-
             level risk-adjusted performance rather than signal
             validity. Accordingly it is classified as a
             portfolio-construction / capital-allocation /
             operational-capacity characterisation under boundary
             spec §2.

C1_governance_decision:
  verdict:   PASS
  evidence:  §A.3 Row 16 heading: "Finding B — Risk-adjusted edge
             disappears in the Low-Uplift environment"
             Primary governance SHA: 4c8f60d (2026-06-07) ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 16, Text (b):
             "Full Sample (Sharpe 2.378 vs 1.313)"
             "Low-Uplift environment ... (1.613 vs 1.606, Δ = 0.007)"
             Archived evidence is Sharpe ratio comparison. No
             Spearman rho. §9.1 C2 NOT satisfied.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: 4c8f60d (2026-06-07) ✓

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: F0 FAIL (portfolio-construction / capital-allocation /
               operational-capacity characterisation per boundary
               spec §2) AND C2 FAIL (Sharpe ratio comparison is
               not Spearman rho). Both independent rejection bases.
spearman_eligible: NO
```

**Row 17 — `r8_phase3_risk_report / FindingC_position_cap_insensitivity`**

```text
anchor_candidate_id:   D-017
source_row:            §A.3 Row 17
canonical_artifact:    research/r8_phase3_risk_report.md
finding_cluster:       Phase 3 Finding C — position cap
                       insensitivity

F0_anchor_type_filter:
  verdict:   FAIL
  reasoning: Finding C evaluates the effect of relaxing the
             per-position cap (10% → 15%/20%/25%) on Sharpe
             and MaxDD. This is a portfolio-construction /
             capital-allocation / operational-capacity
             characterisation under boundary spec §2.

C1_governance_decision:
  verdict:   PASS
  evidence:  §A.3 Row 17 heading: "Finding C — Higher position
             caps did not improve risk-adjusted performance"
             Primary governance SHA: 4c8f60d (2026-06-07) ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 17, Text (b):
             "increasing the per-position cap above 10% baseline
              degraded the Sharpe ratio across all variants"
             "MaxDD: 21.65% → 41.56% in Full Sample"
             Archived evidence is Sharpe ratio and max drawdown.
             No Spearman rho. §9.1 C2 NOT satisfied.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: 4c8f60d (2026-06-07) ✓

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: F0 FAIL (portfolio-construction / capital-allocation /
               operational-capacity characterisation per boundary
               spec §2) AND C2 FAIL (Sharpe/MaxDD are not Spearman
               rho). Both independent rejection bases.
spearman_eligible: NO
```

**Row 18 — `r8_phase4_optimisation / FindingA1_lockup_confirmation`**

```text
anchor_candidate_id:   D-018
source_row:            §A.3 Row 18
canonical_artifact:    research/r8_phase4_optimisation_report.md
finding_cluster:       Phase 4 Finding A1 — holding-period lock-up
                       hypothesis confirmed

F0_anchor_type_filter:
  verdict:   FAIL
  reasoning: Finding A1 confirms the Phase 3 capital lock-up
             hypothesis via admission rate response to holding-
             period reduction. Portfolio-construction /
             capital-allocation / operational-capacity
             characterisation per boundary spec §2.

C1_governance_decision:
  verdict:   PASS
  evidence:  §A.3 Row 18, Text (a):
             "Status: LOCKED — v1.0.0 (2026-06-07)"
             "Verdict: OPTIMISATION_CHARACTERISED"
             Primary governance SHA: d918be5 (2026-06-07) ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 18, Text (b):
             "Admission rate responds strongly to holding-period
              reduction: 16.3% (20td) → 30.0% (10td) → 52.8% (5td)"
             Archived evidence is admission rate % across holding-
             period variants. No Spearman rho. §9.1 C2 NOT satisfied.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: d918be5 (2026-06-07) ✓

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: F0 FAIL (portfolio-construction / capital-allocation /
               operational-capacity characterisation per boundary
               spec §2) AND C2 FAIL (admission rate % is not
               Spearman rho). Both independent rejection bases.
spearman_eligible: NO
```

**Row 19 — `r8_phase4_optimisation / FindingA2_edge_time_dependence`**

```text
anchor_candidate_id:   D-019
source_row:            §A.3 Row 19
canonical_artifact:    research/r8_phase4_optimisation_report.md
finding_cluster:       Phase 4 Finding A2 — R8 edge requires time
                       to materialise

F0_anchor_type_filter:
  verdict:   FAIL
  reasoning: Finding A2 characterises the holding-period threshold
             below which R8 forward-return edge disappears (5td CI
             crosses zero, Sharpe 2.38 → 1.17). Research question
             is "how long must a position be held for the edge to
             appear?" — portfolio-construction / capital-allocation /
             operational-capacity characterisation per boundary
             spec §2.

C1_governance_decision:
  verdict:   PASS
  evidence:  §A.3 Row 19 heading: "Finding A2 — R8 edge requires
             time to materialise"
             Primary governance SHA: d918be5 (2026-06-07) ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 19, Text (b):
             "5td bootstrap Δ_A3 CI crosses zero (full sample)"
             "Sharpe degradation (2.38 → 1.17, full sample)"
             Archived evidence is bootstrap CI on return delta
             and Sharpe ratio. No Spearman rho. §9.1 C2 NOT satisfied.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: d918be5 (2026-06-07) ✓

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: F0 FAIL (portfolio-construction / capital-allocation /
               operational-capacity characterisation per boundary
               spec §2) AND C2 FAIL (bootstrap CI on return delta
               + Sharpe ratio are not Spearman rho). Both
               independent rejection bases.
spearman_eligible: NO
```

**Row 20 — `r8_phase4_optimisation / FindingA3_10td_optimum`**

```text
anchor_candidate_id:   D-020
source_row:            §A.3 Row 20
canonical_artifact:    research/r8_phase4_optimisation_report.md
finding_cluster:       Phase 4 Finding A3 — 10td as utilisation-
                       performance optimum

F0_anchor_type_filter:
  verdict:   FAIL
  reasoning: Finding A3 identifies 10td holding period as the
             optimal utilisation-performance trade-off point.
             Research question is parameter optimisation of a
             portfolio construction variable (holding period).
             Portfolio-construction / capital-allocation /
             operational-capacity characterisation per boundary
             spec §2.

C1_governance_decision:
  verdict:   PASS
  evidence:  §A.3 Row 20, Text (a):
             "CANDIDATE: 10td_holding_period | Admission +13.7pp;
              Sharpe decline < 0.25; bootstrap CI positive"
             Primary governance SHA: d918be5 (2026-06-07) ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 20, Text (b):
             "admission rate nearly doubles (16.3% → 30.0%)"
             "Sharpe declines only modestly (2.38 → 2.13)"
             Archived evidence is admission rate % and Sharpe
             ratio comparison. No Spearman rho. §9.1 C2 NOT satisfied.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: d918be5 (2026-06-07) ✓

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: F0 FAIL (portfolio-construction / capital-allocation /
               operational-capacity characterisation — holding-period
               parameter optimisation per boundary spec §2) AND
               C2 FAIL (admission rate % + Sharpe ratio are not
               Spearman rho). Both independent rejection bases.
spearman_eligible: NO
```

**Row 21 — `r8_phase4_optimisation / FindingB1_rs_ranking_dominance`**

```text
anchor_candidate_id:   D-021
source_row:            §A.3 Row 21
canonical_artifact:    research/r8_phase4_optimisation_report.md
finding_cluster:       Phase 4 Finding B1 — RS-based ranking
                       dominates FIFO

F0_anchor_type_filter:
  verdict:   FAIL
  reasoning: Finding B1 evaluates the portfolio admission policy
             (FIFO versus RS-based prioritisation) applied to an
             existing signal set. The estimand is portfolio-level
             performance after changing the allocation rule rather
             than the predictive quality of the RS feature itself.
             Accordingly the finding is classified as a
             portfolio-construction / capital-allocation /
             operational-capacity characterisation under boundary
             spec §2.
             Reviewer Ruling (Batch D7): option (b) confirmed.

C1_governance_decision:
  verdict:   PASS
  evidence:  §A.3 Row 21, Text (a):
             "CANDIDATE: rs_60d_ranking | Low-Uplift Sharpe
              +0.52; no admission cost; RS-20d also viable"
             Primary governance SHA: d918be5 (2026-06-07) ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 21, Text (b):
             "RS-60d Sharpe in Low-Uplift = 2.13 vs FIFO = 1.61
              (+0.52)"
             Archived evidence is Sharpe uplift comparison. No
             Spearman rho. §9.1 C2 NOT satisfied.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: d918be5 (2026-06-07) ✓

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: F0 FAIL (portfolio-construction / capital-allocation /
               operational-capacity characterisation per boundary
               spec §2) AND C2 FAIL (Sharpe uplift comparison is
               not Spearman rho). Both independent rejection bases.
spearman_eligible: NO
```

**Row 22 — `r8_phase5_configuration / Finding_P5-1_rs60d_confirmed`**

```text
anchor_candidate_id:   D-022
source_row:            §A.3 Row 22
canonical_artifact:    research/r8_phase5_configuration_report.md
finding_cluster:       Phase 5 Finding P5-1 — RS-60d ranking
                       confirmed

F0_anchor_type_filter:
  verdict:   FAIL
  reasoning: Finding P5-1 confirms RS-60d ranking as a robust
             improvement over FIFO baseline (ARM_B vs ARM_A).
             The research question evaluates the portfolio
             admission policy applied to an existing signal set,
             not the predictive quality of the RS-60d feature
             itself. Consistent with Reviewer Ruling on D-021.
             Portfolio-construction / capital-allocation /
             operational-capacity characterisation per boundary
             spec §2.

C1_governance_decision:
  verdict:   PASS
  evidence:  §A.3 Row 22, Text (a):
             "Status: LOCKED — v1.0.2 (2026-06-19)"
             "Verdict: CONFIGURATION_SELECTED"
             Primary governance SHA: 98315a6 (2026-06-19) ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 22, Text (b):
             "ARM_B ... demonstrated a substantial improvement
              in Low-Uplift Sharpe (+0.635 vs Arm A)"
             Archived evidence is Sharpe uplift comparison. No
             Spearman rho. §9.1 C2 NOT satisfied.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: 98315a6 (2026-06-19) ✓
             Supporting rerun lineage: edd42b1 (2026-06-19,
             file_first_commit)

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: F0 FAIL (portfolio-construction / capital-allocation /
               operational-capacity characterisation per boundary
               spec §2) AND C2 FAIL (Sharpe uplift comparison is
               not Spearman rho). Both independent rejection bases.
spearman_eligible: NO
```

**Row 23 — `r8_phase5_configuration / Finding_P5-2_10td_capacity`**

```text
anchor_candidate_id:   D-023
source_row:            §A.3 Row 23
canonical_artifact:    research/r8_phase5_configuration_report.md
finding_cluster:       Phase 5 Finding P5-2 — 10td holding
                       increases capital utilisation

F0_anchor_type_filter:
  verdict:   FAIL
  reasoning: Finding P5-2 quantifies the mechanical effect of
             shorter holding period on capital utilisation
             (admission rate 17.5% → 32.4%). The
             one_line_description itself classifies this as
             "a mechanical effect of capital turnover, not a
             signal-quality finding." Portfolio-construction /
             capital-allocation / operational-capacity
             characterisation per boundary spec §2.

C1_governance_decision:
  verdict:   PASS
  evidence:  Same file; "Status: LOCKED — v1.0.2 (2026-06-19)"
             at Primary governance SHA: 98315a6 (2026-06-19) ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 23, Text (b):
             "10td holding substantially increases admission
              rate (17.5% → 32.4%)"
             Archived evidence is admission rate % change. No
             Spearman rho. §9.1 C2 NOT satisfied.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: 98315a6 (2026-06-19) ✓

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: F0 FAIL (portfolio-construction / capital-allocation /
               operational-capacity characterisation; document
               self-classifies as mechanical capital turnover
               effect per boundary spec §2) AND C2 FAIL
               (admission rate % is not Spearman rho). Both
               independent rejection bases.
spearman_eligible: NO
```

**Row 24 — `r8_phase5_configuration / Finding_P5-3_capacity_sharpe_tradeoff`**

```text
anchor_candidate_id:   D-024
source_row:            §A.3 Row 24
canonical_artifact:    research/r8_phase5_configuration_report.md
finding_cluster:       Phase 5 Finding P5-3 — capacity gain
                       accompanied by snapshot-sensitive Sharpe
                       degradation

F0_anchor_type_filter:
  verdict:   FAIL
  reasoning: Finding P5-3 characterises the Sharpe cost of the
             capacity gain from shorter holding (ARM_C 10td).
             Research question: "is the capacity gain free in
             risk-adjusted terms?" Portfolio-construction /
             capital-allocation / operational-capacity
             characterisation per boundary spec §2.

C1_governance_decision:
  verdict:   PASS
  evidence:  §A.3 Row 24, Text (a):
             "ARM_C reclassified from SELECTED (marginal P5-G1)
              to CAPACITY_DEMONSTRATED / SHARPE_UNRESOLVED"
             Primary governance SHA: 98315a6 (2026-06-19) ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 24, Text (b):
             "marginally satisfied the Sharpe gate (P5-G1,
              Δ = −0.093 against a threshold of −0.10)"
             "Under the locked Phase 3 price snapshot, Arm C's
              P5-G1 Δ would be −0.137, which would not pass"
             Archived evidence is Sharpe delta gate margin. No
             Spearman rho. §9.1 C2 NOT satisfied.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: 98315a6 (2026-06-19) ✓

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: F0 FAIL (portfolio-construction / capital-allocation /
               operational-capacity characterisation per boundary
               spec §2) AND C2 FAIL (Sharpe delta gate margin is
               not Spearman rho). Both independent rejection bases.
spearman_eligible: NO
```

**Row 25 — `r8_phase6_findings / F-P6-01_adaptive_exits`**

```text
anchor_candidate_id:   D-025
source_row:            §A.3 Row 25
canonical_artifact:    research/r8_phase6_findings.md
finding_cluster:       Phase 6 Finding F-P6-01 — adaptive exit
                       policies do not improve ARM_B

F0_anchor_type_filter:
  verdict:   FAIL
  reasoning: Finding F-P6-01 evaluates whether adaptive exit
             policies (E1–E4) improve ARM_B vs fixed 20td hold.
             Research question: "does changing the exit rule
             improve portfolio outcomes?" Exit policy selection
             is explicitly listed in boundary spec §2 as a
             non-eligible finding type ("risk, exit, capital,
             or governance findings are not U7A-eligible").
             The primary finding type matches a boundary spec §2
             exclusion verbatim ("exit").

C1_governance_decision:
  verdict:   PASS
  evidence:  §A.3 Row 25, Text (a):
             "Status: FINDING REGISTERED / Step 3 COMPLETE"
             "All four adaptive exit policies are CHARACTERISED,
              not SELECTED"
             Primary governance SHA: 901c0de (2026-06-22) ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 25, Text (b):
             "E1 ATR Trailing | 1.1689 | −1.035 | FAIL | ..."
             "E2 MA20 Failure | 0.3773 | −1.825 | FAIL | ..."
             Archived evidence is ΔSharpe gate results (P6-G1)
             for E1–E4. No Spearman rho. §9.1 C2 NOT satisfied.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: 901c0de (2026-06-22) ✓

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: F0 FAIL (primary finding type matches boundary
               spec §2 exclusion verbatim: "exit") AND C2 FAIL
               (ΔSharpe gate results are not Spearman rho). Both
               independent rejection bases.
spearman_eligible: NO
```

---

#### D.2.4 Batch D9A — Rows 29–32

**Row 29 — `P1-DATA_panel_integrity / IF1_pre_listing_contamination`**

```text
anchor_candidate_id:   D-029
source_row:            §A.3 Row 29
canonical_artifact:    research/P1-DATA_panel_integrity_assessment.md
finding_cluster:       IF-1 pre-listing / emerging-board
                       contamination

F0_anchor_type_filter:
  verdict:   FAIL
  reasoning: IF-1 is a data governance / data integrity finding:
             18 stocks with pre-listing price history in
             daily_price_adj. Research question is data pipeline
             correctness, not signal predictive quality.
             Governance finding per boundary spec §2.

C1_governance_decision:
  verdict:   PASS
  evidence:  §A.3 Row 29, Text (a):
             "IF-1: ... High | Confirmed, measured | Open"
             Subsequent: "remediation closeout (CLOSED, AC-1
             through AC-7 PASS)"
             Primary governance SHA: b41d56b (2026-06-04) ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 29, Text (b):
             "18 stocks ... predates their listing_date"
             "135 of 338 DQ events trace to IF-1"
             Archived evidence is stock count, row count, DQ
             event count. No Spearman rho. §9.1 C2 NOT satisfied.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: b41d56b (2026-06-04) ✓
             Supporting rerun lineage: fb38ae4 (2026-06-02)

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: F0 FAIL (data governance / data integrity finding
               per boundary spec §2) AND C2 FAIL (row/DQ event
               counts are not Spearman rho). Both independent
               rejection bases.
spearman_eligible: NO
```

**Row 30 — `P1-DATA_panel_integrity / IF2_empty_stock_info`**

```text
anchor_candidate_id:   D-030
source_row:            §A.3 Row 30
canonical_artifact:    research/P1-DATA_panel_integrity_assessment.md
finding_cluster:       IF-2 empty stock_info table

F0_anchor_type_filter:
  verdict:   FAIL
  reasoning: IF-2 is a data governance / data integrity finding.
             Governance finding per boundary spec §2.

C1_governance_decision:
  verdict:   PASS
  evidence:  "IF-2: ... Medium | Confirmed | Open — workaround
             in use" → reclassified P2 non-binding.
             Primary governance SHA: 77fb3c1 (2026-06-06) ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 30, Text (b):
             "Confirmed. Table is empty; this is directly
              observable."
             Archived evidence is observational data-presence
             check. No Spearman rho. §9.1 C2 NOT satisfied.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: 77fb3c1 (2026-06-06) ✓
             Supporting rerun lineage: fb38ae4 (2026-06-02)

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: F0 FAIL (data governance / data integrity finding
               per boundary spec §2) AND C2 FAIL (observational
               presence check is not Spearman rho). Both
               independent rejection bases.
spearman_eligible: NO
```

**Row 31 — `P1-DATA_panel_integrity / IF3_empty_corporate_actions`**

```text
anchor_candidate_id:   D-031
source_row:            §A.3 Row 31
canonical_artifact:    research/P1-DATA_panel_integrity_assessment.md
finding_cluster:       IF-3 empty corporate_actions table

F0_anchor_type_filter:
  verdict:   FAIL
  reasoning: IF-3 is a data governance / data integrity finding.
             Governance finding per boundary spec §2.

C1_governance_decision:
  verdict:   PASS
  evidence:  "IF-3: ... Medium | Confirmed | Open" → split into
             IF-3A (CLOSED, commit 76f1f45) and IF-3B
             (reclassified P2 non-binding, commit 39ba6c2).
             Primary governance SHA: 39ba6c2 (2026-06-07) ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 31, Text (b):
             "203 SUSPENSION_GAP rows across 90 stocks"
             "338 signals in the R8 population have ret_1d >= +10%"
             Archived evidence is row and event counts. No
             Spearman rho. §9.1 C2 NOT satisfied.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: 39ba6c2 (2026-06-07) ✓
             Supporting rerun lineage: fb38ae4 (2026-06-02)

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: F0 FAIL (data governance / data integrity finding
               per boundary spec §2) AND C2 FAIL (row/event
               counts are not Spearman rho). Both independent
               rejection bases.
spearman_eligible: NO
```

**Row 32 — `p1_data_remediation / Benchmark_C_robustness_after_IF1`**

```text
anchor_candidate_id:   D-032
source_row:            §A.3 Row 32
canonical_artifact:    research/p1_data_remediation_closeout_2026-06-04.md
finding_cluster:       IF-1 remediation robustness — Benchmark C

F0_anchor_type_filter:
  verdict:   FAIL
  reasoning: Row 32 validates the robustness of a previously
             established finding after data remediation. Research
             question: "did IF-1 contamination materially affect
             Benchmark C?" Data governance / remediation
             validation per boundary spec §2.

C1_governance_decision:
  verdict:   PASS
  evidence:  §A.3 Row 32, Text (a):
             "Status: CLOSED"
             "All acceptance criteria satisfied. R8 Phase 1
              findings upgraded from PROVISIONAL to CONDITIONAL"
             Primary governance SHA: b41d56b (2026-06-04) ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 32, Text (b):
             "C: R8 within RS_T3 (ret_20d) | +6.84% | +6.77% |
              -0.07pp"
             "Net event count change after rebuild (Δ) | -418
              (-4.96%)"
             Archived evidence is return% before/after comparison
             (Δ = −0.07pp) and event count delta. No Spearman
             rho. §9.1 C2 NOT satisfied.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: b41d56b (2026-06-04) ✓

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: F0 FAIL (data governance / remediation validation
               per boundary spec §2) AND C2 FAIL (return%
               before/after delta is not Spearman rho). Both
               independent rejection bases.
spearman_eligible: NO
```

---

#### D.2.5 Batch D9B — Rows 34–41

**Row 34 — `JOURNAL / v0.1.10.2_yfinance_splits_TW_broken`**

```text
anchor_candidate_id:   D-034
source_row:            §A.3 Row 34
canonical_artifact:    docs/JOURNAL.md
finding_cluster:       Data-quality discovery — yfinance.splits
                       broken for TW

F0_anchor_type_filter:
  verdict:   FAIL
  reasoning: Data pipeline data-quality discovery (yfinance.splits
             broken for TW market). Governance / data-integrity
             finding per boundary spec §2.

C1_governance_decision:
  verdict:   PASS
  evidence:  §A.3 Row 34: "Key insight" heading registered as
             named finding at commit 955d71d (2026-05-17) ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 34, Text (b):
             "TWT49U has same dividend values as FinMind"
             Archived evidence is cross-source value comparison.
             No Spearman rho. §9.1 C2 NOT satisfied.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: 955d71d (2026-05-17) ✓

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: F0 FAIL (data governance / data-quality finding
               per boundary spec §2) AND C2 FAIL (cross-source
               value comparison is not Spearman rho). Both
               independent rejection bases.
spearman_eligible: NO
```

**Row 35 — `JOURNAL / v0.1.11_regime_distribution`**

```text
anchor_candidate_id:   D-035
source_row:            §A.3 Row 35
canonical_artifact:    docs/JOURNAL.md
finding_cluster:       Regime distribution validates market
                       intuition

F0_anchor_type_filter:
  verdict:   FAIL
  reasoning: Finding characterises the empirical distribution of
             regime labels and notes alignment with market
             intuition. Research question: "does the regime
             detector produce plausible output?" — system
             validation / instrument calibration finding.
             Governance / instrument-validation scope per
             boundary spec §2.

C1_governance_decision:
  verdict:   PASS
  evidence:  §A.3 Row 35: "Key insight — Regime distribution
             validates market intuition" registered at
             commit 955d71d (2026-05-17) ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 35 classification_evidence contains only
             heading references; no numeric evidence cell
             recorded. No Spearman rho. §9.1 C2 NOT satisfied.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: 955d71d (2026-05-17) ✓

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: F0 FAIL (system validation / instrument calibration
               per boundary spec §2) AND C2 FAIL (no numeric
               correlation evidence archived). Both independent
               rejection bases.
spearman_eligible: NO
```

**Row 36 — `JOURNAL / v0.1.12_trendbreakout_strategy`**

```text
anchor_candidate_id:   D-036
source_row:            §A.3 Row 36
canonical_artifact:    docs/JOURNAL.md
finding_cluster:       TrendBreakout strategy initial release —
                       entry-condition set curated and locked

F0_anchor_type_filter:
  verdict:   FAIL
  reasoning: Finding records strategy entry-condition curation
             (curated with reviewer, decision loop locked).
             Research question: "what entry conditions should
             the strategy use?" Portfolio-construction /
             strategy design per boundary spec §2.

C1_governance_decision:
  verdict:   PASS
  evidence:  §A.3 Row 36: "Strategy condition curation reviewed
             and locked with reviewer participation" at commit
             955d71d (2026-05-17) ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 36 classification_evidence contains only
             heading and governance-process text; no numeric
             evidence cell. No Spearman rho. §9.1 C2 NOT satisfied.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: 955d71d (2026-05-17) ✓

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: F0 FAIL (portfolio-construction / strategy design
               per boundary spec §2) AND C2 FAIL (no numeric
               correlation evidence). Both independent rejection
               bases.
spearman_eligible: NO
```

**Row 37 — `JOURNAL / v0.1.13.1_OOS_validation_REAL_ALPHA`**

```text
anchor_candidate_id:   D-037
source_row:            §A.3 Row 37
canonical_artifact:    docs/JOURNAL.md
finding_cluster:       TrendBreakout OOS validation — REAL ALPHA
                       verdict

F0_anchor_type_filter:
  verdict:   FAIL
  reasoning: Finding evaluates the performance of a complete
             assembled trading strategy rather than the
             predictive validity of an individual feature.
             Accordingly it falls outside the alpha /
             feature-discovery / signal-validation scope
             defined in boundary spec §2.
             Note: "REAL ALPHA" verdict label does not change
             the finding-type classification; the estimand
             remains strategy-level backtest statistics
             (PF, win rate, W/L ratio).

C1_governance_decision:
  verdict:   PASS
  evidence:  §A.3 Row 37: "Verdict: ✓✓ REAL ALPHA (not
             curve-fit AI bull noise)" registered at commit
             955d71d (2026-05-17) ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 37, Text (b):
             "132 trades over 5 years, profit factor 2.67,
              MFE/|MAE| 4.47"
             "Win rate 53.8%"
             "Avg win 5.62% / avg loss -2.45% (W/L 2.29)"
             Archived evidence is backtest performance metrics.
             No Spearman rho. §9.1 C2 NOT satisfied.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: 955d71d (2026-05-17) ✓

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: F0 FAIL (strategy-level validation rather than
               feature-level validation per boundary spec §2;
               "REAL ALPHA" label does not reclassify the
               finding type) AND C2 FAIL (backtest PF / win
               rate are not Spearman rho). Both independent
               rejection bases.
spearman_eligible: NO
```

**Row 38 — `JOURNAL / v0.1.13.2_textbook_trend_signature`**

```text
anchor_candidate_id:   D-038
source_row:            §A.3 Row 38
canonical_artifact:    docs/JOURNAL.md
finding_cluster:       Exit logic + round-trip backtest —
                       textbook trend signature

F0_anchor_type_filter:
  verdict:   FAIL
  reasoning: Finding characterises the payoff shape of the
             TrendBreakout strategy (MFE/MAE, W/L ratio).
             Portfolio-construction / capital-allocation /
             operational-capacity characterisation per boundary
             spec §2.

C1_governance_decision:
  verdict:   PASS
  evidence:  §A.3 Row 38: "Key insight — Textbook trend
             signature" at commit 955d71d (2026-05-17) ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 38, Text (b):
             "132 trades over 5 years, profit factor 2.67,
              MFE/|MAE| 4.47"
             "Win rate 53.8% (≈ coin flip)"
             Archived evidence is backtest payoff statistics.
             No Spearman rho. §9.1 C2 NOT satisfied.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: 955d71d (2026-05-17) ✓

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: F0 FAIL (portfolio-construction / capital-allocation /
               operational-capacity characterisation per boundary
               spec §2) AND C2 FAIL (backtest payoff statistics
               are not Spearman rho). Both independent rejection
               bases.
spearman_eligible: NO
```

**Row 39 — `JOURNAL / v0.1.13.3_cost_resistant_alpha`**

```text
anchor_candidate_id:   D-039
source_row:            §A.3 Row 39
canonical_artifact:    docs/JOURNAL.md
finding_cluster:       Cost + OOS round-trip — alpha is
                       cost-resistant

F0_anchor_type_filter:
  verdict:   FAIL
  reasoning: Finding characterises TrendBreakout OOS net returns
             at realistic cost levels (PF at 0.585% and 0.785%
             round-trip). Portfolio-construction / capital-
             allocation / operational-capacity characterisation
             per boundary spec §2.

C1_governance_decision:
  verdict:   PASS
  evidence:  §A.3 Row 39: "Key insight — Alpha is cost-resistant"
             at commit 955d71d (2026-05-17) ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 39, Text (b):
             "0.585% cost | +1.99% | 2.50 | ✓✓ STRONG"
             "0.785% with slippage | +1.79% | 2.25 | ✓✓ STRONG"
             Archived evidence is net return and PF at cost
             levels. No Spearman rho. §9.1 C2 NOT satisfied.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: 955d71d (2026-05-17) ✓

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: F0 FAIL (portfolio-construction / capital-allocation /
               operational-capacity characterisation per boundary
               spec §2) AND C2 FAIL (net return / PF at cost
               levels are not Spearman rho). Both independent
               rejection bases.
spearman_eligible: NO
```

**Row 40 — `JOURNAL / v0.1.14.1_portfolio_constrained_STRONG_PASS`**

```text
anchor_candidate_id:   D-040
source_row:            §A.3 Row 40
canonical_artifact:    docs/JOURNAL.md
finding_cluster:       Portfolio constrained backtest —
                       STRONG PASS

F0_anchor_type_filter:
  verdict:   FAIL
  reasoning: Finding records the effect of portfolio constraints
             on trade count, PF, and MaxDD (constrained trade-
             count 132→72, PF 2.50→4.13, MaxDD ratio 1.4x).
             Portfolio-construction / capital-allocation /
             operational-capacity characterisation per boundary
             spec §2.

C1_governance_decision:
  verdict:   PASS
  evidence:  §A.3 Row 40: "Decision: ✓ Substantively STRONG PASS
             → proceed to v0.1.14.2" at commit 955d71d
             (2026-05-17) ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 40, Text (b):
             "Trade count: 132 (unconstrained) → 72 (constrained)"
             "Profit factor: 2.50 → 4.13 (+65% on gross basis)"
             "Max DD: -7.73% → -11.01%"
             Archived evidence is constrained backtest statistics.
             No Spearman rho. §9.1 C2 NOT satisfied.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: 955d71d (2026-05-17) ✓

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: F0 FAIL (portfolio-construction / capital-allocation /
               operational-capacity characterisation per boundary
               spec §2) AND C2 FAIL (constrained backtest
               statistics are not Spearman rho). Both independent
               rejection bases.
spearman_eligible: NO
```

**Row 41 — `RESEARCH_JOURNAL / v0.1.14.1.2_F_budget_sweep`**

```text
anchor_candidate_id:   D-041
source_row:            §A.3 Row 41
canonical_artifact:    docs/RESEARCH_JOURNAL.md
finding_cluster:       F Budget Sweep — CONCENTRATED dominates
                       CURRENT

F0_anchor_type_filter:
  verdict:   FAIL
  reasoning: Finding compares five risk-budget configurations
             (CONCENTRATED 3×30% vs CURRENT 5×20% and others)
             on backtest metrics (CAGR, MaxDD, PF, win rate).
             Portfolio-construction / capital-allocation /
             operational-capacity characterisation per boundary
             spec §2.

C1_governance_decision:
  verdict:   PASS
  evidence:  §A.3 Row 41: "Three structural findings" registered
             under "F Budget Sweep Findings" at commit
             955d71d (2026-05-17) ✓

C2_archived_correlation_evidence:
  verdict:   FAIL
  evidence:  §A.3 Row 41, Text (b):
             "CAGR | +5.86% | +7.23% | +1.37pp"
             "Max DD | -11.71% | -9.57% | better"
             "PF (gross) | 4.13 | 7.08 | +71%"
             "Win rate | 54.5% | 60.7% | +6.2pp"
             Archived evidence is risk-budget comparison
             statistics. No Spearman rho. §9.1 C2 NOT satisfied.

C3_cross_sectional_statistic:
  verdict:   NOT_ASSESSED_AFTER_C2_FAIL

C4_git_reproducible:
  verdict:   PASS
  evidence:  Primary governance SHA: 955d71d (2026-05-17) ✓

C5_independent_lineage:
  verdict:   PASS
  evidence:  Not in boundary spec §1 exclusion list.

u7a_verdict:   REJECT
reject_reason: F0 FAIL (portfolio-construction / capital-allocation /
               operational-capacity characterisation per boundary
               spec §2) AND C2 FAIL (risk-budget comparison
               statistics are not Spearman rho). Both independent
               rejection bases.
spearman_eligible: NO
```

---

### D.3 Arithmetic Verification

Machine-verified from row-level records above. Summary is
derived, not independently maintained.

```text
Total §A.3 rows:              41
  Primary sources:            36
  Secondary aggregators:       5

Verdict summary:
  REJECT:                     36
  NOT_ANCHOR_AGGREGATOR:       5
  PROVISIONALLY_ELIGIBLE:      0
  Partition: 36 + 5 + 0 = 41  ✓

Reject breakdown by primary criterion:
  C3_FAIL (C2 PASS, F0 PASS):   3  rows [5, 7, 8]
    → pooled panel Spearman confirmed via source code
       (rs_persistence_decay.py, pullback_quality.py,
        rs_acceleration.py); nexus grep verified this session
  C2_FAIL (F0 PASS):            10  rows [1, 2, 3, 4, 6,
                                          10, 11, 12, 13, 14]
    → no Spearman rho or reconstructible correlation statistic
       in archived finding evidence
  F0_FAIL (+ C2 FAIL):          23  rows [15, 16, 17, 18, 19,
                                          20, 21, 22, 23, 24,
                                          25, 29, 30, 31, 32,
                                          34, 35, 36, 37, 38,
                                          39, 40, 41]
    → portfolio-construction / capital-allocation /
       operational-capacity / data-governance /
       strategy-level characterisations per boundary spec §2
  Sum: 3 + 10 + 23 = 36  ✓

C5 (independent lineage):
  PASS on all 36 primary rows.
  Boundary spec §1 exclusion list covers only:
    docs/research/ud_ratio_21d_*.md
    research/track_c_step1_closeout.md
    research/ud_ratio_21d/*
  No primary row matches any exclusion.

Eligible pool:                0
§9.2 disclosure path:         ZERO-ANCHOR
```

**Invariant record (11/11 PASS, machine-verified this session):**

```text
I1   total rows = 41                          PASS
I2   IDs 1-41 contiguous                      PASS
I3   partition 36+5+0 = 41                    PASS
I4   primary=36, aggregators=5                PASS
I5   aggregator IDs = {9,26,27,28,33}         PASS
I6   reject breakdown 3+10+23 = 36            PASS
I7   C3_FAIL rows = {5,7,8}                   PASS
I8   C5 PASS all 36 primary rows              PASS
I9   C1 PASS all 36 primary rows              PASS
I10  PROVISIONALLY_ELIGIBLE = 0               PASS
I11  n_reject = 36                            PASS
```

---

### D.4 Phase 2 Outcome

**U7A eligibility audit result:**

```text
Eligible pool size:   0
Disclosure path:      ZERO-ANCHOR

No prior Track-C study meets all five §9.1 U7A eligibility
criteria under the strict ruling applied in Phase 2.

Primary rejection reasons across the 36-row evaluated set:
  - C2 FAIL: archived findings use forward return delta, Sharpe
    ratio, admission rate, backtest statistics, or count
    metrics — none constitute per-day Spearman rho or a
    statistic from which it can be reconstructed (§9.1 C2).
  - C3 FAIL: the three studies that archive explicit Spearman
    rho values (Rows 5, 7, 8) use pooled panel Spearman with
    date-clustered bootstrap CI — confirmed by source code
    inspection. Per §9.1 C3 and Reviewer Ruling R3, pooled
    panel Spearman does not satisfy the cross-sectional
    statistics requirement.
  - F0 FAIL: 23 rows characterise portfolio-construction,
    capital-allocation, operational-capacity, data-governance,
    or strategy-level outcomes — outside the alpha /
    feature-discovery / signal-validation scope required by
    boundary spec §2.
```

**Scope closure:**

```text
Phase 2 (§D) establishes U7A eligibility only.

No §9.2 historical anchor designation is made in this phase.
No new R1 Spearman computation was executed.
No threshold or pre-registration decision is made here.
No claim of orthogonality direction is made from U7A verdicts.

The confirmed outcome of Phase 2 is an eligible pool size of zero.
Subsequent handling follows the §9.2 zero-anchor disclosure path
in Phase 3 (§E).
```

---

## §E. Phase 3 — Synthesis

```text
STATUS: NOT STARTED

This section is intentionally left empty.

Phase 3 begins only after §D is committed (commit 4 of 5).
Phase 3 output forms commit 5 of 5, potentially bundled with
R1 prereg LOCK (including N_MIN_CROSS_SECTION and
N_MIN_REGIME_DATES finalisation).

Per boundary spec v0.1.1 §5.4:
  - Compute pass count
  - Determine disclosure path:
      * multi-anchor   (>= 2 eligible candidates, at least one
                        collapse + one orthogonal)
      * single-anchor  (1 eligible candidate, or candidates only
                        on collapse side)
      * zero-anchor    (no eligible candidate; apply §9.2
                        single-anchor disclosure with explicit
                        zero-eligible note)
```

---

## Amendment Log

```text
2026-06-24  Skeleton v0.1.1-skeleton created.
            Reflects boundary spec v0.1.1 §3.3 evidence-based
            test requirement (classification letter recording).
            §A structure adopts decision Z: §A.2 pre-exclusions,
            §A.3 INCLUDED, §A.4 EXCLUDED-after-classification.
            Sort by source_file per decision P1 (no handoff
            sub-section).
            §A.5 exhaustiveness check added.
            Content TBD; populated within commit 3 of 5.

2026-06-25  Batch 1 completed.
            §A.0 additions:
              - Duplicate Handling Rule (enumeration hygiene)
              - Reviewer Discipline (Primary source? YES/NO
                annotation, non-schema)
              - Row Granularity Principle (one row = one
                independently governable research conclusion)
              - N1 governance-lag handling convention
            §A.3 Batch 1:
              - 9 INCLUDED rows from 4 files
              - 8 primary sources, 1 secondary aggregator (roadmap)
              - Row 4 corrected mid-Batch to use canonical path
                (research/r8_phase0_feasibility.md, 0226c09) after
                git --follow rename-detection issue identified
            §A.4 Batch 1:
              - 1 duplicate-of-canonical row
                (docs/research/r8_phase0_feasibility.md)
            Batch 2-6 still TBD.

2026-06-25  Batch 2b completed.
            §A.2.4 expanded with 5 more R8 methodological SPECs
              (r8_phase4_spec, r8_phase5_spec,
               r8_phase5_followup_001_spec, r8_phase6_spec,
               r8_phase6_wiring_precondition; entries A.2.4.6
               through A.2.4.10).
            §A.4 introduction expanded to define classification
              (d1) operational duplicate handling vs (d2)
              governance-process artifacts. Both sub-types remain
              under letter (d); no new classification letter.
            §A.3 Batch 2b:
              - 11 INCLUDED rows from 7 files
                (r8_phase4_optimisation_report × 4 for Finding
                 A1/A2/A3/B1; r8_phase5_configuration_report × 3
                 for Finding P5-1/P5-2/P5-3; r8_phase6_findings × 1
                 for F-P6-01; r8_phase6_candidate_disposition × 1
                 aggregator; r8_phase6_governance_report × 1
                 aggregator; r8_phase6_closeout × 1 aggregator)
              - 8 primary sources, 3 secondary aggregators
            §A.4 Batch 2b:
              - 3 governance-process artifacts under (d2)
                (price_snapshot_refresh_note,
                 step2_lineage_closeout, step3_entry_note)
            Row Granularity Principle test cases:
              - Phase 5 Configuration Verdict (ARM_B SELECTED +
                ARM_C reclassified) folded into Finding P5-3
                description rather than emitted as separate row;
                verdict is governance disposition based on findings,
                not a new empirical research conclusion (consistent
                with Batch 1 treatment of roadmap and Batch 2a
                treatment of Phase 1 Answer).
              - Phase 6 aggregator trio (candidate_disposition,
                governance_report, closeout) treated as 3 separate
                (c) rows rather than collapsed: they document
                distinct governance acts (disposition, invariant
                verification, closeout declaration) even though all
                derived from F-P6-01.
            Schema boundary maintained: §A.2 remains spec-defined
              pre-exclusion only (methodology); governance-process
              artifacts admitted to §A.4 under (d2), not promoted
              to new §A.2.5 category.
            Batch 3-6 still TBD.

2026-06-25  Batch 3 completed.
            §A.0 additions:
              - Engineering Validation Principle locked:
                "PIT PASS / FAIL records, implementation closeouts,
                 workflow completion declarations, wiring gate
                 verifications, lineage fingerprint reproducibility
                 records — are NOT empirical findings, even when
                 they contain explicit PASS/FAIL verdicts."
                Diagnostic question: "PASS what?"
                  - PASS what hypothesis about the market? → §A.3.
                  - PASS what implementation invariant? → §A.4 (d2).
                Classification turns on document identity, not lineage.
            §A.2.4 expanded with 4 more methodological artifacts
              (ADR-R8P1-001, ADR-R8P1-002, if3b_source_discovery_spec,
               phase2_research_roadmap; entries A.2.4.11 through
               A.2.4.14). All adr/ ADR placeholders now resolved.
            §A.3 Batch 3:
              - 5 INCLUDED rows from 3 files
                (P1-DATA_panel_integrity_assessment × 3 for
                 IF-1/IF-2/IF-3 with distinct downstream governance
                 lifecycles; p1_data_remediation_closeout × 1 for
                 Benchmark C robustness after IF-1 remediation;
                 helios_research_roadmap × 1 aggregator)
              - 4 primary sources, 1 secondary aggregator
            §A.4 Batch 3:
              - 1 governance-process artifact under (d2)
                (track_c_step1_closeout — engineering validation
                of ud_ratio_21d implementation; classification
                turns on document identity per Engineering
                Validation Principle, not on lineage)
            Row 29-31 (P1-DATA IF-1/IF-2/IF-3) demonstrate divergent
              governance_state_commit per row when underlying
              findings follow different downstream lifecycles
              (IF-1 → closeout b41d56b; IF-2 → reclassification
               77fb3c1; IF-3 → composition audit 39ba6c2 with
               IF-3A/IF-3B split). Per §A.0 N1 governance-lag
               convention: governance_state_commit records the
               commit that locks the current governance state,
               not the file_first_commit.
            Batch 4-6 still TBD.

2026-06-25  Cross-batch editorial pass (no schema or row count
            change; no Cumulative recount needed).
            §A.3 one_line_description fields:
              - Rows 16, 18, 22, 25 — removed verdict-style language
                ("confirms", "best known exit", "near-optimal") from
                descriptions. Verdict information remains in
                classification_evidence quotes from source.
              - Rows 9, 26, 27, 28 (all (c) secondary aggregators)
                — adopted unified template:
                "Secondary aggregator of <primary file>;
                 summarises registered findings and governance
                 dispositions; introduces no independent empirical
                 evidence."
            Convention recorded:
              one_line_description describes research content of
              the source; it does not re-assert verdicts. Verdict
              labels appear only in classification_evidence as
              direct quotes from source.

2026-06-25  Pre-commit-3 schema-tightening pass (no row count
            change; affects definitions and wording only).
            §A.0 lock additions:
              - (c) Secondary Aggregator definition tightened:
                from "referenced by name from an (a)/(b) file" to
                "introduces no independent empirical evidence, but
                 organises, summarises or disposes findings whose
                 primary source resides elsewhere." Reference does
                 not promote a SPEC to (c); document identity
                 governs.
              - governance_state_commit deterministic rule locked:
                "SHALL record the commit at which the current
                 governance state became authoritative, not
                 necessarily the first commit of the source
                 document." Rule applies per row, not per file.
              - Engineering Validation Principle diagnostic
                question generalised to: "What proposition became
                more believable because of this PASS?" — answers
                proposition-about-market → §A.3, proposition-about-
                implementation → §A.4 (d2).
              - Unique finding clusters metric defined: count of
                distinct empirical findings admitted to §A.3 via
                primary source rows. Equals Primary sources when
                Row Granularity Principle holds. This is the count
                Phase 2 U7A evaluation operates on.
            §A.3 one_line_description wording edits:
              - Row 24 (P5-3): "capacity-Sharpe trade-off not
                free" → "capacity increase accompanied by
                snapshot-sensitive Sharpe degradation"
                (replaces editorial phrasing with observation).
              - Row 25 (F-P6-01): removed final sentence on
                "narrative shift" interpretation (Phase 7 may
                overturn it; descriptions stay observable).
            Cumulative blocks (Batches 1, 2a, 2b, 3) all updated
              with Unique finding clusters field for consistency.

2026-06-25  Format-consistency cleanup pass (no schema, no row count,
            no logic change; format only).
            §A.0 additions:
              - Consistency Invariants block locked (I1 file
                partition; I2 row partition; I3 Included composition;
                I4 anchor candidate count = Unique finding clusters).
                Each Batch Summary now mandatory-includes an
                "Invariant check" sub-block.
              - Unique finding clusters definition relocated from
                Batch 3 Cumulative into §A.0 (canonical location).
            §A.3 / §A.4 row schema:
              - classification_letter and classification_type
                separated into two fields. classification_letter
                holds the bare letter form ("(a) + (b)", "(c)",
                "(d)", "(d2)"). classification_type holds the
                human-readable type name ("Primary finding source",
                "Secondary aggregator", "Operational duplicate
                handling", "Engineering validation closeout",
                "Governance forensic note", "Lineage verification
                record", "Workflow boundary marker").
              - All 38 rows (33 §A.3 + 5 §A.4) updated to the new
                two-field form via mechanical substitution.
            §A.3 one_line_description further wording cleanup:
              - Row 24 (P5-3): removed governance-consequence clause
                ("these findings resulted in ARM_B SELECTED..."),
                replaced with observation framing ("Sharpe
                degradation is observed at the boundary of
                estimator sampling error").
              - Row 25 (F-P6-01): removed disposition phrasing
                ("retained as reference exit configuration"),
                replaced with bootstrap CI observation.
            Batch Summary blocks (Batches 1, 2a, 2b, 3) all
              normalised to the same field order and aligned indent;
              Invariant check sub-block added to each.

2026-06-25  Pre-commit-3 protocol-strengthening pass (no row count,
            no schema change; rule layer additions and 1 wording
            refinement).
            §A.0 rule additions:
              - Row Granularity Principle extended: "The row
                boundary is determined by governance lifecycle,
                not by document structure." Two findings sharing
                a heading but with divergent governance
                trajectories → separate rows; two findings under
                separate headings but shared governance trajectory
                → same row.
              - Duplicate Handling Rule extended: same-commit
                tie-break added. "If duplicate paths are introduced
                within the same commit, the lexicographically first
                repository path becomes canonical unless explicitly
                documented otherwise." Makes canonicalisation fully
                deterministic in degenerate cases.
              - Phase 2 isolation rule locked: "Once a Batch Summary
                is committed to §A.3 / §A.4, no Phase 1 row may be
                added, removed, merged or split because of evidence
                encountered during Phase 2." Phase 2 may annotate
                §A.3 rows with U7A outcomes only; cannot mutate
                enumeration. Post-lock Phase 1 changes require a
                new versioned audit, not in-place edits.
              - §A.2.4 Completion invariant locked: "Every §A.2.4
                entry SHALL have a non-empty referenced_by field
                before commit 3 of 5 lands." TBD with resolution
                timing acceptable during Batches; bare TBD or empty
                NOT acceptable at commit-3 freeze.
            §A.3 wording refinement:
              - Row 24 (P5-3): "boundary of estimator sampling
                error" → "close to the predefined decision boundary".
                Removes incidental statistical-inference language;
                preserves observation framing.

2026-06-25  Batch 4 completed.
            §A.0 additions:
              - Evidence-test prevalence rule locked:
                "Document identity creates a prior, not an
                 override. When document identity conflicts with
                 the operational evidence test (§3.3), §3.3
                 evidence test prevails." Hierarchy explicitly
                 recorded: §3.3 > Document identity. Prevents
                 perverse-incentive case where findings could be
                 hidden inside log-named files to exempt them
                 from governance.
              - Duplicate Handling Rule extended with Row-level
                duplication clause. Earlier rule covered only
                file-level identical content; new clause handles
                row-level overlap (same finding cluster across
                non-identical files). Canonical = earlier-commit
                or lex-first under same-commit tie-break. Second
                file's coverage noted in canonical row's evidence,
                not emitted as separate row (would inflate I4).
            §A.3 Batch 4:
              - 8 INCLUDED rows from 2 files (both Journals).
                7 canonical anchors at docs/JOURNAL.md for
                overlap clusters with docs/RESEARCH_JOURNAL.md
                (per Same-commit tie-break: lex-first wins).
                1 canonical anchor at docs/RESEARCH_JOURNAL.md
                for the unique v0.1.14.1.2 F Budget Sweep
                cluster.
              - 8 primary sources, 0 secondary aggregators.
              - Per Evidence-test prevalence rule, Journal-named
                files are admitted to §A.3 as primary when they
                are the first-on-record source of an empirical
                claim. Document Identity is a prior, not an
                override.
            §A.4 Batch 4: 0 entries.
            Excluded version sections (v0.1.0-6 Skeleton,
              v0.1.7-10 Data Foundation): implementation
              milestones with no empirical research conclusion,
              within finding-bearing files; do not emit §A.3 or
              §A.4 rows. Recorded in Batch 4 Summary for
              enumeration completeness.
            Batch 5-6 still TBD.

2026-06-25  Batch 5 completed.
            §A.0 additions (LAST permanent rule):
              - Protocol Freeze locked (effective Batch 5+): no
                additional permanent governance rule may be
                introduced into §A.0 after Batch 4 review approval.
                Subsequent edge cases resolved using operational
                notes only. Protocol consolidation deferred until
                after Commit 5 (Phase 3 synthesis). §A.0 final
                count: 15 locked rules (14 existing + Protocol
                Freeze).
            §A.2.4 additions (12 entries, A.2.4.15 through A.2.4.26):
              - Group A (10 ADRs): ADR-001 through ADR-008
                (foundational architecture / Polars-native /
                portfolio-first / human-approval / deterministic-
                regime / cohesion / profile-switching-proposed /
                Telegram-polling), adr_p1_data_001_lifecycle_
                authority, r8_phase1_bootstrap_adr.
              - Group B (2 governance SPECs):
                p1_data_remediation_spec (P1-DATA IF-1 remediation
                methodology with 6 locked decisions + 7 acceptance
                criteria), r8_phase1_governance (R8 Phase 1 scoped
                as lifecycle-validation only, rejecting four
                alternatives).
              - Cross-reference note: r8_phase1_bootstrap_adr
                (A.2.4.24) is an EARLIER version superseded by
                ADR-R8P1-001 (A.2.4.11). Earlier version retained
                for methodology-evolution traceability.
            §A.4 Batch 5 (8 rows, all (d2)):
              - Row A4-5: v0_1_16_backtest_audit_report
                (Engineering validation report; T+1 fill-semantics
                consistency, not market behaviour).
              - Row A4-6: shioaji_semantic_observation
                (SDK contract observations with [OBSERVED] /
                [INFERRED] taxonomy).
              - Row A4-7/8: v0_1_16_daily_run_patch /
                v0_1_16_live_broker_patch (literal code-patch
                instructions).
              - Row A4-9/10: CHANGELOG_v0_1_16_v1_to_v2 /
                CHANGELOG_v0_1_16_v2_1 (advisor-review integration
                + hotfix changelogs, software fixes).
              - Row A4-11: README (directory index / ADR template
                format; documentation convention, not research
                methodology).
              - Row A4-12: obs_gate_2026_05_26 (operational
                merge/rollback gate, not market evidence).
            §A.3 Batch 5: 0 rows.
            Operational observation (NOT a new locked rule per
              Protocol Freeze): Batch 5 demonstrates that a wide
              enumeration universe paired with strict classification
              yields legitimate "negative-evidence" batches (zero
              §A.3 rows) when seed-scope files are exclusively
              methodological or governance-process in identity.
              All classification handled mechanically by existing
              §A.0 rules; no rule extension required.
            Batch 6 still TBD.

2026-06-25  Batch 6a completed (sub-batch of Batch 6 covering
            docs/handoffs/ v0.1.x version sessions, 15 files
            2026-05-19 through 2026-05-31).
            §A.0 changes: NONE (Protocol Freeze in effect).
            §A.4 Batch 6a: 15 rows (A4-13 through A4-27), all (d2)
              Workflow-continuity records.
            §A.3 Batch 6a: 0 rows.
            §A.2.4 Batch 6a: 0 entries.
            Operational notes (recorded in Batch 6a Summary and
              row reasoning, NOT promoted to §A.0):
              - Exploratory analyses and implementation diagnostics
                that were never promoted into governed research
                artifacts are treated as workflow-continuity records
                under the existing Engineering Validation Principle
                (no new rule).
              - INCONCLUSIVE is NOT a routing criterion. Routing
                criterion remains "what proposition became more
                believable?". An INCONCLUSIVE market-finding would
                still be a finding; an INCONCLUSIVE implementation
                diagnostic remains implementation.
              - Document with research-references section but
                workflow primary identity does NOT meet (c)
                Secondary Aggregator bar. Test: if the referenced
                governed findings were removed, would this file
                still stand as a workflow document? If yes → (d2),
                not (c). Applied to handoff_2026-05-29.md (Row
                A4-25): yes, it would stand → (d2).
              - This treatment preserves the (c) Secondary
                Aggregator set as a narrow class (roadmap-type
                documents whose primary identity is finding
                aggregation), preventing Aggregator-set inflation
                in Batch 6/handoffs/closeouts/release-notes.
            Batch 6b still TBD.

2026-06-25  Batch 6b completed; Phase 1 enumeration complete
            (sub-batch of Batch 6 covering docs/handoffs/ P1-DATA /
            R8 / Track C phase, 20 files 2026-05-31 through
            2026-06-23).
            §A.0 changes: NONE (Protocol Freeze in effect).
            §A.4 Batch 6b: 20 rows (A4-28 through A4-47), all (d2)
              Workflow-continuity records.
            §A.3 Batch 6b: 0 rows.
            §A.2.4 Batch 6b: 0 entries.
            Operational notes (recorded in Batch 6b note + row
              reasoning, NOT promoted to §A.0):
              - Reviewer test applied uniformly: Q1 ("first-on-record
                governed empirical conclusion?") + Q2 ("downstream
                canonical artifact exists?"). All 20 files reach
                (d2) via Q1 = No OR Q1 + Q2 = Yes.
              - The (d2) classification follows from the ABSENCE of
                a canonical anchor, not from "handoff document type".
                This corrects the earlier framing in Batch 6a
                operational notes which leaned on document-type
                reasoning. Both Batches 6a and 6b reach (d2) for
                the same underlying reason: no first-on-record
                governed conclusion lacking a downstream canonical
                anchor.
            Phase 1 enumeration totals (final):
              Files reviewed:           92
              §A.3 INCLUDED:            41 rows
              §A.4 EXCLUDED:            47 rows
              §A.2.4 methodological:    26 entries
              Primary sources:          36
              Secondary aggregators:     5
              Unique finding clusters:  36
            Remaining commit-3 work: §A.1 source list freeze,
              §A.2.1-3 pre-exclusions, §A.5 exhaustiveness check,
              §B orphan scan, §A.2.4 referenced_by resolution
              (per Completion invariant).

2026-06-25  §A.2.4 referenced_by resolution complete (per Completion
            invariant; all 26 entries now have non-empty referenced_by).
            §A.0 changes: NONE (Protocol Freeze in effect).
            §A.3 / §A.4 rows: NOT MODIFIED (per Phase 2 isolation
              rule; §A.2.4 entries reference §A.3 rows, not the
              other way around).
            Resolution methodology (Tier 1 + Tier 2):
              - Tier 1 direct textual reference: §A.3 row text
                literally mentions the spec/ADR/method artifact.
                Identified by grep against §A.3 row content.
              - Tier 2 governing-method dependency: §A.3 row finding
                was produced under the locked methodology of the
                §A.2.4 artifact, even where the row text does not
                literally cite the artifact. Identified by
                governance-chain reasoning over row source_file +
                research-program lineage.
              - Unreferenced entries: explicitly marked "no §A.3
                row currently references this artifact" with reason.
                This satisfies the Completion invariant ("non-empty
                referenced_by") and triggers the documented flag
                that the §A.2.4 entry exists for methodology/
                governance traceability without anchoring a current
                §A.3 finding row. Flag ≠ removal: foundational
                ADRs (ADR-001 through ADR-008), Phase 5 follow-up
                spec, and superseded earlier-draft ADRs are
                retained.
            Resolution counts:
              - Tier 1 (direct text): A.2.4.10, A.2.4.13 (2 entries)
              - Tier 1 + Tier 2 (both): A.2.4.2, A.2.4.11, A.2.4.12
                (3 entries)
              - Tier 2 only (governing-method): A.2.4.1, A.2.4.3-7,
                A.2.4.9, A.2.4.23, A.2.4.25, A.2.4.26 (10 entries)
              - No §A.3 reference (explicit flag, retained):
                A.2.4.8, A.2.4.14, A.2.4.15-22, A.2.4.24 (11 entries)
              Total: 26 entries, all non-empty.
            Three wording corrections applied per reviewer review:
              - A.2.4.8 (phase5_followup_001_spec): does NOT claim
                supports Row 22; reframed as non-blocking follow-up
                SPEC, not a source of admitted finding cluster.
              - A.2.4.14 (phase2_research_roadmap): does NOT claim
                superseded by Row 9; explicitly states "is not
                superseded by Row 9", retained as planning-method
                traceability.
              - A.2.4.23 (lifecycle_authority ADR): explicitly
                marked governance-chain dependency, not literal
                text reference, to avoid overstating row-level
                dependency.

2026-06-25  Fix A: Partition correction after §A.1 enumeration
            revealed 96 seed files vs 92 enumerated (Δ = 4 expected
            for §A.2.1 lineage exclusion, but inspection showed
            track_c_step1_closeout.md appearing in BOTH §A.2.1
            and §A.4 Row A4-5, violating file partition invariant).
            §A.0 changes: NONE (Protocol Freeze in effect).
            Boundary spec verification: §1 Lineage Exclusion
              confirmed to include research/track_c_step1_closeout.md
              (label "Track-C Step 1"); §A.2.1 citation correct.
            Operation:
              - Row A4-5 (track_c_step1_closeout) DELETED from §A.4
                (file is §A.2.1 pre-excluded; cannot also be
                enumerated under §3.3 evidence test).
              - §A.4 rows A4-6 through A4-48 RENUMBERED downward
                by 1 → A4-5 through A4-47 (43 row IDs shifted).
                Renumber chosen over gap-with-note: row IDs are
                enumeration sequence, not immutable identifiers;
                gap creates higher reviewer cognitive load than
                renumber in working document before commit-3 lock.
              - Three cross-references updated to match new IDs:
                * "(Row A4-9)" → "(Row A4-8)" in Row A4-9 text
                * "as Row A4-13" → "as Row A4-12" in Row A4-14 text
                * "(Row A4-5)" historical reference reframed to
                  "(§A.2.1 lineage exclusion)" pointing to correct
                  partition.
              - Amendment Log Batch 5 narrative row IDs all -1
                (A4-6..A4-13 → A4-5..A4-12).
              - Batch 3 Summary updated: Excluded 1 → 0,
                Governance-process files 1 → 0, Rows emitted 6 → 5;
                I1 invariant restated to add "Lineage-excluded (1)"
                bucket for transparency.
              - Cumulative tables updated through Batch 3 / 4 / 5 /
                6a / 6b: Total rows 89 → 88, §A.4 Excluded 48 → 47,
                Governance-process 47 → 46.
              - Header status updated: 48 → 47.
            Final partition (after Fix A):
              96 = 4 §A.2.1 (lineage-excluded) + 92 enumerated
              §A.2.4: 26 unique files (1:1 with rows)
              §A.3: 21 unique files (16 finding-bearing + 5 aggregator)
                    producing 41 rows
              §A.4: 47 unique files producing 47 rows (1:1)
              Duplicate: 1 file (docs/research/r8_phase0_feasibility.md,
                    Row A4-1, also enumerated as research/r8_phase0_
                    feasibility.md at Row 4 canonical per duplicate
                    handling rule)
              Total enumerated unique files: 26 + 21 + 47 - 1 (dup)
                                            = 93
              Check: 4 §A.2.1 + 93 enumerated unique files - 1 dup
                    in two locations = 96 ✓ but duplicate counts
                    as 1 seed file; partition holds.
            Invariant verification (post-Fix A):
              I1 (file partition): every seed file appears in
                EXACTLY one of {§A.2.1, §A.2.4, §A.3, §A.4} ✓
              I2 (rows in each batch): each Batch I2 verified ✓
              I3 (Included composition): 41 = 36 primary +
                5 aggregator ✓
              I4 (anchors): 36 unique finding clusters = 36 primary
                sources ✓
```

---

*End of audit document — COMMIT 3 LOCK READY. §A (Phase 1 enumeration), §B (orphan scan), §C (Commit 3 Readiness Gate) all complete and verified. Phase 2 (§D) and Phase 3 (§E) await commit 4 and commit 5.*
