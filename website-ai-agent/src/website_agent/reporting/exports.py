"""Machine-readable exports: JSON and CSV of a run's findings and metrics.

Design rationale: CI, spreadsheets, and the eval harness consume structured output, not
Markdown. JSON carries the full typed report; CSV is a flat one-row-per-finding table plus a
metrics row for quick diffing. Both are pure functions from ReportInputs to strings.
"""

from __future__ import annotations

import csv
import io
import json

from website_agent.reporting.inputs import ReportInputs


def render_json(inputs: ReportInputs) -> str:
    """Full run report as pretty JSON (schema-versioned by the embedded models)."""
    payload = {
        "run": inputs.run_result.model_dump(mode="json"),
        "qa": inputs.qa_report.model_dump(mode="json"),
        "pages": [
            {
                "url": node.normalized_url,
                "title": node.title,
                "interactive_elements": node.interactive_elements,
                "visit_count": node.visit_count,
            }
            for node in sorted(inputs.page_graph.nodes.values(), key=lambda n: n.normalized_url)
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def render_findings_csv(inputs: ReportInputs) -> str:
    """One row per finding: severity, kind, url, detail."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["severity", "kind", "url", "detail"])
    for finding in inputs.qa_report.findings:
        writer.writerow([finding.severity.value, finding.kind, finding.url, finding.detail])
    return buffer.getvalue()
