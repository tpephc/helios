# PR-MS1.1 — Remediation Dispositions

Canonical Path: `docs/research/pr_ms1_1_remediation_dispositions.md`

Version: v0.2.1
Status: LOCKED — PR-MS1.1 REMEDIATION AUTHORISED
Previous Lock Reference: f04bfca7fe4057c312e8b4d3b6e7f0940bd79453
Upstream Boundary: `docs/research/pr_ms1_0_security_market_state_domain_contract.md` v0.2.5 (`2490cde86274262f1a6335eb4e984806a29cb5e7`), backfilled at `3f060ab8c4e6df7d44fc345319b560249ad8796a`
Review Source: PR-MS1.1 branch-level adversarial review originally at `2da9d9c701fa271e00af8324129af4bce69cbb7b`; post-governance rebase content-equivalent HEAD `7b6b125925e955589de9f356ba33012bd2d71c18`
Implementation Branch Under Freeze: `feature/pr-ms1-1-market-state-classifier` @ `7b6b125925e955589de9f356ba33012bd2d71c18` — `CHANGES_REQUIRED`, merge not permitted
Authoring Boundary: evidence, options, and consequences were authored by the reviewer; the domain owner supplied the six decisions in §§2–7. Those decisions completed adversarial review and are locked by this document. Implementation authority is limited to the remediation scope explicitly recorded herein.

---

## 0. Decision / Evidence Labels

Labels follow canonical contract §0 and are used here with identical meaning.

- **VERIFIED REPOSITORY FINDING** — supported by source evidence observed at the stated repository baseline.
- **FORMAL DERIVATION** — follows from stated verified mechanics and a stated mathematical contract.
- **LOCKED DECISION** — normative text locked either upstream or by this document; it is binding within its stated scope and is not re-decided here.
- **DEFERRED** — intentionally excluded from this phase.
- **REPOSITORY GAP** — an observed capability absence that restricts an otherwise desirable obligation.
- **INTEGRATOR ADDITION** — a non-ledger normative addition; not closed until its stated follow-up disposition occurs.

One label is added for this document only:

- **REVIEWER-SUPPLIED CONSEQUENCE** — the acceptance-test effect that follows from a given option. Derived from contract §12 and PR-MS0 §12, not an independent decision.

No statement in this document is a claim about strategy profitability, alpha, fill quality, or production readiness.

---

## 1. Entry Evidence and Governance Boundary

### 1.1 What this document is

Six questions surfaced during branch review that the locked PR-MS1.0 contract does not answer. Each blocks a specific remediation edit, because resolving it requires choosing a domain semantic rather than applying an existing one. This document supplies the evidence for those six and nothing else.

### 1.2 What this document is not

- It does **not** modify, reinterpret, or reopen any locked PR-MS1.0 or PR-MS0 decision, **except where this document explicitly records a narrowly scoped supersession required to close a discovered repository/contract gap**. Where locked text already answers a question, that text governs and the question does not appear here.
- It authorises only the PR-MS1.1 remediation changes explicitly bounded by this document. It does not authorise scope expansion beyond those remediation handoffs, nor any production integration, persistence, scheduler, strategy-adoption, or C-2 remediation work.
- It does **not** restate the review report. Findings whose remediation authority already exists are listed in §8 by ID only.
- It does **not** expand PR-MS1.1 scope. C-2 remediation, persistence, scheduler, strategy adoption, and batch orchestration remain out of scope and out of this document.

### 1.3 Verified entry state (as measured at `2da9d9c` / `3f060ab`)

```text
Reviewed HEAD:            2da9d9c701fa271e00af8324129af4bce69cbb7b
Reviewed base:            3f060ab8c4e6df7d44fc345319b560249ad8796a
Merge base == origin/main: verified (MERGE_BASE_EXIT=0)
Working tree:             CLEAN (STATUS_LINES=0)
Branch scope:             4 files, 1349 insertions, 0 deletions
Governance unchanged:     GOVERNANCE_UNCHANGED_EXIT=0
Ruff / mypy:              PASS (re-run during review)
Targeted / full pytest:   40 passed / 545 passed, 1 skipped (re-run during review)
```

Post-rebase anchors (not a re-attribution of the measurements above):

```text
Post-governance canonical base: 38153070d9e1031e0cd2859b90fff4151d61bed9
Post-rebase feature HEAD:       7b6b125925e955589de9f356ba33012bd2d71c18
Rebase byte identity:           VERIFIED for the four reviewed implementation/test files
```

Byte anchors for the four reviewed files are recorded in the review report §9.2 and are not repeated here.

### 1.4 Files read to produce this document

```text
docs/research/pr_ms1_0_security_market_state_domain_contract.md   (506 lines, complete)
docs/research/pr_ms1_0_q_ms1_02_06_exceptional_bar_disposition.md (§3.1-3.4)
docs/research/pr_ms1_0_q_ms1_08_export_provenance_disposition.md  (§3.1-3.4, §5.1-5.2)
docs/research/pr_ms0_repository_semantic_audit_decision_record.md (§7 MS-P1/P2/P3, §8 MS-I5/MS-I6, §12)
features/market_state.py                       (485 lines, complete)
features/market_state_assembly.py              (371 lines, complete)
tests/features/test_market_state.py            (316 lines, complete)
tests/features/test_market_state_assembly.py   (177 lines, complete)
market/trading_calendar.py                     (349 lines, complete)
data/database.py                               (L515-620: security_lifecycle, listed_market_daily_price_adj, connect)

Reviewer-verified after the branch review:
  data/database.py L345-374                    (daily_price_adj + adjustment_state schema)
  features/dividend_adjustment.py L188-224     (daily_price_adj write + adjustment_state upsert)
  features/dividend_adjustment.py L232-274     (freshness comparison against adjustment_state)
```

---

## 2. G-1 — Operational Diagnostic Taxonomy

Absorbs review findings F-03, F-16, F-31.

### 2.1 Locked evidence

**LOCKED DECISION (contract §4):** `OperationalDiagnosticCode` is assembly/composed-pipeline-owned. Exactly one code is required for every `Availability.OPERATIONAL_FAILURE`. `AS_OF_BAR_MISSING`, `AS_OF_BAR_INVALID`, and `AS_OF_BAR_ZERO_VOLUME` apply to the corresponding `as_of` condition. `REFERENCE_BASIS_UNAVAILABLE` applies **only when no calendar/lifecycle basis exists to construct any terminal eligible-session DTO**. Otherwise `UNCLASSIFIED_ASSEMBLY_FAILURE`, which explicitly communicates non-specific attribution and shall not be represented as a root cause.

**LOCKED DECISION (exceptional-bar disposition §3.3):** where assembly cannot establish the applicable diagnosis basis, it shall emit `DIAGNOSIS_UNAVAILABLE` rather than label the condition by assumption.

**LOCKED DECISION (contract §4):** `REFERENCE_BASIS_UNAVAILABLE` and `DIAGNOSIS_UNAVAILABLE` occupy disjoint pipeline stages — the former prevents DTO construction and classifier invocation; the latter applies only after a valid DTO is classified `INSUFFICIENT_HISTORY`.

### 2.2 Repository finding

