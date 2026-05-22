#!/usr/bin/env python3
# scripts/run_eod_position_alert.py
"""EOD position risk alert — v0.1.15. APPROACH and BREACH positions after close.

Point-in-time zone classification: last_close vs trailing stop.
Does NOT use the intraday state machine (that is for intraday_monitor.py).
BREACH positions will be auto-exited by run_exit_scan at T+1 open.
This alert is informational: operator awareness only, no override semantics.

Two public message builders: build_breach_message() and build_approach_message().
The digest sends each as a separate Telegram message.

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

TELEGRAM_MESSAGE_LIMIT: int = 4096
DIGEST_SOFT_LIMIT: int = 3800
MAX_POSITION_ALERT_ROWS: int = 20


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


def _load_alerts(
    as_of: date_type,
    include_synthetic: bool = False,
) -> tuple[list[_PositionAlert], int]:
    """Load and classify all OPEN positions.

    Returns:
        (alerts_in_warning_zones, total_open_count)
    """
    if include_synthetic:
        synthetic_filter = ""
    else:
        synthetic_filter = "AND (is_synthetic = FALSE OR is_synthetic IS NULL)"

    with connect(read_only=True) as conn:
        rows = conn.execute(
            f"""
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
            """
        ).fetchall()

    total = len(rows)
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
    return alerts, total


def _fmt_row(a: _PositionAlert, as_of: date_type) -> str:
    flag = "†" if (a.last_updated_date and a.last_updated_date != as_of) else ""
    return (
        f"  {a.symbol} {a.display_name}{flag}  {a.shares}股"
        f"  收盤{a.last_close:.2f}"
        f"  停損{a.trailing_stop:.2f}"
        f"  ({a.distance_pct:+.1f}%)"
    )


def build_breach_message(
    as_of: date_type,
    include_synthetic: bool = False,
) -> str | None:
    """Return BREACH-only message, or None if no breach positions."""
    alerts, total = _load_alerts(as_of, include_synthetic)
    breach = [a for a in alerts if a.zone == PriceZone.BREACH]
    if not breach:
        return None

    stale = sum(
        1 for a in breach
        if a.last_updated_date and a.last_updated_date != as_of
    )
    lines = [f"🔴 觸及停損 ({len(breach)} 檔) — 明日自動出場 ({as_of})"]
    if stale:
        lines.append(f"⚠️ {stale} 檔價格非當日資料")
    lines.append("")
    for a in breach:
        lines.append(_fmt_row(a, as_of))
    lines.append(f"\n共 {len(alerts)} 檔需關注 / 總持倉 {total} 檔")
    if stale:
        lines.append("† 價格非當日")
    return "\n".join(lines)


def build_approach_message(
    as_of: date_type,
    include_synthetic: bool = False,
) -> str | None:
    """Return APPROACH-only message, or None if no approach positions."""
    alerts, total = _load_alerts(as_of, include_synthetic)
    approach = [a for a in alerts if a.zone == PriceZone.APPROACH]
    if not approach:
        return None

    stale = sum(
        1 for a in approach
        if a.last_updated_date and a.last_updated_date != as_of
    )
    lines = [f"⚠️ 接近停損 ({len(approach)} 檔) ({as_of})"]
    if stale:
        lines.append(f"⚠️ {stale} 檔價格非當日資料")
    lines.append("")
    for a in approach:
        lines.append(_fmt_row(a, as_of))
    lines.append(f"\n共 {len(alerts)} 檔需關注 / 總持倉 {total} 檔")
    if stale:
        lines.append("† 價格非當日")
    return "\n".join(lines)


def build_position_alert_message(
    as_of: date_type,
    include_synthetic: bool = False,
    max_rows: int = MAX_POSITION_ALERT_ROWS,
) -> str | None:
    """Legacy single-message builder for standalone --dry-run."""
    breach_msg = build_breach_message(as_of, include_synthetic)
    approach_msg = build_approach_message(as_of, include_synthetic)
    parts = [p for p in (breach_msg, approach_msg) if p]
    if not parts:
        return None
    return ("\n" + "─" * 28 + "\n").join(parts)


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
