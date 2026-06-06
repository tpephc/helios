# IF-3B Source Discovery Specification

<!-- research/if3b_source_discovery_spec.md -->
<!-- v0.1.1 — 2026-06-06 -->

**Status:** DRAFT — pending review
**Scope:** Source discovery only. Does not authorise ingestion pipeline
implementation, schema finalisation, or suspension event classification.
**Blocks:** AC-6 (Phase 1 findings remain PROVISIONAL until IF-3B is closed
and a clean-panel re-run is completed)
**Related backlog:** IF-3B (P1 — OPEN), P1-DATA IF-3 / DQ-CA-001

---

## Changelog

| Version | Date | Change |
|---|---|---|
| v0.1.0 | 2026-06-06 | Initial draft |
| v0.1.1 | 2026-06-06 | Add Authority vs Engineering ranking separation; add Event Taxonomy section; add False Positive Audit (Section 6.3); update TWSE OpenAPI assessment based on confirmed endpoint discovery (TWTAWU schema confirmed, current-snapshot only, no 5-year history); update Source Priority tables accordingly |

---

## 1. Problem Statement

### 1.1 What is missing

The `corporate_actions` table currently contains 1106 rows covering dividend
and split events (IF-3A closed, commit `76f1f45`). It has zero records for
suspension, halt, or resumption events.

The Phase 1 research panel (`daily_price_adj`, 5-year horizon, ~top-200 TWSE
universe) contains **203 SUSPENSION_GAP rows across 90 stocks** that cannot
be classified because no suspension/halt reference dataset exists. These rows
are currently treated as ordinary price observations in forward-return
computation, which is incorrect: a stock that is halted and then resumes may
show an artificial price gap that is not a tradeable return.

### 1.2 Why this blocks AC-6

Per `r8_phase1_lifecycle_spec.md` v0.1.5, IF-3 (suspension/halt data absent)
is the sole remaining binding blocker for AC-6. The Phase 1 finding that
"R8 events within RS_T3 are followed by incremental forward returns in bull
regimes" (A-3 Tier 1) is PROVISIONAL because:

- Halt/suspension events cannot currently be excluded from the event panel.
- A stock that halts on or near the signal date T and resumes at a gap price
  can inflate or deflate the measured forward return at T+1 open or subsequent
  horizons.
- The magnitude of contamination is unknown without a reference dataset.

### 1.3 Scope of this document

This spec covers source discovery only:

1. Identify authoritative data sources for TWSE tradability interruptions.
2. Assess accessibility (historical depth, format, licensing).
3. Enumerate fallback strategies if no clean API feed exists.
4. Propose schema design decisions.
5. Define the cross-validation method against the existing 203 SUSPENSION_GAP
   rows.

Implementation of the ingestion pipeline is out of scope here and requires a
separate pipeline spec once source viability is confirmed.

---

## 2. Definitions

| Term | Definition |
|---|---|
| **Tradability interruption** | Umbrella term covering any event that makes a stock untradeable or non-comparably priced during the panel window. See Section 2.1 for the full event taxonomy. |
| **Suspension** | TWSE-ordered halt of trading for a full session or more (e.g. material information pending, regulatory review). Stock does not trade during this period. |
| **Intraday halt** | Short circuit-breaker halt within a session; stock resumes the same day. Less relevant for daily-bar panel but included for taxonomy completeness. |
| **Resumption** | First tradeable session after a suspension ends. Typically accompanied by a price gap relative to the last traded session. |
| **SUSPENSION_GAP** | Internal label for the 203 rows in `daily_price_adj` where a price gap is consistent with a trading interruption but no authoritative classification exists. |

### 2.1 Event Taxonomy

IF-3B scope includes all event classes capable of producing non-tradeable
or non-comparable observations within the research panel. The canonical
classes are:

| Class | `action_type` value | Description | Affects tradability? |
|---|---|---|---|
| Trading halt start | `suspension_start` | TWSE-ordered halt, one or more full sessions | Yes — stock untradeable |
| Trading halt end | `suspension_end` | First tradeable session after halt | Yes — gap price at resumption |
| Disposition start | `disposition_start` | Stock placed under periodic call auction (處置) | Partial — tradeable but microstructure altered |
| Disposition end | `disposition_end` | Disposition period ends | Partial |
| Altered trading method | `altered_trading_method` | Change to full-lot tender offer, call auction, or other non-continuous method | Partial |
| Board transfer start | `board_transfer_start` | Stock moved to altered trading board (變更交易) | Partial |
| Board transfer end | `board_transfer_end` | Stock restored to normal trading board | Partial |
| Delisting transition | `delisting_transition` | Stock enters delisting process; trading may be restricted or suspended | Yes — partially or fully |

**Scope boundary:**

For the purpose of Phase 1 panel cleaning, the primary targets are
`suspension_start` and `suspension_end`. These are the events most likely
to produce artificial price gaps that contaminate forward-return measurement.

`disposition_start/end` and `altered_trading_method` alter microstructure
but do not halt trading entirely; they are secondary targets and should be
tagged but need not block AC-6 closure independently.

`board_transfer` and `delisting_transition` are tertiary; they are unlikely
to affect the ~200-stock top-TWSE universe materially within the 5-year
panel window, but must be tagged to prevent future recurrence of unclassified
gap rows.

**Explicit exclusions from IF-3B scope:**

The following event types are NOT tradability interruptions and must not be
ingested as `corporate_actions` halt records:

- Material announcement filings (重大訊息 — `t187ap04_L`) — these are
  disclosure events, not trading halts. A stock with a material announcement
  continues to trade normally unless a separate halt order is issued.
- Notice stock status (注意股票 — `/announcement/notice`) — surveillance
  flag only; trading continues.
- Disposition (處置 — `/announcement/punish`) — periodic call auction
  replaces continuous auction, but the stock remains tradeable each session.
  Disposition does NOT produce zero-volume days or resumption gaps of the
  type seen in SUSPENSION_GAP rows.

Mixing these event types with true suspension records is a known data quality
failure mode for Taiwan market data providers. The False Positive Audit
(Section 6.3) is designed to detect this contamination.

---

## 3. Authoritative Source Candidates

**Discovery status as of v0.1.1:** TWSE OpenAPI fully audited (143 endpoints,
swagger confirmed). FinMind catalogue endpoint unconfirmed — wrong path
tried, correct path pending. MOPS not yet accessed.

### 3.1 MOPS (Market Observation Post System)

**URL:** `https://mops.twse.com.tw`
**Discovery status:** NOT YET ACCESSED

**Nature:** TWSE/TPEx mandatory disclosure platform. Listed companies are
required to file material event announcements here, including trading halt
notifications.

**Candidate endpoints (to be verified):**
- `https://mops.twse.com.tw/mops/web/t05st10` — trading halt/resumption
  announcements (公告停復牌).
- Keyword search on announcement type `15` (停復牌相關公告).

**Known characteristics (unverified for API access):**
- Web-based disclosure portal; primary access mode is HTML pages or document
  downloads, not a structured JSON/CSV feed.
- Historical depth is reported to extend to at least 2018 but machine-readable
  availability is unconfirmed.
- May require scraping; there is no publicly documented REST API confirmed
  as of this writing. Licensing status for automated access is unclear.
- Filing lag is a known characteristic of MOPS disclosures: the announcement
  date may lag the actual halt date by one business day.

**Discovery tasks remaining:**
1. Confirm whether MOPS exposes a structured (non-HTML) feed for halt events.
2. Determine historical depth of machine-readable records.
3. Confirm whether halt/resumption dates are recorded at date or timestamp
   precision.
4. Characterise filing lag: does announcement date equal halt date or lag?

**Risk:** If MOPS only exposes PDF filings or HTML tables requiring per-filing
scraping, ingestion complexity is high and the pipeline becomes operationally
fragile.

---

### 3.2 TWSE OpenAPI

**URL:** `https://openapi.twse.com.tw`
**Discovery status:** FULLY AUDITED — 143 endpoints confirmed via swagger.json

