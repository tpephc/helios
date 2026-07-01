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
**Commit:** <TBD>

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
| SD-A2-4      | NOT_LOCKED |
| SD-A2-5      | NOT_LOCKED |
| SD-A2-6      | NOT_LOCKED |
| SD-A2-7      | NOT_LOCKED |
| SD-A2-8      | NOT_LOCKED |
| SD-A2-9      | NOT_LOCKED |
| SD-A2-10     | NOT_LOCKED |
| SD-A2-11     | NOT_LOCKED |

Document `Status` field advances OPEN → COMPLETE when all
eleven rows show LOCKED.

*End of ledger at SD-A2-3 lock.*
