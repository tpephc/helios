# `win_rate_21d` Producer Build Readiness — Executable Governance Navigation

**Status:** OPERATIONAL AID (not a governance lock)
**Version:** v0.1.1 (revision of v0.1.0 draft; incorporates review feedback dated 2026-07-05)
**Owner:** Veronica
**Repository:** Helios (`~/projects/helios`)
**Position in Gate A2:** Phase transition artifact between Producer Governance and Implementation

**Derived from:**

- `docs/features/win_rate_21d_spec.md` v0.1.0 (SPEC_LOCKED, md5 `3701f2c2a739ca93aa2f1c963d53a63a`)
- `docs/research/win_rate_21d_a2_sd_locks.md` (LOCKED for SD-A2-1..5, SD-A2-8; md5 `f75b2d70f69933e8c36963d3e704d0a4` at draft time)
- `docs/research/win_rate_21d_a2_governance.md` v0.1.0 (LOCKED, md5 `44238c19bd326a14be40e1ff5b6ac306`)

**Non-binding methodology reference:** `docs/research/ud_ratio_21d_r1_pre_execution_audit.md` (methodology only; no requirements inherited unless independently restated in `win_rate_21d` governance).

**Regeneration:** if any source SD is amended, this document must be regenerated. Canonical source of truth is the SD locks themselves; this document is navigational only.

**Review dimensions:** Coverage, Traceability, Navigability.

**Revision v0.1.1 changes vs v0.1.0:**

- Section 2 module column abstracted to implementation roles, not file paths (R1).
- All private function references removed (R2).
- H10 explicitly retained as derived invariant, not upgraded to governance check (R3).
- Section 4 new preamble (4.0) establishing execution boundary and clarifying ledger-append is not itself a pre-flight (R4).
- Section 5.2 producer manifest language changed from "same object" to explicit "current implementation assumption under P2 refined" (R5).
- Section 6 RE-OPENED state removed; regeneration semantics clarified as per-§5.5, not a rider re-open (R6).
- Section 7 hazards categorized into 5 groups (R7); H1..H22 numbering preserved.
- Section 2 Status column split into Implementation × Verification (R8).

---

## 0. Governance Transition Map

```
                        SPEC_LOCKED (v0.1.0)
                                │
                                ▼
                    Producer Governance
              (SD-A2-1..5, SD-A2-8 LOCKED)
                                │
                                ▼
             Executable Governance                     ← current phase
             (this document + implementation)
                                │
                                ▼
                     Implementation
                (producer builder + consumer
                 feature function + fixture
                 writer + manifest emitter)
                                │
                                ▼
                     Producer Build
                (single pipeline, dual branch)
             ┌──────────────┴──────────────┐
             │                             │
             ▼                             ▼
      Branch 1 (DuckDB)             Branch 2 (Parquet)
      PF-B1..PF-B6 pre-flight       PF-L1..PF-L19 pre-flight
             │                             │
             └──────────────┬──────────────┘
                            ▼
                    Rider closure condition:
             (all PF-B PASS) ∧ (all PF-L PASS)
                    ∧ ledger append succeeded
                            │
                            ▼
                  SD-A2-1 Rider CLOSED
                            │
                            ▼
                  Consumer Governance
              (SD-A2-9, SD-A2-10 to LOCK)
                            │
                            ▼
                  Consumer Implementation
                (add_win_rate_21d function)
                            │
                            ▼
                  Gate A2 COMPLETE
              (SD-A2-6, SD-A2-7, SD-A2-11 also LOCKED)
```

**Legend (one-line each):**

- **Phase transition** happens when a governance artifact reaches its terminal LOCKED state and no further locks block downstream execution.
- **Rider closure** is the single most important event; it is the first empirical proof that the accumulated producer-side governance can be implemented and executed successfully.
- **Single pipeline, dual branch** means one build invocation materializes both artifacts (DuckDB producer table + Parquet fixture) with both pre-flight sets and the ledger append gating the same rider closure. Sequencing (S-A / S-B / S-C) is deferred to implementation; partial canonical state is forbidden regardless.
- **Consumer Governance** unlocks after producer rider closure. SD-A2-9 (I4 tolerance) and SD-A2-10 (producer-consumer interface) do not block rider closure.

---

## 1. Governance Contract Inventory

### 1.1 Spec-derived clauses (`win_rate_21d_spec.md` v0.1.0)

| Anchor | Clause | Normative level | Applies to |
|---|---|---|---|
| §3.2 | Eligible universe `U_s`: stocks in `listed_market_daily_price_adj` at `s` with valid `r_{j,s}` | MUST | Producer |
| §3.3 | Median definition (arithmetic midpoint for even N) | MUST | Producer |
| §3.3 | `m_s` null iff `\|U_s\| < MIN_CROSS_SECTION_OBS_PER_DATE` | MUST | Producer |
| §3.4 | Strict inequality `r_{i,s} > m_s` for win indicator | MUST | Consumer |
| §3.4 | Tie days (`r == m`) counted in denominator, not credited as wins | MUST | Consumer |
| §3.5 | Trailing window includes signal date `t` (inclusive) | MUST | Consumer |
| §3.5 | `win_rate_21d` defined iff `\|S_{i,t}\| >= MIN_OBS` | MUST | Consumer |
| §3.6 | `WINDOW = 21` (locked) | MUST | Both |
| §3.6 | `MIN_OBS = 15` (locked) | MUST | Consumer |
| §3.7 | Post-hoc adjustment of `MIN_CROSS_SECTION_OBS_PER_DATE` after coverage inspection FORBIDDEN | MUST NOT | Producer |
| §4.1 | Trading calendar source: `market.trading_calendar >= 0.2.0`, trading-day count only | MUST | Both |
| §4.2 | Daily return: `r_{i,s} = adj_close_{i,s} / adj_close_{i,s-1} - 1` | MUST | Consumer |
| §4.3 | Validity predicate: all 5 conditions on `adj_close` | MUST | Consumer |
| §4.4 | PIT universe invariant: source is `listed_market_daily_price_adj` (VIEW); direct `daily_price_adj` FORBIDDEN | MUST NOT | Both (P0 lineage violation on breach) |
| §4.5 | Two-layer lineage: producer (Layer 1) + consumer (Layer 2) | MUST | Architecture |
| §4.6 | Lookahead safety: only data `<= t close` used; output available at `t+1 open` | MUST | Both |
| §4.7 | Producer carries `source_snapshot_id` traceable to upstream snapshot | MUST | Producer |
| §4.7 | Any upstream restatement triggers producer rebuild with new snapshot id | MUST | Producer |
| §5.1 | Producer is materialized BASE TABLE (not VIEW), in Helios DuckDB workspace | MUST | Producer |
| §5.3 | Minimum columns: `date`, `median_daily_return`, `n_obs_cross_section`, `source_snapshot_id` | MUST | Producer |
| §5.4 | Byte-identical output on identical inputs (determinism) | MUST | Producer |
| §5.4 | No implicit dependency on wall-clock, host, OS locale, non-deterministic library behavior | MUST NOT | Producer |
| §5.5 | Rebuild required on upstream restatement / lifecycle change / calendar version / threshold lock | MUST | Producer |
| §5.5 | Silent stale-read after regeneration trigger = P0 lineage violation | MUST NOT | Consumer |
| §5.6 | Producer forbidden imports (raw `daily_price_adj`, legacy calendars, other features, R8 builder) | MUST NOT | Producer |
| §5.7 | Consumer MUST NOT recompute median locally | MUST NOT | Consumer |
| §5.7 | Consumer MUST NOT cache median unless cache invalidation matches §5.5 | MUST NOT | Consumer |
| §5.7 | Consumer MUST NOT filter producer universe further | MUST NOT | Consumer |
| §6.1 | Consumer panel columns: `win_rate_21d`, `n_obs_21d`, `n_wins_21d` appended to `(stock_id, date)` | MUST | Consumer |
| §6.2 I1 | `0 <= n_wins_21d <= n_obs_21d <= WINDOW` | MUST | Consumer |
| §6.2 I2 | `win_rate_21d in [0, 1]` OR null | MUST | Consumer |
| §6.2 I3 | `win_rate_21d` null iff `n_obs_21d < MIN_OBS` | MUST | Consumer |
| §6.2 I4 | `win_rate_21d == n_wins_21d / n_obs_21d` within tolerance (value → SD-A2-9) | MUST | Consumer |
| §6.3 | Imputation (forward/backfill/zero/median) FORBIDDEN at feature layer | MUST NOT | Consumer |
| §6.4 | Panel row `date` IS the window-end; no separate `window_end` column | MUST | Consumer |
| §8.4 | String-level SQL checks for source-table verification FORBIDDEN (structural inspection required) | MUST NOT | Tests |
| §8.4 | Parity tests against `ud_ratio_21d` outputs NOT APPLICABLE | MUST NOT | Tests |
| §9.3 | Layer distinction (L1 / L2) is normative; L2 change requires spec amendment | MUST | Governance |

**Spec clause count:** ~38 discrete clauses.

### 1.2 SD-derived clauses

#### SD-A2-1 (MIN_CROSS_SECTION_OBS_PER_DATE)

- Constant value locked at 30.
- Optimization from coverage inspection FORBIDDEN.
- Revision before first producer build requires governance review.
- Revision after first producer build requires spec amendment.
- Conditional rider: closure mechanism = PF-B1 (see SD-A2-3).

