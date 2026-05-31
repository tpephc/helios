# Helios Tracker v2 Migration Runbook

**Version:** 1.0.1  
**Applies to:** `research/forward_return_tracker.py` schema v1 → v2  
**Target host:** Nexus (`tradeagent@nexus:~/projects/helios`)  
**Date:** 2026-05-31  

---

## 1. Scope

This runbook governs the production migration of the forward return tracker from
schema v1 to v2. It covers:

- Destructive replacement of all v1 observations with v2 rows
- Schema additions: `forced_resolved`, `imputed_exit`, `imputation_reason`,
  `entry_slippage_bps`, `cost_bps`
- Resolution policy change: elapsed TWSE trading days (replacing price-count proxy)
- Forced resolution: 4-case missing-data policy with −100% haircut (long-only)
- CI method change: cluster-by-signal-date bootstrap (replacing iid t-interval)
- Diagnostic outputs: forced-case counts, cluster placement, with/without CI delta

**Out of scope for this migration:** exit contract, production screener, strategy gate
criteria calibration, Phase B bearish/TX futures, conflict score calibration.

---

## 2. Frozen Invariants

These are non-negotiable. If any invariant is violated at any phase, **ABORT**
immediately and follow the abort protocol in Section 8.

### INV-1 — Trading-Day Index Source

```
TWSE official calendar  = source of truth
daily_price_adj benchmark coverage  = reconciliation target (not the definition)
```

A TWSE-confirmed trading day on which the benchmark row is absent from
`daily_price_adj` is a **data error**, not a holiday. The tracker must:

- Block resolution for all signals until the gap is resolved or explicitly
  overridden
- Raise an alert
- Never silently treat a missing benchmark row as a non-trading day

Violation consequence: all in-progress signal elapsed-day counts are
systematically wrong from the gap date forward. This is a correlated, silent
distortion across the entire denominator.

### INV-2 — Backup Row Count Before DELETE

```
backup_count == v1_count  must hold before DELETE executes
```

A CREATE TABLE AS SELECT that silently under-captures rows (e.g., due to a WHERE
clause error) followed by an unchecked DELETE destroys data behind a false sense of
safety. Assert the counts match before issuing any DELETE.

### INV-3 — Rebuild Source Self-Sufficiency

```
every signal_id in v1 observations must resolve from the upstream signals table
```

The rebuild derives from `signals` table + `daily_price_adj` only. Any signal whose
entry metadata exists only in the observation rows — and not in the upstream signals
table — cannot be reconstructed after deletion. Assert zero orphaned signal IDs
before DELETE.

### INV-4 — Imputation Scope and Haircut Boundary

```python
# LONG_ONLY_INVARIANT — do not inherit for Phase B
# case-1 / case-3 boundary (post-entry price availability)
if post_entry_price_count >= 1:
    # case 1: normal halt — last available adj_close
    imputation_reason = "last_available_adj_close"
    net_return = (last_available_adj_close / entry_adj_open) - 1 - cost
else:
    # case 3: zero post-entry prices — conservative penalty
    # -100% is the worst-case bound for unlevered long cash-equity only.
    # NOT valid for: short strategies, leveraged products, futures, options.
    imputation_reason = "no_price_after_entry"
    net_return = -1.0
```

This boundary and haircut value are frozen for long cash-equity. **Phase B
(bearish / TX futures) must define its own imputation policy.** Do not allow this
implementation to be silently inherited.

### INV-5 — Empty-Table Window

The observation table may be empty only during the bounded DELETE → rebuild window.
Cron must be paused **before** the backup step and resumed **only after** report
validation passes. No scheduled job may execute against an empty or partially rebuilt
observation table.

---

## 3. Schema v2 Reference

New columns to be added in Phase D, after the backup is created and the row-count
assert passes. Run one statement at a time; some engines reject multi-column syntax.

```sql
ALTER TABLE forward_return_observations ADD COLUMN forced_resolved    BOOLEAN DEFAULT false;
ALTER TABLE forward_return_observations ADD COLUMN imputed_exit       BOOLEAN DEFAULT false;
ALTER TABLE forward_return_observations ADD COLUMN imputation_reason  TEXT;
ALTER TABLE forward_return_observations ADD COLUMN entry_slippage_bps DOUBLE;
ALTER TABLE forward_return_observations ADD COLUMN cost_bps           DOUBLE;
```

Updated constant in tracker source:

```python
TRACKER_SCHEMA_VERSION = 2
ENTRY_SLIPPAGE_BPS = 5.0   # matches harness minimum; was 0 in v1
```

---

## 4. Pre-Conditions Checklist

**Do not begin Phase A until every item is checked.**

### Code

