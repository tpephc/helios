# Phase 6 — Step 2 Lineage Verification Closeout

**Date:** 2026-06-20
**Status:** COMPLETE
**Outcome:** Arm A LU + full_sample lineage fingerprints reproduce on
current snapshot within tolerance. R5 (Phase 6 wiring precondition v0.1.1)
fully validated end-to-end.
**Evidence artifact:**
[`research/r8_phase6/step2_lineage_verified_2026_06_20.json`](r8_phase6/step2_lineage_verified_2026_06_20.json)

---

## 1. Wiring chain

Step 2 commits (chronological, append-only after `v0.1.2` Step 1 baseline):

| Tag    | SHA       | Title                                                            | Status                                       |
|--------|-----------|------------------------------------------------------------------|----------------------------------------------|
| v0.1.2 | `78f8c3b` | Step 1 rename: snapshot identity → lineage semantics             | COMPLETE (no behaviour change)               |
| v0.1.3 | `b33bd19` | Step 2 wiring: ABI consumption + LineageStatus + provenance schema | CRASHED (ABI shape mismatch)               |
| v0.1.4 | `c177151` | Step 2 fix: NAV price loader shape + exception-path provenance   | PARTIAL (lineage VERIFIED, provenance write crashed) |
| v0.1.5 | `9121e2b` | Step 2 fix: NumPy → Python-native cast at provenance boundary    | COMPLETE (exit 0 + provenance artifact)      |

Governance commit chain leading into Step 2:
- Phase 5 closeout v1.0.2: `98315a6`
- Phase 6 SPEC v0.1.1: `0c016ec` (anchor: `edd42b1`)
- Phase 6 runner skeleton v0.1.1: `d692390`
- Wiring precondition v0.1.0: `11cc4a4`
- Wiring precondition v0.1.1: `2d0e34a`

---

## 2. Dry-run command (canonical Step 2 verification)

```bash
uv run python scripts/run_phase6_evaluation.py \
    --snapshot-id 2026-06-08 \
    --code-sha $(git rev-parse HEAD) \
    --bootstrap-seed 42 \
    --output-dir /tmp/phase6_dry_run \
    --dry-run
```

Final execution (against `9121e2b`):
- Exit code: 0
- Runtime: ~8 seconds (DuckDB load + 2 scenarios × full harness chain)
- Artifact: `/tmp/phase6_dry_run/provenance.json` (preserved in
  `research/r8_phase6/step2_lineage_verified_2026_06_20.json`)

---

## 3. Lineage fingerprint match (full table)

Tolerances (per `scripts.run_phase5_analysis`): `ARM_A_SHARPE_TOL = 0.050`,
`ARM_A_ADMISSION_TOL = 0.020`. Lineage gates use `sharpe + admission_rate`
only; `max_dd` recorded as informational diagnostic (Phase 5 lineage
practice).

### low_uplift scenario

| Metric         | Computed | Reference | Δ       | Tolerance         | Gate |
|----------------|----------|-----------|---------|-------------------|------|
| sharpe         | 1.569209 | 1.569     | 2.09e-4 | 0.050             | PASS |
| admission_rate | 0.1751   | 0.175     | 1.00e-4 | 0.020             | PASS |
| max_drawdown   | 0.205372 | 0.2054    | 2.80e-5 | (informational)   | n/a  |

### full_sample scenario

| Metric         | Computed | Reference | Δ       | Tolerance         | Gate |
|----------------|----------|-----------|---------|-------------------|------|
| sharpe         | 2.49805  | 2.498     | 5.00e-5 | 0.050             | PASS |
| admission_rate | 0.16     | 0.163     | 3.00e-3 | 0.020             | PASS |
| max_drawdown   | 0.216498 | 0.2165    | 2.00e-6 | (informational)   | n/a  |

### Observations on match quality

- Sharpe Δ on both scenarios is 10⁻⁵ to 10⁻⁴ order — three to four
  orders of magnitude below the 0.050 tolerance ceiling. Strongly
  supports lineage equivalence (current snapshot ≡ Phase 5 L1
  reference snapshot for Arm A purposes).
- `full_sample` admission Δ = 3.00e-3 is the largest divergence
  recorded but remains 6.7× below the 0.020 tolerance. Likely
  source: rounding precision in `schedule_positions`'
  `admission_rate = round(len(scheduled) / max(n_cand, 1), 4)`
  combined with reference value rounded to 3 decimals.
