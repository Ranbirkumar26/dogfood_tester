"""End-to-end evaluate command over the fixture site with a scripted model."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from evaluation.harness import (
    build_evidence,
    compute_metrics,
    load_ground_truth,
    score,
)

from website_agent.agent.runner import AgentRunner, RunSpec
from website_agent.config.settings import BrowserSettings, PathSettings, Settings
from website_agent.core.clock import SystemClock
from website_agent.core.types import GoalMode
from website_agent.llm.manager import ModelManager
from website_agent.planner.models import ExpectationKind, PlannerScoring, ScoredCandidate
from website_agent.reviewer.models import ReviewDecision, ReviewerJudgement
from website_agent.state.models import Budgets, GoalSpec, RunPolicy

pytestmark = pytest.mark.integration

_ROOT = Path(__file__).parents[2]


class SchemaRoutedModel:
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


async def test_evaluate_pipeline_scores_a_real_run(static_basic_url: str, tmp_path: Path) -> None:
    settings = Settings(
        browser=BrowserSettings(headless=True, action_timeout_ms=5000, nav_timeout_ms=10000),
        paths=PathSettings(
            reports_dir=tmp_path / "reports",
            checkpoint_db=tmp_path / "reports" / "cp.sqlite3",
        ),
    )
    runner = AgentRunner(
        settings, clock=SystemClock(), model_manager=cast(ModelManager, SchemaRoutedModel())
    )
    try:
        artifacts = await runner.run_collecting(
            RunSpec(
                goal=GoalSpec(mode=GoalMode.EXPLORE, start_url=f"{static_basic_url}/index.html"),
                policy=RunPolicy(),
                budgets=Budgets(
                    max_steps=15,
                    max_tokens=1_000_000,
                    max_usd=1.0,
                    max_wall_seconds=120,
                    max_consecutive_failures=8,
                ),
            )
        )
    finally:
        runner.close()

    truth = load_ground_truth(_ROOT / "evaluation" / "ground_truth" / "static-basic.yaml")
    evidence = build_evidence(
        run_result=artifacts.run_result,
        page_graph=artifacts.page_graph,
        qa_report=artifacts.qa_report,
        action_history=artifacts.action_history,
        ledger_totals=artifacts.ledger_totals,
        screenshots=artifacts.screenshots,
        wall_seconds=artifacts.wall_seconds,
    )
    metrics = compute_metrics(evidence, truth)

    # The agent visits multiple pages and the fixture plants a console error the QA engine
    # catches, so coverage and recall are both positive.
    assert metrics.page_coverage > 0.0
    assert metrics.steps >= 1

    from evaluation.harness.models import Scenario, SuccessCriteria

    lenient = Scenario(
        name="smoke",
        site="static-basic",
        success=SuccessCriteria(min_page_coverage=0.0, min_bug_recall=0.0, min_bug_precision=0.0),
    )
    result = score(lenient, metrics)
    assert result.passed
    # The result serializes for the CI gate.
    assert json.loads(result.model_dump_json())["scenario"] == "smoke"