#### SD-A2-2 (Producer identity)

- Table name: `win_rate_21d_cross_section_median` (BASE TABLE per spec §5.1).
- Storage: `data/_storage/helios.duckdb` (Helios canonical research workspace).
- Date range: R8/R1-relevant range extended backward by W−1 = 20 trading days (pre-signal trailing-window buffer, independent of calendar-day buffer K deferred to SD-A2-6).
- Materialized min/max dates determined at build time from requested scope and available `listed_market_daily_price_adj` coverage; recorded in manifest.
- Conditional rider closure: PF-B1 must confirm no material scope broadening/shrinkage.

#### SD-A2-3 (Build orchestration)

- Build strategy: one-shot full rebuild per invocation. Incremental append out of scope for A2.
- Pre-flight checks PF-B1 through PF-B6 (PF-B5 deferred to SD-A2-6):
  - **PF-B1** requested-vs-materialized scope validation (rider-closure gate for DuckDB branch).
  - **PF-B2** canonical source only (reads only from `listed_market_daily_price_adj`; `daily_price_adj` FORBIDDEN).
  - **PF-B3** MIN_CROSS_SECTION_OBS_PER_DATE = 30 constant consistency (code-vs-ledger).
  - **PF-B4** WINDOW = 21, MIN_OBS = 15 constant consistency (code-vs-spec).
  - **PF-B5** (deferred to SD-A2-6): trading-calendar version check.
  - **PF-B6** DuckDB target writeability (writable file, no lock contention on target table).
- Any pre-flight failure aborts build with no side effects.
- Build failures after pre-flight pass use atomic DuckDB transaction semantics (all-or-nothing).
- Manifest emission failure = build failure; producer table replacement rolls back or does not commit if manifest emission fails.
- Silent failure FORBIDDEN; non-zero exit and caller-visible exception required.
- Idempotency: identical inputs + governance constants + upstream snapshot ⇒ byte-identical producer rows (non-deterministic build metadata excluded).
- Manifest schema deferred to SD-A2-5.

#### SD-A2-4 (Fixture strategy)

- Two fixture classes: synthetic (12 tests), anchored-real (5 tests).
- Synthetic tests: PIT-PROD-1, PIT-PROD-3, PIT-PROD-4, PIT-CONS-1..8, PIT-INT-1.
- Anchored-real tests: PIT-PROD-2, PIT-PROD-5, PIT-PROD-6, PIT-INT-2, PIT-INT-3.
- Common invariants: determinism (bit-exact reproducibility), PIT correctness (no lookahead/fill), anti-peek discipline (no real R8/R1 coverage inspection for parameter selection), source independence (test semantics do not depend on fixture class).
- Synthetic fixture principles: fully synthetic price series, synthetic ordered trading-date labels, boundary exercise required (MIN_OBS=15 boundary, MIN_CROSS_SECTION=30 boundary, strict-inequality ties, trailing-window inclusion of `t`, no-lookahead poisoning).
- Anchored-real principles: time-anchored selection (anchor at SD-A2-4 lock stage), no coverage-driven selection, used exclusively for the 5 assigned tests.
- Feature-specific fixture logic from `ud_ratio_21d` MUST NOT be reused as `win_rate_21d` fixture backbone.
- Expected values: prefer explicit in-test literal assertions over on-disk golden files.

#### SD-A2-5 (Snapshot lineage / manifest)

- Identity layer: `(snapshot_id, content_hash)` ordered pair, one-to-one, immutable.
- `snapshot_id` format: `{feature}_{ISO8601_utc}_{content_hash_prefix12}`.
- `content_hash` = SHA-256 of `data.parquet` bytes.
- Hash policy: SHA-256 canonical identity; xxhash/BLAKE3 permitted for non-governance purposes only.
- Parquet writer governance-fixed invariants (compression=zstd, coerce_timestamps=us, allow_truncated_timestamps=false, use_dictionary=true, no wall-clock metadata, alphabetical column sort before write, explicit dtypes).
- Parquet writer recorded-not-fixed (compression_level, row_group_size, data_page_version, library version).
- Writer library version = recorded (for exact rebuild) NOT normative identity component.
- Manifest topology: side-car `manifest.json` per snapshot + append-only master ledger at `docs/research/fixtures/anchored_real_ledger.md`.
- Chain hash: md5 for ledger append-order verification; SHA-256 for content identity.
- Atomic write sequence steps 1-7 (data.tmp → hash → manifest.tmp → hash → rename data → rename manifest → append ledger).
- Failure handling: steps 1-4 = cleanup only; steps 5-6 = remove partial renames; step 7 = retry with backoff OR rename to `<snapshot_id>.orphaned/` and emit P0 governance event.
- Canonical discoverability: master ledger is source of truth; filesystem walks FORBIDDEN for governed consumers.
- Storage path: `data/fixtures/anchored_real/win_rate_21d/<snapshot_id>/{data.parquet, manifest.json}`.
- Immutability: detection (recompute content_hash and compare, HARD FAIL on mismatch) + policy (no overwrite/rename/delete without governance amendment); `chmod 444` opportunistic.
- Determinism: canonical sort by row sort keys before write, no unordered iteration, random seed recorded, no clock reads in data-affecting logic, explicit dtypes.
- Environment canonicalization: `LC_ALL=C.UTF-8`, `TZ=UTC`, `PYTHONHASHSEED=0` at process entry.
- Manifest schema v1.0.0 fields (19 fields).
- Pre-flight checks PF-L1 through PF-L19 (see Section 4.2 verbatim).
- SD-A2-8 interlock: retired at SD-A2-8 LOCK (now inactive).
- Non-canonical artifact reference prohibition: pre-SD-A2-8-LOCK artifacts MUST NOT be referenced by any governance document.

#### SD-A2-8 (Dtype finalization)

- Producer table dtypes (§5.3): `date=Date`, `median_daily_return=Float64 nullable`, `n_obs_cross_section=UInt16`, `source_snapshot_id=Utf8`.
- Consumer panel appended dtypes (§6.1): `win_rate_21d=Float64 nullable`, `n_obs_21d=UInt8`, `n_wins_21d=UInt8`.
- `stock_id` INHERITED from upstream panel schema; SD-A2-8 does not lock.
- Cross-table `date` dtype = same canonical logical type (`Date` / `date32[day]`).
- Column ordering:
  - Producer table: alphabetical over all columns.
  - Consumer panel: identity keys (`stock_id, date`) preserve upstream order; appended feature columns alphabetical.
- Row sort ordering:
  - Producer table: `date` ascending (single-column PK).
  - Consumer panel: `(stock_id, date)` ascending.
- Null policy: Arrow validity bitmap only; NaN in nullable Float64 = producer invariant violation; full-scan check in pre-flight.
- Zero-row canonical semantics: `row_count = 0` is canonical if all schema/manifest/dtype invariants hold.
- Clerical reconciliation: `symbol_id` → `stock_id`.
- SD-A2-9 downstream interlock: I4 tolerance deferred; consumer I4 verification deferred until SD-A2-9 LOCK; does NOT gate rider closure.

**SD clause count:** ~85 discrete clauses.

### 1.3 A2 governance note principles (`win_rate_21d_a2_governance.md`)

- **A2-GOV-1**: Distinction between spec Acceptance Criteria (§7.2) and Required Decisions (spec-deferred clauses). Acceptance Criteria change requires spec amendment; Required Decisions documented via SDs.
- **A2-GOV-2**: Section-conflict precedence rule (Case 1 CONFLICT / Case 2 COMPLEMENTARY / Case 3 REDUNDANT).
- **A2-GOV-3**: Editorial remarks about SPEC_LOCKED artifacts go in separate governance notes, not inside SPEC_LOCKED text.
- **A2-GOV-4**: New Required Decisions may be added only when spec explicitly defers to A2.

**Total inventory:** ~127 discrete governance clauses (38 spec + 85 SD + 4 governance principles).

Breakdown by normative level (best-effort classification):

- MUST / SHALL: ~80
- MUST NOT / FORBIDDEN: ~20
- SHOULD / MAY: ~15
- Cross-cutting principles (governance): ~4
- Interlocks (retired or active): ~8

---

## 2. Traceability Matrix (canonical)

### 2.1 Module decomposition caveat (Section 2 preamble)

> The module decomposition presented here uses **abstract implementation roles**, not concrete file paths or class/function names. Implementations MAY choose different module boundaries and any naming provided that complete traceability from every governance clause to a concrete implementation surface, verification path, and produced artifact is preserved. Any divergence SHALL update this document accordingly.
>
> "Module" columns in this matrix are NOT governance contracts. They are navigational hints for locating "where this clause is implemented" during code review. What is under governance is COVERAGE — that every clause has at least one implementing role and at least one verification path.

**Abstract roles used in this matrix:**

