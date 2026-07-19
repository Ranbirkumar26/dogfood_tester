"""Structured logger facade and run/step correlation context.

Design rationale: call sites log an event name plus keyword fields
(``log.info("step_executed", step_id=..., outcome=...)``) instead of formatted strings.
Fields ride on the LogRecord as ``wa_fields`` and correlation IDs come from contextvars,
so sinks decide presentation and every event in a run is joinable on run_id without
threading loggers through constructors.
"""

from __future__ import annotations

import contextvars
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

ROOT_LOGGER_NAME = "website_agent"

_run_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("wa_run_id", default=None)
_step_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("wa_step", default=None)


@contextmanager
def bind_run_context(run_id: str | None = None, step: str | None = None) -> Iterator[None]:
    """Attach run and/or step IDs to every log event emitted inside the block.

    Nests: an inner binding of ``step`` keeps the outer ``run_id``.
    """
    tokens: list[tuple[contextvars.ContextVar[str | None], contextvars.Token[str | None]]] = []
    if run_id is not None:
        tokens.append((_run_id_var, _run_id_var.set(run_id)))
    if step is not None:
        tokens.append((_step_var, _step_var.set(step)))
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


def current_run_context() -> dict[str, str]:
    """Correlation IDs currently bound, as a dict with only present keys."""
    context: dict[str, str] = {}
    if (run_id := _run_id_var.get()) is not None:
        context["run_id"] = run_id
    if (step := _step_var.get()) is not None:
        context["step"] = step
    return context


class ContextFilter(logging.Filter):
    """Stamps bound correlation IDs onto every record as ``wa_context``."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Attach context; always lets the record through."""
        record.wa_context = current_run_context()
        return True


class StructuredLogger:
    """Thin event-oriented wrapper over a stdlib logger.

    Args:
        component: dotted suffix under the ``website_agent`` logger namespace.
    """

    def __init__(self, component: str) -> None:
        self.component = component
        self._logger = logging.getLogger(f"{ROOT_LOGGER_NAME}.{component}")

    def debug(self, event: str, **fields: Any) -> None:
        """Emit a DEBUG event with structured fields."""
        self._emit(logging.DEBUG, event, fields)

    def info(self, event: str, **fields: Any) -> None:
        """Emit an INFO event with structured fields."""
        self._emit(logging.INFO, event, fields)

    def warning(self, event: str, **fields: Any) -> None:
        """Emit a WARNING event with structured fields."""
        self._emit(logging.WARNING, event, fields)

    def error(self, event: str, *, exc_info: bool = False, **fields: Any) -> None:
        """Emit an ERROR event; set ``exc_info`` inside an except block to attach the traceback."""
        self._emit(logging.ERROR, event, fields, exc_info=exc_info)

    def _emit(
        self, level: int, event: str, fields: dict[str, Any], *, exc_info: bool = False
    ) -> None:
        if not self._logger.isEnabledFor(level):
            return
        self._logger.log(
            level,
            event,
            exc_info=exc_info,
            extra={"wa_fields": fields, "wa_component": self.component},
        )


def get_logger(component: str) -> StructuredLogger:
    """Structured logger for a component, e.g. ``get_logger("browser.session")``."""
    return StructuredLogger(component)