- [ ] `TRACKER_SCHEMA_VERSION = 2` set in tracker
- [ ] `ENTRY_SLIPPAGE_BPS = 5.0` set in tracker
- [ ] Schema v2 `ALTER TABLE` migration SQL written and tested on dry-run DB
- [ ] Forced resolution logic implemented (4-case policy, INV-4 boundary)
- [ ] `forced_resolved`, `imputed_exit`, `imputation_reason` populated per row
- [ ] `entry_slippage_bps`, `cost_bps` stored per row
- [ ] Resolution trigger changed to elapsed TWSE trading days ≥ 20 (not price count)
- [ ] Cluster-by-signal-date bootstrap implemented with deterministic seed
- [ ] `INSERT` uses explicit column list (no `SELECT *`)
- [ ] Crisis regime added to breakdown loop
- [ ] Stuck-signal detector implemented (elapsed ≥ 20 AND resolved = false)
- [ ] Benchmark-calendar-gap detector script implemented

### Reports

- [ ] `forced_resolved_count` emitted in summary
- [ ] `imputed_exit_count` emitted in summary
- [ ] `no_price_after_entry_count` emitted in summary
- [ ] `forced_cases_by_signal_date` emitted (count per date)
- [ ] `bootstrap_ci_with_forced` and `bootstrap_ci_without_forced` both produced
- [ ] `ci_delta` and `mean_delta` (with vs without) emitted
- [ ] Effective n (unique signal_dates) reported alongside nominal n

### Dry-Run

- [ ] All code changes tested against a copied DB (see Phase B)
- [ ] Dry-run report reviewed and diagnostics sensible

---

## 5. Migration Phases

### Phase A — Benchmark Calendar Reconciliation

Confirm no trading-day gaps exist before touching any data.

```bash
ssh tradeagent@nexus
cd ~/projects/helios
export PATH=/home/tradeagent/.local/bin:$PATH

uv run python scripts/check_benchmark_calendar_gap.py --lookback-days 90
```

**Pass:** zero gaps reported for the trailing 90 trading days.  
**Fail:** ABORT. Do not proceed. Investigate `daily_price_adj` pipeline. A gap here
means elapsed-day counts for all in-progress signals are already unreliable; migrating
now locks in a corrupted v2 denominator.

---

### Phase B — Dry-Run Against DB Copy

Never run migration code against the production DB without a successful dry-run first.

```bash
# Fix the date at the start of the dry-run session to avoid cross-day drift
DRYRUN_DB=data/helios_dryrun_$(date +%Y%m%d).db

# Create a throwaway copy
cp data/helios.db "$DRYRUN_DB"

# Run full migration against the copy
HELIOS_DB_PATH="$DRYRUN_DB" \
  uv run python scripts/migrate_tracker_v2.py

# Run tracker rebuild against the copy
HELIOS_DB_PATH="$DRYRUN_DB" \
  uv run python research/forward_return_tracker.py

# Generate and review v2 report from the copy
HELIOS_DB_PATH="$DRYRUN_DB" \
  uv run python research/forward_return_tracker.py --report-only
```

Review dry-run report:

- [ ] Schema v2 columns present and populated
- [ ] `TRACKER_SCHEMA_VERSION = 2` in all rows
- [ ] Forced-resolution cases logged with correct imputation_reason
- [ ] Stuck-signal query returns zero
- [ ] Regime breakdown includes "crisis" bucket
- [ ] Bootstrap CI produced without error
- [ ] With-forced and without-forced reports both generated; delta is non-zero and
      sensible (not suspiciously identical)
- [ ] Reproducibility: run report twice with same seed → identical output

```bash
# Reproducibility check on dry-run DB (DRYRUN_DB must be set from above)
HELIOS_DB_PATH="$DRYRUN_DB" \
  uv run python research/forward_return_tracker.py --report-only --seed 42 \
  > /tmp/tracker_report_run1.txt

HELIOS_DB_PATH="$DRYRUN_DB" \
  uv run python research/forward_return_tracker.py --report-only --seed 42 \
  > /tmp/tracker_report_run2.txt

diff /tmp/tracker_report_run1.txt /tmp/tracker_report_run2.txt
# Must produce no output
```

**Fail on any item above:** fix code, re-run dry-run. Do not proceed to Phase C.

---

### Phase C — Pause Cron

```bash
crontab -e
```

Comment out the two tracker-dependent entries:

```cron
# 10 16 * * 1-5  ... forward_return_tracker.py    # PAUSED: tracker v2 migration
# 30 19 * * 1-5  ... run_evening_digest.py         # PAUSED: tracker v2 migration
```

Confirm pause:

```bash
crontab -l | grep -E "forward_return_tracker|evening_digest"
# Every matching line must begin with #
```

