# 21D Win Rate Feature Specification — v0.1.0 (LOCKED)

**Feature ID:** `win_rate_21d`
**Track:** C
**Status:** SPEC_LOCKED (Gate A1)
**Owner:** Veronica
**Repository:** Helios (`~/projects/helios`)
**Universe (median producer, L2):** `listed_market_daily_price_adj`
                                     (PIT-filtered via `security_lifecycle`)
**R1 evaluation universe (L1):** R8 `treatment_1` signal-date panel
                                  (per `docs/research/ud_ratio_21d_r1_prereg.md`
                                  §3 R1-U1, LOCKED at `13ed404`)
**Governance Anchor:** `docs/research/ud_ratio_21d_r1_pre_execution_audit.md`
                       (`abc2d86`, IN PROGRESS)

---

## 1. Scope

[Addresses A1-C5 (Step 0 vs Step 1 separation) and layer-distinction clarity.]

This document specifies the `win_rate_21d` feature at the conceptual,
mathematical, lineage, and producer-substrate level. It is the **first lock**
of all internal design properties of `win_rate_21d` (the R1 pre-registration
locks only the consumption interface; see §1.3).

### 1.1 What this spec locks (Gate A1, v0.1.0)

[Verified per audit memo §7.2 Exit Criteria + D-008.]

- Feature identity and naming (§2).
- Mathematical contract: relative-outperformance frequency over a trailing
  21-trading-day window (§3).
- PIT contract: two-layer lineage (median producer + feature consumer) (§4).
- Producer contract: cross-sectional median producer as first-class artifact
  (§5).
- Output schema: panel column names, dtypes (preliminary), null semantics
  (§6).
- Acceptance criteria split: Gate A1 (spec lock) vs Gate A2 (implementation)
  vs Gate A3 (prereg amendment) (§7).
- Test strategy: PIT test identifier enumeration; bodies deferred to A2 (§8).
- Governance citation registry (§9).
- Future extensions (§10).

### 1.2 What this spec does NOT lock (Deferred)

[Verified per audit memo §1.3 / §1.4 + D-008 70–80% completeness target.]

- Implementation: function signatures, SQL recipes, Polars expressions
  (Gate A2).
- Numerical thresholds beyond `MIN_OBS` and `WINDOW`, per A1-C6
  (e.g., `MIN_CROSS_SECTION_OBS_PER_DATE` deferred to Gate A2
  lock-before-build).
- PIT test bodies; only identifiers and concerns are enumerated here
  (A1-C4).
- Empirical validation of `MIN_OBS` choice (Step 2 sensitivity analysis).
- Alpha hypothesis, correlation analysis, backtest results
  (out of scope for any Step 0/1 work).

### 1.3 Layer distinction (binding governance)

[Verified per `ud_ratio_21d_r1_prereg.md` §3 R1-U1 + §2 Governance Boundary.]

The R1 pre-registration locks the **R1 evaluation universe** at
`R8 treatment_1 signal-date panel only`. That contract governs which
`(stock_id, date)` rows participate in the R1 cross-sectional Spearman
correlation. It does **NOT** govern the internal universe used to compute
the cross-sectional median benchmark inside `win_rate_21d`.

This spec governs the latter. The two layers are distinct:

| Layer | Concern                                                  | Locked by                                                 |
| ----- | -------------------------------------------------------- | --------------------------------------------------------- |
| L1    | Where downstream consumers (e.g., R1) evaluate the feature | `ud_ratio_21d_r1_prereg.md` §3 R1-U1                      |
| L2    | Source of cross-sectional median benchmark inside feature | This spec §3.2 + §5.2                                     |

This distinction is **normative**. Future R1' or other consumer studies may
further restrict L1 without amending this spec; any change to L2 requires a
spec amendment with version bump (§9.3).

### 1.4 Relationship to `ud_ratio_21d_spec.md`

[Verified per audit memo ER-6.]

`docs/features/ud_ratio_21d_spec.md` v0.1.4 is used as **architectural
template only**. Section structure, normative wording conventions, PIT test
identifier scheme, Step 0/Step 1 acceptance split, and version history
format are inherited. No mathematical content, threshold values, column
names (other than `win_rate_21d` itself, locked by prereg), or design
decisions from `ud_ratio_21d` are inherited semantically.

---

## 2. Identity

[Establishes feature ID precondition for §3 and §6.]

### 2.1 Feature ID and naming

[Verified per `ud_ratio_21d_r1_prereg.md` §5 R1-U3 + §6 R1-U4.]

| Property                    | Value                                                       |
| --------------------------- | ----------------------------------------------------------- |
| Feature ID                  | `win_rate_21d`                                              |
| Output column name (panel)  | `win_rate_21d` (verbatim — prereg-locked)                   |
| Family                      | Cross-sectional aggregate, relative-outperformance frequency |
| Granularity                 | Per `(stock_id, date)` row                                  |

### 2.2 Conceptual definition

[Derived from D-001 + feature naming + cross-sectional aggregate
architecture per D-009.]

`win_rate_21d` measures the fraction of valid trading days within a trailing
21-trading-day window on which a stock's daily simple return strictly
exceeded the cross-sectional median daily simple return computed over the
eligible universe on the **same day**.

The feature is a **double-reduction statistic**:

- Reduction 1 (cross-sectional, daily): for each trading day `s`, the
  cross-sectional median of daily simple returns across the eligible
  universe at `s`. See §3.2–§3.3.
