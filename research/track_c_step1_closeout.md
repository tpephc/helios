# Track C Step 1 Closeout

**Feature:** `ud_ratio_21d`
**Track:** C
**Status:** STEP 1 COMPLETE
**Date:** 2026-06-23
**Spec version (locked, unchanged):** v0.1.4
**Owner:** Veronica
**Repository:** Helios (`~/projects/helios`)

This document is **execution evidence**, not a spec amendment. The
spec (`docs/features/ud_ratio_21d_spec.md` v0.1.4) is the contract;
this closeout records what was built, the governance decisions taken
during construction, and what remains deferred. Step 2 work
(R1 correlation analysis) has NOT begun and no numbers have been
unlocked.

---

## 1. Deliverable

```
Feature ID:        ud_ratio_21d
Public API:        add_ud_ratio_21d(df, *, min_obs=MIN_OBS) -> pl.DataFrame
Module:            features/ud_ratio.py
Output columns:    ud_ratio_21d  (Float64)
                   n_obs_21d     (UInt8)
                   n_up_21d      (UInt8)
Implementation:    Pure Polars (LazyFrame-compatible)
Universe:          R8 treatment_1 via listed_market_daily_price_adj view
```

Conceptual definition: fraction of valid trading days within a
trailing 21-trading-day window on which a stock's daily simple
return on adjusted close was strictly positive. Sign-frequency
persistence feature, by construction less outlier-sensitive than
RS-60d (cumulative magnitude momentum) or MA5 momentum.

---

## 2. Governance Decisions

The following five decisions shaped the implementation and remain
the durable contract behind the Step 1 deliverable. They were
ratified in dedicated gate / lock conversations during Phase 1A–1C.

### D1 — DataFrame-native API; UDRatioResult dataclass rejected

Initial spec (v0.1.0–v0.1.3) proposed a scalar `@dataclass(frozen=True)
UDRatioResult`. GATE-S1-IMPL-001 discovery showed that the
`features/*` subsystem in Helios is uniformly Polars-DataFrame-
native (panel-in, panel-out, pure functions; precedents:
`features/regime.py`, `features/bullish_features.py`,
`features/technical.py`). Introducing a scalar result object would
have been an architectural pattern shift, not a feature addition.

**Decision:** DataFrame-native API. `UDRatioResult` and the
associated `window_start`/`window_end` provenance fields removed
in spec v0.1.4. Each output row's `date` IS the window-end by
construction; no separate column needed.

### D2 — Pure Polars implementation; DuckDB SQL runtime rejected

Spec §4.1 mandates daily-return computation semantically equivalent
to the R8/Phase 1–6 canonical SQL recipe (`research/r8_event_builder.py`
`price_panel` CTE). Two implementation strategies were considered:

- **Option α (rejected):** DuckDB SQL inside Polars via roundtrip
- **Option β (adopted):** Pure Polars expression

Rationale for β:
- Aligned with existing `features/*` Polars-native convention
- LazyFrame-compatible (spec §5.1 requirement)
- No DuckDB roundtrip overhead on large panels
- SQL recipe remains the **oracle** for PIT-10 SQL parity, but is
  not the **implementation dependency**

### D3 — Flat-day rule (locked via Lock L1, Phase 1B)

| `r`         | `n_obs_21d` | `n_up_21d` |
| ----------- | ----------- | ---------- |
| `r > 0`     | +1          | +1         |
| `r < 0`     | +1          | 0          |
| `r == 0`    | +1          | 0          |
| `r` is null | 0           | 0          |

Flat days count toward valid observations but NOT toward positive
days. PIT-4 canonical assertion: **20 up + 1 flat = 20/21**, not
20/20.

Rationale: `r == 0` is a real trading-day observation. Excluding
flat days from the denominator would conflate flatness with missing
data. Counting them as up would mislabel low-volatility persistence
as positive persistence.

### D4 — Strict comparison; no epsilon (locked via Lock L2, Phase 1B)

Sign classification uses Polars `> 0.0`, `< 0.0`, `== 0.0` exact
predicates. No `abs(r) > epsilon` tolerance.