- `Producer Builder` — code that produces the DuckDB producer table (SD-A2-2 / SD-A2-3 domain).
- `Consumer Feature Function` — code that appends `win_rate_21d`, `n_obs_21d`, `n_wins_21d` columns to the panel (spec §6.1).
- `Fixture Writer` — code that materializes the Parquet fixture and computes `content_hash`.
- `Manifest Emitter` — code that assembles and writes `manifest.json`.
- `Ledger Writer` — code that appends entries to the master ledger with chain-hash discipline.
- `Environment Canonicalizer` — code that sets `LC_ALL`, `TZ`, `PYTHONHASHSEED` at process entry.
- `Pre-flight Validator` — code that executes PF-B and PF-L checks.
- `Test Suite` — test files organizing PIT tests and fixtures.
- `Configuration` — locked constants and settings.
- `Governance discipline` — clauses enforced by human code review only (no automated check possible in the surface).

### 2.2 Verification channels used in this matrix

Each row's `Verification` column lists ALL verification channels expected for that clause. A row is "fully verified" when all listed channels have passed.

Channel types:

- `PF-B#` / `PF-L#` — a specific pre-flight check.
- `PIT-*` — a specific PIT test.
- `TEST-*` — a non-PIT test (e.g., fixture-determinism regression test).
- `AUDIT` — required code review; no automated check possible.
- `DERIVED` — invariant derived from other clauses; no direct check but implicit through other channels.

### 2.3 Status columns

Two columns replace the single Status column from v0.1.0:

**Implementation** (linear lifecycle):

- `NOT_STARTED` — no code written for this clause.
- `IN_PROGRESS` — partial implementation exists.
- `IMPLEMENTED` — implementation complete per row's Module column.

**Verification** (set-valued; multiple tags allowed):

- `NOT_RUN` — no verification channel has been executed.
- `PF_PASS` — all PF-# checks in the Verification column have passed.
- `PIT_PASS` — all PIT tests in the Verification column have passed.
- `AUDIT_PASS` — required code review complete and passed.

A row can hold multiple tags simultaneously (e.g., `PF_PASS + PIT_PASS + AUDIT_PASS`). A row is "fully verified" when the union of its Verification tags covers all channels listed in its Verification column.

Initial draft state: all rows `Implementation = NOT_STARTED`, `Verification = NOT_RUN`.

### 2.4 Traceability rows

Row IDs (`TM-###`) are stable references for review.

