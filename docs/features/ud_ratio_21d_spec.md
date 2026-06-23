# 21D Up/Down Ratio Feature Specification — v0.1.4

**Feature ID:** `ud_ratio_21d`
**Track:** C
**Status:** SPEC_LOCKED (GATE-S1-IMPL-001 closed, 2026-06-22)
**Owner:** Veronica
**Repository:** Helios (`~/projects/helios`)
**Universe:** R8 `treatment_1` (Phase 1 IF-1 remediated via
              `listed_market_daily_price_adj` view)

---

## 1. Scope

This document specifies the `ud_ratio_21d` feature at the conceptual,
mathematical, and lineage level. It does NOT specify alpha hypothesis,
signal construction, correlation analysis, or backtest results — those
belong to subsequent Track C steps.

Step 0 deliverable: spec + DataFrame-native API + PIT invariant tests
+ fixture strategy + external-surface contracts.

Step 1 implements `add_ud_ratio_21d` (and any helper functions
required) under the contracts locked here.

---

## 2. Conceptual Definition

`ud_ratio_21d` measures the fraction of valid trading days within a
trailing 21-trading-day window on which a stock's daily simple return
on adjusted close was strictly positive. It captures
**sign-frequency persistence** decoupled from return magnitude.

Contrast with existing Helios features:

| Feature              | Family                          | Outlier sensitivity     |
| -------------------- | ------------------------------- | ----------------------- |
| RS-60d (Phase 4)     | Cumulative magnitude momentum   | High                    |
| MA5 momentum (R8)    | Short-horizon price level       | Moderate                |
| **ud_ratio_21d**     | **Sign-frequency persistence**  | **Low (by construction)** |

Whether `ud_ratio_21d` carries incremental orthogonal information is
a question for Step 2 (redundancy / correlation analysis); Step 0
makes no such claim. See §10 R1 for the pre-registered falsification
protocol.

---

## 3. PIT-Safe Mathematical Definition

### 3.1 Notation

- `t`: observation date for a given (stock_id, date) row in the
  output panel. MUST be a trading day per §12 when used as a window
  end.
- `i`: equity identifier (Taiwan ticker)
- `r_{i,s}`: daily simple return on adjusted close, defined in §4.1
- `W = 21`: window length in trading days (NOT calendar days)
- `S_{i,t}`: set of up-to-21 most recent trading days `s ≤ t` for
  which `r_{i,s}` is a valid return (see §4.2)

Note on terminology: in v0.1.0–v0.1.3 this spec used `signal_date`.
In v0.1.4, since the feature operates on a panel and each row carries
its own `date`, the terminology unifies under `date` (per panel row).
`signal_date` remains a valid synonym in downstream consumer contexts
(e.g. when a strategy passes a specific date to query the panel).

### 3.2 Core Formula

```
ud_ratio_21d_{i,t} = sum_{s in S_{i,t}} 1[r_{i,s} > 0]  /  |S_{i,t}|
```

defined iff `|S_{i,t}| >= MIN_OBS`, else null (NaN in Polars).

### 3.3 Sign Convention

| Case             | n_up_21d | n_obs_21d |
| ---------------- | -------- | --------- |
| `r_{i,s} > 0`    | +1       | +1        |
| `r_{i,s} < 0`    | 0        | +1        |
| `r_{i,s} == 0`   | 0        | +1        |
| `r_{i,s}` is NaN | 0        | 0         |

Flat-day rationale: `r == 0` is a valid trading day but does NOT
constitute positive continuation. Biases the feature DOWNWARD for
low-liquidity tickers, which is the conservative direction for a
persistence feature.

---

## 4. Data Lineage

### 4.1 Return Source & Computation

**Source:** `listed_market_daily_price_adj` (DuckDB VIEW)
**Backing table:** `daily_price_adj`, IF-1 filtered via
                   `security_lifecycle.market IN ('TWSE', 'TPEx')`
**Columns used:** `stock_id`, `date`, `adj_close`

**Canonical SQL recipe (R8 / Phase 1–6 aligned):**

