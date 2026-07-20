"""Executor output model: the mechanical record of one step's execution.

Design rationale (design D2): the executor reports only what mechanically happened, never
whether it was correct; that judgement is the reviewer's, made from these observations. So
ExecutionResult carries the tool outcome, the before/after URLs and snapshot, the captured
observation bundle, and a screenshot reference, with no verdict. A failed tool call produces
a result with ``ok=False`` and the failure classified, not an exception: the loop must keep
control (docs/architecture/failure-recovery.md).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from website_agent.browser.models import ObservationBundle, PageSnapshot
from website_agent.core.types import ArtifactRef


class ExecutionResult(BaseModel):
    """What happened when one PlanStep ran; the reviewer's evidence."""

    model_config = ConfigDict(frozen=True)

    step_id: str
    action: str
    element_id: str | None
    ok: bool
    failure_kind: str | None = None  # element_unavailable, browser_transient, policy, ...
    detail: str = ""
    url_before: str
    url_after: str
    navigated: bool
    snapshot_after: PageSnapshot | None = None
    observations: ObservationBundle
    screenshot: ArtifactRef | None = None
    at: datetime

    @property
    def url_changed(self) -> bool:
        """Whether the top-level URL changed as a result of the step."""
        return self.url_before != self.url_after
