"""ReportInputs: the evidence bundle the reporting engine renders.

Design rationale: reporting is a pure transform from recorded run data to documents, so it
takes one immutable inputs object rather than reaching into live services. This keeps every
renderer independently testable and lets ``website-agent report --from-run`` rebuild all
outputs from a finished run's artifacts without re-exploring (docs/architecture/evaluation.md,
collectors reusable over any past run directory).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from website_agent.browser.models import PageSnapshot
from website_agent.memory.graph import PageGraph
from website_agent.qa.models import QaReport
from website_agent.state.models import ActionRecord, RunResult


class ReportInputs(BaseModel):
    """Everything the reporting engine needs, assembled from a finished run."""

    model_config = ConfigDict(frozen=True)

    run_result: RunResult
    page_graph: PageGraph
    qa_report: QaReport
    snapshots: tuple[PageSnapshot, ...] = ()
    action_history: tuple[ActionRecord, ...] = ()
