# utils/logger.py
"""structlog 配置：JSON 輸出 + 檔案輪轉 + stdlib 整合。

設計：
- 輸出格式 JSON (易餵 alerting/分析工具)
- 同時輸出到 stderr 與 daily-rotating 檔案
- 檔案輪轉以 settings.timezone 為準 (預設 Asia/Taipei)
- 抑制 httpx / urllib3 等 noisy 第三方 logger
- import utils.logger 時自動 configure (idempotent)

Version: v0.1.1 (2026-05-16)
Changelog:
  v0.1.1 (2026-05-16): 檔案輪轉用 settings.timezone (修 UTC server 跨日問題); _add_timestamp 改用 MutableMapping 正確介面
  v0.1.0 (2026-05-16): Initial implementation
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
from collections.abc import MutableMapping
from datetime import datetime
from typing import Any

import structlog

from config.settings import get_settings

_configured = False


def _add_timestamp(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """加上 ISO timestamp。structlog Processor 介面。"""
    event_dict["timestamp"] = datetime.now().astimezone().isoformat(timespec="seconds")
    return event_dict


def configure_logging() -> None:
    """設定 structlog + stdlib logging。Idempotent。

    Timezone 處理：
    - 結構化 timestamp 用 datetime.now().astimezone() (本地時區)
    - 檔案輪轉用 zoneinfo 強制以 settings.timezone (預設 Asia/Taipei) 為準，
      避免 UTC server 上 log 檔以 UTC 切日造成檔名跨日。
    """
    global _configured
    if _configured:
        return

    s = get_settings()
    s.ensure_dirs()

    # 用 settings.timezone 強制設定輪轉時點 (00:00 Asia/Taipei)
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(s.timezone)
    except Exception:
        tz = None  # 退回系統時區

    rotation_kwargs: dict[str, Any] = {
        "when": "midnight",
        "backupCount": 30,
        "encoding": "utf-8",
    }
    if tz is not None:
        from datetime import time as dtime
        rotation_kwargs["atTime"] = dtime(0, 0, tzinfo=tz)

    file_handler = logging.handlers.TimedRotatingFileHandler(
        s.log_dir / "helios.log",
        **rotation_kwargs,
    )
    stream_handler = logging.StreamHandler(sys.stderr)

    logging.basicConfig(
        level=s.log_level,
        format="%(message)s",
        handlers=[file_handler, stream_handler],
        force=True,
    )

    # 抑制第三方 noisy logger
    for noisy in ("httpx", "httpcore", "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            _add_timestamp,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(s.log_level)
        ),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _configured = True


def get_logger(name: str | None = None) -> Any:
    """取得 structlog logger。"""
    if not _configured:
        configure_logging()
    return structlog.get_logger(name)


# Eager configure: 任何 import 此 module 的程式都會立即得到設定好的 logging
configure_logging()
