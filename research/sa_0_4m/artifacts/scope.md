# SA-0.4M — Methodology Stabilization Walk-Forward

**Phase:** B
**Date:** 2026-05-26
**Status:** pre-registration (scope freeze — commit before any runner code)
**Artifact root:** `research/sa_0_4m/artifacts/`

---

## 1. Upstream References (Pinned)

All downstream citations in this document refer to the following
upstream sources. Commit hashes must be filled in at time of commit.

| Source | Section | Commit SHA |
|---|---|---|
| `handoff_governance_review_2026-05-20.md` | §2 (closeout framing) | `<fill at commit>` |
| `phase_a_dg0_handoff_2026-05-20.md` | §6.1 (internally-consistent findings) | `<fill at commit>` |
| `phase_a_dg0_handoff_2026-05-20.md` | §7 (binding constraints) | `<fill at commit>` |
| `docs/findings/hmm_3state_semantic_instability.md` | full (HMM-001 filing) | `<fill at commit>` |

**Note on stale wording in `phase_a_dg0_handoff_2026-05-20.md` §2:**
That section contains wording that has been superseded by governance
review §2 and Phase A handoff §6:

- "BCa CI entirely negative" → percentile CI (BCa not applicable at
  n_segments ≈ 10–15; see §7 binding constraints)
- "session bootstrap" → block bootstrap at segment_id level
- rv co-firing pathway described as structural → refuted by DG-0.2
  (lift < 1.0; see §6.1)

SA-0.4M inherits the superseded versions via §6.1 and governance
review §2. Direct citation of Phase A handoff §2 is avoided.

---

## 2. Scope

### What this run does

Validate walk-forward methodology infrastructure using the **legacy
pre-SA-1 3-state Gaussian HMM** and the **legacy feature vector
(including `depth_pctile`)**.

### What this run is

- Walk-forward orchestration validation
- Embargo handling validation
- Leakage controls verification
- Artifact reproducibility testing
- Threshold drift and label stability telemetry collection
- EM instability surface characterisation under real WF fold structure

### Primary value statement

SA-0.4M primary value is **telemetry generation under a known-unstable
legacy setup**, not successful model validation. The deliverable is:

- instability shape across WF folds
- fold fragility under small-sample EM
- EM behaviour across seed and covariance type
- per-fold diagnostic telemetry surface

`UNDERPOWERED` is not a failure of SA-0.4M. It is a valid and
informative methodology finding. The only true failure mode is an
outcome that cannot be classified as `PASS`, `UNDERPOWERED`, or
`FAIL` (e.g. runner crash, missing diagnostics, non-reproducible
artifacts).

### What this run is NOT (binding interpretation constraints)

```
NOT: a baseline for inter-feature-vector performance comparison.
     SA-0.4M uses depth_pctile, which SA-1 pre-registration removes.
     Any "SA-1 vs SA-0.4M performance delta" is confounded by:
       - feature vector change
       - model state geometry change
       - label semantic change
       - distribution shift
       - EM behaviour change
     It is not a controlled comparison. Cross-artifact numeric deltas
     may not be cited as evidence for or against SA-1 quality.

NOT: evidence of HMM label stability across regime shifts.
     10 trading days is within a single macro/volatility regime by
     construction. Label stability in SA-0.4M = label stability
     within one regime, not regime-generalised stability.

NOT: a calibration source for thresholds, cost buckets, or sizing.
     Any numeric output (threshold values, transition matrix entries,
     state occupancy fractions, emission parameters) is
     methodology-validation telemetry, not a tunable parameter for
     downstream stages.
```

---

## 3. Status Transition from Phase A

```
Phase A SA-0.4:  SKIP
                 Reason: insufficient data (5 days only)
                 Original intent: stability audit on legacy stack

Phase B SA-0.4M: methodology_stabilization run
                 Precondition: >= 10 clean trading days
                 Setup: legacy stack (3-state HMM, legacy feature vector)
```

Phase B SA-0.4M is **not a re-attempt** of the Phase A SA-0.4 that
was skipped. They have different audit targets:

| Artifact | Audit target |
|---|---|
| Phase A SA-0.4 (skipped) | model robustness on legacy stack |
| Phase B SA-0.4M (this run) | methodology infrastructure validity |

The robustness audit function is deferred to SA-0.4R (post-SA-1,
after SA-0.5 PASS). See §9 for naming conventions.

---

## 4. Embargo Specification

**Embargo unit:** 1 full trading session (08:45–13:45 CST day session).

**Rationale:** Avoids cross-session leakage via overnight gap pricing,
opening auction effects, and end-of-day inventory unwind behaviour.

**Epistemic status:** heuristic, not measured.

There is currently no TMFE-specific ACF decay audit, no inventory
unwind half-life estimate, and no opening auction contamination
estimate. The 1-session embargo is a conservative operational prior,
not an empirically estimated decorrelation horizon.

