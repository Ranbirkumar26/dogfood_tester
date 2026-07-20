"""AgentState functional-update helpers and serialization."""

from __future__ import annotations

from datetime import UTC, datetime

from website_agent.core.types import GoalMode, StopReason
from website_agent.state.agent_state import STATE_SCHEMA_VERSION, AgentState
from website_agent.state.models import ActionRecord, Budgets, Counters, GoalSpec, RunPolicy

NOW = datetime(2026, 7, 20, tzinfo=UTC)


def _state() -> AgentState:
    return AgentState(
        run_id="run_x",
        goal=GoalSpec(mode=GoalMode.TEST, start_url="https://ex.com/"),
        policy=RunPolicy(),
        budgets=Budgets(
            max_steps=10,
            max_tokens=100,
            max_usd=0.0,
            max_wall_seconds=60,
            max_consecutive_failures=2,
        ),
    )


def test_default_schema_version_is_current() -> None:
    assert _state().schema_version == STATE_SCHEMA_VERSION


def test_with_updates_returns_evolved_copy() -> None:
    state = _state()
    updated = state.with_updates(counters=Counters(steps=3), stop_reason=StopReason.GOAL_MET)
    assert updated.counters.steps == 3
    assert updated.stop_reason is StopReason.GOAL_MET
    assert state.counters.steps == 0  # original unchanged (frozen)


def test_append_action_grows_immutable_history() -> None:
    state = _state()
    record = ActionRecord(
        step_id="step_0001",
        action="click",
        element_id="e1",
        element_signature="sig",
        url_before="https://ex.com/",
        url_after="https://ex.com/next",
        success=True,
        at=NOW,
    )
    with_one = state.append_action(record)
    assert len(with_one.action_history) == 1
    assert len(state.action_history) == 0  # original untouched
    assert with_one.append_action(record).action_history[-1] is record


def test_state_serializes_and_restores() -> None:
    state = _state().with_updates(counters=Counters(steps=2, tokens=50, usd=0.0))
    restored = AgentState.model_validate_json(state.model_dump_json())
    assert restored == state
