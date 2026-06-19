# R8 MA5 Momentum — Phase 6 SPEC: Exit Policy Evaluation

<!-- research/r8_phase6_spec.md -->
<!-- v0.1.1 — 2026-06-19 -->

**Status:** LOCKED — v0.1.1 (E1 parameter freeze applied; design content
  immutable from v0.1.0)

**Changelog:**

| Version | Date | Change |
|---|---|---|
| v0.1.0 | 2026-06-19 | Initial draft; LOCK APPROVED |
| v0.1.1 | 2026-06-19 | §3.2 (E1 — ATR Trailing Exit) parameter freeze applied. Production source `strategies/exit/trailing_stop.py` v0.2.0 located; parameters locked at Helios HEAD SHA `edd42b14d1d5f2c858730ee140cbd7b5683b2d0a` with five independent textual confirmations of `multiplier = 2.0` (module constant + 4 instantiation sites + monitoring-path hard-coded coefficient). ATR window = 14 from `features.technical.add_atr` (default `period=14`) confirmed via three independent references (`trend_pullback/types.py`, `trend_pullback/signal_generator.py`, `execution/stop_logic.py` docstring). OI-3 (RegimeExit handling in E1 evaluation) resolved as interpretation A: E1 evaluation excludes RegimeExit to preserve P6-INV-001 single-variable invariance — ARM_B's Phase 5 baseline methodology (fixed 20td paper-price NAV reconstruction) does not include RegimeExit, so including it in E1 would simultaneously vary two exit rules. §10.3 pre-registered design list updated with E1 parameter freeze. All other content (objective, baseline, E2–E4 parameters, gates, P6-INV-001/002, snapshot, deliverables) unchanged from v0.1.0.|

**Phase:** 6 (Exit Policy Evaluation)
**Parent verdicts:**
  - `research/r8_phase5_configuration_report.md` v1.0.2 — LOCKED
  - `research/helios_research_roadmap.md` v0.1.1 — LOCKED
**Owned followup:**
  - `research/r8_phase5_followup_001_spec.md` v1.0.0 — LOCKED / EXECUTION SPEC
    (authorisation: EXECUTE / PARALLEL / NON-BLOCKING) — see §7
**Snapshot:** L1 (Phase 5 `daily_price_adj` snapshot as of 2026-06-08)
**Codebase reference:** Helios HEAD `edd42b14d1d5f2c858730ee140cbd7b5683b2d0a`
  at E1 parameter freeze time (2026-06-19)

---

## 1. Objective

Phase 6 asks one pre-registered research question:

> Can any adaptive exit policy, applied on top of the ARM_B baseline,
> materially reduce capital occupancy without degrading Low-Uplift
> risk-adjusted performance below the ARM_B baseline?

This question is the structural successor to Phase 5. Phase 5 §9.2
established that the binding constraint on R8 deployable capacity is
capital occupancy (Arm B Low-Uplift admission = 17.5%; 82.5% of
eligible signals rejected due to capital lock-up, not signal quality).
Arm B improves selection within the fixed 20td hold; it does not relax
the hold itself. ARM_C demonstrated that uniform shorter holding
relaxes the constraint mechanically (+14.83pp admission, robust) but at
a Sharpe cost that is not statistically distinguishable from noise
(Phase 5 §7 P5-3, §6.2). The hypothesis Phase 6 tests is that
**state-conditional** exit can release capital from underperforming
positions early while permitting strong positions to run toward 20td.

### 1.1 Single-variable intervention (core invariance principle)

Phase 6 is structurally a **single-variable intervention study**.
Only the exit contract varies across arms. Every other element of the
Helios portfolio construction pipeline is frozen at the ARM_B
specification:

```
Frozen (identical to ARM_B):
    universe construction
    signal generation (R8 MA5 momentum)
    entry ranking (RS-60d top quintile within signal date)
    admission rule (10-position slot cap, 10% per-position cap)
    position sizing
    slippage / paper-price NAV reconstruction methodology
    20td hard ceiling on holding period

Variable:
    exit decision rule (one of: ARM_B fixed exit, E1, E2, E3, E4)
```