**VERIFIED REPOSITORY FINDING (F-03).** `features/market_state_assembly.py:128-131` returns `REFERENCE_BASIS_UNAVAILABLE` when the `as_of` row is absent and lifecycle is unavailable. The module self-refutes the precondition: with lifecycle unavailable and an `as_of` row present, control reaches `:145-146` and constructs a DTO normally. Calendar basis was already used successfully at `:122`. Therefore a basis capable of constructing a terminal eligible-session DTO does exist, and the locked precondition for this code is not met.

**VERIFIED REPOSITORY FINDING (F-03, compounding).** `:235` converts any DB exception into `available=False`. A transient DuckDB lock combined with a missing `as_of` bar therefore yields a code that reads as permanent capability absence.

**VERIFIED REPOSITORY FINDING (F-16).** `:122-123` returns `AS_OF_BAR_MISSING` when the calendar reports `as_of` as a non-session, including when a row for `as_of` exists. No bar is missing in that case; session eligibility is absent. The five-code vocabulary has no member for this condition.

**VERIFIED REPOSITORY FINDING (F-31).** `market/trading_calendar.py:147-154`: `_is_in_twse_holidays_db` catches `Exception` and returns `False`, which is semantically "not a holiday". Layer 1 is the authoritative TWSE-announced source and takes priority over Layer 2 (XTAI). When the DB is unavailable, control falls through to Layer 2/3 and continues producing apparently normal answers. A closure announced after the XTAI package release exists only in Layer 1; with the DB unavailable, that date is judged an expected session, no row exists, and the terminal walk emits barrier `"gap"` → `DATA_GAP`.

**FORMAL DERIVATION (F-31).** The calendar branch of `REFERENCE_BASIS_UNAVAILABLE` is therefore unreachable along the DB-failure path. It remains reachable via `ec.get_calendar("XTAI")` (`trading_calendar.py:71`) and `_xtai_is_session` (`:94`), neither of which is caught. The existing test `tests/features/test_market_state_assembly.py:148-155` monkeypatches `is_trading_day` to raise `RuntimeError` — a condition the real module does not produce. The test proves the handler is correct; it does not prove the path is reachable.

### 2.3 Decision question

Does the locked five-code `OperationalDiagnosticCode` vocabulary require expansion to represent (i) `as_of` session eligibility that cannot be established, and (ii) a reference basis that is partially degraded but still answering? If not, which existing code owns each path?

### 2.4 Decision options

**Option A — No vocabulary change; reassign to existing codes.**
F-03 path returns `AS_OF_BAR_MISSING` (lifecycle availability does not bear on whether the `as_of` bar exists). F-16 path retains `AS_OF_BAR_MISSING`. F-31 remains a silent degradation with no diagnostic representation.

**Option B — Add one code for `as_of` eligibility not established.**
A sixth member, `AS_OF_ELIGIBILITY_NOT_ESTABLISHED`, covers F-03, F-16, and the governed lifecycle case in which `as_of` precedes `listed_from`. These are cases where eligibility at `as_of` is not established for composed-pipeline classification: evidence may be insufficient, or governed calendar/lifecycle evidence may affirmatively reject eligibility. F-31 remains unaddressed at the diagnostic layer and is instead handled by narrowing the calendar's exception policy.

**Option C — Add two codes: eligibility not established, and degraded reference basis.**
As Option B, plus a member representing "an authoritative reference layer failed and a lower-priority layer answered in its place". Requires `market/trading_calendar.py` to surface degradation to callers, which is outside the four-file remediation scope and would need a separate PR.

**Option D — No vocabulary change; make the authoritative layer fail loudly.**
`_is_in_twse_holidays_db` raises rather than returning `False` on DB failure, so `_cached_calendar` converts it to `_ReferenceBasisError` and `REFERENCE_BASIS_UNAVAILABLE` becomes genuinely reachable. F-03 and F-16 still require an assignment decision under Option A or B. Also outside the four-file scope.

**REVIEWER NOTE (not a decision).** Options C and D both require edits outside `features/market_state*.py` and their tests. Under the review's locked remediation scope this makes them multi-PR paths, not Commit 1 edits. This is a scheduling consequence, not an argument for or against either option.

### 2.5 Acceptance-test consequences

**REVIEWER-SUPPLIED CONSEQUENCE.**

- Under all options, contract §12 continues to require that a terminal-sequence construction basis failure yields `REFERENCE_BASIS_UNAVAILABLE`, no DTO, no classifier invocation, and no guessed history diagnostic. Any option that leaves this path unreachable in practice must state so explicitly rather than rely on a monkeypatched fixture.
- Option A: requires a fixture asserting the reassigned code for the F-03 path, plus a fixture separating a DB error from a genuinely empty lifecycle table, so the two conditions are not conflated.
- Option B: requires the two fixtures above plus a reachability fixture for the new member, and re-verification that all six codes are reachable and that no member becomes dead (review matrix R-17).
- Option C: additionally requires a fixture in which an authoritative layer fails, a lower layer answers, and the record carries the degradation code.
- Option D: additionally requires a fixture in which the holiday DB is unavailable and the record carries `REFERENCE_BASIS_UNAVAILABLE` through the real calendar module rather than a monkeypatch — this is the only option under which the existing reference-failure test becomes non-vacuous.

### 2.6 LOCKED DECISION

**LOCKED DECISION — OPTION B.**

The operational diagnostic vocabulary SHALL be expanded by one member representing failure to establish governed `as_of` eligibility.

The new member SHALL be spelled `AS_OF_ELIGIBILITY_NOT_ESTABLISHED` and SHALL own all three:

1. an `as_of` observation whose lifecycle/calendar evidence is insufficient to establish whether that date is an eligible session;
2. an `as_of` date for which a source row exists but the governed calendar states that the date is not an eligible session; and
3. an `as_of` date that precedes the governed lifecycle `listed_from`, providing affirmative lifecycle evidence that the security was not yet eligible at `as_of`.

The third condition is an operational-stage boundary condition: no classifier DTO SHALL be constructed and the classifier SHALL NOT be invoked. It SHALL NOT be reported as `NATURAL_HISTORY_SHORTFALL`. `NATURAL_HISTORY_SHORTFALL` remains a history-diagnostic-stage result when `as_of` itself is validly listed and the backward terminal walk crosses the governed `listed_from` boundary before sufficient history is collected.

`AS_OF_ELIGIBILITY_NOT_ESTABLISHED` SHALL NOT mean that the bar is missing. `AS_OF_BAR_MISSING` remains reserved for an eligible `as_of` session for which the governed price observation is absent. `REFERENCE_BASIS_UNAVAILABLE` remains reserved for failure severe enough that no terminal eligible-session DTO can be constructed.

F-31 calendar-authority degradation is NOT solved by this member. The silent fallback in `market/trading_calendar.py` SHALL be governed and remediated in a separate PR outside PR-MS1.1's four-file scope.

### 2.7 Closure criteria

