# PR-MS1.0 — Q-MS1-02 / Q-MS1-06 Exceptional-Bar Disposition Draft
Canonical Path: docs/research/pr_ms1_0_q_ms1_02_06_exceptional_bar_disposition.md

Version: v0.1.1
Status: DRAFT — ADVERSARIAL REVIEW REQUIRED
Scope: Canonical eligible-session treatment for Taiwan-market exceptional bars, and the corresponding assembly/classifier boundary. No classifier implementation, source ingestion change, strategy adoption, or production integration is authorised.
Canonical Contract Target: `docs/research/pr_ms1_0_security_market_state_domain_contract.md` v0.2.1 (controlled integration draft)
Upstream Semantic Boundary: `docs/research/pr_ms0_repository_semantic_audit_decision_record.md` (`45f8fea`)
Related Dispositions: Q-MS1-01/02 v0.1.2; Q-MS1-03/06 v0.1.1; Q-MS1-04 v0.1.4.

## 0. Decision Labels

- **VERIFIED REPOSITORY FINDING** — current-source evidence observed at entry.
- **VERIFIED EXECUTION FINDING** — supplied read-only execution result; re-observe at lock HEAD.
- **PROPOSED DECISION** — normative candidate requiring review and lock.
- **REPOSITORY GAP** — current source/schema cannot support a desired distinction.
- **DEFERRED** — intentionally owned by a later closure item.

## 1. Entry Evidence

**VERIFIED REPOSITORY FINDING:** `market.trading_calendar.is_trading_day` has a three-layer Taiwan trading-day model: official `twse_holidays` first, XTAI within its session coverage, then a narrowly scoped post-XTAI fallback. It explicitly separates calendar truth from `daily_price_adj` data availability; `next_fillable_day` is the existing combined helper.

**VERIFIED REPOSITORY FINDING:** `daily_price` / `daily_price_adj` retain OHLC, volume, and adjustment values, but carry no suspension, halt, price-limit, exchange-status, or official bar-quality field. `listed_market_daily_price_adj` performs security-lifecycle filtering only; it does not classify bar quality. Source normalisation preserves unavailable source fields as null rather than forward-filling them.

**VERIFIED EXECUTION FINDING:** On the supplied entry panel, `listed_market_daily_price_adj` has 246,757 rows, zero null OHLC rows, zero zero-volume rows, and 671 zero-range (`adj_high == adj_low`) rows. Every observed zero-range row has positive volume. These counts are descriptive only and do not identify a limit-locked bar.

**REPOSITORY GAP:** No stored field or verified source-side computation identifies an official price-limit-locked session. A zero-range bar is not a valid proxy: it can arise from a one-price traded session and cannot distinguish limit lock from ordinary low-range trading.

## 2. Terms and Boundary

An **expected session** is a date that is both a governed Taiwan trading session under the calendar contract and inside the security's governed listed interval. A bar is **structurally valid** when it meets the Q-MS1-01/02 OHLC, ordering, finiteness, and positive-price requirements.

The pure classifier neither queries the calendar nor decides whether an absent or exceptional source bar is eligible. Assembly owns expected-session derivation, lifecycle comparison, bar-quality treatment, construction of the canonical panel, and the diagnostic/export consequences. The classifier receives only the resulting ordered DTO and retains the sole history-sufficiency decision over its length.

## 3. Exceptional-Bar Disposition

### 3.1 Canonical panel algorithm

**PROPOSED DECISION:** For `as_of=t`, assembly SHALL construct the maximal terminal sequence of consecutive expected sessions ending at `t` for which each bar is structurally valid and eligible under this section. It SHALL NOT silently skip an expected session, forward-fill OHLC, or reach across an ineligible/missing session to use an older bar.

Assembly passes that terminal sequence to the classifier without applying the configuration-owned `required_history_sessions` scalar. The classifier then returns `INSUFFICIENT_HISTORY` if the sequence is shorter than its scalar and evaluates no rule. This retains the classifier-owned sufficiency decision while preventing a non-contiguous panel from masquerading as a valid history window.

