# config/account_config.py
"""Account configuration — v0.1.0.

Loads per-account broker credentials and notification routing from
config/accounts.yaml + environment variables.

Design:
  - YAML stores configuration (account_id, owner, environment, paths)
  - ENV stores secrets (api_key, secret_key, ca_password, chat_id)
  - AccountConfig is a plain dataclass — no Pydantic, no .env coupling
  - Secrets are loaded lazily on first access via SecretStr wrapper

Secret ENV key convention:
  account_id.upper().replace('-', '_') + suffix
  e.g. account_id='philip_sim' → prefix='PHILIP_SIM'
  PHILIP_SIM_SHIOAJI_API_KEY
  PHILIP_SIM_SHIOAJI_SECRET_KEY
  PHILIP_SIM_CA_PASSWORD
  PHILIP_SIM_TELEGRAM_CHAT_ID  (optional, overrides accounts.yaml value)

Legacy compatibility:
  If use_legacy_env=true, reads the non-prefixed keys:
  SHIOAJI_API_KEY, SHIOAJI_SECRET_KEY, CA_PASSWORD, TELEGRAM_CHAT_ID
  This allows a single-account setup to keep the existing .env unchanged.

Version: v0.1.0 (2026-05-26)
Changelog:
  v0.1.0 (2026-05-26): Initial — v0.1.17-A config layer.
    Phase A: config + routing only. DB account_id column added in v0.1.18.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from utils.logger import get_logger

logger = get_logger(__name__)

_ACCOUNTS_YAML = Path(__file__).resolve().parent / "accounts.yaml"


@dataclass
class AccountConfig:
    """Single broker account configuration.

    Secrets are NOT stored as plain strings. Use the property accessors
    which read from ENV at call time (no in-memory caching of secrets).
    """

    account_id: str
    owner: str
    broker: str                       # 'shioaji' only for now
    environment: str                  # 'sim' | 'live'
    telegram_chat_id: str | None      # None = no Telegram push
    ca_cert_path: Path | None
    enabled: bool
    use_legacy_env: bool = False      # backward compat for single-account setups

    # ── Secret accessors (read from ENV at call time) ──────────────────

    @property
    def _env_prefix(self) -> str:
        """ENV key prefix derived from account_id."""
        if self.use_legacy_env:
            return ""  # no prefix — reads SHIOAJI_API_KEY directly
        return self.account_id.upper().replace("-", "_") + "_"

    def _get_secret(self, suffix: str) -> str | None:
        """Read a secret from ENV using the account prefix convention."""
        key = f"{self._env_prefix}{suffix}"
        value = os.environ.get(key)
        if value is None:
            logger.warning(
                "account_secret_missing",
                account_id=self.account_id,
                env_key=key,
            )
        return value

    @property
    def shioaji_api_key(self) -> str | None:
        return self._get_secret("SHIOAJI_API_KEY")

    @property
    def shioaji_secret_key(self) -> str | None:
        return self._get_secret("SHIOAJI_SECRET_KEY")

    @property
    def ca_password(self) -> str | None:
        return self._get_secret("CA_PASSWORD")

    @property
    def resolved_telegram_chat_id(self) -> str | None:
        """Return telegram_chat_id from YAML, or override from ENV if set."""
        env_override = self._get_secret("TELEGRAM_CHAT_ID")
        # suppress warning from _get_secret when ENV key not set (optional override)
        env_key = f"{self._env_prefix}TELEGRAM_CHAT_ID"
        env_override = os.environ.get(env_key)
        if env_override:
            return env_override
        return self.telegram_chat_id

    @property
    def is_simulation(self) -> bool:
        """True if this account runs in Shioaji simulation mode."""
        return self.environment == "sim"

    def validate(self) -> list[str]:
        """Return list of validation errors (empty = valid)."""
        errors = []
        if not self.account_id:
            errors.append("account_id is required")
        if self.broker not in ("shioaji",):
            errors.append(f"unsupported broker: {self.broker}")
        if self.environment not in ("sim", "live"):
            errors.append(f"environment must be 'sim' or 'live', got: {self.environment}")
        if self.shioaji_api_key is None:
            errors.append(f"missing ENV: {self._env_prefix}SHIOAJI_API_KEY")
        if self.shioaji_secret_key is None:
            errors.append(f"missing ENV: {self._env_prefix}SHIOAJI_SECRET_KEY")
        return errors

    def __repr__(self) -> str:
        return (
            f"AccountConfig(account_id={self.account_id!r}, "
            f"owner={self.owner!r}, "
            f"environment={self.environment!r}, "
            f"enabled={self.enabled})"
        )


def load_accounts(
    path: Path = _ACCOUNTS_YAML,
    enabled_only: bool = True,
) -> list[AccountConfig]:
    """Load all accounts from accounts.yaml.

    Args:
        path: Path to accounts.yaml. Defaults to config/accounts.yaml.
        enabled_only: If True (default), skip accounts with enabled=false.

    Returns:
        List of AccountConfig objects.

    Raises:
        FileNotFoundError: if accounts.yaml does not exist.
        ValueError: if accounts.yaml is malformed.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"accounts.yaml not found at {path}. "
            "Create it from the template in config/accounts.yaml."
        )

    with path.open(encoding="utf-8") as fh:
        raw: dict[str, Any] = yaml.safe_load(fh) or {}

    raw_accounts = raw.get("accounts", [])
    if not raw_accounts:
        raise ValueError(f"accounts.yaml has no accounts defined at {path}")

    configs = []
    for entry in raw_accounts:
        account_id = entry.get("account_id", "")
        enabled = bool(entry.get("enabled", True))

        if enabled_only and not enabled:
            logger.debug("account_skipped_disabled", account_id=account_id)
            continue

        ca_cert_raw = entry.get("ca_cert_path")
        ca_cert_path = None
        if ca_cert_raw:
            p = Path(ca_cert_raw)
            if not p.is_absolute():
                # Resolve relative to project root (one level above config/)
                p = path.parent.parent / p
            ca_cert_path = p

        cfg = AccountConfig(
            account_id=account_id,
            owner=str(entry.get("owner", account_id)),
            broker=str(entry.get("broker", "shioaji")),
            environment=str(entry.get("environment", "sim")),
            telegram_chat_id=str(entry["telegram_chat_id"])
                if entry.get("telegram_chat_id") else None,
            ca_cert_path=ca_cert_path,
            enabled=enabled,
            use_legacy_env=bool(entry.get("use_legacy_env", False)),
        )
        configs.append(cfg)
        logger.debug("account_loaded", account_id=account_id,
                     environment=cfg.environment, owner=cfg.owner)

    if not configs:
        raise ValueError(
            "No enabled accounts found in accounts.yaml. "
            "Set enabled: true for at least one account."
        )

    logger.info("accounts_loaded", count=len(configs),
                ids=[c.account_id for c in configs])
    return configs


def get_account(
    account_id: str,
    path: Path = _ACCOUNTS_YAML,
) -> AccountConfig:
    """Load a single account by account_id.

    Raises:
        KeyError: if account_id not found.
        FileNotFoundError: if accounts.yaml not found.
    """
    all_accounts = load_accounts(path, enabled_only=False)
    for acc in all_accounts:
        if acc.account_id == account_id:
            return acc
    available = [a.account_id for a in all_accounts]
    raise KeyError(
        f"Account '{account_id}' not found in accounts.yaml. "
        f"Available: {available}"
    )
