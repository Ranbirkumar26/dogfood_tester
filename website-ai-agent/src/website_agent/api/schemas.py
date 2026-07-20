"""API request and response schemas.

Design rationale: the wire contract is explicit and separate from the internal state models,
so the HTTP surface can evolve without leaking domain types. Requests carry only what a
caller should set; budgets are optional and fall back to server defaults (design D10).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from website_agent.core.types import GoalMode


class StartRunRequest(BaseModel):
    """Body for starting an exploration run."""

    model_config = ConfigDict(frozen=True)

    url: str
    mode: GoalMode = GoalMode.EXPLORE
    same_domain: bool = True
    max_steps: int | None = Field(default=None, ge=1)
    max_usd: float | None = Field(default=None, ge=0.0)


class RunAccepted(BaseModel):
    """Response when a run is accepted for background execution."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    status: str


class RunStatus(BaseModel):
    """A run's current status from the registry."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    status: str  # running | finished | failed
    stop_reason: str | None = None
    steps: int = 0
    cost_usd: float = 0.0
    updated_at: str | None = None


class RunList(BaseModel):
    """A list of runs."""

    model_config = ConfigDict(frozen=True)

    runs: list[RunStatus]
