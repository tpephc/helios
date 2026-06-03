# P1-DATA Remediation SPEC

<!-- docs/decision_records/p1_data_remediation_spec.md -->
<!-- Governance artifact. Authorises remediation of panel listing-status
     contamination identified in research/P1-DATA_panel_integrity_assessment.md.
     This document supersedes the "Proposed scope" section of
     docs/backlog/backlog_P1-DATA_listing_status_integrity.md for
     implementation purposes. The backlog item remains open until all
     acceptance criteria below are satisfied. -->

**Status:** APPROVED  
**Version:** 1.0.0  
**Date:** 2026-06-04  
**Author:** Veronica  
**Supersedes:** Proposed scope in backlog_P1-DATA_listing_status_integrity.md  
**Assessment reference:** research/P1-DATA_panel_integrity_assessment.md v0.1.0  
**Seed artifact:** data/reference/security_lifecycle_seed_v1.csv (SHA-256 to be
recorded at ingest time)

---

## 1. Purpose

This document authorises and fully specifies the remediation of IF-1
(pre-listing / emerging-board contamination, 18 stocks / 7331 rows) identified
in the P1-DATA panel integrity assessment. It locks the remediation approach,
source, schema, filter rule, scope boundaries, and acceptance criteria before
any implementation begins.

This document does NOT authorise:

- Physical deletion of contaminated rows from `daily_price_adj`.
- Remediation of IF-2 (`stock_info` empty) or IF-3 (`corporate_actions` empty).
- Investigation of post-listing anomalies in transfer-board stocks 4583, 6770,
  6789 (out of scope; to be tracked separately as P1-DATA-TB).
- Introduction of any minimum listed-age filter on the research universe.
- Changes to research universe composition beyond listing-status filtering.

---

## 2. Decisions

| ID  | Decision | Rationale |
|-----|----------|-----------|
| D-1 | Trusted source: MOPS, hand-verified | 18 stocks is tractable for manual verification; MOPS is the authoritative official source for Taiwan security lifecycle events |
| D-2 | Storage: DuckDB (`market_data.duckdb`) | `security_lifecycle` is market data, same layer as `daily_price_adj`; R8 pipeline queries DuckDB natively; avoids ETL sync risk |
| D-3 | Exclusion mechanism: view, not physical delete | Reversible if `mainboard_date` corrections are required; preserves audit trail; consistent with project provenance governance |
| D-4 | Transfer-board stocks 4583/6770/6789: apply OTC filter only | Post-listing anomalies are a distinct failure mode; mixing them into P1-DATA would inflate scope and contaminate attribution |
| D-5 | SUSPENSION_GAP (203 rows, 90 stocks): deferred | No halt/suspension dataset exists; these rows affect normal long-listed stocks only; deferral does not block IF-1 remediation |
| D-6 | No minimum listed-age filter | P1-DATA scope is listing-status contamination only; introducing a duration filter would create an attribution gap between pre- and post-remediation Phase 1 results |

---

## 3. Trusted Source

**Source:** MOPS (公開資訊觀測站)  
**URL pattern:** `https://mops.twse.com.tw/mops/#/web/t05st03?companyId={stock_id}`  
**Verified by:** Veronica  
**Verified at:** 2026-06-03  
**Coverage:** 18 affected stocks (IF-1 scope only)  
**Seed file:** `data/reference/security_lifecycle_seed_v1.csv`

The seed file provides, for each of the 18 stocks:

| Field | Semantics |
|-------|-----------|
| `stock_id` | VARCHAR, matches `daily_price_adj.stock_id` |
| `otc_first_date` | Date of first OTC (興櫃) trading session |
| `mainboard_date` | Date of first listed-market (TWSE/TPEx) trading session |
| `mainboard_type` | Board type after transfer (`TWSE` or `TPEx`) |
| `source_type` | Provenance label (`MOPS`) |
| `source_url` | Direct MOPS URL used for verification |
| `verified_at` | Date of manual verification |
| `verified_by` | Verifier identity |
| `notes` | Free-text; transfer-board provisional flags recorded here |

