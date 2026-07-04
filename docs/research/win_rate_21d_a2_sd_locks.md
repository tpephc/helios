# Gate A2 Sub-decision Locks — `win_rate_21d`

**Document ID:** `win_rate_21d_a2_sd_locks`
**Version:** v0.1.0
**Status:** OPEN
**Owner:** Veronica
**Repository:** Helios (`~/projects/helios`)
**Created:** 2026-06-30
**Gate:** A2

---

## Scope

This document is an **append-only decision ledger** recording the
locked sub-decisions (SD-A2-1 through SD-A2-11) enumerated in
`docs/research/win_rate_21d_a2_governance.md` §3.2 (LOCKED at
`5913e06`).

Each entry is committed to Git upon lock; commit history serves
as the authoritative timeline. This document does not use
per-entry version bumps — the version remains v0.1.0 throughout
the append cycle. Its `Status` field advances OPEN → COMPLETE
when all eleven sub-decisions have been locked.

Governance role: **decision ledger, not specification**. It
carries no downstream contract that would require version-based
change management; Git commit chain provides immutable history.

The order of entries in this ledger is normative. Sub-decisions
are appended in locking order and must not be reordered
retrospectively.

## Normative status

This document records decisions taken under the governance
interpretation defined in `win_rate_21d_a2_governance.md`. The
decisions themselves are normative for Gate A2 implementation;
the ledger format is administrative.

---

## SD Locks

### SD-A2-1

```
MIN_CROSS_SECTION_OBS_PER_DATE = 30

Type:
    Heuristic defensive floor

Evidence:
    No coverage inspection.
    No density estimation.

Optimization:
    Explicitly prohibited.

Revision:
    Before the first producer build, revision requires
    governance review.
    After the first producer build, revision requires
    spec amendment and regeneration of all affected
    producer artifacts.

Conditional rider:
    Automatically expires once SD-A2-2 is locked
    without materially changing producer coverage.
```

**Status:** LOCKED
**Date:** 2026-06-30
**Signer:** Veronica
**Commit:** `93a8317`

---

### SD-A2-2

```
Producer scope:
    Date range:
        R8/R1-relevant trading-date range, extended backward by
        20 trading days (the pre-signal trailing-window buffer,
        W - 1 where W = 21 per spec §3.6).

        This trailing-window buffer is independent of the
        calendar-day buffer K deferred to SD-A2-6.

        Requested and actual materialized min/max trading dates
        must be determined at build time from the requested scope
        and available `listed_market_daily_price_adj` coverage
        (the canonical producer source per spec §4.4), then
        recorded in the producer build manifest.

    Table name:
        win_rate_21d_cross_section_median
        (BASE TABLE per spec §5.1; no version suffix — version and
        lineage are carried by snapshot_id / build manifest per
        spec §4.7 / §5.5).

    Storage location:
        data/_storage/helios.duckdb
        (Helios canonical research workspace; no feature-specific
        DuckDB file introduced).

Type:
    Producer identity lock. Defines "what is built", not "how it
    is built" (the latter deferred to SD-A2-3 build orchestration).

Evidence:
    No coverage inspection.
    No empirical range tuning.
    Naming and storage aligned with Helios workspace convention.

Revision:
    Before the first producer build, revision requires governance
    review.
    After the first producer build, revision requires spec amendment
    and regeneration of all affected producer artifacts.

Effect on SD-A2-1 conditional rider:
    The conditional rider expires after build-time scope validation
    confirms that the materialized producer scope does not materially
    broaden the assumed R8/R1-relevant research scope. Any material
    shrinkage or expansion observed during that validation must be
    recorded in the build manifest and reviewed before the first
    producer build.
```

**Status:** LOCKED
**Date:** 2026-06-30
**Signer:** Veronica
**Commit:** `50c093e`

---

### SD-A2-3

