# SPEC-P1-DATA-REMEDIATION-v1

Status: ACCEPTED
Scope: IF-1 only
DB: `data/_storage/helios.duckdb`
Authority: ADR-P1-DATA-001
Seed: `data/reference/security_lifecycle_seed_v1.csv`

---

## 1. Objective

Remediate IF-1 pre-listing / emerging-board panel contamination.

All R8 Phase 1 findings remain PROVISIONAL until this SPEC is implemented,
verified, and the promotion gate passes.

---

## 2. Non-Goals

This SPEC does not remediate:

- IF-2 empty `stock_info`
- IF-3 empty `corporate_actions`
- halt / suspension / delisting lifecycle
- historical PIT universe reconstruction beyond the 18 transfer-board stocks

`OTC` and `TPEx` market values are reserved for future lifecycle coverage.
v1 remediation scope covers only EMERGING → TWSE transfer-board securities.

---

## 3. Lifecycle Model

`security_lifecycle` uses half-open intervals:

```text
listed_from <= trade_date < listed_to
```

If `listed_to IS NULL`:

```text
trade_date >= listed_from
```

For each of the 18 seed stocks, two lifecycle rows are required:

```text
EMERGING row:
    listed_from = otc_first_date
    listed_to   = mainboard_date

TWSE row:
    listed_from = mainboard_date
    listed_to   = NULL
```

`mainboard_date` belongs to the TWSE row.
The EMERGING row does not include `mainboard_date`.

---

## 4. DDL

```sql
CREATE TABLE IF NOT EXISTS security_lifecycle (
    stock_id     TEXT      NOT NULL,
    listed_from  DATE      NOT NULL,
    listed_to    DATE,
    market       TEXT      NOT NULL,
    source_type  TEXT      NOT NULL,
    source_url   TEXT      NOT NULL,
    verified_at  TIMESTAMP,
    verified_by  TEXT,
    notes        TEXT,

    PRIMARY KEY (stock_id, listed_from),

    CHECK (listed_to IS NULL OR listed_from < listed_to),
    CHECK (market IN ('EMERGING', 'OTC', 'TWSE', 'TPEx'))
);
```

---

## 5. Seed ETL

Input:

```text
data/reference/security_lifecycle_seed_v1.csv
```

Required columns:

```text
stock_id, otc_first_date, mainboard_date, mainboard_type,
source_type, source_url, verified_at, verified_by, notes
```

For each seed row, insert two lifecycle rows:

**Step 1 — Insert EMERGING row:**

```text
listed_from = otc_first_date
listed_to   = mainboard_date
market      = 'EMERGING'
source_type = taken directly from the corresponding seed CSV row
source_url  = taken directly from the corresponding seed CSV row
verified_at = taken directly from the corresponding seed CSV row
verified_by = taken directly from the corresponding seed CSV row
notes       = taken directly from the corresponding seed CSV row
```

**Step 2 — Insert TWSE row:**

```text
listed_from = mainboard_date
listed_to   = NULL
market      = mainboard_type (from seed CSV row)
source_type = taken directly from the corresponding seed CSV row
source_url  = taken directly from the corresponding seed CSV row
verified_at = taken directly from the corresponding seed CSV row
verified_by = taken directly from the corresponding seed CSV row
notes       = taken directly from the corresponding seed CSV row
```

**Provenance invariant:**

For both lifecycle rows, all provenance fields (`source_type`, `source_url`,
`verified_at`, `verified_by`, `notes`) shall be copied directly from the
corresponding `security_lifecycle_seed_v1.csv` row.

No provenance field may be inferred, generated, or modified during ETL.

ETL must be idempotent.

---

## 6. Panel Eligibility Predicate

Helios research panel scope is **listed-market only** (TWSE / TPEx).
EMERGING-period rows (otc_first_date <= date < mainboard_date) are
contaminated: they reflect a different market microstructure (no price
limits, different liquidity regime) and must be excluded.

The contamination is 7331 rows across 18 stocks confirmed in
`research/P1-DATA_panel_integrity_assessment.md`.  All 7331 rows exist
in `daily_price_adj` within the EMERGING interval
[otc_first_date, mainboard_date).

Listed-market eligibility predicate (for stocks with a lifecycle record):

```sql
p.date >= l.listed_from
AND (l.listed_to IS NULL OR p.date < l.listed_to)
AND l.market IN ('TWSE', 'TPEx')
```

For the 18 seed stocks this is equivalent to:

```sql
date >= mainboard_date
```

Pass-through predicate (for stocks without a lifecycle record):

