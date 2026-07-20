"""Graph assembly and node unit coverage with a fully faked session and model."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from website_agent.agent.graph import build_graph
from website_agent.agent.graph_state import GraphState
from website_agent.agent.nodes import GraphDeps, GraphNodes
from website_agent.browser.models import ElementRecord, ObservationBundle, PageSnapshot
from website_agent.browser.session import BrowserSession
from website_agent.core.clock import FixedClock
from website_agent.core.types import GoalMode, RiskClass, StopReason
from website_agent.executor.executor import Executor
from website_agent.llm.ledger import TokenLedger
from website_agent.llm.manager import ModelManager
from website_agent.llm.pricing import PriceTable
from website_agent.memory.service import MemoryService
from website_agent.planner.models import (
    ActionType,
    Expectation,
    ExpectationKind,
    Plan,
    PlannerScoring,
    PlanStep,
    ScoredCandidate,
)
from website_agent.planner.planner import Planner
from website_agent.prompts.manager import PromptManager
from website_agent.reviewer.models import ReviewDecision, ReviewerJudgement, ReviewVerdict
from website_agent.reviewer.reviewer import Reviewer
from website_agent.state.agent_state import AgentState
from website_agent.state.models import Budgets, GoalSpec, RunPolicy

NOW = datetime(2026, 7, 20, tzinfo=UTC)


class RoutedModel:
    def __init__(self, planner_scoring: PlannerScoring, judgement: ReviewerJudgement) -> None:
        self._scoring = planner_scoring
        self._judgement = judgement

    async def complete(self, role: str, prompt: object, schema: type) -> object:
        if schema.__name__ == "PlannerScoring":
            return self._scoring
        return self._judgement


class FakePage:
    def __init__(self, url: str) -> None:
        self.url = url


class FakeScreens:
    async def capture(self, page: object, tag: str) -> None:
        return None


class FakeSession:
    """A tiny session: one link that navigates once, then the frontier is exhausted."""

    def __init__(self) -> None:
        self._page = FakePage("https://ex.com/")
        self.screenshots = FakeScreens()
        self._navigated = False

    @property
    def page(self) -> FakePage:
        return self._page

    async def goto(self, url: str) -> int:
        self._page.url = url
        return 200

    async def click(self, element_id: str) -> None:
        self._page.url = "https://ex.com/next"
        self._navigated = True

    async def wait_for_load(self, state: str = "load") -> None:
        return None

    async def snapshot(self) -> PageSnapshot:
        if self._navigated:
            # Destination page has no interactive elements: frontier exhausts here.
            return PageSnapshot(url=self._page.url, title="Next", captured_at=NOW, elements=[])
        return PageSnapshot(
            url=self._page.url,
            title="Home",
            captured_at=NOW,
            elements=[
                ElementRecord(
                    element_id="e1",
                    tag="a",
                    role="link",
                    name="Go",
                    href="https://ex.com/next",
                    selectors=["css=#e1"],
                )
            ],
        )

    def drain_observations(self, step_id: str) -> ObservationBundle:
        return ObservationBundle(step_id=step_id)

    async def save_storage_state(self) -> None:
        return None


def _deps(fixed_clock: FixedClock) -> GraphDeps:
    model = cast(
        ModelManager,
        RoutedModel(
            PlannerScoring(
                scored=(
                    ScoredCandidate(
                        index=1, goal_relevance=0.9, expectation_kind=ExpectationKind.URL_CHANGE
                    ),
                )
            ),
            ReviewerJudgement(expectation_met=True, decision=ReviewDecision.SUCCESS),
        ),
    )
    prompts = PromptManager()
    memory = MemoryService()
    return GraphDeps(
        session=cast(BrowserSession, FakeSession()),
        planner=Planner(model, prompts),
        executor=Executor(fixed_clock),
        reviewer=Reviewer(model, prompts),
        memory=memory,
        ledger=TokenLedger(PriceTable(), fixed_clock),
        clock=fixed_clock,
    )


def _initial() -> GraphState:
    return GraphState(
        agent=AgentState(
            run_id="run_smoke",
            goal=GoalSpec(mode=GoalMode.EXPLORE, start_url="https://ex.com/"),
            policy=RunPolicy(),
            budgets=Budgets(
                max_steps=10,
                max_tokens=100000,
                max_usd=1.0,
                max_wall_seconds=120,
                max_consecutive_failures=5,
            ),
        )
    )


async def test_compiled_graph_runs_to_finalize(fixed_clock: FixedClock) -> None:
    app = build_graph(_deps(fixed_clock))
    final = await app.ainvoke(
        _initial(), config={"configurable": {"thread_id": "t"}, "recursion_limit": 60}
    )
    state = GraphState.model_validate(final)
    assert state.run_result is not None
    assert state.run_result.stop_reason is StopReason.FRONTIER_EXHAUSTED
    assert state.run_result.pages_visited >= 1


async def test_graph_exports_mermaid(fixed_clock: FixedClock) -> None:
    app = build_graph(_deps(fixed_clock))
    mermaid = app.get_graph().draw_mermaid()
    assert "bootstrap" in mermaid
    assert "planner" in mermaid
    assert "finalize" in mermaid


async def test_nodes_bootstrap_sets_started_at(fixed_clock: FixedClock) -> None:
    nodes = GraphNodes(_deps(fixed_clock))
    update = await nodes.bootstrap(_initial())
    agent = update["agent"]
    assert agent.counters.started_at == fixed_clock.now()  # type: ignore[attr-defined]
    assert agent.current_snapshot is not None  # type: ignore[attr-defined]


def _step() -> PlanStep:
    return PlanStep(
        step_id="step_0001",
        action=ActionType.CLICK,
        element_id="e1",
        element_signature="sig",
        label="click",
        risk=RiskClass.SAFE,
        expectation=Expectation(kind=ExpectationKind.CONTENT_CHANGE),
    )


async def test_executor_node_reuses_current_step_on_retry(fixed_clock: FixedClock) -> None:
    nodes = GraphNodes(_deps(fixed_clock))
    step = _step()
    # A RETRY verdict with a current step: the executor must re-run that step, not pop a new one.
    state = _initial().model_copy(
        update={
            "current_step": step,
            "plan": Plan(steps=()),  # empty queue: proves it did not pop from here
            "step_attempt": 1,
            "last_verdict": ReviewVerdict(
                step_id="step_0001", decision=ReviewDecision.RETRY, expectation_met=False
            ),
        }
    )
    update = await nodes.executor(state)
    assert update["current_step"] is step
    assert update["step_attempt"] == 2


def test_decide_node_poisons_looping_branch(fixed_clock: FixedClock) -> None:
    from website_agent.executor.models import ExecutionResult

    nodes = GraphNodes(_deps(fixed_clock))
    result = ExecutionResult(
        step_id="step_0001",
        action="click",
        element_id="e1",
        ok=True,
        url_before="https://ex.com/",
        url_after="https://ex.com/",
        navigated=False,
        snapshot_after=PageSnapshot(url="https://ex.com/", title="T", captured_at=NOW, elements=[]),
        observations=ObservationBundle(step_id="step_0001"),
        at=NOW,
    )
    state = _initial().model_copy(
        update={
            "current_step": _step(),
            "plan": None,
            "last_result": result,
            "last_verdict": ReviewVerdict(
                step_id="step_0001",
                decision=ReviewDecision.REPLAN,
                expectation_met=False,
                is_loop=True,
            ),
        }
    )
    update = nodes.decide(state)
    assert update["next_edge"] == "planner"
    assert len(update["agent"].loop.poisoned) == 1  # type: ignore[attr-defined]


async def test_finalize_survives_storage_state_failure(fixed_clock: FixedClock) -> None:
    deps = _deps(fixed_clock)

    async def _boom() -> None:
        raise RuntimeError("storage state save failed")

    deps.session.save_storage_state = _boom  # type: ignore[method-assign]
    nodes = GraphNodes(deps)
    update = await nodes.finalize(_initial())
    assert update["run_result"] is not None  # finalize still produced a result