Rationale:
- This is a sign-frequency feature, not a numerical optimization
- Adjusted-close ratios on TWSE-tick-quantized prices do not
  produce floating-point noise of magnitude `~1e-18` that could
  ambiguously sign-classify
- Any such noise would be a data-quality signal, not a feature-
  layer concern; epsilon would mask it

IEEE 754 `-0.0` is correctly handled by `>` (yields False) and
`==` (yields True), so signed zero is classified as flat without
special casing.

### D5 — SQL parity contract: bit-exact (Lock L5, Phase 1D)

PIT-10 asserts bit-exact equality between Path A
(`add_ud_ratio_21d` output) and Path B (DuckDB SQL recipe with
rolling window function) on the resulting `n_obs_21d`, `n_up_21d`,
and `ud_ratio_21d` at the signal date.

Operational evidence (Phase 1D nexus run, commit `427d4b7`):
**bit-exact achieved on 20 anchors across 4 years (2022–2025)
without any tolerance applied.** The Phase 1D conversation
pre-registered a tolerance fallback path (1e-15) if ULP drift
appeared; this path was not needed.

Spec §11.1 retains the bit-exact contract. No empirical evidence
exists that would justify weakening it.

---

## 3. PIT Coverage

All 13 PIT invariants from spec §4.5, §5.3, §11, §12, §13 have
landing tests and are green on nexus as of commit `427d4b7`.

