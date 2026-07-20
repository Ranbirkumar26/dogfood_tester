"""Deterministic reviewer checks: QA-candidate extraction and mechanical expectation tests.

Design rationale: the bug signal must not depend on the LLM, so console errors, failed
network requests, and unexpected dialogs are turned into QA candidates here in pure Python
(docs/architecture/data-flow.md, section 3). Some expectations are mechanically decidable
(a URL change either happened or it did not); those are checked here so the reviewer only
spends an LLM call on genuinely semantic judgements (validation errors, content changes).
"""

from __future__ import annotations

from website_agent.core.types import Severity
from website_agent.executor.models import ExecutionResult
from website_agent.planner.models import ExpectationKind, PlanStep
from website_agent.reviewer.models import QaCandidate

# Expectations decidable without an LLM: kind -> function(step, result) -> met.
_MECHANICAL = {
    ExpectationKind.URL_CHANGE,
    ExpectationKind.DIALOG,
    ExpectationKind.DOWNLOAD,
    ExpectationKind.NO_CHANGE,
}


def is_mechanical(kind: ExpectationKind) -> bool:
    """Whether an expectation of this kind can be checked without the LLM."""
    return kind in _MECHANICAL


def check_mechanical(step: PlanStep, result: ExecutionResult) -> bool:
    """Evaluate a mechanically-decidable expectation against the observed result.

    Only call when ``is_mechanical(step.expectation.kind)`` is true.
    """
    kind = step.expectation.kind
    observations = result.observations
    if kind is ExpectationKind.URL_CHANGE:
        return result.url_changed
    if kind is ExpectationKind.DIALOG:
        return len(observations.dialogs) > 0
    if kind is ExpectationKind.DOWNLOAD:
        return len(observations.downloads) > 0
    # NO_CHANGE: nothing navigational or dialog-like happened.
    return not result.url_changed and not observations.dialogs


def extract_qa_candidates(result: ExecutionResult) -> list[QaCandidate]:
    """Deterministic defects from a step's observations and outcome."""
    candidates: list[QaCandidate] = []
    url = result.url_after

    for event in result.observations.console_errors:
        candidates.append(
            QaCandidate(
                kind="console_error",
                severity=Severity.MAJOR,
                detail=event.text[:300],
                url=url,
                step_id=result.step_id,
            )
        )

    for request in result.observations.failed_requests:
        # 5xx is more severe than 4xx: a server error is a real defect, a 404 may be a dead link.
        severity = Severity.CRITICAL if (request.status or 0) >= 500 else Severity.MAJOR
        status = request.status if request.status is not None else "failed"
        candidates.append(
            QaCandidate(
                kind="http_error",
                severity=severity,
                detail=f"{request.method} {request.url} -> {status}",
                url=url,
                step_id=result.step_id,
            )
        )

    # A click that changed nothing observable is a candidate dead action; the LLM verdict
    # decides the step outcome, but the dead-action signal is recorded regardless.
    if (
        result.ok
        and result.action == "click"
        and not result.url_changed
        and not result.observations.dialogs
        and not result.observations.downloads
    ):
        candidates.append(
            QaCandidate(
                kind="dead_action",
                severity=Severity.MINOR,
                detail=f"click on {result.element_id} produced no observable change",
                url=url,
                step_id=result.step_id,
            )
        )

    return candidates
