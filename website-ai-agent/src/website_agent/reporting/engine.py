"""ReportingEngine: render all outputs and persist them to the run's output directory.

Design rationale: one engine composes the pure renderers and writes their results as
artifacts under ``output/`` (docs/architecture/data-flow.md, persistence map). Writing is the
only side effect; all content generation is pure and separately tested. A failure to render
one output is logged and skipped rather than aborting the rest, so a run always ends with as
much documentation as could be produced (graceful degradation, failure-recovery.md s5).
"""

from __future__ import annotations

from website_agent.core.artifacts import ArtifactStore
from website_agent.core.types import ArtifactRef
from website_agent.logging import get_logger
from website_agent.reporting.exports import render_findings_csv, render_json
from website_agent.reporting.flow_graph import render_dot, render_mermaid
from website_agent.reporting.inputs import ReportInputs
from website_agent.reporting.markdown import render_qa_report, render_site_docs

log = get_logger("reporting.engine")


class ReportingEngine:
    """Renders every report output and writes it under the run's ``output/`` directory."""

    def __init__(self, store: ArtifactStore) -> None:
        self._store = store

    def generate(self, inputs: ReportInputs) -> dict[str, ArtifactRef]:
        """Render and persist all outputs; returns the written artifact references by name."""
        renderers = {
            "qa_report.md": render_qa_report(inputs),
            "documentation.md": render_site_docs(inputs),
            "flow.mmd": render_mermaid(inputs.page_graph),
            "flow.dot": render_dot(inputs.page_graph),
            "report.json": render_json(inputs),
            "findings.csv": render_findings_csv(inputs),
        }
        written: dict[str, ArtifactRef] = {}
        for name, content in renderers.items():
            try:
                written[name] = self._store.save_text("output", name, content)
            except Exception as exc:  # noqa: BLE001 - one failed output must not lose the rest
                log.warning("report_output_failed", output=name, reason=str(exc))
        log.info("reports_generated", run_id=inputs.run_result.run_id, outputs=len(written))
        return written
