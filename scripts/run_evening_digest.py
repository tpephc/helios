#!/usr/bin/env python3
# scripts/run_evening_digest.py
"""Evening digest orchestrator — v0.1.15. Combines signal preview and position alert.

Runs run_signal_preview and run_eod_position_alert independently.
Failure isolation: if one section fails, the other still sends.
Empty sections (no signals / no warnings) are silently omitted.

Cron:
    30 19 * * 1-5  cd ~/projects/helios && \\
        uv run python scripts/run_evening_digest.py >> logs/evening_digest.log 2>&1

Usage:
    uv run python scripts/run_evening_digest.py
    uv run python scripts/run_evening_digest.py --dry-run
    uv run python scripts/run_evening_digest.py --include-synthetic
"""

from __future__ import annotations

import argparse
import sys
from datetime import date as date_type

from communication.telegram import TelegramBot, TelegramConfig
from communication.telegram.sender import push_simple
from scripts.run_signal_preview import build_preview_message
from scripts.run_eod_position_alert import build_position_alert_message
from utils.logger import get_logger
from utils.trading_dates import resolve_as_of

logger = get_logger(__name__)

_DIVIDER = "─" * 28


def build_digest(
    as_of: date_type,
    include_synthetic: bool = False,
) -> str | None:
    """Build the combined evening digest message.

    Each section is built independently; exceptions include full traceback
    so production failures are debuggable.

    Returns:
        Combined message string, or None if both sections are empty/failed.
    """
    sections: list[str] = []

    try:
        preview = build_preview_message(as_of=as_of)
        if preview:
            sections.append(preview)
    except Exception:  # noqa: BLE001
        logger.exception("digest_signal_preview_failed", as_of=str(as_of))
        sections.append("📋 明日進場候選\n⚠️ 取得失敗，請查閱 logs/evening_digest.log")

    try:
        alert = build_position_alert_message(
            as_of=as_of,
            include_synthetic=include_synthetic,
        )
        if alert:
            sections.append(alert)
    except Exception:  # noqa: BLE001
        logger.exception("digest_position_alert_failed", as_of=str(as_of))
        sections.append("⚠️ 持倉風險警示\n⚠️ 取得失敗，請查閱 logs/evening_digest.log")

    if not sections:
        return None

    header = f"📊 Helios Evening Digest ({as_of})"
    body = f"\n{_DIVIDER}\n".join(sections)
    return f"{header}\n\n{body}"


def main() -> int:
    parser = argparse.ArgumentParser(description="v0.1.15 evening digest")
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--include-synthetic", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    as_of = resolve_as_of(args.as_of)
    logger.info("evening_digest_start", as_of=str(as_of))

    message = build_digest(as_of=as_of, include_synthetic=args.include_synthetic)
    if message is None:
        print(f"[evening_digest] {as_of}: 無內容")
        return 0

    if args.dry_run:
        print(message)
        return 0

    tg_cfg = TelegramConfig.from_env()
    if tg_cfg is None:
        logger.warning("evening_digest_no_telegram_config")
        print(message)
        return 0

    bot = TelegramBot(tg_cfg)
    push_simple(bot, message)
    logger.info("evening_digest_sent", as_of=str(as_of))
    return 0


if __name__ == "__main__":
    sys.exit(main())
