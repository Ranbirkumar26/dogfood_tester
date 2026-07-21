"""Reviewer pipeline: failure guards, loop detection, mechanical vs LLM verdicts."""

from __future__ import annotations

from datetime import UTC, datetime

from website_agent.browser.models import ConsoleEvent, NetworkEvent, ObservationBundle
from website_agent.core.types import RiskClass
from website_agent.executor.models import ExecutionResult
from website_agent.planner.models import ActionType, Expectation, ExpectationKind, PlanStep
from website_agent.prompts.manager import PromptManager
from website_agent.reviewer.models import ReviewDecision, ReviewerJudgement
from website_agent.reviewer.reviewer import Reviewer

NOW = datetime(2026, 7, 20, tzinfo=UTC)


class ScriptedModel:
    """Stand-in ModelManager.complete returning a fixed ReviewerJudgement."""

    def __init__(self, judgement: ReviewerJudgement | None = None) -> None:
        self._judgement = judgement
        self.calls = 0

    async def complete(self, role: str, prompt: object, schema: type) -> object:
        self.calls += 1
        if self._judgement is None:
            raise AssertionError("LLM should not have been called on this path")
        return self._judgement


def _reviewer(model: object) -> Reviewer:
    return Reviewer(model, PromptManager())  # type: ignore[arg-type]


def _step(kind: ExpectationKind, detail: str = "") -> PlanStep:
    return PlanStep(
        step_id="step_0001",
        action=ActionType.CLICK,
        element_id="e1",
        element_signature="sig",
        label="click",
        risk=RiskClass.SAFE,
        expectation=Expectation(kind=kind, detail=detail),
    )


def _result(
    *,
    ok: bool = True,
    failure_kind: str | None = None,
    url_before: str = "https://ex.com/a",
    url_after: str = "https://ex.com/a",
    console: list[ConsoleEvent] | None = None,
    network: list[NetworkEvent] | None = None,
) -> ExecutionResult:
    return ExecutionResult(
        step_id="step_0001",
        action="click",
        element_id="e1",
        ok=ok,
        failure_kind=failure_kind,
        url_before=url_before,
        url_after=url_after,
        navigated=url_before != url_after,
        observations=ObservationBundle(
            step_id="step_0001", console=console or [], network=network or []
        ),
        at=NOW,
    )


# --------------------------------------------------------------- failure guards


async def test_element_unavailable_maps_to_replan_without_llm() -> None:
    model = ScriptedModel()  # will raise if called
    verdict = await _reviewer(model).review(
        _step(ExpectationKind.CONTENT_CHANGE),
        _result(ok=False, failure_kind="element_unavailable"),
    )
    assert verdict.decision is ReviewDecision.REPLAN
    assert not verdict.expectation_met
    assert model.calls == 0


async def test_browser_transient_maps_to_retry() -> None:
    verdict = await _reviewer(ScriptedModel()).review(
        _step(ExpectationKind.CONTENT_CHANGE), _result(ok=False, failure_kind="browser")
    )
    assert verdict.decision is ReviewDecision.RETRY


async def test_browser_fatal_maps_to_stop() -> None:
    verdict = await _reviewer(ScriptedModel()).review(
        _step(ExpectationKind.CONTENT_CHANGE), _result(ok=False, failure_kind="browser_fatal")
    )
    assert verdict.decision is ReviewDecision.STOP


async def test_policy_failure_maps_to_replan() -> None:
    verdict = await _reviewer(ScriptedModel()).review(
        _step(ExpectationKind.CONTENT_CHANGE), _result(ok=False, failure_kind="policy")
    )
    assert verdict.decision is ReviewDecision.REPLAN


async def test_unknown_failure_defaults_to_retry() -> None:
    verdict = await _reviewer(ScriptedModel()).review(
        _step(ExpectationKind.CONTENT_CHANGE), _result(ok=False, failure_kind="mystery")
    )
    assert verdict.decision is ReviewDecision.RETRY


# ------------------------------------------------------------- loop detection


async def test_loop_below_limit_replans() -> None:
    verdict = await _reviewer(ScriptedModel()).review(
        _step(ExpectationKind.CONTENT_CHANGE),
        _result(),
        loop_repeats=5,
        loop_limit=5,
    )
    assert verdict.decision is ReviewDecision.REPLAN
    assert verdict.is_loop


