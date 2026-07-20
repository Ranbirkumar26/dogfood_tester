"""AgentRunner: the run lifecycle over the compiled graph.

Design rationale: one service assembles the dependency graph, drives the LangGraph app, and
persists the outcome, so the CLI and API are thin adapters over it (docs/architecture/
components.md, rule 5). The runner owns the browser session lifecycle and the checkpoint
store; the graph owns the loop. The LangGraph recursion limit is set above the step budget so
budgets (design D10), not the framework, are what actually stop a run; the recursion limit is
only a last-resort guard. Resume rebuilds the non-serializable handles (session, memory) from
the durable checkpoint and continues.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from langgraph.checkpoint.memory import MemorySaver

from website_agent.agent.graph import build_graph
from website_agent.agent.graph_state import GraphState
from website_agent.agent.nodes import GraphDeps
from website_agent.browser.manager import BrowserManager
from website_agent.config.settings import Settings
from website_agent.core.artifacts import FileArtifactStore
from website_agent.core.clock import Clock, SystemClock
from website_agent.core.ids import generate_run_id
from website_agent.executor.executor import Executor
from website_agent.llm.ledger import TokenLedger
from website_agent.llm.manager import ModelManager
from website_agent.llm.pricing import PriceTable
from website_agent.llm.rate_limit import AsyncRateLimiter
from website_agent.logging import bind_run_context, get_logger
from website_agent.memory.service import MemoryService
from website_agent.planner.planner import Planner
from website_agent.prompts.manager import PromptManager
from website_agent.qa.engine import QaEngine
from website_agent.reviewer.reviewer import Reviewer
from website_agent.state.agent_state import AgentState
from website_agent.state.models import Budgets, GoalSpec, RunPolicy, RunResult
from website_agent.state.store import CheckpointStore

log = get_logger("agent.runner")


@dataclass
class RunSpec:
    """Per-run parameters, layered over settings defaults."""

    goal: GoalSpec
    policy: RunPolicy = field(default_factory=RunPolicy)
    budgets: Budgets | None = None  # None uses settings.budgets
    max_attempts: int = 2
    loop_limit: int = 5


class AgentRunner:
    """Assembles dependencies and runs the agent graph to a RunResult."""

    def __init__(
        self,
        settings: Settings,
        *,
        clock: Clock | None = None,
        model_manager: ModelManager | None = None,
    ) -> None:
        self._settings = settings
        self._clock = clock or SystemClock()
        # An injected model manager lets tests run the full graph with scripted responses;
        # otherwise one is built per run so the ledger is run-scoped.
        self._injected_model = model_manager
        self._store = CheckpointStore(settings.paths.checkpoint_db)

    async def run(self, spec: RunSpec) -> RunResult:
        """Execute a fresh run end to end and return its result."""
        run_id = generate_run_id(self._clock)
        budgets = spec.budgets or _budgets_from_settings(self._settings)
        store = FileArtifactStore(self._settings.paths.reports_dir, run_id, self._clock)
        ledger = TokenLedger(PriceTable(), self._clock)
        model = self._injected_model or _build_model(self._settings, ledger, self._clock)

        initial = GraphState(
            agent=AgentState(run_id=run_id, goal=spec.goal, policy=spec.policy, budgets=budgets)
        )

        async with BrowserManager(self._settings.browser) as manager:
            session = await manager.new_session(self._clock, store)
            memory = MemoryService()
            prompts = PromptManager()
            deps = GraphDeps(
                session=session,
                planner=Planner(model, prompts),
                executor=Executor(self._clock),
                reviewer=Reviewer(model, prompts),
                memory=memory,
                ledger=ledger,
                clock=self._clock,
                store=store,
                qa_engine=QaEngine(),
                max_attempts=spec.max_attempts,
                loop_limit=spec.loop_limit,
            )
            app = build_graph(deps, checkpointer=MemorySaver())
            config = {
                "configurable": {"thread_id": run_id},
                "recursion_limit": budgets.max_steps * 6 + 20,
            }
            with bind_run_context(run_id=run_id):
                final = await app.ainvoke(initial, config=config)

            final_state = _as_graph_state(final)
            self._store.save(final_state.agent)

        assert final_state.run_result is not None  # finalize always sets it
        return final_state.run_result

    def list_runs(self) -> list[dict[str, object]]:
        """Run-registry rows (newest first) for the CLI and API."""
        return self._store.list_runs()

    def close(self) -> None:
        """Release the checkpoint store."""
        self._store.close()


def _budgets_from_settings(settings: Settings) -> Budgets:
    b = settings.budgets
    return Budgets(
        max_steps=b.max_steps,
        max_tokens=b.max_tokens,
        max_usd=b.max_usd,
        max_wall_seconds=b.max_wall_seconds,
        max_consecutive_failures=b.max_consecutive_failures,
    )


def _build_model(settings: Settings, ledger: TokenLedger, clock: Clock) -> ModelManager:
    limiter = AsyncRateLimiter(settings.llm.requests_per_minute, clock)
    return ModelManager(settings.llm, ledger, limiter)


def _as_graph_state(final: object) -> GraphState:
    """LangGraph returns state as a dict; rehydrate the typed GraphState."""
    if isinstance(final, GraphState):
        return final
    return GraphState.model_validate(final)