1. F-03, F-16, and `as_of < listed_from` are owned by `AS_OF_ELIGIBILITY_NOT_ESTABLISHED`.
2. `as_of < listed_from` terminates at the operational stage with no DTO and no classifier invocation; crossing `listed_from` during a validly listed `as_of` history walk remains eligible for `NATURAL_HISTORY_SHORTFALL`.
3. `AS_OF_BAR_MISSING` remains semantically exact: eligible session, observation absent.
4. `REFERENCE_BASIS_UNAVAILABLE` and `DIAGNOSIS_UNAVAILABLE` remain in disjoint pipeline stages as locked by contract §4.
5. The vocabulary supersession from five to six members is recorded explicitly, and all six members are shown reachable by regression evidence.
6. The production reachability profile of all six members is stated explicitly. `AS_OF_BAR_MISSING` is production-reachable only when governed lifecycle eligibility is AVAILABLE, governed calendar eligibility accepts `as_of`, and the governed `as_of` price observation is absent. Lifecycle UNAVAILABLE and NOT_LISTED_AT_AS_OF paths are both owned by `AS_OF_ELIGIBILITY_NOT_ESTABLISHED`. Fixture reachability SHALL NOT be presented as universal production reachability.
7. F-31 remains an explicit separate-PR obligation; PR-MS1.1 SHALL NOT claim to have fixed authoritative calendar degradation.

**CURRENT OBSERVABILITY NOTE (v0.2.1).** Under the current `listed_market_daily_price_adj` view, if governed TWSE/TPEx lifecycle rows exist but every `listed_from > as_of`, then the governed adjusted-price view yields no `date <= as_of` row. Consequently `UNAVAILABLE` and `NOT_LISTED_AT_AS_OF` currently converge to the same exported operational result (`AS_OF_ELIGIBILITY_NOT_ESTABLISHED`, no DTO, no classifier invocation, no `panel_snapshot_id`). The internal distinction is retained because it preserves the evidence semantics required by G-6, prevents future-effective rows from being mistaken for row absence, and becomes observationally relevant if lifecycle coverage or governed view semantics change. Regression evidence SHALL test the state-resolution distinction directly rather than require distinct current export records.

### 2.8 Implementation handoff

Commit 1 may modify `features/market_state.py` **only for the `OperationalDiagnosticCode` vocabulary addition owned by contract §6.2**, plus `features/market_state_assembly.py` for assignment/routing and the corresponding tests in `tests/features/test_market_state.py` and `tests/features/test_market_state_assembly.py`. Definition location does not alter producing/assignment ownership. The broad `:235` DB-exception handler SHALL be narrowed under existing remediation authority. No edit to `market/trading_calendar.py` is authorised by this disposition; F-31 requires a separate governed PR.

---

## 3. G-2 — Applied Adjustment Provenance

Absorbs review finding F-05.

### 3.1 Locked evidence

**LOCKED DECISION (contract §9):** `AdjustmentProvenance` shall identify adjustment method/version, the applied corporate-action factor-set content identity, and the relevant source/basis identity. It **identifies applied values, not merely ingestion time**. Under the current overwrite architecture it shall not be represented as immutable adjustment-factor revision provenance; C-2 remains deferred.

**LOCKED DECISION (contract §8.4):** C-2 covers late or corrected actions with `ex_date <= as_of` whose prior factor values are physically destroyed by `DELETE + INSERT`. `ingested_at`, `last_event_date_used`, and `n_events_applied` are not immutable revision provenance.

**VERIFIED REPOSITORY FINDING (contract §14):** the evidence record lists `data/database.py: adjustment_state` as an existing schema element observed during PR-MS1.0 entry work.

### 3.2 Repository finding

**VERIFIED REPOSITORY FINDING (F-05).** The panel is read from `listed_market_daily_price_adj` (`features/market_state_assembly.py:214`), a view over `daily_price_adj`, which is a materialised artifact produced by a separate rebuild step. The factor-set hash is computed by querying `corporate_actions` directly (`:321-327`). `adjustment_state` is never queried.

**FORMAL DERIVATION (F-05).** Between an update to `corporate_actions` and the next rebuild of `daily_price_adj`, the two objects describe different points in time. The provenance therefore reports a factor set that was not applied to the panel it accompanies.

**VERIFIED REPOSITORY FINDING (F-05, scope limit).** The query window itself is correct and is not in question. `date > bars[0].session` matches contract §8.3's verified mechanics (`cum_factor[T]` is formed from factors strictly later than `T`), so the earliest bar's factor set is an upper bound covering the whole panel. `confirmed = TRUE AND adjustment_factor IS NOT NULL` matches the verified ingestion semantics.

**REVIEWER NOTE.** This is distinct from C-2. C-2 concerns revisions that cannot be reconstructed. This concerns a divergence between source state and applied state that exists even when no revision has occurred. The C-2 deferral does not cover it.

**VERIFIED REPOSITORY FINDING (post-review re-verification).** `adjustment_state` at `data/database.py:367-374` is per-security (`stock_id VARCHAR PRIMARY KEY`) and contains only `last_built_at`, `last_event_date_used`, `n_events_applied`, `raw_first_date`, and `raw_last_date`; there is no factor/content hash, rebuild-content digest, or applied-state identity. Repository-wide `rg` over `*.py` and `*.sql` found no `ALTER TABLE` or migration that extends this capability. `features/dividend_adjustment.py:188-224` rewrites `daily_price_adj` and then upserts only those freshness fields into `adjustment_state`; `:232-274` uses the state only for raw/event date drift detection. Options A/C therefore have no applied-factor content identity to consume at the reviewed baseline.

**VERIFIED REPOSITORY FINDING (atomicity/freshness semantics).** `write_adjusted_to_db` performs four ordered DML statements on one DuckDB connection but contains no explicit `BEGIN`/`COMMIT`; under DuckDB autocommit there is no function-level atomic transaction binding the `daily_price_adj` rewrite to the `adjustment_state` rewrite. `last_built_at` is written from `datetime.now()` at `features/dividend_adjustment.py:218`, so it is freshness/ingestion metadata rather than applied-content identity, consistent with contract §9's exclusion of ingestion-time metadata from applied-value provenance.


### 3.3 Decision question

Must `AdjustmentProvenance.factor_set_hash` be bound to the adjustment state actually applied to the panel, or may it identify the current source factor set provided the distinction is declared?

### 3.4 Decision options

**Option A — Bind to applied state.**
Query `adjustment_state` and incorporate the applied-state identity, so the provenance describes the factors materialised into the panel being classified. Repository verification confirms that `adjustment_state` carries no applied-factor content identity sufficient for this purpose; see §3.2. Accordingly, this option is not implementable at the reviewed baseline without schema/writer expansion.

**Option B — Declare the narrower semantic.**
Keep the current query and rename the field and its documentation to state that it identifies the **source** factor set at assembly time, not the applied set. This weakens the contract §9 obligation and therefore requires an explicit supersession, not a silent narrowing.

**Option C — Bind to applied state where available, degrade explicitly otherwise.**
Use `adjustment_state` when it yields a usable identity; otherwise emit an explicit unavailability marker rather than substituting the source hash. Consistent with the treatment of `DIAGNOSIS_UNAVAILABLE` elsewhere in the contract.

**Option D — Bind to the materialised `cum_factor` state under replay-equivalence semantics.**
Derive the applied factor-set identity from the ordered `(session/date, binary64(cum_factor))` sequence exposed through `listed_market_daily_price_adj` for the governed panel range. The assembly SHALL NOT query `daily_price_adj` directly for this purpose. This identifies the adjustment state actually materialised into the governed panel, but does not uniquely reconstruct the underlying corporate-action event decomposition.