Any candidate that violates this invariance is disqualified before
evaluation. This requirement (P6-INV-001) is the strongest constraint
in the SPEC: if it is violated, the study no longer estimates exit-
policy effect but a confounded sum of effects, and the Phase 6 verdict
is meaningless.

### 1.2 What Phase 6 does not do

Phase 6 does **not**:

- Modify entry ranking, sizing, or universe.
- Optimise exit-policy parameters (D2 from drafting decisions).
- Authorise paper-trading modification. Phase 6 is research only.
- Re-validate the R8 signal edge (settled in Phase 1).
- Re-validate ARM_B selection (settled in Phase 5 v1.0.2).
- Address out-of-sample persistence. Bootstrap CI behaviour from
  Phase 4–5 is expected to recur.

---

## 2. Baseline

**Phase 6 baseline:** ARM_B (20td + RS-60d ranking).

ARM_B is frozen at its Phase 5 specification and is not re-estimated in
Phase 6. The Phase 5 v1.0.2 §4.2 metrics on the L1 snapshot are the
operative reference:

| Metric (Low-Uplift) | ARM_B value |
|---|---|
| Sharpe | 2.204 |
| Annualised Return | 50.22% |
| Annualised Volatility | 22.79% |
| MaxDD | 17.31% |
| Calmar | 2.901 |
| Admission rate | 17.5% |

All Phase 6 gates (§6) are computed as deltas against these ARM_B
values, not against the Phase 3 baseline or against Arm A.

ARM_C is **not** a Phase 6 baseline. Per Phase 5 v1.0.2 §6.3, ARM_C is
reclassified as CAPACITY_DEMONSTRATED / SHARPE_UNRESOLVED and serves
only as a capacity reference, not a candidate.

---

## 3. Exit Candidates

Phase 6 pre-registers four exit candidates. All candidates are
evaluated under the §1.1 invariance principle: only the exit decision
differs from ARM_B.

### 3.1 Universal exit-contract constraints

All four candidates obey the following structural rules:

1. **Hard ceiling:** every position exits no later than 20 trading days
   after entry. Adaptive exits trigger on or before this ceiling.
   Effective holding = min(adaptive_signal_day, 20td).
2. **Decision and execution timing:** exit signal evaluated at end of
   trading day t; exit executed at open of day t+1, with the same
   paper-price slippage convention used for ARM_B. No intraday
   adaptive exits in Phase 6.
3. **No re-entry within signal cycle:** a position exited adaptively
   cannot be re-admitted on a subsequent R8 signal until the next
   signal date independent of the exit. ARM_B already obeys this.
4. **Slot release:** the slot is released for admission of new
   candidates starting day t+1 (i.e., the slot is countable as
   "available" for the t+1 admission decision).

### 3.2 E1 — ATR Trailing Exit (frozen parameters)

**Production source:** `strategies/exit/trailing_stop.py` v0.2.0
  (file-level version timestamp 2026-05-31, three weeks before
  Phase 6 SPEC v0.1.0 drafting on 2026-06-19)
**Helios HEAD SHA at parameter freeze:** `edd42b14d1d5f2c858730ee140cbd7b5683b2d0a`
**Auxiliary references (cross-module confirmation of `multiplier = 2.0`):**

| Reference | Evidence |
|---|---|
| `strategies/exit/trailing_stop.py:43` | `ATR_STOP_MULTIPLIER = 2.0` (module constant) |
| `strategies/exit/trailing_stop.py:46` | `__init__(self, multiplier: float = ATR_STOP_MULTIPLIER)` (default arg) |
| `backtest/round_trip.py:185` | `[RegimeExit(), TrailingStop()]` — instantiation with no override |
| `backtest/portfolio_simulator.py:258` | `[RegimeExit(), TrailingStop()]` — instantiation with no override |
| `scripts/run_exit_scan.py:65` | `[RegimeExit(), TrailingStop(), TimeStop()]` — instantiation with no override |
| `scripts/run_backtest.py:184` | `"Exit: RegimeExit(priority=1) → TrailingStop(2*ATR)"` (docstring) |
| `execution/stop_logic.py:82` | `trailing_stop = max_close_since_entry - 2.0 * entry_atr` (monitoring-path hard-coded coefficient, independent of `TrailingStop` class) |

