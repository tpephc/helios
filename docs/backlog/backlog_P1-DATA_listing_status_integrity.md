# Backlog P1-DATA — Historical listing-status integrity

<!-- docs/backlog/P1-DATA_listing_status_integrity.md -->
<!-- Panel-level data-integrity item. Opened 2026-06-01 from R8 Phase 0 findings. -->

**Priority:** P1 (data)
**Opened:** 2026-06-01
**Source:** R8 MA5 Momentum Phase 0 feasibility audit (panel blast-radius diagnostic)
**Scope note:** This is a PANEL-LEVEL issue. It is NOT specific to R8 and must NOT
be patched inside any single research script.

## Problem

`company_metadata.listing_date` does not reliably represent original listing date.
For transfer-board (興櫃 -> 上市/上櫃) names it stores a re-listing / board-transfer
date. Pre-transfer emerging-board history is mixed into `daily_price_adj`.
Emerging-board trading has NO daily price limit and different liquidity /
microstructure, so those rows are not comparable to listed-market rows.

## Evidence (read-only diagnostics, 2026-06-01)

- 18 stocks have `listing_date > first_price_date`.
- 7331 rows in `daily_price_adj` predate the stock's `listing_date`.
- Surfaced via R8 DQ: 135 of 338 `ret_1d >= +10%` signals (17 symbols) are
  PRE_LISTING_OTC; examples 6831 (first_price 2021-08-12 / listing 2025-11-25),
  6805, 7610, 7799, 7769, 2646, 7750.
- A separate 203 rows (90 symbols) are SUSPENSION_GAP (normal long-listed stocks,
  cross-gap returns from halt-resumption); these need a halt/suspension table that
  does not currently exist.

## Affected downstream work

Any analysis touching the 18 transfer-board names' 2021-2024 early history:
R1 / R2 / R5 forward-return panels; replay engine; cross-sectional RS-tertile
(`beta_adj_rs_*`) computation (emerging-board extreme returns distort per-date
quantiles). Severity per study is unquantified; re-validation needed once a
clean lifecycle source exists.

## Why not a quick filter

`date >= listing_date` was explicitly REJECTED: `listing_date` is the known-wrong
column (transfer date, not original listing), so the filter would convert a known
contamination into a hidden one, and would not address the SUSPENSION_GAP rows.
Governance principle: quantify contamination -> obtain a trusted correction source
-> then correct data. Do not correct with a column already known to be wrong.

## Proposed scope

1. Obtain a trusted source for: original first-trading date, emerging-board
   period, board-transfer date, suspension/halt windows, disposition/altered-
   trading periods.
2. Build a `security_lifecycle` table (one row per stock, or per stock-status
   interval) as the single source of truth.
3. Apply a unified `is_listed_market_session` filter at the ingest/feature layer
   (NOT in research scripts), so all downstream panels inherit the same clean
   universe-by-date.
4. Backfill / flag the 7331 pre-listing rows and the SUSPENSION_GAP set.
5. Re-validate R1/R2/R5 conclusions and the replay baseline on the cleaned panel.

## Acceptance

- `security_lifecycle` exists and is populated for all 205 panel stocks.
- 0 rows in `daily_price_adj` survive the lifecycle filter with
  `date < original_listing_or_board_entry`.
- Re-run of the R8 feasibility DQ check yields 0 PRE_LISTING_OTC rows; remaining
  `ret_1d >= +10%` rows are explained by suspension records or confirmed CA.

## Related

- DQ-CA-001 (`corporate_actions` empty; cum_factor = 1.0 for all stocks).
- Empty `stock_info` table (sector mapping fell back to company_metadata).
- R8 Phase 0 feasibility doc: `docs/research/r8_phase0_feasibility.md`.
