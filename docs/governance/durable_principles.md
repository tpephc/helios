# Helios Durable Governance Principles

This document records cross-feature governance principles that survive
across PRs, sessions, and features. Each principle is entered once and
never rewritten in-place; superseding principles append a new entry
that names the entry being superseded.

Location rationale: this doc is deliberately not colocated with any
feature-local readiness doc (for example,
`docs/research/win_rate_21d_producer_build_readiness.md`). Durable
principles are cross-feature and must not be scoped to any one
feature's lifecycle.

---

## DGP-01: Diff-First Continuation Discipline

**Status:** ACTIVE

**Originated:** PR-2A restart, following a governance incident in
which a session designed an entire skeleton against a session-handoff
prompt without reading HEAD source, then discovered its design was
incompatible with the already-landed PR-1 public API surface. Session
was rolled back to a clean tree; incident notes below.

**Principle:**

Session-handoff prompts (continuation notes, briefing summaries,
resumed-session context blocks) are lossy compressions of code state.
They exist to orient a fresh session, not to authorize implementation
against.

Before a session introduces any change that touches a canonical
identifier, public API, governance-locked constant, or a symbol
mentioned in any locked SD, the implementing session MUST:

1. Read HEAD of every module named in the handoff as "in scope".
2. Read the test files that lock the public API contract of those
   modules.
3. Diff the handoff's factual claims against the read code, treating
   any discrepancy as a governance event rather than an implementation
   detail to be inferred.
4. Resolve every discrepancy BEFORE the first line of implementation
   is written. Resolution may be: (a) confirming the handoff is
   accurate and the session's mental model was wrong; (b) confirming
   the code has drifted from the handoff and the handoff is stale;
   or (c) escalating to the operator to pick canonical truth.

**Anti-pattern this exists to prevent:**

- Inventing canonical identifiers (enum members, string literals used
  in manifests, public function names) based on the handoff's
  paraphrase of an SD entry rather than the SD entry itself or the
  code that mirrors it.
- Overwriting a locked public API because the handoff described an
  earlier iteration or an abstract intent rather than the current
  shape.
- Deferring diff-first verification to "after the skeleton compiles",
  which reliably produces skeletons incompatible with real HEAD.

**Non-goals:**

DGP-01 is not a call for exhaustive whole-repo reads. It applies to
every module named in scope for the current change, plus the tests
that lock the public API of those modules. It does not require
reading unrelated modules.

**Incident summary (retained for institutional memory):**

- Session context: PR-2A skeleton design for
  `features/win_rate_21d`.
- Handoff prompt described pre-flights as "V1-V4+V6" (an SD-A2-3
  internal shorthand for verification steps).
- Session mistook this for a canonical identifier scheme, invented
  `PreFlightCheckId.V1..V6` as an enum, and wrote an entire skeleton
  around it.
- Actual HEAD code used `PF-B1..PF-B6` as canonical string
  identifiers, locked by tests
  (`assert result.check_id == "PF-B3"`).
- Session also overwrote PR-1's real implementations of PF-B3 and
  PF-B4 back to shells, unaware they were already real.
- Discovery mechanism: `uv run pytest` collection errors surfaced
  legacy tests (`test_pre_flight_shell.py`,
  `test_producer_surface.py`) whose imports (`PreFlightResult`,
  `BuildScope`) revealed the incompatible API surface.
- Cost: full rollback of one working tree; two sessions of
  disposition rework.
- Root cause: the session never ran the equivalent of
  `cat features/win_rate_21d/pre_flight.py` before designing.

**Enforcement:**

DGP-01 is a review-time norm, not a mechanical gate. Reviewers should
ask: "Did the implementing session read the HEAD of every module in
scope before designing?" If the answer is no or unclear, the PR
should be blocked pending a diff-first re-read, regardless of
apparent correctness.

**Canonical truth precedence:**

When two artifacts appear to disagree about the current shape of the
system, the following precedence resolves the disagreement:

1. **Locked specification** (SD entries, spec documents, governance
   ledger entries): highest authority. A locked SD supersedes any
   code, test, or handoff that contradicts it. A contradiction is a
   governance event: either the code must be corrected, or the SD
   must be formally amended.
2. **HEAD code**: authoritative for the current implementation shape.
   Deviations from HEAD in any downstream artifact (readiness docs,
   handoffs, session notes) are stale documentation, not license to
   ignore HEAD.
3. **Locked tests**: authoritative for the current public API
   contract. A test that has been merged and is green locks the API
   shape it exercises. Changing behavior that a locked test observes
   requires either updating the test in the same PR (with governance
   justification) or preserving the observed behavior.
4. **Session handoff**: orientation only. Never authoritative on its
   own; must be verified against 1-3 before acting.

This ordering resolves the majority of "the handoff said X but the
code says Y" disputes without further debate.

---

<!--
Future entries append below this line. Never rewrite an existing
entry in place. Supersession is expressed by a new entry that names
the entry it supersedes; the superseded entry's Status field is
updated to reference the superseding entry.
-->
