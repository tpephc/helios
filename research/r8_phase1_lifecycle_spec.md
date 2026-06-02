# R8 MA5 Momentum — Phase 1 Lifecycle Specification

<!-- research/r8_phase1_lifecycle_spec.md -->
<!-- v0.1.2 — 2026-06-02 -->

**Status:** LOCKED — v0.1.2 (2026-06-02)
**Inherits from:** `docs/research/r8_phase0_feasibility.md` (closed 2026-06-01, rev2)
**Authorises:** Lifecycle replay infrastructure and forward-return measurement only.
**Does not authorise:** Production deployment, alpha validation, execution rules,
or any claim of independent alpha.

---

## Status

Phase 1 SPEC LOCKED (2026-06-02).

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
   cannot be distinguished from bad data; 203 SUSPENSION_GAP rows are
   classified as pending.

### Provisional findings constraint

All Phase 1 statistical conclusions are **provisional** until P1-DATA
remediation is completed. No alpha-validation claim, no publication-ready
finding, and no production deployment decision may be based on Phase 1
results alone while these gaps remain open.

This constraint applies without exception. It cannot be waived by
individual judgment; it requires a formal P1-DATA close and a
SPEC-level sign-off on panel integrity.

### P1-DATA relationship

P1-DATA is a parallel backlog item, not a hard prerequisite that blocks
Phase 1 from beginning. The correct sequencing is:

```
Phase 1 SPEC (this document) → Phase 1 implementation → Phase 1 findings
                                     ↕ parallel
              P1-DATA remediation → panel re-run → findings upgraded from provisional
```

Phase 1 findings MUST be clearly labelled as provisional in any report or
presentation until the panel re-run under a clean panel is completed.

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
| AC-6 | All findings are labelled as provisional pending P1-DATA remediation. |
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
| LA-5 | Phase 1 uses the current panel. All findings are provisional pending P1-DATA remediation. |
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
| P1-DATA remediation reveals that pre-listing contamination materially changes RS_T3 composition or R8 signal counts. | Phase 1 must be re-run on the clean panel. All provisional findings are superseded. |
| The regime classification model is retrained or its thresholds change. | Phase 1 findings stratified by `regime[T-1]` must be re-evaluated. |
| The `beta_adj_rs_*` computation methodology changes. | RS_T3 proxy and LA-4 must be re-verified. |
| A suspension/halt table becomes available, enabling reclassification of SUSPENSION_GAP rows. | DQ-338 classification must be revisited; affected rows must be excluded or reclassified. |
| Event count per day distribution changes materially (e.g. sustained >50 simultaneous signals). | Effective-n estimate and clustering assumptions must be revisited. |
| Any Phase 1 output is proposed as the basis for a production deployment decision. | A new Phase 2 SPEC is required. This SPEC does not authorise that step. |

---

*End of r8_phase1_lifecycle_spec.md v0.1.2*
