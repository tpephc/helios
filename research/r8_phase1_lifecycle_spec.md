# R8 MA5 Momentum — Phase 1 Lifecycle Specification — v0.2.1

<!-- research/r8_phase1_lifecycle_spec.md -->
<!-- v0.2.1 — 2026-06-07 -->

**Status:** LOCKED — v0.2.1 (2026-06-07)
**Inherits from:** `docs/research/r8_phase0_feasibility.md` (closed 2026-06-01, rev2)
**Authorises:** Lifecycle replay infrastructure and forward-return measurement only.
**Does not authorise:** Production deployment, alpha validation, execution rules,
or any claim of independent alpha.

---

## Changelog

| Version | Date | Change |
|---|---|---|
| v0.1.2 | 2026-06-02 | Initial SPEC LOCKED |
| v0.1.3 | 2026-06-06 | Added Phase 1 Findings section (A-3 complete). Status updated to reflect P0-B and A-3 completion. No SPEC terms modified. |
| v0.1.4 | 2026-06-06 | A-1 and A-2 complete. Phase 1 Findings section updated. AC-2 satisfied. Analysis progress table updated. Reference to interim findings note added. No SPEC terms modified. |
| v0.1.5 | 2026-06-06 | IF-2 reclassified from AC-6 binding blocker to P2 data backlog. company_metadata accepted as Phase 1 sector diagnostic source. No SPEC terms modified. |
| v0.1.6 | 2026-06-07 | Composition audit finding added (new section). IF-3B reclassified from AC-6 binding blocker to P2 non-binding per composition audit evidence. DQ-ADJ-003 reclassified from adjustment anomaly to capital reduction event; subsumed by DQ-CA-001. Open items table updated. No SPEC terms (AC-1 through AC-7, LA-1 through LA-8) modified. |
| v0.2.0 | 2026-06-07 | Phase 1 Promotion Status section added. PROVISIONAL language removed. Analysis progress table artifact paths updated to v0.2.0. Findings reference updated to v1.0.0. AC-6 formally closed. No SPEC terms (AC-1 through AC-7, LA-1 through LA-8) modified. |
| v0.2.1 | 2026-06-07 | Pre-promotion governance constraint section relabelled as historical. AC-6 row updated with CLOSED status. LA-5 updated with SUPERSEDED note. Future Invalidation P1-DATA row updated with outcome. Cosmetic consistency patch only; no SPEC terms modified. |

---

## Status

Phase 1 SPEC LOCKED (2026-06-02). Findings promoted to CONFIRMED (2026-06-07).

### Phase 1 Promotion Status

**CONFIRMED — 2026-06-07**

AC-6 CLOSED. Clean-panel re-run completed (commit 4a307e6). All binding
blockers resolved:

- IF-3A CLOSED (commit 76f1f45)
- IF-3B reclassified P2 non-binding (composition audit 2026-06-07)
- IF-2 reclassified P2 non-binding (v0.1.5)

Phase 1 findings are promoted from PROVISIONAL to CONFIRMED for measurement
scope only. This promotion does not constitute alpha validation, execution
authorisation, or production deployment authorisation.

See: `research/r8_phase1_interim_findings.md` v1.0.0

**Analysis progress as of v0.2.0:**

| Analysis | Status | Artifact |
|---|---|---|
| P0-B Cell adequacy audit | COMPLETE | `data/_storage/r8_phase1_cell_adequacy/v0.1.1/` |
| A-1 RS_T3 Hold benchmark | COMPLETE | `data/_storage/r8_phase1_a1/v0.2.0/` |
| A-2 RS_T3 + Pullback benchmark | COMPLETE (descriptive only — 0 PASS cells) | `data/_storage/r8_phase1_a2/v0.2.0/` |
| A-3 R8∩RS_T3 vs RS_T3 unconditional | COMPLETE | `data/_storage/r8_phase1_a3/v0.2.0/` |

**AC-2 status: SATISFIED.** All three required comparisons have been measured
and reported. A-2 is satisfied via adequacy outcome: Treatment_2 (R8 ∩ RS_T3 ∩
pullback state) contains only 262 events across 109 dates (4.9% of Treatment_1),
yielding 0 PASS cells. This sparsity is the substantive A-2 finding.