**Confirmed halt-relevant endpoints:**

| Endpoint | Summary | Assessment |
|---|---|---|
| `/exchangeReport/TWTAWU` | 集中市場暫停交易證券 | Schema correct; **current snapshot only** |
| `/exchangeReport/TWT85U` | 集中市場證券變更交易 | Current snapshot, no dates; **no historical value** |
| `/announcement/punish` | 集中市場公布處置股票 | Disposition ≠ halt; **false positive risk** |
| `/company/suspendListingCsvAndHtml` | 終止上市公司 | Delisting only; **not a halt feed** |

**TWTAWU schema (confirmed):**
```
Code, Name, TradingHaltDate, TradingHaltTime,
TradingResumptionDate, TradingResumptionTime
```
Fields are correctly structured. `TradingResumptionDate` can be empty
(open suspension). However, as of the discovery query (2026-06-06), all
23 records are warrants (權證), not common equity, and all `TradingHaltDate`
values are from 2026-05 — confirming this is a current-period snapshot with
no historical depth.

**TWSE OpenAPI final assessment:**

- **Historical backfill (5-year panel): NOT VIABLE.** No historical halt
  feed exists in the confirmed 143-endpoint catalogue.
- **Forward-looking monitoring: VIABLE.** Once a baseline dataset is
  established via another source, `TWTAWU` can be polled daily to append
  new halt events to `corporate_actions` going forward.
- `punish` (處置) data must NOT be ingested as halt records — see Section 2.1
  explicit exclusions.

---

### 3.3 FinMind

**URL:** `https://api.finmindtrade.com`
**Discovery status:** CATALOGUE UNCONFIRMED — `/api/v4/info` returned empty
(wrong endpoint path). Correct catalogue path not yet identified.

**Nature:** Third-party aggregator of Taiwan financial data; already used
in Helios for dividend/split ingestion.

**Candidate dataset names (to be verified):**
- `TaiwanStockTradingHalt`
- `TaiwanStockSuspend`
- `TaiwanStockHalt`
- Any similar name in the FinMind dataset catalogue.

**Known characteristics:**
- Already integrated in Helios; no new authentication or infrastructure
  required if a halt dataset exists.
- Aggregated data: primary source and update methodology are not always
  documented. Requires cross-validation against MOPS ground truth regardless
  of availability.
- Historical depth for most datasets extends 5+ years.
- Known risk: FinMind has historically mixed announcement events with trading
  halt events in some datasets. False Positive Audit (Section 6.3) is
  mandatory if FinMind data is used.

**Discovery tasks remaining:**
1. Identify the correct FinMind catalogue endpoint (try `/api/v4/taiwan_stock`
   or equivalent; check FinMind documentation directly).
2. If halt dataset found: retrieve sample, inspect date range, schema,
   and field definitions.
3. Cross-validate at least one known halt event against MOPS.

---

### 3.4 TWSE Historical Data Downloads

**URL:** `https://www.twse.com.tw/en/trading/historical/`
**Discovery status:** NOT YET ACCESSED

**Nature:** Bulk historical data download portal (CSV/XLS format).

**Assessment:** Likely useful only for manual reference or seed population,
not for automated pipeline ingestion. Zero-volume day inference from daily
trading files is possible but inferential (see Section 3.5).

**Discovery tasks remaining:**
1. Audit the download portal for any explicit halt/suspension history file.
2. If found: determine granularity (date only vs date + reason code) and
   whether file naming is stable enough for automation.

---

### 3.5 Price-Gap Detection (Fallback)

**Nature:** Purely internal inference from `daily_price_adj`; no external
source required.

**Method:**
1. Flag any stock-date where `volume == 0` (no trades occurred).
2. Flag any stock-date immediately following a zero-volume day where
   `abs(open_t / close_{t-1} - 1) > threshold` (resumption gap).
3. Cross-reference against the existing 203 SUSPENSION_GAP rows to assess
   recall and precision.

**Limitations:**
- Does not distinguish suspension from voluntary non-trading (newly listed
  stock, ex-rights quiet period, thin-market days).
