"""State value models: policy, budgets, counters, functional updates."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from website_agent.core.types import GoalMode, RiskClass
from website_agent.state.models import Budgets, Counters, RunPolicy


def test_policy_permits_by_risk_class() -> None:
    default = RunPolicy()
    assert default.permits(RiskClass.SAFE)
    assert default.permits(RiskClass.MUTATING)
    assert not default.permits(RiskClass.DESTRUCTIVE)

    strict = RunPolicy(allow_mutating=False)
    assert strict.permits(RiskClass.SAFE)
    assert not strict.permits(RiskClass.MUTATING)

    permissive = RunPolicy(allow_destructive=True)
    assert permissive.permits(RiskClass.DESTRUCTIVE)


def test_budgets_allow_zero_usd_but_positive_steps() -> None:
    Budgets(max_steps=1, max_tokens=1, max_usd=0.0, max_wall_seconds=1, max_consecutive_failures=1)
    with pytest.raises(ValidationError):
        Budgets(
            max_steps=0, max_tokens=1, max_usd=0.0, max_wall_seconds=1, max_consecutive_failures=1
        )


def test_counters_elapsed_seconds() -> None:
    start = datetime(2026, 7, 20, 12, 0, 0, tzinfo=UTC)
    counters = Counters(started_at=start)
    assert counters.elapsed_seconds(start + timedelta(seconds=45)) == 45.0
    assert Counters().elapsed_seconds(start) == 0.0  # not started yet


def test_goal_mode_values() -> None:
    assert GoalMode.EXPLORE.value == "explore"