async def test_loop_on_poisoned_branch_stops() -> None:
    verdict = await _reviewer(ScriptedModel()).review(
        _step(ExpectationKind.CONTENT_CHANGE),
        _result(),
        loop_repeats=5,
        loop_limit=5,
        branch_poisoned=True,
    )
    assert verdict.decision is ReviewDecision.STOP
    assert verdict.is_loop


# ------------------------------------------------------- mechanical verdicts


async def test_mechanical_url_change_met_is_success_without_llm() -> None:
    model = ScriptedModel()
    verdict = await _reviewer(model).review(
        _step(ExpectationKind.URL_CHANGE), _result(url_after="https://ex.com/b")
    )
    assert verdict.decision is ReviewDecision.SUCCESS
    assert verdict.expectation_met
    assert model.calls == 0


async def test_mechanical_url_change_unmet_is_replan() -> None:
    verdict = await _reviewer(ScriptedModel()).review(
        _step(ExpectationKind.URL_CHANGE),
        _result(),  # no change
    )
    assert verdict.decision is ReviewDecision.REPLAN
    assert not verdict.expectation_met


# --------------------------------------------------------------- llm verdicts


async def test_semantic_expectation_uses_llm() -> None:
    model = ScriptedModel(
        ReviewerJudgement(
            expectation_met=True,
            decision=ReviewDecision.SUCCESS,
            reasoning="validation error is visible",
        )
    )
    verdict = await _reviewer(model).review(
        _step(ExpectationKind.VALIDATION_ERROR, "email field shows an error"), _result()
    )
    assert model.calls == 1
    assert verdict.decision is ReviewDecision.SUCCESS
    assert "validation error is visible" in verdict.reasons


async def test_unmet_validation_expectation_becomes_qa_candidate() -> None:
    model = ScriptedModel(
        ReviewerJudgement(
            expectation_met=False,
            decision=ReviewDecision.REPLAN,
            reasoning="invalid input was accepted",
        )
    )
    verdict = await _reviewer(model).review(
        _step(ExpectationKind.VALIDATION_ERROR, "email field shows an error"), _result()
    )
    assert any(c.kind == "missing_validation" for c in verdict.qa_candidates)


async def test_semantic_judgement_renders_observations_into_prompt() -> None:
    # Populated console and network observations exercise the prompt render helpers.
    model = ScriptedModel(
        ReviewerJudgement(expectation_met=False, decision=ReviewDecision.REPLAN, reasoning="errors")
    )
    result = _result(
        console=[ConsoleEvent(level="error", text="TypeError x", at=NOW)],
        network=[NetworkEvent(method="GET", url="/api", status=500, ok=False, at=NOW)],
    )
    verdict = await _reviewer(model).review(_step(ExpectationKind.CONTENT_CHANGE), result)
    assert model.calls == 1
    assert verdict.decision is ReviewDecision.REPLAN
    # The deterministic extractor also flagged the console error and 500 independently.
    kinds = {c.kind for c in verdict.qa_candidates}
    assert {"console_error", "http_error"} <= kinds


async def test_llm_hallucination_flag_propagates() -> None:
    model = ScriptedModel(
        ReviewerJudgement(
            expectation_met=False,
            decision=ReviewDecision.REPLAN,
            hallucination_suspected=True,
            reasoning="expected navigation but nothing changed",
        )
    )
    verdict = await _reviewer(model).review(_step(ExpectationKind.CONTENT_CHANGE), _result())
    assert verdict.hallucination_suspected


# ------------------------------------------------------ qa candidates always


async def test_qa_candidates_extracted_regardless_of_verdict_path() -> None:
    # A failure guard settles the verdict, but console errors are still captured.
    result = _result(
        ok=False,
        failure_kind="browser",
        console=[ConsoleEvent(level="error", text="boom", at=NOW)],
    )
    verdict = await _reviewer(ScriptedModel()).review(_step(ExpectationKind.CONTENT_CHANGE), result)
    assert verdict.decision is ReviewDecision.RETRY
    assert any(c.kind == "console_error" for c in verdict.qa_candidates)