The cross-module hard-coded coefficient in `execution/stop_logic.py`
is the strongest structural confirmation: the monitoring path computes
the same stop level as the exit decision path, and any silent
re-parameterisation of one side would diverge from the other and
produce live monitoring incidents.

**Frozen decision rule:**

```
stop_price_t = max_close_since_entry_t - 2.0 * entry_atr
where entry_atr = ATR(14) at the position's signal date, frozen
                  for the position's lifetime.
exit at open of day t+1 if close_t <= stop_price_t
```

**Frozen parameters:**

| Parameter | Value | Source |
|---|---|---|
| `multiplier` | 2.0 | 5 independent references above; locked at HEAD `edd42b1` |
| ATR window | 14 | `features/technical.py:92` `add_atr(df, period: int = 14)`; confirmed by `strategies/trend_pullback/types.py:48` (`# ATR(14) on as_of`), `strategies/trend_pullback/signal_generator.py:43` (`# ATR(14) at signal time`), `execution/stop_logic.py:76` (`ATR14 at entry date. Frozen`) |
| ATR basis | `entry_atr` (frozen at signal date) | `strategies/exit/trailing_stop.py` v0.2.0 docstring §11 (rationale recorded); `execution/stop_logic.py:76` independent confirmation |
| ATR convention | Per `features.technical.add_atr` at HEAD `edd42b14d1d5f2c858730ee140cbd7b5683b2d0a` | Audit-by-SHA; convention internal to production code, no behavioural impact on E1 evaluation provided `entry_atr` is consistent across positions |
| Trailing reference price | `max_close_since_entry` (updated externally by `run_exit_scan` before this rule fires) | `strategies/exit/trailing_stop.py:60` |
| Trigger | `close <= stop_price` (close-based; no intraday high/low) | `strategies/exit/trailing_stop.py:64` |
| ATR `atr` rolling argument | NOT used in stop calculation | `strategies/exit/trailing_stop.py:26–28` docstring |

**Phase 6 evaluation context (single-variable invariance, P6-INV-001):**

Per §1.1, E1 evaluation applies TrailingStop as the **sole** adaptive
exit rule on top of the 20td hard ceiling. Specifically:

- Effective holding = `min(TrailingStop_trigger_day, 20td_ceiling)`.
- **RegimeExit is EXCLUDED from E1 evaluation.** Production exit stack
  is `[RegimeExit, TrailingStop, TimeStop]` (confirmed via
  `scripts/run_exit_scan.py:65` and `scripts/run_backtest.py:184`),
  but ARM_B's Phase 5 baseline methodology (fixed 20td paper-price NAV
  reconstruction, Phase 5 v1.0.2 §3) does not include RegimeExit.
  Including RegimeExit in E1 would simultaneously vary two exit rules
  (TrailingStop + RegimeExit) and violate P6-INV-001 single-variable
  invariance. RegimeExit is part of the production exit framework but
  not part of the research baseline; isolating it is correct here.
- The `atr` rolling parameter received via the ExitRule interface is
  ignored (per `strategies/exit/trailing_stop.py` v0.2.0 docstring);
  only `entry_atr` is used.

**Justification for no-optimisation claim (P6-INV-002 evidence):**

`strategies/exit/trailing_stop.py` v0.2.0 was committed in response to
a separate review cited in its docstring as `"Reviewer §37: no
adaptive"`. The file-level version timestamp is **2026-05-31**;
Phase 6 SPEC v0.1.0 was drafted on **2026-06-19**. The
`multiplier = 2.0` value and `entry_atr` basis predate Phase 6 SPEC by
three weeks and were not selected with reference to Phase 6
evaluation outcomes. The same `2.0` coefficient appears independently
in `execution/stop_logic.py` (monitoring-path hard-coded constant) —
a cross-module structural constraint that would diverge from
production behaviour if either side were tuned in isolation,
providing redundant structural evidence against silent
re-parameterisation. This satisfies P6-INV-002 (no in-sample tuning)
with the strongest evidence chain available among the four
candidates.

### 3.3 E2 — MA20 Failure Exit

**Decision rule:** exit when day-t close is below the 20-day simple
moving average for **two consecutive trading days**. Exit executes at
day-(t+1) open.

**Pre-registered parameters:** confirmation lag `m = 2`. SMA window
`w = 20`. Both values are pre-registered before evaluation.

