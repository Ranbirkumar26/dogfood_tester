"""Playwright error classification into the failure taxonomy."""

from __future__ import annotations

import pytest
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from website_agent.browser.errors_map import map_playwright_error
from website_agent.core.errors import (
    BrowserFatalError,
    BrowserTransientError,
    PolicyViolationError,
)


def test_timeout_maps_to_transient() -> None:
    mapped = map_playwright_error(
        PlaywrightTimeoutError("Timeout 10000ms exceeded"), action="click e3"
    )
    assert isinstance(mapped, BrowserTransientError)
    assert mapped.context["action"] == "click e3"


@pytest.mark.parametrize(
    "message",
    [
        "Target closed",
        "Target page, context or browser has been closed",
        "Browser has been closed",
        "Connection closed while reading from the driver",
    ],
)
def test_dead_browser_messages_map_to_fatal(message: str) -> None:
    mapped = map_playwright_error(PlaywrightError(message), action="goto")
    assert isinstance(mapped, BrowserFatalError)


def test_other_playwright_errors_map_to_transient() -> None:
    mapped = map_playwright_error(
        PlaywrightError("Element is not attached to the DOM"), action="click e9"
    )
    assert isinstance(mapped, BrowserTransientError)
    assert mapped.retryable is True


def test_unknown_exceptions_map_to_transient_with_type_in_context() -> None:
    mapped = map_playwright_error(RuntimeError("weird"), action="snapshot")
    assert isinstance(mapped, BrowserTransientError)
    assert mapped.context["playwright_error"] == "RuntimeError"


def test_already_classified_errors_pass_through_unchanged() -> None:
    original = PolicyViolationError("off allowlist")
    assert map_playwright_error(original, action="goto") is original
