# PR-Level Disposition Ledger — `win_rate_21d`

**Document ID:** `win_rate_21d_pr_dispositions`
**Version:** v0.1.3
**Status:** ACTIVE
**Owner:** Veronica
**Repository:** Helios (`~/projects/helios`)
**Feature:** `win_rate_21d`
**Record model:** append-only
**Gate:** A2 (PR-2C implementation phase)
**Created:** 2026-07-11
**Ledger creation anchor:** `624afef`

---

## Linkage anchors at ledger creation

- **Algorithm:** MD5
- **Encoding expectation:** UTF-8
- **Ledger creation anchor:** `624afef`

| Path | MD5 |
| ---- | --- |
| `docs/research/win_rate_21d_a2_governance.md` | `44238c19bd326a14be40e1ff5b6ac306` |
| `docs/research/win_rate_21d_a2_sd_locks.md`   | `f75b2d70f69933e8c36963d3e704d0a4` |

These hashes record the referenced artifacts' byte state when this ledger
was created. They are audit linkage anchors, not immutable lock
invariants. Later legitimate append-only changes to the referenced
artifacts do not invalidate this ledger.

---

## Scope

This ledger is the feature-specific append-only durable carrier for
PR-level governance dispositions (D-PR* series) concerning the
`win_rate_21d` feature.

**Includes:**

- PR-level D-PR* dispositions for `win_rate_21d`.

**Excludes:**

- SD-A2-* records, which remain exclusively in
  `docs/research/win_rate_21d_a2_sd_locks.md`.
- Governance principles (A2-GOV-*, ER-A2-*), which remain in
  `docs/research/win_rate_21d_a2_governance.md`.

**Non-amendment:**

- This ledger does not amend or reopen
  `docs/research/win_rate_21d_a2_governance.md` (LOCKED v0.1.0 at
  2026-06-30).
- This ledger does not modify any SPEC_LOCKED artifact.

**Commit message role:**

- Commit messages remain closure/reference summaries. They are not the
  canonical full-text carrier for D-PR* dispositions. Prior commits
  (for example `0a61aa4` referencing a "PR-2B disposition ledger" not
  present in HEAD at time of ledger creation) establish the durability
  gap that this ledger is created to resolve for future PRs.

---

## Normative status

Entries labelled `ORIGINAL LOCKED DISPOSITION` are normative for their
declared scope from the moment the locking commit is merged into
`main`. The `Commit SHA` backfill records that fact; it does not
create it.

Entries labelled `RECONSTRUCTED CONTRACT SUMMARY` are evidence-limited
historical records. Their normative force is bounded by the epistemic
limit statement in each such entry; they MUST NOT be read as recovering
alternatives, rejected options, or rationale chains not present in the
cited evidence.

Non-normative sections in individual entries (typically titled
"Implementation Notes" or "Engineering Implications") do not carry
governance force even inside `ORIGINAL LOCKED DISPOSITION` entries.

---

## Record model

This ledger is append-only. New entries are appended in append order.

The `Previous D-PR entry` field on each entry records the immediately
preceding entry in this ledger's append order. It provides append-chain
integrity for audit and does NOT represent:

- original decision chronology;
- normative dependency between dispositions;
- historical time ordering of the underlying work.

Normative dependencies between dispositions are recorded, when present,
in an explicit `Normative references` field on the depending entry.

Original historical time (when the underlying decision or its
implementation actually occurred) is recorded, when relevant, in the
entry's `Evidence basis` field for reconstructed records.

---

## Record classes

Two record classes are permitted in this ledger:

### `ORIGINAL LOCKED DISPOSITION`

The full disposition text is authored and committed at the time the
decision is locked. All fields (`Question`, `Decision`, rejected
alternatives if applicable, `Governance metadata`) are original.

The `Evidence basis` field for such entries reads:

```
Evidence basis: Original disposition; no reconstruction basis applicable.
```

### `RECONSTRUCTED CONTRACT SUMMARY`

The disposition is being recorded after the underlying decision was
already implemented but no full-text disposition carrier existed in HEAD
at the time of the original decision.

Such entries:

- MUST cite the specific commit(s), source files, and tests that
  constitute the evidence for the reconstructed contract;
- MUST NOT infer alternatives, rejected options, or rationale chains
  not present in that evidence;
- MUST include an epistemic limit statement explicitly stating what is
  and is not recoverable from the evidence;
- MUST be dated with the reconstruction date, separate from the
  original implementation date.

Example `Evidence basis` shape for reconstructed entries:

```
Evidence basis:
  - commit <sha> body
  - <source path>
  - <test path>
Reconstruction date: <YYYY-MM-DD>
Epistemic limit:
  - decision outcome and implemented contract are evidenced
  - original alternatives and rationale chain are unavailable
```

---

## Metadata schema

Each entry ends with a `Governance metadata` block containing the
following fields, in this order:

| Field | Meaning |
| ----- | ------- |
| `Status` | `DRAFT`, `LOCKED`, or `SUPERSEDED`. |
| `Commit SHA` | SHA of the commit that locks the entry (backfilled). |
| `Entry repository anchor` | HEAD SHA at the time the entry's decision was judged. May differ from the header's `Ledger creation anchor` for entries added in later sessions. |
| `Previous D-PR entry` | Immediately preceding entry in append order, or `(none — first entry in this ledger)`. |
| `Ledger version at lock` | Ledger version string. |
| `Previous ledger tail md5` | MD5 of ledger content immediately before this entry was appended, or `(none — ledger creation)` for the first entry. |
| `New ledger tail md5 after append` | `<TBD — computed after lock commit>` placeholder at lock time; backfilled in a subsequent audit action if required. |
| `Record class` | `ORIGINAL LOCKED DISPOSITION` or `RECONSTRUCTED CONTRACT SUMMARY`. |
| `Evidence basis` | Per record class; see previous section. |

Additional entries may add fields (for example `Normative references`
for dispositions that explicitly depend on prior D-PR entries) without
altering the base schema.

---

## Evolution

This ledger is feature-specific to `win_rate_21d`. Adoption of an
analogous PR-level disposition ledger by another Helios feature requires
an independent decision by that feature. The creation of this ledger
does not silently establish a global repository convention.

---

## Historical backfill policy

Historical D-PR2A-*, D-PR2B-*, and D-PR2B.1-* dispositions predate this
ledger. Backfill of those historical dispositions is governed by three
tiers:

### Tier 1 — Bulk historical backfill: non-blocking

Historical D-PR* series are recorded governance debt. Bulk backfill of
the entire historical corpus is NOT blocking for:

- PR-2C.0 kickoff;
- PR-2C.1 / .2 / .3 implementation;
- SD-A2-1 rider closure;
- any subsequent PR-2C.4 producer end-to-end integration.

### Tier 2 — Normatively referenced historical entries: MUST backfill before referring entry locks

If a new disposition's normative text explicitly cites a historical
D-PR* contract (for example if PR-2C.4 depends on D-PR2B.1-6's
`_ShellWriter` default preservation), the referenced historical entry
MUST be backfilled as a `RECONSTRUCTED CONTRACT SUMMARY` before the
new referring disposition locks.

This prevents new locked dispositions from citing durable records that
do not exist.

### Tier 3 — Unreferenced historical entries: opportunistic

Historical D-PR* entries not referenced by any current normative
disposition SHOULD be backfilled opportunistically. No deadline.

---

# Entries

## D-PR2C-0 — Durable Carrier for PR-Level Dispositions

### Decision

Create `docs/research/win_rate_21d_pr_dispositions.md` (this file) as
the feature-specific append-only durable carrier for D-PR* governance
records concerning `win_rate_21d`.

### Scope

- Includes PR-level D-PR* dispositions for `win_rate_21d`.
- Excludes SD-A2-* records, which remain exclusively in
  `docs/research/win_rate_21d_a2_sd_locks.md`.
- Does not amend or reopen
  `docs/research/win_rate_21d_a2_governance.md`.
- Commit messages remain closure/reference summaries and are not the
  canonical full-text carrier.

### Historical records

- Historical D-PR2A-*, D-PR2B-*, and D-PR2B.1-* records may be
  backfilled only to the extent supported by repository evidence.
