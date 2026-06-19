# R8 MA5 Momentum — P5-FOLLOWUP-001 SPEC

<!-- research/r8_phase5_followup_001_spec.md -->
<!-- v1.0.0 — 2026-06-19 -->

**Status:** LOCKED — EXECUTION SPEC (graduation from SKELETON v0.1.1)

**Changelog:**

| Version | Date | Change |
|---|---|---|
| v0.1.0 | 2026-06-19 | Initial skeleton draft |
| v0.1.1 | 2026-06-19 | §4.5: explicit disclaimer that Lo (2002) SE is a governance noise-floor reference, not a formal inference procedure. §5: documented the conservative-by-design rationale for PROMOTE (two independent noise models required simultaneously); false-PROMOTE / false-INCONCLUSIVE cost asymmetry made explicit. |
| v1.0.0 | 2026-06-19 | Graduation from SKELETON to LOCKED / EXECUTION SPEC under Phase 6 SPEC v0.1.0 §7 authorisation (decision: EXECUTE / PARALLEL / NON-BLOCKING). §6 rewritten from authorisation gate to authorisation record. §7 expanded with runner specification (`scripts/run_phase5_followup_001.py` v0.1.0). §8 expanded with full artifact schema. §9 (new) execution log specification. §10 (new) failure modes and recovery. Sections §1–§5 and original §8 (now §11 limitations) preserved verbatim from v0.1.1 — pre-registered design content is immutable post-graduation. |

**Owner:** Phase 6 SPEC v0.1.0 (this followup is a Phase 6 SPEC item,
  not an open Phase 5 item)
**Phase 6 SPEC authorisation:** EXECUTE / PARALLEL / NON-BLOCKING
  (see §6 and Phase 6 SPEC v0.1.0 §7)
**Blocking (research):** Working Hypothesis P5-4 promotion (hypothesis
  → finding, or hypothesis → rejected, or hypothesis → retained as
  INCONCLUSIVE)
**Not blocking:** Phase 5 verdict (CONFIGURATION_SELECTED, ARM_B
  SELECTED) is LOCKED v1.0.2 and does not depend on this followup's
  outcome. Phase 6 execution is also not gated by this followup.
**Parent:** `research/r8_phase5_configuration_report.md` v1.0.2,
  §7 (Working Hypothesis P5-4), §8.4, §9.4 item 4
**Sibling:** `research/r8_phase6_spec.md` v0.1.0 (parallel execution)

---

## 1. Purpose

P5-FOLLOWUP-001 resolves the identification problem flagged in Phase 5
v1.0.2 §7 (Working Hypothesis P5-4): whether the apparent
sub-additivity between RS-60d ranking and 10td holding is a real
interaction effect or an artefact of comparing Phase 4 single-factor
Sharpe estimates and the Phase 5 combined-configuration Sharpe estimate
across **different `daily_price_adj` snapshots**.

Resolution requires snapshot-consistent estimates of all four cells of
the 2×2 design (ranking × holding period) on a single locked price
snapshot.

---

## 2. Research question (pre-registered)

> On a single locked `daily_price_adj` snapshot, is the interaction
> term in the 2×2 design (ranking ∈ {FIFO, RS-60d} × holding ∈ {20td,
> 10td}) materially different from zero in the Low-Uplift environment?

Interaction term:

```
Δ_interaction = Sharpe(RS-60d, 10td) − Sharpe(RS-60d, 20td)
                                     − Sharpe(FIFO,   10td)
                                     + Sharpe(FIFO,   20td)
```

A non-zero Δ_interaction is the formal expression of "non-additivity".

---

## 3. Scope

### 3.1 In scope

Re-evaluate four configurations on **one** locked snapshot:

| Cell ID | Configuration | Phase 5 status |
|---|---|---|
| C-FF-20 | 20td + FIFO   | Arm A (already on Phase 5 snapshot) |
| C-FF-10 | 10td + FIFO   | **Not collected on Phase 5 snapshot** |
| C-RS-20 | 20td + RS-60d | Arm B (already on Phase 5 snapshot) |
| C-RS-10 | 10td + RS-60d | Arm C (already on Phase 5 snapshot) |

