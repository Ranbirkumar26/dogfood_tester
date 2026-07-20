"""Reporting renderers: flow graph, Markdown, exports."""

from __future__ import annotations

import csv
import io
import json

from tests.unit.reporting._inputs import sample_graph, sample_inputs

from website_agent.memory.graph import PageGraph
from website_agent.reporting.exports import render_findings_csv, render_json
from website_agent.reporting.flow_graph import render_dot, render_mermaid
from website_agent.reporting.markdown import render_qa_report, render_site_docs

# ---------------------------------------------------------------- flow graph


def test_mermaid_has_nodes_and_labelled_edges() -> None:
    mermaid = render_mermaid(sample_graph())
    assert mermaid.startswith("flowchart TD")
    assert "Home" in mermaid
    assert "About" in mermaid
    assert "-->|click|" in mermaid


def test_dot_is_well_formed() -> None:
    dot = render_dot(sample_graph())
    assert dot.startswith("digraph userflow {")
    assert dot.rstrip().endswith("}")
    assert "->" in dot


def test_flow_graph_sanitizes_unsafe_labels() -> None:
    graph = PageGraph().visit(
        url="https://ex.com/x", title='Weird "quoted"\ntitle', content_hash="h", interactive=0
    )
    mermaid = render_mermaid(graph)
    # No raw quotes or newlines from the title leak into the node label grammar.
    assert '"quoted"' not in mermaid
    assert "\n\n" not in mermaid.replace("flowchart TD\n", "")


def test_empty_graph_renders_header_only() -> None:
    assert render_mermaid(PageGraph()) == "flowchart TD"


def test_flow_graph_skips_dangling_edges() -> None:
    from website_agent.memory.graph import PageEdge, PageNode

    # An edge referencing a node key that is not present must be skipped, not crash.
    graph = PageGraph(
        nodes={
            "k1": PageNode(
                key="k1", normalized_url="https://ex.com", title="Home", content_hash="h"
            )
        },
        edges=[
            PageEdge(source_key="k1", target_key="missing", action="click"),
            PageEdge(source_key="missing", target_key="k1", action="click"),
        ],
    )
    mermaid = render_mermaid(graph)
    dot = render_dot(graph)
    assert "-->|" not in mermaid  # both edges dangle and are skipped
    assert "->" not in dot


# ------------------------------------------------------------------ markdown


def test_qa_report_markdown_lists_findings_and_metrics() -> None:
    md = render_qa_report(sample_inputs())
    assert "# QA Report: run_report" in md
    assert "Cost: $0.0021" in md
    assert "| Critical | 1 |" in md
    assert "GET /api -> 500" in md


def test_qa_report_clean_when_no_findings() -> None:
    md = render_qa_report(sample_inputs(findings=False))
    assert "No issues detected." in md


def test_site_docs_have_navigation_features_and_flow() -> None:
    md = render_site_docs(sample_inputs())
    assert "## Navigation tree" in md
    assert "https://ex.com/about" in md
    assert "## Feature inventory" in md
    assert "button: Sign up" in md
    assert "```mermaid" in md


def test_site_docs_without_snapshots_note_no_features() -> None:
    inputs = sample_inputs().model_copy(update={"snapshots": ()})
    md = render_site_docs(inputs)
    assert "No interactive features were catalogued." in md


def test_markdown_escapes_table_pipes() -> None:
    from website_agent.core.types import Severity
    from website_agent.qa.models import QaFinding, QaReport, SeverityCounts

    inputs = sample_inputs()
    tricky = QaReport(
        run_id="run_report",
        findings=(
            QaFinding(
                kind="http_error",
                severity=Severity.MAJOR,
                title="t",
                detail="value with | pipe",
                url="https://ex.com/a|b",
                dedupe_key="k",
            ),
        ),
        counts=SeverityCounts(major=1),
    )
    md = render_qa_report(inputs.model_copy(update={"qa_report": tricky}))
    assert "value with \\| pipe" in md


# ------------------------------------------------------------------- exports


def test_json_export_is_valid_and_complete() -> None:
    payload = json.loads(render_json(sample_inputs()))
    assert payload["run"]["run_id"] == "run_report"
    assert payload["qa"]["counts"]["critical"] == 1
    assert len(payload["pages"]) == 2


def test_csv_export_has_one_row_per_finding() -> None:
    text = render_findings_csv(sample_inputs())
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0] == ["severity", "kind", "url", "detail"]
    assert len(rows) == 3  # header + 2 findings
    assert rows[1][0] == "critical"