- Reconstructed records MUST be labelled `RECONSTRUCTED CONTRACT
  SUMMARY` and MUST NOT imply recovery of unavailable original
  rationale, alternatives, or reviewer reasoning.
- A historical disposition referenced normatively by a new disposition
  MUST be backfilled as a reconstructed record before the referring
  disposition locks.
- Other historical backfill is non-blocking governance debt (Tier 3).

### Evolution

- This ledger is feature-specific, not a cross-repository universal
  policy.
- Adoption by another feature requires an independent decision by that
  feature; this entry does not silently establish a global repository
  convention.

### Situation of origin

At time of ledger creation, HEAD SHA `624afef` contained:

- No `D-PR*` reference in any `docs/**/*.md` file
  (`grep -rn "D-PR" --include="*.md" docs/` returned empty).
- Commit `0a61aa4` (PR-2B v2) body referring to a "PR-2B disposition
  ledger" that was not present as a discoverable file in HEAD.
- Commit `624afef` (PR-2B.1 [4/4]) body closing D-PR2B.1-5 and
  D-PR2B.1-6 with contract summaries only.

This established that D-PR* series had no canonical full-text durable
carrier prior to this ledger's creation. This entry (D-PR2C-0) creates
the carrier as a first-class governance action rather than assuming
one existed.

### Governance metadata

- **Status:** LOCKED
- **Commit SHA:** `caf4dca2644f2b424651869d820883cd47b129cb`
- **Entry repository anchor:** `624afef`
- **Previous D-PR entry:** (none — first entry in this ledger)
- **Ledger version at lock:** v0.1.0
- **Previous ledger tail md5:** (none — ledger creation)
- **New ledger tail md5 after append:** `34ab8810b032a6577b22caa7934fec7e`
- **Record class:** ORIGINAL LOCKED DISPOSITION
- **Evidence basis:** Original disposition; no reconstruction basis applicable.

---

## D-PR2C-1 — Rider-Closing Invocation Model

### Question

How shall the rider-closing pre-flight registry evolve when PF-B1,
PF-B2, and PF-B6 become real checks requiring runtime inputs?

Q-PR2A-D2 at `features/win_rate_21d/pre_flight.py:225-238` explicitly
deferred this decision to the PR introducing the first parameterised
rider-closing check. PR-2C is that PR.

Current HEAD registry shape at `features/win_rate_21d/pre_flight.py:257`:

```python
RIDER_CLOSING_CHECKS: Final[tuple[Callable[[], PreFlightResult], ...]] = (
    pf_b1_scope_check,
    pf_b2_canonical_source_check,
    pf_b6_duckdb_writeability_check,
)
```

Each callable is currently invoked with no arguments at
`features/win_rate_21d/pre_flight.py:311-314`.

### Decision

Adopt a unified immutable `PreFlightContext` runtime carrier.

Canonical callable contract evolves to:

```python
PreFlightCallable = Callable[[PreFlightContext], PreFlightResult]
RIDER_CLOSING_CHECKS: Final[tuple[PreFlightCallable, ...]]
```

Registry ordering, membership, and named-function content are
unchanged.

### `PreFlightContext` definition

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class PreFlightContext:
    scope: BuildScope
    producer_context: ProducerContext
```

**Field naming rationale:** the field is named `producer_context` (not
`context`) to avoid `context.context.duckdb_path` nested generic naming
at call sites.

### Field coverage evidence

All PF-B1 / PF-B2 / PF-B6 runtime inputs identified in HEAD are covered
by these two fields:

- `PreFlightContext.scope.requested_start` and `.requested_end` are
  available via `features/win_rate_21d/build_types.py:61-62`.
- `PreFlightContext.producer_context.duckdb_path` is available via
  `features/win_rate_21d/build_types.py:85`, defaulting to the value at
  `features/win_rate_21d/constants.py:53`.
- `PreFlightContext.producer_context.target_table` is available via
  `features/win_rate_21d/build_types.py:86`, defaulting to the value at
  `features/win_rate_21d/constants.py:49`.

No additional fields are required for PF-B1 / PF-B2 / PF-B6.

### Construction point

`PreFlightContext` SHALL be constructed inside `build_full()`, not by
callers via `ProducerBuildRequest`:

```python
preflight_context = PreFlightContext(
    scope=request.scope,
    producer_context=request.context,
)
```

**Rationale:**

- Preserves `ProducerBuildRequest` API surface; no breaking change to
  callers of `build_full()`.
- All required fields are derivable from `request`; caller
  responsibility is not expanded.
- Minimises PR-2C.0 test churn:
  `tests/features/win_rate_21d/test_safety_gate.py:327-416`
  (`test_build_full_enters_body_after_gate`) requires only `_real` stub
  signature migration, not request-construction changes.

### Rejected alternatives

#### Option A — `functools.partial`

**Rejected** on evidence.

- `tests/features/win_rate_21d/test_safety_gate.py:105-109`
  (`test_rider_closing_checks_content`) asserts exact ordered registry
  membership via `==`. `functools.partial` objects are not equal to
  their underlying functions under `==`; this assertion would break.
- `tests/features/win_rate_21d/test_safety_gate.py:138-142`
  (`test_gate_error_names_all_shells`) reads `check.__name__` while
  iterating `RIDER_CLOSING_CHECKS`. `functools.partial` objects do not
  expose `__name__`; this raises `AttributeError` at runtime.

Both failures are structural, not stylistic.

#### Option B — `(callable, args_provider)` heterogeneous tuples

**Rejected.** Introduces a second abstraction layer whose sole purpose
is argument adaptation. Makes registry members metadata records rather
than executable checks. Breaks the same
`tests/features/win_rate_21d/test_safety_gate.py:105-109` exact ordered
registry membership contract.

#### Option C — unified `PreFlightContext`

**Accepted.** Preserves homogeneous callable registry, named
module-level functions, and exact ordered registry membership contract.
Runtime dependencies are explicit and typed.

### Registry contract compatibility

The following public names SHALL remain stable in identity, ordering,
and membership:

- `ALL_PRE_FLIGHT_CHECKS` at `features/win_rate_21d/pre_flight.py:242`.
- `RIDER_CLOSING_CHECKS` at `features/win_rate_21d/pre_flight.py:257`.

The exact ordered registry membership contracts at
`tests/features/win_rate_21d/test_safety_gate.py:86-114` SHALL continue
to pass after signature migration. Only callable signatures change;
tuple content is unchanged.

### Forward compatibility

`PreFlightContext` field set represents the minimum required by PR-2C
rider-closing checks.

Later PRs may append keyword-only fields with defaults without
reopening D-PR2C-1, provided that:

1. existing fields remain unchanged in name, type, and semantics;
2. the new field is immutable or references governance-stable
   immutable metadata;
3. the new field does not introduce mutable resources, open
   connections, writers, compute callables, hooks, or service objects;
4. the addition does not alter registry shape or the canonical
   `Callable[[PreFlightContext], PreFlightResult]` invocation model;
5. the owning PR documents and tests the new field's necessity.

Any change violating these conditions requires a new governance
disposition.

### Governance metadata

- **Status:** LOCKED
- **Commit SHA:** `caf4dca2644f2b424651869d820883cd47b129cb`
- **Entry repository anchor:** `624afef`
- **Previous D-PR entry:** D-PR2C-0
- **Ledger version at lock:** v0.1.0
- **Previous ledger tail md5:** `34ab8810b032a6577b22caa7934fec7e`
- **New ledger tail md5 after append:** `34ab8810b032a6577b22caa7934fec7e`
- **Record class:** ORIGINAL LOCKED DISPOSITION
- **Evidence basis:** Original disposition; no reconstruction basis applicable.

---

## D-PR2C-2 — Shell Detection and Runtime Pre-Flight Semantics

### Problem

Current HEAD function `verify_rider_closing_checks_are_real()` at
`features/win_rate_21d/pre_flight.py:271-317` invokes every rider-closing
check and catches only `PreFlightShellError`. This behaves as a shell
detector while all checks are shells.

Once checks become real, the same loop would also execute runtime
pre-flight logic. However, HEAD implementation at
`features/win_rate_21d/pre_flight.py:311-314` discards returned
`PreFlightResult` values and therefore would not abort when
`result.passed is False`. This would permit a failed real pre-flight
check to pass through the safety gate — a gate hole introduced silently
by rider closure.

### Decision

Separate shell-state verification from runtime pre-flight execution
into two distinct operations.

#### 1. Shell-state verification (existing symbol, migrated signature)

```python
def verify_rider_closing_checks_are_real(
    context: PreFlightContext,
) -> None:
```

Responsibilities:

- Invoke each `check` in `RIDER_CLOSING_CHECKS` with `context`.
- Aggregate checks raising `PreFlightShellError`.
- Raise one aggregated `PreFlightShellError` naming all remaining
  shells (preserves the aggregate diagnostic contract at
  `tests/features/win_rate_21d/test_safety_gate.py:133-142`).
- Propagate all non-`PreFlightShellError` exceptions unchanged
  (preserves the contracts at
  `tests/features/win_rate_21d/test_safety_gate.py:194-232` and
  `tests/features/win_rate_21d/test_safety_gate.py:235-273`).
- Ignore `PreFlightResult.passed`. Pass/fail semantics belong to the
  runtime executor, not shell classification.

#### 2. Runtime execution and enforcement (new symbol)

```python
def run_rider_closing_checks(
    context: PreFlightContext,
) -> tuple[PreFlightResult, ...]:
```

Responsibilities:

- Execute each check in canonical order with `context`.
- Collect each `PreFlightResult`.
- Raise a domain-specific exception when any result has
  `passed=False`, carrying all collected results for diagnostics. The
  exception class name is deferred to PR-2C.0 implementation review;
  candidate: `PreFlightExecutionFailed`.
- Return the full `tuple[PreFlightResult, ...]` on all-pass, preserving
  the audit trail for future manifest emission (PR-3).
- Propagate operational exceptions unchanged. Operational exceptions
  SHALL NOT be classified as shell state.

### Failure semantics for real check implementations

Real PF-B checks SHALL classify outcomes as follows.

| Outcome | Mechanism |
| ------- | --------- |
| Governance / data validation failure | `return PreFlightResult(check_id="PF-Bx", passed=False, severity=ERROR, message=...)` |
| Operational execution failure | `raise <non-PreFlightShellError exception>` |
| Unimplemented state | `raise PreFlightShellError` — FORBIDDEN in real checks |

Real checks MUST NOT raise `PreFlightShellError`.

### Build ordering (PR-2C canonical)

```
BUILD_STRATEGY guard                        (existing)
    ↓