Assembly MAY use the scalar solely as a bounded fetch-depth hint while retrieving candidate history. It SHALL NOT compare the resulting sequence length with that scalar to decide whether to construct/send the DTO, preempt classifier invocation, or choose a classifier status. A fetch optimisation does not transfer the sufficiency decision from classifier to assembly.

If no eligible bar exists at `as_of=t`, assembly cannot construct a DTO satisfying `bars[-1].session == as_of`; it SHALL emit a composed-pipeline `Availability.OPERATIONAL_FAILURE` envelope with a typed assembly diagnostic and SHALL NOT invoke the classifier.

### 3.2 Treatment table

| Condition at an expected session | Canonical-panel treatment | Export/diagnostic consequence |
| --- | --- | --- |
| Before governed `listed_from` | not expected; never padded | `NATURAL_HISTORY_SHORTFALL` when resulting terminal sequence is insufficient |
| Expected listed session has no bar | terminal-sequence barrier; never skip | `DATA_GAP` when a DTO ending at `t` exists but is insufficient; typed assembly failure if the absent bar is `t` |
| OHLC null, non-finite, non-positive, or violates OHLC ordering | terminal-sequence barrier; never repair | same as missing bar |
| Zero-volume bar with otherwise valid OHLC | ineligible terminal-sequence barrier; never treated as price discovery | `ZERO_VOLUME_BAR_EXCLUDED` when resulting DTO is insufficient; typed assembly failure if the bar is `t` |
| Zero-range bar with positive volume and valid OHLC | included | no price-limit inference and no special classifier branch |
| Official price-limit lock | no special row treatment is currently possible | `LIMIT_STATUS_UNAVAILABLE` capability/provenance marker; zero-range SHALL NOT proxy it |
| Suspension / halt while still listed | absent bar follows missing-bar policy | cause is not inferred as suspension versus source gap |
| Resumption | valid resumed bars begin a new terminal sequence | prior absent sessions are never bridged |

The current repository has zero zero-volume bars at entry; this does not remove the future-data contract. The zero-volume policy is deliberately fail-closed for price-structure classification because the source contains no trade-derived price observation for that session.

### 3.3 Diagnostic ownership adjustment

**PROPOSED DECISION — controlled supersession of Q-MS1-03/06 v0.1.1:** Add `ZERO_VOLUME_BAR_EXCLUDED` to the assembly-owned `HistoryDiagnosticCode` enum. It is required when a zero-volume bar is the reason that an otherwise structurally valid terminal DTO is too short. It does not become a MarketState, classifier reason code, or `ClassificationStatus` member.

The existing codes retain their meanings:

```text
NATURAL_HISTORY_SHORTFALL  = governed lifecycle proves history was not yet expected
DATA_GAP                   = an expected session lacks a usable source bar
DIAGNOSIS_UNAVAILABLE      = assembly cannot establish the applicable diagnosis basis
ZERO_VOLUME_BAR_EXCLUDED   = observed zero-volume bar is intentionally ineligible
```

If the expected-session basis itself cannot be established because the governed calendar or lifecycle source is unavailable, assembly SHALL emit `DIAGNOSIS_UNAVAILABLE` rather than label the condition `DATA_GAP` or `NATURAL_HISTORY_SHORTFALL` by assumption.

**DEFERRED — Q-MS1-08 operational diagnosability:** `OperationalDiagnosticCode` currently has only `ASSEMBLY_FAILURE`, which cannot distinguish an `as_of` missing bar, invalid OHLC, zero-volume bar, unavailable calendar/lifecycle basis, or systemic I/O failure. Q-MS1-08 owns the decision whether and how to expand the operational diagnostic vocabulary and export representation. Until that governed change exists, this disposition requires the envelope invariant but makes no false claim that its operational code alone identifies the root cause.

### 3.4 Limit-status coverage gap

**PROPOSED DECISION:** `LIMIT_STATUS_UNAVAILABLE` is a machine-readable assembly coverage/capability marker, not a classifier input, MarketState, history diagnostic, or proxy derived from OHLC. Q-MS1-08 owns its final export field/type and whether it is emitted per record or declared per panel/source version.