**VERIFIED FEASIBILITY NOTE.** At the reviewed baseline, `adjustment_state` contains no applied-factor content identity that assembly could incorporate. Options A and C are therefore **repository-infeasible without schema/writer expansion outside the four-file remediation scope**. This is a verified repository capability limit, not an owner attestation.

### 3.5 Acceptance-test consequences

**REVIEWER-SUPPLIED CONSEQUENCE.**

- Option A: requires a fixture in which `corporate_actions` changes without a panel rebuild, asserting that the reported provenance does **not** change. Not applicable under the reviewed baseline schema: §3.2 verifies that `adjustment_state` contains no applied-factor content identity sufficient to implement Option A without schema/writer expansion.
- Option B: requires a fixture asserting the declared narrower semantic, and the contract §9 supersession must be recorded in this document. It also requires an explicit statement that replay claims based on this field are bounded accordingly.
- Option C: requires both fixtures above plus one asserting the degraded marker when applied state is unavailable.
- Option D: requires a fixture showing that changing `corporate_actions` without rebuilding the governed adjusted panel does not change the applied-provenance identity; rebuilding to different materialised `cum_factor` values must change it. The hash input must preserve session/date association and exact binary64 factor values.
- Under every option, contract §12's Variant C obligation ("a real assembly-path fixture introducing an action with `ex_date > t`") remains and must use a real DuckDB path, not a mock. Review finding F-08 records that `_adjustment_provenance` is currently monkeypatched in every assembly test, so this obligation is presently undischarged regardless of which option is chosen.

### 3.6 LOCKED DECISION

**LOCKED DECISION — OPTION D.**

For PR-MS1.1, `AdjustmentProvenance.factor_set_hash` SHALL identify the materialised applied adjustment state under **replay-equivalence semantics**.

The identity SHALL be computed from the ordered canonical `cum_factor` values associated with the governed panel observations exposed through `listed_market_daily_price_adj`. Canonical encoding SHALL preserve session/date association and exact binary64 factor values. PR-MS1.1 SHALL NOT query `daily_price_adj` directly for this identity.

Where practical, adjusted OHLC and `cum_factor` SHALL be materialised by the same governed panel query so that panel values and adjustment provenance are observed through the same read boundary.

This identity guarantees replay-equivalence of the applied adjustment state. It does **not** guarantee unique reconstruction of the underlying corporate-action event decomposition, audit-direction traceability, or immutable historical revision provenance. C-2 therefore remains DEFERRED.

Options A and C are repository-infeasible **at the reviewed baseline** without expanding `adjustment_state`; this is now a VERIFIED REPOSITORY FINDING. Option B is rejected because it weakens §9 to source-state semantics rather than remediating F-05.

### 3.7 Closure criteria

1. `factor_set_hash` is defined as replay-equivalent applied-state identity over the governed materialised `cum_factor` sequence.
2. Canonical encoding binds each factor to its session/date and exact binary64 representation.
3. The implementation reads `cum_factor` only through `listed_market_daily_price_adj`; direct `daily_price_adj` access remains forbidden.
4. Source-state changes without a governed panel rebuild do not change the applied-provenance identity; materialised factor changes do.
5. Audit-direction event traceability and immutable revision reconstruction are explicitly outside this identity; C-2 remains DEFERRED.

### 3.8 Implementation handoff

Commit 1, files `features/market_state_assembly.py` and `tests/features/test_market_state_assembly.py`. Fold `cum_factor` into the governed panel read where feasible, remove the direct `corporate_actions` provenance query, and add regression evidence binding provenance to the materialised panel state.

---

## 4. G-3 — Negative-Volume Disposition

Absorbs review finding F-12.

### 4.1 Locked evidence

**LOCKED DECISION (contract §7 treatment table).** Conditions at an expected session and their canonical-panel treatment:

```text
Missing bar, invalid OHLC, or invalid OHLC ordering  → terminal-sequence barrier
Zero-volume bar with valid OHLC                      → ineligible terminal-sequence barrier
Zero-range bar with positive volume and valid OHLC   → included
```

**LOCKED DECISION (exceptional-bar disposition §3.2).** The invalid condition is defined as "OHLC null, non-finite, non-positive, or violates OHLC ordering".

**REVIEWER NOTE.** Both definitions of "invalid" are expressed purely in terms of OHLC. Neither table has a row for negative volume, and negative volume is neither zero nor positive.

### 4.2 Repository finding

**VERIFIED REPOSITORY FINDING (F-12).** `features/market_state_assembly.py:263` routes `row.volume < 0` into the `"invalid"` branch; the docstring at `:250` states this explicitly ("negative volume is invalid, not zero volume"). Consequently an `as_of` bar with negative volume yields `AS_OF_BAR_INVALID`, and a mid-panel negative-volume bar yields barrier `"gap"` → `DATA_GAP`.

**FORMAL DERIVATION (F-12).** Of the three possible treatments, this is the only one that neither mislabels the condition as zero-volume nor admits a structurally corrupt row into price-structure classification. Kickoff scenario 5 (`as_of` OHLC invalid **and** volume negative simultaneously) converges safely under it. The behaviour is defensible; what is absent is authorisation.

**REVIEWER NOTE.** `AS_OF_BAR_INVALID` and `DATA_GAP` both currently name an OHLC-scoped condition. Routing a volume condition through them is a naming imprecision as well as an undeclared extension.

### 4.3 Decision question

How is negative volume treated in the canonical panel, and which diagnostic owns it?

### 4.4 Decision options

**Option A — Ratify current behaviour.**
Add a treatment-table row: negative volume is a terminal-sequence barrier of the same class as invalid OHLC, reported through the invalid-bar codes. No code change; docstring gains a governance citation.

**Option B — Ratify as a distinct condition with its own diagnostic.**
Negative volume is a barrier but is reported through a distinct code or history diagnostic, so that source corruption is distinguishable from OHLC invalidity in audit trails.

**Option C — Treat as source corruption warranting operational failure regardless of position.**
A negative volume anywhere in the fetched window is treated as a data-integrity failure rather than a barrier. Most conservative; changes behaviour for mid-panel occurrences.

**REVIEWER NOTE (not a decision).** The exceptional-bar disposition records that the repository contained zero zero-volume bars at entry, and explicitly states that this does not remove the future-data contract. The reviewer has not measured the incidence of negative volume in the current database and offers no estimate; the same forward-looking reasoning applies.

### 4.5 Acceptance-test consequences

**REVIEWER-SUPPLIED CONSEQUENCE.**

- Option A: requires the existing fixtures at `tests/features/test_market_state_assembly.py:100-101` to be retained and cited against the new table row. No new behaviour to test; the fixtures already assert `AS_OF_BAR_INVALID` for `volume=-1` both alone and combined with invalid OHLC.
- Option B: requires a fixture distinguishing a negative-volume barrier from an OHLC-invalid barrier at both `as_of` and mid-panel positions, and a reachability check for the new diagnostic.
- Option C: requires a fixture asserting operational failure for a mid-panel negative-volume bar — a behaviour change from the current implementation, which treats it as a barrier and can still produce an `AVAILABLE` record.

### 4.6 LOCKED DECISION

**LOCKED DECISION — OPTION A.**