- `max_drawdown` Δ at 10⁻⁵ ~ 10⁻⁶ — sub-bp precision. Not used
  for gating but corroborates the Sharpe-match story.

---

## 4. Lessons learned (recorded for Step 3 wiring discipline)

### L-1 — Signature confirmed ≠ ABI confirmed

**Symptom:** v0.1.3 lineage code crashed with
`KeyError('stock_id')` inside `reconstruct_nav_for_horizon` after
`schedule_positions` succeeded. Step 2A "ABI discovery" phase had
confirmed the signature
`reconstruct_nav_for_horizon(scheduled, price_df, cap, h)` and
return schema `{date, nav, daily_log_return}` but did not inspect
the function body to verify what shape `price_df` was expected to
have, nor look at Phase 5's caller pattern to see how `price_df`
was prepared.

**Reality:** Helios has two distinct price loaders with different
DataFrame shapes:

| Loader                                   | Source         | Shape                                    | Consumer                          |
|------------------------------------------|----------------|------------------------------------------|-----------------------------------|
| `load_price_series(con)`                 | Phase 1 a3     | MultiIndex `(stock_id, date)` + cols     | `build_signal_ledger_for_horizon` |
| `load_daily_price_paths(con, scheduled)` | Phase 3        | Columnar `[stock_id, date, …]`           | `reconstruct_nav_for_horizon`     |

The two are NOT interchangeable. Phase 5 caller pattern at
`scripts/run_phase5_analysis.py:745` uses `load_daily_price_paths`
between `schedule_positions` and `reconstruct_nav_for_horizon`.
Step 2 v0.1.3 missed this distinction.

**Discipline going forward (Step 3 and beyond):**

> ABI confirmation = signature + body access pattern + caller usage
> pattern. All three. Signature alone is insufficient.

Concretely, Step 3 ABI discovery phase must include for each
imported function:

1. `inspect.signature(fn)` — parameter names + types
2. `inspect.getsource(fn)` body grep for `["…"]` / `.loc[]` /
   `.groupby(…)` / `.set_index(…)` / `.reset_index(…)` patterns to
   determine column-vs-index expectations and side effects
3. Grep the parent module (Phase N) for callers — what shape do
   they prepare for this function?

### L-2 — Provenance must normalise NumPy scalars at the boundary

**Symptom:** v0.1.4 lineage verification succeeded (logs showed
`L1 lineage VERIFIED`), but `emit_provenance` crashed with
`TypeError: Cannot serialise bool` because `LineageStatus.results`
contained `numpy.bool_` (from `sharpe_delta <= ARM_A_SHARPE_TOL`
where `sharpe_delta` was `numpy.float64`) and `numpy.float64` (from
`compute_risk_metrics`' `_f()` helper which preserves numpy type
through `round(np.float64, 6)`).

**Reality:** Governance artifacts (LineageStatus, future
CandidateMetrics, GateResult, bootstrap results) consumed by
`emit_provenance` and by future readers of `provenance.json` must
be expressed in Python-native types (`float`, `bool`, `int`, `str`,
`None`). NumPy implementation types must not leak through to
governance artifacts.

**Discipline going forward (Step 3 and beyond):**

> Cast at the data construction site (primary). All dataclass
> fields of governance artifacts are explicitly cast to Python
> natives at the point of dataclass construction. Use
> `_py_float(value)` / `_py_bool(value)` helpers (added in v0.1.5)
> or extend with `_py_int(value)` as needed.

> Defensive serializer (boundary). `_json_default` handles
> `np.generic` (via `.item()`), `np.ndarray` (via `.tolist()`),
> and normalises NaN → None / ±Infinity → string tokens. This is
> a safety net for missed casts at construction sites; it should
> never be the primary defence.

### L-3 — Heredoc placeholder trap (process)

**Symptom:** Commit `63b06cb` and amend `f7cac32` both carried
literal placeholder text as their commit message
(`"(use the v0.1.2 commit message from earlier)"` and
`"(use the corrected message above)"`) due to `git commit
--amend -F-` heredoc containing instruction-paste boilerplate
that was treated as message content. Audit-grep mechanism
silently broken (no substantive keyword matched the commit).

Remediated via final amend at `78f8c3b` (one-time force-push
exception, documented in commit body).

**Discipline going forward (any commit ≥ 5 lines):**

