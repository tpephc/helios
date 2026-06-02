# R8 Phase 1 — Governance Decision Record

<!-- docs/decision_records/r8_phase1_governance.md -->
<!-- v0.1.1 — 2026-06-02 -->

**Status:** ACTIVE
**SPEC reference:** `research/r8_phase1_lifecycle_spec.md` v0.1.2
**Phase 0 reference:** `docs/research/r8_phase0_feasibility.md` (closed 2026-06-01, rev2)

---

## Decision

R8 Phase 1 is authorised as a **lifecycle-validation study only**.

It is not authorised as an alpha-validation study, a strategy construction
exercise, or a basis for production deployment.

The SPEC (`research/r8_phase1_lifecycle_spec.md`) defines what Phase 1
does. This record explains why it is scoped this way and why the
alternatives were rejected.

---

## Context

Phase 0 established four facts that jointly determine Phase 1 scope.
Readers who need the supporting numbers should consult Phase 0 directly;
they are not reproduced here.

1. **R8 is tradable.** T+1 limit-lock is not a material risk. Entry at
   T+1 open is largely fillable.

2. **R8 selection substantially overlaps the RS top-tertile universe.**
   The de-circularised enrichment is measured, not estimated. R8 selects
   from already-high-RS names. Selection novelty is not established.

3. **Any independent edge, if it exists, must come from entry timing.**
   The +5% breakout event is the only candidate source of incremental
   information. This is the only open research question Phase 1 is
   designed to answer.

4. **Panel integrity issues remain unresolved.** Pre-listing contamination
   affects 7331 rows across the panel, including the RS quantile
   computation. Findings on the current panel cannot be treated as final.

These four facts jointly make lifecycle validation the correct Phase 1
scope. Alpha validation on a panel with known integrity issues, against a
benchmark the strategy substantially overlaps, would produce uninterpretable
results.

---

## Alternatives Considered

### Alternative A — Direct alpha validation

Evaluate R8 using absolute performance metrics: returns vs cash, CAGR,
Sharpe ratio, win rate.

**Rejected.** R8 selection overlaps RS exposure. A positive absolute
return result would not distinguish between the R8 timing event and the
underlying RS factor. The relevant question is incremental — R8 vs
holding RS_T3 names unconditionally — not absolute. Absolute metrics
answer the wrong question and would require reinterpretation before any
production decision could be made.

More precisely: alpha validation presupposes that the timing signal has
already been isolated from the selection effect. Phase 1 exists because
that isolation has not yet been established. Doing the wrong measurement
first is not a valid intermediate step.

### Alternative B — Immediate strategy construction

Proceed directly to execution policy design: MA5 break exit, partial
exits, re-entry rules, position sizing, portfolio construction.

**Rejected.** Execution policy requires a demonstrated timing edge as its
upstream input. Phase 0 established feasibility; it did not establish that
a timing edge exists. Building execution rules before timing evidence
exists inverts the dependency. If Phase 1 finds no incremental timing
edge, Alternative B produces a strategy with no validated foundation.
The correct order is: timing evidence first, execution policy second.

### Alternative C — Wait for P1-DATA completion before any Phase 1 work

Treat P1-DATA remediation as a hard prerequisite. Begin no Phase 1 work
until the panel integrity issues are resolved.

**Rejected.** Measurement infrastructure — lifecycle replay tooling,
forward-return computation, benchmark comparison framework — can be
developed and validated on the current panel without making final
statistical claims. The cost of waiting is concrete (delayed
infrastructure development). The benefit is marginal: the provisional
label on findings achieves the same epistemic protection as waiting,
while allowing parallel progress. P1-DATA and Phase 1 are correctly
sequenced as parallel tracks, not serial.

### Alternative D — Treat Phase 0 PASS as sufficient for production

Interpret the 5/5 Phase 0 PASS as authorisation to deploy R8 as a
production signal.

**Rejected explicitly by Phase 0 itself.** The Phase 0 verdict states:
"The PASS authorises a lifecycle-replay SPEC ONLY — not a production
rule, and not a clean orthogonality claim." This alternative is not
open for reconsideration within Phase 1.

---

## Risks

These are governance risks, not implementation risks. Implementation
risks are tracked in the SPEC and backlog.

**Risk 1 — Outcome measurement reinterpreted as alpha validation.**
Phase 1 produces forward-return distributions and benchmark comparisons.
These are measurement outputs. They do not constitute alpha validation,
regardless of how favourable the results appear. The risk is that a
positive Phase 1 result is cited as evidence that R8 has independent
alpha. This risk is mitigated by the Interpretation Restrictions section
of the SPEC (AC-7) and by the provisional findings constraint. It is not
fully eliminable; it requires active governance at the Phase 2 gate.

