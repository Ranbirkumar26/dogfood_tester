"""Scoring weights and priority computation."""

from __future__ import annotations

from website_agent.core.types import GoalMode
from website_agent.planner.models import ActionType, ValueEstimate
from website_agent.planner.scoring import compute_priority, coverage_gain, weights_for


def test_weights_differ_by_goal_mode() -> None:
    explore = weights_for(GoalMode.EXPLORE)
    test = weights_for(GoalMode.TEST)
    document = weights_for(GoalMode.DOCUMENT)
    assert explore.novelty > test.novelty  # explore favors novelty
    assert test.relevance > explore.relevance  # test favors relevance
    assert document.coverage > explore.coverage  # document favors coverage


def test_priority_rewards_relevance_and_novelty_penalizes_failure() -> None:
    weights = weights_for(GoalMode.EXPLORE)
    strong = ValueEstimate(goal_relevance=1.0, novelty=1.0, coverage_gain=1.0)
    weak = ValueEstimate(goal_relevance=0.1, novelty=0.0, coverage_gain=0.1)
    failed = ValueEstimate(goal_relevance=1.0, novelty=1.0, coverage_gain=1.0, failure_penalty=1.0)
    assert compute_priority(strong, weights) > compute_priority(weak, weights)
    assert compute_priority(failed, weights) < compute_priority(strong, weights)


def test_depth_penalty_lowers_priority() -> None:
    weights = weights_for(GoalMode.EXPLORE)
    shallow = ValueEstimate(goal_relevance=0.5, depth_penalty=0.0)
    deep = ValueEstimate(goal_relevance=0.5, depth_penalty=1.0)
    assert compute_priority(deep, weights) < compute_priority(shallow, weights)


def test_coverage_gain_orders_by_action_type() -> None:
    assert coverage_gain(ActionType.NAVIGATE) > coverage_gain(ActionType.CLICK)
    assert coverage_gain(ActionType.CLICK) > coverage_gain(ActionType.FILL)
    assert coverage_gain(ActionType.FILL) > coverage_gain(ActionType.SCROLL)
