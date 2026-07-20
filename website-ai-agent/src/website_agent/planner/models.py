"""Planner data models: candidates, plan steps, expectations, LLM scoring schema.

Design rationale (docs/architecture/planner.md): candidates are generated deterministically
from the inventory (the LLM never proposes an element that is not there, design D6); the LLM
only scores, sequences, and supplies intent and expectations. Every PlanStep carries a
falsifiable Expectation because it is the reviewer's comparison anchor (design D2): a step
without one is invalid by schema.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field

from website_agent.core.types import RiskClass


class ActionType(enum.StrEnum):
    """Actions the planner may schedule; each maps to a tool the executor calls."""

    CLICK = "click"
    FILL = "fill"
    SELECT = "select"
    NAVIGATE = "navigate"
    SCROLL = "scroll"
    GO_BACK = "go_back"


class ExpectationKind(enum.StrEnum):
    """The observable class a step predicts, checked by the reviewer."""

    URL_CHANGE = "url_change"
    NEW_ELEMENTS = "new_elements"
    DIALOG = "dialog"
    VALIDATION_ERROR = "validation_error"
    CONTENT_CHANGE = "content_change"
    DOWNLOAD = "download"
    NO_CHANGE = "no_change"


class Expectation(BaseModel):
    """What should be observable if a step works (reviewer's anchor, design D2)."""

    model_config = ConfigDict(frozen=True)

    kind: ExpectationKind
    detail: str = ""


class InputSpec(BaseModel):
    """Synthetic input for a fill action; ``input_class`` feeds dedupe signatures."""

    model_config = ConfigDict(frozen=True)

    input_class: str  # e.g. valid_email, malformed_email, long_text, empty
    value: str


class ActionCandidate(BaseModel):
    """A deterministically generated afforded action, pre-LLM."""

    model_config = ConfigDict(frozen=True)

    action: ActionType
    element_id: str | None
    element_signature: str | None
    label: str  # human-readable, for prompts and logs (e.g. "click link 'Pricing'")
    risk: RiskClass
    target_url: str | None = None  # for navigate candidates


class ValueEstimate(BaseModel):
    """Component scores kept for eval and debugging (docs/architecture/planner.md s3)."""

    model_config = ConfigDict(frozen=True)

    goal_relevance: float = 0.0
    novelty: float = 0.0
    coverage_gain: float = 0.0
    depth_penalty: float = 0.0
    failure_penalty: float = 0.0


class PlanStep(BaseModel):
    """One scheduled action with intent, expectation, and final priority."""

    model_config = ConfigDict(frozen=True)

    step_id: str
    action: ActionType
    element_id: str | None
    element_signature: str | None
    label: str
    risk: RiskClass
    input_spec: InputSpec | None = None
    expectation: Expectation
    target_url: str | None = None
    priority: float = 0.0
    value: ValueEstimate = Field(default_factory=ValueEstimate)


class Plan(BaseModel):
    """The prioritized task queue produced by one planning pass."""

    model_config = ConfigDict(frozen=True)

    steps: tuple[PlanStep, ...]
    rationale: str = ""

    def next_step(self) -> PlanStep | None:
        """Highest-priority step (queue head), or None when the plan is empty."""
        return self.steps[0] if self.steps else None

    def without_first(self) -> Plan:
        """The plan with its head removed (executor consumed it)."""
        return self.model_copy(update={"steps": self.steps[1:]})

    @property
    def is_empty(self) -> bool:
        """Whether the queue is drained."""
        return not self.steps


# ---- LLM scoring schema: what the model returns, validated by the ModelManager ----


class ScoredCandidate(BaseModel):
    """The model's judgement for one candidate, keyed by its 1-based prompt index."""

    model_config = ConfigDict(frozen=True)

    index: int = Field(ge=1)
    goal_relevance: float = Field(ge=0.0, le=1.0)
    expectation_kind: ExpectationKind
    expectation_detail: str = ""
    input_class: str = ""
    input_value: str = ""


class PlannerScoring(BaseModel):
    """The structured output contract for the planner's LLM call."""

    model_config = ConfigDict(frozen=True)

    scored: tuple[ScoredCandidate, ...]
    rationale: str = ""
