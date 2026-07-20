"""Decide router: budget stops, verdict routing, retry/replan, priority ordering."""

from __future__ import annotations

import pytest

from website_agent.agent.decide import DecideInputs, Edge, decide
from website_agent.core.types import StopReason
from website_agent.reviewer.models import ReviewDecision
from website_agent.state.models import Budgets, Counters

BUDGETS = Budgets(
    max_steps=100,
    max_tokens=1_000_000,
    max_usd=1.0,
    max_wall_seconds=1800,
    max_consecutive_failures=5,
)


def _inputs(
    *,
    decision: ReviewDecision = ReviewDecision.SUCCESS,
    counters: Counters | None = None,
    elapsed: float = 0.0,
    plan_has_next: bool = True,
    step_attempt: int = 1,
    max_attempts: int = 2,
    is_loop: bool = False,
    branch_poisoned: bool = False,
    interrupted: bool = False,
) -> DecideInputs:
    return DecideInputs(
        decision=decision,
        counters=counters or Counters(),
        budgets=BUDGETS,
        elapsed_seconds=elapsed,
        plan_has_next=plan_has_next,
        step_attempt=step_attempt,
        max_attempts=max_attempts,
        is_loop=is_loop,
        branch_poisoned=branch_poisoned,
        interrupted=interrupted,
    )


def test_interrupt_finalizes_first() -> None:
    # Even with a fresh SUCCESS and budget to spare, an interrupt wins.
    out = decide(_inputs(interrupted=True))
    assert out.edge is Edge.FINALIZE
    assert out.stop_reason is StopReason.USER_STOP


@pytest.mark.parametrize(
    ("counters", "elapsed", "reason"),
    [
        (Counters(steps=100), 0.0, StopReason.BUDGET_STEPS),
        (Counters(tokens=1_000_000), 0.0, StopReason.BUDGET_TOKENS),
        (Counters(usd=1.0), 0.0, StopReason.BUDGET_USD),
        (Counters(), 1800.0, StopReason.BUDGET_WALL_CLOCK),
        (Counters(consecutive_failures=5), 0.0, StopReason.BUDGET_FAILURES),
    ],
)
def test_budget_exhaustion_finalizes(
    counters: Counters, elapsed: float, reason: StopReason
) -> None:
    out = decide(_inputs(decision=ReviewDecision.SUCCESS, counters=counters, elapsed=elapsed))
    assert out.edge is Edge.FINALIZE
    assert out.stop_reason is reason


def test_budget_beats_verdict() -> None:
    # Budget exhausted plus a RETRY verdict: budget wins (design D10).
    out = decide(_inputs(decision=ReviewDecision.RETRY, counters=Counters(steps=100)))
    assert out.edge is Edge.FINALIZE
    assert out.stop_reason is StopReason.BUDGET_STEPS


def test_stop_verdict_without_loop_is_goal_met() -> None:
    out = decide(_inputs(decision=ReviewDecision.STOP))
    assert out.edge is Edge.FINALIZE
    assert out.stop_reason is StopReason.GOAL_MET


def test_stop_verdict_with_loop_is_loop_limit() -> None:
    out = decide(_inputs(decision=ReviewDecision.STOP, is_loop=True))
    assert out.stop_reason is StopReason.LOOP_LIMIT


def test_loop_on_poisoned_branch_finalizes() -> None:
    out = decide(_inputs(decision=ReviewDecision.REPLAN, is_loop=True, branch_poisoned=True))
    assert out.edge is Edge.FINALIZE
    assert out.stop_reason is StopReason.LOOP_LIMIT


def test_retry_with_attempts_left_repeats_step() -> None:
    out = decide(_inputs(decision=ReviewDecision.RETRY, step_attempt=1, max_attempts=2))
    assert out.edge is Edge.EXECUTOR
    assert out.stop_reason is None


def test_retry_exhausted_replans() -> None:
    out = decide(_inputs(decision=ReviewDecision.RETRY, step_attempt=2, max_attempts=2))
    assert out.edge is Edge.PLANNER


def test_replan_goes_to_planner() -> None:
    assert decide(_inputs(decision=ReviewDecision.REPLAN)).edge is Edge.PLANNER


def test_success_with_queue_continues_to_executor() -> None:
    out = decide(_inputs(decision=ReviewDecision.SUCCESS, plan_has_next=True))
    assert out.edge is Edge.EXECUTOR
    assert out.stop_reason is None


def test_success_with_empty_queue_replans() -> None:
    out = decide(_inputs(decision=ReviewDecision.SUCCESS, plan_has_next=False))
    assert out.edge is Edge.PLANNER


def test_loop_without_poison_does_not_stop_on_success() -> None:
    # A loop that is not yet poisoned and not a STOP verdict keeps going (planner will
    # get the replan via the reviewer's decision in practice); here SUCCESS+queue continues.
    out = decide(_inputs(decision=ReviewDecision.SUCCESS, is_loop=True, branch_poisoned=False))
    assert out.edge is Edge.EXECUTOR
