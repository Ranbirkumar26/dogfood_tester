"""Graph nodes: the async step functions LangGraph invokes.

Design rationale: node logic is kept here as methods on GraphNodes (which holds the injected
dependencies) rather than inline in the graph assembly, so each node is independently
testable and the graph file stays a thin wiring layer. Nodes read GraphState and return a
dict of updates (LangGraph's contract). The deterministic decide node is the only place
budgets and stop conditions are enforced (design D10, D11); it syncs the token/cost counters
from the ledger before deciding, so a mid-loop budget breach stops the run at the next
decision point.
"""

from __future__ import annotations

from dataclasses import dataclass

from website_agent.agent.decide import DecideInputs, Edge, decide
from website_agent.agent.graph_state import GraphState
from website_agent.agent.loop_detector import (
    is_poisoned,
    observe_signature,
    poison_branch,
    state_signature,
)
from website_agent.browser.models import PageSnapshot
from website_agent.browser.session import BrowserSession
from website_agent.core.artifacts import ArtifactStore
from website_agent.core.clock import Clock
from website_agent.core.types import StopReason
from website_agent.executor.executor import Executor
from website_agent.executor.models import ExecutionResult
from website_agent.llm.ledger import TokenLedger
from website_agent.logging import get_logger
from website_agent.memory.registry import action_signature
from website_agent.memory.service import MemoryService
from website_agent.planner.models import PlanStep
from website_agent.planner.planner import Planner
from website_agent.planner.render import render_inventory
from website_agent.qa.engine import QaEngine
from website_agent.qa.models import QaContext
from website_agent.reviewer.models import ReviewDecision
from website_agent.reviewer.reviewer import Reviewer
from website_agent.state.models import ActionRecord, RunResult

log = get_logger("agent.nodes")


@dataclass
class GraphDeps:
    """Non-serializable handles the nodes need; injected, never checkpointed."""

    session: BrowserSession
    planner: Planner
    executor: Executor
    reviewer: Reviewer
    memory: MemoryService
    ledger: TokenLedger
    clock: Clock
    store: ArtifactStore
    qa_engine: QaEngine
    max_attempts: int = 2
    loop_limit: int = 5


