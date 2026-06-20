#!/usr/bin/env python3
# scripts/run_signal_preview.py
"""Entry signal preview — v0.1.15. Today's trend_breakout_v1 candidates.

Bypasses the T+1 fill gate: generates signals for the latest feature date
without requiring next-day price data.  Does NOT write to the signals table
and does NOT initiate the approval flow.  Informational only.

The formal approval flow runs via daily_run.py at the next trading day's
16:00 cron.

generate_signals() is a pure function with no DB side effects (confirmed:
strategies/trend_breakout.py contains no INSERT/UPDATE/execute calls).

Usage:
    uv run python scripts/run_signal_preview.py
    uv run python scripts/run_signal_preview.py --as-of 2026-05-22
    uv run python scripts/run_signal_preview.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from datetime import date as date_type

from communication.telegram import TelegramBot, TelegramConfig
from communication.telegram.sender import push_simple
from strategies.trend_breakout import TrendBreakoutStrategy
from utils.logger import get_logger
from utils.trading_dates import resolve_as_of
from market.trading_calendar import is_trading_day

logger = get_logger(__name__)


def build_preview_message(as_of: date_type) -> str | None:
    """Generate signal candidates and return a formatted message.

    Args:
        as_of: Signal evaluation date.  Must have features in daily_features.

    Returns:
        Formatted Telegram message string, or None if no signals found.
    """
    strategy = TrendBreakoutStrategy()
    signals = strategy.generate_signals(as_of=as_of)

    if not signals:
        logger.info("signal_preview_no_candidates", as_of=str(as_of))
        return None

    # Batch load company short names
    from data.database import connect
    symbol_ids = [sig.stock_id for sig in signals]
    placeholders = ",".join("?" * len(symbol_ids))
    with connect(read_only=True) as conn:
        name_rows = conn.execute(
            f"SELECT stock_id, short_name FROM company_metadata WHERE stock_id IN ({placeholders})",
            symbol_ids,
        ).fetchall()
    name_map: dict[str, str] = {r[0]: r[1] for r in name_rows if r[1]}

    signals_sorted = sorted(signals, key=lambda s: s.score, reverse=True)

    lines = [f"📋 明日進場候選 ({as_of})", ""]

    for i, sig in enumerate(signals_sorted, 1):
        meta = sig.metadata or {}
        breakout_pct = meta.get("breakout_strength_pct", 0)
        rel_vol = meta.get("rel_volume_20", 0)
        rsi = meta.get("rsi_14", 0)
        donchian_prev = meta.get("donchian_high_prev", 0)
        name = name_map.get(sig.stock_id, "")
        lines.append(
            f"{i}. {sig.stock_id} {name}  {sig.entry_price:.1f}"
            f"  ★{sig.score:.2f}"
            f"  突破{donchian_prev:.0f}(+{breakout_pct:.1f}%)"
            f"  量{rel_vol:.1f}x"
            f"  RSI{rsi:.0f}"
        )

    lines.append("")
    lines.append("⚙️ 正式核准請求將於下個交易日 16:00 推送")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="v0.1.15 signal preview")
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.as_of is None:
        today = date_type.today()
        if not is_trading_day(today):
            logger.info("signal_preview_non_trading_day", date=str(today))
            print(f"{today} is not a trading day; exiting")
            return 0

    as_of = resolve_as_of(args.as_of)
    logger.info("signal_preview_start", as_of=str(as_of))

    message = build_preview_message(as_of)
    if message is None:
        print(f"[signal_preview] {as_of}: 無候選訊號")
        return 0

    if args.dry_run:
        print(message)
        return 0

    tg_cfg = TelegramConfig.from_env()
    if tg_cfg is None:
        logger.warning("signal_preview_no_telegram_config")
        print(message)
        return 0

    bot = TelegramBot(tg_cfg)
    push_simple(bot, message)
    logger.info("signal_preview_sent", as_of=str(as_of))
    return 0


if __name__ == "__main__":
    sys.exit(main())