This document is the upstream governance contract for all Phase 1 implementation
artifacts, analysis notebooks, and any downstream SPEC that references R8 Phase 1
findings. No Phase 1 implementation may proceed without reference to this document.
Amendments require a new versioned SPEC; silent edits are not permitted.

---

## Phase 1 Research Question

**Primary question:**

> Does the R8 +5% breakout event provide incremental timing information
> within the RS top-tertile (RS_T3) universe, beyond what is explained
> by RS exposure alone?

**Framing note:**

This question is conditional and comparative, not absolute. The relevant
counterfactual is "holding high-RS names," not "cash." Phase 0 established
that R8 selection is not novel — any independent edge can only come from
entry timing. Phase 1 tests that specific claim.

**What this question is not:**

- "Can R8 generate positive returns?" — absolute profitability is not the
  Phase 1 question and is not a sufficient condition.
- "Is R8 a viable production strategy?" — Phase 1 does not address this.
- "Does R8 have alpha?" — Phase 1 measures; it does not validate.

---

## Scope

Phase 1 covers:

1. **Lifecycle replay infrastructure** — tag each R8 signal event with
   forward-return observations at standardised horizons (see Lifecycle
   Definition below).
2. **Forward-return measurement** — compute forward returns at T+1 open,
   +1td, +3td, +5td, +10td, +20td relative to T+1 entry (trading days;
   see LA-8). Formula frozen as `adj_close[T+h] / adj_open[T+1] - 1`
   where `h` is measured in trading days and T+1 open is the entry anchor.
3. **Required benchmark comparisons** — measure R8 event outcomes against
   the three baselines mandated by Phase 0 (see Required Comparisons below).
4. **Regime-stratified analysis** — Phase 0 found ~27% of signals in
   crisis/bear regimes. Phase 1 must NOT pool regimes; all analysis must
   be stratified by `regime[T-1]`.
5. **Near-limit-up subset tagging** — Phase 0 identified ~29% of signal
   days closing at >=+9.5% relative to the previous close. Phase 1 must
   tag this subset and evaluate it separately; pooled results that include
   this subset without flagging it are not valid.
6. **Observational MA5 and post-entry state metrics** — see Lifecycle
   Definition and Observation vs Execution Boundary below.
7. **Effective-n estimation** — Phase 0 flagged that `clean_tradable_events
   = 5621` is a row count, not an independent-observation count, due to
   same-day clustering and industry concentration. Phase 1 must report a
   block-bootstrap effective-n estimate alongside any inference. The
   estimation method (block length, resampling unit, date-level vs
   event-level) is not frozen here; it must be fixed by implementation ADR
   before the first Phase 1 output is produced. Phase 1 outputs must
   disclose block length and resampling unit; silent changes between runs
   are not permitted.

---

## Out of Scope

The following are explicitly excluded from Phase 1. Inclusion of any item
below without a new versioned SPEC constitutes a governance violation:

- Execution simulation (fills, slippage, commissions)
- Position sizing or portfolio construction
- Partial exits, sell-half, buy-back mechanics
- MA5 reclaim/break as an exit trigger (see Observation vs Execution Boundary)
- Re-entry rules of any kind
- PnL calculation
- Production deployment or live signal generation
- Alpha validation or claims of independent alpha
- Panel integrity remediation (tracked separately as backlog P1-DATA)
- Industry-code or sector-rotation analysis beyond what Phase 0 established
- Any forward-return horizon beyond +20d

---

## Required Comparisons

Phase 0 mandates the following three benchmarks. Phase 1 MUST include all
three. Omitting any benchmark is a protocol violation regardless of findings.

| Benchmark | Definition |
|---|---|
| **RS_T3 Hold** | Buy all RS_T3 stocks at T+1 open; hold for each forward horizon. |
| **RS_T3 + Pullback** | Same universe filtered to `dist_above_ma20_atr < 0` at T. |
| **R8 within RS_T3 vs RS_T3 unconditional** | R8-triggered entries restricted to the RS_T3 universe, compared against all RS_T3 entries in the same date range. |