Of the four cells, three (C-FF-20, C-RS-20, C-RS-10) already exist on
the Phase 5 snapshot. The single missing cell is **C-FF-10**. The
incremental work is therefore one configuration evaluation, plus the
interaction-term computation.

### 3.2 Out of scope

- Re-evaluation on a third snapshot (locking convention below applies).
- Bootstrap re-evaluation of arms beyond what is needed for C-FF-10.
- Any portfolio configuration not in the 2×2 design.
- Track C feature research.
- Any modification to Phase 5 verdict or ARM_B / ARM_C labels.

---

## 4. Methodology

### 4.1 Snapshot locking

A single `daily_price_adj` snapshot must be locked for the entire
followup. Two acceptable conventions:

- **Option L1 — Phase 5 snapshot (recommended).** Use the
  `daily_price_adj` snapshot as of 2026-06-08, identical to Phase 5
  v1.0.1/v1.0.2 evaluation. This is the cleanest extension of the
  Phase 5 record. The snapshot must be re-materialised from the same
  source (`data/_storage/helios.duckdb` as of 2026-06-08) or, if that
  snapshot is no longer reproducible, the followup must be re-scoped
  under L2.
- **Option L2 — Fresh snapshot at execution time.** Use the
  `daily_price_adj` snapshot as of the followup execution date. Under
  L2, all four cells must be re-evaluated (not just C-FF-10) to
  maintain snapshot consistency, and the followup is no longer a
  one-cell extension. Choose L2 only if L1 is not reproducible.

The Phase 6 SPEC must record which convention is used and why.

### 4.2 Configuration of C-FF-10

C-FF-10 is constructed by taking the existing Arm A pipeline
(`scripts/run_phase5_analysis.py` Arm A configuration on locked
snapshot) and replacing the holding period parameter `H = 20td` with
`H = 10td`, with FIFO admission preserved. All other elements (universe,
slot cap, position size, slippage assumptions, scenario segmentation,
metric definitions) must be identical to Arm A.

Required forward returns: `fwd_10td`.

### 4.3 Scenario evaluation

The interaction term must be computed in **both** scenarios:

- Full Sample
- Low-Uplift (Segments 2+3, 2023-10-24 to 2025-08-08)

The Low-Uplift evaluation is the primary one, consistent with Phase 5
gate logic. Full Sample is supplementary.

### 4.4 Bootstrap

Two-sample stationary block bootstrap on Δ_interaction, with the same
parameters used in Phase 5 (B = 5,000, L = max(5, max(h_arm))). The
bootstrap is supplementary, not a decision gate (consistent with Phase
5 §3.2 D2 rationale: LU bootstrap CIs cross zero).

### 4.5 Sampling-error context

Report the Sharpe estimator's sampling SE for each cell, using the iid
Lo (2002) approximation:

```
SE(Sharpe) ≈ sqrt((1 + Sharpe^2 / 2) / T)
```

where T is the number of daily return observations in the scenario.
This is an under-estimate (it ignores autocorrelation) but provides a
lower-bound reference for whether |Δ_interaction| is in the
distinguishable-from-noise range. A Newey-West-style HAC adjustment is
recommended if execution budget permits but is not required.

**Used only as a governance noise-floor reference, not as a formal
inference procedure.** The Lo (2002) approximation is invoked here to
calibrate the §5 acceptance-criteria thresholds against a transparent
sampling-noise scale; it is not a hypothesis test, does not produce a
p-value, and does not constitute statistical significance evidence
about Δ_interaction.

---

## 5. Acceptance criteria (pre-registered decision rule)

The followup pre-registers a decision rule for promoting / rejecting /
retaining Working Hypothesis P5-4.

Let `|Δ_interaction_LU|` be the absolute value of the Low-Uplift
interaction term, and let `SE_pooled` be the pooled Sharpe sampling SE
across the four cells (computed under §4.5).

| Outcome | Criterion | P5-4 status after followup |
|---|---|---|
| **PROMOTE** | `|Δ_interaction_LU| >= 2 × SE_pooled` AND sign is negative (sub-additive) AND bootstrap CI excludes zero | Promote P5-4 from working hypothesis to finding; update Phase 5 v1.1.0 |
| **REJECT** | `|Δ_interaction_LU| < 1 × SE_pooled` | Reject P5-4; mark as identified-and-not-supported; update Phase 5 v1.1.0 |
| **INCONCLUSIVE** | Otherwise | Retain P5-4 as working hypothesis; do not update Phase 5 verdict; record outcome in Phase 6 SPEC limitations |

