# ADR-R8P1-002 — Baseline Benchmark Construction

<!-- research/adr/ADR-R8P1-002-baseline-benchmark-construction.md -->
<!-- v0.1.0 — 2026-06-06 -->

**Status:** DRAFT — pending sign-off
**Authority:** Implementation ADR resolving methodological ambiguity in
`research/r8_phase1_lifecycle_spec.md` v0.1.2 §Required Comparisons
Benchmarks 1, 2, and 3.
**Scope:** Fixes the universe construction, aggregation unit, and
stratification semantics for Benchmark 1 (RS_T3 Hold), Benchmark 2
(RS_T3 + Pullback), and the RS_T3-unconditional baseline of
Benchmark 3 (R8 within RS_T3 vs RS_T3 unconditional).
**Does not authorise:** Any analysis output. This ADR locks construction;
the first Phase 1 inferential output requires both this ADR and
ADR-R8P1-001 to be signed off.

---

## Context

`r8_phase1_lifecycle_spec.md` v0.1.2 §Required Comparisons specifies
three mandatory benchmarks (AC-2). The spec text reads:

> | RS_T3 Hold | Buy all RS_T3 stocks at T+1 open; hold for each forward horizon. |
> | RS_T3 + Pullback | Same universe filtered to `dist_above_ma20_atr < 0` at T. |
> | R8 within RS_T3 vs RS_T3 unconditional | R8-triggered entries restricted to the RS_T3 universe, compared against all RS_T3 entries in the same date range. |

The phrases "all RS_T3 stocks", "the same universe", and "all RS_T3
entries in the same date range" are mutually consistent at a literal
level but admit at least three substantively different operationalisations:

- **A.** `(date, stock)` panel — every `(d, s)` with `s ∈ RS_T3(d)`
  produces a forward-return observation.
- **B.** Date-level equal-weight portfolio — one return per date.
- **C.** Event-matched, date-anchored — for each R8 event date `d`,
  baseline observations are drawn from `RS_T3(d)` on that date only.

The three options imply different estimands, different sample-size
regimes, and different compatibilities with ADR-R8P1-001
(date-level resampling, joint resampling, AC-3 / AC-4 stratification).

This ADR resolves the ambiguity by locking Construction C with
event-level aggregation and symmetric stratification.

---

## Decision

### D1. Construction approach: C (event-matched, date-anchored)

Benchmark baselines are constructed by **date anchoring on R8 event
dates**. For each date `d ∈ D_R8 := {unique trading dates with ≥1 R8
event}`, baseline observations are drawn from the same-day RS_T3
membership, restricted as specified by D2.

Constructions A (full `(date, stock)` panel) and B (date-level
equal-weight portfolio) are explicitly rejected; see §Alternatives.

### D2. Baseline composition: exclude R8 trigger rows (leave-one-out)

For each `d ∈ D_R8`:

    Baseline_1(d) := { (d, s) : s ∈ RS_T3(d), (d, s) ∉ R8_events }

That is, the R8 trigger rows on `d` are removed from the baseline
universe. The literal-spec alternative (include R8 triggers in
baseline) is rejected: under leave-one-out, treatment and baseline
are disjoint by construction, eliminating an arithmetic correlation
that has no research-question meaning.

### D3. Same construction for Benchmark 1 and Benchmark 2

Benchmark 2 = Benchmark 1 with the additional per-row filter
`dist_above_ma20_atr[d] < 0` applied to **both** treatment and
baseline sides. The filter is computed per-row at the anchor date
`d` (LA-2 point-in-time discipline applies; see also D5).

### D4. Regime treatment

Verified against the Helios production regime model at ADR lock time
(2026-06-06): the regime model emits **market-level** labels — one
`regime[T-1]` label per trading day, independent of stock. Under
Construction C, both treatment and matched baseline rows on date `d`
inherit the **same** `regime[d-1]` tag. AC-3 stratification therefore
operates at the date level for both sides simultaneously.