| Row | Clause | Module (abstract role) | Verification channel | Artifact | Impl | Verif |
|---|---|---|---|---|---|---|
| TM-001 | Spec §3.2 eligible universe | Producer Builder | PIT-PROD-2 | producer table rows | NOT_STARTED | NOT_RUN |
| TM-002 | Spec §3.3 median definition (arithmetic midpoint even N) | Producer Builder | PIT-PROD-3 | `median_daily_return` column | NOT_STARTED | NOT_RUN |
| TM-003 | Spec §3.3 `m_s` null iff `\|U_s\| < 30` | Producer Builder | PIT-PROD-4 | `median_daily_return` null values | NOT_STARTED | NOT_RUN |
| TM-004 | Spec §3.4 strict inequality `>` for win | Consumer Feature Function | PIT-CONS-3 | `n_wins_21d` column | NOT_STARTED | NOT_RUN |
| TM-005 | Spec §3.4 tie in denominator, not credited | Consumer Feature Function | PIT-CONS-3 | `n_obs_21d` includes ties, `n_wins_21d` excludes | NOT_STARTED | NOT_RUN |
| TM-006 | Spec §3.5 trailing window inclusive of `t` | Consumer Feature Function | PIT-CONS-1 | window construction | NOT_STARTED | NOT_RUN |
| TM-007 | Spec §3.5 `win_rate_21d` defined iff `\|S_{i,t}\| >= MIN_OBS` | Consumer Feature Function | PIT-CONS-4 | `win_rate_21d` null gate | NOT_STARTED | NOT_RUN |
| TM-008 | Spec §3.6 WINDOW=21 | Configuration | PF-B4 | `WINDOW` constant | NOT_STARTED | NOT_RUN |
| TM-009 | Spec §3.6 MIN_OBS=15 | Configuration | PF-B4 | `MIN_OBS` constant | NOT_STARTED | NOT_RUN |
| TM-010 | Spec §3.7 no post-hoc adjustment of MIN_CROSS_SECTION_OBS_PER_DATE | Configuration | PF-B3 + AUDIT | `MIN_CROSS_SECTION_OBS_PER_DATE = 30` constant | NOT_STARTED | NOT_RUN |
| TM-011 | Spec §4.1 trading calendar via `market.trading_calendar >= 0.2.0` | Consumer Feature Function + Configuration | PIT-CONS-7 + AUDIT (version pin) | ValueError on non-trading-day | NOT_STARTED | NOT_RUN |
| TM-012 | Spec §4.2 daily return formula | Consumer Feature Function | PIT-CONS-2 | daily return intermediate | NOT_STARTED | NOT_RUN |
| TM-013 | Spec §4.3 validity predicate (5 conditions) | Consumer Feature Function | PIT-CONS-2 | validity intermediate | NOT_STARTED | NOT_RUN |
| TM-014 | Spec §4.4 PIT universe: `listed_market_daily_price_adj` only | Producer Builder + Consumer Feature Function | PF-B2 + PIT-PROD-6 + PIT-INT-1 | AST/structural inspection | NOT_STARTED | NOT_RUN |
| TM-015 | Spec §4.5 two-layer lineage architecture | Governance discipline | AUDIT | module structure | NOT_STARTED | NOT_RUN |
| TM-016 | Spec §4.6 no data past `t close` used | Consumer Feature Function | PIT-CONS-6 (poisoning test) | output at `t` unchanged by `t+1` data | NOT_STARTED | NOT_RUN |
| TM-017 | Spec §4.7 `source_snapshot_id` traceable | Producer Builder + Manifest Emitter | PIT-PROD-5 + PF-L18 | manifest `input_snapshots[]` | NOT_STARTED | NOT_RUN |
| TM-018 | Spec §4.7 upstream restatement triggers rebuild | Governance discipline (deferred to SD-A2-11) | AUDIT (interim) | (deferred artifact) | NOT_STARTED | NOT_RUN |
| TM-019 | Spec §5.1 producer is BASE TABLE (not VIEW) | Producer Builder | PF-B6 + AUDIT | DuckDB catalog | NOT_STARTED | NOT_RUN |
| TM-020 | Spec §5.3 producer columns present | Producer Builder | PF-B6 (schema present) + AUDIT | producer table schema | NOT_STARTED | NOT_RUN |
| TM-021 | Spec §5.4 determinism: byte-identical output | Producer Builder + Environment Canonicalizer | PIT-PROD-1 | producer table bytes | NOT_STARTED | NOT_RUN |
| TM-022 | Spec §5.4 no wall-clock / host / locale / non-deterministic library dependency in data | Producer Builder + Environment Canonicalizer | PIT-PROD-1 + PF-L11..L13 | canonicalized env | NOT_STARTED | NOT_RUN |
| TM-023 | Spec §5.5 rebuild on regeneration triggers 1-4 | Governance discipline (deferred to SD-A2-11) | (deferred verification) | (deferred artifact) | NOT_STARTED | NOT_RUN |
| TM-024 | Spec §5.5 silent stale-read = P0 lineage violation | Consumer Feature Function | PIT-INT-2 | RuntimeError on mismatch | NOT_STARTED | NOT_RUN |
| TM-025 | Spec §5.6 producer forbidden imports | Producer Builder | PIT-PROD-6 + AUDIT | source code imports | NOT_STARTED | NOT_RUN |
| TM-026 | Spec §5.7 consumer does not recompute median | Consumer Feature Function | PIT-INT-1 + AUDIT | consumer source code | NOT_STARTED | NOT_RUN |
| TM-027 | Spec §5.7 consumer does not cache median without invalidation | Consumer Feature Function | AUDIT | consumer source code | NOT_STARTED | NOT_RUN |
| TM-028 | Spec §5.7 consumer does not filter producer universe further | Consumer Feature Function | AUDIT | consumer join semantics | NOT_STARTED | NOT_RUN |
| TM-029 | Spec §6.1 consumer panel columns present | Consumer Feature Function | PIT-CONS-5 (schema slice) | consumer output columns | NOT_STARTED | NOT_RUN |
| TM-030 | Spec §6.2 I1 range | Consumer Feature Function | PIT-CONS-5 (I1) | output validation raises on violation | NOT_STARTED | NOT_RUN |
| TM-031 | Spec §6.2 I2 range or null | Consumer Feature Function | PIT-CONS-5 (I2) | output validation raises on violation | NOT_STARTED | NOT_RUN |
| TM-032 | Spec §6.2 I3 null coupling | Consumer Feature Function | PIT-CONS-4 + PIT-CONS-5 (I3) | output validation raises on violation | NOT_STARTED | NOT_RUN |
| TM-033 | Spec §6.2 I4 arithmetic self-consistency (tolerance → SD-A2-9) | Consumer Feature Function | PIT-CONS-5 (I4, activated at SD-A2-9 LOCK) | output validation raises on violation | NOT_STARTED | NOT_RUN |
| TM-034 | Spec §6.3 no imputation | Consumer Feature Function | PIT-CONS-8 + AUDIT | consumer output null preservation | NOT_STARTED | NOT_RUN |
| TM-035 | Spec §6.4 panel `date` = window-end (no `window_end` column) | Consumer Feature Function | AUDIT | consumer output columns | NOT_STARTED | NOT_RUN |
| TM-036 | Spec §8.4 forbidden test patterns | Test Suite | AUDIT | test code | NOT_STARTED | NOT_RUN |
| TM-037 | Spec §9.3 L2 universe change requires spec amendment | Governance discipline | AUDIT (interpretation) | (no artifact) | NOT_STARTED | NOT_RUN |
| TM-038 | SD-A2-1 MIN_CROSS_SECTION_OBS_PER_DATE=30 (constant) | Configuration | PF-B3 + PF-L14 | constant value | NOT_STARTED | NOT_RUN |
| TM-039 | SD-A2-2 table name `win_rate_21d_cross_section_median` | Configuration | PF-L7 (matches SD-A2-2 identity) | DuckDB table name | NOT_STARTED | NOT_RUN |
| TM-040 | SD-A2-2 storage `data/_storage/helios.duckdb` | Configuration | PF-B6 (writeability) | DuckDB path | NOT_STARTED | NOT_RUN |
| TM-041 | SD-A2-2 producer scope = R8/R1 range + 20 trading days backward | Producer Builder | PF-B1 (rider-closure gate) | requested scope in manifest | NOT_STARTED | NOT_RUN |
| TM-042 | SD-A2-3 one-shot full rebuild | Producer Builder | AUDIT | build strategy | NOT_STARTED | NOT_RUN |
| TM-043 | SD-A2-3 PF-B1 scope validation | Pre-flight Validator | PF-B1 (self) | requested vs materialized in manifest | NOT_STARTED | NOT_RUN |
| TM-044 | SD-A2-3 PF-B2 canonical source only | Pre-flight Validator | PF-B2 (self) + PIT-PROD-6 | source code AST | NOT_STARTED | NOT_RUN |
| TM-045 | SD-A2-3 PF-B3 MIN_CROSS_SECTION consistency | Pre-flight Validator | PF-B3 (self) | code-vs-ledger consistency | NOT_STARTED | NOT_RUN |
| TM-046 | SD-A2-3 PF-B4 WINDOW=21 / MIN_OBS=15 consistency | Pre-flight Validator | PF-B4 (self) | code-vs-spec consistency | NOT_STARTED | NOT_RUN |
| TM-047 | SD-A2-3 PF-B6 DuckDB writeability | Pre-flight Validator | PF-B6 (self) | DuckDB file writable, table free | NOT_STARTED | NOT_RUN |
| TM-048 | SD-A2-3 pre-flight failure = no side effects | Producer Builder + Pre-flight Validator | AUDIT | build behavior on failure | NOT_STARTED | NOT_RUN |
| TM-049 | SD-A2-3 atomic DuckDB replacement | Producer Builder | AUDIT | DuckDB transaction behavior | NOT_STARTED | NOT_RUN |
| TM-050 | SD-A2-3 manifest emission failure = build failure | Producer Builder + Manifest Emitter | AUDIT | build coupling | NOT_STARTED | NOT_RUN |
| TM-051 | SD-A2-3 silent failure FORBIDDEN | Producer Builder | AUDIT | error propagation | NOT_STARTED | NOT_RUN |
| TM-052 | SD-A2-3 idempotency: byte-identical rows | Producer Builder + Environment Canonicalizer | PIT-PROD-1 | producer table bytes | NOT_STARTED | NOT_RUN |
| TM-053 | SD-A2-4 17 PIT tests implemented | Test Suite | (test collection) | test files | NOT_STARTED | NOT_RUN |
| TM-054 | SD-A2-4 synthetic fixture: 12 tests | Test Suite | AUDIT | fixture files | NOT_STARTED | NOT_RUN |
| TM-055 | SD-A2-4 anchored-real fixture: 5 tests | Test Suite | AUDIT | fixture references | NOT_STARTED | NOT_RUN |
| TM-056 | SD-A2-4 fixture determinism | Test Suite | TEST-fixture-determinism | fixture regeneration | NOT_STARTED | NOT_RUN |
| TM-057 | SD-A2-4 no lookahead / fill in fixtures | Test Suite | AUDIT | fixture content | NOT_STARTED | NOT_RUN |
| TM-058 | SD-A2-4 anti-peek discipline for fixture params | Governance discipline | AUDIT | fixture design decisions | NOT_STARTED | NOT_RUN |
| TM-059 | SD-A2-4 no reuse of ud_ratio_21d fixture logic | Test Suite | AUDIT | fixture source | NOT_STARTED | NOT_RUN |
| TM-060 | SD-A2-5 snapshot_id format | Fixture Writer + Manifest Emitter | PF-L3 | snapshot_id string | NOT_STARTED | NOT_RUN |
| TM-061 | SD-A2-5 content_hash = SHA-256 of file bytes | Fixture Writer | PF-L4 + PF-L5 | manifest `content_hash` | NOT_STARTED | NOT_RUN |
| TM-062 | SD-A2-5 (snapshot_id, content_hash) binding one-to-one | Manifest Emitter + Fixture Writer | PF-L6 | binding record in manifest | NOT_STARTED | NOT_RUN |
| TM-063 | SD-A2-5 Parquet writer governance-fixed invariants | Fixture Writer + Configuration | PF-L15 | manifest `parquet_writer_config.governance_fixed` | NOT_STARTED | NOT_RUN |
| TM-064 | SD-A2-5 Parquet writer recorded-not-fixed fields | Fixture Writer + Manifest Emitter | PF-L16 | manifest `parquet_writer_config.recorded` | NOT_STARTED | NOT_RUN |
| TM-065 | SD-A2-5 side-car manifest + master ledger topology | Manifest Emitter + Ledger Writer | PF-L19 | ledger file + sidecar file | NOT_STARTED | NOT_RUN |
| TM-066 | SD-A2-5 md5 chain hash for ledger, SHA-256 for content | Ledger Writer + Fixture Writer | PF-L19 | ledger `prev_entry_chain_hash` | NOT_STARTED | NOT_RUN |
| TM-067 | SD-A2-5 atomic write sequence (7 steps) | Fixture Writer + Manifest Emitter + Ledger Writer | AUDIT | build behavior | NOT_STARTED | NOT_RUN |
| TM-068 | SD-A2-5 step 7 failure → retry OR orphan | Fixture Writer + Ledger Writer | AUDIT | orphan directory naming | NOT_STARTED | NOT_RUN |
| TM-069 | SD-A2-5 canonical discoverability: ledger authoritative | Consumer Feature Function + Ledger Writer | AUDIT | consumer read code | NOT_STARTED | NOT_RUN |
| TM-070 | SD-A2-5 storage path convention | Fixture Writer + Configuration | PF-L19 (ledger entry has path) | filesystem path | NOT_STARTED | NOT_RUN |
| TM-071 | SD-A2-5 immutability: detection via content_hash recompute | Consumer Feature Function + Fixture Writer | AUDIT | consumer read behavior | NOT_STARTED | NOT_RUN |
| TM-072 | SD-A2-5 immutability: policy (no overwrite/rename/delete) | Governance discipline | AUDIT | (no code enforcement) | NOT_STARTED | NOT_RUN |
| TM-073 | SD-A2-5 canonical row sort applied before write | Producer Builder | PIT-PROD-1 (via hash reproduction) | sort behavior | NOT_STARTED | NOT_RUN |
| TM-074 | SD-A2-5 no unordered iteration in output construction | Governance discipline | AUDIT | source code review | NOT_STARTED | NOT_RUN |
| TM-075 | SD-A2-5 random_seed recorded in manifest | Manifest Emitter | AUDIT (field presence) | manifest field | NOT_STARTED | NOT_RUN |
| TM-076 | SD-A2-5 no clock reads affecting data content | Governance discipline | AUDIT | source code review | NOT_STARTED | NOT_RUN |
| TM-077 | SD-A2-5 environment canonicalization | Environment Canonicalizer | PF-L11 + PF-L12 + PF-L13 | env vars at process entry | NOT_STARTED | NOT_RUN |
| TM-078 | SD-A2-5 manifest schema v1.0.0 fields | Manifest Emitter | PF-L1 + PF-L2 | manifest.json | NOT_STARTED | NOT_RUN |
| TM-079 | SD-A2-5 producer_identity fields | Manifest Emitter | PF-L7 + PF-L8 + PF-L9 | manifest `producer_identity` | NOT_STARTED | NOT_RUN |
| TM-080 | SD-A2-5 input_snapshots consistency with row-level source_snapshot_id | Producer Builder + Manifest Emitter | DERIVED (implementation-derived invariant; see Section 7 H10) | manifest ∧ column values | NOT_STARTED | NOT_RUN |
| TM-081 | SD-A2-8 producer dtype `date` = Date | Producer Builder | PF-L17 | producer table schema | NOT_STARTED | NOT_RUN |
| TM-082 | SD-A2-8 producer dtype `median_daily_return` = Float64 nullable | Producer Builder | PF-L17 | producer table schema | NOT_STARTED | NOT_RUN |
| TM-083 | SD-A2-8 producer dtype `n_obs_cross_section` = UInt16 | Producer Builder | PF-L17 | producer table schema | NOT_STARTED | NOT_RUN |
| TM-084 | SD-A2-8 producer dtype `source_snapshot_id` = Utf8 | Producer Builder | PF-L17 | producer table schema | NOT_STARTED | NOT_RUN |
| TM-085 | SD-A2-8 consumer dtype `win_rate_21d` = Float64 nullable | Consumer Feature Function | PIT-CONS-5 | consumer output schema | NOT_STARTED | NOT_RUN |
| TM-086 | SD-A2-8 consumer dtype `n_obs_21d` = UInt8 | Consumer Feature Function | PIT-CONS-5 | consumer output schema | NOT_STARTED | NOT_RUN |
| TM-087 | SD-A2-8 consumer dtype `n_wins_21d` = UInt8 | Consumer Feature Function | PIT-CONS-5 | consumer output schema | NOT_STARTED | NOT_RUN |
| TM-088 | SD-A2-8 `stock_id` INHERITED | Consumer Feature Function | AUDIT | consumer schema handling | NOT_STARTED | NOT_RUN |
| TM-089 | SD-A2-8 cross-table `date` = same logical type | Producer Builder + Consumer Feature Function | AUDIT | schema compatibility | NOT_STARTED | NOT_RUN |
| TM-090 | SD-A2-8 producer column ordering: alphabetical | Producer Builder | PIT-PROD-1 (via hash) | producer table column order | NOT_STARTED | NOT_RUN |
| TM-091 | SD-A2-8 consumer column ordering: identity keys + appended alphabetical | Consumer Feature Function | AUDIT | consumer output column order | NOT_STARTED | NOT_RUN |
| TM-092 | SD-A2-8 producer row sort: date ascending | Producer Builder | PIT-PROD-1 (via hash) | row order | NOT_STARTED | NOT_RUN |
| TM-093 | SD-A2-8 consumer row sort: (stock_id, date) ascending | Consumer Feature Function | AUDIT | row order | NOT_STARTED | NOT_RUN |
| TM-094 | SD-A2-8 null representation: Arrow validity bitmap only | Producer Builder + Consumer Feature Function | AUDIT | null encoding | NOT_STARTED | NOT_RUN |
| TM-095 | SD-A2-8 NaN in nullable Float64 = producer invariant violation | Pre-flight Validator (full-scan) | AUDIT (implementation of NaN scan) | RuntimeError on NaN presence | NOT_STARTED | NOT_RUN |
| TM-096 | SD-A2-8 zero-row canonical semantics | Producer Builder + Fixture Writer | AUDIT | zero-row test | NOT_STARTED | NOT_RUN |
| TM-097 | SD-A2-8 `stock_id` name (not `symbol_id`) | Governance discipline | AUDIT | code + manifest content | NOT_STARTED | NOT_RUN |
| TM-098 | A2-GOV-1 Acceptance Criteria vs Required Decisions distinction | Governance discipline | AUDIT | (governance) | NOT_STARTED | NOT_RUN |
| TM-099 | A2-GOV-2 section-conflict precedence (Case 1/2/3) | Governance discipline | AUDIT | (governance) | NOT_STARTED | NOT_RUN |
| TM-100 | A2-GOV-3 editorial remarks placement | Governance discipline | AUDIT | (governance) | NOT_STARTED | NOT_RUN |
| TM-101 | A2-GOV-4 Required Decisions amendment rule | Governance discipline | AUDIT | (governance) | NOT_STARTED | NOT_RUN |