The 2σ / 1σ thresholds are governance heuristics, not significance
boundaries. The pre-registration of these thresholds in this SPEC
prevents post-hoc threshold selection.

**On the conservatism of PROMOTE:** The PROMOTE criterion combines two
independent noise models (the Lo-approximation SE_pooled in §4.5, and
the stationary-block bootstrap CI in §4.4) and requires both
simultaneously. This is intentionally conservative — passing one but
not the other will land in INCONCLUSIVE, not PROMOTE. The rationale is
that P5-4 is not a deployment blocker (the Phase 6 research direction
holds independently of its outcome per Phase 5 §9.2), so the cost of a
false PROMOTE is higher than the cost of a false INCONCLUSIVE: a false
PROMOTE would let a noise-driven interaction propagate into downstream
SPECs as an "established finding"; a false INCONCLUSIVE simply keeps
the working-hypothesis label, which is the correct default until
identified.

The followup outcome **does not** modify:
- Phase 5 verdict (CONFIGURATION_SELECTED)
- ARM_B SELECTED status
- ARM_C CAPACITY_DEMONSTRATED / SHARPE_UNRESOLVED reclassification
- Phase 6 deployment baseline (ARM_B)

Phase 6 research direction (exit policy) is justified primarily by the
capital-occupancy bottleneck (Phase 5 §9.2), independent of this
followup's outcome.

---

## 6. Authorisation record

Phase 6 SPEC v0.1.0 §7 made the authorisation decision:

```
DECISION:  EXECUTE
EXECUTION: PARALLEL to Phase 6 evaluation (non-blocking)
SOURCE:    research/r8_phase6_spec.md v0.1.0 §7 — LOCKED
```

Rationale (recorded in Phase 6 SPEC §7):

1. Incremental cost is minimal — three of the four 2×2 cells already
   exist on the L1 snapshot; only `C-FF-10` (10td + FIFO) requires
   evaluation.
2. Working Hypothesis P5-4 is referenced across the Phase 5 report,
   roadmap, and Phase 6 SPEC; leaving it unresolved indefinitely
   creates accumulating documentation debt.
3. Resolving P5-4 after Phase 6 begins would require a fresh snapshot
   and a four-cell rerun (§4.1 Option L2), which is more expensive
   than the current one-cell extension under L1.

**What this authorisation does not permit:**

- Modification of Phase 5 v1.0.2 verdict under any followup outcome.
- Modification of ARM_B SELECTED status under any followup outcome.
- Modification of ARM_C reclassification (CAPACITY_DEMONSTRATED /
  SHARPE_UNRESOLVED) under any followup outcome.
- Modification of Phase 6 SPEC v0.1.0 pre-registered design (P6-INV-001,
  P6-INV-002, P6-D1–P6-D5, gate thresholds, candidate parameters).

The followup outcome may trigger a Phase 5 v1.1.0 amendment (per
Phase 6 SPEC §9.3) and a Phase 6 SPEC v0.1.1 amendment, but only in
the §1 motivation language. Verdict and design decisions are immutable.

**Execution timing constraint:** Phase 6 evaluation does not wait for
this followup's completion. If the followup completes before Phase 6
evaluation report LOCK, the followup outcome is referenced; if not,
Phase 6 report LOCKs without the followup result and a later Phase 5
v1.1.0 amendment is filed when the followup completes.

---

## 7. Runner specification

### 7.1 Script

**Path:** `scripts/run_phase5_followup_001.py`
**Version:** v0.1.0 (locked at execution time; subsequent runner changes
  require Phase 5 v1.1.0 amendment chain)
**Header convention (Helios):**

```python
#!/usr/bin/env python3
# scripts/run_phase5_followup_001.py
"""P5-FOLLOWUP-001 runner — v0.1.0.

Snapshot-consistent re-evaluation of Phase 4 single-factor `10td + FIFO`
configuration on the Phase 5 L1 snapshot, with computation of the 2×2
interaction term Δ_interaction and the §5 acceptance-criteria verdict.

Owned by: r8_phase5_followup_001_spec.md v1.0.0
Parent:   r8_phase5_configuration_report.md v1.0.2
Phase 6:  r8_phase6_spec.md v0.1.0 §7 (authorisation)
"""
```