construct PreFlightContext                  (new in PR-2C.0)
    ↓
verify_rider_closing_checks_are_real(ctx)   (signature migrated)
    ↓
run_rider_closing_checks(ctx)               (new in PR-2C.0)
    ↓
body_enter_hook                             (existing)
    ↓
compute                                     (existing)
    ↓
writer.write_full                           (existing)
```

No body side effect may occur before both gates complete successfully.
The D-PR2B-4 invariant is preserved and strengthened (two gates instead
of one).

### Naming decision

`verify_rider_closing_checks_are_real()` SHALL retain its existing name
during PR-2C.

**Rationale (evidence-anchored):**

- `tests/features/win_rate_21d/test_safety_gate.py:49` directly imports
  the symbol.
- `tests/features/win_rate_21d/test_safety_gate.py:130`, `136`, `159`,
  `185`, `230`, `272` — six direct call sites in this test file.
- `features/win_rate_21d/producer.py:71` — import.
- `features/win_rate_21d/producer.py:257` — call site.

Total blast radius of a rename: three files, at least nine call sites.
Combining rename with signature migration in a single PR would conflate
necessary governance change with unrelated API churn, harming diff
reviewability.

Rename or retirement may be considered only after PR-2C closes the
rider and the shell detector's lifecycle is explicitly resolved. This
is deferred debt, not permanent.

### Test migration (PR-2C.0 scope)

#### Signature migration — seven callables

The following stub callables in
`tests/features/win_rate_21d/test_safety_gate.py` require the addition
of a `ctx: PreFlightContext` parameter (parameter is ignored inside the
body):

| Line | Symbol | Enclosing test |
| ---- | ------ | -------------- |
| 149 | `_real` | `test_gate_passes_when_all_rider_closing_are_real` |
| 170 | `_real` | `test_gate_partial_real_still_raises` |
| 208 | `_partial_real_that_leaks` | `test_gate_does_not_swallow_bare_not_implemented_from_real_check` |
| 212 | `_real` | (same test) |
| 255 | `_real_that_fails` | `test_gate_propagates_non_shell_exceptions_immediately` |
| 258 | `_shell_after` | (same test) |
| 356 | `_real` | `test_build_full_enters_body_after_gate` |

#### Call-site migration — seven call sites

`verify_rider_closing_checks_are_real()` calls at
`tests/features/win_rate_21d/test_safety_gate.py:130`, `136`, `159`,
`185`, `230`, `272`, `402` (the last via `build_full`) require passing
`context` argument.

#### Preserved verbatim in PR-2C.0

- `tests/features/win_rate_21d/test_safety_gate.py:64-79` — PreFlightShellError type invariants.
- `tests/features/win_rate_21d/test_safety_gate.py:86-114` — registry membership contracts.
- `tests/features/win_rate_21d/test_safety_gate.py:122-142` — default-shell gate behaviour.
- `tests/features/win_rate_21d/test_safety_gate.py:194-232` — bare NotImplementedError propagation.
- `tests/features/win_rate_21d/test_safety_gate.py:235-273` — non-shell exception propagation.
- `tests/features/win_rate_21d/test_safety_gate.py:309-324` — default `build_full` shell contract.
- `tests/features/win_rate_21d/test_safety_gate.py:419-439` — BUILD_STRATEGY guard ordering.

#### Deferred to PR-2C.1+ (first PF-B implementation PR)

- `tests/features/win_rate_21d/test_safety_gate.py:122-131` (`test_gate_raises_by_default`) — restructure to monkeypatch one shell back to shell state once at least one shell has become real.
- `tests/features/win_rate_21d/test_safety_gate.py:309-318` (`test_build_full_raises_preflight_shell_error_by_default`).
- `tests/features/win_rate_21d/test_safety_gate.py:321-324` (`test_build_full_gate_error_is_still_notimplementederror`).

These three tests fail correctly when the first shell becomes real.
That failure is the acceptance signal per the test-lifecycle notes at
`tests/features/win_rate_21d/test_safety_gate.py:17-28`. PR-2C.0
preserves them intact.

#### New tests to add in PR-2C.0

- `test_run_rider_closing_checks_returns_all_results_on_pass` — happy
  path.
- `test_run_rider_closing_checks_aborts_on_failed_result` — verifies
  runtime enforcement is not delegated to the shell detector.
- `test_run_rider_closing_checks_propagates_operational_exception` —
  mirrors the shell-detector's operational exception contract at
  `tests/features/win_rate_21d/test_safety_gate.py:235-273`.

### Governance metadata

- **Status:** LOCKED
- **Commit SHA:** `caf4dca2644f2b424651869d820883cd47b129cb`
- **Entry repository anchor:** `624afef`
- **Previous D-PR entry:** D-PR2C-1
- **Ledger version at lock:** v0.1.0
- **Previous ledger tail md5:** `34ab8810b032a6577b22caa7934fec7e`
- **New ledger tail md5 after append:** `34ab8810b032a6577b22caa7934fec7e`
- **Record class:** ORIGINAL LOCKED DISPOSITION
- **Evidence basis:** Original disposition; no reconstruction basis applicable.

---

## D-PR2C-3 — PF-B2 Canonical Source Verification Mechanism

### Question

PF-B2 requires structural verification that producer compute reads
exclusively from the canonical PIT view and never directly from the
raw price table.

- `features/win_rate_21d/constants.py:64`:
  `CANONICAL_PIT_VIEW_NAME: Final[str] = "listed_market_daily_price_adj"`
- Direct reads of `"daily_price_adj"` are forbidden and constitute a P0
  lineage violation per spec §4.4 (see governance annotation at
  `features/win_rate_21d/constants.py:60-63`).

The current locked wording in the PF-B2 shell docstring at
`features/win_rate_21d/pre_flight.py:153-167` permits `AST-level or
DuckDB EXPLAIN introspection`. PR-2C must select one canonical
mechanism.

### Decision

Adopt Python AST structural validation as the canonical PF-B2
mechanism, with a dual-layer criterion.

### Layer 1 — Forbidden literal prohibition

In the governed production module `features/win_rate_21d/compute.py`:

```python
ast.Constant(value="daily_price_adj")
```

SHALL NOT appear anywhere in the module AST.

**Escape hatch policy:**

- The production module MUST NOT contain the forbidden literal.
- Explanatory text, test fixtures, and negative-test source belong in
  test-only modules.
- If a runtime error message must reference the forbidden source, it
  MUST derive the string from a pre-flight-owned governance constant,
  not repeat the literal in `compute.py`.

### Layer 2 — Canonical source must participate in governed query construction

PF-B2 SHALL verify that `CANONICAL_PIT_VIEW_NAME` reaches a governed
DuckDB execution sink through a resolvable local data-flow chain:

```
CANONICAL_PIT_VIEW_NAME (ast.Name reference)
    ↓