**Falsification trigger:** If a future SA-1 ACF audit shows that
microstructure autocorrelation in TMFE decays in substantially less
than 1 session, the embargo specification may be revised. Any
revision requires an NE-equivalent sensitivity test and cannot be
treated as a free parameter adjustment.

**Embargo selection freeze:**
The embargo value (1 session) is frozen for the duration of SA-0.4M.
It may not be changed after runner implementation begins.

**Robustness telemetry (report, do NOT gate on):**

Run the same WF configuration with embargo = {0, 1, 2} sessions and
report results for all three. Purpose: quantify methodology sensitivity
to embargo choice.

If results vary meaningfully across {0, 1, 2}, this is a finding about
small-sample WF fragility, not a basis for selecting an embargo value.

**Anti-reinterpretation rule:**
Sensitivity telemetry may not be used to retroactively modify fold
disposition or overall SA-0.4M interpretation. Primary interpretation
is bound to embargo = 1 session. Citing embargo = 0 or embargo = 2
results to soften or strengthen the primary conclusion is prohibited.

---

## 5. Walk-Forward Design

**Rolling WF specification (pre-registered):**

```
train:   4 clean sessions
embargo: 1 full session  (frozen; see §4)
test:    1 clean session
```

**Clean session definition:**

- No gap contamination (DQ-001 exclusion rules apply)
- Recorder stability verified at session level
- Minimum tick + bidask coverage > 95% of session duration

**Session boundary:** trading session (08:45–13:45 CST), not
wall-clock calendar day.

---

## 6. Per-Fold Mandatory Diagnostics

The following diagnostics **must** be computed and recorded for every
fold. If any diagnostic trips, the fold is marked `methodology_unstable`.
`methodology_unstable` is not pass or fail — it means the fold cannot
support the intended inference.

### 6.1 Diagnostic table

| Diagnostic | Trip condition | Disposition |
|---|---|---|
| EM log-likelihood convergence | `monitor_.converged == False` OR `final log-lik change > 10 * tol` | `methodology_unstable` |
| Covariance condition number | any state: `cond > 1e6` | `methodology_unstable` |
| State occupancy fraction | any state: occupancy < 5% | `methodology_unstable` |
| EM init sensitivity | log-lik dispersion across seeds `> 0.1 * (max - min)` | `methodology_unstable` |
| Forward-backward numerical stability | any NaN or Inf in gamma matrix | `methodology_unstable` |

EM hyperparameters: `max_iter=500`, `tol=1e-4`.

### 6.2 EM init sensitivity detail

Run each fold with seeds `[0, 1, 13, 42, 123]`.

Rationale for seed selection:
- `{0, 1, 13}`: reproduce HMM-001 basin bifurcation (SA-0.1 finding:
  these seeds converge to Basin B, overall ≈ 0.446). Presence in WF
  folds tests whether the basin structure persists under rolling train
  windows.
- `{42, 123}`: sample initialisation space not covered by HMM-001.

For each fold, record per seed: log-likelihood, convergence flag,
Hungarian-matched state-label agreement against seed=0 reference.

Log-lik dispersion trip: `max(log_lik) - min(log_lik) > 0.1 * abs(mean(log_lik))`.

### 6.3 Covariance secondary telemetry (report, do not gate)

In addition to the primary trip at cond > 1e6:

- Count of states per fold with condition number in `[1e4, 1e6]`
  (borderline degradation zone)
- Maximum condition number observed across all states and all folds

Purpose: characterise the distribution of covariance health before
deciding whether to tighten the primary threshold in SA-0.4R.

### 6.4 Fold disposition rule

```
Any diagnostic trips → fold = methodology_unstable

>= 2 / N folds = methodology_unstable →
    SA-0.4M overall = UNDERPOWERED
    ResultStatus.underpowered = True

All folds pass all diagnostics →
    SA-0.4M overall = PASS (methodology infrastructure validated)

Systematic failure pattern in diagnostics →
    SA-0.4M overall = FAIL (infra defect identified)
```

`UNDERPOWERED` is an expected and valid outcome given n_train = 4
sessions and known EM multimodality (HMM-001). It should be reported
as a methodology finding, not treated as an error state.

---

## 7. What SA-0.4M Unlocks / Does Not Unlock

### Unlocks (after SA-0.4M commit with PASS or UNDERPOWERED)

- SA-1 implementation start (methodology infrastructure verified or
  instability surface characterised)
- SA-0.5 (2-state HMM robustness audit) start

### Does NOT unlock

```
NOT: direct numerical comparison of SA-0.4M vs SA-1 outputs
     (different feature vectors — confounded; see §2 binding constraints)

NOT: threshold, cost, or sizing calibration

NOT: execution policy design (EP-0A / EP-0B remain blocked pending
     Entry Contract §X.1 and SA-0 PASS on redesigned stack)

NOT: any production-alpha claim

NOT: macro overlay → HMM prior injection
     (still blocked on SA-0.5 PASS + SA-2 pre-registration)
```

