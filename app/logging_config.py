from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        # 常用上下文（如果有 extra 注入就带上）
        for key in ("path", "method", "client", "request_id"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)

        return json.dumps(payload, ensure_ascii=False)


def init_logging() -> None:
    """
    统一日志初始化。
    - 默认输出 JSON（便于云上采集/检索）
    - LOG_LEVEL: DEBUG/INFO/WARNING/ERROR
    """
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