- Reduction 2 (time-series, per stock): the fraction over the trailing
  W-day window where the per-stock daily return exceeded the date-`s`
  cross-sectional median. See §3.4–§3.5.

This contrasts with single-reduction features (e.g., `ud_ratio_21d`) that
reduce only along the time axis. The additional cross-sectional reduction
layer is the structural reason `win_rate_21d` requires a first-class
Producer Contract (§5) per D-009.

### 2.3 Information-content claim

[Deferred to Step 2 / R2 or later analysis.]

Whether `win_rate_21d` carries information orthogonal to magnitude momentum
or sign-frequency persistence is **NOT** claimed at v0.1.0. Such claims
belong to a separately pre-registered analysis. See
`ud_ratio_21d_r1_prereg.md` §6 R1-U4 for the parallel R1 Spearman
correlation between `ud_ratio_21d` and `win_rate_21d`.

---

## 3. Mathematical Contract

[Addresses A1-C2 (a) universe, (b) median PIT, (c) window inclusion of
signal date, (d) flat-equal handling, (e) MIN_OBS. A1-C6 restricts numerical
thresholds to `MIN_OBS` / `WINDOW`.]

### 3.1 Notation

- `t`: panel observation date. MUST be a trading day per the Taiwan trading
  calendar (§4.1).
- `i`: equity identifier (Taiwan ticker).
- `r_{i,s}`: daily simple return on adjusted close for stock `i` on day `s`,
  defined per §4.2 and valid per §4.3.
- `U_s`: eligible universe for the cross-sectional median at date `s`,
  defined in §3.2.
- `m_s`: cross-sectional median of `{r_{j,s} : j in U_s}`, defined iff
  `|U_s| >= MIN_CROSS_SECTION_OBS_PER_DATE` (value deferred to Gate A2;
  §3.7 + §5.3); else null.
- `W = 21`: trailing window length in trading days (LOCKED, §3.6).
- `S_{i,t}`: the set of trading days `s` with `t - W + 1 <= s <= t`
  (inclusive of `t`) for which BOTH `r_{i,s}` is valid AND `m_s` is defined.

### 3.2 Eligible universe `U_s` for the median (A1-C2(a))

[Derived from SD-1 confirmation + Helios-wide PIT-view convention
established via `SPEC-P1-DATA-REMEDIATION-v1`; `ud_ratio_21d_spec.md` §4.4
is cited only as the prior locked precedent of this Helios-wide pattern.]

The eligible universe `U_s` at date `s` is the set of stocks `j` such that:

1. `j` is present in `listed_market_daily_price_adj` at date `s`
   (the PIT view enforces IF-1 lifecycle filtering automatically, via the
   `security_lifecycle.market IN ('TWSE', 'TPEx')` join).
2. `r_{j,s}` is a valid daily return per §4.3.

Stocks for which `r_{j,s}` is undefined on day `s` (e.g., first listing day,
suspension recovery without a valid prior price) are excluded from `U_s` on
that day, but may re-enter on subsequent days.

`U_s` is **strictly broader than the R1 evaluation universe (L1)** by §1.3.

### 3.3 Cross-sectional median statistic (A1-C2(b))

[Derived from D-001 "relative-outperformance frequency" direction +
standard cross-sectional aggregation conventions.]

For each date `s` with `|U_s| >= MIN_CROSS_SECTION_OBS_PER_DATE`
(§5.3; value deferred to A2):

```
m_s = median({r_{j,s} : j in U_s})
```

The median is defined as the **standard sample median**, with the
following interpolation rule (LOCKED at Gate A1):

```
Let the elements of {r_{j,s} : j in U_s} be sorted ascending as
    r_{(1)} <= r_{(2)} <= ... <= r_{(N)}   where N = |U_s|.

If N is odd:
    m_s = r_{((N+1)/2)}                    (the single middle value)

If N is even:
    m_s = ( r_{(N/2)} + r_{(N/2 + 1)} ) / 2
                                            (arithmetic midpoint of the
                                             two central values)
```

Gate A2 implements this rule but does not redefine it. The arithmetic
midpoint convention (rather than lower / upper / linear-interpolation
variants) is adopted as part of the mathematical definition of this
specification.

For any date `s` with `|U_s| < MIN_CROSS_SECTION_OBS_PER_DATE`:
`m_s` is null, and date `s` does NOT contribute to any stock's `S_{i,t}`
(effectively excluded from all trailing windows containing `s`).

### 3.4 Per-day outperformance indicator (A1-C2(d))

[Derived from D-001 "outperformance" semantic + conservative
interpretation of strict comparison.]

For stock `i` on day `s` with both `r_{i,s}` valid and `m_s` defined:

```
win_{i,s} = 1   if r_{i,s} >  m_s
            0   otherwise   (includes the exact-tie case)
```

**Tie handling (flat-equal):** when `r_{i,s} == m_s` exactly, `win_{i,s} = 0`
(NOT credited as a win). Tie days DO count in the denominator `|S_{i,t}|`
(the observation existed; the stock simply did not strictly outperform).

**Rationale for strict (`>`) comparison:**

[Derived; not inherited from `ud_ratio_21d` `r > 0` decision, which
addresses a structurally different question (sign vs zero, not relative
position).]

A "relative-outperformance frequency" feature should not credit ties as
outperformance. Strict inequality is the conservative reading of D-001 and
is robust to floating-point edge cases. Exact ties are measure-zero under
continuous return distributions but DO occur in practice — particularly on
low-volume sessions when the cross-sectional median is at or very near zero
and many stocks have `r ≈ 0` from inactivity or low ticks. See §10.3 for
the acknowledged tie-inflation research risk.