Negative volume is invalid source data. A negative-volume observation SHALL be an ineligible terminal-sequence barrier in the same canonical treatment class as an otherwise invalid bar.

At `as_of`, it SHALL be owned by `AS_OF_BAR_INVALID`. Inside the terminal history sequence, it SHALL participate in the same barrier/data-gap semantics as other invalid observations.

The documented scope of "invalid bar" SHALL be widened from OHLC validity alone to **observation validity**, covering OHLC null/non-finite/non-positive/order-invalid conditions and `volume < 0`. `volume == 0` remains a separate zero-volume semantic because it has a distinct market interpretation and already owns a separate contract path. No new diagnostic member is introduced for negative volume.

### 4.7 Closure criteria

1. The canonical treatment table explicitly includes negative volume as invalid observation data and a terminal-sequence barrier.
2. `AS_OF_BAR_INVALID` documentation is widened from OHLC-only to observation validity including `volume < 0`.
3. Mid-panel negative volume retains the same barrier/data-gap semantics as other invalid observations; no new dead-prone diagnostic is created.
4. Zero volume remains a separate semantic path and is not conflated with negative volume.

### 4.8 Implementation handoff

No behavioural code change is required if the existing routing remains unchanged. Commit 1 may update the `_bar_condition` documentation/governance trace and retain the existing regression fixtures that already cover negative volume.

---

## 5. G-4 — `corporate_actions` Reference-Source Admission

Absorbs review finding F-15.

### 5.1 Locked evidence

**LOCKED DECISION (contract §5.3, Q-MS1-08):**

```text
CLASSIFIER_REFERENCE_INPUTS_ADMITTED = NO
ASSEMBLY_REFERENCE_SOURCES = {calendar, security_lifecycle}
```

Any additional source requires a superseding Q-MS1-02 / Q-MS1-08 disposition. Every assembly reference source requires governed effective-date semantics; undated latest-state lookup is forbidden.

**LOCKED DECISION (contract §9):** `AdjustmentProvenance` shall identify the applied corporate-action factor-set content identity.

### 5.2 Repository finding

**VERIFIED REPOSITORY FINDING (F-15).** `features/market_state_assembly.py:321-327` queries `corporate_actions`, which is not a member of the declared `ASSEMBLY_REFERENCE_SOURCES` set.

**REVIEWER NOTE.** This is an internal contract inconsistency, not primarily an implementation violation. Contract §9 requires a factor-set content identity, which cannot be produced without reading the factor source, while contract §5.3 does not list that source. The implementation satisfies §9 and thereby exceeds §5.3's declaration. A reviewer cannot resolve which of the two locked statements yields.

