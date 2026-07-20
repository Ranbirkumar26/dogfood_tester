"""Client-side request rate limiting: sliding one-minute window.

Design rationale: provider 429s are handled reactively by the retry policy, but a
client-side limiter keeps the agent a good citizen proactively and prevents burst-retry
feedback loops when the API server runs several agents in one process. Sliding window
over a fixed bucket because agent traffic is bursty (plan spikes, then quiet execution);
the window shapes bursts without penalizing sustained low rates. Clock and sleep are
injected so tests never wait real time.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable

from website_agent.core.clock import Clock

_WINDOW_SECONDS = 60.0

AsyncSleep = Callable[[float], Awaitable[None]]


class AsyncRateLimiter:
    """Admits at most ``requests_per_minute`` acquisitions per sliding minute.

    Args:
        requests_per_minute: 0 disables limiting entirely.
        clock: monotonic time source.
        sleep: injectable wait (tests pass a recorder that advances a fake clock).
    """

    def __init__(
        self,
        requests_per_minute: int,
        clock: Clock,
        sleep: AsyncSleep = asyncio.sleep,
    ) -> None:
        self._limit = requests_per_minute
        self._clock = clock
        self._sleep = sleep
        self._window: deque[float] = deque()

    async def acquire(self) -> None:
        """Block until a request slot is available, then consume it."""
        if self._limit <= 0:
            return
        while True:
            now = self._clock.monotonic()
            while self._window and now - self._window[0] >= _WINDOW_SECONDS:
                self._window.popleft()
            if len(self._window) < self._limit:
                self._window.append(now)
                return
            await self._sleep(self._window[0] + _WINDOW_SECONDS - now)

    @property
    def in_flight_window(self) -> int:
        """Requests currently counted in the window (diagnostics and tests)."""
        return len(self._window)
