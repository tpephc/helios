# R8 MA5 Momentum — Phase 6 Wiring Precondition

<!-- research/r8_phase6_wiring_precondition.md -->
<!-- v0.1.1 — 2026-06-19 -->

**Status:** LOCKED — v0.1.1 (2026-06-19)

**Owned by:** `research/r8_phase6_spec.md` v0.1.1 (LOCKED)

**Authority level:** Governance constraint. Equivalent in binding force
to Phase 6 SPEC v0.1.1 pre-registered design decisions (§10.3).
Violation of any BLOCKING risk recorded here invalidates the affected
Phase 6 verdict component and may invalidate the entire Phase 6
evaluation depending on which risk is violated (see per-risk Failure
consequence fields).

---

## 0. Document purpose and authority

### 0.1 Why this document exists separately

Phase 6 wiring involves two distinct categories of work:

1. **Implementation discovery** — understanding the Phase 5 canonical
   evaluation harness, its ABI, its data persistence schema, and its
   feature-construction conventions. This work is exploratory and
   evolves as Phase 5 codebase is inspected. The artifact is
   `research/r8_phase6_wiring_surface.md` (private working memo until
   stable; not committed to main during the discovery phase).

2. **Methodology gate** — the set of research-level invariants that
   Phase 6 wiring code MUST preserve regardless of how the
   implementation details turn out. These invariants follow from
   Phase 5 v1.0.2 verdict, Phase 6 SPEC v0.1.1 pre-registered design,
   and the single-variable intervention principle (P6-INV-001). The
   artifact is **THIS DOCUMENT**.

The two artifacts have different lifecycles. The wiring surface doc
changes as you learn about the codebase; this precondition doc is
LOCKED before any wiring code is written and does not change without
SPEC amendment.

### 0.2 Authority and immutability

This document was initially LOCKED at v0.1.0; current version v0.1.1
incorporates Step 0 discovery refinements (see §0.4 changelog). Once
LOCKED, its content (§1 hard gates, §2 wiring order, §3 risk register,
§4 per-risk test discipline, §4.1 Wiring Gates) is immutable.
Modifications require a new minor version under the standard SPEC
LOCK chain.

Specifically:

- Adding a new risk (R7+) requires v0.2.0 and may not be done after
  Phase 6 evaluation begins (would constitute post-hoc
  pre-registration violation).
- Downgrading a BLOCKING risk to NON-BLOCKING, or upgrading
  NON-BLOCKING to BLOCKING, requires explicit SPEC amendment with
  recorded rationale.
- Modifying a risk's `Required invariant` field requires SPEC
  amendment and re-evaluation of any affected candidates already run.

### 0.3 Relationship to Phase 6 SPEC v0.1.1

This document does not redefine, supersede, or relax any Phase 6 SPEC
v0.1.1 design decision. It operationalises the SPEC for the wiring
phase: where the SPEC states "what must hold", this document states
"what code must do to make it hold and how to verify".

### 0.4 Version history

**v0.1.1 (2026-06-19) — post-Step-0-discovery refinements:**

Patch incorporates discovery findings from Step 0 (`r8_phase6_wiring_surface.md`
v0.0.1 working memo). Five Working-Paper (WP) items applied:

  - **WP-004 (R6 refinement, applied to §3):** Feature ABI clarified
    as persistence-first. Phase 6 evaluation reads feature values from
    the same persisted DuckDB tables (daily_features, bullish_features)
    that Phase 5 ARM_B reads. Calculation functions (e.g.
    features.technical.add_atr) are used only at compute-features time.
    E4 Donchian exception clause added (Phase 6 first usage; on-the-fly
    calculation acceptable with day-t exclusion unit test).
  - **WP-005 (new gate WG-1, applied to §4):** Adaptive simulator
    degenerate equivalence test added as Wiring Gate. Required before
    any E1-E4 challenger evaluation. Operationalises R3 (admission
    engine invariance) + R6 (NAV math invariance) for the unified
    simulator structural-reuse pattern (per Cross-cutting Issue 6).
  - **WP-001 (§2 Step 3 wording):** "expected direction" replaced
    with "mechanistically interpretable direction" to avoid outcome
    expectation contamination.
  - **WP-002 (§3 R4 unit test wording):** Test description revised
    from "CIs match analytical expectation" to "block length used
    equals 20 rather than 5; CI generation is deterministic given
    fixed seed" — more testable.
  - **WP-003 (§3 R1 clarification):** Explicit "for adaptive exits
    only" wording added to Required invariant. ARM_B fixed-horizon
    same-day exit-and-admit is correctly excluded by the existing
    "triggers exit" language, but the explicit clarification prevents
    future misreading.

v0.1.1 also incorporates six Cross-cutting Issues from Step 0 discovery
as informational footnotes within affected sections (§3 R5, §3 R6, §4).

