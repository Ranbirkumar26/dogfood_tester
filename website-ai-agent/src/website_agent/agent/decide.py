"""The decide router: pure function from verdict and budgets to the next edge.

Design rationale (design D11, docs/architecture/state-machine.md): routing is safety-critical
because it enforces budgets and stop conditions, so it is pure Python, LLM-free, and
exhaustively unit-tested. Conditions are evaluated in strict priority order; the first match
wins. An LLM router could be talked out of stopping; this one cannot. Budgets are checked
before the verdict, so an exhausted budget always finalizes regardless of what the reviewer
wanted (design D10).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from website_agent.core.types import StopReason
from website_agent.reviewer.models import ReviewDecision
from website_agent.state.models import Budgets, Counters


class Edge(enum.StrEnum):
    """Where the router sends control next."""

    EXECUTOR = "executor"
    PLANNER = "planner"
    FINALIZE = "finalize"


@dataclass(frozen=True)
class DecideInputs:
    """Everything the router reads. Assembled by the decide node from graph state."""

    decision: ReviewDecision
    counters: Counters
    budgets: Budgets
    elapsed_seconds: float
    plan_has_next: bool
    step_attempt: int
    max_attempts: int
    is_loop: bool
    branch_poisoned: bool
    interrupted: bool = False


@dataclass(frozen=True)
class DecideOutcome:
    """The router's decision: the next edge and, when stopping, why."""

    edge: Edge
    stop_reason: StopReason | None


def _budget_stop(inputs: DecideInputs) -> StopReason | None:
    """The first exhausted budget, or None. Order is stable for reproducible reasons."""
    counters, budgets = inputs.counters, inputs.budgets
    if counters.steps >= budgets.max_steps:
        return StopReason.BUDGET_STEPS
    if counters.tokens >= budgets.max_tokens:
        return StopReason.BUDGET_TOKENS
    if counters.usd >= budgets.max_usd:
        return StopReason.BUDGET_USD
    if inputs.elapsed_seconds >= budgets.max_wall_seconds:
        return StopReason.BUDGET_WALL_CLOCK
    if counters.consecutive_failures >= budgets.max_consecutive_failures:
        return StopReason.BUDGET_FAILURES
    return None


def decide(inputs: DecideInputs) -> DecideOutcome:
    """Map the current situation onto exactly one next edge (first match wins).

    Priority (docs/architecture/state-machine.md, edge conditions):
      1. user interrupt      -> finalize (user_stop)
      2. budget exhausted    -> finalize (budget_*)
      3. verdict STOP        -> finalize (loop_limit if a loop, else goal_met)
      4. loop poisoned       -> finalize (loop_limit)
      5. RETRY, attempts left -> executor (same step)
      6. RETRY, exhausted    -> planner (step failed, replan)
      7. REPLAN              -> planner
      8. SUCCESS, queue left -> executor (next step)
      9. SUCCESS, queue empty -> planner (refresh from frontier)
    """
    if inputs.interrupted:
        return DecideOutcome(Edge.FINALIZE, StopReason.USER_STOP)

    if (budget := _budget_stop(inputs)) is not None:
        return DecideOutcome(Edge.FINALIZE, budget)

    if inputs.decision is ReviewDecision.STOP:
        reason = StopReason.LOOP_LIMIT if inputs.is_loop else StopReason.GOAL_MET
        return DecideOutcome(Edge.FINALIZE, reason)

    # A loop on an already-poisoned branch has no escape: stop rather than spin.
    if inputs.is_loop and inputs.branch_poisoned:
        return DecideOutcome(Edge.FINALIZE, StopReason.LOOP_LIMIT)

    if inputs.decision is ReviewDecision.RETRY:
        if inputs.step_attempt < inputs.max_attempts:
            return DecideOutcome(Edge.EXECUTOR, None)
        return DecideOutcome(Edge.PLANNER, None)

    if inputs.decision is ReviewDecision.REPLAN:
        return DecideOutcome(Edge.PLANNER, None)

    # SUCCESS: continue the queue if any step remains, else replan from the frontier.
    if inputs.plan_has_next:
        return DecideOutcome(Edge.EXECUTOR, None)
    return DecideOutcome(Edge.PLANNER, None)