### 3.5 Core formula (A1-C2(c) + A1-C2(e))

[Derived from §3.1–§3.4 and PIT-window convention.]

For each panel row `(i, t)` where `t` is a trading day:

```
S_{i,t} = { s : s is a trading day,
            t - W + 1 <= s <= t   (inclusive of t),
            r_{i,s} is valid (§4.3),
            m_s is defined (§3.3) }

win_rate_21d_{i,t} = ( sum_{s in S_{i,t}} win_{i,s} )  /  |S_{i,t}|

defined iff |S_{i,t}| >= MIN_OBS;  else null
```

**Window inclusion of signal date `t` (A1-C2(c)):**

[Derived from PIT consistency + Option II decision-date convention
established Helios-wide.]

The trailing window includes date `t` itself, because `r_{i,t}` and `m_t`
are determinable from end-of-day prices at `t close` — information that is
available when the feature is computed at end-of-day `t` (and consumed at
`t+1 open` per the Option II convention).

### 3.6 Locked numerical constants (A1-C6)

[Verified per A1-C6 + audit memo §7.2.]

```
WINDOW   = 21    # LOCKED at Gate A1
MIN_OBS  = 15    # LOCKED at Gate A1
```

| Constant   | Value | Rationale                                                                                                                                                                                                                                                                                                   |
| ---------- | ----- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `WINDOW`   | 21    | Derived from feature name (`win_rate_21d`); aligns with the Helios trailing-21-trading-day feature convention. Not empirically optimized.                                                                                                                                                                  |
| `MIN_OBS`  | 15    | Heuristic ~71% completeness floor (15/21). **NOT empirically optimized.** Step 2 may revisit via a parameterized `min_obs` sensitivity sweep.                                                                                                                                                              |

**Independence note:** the convergence with `ud_ratio_21d`'s `MIN_OBS = 15`
is **independently derived** from the same completeness-floor heuristic, not
inherited semantically from that spec. The convergence is unsurprising
because both features adopt the same `WINDOW = 21` and the same ~70%
heuristic floor — distinct decisions that happen to yield the same number.

### 3.7 Deferred numerical decisions

[Deferred per A1-C6 + F.3 option (ii) Gate A1 kickoff confirmation.]

```
MIN_CROSS_SECTION_OBS_PER_DATE  =  [Deferred to Gate A2 lock-before-build]
```

This constant defines the minimum eligible-universe count per date for
`m_s` to be defined. Its **role** is locked here (§3.3 and §5.3); its
**numerical value** is deferred to Gate A2 under the prereg §15
lock-before-look discipline, applied here as lock-before-first-producer-build.

A2 MUST lock this value before the first cross-sectional aggregation run.
Post-hoc adjustment after coverage inspection is FORBIDDEN.

---

## 4. PIT Contract

[Addresses A1-C2 (b) PIT semantics of median, (f) deterministic
reproducibility, with two-layer lineage per D-009 cross-sectional reduction
asymmetry.]

### 4.1 Trading calendar source

[Derived from Helios-wide convention; `ud_ratio_21d_spec.md` §12 is
architectural template only.]

The canonical trading calendar source is `market.trading_calendar`
(version `>= 0.2.0`). Window construction MUST use trading-day count, not
calendar-day count.

The specific calendar API surface, the calendar-day buffer constant (analog
to `ud_ratio_21d_spec.md` §12.3 K), and the window-end date validation
behavior are **deferred to Gate A2**.

### 4.2 Daily return source (per stock)

[Verified per Helios canonical convention codified via
`SPEC-P1-DATA-REMEDIATION-v1`; `ud_ratio_21d_spec.md` §4.1 is template
reference, not the semantic source.]

For each stock `i` and trading day `s`:

```
r_{i,s} = adj_close_{i,s} / adj_close_{i,s-1} - 1
```

where:

- `adj_close_{i,s}` is sourced from `listed_market_daily_price_adj`
  (PIT-filtered DuckDB VIEW).
- `s-1` is the prior trading day per `market.trading_calendar`.
- Backing table for the view: `daily_price_adj`, IF-1 filtered via
  `security_lifecycle.market IN ('TWSE', 'TPEx')`.

### 4.3 Validity predicate for daily return

[Derived from `ud_ratio_21d_spec.md` §4.2 architectural template;
safety-critical guards independently restated.]

A daily return `r_{i,s}` is valid iff ALL of the following hold:

1. `adj_close_{i,s-1}` IS NOT NULL.
2. `adj_close_{i,s-1} > 0`.
3. `adj_close_{i,s}` IS NOT NULL.
4. `adj_close_{i,s} > 0`.
5. Trading day `s` is present in `listed_market_daily_price_adj` for
   stock `i` (PIT lifecycle membership automatic via §4.4 invariant).

### 4.4 PIT universe invariant

[Verified per Helios IF-1 remediation governance.]

**INVARIANT:** Both the median producer (§5) and the per-stock daily return
source MUST source price data from `listed_market_daily_price_adj`. Direct
queries against `daily_price_adj` (raw table, without the IF-1 lifecycle
filter) are FORBIDDEN and constitute a P0 lineage violation. The invariant
applies symmetrically to Layer 1 (median producer) and Layer 2 (per-stock
return computation).

### 4.5 Two-layer lineage architecture

[Derived from D-009 cross-sectional reduction asymmetry; this section has
no template analogue in `ud_ratio_21d_spec.md` and is independently
designed.]

