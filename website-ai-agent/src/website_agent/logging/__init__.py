"""Structured logging: Rich console for humans, JSON lines for machines, redaction always on.

Design rationale: built on stdlib logging (no structlog dependency; two small modules cover
our needs). Events are a name plus keyword fields, never interpolated strings, so the JSON
sink is queryable and the Rich sink stays readable. Run and step correlation IDs travel in
contextvars, so deeply nested components never pass logger context by hand. The redaction
filter runs in the logging pipeline itself: nothing that looks like a secret reaches any
sink (design D12).
"""

from website_agent.logging.redaction import RedactionFilter, redact_text
from website_agent.logging.setup import configure_logging
from website_agent.logging.structured import StructuredLogger, bind_run_context, get_logger

__all__ = [
    "RedactionFilter",
    "StructuredLogger",
    "bind_run_context",
    "configure_logging",
    "get_logger",
    "redact_text",
]