**Measurement requirement, not acceptance gate:**

These comparisons are required components of the analysis. Phase 1 is
complete when all three comparisons are measured and reported. Phase 1
is NOT contingent on R8 outperforming any baseline. Whether R8 beats
or fails to beat a baseline is a finding, not a pass/fail condition.

**RS_T3 proxy note (inherited from Phase 0):**

RS_T3 is a reconstructed proxy (per-date top tertile of `beta_adj_rs_*`),
not the production tier. The decisive version is the T-1 de-circularised
measure. The signal candle (+5%) MUST be excluded from the RS window to
avoid circularity.

---

## Lifecycle Definition

### Event timeline

| Point | Definition |
|---|---|
| `T` | Signal date: `daily_return >= +5% AND close > open`. |
| `T+1 open` | First tradable entry point. No T-day entry is permitted. |
| `T+1d` | Close of T+1. |
| `T+3td`, `T+5td`, `T+10td`, `T+20td` | Close at N **trading days** after T+1 open. Non-trading days do not advance event age (see LA-8). |
| Resolution | Event is resolved when the last measured horizon (+20td) is reached. |

**Forward-return formula (frozen):** `adj_close[T+h] / adj_open[T+1] - 1`,
where `h` ∈ {1, 3, 5, 10, 20} trading days and T+1 open is the entry anchor.
This formula is locked; any deviation requires a SPEC amendment.

**SMA / RS / `dist_above_ma20_atr`** are recorded as-of T close (assumed
point-in-time; verify via `bullish_features.computed_at`). Regime is
attached as `regime[T-1]`. No post-signal feature is permitted in any
feature computed at T or earlier.

### Observational metrics

Each event record may include the following post-entry observational metrics:

- `days_above_ma5` — count of trading days price closes above MA5 within
  the measurement window.
- `first_ma5_break_date` — first date price closes below MA5 after T+1 entry.
- `ma5_reclaim_count` — number of times price reclaims MA5 after a break
  within the measurement window.
- `pct_time_above_ma5` — fraction of measurement window days price is above MA5.
- `max_drawdown_from_entry` — maximum peak-to-trough drawdown from T+1 open
  within the measurement window.
- `new_high_flag` — whether price achieves a new 20d high at any point in
  the measurement window.

These metrics are descriptive lifecycle telemetry. See Observation vs
Execution Boundary below.

### Observation vs Execution Boundary

**This section is a mandatory governance constraint, not implementation guidance.**

Phase 1 records post-entry interactions with MA5 for observational purposes
only. The presence of an observational metric in the event record does NOT
authorise any execution policy derived from that metric.

**IN SCOPE — observation:**

- Measure whether price is above or below MA5 on each post-entry day.
- Record the date of first MA5 break after entry.
- Count MA5 reclaim events within the measurement window.
- Compute fraction of time above MA5.
- Stratify forward returns by MA5 state at intermediate horizons.
- Compare outcomes conditional on MA5 interaction patterns.

**OUT OF SCOPE — execution policy:**

- Exit on MA5 break.
- Re-enter on MA5 reclaim.
- Sell-half on MA5 break.
- Scale position based on MA5 state.
- Use MA5 interaction as a stop-loss trigger.
- Use MA5 state in any sizing or allocation rule.

Any Phase 2 or later proposal to use MA5 as an execution trigger requires
an independent SPEC with explicit governance rationale. It MUST NOT cite
Phase 1 observational findings as authorisation.

---

## Panel Governance

### Current panel status

Phase 1 may proceed on the current panel as defined in Phase 0.

Phase 0 identified three panel integrity gaps that remain unresolved at the
time of this SPEC:

1. **Pre-listing / emerging-board contamination** — 18 stocks with
   `listing_date > first_price_date`; 7331 rows in `daily_price_adj`
   predate their stock's `listing_date`. These rows contain emerging-board
   (興櫃) history with no daily price limit and different microstructure.
   Affects R1/R2/R5 panels, the replay engine, and RS_T3 quantile
   computation (backlog P1-DATA).
2. **Empty `stock_info`** — sector mapping relies on `company_metadata
   .industry_code` only.