Unlike per-stock features (e.g., `ud_ratio_21d`), `win_rate_21d` involves
an additional cross-sectional reduction step. Its PIT contract is split
across two layers:

**Layer 1 — Cross-sectional median producer:**

- Inputs: `listed_market_daily_price_adj` daily returns over the time axis.
- Output: per-date median table (schema in §5.3).
- PIT obligation: the producer's output for date `s` uses only information
  observable at or before `s close`.
- Materialization: BASE TABLE per SD-2 (see §5.1).

**Layer 2 — Per-stock feature consumer:**

- Inputs: per-stock daily returns (§4.2) + median producer output (Layer 1).
- Output: `win_rate_21d` panel column.
- PIT obligation: for a row at `(i, t)`, only data with timestamp `<= t close`
  is used. This INCLUDES the Layer-1 medians `m_s` for `s <= t`.

### 4.6 Lookahead safety guarantees

[Derived from §4.5 + Helios-wide Option II convention.]

For any output row at `(stock_id=i, date=t)`:

1. Only data with timestamp `<= t close` is used (per-stock returns AND
   cross-sectional medians).
2. NO use of `t+1` open, intraday ticks of `t+1`, or any post-`t`
   information.
3. The output row is available for downstream use at `t+1 open`.

For the median producer specifically: `m_s` MUST be deterministically
reproducible from `listed_market_daily_price_adj` as of any snapshot at or
after `s close`. The producer MUST NOT inject cross-date information into
`m_s` (e.g., no rolling smoothing across dates inside `m_s`).

### 4.7 Snapshot lineage requirement

[Derived from D-009 deterministic reproducibility contract +
`ud_ratio_21d_r1_prereg.md` §13 manifest requirement.]

The median producer (§5) MUST carry a `source_snapshot_id` traceable to the
`listed_market_daily_price_adj` snapshot used to build it. Any restatement
of upstream price data (corporate-actions backfill, adj-price restatement
analogous to P5-REF-001, IF-1-style remediation) MUST trigger a producer
rebuild with a new snapshot identifier.

The specific snapshot-id mechanism (table-level metadata column, separate
manifest file, or both) is deferred to Gate A2.

---

## 5. Producer Contract

[Addresses A1-C2 (a) universe, (b) PIT semantics, (e) MIN_OBS role,
(f) deterministic reproducibility, plus A1-C3 (deterministic reproducibility
contract explicit) and A1-C7 (producer dependency surface explicit).
First-class section per the cross-sectional reduction asymmetry of D-009.]

### 5.1 Producer identity

[Derived from SD-2 confirmation + D-009 deterministic reproducibility
contract.]

The cross-sectional median producer is a **materialized BASE TABLE**
(NOT a VIEW), persisted in the Helios DuckDB workspace. Its purposes are:

1. Provide a deterministic, hash-verifiable cross-sectional median series
   for `win_rate_21d` consumption.
2. Enable snapshot lineage tracking against upstream
   `listed_market_daily_price_adj` restatements.
3. Decouple per-stock feature consumers from the cost of re-running
   cross-sectional aggregation per query.

The specific table name and storage location are deferred to Gate A2.

### 5.2 Producer build inputs

[Derived from §3.2 universe definition + §4 PIT contract.]

| Input                  | Source                                                  | PIT discipline                                          |
| ---------------------- | ------------------------------------------------------- | ------------------------------------------------------- |
| Daily returns by stock | `listed_market_daily_price_adj` (DuckDB VIEW)           | IF-1 lifecycle filter inherited automatically (§4.4).   |
| Trading calendar       | `market.trading_calendar` (`>= 0.2.0`)                  | Trading-day axis only.                                  |
| Source snapshot id     | Upstream `listed_market_daily_price_adj` version metadata | Recorded at build time per §4.7.                        |

Build operates per `date`, aggregating across the eligible universe `U_s`
defined in §3.2.

### 5.3 Producer output schema (preliminary)

[Derived from §3.3 median definition + §4.7 snapshot lineage requirement.
Final dtype list deferred to A2.]

The producer table MUST contain at minimum the following columns:

| Column                | Semantic role                                                   | Notes                                                                        |
| --------------------- | --------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `date`                | Trading day                                                     | Primary key.                                                                 |
| `median_daily_return` | `m_s` per §3.3                                                  | Null iff `|U_s| < MIN_CROSS_SECTION_OBS_PER_DATE`.                           |
| `n_obs_cross_section` | `|U_s|`                                                         | Eligible-universe count, for diagnostic and threshold-gating purposes.       |
| `source_snapshot_id`  | Upstream snapshot identifier                                    | Per §4.7. Type / mechanism deferred to A2.                                   |

Additional metadata columns (build timestamp, producer version,
etc.) are deferred to A2.

### 5.4 Deterministic reproducibility contract

[Verified per D-009 mandatory requirement + A1-C3.]

**Spec contract:** Given identical inputs (same
`listed_market_daily_price_adj` snapshot, same trading-calendar version,
same locked `MIN_CROSS_SECTION_OBS_PER_DATE` value), the producer MUST
produce a **byte-identical** output table. There MUST be no implicit
dependencies on build wall-clock time, build host, OS locale, or any
non-deterministic library behavior (e.g., unordered hash iteration,
non-stable sort).

**Test enforcement (deferred to A2):** PIT-PROD-1 (§8.2) verifies
bit-exact reproducibility on a fixed input snapshot.