**Risk 2 — MA5 observations reinterpreted as exit rules.**
Phase 1 records MA5 interaction metrics as descriptive lifecycle
telemetry. The risk is that a future proposal cites Phase 1 MA5
observations as justification for an MA5-based exit policy, bypassing
the requirement for an independent SPEC. This risk is mitigated by the
Observation vs Execution Boundary section of the SPEC, which explicitly
prohibits this citation path. Any Phase 2 exit-policy proposal must
establish its own rationale independently.

**Risk 3 — Provisional findings treated as production evidence.**
Phase 1 findings are provisional pending P1-DATA remediation. The risk
is that provisional results are used in a production decision before the
panel re-run is completed, with the provisional label either overlooked
or rationalised away. This risk is mitigated by AC-6 (mandatory
provisional labelling) and by the Panel Governance section of the SPEC.
It requires active enforcement at any handoff or presentation boundary.

**Risk 4 — Scope creep into execution design during Phase 1 implementation.**
The risk is that implementation work gradually acquires execution-policy
characteristics without a formal SPEC amendment, rationalised as "just
exploratory." This is the canonical form of governance drift in research
systems. Concrete examples include: MA5 break exit logic, partial exit
mechanics, sell-half rules, sizing heuristics, or re-entry conditions
introduced under the label of exploratory or sensitivity analysis. These
are precisely the items Phase 0 deferred; their reintroduction under a
different label does not change their governance status. Mitigation: any
artifact that specifies entry, exit, sizing, or re-entry behaviour requires
a SPEC amendment or a new Phase 2 SPEC before it is written.

---

## Governance Assumptions

These are the assumptions on which this decision rests. If any is
overturned, the decision must be revisited. They are distinct from the
implementation-level Locked Assumptions in the SPEC (LA-1 through LA-8).

**GA-1 — Selection overlap is treated as established background.**
Phase 0 measured RS_T3 enrichment using a de-circularised T-1 metric.
The finding that R8 selection overlaps RS is not under re-investigation
in Phase 1. Phase 1 proceeds on the assumption that this finding holds.
If subsequent analysis overturns it, Phase 1 scope must be reconsidered.

**GA-2 — Entry timing is the only remaining open research question.**
Given GA-1, the only candidate source of incremental R8 value is the
+5% breakout event as a timing signal. Phase 1 is designed around this
single open question. If the question changes — for example, if a
selection-level argument is reopened — Phase 1 scope is no longer
appropriate.

**GA-3 — Phase 1 findings are provisional until P1-DATA remediation.**
The panel integrity issues identified in Phase 0 are real, measured, and
unresolved. Phase 1 findings cannot be treated as final while 7331
contaminated rows remain in the panel and RS quantiles are computed
over that contaminated data. Provisional status is not a formality; it
reflects a genuine epistemic limitation.

**GA-4 — The governance chain is spec-first.**
Phase 1 implementation is downstream of this SPEC and this decision
record. Implementation artifacts that contradict the SPEC or this record
are governance violations, not disagreements to be resolved by
implementation judgment. Amendments go through the SPEC, not around it.

---

## Future Invalidation Conditions

This decision record is superseded or requires amendment under any of
the following conditions:

- Phase 0's RS overlap finding is overturned by a subsequent analysis
  with a stronger identification strategy. GA-1 and GA-2 would need
  revision; Phase 1 scope may need to expand.

- P1-DATA remediation reveals that pre-listing contamination materially
  alters RS_T3 composition. GA-3 would be resolved; Phase 1 findings
  must be re-run on the clean panel before the provisional label is
  lifted.

- R8 is no longer framed as a timing question. If the research question
  shifts away from incremental timing evidence, this decision record no
  longer applies and a new governance record is required.

- A Phase 2 SPEC is approved. At that point, this record's role as the
  active governance anchor for R8 is transferred to the Phase 2 SPEC.
  This record becomes historical background.

---

## Successor Condition

This decision record authorises Phase 1 only.

Completion of Phase 1 (AC-1 through AC-7 satisfied) does not
automatically authorise transition to Phase 2. Phase 1 completion is a
necessary condition for Phase 2; it is not sufficient.

Transition to Phase 2 requires all of the following:

- AC-1 through AC-7 are satisfied and documented.
- Benchmark comparison results (RS_T3 Hold, RS_T3+Pullback,
  R8-within-RS_T3) have been explicitly reviewed, not merely computed.
- P1-DATA status has been reviewed: either remediation is complete and
  findings have been re-run on the clean panel, or a deliberate decision
  has been made to carry the provisional label into Phase 2 with explicit
  acknowledgement of the epistemic limitation.
- A Phase 2 SPEC is written and locked before Phase 2 implementation
  begins. The Phase 2 SPEC must reference this record and the Phase 1
  SPEC; it may not silently inherit scope.

If Phase 1 findings are negative (R8 does not demonstrate incremental
timing edge over RS_T3), a Phase 2 SPEC may still be appropriate — for
example, to investigate a modified entry definition or a different
regime filter. That decision requires its own governance rationale and
may not rely on Phase 1 authorisation.

---

*End of r8_phase1_governance.md v0.1.1*