**Do not proceed until both lines are confirmed paused.**

---

### Phase D — Pre-Migration Asserts

Execute against the **production DB**. Steps must run in the order listed. The backup
is created before any DDL change so the v1 schema is preserved for restore purposes.

#### Step D-0: Capture v1 Column List

The ALTER TABLE in Step D-2 adds 5 new columns to the main table. After that point,
a `SELECT *` restore from the backup will fail due to column count mismatch. Capture
the v1 column list now, before any DDL runs, so the restore command in Section 8 can
use an explicit column list.

```bash
# SQLite — save v1 column names to file
sqlite3 data/helios.db "PRAGMA table_info(forward_return_observations);" \
  | awk -F'|' '{print $2}' \
  > /tmp/v1_column_list.txt
cat /tmp/v1_column_list.txt
# Verify: list must NOT yet contain forced_resolved, imputed_exit,
# imputation_reason, entry_slippage_bps, cost_bps
```

Keep `/tmp/v1_column_list.txt` for the session. If a restore becomes necessary,
build the INSERT column list from this file (see Section 8).

#### Assert D-1: Backup Row Count (INV-2)

```bash
# Set date variable for consistent table name throughout this session
MIGRATION_DATE=$(date +%Y%m%d)
echo "Migration date: $MIGRATION_DATE"
```

```sql
-- Create backup BEFORE ALTER TABLE (backup retains v1 schema)
CREATE TABLE forward_return_observations_backup_v1_{MIGRATION_DATE}
  AS SELECT * FROM forward_return_observations
     WHERE tracker_schema_version = 1;

-- Assert counts match
SELECT
  (SELECT COUNT(*) 
     FROM forward_return_observations_backup_v1_{MIGRATION_DATE})  AS backup_count,
  (SELECT COUNT(*) 
     FROM forward_return_observations 
    WHERE tracker_schema_version = 1)                               AS v1_count,
  CASE 
    WHEN (SELECT COUNT(*) FROM forward_return_observations_backup_v1_{MIGRATION_DATE})
       = (SELECT COUNT(*) FROM forward_return_observations WHERE tracker_schema_version = 1)
    THEN 'PASS' ELSE 'FAIL'
  END AS assert_d1;
```

**Pass:** `assert_d1 = PASS` and both counts are non-zero.  
**Fail:** ABORT. Do not run ALTER TABLE or DELETE. Investigate why backup
under-captured rows before re-attempting.

#### Step D-2: Run Schema Migration (ALTER TABLE)

Only run after Assert D-1 passes. The backup now exists with the v1 schema; the main
table gains 5 new columns. If this step fails, no rows have been deleted — the
migration can be retried after fixing the issue.

```bash
uv run python scripts/migrate_tracker_v2.py --schema-only
```

Or run the statements from Section 3 manually, one at a time.

Confirm new columns are present:

```bash
# SQLite
sqlite3 data/helios.db "PRAGMA table_info(forward_return_observations);" | grep -E \
  "forced_resolved|imputed_exit|imputation_reason|entry_slippage_bps|cost_bps"
# Must return 5 rows
```

#### Assert D-3: Rebuild Source Self-Sufficiency (INV-3)

```sql
-- Orphaned signal check: any signal_id in v1 rows that has no upstream record
SELECT o.signal_id
FROM forward_return_observations o
LEFT JOIN signals s ON s.signal_id = o.signal_id
WHERE o.tracker_schema_version = 1
  AND s.signal_id IS NULL;
```

**Pass:** query returns zero rows.  
**Fail:** ABORT. The returned signal_ids cannot be reconstructed from upstream after
deletion. Options: (a) locate the missing upstream record and insert it, or (b)
document the signal as permanently unrecoverable and obtain explicit sign-off before
proceeding. Do not silently DELETE signals that cannot be rebuilt.

---

### Phase E — Delete and Rebuild

Only proceed if **Assert D-1 and Assert D-3 both pass** and Step D-2 (ALTER TABLE) has completed successfully.

```sql
-- Delete all v1 rows
DELETE FROM forward_return_observations
WHERE tracker_schema_version = 1;
```

Immediately confirm table is empty:

```sql
SELECT COUNT(*) AS v1_remaining
FROM forward_return_observations
WHERE tracker_schema_version = 1;
-- Must return 0
```

Then run rebuild:

```bash
uv run python research/forward_return_tracker.py
```

Expected output: v2 rows written to `forward_return_observations`, forced-resolution
cases logged, schema version 2 in all rows. If rebuild exits with error, follow abort
protocol immediately — do not leave table empty and unmonitored.

---

### Phase F — Post-Migration Validation