| PIT    | Invariant                                         | Phase | Status |
| ------ | ------------------------------------------------- | ----- | ------ |
| PIT-1  | Lookahead protection (future row mutation)        | 1C    | PASS   |
| PIT-2  | Determinism (within-process)                      | 1C    | PASS   |
| PIT-3  | min_obs coupling (I3: null iff n_obs < min_obs)   | 1B    | PASS   |
| PIT-4  | Flat-day semantics (D3 truth table)               | 1B    | PASS   |
| PIT-5  | NaN return excluded from both n_obs and n_up      | 1B    | PASS   |
| PIT-6  | Window-end identity (row's date IS window-end)    | 1B    | PASS   |
| PIT-7  | EMERGING-period exclusion via view                | 1D    | PASS   |
| PIT-8  | Fixture provenance (raw vs view divergence)       | 1D    | PASS   |
| PIT-9  | min_obs parameter override                        | 1B    | PASS   |
| PIT-10 | SQL parity bit-exact vs r8_event_builder recipe   | 1D    | PASS   |
| PIT-11 | Forbidden imports (AST inspection)                | 1C    | PASS   |
| PIT-12 | Non-trading-day window_end rejected               | 1A    | PASS   |
| PIT-13 | Window construction (K=45 + fail-fast)            | 1A    | PASS   |

Total: **67 tests green** across `tests/features/`
(schema 23 + synthetic PIT 34 + anchored DB PIT 10).

---

## 4. Commits

```
f20d675  Track C: lock ud_ratio_21d v0.1.4 DataFrame-native specification
a48cda9  Track C Phase B: ud_ratio_21d module skeleton + schema tests (v0.1.4)
10cb714  Track C Phase 1A: ud_ratio_21d entry-point validation (PIT-12, PIT-13)
b98a4a3  Track C Phase 1B: ud_ratio_21d Polars computation + PIT-3/4/5/6/9
c9ab948  Track C Phase 1C: ud_ratio_21d lookahead, determinism, and import guards
427d4b7  Track C Phase 1D: ud_ratio_21d anchored DB tests (PIT-7, PIT-8, PIT-10)
```

Six commits, all green on landing. No reverts. No follow-up
patches to feature code after Phase 1B landing (fixture-only
corrections to test infra in Phase 1D v2/v3).

---

## 5. Discoveries During Implementation

Three findings worth recording because they may inform future
decisions:

### F1 — security_lifecycle uses half-open intervals `[from, to)`

Phase 1D PIT-8 v2 initially used `BETWEEN listed_from AND listed_to`
to detect EMERGING-period rows leaking into the view. This flagged
17 false-positive transition-day rows. The correct predicate is
`d.date >= s.listed_from AND d.date < COALESCE(s.listed_to, ...)`.

The transition day (e.g. 6831 / 2025-11-25) belongs to the
mainboard interval (TWSE row's `listed_from`), not the EMERGING
interval (whose `listed_to` is the transition day exclusive). The
view correctly shows the transition day as mainboard.

**Implication:** any future code that walks `security_lifecycle`
boundaries should use half-open intervals. This is now documented
in `tests/features/test_ud_ratio_anchored.py` docstring of
`test_view_excludes_lifecycle_emerging_period`.

### F2 — DuckDB → pandas → Polars loses Date dtype

`con.execute(...).fetchdf()` returns pandas DataFrame; pandas has
no native `date` dtype, so DuckDB `DATE` columns arrive as
`datetime64[us]`. `pl.from_pandas` preserves this as
`Datetime(time_unit='us')`. Strict input validation in
`add_ud_ratio_21d` correctly rejects this.

Workaround applied in Phase 1D anchored tests: explicit
`pl.col("date").cast(pl.Date)` after `from_pandas`. A more
idiomatic alternative (`pl.from_arrow(con.execute(...).arrow())`)
was deferred as a future cleanup; not landing this round.

### F3 — Polars sample(n=height) is not a guaranteed shuffle

Phase 1C `df.sample(n=height, with_replacement=False, seed=42)`
and `df.sample(fraction=1.0, shuffle=True, seed=42)` both returned
the original ordering for this DataFrame size on Polars 1.41.x.
`df.reverse()` was substituted as a deterministic, version-
independent guaranteed-permutation primitive. Documented inline in
`test_shuffled_multi_stock_panel_rejected`.

---

## 6. Deferred Items

```
BACKLOG-CALENDAR-LEGACY-001    repo-wide audit of utils/trading_calendar consumers
                               and migration to canonical market.trading_calendar
                               (Track C contributes Tier 1 only; Tier 2/3 are
                               Helios platform scope)

BACKLOG-CORP-ACTIONS-MULTI-SOURCE-001
                               survey of multi-source rows in corporate_actions
                               (PK = date, stock_id, kind) and resolution policy
                               for dividend_adjustment pipeline
```

No new backlog items surfaced during Step 1 implementation. No open
blockers for Step 2.

---

## 7. Step 2 Readiness

Step 1 acceptance criteria (spec §8) are satisfied:

```
[X] Q1–Q4 design decisions resolved
[X] Spec at v0.1.4
[X] Module + constants + API signature implemented
[X] Schema tests + row-invariant tests (TestInputValidation,
    TestConstants, TestPublicAPISignature)
[X] §4.1 lineage policy enforced via PIT-10
[X] Trading calendar source canonical (market.trading_calendar)
[X] Fixture strategy executed (synthetic + anchored-real)
[X] PIT-1..PIT-13 all green
[X] No imports of utils.trading_calendar or utils.trading_dates
[X] SQL parity bit-exact against r8_event_builder recipe (verified
    on 20 anchors across 4 years)
```

Track C may proceed to Step 2 (R1 correlation analysis) without
additional implementation work.

R1 process is pre-registered in spec §10:
- Compute cross-sectional Spearman per day for
  rho(ud_ratio_21d, RS_60d), rho(ud_ratio_21d, ROC_20d),
  rho(ud_ratio_21d, win_rate_21d)
- Characterise time-series distribution (median, IQR, tail,
  regime conditioning)
- Compare against prior Track-C proxy-collapse cases
- Set escalation threshold AFTER characterisation (process locked,
  number deliberately unlocked)

**No R1 numbers have been computed or examined.** Step 2 should
begin with R1 number-lock pre-registration before the first
correlation query is run.

---

## 8. Closeout Boundary

This document records what Step 1 produced and how. It does NOT:

- Amend spec v0.1.4 (the contract remains unchanged)
- Update backlog items (no new issues)
- Unlock R1 escalation threshold (deferred to Step 2)
- Examine any correlation or empirical alpha evidence
- Pre-judge `ud_ratio_21d` orthogonality vs RS_60d / ROC_20d
- Commit to Step 2 timeline or scope

The next governance event is **Step 2 pre-registration**, at which
point R1 process re-confirms, sample window is selected, and the
escalation threshold is committed BEFORE any number is read.

---

*End of closeout. Spec v0.1.4 remains the authoritative contract.*
