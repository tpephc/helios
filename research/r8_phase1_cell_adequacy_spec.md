# R8 Phase 1 — P0-B Cell Adequacy Audit Specification

<!-- research/r8_phase1_cell_adequacy_spec.md -->
<!-- v0.1.1 — 2026-06-06 -->

**Status:** LOCKED — v0.1.1
**Lock date:** 2026-06-06
**Supersedes:** v0.1.0 (LOCKED 2026-06-06)
**Inherits from:**
- `research/r8_phase1_lifecycle_spec.md` v0.1.2
- `research/adr/ADR-R8P1-001-block-bootstrap-effective-n.md` v0.1.0
- `research/adr/ADR-R8P1-002-baseline-benchmark-construction.md` v0.1.0

**Authorises:** Production of four adequacy output tables
(D-1, D-2, D-2A, D-2B) and their downstream interpretive use by
Phase 1 outputs.

---

## Changelog from v0.1.0

| Change | Section | Description |
|---|---|---|
| ADDED | §Outputs › D-2B | Baseline-side adequacy audit covering `Baseline_1` and `Baseline_2` as defined by ADR-R8P1-002. Single-table design with `baseline_universe` dimension. |
| MODIFIED | §Outputs › D-2 schema | Retrofit `must_propagate_reason` field for machine-readable propagation rationale. |
| MODIFIED | §Outputs › D-2A schema | Retrofit `must_propagate_reason` field. |
| MODIFIED | §Acceptance Criteria › AAC-1 | "Three output tables" → "Four output tables". |
| MODIFIED | §Acceptance Criteria › AAC-5 | `must_propagate` clause extended to `must_propagate_reason`. |
| MODIFIED | §Implementation Invariants › #8 | Output location list extended with `d2b_baseline_adequacy.parquet`. |
| MODIFIED | §Out of Scope | A-1/A-2 baseline universe construction removed from Out of Scope (now defined upstream by ADR-R8P1-002 and audited downstream by D-2B). |
| MODIFIED | §Amendment Procedure | Rationale list expanded to include any locked Phase 1 methodology ADR. |
| MODIFIED | §Relationship to Pending Work | ADR-R8P1-002 status updated from "NOT YET DRAFTED" to "LOCKED v0.1.0". |
| UNCHANGED | §Outputs › D-1 | D-1 retains Phase 0 inheritance diagnostic scope; not extended to baseline universe. |
| UNCHANGED | §Gate Definition | Locked thresholds (PASS ≥ 100, DIRECTIONAL 30–99, INSUFFICIENT < 30) apply uniformly to D-2, D-2A, D-2B. |

D-1, D-2 (existing dimensions), and D-2A (existing dimensions) are
not restructured. Their classification logic and gate thresholds
are unchanged.

---

## Status

P0-B SPEC v0.1.1 drafted 2026-06-06. Lock pending review.

This document is the governance contract for the R8 Phase 1 cell
adequacy audit. It is upstream of any Phase 1 inferential output
(A-1 through A-6) that relies on stratified cell interpretation,
including any inferential output that consumes a baseline universe
defined by ADR-R8P1-002.

Amendments require a new versioned SPEC; silent edits are prohibited
per the inherited SPEC §7 discipline.

---

## Purpose

P0-B answers exactly one question:

> **Can Phase 1 cells be interpreted?**

It does NOT answer:

- What are the Phase 1 findings?
- Does R8 outperform RS_T3?
- Is R8 alpha-bearing?
- What is the mean forward return of any cell?

P0-B produces structural diagnostics on the event panel (treatment
side, D-2A) and the baseline universes (baseline side, D-2B) only.
No forward-return computation, no inferential statement, and no
benchmark comparison is in scope. Any output of P0-B that resembles
a research finding is a governance violation.

---

## Scope

P0-B covers:

1. **D-1**: R8 × RS_tertile contingency table — selection-overlap
   sanity check on the IF-1-remediated panel. Diagnostic only;
   Phase 0 settled selection-level overlap.
2. **D-2**: `regime × near_limit_up × R8` cell adequacy audit —
   answers whether the SPEC-mandated stratifications (AC-3, AC-4)
   have sufficient date support across the global R8 event panel.
3. **D-2A**: A-3 treatment support audit — `regime × near_limit_up`
   cell adequacy restricted to `R8 ∩ RS_T3` (the A-3 treatment
   universe). Answers whether the primary research question is
   interpretable in stratified form on the treatment side.