```bash
uv run python research/forward_return_tracker.py --report-only --seed 42 \
  > /tmp/tracker_v2_report_production.txt
cat /tmp/tracker_v2_report_production.txt
```

Validation checklist:

- [ ] All rows have `tracker_schema_version = 2`
- [ ] All rows have `entry_slippage_bps = 5.0`
- [ ] All rows have `cost_bps` populated
- [ ] `forced_resolved_count` reported (value and list of affected signal_dates)
- [ ] `imputed_exit_count` reported
- [ ] `no_price_after_entry_count` reported
- [ ] `forced_cases_by_signal_date` reported
- [ ] `bootstrap_ci_with_forced` and `bootstrap_ci_without_forced` both present
- [ ] `ci_delta` and `mean_delta` both present and non-zero
- [ ] Effective n (unique signal_dates) reported alongside nominal n; effective n ≤ nominal n
- [ ] Stuck-signal query returns zero
- [ ] Crisis regime present in breakdown
- [ ] Reproducibility confirmed (re-run with `--seed 42` → identical output):

```bash
uv run python research/forward_return_tracker.py --report-only --seed 42 \
  > /tmp/tracker_v2_report_production_run2.txt

diff /tmp/tracker_v2_report_production.txt /tmp/tracker_v2_report_production_run2.txt
# Must produce no output
```

**Fail on any item:** investigate before resuming cron. The observation table is
populated (not empty) at this point, so there is no urgency to rush cron restoration.
Fix the issue in a subsequent migration attempt if needed; restore from backup if the
data is unusable.

---

### Phase G — Resume Cron

```bash
crontab -e
```

Uncomment both entries:

```cron
10 16 * * 1-5  ... forward_return_tracker.py
30 19 * * 1-5  ... run_evening_digest.py
```

Confirm:

```bash
crontab -l | grep -E "forward_return_tracker|evening_digest"
# Both lines must be active (no leading #)
```

After the next scheduled 16:10 run, verify:

- [ ] Tracker completes without error in system logs
- [ ] New rows written with `tracker_schema_version = 2`
- [ ] Evening digest (19:30) reads v2 rows and produces output

---

## 6. Backup Retention Policy

Table `forward_return_observations_backup_v1_{YYYYMMDD}` is safe to DROP only after
**all five conditions** are met:

1. v2 rebuild completed without error (Phase E pass)
2. v2 report generated and all Phase F checklist items verified
3. Report is reproducible from same inputs (diff is empty)
4. Forced-case diagnostics reviewed: counts, cluster placement, CI delta are
   understood and acceptable
5. At least one subsequent scheduled tracker run (16:10) completes normally and
   writes v2 rows

**Do not DROP the backup table as part of this runbook.** Schedule the DROP as a
separate explicit action after all five conditions are documented.

---

## 7. Dry-Run DB Retention Policy

File `data/helios_dryrun_{YYYYMMDD}.db` may be deleted after Phase F passes
(production report validates). It has no diagnostic value once production v2 is
confirmed good.

---

## 8. Abort Protocol

| Abort point | Data state | Recovery |
|---|---|---|
| Phase A or B fails | No data touched | Fix code or pipeline; re-run from Phase A |
| Phase C (cron pause) fails | No data touched | Confirm pause before proceeding |
| Phase D assert fails | No data touched; backup may exist | If backup created, verify it; do not DELETE; investigate |
| Phase E DELETE executed; rebuild fails | Table empty | Restore immediately from backup (see below); resume cron on v1; document failure |
| Phase F validation fails | Table rebuilt as v2 | Do not resume cron; investigate; if report is wrong, restore from backup and re-run migration |

**Restore from backup:**

```sql
-- Restore using the v1 column list saved in Step D-0.
-- SELECT * from the backup is safe (backup has v1 schema).
-- The INSERT column list must be explicit to exclude the 5 new v2 columns,
-- which will default to: false, false, NULL, NULL, NULL.
--
-- Build the column list from /tmp/v1_column_list.txt, then run:
INSERT INTO forward_return_observations (
    col1, col2, ...   -- replace with actual v1 column names from /tmp/v1_column_list.txt
)
SELECT * FROM forward_return_observations_backup_v1_{YYYYMMDD};

-- Verify row count restored (v1 rows only)
SELECT COUNT(*) AS v1_restored
FROM forward_return_observations
WHERE tracker_schema_version = 1;
-- Must equal original v1_count from Assert D-1
```

After restore: resume cron, document the failure, do not re-attempt migration in the
same session.

---

## 9. Remote Access

```bash
ssh tradeagent@nexus
cd ~/projects/helios
export PATH=/home/tradeagent/.local/bin:$PATH
```

---

*End of runbook. Next deliverable: forced resolution + cluster bootstrap code (items 4 and 6 of migration scope).*