**Total rows in matrix:** 101.

**Coverage sanity check (per Section 1 count):** ~127 governance clauses, 101 traceability rows. Delta accounted for by:

- Some governance clauses (e.g., SD-A2-5 sub-clauses inside atomic write sequence) covered by a single TM row.
- Some clauses are non-code (e.g., regeneration policy, deferrals) and mapped to AUDIT-only or deferred artifacts.
- Section 7 drift hazards catalog residual clauses that need attention but are not module-mappable.

Any TM row whose Verification column contains only `AUDIT` should be considered a **higher-drift-risk clause** because it depends on human review discipline, not automated verification. These rows warrant special attention during code review before rider closure.

---

## 3. Implementation Cross-reference (derived from Section 2)

Grouped by abstract role; each row lists the TM row IDs whose clauses that role implements. Since this view is derived, a discrepancy between Section 2 and Section 3 IS a document integrity failure (regenerate this section from Section 2 as needed).

### Producer Builder

TM-001, TM-002, TM-003, TM-014, TM-017, TM-019, TM-020, TM-021, TM-022, TM-025, TM-041, TM-042, TM-048, TM-049, TM-050, TM-051, TM-052, TM-073, TM-080, TM-081, TM-082, TM-083, TM-084, TM-089, TM-090, TM-092, TM-094, TM-096.

### Consumer Feature Function

TM-004, TM-005, TM-006, TM-007, TM-011, TM-012, TM-013, TM-014 (also here — cross-cutting), TM-016, TM-024, TM-026, TM-027, TM-028, TM-029, TM-030, TM-031, TM-032, TM-033, TM-034, TM-035, TM-069, TM-071, TM-085, TM-086, TM-087, TM-088, TM-089 (also), TM-091, TM-093, TM-094 (also).

### Fixture Writer

TM-060, TM-061, TM-062, TM-063, TM-064, TM-066, TM-067, TM-068, TM-070, TM-071 (also), TM-096 (also).

### Manifest Emitter

TM-017 (also), TM-060 (also), TM-062 (also), TM-064 (also), TM-065, TM-067 (also), TM-075, TM-078, TM-079, TM-080 (also).

### Ledger Writer

TM-065 (also), TM-066 (also), TM-067 (also), TM-068 (also), TM-069 (also).

### Environment Canonicalizer

TM-021 (also), TM-022 (also), TM-052 (also), TM-077.

### Pre-flight Validator

TM-043, TM-044, TM-045, TM-046, TM-047, TM-095.

### Test Suite

TM-036, TM-053, TM-054, TM-055, TM-056, TM-057, TM-059.

### Configuration

TM-008, TM-009, TM-010, TM-011 (also), TM-038, TM-039, TM-040, TM-063 (also), TM-070 (also).

### Governance discipline (AUDIT-only)

TM-015, TM-018, TM-023, TM-037, TM-058, TM-072, TM-074, TM-076, TM-097, TM-098, TM-099, TM-100, TM-101.

---

## 4. Pre-flight Verification Enumeration

### 4.0 Execution boundary (added in v0.1.1)

The following timeline defines when each check set runs and where the canonical commit event lies. Implementation MUST preserve this ordering:

```
Stage 1 — Producer build starts.
Stage 2 — PF-B checks execute BEFORE any DuckDB mutation.
              If any PF-B fails: build aborts; no side effects; existing table
              and manifest preserved.
Stage 3 — DuckDB producer table materialized (atomic transaction).
              Table written but NOT YET consumer-visible under P2 refined
              (per Decision A partial-state prohibition).
Stage 4 — Fixture materialization: data.parquet.tmp and manifest.json.tmp
              written to staging paths per SD-A2-5 N-A2-5-3 steps 1-4.
Stage 5 — PF-L checks execute AFTER fixture temp files exist, BEFORE ledger
              append.
              If any PF-L fails: fixture temp files removed or orphaned per
              SD-A2-5 N-A2-5-3; no ledger append; DuckDB table (Stage 3)
              MUST be marked non-canonical or rolled back per Decision A.
Stage 6 — Atomic renames of data.parquet and manifest.json to final paths
              (SD-A2-5 N-A2-5-3 steps 5-6).
Stage 7 — Ledger append (SD-A2-5 N-A2-5-3 step 7). This is the CANONICAL
              COMMIT EVENT.
Stage 8 — Rider closure evaluation (see Section 6).
```

**Key clarifications:**

- **PF-B and PF-L are pre-flight (validation) checks.** They execute before their respective canonical-commit points and gate whether the pipeline proceeds.
- **Ledger append is NOT itself a pre-flight check.** It is the canonical commit event whose failure semantics (retry with backoff OR orphan) are defined in SD-A2-5 N-A2-5-3 step 7. Do not conflate "ledger append succeeded" with "a pre-flight check passed"; they are semantically different events.
- **Sequencing between Stage 3 and Stages 4-7** (S-A / S-B / S-C) is implementation-phase. The partial-state prohibition (Decision A refined) applies regardless of chosen sequencing.

### 4.1 Branch 1 — DuckDB producer table (PF-B1..PF-B6)

Source: SD-A2-3 pre-flight enumeration. All execute at Stage 2.

| ID | Name | Verifies | Failure semantics |
|---|---|---|---|
| PF-B1 | Requested-vs-materialized scope validation | Materialized scope from `listed_market_daily_price_adj` does not materially broaden/shrink requested scope. Both ranges recorded in manifest. | Failure = build abort; SD-A2-1 rider stays ACTIVE; governance review required before retry if failure indicates material scope discrepancy. |
| PF-B2 | Canonical source validation | Producer code reads only from `listed_market_daily_price_adj`. Direct reads of `daily_price_adj` FORBIDDEN. Code-vs-spec structural check (AST-level). | Failure = build abort. Governance review required (code-vs-spec inconsistency). |
| PF-B3 | MIN_CROSS_SECTION_OBS_PER_DATE constant consistency | Producer code uses value 30 (per SD-A2-1). Code-vs-ledger. | Failure = build abort. Governance review required (code-vs-ledger inconsistency). |
| PF-B4 | WINDOW / MIN_OBS constant consistency | Producer code uses WINDOW=21, MIN_OBS=15 (per spec §3.6). | Failure = build abort. Governance review required. |
| PF-B5 | (DEFERRED to SD-A2-6) | Trading-calendar version check. | Not implementable until SD-A2-6 LOCK. |
| PF-B6 | DuckDB target writeability | Target DuckDB file writable, target table name not locked by another process. Does not perform trial writes. | Failure = build abort. Standard retry semantics. |