If the production regime model is later modified to emit
stock-level labels, this ADR requires amendment per
§Future Invalidation Conditions inherited from
`r8_phase1_lifecycle_spec.md`.

### D5. Pullback filter granularity

Verified against the `daily_features` schema at ADR lock time
(2026-06-06): `dist_above_ma20_atr` is a **per-stock-day** feature,
one scalar per `(date, stock)`. Benchmark 2 applies this filter
independently per row on each side, evaluated at anchor date `d`
under LA-2 point-in-time discipline (`bullish_features.computed_at`
must be `<= d` close).

### D6. Aggregation: event-duplicated, event-level point estimate

Point estimates are computed at the **event/observation level**, not
at the date level:

    θ_treat = mean over R8 ∩ RS_T3 events of forward_return
    θ_base  = mean over Baseline_1 rows of forward_return
    Δ       = θ_treat − θ_base

When multiple R8 events fire on the same date, all of them are
retained in the treatment sum; the matched baseline rows on that
date are similarly enumerated once per `(d, s)` pair. Same-day
clustering is **not** corrected at the point-estimate stage; it
is handled at the inference stage by ADR-R8P1-001's date-level
joint resampling.

Date-collapsed aggregation (one mean per date per side) and hybrid
two-estimand designs are explicitly rejected; see §Alternatives.

### SD-1. Symmetric near_limit_up stratification

AC-4 stratification by `near_limit_up` is applied **symmetrically**
to both treatment and baseline rows. For any row `(d, s)`:

    near_limit_up(d, s) := 1 iff close[d, s] / close[d-1, s] - 1 >= 0.095

The same predicate is evaluated on the row's own price data,
regardless of whether the row is a treatment event or a baseline
observation. Asymmetric stratification (treatment-only slicing,
baseline pooled) is rejected because it conflates the near-limit-up
condition effect with the R8 selection effect, which is precisely
the contrast the stratification is intended to isolate.

**Fall-through discipline (locked):**

> If symmetric stratification yields a baseline cell with insufficient
> date support, the cell is classified per P0-B
> (`r8_phase1_cell_adequacy_spec.md` v0.1.0) as `DIRECTIONAL_ONLY`
> or `INSUFFICIENT`. Falling back to asymmetric (treatment-only)
> stratification to recover sample size is prohibited. Sample-size
> shortfall is a finding to be reported, not a methodology to
> repair.

---

## Operational Universe Definitions

The following predicates are the locked, SQL-able definitions of
the treatment and baseline universes. Implementation must derive
these strictly from `listed_market_daily_price_adj` and
`daily_features` (or equivalent post-IF-1 canonical sources).

### Symbols

| Symbol | Definition |
|---|---|
| `d` | Anchor (signal) date. For Benchmark 3 treatment / A-3 numerator: R8 event date. For baseline rows: the matched R8 event date `d ∈ D_R8`. |
| `s` | Stock identifier. |
| `R8_events` | The R8 event panel (post-IF-1 remediation): rows where `r8_flag = 1`, i.e. `daily_return[d, s] >= +0.05 AND close[d, s] > open[d, s]`. |
| `D_R8` | `{ d : ∃ s such that (d, s) ∈ R8_events }`; the set of distinct R8 event dates. Derived from the versioned R8 event manifest used by the analysis run; the manifest hash and `R8_events` row count must be recorded in the output provenance per ADR-R8P1-001 D6. Re-runs against different panel snapshots will produce different `D_R8`; this is correct behaviour and must not be silently reconciled across runs. |
| `RS_T3(d)` | The T-1 de-circularised top tertile of `beta_adj_rs_*` per LA-4, evaluated at `d-1` (the `+5%` signal candle is excluded from the RS calculation window upstream in the feature pipeline; this ADR does not redefine that exclusion). |
| `dist_above_ma20_atr[d, s]` | Per-stock-day feature read from `daily_features` (per D5). |
| `regime[d]` | Market-level regime label at date `d` (per D4). AC-3 attaches `regime[d-1]` per LA-3. |

