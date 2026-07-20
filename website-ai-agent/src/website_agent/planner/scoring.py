"""Deterministic priority scoring and re-rank (docs/architecture/planner.md, section 3).

Design rationale: value estimation is a hybrid. The LLM judges goal relevance (semantic);
code judges novelty, coverage gain, and depth (structural). Neither alone suffices: pure-LLM
ranking loops on attractive-looking dead ends, pure-structural ranking wastes budget on
irrelevant breadth. Weights are per goal mode and are eval-harness tunables (Phase 12). The
final priority is computed here in pure Python so ordering is reproducible and unit-testable
given fixed LLM scores.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from website_agent.core.types import GoalMode
from website_agent.planner.models import ActionType, ValueEstimate

# Structural coverage weight by action: links open pages, inputs less so, scroll least.
_COVERAGE_BY_ACTION: dict[ActionType, float] = {
    ActionType.NAVIGATE: 1.0,
    ActionType.CLICK: 0.8,
    ActionType.SELECT: 0.4,
    ActionType.FILL: 0.3,
    ActionType.GO_BACK: 0.1,
    ActionType.SCROLL: 0.05,
}


class ScoringWeights(BaseModel):
    """Priority formula weights. Defaults tuned per goal mode by :func:`weights_for`."""

    model_config = ConfigDict(frozen=True)

    relevance: float = 1.0
    novelty: float = 1.0
    coverage: float = 1.0
    depth: float = 0.5
    failure: float = 1.0


def weights_for(mode: GoalMode) -> ScoringWeights:
    """Goal-mode-specific weights.

    explore favors novelty and coverage; test favors goal relevance (form and edge-case
    candidates score high via the LLM); document favors breadth-first coverage.
    """
    if mode is GoalMode.EXPLORE:
        return ScoringWeights(relevance=0.8, novelty=1.2, coverage=1.1, depth=0.6, failure=1.0)
    if mode is GoalMode.TEST:
        return ScoringWeights(relevance=1.3, novelty=0.8, coverage=0.7, depth=0.3, failure=1.2)
    return ScoringWeights(relevance=0.7, novelty=1.0, coverage=1.3, depth=0.8, failure=1.0)


def compute_priority(value: ValueEstimate, weights: ScoringWeights) -> float:
    """Weighted priority from component value scores (higher is better)."""
    return (
        weights.relevance * value.goal_relevance
        + weights.novelty * value.novelty
        + weights.coverage * value.coverage_gain
        - weights.depth * value.depth_penalty
        - weights.failure * value.failure_penalty
    )


def coverage_gain(action: ActionType) -> float:
    """Structural estimate of how much new surface an action tends to unlock."""
    return _COVERAGE_BY_ACTION.get(action, 0.2)
