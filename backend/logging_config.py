"""结构化日志配置：rotating file + console，按用途分流。

替换 app.py 中的 logging.basicConfig，并把 services/llm.py 与
handlers.py 中各自创建 FileHandler 的散乱写法统一收口到这里。
"""
from __future__ import annotations

import logging
import logging.config
import os
from pathlib import Path

LOG_DIR = Path(os.getenv("LOG_DIR", Path(__file__).resolve().parent / "logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


def _file_handler(filename: str) -> dict:
    return {
        "class": "logging.handlers.RotatingFileHandler",
        "filename": str(LOG_DIR / filename),
        "maxBytes": 5 * 1024 * 1024,
        "backupCount": 5,
        "encoding": "utf-8",
        "formatter": "default",
        "level": LOG_LEVEL,
    }


LOGGING_CONFIG: dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s [%(levelname)s] %(name)s [%(request_id)s]: %(message)s",
            "defaults": {"request_id": "-"},
        },
        "plain": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        },
    },
    "filters": {
        "request_id": {
            "()": "logging_config.RequestIdFilter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "level": LOG_LEVEL,
            "filters": ["request_id"],
        },
        "access": {**_file_handler("access.log"), "filters": ["request_id"]},
        "error": {**_file_handler("error.log"), "level": "WARNING", "filters": ["request_id"]},
        "llm": {**_file_handler("llm.log"), "filters": ["request_id"]},
        "security": {**_file_handler("security.log"), "filters": ["request_id"]},
    },
    "loggers": {
        # 应用主日志
        "": {"handlers": ["console", "error"], "level": LOG_LEVEL},
        # HTTP 访问日志
        "access": {"handlers": ["access"], "level": "INFO", "propagate": False},
        # LLM 调用与用量
        "llm": {"handlers": ["console", "llm"], "level": "INFO", "propagate": False},
        "llm_return": {"handlers": ["llm"], "level": "INFO", "propagate": False},
        "llm_budget_suggest": {"handlers": ["llm"], "level": "INFO", "propagate": False},
        # 安全中间件
        "llm_security": {"handlers": ["security"], "level": "INFO", "propagate": False},
        # Werkzeug / waitress 噪音降级
        "werkzeug": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "waitress": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}


class RequestIdFilter(logging.Filter):
    """从 Flask g 中读取 request_id，便于追踪一次请求的全链路日志。"""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            try:
                from flask import g, has_request_context
                if has_request_context():
                    record.request_id = getattr(g, "request_id", "-")
                else:
                    record.request_id = "-"
            except Exception:
                record.request_id = "-"
        return True


def setup_logging() -> None:
    """在 app 启动时调用一次。"""
    logging.config.dictConfig(LOGGING_CONFIG)