query-building expression / assigned SQL string variable
    ↓
DuckDB execution sink: conn.execute(...) / duckdb.execute(...) / equivalent
```

**Verified evidence in current HEAD** (`features/win_rate_21d/compute.py`):

- Line 12: `from features.win_rate_21d.constants import CANONICAL_PIT_VIEW_NAME, ...`
- Lines 85-88: `sql = _SQL_MEDIAN_QUERY_TEMPLATE.format(view_name=CANONICAL_PIT_VIEW_NAME, min_obs=...)` — canonical constant enters SQL string construction.
- Line 92: `reader = conn.execute(sql).arrow()` — SQL string reaches DuckDB execution sink.

Chain: `CANONICAL_PIT_VIEW_NAME` (line 86) → `sql` (line 85 assignment)
→ `conn.execute(sql)` (line 92).

### Implementation scope boundary

PR-2C.2 SHALL support the local-assignment data-flow patterns present
in HEAD `features/win_rate_21d/compute.py`. PR-2C.2 SHALL NOT be
required to implement a general Python data-flow engine.

PR-2C.2 SHALL fail closed when the structural chain cannot be
established. "Reference exists somewhere in the module" alone is NOT
sufficient — Layer 2 must be satisfiable, not merely Layer 1.

### Scope boundary (what PF-B2 does NOT verify)

PF-B2 validates source-code lineage identity. It does not prove:

- the DuckDB catalog object at runtime is actually a view;
- the view definition is PIT-correct;
- runtime query execution resolves to the expected physical plan;
- upstream view contents are uncontaminated.

Those belong to catalog integration tests, upstream lineage tests, and
runtime audit — separate governance surfaces.

### Why DuckDB `EXPLAIN` is rejected

- Requires a live database and valid catalog state — conflates
  source-code governance with environment availability.
- Optimizer plans may normalize or inline relations.
- Plan format may vary across DuckDB versions.
- PF-B2 is defined by SD-A2-3 as a code-vs-spec structural check.
- A live plan cannot reliably prove the absence of alternative
  forbidden query paths elsewhere in the producer source.

`EXPLAIN` MAY be added later as defense-in-depth integration coverage
but SHALL NOT replace AST validation as the canonical mechanism.

### Target of inspection

The initial governed inspection target SHALL be the module:

```
features.win_rate_21d.compute
```

Its source file SHALL be resolved via `inspect.getsourcefile()` (or an
equivalent module-metadata lookup) at check invocation time.

**Rationale:** module identity is stable across repository layout
changes (e.g. src-layout migration, editable installs, packaging
refactors) whereas filesystem paths are not. PF-B2's governance target
is the logical module, not a specific file path.

In governed production execution, the check SHALL NOT accept an
arbitrary caller-supplied module or source. Test-only dependency
injection may be provided through a private helper accepting source
text or a file path.

### Result semantics

Pass:

```python
PreFlightResult(
    check_id="PF-B2",
    passed=True,
    severity=PreFlightSeverity.INFO,
    message="canonical PIT source structurally verified",
)
```

Layer 1 violation (forbidden literal found):

```python
PreFlightResult(
    check_id="PF-B2",
    passed=False,
    severity=PreFlightSeverity.ERROR,
    message='forbidden raw-table literal "daily_price_adj" detected at compute.py:<line>',
)
```

Layer 2 violation (canonical constant not on execution path):

```python
PreFlightResult(
    check_id="PF-B2",
    passed=False,
    severity=PreFlightSeverity.ERROR,
    message="CANONICAL_PIT_VIEW_NAME not reachable to DuckDB execution sink via resolvable local assignment chain",
)
```

Infrastructure failure (parse error, missing source file, unresolvable
analysis):

```python
raise <non-PreFlightShellError exception, e.g. RuntimeError>
```

### Governance metadata

- **Status:** LOCKED
- **Commit SHA:** `caf4dca2644f2b424651869d820883cd47b129cb`
- **Entry repository anchor:** `624afef`
- **Previous D-PR entry:** D-PR2C-2
- **Ledger version at lock:** v0.1.0
- **Previous ledger tail md5:** `34ab8810b032a6577b22caa7934fec7e`
- **New ledger tail md5 after append:** `34ab8810b032a6577b22caa7934fec7e`
- **Record class:** ORIGINAL LOCKED DISPOSITION
- **Evidence basis:** Original disposition; no reconstruction basis applicable.

---

# Implementation Notes (non-normative)

The following observations are engineering implications of D-PR2C-3,
not additional governance rules. Implementers and future refactorers
SHOULD be aware of them; reviewers MUST NOT reject a change solely
because it violates an Implementation Note.

### IN-1 — Two `.format(...)` call sites in current `compute.py`

HEAD `features/win_rate_21d/compute.py` contains two `.format(...)`
invocations:

- Line 82: `_ATTACH_STATEMENT_TEMPLATE.format(path_literal=...)` — does
  not involve `CANONICAL_PIT_VIEW_NAME`.
- Line 85: `_SQL_MEDIAN_QUERY_TEMPLATE.format(view_name=CANONICAL_PIT_VIEW_NAME, min_obs=...)` — governed path.

The PR-2C.2 analyzer must distinguish these two sites when tracing the
Layer 2 execution-path binding. This is a straightforward
implementation concern, not a governance surface.

### IN-2 — Analyzer capability shapes analyzable `compute.py` patterns

Because D-PR2C-3 requires fail-closed semantics on unresolvable
data-flow chains, the analyzer's supported patterns implicitly
constrain what SQL-construction styles `compute.py` can adopt without
failing PF-B2.

If a future refactor of `compute.py` introduces a pattern the analyzer
cannot resolve (dynamic SQL builder classes, cross-function SQL
fragment composition, external-config-sourced view names), PF-B2 will
fail closed even if the actual lineage remains correct.

This is a consequence of D-PR2C-3's fail-closed rule, not a separate
governance restriction. The remedy is one of:

1. extend the analyzer's supported patterns in the same PR that
   introduces the new `compute.py` pattern;
2. open a new governance disposition amending the analyzer's
   supported-patterns surface;
3. keep `compute.py` within the analyzable pattern set.

The choice is left to future implementers.

### IN-3 — PR ladder ordering is implementation planning

The proposed ordering `PR-2C.1 (PF-B1) → PR-2C.2 (PF-B2) → PR-2C.3
(PF-B6)` reflects a canonical-order default. An alternative ordering
`PR-2C.1 (PF-B1) → PR-2C.2 (PF-B6) → PR-2C.3 (PF-B2)` may be preferable
because PF-B2 requires an AST analyzer and regression harness, making
it the highest-effort implementation.

Both orderings are compliant with the D-PR2C-* dispositions. The final
choice is deferred to the implementer at PR-2C.1 kickoff and does not
require a new disposition entry.

---

# Gate A1 exit criteria

PR-2C Gate A1 locks when all of the following are accepted:

- **D-PR2C-0** — durable carrier for PR-level dispositions established.
- **D-PR2C-1** — unified `PreFlightContext` invocation model with
  guarded additive-only forward evolution.
- **D-PR2C-2** — shell detection separated from runtime result
  enforcement, existing `verify_rider_closing_checks_are_real` name
  retained.
- **D-PR2C-3** — AST canonical mechanism with dual-layer criterion
  (Layer 1 forbidden literal prohibition, Layer 2 execution-path
  binding), fail-closed on unresolvable analysis.

No production implementation of PF-B1, PF-B2, or PF-B6 may begin before
this ledger is appended and this commit is on `main` with the
`Commit SHA` fields backfilled per the SD-A2-* precedent.

---

# Proposed PR ladder

The following ladder is a working plan; final ordering choice is
subject to IN-3.

- **PR-2C.0** — `PreFlightContext` dataclass; `RIDER_CLOSING_CHECKS`
  signature migration; `verify_rider_closing_checks_are_real(context)`
  migration; `run_rider_closing_checks(context)` new symbol;
  `test_safety_gate.py` signature migration (seven stubs + seven call
  sites); new tests for `run_rider_closing_checks`; default-shell tests
  preserved verbatim; `build_full` internal `PreFlightContext`
  construction.
- **PR-2C.1** — PF-B1 real implementation (scope validation);
  restructure `test_gate_raises_by_default`,
  `test_build_full_raises_preflight_shell_error_by_default`, and
  `test_build_full_gate_error_is_still_notimplementederror` to
  monkeypatch remaining shells.
- **PR-2C.2** — PF-B2 real implementation (AST dual-layer per
  D-PR2C-3); `features/win_rate_21d/compute.py` module docstring:
  PF-B2 analyzer constraint note per IN-2.
- **PR-2C.3** — PF-B6 real implementation (DuckDB writeability, no
  trial writes).
- **PR-2C.4** — default `_ShellWriter` replacement decision (may
  normatively reference D-PR2B.1-6, in which case that historical
  disposition MUST be backfilled first per this ledger's Historical
  backfill policy Tier 2); `_BuildDependencies.writer` default
  migration; true `build_full()` end-to-end integration test; rider
  closure validation; SD-A2-1 rider status transition to CLOSED.

---

# Version history

| Version | Date       | Change |
| ------- | ---------- | ------ |
| v0.1.0  | 2026-07-11 | Initial ledger creation. Locks D-PR2C-0, D-PR2C-1, D-PR2C-2, D-PR2C-3 as ORIGINAL LOCKED DISPOSITION entries at repository anchor `624afef`. |
| v0.1.1  | 2026-07-12 | Appends D-PR2C-4 (PR-2C.0 Ruff baseline treatment) as an ORIGINAL LOCKED DISPOSITION at repository anchor `41e8e1e`. Governs PR-2C.0 static-analysis acceptance criteria and the deferred runtime-failure exception name; amends no implementation disposition and is not a Gate A1 lock condition. |
| v0.1.2  | 2026-07-12 | Appends D-PR2C-5 (completion of the PR-2C.0 signature-migration blast radius) as an ORIGINAL LOCKED DISPOSITION at repository anchor `182d26f`. Corrects a factual omission in D-PR2C-2's test-migration enumeration, observed during implementation validation; amends no design disposition. |
| v0.1.3  | 2026-07-13 | Appends D-PR2C-6, D-PR2C-7, D-PR2C-8 as ORIGINAL LOCKED DISPOSITION entries at repository anchor `6989d17`. Commit-anchor fields for all three entries backfilled in the same governance session. |

*End of ledger initial content. Future entries append below.*

---

## D-PR2C-4 — PR-2C.0 Ruff Baseline Treatment

### Question

The PR-2C.0 kickoff §Validation requires `ruff check` to pass on the four
files touched by PR-2C.0. Repository HEAD `41e8e1e` does not satisfy this
condition prior to any PR-2C.0 change.

### Evidence (observed at HEAD 41e8e1e)

`uv run ruff check` on the four touched files, under the project
configuration at `pyproject.toml:67-82`
(`select = ["E","F","I","N","UP","B","SIM","RUF"]`), reports six
violations:

| Rule | Location |
| ---- | -------- |
| `UP035` | `features/win_rate_21d/pre_flight.py:54` |
| `UP042` | `features/win_rate_21d/pre_flight.py:63` |
| `RUF022` | `features/win_rate_21d/producer.py:77` |
| `I001` | `tests/features/win_rate_21d/test_safety_gate.py:30` |
| `SIM300` | `tests/features/win_rate_21d/test_safety_gate.py:88` |
| `SIM300` | `tests/features/win_rate_21d/test_safety_gate.py:105` |

All six predate PR-2C.0.

`ruff format --check` on the same files reports three requiring
reformatting (`pre_flight.py`, `producer.py`, `test_safety_gate.py`);
`build_types.py` is already formatted.

### Conflict

`SIM300` fires precisely on the exact ordered registry membership
assertions that D-PR2C-2 requires be preserved verbatim, and that
D-PR2C-1 cites as structural evidence for rejecting `functools.partial`.
`UP042` cannot be resolved without altering `PreFlightSeverity`'s
serialization behaviour. Absolute Ruff cleanliness and the kickoff's
own scope restrictions are therefore not jointly satisfiable at HEAD.

### Decision

**D4-1 — No new violations.** PR-2C.0 SHALL introduce no `ruff check`
violation absent from the recorded HEAD baseline above. Verified by
line-normalised diff of concise Ruff output before and after.

**D4-2 — Touched-block compliance.** PR-2C.0 SHALL fix exactly the two
violations located in import blocks that PR-2C.0 necessarily rewrites:

- `UP035` at `pre_flight.py:54` — `typing.Callable` is a deprecated
  alias of `collections.abc.Callable`; substitution is semantically
  equivalent under `target-version = "py312"`.
- `I001` at `test_safety_gate.py:30` — the import block is modified by
  PR-2C.0 regardless.

Leaving these would make PR-2C.0 appear to be their origin.

**D4-3 — Preserved baseline debt.** PR-2C.0 SHALL NOT modify `UP042`,
`RUF022`, or `SIM300`. `UP042` would alter enum serialization behaviour;
`RUF022` would alter declared public-surface ordering; `SIM300` fires on
assertions D-PR2C-2 requires preserved verbatim. These SHALL NOT be
silenced with `# noqa`: suppression comments are an ungoverned surface
and would render the debt invisible in future lint output. They remain
visibly red.

