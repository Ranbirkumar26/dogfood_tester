"""Time as an injected dependency.

Design rationale: budgets (wall-clock), backoff, and artifact timestamps all read time.
Direct ``datetime.now()`` calls would make retry and budget logic untestable without
sleeping, so every component takes a Clock and tests inject FixedClock.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """Source of wall-clock and monotonic time."""

    def now(self) -> datetime:
        """Current time as an aware UTC datetime."""
        ...

    def monotonic(self) -> float:
        """Monotonic seconds; use for durations, never for timestamps."""
        ...


class SystemClock:
    """Production clock backed by the OS."""

    def now(self) -> datetime:
        """Current time as an aware UTC datetime."""
        return datetime.now(UTC)

    def monotonic(self) -> float:
        """Monotonic seconds from ``time.monotonic``."""
        return time.monotonic()


class FixedClock:
    """Deterministic clock for tests; advances only when told to.

    Args:
        start: initial wall-clock time (must be timezone-aware).
    """

    def __init__(self, start: datetime) -> None:
        if start.tzinfo is None:
            raise ValueError("FixedClock requires an aware datetime")
        self._now = start
        self._mono = 0.0

    def now(self) -> datetime:
        """Current frozen time."""
        return self._now

    def monotonic(self) -> float:
        """Current frozen monotonic value."""
        return self._mono

    def advance(self, seconds: float) -> None:
        """Move both wall-clock and monotonic time forward by ``seconds``."""
        from datetime import timedelta

        self._now += timedelta(seconds=seconds)
        self._mono += seconds