3. **Empty `corporate_actions`** (DQ-CA-001) — halt/resumption rows
   cannot be distinguished from bad data. 203 SUSPENSION_GAP rows were
   classified as pending at Phase 0 time. A composition audit conducted
   2026-06-07 (see Phase 1 Findings: Composition Audit) found 0 confirmed
   halt-resumption events in the r8_events population. IF-3B reclassified
   as P2 non-binding per v0.1.6.

### Pre-promotion governance constraint *(historical — superseded by v0.2.0)*

> **Note (v0.2.0):** The constraint below was the operative governance rule
> from SPEC LOCKED (v0.1.2) through clean-panel re-run completion (2026-06-07).
> It has been satisfied. AC-6 is CLOSED. Findings are CONFIRMED.
> This section is retained for audit continuity only.

All Phase 1 statistical conclusions were **provisional** until P1-DATA
remediation was completed. No alpha-validation claim, no publication-ready
finding, and no production deployment decision may be based on Phase 1
results alone while these gaps remain open.

This constraint applied without exception. It could not be waived by
individual judgment; it required a formal P1-DATA close and a
SPEC-level sign-off on panel integrity.

### P1-DATA relationship

P1-DATA is a parallel backlog item, not a hard prerequisite that blocks
Phase 1 from beginning. The correct sequencing was:

```
Phase 1 SPEC (this document) → Phase 1 implementation → Phase 1 findings
                                     ↕ parallel
              P1-DATA remediation → panel re-run → findings upgraded from provisional
```

**Outcome (v0.2.0):** P1-DATA remediation completed. Clean-panel re-run
completed 2026-06-07 (commit 4a307e6). Findings promoted to CONFIRMED.

---

## Acceptance Criteria

Phase 1 is complete when ALL of the following are satisfied:

| # | Criterion |
|---|---|
| AC-1 | Forward returns computed at T+1 open, +1td, +3td, +5td, +10td, +20td (trading days) for all R8 events in scope. |
| AC-2 | All three Required Comparisons are computed and reported (RS_T3 Hold, RS_T3+Pullback, R8-within-RS_T3). |
| AC-3 | All analysis is stratified by `regime[T-1]`; no pooled-regime result is presented without explicit caveat. |
| AC-4 | Near-limit-up subset (signal day close >= +9.5% relative to previous close) is tagged and reported separately; pooled results note this subset explicitly. |
| AC-5 | Block-bootstrap effective-n estimate is reported alongside any inferential statistic. |
| AC-6 | All findings are labelled as provisional pending P1-DATA remediation. **CLOSED 2026-06-07** (commit 4a307e6; findings promoted to CONFIRMED). |
| AC-7 | No execution policy, production deployment, or alpha-validation claim appears in Phase 1 outputs. |

AC-7 is a negative criterion. Violation of AC-7 constitutes a governance
failure regardless of whether the other six criteria are met.

---

## Interpretation Restrictions

Phase 1 completion does NOT establish, authorise, or imply any of the
following:

- That R8 has independent alpha.
- That R8 outperforms holding high-RS names.
- That R8 is ready for production deployment.
- That MA5 observations constitute a valid exit rule.
- That forward-return distributions are stable across regimes or time.
- That findings on the current panel are valid without P1-DATA remediation.
- That any execution policy (entry, exit, sizing, scaling, re-entry) is
  authorised for R8.
- That Phase 1 findings constitute portfolio allocation guidance.

Phase 1 establishes **measurement infrastructure and benchmarked lifecycle
evidence only**. Any downstream claim that exceeds this scope requires a
new SPEC with explicit governance rationale and citation of the specific
Phase 1 output being relied upon.

This restriction is inherited from Phase 0:

> "The 5/5 PASS authorises a lifecycle-replay SPEC ONLY — not a
> production rule, and not a clean orthogonality claim."
> — r8_phase0_feasibility.md

---

## Locked Assumptions

The following assumptions are frozen for Phase 1. They may not be changed
within Phase 1 without a SPEC amendment. If empirical evidence contradicts
a locked assumption, the correct response is to document the contradiction
and defer to a Phase 1 amendment or Phase 2 SPEC — not to silently modify
the analysis.

