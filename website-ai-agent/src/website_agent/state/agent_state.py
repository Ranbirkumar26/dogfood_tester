"""AgentState: the whole run in one serializable object.

Design rationale: LangGraph nodes receive this and return an updated copy; the checkpointer
persists it on every transition (docs/architecture/state-machine.md). It carries small
structured data and ArtifactRef pointers only (design D8). Kept deliberately free of
LangGraph imports so it serializes and unit-tests without the orchestration framework
(Phase 9 wires it into a StateGraph). The current PageSnapshot is stored so resume can
verify drift against a freshly extracted snapshot.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from website_agent.browser.models import PageSnapshot
from website_agent.core.types import StopReason
from website_agent.memory.registry import MemoryState
from website_agent.state.models import (
    ActionRecord,
    Budgets,
    Counters,
    GoalSpec,
    LoopSignal,
    RunPolicy,
)

STATE_SCHEMA_VERSION = 1


class AgentState(BaseModel):
    """Complete, serializable run state. Nodes replace it wholesale (functional update)."""

    model_config = ConfigDict(frozen=True)

    schema_version: int = STATE_SCHEMA_VERSION
    run_id: str
    goal: GoalSpec
    policy: RunPolicy
    budgets: Budgets
    counters: Counters = Field(default_factory=Counters)

    current_snapshot: PageSnapshot | None = None
    memory: MemoryState = Field(default_factory=MemoryState)
    action_history: tuple[ActionRecord, ...] = ()
    loop: LoopSignal = Field(default_factory=LoopSignal)

    stop_reason: StopReason | None = None
    forced_replan: bool = False

    def with_updates(self, **changes: object) -> AgentState:
        """Typed functional update; the one way nodes evolve state."""
        return self.model_copy(update=changes)

    def append_action(self, record: ActionRecord) -> AgentState:
        """Return state with an action appended to the immutable history tuple."""
        return self.model_copy(update={"action_history": (*self.action_history, record)})