4. **D-2B** (added in v0.1.1): Baseline-side adequacy audit —
   `baseline_universe × regime × near_limit_up` cell adequacy over
   `Baseline_1` and `Baseline_2` as defined by ADR-R8P1-002.
   Answers whether the baselines used by A-1, A-2, A-3 have
   sufficient date support after symmetric stratification under SD-1.
5. **Gate classification**: each cell in D-2, D-2A, and D-2B
   receives a classification per the locked thresholds in §Gate
   Definition. D-1 remains diagnostic-only without gate.
6. **Manifest**: audit-version, panel snapshot hash, regime labels
   verbatim from the production regime model, threshold values,
   query SQL, reproducibility metadata, and the locked ADR-R8P1-002
   universe definitions actually used to produce D-2B.

---

## Out of Scope

The following are explicitly excluded. Inclusion of any item below
constitutes a governance violation regardless of analytical interest:

- Forward-return computation at any horizon.
- Bootstrap inference, standard errors, confidence intervals.
- Industry-code breakdown beyond what Phase 0 established
  (~78% electronics).
- MA5 observational metrics (lifecycle telemetry — out of P0-B scope).
- Effective-n estimation (ADR-R8P1-001 method, but for inferential
  outputs — not for adequacy classification).
- Any provisional / non-provisional label change. Findings remain
  PROVISIONAL per SPEC AC-6.

**Removed from Out of Scope in v0.1.1:** A-1 / A-2 baseline universe
construction. ADR-R8P1-002 v0.1.0 now defines these universes;
adequacy of their cells is audited by D-2B (new in v0.1.1).

---

## Outputs

### D-1: R8 × RS_tertile contingency

**(Unchanged from v0.1.0.)**

**Purpose:** Selection-overlap sanity check on IF-1-remediated panel.

**Audited panel scope:** The full `daily_features` panel
(IF-1-remediated, post-listing rows only, via
`listed_market_daily_price_adj`), where `r8_flag` is defined for
every `(date, stock)` observation: `r8_flag = 1` iff the row meets
the R8 signal definition (`daily_return >= +5% AND close > open`),
else `r8_flag = 0`. D-1's panel is strictly broader than D-2 / D-2A /
D-2B's panels; this is intentional because selection overlap
requires both the R8 and non-R8 sides.

**Schema:**

| Column | Type | Definition |
|---|---|---|
| `rs_tertile` | string | `RS_T1` / `RS_T2` / `RS_T3` (per LA-4) |
| `r8_flag` | int | 0 or 1 |
| `n_observations` | int | observation count |
| `n_unique_dates` | int | distinct trading dates with ≥1 observation in cell |

**Classification:** None applied. D-1 is Diagnostic.

---

### D-2: Global stratification adequacy audit

**(v0.1.0 dimensions unchanged; `must_propagate_reason` field added.)**

**Purpose:** Answer whether the SPEC-mandated stratifications (AC-3,
AC-4) have sufficient date support across the global R8 event panel.

**Audited panel scope:** R8 event panel.

**Schema:**

| Column | Type | Definition |
|---|---|---|
| `regime` | string | `regime[T-1]` label, verbatim from production regime model |
| `near_limit_up` | int | 0 or 1; 1 iff signal-day close ≥ +9.5% relative to previous close |
| `n_events` | int | event count in cell |
| `n_unique_dates` | int | distinct trading dates with ≥1 event in cell |
| `events_per_date_mean` | float | clustering severity indicator (advisory) |
| `events_per_date_p95` | int | per-date concentration tail (advisory) |
| `classification` | string | `PASS` / `DIRECTIONAL_ONLY` / `INSUFFICIENT` |
| `must_propagate` | bool | `true` iff `classification ∈ {DIRECTIONAL_ONLY, INSUFFICIENT}` |
| `must_propagate_reason` | string \| NULL | Machine-readable reason for `must_propagate = true`; NULL when `must_propagate = false`. See §Reason Encoding. |

**Cell space:** `n_regimes × 2 (near_limit_up)`.

Dimension discipline (locked in v0.1.0): P0-B does not include
dimensions with no empirical variation inside the audited panel.

---

### D-2A: A-3 treatment support audit

**(v0.1.0 dimensions unchanged; `must_propagate_reason` field added.)**

**Purpose:** Answer whether the A-3 treatment universe
(`R8 ∩ RS_T3`) is interpretable when stratified by `regime[T-1]` and
`near_limit_up` jointly.

**Audited panel scope:** R8 ∩ RS_T3 event panel.

**Schema:**