**v0.1.0 (2026-06-19):** Initial LOCK. Six pre-registered risks
(R1-R6). Hard gates HG-1 through HG-4. Wiring order Step 0 through
Step 5.

---

## 1. Hard gates before any wiring code

The following must be true before the first line of wiring code is
written:

| Gate | Description | Verification |
|---|---|---|
| HG-1 | Monitored repo tree is clean | `git status --porcelain -- scripts/ core/ research/ strategies/ features/` returns empty |
| HG-2 | Phase 5 canonical evaluation harness identified | `research/r8_phase6_wiring_surface.md` exists locally with non-empty content covering the seven items in §2 Step 0 |
| HG-3 | Governance chain pushed to origin | `git log origin/main..main` returns empty (no local-only commits ahead of origin) |
| HG-4 | This document (Phase 6 Wiring Precondition, latest version) is committed to main | `git log --grep "Phase 6 Wiring Precondition" --oneline` returns at least one LOCK commit |

If any HG-N is unsatisfied, do not begin wiring. The runner skeleton's
`verify_code_sha()` enforces HG-1 at runtime, but the other three are
governance-level gates with no runtime enforcement; you are
responsible for verifying them manually before each wiring session.

---

## 2. Wiring order

Wiring proceeds in this order. Each step has explicit completion
criteria before the next step begins.

### Step 0 — Phase 5 canonical harness identification

**Deliverable:** `research/r8_phase6_wiring_surface.md` (private working
memo; not committed during discovery).

**Required content:**

1. Phase 5 runner script path and entry function signature
2. Signal pool persistence location, schema, and partition convention
3. Admission scheduling logic — function reference, tie-breaking rule,
   deferred-signal handling
4. NAV parquet schema — columns, types, date index convention
   (trading day vs calendar day), return calculation point
   (close-to-close vs open-to-close)
5. Metric computation surface — canonical functions for Sharpe,
   MaxDD, admission_rate, with annualisation and business-day
   conventions
6. Feature pipeline ABI — RS_60d, MA20, ATR(14), with explicit
   lookback boundary conventions
7. L1 snapshot identifier — how to query snapshot metadata,
   `daily_price_adj` snapshot_id storage location

**Completion criterion:** All seven items have documented content. If
any item cannot be unambiguously resolved from Phase 5 code, that
item becomes a wiring blocker requiring SPEC clarification before
proceeding.

### Step 1 — `verify_snapshot_id()` wiring

**Scope:** Implement the snapshot ID verification stub in
`scripts/run_phase6_evaluation.py`. Wire to the Phase 5 snapshot
metadata mechanism identified in Step 0 item 7.

**Completion criterion:** Runner invocation with
`--snapshot-id 2026-06-08 --dry-run` no longer raises
`NotImplementedError` at Step 2 of pre-execution checks; exits with
code 0 if snapshot matches, code 3 if mismatch.

### Step 2 — `verify_arm_a_lineage_reference()` wiring

**Scope:** Wire Arm A LU Sharpe re-evaluation to Phase 5 paper-price
NAV reconstruction harness. On the L1 snapshot, recomputed Arm A LU
Sharpe must equal Phase 5 v1.0.2 recorded value (1.569) within
±0.050 tolerance.

**Completion criterion:** Runner invocation with `--dry-run` exits 0
when L1 snapshot is reproducible; exits 3 with structured error and
required SPEC §8.1 recovery-path guidance when not reproducible.

### Step 3 — `evaluate_candidate()` orchestration

**Scope:** Daily evaluation loop with ARM_B baseline and one selected
candidate (start with E1 as proof-of-concept; extend to E2/E3/E4
after E1 produces non-trivial results).

**Subject to R1, R3, R5, R6 invariants** — see §3.

**Completion criterion:** ARM_B regeneration on L1 snapshot reproduces
Phase 5 v1.0.2 ARM_B metrics (§2 of Phase 6 SPEC) within tolerance
acceptable for floating-point determinism. E1 produces non-trivial
metrics (admission rate, mean holding days, Sharpe) that differ from
ARM_B in a mechanistically interpretable direction (per the candidate's
exit policy semantics — not a pre-registered outcome expectation).

### Step 4 — `compute_metrics()` wiring

**Scope:** Sharpe, MaxDD, admission rate, mean holding days,
calmar — all computed from NAV time series + admission/exit logs.

**Subject to R6 invariant** — reuse Phase 5 metric functions where
they exist.

**Completion criterion:** Metrics for ARM_B regenerated under Step 3
reproduce Phase 5 v1.0.2 recorded values within floating-point
tolerance.

### Step 5 — `bootstrap_delta_sharpe()` wiring