---

## 8. Governance Freeze Status

Freeze rule established in governance review §1.4. Three triggers
required for full lift:

| Trigger | Status after SA-0.4M commit |
|---|---|
| (a) SA-0.4M committed | ✓ satisfied |
| (b) 10 trading days validated tick+book data | pending |
| (c) SA-1 first feature OR CR-0 pilot committed | pending |

**Partial lift (after SA-0.4M commit):**
New governance artifacts are permitted only if directly required by
SA-0.4M findings (e.g. SA-0.4M surfaces a failure mode not covered
by existing ResultStatus presets → extension allowed).

**Full lift:** when 2 of 3 triggers are satisfied.

The governance freeze principle remains in effect: governance
complexity must scale slower than research uncertainty. SA-0.4M
commit does not license new governance layer additions beyond what
its findings require.

---

## 9. Naming Conventions

```
SA-0.4   = Phase A original design
           Status: permanent SKIP
           Reason: legacy feature vector (including depth_pctile)
           ceases to exist after SA-1. The audit this name referred
           to cannot be run on the post-SA-1 stack.

SA-0.4M  = Phase B methodology stabilization run (this artifact)
           Setup: legacy stack, legacy feature vector
           Audit target: methodology infrastructure

SA-0.4R  = post-SA-1 robustness rerun (future artifact)
           Precondition: SA-0.5 PASS + SA-1 implementation complete
           Setup: post-SA-1 stack, new feature vector
           Audit target: model robustness on redesigned stack
           Scope: not yet pre-registered
```

The name `SA-0.4` is retired and must not be reused. `SA-0.4R` scope
must be pre-registered independently before implementation.

---

## 10. Artifact Outputs

| Path | Content |
|---|---|
| `research/sa_0_4m/artifacts/manifest.json` | Run metadata: git hash, timestamp, WF config, session list, seed list |
| `research/sa_0_4m/artifacts/per_fold_diagnostics.parquet` | Per-fold disposition flags and all diagnostic values |
| `research/sa_0_4m/artifacts/em_init_sensitivity.parquet` | Per-fold, per-seed: log_lik, converged, hungarian_agreement |
| `research/sa_0_4m/artifacts/embargo_sensitivity_0.parquet` | WF run with embargo = 0 sessions (descriptive telemetry only) |
| `research/sa_0_4m/artifacts/embargo_sensitivity_1.parquet` | WF run with embargo = 1 session (primary) |
| `research/sa_0_4m/artifacts/embargo_sensitivity_2.parquet` | WF run with embargo = 2 sessions (descriptive telemetry only) |
| `data/audits/SA-0/sa_0_4m_summary.md` | Human-readable summary; links to artifacts above |

All artifacts must be reproducible from `manifest.json` parameters
and pinned git state. Non-reproducible artifacts are a `FAIL`
outcome regardless of diagnostic results.

---

## 11. Interpretation and Unlock Constraints

See §7 for binding unlock allowlist and prohibited interpretations.

---

## 12. Commit Ordering (Binding)

```
1. Commit this scope.md BEFORE writing any runner code.
   Pre-registration credibility requires scope to precede implementation.

2. Commit runner implementation (research/sa_0_4m/walkforward_runner.py
   and supporting modules).

3. Commit artifacts after run completes
   (research/sa_0_4m/artifacts/, data/audits/SA-0/sa_0_4m_summary.md).
```

Any deviation from this ordering must be noted in the commit message
with explicit justification.

---

## 13. Suggested Commit Message

```
research(sa-0.4m): pre-register methodology stabilization walk-forward

Add SA-0.4M scope pre-registration for Phase B rolling walk-forward
methodology validation using the legacy pre-SA-1 3-state Gaussian HMM
and legacy feature vector (including depth_pctile).

Scope is limited to methodology stabilization: walk-forward
orchestration, one-session embargo handling, artifact reproducibility,
leakage controls, threshold drift, label stability, and EM instability
surface characterisation.

Primary value is telemetry generation under a known-unstable legacy
setup, not successful model validation. UNDERPOWERED is a valid and
informative outcome.

This artifact uses the pre-SA-1 feature vector and is not directly
comparable to SA-1 outputs. Any cross-artifact performance delta is
confounded by feature vector change, state geometry change, and label
semantic change.

This is not production alpha validation and does not claim deployable
edge or regime-generalised robustness.

Naming:
  SA-0.4M = this methodology run (Phase B, legacy stack)
  SA-0.4R = future post-SA-1 robustness rerun (not yet pre-registered)
  SA-0.4  = retired (permanent SKIP; legacy feature vector obsolete)

Upstream references pinned to:
  governance_review_handoff §2, phase_a_handoff §6.1 and §7, HMM-001
```
