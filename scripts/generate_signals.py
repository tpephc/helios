#!/usr/bin/env python3
# scripts/generate_signals.py
"""Strategy → Signal pipeline.

Modes:
  (no flag)              預設今天，寫入 DB (signals 表, status=PENDING)
  --date YYYY-MM-DD      指定歷史日 (預設 dry-run, 只 print 不寫)
  --date X --commit      強制寫入 (replay mode)
  --symbols 2330,0050    限定 universe
  --dry-run              永遠不寫，只 print

Example:
  uv run python scripts/generate_signals.py                            # today, write
  uv run python scripts/generate_signals.py --date 2025-06-18          # replay, dry-run
  uv run python scripts/generate_signals.py --date 2025-06-18 --commit # replay, write

Version: v0.1.0 (2026-05-17)
Changelog:
  v0.1.0 (2026-05-17): Initial — TrendBreakout strategy, dry-run-by-default replay
"""
from __future__ import annotations

import argparse
import sys
from datetime import date as date_type
from datetime import datetime

from data.database import connect, init_schema
from storage.signals import save_signal
from strategies.base import Signal
from strategies.trend_breakout import TrendBreakoutStrategy
from utils.logger import get_logger

logger = get_logger(__name__)


def resolve_target_date(arg: str | None) -> date_type:
    if arg:
        return date_type.fromisoformat(arg)
    with connect(read_only=True) as conn:
        row = conn.execute("SELECT MAX(date) FROM daily_features").fetchone()
    if not row or not row[0]:
        raise SystemExit("❌ daily_features 為空，請先跑 scripts/compute_features.py")
    return row[0]


def print_signal(sig: Signal) -> None:
    print(
        f"  [{sig.strategy}] {sig.side.upper():4s} {sig.stock_id:8s} "
        f"@ {sig.entry_price:.2f}  ATR={sig.entry_atr:.2f}  "
        f"score={sig.score:.2f}  regime={sig.regime}"
    )
    for r in sig.reason:
        print(f"     · {r}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run strategies for a given date")
    parser.add_argument("--date", type=str, help="YYYY-MM-DD (預設最新 daily_features 日期)")
    parser.add_argument("--symbols", type=str, help="逗號分隔 (限定 universe)")
    parser.add_argument(
        "--commit", action="store_true",
        help="在 --date 模式下強制寫入 DB (預設 dry-run)",
    )
    parser.add_argument("--dry-run", action="store_true", help="永遠不寫，只 print")
    args = parser.parse_args()

    init_schema()

    target = resolve_target_date(args.date)
    symbols = (
        [s.strip() for s in args.symbols.split(",") if s.strip()]
        if args.symbols else None
    )

    # 決定是否寫 DB:
    # - --dry-run                       → 永遠不寫
    # - 沒給 --date                     → 寫 (live mode, today)
    # - 給 --date 但沒 --commit         → 不寫 (replay, 預設 dry-run)
    # - 給 --date + --commit            → 寫 (replay 寫入)
    write_to_db = not (args.dry_run or (args.date and not args.commit))

    mode = "LIVE" if (write_to_db and not args.date) else (
        "REPLAY-COMMIT" if write_to_db else "DRY-RUN"
    )
    print(f"Helios generate_signals — {datetime.now().isoformat(timespec='seconds')}")
    print(f"Target date: {target}  Mode: {mode}")
    if symbols:
        print(f"Symbols filter: {symbols}")
    print()

    # 跑所有 strategies
    strategies = [TrendBreakoutStrategy()]
    all_signals: list[Signal] = []
    for strat in strategies:
        sigs = strat.generate_signals(as_of=target, symbols=symbols)
        all_signals.extend(sigs)
        print(f"[{strat.name}] generated {len(sigs)} signal(s)")

    print()
    if not all_signals:
        print("(no signals)")
        return 0

    print(f"Generated {len(all_signals)} signal(s):")
    print()
    for sig in all_signals:
        print_signal(sig)
        print()

    # 寫入
    if write_to_db:
        n_written = 0
        for sig in all_signals:
            try:
                signal_id = save_signal(
                    symbol=sig.stock_id,
                    strategy=sig.strategy,
                    signal_type=sig.side,
                    score=sig.score,
                    price=sig.entry_price,
                    signal_date=target,
                    reason=sig.reason,
                    entry_atr=sig.entry_atr,
                    regime=sig.regime,
                    metadata=sig.metadata,
                )
                logger.info(
                    "signal_written",
                    signal_id=signal_id, stock_id=sig.stock_id,
                    strategy=sig.strategy, score=sig.score,
                )
                n_written += 1
            except Exception as e:
                logger.exception("signal_save_failed", stock_id=sig.stock_id)
                print(f"  ✗ Failed to save {sig.stock_id}: {e}")
        print(f"✓ Wrote {n_written} signals to DB (status=PENDING)")
    else:
        print(f"(DRY-RUN: {len(all_signals)} signals NOT written to DB)")
        if args.date and not args.commit:
            print("    add --commit to write (replay mode default is dry-run)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