**D4-4 — Exception naming.** D-PR2C-2 deferred the runtime-failure
exception name to PR-2C.0 implementation review, with
`PreFlightExecutionFailed` as candidate. That name triggers `N818`
(`select` includes `N`), which would violate D4-1. The name is therefore
LOCKED as `PreFlightExecutionError`, consistent with `PreFlightShellError`
and `EnvironmentVerificationError`. No semantic change.

### Not governed by D-PR2C-4

`ruff format --check` remains in the PR-2C.0 validation set unmodified;
this disposition does not remove it. Its baseline is recorded as evidence
and the acceptance condition is that the set of files requiring
reformatting does not expand. mypy is not governed by this disposition;
HEAD's mypy status is UNOBSERVED and no claim is made about it.

### Rejected alternative

**Silence `UP042`, `RUF022`, and `SIM300` with `# noqa` so the four files
report clean.** Rejected: disguises knowingly-retained contract decisions
as resolved findings, degrades future lint signal, and adds three
ungoverned suppression sites. Visible red plus an explicit disposition is
the honest record.

### Scope restriction

D-PR2C-4 governs validation criteria and one deferred naming decision.
It amends neither D-PR2C-1 nor D-PR2C-2.

### Governance metadata

- **Status:** LOCKED
- **Commit SHA:** `21ef72924f965e61f76ece5310d648cff7e7205a`
- **Entry repository anchor:** `41e8e1e`
- **Previous D-PR entry:** D-PR2C-3
- **Ledger version at lock:** v0.1.1
- **Previous ledger tail md5:** `c1f6086fc7b479bc89ba24192c98eefc`
- **New ledger tail md5 after append:** `0e4f28872d3920b8601e10c3f9faeea5`
- **Record class:** ORIGINAL LOCKED DISPOSITION
- **Evidence basis:** Original disposition; grounded in observed HEAD
  Ruff output and `pyproject.toml:67-82`.