```sql
-- no lifecycle record → no filter applied
COALESCE(
    (SELECT MIN(l.listed_from)
     FROM security_lifecycle l
     WHERE l.stock_id = p.stock_id
       AND l.market IN ('TWSE', 'TPEx')),
    DATE '1900-01-01'
)
```

Implementation: `data/eligible_universe.eligible_date_predicate(alias)`
returns the COALESCE-based SQL fragment.  Stocks without any lifecycle
record pass through unchanged via the `DATE '1900-01-01'` sentinel.

Note on the three exception stocks (4583, 6770, 6789): their EMERGING-
period rows have a different DQ root cause (not typical OTC microstructure
artifacts) but are excluded by the same predicate.  No special-case logic
is required.

---

## 7. Recompute Blast Radius

Do not recompute only the 18 affected stocks.

Full-panel recomputation is required for generation consistency.  The
mechanism is as follows:

`bullish_features.beta_adj_rs_20d` and `beta_adj_rs_60d` are stock-vs-TAIEX
time-series beta-adjusted relative returns, not peer-universe percentile
ranks.  Each stock's value is computed independently from its own price path
and TAIEX.  Removing the 18 stocks' contaminated rows does not change other
stocks' `beta_adj_rs_20d` values directly.

However, `r8_event_builder.py` computes a per-date cross-sectional RS_T3
threshold via `PERCENTILE_CONT(2/3) WITHIN GROUP (ORDER BY beta_adj_rs_20d)`.
Removing 7331 contaminated rows from the universe changes the daily
cross-sectional distribution of `beta_adj_rs_20d`, which shifts the RS_T3
threshold and therefore changes `rs_t3_flag_same_day` and `rs_t3_t_minus_1`
for all stocks on affected dates.

Additionally, `daily_features` and `bullish_features` derived from the
contaminated panel must not be mixed with remediated artifacts.  Mixed-
generation panels are invalid regardless of whether individual values change.

Remediation therefore requires full-panel recomputation of:

```text
daily_features
bullish_features          (includes beta_adj_rs_20d / beta_adj_rs_60d)
bearish_features
RS_T3 cross-sectional threshold (inside r8_event_builder.py, per-date)
R1 / R2 / R5 research artifacts
R8 Phase 1 artifacts
```

Any partial recomputation is invalid.

---

## 8. Required Re-run Order

```text
1.  Backup DuckDB file and current R8 artifacts (see Section 11)
2.  Create / refresh security_lifecycle table
3.  Apply panel eligibility filter (scripts/compute_features.py patched)
4.  Rebuild daily_features:
        uv run python scripts/compute_features.py
5.  Rebuild bullish_features (recomputes beta_adj_rs_20d / beta_adj_rs_60d):
        uv run python scripts/compute_bullish_features.py
6.  Rebuild bearish_features:
        uv run python scripts/compute_bearish_features.py
7.  Re-run R1: uv run python research/rs_persistence_decay.py
8.  Re-run R2: uv run python research/rs_acceleration.py
9.  Re-run R5: uv run python research/pullback_quality.py
10. Re-run R8 Phase 1:
        r8_event_builder        (recomputes RS_T3 cross-sectional threshold)
        r8_forward_returns
        r8_lifecycle_metrics
        r8_benchmarks
        r8_phase1_export        (write to data/_storage/r8_phase1_remediated/)
11. Generate delta report
```

Note: steps 4–6 enforce the panel eligibility predicate via
`data/eligible_universe.eligible_date_predicate()`.  The RS_T3 cross-
sectional threshold recomputation in step 10 is implicit inside
`r8_event_builder.py` and requires no additional patching.

---

## 9. Delta Report Minimum Schema

Delta report must include at least:

```text
n_events_provisional
n_events_remediated
n_events_delta

benchmark_a_ret_20d_mean_provisional
benchmark_a_ret_20d_mean_remediated
benchmark_a_ret_20d_mean_delta

benchmark_b_ret_20d_mean_provisional
benchmark_b_ret_20d_mean_remediated
benchmark_b_ret_20d_mean_delta

benchmark_c_ret_20d_mean_provisional
benchmark_c_ret_20d_mean_remediated
benchmark_c_ret_20d_mean_delta

near_limit_up_ratio_provisional
near_limit_up_ratio_remediated
near_limit_up_ratio_delta

rs_t3_null_rows_provisional
rs_t3_null_rows_remediated
rs_t3_null_rows_delta

affected_stock_ids
row_exclusion_count_by_stock_id
total_rows_excluded          (expected: 7331 EMERGING-period rows)
artifact_paths_provisional
artifact_paths_remediated
generated_at
spec_version
```

