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
| SD-A2-2      | NOT_LOCKED |
| SD-A2-3      | NOT_LOCKED |
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

*End of ledger at SD-A2-1 lock.*