Until an official or governed limit-status source is admitted, V1 makes no claim that it can identify or exclude every price-limit-locked bar. It includes structurally valid positive-volume zero-range bars as official observations and relies on the declared source limitation rather than fabricating a limit-lock inference.

## 4. Required Invariants and Tests

**PROPOSED DECISION:** PR-MS1.1 acceptance fixtures shall prove:

1. an expected missing session before `as_of` truncates the panel at that point; earlier bars are not borrowed and classifier result is `INSUFFICIENT_HISTORY` when the terminal sequence is shorter than the scalar;
2. a missing or invalid bar at `as_of` produces `Availability.OPERATIONAL_FAILURE`, typed operational diagnostic, no `ClassificationResult`, and no classifier invocation;
3. a zero-volume bar is treated identically as a terminal-sequence barrier but is distinguishable by `ZERO_VOLUME_BAR_EXCLUDED` when insufficient history results;
4. a positive-volume zero-range bar remains in the panel and does not trigger a limit-lock classification branch;
5. a lifecycle-proven pre-listing shortfall yields `NATURAL_HISTORY_SHORTFALL`, while an unavailable calendar/lifecycle basis yields `DIAGNOSIS_UNAVAILABLE`;
6. the calendar/data-availability split is preserved: a calendar session alone does not prove a bar exists, and a bar alone does not make a non-session date eligible;
7. resumption creates no implicit bridge over earlier missing sessions.
8. a zero-volume bar exactly at `as_of=t` produces `Availability.OPERATIONAL_FAILURE`, typed operational diagnostic, no `ClassificationResult`, and no classifier invocation; this fixture is distinct from the missing-bar-at-`t` fixture.

No acceptance test may identify a price-limit lock from zero range, zero volume, or an assumed fixed percentage cap unless a superseding disposition admits an official/governed source and its effective-date semantics.

## 5. Closure Criteria

Q-MS1-02/06 exceptional-bar treatment may close only when:

1. the expected-session definition is canonically integrated with a versioned calendar and lifecycle basis;
2. terminal-sequence assembly and the classifier-owned scalar sufficiency boundary are explicit;
3. every listed exceptional condition has exactly one treatment and no silent skip/fill path;
4. `ZERO_VOLUME_BAR_EXCLUDED` is integrated as a typed assembly history diagnostic;
5. `LIMIT_STATUS_UNAVAILABLE` is assigned a machine-readable Q-MS1-08 export/capability representation;
6. the Section 4 fixtures are assigned to assembly/composed-pipeline boundaries and exercised against the real panel-construction path;
7. the source calendar's coverage/version and lifecycle effective-date semantics are retained in export provenance.

## 6. Session Handoff

### Session Summary

Current Helios separates Taiwan calendar truth from adjusted-price availability but does not store official suspension or price-limit status. The disposition therefore treats non-contiguous or zero-volume source observations as explicit panel barriers, not observations that the classifier may silently skip.

### Decision Record

- Zero-range with positive volume is included and never treated as a price-limit proxy.
- Zero-volume is excluded from price-structure history and requires a typed reason if it causes insufficiency.
- Missing expected sessions truncate the terminal panel; pre-gap history is never borrowed.
- Official limit-lock identification remains unavailable pending an admitted source.

### Open Questions

- Q-MS1-08: final export representation for `LIMIT_STATUS_UNAVAILABLE` and calendar/lifecycle coverage identity.
- Q-MS1-08: whether/how `OperationalDiagnosticCode` gains root-cause granularity beyond `ASSEMBLY_FAILURE`.
- Accept, modify, or reject the proposed zero-volume barrier policy and `ZERO_VOLUME_BAR_EXCLUDED` supersession.

### Evidence

All repository facts in Section 1 must be re-observed at the candidate lock HEAD; the supplied row counts are not a permanent panel assertion.

### Next Actions

Obtain adversarial review. If accepted, integrate this document's Section 3.3 supersession into the Q-MS1-03/06 and canonical type tables, then resolve the Q-MS1-08 capability/export design before marking exceptional-bar treatment closed.
