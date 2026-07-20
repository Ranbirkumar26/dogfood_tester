"""GraphState: the orchestration-layer state the LangGraph graph carries.

Design rationale: this is Layer 4, so unlike the Layer 2 AgentState it may hold the Layer 3
role outputs (Plan, ExecutionResult, ReviewVerdict) that AgentState cannot import without
inverting the layer dependencies. It embeds the serializable AgentState (the durable run
state, design D8) and adds the transient per-loop fields the nodes pass between each other.
Non-serializable handles (the browser session, the live memory service, role objects) live
in GraphDeps, injected into the nodes, never in state, so checkpoints stay clean and resume
can rebuild them.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from website_agent.browser.models import PageSnapshot
from website_agent.executor.models import ExecutionResult
from website_agent.planner.models import Plan, PlanStep
from website_agent.qa.models import QaReport
from website_agent.reviewer.models import QaCandidate, ReviewVerdict
from website_agent.state.agent_state import AgentState
from website_agent.state.models import RunResult


class GraphState(BaseModel):
    """State flowing through the plan-execute-review graph.

    Not frozen: LangGraph replaces fields from node return dicts. The embedded AgentState
    is itself frozen and replaced wholesale, so durable state transitions stay explicit.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    agent: AgentState
    plan: Plan | None = None
    current_step: PlanStep | None = None
    step_attempt: int = 0
    last_result: ExecutionResult | None = None
    last_verdict: ReviewVerdict | None = None
    qa_candidates: tuple[QaCandidate, ...] = ()
    visited_snapshots: tuple[PageSnapshot, ...] = ()  # distinct pages, for whole-run QA
    next_edge: str = ""
    branch_poisoned: bool = False
    run_result: RunResult | None = None
    qa_report: QaReport | None = None
