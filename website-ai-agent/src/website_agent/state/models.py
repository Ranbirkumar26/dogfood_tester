"""Run state models: the serializable heart of every run.

Design rationale: AgentState is the single object the checkpointer persists on every node
transition (docs/architecture/state-machine.md). It holds small structured data and
ArtifactRef pointers only, never binaries (design D8), so serialization stays fast and
checkpoints stay small. Budgets and counters are first-class (design D10): the decide
router reads them to stop a run by construction rather than by hope. Everything here is a
frozen Pydantic model except AgentState itself, which the graph nodes replace wholesale
(functional update), so state transitions are explicit and auditable.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from website_agent.core.types import ArtifactRef, GoalMode, RiskClass, StopReason


class GoalSpec(BaseModel):
    """What the run is trying to do."""

    model_config = ConfigDict(frozen=True)

    mode: GoalMode
    start_url: str
    description: str = ""
    max_depth: int = Field(default=8, ge=1)  # graph distance cap from the start page


class RunPolicy(BaseModel):
    """Safety fences for a run (design D12)."""

    model_config = ConfigDict(frozen=True)

    allowed_domains: frozenset[str] = frozenset()
    allow_mutating: bool = True
    allow_destructive: bool = False
    require_approval_for_destructive: bool = True

    def permits(self, risk: RiskClass) -> bool:
        """Whether an action of this risk class may run under this policy."""
        if risk is RiskClass.SAFE:
            return True
        if risk is RiskClass.MUTATING:
            return self.allow_mutating
        return self.allow_destructive


class Budgets(BaseModel):
    """Hard stops for a run (design D10). Zero USD is valid (free local models)."""

    model_config = ConfigDict(frozen=True)

    max_steps: int = Field(ge=1)
    max_tokens: int = Field(ge=1)
    max_usd: float = Field(ge=0.0)
    max_wall_seconds: int = Field(ge=1)
    max_consecutive_failures: int = Field(ge=1)


class Counters(BaseModel):
    """Live tallies compared against budgets by the decide router."""

    model_config = ConfigDict(frozen=True)

    steps: int = 0
    tokens: int = 0
    usd: float = 0.0
    consecutive_failures: int = 0
    started_at: datetime | None = None

    def elapsed_seconds(self, now: datetime) -> float:
        """Wall-clock seconds since the run started; 0 before bootstrap."""
        if self.started_at is None:
            return 0.0
        return (now - self.started_at).total_seconds()


class ActionRecord(BaseModel):
    """One executed action, appended to history; the audit trail and memory input."""

    model_config = ConfigDict(frozen=True)

    step_id: str
    action: str
    element_id: str | None
    element_signature: str | None
    url_before: str
    url_after: str
    success: bool
    detail: str = ""
    screenshot: ArtifactRef | None = None
    at: datetime


class LoopSignal(BaseModel):
    """Loop-detector state: recent state signatures and their repeat counts."""

    model_config = ConfigDict(frozen=True)

    recent: tuple[str, ...] = ()
    repeats: int = 0
    poisoned: frozenset[str] = frozenset()


class RunResult(BaseModel):
    """Terminal summary of a finished run; what reports and the API surface."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    stop_reason: StopReason
    steps: int
    pages_visited: int
    findings: int
    tokens: int
    cost_usd: float
    started_at: datetime | None
    finished_at: datetime