### 4.2 Branch 2 — Parquet anchored-real fixture (PF-L1..PF-L19)

Source: SD-A2-5 N-A2-5-7. Verbatim reproduction. All execute at Stage 5.

| # | Field | Source | Check |
|---|---|---|---|
| PF-L1 | `manifest_format` | manifest | equals `"json"` |
| PF-L2 | `manifest_schema_version` | manifest | equals `"1.0.0"` |
| PF-L3 | `snapshot_id` | manifest | regex `^win_rate_21d_\d{8}T\d{6}Z_[0-9a-f]{12}$` |
| PF-L4 | `content_hash` | manifest | 64 lowercase hex characters |
| PF-L5 | `content_hash_recomputed` | data.parquet bytes | SHA-256 of file equals manifest `content_hash` |
| PF-L6 | `snapshot_id_prefix_binding` | derived | `content_hash[:12]` equals `snapshot_id` last 12 chars |
| PF-L7 | `producer_identity.producer_id` | manifest | matches SD-A2-2 locked identity |
| PF-L8 | `producer_identity.producer_code_sha` | manifest | equals `git rev-parse HEAD`; clean tree required |
| PF-L9 | `producer_identity.repository_clean` | manifest | equals `true` |
| PF-L10 | `producer_version` | manifest | valid semver string |
| PF-L11 | `producer_environment.canonicalized.LC_ALL` | manifest | equals `"C.UTF-8"` |
| PF-L12 | `producer_environment.canonicalized.TZ` | manifest | equals `"UTC"` |
| PF-L13 | `producer_environment.canonicalized.PYTHONHASHSEED` | manifest | equals `"0"` |
| PF-L14 | `min_cross_section_obs_per_date` | manifest | equals 30 (SD-A2-1) |
| PF-L15 | `parquet_writer_config.governance_fixed` | manifest | every field equals SD-A2-5 locked value |
| PF-L16 | `parquet_writer_config.recorded` | manifest | present; specific values not checked against fixed reference |
| PF-L17 | `column_dtypes` | manifest ∧ data | manifest values equal actual Parquet schema |
| PF-L18 | `input_snapshots[*].content_hash` | manifest ∧ upstream ledger | each upstream `content_hash` resolvable in a prior ledger entry |
| PF-L19 | `master_ledger_entry` | master ledger | new entry appended with correct `prev_entry_chain_hash` md5 |

**Additional invariants surfaced during readiness draft (derived, not governance):**

- **NaN scan** (per SD-A2-8 N-A2-8-5): for every nullable Float64 column in the fixture (`median_daily_return`), full scan MUST yield zero NaN. Producer invariant violation on failure. Section 7 H7.
- **Row-level `source_snapshot_id` ∧ manifest `input_snapshots[*]` consistency** (per Decision B): row `source_snapshot_id` set MUST match manifest `input_snapshots[*].snapshot_id` set. Section 7 H10. NOT proposed as a new PF-L check.

### 4.3 Rider closure conjunction rule

```
Rider closes ⇔ (PF-B1 ∧ PF-B2 ∧ PF-B3 ∧ PF-B4 ∧ PF-B6) ∧ (PF-L1 ∧ ... ∧ PF-L19)
                     ↑                                       ↑
                     PF-B5 deferred to SD-A2-6              full set
                 ∧ Stage 7 ledger append succeeded
                     ↑
                     canonical commit event (not a pre-flight)
```

**Partial canonical state prohibition (Decision A refined):**

> No branch output becomes canonical until BOTH branches pass their respective pre-flight checks AND the lineage ledger append is complete. Partial success is not rider-closable and MUST NOT be consumer-visible.

Implementation implication: producer build MUST have a definition of "consumer-visible" that is gated on ledger append completion. Consumers MUST use the ledger as the discovery mechanism (per SD-A2-5 N-A2-5-3 "filesystem existence ≠ canonical existence"). See Section 7 H4.

### 4.4 Failure recovery paths

**Branch 1 (DuckDB) failure modes:**

- Pre-flight failure (PF-B1..PF-B6): no side effects on existing table.
- Build failure after pre-flight pass: atomic DuckDB transaction rollback; existing table preserved.
- Manifest emission failure: producer table replacement rolls back OR does not commit.

**Branch 2 (Parquet) failure modes (per SD-A2-5 N-A2-5-3):**

- Steps 1–4 (temp files, hashes): remove temp files; no canonical state created.
- Steps 5–6 (atomic renames): remove partially renamed files; no canonical state.
- Step 7 (ledger append): retry with bounded backoff OR rename directory to `<snapshot_id>.orphaned/` and emit P0 governance event.

**Cross-branch failure interaction (per Decision A refined):**

- If Branch 1 succeeds and Branch 2 fails, DuckDB table state MUST be marked non-canonical (manifest not emitted, OR emitted with explicit failure flag, OR table rolled back — implementation choice). Consumers MUST NOT see the table as ready until the pair passes AND ledger append succeeded.
- If Branch 2 succeeds and Branch 1 fails, Parquet fixture should not have been materialized under sequencing that runs Branch 1 first. If it was materialized under out-of-order sequencing, rename to orphan directory.
- Recovery from any partial state: **do not resume from partial**; discard partial artifacts and re-run full pipeline.

---

## 5. Expected Artifact Inventory

### 5.1 DuckDB producer table

- **Path:** `data/_storage/helios.duckdb`
- **Table name:** `win_rate_21d_cross_section_median`
- **Schema (locked by SD-A2-8 N-A2-8-1):**

  | Column | Polars dtype | Nullable | Range / meaning |
  |---|---|---|---|
  | `date` | `Date` | No | Trading day (single-column PK) |
  | `median_daily_return` | `Float64` | Yes (Arrow bitmap) | `m_s` per spec §3.3; null iff `\|U_s\| < 30` |
  | `n_obs_cross_section` | `UInt16` | No | `\|U_s\|` count |
  | `source_snapshot_id` | `Utf8` | No | FK to upstream `listed_market_daily_price_adj` snapshot; constant per fixture (Decision B) |

- **Column order:** alphabetical (`date, median_daily_return, n_obs_cross_section, source_snapshot_id`).
- **Row sort:** `date` ascending.
- **Materialization:** BASE TABLE (per spec §5.1); atomic DuckDB transaction (SD-A2-3).

### 5.2 Producer build manifest

**Governance status.** SD-A2-3 defers producer manifest schema to SD-A2-5. SD-A2-5 scope statement addresses anchored-real fixtures. Under P2 refined interpretation of the two-branch pipeline:

> **Current implementation assumption (under P2 refined):** the producer build emits a single manifest shared by the DuckDB producer output and the anchored-real fixture. This assumption is derived from SD-A2-3 (which defers producer manifest schema to SD-A2-5) and SD-A2-5 (which specifies manifest for fixture); neither SD explicitly states the two manifests are the same object.
>
> If future governance (e.g., SD-A2-10, or an amendment to SD-A2-3/SD-A2-5) separates the two artifacts' manifest schemas, this section must be regenerated.

Under the current assumption:

- **Format:** JSON (per SD-A2-5 N-A2-5-3).
- **Schema:** as SD-A2-5 N-A2-5-6 v1.0.0 (19 required fields).
- **Storage:** side-car with the fixture (see 5.4).

### 5.3 Parquet fixture data file

- **Path:** `data/fixtures/anchored_real/win_rate_21d/<snapshot_id>/data.parquet`
- **Schema:** matches producer table schema (P2 refined: fixture is reproducibility projection of producer table).
- **Column order:** alphabetical (same as 5.1).
- **Row sort:** `date` ascending (same as 5.1).
- **Parquet writer governance-fixed:** compression=zstd, coerce_timestamps=us, allow_truncated_timestamps=false, use_dictionary=true, no wall-clock metadata, alphabetical column sort applied, explicit dtypes.
- **Parquet writer recorded-not-fixed:** compression_level, row_group_size, data_page_version, library version (recorded in manifest).

### 5.4 Fixture manifest.json

- **Path:** `data/fixtures/anchored_real/win_rate_21d/<snapshot_id>/manifest.json`
- **Schema (v1.0.0 per SD-A2-5 N-A2-5-6):** 19 required fields:

  ```
  manifest_format, manifest_schema_version, producer_version,
  snapshot_id, content_hash, content_hash_algorithm, feature,
  producer_identity {producer_id, producer_code_sha, producer_config_hash,
                     repository_clean},
  producer_environment {python_version, os_platform, arrow_library_version,
                        polars_version, canonicalized {LC_ALL, TZ,
                                                       PYTHONHASHSEED}},
  build_utc_timestamp, build_host,
  input_snapshots [{role, snapshot_id, content_hash}],
  row_count, column_names, column_dtypes,
  min_cross_section_obs_per_date,
  parquet_writer_config {governance_fixed, recorded},
  random_seed
  ```