```sql
WITH price_panel AS (
    SELECT
        stock_id,
        date,
        adj_close,
        LAG(adj_close) OVER (PARTITION BY stock_id ORDER BY date)
            AS prev_adj_close
    FROM listed_market_daily_price_adj
)
SELECT
    stock_id,
    date,
    adj_close / prev_adj_close - 1.0  AS daily_simple_return
FROM price_panel
WHERE prev_adj_close IS NOT NULL
  AND prev_adj_close > 0
  AND adj_close      IS NOT NULL
  AND adj_close      > 0
```

**Governance:**
- `ud_ratio_21d` MUST compute daily returns using a method that is
  **semantically equivalent** to this SQL recipe. When implemented
  in Polars rather than DuckDB SQL, the Polars expression must
  produce the same daily-return series for the same inputs.
- **PIT-10 enforces bit-exact equality on the resulting daily-return
  series** between the `ud_ratio_21d` pipeline and the canonical
  recipe. Semantic equivalence is the spec contract; bit-exact
  equality is the test enforcement (§11.1).
- NO Polars-expression variant repurposed from `features/regime.py`,
  `features/bullish_features.py`, or `features/bearish_regime.py`.
  Those `daily_ret` patterns operate on DIFFERENT semantics (close
  vs adj_close, sma momentum vs single-period return).
- NO local price→return arithmetic outside this canonical pattern.

### 4.2 Validity Predicate

A daily return `r_{i,s}` is valid iff ALL of:

1. `prev_adj_close IS NOT NULL`
2. `prev_adj_close > 0`
3. `adj_close IS NOT NULL`
4. `adj_close > 0`
5. Trading day `s` is present in `listed_market_daily_price_adj`
   (PIT universe membership is automatic by §4.4)

Note: `adj_close > 0` is included as a data-quality guard against
zero/negative sentinel values, even though R8 chain SQL does not
always make this guard explicit. This is conservative and never
alters the semantic of valid data.

### 4.3 Minimum Observation Threshold

```
MIN_OBS = 15          # production default; LOCKED
WINDOW  = 21          # LOCKED
```

- `|S_{i,t}| < MIN_OBS` → `ud_ratio_21d` is null, `n_obs_21d` reflects
  the actual count, no imputation.
- Step 1 compute API contract:
  `add_ud_ratio_21d(df, *, min_obs: int = MIN_OBS) -> pl.DataFrame`
  The parameter is exposed for Step 2 sensitivity testing in
  `{12, 15, 18}` without module-level mutation.
- 15/21 ≈ 71% completeness; heuristic, NOT empirically optimized.

### 4.4 PIT Universe Invariant

The `listed_market_daily_price_adj` view enforces Phase 1 IF-1
EMERGING-period exclusion at query time via the
`security_lifecycle` join (per SPEC-P1-DATA-REMEDIATION-v1).

**INVARIANT:** `ud_ratio_21d` MUST source price data from
`listed_market_daily_price_adj`. Direct queries against
`daily_price_adj` (raw table without the IF-1 filter) are
FORBIDDEN and constitute a P0 lineage violation.

This invariant subsumes IF-1 remediation automatically; no separate
exclusion list maintenance is required at the feature level.

### 4.5 Lookahead Safety Guarantees

For any output row at `(stock_id=i, date=t)`:

1. Only data with timestamp `≤ t close` is used
2. NO use of `t+1` open, intraday ticks, or any post-`t` information
3. Available for downstream use at `t+1` open (Option II
   convention: panel row date is the decision date)

The DataFrame-native API enforces this naturally: when computing
`ud_ratio_21d` for row `(i, t)`, the rolling-window operator MUST be
configured to look BACKWARD only (e.g. Polars `rolling_*` with
default `closed='right'`, or explicit window slicing where the most
recent row in the window is `t` itself).

---

## 5. Output Schema (REWRITTEN v0.1.4)

`ud_ratio_21d` is exposed as a DataFrame-native feature, aligned with
the `features/*` subsystem convention (panel-in, panel-out, pure
function, Polars-native, LazyFrame-compatible).

### 5.1 Public API