| # | Assumption |
|---|---|
| LA-1 | Signal day = T. Earliest tradable entry = T+1 open. T-day entry is not permitted. |
| LA-2 | SMA / RS / `dist_above_ma20_atr` are point-in-time as-of T close. Verify via `bullish_features.computed_at`. |
| LA-3 | Regime is attached as `regime[T-1]`, consistent with production. |
| LA-4 | RS_T3 is the T-1 de-circularised top tertile of `beta_adj_rs_*`. The +5% signal candle is excluded from the RS window. |
| LA-5 | Phase 1 uses the current panel. ~~All findings are provisional pending P1-DATA remediation.~~ **Superseded (v0.2.0):** P1-DATA remediation complete; findings CONFIRMED (2026-06-07). |
| LA-6 | Industry concentration and same-day clustering (up to 77 simultaneous signals on 2024-08-07) mean that row count is not independent-observation count. Effective-n must be estimated. |
| LA-7 | `find_bullish_setups.py` is an observational screener with uncalibrated thresholds ([ASSUMED]). It is not a validated entry strategy and may not be used as a benchmark. |
| LA-8 | All forward-return horizons are measured in **trading days**. Non-trading days (weekends, public holidays) do not advance event age. Calendar-day interpretation is not permitted. |

---

## Inheritance from Phase 0

The following Phase 0 findings are inherited into Phase 1 as background
facts. They do not require re-derivation but must not be contradicted
without explicit documentation:

- R8 selection is substantially overlapping with the RS_T3 / high-RS
  universe. Selection-level overlap is established; it is not under study.
- T+1 limit-lock is not a material risk (0.95% of signals open at >=+9.5%).
  Fillability at T+1 open is assumed.
- Fillability does not validate entry quality. ~29% of signal days close
  near limit-up but open flat the next day; this subset likely represents
  exhausted moves.
- The electronics complex (industry codes 24+28+26+25+27+31+29+30) accounts
  for ~78% of R8 signals. R8 is an electronics/momentum strategy, not a
  broad-market one.
- Phase 0 data-quality figures are taken from the v0.1.2 audit run
  (2026-06-01 09:20). They are verbatim measurements, not estimates.

---

## Future Invalidation Conditions

This SPEC and its Phase 1 findings are invalidated or require amendment
under any of the following conditions:

| Condition | Action required |
|---|---|
| P1-DATA remediation reveals that pre-listing contamination materially changes RS_T3 composition or R8 signal counts. | Phase 1 must be re-run on the clean panel. All provisional findings are superseded. **Outcome (v0.2.0):** Clean-panel re-run completed 2026-06-07 (commit 4a307e6). Benchmark C Δ = +0.0872pp. Findings confirmed robust; not superseded. |
| The regime classification model is retrained or its thresholds change. | Phase 1 findings stratified by `regime[T-1]` must be re-evaluated. |
| The `beta_adj_rs_*` computation methodology changes. | RS_T3 proxy and LA-4 must be re-verified. |
| A suspension/halt table becomes available, enabling reclassification of SUSPENSION_GAP rows. | DQ-338 classification must be revisited. Composition audit (v0.1.6) found 0 confirmed halt-resumption events in r8_events. A halt table may reclassify rows in `daily_price_adj` at forward-return observation dates outside the reviewed signal population. |
| Event count per day distribution changes materially (e.g. sustained >50 simultaneous signals). | Effective-n estimate and clustering assumptions must be revisited. |
| Any Phase 1 output is proposed as the basis for a production deployment decision. | A new Phase 2 SPEC is required. This SPEC does not authorise that step. |

---

## Phase 1 Findings

<!-- Updated v0.2.0 — 2026-06-07 — LOCK APPROVED -->

**Findings status: CONFIRMED (2026-06-07)**

All findings in this section are confirmed per AC-6 closeout (2026-06-07,
commit 4a307e6). IF-3A CLOSED. IF-3B and IF-2 reclassified P2 non-binding.
Clean-panel re-run complete. Findings are confirmed for measurement scope only.

Full integrated findings with narrative, research hypotheses, and benchmark
hierarchy: see `research/r8_phase1_interim_findings.md` v1.0.0.

