"""
Structured JSON logging configuration.

Call `setup_logging()` once at application startup (inside the lifespan handler).
After that, every `logging.getLogger(__name__)` call in the codebase will emit
newline-delimited JSON records readable by tools such as Datadog, Splunk, or
Azure Monitor.
"""
from __future__ import annotations

import json
import logging
import sys
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    # Fields to include from LogRecord (plus any extras set on the record)
    BASE_FIELDS = {
        "timestamp",
        "level",
        "logger",
        "message",
        "module",
        "function",
        "line",
    }

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        log_object: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Attach exception info when present
        if record.exc_info:
            log_object["exception"] = self.formatException(record.exc_info)
        if record.exc_text:
            log_object["exception_text"] = record.exc_text
        if record.stack_info:
            log_object["stack_info"] = self.formatStack(record.stack_info)

        # Pass through any extra fields attached by the caller
        for key, value in record.__dict__.items():
            if key not in logging.LogRecord.__dict__ and key not in self.BASE_FIELDS:
                # Skip internal Python logging internals
                if not key.startswith("_"):
                    log_object[key] = value

        return json.dumps(log_object, default=str, ensure_ascii=False)


def setup_logging(
    level: str = "INFO",
    force: bool = False,
) -> None:
    """
    Configure the root logger with a JSON handler writing to *stdout*.

    Parameters
    ----------
    level:
        Logging level as a string, e.g. "DEBUG", "INFO", "WARNING".
    force:
        If True, remove any existing handlers before adding ours.
        Useful in test environments.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    root_logger = logging.getLogger()

    if force:
        root_logger.handlers.clear()

    # Avoid adding duplicate handlers if called more than once
    if not root_logger.handlers or force:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        root_logger.addHandler(handler)

    root_logger.setLevel(numeric_level)

    # Quieten noisy third-party loggers
    for noisy in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        "Logging initialised",
        extra={"log_level": level},
    )


def get_logger(name: str) -> logging.Logger:
    """Convenience wrapper around ``logging.getLogger``."""
    return logging.getLogger(name)