```
Type:
    Build orchestration lock. Defines "how it is built", not "what
    is built" (the latter locked in SD-A2-2).

Scope:
    Medium orchestration scope, covering:
        - build strategy
        - pre-flight validation
        - failure semantics
        - idempotency implication
        - manifest emission hook
    Excludes (delegated to other SDs):
        - manifest schema / hash algorithm / snapshot lineage fields
          → SD-A2-5
        - calendar-day buffer K / calendar version policy
          → SD-A2-6
        - regeneration-trigger detection mechanism
          → SD-A2-11
        - fixture strategy for tests
          → SD-A2-4

Build strategy:
    One-shot full rebuild of the full requested producer scope on
    each build invocation. Incremental append is explicitly out of
    scope for A2.

    Rationale (recorded for future audit; not empirically tuned):
    the producer computes one cross-sectional median per trading
    day over the requested scope. The expected computational cost
    is sufficiently small that the additional engineering complexity
    of incremental append — state management, coverage-boundary
    handling, duplicate-date guards, and partial-rebuild semantics —
    is not justified. Upstream restatement (spec §5.5) already
    requires full rebuild in principle.

Pre-flight validation:
    All checks below MUST pass before any mutation of the producer
    table. Any pre-flight failure aborts the build with no side
    effects on the existing producer table or manifest.

    V1  Requested-vs-materialized scope validation:
        The materialized producer scope (min/max trading date
        actually available from listed_market_daily_price_adj)
        must not materially broaden or shrink the requested scope
        locked in SD-A2-2. Both requested and materialized ranges
        are recorded in the build manifest. V1 is the canonical
        implementation mechanism for evaluating closure of the
        SD-A2-1 conditional rider.

    V2  Canonical source validation:
        The producer code path reads only from
        listed_market_daily_price_adj (per spec §4.4). Direct
        reads of daily_price_adj are FORBIDDEN. This is a
        code-vs-spec structural check, not a data check.

    V3  MIN_CROSS_SECTION_OBS_PER_DATE constant consistency:
        The threshold used by the producer code path equals 30
        (per SD-A2-1). This is a code-vs-ledger consistency check,
        not a data-driven sanity check on threshold appropriateness
        (which would violate spec §3.7 anti-peek discipline).

    V4  WINDOW and MIN_OBS constant consistency:
        The window length used by the producer code path equals 21
        and the minimum observation count equals 15 (per spec §3.6).
        Same code-vs-spec consistency semantics as V3.

    V6  DuckDB target writeability:
        The target DuckDB file (data/_storage/helios.duckdb) is
        writable and accessible; the target table name is not
        currently held by another process. This check does not
        perform trial writes.

    Deferred:
        V5 (trading calendar version check) is deferred to SD-A2-6
        because calendar mechanism, calendar-day buffer K, and
        calendar version policy are not yet locked. Adding a
        version check here would prematurely constrain SD-A2-6.

Failure semantics:
    Pre-flight failure:
        No mutation of the producer table or manifest occurs.
        Existing valid producer table and manifest are preserved.
        The rider status of SD-A2-1 is not changed by a failed V1
        (rider remains active).
        Governance review is required before retry if the failure
        indicates a material scope discrepancy (V1) or a code-vs-
        ledger inconsistency (V3, V4).

    Build failure after pre-flight pass:
        Build writes MUST use atomic replacement semantics at the
        DuckDB transaction level: either the new producer table
        and manifest replace the existing artifacts entirely, or
        the existing artifacts are preserved untouched. Partial
        producer output MUST NOT be left as a valid table.

    Manifest failure:
        Manifest emission failure is a build failure. The
        producer table replacement MUST be rolled back or MUST
        NOT be committed if manifest emission fails, so that
        the producer table and manifest remain in a consistent
        pair.

    Error propagation:
        Any build failure MUST raise a non-zero process exit and
        a caller-visible exception. Silent failure is FORBIDDEN.

Idempotency implication:
    Repeated full builds over identical inputs, identical governance
    constants (SD-A2-1 threshold; spec §3.6 constants), and the
    identical canonical source snapshot MUST produce byte-identical
    producer rows. The specific content-hash algorithm and the exact
    set of hashed columns are deferred to SD-A2-5. Non-deterministic
    build metadata (e.g., build timestamp, build host) is excluded
    from this bit-identity requirement.

    This restates the orchestration-level implication of the
    deterministic reproducibility contract already locked in
    spec §5.4.

Manifest hook:
    Every successful producer build MUST emit or update a build
    manifest. Manifest emission is part of the atomic replacement
    semantics defined in Failure semantics above: manifest emission
    failure is a build failure. Manifest schema (fields, format,
    storage location) is deferred to SD-A2-5.

Evidence:
    No coverage inspection.
    No empirical build-strategy tuning.
    Orchestration boundaries aligned with governance-note §3.2
    SD delegation.

Revision:
    Before the first producer build, revision requires governance
    review.
    After the first producer build, revision requires spec amendment
    and regeneration of all affected producer artifacts.

Effect on SD-A2-1 conditional rider:
    V1 above is the canonical implementation mechanism for closing
    the SD-A2-1 rider. The rider remains active until the first
    successful producer build passes V1. If V1 fails on the first
    attempt, no mutation occurs, the rider remains active, and
    governance review is required before retry.
```

