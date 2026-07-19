"""Console and network observers: push-based capture, pull-based draining per step.

Design rationale: Playwright events arrive continuously; the loop needs them windowed per
step so the reviewer sees exactly the consequences of one action
(docs/architecture/data-flow.md, section 3). Observers therefore buffer everything and the
session drains the buffers at step boundaries. Observers never raise into the event loop:
a broken handler degrades the signal, not the run (graceful degradation,
docs/architecture/failure-recovery.md section 5).
"""

from __future__ import annotations

from typing import Any

from website_agent.browser.models import ConsoleEvent, NetworkEvent
from website_agent.core.clock import Clock
from website_agent.logging import get_logger

log = get_logger("browser.observers")


class ConsoleObserver:
    """Buffers console messages and uncaught page errors for one page."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._events: list[ConsoleEvent] = []

    def attach(self, page: Any) -> None:
        """Subscribe to a page's console and pageerror events."""
        page.on("console", self._on_console)
        page.on("pageerror", self._on_pageerror)

    def _on_console(self, message: Any) -> None:
        try:
            location = message.location or {}
            self._events.append(
                ConsoleEvent(
                    level=message.type,
                    text=message.text,
                    url=location.get("url") or None,
                    at=self._clock.now(),
                )
            )
        except Exception:  # noqa: BLE001 - observer must never break the event loop
            log.warning("console_observer_degraded", reason="failed to record console message")

    def _on_pageerror(self, error: Any) -> None:
        try:
            self._events.append(
                ConsoleEvent(level="pageerror", text=str(error), url=None, at=self._clock.now())
            )
        except Exception:  # noqa: BLE001
            log.warning("console_observer_degraded", reason="failed to record page error")

    def drain(self) -> list[ConsoleEvent]:
        """Return and clear everything buffered since the last drain."""
        events, self._events = self._events, []
        return events


class NetworkObserver:
    """Buffers finished responses and transport-level request failures for one page."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._events: list[NetworkEvent] = []

    def attach(self, page: Any) -> None:
        """Subscribe to a page's response and requestfailed events."""
        page.on("response", self._on_response)
        page.on("requestfailed", self._on_request_failed)

    def _on_response(self, response: Any) -> None:
        try:
            request = response.request
            self._events.append(
                NetworkEvent(
                    method=request.method,
                    url=response.url,
                    status=response.status,
                    ok=response.status < 400,
                    resource_type=request.resource_type,
                    at=self._clock.now(),
                )
            )
        except Exception:  # noqa: BLE001
            log.warning("network_observer_degraded", reason="failed to record response")

    def _on_request_failed(self, request: Any) -> None:
        try:
            failure = request.failure
            self._events.append(
                NetworkEvent(
                    method=request.method,
                    url=request.url,
                    status=None,
                    ok=False,
                    resource_type=request.resource_type,
                    failure=str(failure) if failure else "request failed",
                    at=self._clock.now(),
                )
            )
        except Exception:  # noqa: BLE001
            log.warning("network_observer_degraded", reason="failed to record request failure")

    def drain(self) -> list[NetworkEvent]:
        """Return and clear everything buffered since the last drain."""
        events, self._events = self._events, []
        return events
