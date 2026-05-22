#!/usr/bin/env python3
# scripts/run_eod_position_alert.py
"""EOD position risk alert — v0.1.15. APPROACH and BREACH positions after close.

Point-in-time zone classification: last_close vs trailing stop.
Does NOT use the intraday state machine (that is for intraday_monitor.py).
BREACH positions will be auto-exited by run_exit_scan at T+1 open.
This alert is informational: operator awareness only, no override semantics.

Usage:
    uv run python scripts/run_eod_position_alert.py
    uv run python scripts/run_eod_position_alert.py --include-synthetic
    uv run python scripts/run_eod_position_alert.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date as date_type

from communication.telegram import TelegramBot, TelegramConfig
from communication.telegram.sender import push_simple
from data.database import connect
from execution.stop_logic import PriceZone, classify_zone, compute_stop_levels
from utils.logger import get_logger
from utils.trading_dates import resolve_as_of

logger = get_logger(__name__)


@dataclass
class _PositionAlert:
    symbol: str
    display_name: str
    shares: int
    last_close: float
    last_updated_date: date_type | None
    trailing_stop: float
    distance_pct: float
    zone: PriceZone


def build_position_alert_message(
    as_of: date_type,
    include_synthetic: bool = False,
) -> str | None:
    """Classify OPEN positions and return a risk alert message.

    stale_count tracks positions IN WARNING ZONES whose last_updated_date
    differs from as_of.  It does not count all stale positions, only those
    that appear in the alert.  The wording reflects this scope.

    Args:
        as_of: Reference date for message header and staleness check.
        include_synthetic: If False (default), exclude is_synthetic positions.

    Returns:
        Formatted Telegram message, or None if no positions in warning zones.
    """
    synthetic_filter = (
        ""
        if include_synthetic
        else "AND (is_synthetic = FALSE OR is_synthetic IS NULL)"
    )

    with connect(read_only=True) as conn:
        rows = conn.execute(f"""
            SELECT p.symbol,
                   COALESCE(cm.short_name, p.symbol) AS display_name,
                   p.shares, p.last_close, p.last_updated_date,
                   p.entry_atr, p.max_close_since_entry
            FROM   positions p
            LEFT JOIN company_metadata cm ON p.symbol = cm.stock_id
            WHERE  p.status                = 'OPEN'
              AND  p.entry_atr             > 0
              AND  p.max_close_since_entry > 0
              AND  p.last_close            IS NOT NULL
              AND  p.last_close            > 0
              {synthetic_filter}
            ORDER  BY p.symbol
        """).fetchall()

    if not rows:
        return None

    alerts: list[_PositionAlert] = []

    for sym, display_name, shares, last_close, last_upd, entry_atr, max_close in rows:
        last_close = float(last_close)
        levels = compute_stop_levels(float(max_close), float(entry_atr))
        zone = classify_zone(last_close, levels, PriceZone.NORMAL)

        if zone == PriceZone.NORMAL:
            continue

        distance_pct = (last_close - levels.trailing_stop) / levels.trailing_stop * 100
        alerts.append(_PositionAlert(
            symbol=sym,
            display_name=str(display_name),
            shares=int(shares),
            last_close=last_close,
            last_updated_date=last_upd,
            trailing_stop=levels.trailing_stop,
            distance_pct=distance_pct,
            zone=zone,
        ))

    if not alerts:
        return None

    # stale_count: warning-zone positions only (not all open positions)
    stale_count = sum(
        1 for a in alerts
        if a.last_updated_date is not None and a.last_updated_date != as_of
    )

    breach = [a for a in alerts if a.zone == PriceZone.BREACH]
    approach = [a for a in alerts if a.zone == PriceZone.APPROACH]

    lines = [f"⚠️ 持倉風險警示 ({as_of})"]

    if stale_count > 0:
        lines.append(f"⚠️ {stale_count} 檔警示部位價格非當日資料")

    if breach:
        lines.append(f"\n🔴 觸及停損 ({len(breach)} 檔) — 明日自動出場")
        for a in breach:
            flag = "†" if (a.last_updated_date and a.last_updated_date != as_of) else ""
            lines.append(
                f"  {a.symbol} {a.display_name}{flag}  {a.shares}股"
                f"  收盤{a.last_close:.2f}"
                f"  停損{a.trailing_stop:.2f}"
                f"  ({a.distance_pct:+.1f}%)"
            )

    if approach:
        lines.append(f"\n⚠️ 接近停損 ({len(approach)} 檔)")
        for a in approach:
            flag = "†" if (a.last_updated_date and a.last_updated_date != as_of) else ""
            lines.append(
                f"  {a.symbol} {a.display_name}{flag}  {a.shares}股"
                f"  收盤{a.last_close:.2f}"
                f"  停損{a.trailing_stop:.2f}"
                f"  ({a.distance_pct:+.1f}%)"
            )

    lines.append(f"\n共 {len(alerts)} 檔需關注 / 總持倉 {len(rows)} 檔")
    if stale_count > 0:
        lines.append("† 警示部位價格非當日")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="v0.1.15 EOD position risk alert")
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--include-synthetic", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    as_of = resolve_as_of(args.as_of)
    logger.info("eod_position_alert_start", as_of=str(as_of))

    message = build_position_alert_message(
        as_of=as_of,
        include_synthetic=args.include_synthetic,
    )
    if message is None:
        print(f"[eod_position_alert] {as_of}: 無持倉警示")
        return 0

    if args.dry_run:
        print(message)
        return 0

    tg_cfg = TelegramConfig.from_env()
    if tg_cfg is None:
        logger.warning("eod_position_alert_no_telegram_config")
        print(message)
        return 0

    bot = TelegramBot(tg_cfg)
    push_simple(bot, message)
    logger.info("eod_position_alert_sent", as_of=str(as_of))
    return 0


if __name__ == "__main__":
    sys.exit(main())