### Inference method

All inferential statistics use the stationary block-bootstrap per
ADR-R8P1-001 v0.1.0:

- Resampling unit: trading date (date-level, not event-level)
- Block length: L=20 (primary); sensitivity grid L={5, 10, 20, 40}
- Replications: B=5000
- CI method: percentile (95%)
- p-value method: null-shifted two-tailed
- Joint resample applied to treatment and baseline within each replication
- n_eff reference unit: treatment date pool
- Seed: 42

A-1 uses a single-side bootstrap (baseline date pool only, no joint resample)
per ADR-R8P1-002 and session-locked spec decision (Option X). No p-value is
reported for A-1.

A-2 uses no bootstrap (descriptive only — 0 PASS cells).

### A-1: RS_T3 Hold Benchmark

**Artifact:** `data/_storage/r8_phase1_a1/v0.2.0/`
**Mode:** Descriptive with bootstrap uncertainty (no p-value)
**Panel:** Baseline_1 — 63,363 observations, 1,068 unique dates

PASS cells: bull/nlu=0, bear/nlu=0, neutral/nlu=0.

**Bull regime, nlu=0 — key results:**

| Horizon | θ_base | 95% CI (L=20) | n_eff |
|---|---|---|---|
| 10td | +1.50% | [+0.85%, +2.13%] | 105 |
| 20td | +3.03% | [+1.84%, +4.17%] | 71 |

RS_T3 baseline is materially positive in bull regimes at longer horizons.
CI excludes zero at 5td and beyond. Findings robust across L={5,10,20,40}.

Bear and neutral baselines: all 95% CIs contain zero at 5td and beyond.
The RS_T3 Hold strategy does not produce reliably positive returns in
bear or neutral regimes on R8 event dates.

### A-2: RS_T3 + Pullback Benchmark

**Artifact:** `data/_storage/r8_phase1_a2/v0.2.0/`
**Mode:** DESCRIPTIVE ONLY — no bootstrap, no CI, no p-value
**Adequacy outcome: 0 PASS cells, 2 DIRECTIONAL_ONLY, 6 INSUFFICIENT**

Treatment_2 (R8 ∩ RS_T3 ∩ `dist_above_ma20_atr < 0`) contains 262 events
across 109 dates — 4.9% of Treatment_1. This sparsity is a structural finding:
R8's +5% intraday move definition is nearly incompatible with simultaneous
pullback state at the signal date. Full inferential evaluation of Δ_A2 is
not possible under the current sample.

**Directional evidence (inference prohibited):**

Bull/nlu=0: Δ_A2 ≈ +2.20% at 20td (38 treatment dates).
Bear/nlu=0: Δ_A2 ≈ +5.00% at 20td (36 treatment dates).

These point estimates are directionally consistent with A-3 (H2: R8 uplift
independent of pullback state), but carry no inferential weight. The H1/H2
question remains unresolved.

### A-3: R8 within RS_T3 vs RS_T3 Unconditional

**Artifact:** `data/_storage/r8_phase1_a3/v0.2.0/`
**Mode:** Full inferential (B=5000, L=20 primary, joint bootstrap)
**Panel:** Treatment_1 — 5,330 events; Baseline_1 — 63,363 observations

Full inference cells (PASS × PASS): bull/nlu=0, bear/nlu=0, neutral/nlu=0.

#### Tier 1 — Robust findings (full inference, robust across sensitivity grid)

**Bull regime, near_limit_up=0**
(treatment n≈2,141–2,276 events; treatment dates≈596–614 per horizon)

| Horizon | δ_obs | 95% CI (L=20) | CI range across L={5,10,20,40} | p (L=20) | p range across L | n_eff (L=20) |
|---|---|---|---|---|---|---|
| 10td | +1.35% | [+0.69%, +2.18%] | lower bound +0.61% to +0.72% | 0.0002 | 0.0000–0.0010 | 299 |
| 20td | +2.10% | [+0.94%, +3.45%] | lower bound +0.77% to +1.11% | 0.0008 | 0.0006–0.0036 | 258 |

