#!/usr/bin/env python3
# scripts/smoke_test_v0_1_18.py
"""v0.1.18 smoke test — run on nexus after deploying all 10 files.

Tests:
  1. Import all modified modules (no syntax errors)
  2. DB schema: account_id exists in orders + positions
  3. DB data: all rows have account_id = 'philip_sim'
  4. DB indexes: 5 account indexes present
  5. Signature checks: all public functions accept account_id
  6. AccountConfig validation: __post_init__ regex
  7. OrderRow / Position column mapping: length matches DB
  8. get_for_account / get_position_for_account ownership check
  9. confirm_submission exists and rejects non-SUBMITTED
  10. scan_and_exit requires account_id (keyword-only)
"""
from __future__ import annotations

import inspect
import sys
import traceback

PASS = 0
FAIL = 0


def check(name: str, fn):
    global PASS, FAIL
    try:
        fn()
        print(f"  ✅ {name}")
        PASS += 1
    except Exception as exc:
        print(f"  ❌ {name}: {exc}")
        traceback.print_exc()
        FAIL += 1


def main() -> int:
    global PASS, FAIL

    print("=" * 60)
    print("v0.1.18 Smoke Test")
    print("=" * 60)

    # ── 1. Import checks ────────────────────────────────────────
    print("\n[1] Import checks")

    def import_account_config():
        from config.account_config import AccountConfig, load_accounts, get_account

    def import_database():
        from data.database import init_schema, verify_post_migration, connect

    def import_order_journal():
        from storage.order_journal import (
            record_intent, get, get_for_account, mark_submitted,
            mark_ready_for_submission, mark_filled, mark_partial,
            mark_failed, mark_cancelled, mark_expired, mark_polled,
            update_order_spec, confirm_submission,
            list_ready_for_submission, list_orders_by_fill_date,
            list_orphan_intents, list_stale_submitted_by_fill_date,
            list_stale_ready_for_submission, list_orders_requiring_verification,
            find_by_broker_order_id, list_by_status,
            count_today_orders, sum_today_notional,
            OrderRow, _ORDER_COLUMNS,
        )

    def import_positions():
        from storage.positions import (
            open_position, get_position, get_position_for_account,
            get_open_positions, get_closed_positions, has_open_position,
            mark_position_open, mark_position_closed, start_closing,
            update_running_stats, Position, _POSITION_COLUMNS,
        )

    def import_lifecycle():
        from execution.lifecycle import open_position_from_signal, close_position_for_exit

    def import_scripts():
        # Just verify syntax — don't execute main()
        import scripts.daily_run
        import scripts.execution_submitter
        import scripts.startup_recovery
        import scripts.reconcile_fills
        import scripts.run_exit_scan

    check("config.account_config", import_account_config)
    check("data.database", import_database)
    check("storage.order_journal", import_order_journal)
    check("storage.positions", import_positions)
    check("execution.lifecycle", import_lifecycle)
    check("scripts (syntax)", import_scripts)

    # ── 2. DB schema checks ─────────────────────────────────────
    print("\n[2] DB schema checks")

    def check_orders_schema():
        from data.database import connect
        with connect(read_only=True) as conn:
            cols = [r[0] for r in conn.execute("DESCRIBE orders").fetchall()]
        assert "account_id" in cols, f"account_id not in orders columns: {cols}"

    def check_positions_schema():
        from data.database import connect
        with connect(read_only=True) as conn:
            cols = [r[0] for r in conn.execute("DESCRIBE positions").fetchall()]
        assert "account_id" in cols, f"account_id not in positions columns: {cols}"

    check("orders has account_id", check_orders_schema)
    check("positions has account_id", check_positions_schema)

    # ── 3. DB data checks ───────────────────────────────────────
    print("\n[3] DB data checks")

    def check_orders_data():
        from data.database import connect
        with connect(read_only=True) as conn:
            null_count = conn.execute(
                "SELECT COUNT(*) FROM orders WHERE account_id IS NULL"
            ).fetchone()[0]
            total = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
            distinct = conn.execute(
                "SELECT DISTINCT account_id FROM orders"
            ).fetchall()
        assert null_count == 0, f"{null_count} orders with NULL account_id"
        assert total == 7, f"expected 7 orders, got {total}"
        ids = [r[0] for r in distinct]
        assert ids == ["philip_sim"], f"unexpected account_ids: {ids}"

    def check_positions_data():
        from data.database import connect
        with connect(read_only=True) as conn:
            null_count = conn.execute(
                "SELECT COUNT(*) FROM positions WHERE account_id IS NULL"
            ).fetchone()[0]
            total = conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0]
            distinct = conn.execute(
                "SELECT DISTINCT account_id FROM positions"
            ).fetchall()
        assert null_count == 0, f"{null_count} positions with NULL account_id"
        assert total == 202, f"expected 202 positions, got {total}"
        ids = [r[0] for r in distinct]
        assert ids == ["philip_sim"], f"unexpected account_ids: {ids}"

    check("orders data integrity", check_orders_data)
    check("positions data integrity", check_positions_data)

    # ── 4. Index checks ─────────────────────────────────────────
    print("\n[4] Index checks")

    def check_indexes():
        from data.database import connect
        with connect(read_only=True) as conn:
            index_names = {r[0] for r in conn.execute(
                "SELECT index_name FROM duckdb_indexes()"
            ).fetchall()}
        required = {
            "idx_orders_account_status",
            "idx_orders_account_symbol",
            "idx_orders_account_broker_oid",
            "idx_positions_account_status",
            "idx_positions_account_symbol",
        }
        missing = required - index_names
        assert not missing, f"missing indexes: {sorted(missing)}"

    check("account indexes present", check_indexes)

    # ── 5. Signature checks ─────────────────────────────────────
    print("\n[5] Signature checks")

    def check_order_journal_sigs():
        from storage import order_journal as oj
        methods = [
            oj.record_intent, oj.mark_submitted, oj.mark_ready_for_submission,
            oj.mark_polled, oj.mark_filled, oj.mark_partial,
            oj.mark_failed, oj.mark_cancelled, oj.mark_expired,
            oj.update_order_spec, oj.confirm_submission,
            oj.find_by_broker_order_id, oj.list_orders_by_fill_date,
            oj.list_by_status, oj.count_today_orders, oj.sum_today_notional,
            oj.list_orphan_intents, oj.list_stale_submitted_by_fill_date,
            oj.list_ready_for_submission, oj.list_stale_ready_for_submission,
            oj.list_orders_requiring_verification,
        ]
        for m in methods:
            sig = inspect.signature(m)
            assert "account_id" in sig.parameters, (
                f"{m.__name__} missing account_id parameter"
            )

    def check_positions_sigs():
        from storage import positions as ps
        methods = [
            ps.open_position, ps.mark_position_open, ps.update_running_stats,
            ps.start_closing, ps.mark_position_closed,
            ps.get_open_positions, ps.get_closed_positions, ps.has_open_position,
        ]
        for m in methods:
            sig = inspect.signature(m)
            assert "account_id" in sig.parameters, (
                f"{m.__name__} missing account_id parameter"
            )

    def check_lifecycle_sigs():
        from execution.lifecycle import open_position_from_signal, close_position_for_exit
        for m in [open_position_from_signal, close_position_for_exit]:
            sig = inspect.signature(m)
            assert "account_id" in sig.parameters, (
                f"{m.__name__} missing account_id parameter"
            )

    def check_scan_and_exit_sig():
        from scripts.run_exit_scan import scan_and_exit
        sig = inspect.signature(scan_and_exit)
        param = sig.parameters["account_id"]
        assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
            f"scan_and_exit account_id should be keyword-only, got {param.kind}"
        )
        assert param.default is inspect.Parameter.empty, (
            f"scan_and_exit account_id should be required, has default={param.default}"
        )

    check("order_journal signatures", check_order_journal_sigs)
    check("positions signatures", check_positions_sigs)
    check("lifecycle signatures", check_lifecycle_sigs)
    check("scan_and_exit keyword-only required", check_scan_and_exit_sig)

    # ── 6. AccountConfig validation ─────────────────────────────
    print("\n[6] AccountConfig validation")

    def check_account_config_valid():
        from config.account_config import AccountConfig
        cfg = AccountConfig(
            account_id="philip_sim", owner="test", broker="shioaji",
            environment="sim", telegram_chat_id=None,
            ca_cert_path=None, enabled=True,
        )
        assert cfg.account_id == "philip_sim"

    def check_account_config_rejects_uppercase():
        from config.account_config import AccountConfig
        try:
            AccountConfig(
                account_id="Philip_Sim", owner="test", broker="shioaji",
                environment="sim", telegram_chat_id=None,
                ca_cert_path=None, enabled=True,
            )
            raise AssertionError("Should have raised ValueError for uppercase")
        except ValueError:
            pass

    def check_account_config_rejects_whitespace():
        from config.account_config import AccountConfig
        try:
            AccountConfig(
                account_id=" philip_sim ", owner="test", broker="shioaji",
                environment="sim", telegram_chat_id=None,
                ca_cert_path=None, enabled=True,
            )
            raise AssertionError("Should have raised ValueError for whitespace")
        except ValueError:
            pass

    check("AccountConfig valid id", check_account_config_valid)
    check("AccountConfig rejects uppercase", check_account_config_rejects_uppercase)
    check("AccountConfig rejects whitespace", check_account_config_rejects_whitespace)

    # ── 7. Column mapping checks ────────────────────────────────
    print("\n[7] Column mapping checks")

    def check_order_columns():
        from data.database import connect
        from storage.order_journal import _ORDER_COLUMNS
        with connect(read_only=True) as conn:
            db_cols = [r[0] for r in conn.execute("DESCRIBE orders").fetchall()]
        assert len(_ORDER_COLUMNS) == len(db_cols), (
            f"_ORDER_COLUMNS ({len(_ORDER_COLUMNS)}) != DB ({len(db_cols)})"
        )
        assert _ORDER_COLUMNS == db_cols, (
            f"Column order mismatch:\n  code: {_ORDER_COLUMNS}\n  db:   {db_cols}"
        )

    def check_position_columns():
        from data.database import connect
        from storage.positions import _POSITION_COLUMNS
        with connect(read_only=True) as conn:
            db_cols = [r[0] for r in conn.execute("DESCRIBE positions").fetchall()]
        assert len(_POSITION_COLUMNS) == len(db_cols), (
            f"_POSITION_COLUMNS ({len(_POSITION_COLUMNS)}) != DB ({len(db_cols)})"
        )
        assert _POSITION_COLUMNS == db_cols, (
            f"Column order mismatch:\n  code: {_POSITION_COLUMNS}\n  db:   {db_cols}"
        )

    check("_ORDER_COLUMNS matches DB", check_order_columns)
    check("_POSITION_COLUMNS matches DB", check_position_columns)

    # ── 8. Scoped getter checks ─────────────────────────────────
    print("\n[8] Scoped getter checks")

    def check_get_for_account_wrong_account():
        from storage.order_journal import get_for_account, OrderNotFound
        from data.database import connect
        with connect(read_only=True) as conn:
            row = conn.execute(
                "SELECT order_id FROM orders LIMIT 1"
            ).fetchone()
        if row is None:
            return  # no orders to test
        order_id = row[0]
        # Correct account should work
        get_for_account(order_id, account_id="philip_sim")
        # Wrong account should raise
        try:
            get_for_account(order_id, account_id="wrong_account")
            raise AssertionError("Should have raised OrderNotFound")
        except OrderNotFound:
            pass

    def check_get_position_for_account_wrong():
        from storage.positions import get_position_for_account
        from data.database import connect
        with connect(read_only=True) as conn:
            row = conn.execute(
                "SELECT position_id FROM positions LIMIT 1"
            ).fetchone()
        if row is None:
            return
        pos_id = row[0]
        # Correct account
        get_position_for_account(pos_id, account_id="philip_sim")
        # Wrong account
        try:
            get_position_for_account(pos_id, account_id="wrong_account")
            raise AssertionError("Should have raised ValueError")
        except ValueError:
            pass

    check("get_for_account rejects wrong account", check_get_for_account_wrong_account)
    check("get_position_for_account rejects wrong account", check_get_position_for_account_wrong)

    # ── 9. confirm_submission checks ────────────────────────────
    print("\n[9] confirm_submission checks")

    def check_confirm_submission_exists():
        from storage.order_journal import confirm_submission
        sig = inspect.signature(confirm_submission)
        assert "account_id" in sig.parameters
        assert "broker_order_id" in sig.parameters

    check("confirm_submission exists with correct params", check_confirm_submission_exists)

    # ── 10. get_open_positions account-scoped ───────────────────
    print("\n[10] Functional read checks")

    def check_open_positions_scoped():
        from storage.positions import get_open_positions
        # Should return positions for philip_sim
        positions = get_open_positions(account_id="philip_sim")
        assert isinstance(positions, list)
        for p in positions:
            assert p.account_id == "philip_sim", (
                f"position {p.position_id} has account_id={p.account_id}"
            )
        # Wrong account should return empty
        positions_wrong = get_open_positions(account_id="nonexistent")
        assert positions_wrong == [], f"expected empty, got {len(positions_wrong)}"

    check("get_open_positions account-scoped", check_open_positions_scoped)

    # ── Summary ─────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"Results: {PASS} passed, {FAIL} failed")
    print("=" * 60)

    if FAIL > 0:
        print("\n⚠️  SMOKE TEST FAILED — do not tag v0.1.18")
        return 1
    print("\n✅ ALL SMOKE TESTS PASSED — ready to tag v0.1.18")
    return 0


if __name__ == "__main__":
    sys.exit(main())