### 7.2 CLI interface

Required arguments:

```
--snapshot-id YYYY-MM-DD          Required. Must equal 2026-06-08 under L1.
--bootstrap-seed INT              Required. Recorded in provenance.json.
--code-sha STRING                 Required. Git SHA of helios repo at run time.
                                  Must match current `git rev-parse HEAD`.
--config-mode {L1, L2}            Default: L1. L2 triggers four-cell rerun
                                  and emits a warning that L1 was abandoned
                                  per §10.1 failure-mode trigger.
--output-dir PATH                 Default: data/_storage/r8_phase5_followup_001/v0.1.0/
--dry-run                         Optional. Validates inputs, reproducibility,
                                  and existing-artifact paths without running
                                  evaluation. Exits 0 if all checks pass.
```

The runner must refuse to run if `git status --porcelain` reports
uncommitted changes in `scripts/`, `core/`, or `research/`. The
`--code-sha` argument must match the current HEAD SHA exactly; this is
a structural reproducibility guard, not optional.

### 7.3 Determinism requirements

The runner must satisfy:

1. **Bootstrap seed locked.** The `--bootstrap-seed` argument seeds both
   numpy and any internal RNG. The same seed must produce bit-identical
   bootstrap CIs across reruns.
2. **Snapshot ID locked.** Before any computation, the runner verifies
   that the `daily_price_adj` snapshot in `data/_storage/helios.duckdb`
   matches the recorded snapshot ID. Verification protocol per §10.1.
3. **Code SHA recorded.** The runner records the git HEAD SHA and
   refuses to proceed if HEAD has uncommitted changes.
4. **Floating-point determinism.** No multi-threaded reductions are
   permitted in metric computation. Bootstrap parallelism is permitted
   only if seeds are partitioned deterministically (e.g., child seeds
   = parent_seed + i).
5. **No randomness outside bootstrap.** All metric calculations
   (Sharpe, MaxDD, admission rate, etc.) must be deterministic
   functions of the snapshot. Bootstrap is the only stochastic
   component.

### 7.4 Computation steps (locked execution sequence)

The runner executes the following steps in order. Each step emits a
structured log entry per §9.

```
Step  Action
----  ------
 1    Verify code SHA matches --code-sha
 2    Verify --snapshot-id matches daily_price_adj snapshot
 3    Verify L1 reproducibility (Arm A LU Sharpe check, §10.1)
 4    Locate existing Phase 5 cell artifacts:
        C-FF-20:  data/_storage/r8_phase5/v0.1.0/arm_a/
        C-RS-20:  data/_storage/r8_phase5/v0.1.0/arm_b/
        C-RS-10:  data/_storage/r8_phase5/v0.1.0/arm_c/
      Abort if any of the three is missing or has snapshot mismatch.
 5    Construct C-FF-10 configuration from Arm A spec with
      single-parameter override: H = 20td → H = 10td.
      No other parameter change permitted (P6-INV-001 analogy).
      Configuration diff must be exactly one line.
 6    Run C-FF-10 evaluation. Emit per-scenario metrics.
 7    Compute Δ_interaction (Full Sample, Low-Uplift).
 8    Compute SE_pooled per §4.5 (Lo 2002 approximation).
 9    Run stationary block bootstrap on Δ_interaction
      (B = 5000, L = max(5, max(h_arm))).
10    Apply §5 acceptance-criteria decision rule.
11    Emit all artifacts per §8.
12    Emit final execution log per §9.
```

Steps 1–4 are pre-execution checks. Any failure in these steps aborts
the run with the artifact directory left untouched. Steps 5–12 are the
execution proper.

### 7.5 Configuration diff requirement (single-variable intervention)

Step 5 constructs C-FF-10 by deriving from the locked Arm A spec. The
diff between the Arm A configuration and the C-FF-10 configuration must
be exactly one line, the holding-period parameter. The runner must
emit this diff into the execution log (§9) for human review. Any diff
larger than one line is a structural error and aborts the run.

This mirrors the §1.1 P6-INV-001 single-variable intervention principle
from Phase 6 SPEC, applied here within the followup design: the
followup tests one cell change against a locked baseline, nothing else.