| Column | Type | Definition |
|---|---|---|
| `regime` | string | `regime[T-1]` label, verbatim |
| `near_limit_up` | int | 0 or 1 |
| `n_events` | int | event count where `rs_tertile_T-1 = RS_T3` |
| `n_unique_dates` | int | distinct trading dates with ≥1 such event |
| `events_per_date_mean` | float | clustering indicator (advisory) |
| `events_per_date_p95` | int | per-date concentration tail (advisory) |
| `classification` | string | `PASS` / `DIRECTIONAL_ONLY` / `INSUFFICIENT` |
| `must_propagate` | bool | propagation flag |
| `must_propagate_reason` | string \| NULL | Machine-readable reason; see §Reason Encoding. |

**Cell space:** `n_regimes × 2 (near_limit_up)`.

`within_RS_T3` is not a dimension; D-2A's audited panel is
`R8 ∩ RS_T3` by scope.

---

### D-2B: Baseline-side adequacy audit (new in v0.1.1)

**Purpose:** Answer whether the baseline universes defined by
ADR-R8P1-002 (`Baseline_1` for A-1 / A-3, `Baseline_2` for A-2)
have sufficient date support after symmetric stratification under
SD-1 (ADR-R8P1-002).

**Audited panel scope:** The union of `Baseline_1` and `Baseline_2`
universes, as defined in ADR-R8P1-002 §Operational Universe
Definitions:

    Baseline_1 = { (d, s) : d ∈ D_R8, s ∈ RS_T3(d), (d, s) ∉ R8_events }
    Baseline_2 = { (d, s) ∈ Baseline_1 : dist_above_ma20_atr[d, s] < 0 }

Rows of each universe are tagged with `baseline_universe` and
audited side by side.

**Schema:**

| Column | Type | Definition |
|---|---|---|
| `baseline_universe` | string | `"Baseline_1"` or `"Baseline_2"` |
| `regime` | string | `regime[d-1]` label, verbatim (market-level per ADR-R8P1-002 D4; inherited from anchor date `d`) |
| `near_limit_up` | int | 0 or 1; 1 iff `close[d, s] / close[d-1, s] - 1 >= 0.095` evaluated on the baseline row's own price data (SD-1 β symmetric stratification) |
| `n_observations` | int | observation count in cell; one row per `(d, s) ∈ Baseline_k` matching `regime` and `near_limit_up` |
| `n_unique_dates` | int | distinct trading dates `d` with ≥1 observation in cell. Note: `n_unique_dates ≤ |D_R8|` by construction (baseline dates are a subset of R8 event dates). |
| `events_per_date_mean` | float | `n_observations / n_unique_dates`; clustering severity indicator (advisory) |
| `events_per_date_p95` | int | per-date concentration tail (advisory) |
| `classification` | string | `PASS` / `DIRECTIONAL_ONLY` / `INSUFFICIENT` per §Gate Definition (same thresholds as D-2 / D-2A) |
| `must_propagate` | bool | `true` iff `classification ∈ {DIRECTIONAL_ONLY, INSUFFICIENT}` |
| `must_propagate_reason` | string \| NULL | Machine-readable reason; NULL when `must_propagate = false`. See §Reason Encoding. |

**Cell space:** `2 (baseline_universe) × n_regimes × 2 (near_limit_up)`.

**Dimension discipline check:** `baseline_universe` is a valid
dimension because the audited panel is the **union** of `Baseline_1`
and `Baseline_2`, and `baseline_universe` varies empirically over
this union. This is distinct from a tautological dimension (where
the value is constant on the audited panel).

**Downstream consumption rule:**

- A-1 reads cells with `baseline_universe = "Baseline_1"`.
- A-2 reads cells with `baseline_universe = "Baseline_2"`.
- A-3 reads cells with `baseline_universe = "Baseline_1"`
  (per ADR-R8P1-002 §Operational Universe Definitions: `Baseline_3 = Baseline_1`).

Downstream artefacts inherit `classification` and
`must_propagate_reason` for the cell(s) they consume; failure to
inherit is a downstream governance violation (per v0.1.0 AAC-5
ownership boundary, unchanged in v0.1.1).

**Joint-pair adequacy:**

A-1, A-2, A-3 are difference statistics across treatment and
baseline. For inference on a stratified cell `(regime, near_limit_up)`,
**both** the treatment-side cell (D-2A) and the baseline-side cell
(D-2B) must classify as `PASS`; the weaker of the two governs the
joint classification used by downstream inferential output.

This joint rule is the responsibility of the downstream artefact
(A-1 / A-2 / A-3 owns the joint classification logic); P0-B emits
the two single-side classifications and the propagation metadata,
not the joint product.