The remaining 187 panel stocks are not included in the seed file because they
have no IF-1 contamination. They are not required to appear in
`security_lifecycle` for the filter view to function correctly (see Section 5).

---

## 4. Schema

```sql
CREATE TABLE IF NOT EXISTS security_lifecycle (
    stock_id        VARCHAR     NOT NULL,
    otc_first_date  DATE,
    mainboard_date  DATE        NOT NULL,
    mainboard_type  VARCHAR     NOT NULL,
    source          VARCHAR     NOT NULL,
    source_url      VARCHAR,
    verified_at     DATE        NOT NULL,
    verified_by     VARCHAR     NOT NULL,
    notes           VARCHAR,
    PRIMARY KEY (stock_id)
);
```

**Constraints and invariants:**

- `mainboard_date` is NOT NULL and must be a valid trading date.
- `otc_first_date` is nullable (some stocks may lack OTC history records).
- Where both dates are present: `otc_first_date < mainboard_date` must hold.
- `stock_id` must match the `VARCHAR` type used in `daily_price_adj`.
- Schema changes require a new version of this SPEC.

---

## 5. Filter Rule

### Definition

A row `(stock_id, date)` in `daily_price_adj` is a **listed market session** if
and only if one of the following holds:

1. The stock has no entry in `security_lifecycle` (stock was listed from the
   start of the panel; no OTC contamination); **OR**
2. The stock has an entry in `security_lifecycle` AND
   `daily_price_adj.date >= security_lifecycle.mainboard_date`.

### Implementation

```sql
CREATE VIEW listed_market_daily_price_adj AS
SELECT p.*
FROM daily_price_adj p
LEFT JOIN security_lifecycle s
    ON p.stock_id = s.stock_id
WHERE s.stock_id IS NULL
   OR p.date >= s.mainboard_date;
```

**Properties of this view:**

- Stocks absent from `security_lifecycle` pass through unfiltered (LEFT JOIN
  with NULL check).
- Only rows predating `mainboard_date` are excluded; no stock is fully removed
  from the panel.
- The view is the single point of enforcement. Research scripts and feature
  pipelines must query `listed_market_daily_price_adj`, not `daily_price_adj`
  directly, after this remediation is applied.

### Transfer-board exception (D-4)

Stocks 4583, 6770, 6789 have post-listing data quality anomalies that are out
of scope for this remediation. The filter rule above applies to them identically
(OTC rows excluded by `date >= mainboard_date`); their post-listing rows are
retained. Residual risk is recorded in the re-run manifest.

---

## 6. Implementation Steps

Steps must be executed in order. Each step has an explicit verification gate
before proceeding.

### Step 1 — Ingest seed into `security_lifecycle`

```python
# scripts/ingest_security_lifecycle.py
# - Read data/reference/security_lifecycle_seed_v1.csv
# - Validate: no nulls in required fields, otc_first_date < mainboard_date
#   where both present, stock_id type compatibility
# - Compute and log SHA-256 of seed file
# - INSERT into security_lifecycle (fail on duplicate stock_id)
# - Log row count inserted
```

Verification gate: `SELECT COUNT(*) FROM security_lifecycle` = 18.

### Step 2 — Create filter view

Execute the `CREATE VIEW listed_market_daily_price_adj` DDL defined in
Section 5.

Verification gate:
```sql
-- Confirm excluded row count matches IF-1 assessment
SELECT COUNT(*) FROM daily_price_adj
LEFT JOIN security_lifecycle s ON daily_price_adj.stock_id = s.stock_id
WHERE s.stock_id IS NOT NULL
  AND daily_price_adj.date < s.mainboard_date;
-- Expected: approximately 7331 rows (exact figure from Step 3 audit)
```

### Step 3 — Contamination impact audit

Before re-running any research pipeline, quantify the remediation impact:

