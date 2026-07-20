"""End-to-end agent graph against the local fixture site with a scripted model.

Exercises the full plan-execute-review-decide loop over a real browser session, with the
LLM replaced by a schema-routed fake so the run is deterministic and keyless.
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
from website_agent.planner.models import (
    ExpectationKind,
    PlannerScoring,
    ScoredCandidate,
)
from website_agent.reviewer.models import ReviewDecision, ReviewerJudgement
from website_agent.state.models import Budgets, GoalSpec, RunPolicy

pytestmark = pytest.mark.integration


class SchemaRoutedModel:
    """Fake model: schedules the top candidate and judges every step a success.

    Planner expectations are URL_CHANGE (mechanical), so the reviewer settles most steps
    without an LLM call; the ReviewerJudgement branch covers the rest.
    """

    def __init__(self) -> None:
        self.planner_calls = 0
        self.reviewer_calls = 0

    async def complete(self, role: str, prompt: object, schema: type) -> object:
        name = schema.__name__
        if name == "PlannerScoring":
            self.planner_calls += 1
            return PlannerScoring(
                scored=(
                    ScoredCandidate(
                        index=1,
                        goal_relevance=0.9,
                        expectation_kind=ExpectationKind.URL_CHANGE,
                    ),
                ),
                rationale="explore top candidate",
            )
        if name == "ReviewerJudgement":
            self.reviewer_calls += 1
            return ReviewerJudgement(
                expectation_met=True, decision=ReviewDecision.SUCCESS, reasoning="looks fine"
            )
        raise AssertionError(f"unexpected schema {name}")


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        browser=BrowserSettings(headless=True, action_timeout_ms=5000, nav_timeout_ms=10000),
        paths=PathSettings(
            reports_dir=tmp_path / "reports",
            checkpoint_db=tmp_path / "reports" / "checkpoints.sqlite3",
        ),
    )


async def test_agent_explores_fixture_site_to_completion(
    static_basic_url: str, tmp_path: Path
) -> None:
    settings = _settings(tmp_path)
    model = cast(ModelManager, SchemaRoutedModel())
    runner = AgentRunner(settings, clock=SystemClock(), model_manager=model)
    try:
        result = await runner.run(
            RunSpec(
                goal=GoalSpec(mode=GoalMode.EXPLORE, start_url=f"{static_basic_url}/index.html"),
                policy=RunPolicy(),
                budgets=Budgets(
                    max_steps=12,
                    max_tokens=1_000_000,
                    max_usd=1.0,
                    max_wall_seconds=120,
                    max_consecutive_failures=8,
                ),
            )
        )
    finally:
        runner.close()

    # The run terminated cleanly for a real reason (budget or frontier exhausted).
    assert result.stop_reason in {
        StopReason.BUDGET_STEPS,
        StopReason.FRONTIER_EXHAUSTED,
    }
    assert result.steps >= 1
    assert result.pages_visited >= 1
    assert result.finished_at is not None


async def test_run_is_recorded_in_the_registry(static_basic_url: str, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runner = AgentRunner(
        settings, clock=SystemClock(), model_manager=cast(ModelManager, SchemaRoutedModel())
    )
    try:
        result = await runner.run(
            RunSpec(
                goal=GoalSpec(mode=GoalMode.EXPLORE, start_url=f"{static_basic_url}/about.html"),
                budgets=Budgets(
                    max_steps=4,
                    max_tokens=1_000_000,
                    max_usd=1.0,
                    max_wall_seconds=60,
                    max_consecutive_failures=8,
                ),
            )
        )
        runs = runner.list_runs()
    finally:
        runner.close()

    assert any(r["run_id"] == result.run_id for r in runs)
    recorded = next(r for r in runs if r["run_id"] == result.run_id)
    assert recorded["status"] == "finished"