### 5.5 Regeneration triggers

[Derived from §4.7 + A1-C3 + Helios P5-REF-001 historical precedent of
silent adj-price restatement.]

The producer table MUST be rebuilt (with a new `source_snapshot_id`) when
any of the following events occur:

1. `listed_market_daily_price_adj` source data is restated
   (corporate-actions backfill, adj-price snapshot refresh, IF-1-style
   remediation).
2. `security_lifecycle` is restated in a way that changes per-date universe
   membership for any date in the producer's covered range.
3. Trading calendar version changes in a way that alters trading-day
   classification within the producer's date range.
4. `MIN_CROSS_SECTION_OBS_PER_DATE` is locked at Gate A2, or revised
   subsequently via spec amendment.

Silent stale-read of the producer table after any of (1)–(4) is a P0
lineage violation. The specific detection mechanism (e.g., snapshot-id
mismatch check at consumer query time, periodic integrity audit) is
deferred to Gate A2.

### 5.6 Producer dependency surface (A1-C7)

[Verified per A1-C7. Forbidden-imports list adapted architecturally from
`ud_ratio_21d_spec.md` §12.4; the additions are specific to the
cross-sectional aggregate context.]

The producer's primary upstream data dependencies are:

```
listed_market_daily_price_adj   (DuckDB VIEW, IF-1 PIT-filtered)
market.trading_calendar         (>= 0.2.0)
```

The producer MUST NOT depend on:

```
daily_price_adj                 (raw table; FORBIDDEN per §4.4)
utils.trading_calendar          (legacy weekday-only stub)
utils.trading_dates             (DB-MAX-date semantic, different)
features/regime.py              (different return semantic)
features/bullish_features.py    (different return semantic)
features/bearish_regime.py      (different return semantic)
research/r8_event_builder.py    (R8 signal-construction logic, not feature
                                 substrate)
features/ud_ratio.py            (parallel feature; producers must remain
                                 architecturally independent)
```

### 5.7 Producer-consumer interface contract

[Derived from §4.5 two-layer lineage.]

The `win_rate_21d` feature consumer (§3, §6) reads from the producer table
via a documented query interface (signature deferred to A2). The consumer
MUST NOT:

1. Recompute the median locally (this would bypass the deterministic
   reproducibility contract and risk silent drift from the producer table).
2. Cache intermediate median values across queries unless the cache
   invalidation policy matches §5.5 regeneration triggers exactly.
3. Filter the producer's universe further before consuming the median
   (the producer's `U_s` is the median's universe by §3.2; any further
   filter would change the semantic of `m_s`).

---

## 6. Output Schema

[Addresses A1-C2 (b), (d). Column naming verbatim per prereg lock.]

### 6.1 Panel column schema (consumer output)

[Verified per `ud_ratio_21d_r1_prereg.md` §5 R1-U3 (column name
`win_rate_21d` mandatory) + §6 R1-U4. Dtypes are preliminary.]

The feature consumer appends columns to a `(stock_id, date)` panel:

| Column            | Polars dtype (preliminary) | Range / null semantic                                            |
| ----------------- | -------------------------- | ---------------------------------------------------------------- |
| `win_rate_21d`    | `Float64`                  | `[0.0, 1.0]` when `|S_{i,t}| >= MIN_OBS`, else `null`.           |
| `n_obs_21d`       | `UInt8`                    | `[0, WINDOW]`, count of valid `s` in trailing window (= `|S_{i,t}|`). |
| `n_wins_21d`      | `UInt8`                    | `[0, n_obs_21d]`, count of `s` where `r_{i,s} > m_s`.            |

Dtype finalization (in particular the exact width for the count columns and
the Polars-vs-DuckDB native-type mapping) is deferred to Gate A2.

### 6.2 Row-level invariants

[Derived from §3 mathematical contract.]

For every output row:

```
I1   0 <= n_wins_21d <= n_obs_21d <= WINDOW

I2   win_rate_21d in [0.0, 1.0]  OR  win_rate_21d is null

I3   win_rate_21d is null  iff  n_obs_21d < MIN_OBS

I4   if win_rate_21d is not null:
         win_rate_21d == n_wins_21d / n_obs_21d
         within floating-point precision tolerance
         (specific tolerance value deferred to A2)
```

### 6.3 Null semantic contract (prereg consumption interface)

[Verified per `ud_ratio_21d_r1_prereg.md` §5 R1-U3.]

`win_rate_21d` MUST be nullable. Null is produced ONLY by the conditions in
`I3` above (`n_obs_21d < MIN_OBS`). Imputation, forward-fill, backfill,
zero-fill, and cross-sectional median fill are FORBIDDEN at the feature
layer. The prereg forbids these on the consumer (R1) side; this spec
mirrors the discipline on the producer side.

### 6.4 Window-end identity

[Derived from §3.5 inclusion of `t`.]

Each output row's `date` IS the window-end. There is no separate
`window_end` column. Downstream consumers MUST treat the panel row `date`
as the feature observation date and as the decision date for any strategy
that consumes `win_rate_21d` (Option II convention).

---

## 7. Acceptance Criteria

[A1-C5 Step 0 vs Step 1 vs Step "A3" separation explicit.]

### 7.1 Gate A1 (this spec lock; Step 0 in template parlance)

[Verified per audit memo §7.2 A1-C1 through A1-C9.]

1. Ten sections drafted at ~70–80% completeness per D-008 — assert at
   reviewer review.
