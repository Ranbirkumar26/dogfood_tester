"""Observers: buffering, drain windows, and never-raise degradation."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from website_agent.browser.observers import ConsoleObserver, NetworkObserver
from website_agent.core.clock import FixedClock


class FakePage:
    """Minimal event emitter matching the page.on subscription surface."""

    def __init__(self) -> None:
        self.handlers: dict[str, list[Any]] = {}

    def on(self, event: str, handler: Any) -> None:
        self.handlers.setdefault(event, []).append(handler)

    def emit(self, event: str, payload: Any) -> None:
        for handler in self.handlers.get(event, []):
            handler(payload)


def _console_message(level: str = "error", text: str = "boom") -> SimpleNamespace:
    return SimpleNamespace(type=level, text=text, location={"url": "https://ex.com/app.js"})


def _response(
    status: int = 200,
    url: str = "https://ex.com/api",
    *,
    timing: dict[str, float] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        url=url,
        status=status,
        request=SimpleNamespace(method="GET", resource_type="fetch", timing=timing),
    )


def test_console_observer_buffers_and_drains_in_windows(fixed_clock: FixedClock) -> None:
    page = FakePage()
    observer = ConsoleObserver(fixed_clock)
    observer.attach(page)

    page.emit("console", _console_message("log", "first"))
    page.emit("console", _console_message("error", "second"))
    first_window = observer.drain()
    assert [(e.level, e.text) for e in first_window] == [("log", "first"), ("error", "second")]
    assert first_window[0].url == "https://ex.com/app.js"

    page.emit("console", _console_message("warning", "third"))
    second_window = observer.drain()
    assert [e.text for e in second_window] == ["third"]
    assert observer.drain() == []


def test_console_observer_records_uncaught_page_errors(fixed_clock: FixedClock) -> None:
    page = FakePage()
    observer = ConsoleObserver(fixed_clock)
    observer.attach(page)
    page.emit("pageerror", ValueError("ReferenceError: x is not defined"))
    [event] = observer.drain()
    assert event.level == "pageerror"
    assert "ReferenceError" in event.text


def test_console_observer_survives_hostile_message_objects(fixed_clock: FixedClock) -> None:
    class HostileMessage:
        @property
        def type(self) -> str:
            raise RuntimeError("driver hiccup")

        text = "x"
        location: dict[str, str] = {}

    page = FakePage()
    observer = ConsoleObserver(fixed_clock)
    observer.attach(page)
    page.emit("console", HostileMessage())  # must not raise
    page.emit("console", _console_message("log", "after"))
    assert [e.text for e in observer.drain()] == ["after"]


def test_network_observer_records_responses_and_failures(fixed_clock: FixedClock) -> None:
    page = FakePage()
    observer = NetworkObserver(fixed_clock)
    observer.attach(page)

    page.emit("response", _response(200, "https://ex.com/ok"))
    page.emit("response", _response(404, "https://ex.com/missing"))
    page.emit(
        "requestfailed",
        SimpleNamespace(
            method="GET",
            url="https://ex.com/dead",
            resource_type="xhr",
            failure="net::ERR_CONNECTION_REFUSED",
        ),
    )

    events = observer.drain()
    assert [(e.status, e.ok) for e in events] == [(200, True), (404, False), (None, False)]
    assert events[2].failure == "net::ERR_CONNECTION_REFUSED"
    assert observer.drain() == []


def test_network_observer_records_response_duration(fixed_clock: FixedClock) -> None:
    page = FakePage()
    observer = NetworkObserver(fixed_clock)
    observer.attach(page)

    page.emit("response", _response(200, timing={"responseEnd": 321.5}))

    [event] = observer.drain()
    assert event.duration_ms == 321.5


def test_network_observer_survives_hostile_objects(fixed_clock: FixedClock) -> None:
    class HostileResponse:
        @property
        def request(self) -> object:
            raise RuntimeError("gone")

    page = FakePage()
    observer = NetworkObserver(fixed_clock)
    observer.attach(page)
    page.emit("response", HostileResponse())  # must not raise
    page.emit("response", _response(500, "https://ex.com/err"))
    [event] = observer.drain()
    assert event.status == 500