---

## D-PR2C-5 — Completion of the PR-2C.0 Signature-Migration Blast Radius

### Timing (honest record)

This disposition was NOT locked before code. The PR-2C.0 implementation
was already in the working tree when the omission surfaced during
validation. D-PR2C-5 is locked before the two affected test files are
remediated, not before PR-2C.0 began.

DGP-01's "no code before disposition lock" discipline was satisfied for
D-PR2C-1, D-PR2C-2, and D-PR2C-4, all of which preceded implementation.
D-PR2C-5 corrects a factual omission in D-PR2C-2's enumeration that could
only be observed by executing the migration. Recording it as an ex-ante
decision would be false.

### Question

D-PR2C-2 §Test migration enumerated the signature-migration surface as
`tests/features/win_rate_21d/test_safety_gate.py` only. Is that
enumeration complete?

### Evidence (observed at PR-2C.0 implementation, repository anchor 182d26f)

It is not. After the D-PR2C-1 signature migration,
`uv run pytest tests/features/win_rate_21d` reports 5 failed, 142 passed.
All five failures are arity `TypeError`s in two additional files:

| File | Site | Failure |
| ---- | ---- | ------- |
| `test_pre_flight_shell.py:90` | `check()` in `test_pf_b_shells_do_not_pass_vacuously` (3 parametrisations) | `missing 1 required positional argument: 'context'` |
| `test_producer_body.py:75` | `_real()` in `_patch_gate_open` (2 dependent tests) | `takes 0 positional arguments but 1 was given` |

A repository-wide reference scan confirms the surface is now closed. The
only other matches (`tests/features/win_rate_21d/test_environment.py:124`,
`features/win_rate_21d/environment.py:128`) are docstring references
requiring no change.

`test_safety_gate.py` passes in full (27 tests) after migration. The
D-PR2C-1 / D-PR2C-2 design is not implicated. D-PR2C-2's blast-radius
figure ("three files, at least nine call sites") was computed for a
*rename* and was never re-derived for the *signature migration*.

### Decision

PR-2C.0 SHALL migrate the rider-closing call-site signatures in
`test_pre_flight_shell.py` and `test_producer_body.py`.

Strictly limited to:

1. adding the `PreFlightContext` parameter to affected callables and
   call sites;
2. adding the imports those signatures require.

The following SHALL NOT change: any assertion, any parametrisation, any
test name, any docstring semantics, any fixture behaviour, any PF-B3 /
PF-B4 test, any production code.

### Static analysis

The two files remediated under D-PR2C-5 are added to the D-PR2C-4 D4-1
delta rule. Their HEAD Ruff baseline, captured before remediation, is:

| Rule | Location |
| ---- | -------- |
| `I001` | `test_producer_body.py` |
| `N813` | `test_producer_body.py` (`BuildScope` as `_canonical_build_scope`) |
| `N813` | `test_producer_body.py` (`ProducerContext` as `_canonical_producer_context`) |

`test_pre_flight_shell.py` reports no `ruff check` violation at HEAD and
SHALL remain so.

`ruff format --check` reports BOTH files as requiring reformatting before
remediation. That set SHALL NOT expand.

Remediation SHALL introduce no violation absent from this baseline, and
SHALL NOT fix the baseline findings: they are pre-existing debt outside
the import blocks this patch necessarily rewrites, and fall under
D-PR2C-4 D4-3's preserved-debt principle.

### Relation to the kickoff's out-of-scope clause

The kickoff forbids *restructuring* the default-shell anchor tests — that
is, rewriting `test_pf_b_shells_do_not_pass_vacuously` to monkeypatch a
now-real check back into shell state. That restructure remains deferred to
the first PR that makes a PF-B shell real.

Signature migration is a distinct operation. It preserves the anchor's
assertion (`pytest.raises(NotImplementedError)`) verbatim. Without it,
PR-2C.0 cannot land at all. This disposition does not relax the
restructure prohibition.

### Governance metadata

- **Status:** LOCKED
- **Commit SHA:** `32a0ab8b89800054753264c7dc661156a4fb63db`
- **Entry repository anchor:** `182d26f`
- **Previous D-PR entry:** D-PR2C-4
- **Ledger version at lock:** v0.1.2
- **Previous ledger tail md5:** `dff03e59bcc87d162cb0755a76aa72e8`
- **New ledger tail md5 after append:** `0f4e89b8f9517003a8b6d9c7ea75ef65`
- **Record class:** ORIGINAL LOCKED DISPOSITION
- **Evidence basis:** Original disposition; grounded in observed pytest
  failures and a repository-wide reference scan.

---

## D-PR2C-6 — PF-B1 Materialized-Scope Mechanism and Operational Boundary

### Status
LOCKED

### Scope
PF-B1 mechanism and operational/correctness boundary. Order implication: none.
PR-2C.1 target: selected separately in D-PR2C-7.

### Terminology note
The term "materialized scope" in this disposition means the date-availability
domain observed from the canonical PIT source for one-shot full rebuild. It
does NOT reuse spec §9.1 SD-2's storage-persistence meaning ("materialized
BASE TABLE" as a persisted table vs. a view). These are unrelated concepts
that happen to share a word; conflating them was flagged during entry
evidence review as a false-positive search hit and must not recur.

This disposition does not authorize implementation and does not select the
PR-2C.1 target.

### Verified findings that motivate this mechanism

- `features/win_rate_21d/compute.py`'s query performs no date-range
  filtering. The `scope` parameter is explicitly discarded
  (`compute.py`, `_ = scope`), and `_SQL_MEDIAN_QUERY_TEMPLATE`'s `dates`
  CTE selects the full unbounded date range from the canonical PIT view
  (`CANONICAL_PIT_VIEW_NAME`). This is architecturally consistent with
  `BUILD_STRATEGY == "one_shot_full_rebuild"` (incremental/partial build is
  forbidden; see `test_no_forbidden_names.py`).
- `resolve_scope()` remains an unimplemented shell
  (`test_producer_surface.py::test_resolve_scope_is_shell`); requested scope
  is currently supplied only via direct `BuildScope(...)` construction by
  callers/tests.
- No existing materialized-scope query pattern exists anywhere in the
  repository for PF-B1 to build on. No analogous requested/materialized
  date-boundary policy exists in `ud_ratio.py` or its tests. This is a
  confirmed absence (repository-wide search performed), not an inferred one.

### Locked mechanism contract

1. PF-B1 observes the unbounded date-availability domain of the canonical
   PIT view. It does not apply the requested `BuildScope` as a SQL filter.

2. The unbounded observation is intentional and aligned with
   `one_shot_full_rebuild`: `compute()` consumes the full canonical source,
   while `BuildScope` expresses the requested intent whose support must be
   validated before producer entry.

3. PF-B1 passes only when:
   ```
   view_min <= requested_start
   AND
   view_max >= requested_end
   ```

4. PF-B1 validates outer-bound coverage only. It does not validate interior
   trading-date completeness, per-symbol completeness, or cross-sectional
   observation sufficiency. Full trading-calendar completeness, if required,
   belongs to a separate PF or disposition.

5. A successfully queried canonical scope whose two observed boundaries are
   both NULL is an empty-source validation failure. The returned
   `PreFlightResult` MUST have `passed=False` and carry a deterministic
   diagnostic identifiable as `PF_B1_EMPTY_CANONICAL_SCOPE`.

   Insufficient non-empty coverage (`view_min > requested_start` OR
   `view_max < requested_end`, with both boundaries non-NULL) is a distinct
   validation failure. The returned `PreFlightResult` MUST have
   `passed=False` and carry a deterministic diagnostic identifiable as
   `PF_B1_REQUESTED_SCOPE_NOT_COVERED`.

   An asymmetric NULL result (exactly one boundary is NULL) is NOT a valid
   empty-scope observation. It is a semantically uninterpretable result and
   MUST propagate through the non-shell operational-error channel.