**Sensitivity verdict:** ROBUST. At all tested block lengths L={5,10,20,40},
the 95% CI lower bound remains strictly positive. p ≤ 0.004 at all block
lengths. The finding does not depend on the L=20 choice.

**Economic pattern:** δ_obs increases monotonically with horizon
(1td: −0.03%, 5td: +0.38%, 10td: +1.35%, 20td: +2.10%), consistent
with a trend-continuation dynamic rather than an immediate entry-timing
effect. This pattern is a descriptive observation; causal interpretation
requires further analysis outside Phase 1 scope.

**Interpretation boundary:** This finding establishes that R8 events
within RS_T3 are followed by incrementally higher forward returns than
RS_T3 non-R8 observations at 10td and 20td horizons in bull regimes.
It does not establish that this difference is exploitable net of execution
costs, that it is stable over time, or that it constitutes tradeable alpha.
The finding is conditional on the RS_T3 proxy defined in LA-4. It should
not be interpreted as evidence that R8 provides incremental information
outside the high-RS universe.

#### Tier 2 — Consistent direction, insufficient evidence for significance

**Bull regime, near_limit_up=0, 5td**
(treatment n=2,235; treatment dates=610)

δ_obs = +0.38%. Positive direction observed at all block lengths
(L={5,10,20,40}). p ranges from 0.046 to 0.085 across the sensitivity
grid; CI lower bound ranges from +0.003% to +0.059%. The result does not
meet the α=0.05 significance threshold consistently across block lengths.

**Verdict:** Consistent positive direction; insufficient evidence for
promotion to a statistically-supported finding.

#### Tier 3 — Suggestive, not promoted

**Bear regime, near_limit_up=0, 20td**
(treatment n=491; treatment dates=173)

δ_obs = +1.46%. p ranges from 0.025 to 0.034 across the sensitivity grid
(nominally significant), but the 95% percentile CI contains zero at all
tested block lengths (lower bound −0.19% to −0.11%). Under the governance
principle that the ADR-locked CI method (percentile) takes precedence over
the p-value method, this result is classified as suggestive.

Additional structural note: n_eff is non-monotone across horizons in the
bear cell (5td: 184, 10td: 80, 20td: 141). The 10td drop suggests
concentrated clustering in a small number of influential date clusters
within the bear regime. This is a structural observation, not a defect.

**Verdict:** Suggestive positive trend at 20td. Not promoted. Re-evaluate
after P1-DATA clean-panel re-run.

#### No-signal cells (full inference)

**Bear regime, nlu=0, horizons 1td / 5td / 10td:** p > 0.23 at all block
lengths, CI contains zero. No evidence of incremental timing effect at
these horizons.

**Neutral regime, nlu=0, all horizons:** All deltas are negative
(range −0.02% to −0.59%); all 95% CIs contain zero; all p > 0.05 across
the sensitivity grid. n_eff at 20td = 47–60, reflecting limited date
coverage (treatment_dates=126) and high VIF at longer horizons. Wide CIs
at 20td are a structural finding per ADR-R8P1-001 D7 (honest disclosure
of small n_eff), not a defect to be resolved by pooling.

#### Adequacy-restricted cells (not included in findings)

Cells with joint adequacy DIRECTIONAL_ONLY or INSUFFICIENT are excluded
from the findings table. Point estimates exist in the artifact but are
not promoted to findings without adequate inferential support. These
cells are: bull/nlu=1, crisis/nlu=0, crisis/nlu=1, bear/nlu=1,
neutral/nlu=1.

### Composition Audit — SUSPENSION_GAP Candidate Rows

**Conducted:** 2026-06-07
**Method:** Exhaustive classification of all r8_events rows with
`signal_daily_return >= 0.10`, cross-referenced against `daily_price_adj`
`calendar_gap_days`, volume signals, TWSE holiday calendar, and news
sources for long-gap rows.

#### Motivation

IF-3B was designated an AC-6 binding blocker in commit `77fb3c1` on the
basis that `corporate_actions` contained no halt/suspension records and
that "203 SUSPENSION_GAP rows" in the r8_events population might represent
halt-resumption cross-gaps inflating or deflating forward returns. The
composition audit was conducted to verify whether this risk materialises
in the actual r8_events data.