---

## 8. Artifact specification

### 8.1 Output directory

```
data/_storage/r8_phase5_followup_001/v0.1.0/
```

Directory must not exist before the run. The runner creates it. This
prevents accidental overwrite of a prior execution's outputs.

### 8.2 Required artifacts (locked schema)

| Filename | Content | Format |
|---|---|---|
| `provenance.json` | snapshot_id, code_sha, bootstrap_seed, runner_version, runtime_utc, config_mode | JSON |
| `c_ff_10_metrics.json` | Per-scenario metrics for C-FF-10: Sharpe, ann_return, ann_vol, max_dd, calmar, admission_rate, scheduled_count, candidates_count, mean_holding_days | JSON |
| `existing_cells_reference.json` | Snapshot of metrics from C-FF-20, C-RS-20, C-RS-10 (read from existing Phase 5 artifacts, copied verbatim for provenance) | JSON |
| `interaction_term.json` | Δ_interaction (FS, LU), SE_pooled (FS, LU), input cell values used for computation | JSON |
| `bootstrap_interaction.json` | Bootstrap distribution summary, 95% CI for Δ_interaction (FS, LU), B, L, seed | JSON |
| `verdict.json` | §5 decision (PROMOTE/REJECT/INCONCLUSIVE), per-criterion rationale, marginal flags if any | JSON |
| `execution_log.json` | Structured log per §9 | JSON |
| `c_ff_10_daily_nav.parquet` | Daily NAV time series for C-FF-10 (FS and LU segments) | Parquet |

JSON files must be deterministic (sorted keys, fixed float precision —
6 decimals for ratios, 2 decimals for percentage points). Parquet
files must use zstd compression with seed-independent ordering.

### 8.3 Report artifact

Filename: `research/r8_phase5_followup_001_report.md` v1.0.0

Produced post-execution by manual authoring. The report consumes the
§8.2 artifacts and produces a human-readable verdict document. The
report version locks at v1.0.0 on LOCK approval and follows the
Phase 5 report v1.0.2 §10 governance pattern.

Required report sections:

```
1. Executive Summary (verdict and one-paragraph rationale)
2. Inputs (cite this SPEC, snapshot ID, code SHA, seed)
3. Cell Metrics (C-FF-20, C-FF-10, C-RS-20, C-RS-10 on L1)
4. Interaction Term (Δ_interaction, SE_pooled, bootstrap CI)
5. §5 Acceptance Criteria Evaluation
6. Verdict (PROMOTE / REJECT / INCONCLUSIVE)
7. Implications for Working Hypothesis P5-4
8. Limitations (cite §11 of this SPEC)
9. Governance (artifact paths, parent documents)
```

### 8.4 Phase 5 v1.0.2 amendment trigger (conditional)

Per Phase 6 SPEC §9.3:

- If verdict is **PROMOTE** or **REJECT**: trigger Phase 5 v1.0.2 →
  v1.1.0 amendment (P5-PATCH-005). The Phase 5 report's Working
  Hypothesis P5-4 status updates to either `FINDING` (PROMOTE) or
  `IDENTIFIED-AND-NOT-SUPPORTED` (REJECT).
- If verdict is **INCONCLUSIVE**: no Phase 5 amendment is triggered.
  Working Hypothesis P5-4 retains its v1.0.2 working-hypothesis status.
  This SPEC retains v1.0.0; no further version.

The Phase 5 amendment SPEC is not pre-authored; if triggered, it is
drafted and approved through the standard SPEC-LOCK chain.

---

## 9. Execution log specification

A structured execution log is required for reproducibility, audit, and
downstream consumption by the report (§8.3).

### 9.1 Pre-execution entries (Steps 1–4)

| Entry | Required content |
|---|---|
| `code_sha_verification` | git HEAD SHA at runtime, --code-sha argument, match status |
| `git_clean_check` | Output of `git status --porcelain` for scripts/, core/, research/ — must be empty |
| `snapshot_id_verification` | --snapshot-id argument, snapshot ID in `helios.duckdb`, match status |
| `l1_reproducibility_check` | Recomputed Arm A LU Sharpe, expected 1.569 ±0.050, observed value, deviation, pass/fail |
| `existing_artifacts_check` | Per-cell (C-FF-20, C-RS-20, C-RS-10) artifact path existence, snapshot ID match, integrity hash |

