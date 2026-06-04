# P1-DATA Remediation Closeout — 2026-06-04

## Status

**CLOSED**
All acceptance criteria satisfied. R8 Phase 1 findings upgraded from
PROVISIONAL to CONDITIONAL.

## Problem Statement

`daily_price_adj` contained 7,331 rows of emerging-board (興櫃) history
for 18 stocks, predating their TWSE main-board listing dates. Emerging-board
trading has no daily price limit and different microstructure, making these
rows incomparable to listed-market rows. The contamination distorted
cross-sectional RS quantile computation and R8 event qualification.

Root cause: `company_metadata.listing_date` stores board-transfer date,
not original listing date, for transfer-board names.

## Governance

| Artifact | Location | Commit |
|---|---|---|
| Assessment | research/P1-DATA_panel_integrity_assessment.md | — |
| SPEC v1.0.0 | docs/decision_records/p1_data_remediation_spec.md | 74904e1 |
| Seed dataset | data/reference/security_lifecycle_seed_v1.csv | (prior session) |
| Seed SHA-256 | 6a0989936f2ab382b42a505d4cdd936a08a186709c11b1b29d74bb2647c4625a | — |

## Implementation Commits

| Commit | Description |
|---|---|
| 74904e1 | governance(p1-data): approve remediation spec and seed dataset |
| 9c9d72b | feat(schema): add security_lifecycle table — v0.1.20 |
| 85dbbf4 | feat(p1-data): add ingest_security_lifecycle.py v0.1.1 |
| f2d6d61 | feat(p1-data): add listed_market_daily_price_adj view |
| 14436de | research(p1-data): implement AC-4 contamination impact audit |
| bb97d93 | research(p1-data): redirect R8 pipeline to listed_market_daily_price_adj |

## Acceptance Criteria Results

| AC | Criterion | Result |
|---|---|---|
| AC-1 | security_lifecycle contains 18 rows | PASS |
| AC-2 | listed_market_daily_price_adj view exists and queryable (236,713 rows) | PASS |
| AC-3 | Zero violations: no pre-mainboard rows survive view filter | PASS |
| AC-4 | Contamination impact report produced | PASS |
| AC-5 | R8 Phase 1 pipeline rerun completed | PASS |
| AC-6 | New manifest records seed SHA-256, excluded rows, affected events, residual risks | PASS |
| AC-7 | R8 Phase 1 findings upgraded PROVISIONAL → CONDITIONAL | PASS |

## Contamination Impact

| Metric | Value |
|---|---|
| Excluded rows | 7,331 |
| Stocks with exclusions | 18 |
| Affected R8 events (pre-rebuild) | 463 (5.49%) |
| Net event count change after rebuild (Δ) | -418 (-4.96%) |
| R8 events: before → after | 8,430 → 8,012 |
| n_eff: before → after | 396.2 → 381.3 |

## Benchmark Results: Provisional vs Remediated

| Benchmark | Provisional | Remediated | Δ |
|---|---|---|---|
| A: RS_T3 Hold (ret_20d) | +2.52% (see note) | +2.52% | — |
| B: RS_T3 + Pullback (ret_20d) | +2.54% (see note) | +2.54% | — |
| C: R8 within RS_T3 (ret_20d) | +6.84% | +6.77% | -0.07pp |
| C unconditional aligned (ret_20d) | +2.82% | +2.71% | -0.11pp |

> **Note on A/B provisional figures:** The original provisional benchmark
> artifacts were overwritten by the Step 4 rerun before the delta could be
> verified from source. Provisional figures for A and B are taken from
> handoff_2026_06_03_session_end.md and should be treated as approximate.
> Benchmark C provisional figure (+6.84%) is confirmed from the same
> handoff. The key finding (Benchmark C stability) is unaffected.

**Key finding:** Benchmark C uplift is robust to IF-1 remediation.
The hypothesis that Benchmark C was an emerging-board artifact is not
supported. The net -418 event change was predominantly outside the
R8×RS_T3 cell (R8 subset: 4,031 → 4,028, Δ = -3).

## Status Transition
PROVISIONAL → CONDITIONAL
IF-1 listing-status contamination has been remediated. R8 Phase 1
findings are no longer provisional with respect to listing-status
contamination, but remain conditional on the following residual risks.

## Residual Risks

| Risk | Tracking |
|---|---|
| SUSPENSION_GAP: 203 rows, 90 stocks; halt-resumption cross-gaps unclassified | Deferred — no halt/suspension dataset |
| Transfer-board post-listing anomalies: 4583, 6770, 6789 | P1-DATA-TB (new backlog item) |
| corporate_actions empty: cum_factor=1.0 for all stocks | DQ-CA-001 |

---
*End of p1_data_remediation_closeout_2026-06-04.md*
