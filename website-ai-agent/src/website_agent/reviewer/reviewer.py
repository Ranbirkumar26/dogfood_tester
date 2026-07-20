"""Reviewer: compare a step's expectation against observed reality, decide what next.

Design rationale (design D2, docs/architecture/state-machine.md): the reviewer is the truth
authority. It never trusts the executor's success claim; it reasons from observations only.
The decision pipeline is layered so the expensive LLM call is avoided whenever a
deterministic guard already settles the outcome:

  1. execution failed          -> map failure class to RETRY / REPLAN / STOP
  2. loop detected             -> REPLAN (or STOP once the branch is poisoned)
  3. expectation is mechanical -> decide from observations, no LLM
  4. otherwise                 -> one LLM judgement of expectation-vs-observed

QA candidates are extracted deterministically in every branch, so the bug signal is
independent of the verdict path.
"""

from __future__ import annotations

from website_agent.executor.models import ExecutionResult
from website_agent.llm.manager import ModelManager
from website_agent.logging import get_logger
from website_agent.planner.models import PlanStep
from website_agent.prompts.manager import PromptManager
from website_agent.reviewer.checks import check_mechanical, extract_qa_candidates, is_mechanical
from website_agent.reviewer.models import (
    QaCandidate,
    ReviewDecision,
    ReviewerJudgement,
    ReviewVerdict,
)

log = get_logger("reviewer")

# Failure class (from the executor) mapped to the router decision it warrants.
_FAILURE_DECISION = {
    "element_unavailable": ReviewDecision.REPLAN,  # page changed; a fresh plan is needed
    "browser": ReviewDecision.RETRY,  # transient; retry the same step
    "browser_fatal": ReviewDecision.STOP,  # unrecoverable
    "policy": ReviewDecision.REPLAN,  # action forbidden; plan a different one
}


class Reviewer:
    """Judges one executed step and issues a router decision plus QA candidates."""

    def __init__(self, model: ModelManager, prompts: PromptManager) -> None:
        self._model = model
        self._prompts = prompts

    async def review(
        self,
        step: PlanStep,
        result: ExecutionResult,
        *,
        loop_repeats: int = 0,
        loop_limit: int = 5,
        branch_poisoned: bool = False,
    ) -> ReviewVerdict:
        """Produce a verdict for ``result`` against ``step``'s expectation.

        Args:
            loop_repeats: how many times the resulting state signature has recurred.
            loop_limit: repeats at which a loop escalates from REPLAN to STOP.
            branch_poisoned: set when this branch was already force-replanned once.
        """
        candidates = tuple(extract_qa_candidates(result))

        guard = self._guard_decision(
            result, loop_repeats=loop_repeats, loop_limit=loop_limit, poisoned=branch_poisoned
        )
        if guard is not None:
            decision, reasons, is_loop = guard
            return self._verdict(
                step,
                decision,
                expectation_met=False,
                reasons=reasons,
                candidates=candidates,
                is_loop=is_loop,
            )

        if is_mechanical(step.expectation.kind):
            met = check_mechanical(step, result)
            decision = ReviewDecision.SUCCESS if met else ReviewDecision.REPLAN
            reason = (
                f"mechanical expectation {step.expectation.kind.value} {'met' if met else 'unmet'}"
            )
            return self._verdict(
                step, decision, expectation_met=met, reasons=(reason,), candidates=candidates
            )

        judgement = await self._judge(step, result)
        reasons = (judgement.reasoning,) if judgement.reasoning else ()
        return self._verdict(
            step,
            judgement.decision,
            expectation_met=judgement.expectation_met,
            reasons=reasons,
            candidates=candidates,
            hallucination=judgement.hallucination_suspected,
        )

    # ---------------------------------------------------------- deterministic

    def _guard_decision(
        self,
        result: ExecutionResult,
        *,
        loop_repeats: int,
        loop_limit: int,
        poisoned: bool,
    ) -> tuple[ReviewDecision, tuple[str, ...], bool] | None:
        """Return a settled decision when a guard applies, else None (defer to expectation)."""
        if not result.ok:
            decision = _FAILURE_DECISION.get(result.failure_kind or "", ReviewDecision.RETRY)
            return decision, (f"execution failed: {result.failure_kind}", result.detail), False

        if loop_repeats >= loop_limit:
            # Poisoned branch that still loops has no escape here: stop the run.
            decision = ReviewDecision.STOP if poisoned else ReviewDecision.REPLAN
            return decision, (f"loop detected ({loop_repeats} repeats)",), True

        return None

    # ----------------------------------------------------------------- llm

    async def _judge(self, step: PlanStep, result: ExecutionResult) -> ReviewerJudgement:
        """LLM judgement for a semantic expectation."""
        prompt = self._prompts.render(
            "reviewer",
            {
                "action": step.action.value,
                "expectation_kind": step.expectation.kind.value,
                "expectation_detail": step.expectation.detail or "(none)",
                "url_before": result.url_before,
                "url_after": result.url_after,
                "navigated": str(result.navigated),
                "console_errors": _render_console(result),
                "failed_requests": _render_network(result),
                "snapshot_title": (
                    result.snapshot_after.title if result.snapshot_after else "(no snapshot)"
                ),
            },
        )
        return await self._model.complete("reviewer", prompt, ReviewerJudgement)

    # -------------------------------------------------------------- helpers

    def _verdict(
        self,
        step: PlanStep,
        decision: ReviewDecision,
        *,
        expectation_met: bool,
        reasons: tuple[str, ...],
        candidates: tuple[QaCandidate, ...],
        is_loop: bool = False,
        hallucination: bool = False,
    ) -> ReviewVerdict:
        verdict = ReviewVerdict(
            step_id=step.step_id,
            decision=decision,
            expectation_met=expectation_met,
            reasons=tuple(r for r in reasons if r),
            qa_candidates=candidates,
            is_loop=is_loop,
            hallucination_suspected=hallucination,
        )
        log.info(
            "step_reviewed",
            step_id=step.step_id,
            decision=decision.value,
            expectation_met=expectation_met,
            qa_candidates=len(candidates),
            is_loop=is_loop,
        )
        return verdict


def _render_console(result: ExecutionResult) -> str:
    errors = result.observations.console_errors
    if not errors:
        return "(none)"
    return "\n".join(f"- {e.text[:200]}" for e in errors[:10])


def _render_network(result: ExecutionResult) -> str:
    failures = result.observations.failed_requests
    if not failures:
        return "(none)"
    return "\n".join(
        f"- {e.method} {e.url} -> {e.status if e.status is not None else 'failed'}"
        for e in failures[:10]
    )
