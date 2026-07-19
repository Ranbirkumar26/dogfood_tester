"""Clock implementations and ID generation."""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest

from website_agent.core.clock import Clock, FixedClock, SystemClock
from website_agent.core.ids import generate_run_id, generate_step_id


def test_system_clock_is_aware_utc_and_monotonic() -> None:
    clock = SystemClock()
    now = clock.now()
    assert now.tzinfo is UTC
    first = clock.monotonic()
    assert clock.monotonic() >= first


def test_fixed_clock_advances_deterministically() -> None:
    clock = FixedClock(datetime(2026, 7, 20, 12, 0, 0, tzinfo=UTC))
    assert clock.monotonic() == 0.0
    clock.advance(90)
    assert clock.now() == datetime(2026, 7, 20, 12, 1, 30, tzinfo=UTC)
    assert clock.monotonic() == 90.0


def test_fixed_clock_rejects_naive_datetimes() -> None:
    with pytest.raises(ValueError, match="aware"):
        FixedClock(datetime(2026, 7, 20))


def test_clocks_satisfy_the_protocol() -> None:
    assert isinstance(SystemClock(), Clock)
    assert isinstance(FixedClock(datetime(2026, 1, 1, tzinfo=UTC)), Clock)


def test_run_id_embeds_timestamp_and_is_unique(fixed_clock: FixedClock) -> None:
    run_id = generate_run_id(fixed_clock)
    assert re.fullmatch(r"run_20260720_120000_[0-9a-f]{6}", run_id)
    ids = {generate_run_id(fixed_clock) for _ in range(200)}
    assert len(ids) == 200


def test_run_ids_sort_by_creation_time(fixed_clock: FixedClock) -> None:
    earlier = generate_run_id(fixed_clock)
    fixed_clock.advance(61)
    later = generate_run_id(fixed_clock)
    assert earlier < later


def test_step_id_is_zero_padded_and_validates() -> None:
    assert generate_step_id(1) == "step_0001"
    assert generate_step_id(42) == "step_0042"
    assert generate_step_id(9) < generate_step_id(10)  # lexicographic == execution order
    with pytest.raises(ValueError, match=">= 1"):
        generate_step_id(0)