**Status:** LOCKED
**Date:** 2026-06-30
**Signer:** Veronica
**Commit:** `40c0cd1`

---

### SD-A2-4

```
Type:
    Fixture strategy lock. Defines the two fixture classes used by
    Gate A2 PIT tests, the test-to-class assignment, and the design
    principles binding each class. Does not lock builder API,
    directory layout, or per-test scenario construction (deferred;
    see Exclusions).

Scope:
    Governance of fixture strategy for the 17 PIT tests enumerated
    in spec §8.2. Covers:
        - fixture taxonomy (two classes)
        - test-to-class assignment
        - common invariants binding both classes
        - synthetic fixture design principles
        - anchored-real fixture design principles
        - reuse posture
    Excludes (delegated to other SDs or implementation phase):
        - builder API signature / entry-point identity
          → implementation phase
        - fixture directory layout and file organization
          → implementation phase
        - dtype widths for producer output columns
          → SD-A2-8
        - I4 floating-point tolerance EPS
          → SD-A2-9
        - source_snapshot_id format, manifest schema fields,
          physical storage location for anchored-real fixtures
          → SD-A2-5
        - regeneration-trigger detection mechanism
          → SD-A2-11

Fixture taxonomy:
    Two fixture classes are locked, matching spec §8.3 (high-level):
        - Synthetic fixture (DataFrame-native, no DB dependency)
        - Anchored-real fixture (real-data-anchored, used only for
          structural / lineage coverage)

Test assignment:
    Synthetic fixture applies to 12 tests:
        PIT-PROD-1, PIT-PROD-3, PIT-PROD-4,
        PIT-CONS-1, PIT-CONS-2, PIT-CONS-3, PIT-CONS-4,
        PIT-CONS-5, PIT-CONS-6, PIT-CONS-7, PIT-CONS-8,
        PIT-INT-1

    Anchored-real fixture applies to 5 tests:
        PIT-PROD-2, PIT-PROD-5, PIT-PROD-6,
        PIT-INT-2, PIT-INT-3

    Total = 17 tests, matching the full PIT test enumeration in
    spec §8.2.

    Spec §8.3 explicitly categorizes 15 tests (PIT-PROD-3,
    PIT-PROD-4, PIT-CONS-1..8, PIT-INT-1 as synthetic; PIT-PROD-2,
    PIT-PROD-5, PIT-PROD-6, PIT-INT-2, PIT-INT-3 as anchored-real).
    PIT-PROD-1 is not categorized by §8.3 and requires an A2
    assignment decision, which this sub-decision makes.

    PIT-PROD-1 assignment rationale:
        PIT-PROD-1 (spec §8.2) verifies bit-exact reproducibility
        over a fixed input snapshot per spec §5.4. The core
        requirement is a fixed, deterministic input, not real-data
        lineage.

        Synthetic fixture provides a cleaner idempotency substrate:
        no external snapshot coupling; no anchored-real lineage
        dependency; failure attribution is unambiguous (a
        non-deterministic outcome implicates the producer or write
        path, not snapshot materialization); alignment with the
        deterministic reproducibility contract restated at SD-A2-3
        idempotency implication and spec §5.4.

        PIT-PROD-1 is therefore assigned to the synthetic fixture
        class.

Common invariants:
    Both fixture classes must satisfy:

    Determinism:
        Bit-exact reproducibility over identical input specifications.
        Any generator randomness must be pure and seed-locked in
        fixture code; runtime overrides of seeds or generator
        parameters are FORBIDDEN.

    PIT correctness:
        No lookahead. No forward-fill, backfill, zero-fill, or
        median-fill applied to fixture data. Null observations
        remain null (per spec §6.2 I3 and PIT-CONS-8 semantics).

    Anti-peek discipline:
        No coverage inspection or density estimation on real R8/R1
        data is used to select fixture parameters, thresholds, or
        boundary values. This binds both classes; the concrete
        selection mechanism per class is defined below.

    Source independence:
        Test semantics shall not depend on whether the assigned
        fixture class is synthetic or anchored-real. A fixture
        class exists solely to exercise the intended contract of
        the assigned PIT tests.

Synthetic fixture principles:
    Source:
        Fully synthetic price series. No real R8/R1 data used as
        fixture content.

    Calendar:
        Synthetic ordered trading-date labels. Real TWSE calendar
        is not used as fixture calendar substrate. Calendar-day
        gaps between trading-date labels may be included as labels
        to exercise gap-related semantics, but carry no
        correspondence to real TWSE holidays.

    Shape:
        Fixture design must exercise the following boundary
        conditions across the assigned tests:
            - MIN_OBS = 15 boundary (14 vs 15 valid observations)
              per spec §3.6 and §6.2 I3
            - MIN_CROSS_SECTION_OBS_PER_DATE = 30 per SD-A2-1
              (29 vs 30 vs > 30 cross-section observations)
            - Strict-inequality tie handling per spec §3.4
              (exact r == m_s → win = 0)
            - Trailing-window inclusion of signal date t per §3.5
            - No-lookahead poisoning (poisoned t+1 data must not
              alter output at t) per PIT-CONS-6

        Per-test shape parameters (number of stocks, number of
        trading dates, scenario-to-test mapping) are
        implementation-phase decisions and are not locked here.

    Expected values:
        Prefer explicit in-test literal assertions over on-disk
        golden output files. Committed golden parquet/csv files
        are deferred and permitted only if the implementation
        phase determines explicit literals are unmanageable.

Anchored-real fixture principles:
    Source anchor:
        Selection principle:
            Anchored-real fixture selection is time-anchored rather
            than coverage-driven.

        Anchor point:
            The governed anchor point for Gate A2 is established at
            the SD-A2-4 lock stage, taken over the canonical producer
            source per spec §4.4 (listed_market_daily_price_adj) and
            its underlying dependencies (e.g., security_lifecycle per
            the IF-1 PIT lifecycle filter).

        Rationale:
            Time-anchored selection is non-coverage-driven and
            reproducible by commit / md5 / manifest. Spec-lock commit
            (1cf8365) is not used as anchor because it would require
            historical environment reconstruction of upstream state;
            SD-A2-4 lock time is the natural anchor for A2
            implementation-scope fixtures.

    Selection discipline:
        No stock/date subset may be chosen because it satisfies
        coverage, density, pass/fail convenience, or numerical
        desirability. Anchored-real fixtures are selected only by
        governed snapshot identity and structural source-table
        contract.

    Scope:
        Anchored-real fixtures are used exclusively for the 5
        assigned structural / lineage tests (PIT-PROD-2, PIT-PROD-5,
        PIT-PROD-6, PIT-INT-2, PIT-INT-3). Numerical semantic tests
        do not use anchored-real fixtures.

    Mechanism:
        Concrete snapshot identity, source_snapshot_id
        representation, manifest linkage, and physical storage for
        anchored-real fixtures are deferred to SD-A2-5.

Reuse posture:
    Neutral test utilities may be reused. This includes generic
    helpers such as trading calendar builders, DuckDB temp table
    harnesses, and Polars schema helpers that are not tied to a
    specific feature's semantics.

    Feature-specific fixture logic from ud_ratio_21d must not be
    reused as the win_rate_21d fixture backbone. This includes
    ud_ratio_21d producer helpers and any fixture generator that
    encodes ud_ratio_21d numerical semantics.

    Feature-specific architectural patterns may be referenced, but
    numerical behaviour, expected values, or feature semantics shall
    not be inherited.

    Concrete identification of which existing conftest.py fixtures
    qualify as neutral utilities is an implementation-phase decision.

Evidence:
    No coverage inspection.
    No empirical fixture-parameter tuning.
    Fixture taxonomy aligned with spec §8.3 (high-level);
    PIT-PROD-1 assignment resolves a §8.3 categorization gap under
    A2 authority per governance-note §3.2.

Revision:
    Before the first producer build, revision requires governance
    review.
    After the first producer build, revision requires spec amendment
    and regeneration of all affected producer artifacts.

Effect on SD-A2-1 conditional rider:
    SD-A2-4 is a fixture strategy lock and does not perform,
    validate, or trigger a producer build. The SD-A2-1 conditional
    rider therefore remains ACTIVE. No closure event occurs at
    SD-A2-4 lock.
```