### Universe definitions

**Benchmark 1 (RS_T3 Hold) — Construction C:**

    Treatment_1 := { (d, s) ∈ R8_events : s ∈ RS_T3(d) }
    Baseline_1  := { (d, s) : d ∈ D_R8,
                              s ∈ RS_T3(d),
                              (d, s) ∉ R8_events }

**Benchmark 2 (RS_T3 + Pullback) — Construction C + per-row pullback filter:**

    Treatment_2 := { (d, s) ∈ Treatment_1 : dist_above_ma20_atr[d, s] < 0 }
    Baseline_2  := { (d, s) ∈ Baseline_1  : dist_above_ma20_atr[d, s] < 0 }

**SPEC INTERPRETATION NOTE — Benchmark 2 filter symmetry:**

Spec §Required Comparisons describes Benchmark 2 as "Same universe
filtered to `dist_above_ma20_atr < 0` at T", which is under-specified
in two respects:

1. *Whether the filter applies to both sides or only to the baseline.*
   The literal "universe" reading could mean (α) only the baseline
   universe is filtered, leaving the R8 treatment universe untouched,
   or (β) both treatment and baseline are filtered symmetrically.

2. *What "at T" anchors to for non-R8 baseline rows.* Under
   Construction C, the anchor is the R8 event date `d`, applied per
   row to both sides.

This ADR locks **interpretation β (symmetric filter)** for the
following reasons:

- It is the direct analogue of SD-1 (symmetric near_limit_up
  stratification), which is already locked. The same principle —
  isolate the R8 selection effect within a conditioning state —
  applies here.
- Under β, A-2 answers a within-state question: "Among pullback-state
  RS_T3 stocks, does R8 trigger add timing information?" Under α,
  A-2 conflates the R8 selection effect with a treatment-vs-baseline
  state mismatch (un-pullback-conditioned R8 events vs
  pullback-conditioned baseline), which is harder to interpret.

This interpretation **should be verified against the original AC-2
wording**. If the Phase 1 SPEC owner reads the spec as mandating α,
this ADR requires an amendment to v0.1.1 (or a SPEC v0.1.3 amendment
that clarifies the spec wording explicitly). Until then, β is the
locked operational definition.

The asymmetry of sample sizes between α and β is significant: under
α, `Treatment_2 = Treatment_1` (full R8 ∩ RS_T3 size). Under β,
Treatment_2 is a likely-small subset, because R8 events by definition
involve a +5% intraday move that typically lifts the stock above
MA20 by ATR units, making post-trigger `dist_above_ma20_atr < 0`
unusual. This sparsity is a substantive Phase 1 finding under β and
must be reported as such, not engineered around.

**Benchmark 3 (R8 within RS_T3 vs RS_T3 unconditional):**

    Treatment_3 := Treatment_1
    Baseline_3  := Baseline_1

