"""Logging pipeline configuration: sink selection, level, filters.

Design rationale: exactly one configuration entry point, idempotent, applied to the
``website_agent`` logger namespace only (propagate=False) so embedding this package never
hijacks a host application's root logger. Both sinks receive the same filter chain:
redaction first, then context stamping.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from rich.logging import RichHandler

from website_agent.config.settings import LogFormat, LoggingSettings
from website_agent.logging.redaction import RedactionFilter
from website_agent.logging.structured import ROOT_LOGGER_NAME, ContextFilter


class JsonLineFormatter(logging.Formatter):
    """One JSON object per line: ts, level, component, event, context, fields."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialize the record; non-JSON-safe field values fall back to ``str``."""
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "component": getattr(record, "wa_component", record.name),
            "event": record.getMessage(),
        }
        payload.update(getattr(record, "wa_context", {}))
        fields = getattr(record, "wa_fields", None)
        if fields:
            payload["fields"] = fields
        if record.exc_info and record.exc_info[1] is not None:
            payload["exception"] = repr(record.exc_info[1])
        return json.dumps(payload, default=str)


class RichFieldsHandler(RichHandler):
    """Rich console handler that appends structured fields to the rendered message."""

    def render_message(self, record: logging.LogRecord, message: str) -> Any:
        """Suffix ``key=value`` pairs (context first) onto the event name."""
        parts = [message]
        context = getattr(record, "wa_context", {})
        fields = getattr(record, "wa_fields", {}) or {}
        for key, value in {**context, **fields}.items():
            parts.append(f"{key}={value}")
        return super().render_message(record, " ".join(parts))


def configure_logging(settings: LoggingSettings) -> None:
    """Configure the package logger namespace. Safe to call repeatedly; last call wins."""
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    logger.handlers.clear()
    logger.filters.clear()
    logger.setLevel(settings.level.upper())
    logger.propagate = False

    handler: logging.Handler
    if settings.format is LogFormat.JSON:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonLineFormatter())
    else:
        handler = RichFieldsHandler(rich_tracebacks=True, markup=False, show_path=False)

    # Filters go on the handler, not the logger: stdlib logger-level filters only run
    # for records emitted on that exact logger, and our events come from child loggers.
    # Handler-level filters run for every record the handler processes.
    handler.addFilter(RedactionFilter())
    handler.addFilter(ContextFilter())
    logger.addHandler(handler)
