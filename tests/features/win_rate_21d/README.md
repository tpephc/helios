# win_rate_21d test suite

This directory contains **PR-1 governance skeleton tests only**.

## What these tests cover

- Locked constants (values, `Literal` type, SHA hex lengths).
- Manifest schema shape and validation (SD-A2-5 N-A2-5-6 v1.0.0).
  - Includes the `producer_id` == `PRODUCER_TABLE_NAME` lock (Issue 3
    disposition).
  - Includes `producer_code_sha` format acceptance for SHA-1 and SHA-256
    (Issue 1 disposition, forward-compat).
  - Includes `producer_config_hash` format check (Issue 2 disposition).
- Environment canonicalization enforcement (`LC_ALL=C.UTF-8`, `TZ=UTC`,
  `PYTHONHASHSEED=0`) at the manifest layer only.
- PF-B shell behavior: PF-B3 and PF-B4 are implementable now; PF-B1,
  PF-B2, PF-B6 raise `NotImplementedError` and MUST NOT return vacuous
  PASS.
- Guardrails preventing incremental-build drift (function names, keyword
  arguments, and Issue G attribute-call names).
- `stock_id` naming discipline (no `symbol_id` anywhere in added files).
- Raw price table isolation (no standalone raw-table reference in
  `producer.py`).

## What these tests DO NOT cover

The following are intentionally **out of scope** for PR-1 and belong to
later PRs:

- Producer computation (cross-sectional median, `n_obs_cross_section`,
  daily-return derivation).
- DuckDB reads or writes.
- Fixture writer / master ledger writer.
- Manifest emission with real build-time values (`content_hash`
  reproduction, `producer_code_sha` from `git rev-parse HEAD`, etc.).
- Environment canonicalization at process entry (the `LC_ALL`, `TZ`,
  `PYTHONHASHSEED` values in the manifest are asserted, but no code here
  actually sets them at process start).
- Consumer feature function `add_win_rate_21d`.
- PIT tests (`PIT-PROD-*`, `PIT-CONS-*`, `PIT-INT-*`).
- Integration tests against real `listed_market_daily_price_adj` data.
- Rider-closure end-to-end tests.

Do not add tests here for any of the above without first ensuring the
scope is appropriate for the PR under review.

## How to run

From the repository root:

```bash
python -m pytest tests/features/win_rate_21d/ -v
```

Expected outcome for PR-1:

- All tests pass.
- No `pytest.skip` markers are used; the shell checks pass by raising
  `NotImplementedError` inside the parametrized "no vacuous PASS" test.

## Governance references

- Executable Governance Navigation Document:
  `docs/research/win_rate_21d_producer_build_readiness.md` (commit
  `a110500`).
- SD-A2-1 through SD-A2-8 lock entries:
  `docs/research/win_rate_21d_a2_sd_locks.md`.
- Feature spec: `docs/features/win_rate_21d_spec.md` v0.1.0.
