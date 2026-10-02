"""Structured JSON logging (NFR-07, R-54).

JSON out, one event per line, with a correlation id bound per request. Fields
are an allowlist: never log raw usernames or hostnames, redact upstream instead.
"""

from __future__ import annotations

import logging
import sys
from typing import cast

import structlog

from app.core.config import Environment, Settings


def configure_logging(settings: Settings) -> None:
    """Configure structlog and the stdlib root logger for this process.

    Development renders to the console for humans; every other environment emits
    JSON so the output is machine-parseable.
    """
    level = getattr(logging, settings.log_level, logging.INFO)

    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: structlog.typing.Processor
    if settings.env is Environment.DEVELOPMENT:
        renderer = structlog.dev.ConsoleRenderer(colors=False)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(level=level, stream=sys.stdout, format="%(message)s")


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a named structured logger."""
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))


def bind_request_id(request_id: str) -> None:
    """Bind a correlation id that will appear on every subsequent log line."""
    structlog.contextvars.bind_contextvars(request_id=request_id)


def clear_request_id() -> None:
    """Clear per-request context so ids never leak across requests."""
    structlog.contextvars.clear_contextvars()