**Justification for parameter choice:** SMA(20) is the canonical
medium-term moving average and is structurally aligned with ARM_B's
20-day hold ceiling. The 2-day confirmation lag is the standard
trend-following anti-whipsaw default (Faber 2007, Wilder 1978 use 1-day
"close below" rules but Phase 6 errs toward the more conservative
2-day variant to avoid noise-driven exits). Both values are chosen
from convention, not from Phase 3–5 data inspection.

### 3.4 E3 — RS Deterioration Exit

**Decision rule:** exit when day-t RS_60d (`beta_adj_rs_60d`) rank of
the position within the trading universe falls below the **50th
percentile**.

**Pre-registered parameters:** rank threshold = 50th percentile
(median). Rank computed over the same trading universe used by ARM_B
entry ranking.

**Justification for parameter choice:** ARM_B admits positions whose
RS_60d rank is in the top quintile (top 20%) at entry. The natural
**symmetric exit** is when the position falls below the median (bottom
50%), i.e., halfway from the entry threshold to the universe median.
This is a structurally motivated choice, not a data-fit. Alternative
thresholds (40th, 60th percentile, fall-out-of-top-quintile) are
deferred to a potential Phase 6A parameter study and are out-of-scope
for Phase 6.

### 3.5 E4 — Donchian Exit

**Decision rule:** exit when day-t close is at or below the lowest
close of the prior `n` trading days (excluding day t itself).

**Pre-registered parameters:** lookback `n = 10`.

**Justification for parameter choice:** 10-day Donchian low is the
classic Turtle Trading short-term exit (Faith 2003, Curtis Faith Way
of the Turtle). For a 20td-ceiling strategy, the 10-day Donchian sits
at exactly half the ceiling and is the conventional shorter trailing
exit. The value is taken from documented literature, not optimised
on Phase 3–5 data.

### 3.6 Candidate summary

| ID | Name | Type | Parameter(s) | Source |
|---|---|---|---|---|
| BL | ARM_B baseline | Fixed-hold | hold = 20td | Phase 5 v1.0.2 |
| E1 | ATR Trailing | State-conditional | `multiplier=2.0`, ATR(14), `entry_atr` basis | Production code `trailing_stop.py` v0.2.0 (pre-Phase-6, locked at HEAD `edd42b1`) |
| E2 | MA20 Failure | State-conditional | SMA(20), confirmation = 2 days | Trend-following convention |
| E3 | RS Deterioration | State-conditional | rank threshold = 50th pctile | Symmetric to ARM_B entry quintile |
| E4 | Donchian | State-conditional | lookback n = 10 | Turtle/Faith literature |

---

## 4. Fixed Parameters / No Optimisation

**P6-INV-002 (no in-sample tuning).** Phase 6 evaluates each candidate
under exactly one pre-registered parameter set (§3.2–§3.5). No
parameter search, walk-forward optimisation, regime-conditional
parameter selection, or post-hoc parameter substitution is permitted
within Phase 6. This restriction applies to all four candidates
without exception.

If post-Phase-6 analysis suggests that a candidate's failure or
success was parameter-driven, the appropriate response is a new SPEC
(Phase 6A: parameter refinement, scope-limited to candidates that
passed §6 gates with non-trivial margin). It is **not** to retroactively
adjust Phase 6 parameters.

**Why this restriction matters.** The Phase 1–5 chain has accumulated
governance gates without family-wise error correction. Permitting
parameter sweeps within Phase 6 would compound this by giving each
candidate multiple chances to pass, inflating false-positive rates
substantially. The fixed-parameter rule is the primary defence against
in-sample optimisation contamination of the Phase 6 verdict.

---

## 5. Evaluation Framework

### 5.1 Scenarios

Both scenarios are evaluated, consistent with Phases 3–5:

- **Full Sample** (2021-09-13 to 2025-08-08): supplementary.
- **Low-Uplift** (Segments 2+3, 2023-10-24 to 2025-08-08): **primary**
  stress environment per Phase 3 §4.3. All gate decisions are made on
  Low-Uplift.

### 5.2 Metrics

Per-candidate metrics, computed identically to Phase 5 v1.0.2 §4:

```
Sharpe              annualised (252-day)
Ann. Return         annualised CAGR
Ann. Volatility     annualised std of daily returns
MaxDD               peak-to-trough drawdown on equity curve
Calmar              Ann. Return / MaxDD
Admission rate      slots scheduled / signals eligible
Mean holding days   mean effective hold across exited positions
Mean holding pct of ceiling   mean (effective_hold / 20)
```

The last two metrics are Phase-6-specific and characterise the degree
of holding-period truncation each candidate produces; they are
diagnostics, not gate criteria.

### 5.3 Multi-effect entanglement (pre-registered warning)

Each adaptive exit candidate produces a Phase 6 outcome that mixes
**two distinct effects** which Phase 6 evaluation cannot fully
disentangle:

1. **Position-level return distribution shift.** Truncating the hold
   from 20td to some shorter effective hold changes the realised return
   per position. Some early exits avoid drawdowns (positive
   contribution); some early exits cut profitable positions short
   (negative contribution).
2. **Selection effect at the portfolio level.** Faster slot release
   admits more signals, which then have their own return realisations.
   The admitted-signal pool composition changes.

Phase 6 verdict reports the **combined** effect at the portfolio NAV
level. Attribution between (1) and (2) requires position-level
counterfactual analysis (e.g., "what if this position had been held to
20td?") which is itself non-trivial because slot occupancy is
state-dependent. This decomposition is out-of-scope for Phase 6 and
may be a Phase 6B research topic if any candidate passes §6 gates.

### 5.4 Bootstrap (supplementary)

For each candidate, two-sample stationary block bootstrap on
Δ_A3 (challenger vs ARM_B) at each candidate's effective horizon set,
with parameters consistent with Phase 5: `B = 5000`, `L = max(5, h)`.
Bootstrap is supplementary, not a gate criterion, consistent with the
Phase 3–5 finding that Low-Uplift bootstrap CIs cross zero for all
arms (Phase 5 §8.3).

**Note on bootstrap design.** Position-level paired bootstrap is not
used because adaptive exits change slot timing, which changes
subsequent admission decisions; the paired structure breaks down after
the first adaptive exit. The stationary-block bootstrap on daily NAV
returns is the same convention used in Phase 5 §3.3 and is the
appropriate choice given this structural feature.

---

## 6. Gates

All gates are computed as `metric(candidate, LU) − metric(ARM_B, LU)`
on the L1 snapshot. Gates are **governance heuristics**, not
statistical significance criteria (consistent with Phase 5 v1.0.2
§3.2 D2 rationale and §7 P5-3 wording correction).

### 6.1 Gate definitions

| Gate | Criterion | Threshold | Applies to |
|---|---|---|---|
| P6-G1 | Sharpe Δ vs ARM_B (LU) | ≥ −0.15 | E1, E2, E3, E4 |
| P6-G2 | MaxDD Δ vs ARM_B (LU) | ≤ +3pp | E1, E2, E3, E4 |
| P6-G3 | Admission Δ vs ARM_B (LU) | ≥ +5pp | E1, E2, E3, E4 |

### 6.2 Threshold justifications

**P6-G1 (Sharpe, −0.15 threshold).** ARM_B LU Sharpe is 2.204. A −0.15
threshold sets the floor at 2.054, which is still substantially above
the Arm A LU Sharpe of 1.569 (Phase 5 baseline) and above the Phase 3
P3-G1 reference threshold. The threshold is wider than Phase 5's
P5-G1 (−0.10) because the ARM_B baseline is materially higher and a
small fraction of that high Sharpe is a reasonable allowance for
adaptive-exit selection cost. Under the iid Lo (2002) approximation
with ARM_B LU Sharpe = 2.204 and T ≈ 460 trading days:

```
SE(Sharpe_ARM_B) ≈ sqrt((1 + 2.204^2 / 2) / 460) ≈ 0.080
```

The −0.15 threshold is approximately 1.9 × SE(Sharpe_ARM_B), which is
similar in spirit to a 2σ tolerance band. This calibration is a
governance noise-floor reference, not a formal inference procedure.

**P6-G2 (MaxDD, +3pp threshold).** Mirrors Phase 5 P5-G2 unchanged.
ARM_B MaxDD (LU) is 17.31%; threshold permits up to 20.31%, still
below Arm A's 20.54%.

**P6-G3 (Admission, +5pp threshold).** ARM_B LU admission is 17.5%.
A +5pp threshold requires the candidate to lift admission to at least
22.5%. This is a deliberately moderate bar: it sets the minimum
capacity gain Phase 6 considers research-relevant. Phase 5 P5-G3 used
+10pp (Arm C achieved +14.83pp) but P5-G3 was applied only to the
candidate that explicitly halved fixed holding period; adaptive exits
will produce smaller, distribution-dependent capacity gains, and a
+10pp threshold would be implausibly aggressive. The +5pp threshold
preserves the "capacity must be meaningful" governance intent without
requiring matching the ARM_C ceiling.

### 6.3 Candidate verdict rules

For each candidate independently:

| Verdict | Criterion |
|---|---|
| **SELECTED** | P6-G1 ✓ AND P6-G2 ✓ AND P6-G3 ✓ |
| **CHARACTERISED** | At least one but not all of {P6-G1, P6-G2, P6-G3} pass |
| **REJECTED** | None of the three gates pass |

**Multi-arm verdict aggregation.** Candidates are evaluated
**independently** against ARM_B. Phase 6 does not pre-register a
cross-candidate ranking or tiebreak rule. If multiple candidates
achieve SELECTED, all are reported as Phase 6 deployment candidates
and a subsequent SPEC (Phase 6A) is responsible for selection among
them. If exactly one candidate achieves SELECTED, that candidate is
the unique Phase 6 deployment candidate. If no candidate achieves
SELECTED, the Phase 6 verdict is `NO_CANDIDATE` and exit-policy
research is exhausted under the current scope; future work would
require new SPEC authorisation (e.g., parameter refinement, alternative
exit families).

**Marginal-margin discipline.** Following Phase 5 v1.0.2 §7 P5-3, any
candidate that passes a gate with margin smaller than 2 × SE(metric)
under the Lo approximation must be labelled `SELECTED (marginal P6-Gn)`
in the verdict. The marginal label propagates into the Phase 6 report.

### 6.4 Family-wise error (acknowledged limitation)

Phase 6 evaluates four challengers against one baseline. Under a
1-tailed governance gate per candidate, the probability that at least
one challenger passes a single gate purely by sampling noise is
materially higher than the per-candidate gate margin suggests. Phase 6
**does not apply** Bonferroni-style correction because:

1. Gates are explicitly governance heuristics, not statistical tests
   (consistent with Phase 5 §3.2).
2. The four candidates differ structurally (different exit families),
   so the implicit assumption of independent identical hypotheses does
   not hold cleanly.
3. The downstream consumer of this study — Phase 6A or a deployment
   SPEC — will require additional out-of-sample evidence (paper-
   trading forward returns under the Track B framework) before any
   SELECTED candidate is deployed, providing a second filter.

This limitation is recorded explicitly and is not eliminated.

---

## 7. P5-FOLLOWUP-001 Ownership

**Decision: EXECUTE (parallel, not blocker).**

Per `research/r8_phase5_followup_001_spec.md` v0.1.1 §6, the Phase 6
SPEC selects EXECUTE.

**Rationale (from drafting decisions D4):**

1. Incremental cost is minimal — three of the four 2×2 cells already
   exist on the L1 snapshot; only `C-FF-10` (10td + FIFO) requires
   evaluation.
2. Working Hypothesis P5-4 is referenced across the Phase 5 report,
   roadmap, and followup SPEC; leaving it unresolved indefinitely
   creates accumulating documentation debt.
3. Resolving P5-4 after Phase 6 begins would require a fresh snapshot
   and a four-cell rerun (followup SPEC §4.1 Option L2), which is more
   expensive than the current one-cell extension under L1.

**Execution arrangement.**

- P5-FOLLOWUP-001 has graduated from SPEC SKELETON (v0.1.1) to LOCKED
  execution SPEC v1.0.0 under separate document
  (`research/r8_phase5_followup_001_spec.md` v1.0.0). This Phase 6
  SPEC authorises that graduation; the execution SPEC details runner,
  artifact, and execution-log requirements.
- P5-FOLLOWUP-001 execution is **parallel** to Phase 6 execution. The
  Phase 6 evaluation does not depend on the followup's outcome. If the
  followup completes first and PROMOTES P5-4 to finding, Phase 6 SPEC
  is amended (v0.1.1) to reference the finding in §1; if the followup
  REJECTS P5-4, Phase 6 SPEC §1 motivation language about "Phase 5
  Arm C did not preserve Sharpe" is unaffected (the level-effect
  observation stands regardless of interaction-effect resolution).