6. DuckDB connection, source resolution, query execution, result-shape, or
   type-conversion failures are operational failures and MUST propagate as
   non-`PreFlightShellError` exceptions.

7. Requested and observed boundaries MUST be converted to domain-level
   `date` values before comparison. Raw DuckDB or Arrow result objects MUST
   NOT participate directly in scope comparison.

8. `requested_start > requested_end` MUST NOT be allowed to reach the
   coverage predicate unchecked.

   Classification note: reversed requested bounds are a domain-precondition
   failure, not a source-validation result and not a DuckDB/environment
   failure. Under the current three-channel GC-7 taxonomy, the failure MUST
   propagate through the non-shell exception channel and MUST NOT be
   converted into `PreFlightResult(passed=False)`. It is non-retryable;
   retry handling applicable to transient DuckDB failures MUST NOT be
   applied to this condition.

   Canonical invariant ownership belongs to `BuildScope`. Once `BuildScope`
   enforces the invariant at construction time (e.g. via `__post_init__`),
   this defensive PF-B1 guard is removed rather than translated into
   another PF-B1 branch. [BACKLOG note: `BuildScope` currently has no
   `__post_init__`; verified against `build_types.py`.]

### Representation boundary

Requested scope and materialized scope MUST be reduced to domain-level
date-boundary values before comparison. PF-B1 MUST NOT compare `BuildScope`
directly against a raw DuckDB cursor, Arrow reader, relation, or other
backend-specific result object.

`BuildScope` remains the canonical requested-scope representation. Its
fields are semantically named `requested_start` and `requested_end`;
therefore it MUST NOT be repurposed as the materialized-scope carrier
merely because its structural shape is compatible (primitive/structural
compatibility must not be treated as semantic compatibility).

The implementation MAY use:
- two explicitly named local `date` values such as `materialized_start`
  and `materialized_end`; or
- a private immutable value object with explicit materialized-scope
  semantics.

This disposition does not authorize a new public API or require a new
exported type. It requires semantic alignment before comparison and
prohibits comparison between a domain value and a backend artifact.

### Governance metadata
- **Status:** LOCKED
- **Previous D-PR entry:** D-PR2C-5
- **Entry repository anchor:** dc6c32b873b4797fa311d50d3c27afd20a10e208
- **Ledger MD5 at session entry:** 8e2dd4db68581953854986b727aa661d
- **Commit SHA:** `6989d170ca34fe534211174ee2bfc51005691fc3`
- **Ledger version at lock:** v0.1.3
- **Record class:** ORIGINAL LOCKED DISPOSITION

---

## D-PR2C-7 — PR-2C.1 Implementation Order Selection

### Status
LOCKED

### Decision question
Given locked PF-B1 (D-PR2C-6) and PF-B2 (D-PR2C-3) mechanisms, which check
should become the first real rider-closing check in PR-2C.1?

### Finding F-7 — mechanism maturity asymmetry

Previous implementation-order discussions (including this ledger's own
IN-3) treated PF-B1 as the "smaller" implementation, on the assumption that
PF-B1 required only reading existing data while PF-B2 required building an
AST analyzer.

Repository inspection performed during D-PR2C-6 invalidated that
assumption. PF-B1 required an entirely new mechanism contract (unbounded
observation, coverage semantics, a six-branch validation/operational
taxonomy, representation-boundary rules, and a defensive precondition
guard), authored de novo in this governance session with no corresponding
production implementation or repository-backed execution evidence.

PF-B2's mechanism, by contrast, was locked in D-PR2C-3 and its Layer
1/Layer 2 data-flow chain was verified against HEAD `compute.py:85-88,92`
at lock time — before this session began.

Implementation complexity therefore cannot be inferred from apparent
algorithmic simplicity alone. IN-3 is SUPERSEDED as an ordering basis by
this Finding.

### Finding F-8 — risk-source isolation (orthogonal to F-7)

PR-2C.1 is unavoidably the first rider-closing lifecycle transition
(Form 1/Form 2, see D-PR2C-8). This is a novel event regardless of which
check is selected.

Selecting a mechanism whose correctness has not yet been repository-
validated would stack two independent novel risk sources into the same
change: transition-mechanics correctness and mechanism correctness. Any
regression in such a PR could not be cleanly attributed to either source.

Mechanism maturity (F-7) and transition novelty are orthogonal dimensions.
This Finding holds independently of which check is currently more mature —
if mechanism maturity were to reverse in the future, F-8 would still
counsel introducing at most one previously unvalidated engineering
dimension per rider transition.

### Primary comparison table (neutral mechanics)

| Dimension | PF-B1 | PF-B2 |
|---|---|---|
| External dependency | Read-only DuckDB | Production source file (`compute.py`) |
| Mutable-state exposure | Yes | Negligible |
| Double invocation | Two DB observations | Duplicate static analysis |
| Core algorithm | Aggregate query + domain normalization + containment predicate | AST parse + two-layer data-flow binding |
| Failure branches | 6 (empty/symmetric-NULL, insufficient-coverage, asymmetric-NULL, DB/connection, reversed-bounds, generic operational) | 3 (Layer-1 literal violation, Layer-2 unresolved binding, infrastructure/parse failure) |
| Verified against current HEAD | No — mechanism authored de novo this session | Yes — verified against HEAD `compute.py` at D-PR2C-3 lock time |
| Determinism | Depends on live DB state at test time | Deterministic for fixed source bytes |
| Test fixture burden | Requires synthetic DB states for 6 branches, including a pathological asymmetric-NULL state that may require mocking a connection/cursor | Requires synthetic/static source files per branch, all reachable via ordinary Python source text |
| Flakiness surface | DB lock/catalog/connection state | Source resolution, analyzer completeness |
| First-transition value | Exercises the two-gate authority rule (D-PR2C-2) against real mutable external state for the first time | Exercises a complex fail-closed static analyzer with no TOCTOU exposure |

Deliberately excluded from this table: P0/severity classification, blast
radius of a wrong result. See "Consequence severity" below.

### Ordering criteria (defined, not pre-weighted)

- **Engineering landing risk** (formerly "Criterion A") — lower
  implementation and landing risk.
- **Governance validation value** (formerly "Criterion B") — higher
  governance value as the first real lifecycle
  transition (e.g. earliest validation of the D-PR2C-2 authority-rule
  hypothesis against real mutable state).

Engineering landing risk favors PF-B2 (Findings F-7, F-8). Governance
validation value favors PF-B1
(earliest exercise of mutable external state). These criteria point to
different answers; this is a real tension, not an artifact of insufficient
analysis.

### Consequence severity — independent analysis

PF-B2 protects an explicitly P0 lineage rule under spec §4.4.

PF-B1 protects source-coverage sufficiency for the declared build intent.
The current governance record does not assign this failure a formal
severity tier.

Therefore PF-B2 has a formally classified consequence, while PF-B1's
consequence is materially important but not formally tiered. This
difference is relevant to governance-value analysis, but it is NOT by
itself dispositive of implementation order, and is NOT invoked as the
deciding factor below.

Regardless of ordering choice, PF-B2's P0 lineage protection does not
become active until PF-B2 itself lands as a real check — this exposure is
a pre-existing condition of HEAD, not created by this disposition.
Selecting PF-B1 first would extend this pre-existing exposure window by
one additional PR cycle; selecting PF-B2 first does not extend it. This
delta is disclosed for completeness; it is not the basis of the decision
below.

### Decision rule

For the first rider-closing lifecycle transition, this disposition selects
**engineering landing risk** as the primary criterion.

Two independent grounds support this, both evidence-based:

1. **Mechanism maturity (Finding F-7).** PF-B2's mechanism was locked and
   verified against HEAD before this session began. PF-B1's mechanism was
   authored de novo in this session with no repository-backed execution
   evidence.

2. **Risk-stacking avoidance (Finding F-8).** PR-2C.1 already carries novel
   risk as the first PR to exercise the Form 1/Form 2 anchor-test lifecycle
   transition (D-PR2C-8). Landing an unverified mechanism in the same PR
   would compound two independent sources of uncertainty. Selecting the
   verified mechanism confines PR-2C.1's risk surface to transition
   mechanics alone.