**The weaker-of-two rule is deterministic and must not be persisted
as an additional audit artefact.** Any future proposal to materialise
a joint-pair output (e.g. `d2c_joint_pair.parquet`) is a P0-B scope
expansion requiring a versioned spec amendment, not a caching
optimisation.

---

## Reason Encoding (new in v0.1.1)

The `must_propagate_reason` field is a string with locked allowed
values to preserve machine-readability:

| Value | Meaning |
|---|---|
| `"n_unique_dates<30"` | `classification = INSUFFICIENT`; below INSUFFICIENT threshold |
| `"30<=n_unique_dates<100"` | `classification = DIRECTIONAL_ONLY`; below PASS threshold |
| `NULL` | `must_propagate = false`; no caveat propagation required |

Future amendments may add reasons (e.g. for joint multi-criterion
gates); when added, values must remain machine-parsable string
literals, not free text. Free-text reasons are prohibited at this
audit layer.

The encoding above is exhaustive for v0.1.1 gate definitions; if
a v0.1.2 amendment introduces additional gate criteria (e.g.
`events_per_date_mean` is promoted from advisory to gate), the
reason vocabulary must be extended in the same amendment.

---

## Gate Definition

**(Unchanged from v0.1.0; applies uniformly to D-2, D-2A, D-2B.)**

**Primary gate**: `n_unique_dates`.

**Locked thresholds (governance choice, NOT statistically derived):**

| Classification | Condition |
|---|---|
| `PASS` | `n_unique_dates ≥ 100` |
| `DIRECTIONAL_ONLY` | `30 ≤ n_unique_dates < 100` |
| `INSUFFICIENT` | `n_unique_dates < 30` |

Secondary diagnostics (`events_per_date_mean`, `events_per_date_p95`)
remain advisory only and not gated.

---

## Downstream Interpretation Rules

**(Unchanged from v0.1.0.)**

Mandatory caveat propagation rules and ownership-of-enforcement
boundary apply identically to D-2, D-2A, and D-2B classifications.
Downstream artefacts own enforcement; P0-B is a closed artefact
whose compliance state does not depend on future downstream
behaviour.

For joint-pair adequacy on inferential outputs spanning both
treatment and baseline (A-1, A-2, A-3), the downstream artefact
must derive the joint classification by taking the weaker of the
D-2A and D-2B classifications for the matching
`(regime, near_limit_up)` cell. This logic resides downstream,
not in P0-B.

---

## Acceptance Criteria

P0-B v0.1.1 is complete when ALL of the following are satisfied:

| # | Criterion |
|---|---|
| AAC-1 | **Four** output tables produced (D-1, D-2, D-2A, D-2B) per schemas above. |
| AAC-2 | Cell adequacy classification (`PASS` / `DIRECTIONAL_ONLY` / `INSUFFICIENT`) applied to D-2, D-2A, and D-2B using the locked thresholds. |
| AAC-3 | `n_unique_dates` is reported alongside the cardinality column (`n_observations` for D-1 and D-2B; `n_events` for D-2 / D-2A) in every cell. Reports that omit `n_unique_dates` are invalid. |
| AAC-4 | Manifest records: audit spec version (v0.1.1), panel snapshot hash, `regime[T-1]` labels verbatim, threshold values used, query SQL, seed (if any sampling involved), and the ADR-R8P1-002 version under which `Baseline_1` / `Baseline_2` were derived. |
| AAC-5 | P0-B declares classification propagation rules and emits machine-readable classification metadata. Each cell record in D-2, D-2A, and D-2B must include `classification`, `must_propagate`, and `must_propagate_reason` fields; the audit manifest must reference the propagation rule. Enforcement of propagation in downstream artefacts is not within P0-B's compliance scope. |
| AAC-6 | No forward-return statistic, no mean / median / hit-rate, no inferential CI appears anywhere in P0-B output. Violation is a governance failure regardless of AAC-1 through AAC-5. |
| AAC-7 (new in v0.1.1) | D-2B `baseline_universe` values must be drawn from the closed set `{"Baseline_1", "Baseline_2"}`. No other values permitted in v0.1.1. |
| AAC-8 (new in v0.1.1) | `must_propagate_reason` values must be drawn from the closed enumeration in §Reason Encoding. Free-text values are a P0-B compliance failure. |

---

## Implementation Invariants

The following invariants apply to any script implementing P0-B v0.1.1:

1. **Panel source.** All price reads must go through
   `listed_market_daily_price_adj` view. Repository-wide enforcement
   is tracked as `BACKLOG-IF1-GUARD`; **not** a P0-B lock dependency.