> File-based commit message delivery only. Never use heredoc with
> `git commit -F- <<EOF ... EOF` for messages ≥ 5 lines. Always
> save the full message to a file (e.g. via `cat > ... << EOF`
> with verified content, or by downloading from the artifact
> source), then `git commit -F <file>`. Subject paranoid check
> (`git log -1 --pretty=%s`) BEFORE `git push`.

### L-4 — Hyphenated multi-word audit-grep keywords risk line-wrap break

**Symptom:** Commit `78f8c3b` audit-grep for
`"force-push-with-lease"` missed because the term was line-broken
in the commit body as `"force-push-` / `"with-lease)"`. Substitute
keywords (`"force-push"`, `"with-lease"`, `"audit-grep mechanism"`)
all hit; the 4-word hyphenated form did not.

**Discipline going forward:**

> Audit-grep keywords designed for commit messages: ≤4 short words,
> single-line guarantee, prefer space-separated phrases over
> hyphenated compounds for grep targets. Hyphenated terms remain
> fine in prose but should not be the *intended* grep target.

---

## 5. Risk activation status (per `r8_phase6_wiring_precondition.md` v0.1.1)

| Risk | Topic                                          | Status              | Notes                                                                                                       |
|------|------------------------------------------------|---------------------|-------------------------------------------------------------------------------------------------------------|
| R1   | Slot timing (ARM_B same-day vs E1-E4 t+1)      | NOT YET BINDING     | Step 3 challenger evaluation territory; activates when `adaptive_release_engine` lands.                     |
| R2   | Feature lookahead in adaptive exits            | NOT YET BINDING     | Step 3; depends on E1-E4 feature consumption via `bullish_features` columns at `T`-vs-`T-1` boundary.       |
| R3   | Frozen signal pool ≠ frozen admission schedule | NOT YET BINDING     | Step 3 `evaluate_candidate` wiring; will activate when admission regeneration is invoked.                   |
| R5   | L1 lineage equivalence via Arm A fingerprint   | **FULLY ACTIVE — VALIDATED** | Step 2 complete. Lineage check operational and reproduces Phase 5 Arm A reference within tolerance.        |
| R6   | Persistence-first hierarchy                    | ACTIVE              | Step 2 reused canonical Phase 1/3/4/5 harness functions; no Phase 6 re-derivation. `ARM_A_REFERENCE`, `BASELINE_CAP`, `BASELINE_MAX_POS` imported from Phase 4/5. |
| WG-1 | Degenerate equivalence test for adaptive simulator | NOT YET BINDING | Step 3 wiring gate; required before E1-E4 evaluation. Bit-identical equivalence of structurally-reused simulator code vs canonical Phase 5 functions when adaptive features are degenerate. |

---

## 6. Step 3 entry preconditions

Per precondition v0.1.1 §2 Step 3, Step 3 wiring may proceed when:

- ☑ Step 2 lineage check produces `verified=true` on current snapshot
  (this document is the evidence)
- ☑ Provenance.json schema (`lineage_check` block) stabilised
- ☑ Phase 1/3/4/5 harness ABI consumption pattern established
- ☐ Phase 5 ARM_B / ARM_C reference values available for Step 3 Gate
  G2 comparisons (already in `r8_phase5_configuration_report.md`
  v1.0.1; needs explicit import path verification when Step 3
  wiring begins)
- ☐ E1-E4 adaptive exit policy decision functions implemented and
  unit-tested
- ☐ `adaptive_release_engine` (Step 3 new code) implemented with
  WG-1 degenerate equivalence test passing
- ☐ `bootstrap_delta_sharpe` (Lo 2002 stationary block bootstrap)
  implemented per SPEC §5.4

Step 3 ABI discovery phase will be the first action under the new
"signature + body + caller pattern" discipline established by L-1
above.

---

## 7. Cross-references

- SPEC: `research/r8_phase6_spec.md` v0.1.1
- Wiring precondition: `research/r8_phase6_wiring_precondition.md` v0.1.1
- Phase 5 closeout: `research/r8_phase5_configuration_report.md` v1.0.1
- Phase 5 lineage origin: `research/r8_phase5_price_snapshot_refresh_note.md`
- Provenance artifact: `research/r8_phase6/step2_lineage_verified_2026_06_20.json`
- Final runner commit: `9121e2b`

---

*Closeout authored 2026-06-20 immediately following successful
Step 2 dry-run. No SPEC or precondition amendments resulted from
Step 2; lessons learned recorded for Step 3 discipline.*
