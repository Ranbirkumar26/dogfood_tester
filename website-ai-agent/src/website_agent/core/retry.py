"""Retry policies and the single async retry helper.

Design rationale: the failure taxonomy (docs/architecture/failure-recovery.md, section 2)
fixes who retries what, how often, and with what backoff. Implementing retries once here,
with injectable sleep and randomness, keeps every retry in the system consistent, counted,
and testable without real waiting. Full jitter is used everywhere: delay is drawn uniformly
from [0, capped_backoff], which avoids synchronized retry bursts when the API server runs
concurrent agents.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")

AsyncSleep = Callable[[float], Awaitable[None]]
OnRetry = Callable[[BaseException, int, float], None]


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded exponential backoff with full jitter.

    Args:
        attempts: total call attempts, including the first (attempts=1 means no retry).
        base_delay: backoff base in seconds; attempt n waits up to base * 2**(n-1).
        max_delay: cap on the backoff window in seconds.
    """

    attempts: int
    base_delay: float
    max_delay: float

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError(f"attempts must be >= 1, got {self.attempts}")
        if self.base_delay < 0 or self.max_delay < self.base_delay:
            raise ValueError(f"invalid delays: base={self.base_delay}, max={self.max_delay}")

    def backoff_window(self, attempt: int) -> float:
        """Upper bound of the jitter window after failed attempt number ``attempt`` (1-based)."""
        return min(self.max_delay, self.base_delay * (2.0 ** (attempt - 1)))


# Presets fixed by the failure-recovery design; config may override the numbers per run.
BROWSER_TRANSIENT_POLICY = RetryPolicy(attempts=2, base_delay=0.5, max_delay=4.0)
LLM_TRANSIENT_POLICY = RetryPolicy(attempts=3, base_delay=1.0, max_delay=30.0)
LLM_REPAIR_POLICY = RetryPolicy(attempts=2, base_delay=0.0, max_delay=0.0)


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy,
    retry_on: tuple[type[BaseException], ...],
    sleep: AsyncSleep = asyncio.sleep,
    rng: Callable[[], float] = random.random,
    on_retry: OnRetry | None = None,
) -> T:
    """Call ``fn`` under ``policy``, retrying only exceptions in ``retry_on``.

    Honors an exception's ``retry_after`` attribute (server-suggested delay) when it
    exceeds the computed jittered backoff. Exceptions outside ``retry_on`` propagate
    immediately; the final failure re-raises the last exception unchanged so callers
    keep the original type and context.

    Args:
        fn: zero-argument coroutine factory; a fresh coroutine is made per attempt.
        policy: attempts and backoff shape.
        retry_on: exception types that are worth retrying.
        sleep: injectable delay function (tests pass a recorder).
        rng: injectable uniform [0,1) source for jitter.
        on_retry: callback (exception, attempt_number, delay_seconds) before each wait,
            used by callers to emit structured log events and count retries.
    """
    last_error: BaseException | None = None
    for attempt in range(1, policy.attempts + 1):
        try:
            return await fn()
        except retry_on as exc:  # noqa: PERF203 - loop-level catch is the point here
            last_error = exc
            if attempt == policy.attempts:
                break
            delay = rng() * policy.backoff_window(attempt)
            retry_after = getattr(exc, "retry_after", None)
            if retry_after is not None:
                delay = max(delay, float(retry_after))
            if on_retry is not None:
                on_retry(exc, attempt, delay)
            if delay > 0:
                await sleep(delay)
    assert last_error is not None  # attempts >= 1 guarantees an exception reached here
    raise last_error
