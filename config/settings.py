# config/settings.py
"""中央設定：Pydantic Settings 載入 .env，函數式 loader 讀 YAML。

設計原則：
- 機密與環境差異走 .env (Pydantic Settings 驗證型別)
- 策略參數、universe、風控門檻走 YAML (純資料，易讀易改)
- get_settings() 是 singleton，第一次呼叫時建立並 ensure_dirs

Version: v0.1.1 (2026-05-16)
Changelog:
  v0.1.1 (2026-05-16): Telegram approval timeout 預設 10 → 30 分鐘 (review 採納)
  v0.1.0 (2026-05-16): Initial implementation
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """從 .env 載入：機密、路徑、環境旗標。"""

    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Environment ─────────────────────────────────────────
    env: Literal["dev", "paper", "live"] = "dev"
    mode: Literal["notification_only", "semi_auto", "full_auto"] = "semi_auto"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    timezone: str = "Asia/Taipei"

    # ── Paths ──────────────────────────────────────────────
    root_dir: Path = ROOT
    data_dir: Path = ROOT / "data" / "_storage"
    cache_dir: Path = ROOT / "data" / "_cache"
    log_dir: Path = ROOT / "logs"
    config_dir: Path = ROOT / "config"
    db_path: Path = ROOT / "data" / "_storage" / "helios.duckdb"

    # ── FinMind ────────────────────────────────────────────
    finmind_token: SecretStr | None = None
    finmind_base_url: str = "https://api.finmindtrade.com/api/v4"
    finmind_min_interval_sec: float = 1.2
    finmind_max_retries: int = 5
    finmind_rate_limit_sleep_sec: int = 60

    # ── Telegram (v0.1 Step 8) ─────────────────────────────
    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None
    telegram_approval_timeout_min: int = 30  # review 採納：中波段日 K，30 分鐘合理

    # ── Shioaji (v0.4) ─────────────────────────────────────
    shioaji_api_key: SecretStr | None = None
    shioaji_secret_key: SecretStr | None = None
    shioaji_simulation: bool = True

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.cache_dir, self.log_dir):
            d.mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None


def get_settings() -> Settings:
    """Singleton accessor。第一次呼叫時建立並建好目錄。"""
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.ensure_dirs()
    return _settings


# ── YAML loaders (純函數，無狀態) ────────────────────────────

def load_yaml(name: str) -> dict:
    """從 config_dir/<name>.yaml 載入。"""
    s = get_settings()
    path = s.config_dir / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_universe() -> dict:
    return load_yaml("universe")


def load_strategy_config() -> dict:
    return load_yaml("strategy_config")


def load_risk_limits() -> dict:
    return load_yaml("risk_limits")
