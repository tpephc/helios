# scripts/validate_install.py
"""Helios v0.1.3 安裝驗證腳本。

驗證範圍：
- Python 版本與必要套件
- .env 設定 (FinMind token 等)
- 目錄權限 (data/, logs/)
- DuckDB schema 建立
- Config YAML 載入
- Logger 初始化
- Storage 層 (signals/orders/positions/snapshots) 端到端
- Trading calendar
- (可選) FinMind API 連線

執行：
  uv run python scripts/validate_install.py             # 基本檢查
  uv run python scripts/validate_install.py --with-api  # 含 FinMind 連線

Exit code: 0 = 全部 PASS, 1 = 有 FAIL

Version: v0.1.0 (2026-05-16)
Changelog:
  v0.1.0 (2026-05-16): Initial implementation
"""
from __future__ import annotations

import argparse
import platform
import sys
import traceback
from datetime import date, datetime
from pathlib import Path

# ─────────────────────────────────────────────────────────────
# 不依賴 helios 任何 import，先做 Python 與套件檢查
# ─────────────────────────────────────────────────────────────

RESULTS: list[tuple[str, str, str]] = []  # (status, name, details)


def record(name: str, ok: bool, details: str = "") -> bool:
    status = "PASS" if ok else "FAIL"
    RESULTS.append((status, name, details))
    icon = "✓" if ok else "✗"
    print(f"  {icon} [{status}] {name}{('  → ' + details) if details else ''}")
    return ok


def section(title: str) -> None:
    print(f"\n{'='*60}\n{title}\n{'='*60}")


# ─────────────────────────────────────────────────────────────
# Checks
# ─────────────────────────────────────────────────────────────


def check_python() -> bool:
    section("1. Python 環境")
    pv = sys.version_info
    record("Python >= 3.12", pv >= (3, 12),
           f"current = {pv.major}.{pv.minor}.{pv.micro}")
    record("Platform", True, f"{platform.system()} {platform.machine()}")
    return pv >= (3, 12)


def check_packages() -> bool:
    section("2. 必要套件")
    REQUIRED = [  # noqa: N806 — local constant list
        "polars", "pandas", "duckdb", "pydantic", "pydantic_settings",
        "yaml", "dotenv", "httpx", "tenacity", "structlog",
    ]
    all_ok = True
    for pkg in REQUIRED:
        try:
            __import__(pkg)
            record(f"import {pkg}", True)
        except ImportError as e:
            record(f"import {pkg}", False, str(e))
            all_ok = False
    return all_ok


def check_working_dir() -> bool:
    section("3. 工作目錄")
    cwd = Path.cwd()
    # 應該在 helios 專案根 (有 pyproject.toml 與 config/ 等)
    has_pyproject = (cwd / "pyproject.toml").exists()
    has_config = (cwd / "config").is_dir()
    has_data = (cwd / "data").is_dir()
    ok = has_pyproject and has_config and has_data
    record("在 helios/ 專案根目錄執行",
           ok, f"cwd = {cwd}")
    if not ok:
        print("      → 請 cd 到 helios/ 後重試: cd /path/to/helios && uv run python scripts/validate_install.py")
    return ok


def check_env_file() -> bool:
    section("4. .env 設定")
    env_path = Path(".env")
    if not env_path.exists():
        record(".env 存在", False, ".env 檔案找不到")
        print("      → 執行: cp .env.example .env 後填入 FINMIND_TOKEN")
        return False
    record(".env 存在", True)

    # 讀取 .env 簡易解析
    env_content = env_path.read_text(encoding="utf-8")
    has_token = False
    timezone = None
    for line in env_content.splitlines():
        line = line.strip()
        if line.startswith("FINMIND_TOKEN=") and len(line) > len("FINMIND_TOKEN="):
            has_token = True
        if line.startswith("TIMEZONE="):
            timezone = line.split("=", 1)[1].strip()

    record("FINMIND_TOKEN 已填", has_token,
           "" if has_token else "免費版仍可跑 anonymous mode 但限速更嚴")
    record("TIMEZONE 設定", timezone is not None,
           f"= {timezone}" if timezone else "預設 Asia/Taipei")
    return True