2. A1-C2 design landmines (a)–(f) resolved in §3, §4, §5 with explicit
   `[Verified | Derived]` provenance.
3. A1-C3 deterministic reproducibility contract explicit in §5.4.
4. A1-C4 PIT test identifiers enumerated in §8.2; bodies deferred to A2.
5. A1-C5 Step 0 vs Step 1 acceptance criteria separated in this §7.
6. A1-C6 no numerical thresholds beyond `MIN_OBS` (15) and `WINDOW` (21);
   `MIN_CROSS_SECTION_OBS_PER_DATE` explicitly deferred (§3.7).
7. A1-C7 producer dependency surface explicit in §5.6.
8. A1-C8 reviewed and approved — ✓ Governance Consistency Review PASS, 2026-06-30, Veronica.
9. A1-C9 committed; status DRAFT → SPEC_LOCKED — ✓ at this commit.

### 7.2 Gate A2 (implementation; Step 1 in template parlance)

[Verified per audit memo F2 + D-008 deferred to next gate.]

To be delivered in Gate A2 (implementation PR + tests):

1. `MIN_CROSS_SECTION_OBS_PER_DATE` locked-before-first-build, per
   prereg §15 discipline applied at producer layer.
2. Producer build pipeline implemented and tested.
3. Consumer feature function implemented and tested.
4. All PIT tests enumerated in §8.2 implemented and passing.
5. Producer-consumer query interface documented.
6. Snapshot lineage mechanism implemented and documented.
7. Regeneration-trigger detection mechanism implemented and documented.
8. Calendar-day buffer constant (analog to `ud_ratio_21d_spec.md` §12.3 K)
   locked.

### 7.3 Gate A3 (prereg amendment R1-amend-001)

[Verified per audit memo F2 + Gate 0 outcome.]

To be delivered in Gate A3 (R1 prereg amendment `R1-amend-001`, per audit
memo Gate A3 scope):

1. Prereg identity clarification reflecting `win_rate_21d` first spec
   lock at this document.
2. Reference to the Gate A2 implementation commit (producer + consumer)
   inside the amended prereg.
3. Formalization of the feature panel reconstruction protocol now that
   `win_rate_21d` becomes available as a panel column.
4. Alignment between the prereg's feature-contract reference and the
   implementation lineage (spec → producer → consumer → panel column).
5. Closure of the implementation gap identified in audit memo F2 that
   blocked R1 execution.
6. The amendment MUST NOT modify the R1 evaluation universe (L1); the
   §1.3 layer distinction is binding.

---

## 8. Test Strategy

[A1-C4: PIT test identifiers enumerated; bodies deferred to A2.]

### 8.1 Test scope partition

[Derived from §4.5 two-layer lineage + §5 producer first-class status.]

Tests are partitioned across three surfaces, reflecting the two-layer
architecture and its interface:

- `PIT-PROD-*`: Producer-side tests (Layer 1, §5).
- `PIT-CONS-*`: Consumer-side tests (Layer 2, §3 + §6).
- `PIT-INT-*`: Producer-consumer interface tests (§5.7).

### 8.2 Enumerated PIT test identifiers (bodies deferred to A2)

| ID            | Surface  | Concern                                                                                                                                              |
| ------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `PIT-PROD-1`  | Producer | Deterministic reproducibility: bit-exact output on a fixed input snapshot (§5.4).                                                                    |
| `PIT-PROD-2`  | Producer | Universe membership matches §3.2: IF-1 PIT lifecycle filter applied automatically via view.                                                          |
| `PIT-PROD-3`  | Producer | Median computation correctness on synthetic fixture with known cross-section.                                                                        |
| `PIT-PROD-4`  | Producer | `m_s` null iff `|U_s| < MIN_CROSS_SECTION_OBS_PER_DATE` (synthetic fixture at the boundary).                                                         |
| `PIT-PROD-5`  | Producer | `source_snapshot_id` correctly propagated to producer metadata at build time.                                                                        |
| `PIT-PROD-6`  | Producer | Forbidden source-table reference `daily_price_adj` not present in producer code/SQL (structural inspection per `ud_ratio_21d_spec.md` §11.2 pattern). |
| `PIT-CONS-1`  | Consumer | Trailing window inclusion of signal date `t` per §3.5.                                                                                               |
| `PIT-CONS-2`  | Consumer | Daily return validity predicate per §4.3 (all five conditions).                                                                                      |
| `PIT-CONS-3`  | Consumer | Strict-inequality tie handling per §3.4 (synthetic fixture with exact `r == m_s` ties → `win_{i,s} = 0`).                                            |
| `PIT-CONS-4`  | Consumer | `win_rate_21d` null iff `n_obs_21d < MIN_OBS` per §6.2 I3.                                                                                           |
| `PIT-CONS-5`  | Consumer | Row-level invariants I1–I4 (§6.2).                                                                                                                   |
| `PIT-CONS-6`  | Consumer | No lookahead: row at `t` depends only on data `<= t close` (synthetic fixture with poisoned `t+1` data must not alter output at `t`).                |
| `PIT-CONS-7`  | Consumer | Window-end date validation: `ValueError` if a date used as `window_end` is not a trading day.                                                        |
| `PIT-CONS-8`  | Consumer | No imputation: null observations remain null; no forward-fill / backfill / zero-fill / median-fill applied.                                          |
| `PIT-INT-1`   | Interface | Consumer reads producer output verbatim (no local recomputation; verified by structural inspection of consumer code).                                |
| `PIT-INT-2`   | Interface | Consumer detects producer `source_snapshot_id` mismatch (stale-read regression).                                                                     |
| `PIT-INT-3`   | Interface | Universe coherence: producer-reported `n_obs_cross_section` for date `s` matches independently re-derived `|U_s|` from the source view at `s`.       |

