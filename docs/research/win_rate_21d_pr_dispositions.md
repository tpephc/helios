# PR-Level Disposition Ledger — `win_rate_21d`

**Document ID:** `win_rate_21d_pr_dispositions`
**Version:** v0.1.0
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
- **Commit SHA:** `<TBD — backfill after lock commit>`
- **Entry repository anchor:** `41e8e1e`
- **Previous D-PR entry:** D-PR2C-3
- **Ledger version at lock:** v0.1.1
- **Previous ledger tail md5:** `c1f6086fc7b479bc89ba24192c98eefc`
- **New ledger tail md5 after append:** `<TBD>`
- **Record class:** ORIGINAL LOCKED DISPOSITION
- **Evidence basis:** Original disposition; grounded in observed HEAD
  Ruff output and `pyproject.toml:67-82`.