- If the followup outcome is INCONCLUSIVE, Working Hypothesis P5-4
  remains as-is and no Phase 6 SPEC amendment is needed.

**What this decision does not authorise.** It does not authorise
modifying Phase 5 v1.0.2 verdict, ARM_B SELECTED, or ARM_C
reclassification under any followup outcome. These are LOCKED at
Phase 5 v1.0.2.

---

## 8. Snapshot Locking

**Decision: L1 — Phase 5 `daily_price_adj` snapshot as of 2026-06-08.**

Per drafting decisions D5, Phase 6 uses the Phase 5 snapshot to
preserve cross-phase comparability and eliminate snapshot-shift
confounding between ARM_B (the baseline against which all gates are
computed) and the Phase 6 challengers.

### 8.1 Reproducibility check (execution prerequisite)

Before Phase 6 evaluation begins, the execution team must verify that
the Phase 5 snapshot is reproducible from `data/_storage/helios.duckdb`
as of 2026-06-08. The verification is:

1. Compute Arm A LU Sharpe on the current snapshot.
2. Compare against the Phase 5 v1.0.2 §4.1 recorded value (1.569).
3. The tolerance is the same Phase 5 lineage-gate tolerance (±0.050).

If reproducibility fails, Phase 6 cannot proceed under L1. Two
contingency paths:

- **L2 fallback:** switch to a fresh snapshot at execution time. ARM_B
  reference values must be recomputed on the fresh snapshot before any
  Phase 6 gate evaluation. The recomputed ARM_B values become the new
  Phase 6 baseline reference, replacing §2 values. P5-FOLLOWUP-001
  must also switch to L2 with full four-cell rerun.
- **Snapshot reconstruction:** attempt to reconstruct the L1 snapshot
  from upstream sources (FinMind/Shioaji corporate action records) and
  retry verification. This is the preferred contingency if technically
  feasible; failure on this path triggers the L2 fallback.

### 8.2 Lineage-gate override governance (forward requirement)

Per Phase 5 v1.0.2 §9.4 item 5, any Phase 6 lineage-gate trigger of
magnitude comparable to the Phase 5 +0.120 full-sample Sharpe shift
must require:

1. Divergence localisation (which dates / which symbols).
2. **Independent attribution check** — symbol-level reconciliation
   against TWSE source records, or cross-validation against a second
   adj-price source. Plausibility arguments alone are insufficient.
3. Documented evidence chain in the Phase 6 execution log.

Reference baseline updates without satisfying (1)–(3) are not
permitted under Phase 6 governance.

---

## 9. Deliverables

### 9.1 Execution artifacts

| Artifact | Location | Purpose |
|---|---|---|
| `scripts/run_phase6_evaluation.py` v0.1.0 | scripts/ | Runner producing E1–E4 outputs against ARM_B baseline |
| Per-candidate evaluation outputs | `data/_storage/r8_phase6/v0.1.0/` | Raw NAV time series, position-level exit timing, metric summaries |
| Bootstrap outputs | Same | Stationary-block bootstrap on Δ_A3 per candidate |
| Gate evaluation table | Same | P6-G1 / P6-G2 / P6-G3 per candidate, with margins |

### 9.2 Report artifact

`research/r8_phase6_evaluation_report.md` v1.0.0 (LOCKED on
completion). Required sections (mirroring Phase 5 v1.0.2 structure):

```
1. Executive Summary
2. Objectives (cite this SPEC)
3. Experimental Design (per §1.1 / §3 / §5)
4. Candidate Results (one per E1–E4 + ARM_B reference table)
5. Bootstrap (supplementary)
6. Gate Evaluation
7. Findings + Working Hypotheses
8. Limitations (including §6.4 family-wise error, §5.3 entanglement)
9. Phase 7+ Implications
10. Conclusion
```