2. **RS_T3 definition.** Per LA-4: T-1 de-circularised top tertile
   of `beta_adj_rs_*`. The +5% signal candle excluded from the RS
   window. Column name used must be recorded in manifest.

3. **Regime attachment.** Per LA-3 + ADR-R8P1-002 D4: `regime[T-1]`,
   market-level, verbatim from production regime model. For baseline
   rows in D-2B: `regime[d-1]` where `d` is the anchor R8 event date
   (inherited symmetrically per ADR-R8P1-002 D4).

4. **Near-limit-up criterion.** Strictly
   `close[d, s] / close[d-1, s] - 1 ≥ 0.095`. Applied symmetrically
   on each row's own price data per ADR-R8P1-002 SD-1 β.

5. **n_unique_dates definition.** Distinct trading dates `d` on
   which at least one observation satisfies the cell membership
   predicate. Dates with zero qualifying observations are not counted.

6. **Reproducibility.** Re-running the audit on the same panel
   snapshot must produce bit-identical D-1, D-2, D-2A, D-2B outputs.

7. **File header convention.** Per project convention:

       #!/usr/bin/env python3
       # scripts/audit_r8_phase1_cell_adequacy.py
       """R8 Phase 1 cell adequacy audit — vX.Y.Z. Brief.
       ...
       """

8. **Output location.** Audit artefacts written under a versioned
   directory:

       data/_storage/r8_phase1_cell_adequacy/<audit_spec_version>/
         ├── d1_r8_x_rs_tertile.parquet
         ├── d2_global_adequacy.parquet
         ├── d2a_a3_support.parquet
         ├── d2b_baseline_adequacy.parquet      ← new in v0.1.1
         └── manifest.json

9. **Baseline universe derivation provenance (new in v0.1.1).**
   D-2B must be derived from `Baseline_1` and `Baseline_2` exactly
   as defined by ADR-R8P1-002 §Operational Universe Definitions.
   The audit script must not redefine, relax, or extend these
   universe predicates. The ADR-R8P1-002 version under which D-2B
   was generated must be recorded in the audit manifest.

10. **Disjointness check (new in v0.1.1).** Before emitting D-2B,
    the audit script must verify the ADR-R8P1-002 disjointness
    invariant on the materialised panel:

        Treatment_1 ∩ Baseline_1 = ∅
        Treatment_2 ∩ Baseline_2 = ∅

    Failure is a P0-B compliance failure and the audit must abort
    rather than emit potentially corrupt output.

---

## Amendment Procedure

This SPEC is locked when signed off. Amendment requires:

1. A new SPEC version (`v0.1.2`, `v0.2.0`, ...) with explicit changelog.
2. Written rationale citing one of:
   - A change in `r8_phase1_lifecycle_spec.md`.
   - A change in `ADR-R8P1-001`.
   - **A change in or new lock of any Phase 1 methodology ADR
     (ADR-R8P1-002, ADR-R8P1-003, ...). (new in v0.1.1)**
   - Empirical evidence from a pre-flight stability study that the
     locked thresholds in §Gate Definition produce material
     mismatch with bootstrap behaviour.
3. Re-run of any P0-B output produced under the prior SPEC version,
   stored under the new version directory. Prior outputs remain
   valid under their SPEC version of record.

Silent edits are prohibited.

---

## Relationship to Pending Work

| Artefact | Status | Relationship to P0-B |
|---|---|---|
| `ADR-R8P1-002` Baseline Benchmark Construction | **LOCKED v0.1.0** (2026-06-06) | Defines `Baseline_1` and `Baseline_2`. D-2B (new in v0.1.1) audits these universes. |
| A-3 inferential output | NOT YET PRODUCED | Depends on P0-B v0.1.1 (both D-2A treatment-side and D-2B baseline-side adequacy) and ADR-R8P1-001 (inference method). |
| A-1 / A-2 inferential output | NOT YET PRODUCED | Depends on P0-B v0.1.1 (D-2A + D-2B with `baseline_universe = "Baseline_1"` for A-1, `"Baseline_2"` for A-2) and ADR-R8P1-001. |
| P1-DATA IF-2 / IF-3 | OPEN | Findings remain PROVISIONAL per SPEC AC-6 regardless of P0-B outcome. |
| `BACKLOG-IF1-GUARD` | OPEN backlog item | Repo-wide enforcement of `listed_market_daily_price_adj` view usage. Not a P0-B dependency. |

---

*End of r8_phase1_cell_adequacy_spec.md v0.1.1*