```python
# features/ud_ratio.py

import polars as pl

MIN_OBS: int = 15
WINDOW: int = 21
FEATURE_ID: str = "ud_ratio_21d"
SPEC_VERSION: str = "v0.1.4"
WINDOW_LOOKBACK_BUFFER_DAYS: int = 45  # calendar-day buffer, §12.3

def add_ud_ratio_21d(
    df: pl.DataFrame,
    *,
    min_obs: int = MIN_OBS,
) -> pl.DataFrame:
    """Append ud_ratio_21d, n_obs_21d, n_up_21d columns to a panel.

    Input contract:
        - Columns required: stock_id (Utf8), date (Date),
          adj_close (Float64)
        - Sorted ascending by (stock_id, date)
        - One row per (stock_id, date) trading-day observation
        - adj_close sourced from listed_market_daily_price_adj (§4.4)

    Output contract:
        Input columns preserved, with three columns appended.

    Raises:
        ValueError: input contract violation (missing columns, wrong
                    dtypes, unsorted) OR a date used as window_end
                    is not a trading day (§12.2).
    """
    ...
```

### 5.2 Output Column Schema

| Column          | Polars dtype | Range / null semantic                              |
| --------------- | ------------ | -------------------------------------------------- |
| `ud_ratio_21d`  | `Float64`    | `[0.0, 1.0]` when `n_obs_21d >= MIN_OBS`, else `null` |
| `n_obs_21d`     | `UInt8`      | `[0, 21]`                                          |
| `n_up_21d`      | `UInt8`      | `[0, n_obs_21d]` (cell-wise upper bound)           |

**Rationale for `UInt8`:** both counts are bounded above by `WINDOW = 21`.
`UInt8` (0-255 range) is sufficient, deterministic, and 8x smaller than
`Int64`. If a future WINDOW increase exceeds 255, this dtype must be
revisited.

### 5.3 Row-Level Invariants (enforced by `_validate_output` + PIT tests)

For every output row:

```
I1  0 <= n_up_21d <= n_obs_21d <= 21
I2  ud_ratio_21d in [0.0, 1.0]  OR  ud_ratio_21d is null
I3  ud_ratio_21d is null  iff  n_obs_21d < MIN_OBS (= 15)
I4  if ud_ratio_21d is not null:
        |ud_ratio_21d - n_up_21d / n_obs_21d| < 1e-12  (self-consistency)
```

**Enforcement layers:**
- Function-internal: `add_ud_ratio_21d` MAY call `_validate_output(df)`
  after computation to assert I1–I4 on the produced columns. Optional
  for hot-path performance, but recommended.
- Test layer: `tests/features/test_ud_ratio_schema.py` asserts I1–I4
  by constructing minimal panels and verifying output rows.

### 5.4 Removed in v0.1.4

The following were specified in v0.1.0–v0.1.3 and are **REMOVED**:

- `UDRatioResult` frozen dataclass — replaced by DataFrame columns
- `window_start`, `window_end` provenance fields — `window_end` is
  the row's `date` (no separate column needed); `window_start` is
  derivable from `date` and the trading calendar and is asserted in
  PIT-13 (not stored)
- `signal_date` as a distinct concept — replaced by panel row `date`

### 5.5 Window-End Identity (replaces former I6)

In v0.1.0–v0.1.3, invariant `I6: window_end == signal_date` was
introduced. In v0.1.4 this is **implicit by construction**: each
output row's `date` IS the window-end. The Research ABI contract
remains:

```
date (panel row)
    = feature observation date
    = event date for any downstream consumer
    = portfolio decision date when consumed by a strategy
```

This identity is preserved; only the column-level enforcement
changed (no longer needed because there is no separate field).

---

## 6. Resolved Design Decisions

| ID | Question                                | Decision                          |
| -- | --------------------------------------- | --------------------------------- |
| Q1 | Flat day `r == 0` handling              | Denominator yes, numerator no     |
| Q2 | `ud_ratio_21d_excl_limit` variant       | Deferred to Step 2                |
| Q3 | Multi-horizon (21d / 63d / 252d)        | 21d only in Step 0                |
| Q4 | Simple return vs log return             | Simple return                     |