class GraphNodes:
    """Bound node implementations over a set of dependencies."""

    def __init__(self, deps: GraphDeps) -> None:
        self._d = deps

    async def bootstrap(self, state: GraphState) -> dict[str, object]:
        """Navigate to the start URL, take the first snapshot, initialize the run."""
        agent = state.agent
        await self._d.session.goto(agent.goal.start_url)
        snapshot = await self._d.session.snapshot()
        self._d.memory.observe_page(snapshot)
        started = agent.counters.model_copy(update={"started_at": self._d.clock.now()})
        new_agent = agent.with_updates(
            current_snapshot=snapshot, counters=started, memory=self._d.memory.state
        )
        log.info("bootstrap_complete", url=snapshot.url, elements=len(snapshot.elements))
        return {
            "agent": new_agent,
            "plan": None,
            "current_step": None,
            "visited_snapshots": (snapshot,),
        }

    async def planner(self, state: GraphState) -> dict[str, object]:
        """Produce a fresh plan from the current snapshot and memory."""
        agent = state.agent
        snapshot = agent.current_snapshot
        assert snapshot is not None  # bootstrap guarantees a snapshot before planning
        feedback = ""
        if state.last_verdict is not None and state.last_verdict.reasons:
            feedback = "; ".join(state.last_verdict.reasons)
        plan = await self._d.planner.plan(
            goal=agent.goal,
            policy=agent.policy,
            memory=self._d.memory,
            snapshot=snapshot,
            snapshot_render=render_inventory(snapshot),
            feedback=feedback,
        )
        return {"plan": plan, "current_step": None, "step_attempt": 0}

    async def executor(self, state: GraphState) -> dict[str, object]:
        """Execute the current step (a retry) or pop and execute the next queued step."""
        retrying = (
            state.last_verdict is not None
            and state.last_verdict.decision is ReviewDecision.RETRY
            and state.current_step is not None
        )
        if retrying:
            step = state.current_step
            attempt = state.step_attempt + 1
            plan = state.plan
        else:
            assert state.plan is not None
            step = state.plan.next_step()
            plan = state.plan.without_first()
            attempt = 1
        assert step is not None

        result = await self._d.executor.execute(step, self._d.session, self._d.memory)
        agent = state.agent.append_action(_action_record(step, result, self._d.clock))
        visited = state.visited_snapshots
        if result.snapshot_after is not None:
            agent = agent.with_updates(current_snapshot=result.snapshot_after)
            visited = _accumulate_snapshot(visited, result.snapshot_after)
        agent = agent.with_updates(memory=self._d.memory.state)

        return {
            "agent": agent,
            "plan": plan,
            "current_step": step,
            "step_attempt": attempt,
            "last_result": result,
            "visited_snapshots": visited,
        }

    async def reviewer(self, state: GraphState) -> dict[str, object]:
        """Judge the last result, accumulate QA candidates, update the loop signal."""
        assert state.current_step is not None
        assert state.last_result is not None
        agent = state.agent

        signature = _current_signature(state)
        loop_signal, repeats = observe_signature(agent.loop, signature)
        poisoned = is_poisoned(loop_signal, signature)

        verdict = await self._d.reviewer.review(
            state.current_step,
            state.last_result,
            loop_repeats=repeats,
            loop_limit=self._d.loop_limit,
            branch_poisoned=poisoned,
        )
        agent = agent.with_updates(loop=loop_signal)
        qa_candidates = (*state.qa_candidates, *verdict.qa_candidates)
        return {
            "agent": agent,
            "last_verdict": verdict,
            "qa_candidates": qa_candidates,
            "branch_poisoned": poisoned,
        }

    def decide(self, state: GraphState) -> dict[str, object]:
        """Sync counters from the ledger, then route (design D10, D11)."""
        assert state.last_verdict is not None
        assert state.last_result is not None
        agent = state.agent
        totals = self._d.ledger.totals()

        failed = not state.last_result.ok
        consecutive = agent.counters.consecutive_failures + 1 if failed else 0
        counters = agent.counters.model_copy(
            update={
                "steps": agent.counters.steps + 1,
                "tokens": totals.total_tokens,
                "usd": totals.cost_usd,
                "consecutive_failures": consecutive,
            }
        )

        outcome = decide(
            DecideInputs(
                decision=state.last_verdict.decision,
                counters=counters,
                budgets=agent.budgets,
                elapsed_seconds=counters.elapsed_seconds(self._d.clock.now()),
                plan_has_next=state.plan is not None and not state.plan.is_empty,
                step_attempt=state.step_attempt,
                max_attempts=self._d.max_attempts,
                is_loop=state.last_verdict.is_loop,
                branch_poisoned=state.branch_poisoned,
            )
        )

        # Poison a looping branch the first time we replan it, so a second recurrence stops.
        loop = agent.loop
        if state.last_verdict.is_loop and outcome.edge is Edge.PLANNER:
            loop = poison_branch(loop, _current_signature(state))

        agent = agent.with_updates(counters=counters, loop=loop, stop_reason=outcome.stop_reason)
        return {"agent": agent, "next_edge": outcome.edge.value}

    async def finalize(self, state: GraphState) -> dict[str, object]:
        """Close the run: run QA, persist storage state and the QA report, build the RunResult."""
        agent = state.agent
        report = self._d.qa_engine.analyze(
            QaContext(
                run_id=agent.run_id,
                candidates=state.qa_candidates,
                snapshots=state.visited_snapshots,
            )
        )
        try:
            self._d.store.save_json("qa", "findings.json", report.model_dump(mode="json"))
        except Exception as exc:  # noqa: BLE001 - a report write must not fail the run
            log.warning("qa_report_write_failed", reason=str(exc))
        try:
            await self._d.session.save_storage_state()
        except Exception as exc:  # noqa: BLE001 - finalize must never fail the run
            log.warning("finalize_storage_state_failed", reason=str(exc))

        totals = self._d.ledger.totals()
        # Reached without a stop reason only when the plan ran dry: frontier exhausted.
        stop_reason = agent.stop_reason or StopReason.FRONTIER_EXHAUSTED
        result = RunResult(
            run_id=agent.run_id,
            stop_reason=stop_reason,
            steps=agent.counters.steps,
            pages_visited=self._d.memory.graph.page_count,
            findings=report.counts.total,
            tokens=totals.total_tokens,
            cost_usd=totals.cost_usd,
            started_at=agent.counters.started_at,
            finished_at=self._d.clock.now(),
        )
        log.info(
            "run_finalized",
            run_id=agent.run_id,
            stop_reason=stop_reason.value,
            steps=result.steps,
            pages=result.pages_visited,
            findings=result.findings,
            cost_usd=result.cost_usd,
        )
        return {
            "agent": agent.with_updates(stop_reason=stop_reason),
            "run_result": result,
            "qa_report": report,
        }


def route_after_decide(state: GraphState) -> str:
    """Conditional-edge function: read the edge the decide node chose."""
    return state.next_edge


def _current_signature(state: GraphState) -> str:
    result = state.last_result
    assert result is not None
    content_hash = result.snapshot_after.snapshot_hash if result.snapshot_after else ""
    last_action = action_signature(
        url=result.url_before,
        element_signature=state.current_step.element_signature if state.current_step else None,
        action=result.action,
    )
    return state_signature(
        url=result.url_after, content_hash=content_hash, last_action_signature=last_action
    )


def _accumulate_snapshot(
    visited: tuple[PageSnapshot, ...], snapshot: PageSnapshot
) -> tuple[PageSnapshot, ...]:
    """Append a snapshot only if its content-class is new (dedupe by hash for whole-run QA)."""
    if any(existing.snapshot_hash == snapshot.snapshot_hash for existing in visited):
        return visited
    return (*visited, snapshot)


def _action_record(step: PlanStep, result: ExecutionResult, clock: Clock) -> ActionRecord:
    return ActionRecord(
        step_id=result.step_id,
        action=result.action,
        element_id=result.element_id,
        element_signature=step.element_signature,
        url_before=result.url_before,
        url_after=result.url_after,
        success=result.ok,
        detail=result.detail,
        screenshot=result.screenshot,
        at=clock.now(),
    )