The 203 figure originated from a Phase 0 audit run (2026-06-02,
`ma5_momentum_feasibility.py` v0.1.2) using an earlier r8_events snapshot.
The current panel contains 234 candidate rows under the same definition
(`signal_daily_return >= 0.10`, excluding PRE_LISTING_OTC). The
classification method is identical.

#### Results

| Class | Count | % | Notes |
|---|---|---|---|
| Normal limit-up (ret≈10%, gap=1–4d) | 227 | 97.0% | Standard Taiwan daily price limit; normal trading |
| Holiday gap (gap≥5d, ret=10–14%) | 6 | 2.6% | Lunar New Year, Mid-Autumn, Typhoon, Tomb Sweeping; verified against TWSE calendar |
| Capital reduction 換發新股 | 1 | 0.4% | 2327 / 2022-10-31; see DQ-ADJ-003 reclassification below |
| **Confirmed halt-resumption** | **0** | **0%** | None found |

**Total candidate rows examined:** 234
**Confirmed halt-resumption events in r8_events:** 0

#### Implication for IF-3B

No empirical evidence of halt-resumption contamination was identified in
the reviewed r8_events population. The hypothesised halt-contamination
pathway that motivated IF-3B binding status is not supported by the
evidence in the event population reviewed.

Residual uncertainty remains regarding trading interruptions at
forward-return observation dates (T+1 to T+20) outside the reviewed
signal population. IF-3B therefore remains a data-infrastructure concern,
but no longer blocks AC-6.

IF-3B is reclassified from AC-6 binding blocker to P2 data infrastructure
(same treatment as IF-2, v0.1.5). Clean-panel re-run is unblocked.

#### DQ-ADJ-003 Reclassification

**Previous classification:** 2327 / 2022-10-31 — possible adjustment
calculation anomaly (`adj_close` showed +36.94% while `raw_close` appeared
normal).

**Reclassification (v0.1.6):** 2327 / 2022-10-31 is a 現金減資換發新股
(capital reduction with share re-issuance) event confirmed via news source
(cnyes.com/news/id/4972505). The stock resumed trading on 2022-10-31 after
a 12-calendar-day suspension during the capital reduction process. The
+36.94% return reflects the price adjustment from the reduced share count,
which is correct. The `adj_close` value is not anomalous; the root cause
is the absence of this event in `corporate_actions` (DQ-CA-001).

**Disposition:** DQ-ADJ-003 closed as a standalone DQ item. Underlying gap
subsumed by DQ-CA-001 / IF-3B P2 backlog.

**Impact on findings:** 2327 / 2022-10-31 carries `rs_t3_t_minus_1 = 0.0`
and `near_limit_up_flag = True`, placing it in the `bear/nlu=1` cell.
This cell is adequacy-restricted (INSUFFICIENT) and excluded from all
Tier 1, Tier 2, and Tier 3 findings. No finding is affected.

### Open items affecting findings

| ID | Description | Impact on findings |
|---|---|---|
| IF-2 | Empty `stock_info` — **RECLASSIFIED P2** | Sector composition of treatment/baseline unknown; electronics-concentration bias from Phase 0 cannot be re-verified. Non-binding per v0.1.5. |
| IF-3A | `corporate_actions` dividend/split — **CLOSED** (commit `76f1f45`) | 1106 rows, 199 symbols populated. No residual impact. |
| IF-3B | Suspension/halt/resumption dataset — **RECLASSIFIED P2** | Composition audit (v0.1.6) found 0 confirmed halt-resumption events in r8_events. Non-binding per v0.1.6. Residual uncertainty at T+1–T+20 observation dates disclosed above. |
| DQ-ADJ-003 | 2327 / 2022-10-31 — **CLOSED** | Reclassified as capital reduction event; subsumed by DQ-CA-001. No finding affected (adequacy-restricted cell). |
| BACKLOG-IF1-GUARD | No repo-wide guard preventing direct access to `daily_price_adj` outside allowlist | Forward return computation integrity unguarded at repo level |

---

*End of r8_phase1_lifecycle_spec.md v0.2.1*