**Scope:** Stationary block bootstrap on daily NAV return delta
between challenger and ARM_B.

**Subject to R4 invariant** — block length per §3 R4.

**Completion criterion:** Bootstrap produces deterministic CIs given
fixed seed. Provenance JSON records L per candidate.

---

## 3. Pre-registered risk register

Six risks. Each was pre-registered at v0.1.0 LOCK; v0.1.1 refines
R1 (WP-003), R4 unit test wording (WP-002), and R6 (WP-004,
persistence-first hierarchy). New risks may be added only via SPEC
amendment before evaluation begins (§0.2).

### Risk #1 — Slot release timing

**Status:** BLOCKING

**Risk:** Implementing the daily evaluation loop with same-day
exit-and-admit (treating close_t exit decision and t+1-open admission
as a single same-day step) collapses the timing distinction mandated
by Phase 6 SPEC §3.1 and inflates admission count on dates with
overlapping exit triggers and pending signals.

**Required invariant:** This invariant applies to **adaptive exits**
only (E1-E4 candidates). ARM_B fixed-horizon exit is excluded: a
fixed-horizon position does not "trigger" exit at close_t — its
exit date is pre-scheduled at entry, with no decision moment.
ARM_B same-day exit-and-admit semantics (per Phase 5 `schedule_positions`)
are mathematically equivalent to t+1 admission for fixed-horizon
and are preserved as-is by Phase 6 ARM_B baseline regeneration.

For any **adaptive-exit candidate** position p that triggers exit at
close_t, the slot p occupied:
  - MUST be unavailable for admission decisions evaluated at any
    point during day t (including at close_t when day-t signals are
    being processed);
  - MUST be available for admission decisions evaluated at t+1 open
    or later.

The daily loop ordering for adaptive-exit candidates MUST be: (a) at
close_t, evaluate exit signals on all open positions; (b) at t+1
open, execute exits (record exit price = day-(t+1) open), release
slots, then evaluate admission decisions against day-t signal pool
entries that have not yet been processed (or process day-(t+1) signal
pool entries — convention to be locked in Step 0 deliverable).

**Cross-cutting Issue 4 reference:** The asymmetry between ARM_B
same-day semantics and challenger t+1 semantics is structural, not
a defect. Phase 6 evaluation report §8 limitations must document
this asymmetry. The `evaluate_candidate()` implementation must have
a bifurcated internal path: ARM_B reuses Phase 5 `schedule_positions`
directly; challengers use a unified daily simulator with explicit t+1
admission per this invariant.

**Required test / audit evidence:**

- Unit test `test_slot_release_timing_invariant()` in
  `scripts/run_phase6_evaluation.py` test suite. Synthetic scenario:
  10 slots full, one position triggers exit at close_t, one signal
  pending admission. Assertion: admission_count(day=t) == 0,
  admission_count(day=t+1) == 1.
- Execution-log audit field: per-day record of (n_exits_evaluated,
  n_exits_executed, n_slots_released, n_admissions_evaluated,
  n_admissions_executed). Manual inspection of LU window for
  same-day inflation pattern.

**SPEC reference:** Phase 6 SPEC v0.1.1 §3.1 (universal
exit-contract constraints: decision/execution timing, slot release).

**Failure consequence:** Admission rate metric inflated by
approximately the count of date pairs with both an exit trigger and
a pending admission. P6-G3 (admission Δ vs ARM_B) gate evaluation
invalidated for the affected candidate(s). Because P6-G3 is required
for SELECTED status (§6.3), any SELECTED verdict under R1 violation
is invalid. Remediation: re-run full candidate evaluation with
corrected daily loop ordering; Phase 6 evaluation report cannot be
LOCKED until remediation is complete.

---

### Risk #2 — Exit feature lookahead

**Status:** BLOCKING

**Risk:** Exit decision functions consume day-t feature values
constructed with information not strictly available at close_t.
Specifically, E4 Donchian including close_t in its lookback window
despite SPEC §3.5 explicit exclusion, or E2/E3 features using
forward-shifted aggregations.

**Required invariant:** For each exit decision function evaluated at
close_t, all input feature values MUST be computable from market data
with effective timestamp ≤ close_t, subject to per-feature exclusion
rules:

| Candidate | Feature | Day-t close inclusion |
|---|---|---|
| E1 (trailing) | `max_close_since_entry_t` | MAY include `close_t` (post-close evaluation, pre-execution at t+1 open) |
| E2 (MA20 failure) | `ma20_t`, `ma20_t-1` | MAY include `close_t` and `close_t-1` respectively (same convention) |
| E3 (RS deterioration) | `rs_60d_rank_t` | MAY include `close_t` (same convention); MUST match Phase 5 RS feature pipeline lookback convention |
| E4 (Donchian) | `donchian_low_excl_t` | MUST exclude `close_t` per SPEC §3.5 explicit wording ("lowest close of the prior `n` trading days, excluding day `t` itself") |

