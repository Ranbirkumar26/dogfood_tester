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
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from website_agent.agent.graph import build_graph
from website_agent.agent.graph_state import GraphState
from website_agent.agent.nodes import GraphDeps
from website_agent.browser.manager import BrowserManager
from website_agent.config.settings import Settings
from website_agent.core.artifacts import FileArtifactStore
from website_agent.core.clock import Clock, SystemClock
from website_agent.core.errors import StateError
from website_agent.core.ids import generate_run_id
from website_agent.executor.executor import Executor
from website_agent.llm.ledger import LedgerTotals, TokenLedger
from website_agent.llm.manager import ModelManager
from website_agent.llm.pricing import PriceTable
from website_agent.llm.rate_limit import AsyncRateLimiter
from website_agent.logging import bind_run_context, get_logger
from website_agent.memory.graph import PageGraph
from website_agent.memory.service import MemoryService
from website_agent.planner.planner import Planner
from website_agent.prompts.manager import PromptManager
from website_agent.qa.engine import QaEngine
from website_agent.qa.models import QaReport
from website_agent.reporting.engine import ReportingEngine
from website_agent.reporting.inputs import ReportInputs
from website_agent.reviewer.reviewer import Reviewer
from website_agent.state.agent_state import AgentState
from website_agent.state.models import ActionRecord, Budgets, GoalSpec, RunPolicy, RunResult
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


