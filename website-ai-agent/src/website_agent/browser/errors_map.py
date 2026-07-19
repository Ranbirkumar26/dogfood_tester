"""Playwright exception classification into the project failure taxonomy.

Design rationale: the taxonomy (docs/architecture/failure-recovery.md) is enforced by type,
so raw Playwright errors must never escape the browser layer. Classification is
conservative: closed targets and dead browser processes are fatal (F2); everything else,
including timeouts and transient page weirdness, is transient (F1) because F1 retries are
tightly bounded anyway and misclassifying a transient as fatal kills runs needlessly.
"""

from __future__ import annotations

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from website_agent.core.errors import AgentError, BrowserFatalError, BrowserTransientError

# Substrings Playwright uses when the browser, context, or page is gone for good.
_FATAL_MARKERS = (
    "target closed",
    "target page, context or browser has been closed",
    "browser has been closed",
    "browser closed",
    "connection closed",
    "has been closed",
)


def map_playwright_error(exc: BaseException, *, action: str) -> AgentError:
    """Translate a Playwright exception into the taxonomy.

    Args:
        exc: the caught exception.
        action: what was being attempted (goes into error context for logs).

    Already-classified AgentErrors pass through unchanged so nested layers can
    pre-classify without double wrapping.
    """
    if isinstance(exc, AgentError):
        return exc

    context = {"action": action, "playwright_error": type(exc).__name__}

    if isinstance(exc, PlaywrightTimeoutError):
        return BrowserTransientError(f"timeout during {action}", context=context)

    if isinstance(exc, PlaywrightError):
        message = str(exc).lower()
        if any(marker in message for marker in _FATAL_MARKERS):
            return BrowserFatalError(f"browser gone during {action}", context=context)
        return BrowserTransientError(f"browser error during {action}", context=context)

    return BrowserTransientError(f"unexpected error during {action}", context=context)