The retroactive corporate-action adjustment convention inherent to
the L1 `daily_price_adj` snapshot is INHERITED from Phase 5 ARM_B and
is not classified as Phase-6-introduced lookahead. The Phase 6
evaluation report §8 limitations MUST explicitly record this
inheritance.

**Required test / audit evidence:**

- Per-candidate documentation in Phase 6 evaluation report appendix:
  one-line statement per feature stating which day-t observations are
  included in the feature computation.
- E4-specific invariant test: synthetic scenario where `close_t` is
  the new all-time low over the prior `n` days; assertion
  `donchian_low_excl_t > close_t` (i.e., the lookback excludes day-t
  itself, so day-t low does not appear in the comparison reference).
- Per-day execution-log trace of first signal date in each scenario:
  emit the constructed `MarketSnapshot` for one open position,
  including feature timestamps and lookback windows for manual
  inspection.

**SPEC reference:** Phase 6 SPEC v0.1.1 §3.1 (decision/execution
timing), §3.2–§3.5 (per-candidate feature definitions); Phase 5
v1.0.2 §3 (paper-price NAV reconstruction methodology and
adj-price convention).

**Failure consequence:** Per-candidate verdict invalid. If E4
violates Donchian exclusion, exit triggers fire earlier than SPEC
allows, biasing E4 toward higher admission and lower mean holding;
P6-G2 (MaxDD Δ) and P6-G3 (admission Δ) both affected. If E2/E3
violate inclusion convention, similar bias direction. Remediation:
correct the feature construction; re-run affected candidate(s).

---

### Risk #3 — Admission regeneration (frozen pool ≠ frozen schedule)

**Status:** BLOCKING

**Risk:** Treating Phase 5 ARM_B's persisted admission schedule
(which positions were actually admitted, with which entry dates) as
Phase 6 input rather than regenerating admission decisions under each
candidate's adaptive slot dynamics. This locks the admitted-positions
count to ARM_B's, making P6-G3 mechanically zero by construction.

**Required invariant:** `evaluate_candidate()` MUST consume the
**frozen signal pool**: the set of
`(signal_date, symbol, rs_60d_rank, signal_metadata)` tuples produced
by Phase 5's signal generation pipeline on the L1 snapshot. It MUST
**regenerate admission decisions** for each candidate under that
candidate's own slot dynamics.

The frozen signal pool ≠ frozen admission schedule. ARM_B's persisted
admission schedule is an OUTCOME of Phase 5 evaluation under ARM_B's
fixed-hold dynamics, not an INPUT to Phase 6. Phase 6 reuses the
signal-generation result; it regenerates the admission result.

Tie-breaking among signals with identical RS-60d rank on the same
signal date MUST use the same deterministic helper as ARM_B. The
helper MUST be imported from the Phase 5 codebase (or its identical
equivalent), not reimplemented in Phase 6 wiring code (per R6).

**Required test / audit evidence:**

- ARM_B regeneration determinism test: run `evaluate_candidate(ARM_B,
  ...)` on the L1 snapshot; verify the regenerated admission schedule
  matches Phase 5 v1.0.2's persisted ARM_B schedule symbol-by-symbol
  and date-by-date.
- Cross-check audit: for at least one signal date d in the LU window
  where ARM_B admitted a signal that E1 would NOT admit (due to E1's
  altered slot state on day d), verify the Phase 6 admission decision
  is computed from day-d slot state + day-d signal pool entry — NOT
  from any persisted ARM_B outcome.
- `evaluate_candidate()` implementation MUST NOT have any reference
  to ARM_B's persisted admission schedule (`arm_b_admissions.parquet`
  or equivalent). Code review check during first wiring patch.

**SPEC reference:** Phase 6 SPEC v0.1.1 §1.1 (single-variable
intervention — entry/admission frozen at the *specification* level,
not the *outcome* level); Phase 5 v1.0.2 §4 (admission rule
definition); Phase 6 SPEC v0.1.1 §9.2 (capital occupancy as primary
Phase 6 research target — only meaningful if admission can vary
between arms).

**Failure consequence:** P6-G3 (admission Δ) becomes mechanically
zero by construction for all candidates. The primary Phase 6 research
question (capacity expansion via adaptive exit) cannot be answered.
Entire Phase 6 verdict cannot be produced. Remediation requires
re-architecting `evaluate_candidate()` orchestration before any
candidate evaluation produces a non-trivial result.