Benchmark 3's baseline universe is identical to Benchmark 1's. The
spec phrase "same date range" is operationalised as "the set of R8
event dates `D_R8`"; this is the natural reading under Construction C
and is consistent with the Phase 1 primary research question
("incremental timing information **within RS_T3**, beyond what is
explained by RS exposure alone").

### Disjointness invariant

By D2 (Lock 2 leave-one-out):

    Treatment_k ∩ Baseline_k = ∅   for k ∈ {1, 2, 3}

This invariant must be verified at implementation time (see
§Validation Requirements).

---

## Stratification

### AC-3 regime stratification

Per D4: `regime[d-1]` tags both sides identically on each anchor
date `d`. Stratified estimation per regime `r`:

    Treatment_k|r := { (d, s) ∈ Treatment_k : regime[d-1] = r }
    Baseline_k|r  := { (d, s) ∈ Baseline_k  : regime[d-1] = r }

### AC-4 near_limit_up stratification (per SD-1 symmetric)

For each row, compute `near_limit_up(d, s)` per the predicate in SD-1.
Stratified estimation per `nlu ∈ {0, 1}`:

    Treatment_k|nlu := { (d, s) ∈ Treatment_k : near_limit_up(d, s) = nlu }
    Baseline_k|nlu  := { (d, s) ∈ Baseline_k  : near_limit_up(d, s) = nlu }

### Joint stratification (mandatory under AC-3)

All Phase 1 outputs that present a stratified result must compute
joint cells `(regime, near_limit_up)` on both sides. Marginal
stratification is permitted only as a diagnostic; it does not
satisfy AC-3 + AC-4 individually.

### Cell adequacy gate

Joint cells `(regime, near_limit_up)` on the treatment side are
classified per P0-B `r8_phase1_cell_adequacy_spec.md` v0.1.0
(D-2A audit). Cells on the **baseline side** must additionally be
audited for date support; the baseline-side adequacy table is **not**
produced by P0-B v0.1.0 (which audits the R8 event panel only).
Implementation note: a baseline-side D-2A-equivalent audit is
required before A-1 / A-2 inferential outputs are produced; this
audit's specification is deferred to a minor amendment of the P0-B
spec or to an inline section of the A-1 / A-2 analysis manifest.

---

## Rationale

The decision set above is driven by four principles:

1. **Operationalise the Phase 1 primary research question.** The
   spec question is "Does R8 provide incremental timing information
   **within the RS_T3 universe**?" The natural counterfactual is
   "same-date RS_T3 stocks that did not trigger R8". Construction C
   with leave-one-out and event-level aggregation is the direct
   operationalisation of this counterfactual.

2. **Internal consistency with ADR-R8P1-001.** Date-level
   resampling (ADR-001 D1) and joint resampling for cross-universe
   differences (ADR-001 D5) presuppose that treatment and baseline
   share dates. Construction C makes this trivially true. Event-level
   aggregation (D6) preserves event-grain detail while letting the
   date-level bootstrap handle clustering — the standard
   cluster-robust inference pattern.

3. **Spec-mandated binary stratifications are preserved as binary.**
   AC-4 is defined on signal-day close ≥ +9.5%, a per-row binary
   property. SD-1 symmetric stratification preserves this binary
   structure on both sides without introducing a derived rule (e.g.
   date-level "near-limit-up share ≥ 50%"), avoiding the governance
   surface that B or asymmetric SD-1α would create.

4. **Disjoint treatment and baseline.** D2 leave-one-out makes the
   sets disjoint, removing an arithmetic correlation between
   treatment and baseline means that has no research-question
   content. The literal-spec alternative ("include R8 trigger in
   baseline") inflates baseline by adding the very rows whose effect
   is being measured.

---

## Consequences

### Sample-size profile

- **Treatment_1**: a subset of `R8_events` filtered to `RS_T3`
  membership. Magnitude is bounded above by 8012 (the IF-1-remediated
  R8 event count in the 2026-06-05 handoff); precise count must be
  read from the event manifest, not assumed.
- **Baseline_1**: bounded above by `|D_R8| × |RS_T3 mean size|`.
  This ADR does not commit to a numeric estimate; the implementation
  must report `|Baseline_1|` in the output manifest.
- **Treatment_2 / Baseline_2**: filtered subsets of Treatment_1 /
  Baseline_1. Treatment_2 is expected to be small because R8 events
  by definition involve a +5% intraday move, after which
  `dist_above_ma20_atr` is usually positive. This sparsity is a
  Phase 1 finding to be reported, not engineered around.

### Asymmetry of sample sizes

Construction C produces `|Baseline_k| >> |Treatment_k|` in general.
This is intentional: the baseline mean has lower point-estimate
variance, which improves the precision of `Δ = θ_treat − θ_base`
without distorting the estimand. ADR-R8P1-001's bootstrap inference
handles this asymmetry correctly under date-level joint resampling.

### Disjointness and rebuildability

The leave-one-out predicate `(d, s) ∉ R8_events` requires reading
the R8 event panel and the baseline panel from the same snapshot.
Re-runs after panel update (e.g. future P1-DATA IF-2 / IF-3
remediation) will produce different `R8_events` and therefore
different `Baseline_k`. This is expected and proper; all Phase 1
outputs must record the panel snapshot hash in the manifest per
ADR-R8P1-001 provenance discipline.

### Baseline-side adequacy gap — locked resolution

P0-B v0.1.0 audits the R8 event panel only (D-2A: `R8 ∩ RS_T3`
cells). The baseline universe defined in this ADR (`Baseline_1`,
`Baseline_2`) is **not** covered by P0-B v0.1.0.

**Locked resolution:** A scope-only amendment to P0-B
(`r8_phase1_cell_adequacy_spec.md` v0.1.1) is required to extend
D-2A to baseline-side cells, using the same locked thresholds and
the same `must_propagate` machine-readable contract. The amendment
adds a new audit output (e.g. `D-2B`) covering
`regime × near_limit_up` cells over `Baseline_k`, classified per
the same `PASS / DIRECTIONAL_ONLY / INSUFFICIENT` rule.

**Hard prerequisite:** No A-1, A-2, or A-3 inferential output may be
produced before `r8_phase1_cell_adequacy_spec.md` v0.1.1 is signed
off and the corresponding baseline-side audit output is generated
on the IF-1-remediated panel.

Inline manifest-only declarations of baseline adequacy in the
analysis output (the previously-floated option (b)) are **rejected**:
they would split the audit logic across two documents and weaken
the single-source-of-truth discipline that P0-B is meant to provide.

### Provisional labeling continues

Per `r8_phase1_lifecycle_spec.md` AC-6, all Phase 1 findings remain
PROVISIONAL until formal P1-DATA close + SPEC-level sign-off. This
ADR does not lift that label.

---

## Validation Requirements

Before the first Phase 1 inferential output is produced under this
ADR, the implementation must demonstrate:

1. **Disjointness.** For each `k ∈ {1, 2, 3}`:

       Treatment_k ∩ Baseline_k = ∅

   verified by row-level join on `(d, s)`.

2. **Date support coverage.** The set of distinct dates in
   `Baseline_k` equals `D_R8` (i.e. every R8 event date has at least
   one baseline observation), modulo dates on which RS_T3 ∩ non-R8
   is empty. Such dates must be reported as `DROPPED_NO_BASELINE`
   in the audit manifest; they cannot be silently excluded from
   `D_R8`.

3. **Stratification consistency.** For each `k ∈ {1, 2, 3}` and for
   each stratification axis (regime, near_limit_up, or joint
   regime × near_limit_up):

       Σ over Treatment cells of |Treatment_k|Cell|  =  |Treatment_k|
       Σ over Baseline  cells of |Baseline_k|Cell|   =  |Baseline_k|

   That is, the stratified cell counts on each side independently sum
   to that side's total. Any cell-membership bug that violates either
   identity is a P1 implementation defect.

4. **Reproducibility.** Two runs on the same panel snapshot produce
   bit-identical universe membership for Treatment_k and Baseline_k.
   Any non-determinism (parallel join order, RS_T3 tie-breaking)
   must be eliminated or sorted at write time.

5. **Pullback filter symmetry.** For Benchmark 2, the same
   `dist_above_ma20_atr[d, s] < 0` predicate is applied to both
   sides; a per-row toy test must demonstrate identical inclusion
   logic on a constructed example.

A pre-flight diagnostic notebook implementing items 1–5 on the
current panel is recommended before producing A-1 / A-2 / A-3.

---

## Alternatives Considered and Rejected

| Alternative | Reason rejected |
|---|---|
| Construction A: `(date, stock)` panel of all RS_T3 stock-days | Estimand becomes `E[r \| RS_T3]` (unconditional exposure mean), not "incremental timing within RS_T3". Massive sample asymmetry vs A-3 (≈10⁵ vs 10³) without research-question benefit. Joint resampling under ADR-001 D5 is technically possible but operationally expensive and conceptually muddled. |
| Construction B: date-level equal-weight RS_T3 portfolio | Reduces both sides to a portfolio-return time series, losing event-level grain. AC-4 near_limit_up has no clean date-level definition; would require a derived rule (e.g. "share ≥ 50%") that is not in spec. Compatibility with ADR-001 joint resampling is awkward. |
| Lock 2 (ii): include R8 trigger rows in baseline | Treatment and baseline overlap. The R8 trigger contributes to both `θ_treat` and `θ_base`, introducing arithmetic correlation with no research-question content. Inflates baseline by exactly the effect being measured. |
| Lock 3 split: Benchmark 1 and Benchmark 2 use different constructions | No spec basis for differentiation. Benchmark 2 is defined as Benchmark 1 with an added filter; treating it as a separate methodology unnecessarily multiplies governance surface. |
| Lock 6b: date-collapsed aggregation | Forces a derived date-level definition of `near_limit_up`, conflicting with AC-4's per-row binary structure. ADR-R8P1-001's date-level bootstrap already provides cluster-robust inference at event-level point estimate; date-collapse discards information without inferential gain. |
| Lock 6c: hybrid event-level point + date-level inference | Produces two estimands and two inference paths for the same comparison, doubling governance surface and creating selection risk between estimands. Violates minimum-governance-surface principle. |
| SD-1α: treatment-only stratification, baseline pooled across `near_limit_up` | Conflates near-limit-up condition effect with R8 selection effect. Stratification's purpose is to isolate these effects; asymmetric stratification defeats the purpose. |
| SD-1 fall-back to asymmetric on small cells | Sample-size-driven methodology switching is governance laundering; the locked discipline is to classify the cell per P0-B and report DIRECTIONAL_ONLY or INSUFFICIENT, not to relax the stratification rule. |

---

## Relationship to ADR-R8P1-001 and P0-B Spec

This ADR is jointly required with:

- `ADR-R8P1-001` v0.1.0 — Bootstrap inference method. Construction C
  with D6 event-level aggregation and date-level joint resampling
  (ADR-001 D1+D5) is the locked composition. The two ADRs are not
  independently sufficient.

- `r8_phase1_cell_adequacy_spec.md` — P0-B cell adequacy audit.
  - **v0.1.0 (treatment-side)**: Adequacy classifications on the
    treatment side (D-2A: `R8 ∩ RS_T3` cells stratified by
    `regime × near_limit_up`) propagate to A-1 / A-2 / A-3 outputs
    per AAC-5.
  - **v0.1.1 (baseline-side extension, required)**: extends D-2A to
    cover `Baseline_k` cells via a baseline-side audit output
    (working name D-2B). v0.1.0 alone is **not sufficient** for
    A-1 / A-2 / A-3 inferential outputs under this ADR; v0.1.1
    sign-off is a hard prerequisite per §Consequences.

- `r8_phase1_lifecycle_spec.md` v0.1.2 — Phase 1 governance contract.
  This ADR resolves the under-specified portion of §Required
  Comparisons; it does not modify any spec text.

---

## Amendment Procedure

This ADR is locked when signed off. Amendment requires:

1. A new ADR version (`v0.1.1`, `v0.2.0`, ...) with explicit changelog.
2. Written rationale citing one of:
   - A change in `r8_phase1_lifecycle_spec.md`.
   - A change in `ADR-R8P1-001`.
   - Empirical evidence that a locked choice produces materially
     misleading inference on the IF-1-remediated panel.
3. Re-run of any Phase 1 output produced under the prior ADR
   version, stored under the new version directory.

Silent edits are prohibited.

---

## Sign-off

| Role | Status |
|---|---|
| Method author | Drafted v0.1.0, 2026-06-06 |
| Phase 1 SPEC owner | Pending |
| Lock date | Pending |

Until sign-off, no Phase 1 inferential output may be produced.

---

*End of ADR-R8P1-002 v0.1.0*