If any pre-execution entry fails, the runner aborts and the log
records the failure with full diagnostic detail (§10).

### 9.2 Configuration log entry (Step 5)

| Entry | Required content |
|---|---|
| `arm_a_spec_loaded` | Path to Arm A spec, content hash, parameters used |
| `c_ff_10_config_diff` | Unified diff between Arm A spec and C-FF-10 config — must be exactly one line |
| `c_ff_10_config_validated` | OK / FAIL — fails if diff is > 1 line |

### 9.3 Computation log entries (Steps 6–10)

| Entry | Required content |
|---|---|
| `c_ff_10_evaluation_completed` | Runtime seconds, per-scenario metric summary |
| `interaction_term_computed` | Δ_interaction (FS, LU), input values, formula recorded |
| `se_pooled_computed` | SE_pooled (FS, LU), per-cell Sharpe SE, T (observation count) per scenario |
| `bootstrap_completed` | B, L, seed, observed Δ, 95% CI (FS, LU), runtime seconds, warnings if any |
| `verdict_applied` | §5 decision rule input values, decision output, per-criterion pass/fail |

### 9.4 Post-execution entry (Steps 11–12)

| Entry | Required content |
|---|---|
| `artifacts_written` | List of artifact paths, file sizes, content hashes |
| `verdict_summary` | Final verdict (PROMOTE / REJECT / INCONCLUSIVE), marginal flags, expected Phase 5 amendment trigger per §8.4 |
| `runtime_total_seconds` | End-to-end runtime |

### 9.5 Log file format

The execution log is written to `execution_log.json` as a JSON array of
log entries, each entry an object with `step`, `timestamp_utc`, `level`
(INFO / WARNING / ERROR), and `payload`. The schema must be stable
across runs; downstream consumers (Phase 5 v1.1.0 amendment process)
depend on the structure.

---

## 10. Failure modes and recovery

### 10.1 L1 reproducibility failure

**Trigger:** Step 3 detects that recomputed Arm A LU Sharpe deviates
from 1.569 by more than ±0.050 tolerance.

**Diagnosis required (per Phase 5 v1.0.2 §9.4 item 5 forward
governance):**

1. Divergence localisation: which dates and which symbols changed.
2. Independent attribution check: symbol-level reconciliation against
   TWSE source records, or cross-validation against a second adj-price
   source.
3. Documented evidence chain in the failure report.

Plausibility argument alone is insufficient. This is the explicit
forward governance correction from Phase 5 §8.6 and §9.4 item 5.

**Recovery paths (in order of preference):**

1. **Snapshot reconstruction.** If the deviation is attributable to an
   accidental local snapshot drift (e.g., a recent re-ingestion of
   FinMind/Shioaji corporate-action records), attempt to reconstruct
   the 2026-06-08 snapshot from upstream sources and retry Step 3.
2. **L2 fallback (per §4.1 Option L2).** Switch to a fresh snapshot at
   execution time. The followup scope expands to all four cells
   (C-FF-20, C-FF-10, C-RS-20, C-RS-10 all re-evaluated). The runner
   `--config-mode L2` argument triggers this path; the runner emits a
   prominent warning that L1 was abandoned and that all four cells
   will be recomputed.

L2 fallback requires updating this SPEC to v1.0.1 (post-graduation
amendment) with explicit recording of the L1 → L2 switch rationale and
the new snapshot ID. The acceptance criteria (§5), scope (§3), and
research question (§2) are unchanged; only the snapshot reference
changes.

### 10.2 Existing-cell artifact mismatch

**Trigger:** Step 4 detects that one or more of C-FF-20, C-RS-20,
C-RS-10 artifact directories are missing, have different snapshot IDs,
or fail integrity-hash check against expected values.

**Recovery:** Abort. Inspect the Phase 5 artifact directory for
provenance. If the Phase 5 artifacts have been overwritten or
corrupted, escalate to Phase 5 v1.0.2 governance — the followup cannot
proceed because the comparison requires the original Phase 5
snapshot-consistent estimates as anchors. Do not regenerate the
Phase 5 artifacts inside the followup; that would entangle Phase 5 and
the followup and contaminate provenance.

### 10.3 Bootstrap divergence or numerical issues