**Skeleton TODO correction required at first wiring patch:** The
v0.1.1 skeleton's `evaluate_candidate()` TODO comment currently
states "Load signal calendar and admission decisions (frozen per
ARM_B)". This wording is incorrect under R3. The first wiring patch
MUST correct this to: "Load frozen signal pool (per ARM_B): list of
`(signal_date, symbol, rs_60d_rank, signal_metadata)` — this is the
candidate set, not the admission outcome. Regenerate admission
decisions under this candidate's slot dynamics."

---

### Risk #4 — Bootstrap block length

**Status:** NON-BLOCKING for verdict (gates do not depend on
bootstrap per Phase 6 SPEC §5.4 and §6); BLOCKING for bootstrap
implementation (incorrect L will produce miscalibrated CIs that
contaminate the Phase 6 report's supplementary analysis).

**Risk:** Bootstrap block length chosen from challenger's mean
holding period only, ignoring ARM_B's 20td fixed-hold horizon. The
resulting block length is too short to capture the ARM_B side's
dependence, narrowing CIs.

**Required invariant:** For each challenger-vs-ARM_B stationary
block bootstrap on the daily NAV return delta series:

```
L = max(5, ceil(max(mean_effective_hold_candidate,
                    mean_effective_hold_ARM_B)))
```

`mean_effective_hold_ARM_B` is approximately 20 (ARM_B is fixed
20td hold; trivial exits via universe exclusion etc. shorten this
slightly). In practice `L ≈ 20` for all challenger-vs-ARM_B
comparisons.

`bootstrap_delta_sharpe()` MUST accept `block_length` as an explicit
argument; the caller (orchestration code) is responsible for
computing L from both arms' holding statistics. `bootstrap_delta_sharpe()`
MUST NOT compute L internally based on only one side's data.

**Required test / audit evidence:**

- Bootstrap provenance JSON records L per candidate evaluation, with
  the source values (`mean_effective_hold_candidate`,
  `mean_effective_hold_ARM_B`) and the computed L.
- Unit test: pass two arms (one challenger candidate, one ARM_B) with
  recorded `mean_effective_hold` values; verify the computed L equals
  20 (driven by ARM_B's hold) rather than 5 (driven by challenger),
  and that CI generation is deterministic given a fixed bootstrap seed
  (same seed + same input → bit-identical CI bounds).

**SPEC reference:** Phase 6 SPEC v0.1.1 §5.4 (stationary block
bootstrap, `L = max(5, max(h_arm))`); Phase 5 v1.0.2 §3.3
(bootstrap precedent).

**Failure consequence:** Bootstrap CIs narrower than they should be
(under-estimated dependence). Because bootstrap is supplementary per
SPEC §5.4 and does not affect gate verdict, this does not invalidate
Phase 6 SELECTED/CHARACTERISED/REJECTED labels under §6.3.
SELECTED_MARGINAL labels driven by Lo (2002) SE are also unaffected
(§6.3 marginal-margin discipline uses Lo SE as the primary criterion,
not bootstrap CI). However, the Phase 6 evaluation report's
supplementary bootstrap section would be miscalibrated. Remediation:
re-run bootstrap with corrected L; verdict labels unchanged.

---

### Risk #5 — Universe membership snapshot consistency

**Status:** BLOCKING

**Risk:** Phase 6 evaluation uses universe membership different from
Phase 5 — e.g., point-in-time-as-of-signal-date if Phase 5 used
point-in-time-as-of-L1-snapshot, or vice versa. RS_60d rank
denominator (universe size at day t) computed against a different
universe than ARM_B. Result: signal pool composition or rank values
drift between ARM_B and challengers, breaking cross-arm comparability.

**Required invariant:** Universe membership at every signal date and
at every exit-decision date MUST be derived from the same
membership-history snapshot used by Phase 5 — the L1 snapshot,
representing the "point-in-time-as-of-2026-06-08 view" of universe
constituency. RS_60d rank denominator (universe size at day t) MUST
match Phase 5 ARM_B's convention exactly. If Phase 5 used a
different convention than what this document interprets, Phase 5's
actual convention takes precedence and this document must be amended.

**Required test / audit evidence:**

- For a sample of signal dates within the LU window (at minimum: LU
  start date, LU mid-point, LU end date), verify the Phase 6 harness
  returns the same universe membership and the same universe size as
  Phase 5 ARM_B at the corresponding dates. Differences must be
  explained (e.g., by an identified bug in either harness) and
  remediated.
- Execution log persists universe size and a hash of universe
  membership for at least the first signal date of each scenario
  evaluated.

**SPEC reference:** Phase 6 SPEC v0.1.1 §1.1 (universe construction
frozen at ARM_B); Phase 5 v1.0.2 §8.1 (survivorship bias
documentation, 94% current-constituent confirmation).

**Failure consequence:** Cross-arm comparability broken. Phase 6
challenger results are not directly comparable to ARM_B baseline,
because the underlying signal pool's selection bias differs.
Any gate decision (P6-G1, P6-G2, P6-G3) becomes unreliable.
Entire Phase 6 verdict invalid. Remediation: identify the convention
mismatch, correct the wiring, re-run all affected candidate
evaluations including ARM_B regeneration.

---

### Risk #6 — Feature pipeline reuse (persistence-first)

**Status:** BLOCKING

**Risk:** Phase 6 wiring reads feature values from a different source
than Phase 5 ARM_B reads, or reimplements feature calculation
on-the-fly when persisted values exist. Subtle differences in
edge-case handling (first-N-day NaN treatment, suspension day handling,
ex-dividend day handling, listing-date edge handling) drift between
ARM_B and challengers. The drift may be invisible in unit tests but
produces systematic differences in the LU window's stressed segments.

**Required invariant — Feature reuse hierarchy:**

Phase 6 wiring resolves each feature in the following order:

1. **Persisted feature values first.** If the feature exists in
   `daily_features` (e.g. `atr_14`, `sma_20`) or `bullish_features`
   (e.g. `beta_adj_rs_60d`), Phase 6 evaluation MUST query the
   persisted value via DuckDB. This is the path used by Phase 5
   ARM_B and inherits the L1 snapshot lineage convention
   (per Cross-cutting Issue 5).
2. **Production calculation functions** (e.g. `features.technical.add_atr`)
   are used only at **compute-features time**
   (`scripts/compute_features.py`) to populate persisted tables.
   Phase 6 evaluation MUST NOT call these functions directly when the
   feature is persisted.
3. **On-the-fly calculation** is permitted only for **features not
   in any persisted table**, namely:
   - **E4 Donchian low** — Phase 6 first usage; not in `daily_features`
     or `bullish_features`. The calculation function MUST be added to
     `features/technical.py` with type hints, docstring matching
     convention, and a unit test asserting the explicit exclusion of
     day-t close (per Phase 6 SPEC §3.5 and Risk #2).

Adapter functions are permitted (e.g., to convert between polars
DataFrame batch interface and per-row `MarketSnapshot` evaluation
context) AS LONG AS the underlying value comes from one of the three
sources above. No alternative computation path. No fork. No
reimplementation for performance reasons.

**Concrete per-candidate reuse targets:**

| Candidate | Feature | Source path |
|---|---|---|
| E1 ATR Trailing | `atr_14` | `daily_features.atr_14` (DuckDB query) |
| E2 MA20 Failure | `sma_20` | `daily_features.sma_20` (DuckDB query) |
| E3 RS Deterioration | `beta_adj_rs_60d` | `bullish_features.beta_adj_rs_60d` (DuckDB query; same column ARM_B ranking uses) |
| E4 Donchian | `donchian_low_excl` | On-the-fly via `features.technical.donchian_low_excl` (NEW function added by Phase 6 wiring) |

**Required test / audit evidence:**

- Code review / lint check: `grep -rn "def .*atr\b\|def .*_ma\b\|def
  .*rs_rank\b" scripts/run_phase6_evaluation.py` must return empty.
  Functions with these names defined in the Phase 6 runner are
  evidence of forbidden reimplementation. (Donchian is exempt — the
  Phase 6 runner MAY contain `donchian_low_excl` IF the function is
  also added to `features/technical.py` and imported from there.)
- Import audit: `grep -nE "^from features\.|^from scripts\." 
  scripts/run_phase6_evaluation.py` must show imports of feature
  values via DuckDB query helpers and / or `features.technical.donchian_low_excl`.
- Spot check (E3): for one signal date in the LU window, compare
  `bullish_features.beta_adj_rs_60d` queried by Phase 6 wiring against
  the value used by Phase 5 ARM_B admission at the same date and
  symbol; values must match exactly (bit-identical).
- E4 day-t exclusion unit test (per Risk #2 cross-reference):
  synthetic scenario where `close_t` is the new all-time low over the
  prior `n` days; assertion `donchian_low_excl_t > close_t` (i.e., the
  lookback excludes day-t itself).

**SPEC reference:** Phase 6 SPEC v0.1.1 §1.1 (entry/ranking/sizing
frozen at ARM_B specification level — implies feature values must be
bit-identical, not just calculation-equivalent); Phase 6 SPEC v0.1.1
§3.2 (E1 ATR(14) baseline parameter); Phase 6 SPEC v0.1.1 §3.5
(E4 Donchian day-t exclusion).

**Failure consequence:** Silent feature drift between ARM_B and
challenger evaluations. Most acute at universe edge cases (newly
listed symbols, suspension days, ex-dividend days). Cross-arm
comparability degrades; the degradation is invisible in headline
metrics but biases per-position contributions. Remediation: replace
reimplemented or freshly-computed feature path with the persisted
query path; re-run affected candidate evaluations.

**Cross-cutting Issue 5 reference:** Helios feature architecture
separates calculation (`compute_features.py` writes `daily_features`)
from consumption (admission / evaluation reads `daily_features`).
This is by design and inherits the L1 snapshot lineage convention.
Phase 6 evaluation occupies the "consumption" role exclusively.

---

## 4. Per-risk test discipline

Each risk's `Required test / audit evidence` field in §3 specifies
the minimum verification. The Phase 6 wiring test suite (located in
the same repository, at a path to be confirmed during Step 0)
SHOULD organise tests so that each test references the risk it
guards against:

```python
def test_slot_release_timing_invariant():
    """R1 — slot release timing.

    See research/r8_phase6_wiring_precondition.md §3 R1.
    """
    ...

def test_donchian_excludes_day_t():
    """R2 — exit feature lookahead, E4-specific.

    See research/r8_phase6_wiring_precondition.md §3 R2.
    """
    ...

def test_arm_b_regeneration_matches_phase5_schedule():
    """R3 — admission regeneration determinism.

    See research/r8_phase6_wiring_precondition.md §3 R3.
    """
    ...
```

This cross-referencing serves three purposes:

1. Audit traceability: any future reader of the test suite can trace
   the test back to the governance constraint it enforces.
2. Remediation triage: if a risk is later violated, the failing test
   immediately identifies which §3 entry's `Failure consequence`
   applies.
3. Test maintenance: if §3 is amended (via SPEC amendment), the
   corresponding tests are identified by grep.

Tests for NON-BLOCKING risks (R4) MAY be included but are not
required to be present before evaluation begins. Tests for all
BLOCKING risks (R1, R2, R3, R5, R6) MUST be present and passing
before `evaluate_candidate()` is run on any candidate other than
ARM_B regeneration verification.

### 4.1 Wiring Gates — cross-cutting structural-reuse tests

Beyond per-risk tests in §4, certain cross-cutting tests gate
specific wiring milestones. Wiring Gates (WG-N) are operationalisations
of multi-risk invariants and apply at the structural-reuse pattern
level (per Cross-cutting Issue 6).

#### WG-1 — adaptive_simulator_degenerate_equivalence

**Required before:** any E1-E4 challenger evaluation in Step 3.
ARM_B baseline regeneration (Step 3 first half) may proceed without
WG-1 because ARM_B uses Phase 5 `schedule_positions` + 
`reconstruct_nav_for_horizon` directly, not the unified simulator.

**Risks operationalised:** R3 (admission engine invariance) +
R6 (feature pipeline reuse → NAV math reuse extension via Cross-cutting
Issue 6).

**Background:** Cross-cutting Issue 6 establishes that
`reconstruct_nav_for_horizon` is h-scalar coupled (`for k in range(h)`
loop bound applies uniformly to all positions). Adaptive exit requires
per-position variable holding period and per-bar exit decision, which
cannot be expressed via Phase 5's split admission-then-NAV pass. Phase 6
challenger evaluation therefore implements a **unified daily simulator**
that **structurally reuses** the admission decision block from
`schedule_positions` and the NAV math block from
`reconstruct_nav_for_horizon`, while substituting only the exit-trigger
mechanism.

Structural reuse means code-block copy with bit-identical semantics
for the reused logic. It is weaker than function-call reuse and
therefore requires explicit verification that the reused blocks
preserve Phase 5 behaviour under conditions where Phase 6-specific
modifications are inactive.

**Test setup:**

1. **Canonical path:** Run ARM_B baseline through Phase 5 canonical
   call sequence:
   ```
   ledger      = build_signal_ledger_for_horizon(panel, prices,
                                                  pool, scenario, h=20)
   ranked      = _rank_ledger(ledger, "beta_adj_rs_60d", "arm_b")
   sched, diag = schedule_positions(ranked, BASELINE_CAP, BASELINE_MAX_POS)
   nav_canonical = reconstruct_nav_for_horizon(sched, prices, BASELINE_CAP, h=20)
   ```

2. **Adaptive path with degenerate policy:** Run ARM_B baseline
   through Phase 6 unified simulator with exit policy that NEVER
   triggers before T+20 (i.e., exit policy = "return False until k=20"):
   ```
   nav_adaptive = evaluate_candidate_adaptive(
       ledger=ledger,
       ranked=ranked,
       exit_policy_fn=lambda pos, market: False,  # never triggers
       hard_ceiling_h=20,
       cap=BASELINE_CAP,
       max_pos=BASELINE_MAX_POS,
   )
   ```
   Under this degenerate policy, every position exits at the T+20
   hard ceiling, which is mathematically equivalent to ARM_B
   fixed-horizon exit.

**Assertion:**

  - Scheduled positions (set of (stock_id, signal_date, entry_date,
    exit_date, weight)) MUST be set-equal between canonical and
    adaptive paths.
  - Daily NAV time series MUST be bit-identical between canonical
    and adaptive paths.
  - Computed metrics (Sharpe, MaxDD, admission_rate, mean_holding_days)
    MUST be bit-identical.

Tolerance: bit-identical means equality under default pandas/numpy
float64 comparison — no epsilon. The two paths process the same
inputs through the same arithmetic operations in the same order;
any non-identity reveals admission drift, NAV math drift, or
ordering non-determinism in the unified simulator.

**Failure consequence:**

If WG-1 fails:
  - Phase 6 adaptive evaluation is INVALID. Do not run E1-E4
    challengers.
  - The Phase 6 unified simulator has drifted from Phase 5 semantics
    in either admission logic, NAV math, or ordering.
  - Diagnose by comparing per-position contributions (which positions
    are admitted with what entry/exit dates) and per-day NAV
    contributions until the drift point is localised.
  - Remediation: fix the structural reuse code-block to bit-identity
    with the corresponding Phase 5 function block.
  - WG-1 must PASS before any non-ARM_B candidate evaluation
    resumes.

**Test placement:** Unit test
`test_adaptive_simulator_degenerate_equivalence` in the Phase 6
wiring test suite, with docstring:
```python
def test_adaptive_simulator_degenerate_equivalence():
    """WG-1 — adaptive simulator degenerate equivalence.

    Verifies that the unified daily simulator (used for E1-E4
    challengers) produces bit-identical output to the Phase 5
    canonical path (schedule_positions + reconstruct_nav_for_horizon)
    under a degenerate exit policy that never triggers before the
    T+20 hard ceiling.

    See research/r8_phase6_wiring_precondition.md §4.1 WG-1.
    Operationalises R3 + R6 invariance for the structural-reuse
    pattern documented in Cross-cutting Issue 6.
    """
```

---

## 5. SPEC references summary

For convenience, all referenced SPEC sections collected here:

**Phase 5 v1.0.2:**
- §3 — paper-price NAV reconstruction methodology, adj-price
  convention (referenced by R2)
- §4 — admission rule definition (referenced by R3)
- §3.3 — bootstrap precedent (referenced by R4)
- §8.1 — universe membership / survivorship documentation
  (referenced by R5)

**Phase 6 SPEC v0.1.1:**
- §1.1 — single-variable intervention principle (referenced by R3,
  R5, R6)
- §3.1 — universal exit-contract constraints, decision/execution
  timing, slot release (referenced by R1, R2)
- §3.2 — E1 ATR Trailing frozen parameters (referenced by R6)
- §3.3 — E2 MA20 Failure frozen parameters (referenced by R2)
- §3.4 — E3 RS Deterioration frozen parameters (referenced by R2)
- §3.5 — E4 Donchian frozen parameters, Donchian exclusion of day t
  (referenced by R2)
- §5.4 — stationary block bootstrap, L formula (referenced by R4)
- §6 — gate definitions (referenced by R1 failure consequence)
- §6.3 — marginal-margin discipline (referenced by R4)
- §9.2 — capital occupancy as primary Phase 6 research target
  (referenced by R3 failure consequence)

**P5-FOLLOWUP-001 v1.0.0:**
- Not directly referenced by any risk in this document. Phase 6
  evaluation is independent of P5-FOLLOWUP-001 per Phase 6 SPEC §7
  (EXECUTE / PARALLEL / NON-BLOCKING).

---

## Governance

| Document | Version | Status |
|---|---|---|
| `research/r8_phase5_configuration_report.md` | v1.0.2 | LOCKED |
| `research/helios_research_roadmap.md` | v0.1.1 | LOCKED |
| `research/r8_phase5_followup_001_spec.md` | v1.0.0 | LOCKED / EXECUTION SPEC |
| `research/r8_phase6_spec.md` | v0.1.1 | LOCKED |
| `scripts/run_phase6_evaluation.py` | v0.1.1 | APPROVED AS SKELETON |
| `research/r8_phase6_wiring_precondition.md` | v0.1.1 | **THIS DOCUMENT — LOCKED** |
| `research/r8_phase6_wiring_surface.md` | v0.0.1 | DISCOVERY MEMO — not committed during wiring (Step 0 ~100% complete; promotion to v1.0.0 deferred to evaluation report appendix) |

This document does not authorise any Phase 6 evaluation execution.
It defines the methodological constraints that wiring code must
satisfy before evaluation execution may begin. Compliance is
evaluated per-risk at code-review time and per-candidate at
evaluation time via the test suite specified in §4.

---

*End of r8_phase6_wiring_precondition.md v0.1.1*
