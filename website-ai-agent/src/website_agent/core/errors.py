"""Exception hierarchy mapped 1:1 onto the failure taxonomy (docs/architecture/failure-recovery.md).

Design rationale: failure class determines owner and retry policy, so classification must be
structural (exception type), never string matching on messages. Each class carries a
``retryable`` marker consumed by the retry helpers, and a ``context`` dict for structured
detail. Context must never contain secrets; it flows into logs and reports verbatim.
"""

from __future__ import annotations

from typing import Any, ClassVar


class AgentError(Exception):
    """Base for every error raised by this project.

    Args:
        message: human-readable summary, stable enough to appear in reports.
        context: structured detail (URLs, element IDs, attempt counts). No secrets.
    """

    retryable: ClassVar[bool] = False

    def __init__(self, message: str, *, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.context: dict[str, Any] = context or {}

    def __str__(self) -> str:
        if not self.context:
            return self.message
        detail = ", ".join(f"{k}={v!r}" for k, v in sorted(self.context.items()))
        return f"{self.message} ({detail})"


class ConfigError(AgentError):
    """Invalid or missing configuration. Fatal at bootstrap (class F8)."""


class DependencyError(AgentError):
    """Dependency-injection failure: unregistered interface or resolution cycle."""


class PolicyViolationError(AgentError):
    """Action blocked by run policy: off-allowlist navigation or disallowed
    destructive action (design D12). Never retried; surfaced in reports."""


class BrowserError(AgentError):
    """Base for browser-layer failures."""


class BrowserTransientError(BrowserError):
    """Recoverable browser failure: detached element, intercepted click,
    navigation timeout (class F1). Retried in place by the tool layer."""

    retryable: ClassVar[bool] = True


class BrowserFatalError(BrowserError):
    """Browser or context crash (class F2). BrowserManager relaunches once
    per run; a second occurrence escalates to FatalError."""


class ModelError(AgentError):
    """Base for LLM-layer failures."""


class ModelTransientError(ModelError):
    """Recoverable provider failure: 5xx, timeout, connection reset (class F3).

    Args:
        retry_after: server-suggested delay in seconds, honored by the retry
            helper when it exceeds the computed backoff.
    """

    retryable: ClassVar[bool] = True

    def __init__(
        self,
        message: str,
        *,
        retry_after: float | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, context=context)
        self.retry_after = retry_after


class ModelRateLimitError(ModelTransientError):
    """HTTP 429 from the provider (class F3). Separate type so rate limiting
    can be counted and alerted on distinctly from generic transients."""


class OutputParseError(ModelError):
    """Model output failed schema validation after the bounded repair reprompt
    (class F4). The owning step fails with semantic (F5) handling."""


class StateError(AgentError):
    """Persistence failure: corrupt checkpoint, schema version mismatch,
    non-resumable run."""


class FatalError(AgentError):
    """Unrecoverable run failure (class F8): unreachable start URL, rejected
    auth state, repeated browser crash. Run finalizes with stop_reason=fatal_error."""
