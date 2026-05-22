#!/usr/bin/env python3
# scripts/run_evening_digest.py
"""Evening digest orchestrator — v0.1.15. Multi-message send by zone.

Sends up to 3 separate Telegram messages:
    1. Signal preview (明日進場候選)
    2. BREACH positions (觸及停損) — if any
    3. APPROACH positions (接近停損) — if any

Separating by zone ensures each message is complete and not truncated.
Each section is failure-isolated: one failing does not suppress the others.

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
from scripts.run_eod_position_alert import (
    build_breach_message,
    build_approach_message,
    TELEGRAM_MESSAGE_LIMIT,
)
from utils.logger import get_logger
from utils.trading_dates import resolve_as_of

logger = get_logger(__name__)


def _build_sections(
    as_of: date_type,
    include_synthetic: bool = False,
) -> list[str]:
    """Build all message sections, each failure-isolated.

    Returns:
        List of non-empty message strings, at most 3 items.
    """
    sections: list[str] = []

    # 1. Signal preview
    try:
        msg = build_preview_message(as_of=as_of)
        if msg:
            sections.append(msg)
    except Exception:  # noqa: BLE001
        logger.exception("digest_signal_preview_failed", as_of=str(as_of))
        sections.append("📋 明日進場候選\n⚠️ 取得失敗，請查閱 logs/evening_digest.log")

    # 2. BREACH positions
    try:
        msg = build_breach_message(as_of=as_of, include_synthetic=include_synthetic)
        if msg:
            sections.append(msg)
    except Exception:  # noqa: BLE001
        logger.exception("digest_breach_message_failed", as_of=str(as_of))
        sections.append("🔴 觸及停損\n⚠️ 取得失敗，請查閱 logs/evening_digest.log")

    # 3. APPROACH positions
    try:
        msg = build_approach_message(as_of=as_of, include_synthetic=include_synthetic)
        if msg:
            sections.append(msg)
    except Exception:  # noqa: BLE001
        logger.exception("digest_approach_message_failed", as_of=str(as_of))
        sections.append("⚠️ 接近停損\n⚠️ 取得失敗，請查閱 logs/evening_digest.log")

    return sections


def main() -> int:
    parser = argparse.ArgumentParser(description="v0.1.15 evening digest")
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--include-synthetic", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    as_of = resolve_as_of(args.as_of)
    logger.info("evening_digest_start", as_of=str(as_of))

    sections = _build_sections(as_of=as_of, include_synthetic=args.include_synthetic)

    if not sections:
        print(f"[evening_digest] {as_of}: 無內容")
        return 0

    if args.dry_run:
        for i, msg in enumerate(sections, 1):
            print(f"\n{'='*40}")
            print(f"Message {i}/{len(sections)}  ({len(msg)} chars)")
            print('='*40)
            print(msg)
        print(f"\n[total: {len(sections)} messages]")
        return 0

    tg_cfg = TelegramConfig.from_env()
    if tg_cfg is None:
        logger.warning("evening_digest_no_telegram_config")
        for msg in sections:
            print(msg)
        return 0

    bot = TelegramBot(tg_cfg)
    sent = 0
    for msg in sections:
        if len(msg) > TELEGRAM_MESSAGE_LIMIT:
            msg = msg[:TELEGRAM_MESSAGE_LIMIT - 20] + "\n...(訊息已截斷)"
            logger.error("digest_section_hard_truncated", as_of=str(as_of))
        push_simple(bot, msg)
        sent += 1

    logger.info("evening_digest_sent", as_of=str(as_of), messages=sent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
