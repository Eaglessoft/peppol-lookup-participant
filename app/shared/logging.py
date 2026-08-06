import logging
import sys

import structlog

from app.shared.config import Settings

_LOGGER_NAMES = (
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "httpx",
    "httpcore",
)


def log_level_from_name(value: str) -> int:
    return getattr(logging, value.upper(), logging.INFO)


def normalized_log_format(log_format: str) -> str:
    value = log_format.strip().lower()
    if value == "text":
        return "plain"
    if value not in {"json", "plain"}:
        return "json"
    return value


def processors_for(log_format: str) -> list[object]:
    processors: list[object] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.format_exc_info,
    ]
    if normalized_log_format(log_format) == "plain":
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        processors.append(structlog.processors.JSONRenderer())
    return processors


def configure_logging(settings: Settings) -> None:
    level = log_level_from_name(settings.log_level)
    processors = processors_for(settings.log_format)

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=processors[-1],
        foreign_pre_chain=processors[:-1],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level)
    root_logger.addHandler(handler)

    for logger_name in _LOGGER_NAMES:
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.setLevel(level)
        logger.propagate = True

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
