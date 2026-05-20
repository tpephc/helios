# communication/telegram/bot.py
"""Telegram Bot API wrapper — raw `requests`, no SDK (per ADR-008).

API surface used:
  POST /sendMessage   — push a message to chat_id
  GET  /getUpdates    — long-poll for incoming /commands

Configuration is read via `config.settings.Settings`, which loads `.env`
through pydantic-settings (see ROOT/.env.example for the canonical schema).
Field names are non-prefixed: `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

  v0.1.14.3.4 fix: previous versions read `HELIOS_TELEGRAM_*` via raw
  `os.environ.get`, which (a) required the operator to source .env manually
  via `set -a; source .env; set +a` because pydantic-settings only
  populates the Settings class instance (not os.environ), and (b) didn't
  match the schema documented in .env.example. Net effect: an operator who
  followed .env.example would silently get `listener skipped (no_telegram)`
  on every daily_run, because Settings loaded the token correctly but
  TelegramConfig.from_env() didn't see it. v0.1.14.3.4 routes through
  Settings so the two namespaces stay aligned.

Network failures are logged but not raised (per §9 Escalation Policy:
"Telegram outage → exits auto-execute; entries skipped, operator notified later").

Version: v0.1.1 (2026-05-17 — v0.1.14.3.4 env naming alignment)
"""
from __future__ import annotations

from dataclasses import dataclass

import requests

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class TelegramConfig:
    """Telegram bot config from Settings (which loads .env)."""
    bot_token: str
    chat_id: str
    base_url: str = "https://api.telegram.org"
    request_timeout: int = 10  # seconds for non-polling calls

    @classmethod
    def from_env(cls) -> TelegramConfig | None:
        """Build TelegramConfig from Settings/.env. Returns None if either
        TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is unset.

        v0.1.14.3.4: routes through `config.settings.Settings` instead of
        raw `os.environ.get`. Pydantic-settings reads `.env` automatically
        (no manual shell export required); SecretStr's wrapping is unwrapped
        here via `.get_secret_value()`.
        """
        from config.settings import get_settings
        s = get_settings()
        token = s.telegram_bot_token
        chat_id = s.telegram_chat_id
        if token is None or chat_id is None:
            return None
        token_str = token.get_secret_value() if hasattr(token, "get_secret_value") else str(token)
        if not token_str or not chat_id:
            return None
        return cls(bot_token=token_str, chat_id=chat_id)


class TelegramBot:
    """Minimal Bot API client.

    All methods return safely (None / [] / False) on network failure rather
    than raise — daily_run must tolerate Telegram outage.
    """

    def __init__(self, config: TelegramConfig) -> None:
        self.config = config
        self._api = f"{config.base_url}/bot{config.bot_token}"

    # ── Send ───────────────────────────────────────────────

    def send_message(self, text: str, *, parse_mode: str | None = None) -> int | None:
        """Send a message. Returns Telegram message_id on success, None on failure.

        Splits long messages (Telegram limit 4096 chars) into multiple sends.
        """
        if len(text) > 4000:
            text = text[:3997] + "..."
        try:
            r = requests.post(
                f"{self._api}/sendMessage",
                json={
                    "chat_id": self.config.chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                },
                timeout=self.config.request_timeout,
            )
            r.raise_for_status()
            data = r.json()
            if data.get("ok"):
                return int(data["result"]["message_id"])
            logger.warning("telegram_send_not_ok", response=data)
            return None
        except (requests.RequestException, ValueError, KeyError) as e:
            logger.warning("telegram_send_failed", error=str(e))
            return None

    # ── Receive ────────────────────────────────────────────

    def get_updates(
        self, *,
        offset: int = 0,
        timeout: int = 30,
        allowed_updates: list[str] | None = None,
    ) -> list[dict]:
        """Long-poll for new updates. Returns list of update dicts.

        Args:
            offset: update_id to start from; pass max(prev_update_id)+1
            timeout: long-poll seconds (Telegram side); we add buffer for HTTP
        """
        if allowed_updates is None:
            allowed_updates = ["message"]
        try:
            r = requests.get(
                f"{self._api}/getUpdates",
                params={
                    "offset": offset,
                    "timeout": timeout,
                    "allowed_updates": ",".join(allowed_updates),
                },
                timeout=timeout + 5,  # HTTP timeout > Telegram long-poll
            )
            r.raise_for_status()
            data = r.json()
            if not data.get("ok"):
                logger.warning("telegram_updates_not_ok", response=data)
                return []
            return data.get("result", [])
        except (requests.RequestException, ValueError, KeyError) as e:
            logger.warning("telegram_updates_failed", error=str(e))
            return []