- Does not provide authoritative halt reason or regulatory classification.
- If used as the sole classification method, the resulting panel treatment
  must be documented as conservative exclusion under uncertainty, not
  confirmed suspension exclusion.
- AC-6 can only be conditionally closed under this fallback; a residual
  uncertainty note must be appended to `r8_phase1_lifecycle_spec.md`.

**Assessment:** Valid as last-resort fallback. Produces a defensible
conservative exclusion list with explicit disclosure of inferential nature.

---

## 4. Source Ranking

IF-3A established the principle: **Official Source > Aggregator > Inference**.
This applies to authority ranking. Engineering ranking (integration effort)
is a separate consideration and must not override authority ranking in
governance decisions.

### 4.1 Authority Ranking

Determines which source is trusted for classifying events in
`corporate_actions`. Higher authority = lower DQ ticket risk downstream.

| Rank | Source | Rationale |
|---|---|---|
| 1 | MOPS | Primary statutory disclosure platform; halt filings are authoritative by regulation |
| 2 | TWSE OpenAPI (`TWTAWU`) | Official TWSE feed; correct schema confirmed; limited to current period |
| 3 | TWSE Historical Downloads | Official but manual/semi-manual; not machine-reliable |
| 4 | FinMind | Aggregator; secondary source; requires MOPS cross-validation |
| 5 | Price-gap detection | Internal inference; no external authority; fallback only |

### 4.2 Engineering Ranking

Determines implementation sequence given integration effort. Does not
override authority ranking for `source` field tagging in `corporate_actions`.

| Rank | Source | Rationale |
|---|---|---|
| 1 | FinMind | Already integrated; if halt dataset exists, lowest friction |
| 2 | TWSE OpenAPI (`TWTAWU`) | JSON, no auth, stable schema; usable for forward monitoring immediately |
| 3 | MOPS | Authoritative but HTML-first; scraping risk; filing lag must be characterised |
| 4 | TWSE Historical Downloads | Manual; one-time backfill only |
| 5 | Price-gap detection | Always available; inferential only |

### 4.3 Recommended execution path

Given the authority/engineering split, the recommended approach is:

1. **Confirm FinMind catalogue** (5-minute task). If halt dataset exists:
   ingest via FinMind, tag `source = 'finmind'`, then cross-validate a
   sample against MOPS (authority check). Do not promote to `source =
   'mops'` unless records are verified against MOPS filings.
2. **Enable TWTAWU polling** for forward monitoring regardless of
   backfill outcome.
3. **Access MOPS** for ground-truth spot-check sample (Section 6.2) even
   if FinMind is used as primary ingestion source.
4. **Fall back to price-gap detection** only if both FinMind and MOPS
   fail to provide 5-year historical coverage.

---

## 5. Schema Design

The `corporate_actions` table already has structural capacity for halt
records. Confirm against current DDL before finalising.

```sql
-- Proposed columns for suspension/halt rows in corporate_actions
symbol          TEXT    NOT NULL,
action_date     DATE    NOT NULL,   -- first non-trading day (halt start)
                                    -- or first trading day (resumption)
action_type     TEXT    NOT NULL,   -- see taxonomy in Section 2.1
reason_code     TEXT,               -- regulatory reason if available (nullable)
resume_date     DATE,               -- first trading day after suspension
                                    -- nullable for open suspensions
source          TEXT    NOT NULL,   -- 'mops' | 'twse_openapi' | 'finmind'
                                    -- | 'twse_historical' | 'price_gap_inferred'
source_id       TEXT,               -- source-specific record identifier
ingested_at     TIMESTAMP NOT NULL
```

**Design decisions:**

1. **`action_date` semantics:** First non-trading day for `suspension_start`;
   first trading day for `suspension_end`. Document this convention explicitly
   in the pipeline spec. Do not use the MOPS announcement date as `action_date`
   without adjusting for filing lag.

2. **Open suspensions:** `resume_date` is nullable. An update pass is required
   when the resumption date becomes known.

