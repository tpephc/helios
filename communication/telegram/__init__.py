# communication/telegram/__init__.py
"""Telegram bot — long polling, raw `requests`, no SDK (per ADR-008).

Three modules:
  bot.py       — TelegramBot wrapper: send_message, get_updates
  sender.py    — high-level: format + push entry-approval request, exit notify, etc.
  listener.py  — poll for /approve /reject /status commands (30-min window)
"""
from communication.telegram.bot import TelegramBot, TelegramConfig

__all__ = ["TelegramBot", "TelegramConfig"]