def check_settings_load() -> bool:
    section("5. Settings 載入")
    try:
        from config.settings import (
            get_settings,
            load_risk_limits,
            load_strategy_config,
            load_universe,
        )
        s = get_settings()
        record("config.settings 載入", True, f"env={s.env}, mode={s.mode}")

        universe = load_universe()
        record("universe.yaml 載入", True,
               f"{len(universe.get('universes', {}))} universes 定義")

        strat = load_strategy_config()
        record("strategy_config.yaml 載入", True,
               f"{len(strat.get('strategies', {}))} strategies")

        risk = load_risk_limits()
        regimes = list(risk.get("regime_policy", {}).keys())
        record("risk_limits.yaml 載入", True,
               f"regimes: {', '.join(regimes)}")
        return True
    except Exception as e:
        record("Settings 載入", False, f"{type(e).__name__}: {e}")
        traceback.print_exc()
        return False


def check_directories() -> bool:
    section("6. 目錄與權限")
    from config.settings import get_settings
    s = get_settings()
    all_ok = True
    for name, path in [("data_dir", s.data_dir), ("cache_dir", s.cache_dir),
                       ("log_dir", s.log_dir)]:
        if not path.exists():
            record(f"{name} 存在", False, str(path))
            all_ok = False
            continue
        try:
            test_file = path / ".helios_validate_test"
            test_file.write_text("x")
            test_file.unlink()
            record(f"{name} 可寫", True, str(path))
        except Exception as e:
            record(f"{name} 可寫", False, f"{path}: {e}")
            all_ok = False
    return all_ok


def check_logger() -> bool:
    section("7. Logger")
    try:
        from utils.logger import configure_logging, get_logger
        configure_logging()
        log = get_logger("validate")
        log.info("validation_test_event", check="logger")
        record("structlog JSON logger 初始化", True)
        return True
    except Exception as e:
        record("Logger 初始化", False, f"{type(e).__name__}: {e}")
        traceback.print_exc()
        return False


def check_duckdb() -> bool:
    section("8. DuckDB schema")
    try:
        from data.database import connect, init_schema, list_tables
        init_schema()
        tables = list_tables()
        expected = {
            "stock_info", "daily_price", "institutional_investors",
            "monthly_revenue", "signals", "orders", "snapshots",
            "ingest_watermark", "data_quality_log", "universe_snapshot",
        }
        missing = expected - set(tables)
        if missing:
            record("DuckDB tables 完整", False, f"missing: {missing}")
            return False
        record("DuckDB schema 建立", True,
               f"{len(tables)} tables: {', '.join(sorted(tables))}")

        # 確認 signals 表有 entry_atr (v0.1.1 升級)
        with connect(read_only=True) as conn:
            cols = conn.execute("DESCRIBE signals").fetchall()
        col_names = [c[0] for c in cols]
        has_atr = "entry_atr" in col_names
        record("signals.entry_atr 欄位存在 (v0.1.1)", has_atr,
               "ATR-drift expiry 必須" if not has_atr else "")

        has_expired_reason = "expired_reason" in col_names
        record("signals.expired_reason 欄位存在 (v0.1.1)", has_expired_reason)

        return has_atr and has_expired_reason
    except Exception as e:
        record("DuckDB schema", False, f"{type(e).__name__}: {e}")
        traceback.print_exc()
        return False


def check_storage_e2e() -> bool:
    section("9. Storage 端到端")
    try:
        from storage import orders, positions, signals

        # 用 unique stock_id 避免污染既有資料
        test_sym = f"_TEST_{datetime.now().strftime('%H%M%S')}"

        # 1. Signal lifecycle
        sid = signals.save_signal(
            symbol=test_sym, strategy="validate", signal_type="buy",
            score=0.7, price=100.0, entry_atr=2.0,
            reason=["install validation test"],
        )
        record("save_signal", bool(sid), f"signal_id={sid[:8]}...")

        # 2. update_approval (UPDATE...RETURNING)
        ok = signals.update_approval(sid, "APPROVED", approved_by="validate")
        record("update_approval (atomic)", ok)

        # 3. record_order
        oid = orders.record_order(test_sym, "buy", 1000, signal_id=sid)
        record("record_order", bool(oid), f"order_id={oid[:8]}...")

        # 4. update_order_status
        ok = orders.update_order_status(oid, "filled", filled_qty=1000, avg_price=100.5)
        record("update_order_status", ok)

        # 5. has_duplicate_recent with exclude (v0.1.1 fix)
        no_dup = not orders.has_duplicate_recent(test_sym, "buy", exclude_order_id=oid)
        record("has_duplicate_recent (exclude self)", no_dup)

        # 6. compute_current_positions
        pos = positions.compute_current_positions()
        has_test = test_sym in pos and pos[test_sym].quantity == 1000
        record("compute_current_positions", has_test,
               f"qty={pos.get(test_sym, None).quantity if has_test else 'missing'}")

        # 7. ATR drift expiry (v0.1.1 batch fix)
        sid2 = signals.save_signal(
            symbol=test_sym, strategy="validate", signal_type="sell",
            score=0.7, price=100.0, entry_atr=2.0,
            reason=["drift test"],
        )
        n = signals.expire_drifted({test_sym: 102.0}, max_drift_atr=0.5)
        # drift = 2.0 / 2.0 = 1.0 > 0.5 → 應該被 expire
        sig2 = signals.get_signal(sid2)
        record("expire_drifted (batch)", n == 1 and sig2.approval_status == "EXPIRED_DRIFT",
               f"expired={n}, status={sig2.approval_status}")

        return all([sid, ok, oid, no_dup, has_test, n == 1])
    except Exception as e:
        record("Storage e2e", False, f"{type(e).__name__}: {e}")
        traceback.print_exc()
        return False