3. **Source provenance is mandatory.** Every row must carry its actual ingestion
   source. Mixed-source ingestion must tag each row individually. Rows ingested
   from FinMind carry `source = 'finmind'` even if subsequently spot-checked
   against MOPS — spot-checking does not change the source tag.

4. **`price_gap_inferred` rows must never be silently promoted.** If the
   fallback method is used, `source = 'price_gap_inferred'` must be preserved
   in all downstream queries. Any query that filters on `source != 'price_gap_inferred'`
   to get "authoritative only" records must be explicitly documented.

---

## 6. Cross-Validation Against SUSPENSION_GAP 203 Rows

Once a candidate dataset is retrieved, run the following procedure before
accepting the source as viable for ingestion.

### 6.1 Recall Audit

```
For each of the 203 SUSPENSION_GAP rows (symbol, date):
    Check whether the candidate dataset contains a halt record for
    (symbol, date) OR (symbol, date ± 1 business day).
    Classify each row as: MATCHED | UNMATCHED
```

Report: matched count, unmatched count, unmatched symbol/date list.

**Note:** Perfect recall is not expected. Some SUSPENSION_GAP rows may
reflect data feed outages or ex-date price distortions rather than
genuine halts. A recall rate below ~70% suggests either source
incompleteness or that the 203 rows contain a mix of event types that
must be decomposed before cross-validation.

Minimum threshold for source acceptance: **to be set after inspecting
the 203-row composition** via manual review of a 10-row sample.

### 6.2 Precision Spot-Check

```
Sample 20 halt records from the candidate dataset (stratified by year).
For each record, verify against MOPS filing (manual lookup):
    - Correct halt date
    - Correct resume date (if populated)
    - Correct symbol
```

Minimum acceptable precision: **≥ 90%** of the 20-record sample.

### 6.3 False Positive Audit

```
Sample 20 records from the candidate dataset.
For each record, confirm:
    - Did this event actually halt trading (zero-volume day)?
    - Is this a genuine tradability interruption, not one of the following:
        * Material announcement (重大訊息) without an accompanying halt
        * Disposition (處置) period entry
        * Ex-rights / ex-dividend date
        * New listing first-day trading restriction
```

**Purpose:** Some Taiwan market data providers conflate material announcement
filings with trading halt records in their event datasets. A disposition
(處置) entry changes the matching mechanism but the stock remains tradeable
— ingesting it as a halt would contaminate the `corporate_actions` table with
false suspension records and cause valid forward-return observations to be
incorrectly excluded from the Phase 1 panel.

Minimum acceptable false positive rate: **≤ 10%** of the 20-record sample.
If false positive rate exceeds 10%, the source requires field-level filtering
before ingestion (e.g. filter to specific `action_type` codes that correspond
to true halts), and the filter logic must be documented in the pipeline spec.

### 6.4 Coverage Audit

```
For each symbol in the Phase 1 research panel (~200 stocks):
    Report: number of halt records found, date range of halt records.
```

This confirms whether the source covers the full 5-year panel window
uniformly or has systematic gaps (e.g. pre-2022 records missing).

### 6.5 Classification of Residual SUSPENSION_GAP Rows

After applying the authoritative dataset:

- Rows matching a confirmed halt record → classified as `suspension_gap`;
  exclude from forward-return computation.
- Rows with no matching halt record → remain unclassified; must be
  separately reviewed. Do not silently include or exclude.
- Unclassified rows must be reported in the Phase 1 spec update with a
  count, a sample of symbol/dates, and a stated disposition (include with
  flag, exclude conservatively, or defer).

---

## 7. Fallback Decision Tree

| Outcome | Action |
|---|---|
| FinMind halt dataset found; recall ≥ threshold; precision ≥ 90%; FP rate ≤ 10% | Ingest via FinMind (`source = 'finmind'`). Cross-validate sample against MOPS. Enable TWTAWU forward monitoring. |
| FinMind absent or fails validation; MOPS structured feed accessible | MOPS-based pipeline spec. Document filing lag adjustment. Enable TWTAWU forward monitoring. |
| MOPS HTML-only (scraping required) | Assess scraping feasibility. If complexity is high, escalate to P0 decision: accept price-gap fallback or defer AC-6 further. |
| All API sources absent or insufficient depth | Price-gap detection fallback. Tag all rows `source = 'price_gap_inferred'`. AC-6 closes conditionally — residual uncertainty note required in lifecycle spec. |