**FORMAL DERIVATION.** The `corporate_actions` query is `as_of`-bounded in the relevant direction (`date > bars[0].session`, derived from contract §8.3's cum-factor mechanics), so it does not introduce a lookahead path. The admission question is declarative completeness, not PIT safety.

### 5.3 Decision question

Is `corporate_actions` admitted as an assembly reference source, and if so, what are its governed effective-date semantics?

### 5.4 Decision options

**Option A — Admit as a third assembly reference source.**
`ASSEMBLY_REFERENCE_SOURCES = {calendar, security_lifecycle, corporate_actions}`, with effective-date semantics stated (ex-date based, confirmed actions only) and the PIT obligation made explicit.

**Option B — Declare it a provenance source, not a reference source.**
Distinguish sources that shape the canonical input (calendar, lifecycle) from sources that only identify provenance of an already-materialised artifact. `corporate_actions` is the latter, so §5.3's set stays unchanged and a separate provenance-source declaration is added.

**Option C — Remove the direct `corporate_actions` dependency.**
Obtain the applied adjustment identity from the governed materialised adjusted-price artifact rather than from `corporate_actions`. Under G-2 Option D this means the ordered `cum_factor` state exposed through `listed_market_daily_price_adj`; the admission question is then superseded because the undeclared source is no longer read by assembly.

**REVIEWER NOTE.** G-4 depends on G-2. If G-2 selects a materialised-artifact identity, `corporate_actions` leaves the assembly dependency surface and this section dissolves into a recorded supersession. If a future design again reads an upstream provenance source directly, that source must receive its own governed admission/effective-date semantics.

### 5.5 Acceptance-test consequences

**REVIEWER-SUPPLIED CONSEQUENCE.**

- Option A: contract §12 requires effective-date filtering for **every admitted source**, and PR-MS0 MS-P1 Variant B requires both a negative-direction and a positive-direction fixture per admitted source. Admitting `corporate_actions` therefore adds two required fixtures beyond those already owed for calendar and lifecycle (review findings F-06, F-07).
- Option B: no new Variant B obligation, but the provenance-source category must state its own temporal-validity rule, and a fixture must show that a future-effective action does not alter the provenance identity for `as_of=t`.
- Option C: the admission obligation moves to whichever source replaces it; its own effective-date semantics must then be declared under G-2.

### 5.6 LOCKED DECISION

**LOCKED DECISION — SUPERSEDED BY G-2 OPTION D.**

Because G-2 removes PR-MS1.1 assembly's direct dependency on `corporate_actions` for adjustment provenance, `corporate_actions` is not admitted as an assembly reference source.

`ASSEMBLY_REFERENCE_SOURCES` remains `{calendar, security_lifecycle}`. `corporate_actions` remains an upstream source owned by the adjustment pipeline that materialises the governed adjusted-price artifact. PR-MS1.1 assembly SHALL consume that governed materialised artifact and SHALL NOT independently reconstruct applied adjustment provenance from `corporate_actions`.

F-15 therefore closes by removal of the undeclared dependency rather than by admission of an additional reference source.

### 5.7 Closure criteria

1. `corporate_actions` is no longer queried by PR-MS1.1 assembly.
2. `ASSEMBLY_REFERENCE_SOURCES` remains exactly `{calendar, security_lifecycle}`.
3. Adjustment provenance is obtained from the governed materialised panel state under G-2, not reconstructed from producer-source events.
4. No new Variant B obligation is created for `corporate_actions` at the assembly layer.

### 5.8 Implementation handoff

Commit 1 removes the direct `corporate_actions` provenance dependency as part of G-2/F-05 remediation. Commit 3 retains Variant B obligations only for the admitted assembly reference sources `calendar` and `security_lifecycle`.

---

## 6. G-5 — Snapshot Identity Within Variant B

Bears on review findings F-07 (fixture assertion scope), F-13 (lifecycle exposure path), and F-14 (calendar identity construction).

### 6.1 Locked evidence

**LOCKED DECISION (contract §8.2, PIT Variant B):** for each admitted classifier reference input or assembly reference source, a mutation effective strictly after `t` shall not change the `as_of=t` **canonical input, history diagnostic, or classification**. An effective-at-or-before-`t` positive-direction fixture is required where that field is classification-relevant.

**LOCKED DECISION (contract §9):** `PanelSnapshotId` shall be a stable content identity of the exact terminal adjusted-OHLC sequence submitted to the classifier. Its **canonical input contains** security/as-of/session identities, adjusted OHLC binary64 bit patterns, **eligible-session/reference basis identities**, adjustment-provenance identity, and assembly schema version. Any semantic canonical-input change produces a different ID.

**REVIEWER NOTE.** §8.2 enumerates three protected objects and does not name snapshot identity. §9 states that reference basis identities are part of the snapshot's canonical input. Whether a future-effective reference mutation that changes only the snapshot ID violates Variant B depends on whether "canonical input" in §8.2 refers to the classifier DTO alone or includes the snapshot's canonical input. The two sections use the same phrase for different objects.

### 6.2 Repository finding

**VERIFIED REPOSITORY FINDING (F-13).** `features/market_state_assembly.py:228-234` selects all lifecycle rows for the security with no `as_of` bound.

**FORMAL DERIVATION (F-13, exposure is narrower than first stated).** `listed_from` is taken as `min(...)` at `:237`, so a future-effective row with a later `listed_from` does not change it; classification behaviour is therefore PIT-safe on this path. However `content_identity` at `:238-245` hashes **all** returned rows including `listed_to`, `source_type`, and `source_url`, and that identity enters `_panel_snapshot_id` at `:357`. A future-effective lifecycle row therefore changes the snapshot ID while leaving classification unchanged. This is a pure identity exposure, not a classification lookahead.

**REVIEWER NOTE.** F-13's remediation authority is independent of this question. Contract §5.3 forbids undated latest-state lookup and MS-I6 requires every dated dependency to be valid for the requested `as_of`; both are locked and already require the effective-date filter. G-5 determines only what the Variant B fixture must assert, not whether the filter is added.

### 6.3 Decision question

Does PIT Variant B protect `panel_snapshot_id`, or only the classifier DTO, history diagnostic, and classification?

### 6.4 Decision options

**Option A — Variant B protects snapshot identity.**
A future-effective reference mutation must leave `panel_snapshot_id` unchanged. Strongest replay guarantee; requires every reference identity feeding the snapshot to be `as_of`-scoped.

**Option B — Variant B protects only the three objects §8.2 names.**
Snapshot identity may vary with reference state as observed at assembly time. Reproducibility is then bounded: replay at a later date may produce a different snapshot ID for the same classification.

**Option C — Split the identity.**
Separate the `as_of`-scoped reference basis identity, which feeds the snapshot, from assembly-time observational metadata, which does not. Preserves both a stable snapshot ID and the full provenance record.

**REVIEWER NOTE.** Option B interacts with C-2's deferred remediation, whose stated prerequisite is "an append-only history/audit model **or an equivalent immutable snapshot identity**". A decision that snapshot identity need not be stable under reference mutation narrows the second of those two remediation routes. The reviewer states the interaction without asserting how much it narrows it.

### 6.5 Acceptance-test consequences

**REVIEWER-SUPPLIED CONSEQUENCE.**

- Option A: the Variant B negative-direction fixture (owed under F-07) must assert that status, state, `matched_rule_id`, history diagnostic, **and** `panel_snapshot_id` are unchanged. The snapshot mutation fixtures owed under F-09 must then distinguish `as_of`-relevant reference changes, which must alter the ID, from future-effective ones, which must not.
- Option B: the same fixture asserts only the three named objects; `panel_snapshot_id` is explicitly excluded, and that exclusion is documented so it is not read as an oversight. The reproducibility bound must be stated in contract §9's terms.
- Option C: requires fixtures for both halves of the split and an explicit statement of which fields belong to which half.
- Under all options, F-09's four mutation fixtures (adjusted OHLC, calendar basis, lifecycle identity, factor set) and one reproducibility assertion remain owed, since none is currently present.

### 6.6 LOCKED DECISION

**LOCKED DECISION — OPTION A.**

PIT Variant B SHALL protect `panel_snapshot_id` against reference mutations whose effective time is strictly after `as_of=t`.

For such future-effective reference mutations, canonical classifier input, history diagnostic, classification status/state/`matched_rule_id`, and `panel_snapshot_id` SHALL remain unchanged.

This stability requirement is specific to Variant B reference mutations. It does **not** require unconditional snapshot stability when the governed panel itself legitimately changes under another contract path. In particular, Variant C may change adjusted-OHLC binary64 values and therefore `panel_snapshot_id` while status/state/`matched_rule_id` remain unchanged, as permitted by contract §8.3.

Calendar and lifecycle basis identities feeding the snapshot SHALL therefore be `as_of`-scoped. A future-effective calendar/lifecycle mutation outside the governed panel basis SHALL NOT perturb an earlier snapshot identity.

### 6.7 Closure criteria

1. Contract §8.2's protected set explicitly includes `panel_snapshot_id` for future-effective Variant B reference mutations.
2. The Variant B fixture asserts field-by-field invariance for canonical classifier input, history diagnostic, classification identity, and snapshot identity.
3. Calendar/lifecycle content identities are `as_of`-scoped rather than global/latest-state identities.
4. Variant C remains allowed to change snapshot identity when the governed adjusted panel itself changes; this is recorded to prevent a false cross-variant conflict.
5. The C-2 remediation route based on an immutable/equivalent snapshot identity remains available rather than being silently narrowed.

### 6.8 Implementation handoff

F-13's lifecycle effective-date filter proceeds in Commit 1 under existing locked authority. F-14's calendar identity remediation SHALL derive identity from the governed panel-relevant calendar/session decisions rather than a hardcoded version or an unscoped whole-calendar hash. Commit 3 adds Variant B negative/positive-direction fixtures and F-09 snapshot mutation/reproducibility coverage.

---

## 7. G-6 — Lifecycle Basis Coverage

Absorbs review finding F-29.

### 7.1 Locked evidence

**LOCKED DECISION (contract §7 treatment table):** a session before the governed `listed_from` is "not expected; never padded", and yields `NATURAL_HISTORY_SHORTFALL` when the terminal DTO is insufficient.

**LOCKED DECISION (exceptional-bar disposition §3.3):** if the expected-session basis itself cannot be established because the governed calendar or lifecycle source is unavailable, assembly shall emit `DIAGNOSIS_UNAVAILABLE` rather than label the condition `DATA_GAP` or `NATURAL_HISTORY_SHORTFALL` by assumption.

### 7.2 Repository finding

**VERIFIED REPOSITORY FINDING (F-29).** `data/database.py:516-523`: `security_lifecycle` "Covers only the 18 stocks with IF-1 pre-listing contamination", and "Stocks absent from this table are assumed fully listed throughout the panel". Its governance is SPEC-P1-DATA-REMEDIATION-v1, whose scope is contamination removal, not universal lifecycle coverage.

**VERIFIED REPOSITORY FINDING (F-29).** `features/market_state_assembly.py:239-246`: when the lifecycle query returns zero rows, the module returns `available=True` with `listed_from=None`. At `:282` the natural-shortfall check requires `listed_from is not None`, so it is skipped. The walk therefore continues past the security's real listing date, finds no row at an expected session, and returns barrier `"gap"` → `DATA_GAP` at `:313-314`.

**FORMAL DERIVATION (F-29).** For any security outside the 18-stock seed — that is, the large majority of the dynamic top-200 universe — `NATURAL_HISTORY_SHORTFALL` is structurally unreachable, and genuinely short history is reported as `DATA_GAP`. A recently listed security therefore presents as a data-quality defect rather than as insufficient history.

**REVIEWER NOTE.** The implementation faithfully follows the seed table's declared assumption. The gap is that returning `available=True` on zero rows asserts that a basis exists on the strength of a blanket assumption rather than evidence, which the locked disposition §3.3 rule addresses directly.

**REPOSITORY GAP.** Contract §7 presumes every security has a governed `listed_from`. `security_lifecycle` provides one for 18 securities. This is a scope mismatch between the contract and the remediation artifact it relies on.

**VERIFIED REPOSITORY FINDING (consistency, not a defect).** `data/database.py:548-559`: the `listed_market_daily_price_adj` view applies `COALESCE(MIN(listed_from) for TWSE/TPEx, DATE '1900-01-01')`. `_load_lifecycle_basis`'s `market IN ('TWSE','TPEx')` filter and `min(listed_from)` selection match the view's semantics exactly. Neither uses `listed_to`. The `listed_to` deferral recorded in the review report is therefore consistent at both layers.

### 7.3 Decision question

When `security_lifecycle` returns no row for a security, is the lifecycle basis considered available, unavailable, or available under a governed default?

### 7.4 Decision options

**Option A — Absent row means basis unavailable.**
`available=False` → `DIAGNOSIS_UNAVAILABLE`. Most faithful to disposition §3.3. Consequence: for most of the universe the history diagnostic becomes constant, carrying near-zero information, and `NATURAL_HISTORY_SHORTFALL` and `DATA_GAP` both become largely unreachable.

**Option B — Extend `security_lifecycle` to the full universe.**
Semantically correct and restores every diagnostic's reachability. Requires data engineering beyond P1-DATA's scope and well beyond PR-MS1.1's four-file remediation surface; would be a separate governed programme.

**Option C — Govern the default explicitly.**
Record a locked decision that an absent row means "listed no later than the earliest available observation", and derive natural shortfall from the earliest available row rather than from `listed_from`. A barrier occurring before the earliest available observation is then `NATURAL_HISTORY_SHORTFALL`; a barrier at a session for which older data exists remains `DATA_GAP`.

**REVIEWER NOTE (mechanism, corrected after owner decision).** F-02, F-04, and F-29 still require coordinated editing in the same `_terminal_bars` function/Commit 1, but they do **not** share one semantic mechanism. `min(row_by_session)` is mechanical evidence for fetch exhaustion and an explicit iteration bound (F-02/F-04). Lifecycle semantics remain governed by `listed_from`/basis availability; under the selected G-6 Option A, `min(row_by_session)` SHALL NOT be used as a proxy listing date for F-29.

**REVIEWER NOTE (limitation of Option C).** Earliest-available-observation is a proxy for listing date, not the same thing. A security whose early history was never ingested would present as naturally short when it is in fact gapped. Option C trades one misattribution for another with a different failure profile; the reviewer does not assert which profile is preferable.

### 7.5 Acceptance-test consequences

**REVIEWER-SUPPLIED CONSEQUENCE.**

- Option A: requires a fixture asserting `DIAGNOSIS_UNAVAILABLE` for a security absent from the lifecycle table, and an explicit statement in the review matrix that `NATURAL_HISTORY_SHORTFALL` is reachable only for the 18 seed securities. Review matrix R-17 (diagnostic reachability) must be re-evaluated against that statement.
- Option B: restores full reachability; requires fixtures for all four history diagnostics against real lifecycle data, and a separate programme with its own acceptance criteria.
- Option C: requires two fixtures — a barrier before the earliest available observation yielding `NATURAL_HISTORY_SHORTFALL`, and a barrier at a session with older data present yielding `DATA_GAP` — plus the F-02 fixture (a non-session row inside the window must not yield `DATA_GAP`), since all three exercise the same boundary.
- Under every option, contract §12's requirement of governed history diagnostics and `DIAGNOSIS_UNAVAILABLE` remains, and the existing test at `tests/features/test_market_state_assembly.py:158-168` continues to cover the lifecycle-unavailable path.

### 7.6 LOCKED DECISION

**LOCKED DECISION — OPTION A, WITH OPTION B AS A SEPARATE GOVERNED REMEDIATION PROGRAMME.**

Absence of a `security_lifecycle` row SHALL NOT be treated as affirmative evidence of listing eligibility.

**v0.2.1 G-1 cross-reference.** This absence rule is distinct from affirmative governed evidence that `as_of < listed_from`. The former is lifecycle `UNAVAILABLE`; the latter is `NOT_LISTED_AT_AS_OF`. Both currently route to `AS_OF_ELIGIBILITY_NOT_ESTABLISHED` at the operational `as_of` boundary, but only the latter carries affirmative evidence of non-listing. When `as_of` itself is validly listed and the backward history walk crosses `listed_from`, the condition remains history-stage `NATURAL_HISTORY_SHORTFALL` semantics rather than an operational G-1 failure.

For PR-MS1.1, when no governed lifecycle row exists and lifecycle evidence is required to attribute terminal-history insufficiency, the history diagnostic SHALL be `DIAGNOSIS_UNAVAILABLE` rather than `DATA_GAP` or `NATURAL_HISTORY_SHORTFALL` inferred from a proxy.

The repository assumption that an absent lifecycle row means "fully listed throughout the panel" is insufficient evidence for Market State history-diagnostic attribution and is superseded for this specific composed-pipeline diagnostic purpose. PR-MS1.1 SHALL NOT infer listing date from the earliest available price observation.

A separate governed data-remediation programme SHALL extend lifecycle basis coverage beyond the current 18-stock seed. Once authoritative lifecycle coverage exists, `NATURAL_HISTORY_SHORTFALL` and `DATA_GAP` reachability SHALL be re-evaluated for the full universe.

### 7.7 Closure criteria

1. An absent `security_lifecycle` row yields lifecycle-diagnostic unavailability rather than an assumed listing state for Market State attribution.
2. `min(row_by_session)` is used only as mechanical fetch/iteration evidence for F-02/F-04 and SHALL NOT be promoted into a proxy listing date.
3. `NATURAL_HISTORY_SHORTFALL` requires governed lifecycle evidence such as `listed_from`; absence of that evidence does not authorize inference.
4. The resulting reachability limitation for non-seed securities is recorded explicitly rather than hidden.
5. Full-universe lifecycle coverage is opened as a separate governed data-remediation programme, not silently folded into PR-MS1.1.
6. The G-1 interaction is recorded explicitly: for securities without governed lifecycle coverage, an absent `as_of` row is owned by the new eligibility-undetermined operational diagnostic, so `AS_OF_BAR_MISSING` is not universally production-reachable across the universe.

### 7.8 Implementation handoff

Commit 1, files `features/market_state_assembly.py` and `tests/features/test_market_state_assembly.py`. `_terminal_bars` SHALL separate mechanical row-window bounds from lifecycle semantic evidence: `min(row_by_session)` may bound iteration and prevent false `DATA_GAP` attribution caused by fetch exhaustion, but it SHALL NOT determine `NATURAL_HISTORY_SHORTFALL`. When governed lifecycle evidence is absent, the history diagnosis is `DIAGNOSIS_UNAVAILABLE`.

---

## 8. Non-Governance Items

The following review findings have remediation authority in already-locked text. They proceed directly to the remediation commits and require no decision in this document. Listed by ID with the authority that governs them.

| Finding | Governing authority |
|---|---|
| F-01 | contract §9 — hash covers each admitted indicator's algorithm/lookback/window semantics |
| F-02 | exceptional-bar disposition §3.3 — `DIAGNOSIS_UNAVAILABLE` rather than assumed `DATA_GAP` |
| F-04 | kickoff R-25 — bounded terminal walk; `trading_calendar`'s own `max_back_days` convention |
| F-06, F-07, F-08, F-09 | contract §12 composed-pipeline boundary; PR-MS0 §12 PR-MS1.1 item 3 |
| F-10 | contract §6.1 — closed V1 rule set; no lookback other than 20 or 50 |
| F-11 | contract §4 — a malformed DTO shall not produce `OPERATIONAL_FAILURE` |
| F-13 | contract §5.3 undated lookup forbidden; MS-I6 dated-dependency validity |
| F-14 | contract §9 — any semantic canonical-input change produces a different ID |
| F-19, F-24 | contract §12 — exact-boundary fixtures for every rule comparison; transform-group property tests |
| F-20 | contract §7 — earlier barriers are never bridged |
| F-21 | PR-MS0 §12 PR-MS1.1 item 3 — executable MS-I6 test |
| F-22 | kickoff R-28 — SQL boundary must be demonstrated, not string-matched |
| F-23 | contract §4 — exception containment; scenario 12 |
| F-25 | contract §9 — relative-deadband formula and value |
| F-26 | code hygiene; no contract question |
| F-30 | contract §9 snapshot canonical-input consistency + G-5 Option A — lifecycle basis identity must describe the same `as_of`-scoped basis actually used to filter/build the panel; lifecycle read SHOULD be folded into the same governed read snapshot/connection where feasible |

**F-29 is not listed here.** Its semantics are decided under G-6.

Recorded as deferred or operational in review report §9.7, not as remediation items: F-17 (connection count observation; G-2/D removes the separate `corporate_actions` read, and F-30 remediation may further consolidate lifecycle/panel reads; exact post-remediation count is implementation-dependent and not asserted here), F-18 (`decision_available_at` ordering unenforced — REPOSITORY GAP, no `close_timestamp` source exists), F-27 (no batch assembly API; N/A must be declared), F-28 (Python 3.12.13 versus the 3.13 project standard), F-32 (per-date DuckDB connection inside `is_trading_day`; outside the four-file scope, and it becomes HIGH if a universe-scale batch API is implemented).

**Operational risk (out of PR-MS1.1 scope).** `write_adjusted_to_db` does not provide an explicit transaction spanning the `daily_price_adj` and `adjustment_state` rewrites. A crash between statements can therefore leave the materialised panel and freshness state inconsistent. This is an adjustment-pipeline robustness concern and SHALL NOT be represented as remediated by PR-MS1.1.

---

## 9. Session Handoff

### Session Summary

A branch-level adversarial review of `feature/pr-ms1-1-market-state-classifier` at `2da9d9c` returned `CHANGES_REQUIRED`. After the remediation dispositions were locked and landed, the feature branch was rebased onto governance base `3815307`, producing content-equivalent feature HEAD `7b6b125`. The four reviewed implementation/test files retained their reviewed byte content across that rebase. This v0.2.1 amendment updates the commit-level review anchors and narrows G-1 routing by explicitly assigning `as_of < listed_from` to the operational-stage `AS_OF_ELIGIBILITY_NOT_ESTABLISHED` diagnostic while preserving `NATURAL_HISTORY_SHORTFALL` for a validly listed `as_of` whose backward history walk crosses `listed_from`.

### Decision Record

- No locked PR-MS1.0 or PR-MS0 decision is reopened except where this document explicitly records a scoped supersession needed to close a discovered gap.
- PR-MS1.1 remediation implementation is authorised only within the locked handoff boundaries recorded in §§2–7. No scope expansion is authorised.
- G-1: Option B — add `AS_OF_ELIGIBILITY_NOT_ESTABLISHED`; it owns insufficient eligibility evidence, governed-calendar rejection, and `as_of < listed_from`. The last case terminates before DTO construction; F-31 remains a separate calendar-authority PR.
- G-2: Option D — applied adjustment provenance is replay-equivalent identity over governed materialised `cum_factor` values.
- G-3: Option A — negative volume is ratified as invalid observation data in the existing invalid-bar treatment class.
- G-4: superseded by G-2/D — remove direct `corporate_actions` assembly dependency; reference-source set remains unchanged.
- G-5: Option A — Variant B future-effective reference mutations SHALL leave `panel_snapshot_id` unchanged.
- G-6: Option A — absent lifecycle evidence yields `DIAGNOSIS_UNAVAILABLE`; full-universe lifecycle coverage becomes a separate governed remediation programme.
- F-02/F-04 share a mechanical `_terminal_bars` boundary, but G-6 forbids using the row minimum as a proxy listing date.
- G-1 × G-6 reachability: for securities without governed lifecycle coverage, an absent `as_of` row routes to the new eligibility-undetermined diagnostic; `AS_OF_BAR_MISSING` remains reachable only where lifecycle/session eligibility is affirmatively established.
- F-30 is not dissolved by G-2: lifecycle basis loading and panel filtering must be made observation-consistent under contract §9/G-5, preferably by sharing one governed read snapshot/connection where feasible.

### Open Questions

1. Scope/name/priority of the separate F-31 calendar-authority degradation PR.
2. Scope/name/priority of the full-universe `security_lifecycle` remediation programme opened by G-6.

### Evidence

All findings cited here are `VERIFIED_FINDING` class from the review report unless labelled otherwise. The `adjustment_state` schema/writer capability limits added after the initial review have now been independently re-verified and are recorded as `VERIFIED REPOSITORY FINDING`. The same re-verification confirmed the absence of an explicit function-level transaction in `write_adjusted_to_db`; this is recorded only as an out-of-scope adjustment-pipeline robustness risk. Source-level repository evidence was originally observed against feature baseline `2da9d9c` and governance base `3f060ab`; after governance landing and rebase, the corresponding commit-level anchors are feature HEAD `7b6b125` and governance base `3815307`, with the four reviewed implementation/test files byte-identical across the rebase. This is not production validation, historical replay verification, or a performance measurement. No latency, incidence, or coverage figure appears in this document, because none was measured during the review.

### Next Actions

```text
1.  backfill this lock commit SHA as Lock Reference
2.  land the locked governance chain on main
3.  refresh origin/main and verify governance ancestry
4.  rebase feature/pr-ms1-1-market-state-classifier onto the new origin/main
5.  record the new post-rebase feature HEAD and new base
6.  re-establish entry evidence
7.  Commit 1 — assembly correctness and provenance
8.  Commit 2 — classifier identity
9.  Commit 3 — acceptance contract
10. full verification (ruff, mypy, targeted pytest, full pytest, diff --check)
11. branch-level adversarial re-review at the new HEAD
12. register OPEN-1 = F-31 calendar-authority degradation as separate governed work
13. register OPEN-2 = full-universe security_lifecycle remediation programme
```

Step 5 is not optional. Once governance advances `origin/main`, the feature branch's merge base no longer equals `origin/main`, and the kickoff's §2.2 gate will fail and correctly yield `BLOCKED` for the next reviewer. The rebase and re-verification must precede Commit 1.