Sign-off: Veronica, 2026-06-22 (Q1–Q4 in v0.1.0; reaffirmed in v0.1.4).

---

## 7. Non-Goals (Step 0/1)

- Alpha hypothesis (Step 2+)
- Cross-correlation with RS-60d / MA5 (Step 2)
- Cross-sectional ranking / percentile (Step 3)
- Integration with ARM_B exit policy (Phase 6 closed per RP-01)
- Backtest / IC / IR analysis
- `excl_limit` variant or alternative window lengths
- Repo-wide legacy calendar cleanup (see §12.6; backlog item)
- Scalar result-object API (`UDRatioResult` rejected per
  GATE-S1-IMPL-001; downstream must consume DataFrame)

---

## 8. Acceptance Criteria (REVISED v0.1.4)

Step 0 (closed):
1. Q1–Q4 resolved
2. Spec at v0.1.4 (this document)
3. `features/ud_ratio.py` module skeleton + constants + API
   signature committed (Phase B)
4. `tests/features/test_ud_ratio_schema.py` asserting constants +
   API signature (Phase B); row-invariant tests deferred to Step 1
   PR alongside implementation
5. Spec §4.1 lineage policy = B4 (inline SQL + parity test)
6. Trading calendar source identified (§12)
7. Fixture strategy locked (§13)

Step 1 (pending; tracked separately):
1. `add_ud_ratio_21d` implements §3 + §4 + §12
2. PIT-1 through PIT-13 all pass
3. No imports of `utils.trading_calendar` or `utils.trading_dates`
4. SQL parity (PIT-10) bit-exact against `r8_event_builder` recipe

**Note on schema test scope (v0.1.4):** With the dataclass removed,
`test_ud_ratio_schema.py` cannot test invariant enforcement at
construction time. Instead it tests:
- Module constants (MIN_OBS, WINDOW, SPEC_VERSION, etc.)
- API signature (function exists, parameter name `min_obs`, default
  value)
- Output column schema (names + dtypes) on a minimal valid input
- Row invariants I1–I4 on a minimal computed result

The minimal-input test requires `add_ud_ratio_21d` to actually
execute. If Step 1 has not yet implemented the function, schema
tests asserting output (rather than constants/signature) will fail.

**Phase B commit (per GATE-S1-IMPL-001 decision):**
For the docs+schema commit, only constants + API-signature tests are
included. Row-invariant tests on actual output move to Step 1 PR
together with the implementation.

---

## 9. Version History

