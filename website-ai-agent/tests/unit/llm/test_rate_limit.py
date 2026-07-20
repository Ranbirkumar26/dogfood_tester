"""Rate limiter: disabled pass-through, window admission, sliding expiry."""

from __future__ import annotations

from website_agent.core.clock import FixedClock
from website_agent.llm.rate_limit import AsyncRateLimiter


class RecordingSleep:
    """Fake async sleep that advances a FixedClock and records requested waits."""

    def __init__(self, clock: FixedClock) -> None:
        self._clock = clock
        self.waits: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)
        self._clock.advance(max(0.0, seconds))


async def test_zero_limit_disables_limiting(fixed_clock: FixedClock) -> None:
    sleep = RecordingSleep(fixed_clock)
    limiter = AsyncRateLimiter(0, fixed_clock, sleep)
    for _ in range(1000):
        await limiter.acquire()
    assert sleep.waits == []


async def test_admits_up_to_limit_without_waiting(fixed_clock: FixedClock) -> None:
    sleep = RecordingSleep(fixed_clock)
    limiter = AsyncRateLimiter(3, fixed_clock, sleep)
    for _ in range(3):
        await limiter.acquire()
    assert sleep.waits == []
    assert limiter.in_flight_window == 3


async def test_blocks_when_window_full_then_admits_after_expiry(fixed_clock: FixedClock) -> None:
    sleep = RecordingSleep(fixed_clock)
    limiter = AsyncRateLimiter(2, fixed_clock, sleep)
    await limiter.acquire()  # t=0
    await limiter.acquire()  # t=0, window full
    await limiter.acquire()  # must wait ~60s for the first to expire
    assert sleep.waits
    assert abs(sleep.waits[0] - 60.0) < 1e-6
    # Both t=0 slots expire together at t=60, leaving only the just-admitted request.
    assert limiter.in_flight_window == 1


async def test_sliding_window_expires_old_requests(fixed_clock: FixedClock) -> None:
    sleep = RecordingSleep(fixed_clock)
    limiter = AsyncRateLimiter(1, fixed_clock, sleep)
    await limiter.acquire()  # t=0
    fixed_clock.advance(61)  # first request now outside the 60s window
    await limiter.acquire()  # admitted without waiting
    assert sleep.waits == []
    assert limiter.in_flight_window == 1
