import json
import os
from pathlib import Path
from typing import Any

from app.shared.logging import normalized_log_format


def build_uvicorn_log_config(log_format: str, log_level: str) -> dict[str, Any]:
    renderer = (
        "structlog.dev.ConsoleRenderer"
        if normalized_log_format(log_format) == "plain"
        else "structlog.processors.JSONRenderer"
    )
    level = log_level.upper()

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": "structlog.stdlib.ProcessorFormatter",
                "processor": {"()": renderer},
                "foreign_pre_chain": [
                    {"()": "structlog.contextvars.merge_contextvars"},
                    {"()": "structlog.stdlib.add_logger_name"},
                    {"()": "structlog.stdlib.add_log_level"},
                    {"()": "structlog.processors.TimeStamper", "fmt": "iso"},
                    {"()": "structlog.processors.format_exc_info"},
                ],
            },
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "stream": "ext://sys.stdout",
            },
        },
        "root": {
            "handlers": ["default"],
            "level": level,
        },
        "loggers": {
            "uvicorn": {"handlers": [], "level": level, "propagate": True},
            "uvicorn.error": {"handlers": [], "level": level, "propagate": True},
            "uvicorn.access": {"handlers": [], "level": level, "propagate": True},
            "httpx": {"handlers": [], "level": level, "propagate": True},
            "httpcore": {"handlers": [], "level": level, "propagate": True},
        },
    }


def write_uvicorn_log_config(path: str | Path, log_format: str, log_level: str) -> None:
    config = build_uvicorn_log_config(log_format, log_level)
    Path(path).write_text(json.dumps(config), encoding="utf-8")


def main() -> None:
    write_uvicorn_log_config(
        os.environ.get("UVICORN_LOG_CONFIG", "/tmp/uvicorn-log-config.json"),
        os.environ.get("LOG_FORMAT", "json"),
        os.environ.get("LOG_LEVEL", "INFO"),
    )


if __name__ == "__main__":
    main()
