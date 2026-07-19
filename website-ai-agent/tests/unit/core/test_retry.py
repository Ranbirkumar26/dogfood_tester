"""Retry helper: policies, backoff bounds, jitter, retry_after, pass-through semantics."""

from __future__ import annotations

import pytest

from website_agent.core.errors import BrowserTransientError, FatalError, ModelRateLimitError
from website_agent.core.retry import (
    BROWSER_TRANSIENT_POLICY,
    LLM_REPAIR_POLICY,
    LLM_TRANSIENT_POLICY,
    RetryPolicy,
    retry_async,
)


class SleepRecorder:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


class Flaky:
    """Fails ``failures`` times, then returns ``result``."""

    def __init__(self, failures: int, exc: BaseException, result: str = "ok") -> None:
        self.failures = failures
        self.exc = exc
        self.result = result
        self.calls = 0

    async def __call__(self) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise self.exc
        return self.result


async def test_returns_immediately_on_success() -> None:
    fn = Flaky(failures=0, exc=BrowserTransientError("x"))
    sleep = SleepRecorder()
    result = await retry_async(
        fn, policy=BROWSER_TRANSIENT_POLICY, retry_on=(BrowserTransientError,), sleep=sleep
    )
    assert result == "ok"
    assert fn.calls == 1
    assert sleep.delays == []


async def test_retries_then_succeeds_and_reports_via_callback() -> None:
    fn = Flaky(failures=2, exc=BrowserTransientError("detached"))
    sleep = SleepRecorder()
    seen: list[tuple[int, float]] = []
    result = await retry_async(
        fn,
        policy=RetryPolicy(attempts=3, base_delay=1.0, max_delay=8.0),
        retry_on=(BrowserTransientError,),
        sleep=sleep,
        rng=lambda: 0.5,
        on_retry=lambda exc, attempt, delay: seen.append((attempt, delay)),
    )
    assert result == "ok"
    assert fn.calls == 3
    # Full jitter with rng=0.5: 0.5 * base * 2**(n-1).
    assert sleep.delays == [0.5, 1.0]
    assert seen == [(1, 0.5), (2, 1.0)]


async def test_exhaustion_reraises_last_exception_unchanged() -> None:
    original = BrowserTransientError("persistent", context={"element": "e9"})
    fn = Flaky(failures=99, exc=original)
    with pytest.raises(BrowserTransientError) as excinfo:
        await retry_async(
            fn,
            policy=BROWSER_TRANSIENT_POLICY,
            retry_on=(BrowserTransientError,),
            sleep=SleepRecorder(),
        )
    assert excinfo.value is original
    assert fn.calls == BROWSER_TRANSIENT_POLICY.attempts


async def test_non_retryable_exception_propagates_without_retry() -> None:
    fn = Flaky(failures=99, exc=FatalError("nope"))
    with pytest.raises(FatalError):
        await retry_async(
            fn,
            policy=LLM_TRANSIENT_POLICY,
            retry_on=(BrowserTransientError,),
            sleep=SleepRecorder(),
        )
    assert fn.calls == 1


async def test_backoff_window_is_capped() -> None:
    policy = RetryPolicy(attempts=5, base_delay=1.0, max_delay=4.0)
    assert policy.backoff_window(1) == 1.0
    assert policy.backoff_window(2) == 2.0
    assert policy.backoff_window(3) == 4.0
    assert policy.backoff_window(4) == 4.0  # capped


async def test_retry_after_overrides_smaller_jittered_delay() -> None:
    fn = Flaky(failures=1, exc=ModelRateLimitError("429", retry_after=10.0))
    sleep = SleepRecorder()
    await retry_async(
        fn,
        policy=LLM_TRANSIENT_POLICY,
        retry_on=(ModelRateLimitError,),
        sleep=sleep,
        rng=lambda: 0.0,  # jitter would give 0s; retry_after must win
    )
    assert sleep.delays == [10.0]


async def test_repair_policy_retries_once_with_no_delay() -> None:
    fn = Flaky(failures=1, exc=BrowserTransientError("parse"))
    sleep = SleepRecorder()
    result = await retry_async(
        fn, policy=LLM_REPAIR_POLICY, retry_on=(BrowserTransientError,), sleep=sleep
    )
    assert result == "ok"
    assert fn.calls == 2
    assert sleep.delays == []  # zero-delay policy must not sleep at all


def test_policy_validation_rejects_nonsense() -> None:
    with pytest.raises(ValueError, match="attempts"):
        RetryPolicy(attempts=0, base_delay=1.0, max_delay=2.0)
    with pytest.raises(ValueError, match="delays"):
        RetryPolicy(attempts=2, base_delay=5.0, max_delay=1.0)