- **`column_names` value (post-SD-A2-8 reconciliation):** `["date", "median_daily_return", "n_obs_cross_section", "source_snapshot_id"]` — producer table schema per Decision B. SD-A2-5 example showing `symbol_id / win_rate_21d` is placeholder drift; see Section 7 H2.
- **`column_dtypes` value:** `{"date": "date32[day]", "median_daily_return": "float64", "n_obs_cross_section": "uint16", "source_snapshot_id": "string"}` (Polars/Arrow canonical strings).
- **`input_snapshots[*].snapshot_id` set:** expected size 1 (single upstream `listed_market_daily_price_adj` snapshot per governed build, per Decision B).
- **`row_count`:** exact row count of `data.parquet`.

### 5.5 Master ledger entry

- **Path:** `docs/research/fixtures/anchored_real_ledger.md` (append-only).
- **Per-entry fields (SD-A2-5 N-A2-5-3):**

  ```
  snapshot_id
  content_hash                   (SHA-256)
  manifest_hash                  (SHA-256 of manifest.json bytes)
  prev_entry_chain_hash          (md5 of previous entry's canonical form)
  commit_sha_at_build            (git rev-parse HEAD at successful build)
  ```

- **Chain hash:** md5 (append-order verification; matches SD-lock ledger discipline).

---

## 6. Rider Closure Detection

### 6.1 Rider state observables

Governance defines two states for the SD-A2-1 conditional rider:

- **ACTIVE** — no producer build has yet materialized both branches passing pre-flight, and no ledger append has succeeded.
- **CLOSED** — at least one producer build has materialized both branches passing pre-flight; ledger append succeeded.

**Note on regeneration.** Subsequent producer rebuilds after regeneration triggers (spec §5.5) follow the normal producer lifecycle governed by §5.5. The SD-A2-1 rider itself is not reintroduced; the rider is a one-time closure event at first successful build. Rebuild governance is per §5.5, not per SD-A2-1. No third rider state exists.

### 6.2 Programmatic detection

The following queries define observability. Implementation MAY combine them:

1. **Ledger has a valid `win_rate_21d`-prefixed entry** whose associated snapshot manifest passes PF-L1..PF-L19 verification (recomputed content_hash matches, all fields present, chain hash matches).
2. **DuckDB producer table `win_rate_21d_cross_section_median` exists** with row count > 0 (or = 0 accepted if that is the semantic result per zero-row canonical semantics) AND its schema matches N-A2-8-1.
3. **Producer manifest** (side-car under 5.4) exists and its `input_snapshots` references upstream (`listed_market_daily_price_adj`) at a resolvable snapshot.
4. **PF-B logs** (implementation-derived): pre-flight audit trail records PF-B1..PF-B4, PF-B6 all PASS.
5. **Cross-consistency** (Section 7 H10): row-level `source_snapshot_id` set matches manifest `input_snapshots[*].snapshot_id` set.

If (1)..(5) all evaluate TRUE for some build, the rider is CLOSED.

### 6.3 Post-closure invariants

- SD-A2-1 rider is CLOSED (no further pre-first-build governance review requirement).
- Any subsequent change to `MIN_CROSS_SECTION_OBS_PER_DATE` requires spec amendment (per SD-A2-1 revision rule).
- The producer table becomes consumer-visible; consumer builds (SD-A2-9, SD-A2-10 domain) may now proceed once those SDs are LOCKED.
- Regeneration triggers (spec §5.5) become the mechanism for producer re-build; each re-build creates a new snapshot_id and appends a new ledger entry.

---

## 7. Known Drift Hazards

Each hazard identifies a governance clause or interaction that is easy to miss during implementation. Numbered for stable review reference. Hazards are non-normative; they exist to flag risk, not to add contract. Categorized in v0.1.1 for review efficiency; numbering H1..H22 preserved.

### 7.1 Governance & discipline hazards

#### H1 — Pre-flight nomenclature collision (V1)

SD-A2-3 uses `V1` as check identifier #1 (scope validation). SD-A2-5 pre-flight checks were sometimes informally called "V1 pre-flight" during governance discussion. The readiness document uses `PF-B1..PF-B6` and `PF-L1..PF-L19` to disambiguate. Implementation code and log messages MUST use these tags, not "V1".

#### H2 — SD-A2-5 manifest example schema drift

SD-A2-5 N-A2-5-6 example manifest shows `column_names: ["date", "symbol_id", "win_rate_21d"]`. This is a pre-SD-A2-8 placeholder that does not match the P2 refined interpretation (fixture snapshots producer table, not consumer panel). Correct values are given in Section 5.4. Implementation MUST use producer-table column names in `column_names`, not the placeholder.

#### H3 — DuckDB producer table vs Parquet anchored-real fixture: distinct artifact classes

The producer build materializes TWO artifact classes in ONE pipeline invocation:

- Class A: DuckDB base table (governed by SD-A2-2, SD-A2-3).
- Class B: Parquet fixture with side-car manifest and master ledger entry (governed by SD-A2-4, SD-A2-5, SD-A2-8).

They share content (Class B is a reproducible projection of Class A per Decision B) but are distinct storage artifacts. Rider closure requires BOTH. Consumer read paths for the two use different interfaces (DuckDB SQL vs Parquet + manifest). Do not conflate.

#### H4 — Branch sequencing S-A / S-B / S-C deferred

Three possible sequencings for materializing Branches 1 and 2 (S-A: Branch 1 first, S-B: Branch 2 first, S-C: simultaneous 2-phase-commit). Sequencing choice is implementation-phase; the invariant is that no branch output becomes canonical until BOTH branches pass AND ledger append succeeded. Partial canonical state is forbidden regardless of sequencing. Implementation MUST include a mechanism to ensure consumers cannot observe half-completed state.

#### H8 — `stock_id` name (not `symbol_id`) everywhere

Spec §6.1 authoritative name is `stock_id`. SD-A2-5 N-A2-5-5 used `symbol_id` (clerical error, reconciled in SD-A2-8 N-A2-8-8). All producer code, consumer code, manifest fields, log messages, and comments MUST use `stock_id`. Grep for `symbol_id` in the codebase should return zero results in `win_rate_21d`-related files.

#### H9 — Repository cleanliness at build time (PF-L9)

Producer manifest field `producer_identity.repository_clean` MUST be `true` at build time, which requires:

- Working tree clean (no uncommitted changes).
- Index clean (no staged changes).
- No untracked files that could affect the build (implementation may relax this to "no untracked Python files under the producer/consumer implementation paths").

Common failure mode: a governance commit is prepared but not yet made; developer tries a build to verify; PF-L9 fails.

#### H22 — SD-A2-2 conditional rider on scope validation

SD-A2-2 says its own conditional-rider element (scope broadening/shrinkage) is validated at build time via PF-B1. If materialized scope differs materially from requested, PF-B1 fails AND this must be recorded in the manifest with governance-review requirement. Implementation implication: manifest emission on PF-B1 failure is a soft-emission (record for review) distinct from successful build manifest.

### 7.2 Determinism hazards

#### H5 — Environment canonicalization

`LC_ALL=C.UTF-8`, `TZ=UTC`, `PYTHONHASHSEED=0` MUST be set at process entry (per SD-A2-5 N-A2-5-5) BEFORE any producer code runs. If not set, PF-L11..PF-L13 will fail on manifest read even if the producer output happens to be deterministic — the manifest values would not match the required values.

Common failure mode: development environment happens to have the right locale by accident; CI or production environment does not. Recommend early `assert` guards in the entry point.

#### H6 — `content_hash` is file bytes, not logical data

`content_hash` is SHA-256 of `data.parquet` raw bytes, NOT a hash of logical data (i.e., not `hash(df.to_records())`). This means:

- Parquet writer library version affects `content_hash` (recorded in manifest per SD-A2-5 N-A2-5-2).
- Same logical data written by two different library versions yields two different `content_hash` values.
- Rebuild with recorded writer configuration + library version MUST reproduce identical bytes (the invariant that makes the pipeline reproducible).

Implementation implication: pyarrow version pin in `pyproject.toml`; if it changes, treat as regeneration trigger.

#### H7 — NaN forbidden as null; full-scan check

Nullable Float64 columns (`median_daily_return`, `win_rate_21d`) MUST use Arrow validity bitmap for nulls. NaN in these columns is a producer invariant violation, detected by full-scan in pre-flight. Common failure mode: some numeric library operation returns NaN silently (e.g., `0/0`, `log(-x)`, `sqrt(-x)`), and it propagates to output.

### 7.3 Lineage & consumer coupling hazards

#### H10 — Row-level `source_snapshot_id` ∧ manifest `input_snapshots[*]` consistency

Per Decision B, `source_snapshot_id` column is expected constant per fixture; the row set of `source_snapshot_id` values MUST match the manifest's `input_snapshots[*].snapshot_id` set. This is NOT currently in PF-L1..PF-L19.

This is a **derived implementation invariant**, NOT a new governance check. It is caught by AUDIT and by test coverage of consumer-side lineage verification, not by an added PF-L20. Cataloged in TM-080 with Verification = `DERIVED`.

#### H11 — Silent stale-read after regeneration trigger = P0 lineage violation

Per spec §5.5, if any of (upstream restatement / lifecycle change / calendar version / threshold change) occurs and a consumer reads the stale producer output, that read is a P0 lineage violation. Detection mechanism is DEFERRED to SD-A2-11 (regeneration-trigger detection). Until SD-A2-11 LOCK, consumers rely on manual coordination.

