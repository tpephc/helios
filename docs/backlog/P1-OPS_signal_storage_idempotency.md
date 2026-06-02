# P1-OPS — Signal Storage Idempotency

**Priority:** P1  
**Authored:** 2026-06-02  
**Status:** OPEN  
**Related hotfix:** 96391af fix(entries): guard duplicate active signals before save

---

## Problem

`save_signal()` currently generates a new `uuid4()` on every call and inserts
unconditionally. There is no DB-level constraint preventing two rows with the
same `(symbol, strategy, signal_type, signal_date)` from coexisting.

The application-level guard added in the hotfix (`_has_active_signal_for()`)
prevents active duplicates in the happy path but has two known gaps:

1. **Race condition (TOCTOU):** Two processes checking simultaneously before
   either inserts will both pass the guard and both insert.

2. **Terminal-state re-generation:** A signal that was REJECTED/EXPIRED/TIMEOUT
   can be regenerated with a new `signal_id` on a rerun. Whether this is
   correct behaviour for a Signal Event semantic is unresolved.

---

## Required Fix

### 1. `save_signal()` must be idempotent-returning

```python
@dataclass(frozen=True)
class SaveSignalResult:
    signal_id: str
    created: bool   # False = existing signal returned, no new row inserted
```

Conflict path must return the canonical `signal_id` of the existing row,
not `None` and not raise.

### 2. DB UNIQUE constraint

```sql
UNIQUE (symbol, strategy, signal_type, signal_date)
```

Combined with INSERT ... ON CONFLICT DO UPDATE RETURNING signal_id,
this makes the storage layer the authoritative guard.

### 3. Caller updates

All callers must:
- Use `result.signal_id` instead of bare string return
- Skip Telegram notification when `result.created = False`
- Skip `_auto_approve_and_fill()` when `result.created = False`

Callers to update (21 call sites total):
- `scripts/process_entries.py` (4)
- `scripts/generate_signals.py` (1)
- `scripts/dev_push_signal.py` (1)
- `scripts/validate_install.py` (2)
- `tests/test_state_machine.py` (11)
- `tests/invariants/test_semantic_invariants.py` (2)
- `storage/signals.py` (1 internal)

### 4. Migration

Existing duplicate rows (REJECTED status, same event key) must be resolved
before adding the UNIQUE constraint:
- Keep only the earliest row per canonical key
- Delete remaining duplicates
- Then apply UNIQUE constraint via schema migration

---

## Acceptance Criteria

```text
1. save_signal() returns SaveSignalResult(signal_id, created)
2. Repeated calls with same (symbol, strategy, signal_type, signal_date)
   return the same signal_id with created=False
3. DB UNIQUE constraint enforced on canonical event key
4. All callers updated; no duplicate Telegram notifications on rerun
5. Existing duplicate rows cleaned up before constraint migration
```
