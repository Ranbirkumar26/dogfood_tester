"""Shared fixtures for the whole suite.

Every test runs with a scrubbed WA_* environment so developer machines and CI cannot leak
real configuration (or secrets) into assertions.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from website_agent.core.clock import FixedClock


@pytest.fixture(autouse=True)
def _clean_wa_env(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    for key in [k for k in os.environ if k.startswith("WA_")]:
        monkeypatch.delenv(key)


@pytest.fixture
def fixed_clock() -> FixedClock:
    return FixedClock(datetime(2026, 7, 20, 12, 0, 0, tzinfo=UTC))