This disposition therefore selects:
```
PR-2C.1 → PF-B2
PR-2C.2 → PF-B1
```

The authority-rule validation (D-PR2C-2's separation-of-duties model
against real mutable external state) is intentionally deferred by one
rider transition, not removed. This deferral is a byproduct of grounds 1
and 2 above; no P0-severity argument is invoked.

### Residual note

Grounds 1 and 2 materially narrow the range of reasonable ordering choices
but do not uniquely determine one. Selecting the verified mechanism first
reflects a sequencing principle (prefer isolating independent engineering
risks across successive PRs) rather than a mathematical consequence of the
repository evidence alone. This preference is disclosed explicitly rather
than being presented as an inevitable conclusion from the evidence.

### Extraction note (non-blocking, for future governance session)

Findings F-7 and F-8 above are scoped to PR-2C.1 ordering but their
underlying principles are not PR-2C-specific:

  F-7 → mechanism maturity must be evaluated independently of apparent
        algorithmic simplicity
  F-8 → do not stack independent novel engineering dimensions into the
        same governance transition when equivalent sequencing is
        available

A future governance session MAY consider extracting these findings if a
subsequent PR encounters an equivalent ordering problem. Examples could
include PR-3, PF-L, or other Track C governance work, but no specific
future PR is designated by this note.

This extraction is NOT required for D-PR2C-7 to remain LOCKED and does not
block this disposition's append. It also does not modify
`docs/governance/durable_principles.md`; F-7 and F-8 remain single-case
findings until repeated independent occurrences justify promotion into a
durable governance principle.

### Supersession

This disposition supersedes IN-3 (both the canonical-order and
alternative-order ladders it proposed) as the ordering basis for PR-2C.1.
IN-3 remains in the ledger as a historical, explicitly non-normative
Implementation Note; it must not be read as current governance guidance
for ordering after this disposition locks.

### Governance metadata
- **Status:** LOCKED
- **Cites:** D-PR2C-6 (PF-B1 mechanism), D-PR2C-3 (PF-B2 mechanism)
- **Does not cite:** IN-3 (superseded, see above)
- **Order implication:** PR-2C.1 = PF-B2, PR-2C.2 = PF-B1
- **Entry repository anchor:** dc6c32b873b4797fa311d50d3c27afd20a10e208
- **Ledger MD5 at session entry:** 8e2dd4db68581953854986b727aa661d
- **Commit SHA:** `6989d170ca34fe534211174ee2bfc51005691fc3`
- **Ledger version at lock:** v0.1.3
- **Record class:** ORIGINAL LOCKED DISPOSITION

---

## D-PR2C-8 — Anchor-Test Lifecycle Transition Contract

### Status
LOCKED

### Scope boundary
This disposition governs only the anchor-test transition triggered by the
first rider-closing check (per D-PR2C-7: PF-B2) becoming real. It does not
reopen mechanism content (D-PR2C-3, D-PR2C-6) or ordering (D-PR2C-7).

### Form 1 — default-registry shell tests

Governed tests (`tests/features/win_rate_21d/test_safety_gate.py`):
```
test_gate_raises_by_default
test_build_full_raises_preflight_shell_error_by_default
test_build_full_gate_error_is_still_notimplementederror
```

**Verified against HEAD (`pre_flight.py:387-397`):**
`verify_rider_closing_checks_are_real` aggregates across all members of
`RIDER_CLOSING_CHECKS` and raises `PreFlightShellError` only if
`shell_names` is non-empty. With PF-B2 becoming real, `RIDER_CLOSING_CHECKS`
still contains two remaining shells (PF-B1, PF-B6).

**Verified against HEAD (`test_safety_gate.py:176-181`, docstring on
`test_gate_raises_by_default`):** the test's own stated acceptance
criterion is triggered only "when all shells have become real."

**Contract:** Form 1 tests require NO restructuring when PF-B2 becomes
real. They remain valid, unmodified, exercising the two-remaining-shells
state. Any change to these three tests at PF-B2's transition is a
governance violation of this disposition and must be reverted or
separately justified.

### Form 2 — shell-parametrized vacuous-pass guard

Governed test (`tests/features/win_rate_21d/test_pre_flight_shell.py:78-84`):
```
test_pf_b_shells_do_not_pass_vacuously
```
parametrized over `[pf_b1_scope_check, pf_b2_canonical_source_check,
pf_b6_duckdb_writeability_check]`.

**Contract:**
- Remove `pf_b2_canonical_source_check` from the parametrization list.
- Retain `pf_b1_scope_check` and `pf_b6_duckdb_writeability_check`.
- Preserve `with pytest.raises(NotImplementedError):` verbatim for the
  remaining two.
- Do NOT delete or weaken the test function itself; do NOT collapse it
  into a non-parametrized form.

**Distinction from Form 1** (stated separately per the original kickoff's
explicit requirement): Form 1 tests exercise the aggregate default-registry
state and require no edit at PF-B2's transition. Form 2 exercises each
shell individually via parametrization and requires exactly one
parametrization-list removal per shell that transitions. These are
structurally different migrations triggered by the same event; neither
substitutes for the other.

### GC-6 — producer runtime-gate preservation

Governed test (`tests/features/win_rate_21d/test_safety_gate.py:700-758`):
```
test_build_full_runtime_gate_blocks_body_on_failed_result
```

**Verified against HEAD:** this test already monkeypatches
`RIDER_CLOSING_CHECKS` with three stub callables (`_passing`/`_failing`
factories) independent of any PF-B check's real/shell status. It requires
NO modification when PF-B2 becomes real.

**Prohibition** (restated from kickoff GC-6, made binding under this
disposition): at every point across the PF-B2, PF-B1, and PF-B6
transitions, at least one producer-level test MUST continue to exercise
the full chain:
```
first gate (verify_*) passes
→ second gate (run_*) receives passed=False
→ PreFlightExecutionError
→ body_enter_hook NOT called
→ compute NOT called
→ writer NOT called
```
A migration that leaves all producer-level tests stopping at `verify_*`
shell detection — such that deleting `run_rider_closing_checks()` from
`build_full()` would be invisible to CI — is a prohibited state under this
disposition, regardless of which PF-B check triggered the migration that
produced it.

### Non-reopening clause

This disposition does not evaluate, reference, or depend on:
- PF-B1 or PF-B2 mechanism content (owned by D-PR2C-6, D-PR2C-3
  respectively);
- implementation ordering rationale (owned by D-PR2C-7);
- TOCTOU or double-invocation semantics (owned by D-PR2C-6 §Q2, D-PR2C-3).

If a future PR-2C.2/.3 transition (PF-B1 or PF-B6 becoming real) requires
restating Forms 1/2/GC-6 for that specific check, the restatement follows
the same structural template as above without amending this disposition —
this disposition's contract is check-agnostic by construction (it never
named a specific check's internals, only registry-state arithmetic),
provided the registry lifecycle (RIDER_CLOSING_CHECKS membership, the
two-gate verify_*/run_* model) remains unchanged. A future refactor of the
registry model itself would require a new disposition rather than falling
under this one by extension.

### Governance metadata
- **Status:** LOCKED
- **Scope:** anchor-test lifecycle transition contract (Form 1, Form 2,
  GC-6)
- **Applies to:** the transition triggered by PF-B2 becoming real (per
  D-PR2C-7 ordering)
- **Cites:** D-PR2C-3 (verified evidence), D-PR2C-7 (ordering), original
  kickoff document (Question 4, GC-6)
- **Does not reopen:** PF-B1/PF-B2 mechanism, implementation ordering
  rationale, TOCTOU analysis
- **Entry repository anchor:** dc6c32b873b4797fa311d50d3c27afd20a10e208
- **Ledger MD5 at session entry:** 8e2dd4db68581953854986b727aa661d
- **Commit SHA:** `6989d170ca34fe534211174ee2bfc51005691fc3`
- **Ledger version at lock:** v0.1.3
- **Record class:** ORIGINAL LOCKED DISPOSITION