| Version | Date       | Change                                       |
| ------- | ---------- | -------------------------------------------- |
| v0.1.0  | 2026-06-22 | Initial spec. Q1–Q4 resolved.                |
| v0.1.1  | 2026-06-22 | I4 self-consistency; I6 == signal_date;      |
|         |            | min_obs parameterised; R1/R2 risks.          |
| v0.1.2  | 2026-06-22 | I6 reframed as Research ABI invariant; R1    |
|         |            | numeric threshold removed (process pre-      |
|         |            | locked, number unlocked until Step 2).       |
| v0.1.3  | 2026-06-22 | Step 1-0 external surface lock:              |
|         |            | (a) §4 B4 inline SQL + PIT-10 parity         |
|         |            | (b) §4.2 explicit guards                     |
|         |            | (c) §4.4 view-source invariant               |
|         |            | (d) §11 PIT-10 SQL semantics (Observation A) |
|         |            | (e) §11.2 PIT-8 structural inspection        |
|         |            | (f) §12 Trading Calendar Contract            |
|         |            | (g) §13 Fixture Strategy                     |
|         |            | (h) Flat layout per PATH-CHECK-001           |
| v0.1.4  | 2026-06-22 | GATE-S1-IMPL-001 PIVOT: DataFrame-native API |
|         |            | (a) §5 fully rewritten: output is panel      |
|         |            |     columns (ud_ratio_21d, n_obs_21d,        |
|         |            |     n_up_21d), NOT scalar UDRatioResult      |
|         |            | (b) §5.4 UDRatioResult dataclass REMOVED;    |
|         |            |     window_start/window_end NOT exposed as   |
|         |            |     columns                                  |
|         |            | (c) §3.1 terminology unified under `date`    |
|         |            | (d) §4.5 lookahead-safety phrased for        |
|         |            |     row-wise panel computation               |
|         |            | (e) §5.5 I6 absorbed: each row's `date` IS   |
|         |            |     the window-end by construction           |
|         |            | (f) §8 schema-test scope split Phase B /     |
|         |            |     Step 1 PR                                |
|         |            | (g) §13.1 synthetic helper aligned with      |
|         |            |     panel-shape input/output                 |
|         |            | (h) Edit A: §12.2 scope narrowed to          |
|         |            |     window_end dates only, not every row     |
|         |            | (i) Edit B: §4.1 wording — semantically      |
|         |            |     equivalent (spec contract) vs bit-exact  |
|         |            |     equality (PIT-10 enforcement)            |
|         |            | (j) Rationale: features/* subsystem is       |
|         |            |     Polars-DataFrame-native by convention    |
|         |            |     (G3/G4 discovery); scalar result object  |
|         |            |     was wrong shape for this layer.          |

---

## 10. Known Research Risks

### R1 — Sign-vs-magnitude proxy collapse

**Hypothesis at risk:** `ud_ratio_21d` carries information orthogonal
to magnitude-based momentum (RS-60d, ROC-20d).

**Failure mode:** empirically, `ud_ratio_21d` may collapse to a
near-monotone function of trailing magnitude momentum, in which case
it provides no incremental information after RS-60d is already in
the feature set.

**Step 2 falsification protocol (process pre-registered; threshold
DELIBERATELY UNLOCKED):**

1. Compute Spearman correlation cross-sectionally per day:
   - `rho(ud_ratio_21d, RS_60d)`
   - `rho(ud_ratio_21d, ROC_20d)`
   - `rho(ud_ratio_21d, win_rate_21d)`
2. Characterise the time-series distribution of each rho: median,
   IQR, tail behaviour, regime conditioning.
3. Compare against prior Track-C proxy-collapse cases (distance /
   slope / spread) using the same diagnostics they were eventually
   flagged on.
4. THEN — and only then — set an escalation threshold informed by
   the characterisation.
5. If escalation triggered: redundancy review before any predictive
   analysis. Do NOT proceed to alpha hypothesis until R1 is resolved.

**Governance note (LOCKED):** the escalation threshold is
intentionally NOT specified at Step 0. Follow Helios practice: lock
the process, let the data set the number.

### R2 — Flat-day inflation in low-liquidity tail

By Q1 resolution, flat days bias `ud_ratio_21d` downward. For
low-liquidity small caps with frequent `r == 0`, the feature may
primarily encode liquidity rather than direction. Step 2 must
include conditional analysis by ADV bucket.

---

## 11. PIT-10 SQL Parity + PIT-8 Hardening

### 11.1 PIT-10 — SQL Parity Test (Observation A)

**Rationale:** in absence of a canonical return helper module,
lineage equivalence between `ud_ratio_21d` and the R8/Phase 1–6
chain must be enforced empirically via test parity rather than by
shared imports.

**Spec contract:** the `ud_ratio_21d` daily-return series is
**semantically equivalent** to the recipe in
`research/r8_event_builder.py` `price_panel` CTE.

**Test enforcement:** PIT-10 asserts **bit-exact equality** on the
resulting daily-return series (no tolerance, no `math.isclose`).
Semantic equivalence + same DuckDB engine + same view + same
adjusted prices yields bit-identical output; any difference is
lineage drift, not numerical noise.

**Test design:**

1. Query a small set of `(stock_id, date)` anchors from
   `data/_storage/r8_phase1_remediated/r8_events.parquet`.
2. For each anchor, compute the daily_simple_return series over the
   21d window via:
   - **Path A:** `ud_ratio_21d` internal pipeline (SQL or Polars
     expression in `features/ud_ratio.py`)
   - **Path B:** the daily-return SQL recipe in
     `research/r8_event_builder.py`, specifically the `price_panel`
     CTE pattern. Test re-derives this pattern inline; MUST NOT
     depend on any specific implementation symbol name.
3. Assert bit-exact equality for every overlapping
   `(stock_id, date)` pair.

**Out of scope for PIT-10:** Polars-expression `daily_ret` variants
across `features/*` operate on different semantics and MUST NOT be
tested for parity against `ud_ratio_21d`.

### 11.2 PIT-8 SQL Inspection (Patch-1)

String-level checks (`"FROM ..." in sql`) are FORBIDDEN due to
false-negatives from whitespace, comments, and identifier quoting.

PIT-8 MUST verify source-table resolution via a structural mechanism
that is robust to formatting variation. The specific mechanism
(DuckDB plan introspection, SQL AST parsing, or other) is an
implementation choice for Step 1 and is documented in the test
module, NOT in this spec.

**Spec contract:**
    The PIT-8 test MUST distinguish, by structural inspection of the
    SQL or its query plan, between:
        - listed_market_daily_price_adj as a FROM/scan target (REQUIRED)
        - daily_price_adj as a direct FROM/scan target        (FORBIDDEN)
    View-expansion of daily_price_adj inside the plan as a downstream
    consequence of querying the view is permitted and expected.

If `add_ud_ratio_21d` is implemented purely in Polars (no SQL string
to inspect), PIT-8 instead verifies the data-source provenance:
input DataFrame MUST have been loaded from `listed_market_daily_price_adj`
or another equivalently-IF-1-filtered source. The test then verifies
that the function does NOT internally re-query the database with a
hardcoded raw-table reference.

---

## 12. Trading Calendar Contract

### 12.1 Canonical Source

**Module:** `market.trading_calendar` (version >= 0.2.0)
**Functions used by `ud_ratio_21d`:**
- `is_trading_day(d: date) -> bool`
- `get_trading_days(start: date, end: date) -> list[date]`

### 12.2 Window-End Date Validation (REVISED v0.1.4)

The feature module MUST raise `ValueError` if **a date used as a
window_end** (i.e. the row date for which `ud_ratio_21d` is being
computed) is not a trading day per `is_trading_day`.

This is intentionally narrower than "every row in the input panel
must be a trading day". Rationale:
- The feature layer's responsibility is to validate computation
  windows, not to police the entire dataset
- Future test fixtures may include calendar gaps
- Panel assembly upstream may temporarily contain non-trading-day
  rows that are later filtered or excluded from computation
- Input rows that do not participate in computation (e.g. rows
  skipped because of insufficient lookback) need not be trading days

Implementation freedom: how the feature determines which rows are
"window_end" rows is at Step 1's discretion (e.g. compute for all
rows but null-out non-trading-day window_ends with a clear warning,
versus pre-filter the panel to trading-day rows only). The contract
is on what raises `ValueError` versus what produces null output.

### 12.3 Window Construction Algorithm (LOCKED)

For each output row at `(stock_id=i, date=t)` where t is a trading day:

```python
from datetime import timedelta
from market.trading_calendar import get_trading_days, is_trading_day

if not is_trading_day(t):
    raise ValueError(f"date {t} is not a trading day")

K = 45  # calendar-day buffer
look_back_start = t - timedelta(days=K)
all_td = get_trading_days(look_back_start, t)

if len(all_td) < WINDOW:
    raise ValueError(
        f"insufficient trading days in [{look_back_start}, {t}]: "
        f"got {len(all_td)}, need >= {WINDOW}"
    )

assert all_td[-1] == t
window_td = all_td[-WINDOW:]
```

When implemented vectorially in Polars (preferred for performance),
the calendar derivation can be done once per `stock_id × date_range`
and the trading-day index used to compute rolling windows by
trading-day count rather than calendar-day count.

**K = 45 rationale:** Taiwan's longest historical holiday cluster
yields ~10 non-trading days. 45 calendar days provides ~30+ trading
days, guaranteeing coverage of 21 with substantial buffer. Runtime
guard ensures regression fails fast.

### 12.4 Forbidden Imports

`features/ud_ratio.py` MUST NOT import:

- `utils.trading_calendar` — legacy weekday-only stub
- `utils.trading_dates` — different semantic (DB-MAX-date)

Enforced by **PIT-11** (import inspection test).

### 12.5 DB Dependency in Test Fixtures

Tests MUST monkeypatch `_is_in_twse_holidays_db` to constant
`False` (pattern from `tests/test_trading_calendar_v0_2_0.py:49`),
isolating calendar logic to XTAI + static fallback.

### 12.6 Legacy Calendar Defence (Three-Tier Strategy)

```
Tier 1 (Track C, ACTIVE):
    - features/ud_ratio.py MUST NOT import forbidden modules
    - PIT-11 enforces via import inspection
    - Spec §12.4 forbidden list

Tier 2 (Helios backlog, NOT Track C):
    - BACKLOG-CALENDAR-LEGACY-001 (separate document)
    - Repo-wide audit + migration

Tier 3 (Future cleanup, blocked by Tier 2):
    - Deprecation warning, CI ban, final deletion
```

Track C contributes Tier 1 only.

---

## 13. Fixture Strategy

### 13.1 Synthetic Fixtures (DataFrame-native)

Synthetic tests construct panel DataFrames of prescribed daily
adj_close sequences to exercise PIT-1, 2, 3, 4, 5, 6, 9, 11, 12, 13
without DB dependency.

**Helper contract:**

```python
_make_adj_close_panel(
    ticker: str,
    end_date: date,
    returns: list[float | None],
    base_price: float = 100.0,
) -> pl.DataFrame
```

- `len(returns)` == number of daily return observations
- output panel has `len(returns) + 1` rows (row 0 = base_price, no
  return; rows 1..N produced by sequential `prev * (1 + returns[i-1])`,
  NaN if `returns[i-1]` is None)
- output columns: `stock_id (Utf8)`, `date (Date)`, `adj_close (Float64)`
- output sorted ascending by date

Implementation details — NaN propagation semantics, weekday-only
date alignment, trading-calendar awareness — are documented in
`tests/features/conftest.py` (to be created in Phase C).

**Spec contract:**
    Synthetic fixtures MUST be deterministic, bit-exact reproducible,
    and require no DB connection.

### 13.2 Anchored-Real Fixture Conditions

| PIT    | Anchor selection condition                                  | Purpose                          |
| ------ | ----------------------------------------------------------- | -------------------------------- |
| PIT-7  | A stock_id whose security_lifecycle mainboard date is       | EMERGING-period exclusion        |
|        | within the dataset, with a date 10–18 trading days after    |                                  |
|        | mainboard so the 21d window straddles the transition.       |                                  |
|        | Compute MUST return null `ud_ratio_21d` (n_obs_21d < 15)    |                                  |
|        | because pre-mainboard rows are excluded by the view.        |                                  |
| PIT-8  | A (stock_id, date) corporate-action event with at least one | Adjusted-price source lineage    |
|        | row in corporate_actions satisfying                         |                                  |
|        | |adjustment_factor - 1.0| > 0.2, within view date range,    |                                  |
|        | and a target date such that the 21d window straddles the    |                                  |
|        | event date. Multi-source rows on the same (stock_id, date)  |                                  |
|        | are an acknowledged data condition (see                     |                                  |
|        | BACKLOG-CORP-ACTIONS-MULTI-SOURCE-001) and do not           |                                  |
|        | invalidate the anchor; PIT-8 verifies adj vs raw lineage,   |                                  |
|        | NOT corporate-action source adjudication.                   |                                  |
| PIT-10 | Any R8 event from r8_events.parquet within view date range  | SQL parity vs r8_event_builder   |
|        | with full 21d lookback available.                           |                                  |
| PIT-12 | Known non-trading dates: weekends, CNY (any year in XTAI    | Non-trading-day rejection        |
|        | coverage), at least one typhoon closure within the XTAI     |                                  |
|        | coverage window.                                            |                                  |

Concrete anchor selections live in `tests/features/conftest.py`
constants (Phase C) and may be updated as data evolves, provided the
above conditions remain satisfied.

### 13.3 Anchor Maintenance

Failing-test messages MUST include reconstruction guidance pointing
back to the spec condition (§13.2) and a re-selection hint, so
future maintainers can update anchors without consulting prior
conversation history.
