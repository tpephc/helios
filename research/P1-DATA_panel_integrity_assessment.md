# P1-DATA — Panel Integrity Assessment

<!-- docs/research/P1-DATA_panel_integrity_assessment.md -->
<!-- v0.1.0 — 2026-06-02 -->

**Status:** OPEN — remediation not started
**Source:** `docs/research/r8_phase0_feasibility.md` (closed 2026-06-01, rev2)
**Tool:** `research/ma5_momentum_feasibility.py` v0.1.2 (read-only DuckDB audit)
**Scope:** All quantitative figures are verbatim from the Phase 0 audit run
(2026-06-01 09:20) and follow-up read-only diagnostics. None are estimated.

---

## Status

Three panel integrity gaps are confirmed open as of 2026-06-02. No
remediation has been approved or started. This document is the canonical
evidence base for the P1-DATA backlog item. It records what is broken,
how certain the findings are, and how large the impact is. It does not
specify how or when remediation will occur.

---

## Summary Verdict

| Finding | Severity | Certainty | Remediation status |
|---|---|---|---|
| IF-1: Pre-listing / emerging-board contamination | High | Confirmed, measured | Open — no approved fix |
| IF-2: Empty `stock_info` | Medium | Confirmed | Open — workaround in use |
| IF-3: Empty `corporate_actions` | Medium | Confirmed | Open — affected rows unresolvable |

All three findings were discovered during R8 Phase 0. None are R8-specific;
they affect the full panel and all research series that touch it.

### Overall Assessment

The panel is degraded but usable.

It is sufficient for: measurement infrastructure development, exploratory
analysis, and provisional findings labelled as such.

It is not sufficient for: final statistical claims, publication-grade
evidence, or production-deployment decisions.

This distinction is the basis for the provisional findings constraint in
`research/r8_phase1_lifecycle_spec.md` and the corresponding governance
assumption GA-3 in `docs/decision_records/r8_phase1_governance.md`.

---

## Integrity Finding 1 — Pre-listing / Emerging-board Contamination

### What is broken

`daily_price_adj` contains price history for 18 stocks that predates their
`listing_date` in `company_metadata`. These pre-`listing_date` rows are
emerging-board (興櫃) history, not listed-market history.

Emerging-board trading has:
- No daily price limit (listed Taiwan stocks are subject to ±10%)
- Different liquidity profile and microstructure
- Different tick structure

Mixing emerging-board history into the listed panel means that return
distributions, volatility estimates, and cross-sectional ranking metrics
computed over these rows are not comparable to the rest of the panel.

### Scale

- **18 stocks** have `listing_date > first_price_date` in the panel.
- **7331 rows** in `daily_price_adj` predate their stock's `listing_date`.
- These 7331 rows span the panel start (2021-05-21) through each stock's
  individual `listing_date`.

### Root cause

`listing_date` in `company_metadata` stores the transfer/re-listing date
for transfer-board names, not the original listing date. For these 18
stocks, the column semantics are known-wrong: it records when the stock
moved to the main board, not when it first appeared in the source data.

This means a `date >= listing_date` filter — the obvious candidate fix —
cannot be applied safely. It would use a column with known-wrong semantics,
converting confirmed contamination into hidden contamination without
resolving it. See Rejected Remediation Paths below.

### Exceptions within the 18 stocks

Three stocks within the 18 (6789, 6770, 4583) are transfer-board names
whose DQ rows post-date listing and are not emerging-board artifacts. Their
pre-listing rows require separate classification. They are counted within
the 7331 total but their root cause differs from the other 15.

### Certainty

High. The finding was confirmed via a corrected read-only diagnostic after
a join-blow-up bug in the first diagnostic pass was identified and fixed.
The figures here are from the corrected query.

---

## Integrity Finding 2 — Empty `stock_info`

### What is broken

The `stock_info` table is empty. It is the intended source for sector
classification and other security-level metadata.

### Current workaround

Sector mapping uses `company_metadata.industry_code` decoded from
representative constituents. This is a proxy, not the authoritative source.
Its completeness and accuracy have not been formally validated.

### Impact

