# R8 MA5 Momentum — Phase 0 Feasibility

<!-- docs/research/r8_phase0_feasibility.md -->
<!-- Phase 0 Feasibility Audit — closed 2026-06-01 (rev2). Tool: research/ma5_momentum_feasibility.py v0.1.2. -->

**Status:** Phase 0 CLOSED (2026-06-01, rev2)
**Tool:** `research/ma5_momentum_feasibility.py` v0.1.2 (read-only DuckDB audit)
**Outputs:** `data/_storage/r8_feasibility/*.csv`
**Provenance note:** All quantitative figures below are taken verbatim from the
v0.1.2 audit run (2026-06-01 09:20) and the follow-up read-only diagnostics
(industry_code decode; DQ-338 classification; panel blast-radius). None are
estimated. The DQ classification was contested and re-run after a join-blow-up
bug in the first diagnostic; the figures here are from the corrected query.

---

## Verdict

Decision gate is **5/5 PASS**, but the PASS authorises **a lifecycle-replay SPEC
ONLY** — not a production rule, and not a clean orthogonality claim. Two of the
five criteria pass on threshold placement, not on strength of evidence
(criterion 4 RS enrichment = 1.63 vs an arbitrary 2.0 bar; criterion 5 counts
rows, not independent observations). R8 is feasible to study further; it is not
established as independent alpha.

---

## Entry population

R8 entry definition: `daily_return >= +5% AND close > open`.

- 8372 signals, 2021-06 .. 2026-05, CA stock-dates excluded, regime attached as
  `regime[T-1]` (production-consistent).
- 99.94% of signals (8367/8372) fall inside the `dynamic_top200` snapshot, so the
  full 205-stock feature panel and the 200-symbol screener universe are
  effectively the same set here.
- Regime mix: bull 5000, crisis 1153, bear 1123, neutral 1096. ~27% of signals
  sit in crisis/bear regimes, where a +5% candle is more plausibly a volatility
  bounce than trend continuation; Phase 1 should not pool regimes.

## Tradability (the genuine good news)

- T+1-open limit-lock is NOT a material risk: only 0.95% of signals open at
  >= +9.5% (near limit-up). `next_open_ret` p05/p50/p95 = -3.04% / +0.48% / +4.96%.
  Entry at T+1 open is largely fillable.
- Counterpoint (tradable != good entry): ~29% of signal days CLOSED at >= +9.5%
  (near limit-up) yet open roughly flat the next day. These are likely exhausted
  moves; fillability does not validate entry quality. Phase 1 must tag and
  separately evaluate the near-limit-up signal-day subset.

## Selection-level redundancy (the core finding)

R8's stock selection is not novel. Three independent lenses agree:

- De-circularised T-1 RS60 top-tertile enrichment = **1.63** (vs base 0.33;
  tertile mechanical ceiling ~3.0). Measured as-of T-1, so the +5% signal candle
  is excluded from the RS window — circularity ruled out. R8 lives in
  already-high-RS names.
- Overlap with `find_bullish_setups.py` profiles ([ASSUMED] / uncalibrated):
  MOMENTUM enrichment 2.98 (partly constructive — the breakout-feature windows
  include the signal day), COMPRESSION 0.16, RECLAIM 1.17, ANY 1.47.
- Pullback proxy (`dist_above_ma20_atr < 0`) enrichment 0.31: R8 is a
  breakout/extension entry, anti-correlated with the below-MA20 zone.

**Conclusion:** R8 selects essentially the "high-RS + volume-breakout" universe —
the screener's MOMENTUM branch. It is NOT orthogonal alpha at the selection
level. Any independent edge can only come from ENTRY TIMING (the +5% breakout
day), not from which stocks it picks.

## Independence / sampling caveats

- `clean_tradable_events = 5621` is a ROW count, NOT independent n. 23.4% of all
  events fall on days with >= 20 simultaneous signals (event_days = 1115,
  max 77 on 2024-08-07). A large fraction of "events" share one market-beta move;
  effective independent n is materially smaller. Block-bootstrap effective-n is
  deferred to Phase 1.
- Population is non-stationary: event counts are strongly back-loaded into
  2024-2026 (2026 reached 1814 in ~5 months, matching full prior years).
  Feasibility is conditional on the recent high-momentum regime persisting.
- Industry-concentrated, and more severely than a "top-2" framing suggests.
  By `company_metadata.industry_code` (decoded from representative constituents):
  code 24 = semiconductors (~27% of signals), 28 = electronic components (~18%),
  plus 26 optoelectronics / 25 computer-peripherals / 27 comms-network /
  31 other-electronics / 29 electronic-distribution / 30 IT-services. The
  electronics complex (24+28+26+25+27+31+29+30) is ~78% of all R8 signals.
  R8 is effectively an electronics/momentum strategy, NOT a broad-market one.
  Within-industry correlation means the same-day clustering (C3) and this
  industry concentration are the SAME dependence: effective independent n is
  even lower than the date-clustering figure alone implies.

## Data-quality findings (classified)