### 9.3 SPEC amendment artifacts (conditional)

- If P5-FOLLOWUP-001 PROMOTES or REJECTS P5-4 before Phase 6 report
  LOCK: amend this SPEC to v0.1.1 with §1 motivation update; amend
  Phase 5 v1.0.2 report to v1.1.0 with finding-status update.
- If any Phase 6 candidate is marked `SELECTED (marginal)`: the Phase 6
  report must explicitly justify marginal status with sampling-error
  context per §6.3.

---

## 10. Governance

### 10.1 Document chain

| Document | Version | Status |
|---|---|---|
| `research/r8_phase1_interim_findings.md` | v1.0.0 | CONFIRMED |
| `research/r8_phase3_risk_report.md` | v1.0.1 | LOCKED |
| `research/r8_phase4_optimisation_report.md` | v1.0.0 | LOCKED |
| `research/r8_phase5_spec.md` | v0.1.0 | LOCKED |
| `research/r8_phase5_configuration_report.md` | v1.0.2 | LOCKED |
| `research/r8_phase5_price_snapshot_refresh_note.md` | v0.1.0 | GOVERNANCE NOTE |
| `research/r8_phase5_followup_001_spec.md` | v1.0.0 | LOCKED / EXECUTION SPEC (parallel) |
| `research/helios_research_roadmap.md` | v0.1.1 | LOCKED |
| `research/r8_phase6_spec.md` | v0.1.1 | **THIS DOCUMENT — LOCKED** |

### 10.2 Authorisation

Phase 6 evaluation is authorised by this SPEC. v0.1.0 received LOCK
approval on 2026-06-19; v0.1.1 LOCKED on the same day applies only
the §3.2 E1 parameter freeze under §10.3 pre-registered design (no
substantive design change). Further amendments require new minor
version (v0.1.x) and may amend only under the §9.3 conditional cases
(P5-FOLLOWUP-001 outcome, marginal-candidate disclosure, E1
contingency if production code changes before evaluation). Any
substantive design change (new candidate, parameter modification, gate
threshold revision, snapshot convention change) requires v0.2.0+ and
forfeits pre-registration for the modified elements.

### 10.3 Pre-registered design decisions (immutable post-LOCK)

The following Phase 6 design decisions are pre-registered and may not
be modified post-LOCK without invalidating the Phase 6 verdict:

- **P6-D1:** Multi-arm champion-vs-challengers structure (§1, §3).
- **P6-D2:** No parameter optimisation (§4, P6-INV-002).
- **P6-D3:** Gates relative to ARM_B (§6).
- **P6-D4:** P5-FOLLOWUP-001 EXECUTE in parallel (§7).
- **P6-D5:** L1 snapshot (§8).
- **P6-INV-001:** Single-variable intervention — exit only, all else
  frozen at ARM_B (§1.1).
- **P6-INV-002:** No in-sample parameter tuning within Phase 6 (§4).
- **Pre-registered parameter values for E1–E4** (§3.2–§3.5). E1
  parameter freeze applied in v0.1.1: `multiplier = 2.0`, ATR(14),
  `entry_atr` basis, anchored at Helios HEAD
  `edd42b14d1d5f2c858730ee140cbd7b5683b2d0a`. E1 evaluation excludes
  RegimeExit per single-variable invariance (§3.2 interpretation A).
- **Pre-registered gate thresholds and verdict rules** (§6.1, §6.3).
- **Pre-registered scenario set** (§5.1 Full Sample + Low-Uplift, with
  Low-Uplift as primary).

Any modification to the above post-LOCK requires a new SPEC version
(v0.2.0+) and forfeits Phase 6's pre-registration discipline for the
modified elements.

### 10.4 What Phase 6 does not establish

- That any SELECTED candidate produces superior out-of-sample returns.
- That LOCK of this SPEC authorises paper-trading modification.
- That gate passage at Phase 6 implies statistical significance.
- That Phase 6 findings persist on future `daily_price_adj` snapshots.
- That non-pre-registered exit-policy parameters are validated.
- That the family-wise error from evaluating four challengers has been
  controlled (§6.4 acknowledged).

---

*End of r8_phase6_spec.md v0.1.1*