```sql
-- Excluded rows by stock
SELECT p.stock_id, COUNT(*) AS excluded_rows,
       MIN(p.date) AS first_excluded, MAX(p.date) AS last_excluded
FROM daily_price_adj p
JOIN security_lifecycle s ON p.stock_id = s.stock_id
WHERE p.date < s.mainboard_date
GROUP BY p.stock_id
ORDER BY excluded_rows DESC;

-- R8 events affected (events with entry_date < mainboard_date)
-- Query to be written against r8_events.parquet + security_lifecycle
```

Output: contamination impact report. This report is a required input to the
re-run manifest. **Do not proceed to Step 4 until this report is produced.**

### Step 4 — Re-run R8 Phase 1 pipeline

Re-run in order against `listed_market_daily_price_adj`:

1. `research/r8_event_builder.py`
2. `research/r8_forward_returns.py`
3. `research/r8_lifecycle_metrics.py`
4. `research/r8_benchmarks.py`
5. `research/r8_phase1_export.py`

Output artifacts replace the provisional set in `data/_storage/r8_phase1/`.
The new manifest must record:

- Seed file SHA-256
- Excluded row count (from Step 3)
- Number of R8 events affected / excluded
- Residual risks: SUSPENSION_GAP deferred, transfer-board post-listing anomalies
  deferred (P1-DATA-TB)

### Step 5 — R1 / R2 / R5 re-validation

Scope and scheduling to be determined separately. Not a blocking dependency for
R8 Phase 1 upgrade from provisional status.

---

## 7. Out of Scope

The following are explicitly deferred and must NOT be addressed in this
remediation:

| Item | Tracking |
|------|----------|
| SUSPENSION_GAP (203 rows, 90 stocks) | Requires halt/suspension dataset; deferred |
| Transfer-board post-listing anomalies (4583, 6770, 6789) | P1-DATA-TB (new backlog item) |
| IF-2: `stock_info` empty | Separate issue |
| IF-3: `corporate_actions` empty / DQ-CA-001 | Separate issue |
| TWSE Holiday Calendar | P1 production-infra debt; separate issue |
| Minimum listed-age filter | Not introduced; see D-6 |

---

## 8. Acceptance Criteria

All criteria must be satisfied before P1-DATA backlog item is closed.

| ID   | Criterion |
|------|-----------|
| AC-1 | `security_lifecycle` table exists in `market_data.duckdb` with 18 rows |
| AC-2 | `listed_market_daily_price_adj` view exists and is queryable |
| AC-3 | `SELECT COUNT(*) AS violations FROM listed_market_daily_price_adj p JOIN security_lifecycle s ON p.stock_id = s.stock_id WHERE p.date < s.mainboard_date` returns 0 |
| AC-4 | Contamination impact report produced (Step 3 output) |
| AC-5 | R8 Phase 1 pipeline re-run completed against `listed_market_daily_price_adj` |
| AC-6 | New R8 Phase 1 manifest records seed SHA-256, excluded row count, affected event count, and residual risks |
| AC-7 | R8 Phase 1 findings are upgraded from PROVISIONAL to CONDITIONAL: IF-1 listing-status contamination has been remediated, while SUSPENSION_GAP, transfer-board post-listing anomalies, and corporate-actions gaps remain documented residual risks |

**Note on AC-7:** CONDITIONAL means IF-1 contamination has been remediated and
R8 Phase 1 results are no longer provisional with respect to listing-status
contamination, but remain conditional on unresolved residual data risks. The
CONDITIONAL designation is to be recorded in the re-run manifest and carried
forward into any analysis or reporting that cites Phase 1 findings.

---

## 9. Residual Risks After Remediation

| Risk | Scope | Tracking |
|------|-------|----------|
| SUSPENSION_GAP | 203 rows, 90 stocks; halt-resumption cross-gap returns unclassified | Deferred; manifest flag |
| Transfer-board post-listing anomalies | 4583, 6770, 6789; post-`mainboard_date` DQ rows unresolved | P1-DATA-TB |
| `corporate_actions` empty | cum_factor = 1.0 for all stocks; return series not CA-adjusted | DQ-CA-001 |

---

*End of p1_data_remediation_spec.md v1.0.0*