**Trigger:** Step 9 reports numerical warnings (NaN in CI, bootstrap
sample variance underflow, etc.).

**Recovery:** Record the warnings in the execution log. The bootstrap
is supplementary per §4.4, so verdict can still be issued from §5
acceptance criteria. If `SE_pooled` itself fails to compute (e.g.,
zero variance in a cell — pathological case), abort and inspect the
input cells.

### 10.4 Code SHA mismatch or uncommitted changes

**Trigger:** Step 1 detects `--code-sha` does not match `HEAD`, or
`git status --porcelain` is non-empty for monitored directories.

**Recovery:** Abort. Reproducibility requires a clean, identified
codebase state. Commit the changes (or stash them), update
`--code-sha` to the new HEAD, and retry. The followup does not run on
an uncommitted codebase.

### 10.5 Verdict ambiguity

**Trigger:** Step 10's §5 decision rule produces a result that does
not fit cleanly into PROMOTE / REJECT / INCONCLUSIVE (e.g., one
bootstrap CI excludes zero but the other doesn't, and the magnitudes
straddle the 1σ/2σ boundaries).

**Recovery:** The §5 decision rule is deterministic by design.
Ambiguity should not occur if the rule is implemented correctly. If
the runner detects ambiguity, the implementation is wrong; abort and
fix the runner, not the SPEC.

---

## 11. Limitations (pre-registered)

- The followup cannot resolve general additivity questions across the
  broader Phase 4 candidate space (e.g., other ranking factors, other
  holding-period values). It addresses only the specific 2×2 cell that
  Working Hypothesis P5-4 concerns.
- The followup remains conditional on the locked snapshot and on the
  fixed-hold, paper-price NAV reconstruction methodology used in Phases
  3–5. It does not address execution realism, live slippage, or any
  out-of-sample question.
- The Low-Uplift bootstrap CI crossing zero (Phase 5 §8.3) applies
  equally to this followup. The sampling-error context in §4.5 is the
  primary noise-floor reference; the bootstrap is supplementary.
- The acceptance criteria thresholds (§5) are governance heuristics.
  A 2σ / 1σ rule is conventional but not statistically calibrated.

---

## 12. Governance

### 12.1 Document chain

| Document | Version | Status |
|---|---|---|
| `research/r8_phase5_configuration_report.md` | v1.0.2 | LOCKED |
| `research/r8_phase5_followup_001_spec.md` | v1.0.0 | **THIS DOCUMENT — LOCKED / EXECUTION SPEC** |
| `research/r8_phase6_spec.md` | v0.1.0 | LOCKED (owns this followup, §7) |
| `scripts/run_phase5_followup_001.py` | v0.1.0 | TO BE IMPLEMENTED |
| `research/r8_phase5_followup_001_report.md` | v1.0.0 | TO BE AUTHORED post-execution |

### 12.2 Immutable post-LOCK content

The following are immutable under v1.0.0 LOCK; modification requires
new SPEC version (v1.1.0+) with explicit rationale:

- §1 Purpose
- §2 Research question
- §3 Scope (in-scope / out-of-scope)
- §4 Methodology (including §4.1 L1/L2 snapshot convention, §4.5
  Lo (2002) governance noise-floor framing)
- §5 Acceptance criteria (PROMOTE / REJECT / INCONCLUSIVE rule and
  thresholds)
- §11 Limitations

### 12.3 Mutable execution detail

The following may receive minor version bumps (v1.0.x) for clarification
or error correction without invalidating pre-registration:

- §7 Runner CLI flag additions (if backward-compatible)
- §8 Artifact format clarifications (provided schema fields are not
  removed or repurposed)
- §9 Execution log additional entries (additive only)
- §10 Failure mode additions or clarifications

### 12.4 What this followup does not authorise

- Modification of Phase 5 v1.0.2 verdict under any outcome.
- Modification of ARM_B SELECTED / ARM_C reclassification under any
  outcome.
- Modification of Phase 6 SPEC v0.1.0 pre-registered design under any
  outcome.
- Promotion of Working Hypothesis P5-4 to finding without §5 PROMOTE
  verdict.
- Rejection of Working Hypothesis P5-4 without §5 REJECT verdict.
- Any production change.

---

*End of r8_phase5_followup_001_spec.md v1.0.0*
