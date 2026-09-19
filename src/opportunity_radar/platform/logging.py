"""Structured logging.

Section 63 of the roadmap asks that logs identify failures. A line that a human skims is
not enough for that: the fields a failure is searched by — the source, the run, the
request — have to be machine-readable, so every record is emitted as one JSON object.

The correlation id travels in a context variable rather than in every signature, so a log
written deep inside a collector still carries the request or run it belongs to.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

CORRELATION_ID: ContextVar[str | None] = ContextVar("correlation_id", default=None)

#: Attributes the logging module puts on every record. Anything else an adapter attached
#: is application context and gets merged into the JSON object.
_RESERVED = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        correlation_id = CORRELATION_ID.get()
        if correlation_id is not None:
            payload["correlation_id"] = correlation_id
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = _encodable(value)
        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def _encodable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Mapping):
        return {str(key): _encodable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_encodable(item) for item in value]
    return str(value)


def configure_logging(level: str = "INFO", *, stream: Any = None) -> None:
    """Replace the root handlers. Idempotent: calling it twice does not double lines."""
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level.upper())
    # Uvicorn installs its own handlers; letting records propagate keeps one format.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True


def new_correlation_id() -> str:
    return uuid4().hex


@contextmanager
def correlation_scope(correlation_id: str | None = None) -> Iterator[str]:
    """Bind a correlation id for everything logged inside the block."""
    value = correlation_id or new_correlation_id()
    token = CORRELATION_ID.set(value)
    try:
        yield value
    finally:
        CORRELATION_ID.reset(token)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


__all__ = [
    "CORRELATION_ID",
    "JsonFormatter",
    "configure_logging",
    "correlation_scope",
    "get_logger",
    "new_correlation_id",
]