@dataclass
class RunArtifacts:
    """The full raw output of a run, for consumers (like the eval harness) that need more
    than RunResult. Kept as plain package types so dev tooling can reduce it without the
    package importing dev-only code."""

    run_result: RunResult
    qa_report: QaReport
    page_graph: PageGraph
    action_history: tuple[ActionRecord, ...]
    ledger_totals: LedgerTotals
    screenshots: int
    wall_seconds: float


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
        return (await self.run_collecting(spec)).run_result

    async def run_collecting(self, spec: RunSpec, *, run_id: str | None = None) -> RunArtifacts:
        """Execute a run and return the full artifact bundle (for evaluation and tooling).

        ``run_id`` may be supplied for deterministic runs (tests); otherwise one is generated.
        If the run crashes mid-flight, the graph checkpoint persists and the run can be
        continued with :meth:`resume`.
        """
        run_id = run_id or generate_run_id(self._clock)
        budgets = spec.budgets or _budgets_from_settings(self._settings)
        store = FileArtifactStore(self._settings.paths.reports_dir, run_id, self._clock)
        ledger = TokenLedger(PriceTable(), self._clock)
        model = self._injected_model or _build_model(self._settings, ledger, self._clock)
        started = self._clock.monotonic()

        initial = GraphState(
            agent=AgentState(run_id=run_id, goal=spec.goal, policy=spec.policy, budgets=budgets)
        )

        async with (
            BrowserManager(self._settings.browser) as manager,
            AsyncSqliteSaver.from_conn_string(str(self._graph_db)) as saver,
        ):
            session = await manager.new_session(self._clock, store)
            memory = MemoryService()
            deps = self._make_deps(
                session, model, memory, ledger, store, spec.max_attempts, spec.loop_limit
            )
            app = build_graph(deps, checkpointer=saver)
            config = {
                "configurable": {"thread_id": run_id},
                "recursion_limit": budgets.max_steps * 6 + 20,
            }
            with bind_run_context(run_id=run_id):
                final = await app.ainvoke(initial, config=config)
            return self._finish(_as_graph_state(final), memory, ledger, store, session, started)

    async def resume(self, run_id: str) -> RunResult:
        """Resume a crashed run from its last checkpoint and run it to completion."""
        return (await self.resume_collecting(run_id)).run_result

    async def resume_collecting(self, run_id: str) -> RunArtifacts:
        """Resume a run from its persisted checkpoint (design D8, failure-recovery.md s4).

        Rebuilds the browser session, restores storage state if present, navigates to the
        checkpointed page and re-extracts it, rebuilds memory, seeds the ledger with prior
        spend so budgets stay continuous, forces a replan on drift, then continues the graph.
        """
        store = FileArtifactStore(self._settings.paths.reports_dir, run_id, self._clock)
        ledger = TokenLedger(PriceTable(), self._clock)
        model = self._injected_model or _build_model(self._settings, ledger, self._clock)
        started = self._clock.monotonic()
        storage_state = self._storage_state_path(run_id)

        async with (
            BrowserManager(self._settings.browser) as manager,
            AsyncSqliteSaver.from_conn_string(str(self._graph_db)) as saver,
        ):
            session = await manager.new_session(self._clock, store, storage_state=storage_state)
            memory = MemoryService()
            deps = self._make_deps(session, model, memory, ledger, store, 2, 5)
            app = build_graph(deps, checkpointer=saver)
            config: dict[str, Any] = {"configurable": {"thread_id": run_id}}

            snapshot = await app.aget_state(config)
            if not snapshot.values:
                raise StateError("no checkpoint to resume", context={"run_id": run_id})
            checkpointed = _as_graph_state(snapshot.values)
            agent = checkpointed.agent
            assert agent.current_snapshot is not None

            # Rehydrate: reload the checkpointed page and re-extract it fresh.
            await session.goto(agent.current_snapshot.url)
            fresh = await session.snapshot()
            # Rebuild the live memory service from the checkpointed memory; the graph nodes
            # hold the deps object, so reassigning the field is seen on the next node.
            deps.memory = MemoryService(agent.memory)
            ledger.seed(tokens=agent.counters.tokens, cost_usd=agent.counters.usd)

            drift = fresh.snapshot_hash != agent.current_snapshot.snapshot_hash
            await app.aupdate_state(
                config,
                {"agent": agent.with_updates(current_snapshot=fresh, forced_replan=drift)},
            )
            config["recursion_limit"] = agent.budgets.max_steps * 6 + 20
            with bind_run_context(run_id=run_id):
                final = await app.ainvoke(None, config=config)
            return self._finish(
                _as_graph_state(final), deps.memory, ledger, store, session, started
            )

    # ------------------------------------------------------------- internals

    def _make_deps(
        self,
        session: object,
        model: ModelManager,
        memory: MemoryService,
        ledger: TokenLedger,
        store: FileArtifactStore,
        max_attempts: int,
        loop_limit: int,
    ) -> GraphDeps:
        prompts = PromptManager()
        return GraphDeps(
            session=session,  # type: ignore[arg-type]
            planner=Planner(model, prompts),
            executor=Executor(self._clock),
            reviewer=Reviewer(model, prompts),
            memory=memory,
            ledger=ledger,
            clock=self._clock,
            store=store,
            qa_engine=QaEngine(),
            max_attempts=max_attempts,
            loop_limit=loop_limit,
        )

    def _finish(
        self,
        final_state: GraphState,
        memory: MemoryService,
        ledger: TokenLedger,
        store: FileArtifactStore,
        session: object,
        started: float,
    ) -> RunArtifacts:
        self._store.save(final_state.agent)
        self._generate_reports(final_state, memory, store)
        assert final_state.run_result is not None  # finalize always sets it on completion
        assert final_state.qa_report is not None
        return RunArtifacts(
            run_result=final_state.run_result,
            qa_report=final_state.qa_report,
            page_graph=memory.graph,
            action_history=final_state.agent.action_history,
            ledger_totals=ledger.totals(),
            screenshots=session.screenshots.count,  # type: ignore[attr-defined]
            wall_seconds=self._clock.monotonic() - started,
        )

    @property
    def _graph_db(self) -> Path:
        return graph_checkpoint_path(self._settings)

    def _storage_state_path(self, run_id: str) -> Path | None:
        path = self._settings.paths.reports_dir / run_id / "state" / "storage_state.json"
        return path if path.is_file() else None

    def _generate_reports(
        self, state: GraphState, memory: MemoryService, store: FileArtifactStore
    ) -> None:
        """Render and persist the human and machine reports for a finished run."""
        if state.run_result is None or state.qa_report is None:
            return
        inputs = ReportInputs(
            run_result=state.run_result,
            page_graph=memory.graph,
            qa_report=state.qa_report,
            snapshots=state.visited_snapshots,
            action_history=state.agent.action_history,
        )
        ReportingEngine(store).generate(inputs)

    def list_runs(self) -> list[dict[str, object]]:
        """Run-registry rows (newest first) for the CLI and API."""
        return self._store.list_runs()

    def close(self) -> None:
        """Release the checkpoint store."""
        self._store.close()


def graph_checkpoint_path(settings: Settings) -> Path:
    """Path to the LangGraph checkpoint database (distinct from the run-registry DB)."""
    return settings.paths.checkpoint_db.parent / "graph_checkpoints.sqlite3"


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