### 8.3 Fixture strategy (high-level)

[Derived from `ud_ratio_21d_spec.md` §13 architectural template; semantic
fixture content is independently designed per cross-sectional aggregate
asymmetry.]

- **Synthetic fixtures (DataFrame-native):** `PIT-PROD-3`, `PIT-PROD-4`,
  `PIT-CONS-1`–`PIT-CONS-8`, `PIT-INT-1` exercise prescribed price panels
  spanning multiple synthetic "stocks" to enable cross-sectional
  fixtures, without DB dependency. Multi-stock fixture helper signature
  deferred to A2.
- **Anchored-real fixtures:** `PIT-PROD-2` (PIT universe membership),
  `PIT-PROD-5` (snapshot id), `PIT-PROD-6` (source-table audit),
  `PIT-INT-2` (snapshot mismatch), `PIT-INT-3` (universe coherence)
  require real `listed_market_daily_price_adj` access. Specific anchor
  selection conditions deferred to A2.

### 8.4 Forbidden test patterns

[Derived from `ud_ratio_21d_spec.md` §11.2 architectural pattern.]

- **String-level SQL checks** (e.g., `"FROM daily_price_adj" in sql`)
  for source-table verification: FORBIDDEN due to false-negative risk from
  whitespace, comments, identifier quoting. Use structural inspection
  (DuckDB plan introspection, SQL AST parsing, or Polars source-attribution
  inspection) instead.
- **Parity tests against `ud_ratio_21d` outputs**: NOT APPLICABLE.
  `win_rate_21d` has materially different semantics (relative
  outperformance vs sign-frequency persistence); no numerical parity
  should hold, and asserting any would be a category error.

---

## 9. Governance

[A1-C9 commit/lock metadata; audit memo §1.3 / §1.4 non-duplication
discipline applied — this section is a citation registry, not a rationale
restatement.]

### 9.1 Citation registry

| Decision / Contract                                                        | Source document                                              | Section / Anchor    | Commit (or status) |
| -------------------------------------------------------------------------- | ------------------------------------------------------------ | ------------------- | ------------------ |
| D-001 Definition E (relative-outperformance frequency direction)           | `docs/research/ud_ratio_21d_r1_pre_execution_audit.md`       | D-001               | `abc2d86`          |
| D-008 v0.1.0 scope (10 sections, 70–80% completeness)                      | `docs/research/ud_ratio_21d_r1_pre_execution_audit.md`       | D-008               | `abc2d86`          |
| D-009 deterministic reproducibility contract mandatory                     | `docs/research/ud_ratio_21d_r1_pre_execution_audit.md`       | D-009               | `abc2d86`          |
| Gate A1 Exit Criteria A1-C1 through A1-C9                                  | `docs/research/ud_ratio_21d_r1_pre_execution_audit.md`       | §7.2                | `abc2d86`          |
| ER-6 architectural-template usage of `ud_ratio_21d_spec.md`                | `docs/research/ud_ratio_21d_r1_pre_execution_audit.md`       | ER-6                | `abc2d86`          |
| F2 win_rate_21d implementation gap → Gate A1→A2→A3 sequencing              | `docs/research/ud_ratio_21d_r1_pre_execution_audit.md`       | F2                  | `abc2d86`          |
| R1 evaluation universe (L1) = R8 `treatment_1` signal-date panel           | `docs/research/ud_ratio_21d_r1_prereg.md`                    | §3 R1-U1            | `13ed404`          |
| R1 consumption interface for `win_rate_21d` (column name, nullability)     | `docs/research/ud_ratio_21d_r1_prereg.md`                    | §5 R1-U3, §6 R1-U4 | `13ed404`          |
| Imputation forbidden at consumer side                                      | `docs/research/ud_ratio_21d_r1_prereg.md`                    | §5 R1-U3            | `13ed404`          |
| Lock-before-look discipline (template for §3.7 deferral)                   | `docs/research/ud_ratio_21d_r1_prereg.md`                    | §15, §6a            | `13ed404`          |
| Reproducibility manifest requirement (`feature_spec_version`, hashes)      | `docs/research/ud_ratio_21d_r1_prereg.md`                    | §13                 | `13ed404`          |
| R1 prereg governance boundary (does not modify feature implementation)     | `docs/research/ud_ratio_21d_r1_prereg.md`                    | §2                  | `13ed404`          |
| Architectural template (sections, normative wording, PIT id scheme)        | `docs/features/ud_ratio_21d_spec.md` v0.1.4                  | §1–§13              | SPEC_LOCKED        |
| SD-1: median universe = `listed_market_daily_price_adj` PIT-filtered full  | Gate A1 kickoff session 2026-06-30                           | confirmed in session | (this spec, first lock) |
| SD-2: median producer = materialized BASE TABLE                            | Gate A1 kickoff session 2026-06-30                           | confirmed in session | (this spec, first lock) |
| F.3 option (ii): `MIN_CROSS_SECTION_OBS_PER_DATE` deferred to A2           | Gate A1 kickoff session 2026-06-30                           | confirmed in session | (this spec, first lock) |
| Daily-return canonical convention (`adj_close / prev_adj_close - 1`)       | Helios-wide; prior lock in `SPEC-P1-DATA-REMEDIATION-v1`     | (canonical)         | (canonical)        |
| PIT-view universe convention (`listed_market_daily_price_adj`)             | Helios-wide; prior lock in `SPEC-P1-DATA-REMEDIATION-v1`     | (canonical)         | (canonical)        |