Common failure mode: upstream refresh happens on schedule (e.g., overnight), consumer job runs against stale producer output the following morning before a rebuild triggers. Recommend: interim safeguard = consumer verifies `source_snapshot_id` against upstream `listed_market_daily_price_adj` snapshot at read time (already partly covered by PIT-INT-2).

#### H12 — Consumer MUST NOT recompute median locally

Spec §5.7 explicitly forbids consumer-side median recomputation. Common failure mode during rapid iteration: consumer developer inlines a `df.group_by('date').agg(pl.median(...))` as a quick check; this bypasses the producer and creates silent lineage drift. Structural inspection (PIT-INT-1) catches this if properly implemented.

#### H13 — Consumer MUST NOT cache median without invalidation matching §5.5

If consumer caches median values across queries, cache invalidation policy MUST match spec §5.5 regeneration triggers exactly. Simpler alternative: do not cache at consumer layer; always read from producer table each query. Given TW-scale data size, recomputation cost of a query-time read is small; caching is a premature optimization.

#### H14 — Consumer MUST NOT filter producer universe further

Per spec §5.7, consumer must accept producer's `U_s` as the median's universe. Any consumer-side filter changes the semantic of `m_s`. Common failure mode: consumer wants a "clean universe" subset (e.g., exclude low-volume names); this must be done at prereg / research layer, not at feature-computation layer.

### 7.4 Mathematical hazards

#### H15 — Strict inequality (`>`) for win comparison

Spec §3.4 requires strict `r > m_s`. Common failure mode: developer writes `r >= m_s` "for safety". This inflates win rate on low-volatility days where many stocks tie the median (see spec §10.3 acknowledged research risk). PIT-CONS-3 must specifically test tie cases.

#### H16 — Tie days count in denominator, not credited as wins

Tie cases: `r == m_s` exactly. `win_{i,s} = 0` (not a win), but `s` is in `S_{i,t}` (contributes to denominator). Common failure mode: developer excludes ties from both numerator and denominator ("clean semantics"); this is wrong per §3.4.

#### H20 — Median interpolation for even N: arithmetic midpoint (LOCKED)

Spec §3.3 specifies arithmetic midpoint `(r_{(N/2)} + r_{(N/2 + 1)}) / 2` for even N. NOT lower-median, upper-median, or linear-interpolation variants. `numpy.median` and Polars `.median()` default to this convention, but library changes could shift; document the assumption and pin library versions.

#### H21 — Window inclusive of signal date `t`

Spec §3.5 is explicit: `t - W + 1 <= s <= t` (INCLUSIVE of `t`). Common failure mode: developer writes `s < t` (exclusive) "to avoid lookahead"; this is wrong because §4.6 explicitly permits `r_{i,t}` and `m_t` at `t close`.

### 7.5 Testing hazards

#### H17 — Structural inspection required for source-table verification

Per spec §8.4, PIT-PROD-6 and analogous checks MUST NOT use string-level SQL checks (e.g., substring match on `"FROM daily_price_adj"`). Use DuckDB EXPLAIN plan introspection, SQL AST parsing, or Polars source-attribution inspection. Common failure mode: developer writes a quick regex-based check; it passes but has false negatives (comments, whitespace, quoting).

#### H18 — No numerical parity assertions against `ud_ratio_21d`

Per spec §8.4, `win_rate_21d` and `ud_ratio_21d` have materially different semantics (relative outperformance frequency vs sign-frequency persistence). Asserting numerical parity is a category error. Common failure mode: developer sees both are `[0,1]` bounded and thinks "should be roughly equal on similar days"; this is a mistake.

#### H19 — Producer forbidden imports (spec §5.6)

Producer code MUST NOT import from: `daily_price_adj` (raw), `utils.trading_calendar` (legacy), `utils.trading_dates` (different semantic), `features/regime.py`, `features/bullish_features.py`, `features/bearish_regime.py`, `research/r8_event_builder.py`, `features/ud_ratio.py`. Structural inspection (PIT-PROD-6) verifies. Common failure mode: developer imports a utility from a nearby module thinking it's harmless.

---

## Appendix A — Coverage Matrix (governance × section)

Section presence for each governance source. This appendix is a sanity check that no source is orphaned.

| Source | §0 | §1 | §2 | §3 | §4 | §5 | §6 | §7 |
|---|---|---|---|---|---|---|---|---|
| Spec §3 (mathematical contract) |   | ✓ | ✓ | ✓ | ✓ (via PF) | ✓ (via output) | ✓ | ✓ (H15, H16, H20, H21) |
| Spec §4 (PIT contract) |   | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ (H11) |
| Spec §5 (producer contract) | ✓ | ✓ | ✓ | ✓ | ✓ (Branch 1) | ✓ | ✓ | ✓ (H3, H11, H12–H14, H19) |
| Spec §6 (output schema) |   | ✓ | ✓ | ✓ |   | ✓ | ✓ | ✓ (H15, H16) |
| Spec §7.2 (Gate A2 items) |   | ✓ | (partial) | (partial) |   | (partial) |   |   |
| Spec §8 (test strategy) |   | ✓ | ✓ | ✓ | (via PIT refs) |   |   | ✓ (H17, H18) |
| Spec §9.3 (layer distinction) |   | ✓ | ✓ |   |   |   |   |   |
| SD-A2-1 | ✓ | ✓ | ✓ | ✓ | ✓ (PF-B3, PF-L14) | ✓ | ✓ |   |
| SD-A2-2 | ✓ | ✓ | ✓ | ✓ | ✓ (PF-B1) | ✓ | ✓ | ✓ (H22) |
| SD-A2-3 | ✓ | ✓ | ✓ | ✓ | ✓ (PF-B set) | ✓ | ✓ | ✓ (H3) |
| SD-A2-4 |   | ✓ | ✓ | ✓ | (fixture context) | (fixture context) |   | ✓ (H18) |
| SD-A2-5 | ✓ | ✓ | ✓ | ✓ | ✓ (PF-L set) | ✓ | ✓ | ✓ (H1, H2, H5–H10) |
| SD-A2-8 | ✓ | ✓ | ✓ | ✓ | ✓ (dtype checks in PF-L) | ✓ | ✓ | ✓ (H7, H8) |
| A2 gov note (A2-GOV-1..4) |   | ✓ | ✓ (as AUDIT) |   |   |   |   |   |

**Interpretation:** Every governance source is referenced in Section 1 (inventory) and Section 2 (matrix). Spec §7.2 partial coverage is intentional — §7.2 items are meta-deliverables, most of which are covered by their underlying SDs (e.g., §7.2 #1 → SD-A2-1). A2 governance note principles are meta-governance and mostly AUDIT-only.

---

## Appendix B — Terminology Crosswalk

| Canonical (use this) | Deprecated / historical / alternative | Notes |
|---|---|---|
| `stock_id` | `symbol_id` | SD-A2-8 clerical reconciliation. Grep for `symbol_id` in `win_rate_21d` code should return zero. |
| `snapshot_id` | `fixture_id`, `snapshot_uid` | SD-A2-5 N-A2-5-1 identity layer; format `{feature}_{ISO8601_utc}_{content_hash_prefix12}`. |
| `content_hash` | `data_hash`, `fixture_hash` | SD-A2-5 N-A2-5-2; SHA-256 of `data.parquet` bytes. |
| `source_snapshot_id` | `upstream_snapshot`, `source_id` | Spec §5.3 column; FK to upstream snapshot; constant per fixture (Decision B). |
| `manifest_hash` | `manifest_checksum` | SD-A2-5 N-A2-5-3; SHA-256 of `manifest.json` bytes. |
| `prev_entry_chain_hash` | `chain_hash`, `md5_chain` | SD-A2-5 N-A2-5-3; md5 for ledger append-order verification. |
| Canonical artifact | Transport artifact, working artifact | SD-A2-5 N-A2-5-3: filesystem existence ≠ canonical existence; ledger is source of truth. |
| Producer table | Median table, cross-section table, m_s table | SD-A2-2: `win_rate_21d_cross_section_median` in `data/_storage/helios.duckdb`. |
| Consumer panel | Feature panel, output panel | Spec §6.1: `(stock_id, date)` panel with 3 appended columns. |
| Anchored-real fixture | Real fixture, live-anchored fixture | SD-A2-4; used exclusively for 5 lineage/structural tests. |
| Synthetic fixture | Mock fixture, unit fixture | SD-A2-4; used for 12 numerical/behavioral tests. |
| PF-B1..PF-B6 | V1..V6 (SD-A2-3 wording), build pre-flight | Branch 1 pre-flight per SD-A2-3. |
| PF-L1..PF-L19 | "V1 pre-flight" (informal), N-A2-5-7 checks | Branch 2 pre-flight per SD-A2-5. |
| Rider (SD-A2-1) | Conditional rider, scope-validation rider | Producer-side; closure = both branches pass ∧ ledger append succeeded. |
| Branch 1 | Producer build, DuckDB build | Class A artifact (DuckDB base table). |
| Branch 2 | Fixture materialization, Parquet build | Class B artifact (Parquet + manifest + ledger). |
| Ledger append | Canonical commit event | Not a pre-flight; SD-A2-5 N-A2-5-3 step 7. |
| Executable Governance | (owner's proposed term) | Phase where documented governance meets first executable implementation. |

---

*End of `win_rate_21d_producer_build_readiness.md` v0.1.1.*