The 338 signals with `ret_1d >= +10%` (structurally impossible for a non-CA
Taiwan stock-date under the +/-10% limit) were classified via a corrected
read-only diagnostic (`listing_date` vs per-symbol `first_price_date`):

| Cause | Symbols | Events |
|---|---:|---:|
| PRE_LISTING_OTC (emerging-board 興櫃 history mixed in) | 17 | 135 |
| SUSPENSION_GAP (halt-resumption cross-gap / pending) | 90 | 203 |
| **Total** | — | **338** |

- PRE_LISTING_OTC = 40% of the DQ set, BELOW the >50% threshold that would have
  reopened Phase 0. ~125 of these 135 rows carry the unambiguous before-listing
  fingerprint; ~10 (6789, 6770, 4583) are transfer-board names whose DQ rows
  actually post-date listing and are not emerging-board artifacts.
- SUSPENSION_GAP rows are all normal long-listed stocks (e.g. 1503 listed 1969,
  2615 1996, 3035/3037 2002) with first_price = panel start 2021-05-21. These
  mix genuine halt-resumption cross-gaps with possible bad rows; finer split
  needs a suspension/halt table the DB does not have. Left as "pending".
- `stock_info` table is EMPTY; sector mapping uses `company_metadata.industry_code`.

### Panel Integrity Caveat #3 — pre-listing / emerging-board contamination

This is the most consequential finding and is LARGER than R8. Blast radius
(full panel, not just the DQ set):

- 18 stocks have `listing_date > first_price_date` (transfer-board names whose
  `listing_date` stores a re-listing / board-transfer date, NOT original listing).
- 7331 rows in `daily_price_adj` predate their stock's `listing_date`.

These pre-transfer rows are emerging-board (興櫃) history, which has NO daily
price limit and different liquidity/microstructure, mixed into the listed panel.
Any study touching these 18 stocks' 2021-2024 early history is affected — R1 /
R2 / R5 forward-return panels, the replay engine, and the cross-sectional
RS-tertile computation (emerging-board extreme returns distort the beta_adj_rs
quantiles). R8's 135 rows are one visible corner of these 7331 rows.

This is the THIRD metadata/panel integrity gap, alongside empty `stock_info` and
empty `corporate_actions` (DQ-CA-001).

**Why no in-script fix:** a `date >= listing_date` filter was REJECTED. It would
use a column whose semantics are known-wrong (listing_date = transfer date, not
original listing), converting known contamination into hidden contamination, and
it would not touch the 203 SUSPENSION_GAP rows anyway. The correct fix is a
trusted security-lifecycle source applied at the ingest/feature layer
(see backlog P1-DATA), not a filter inside this feasibility script.

## Governance

- `find_bullish_setups.py` is an OBSERVATIONAL screener, NOT a validated entry
  strategy. Its thresholds are [ASSUMED] (pending backlog #18 outcome study), and
  the author explicitly states they are not entry signals.
- `above_ma20_streak` is NOT forward-return validated (R5 Section C, 2026-05;
  Spearman mildly negative, CI spans zero).
- All Section D overlap figures are DESCRIPTIVE overlap with an uncalibrated
  screener — not a comparison against validated production alpha. Helios has no
  validated bullish entry strategy at the time of writing (trend_breakout_v1 is
  the live signal source; this screener is not).

## Mandatory requirement for the Phase 1 lifecycle SPEC

Because R8's selection overlaps the RS factor, cash-relative profitability would
NOT prove an independent timing edge. The Phase 1 SPEC MUST benchmark R8 against:

1. RS-top-tertile hold baseline,
2. RS_T3 + pullback baseline,
3. R8-within-RS_T3 vs RS_T3-unconditional.

R8 must beat "simply holding high-RS names" to justify a lifecycle engine.

## Method note (frozen for Phase 1 inheritance)

- signal day = T; SMA / RS / `dist_above_ma20_atr` used as-of T close (assumed
  point-in-time, no future leakage — verify via `bullish_features.computed_at`).
- earliest tradable entry = T+1 open; any post-signal "does not break MA5"
  condition must be evaluated on T+1 onward (T must never count as evidence).
- regime attached as `regime[T - 1]`.
- RS_T3 is a reconstructed PROXY (per-date top tertile of `beta_adj_rs_*`), NOT
  the production tier; the decisive metric is the T-1 de-circularised version.

## Scope explicitly NOT done in Phase 0

partial exit / sell-half / buy-back, MA5 reclaim/break exit, position sizing,
any PnL or forward-return metric, block-bootstrap effective-n. Industry-code
decode and DQ-338 classification are now DONE (see above); the resulting
panel-integrity remediation is tracked separately as backlog P1-DATA.

## Deliverables

- `research/ma5_momentum_feasibility.py` v0.1.2
- `data/_storage/r8_feasibility/`: `a_by_year.csv`, `a_by_regime.csv`,
  `a_by_sector.csv`, `a_rs_split.csv`, `b_signal_limit.csv`,
  `b_open_tradability.csv`, `c_by_month.csv`, `c_top_days.csv`,
  `c_top_sectors.csv`, `c3_clustering.csv`, `d_overlap.csv`,
  `d2_screener_overlap.csv`, `dq_ret_ge_10pct.csv`