### 9.2 Sub-decision sign-off

| ID    | Decision                                                                       | Sign-off               |
| ----- | ------------------------------------------------------------------------------ | ---------------------- |
| SD-1  | Median universe = `listed_market_daily_price_adj` (PIT-filtered full listed)   | Veronica, 2026-06-30   |
| SD-2  | Median producer storage = materialized BASE TABLE                              | Veronica, 2026-06-30   |
| F.3   | `MIN_CROSS_SECTION_OBS_PER_DATE` numerical value deferred to A2 lock-before-build | Veronica, 2026-06-30   |

### 9.3 Layer distinction (binding governance)

The layer distinction in §1.3 (L1 R1 evaluation universe vs L2
`win_rate_21d` internal median universe) is **normative**.

- A future R1' or downstream consumer that wishes to use `win_rate_21d`
  on a different L1 evaluation universe does NOT require this spec to be
  amended. Any such consumer-side restriction is governed by that
  consumer's own pre-registration.
- Any change to L2 (the median producer's universe definition in §3.2)
  requires a spec amendment with version bump.

### 9.4 Version history

| Version         | Date       | Change                                                                                                                                                                                                                                                                                                |
| --------------- | ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| v0.1.0 (LOCKED) | 2026-06-30 | Initial spec. Gate A1 first lock. D-001 Definition E technical realization. SD-1 / SD-2 / F.3 confirmed. `MIN_OBS = 15`, `WINDOW = 21` locked. Median interpolation rule (arithmetic midpoint for even counts) locked in §3.3. `MIN_CROSS_SECTION_OBS_PER_DATE` deferred to A2. Architectural template from `ud_ratio_21d_spec.md` v0.1.4; no semantic inheritance. Governance Consistency Review PASS, 2026-06-30, Veronica. |

---

## 10. Future Extensions

[Deferred items; not normative for v0.1.0.]

### 10.1 Gate A2 deliverables (binding next step)

- Producer build pipeline implementation.
- Consumer feature-function implementation.
- Lock of `MIN_CROSS_SECTION_OBS_PER_DATE`.
- Lock of producer table name and storage location.
- Lock of calendar-day buffer constant (analog to `ud_ratio_21d_spec.md`
  §12.3 K).
- Lock of dtype widths.
- Lock of floating-point tolerance for I4 self-consistency.
- PIT test bodies for all identifiers enumerated in §8.2.

### 10.2 v0.1.1 candidate items (not in v0.1.0 per D-008)

Subjects acknowledged as out of scope for v0.1.0 but candidate for v0.1.1
or later:

- Multi-horizon variants (e.g., `win_rate_63d`, `win_rate_252d`).
- Parameterized `min_obs` sensitivity sweep (Step 2 robustness analog to
  `ud_ratio_21d_spec.md` §4.3 `min_obs` parameter pattern).
- Alternative benchmark statistics (e.g., universe-weighted mean,
  sector-relative median, robust trimmed mean).
- Eligible-universe variants (e.g., liquidity-filtered, market-cap-bucket
  stratified).
- Alternative tie-handling rules (e.g., half-credit, exclude-from-both).

### 10.3 Known research risks (acknowledged; not locked)

- **Universe-composition drift (L2):** the median's universe (Candidate A
  = full PIT-filtered listed universe) has time-varying composition (new
  listings, delistings, IF-1 lifecycle transitions). Whether this
  introduces non-stationarity in the `m_s` series is an empirical question
  for Step 2.
- **Tie inflation in low-vol regimes:** on flat sessions the cross-sectional
  median may be at or very near zero, and many stocks with `r ≈ 0` (due to
  inactivity, tick-size discretization, or low volume) may exactly tie the
  median. The strict-inequality rule (§3.4) biases the feature DOWN on such
  days. Conditional analysis by realized volatility regime is a candidate
  Step 2 robustness check.
- **Suspension-day inclusion:** stocks listed but inactive on day `s` may
  have valid `adj_close` carried forward, yielding `r_{j,s} = 0`. These
  stocks enter `U_s` and may distort the median (pull it toward zero in
  low-vol regimes). The §4.3 validity predicate does not currently exclude
  suspension days as a class — only days without valid prior/current prices.
  Whether to add a suspension-day filter is deferred to v0.1.1.
- **L1/L2 asymmetry artefacts:** R1 (and other consumers) evaluate
  `win_rate_21d` on a narrow L1 (R8 `treatment_1`), but the median is
  computed on a broad L2 (full listed universe). Whether this
  broad-benchmark / narrow-evaluation asymmetry produces Spearman-rho
  artefacts when paired with `ud_ratio_21d` is the kind of question R1 is
  designed to detect.

### 10.4 Routing under R1 outcome (informational; not binding on this spec)

Per `ud_ratio_21d_r1_prereg.md` §14, R1 outcome routing applies to
`ud_ratio_21d` itself, not directly to `win_rate_21d`. Any future failure
of an analogous proxy-collapse analysis featuring `win_rate_21d` as the
primary feature would be defined in a separate pre-registration specific
to `win_rate_21d` (not in this spec). This spec acknowledges the existence
of such a future path but does not enumerate its triggers.

---

*End of v0.1.0 SPEC_LOCKED.*
