"""Secret redaction for the logging pipeline.

Design rationale: redaction lives in a logging.Filter so it is impossible to emit through a
configured sink without passing it; components cannot opt out. Patterns are deliberately
conservative (high-precision shapes like key-value assignments and bearer tokens) because
over-eager masking destroys log usefulness; the artifact writers apply the same
``redact_text`` at write time (docs/architecture/data-flow.md, section 6).
"""

from __future__ import annotations

import logging
import re
from typing import Any

MASK = "***REDACTED***"

# Order matters: value-bearing assignments first, then standalone token shapes.
_PATTERNS: tuple[re.Pattern[str], ...] = (
    # key=value / key: value for common secret names; keeps the key, masks the value.
    re.compile(
        r"(?i)\b(api[_-]?key|apikey|secret|password|passwd|token|authorization)\b"
        r"(\s*[:=]\s*)(\"[^\"]+\"|'[^']+'|\S+)"
    ),
    # Bearer credentials in headers or curl snippets.
    re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{8,}"),
    # OpenAI-style secret keys anywhere in text.
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
)


def redact_text(text: str) -> str:
    """Mask secret-shaped substrings in ``text``. Idempotent and safe on any string.

    Bearer credentials are masked before key-value assignments: in
    ``Authorization: Bearer <token>`` the assignment pattern would otherwise consume
    the word ``Bearer`` as the value and leave the token exposed.
    """
    result = _PATTERNS[1].sub(rf"\1 {MASK}", text)
    result = _PATTERNS[0].sub(rf"\1\2{MASK}", result)
    return _PATTERNS[2].sub(MASK, result)


def redact_value(value: Any) -> Any:
    """Recursively redact strings inside plain containers; other types pass through."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: redact_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        redacted = [redact_value(v) for v in value]
        return type(value)(redacted) if isinstance(value, tuple) else redacted
    return value


class RedactionFilter(logging.Filter):
    """Applies redaction to the record message and structured fields before any handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact in place; always lets the record through."""
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        fields = getattr(record, "wa_fields", None)
        if isinstance(fields, dict):
            record.wa_fields = redact_value(fields)
        return True