**Status:** LOCKED
**Date:** 2026-07-02
**Signer:** Veronica
**Commit:** `036f0b4`

---

## Anchor References

| Document                                              | Status         | Commit / Anchor |
| ----------------------------------------------------- | -------------- | --------------- |
| `docs/features/win_rate_21d_spec.md`                  | SPEC_LOCKED    | `1cf8365`       |
| `docs/research/win_rate_21d_a2_governance.md`         | LOCKED         | `5913e06`       |
| `docs/research/ud_ratio_21d_r1_prereg.md`             | LOCKED         | `13ed404`       |
| `docs/research/ud_ratio_21d_r1_pre_execution_audit.md`| Gate A1 CLOSED | `89fa08e`       |

Anchor md5 hashes (verified at this ledger's creation):

```
win_rate_21d_spec.md                          3701f2c2a739ca93aa2f1c963d53a63a
win_rate_21d_a2_governance.md                 44238c19bd326a14be40e1ff5b6ac306
ud_ratio_21d_r1_prereg.md                     4fd52fe75c38c6b489ee5311e9f6525b
ud_ratio_21d_r1_pre_execution_audit.md        fafc04b9ee6a5bc9311ea75c884d9ff5
```

Repository HEAD at this ledger's creation: `5913e06`.

---

## Ledger Status

| Sub-decision | Status     |
| ------------ | ---------- |
| SD-A2-1      | LOCKED     |
| SD-A2-2      | LOCKED     |
| SD-A2-3      | LOCKED     |
| SD-A2-4      | LOCKED     |
| SD-A2-5      | NOT_LOCKED |
| SD-A2-6      | NOT_LOCKED |
| SD-A2-7      | NOT_LOCKED |
| SD-A2-8      | NOT_LOCKED |
| SD-A2-9      | NOT_LOCKED |
| SD-A2-10     | NOT_LOCKED |
| SD-A2-11     | NOT_LOCKED |

Document `Status` field advances OPEN → COMPLETE when all
eleven rows show LOCKED.

*End of ledger at SD-A2-4 lock.*
---

## SD-A2-5 — Snapshot lineage and manifest mechanism

**Status:** LOCKED
**Commit:** `23b249b` (backfill post-commit per SD-A2-1..4 pattern)
**Prev SD lock:** SD-A2-4 (commit `036f0b4`)
**Prev ledger tail md5:** `83c101a7c3373931bbd9fd47a5f922c0` (captured 2026-07-02 post-SD-A2-4 apply)
**Ledger version at lock:** `v0.1.0` (append cycle continues)

### Scope

Establishes snapshot lineage, manifest schema, content-integrity mechanism, storage layout, determinism requirements, and pre-flight verifiable field set for anchored-real fixtures produced by the `win_rate_21d` feature pipeline. Defines the SD-A2-1 conditional rider closure path. Contains an interlock against SD-A2-8 to prevent premature fixture materialization.

### N-A2-5-1: Identity layer

Every anchored-real fixture snapshot is identified by an ordered pair:

- `snapshot_id`: semantic build identifier, format `{feature}_{ISO8601_utc}_{content_hash_prefix12}`.
- `content_hash`: SHA-256 hex digest of on-disk fixture data file bytes, 64 lowercase hex characters.

Binding rules:

- `(snapshot_id, content_hash)` is one-to-one and immutable. A given `snapshot_id` MUST NOT resolve to two distinct `content_hash` values. If a producer build attempts this, pre-flight validation MUST FAIL (non-deterministic build indicator).
- Canonical governance references to a fixture MUST cite both `snapshot_id` and `content_hash[:12]`. Semantic ID alone is not a governance-defensible reference.
- `snapshot_id` MAY embed build-time information (timestamp, counter). `content_hash` MUST be a pure function of `(input snapshots, producer code SHA, producer config)`; no clock or host state may influence it.

### N-A2-5-2: Hash policy

SHA-256 is the canonical identity hash algorithm. No alternatives are permitted for governance identity. Hash target: raw bytes of the on-disk `data.parquet` file. Performance-tier checksums (xxhash, BLAKE3) MAY be computed for non-governance purposes but MUST NOT enter the canonical chain.

**Governance-fixed Parquet writer invariants.** Producer MUST satisfy every one:

- `compression = 'zstd'` (deterministic codec; forbid snappy pre-1.1.9 and other non-deterministic codecs).
- `coerce_timestamps = 'us'` with `allow_truncated_timestamps = False`.
- `use_dictionary = True`.
- No producer-side wall-clock or hostname keys in file-level metadata.
- Canonical column sort: alphabetical by column name, applied before write.
- Explicit dtype specification for every output column (SD-A2-8 fixes the values).

**Recorded in manifest but NOT governance-fixed.** Producer records every parameter passed to the writer; specific values MAY vary across snapshots:

- `compression_level`
- `row_group_size`
- `data_page_version`
- Writer library name and version (e.g., `pyarrow==15.0.2`)
- Any additional writer parameters

**Interpretation of writer library version.** The canonical identity is defined by the serialized file bytes. Writer library version metadata is retained in file metadata and recorded in the manifest because it may influence serialization output and is therefore required for exact rebuild. Library version is NOT itself a normative identity component. Same-input rebuild with the RECORDED writer configuration and library version MUST reproduce the SAME `content_hash`; this is the actual invariant.

### N-A2-5-3: Manifest topology

Two-tier hybrid:

- **Side-car manifest** (per snapshot): `manifest.json`, colocated with the data file. Format: JSON only. Top-level field `manifest_format: "json"` is required. Format transitions (e.g., CBOR, msgpack) require major schema version bump AND governance amendment.
- **Master ledger** (append-only): `docs/research/fixtures/anchored_real_ledger.md`. Each entry chains to previous entry via `prev_entry_chain_hash` (md5), matching existing Helios SD-lock ledger discipline.

**Chain hash algorithm split.** Content hashes are SHA-256 (identity). Ledger chain hashes are md5 (append-order verification). This is intentional: chain integrity is corruption detection, not adversarial resistance; md5 matches existing pattern.

**Producer atomic write sequence.**

1. Write `data.parquet.tmp` (temporary path).
2. Compute `content_hash` from written bytes.
3. Write `manifest.json.tmp` (temporary path) containing `content_hash`.
4. Compute `manifest_hash = SHA-256(manifest.json bytes)`.
5. Atomic rename `data.parquet.tmp` → `data.parquet`.
6. Atomic rename `manifest.json.tmp` → `manifest.json`.
7. Append master ledger entry: `(snapshot_id, content_hash, manifest_hash, prev_entry_chain_hash, commit_sha_at_build)`.

**Rollback and canonical discoverability.** Canonical status is conferred by the master ledger, not by the filesystem.

- Producer snapshot discovery / resolution logic MUST consult the master ledger as the authoritative registry. Filesystem walks over `data/fixtures/anchored_real/` MUST NOT be used for canonical resolution by any governed consumer.
- Failure handling for the atomic write sequence:
  - **Steps 1–4 failure** (temp files, hashes): remove temp files; no canonical state was created; no rollback obligation beyond cleanup.
  - **Steps 5–6 failure** (atomic renames): remove any partially renamed files; no ledger append; nothing canonical was created.
  - **Step 7 failure** (ledger append): `data.parquet` and `manifest.json` exist on disk but are NOT canonical. Producer MUST either (a) retry ledger append with bounded exponential backoff, or (b) rename the snapshot directory to `<snapshot_id>.orphaned/` and emit a P0 governance event.
- Consumer read semantics: a snapshot directory whose `snapshot_id` is not resolvable through the master ledger is NOT readable by any governed consumer, regardless of filesystem presence.
- Orphaned snapshot directories MAY be retained for post-hoc audit but MUST NOT be reachable through canonical producer resolution paths.

**Invariant.** `filesystem existence ≠ canonical existence`. The master ledger is the source of truth.

### N-A2-5-4: Storage layout

Path convention:

```
data/fixtures/anchored_real/<feature>/<snapshot_id>/
    data.parquet
    manifest.json
```

Where `<feature>` matches the feature name (`win_rate_21d`) and `<snapshot_id>` follows N-A2-5-1 format.

**Immutability enforcement: Detection + Policy (no filesystem-level prevention).**

- **Detection (mandatory).** Pre-flight validation and every consumer of an anchored-real fixture MUST recompute `content_hash` from bytes and compare against the manifest. Any mismatch is a HARD FAIL; no partial acceptance.
- **Policy (mandatory).** No automated process may overwrite, rename, or delete files under `data/fixtures/anchored_real/`. Any such action requires explicit governance amendment.
- **Filesystem `chmod 444` (optional).** MAY be applied opportunistically but is NOT relied upon (cross-machine sync between nexus / local Downloads / backup targets is not permission-preserving in all cases).

**Retention policy.** DEFERRED to operational governance. Constraint: snapshots MUST NOT be deleted by any automated process without explicit governance amendment. This deferral is non-blocking for SD-A2-5 LOCK.

### N-A2-5-5: Determinism requirement

Producer builds MUST be deterministic:

> Same input snapshots + same producer code SHA + same producer config + same recorded writer configuration and library version ⇒ identical `content_hash`.

**Required producer implementation guarantees.**

- Canonical sort applied to output DataFrame before write. Sort keys: `(date, symbol_id)` ascending. Both keys MUST be present as columns.
- No unordered iteration in output construction (no reliance on `set` iteration order, no `dict.keys()` in output-affecting paths).
- Any random seed used MUST be recorded in `manifest.json` under `random_seed`. If randomness is not used, field value is `null`.
- No `datetime.now()`, `time.time()`, or system-clock reads in producer logic that affect data content. `build_utc_timestamp` is recorded once at build start, stored in manifest for audit, and is NOT included in `content_hash` scope.
- Explicit dtype specification for all output columns (SD-A2-8 fixes the dtype values; SD-A2-5 fixes that dtypes MUST be explicit).

**Execution environment canonicalization.** Producer execution environment variables that MAY influence serialized output MUST be either canonicalized at process entry OR explicitly recorded in the manifest.

Canonicalized at process entry (nexus / Linux target):

- `LC_ALL = "C.UTF-8"` — string sort collation follows C locale; UTF-8 encoding enforced.
- `TZ = "UTC"` — all timezone-naive datetime operations resolve to UTC; producer code MUST use timezone-aware UTC datetimes throughout.
- `PYTHONHASHSEED = "0"` — Python dict/set hash randomization disabled. Producer MUST NOT rely on dict/set iteration order regardless; this is defense in depth.

Recorded in manifest under `producer_environment`:

- `python_version`
- `os_platform`
- `arrow_library_version`
- `polars_version` (if used)
- `canonicalized` block echoing the values set at process entry

**Cross-platform note (non-normative).** Producer target is nexus (Linux). If producer execution ever migrates to macOS, `LC_ALL=C.UTF-8` availability MUST be verified; otherwise governance amendment required.

**Failure semantics.** Non-deterministic rebuild (identical inputs → different `content_hash`) is a P0 governance failure. Pipeline execution MUST HALT pending investigation.

### N-A2-5-6: Manifest schema

Version: `manifest_schema_version: "1.0.0"` (semver).

- Additive field additions in future SDs → minor version bump (v1.x.x).
- Breaking changes (removal, rename, semantic redefinition) → major version bump + governance amendment.

**Version bump semantics.** `manifest_schema_version` describes JSON schema shape. `producer_version` describes producer implementation semver. The two are independent: schema minor bump does NOT require producer version change; producer major change does NOT necessarily bump schema.

**Required fields for v1.0.0.**

```json
{
  "manifest_format": "json",
  "manifest_schema_version": "1.0.0",
  "producer_version": "0.1.0",
  "snapshot_id": "win_rate_21d_20260702T134502Z_a3f92e18c04b",
  "content_hash": "a3f92e18c04b7d...",
  "content_hash_algorithm": "sha256",
  "feature": "win_rate_21d",
  "producer_identity": {
    "producer_id": "<from SD-A2-2 locked identity>",
    "producer_code_sha": "<git rev-parse HEAD at build; clean tree required>",
    "producer_config_hash": "<SHA-256 of resolved config as canonical JSON>",
    "repository_clean": true
  },
  "producer_environment": {
    "python_version": "3.13.2",
    "os_platform": "Linux-6.5.0-x86_64",
    "arrow_library_version": "pyarrow==15.0.2",
    "polars_version": "<version-or-null>",
    "canonicalized": {
      "LC_ALL": "C.UTF-8",
      "TZ": "UTC",
      "PYTHONHASHSEED": "0"
    }
  },
  "build_utc_timestamp": "2026-07-02T13:45:02Z",
  "build_host": "<hostname; audit only, not hashed>",
  "input_snapshots": [
    {
      "role": "<e.g., listed_market_daily_price_adj>",
      "snapshot_id": "<upstream snapshot_id>",
      "content_hash": "<upstream content_hash>"
    }
  ],
  "row_count": 0,
  "column_names": ["date", "symbol_id", "win_rate_21d"],
  "column_dtypes": {"date": "date32[day]", "symbol_id": "uint32"},
  "min_cross_section_obs_per_date": 30,
  "parquet_writer_config": {
    "governance_fixed": {
      "compression": "zstd",
      "coerce_timestamps": "us",
      "allow_truncated_timestamps": false,
      "use_dictionary": true,
      "column_sort": "alphabetical",
      "wall_clock_metadata": false
    },
    "recorded": {
      "compression_level": 3,
      "row_group_size": 65536,
      "data_page_version": "2.0"
    }
  },
  "random_seed": null
}
```

**Fields explicitly DEFERRED (not v1.0.0).**

- Full snapshot lineage DAG (upstream chain beyond direct inputs) → SD-A2-11.
- Regeneration-trigger conditions → SD-A2-11.

### N-A2-5-7: Pre-flight verifiable fields

Every normative field listed in this section MUST be verified by producer build pre-flight validation. The current version defines the following checks. Any FAIL closes the build with no artifact persistence and no ledger append.

| # | Field | Source | Check |
|---|---|---|---|
| 1 | `manifest_format` | manifest | equals `"json"` |
| 2 | `manifest_schema_version` | manifest | equals `"1.0.0"` |
| 3 | `snapshot_id` | manifest | regex `^win_rate_21d_\d{8}T\d{6}Z_[0-9a-f]{12}$` |
| 4 | `content_hash` | manifest | 64 lowercase hex characters |
| 5 | `content_hash_recomputed` | `data.parquet` bytes | SHA-256 of file equals manifest `content_hash` |
| 6 | `snapshot_id_prefix_binding` | derived | `content_hash[:12]` equals `snapshot_id` last 12 characters |
| 7 | `producer_identity.producer_id` | manifest | matches SD-A2-2 locked identity |
| 8 | `producer_identity.producer_code_sha` | manifest | equals `git rev-parse HEAD`; working tree clean |
| 9 | `producer_identity.repository_clean` | manifest | equals `true` |
| 10 | `producer_version` | manifest | valid semver string |
| 11 | `producer_environment.canonicalized.LC_ALL` | manifest | equals `"C.UTF-8"` |
| 12 | `producer_environment.canonicalized.TZ` | manifest | equals `"UTC"` |
| 13 | `producer_environment.canonicalized.PYTHONHASHSEED` | manifest | equals `"0"` |
| 14 | `min_cross_section_obs_per_date` | manifest | equals 30 (SD-A2-1) |
| 15 | `parquet_writer_config.governance_fixed` | manifest | every field equals SD-A2-5 locked value |
| 16 | `parquet_writer_config.recorded` | manifest | present; specific values not checked against fixed reference |
| 17 | `column_dtypes` | manifest ∧ data | manifest values equal actual Parquet schema |
| 18 | `input_snapshots[*].content_hash` | manifest ∧ upstream ledger | each upstream `content_hash` resolvable in a prior ledger entry |
| 19 | `master_ledger_entry` | master ledger | new entry appended with correct `prev_entry_chain_hash` md5 |

**SD-A2-1 rider closure.** The first successful producer build passing all normative pre-flight checks defined in this section closes the SD-A2-1 conditional rider (rider closure mechanism per SD-A2-3).

### N-A2-5-8: SD-A2-8 interlock

**Rationale.** `content_hash` is defined as SHA-256 of raw Parquet file bytes. Parquet file bytes depend on column dtypes. SD-A2-8 (dtype widths) is not yet LOCKED. Any anchored-real fixture built between SD-A2-5 LOCK and SD-A2-8 LOCK would carry a dtype-dependent `content_hash` that SD-A2-8 might invalidate, forcing rebuild or governance amendment.

**Normative clause.**

> No anchored-real fixture may be materialized via the governed producer path until BOTH SD-A2-5 and SD-A2-8 are LOCKED. Producer builds attempted before SD-A2-8 LOCK are OUT OF SCOPE for governance and their outputs are NON-CANONICAL. Master ledger entries MUST NOT be appended for such builds.

**Non-canonical artifact reference prohibition.**

> Non-canonical artifacts (produced before SD-A2-8 LOCK or through any non-governed path) MUST NOT be referenced by any governance document, audit memo, research note, or ledger entry. Referencing a non-canonical artifact within a governance context is itself a governance error and requires correction before further governance action can proceed.

This entire clause is automatically retired at SD-A2-8 LOCK.

### Deferrals recorded

- Retention policy → operational governance (non-blocking).
- Full snapshot lineage DAG → SD-A2-11.
- Regeneration-trigger detection → SD-A2-11.
- Column dtype widths → SD-A2-8 (with interlock per N-A2-5-8).

### SD-A2-1 rider closure path

Post-SD-A2-5 LOCK, the SD-A2-1 conditional rider remains ACTIVE until the first successful producer build passes all pre-flight checks defined in N-A2-5-7. This requires SD-A2-8 LOCK to precede any legitimate producer build (per N-A2-5-8 interlock). Rider closure is therefore gated on the sequence: SD-A2-8 LOCK → producer build → pre-flight pass.

### Governance metadata

- **SD ID:** SD-A2-5
- **Status:** LOCKED
- **Commit SHA:** `23b249b` (backfill post-commit per SD-A2-1..4 pattern; see commits `9ca0aa8`, `d83b80e`, `76cd6bb`, `e330a39` for the backfill precedent)
- **Prev SD lock:** SD-A2-4 (commit `036f0b4`)
- **Ledger version at lock:** v0.1.0 (append cycle continues)
- **Prev ledger tail md5:** `83c101a7c3373931bbd9fd47a5f922c0`
- **New ledger tail md5 after append:** `<computed post-write>`
- **SD lock progress after this entry:** 5/11

---