---

## 10. Promotion Gate

R8 findings may be promoted from PROVISIONAL to NON-PROVISIONAL only if
all gates pass.

```text
PG-1   security_lifecycle_seed_v1 acceptance checks remain 18/18 PASS

PG-2   security_lifecycle table contains exactly two rows per seed stock

PG-2b  No interval overlap exists for any stock_id.
       For every stock, all lifecycle intervals must be non-overlapping
       under the half-open convention: [listed_from, listed_to).
       NULL listed_to is treated as open-ended via sentinel DATE '9999-12-31'.
       Canonical ordering (a.listed_from < b.listed_from) ensures each
       pair is evaluated exactly once.
       Verification query:
           SELECT a.stock_id
           FROM   security_lifecycle a
           JOIN   security_lifecycle b
                  ON  a.stock_id    = b.stock_id
                  AND a.listed_from < b.listed_from
           WHERE  a.listed_from < COALESCE(b.listed_to, DATE '9999-12-31')
             AND  b.listed_from < COALESCE(a.listed_to, DATE '9999-12-31')
       Must return zero rows.

PG-3   No affected stock has rows in EMERGING period (date < mainboard_date) in eligible panel

PG-3b  For the v1 seed set, row_exclusion_count_by_stock_id must be
       non-zero for all 18 affected stocks.
       If any of the 18 v1 seed stocks shows zero excluded rows, the
       panel filter must be treated as not having taken effect,
       regardless of PG-3.
       Note: this gate is v1 seed-specific. Future stocks where
       mainboard_date precedes or equals the panel start date may
       legitimately produce zero excluded rows and must not be
       evaluated against this gate.

PG-4   Full-panel bullish_features recomputed from remediated daily_features
       (beta_adj_rs_20d / beta_adj_rs_60d regenerated for all stocks)

PG-5   R8 Phase 1 is fully re-run on remediated panel

PG-6   Delta report contains all required fields (Section 9)

PG-7   Benchmark deltas are reviewed and signed off

PG-8   Provisional artifacts are preserved, not overwritten
```

---

## 11. Rollback / Backup Policy

Before remediation begins:

```text
Backup DuckDB file:
    data/_storage/helios.duckdb
    →
    data/_storage/helios.duckdb.pre_p1_remediation

Backup R8 provisional artifacts:
    data/_storage/r8_phase1/
    (do not delete or overwrite)

Record git HEAD and SPEC checksum.
```

Remediated artifacts must be written to a new path:

```text
data/_storage/r8_phase1_remediated/
```

Do not overwrite:

```text
data/_storage/r8_phase1/
```

**Rollback procedure:**

```text
1. Stop all writers.
2. Restore file copy:
       data/_storage/helios.duckdb.pre_p1_remediation
       →
       data/_storage/helios.duckdb
3. Re-run validation queries to confirm restored state.
```

---

## 12. Acceptance Criteria

Implementation is complete only when:

```text
AC-1  security_lifecycle DDL applied
AC-2  seed ETL idempotency verified
AC-3  half-open interval semantics tested
AC-4  no interval overlap for any stock_id (PG-2b COALESCE-sentinel query returns zero rows)
AC-4b row_exclusion_count_by_stock_id is non-zero for all 18 affected stocks (PG-3b)
AC-5  EMERGING-period rows (date < mainboard_date) excluded from eligible panel
AC-6  full RS recomputation completed
AC-7  R8 Phase 1 remediated artifacts generated
AC-8  delta report generated and contains all required fields
AC-9  promotion gate result recorded
AC-10 test suite remains green
```

---

## 13. Explicit Failure Conditions

The remediation fails if any of the following occurs:

```text
- mainboard_date is included in the EMERGING row interval
- listed_from is inferred from first available price date rather than seed CSV
- filter uses date >= otc_first_date instead of date >= mainboard_date
- any provenance field is inferred, generated, or modified during ETL
- only the 18 affected stocks are recomputed (partial recomputation)
- R8 provisional artifacts are overwritten in place
- delta report omits Benchmark A/B/C ret_20d mean
- interval overlap exists for any stock_id
- row_exclusion_count_by_stock_id is zero for any affected stock (filter not effective)
- findings are promoted without all promotion gates passing
```

---

## 14. Research Status After SPEC

Until all promotion gates pass:

```text
R8 Phase 1 findings = PROVISIONAL
```

After all promotion gates pass:

```text
R8 Phase 1 findings may be reviewed for NON-PROVISIONAL promotion
```

---

*SPEC-P1-DATA-REMEDIATION-v1 — generated 2026-06-05*