Any analysis that relies on sector classification (industry concentration
analysis, sector-stratified returns, sector-level screening) is using an
unvalidated proxy. R8 Phase 0 industry concentration findings (electronics
complex ~78% of signals) are based on this proxy.

### Certainty

Confirmed. Table is empty; this is directly observable.

---

## Integrity Finding 3 — Empty `corporate_actions`

### What is broken

The `corporate_actions` table is empty. It is the intended source for
halt and resumption events, ex-dividend dates, rights issues, and other
corporate actions that affect price continuity.

### Impact on DQ-338

338 signals in the R8 population have `ret_1d >= +10%`, which is
structurally impossible for a non-CA (corporate action) Taiwan stock-date
under the ±10% daily limit. Of these, 203 are classified as
SUSPENSION_GAP (halt-resumption cross-gap or pending). Without a
suspension/halt table, these 203 rows cannot be definitively split into:

- Genuine halt-resumption cross-gaps (structurally valid, but anomalous)
- Bad data rows (to be excluded)

They are currently left as "pending." The correct classification requires
an external halt/suspension dataset that the DB does not have.

### Certainty

Confirmed. Table is empty; this is directly observable.

---

## DQ-338 Classification

338 signals in the R8 population carry `ret_1d >= +10%`. These were
classified via a corrected read-only diagnostic using `listing_date` vs
per-symbol `first_price_date`.

| Cause | Symbols | Events |
|---|---:|---:|
| PRE_LISTING_OTC (emerging-board history mixed in) | 17 | 135 |
| SUSPENSION_GAP (halt-resumption / pending) | 90 | 203 |
| **Total** | — | **338** |

**PRE_LISTING_OTC (135 rows):** ~125 carry the unambiguous pre-listing
fingerprint. ~10 rows (stocks 6789, 6770, 4583) are transfer-board names
whose DQ rows post-date listing; their inclusion in this category is
provisional pending finer classification.

**SUSPENSION_GAP (203 rows):** All 90 affected stocks are normal
long-listed names (e.g. 1503 listed 1969, 2615 listed 1996). Their
`first_price_date` equals the panel start (2021-05-21), indicating no
pre-listing contamination. These mix genuine halt-resumption cross-gaps
with possible bad rows; they cannot be split further without a
suspension/halt table. Status: pending.

**Relationship to IF-1:** PRE_LISTING_OTC rows are one visible corner of
the 7331 IF-1 contaminated rows. The DQ-338 classification covers the
subset that manifests as impossible return values; it does not cover all
7331 contaminated rows.

---

## Blast Radius Assessment

IF-1 is not scoped to R8. The 7331 contaminated rows and the 18 affected
stocks reach across the full panel. Confirmed affected components:

| Component | How affected |
|---|---|
| `daily_price_adj` | 7331 contaminated rows (no price limit, different microstructure) |
| R1 forward-return panel | Any R1 event touching an affected stock in its pre-listing window is contaminated |
| R2 forward-return panel | Same as R1 |
| R5 forward-return panel | Same as R1 |
| RS quantile computation (`beta_adj_rs_*`) | Emerging-board extreme returns distort cross-sectional quantiles; RS_T3 tier membership for all stocks on affected dates is suspect |
| Replay engine | Events replayed against the contaminated panel inherit the contamination |
| R8 Phase 0 findings | 135 of 338 DQ events trace to IF-1; R8 Phase 1 findings are provisional until IF-1 is resolved |

**The RS quantile distortion is the highest-priority consequence.** RS
tertile membership determines which stocks enter baseline comparisons,
which stocks pass the RS_T3 filter, and which regime-stratified results
are valid. If emerging-board extreme returns shift quantile boundaries on
affected dates, the entire cross-sectional ranking is affected — not just
the 18 stocks themselves.

---

## Rejected Remediation Paths

### Rejected: `date >= listing_date` filter

A filter excluding rows where `date < listing_date` was considered and
explicitly rejected during Phase 0.

**Reason:** `listing_date` stores the transfer/re-listing date for the 18
affected stocks, not the original listing date. Applying this filter would:

1. Use a column with known-wrong semantics as the decision boundary.
2. Convert confirmed contamination into hidden contamination — rows that
   should be excluded would appear to pass the filter for stocks where
   `listing_date` predates the contaminated window.
