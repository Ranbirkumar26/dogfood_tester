"""Crash-resume: a run that crashes mid-flight continues from its checkpoint.

Simulates a real crash by having the model raise partway through, then resumes with a
healthy model. Exercises the persisted-checkpoint path end to end over a real browser
(design D8, failure-recovery.md section 4).
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from website_agent.agent.runner import AgentRunner, RunSpec
from website_agent.config.settings import BrowserSettings, PathSettings, Settings
from website_agent.core.clock import SystemClock
from website_agent.core.types import GoalMode, StopReason
from website_agent.llm.manager import ModelManager
from website_agent.planner.models import ExpectationKind, PlannerScoring, ScoredCandidate
from website_agent.reviewer.models import ReviewDecision, ReviewerJudgement
from website_agent.state.models import Budgets, GoalSpec, RunPolicy

pytestmark = pytest.mark.integration


class CrashingModel:
    """Plans and reviews normally, then raises on the Nth planner call to simulate a crash."""

    def __init__(self, crash_on_planner_call: int) -> None:
        self._crash_on = crash_on_planner_call
        self.planner_calls = 0

    async def complete(self, role: str, prompt: object, schema: type) -> object:
        if schema.__name__ == "PlannerScoring":
            self.planner_calls += 1
            if self.planner_calls >= self._crash_on:
                raise RuntimeError("simulated provider crash")
            return PlannerScoring(
                scored=(
                    ScoredCandidate(
                        index=1, goal_relevance=0.9, expectation_kind=ExpectationKind.URL_CHANGE
                    ),
                )
            )
        return ReviewerJudgement(expectation_met=True, decision=ReviewDecision.SUCCESS)


class HealthyModel:
    async def complete(self, role: str, prompt: object, schema: type) -> object:
        if schema.__name__ == "PlannerScoring":
            return PlannerScoring(
                scored=(
                    ScoredCandidate(
                        index=1, goal_relevance=0.9, expectation_kind=ExpectationKind.URL_CHANGE
                    ),
                )
            )
        return ReviewerJudgement(expectation_met=True, decision=ReviewDecision.SUCCESS)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        browser=BrowserSettings(headless=True, action_timeout_ms=5000, nav_timeout_ms=10000),
        paths=PathSettings(
            reports_dir=tmp_path / "reports",
            checkpoint_db=tmp_path / "reports" / "checkpoints.sqlite3",
        ),
    )


def _spec(url: str) -> RunSpec:
    return RunSpec(
        goal=GoalSpec(mode=GoalMode.EXPLORE, start_url=f"{url}/index.html"),
        policy=RunPolicy(),
        budgets=Budgets(
            max_steps=20,
            max_tokens=1_000_000,
            max_usd=1.0,
            max_wall_seconds=120,
            max_consecutive_failures=8,
        ),
    )


async def test_run_crashes_then_resumes_to_completion(
    static_basic_url: str, tmp_path: Path
) -> None:
    settings = _settings(tmp_path)
    run_id = "run_resume_test"

    # First attempt: crashes on the second planning pass, after taking at least one step.
    crashing = AgentRunner(
        settings, clock=SystemClock(), model_manager=cast(ModelManager, CrashingModel(2))
    )
    try:
        with pytest.raises(RuntimeError, match="simulated provider crash"):
            await crashing.run_collecting(_spec(static_basic_url), run_id=run_id)
    finally:
        crashing.close()

    # Resume with a healthy model: continues from the checkpoint to a clean finish.
    resumer = AgentRunner(
        settings, clock=SystemClock(), model_manager=cast(ModelManager, HealthyModel())
    )
    try:
        result = await resumer.resume(run_id)
        runs = {r["run_id"]: r for r in resumer.list_runs()}
    finally:
        resumer.close()

    assert result.run_id == run_id
    assert result.stop_reason in {StopReason.FRONTIER_EXHAUSTED, StopReason.BUDGET_STEPS}
    assert result.steps >= 1
    assert result.pages_visited >= 1
    assert runs[run_id]["status"] == "finished"


async def test_resume_unknown_run_raises(tmp_path: Path) -> None:
    from website_agent.core.errors import StateError

    resumer = AgentRunner(_settings(tmp_path), clock=SystemClock())
    try:
        with pytest.raises(StateError, match="no checkpoint"):
            await resumer.resume("never_existed")
    finally:
        resumer.close()