def check_calendar() -> bool:
    section("10. Trading calendar")
    try:
        from market import is_trading_day, previous_trading_day

        # 週末判斷
        sat = date(2026, 5, 16)  # 2026/5/16 是週六
        record("週六非交易日", not is_trading_day(sat))

        # 春節判斷 (在 fallback 表內)
        cny = date(2026, 2, 17)
        record("春節非交易日", not is_trading_day(cny))

        # 前後找日子
        mon = date(2026, 5, 18)
        prev = previous_trading_day(mon)
        record("週一的前一交易日 = 週五", prev == date(2026, 5, 15),
               f"got {prev}")

        return True
    except Exception as e:
        record("Calendar", False, f"{type(e).__name__}: {e}")
        traceback.print_exc()
        return False


def check_finmind_api() -> bool:
    section("11. FinMind API (optional)")
    try:
        from data.fetcher import DataFetcher

        with DataFetcher() as fetcher:
            # 抓股票基本資料表 (最小 query)
            result = fetcher.stock_info()
            if result.data.is_empty():
                record("FinMind stock_info", False, "回傳空 (token 錯誤或網路問題?)")
                return False

            n = result.data.height
            record("FinMind stock_info", True,
                   f"fetched {n} stocks (source={result.source})")

            # 抓一檔最小資料試試
            from datetime import date, timedelta
            end = date.today()
            start = end - timedelta(days=14)
            result = fetcher.daily_price("2330", start, end)
            record("FinMind daily_price (2330)", result.rows > 0,
                   f"rows={result.rows}, issues={result.quality_issues}")

        return True
    except Exception as e:
        record("FinMind API", False, f"{type(e).__name__}: {e}")
        traceback.print_exc()
        return False


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="Helios v0.1.3 install validation")
    parser.add_argument(
        "--with-api", action="store_true",
        help="包含 FinMind API 連線測試 (需要 FINMIND_TOKEN)",
    )
    args = parser.parse_args()

    print("Helios v0.1.3 Install Validation")
    print(f"Started: {datetime.now().isoformat(timespec='seconds')}")

    # 前 3 個檢查無依賴關係，先跑
    if not check_python():
        return _summary()
    if not check_packages():
        return _summary()
    if not check_working_dir():
        return _summary()

    # 後續檢查依賴前面
    check_env_file()
    if not check_settings_load():
        return _summary()
    check_directories()
    check_logger()
    if not check_duckdb():
        return _summary()
    check_storage_e2e()
    check_calendar()

    if args.with_api:
        check_finmind_api()
    else:
        print("\n11. FinMind API (跳過，使用 --with-api 啟用)")

    return _summary()


def _summary() -> int:
    print(f"\n{'='*60}")
    print("Summary")
    print('='*60)
    passes = sum(1 for r in RESULTS if r[0] == "PASS")
    fails = sum(1 for r in RESULTS if r[0] == "FAIL")
    total = len(RESULTS)
    print(f"  PASS: {passes}/{total}")
    print(f"  FAIL: {fails}/{total}")

    if fails > 0:
        print("\nFailed checks:")
        for status, name, details in RESULTS:
            if status == "FAIL":
                print(f"  ✗ {name}{('  → ' + details) if details else ''}")
        print("\nRecommended next steps:")
        print("  1. 看上面 traceback 找 root cause")
        print("  2. 確認 'uv sync' 跑過、'.env' 設定正確、cd 在 helios/ 根目錄")
        print("  3. 仍卡關回貼 fail 訊息")
        return 1

    print("\n✓ 全部通過。Helios v0.1.3 環境就緒。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
