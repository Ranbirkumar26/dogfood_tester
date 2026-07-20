"""Reviewer output models: verdict, QA candidates, LLM judgement schema.

Design rationale (design D2): the reviewer only trusts observations, never the executor's
claim of success, so a failed click cannot silently become "success". The verdict drives
the deterministic router (docs/architecture/state-machine.md): SUCCESS advances, RETRY
repeats the step, REPLAN sends control back to the planner, STOP finalizes. QA candidates
are the reviewer's flagged issues awaiting the Phase 10 QA engine's confirmation; extracting
console errors and failed requests here (deterministically) means the bug signal does not
depend on the LLM.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict

from website_agent.core.types import Severity


class ReviewDecision(enum.StrEnum):
    """The router-facing outcome of a step review (state-machine.md, decide edges)."""

    SUCCESS = "success"
    RETRY = "retry"
    REPLAN = "replan"
    STOP = "stop"


class QaCandidate(BaseModel):
    """A potential defect the reviewer flagged from observations, pre-confirmation."""

    model_config = ConfigDict(frozen=True)

    kind: str  # console_error, http_error, dead_action, unexpected_dialog, ...
    severity: Severity
    detail: str
    url: str
    step_id: str


class ReviewVerdict(BaseModel):
    """The reviewer's judgement of one executed step."""

    model_config = ConfigDict(frozen=True)

    step_id: str
    decision: ReviewDecision
    expectation_met: bool
    reasons: tuple[str, ...] = ()
    qa_candidates: tuple[QaCandidate, ...] = ()
    is_loop: bool = False
    hallucination_suspected: bool = False


# ---- LLM judgement schema: what the model returns for the semantic verdict ----


class ReviewerJudgement(BaseModel):
    """Structured output contract for the reviewer's LLM call.

    The model receives the step's expectation and the observed outcome, and judges whether
    the expectation was met. It never sees a claim of success: only observations.
    """

    model_config = ConfigDict(frozen=True)

    expectation_met: bool
    decision: ReviewDecision
    reasoning: str = ""
    hallucination_suspected: bool = False
