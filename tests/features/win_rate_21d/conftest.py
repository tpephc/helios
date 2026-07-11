# tests/features/win_rate_21d/conftest.py
"""Shared fixtures for PR-2B.1 [4/4] producer wiring tests.

`test_compute.py` retains a behaviourally equivalent module-local
fixture because PR-2B.1 [4/4] does not modify existing test files.
A later test-infrastructure cleanup may consolidate both fixtures
into one shared source after independently verifying behavioural
equivalence.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from features.win_rate_21d.constants import CANONICAL_PIT_VIEW_NAME


@pytest.fixture()
def win_rate_21d_pit_db(tmp_path: Path) -> Path:
    """Materialize a DuckDB file containing a synthetic canonical PIT view.

    Row layout is behaviourally equivalent to the module-local fixture
    in ``test_compute.py``:

    - Dates: 2020-01-02, 2020-01-03, 2020-01-06.
    - 2020-01-02: seed prices (no prior close; no valid return).
    - 2020-01-03: 30 valid cross-sectional returns + one invalid
      (prev>0, curr=0 -> filtered by ``adj_close > 0`` guard).
    - 2020-01-06: 5 valid returns (below-threshold date; median
      should be NULL after applying MIN_CROSS_SECTION_OBS_PER_DATE).
    """
    db_path = tmp_path / "helios_wiring_e2e.duckdb"

    with duckdb.connect(str(db_path)) as conn:
        conn.execute(
            f"""
            CREATE TABLE {CANONICAL_PIT_VIEW_NAME} (
                stock_id VARCHAR,
                date DATE,
                adj_close DOUBLE
            )
            """
        )

        rows: list[tuple[str, str, float]] = []

        for i in range(1, 31):
            stock_id = f"S{i:03d}"
            rows.append((stock_id, "2020-01-02", 100.0))
            rows.append((stock_id, "2020-01-03", 101.0 + i))

        # Invalid current price on 2020-01-03; must be excluded.
        rows.append(("S031", "2020-01-02", 100.0))
        rows.append(("S031", "2020-01-03", 0.0))

        # Below-threshold date: only five valid returns.
        for i in range(1, 6):
            stock_id = f"S{i:03d}"
            rows.append((stock_id, "2020-01-06", 102.0 + i))

        conn.executemany(
            f"INSERT INTO {CANONICAL_PIT_VIEW_NAME} VALUES (?, ?, ?)",
            rows,
        )

    return db_path