3. Not address the 203 SUSPENSION_GAP rows, which are unaffected by
   `listing_date` semantics.

This path is closed. Any future remediation proposal that uses
`listing_date` as a filter boundary must first resolve the semantic
ambiguity of that column for the 18 affected stocks.

### Rejected: In-script row exclusion without a trusted source

Ad-hoc exclusion logic inside research scripts (e.g. hard-coded symbol
lists, return-threshold filters) was not adopted. Such logic would be
fragile, non-auditable, and would need to be replicated independently
in every script that touches the panel.

The correct fix is a trusted security-lifecycle source applied at the
ingest or feature layer, not inside individual research scripts.

---

## Open Questions

The following questions are unresolved and block a complete remediation
plan. They are recorded here as scope for whoever owns the P1-DATA
remediation work.

1. **What is the authoritative source for Taiwan security lifecycle data?**
   A trusted source is needed to establish: original listing date (not
   transfer date), board-transfer dates, delisting dates, and halt/
   resumption history. The correct fix for IF-1 depends on this source.

2. **How should `listing_date` semantics be corrected for the 18 affected
   stocks?** The column currently stores transfer date. Should a new column
   be added? Should the existing column be overwritten? What is the correct
   value for each of the 18 stocks?

3. **Can the 203 SUSPENSION_GAP rows be split?** A halt/suspension dataset
   would enable classification of these rows as genuine cross-gap events
   (keep, flag) vs bad data (exclude). Without it, the split is not
   possible.

4. **What is the correct population of the 3 provisional transfer-board
   stocks (6789, 6770, 4583)?** Their DQ rows post-date listing but are
   included in the PRE_LISTING_OTC count. Their final classification
   affects the DQ-338 split.

5. **After remediation, which research series require a full re-run?**
   The blast radius assessment above identifies R1/R2/R5/RS quantiles/
   replay engine as affected. The order and scope of re-runs needs to be
   planned after the remediation source is confirmed.

---

## Relationship to R1 / R2 / R5 / R8

| Series | Relationship to panel integrity |
|---|---|
| R1 | Forward-return panels affected by IF-1 contamination on pre-listing dates |
| R2 | Same as R1 |
| R5 | Same as R1; `above_ma20_streak` feature uses the same panel |
| R8 | Phase 1 findings are explicitly provisional until IF-1 resolved; RS_T3 baseline may be distorted; 135 DQ-338 rows are IF-1 artifacts |
| RS Infrastructure | Cross-sectional quantile computation (`beta_adj_rs_*`) is a shared dependency across all R series. Emerging-board extreme returns distort quantile boundaries on affected dates; RS tertile membership for all stocks on those dates is suspect, not just the 18 affected stocks. |

No R series currently in Phase 1 or later should publish final statistical
conclusions that rely on RS quantile membership or cross-sectional feature
values on dates affected by IF-1, until remediation is complete and a
panel re-run has been performed.

---

## Next-Step Requirements

These are necessary conditions for any future remediation, not a plan.
They record what must exist before remediation can proceed.

- **A trusted security lifecycle source** that provides original listing
  date (not transfer date), board-transfer history, and delisting dates
  for Taiwan-listed equities. This is the upstream dependency for IF-1.

- **Resolution of `listing_date` column semantics** for the 18 affected
  stocks. The column's current values are known-wrong for these names.
  Remediation that depends on this column cannot proceed until its
  semantics are corrected or a replacement column is provided.

- **A suspension/halt dataset** that enables classification of the 203
  SUSPENSION_GAP rows. Without it, these rows remain pending and cannot
  be definitively excluded or retained.

- **A panel re-run** of all affected research series (R1, R2, R5, R8
  Phase 1) after IF-1 is resolved. Re-run scope and order are to be
  determined when the remediation source is confirmed.

- **A formal P1-DATA remediation SPEC or decision record** that locks the
  remediation approach, source, and acceptance criteria before
  implementation begins. This assessment document does not authorise
  remediation; a separate governance artifact is required.

---

*End of P1-DATA_panel_integrity_assessment.md v0.1.0*
