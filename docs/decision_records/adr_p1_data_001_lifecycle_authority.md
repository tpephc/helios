# ADR-P1-DATA-001 — Lifecycle Authority Selection for Transfer-Board Stocks

<!-- docs/decision_records/adr_p1_data_001_lifecycle_authority.md -->
<!-- v1.0.0 — 2026-06-03 -->

**Status:** ACCEPTED  
**Date:** 2026-06-03  
**Author:** Veronica  
**Relates to:** P1-DATA backlog, IF-1 (pre-listing contamination)

---

## Context

`daily_price_adj` contains 7331 rows of emerging-board (興櫃) price history
for 18 stocks that have since transferred to TWSE main board. These rows
predate each stock's official TWSE listing date and have different
microstructure characteristics (no daily price limit, different liquidity).

The column `company_metadata.listing_date` stores the board-transfer date,
not the original emerging-board first-trading date. A `date >= listing_date`
filter is therefore unsafe — it would convert confirmed contamination into
hidden contamination.

A systematic, programmable source for original emerging-board first-trading
dates was sought and evaluated. All candidates were tested on 2026-06-03:

| Source | Result | Reason |
|---|---|---|
| TWSE isin portal (strMode=2,4) | FAIL | Returns board-transfer date only; identical to company_metadata.listing_date |
| TPEx isin portal | FAIL | Same as TWSE |
| TPEx OpenAPI /mopsfin_t187ap03_R | FAIL | Current emerging-board snapshot only; transferred stocks absent |
| FinMind TaiwanStockInfo | FAIL | Current snapshot; date field is today's date |
| TPEx legacy URLs | FAIL | All redirect to 404 |

Validation evidence: `data/_storage/p1_data_source_validation.csv`
(18/18 SAME_AS_META_SUSPECT, Phase 0 VERDICT: FAIL, 2026-06-03).

No authoritative, programmable, free source exists for historical
emerging-board first-trading dates of already-transferred stocks.

---

## Decision

**Manual curation of a lifecycle seed file for the 18 affected symbols.**

Source: MOPS (公開資訊觀測站, mops.twse.com.tw) — official regulatory
disclosure platform, primary authority for Taiwan security lifecycle events.

Output: `data/reference/security_lifecycle_seed_v1.csv`

This file is the **Lifecycle Authority v1** for IF-1 remediation.
It is versioned, committed to the repository, and immutable after acceptance.
Any correction requires a new version (v2, v3, ...) with a separate
verification record.

---

## Scope

**Exactly 18 symbols.** No other symbols are in scope for this ADR.

| stock_id | first_price_date | listing_date (current, known-wrong) |
|---|---|---|
| 2645 | 2022-02-21 | 2023-03-14 |
| 2646 | 2022-10-03 | 2024-10-25 |
| 4583 | 2021-05-21 | 2022-05-09 |
| 6446 | 2021-05-21 | 2024-01-25 |
| 6472 | 2021-05-21 | 2023-12-19 |
| 6526 | 2022-06-23 | 2023-10-19 |
| 6691 | 2021-05-21 | 2022-01-03 |
| 6770 | 2021-05-21 | 2021-12-06 |
| 6789 | 2021-05-21 | 2022-06-30 |
| 6805 | 2021-05-21 | 2023-11-09 |
| 6831 | 2021-08-12 | 2025-11-25 |
| 6919 | 2022-12-27 | 2024-10-02 |
| 6944 | 2023-04-28 | 2025-05-28 |
| 7610 | 2023-03-15 | 2025-09-09 |
| 7750 | 2024-06-19 | 2025-09-17 |
| 7769 | 2024-11-04 | 2025-11-27 |
| 7799 | 2024-11-28 | 2025-09-15 |
| 7822 | 2025-03-28 | 2026-03-30 |

---

## Acceptance Gate

**All 18 symbols must be resolvable before the seed file is committed.**

If any symbol cannot be found in MOPS with a verifiable emerging-board
first-trading date, the gate FAILS and the seed file must not be used for
remediation until that symbol is resolved.

Pass criteria:
- All 18 symbols have `otc_first_date` populated
- All 18 symbols have `mainboard_date` populated
- For all 18: `otc_first_date <= first_price_date` (date in DB is not earlier
  than the claimed emerging-board start)
- For all 18: `mainboard_date == listing_date` in company_metadata
  (confirms the column semantics: listing_date = transfer date)
- Each row has a non-null `source_url` pointing to the MOPS page used

---

## Consequences

**Immediate:**
- IF-1 remediation is unblocked once seed file passes acceptance gate
- `security_lifecycle` table can be populated from seed file
- Panel filter `is_listed_market_session()` can be implemented
- R8 Phase 1 findings remain PROVISIONAL until panel rebuild is complete

**Downstream (after seed file accepted):**
- `daily_price_adj`: 7331 pre-otc_first_date rows flagged and excluded
- RS quantile recomputation required (highest blast-radius item)
- R1 / R2 / R5 / R8 Phase 1 full re-run required
- Re-run scope and order to be specified in a separate remediation SPEC

**Future authority migration:**
If TEJ or an equivalent programmable lifecycle source becomes available,
authority may migrate from this seed file to the new source. Migration
requires a new ADR superseding this one. The seed file remains as
provenance record regardless.

**What this ADR does NOT authorise:**
- Symbol-level exclusion of the 18 stocks (Option 2 rejected)
- Any panel rebuild or re-run (requires separate SPEC)
- Remediation of IF-2 (empty stock_info) or IF-3 (empty corporate_actions)

---

## Rejected Alternatives

**Option 2 — Symbol-level exclusion of 18 stocks:**
Rejected. Does not close IF-1 because:
(a) historical RS quantiles computed over contaminated panel are already
    materialised in research artifacts and require recomputation regardless;
(b) violates minimum-correction principle — post-transfer data for these
    symbols is clean and should be retained.

**Option 3 — TEJ subscription:**
Deferred. The 18-symbol contamination set is a finite, one-time problem.
TEJ ROI is justified only if Helios requires point-in-time universe
reconstruction or full survivorship-bias control at scale. Neither is
currently in scope.

---

*End of ADR-P1-DATA-001 v1.0.0*