**The fallback path does not eliminate the PROVISIONAL status of Phase 1
findings.** If `price_gap_inferred` is the final source, Section 10 of
`r8_phase1_interim_findings.md` must be updated to state that IF-3 was
resolved via inferential classification, not authoritative data, and that
the clean-panel re-run result carries this residual uncertainty.

---

## 8. Opportunistic Finding: TWSE Holiday Calendar

During TWSE OpenAPI discovery, `/holidaySchedule/holidaySchedule` was
confirmed accessible. Response: 27 records, fields `Name`, `Date`,
`Weekday`, `Description`. Date format: `YYYMMDD` (ROC calendar).

This endpoint directly addresses the **TWSE Holiday Calendar backlog item**
(P1 — OPEN). It should be ingested separately from IF-3B as a standalone
task. Recommend opening a dedicated ticket to ingest this endpoint into
Helios's calendar infrastructure before the next cron-based pipeline run
that depends on trading-day counting.

---

## 9. Deliverables and Acceptance Criteria for IF-3B

| Deliverable | Acceptance Criterion |
|---|---|
| Source discovery report | Each candidate in Section 3 evaluated with concrete evidence. All "unconfirmed" annotations replaced with confirmed findings. |
| Schema decision record | `action_date` semantics, open-suspension handling, source provenance convention documented and approved. |
| Cross-validation report | Recall audit (Section 6.1), precision spot-check (Section 6.2), false positive audit (Section 6.3), and coverage audit (Section 6.4) completed. |
| Pipeline spec (separate document) | Drafted only after source viability confirmed. Out of scope here. |
| `corporate_actions` table populated | Suspension/halt rows ingested for all Phase 1 panel symbols, 5-year window. |
| Phase 1 spec update | `r8_phase1_lifecycle_spec.md` updated to reflect IF-3B closure or conditional closure status. |

**IF-3B is CLOSED when:** `corporate_actions` contains a documented and
cross-validated suspension/halt dataset covering the Phase 1 panel window,
and a clean-panel re-run of A-3 has been initiated. Closed status does not
require the re-run to be complete; it requires the data to be in place and
the re-run to be in flight.

---

## 10. Immediate Next Steps

Execute in order. Do not proceed to pipeline design until Step 4 is complete.

1. **Confirm FinMind catalogue** — identify correct endpoint for dataset
   listing; check for halt/suspension dataset names.
   ```bash
   # Try known alternative paths on nexus
   curl -s "https://api.finmindtrade.com/api/v4/taiwan_stock_info" | head -200
   # Or consult https://finmindtrade.com/analysis/#/data/api directly
   ```

2. **Access MOPS t05st10** — retrieve at least one known halt event manually
   to establish a ground-truth anchor for cross-validation.
   ```
   https://mops.twse.com.tw/mops/web/t05st10
   Search: year=114 (2025), type=sii (上市)
   ```

3. **Inspect 10 SUSPENSION_GAP rows manually** — query
   `daily_price_adj` for the 203 rows, sample 10, and determine whether
   they are zero-volume days, ex-date distortions, or data feed gaps. This
   sets the recall threshold for Section 6.1.
   ```sql
   -- On nexus DuckDB
   SELECT symbol, date, open, close, volume
   FROM daily_price_adj
   WHERE <suspension_gap_flag condition>
   LIMIT 10;
   ```

4. **Report findings** — update Section 3 annotations with confirmed
   results before pipeline spec work begins.

5. **Open separate ticket** for TWSE Holiday Calendar ingestion
   (`/holidaySchedule/holidaySchedule`) — unblock P1-OPEN calendar debt
   independently of IF-3B timeline.

---

*End of if3b_source_discovery_spec.md v0.1.1*
