"""Shared ReportInputs builders for reporting unit tests."""

from __future__ import annotations

from datetime import UTC, datetime

from website_agent.browser.models import ElementRecord, PageSnapshot
from website_agent.core.types import Severity, StopReason
from website_agent.memory.graph import PageGraph
from website_agent.qa.models import QaFinding, QaReport, SeverityCounts
from website_agent.reporting.inputs import ReportInputs
from website_agent.state.models import RunResult

NOW = datetime(2026, 7, 20, tzinfo=UTC)


def sample_graph() -> PageGraph:
    graph = PageGraph()
    graph = graph.visit(url="https://ex.com/", title="Home", content_hash="h1", interactive=3)
    graph = graph.visit(url="https://ex.com/about", title="About", content_hash="h2", interactive=1)
    key_home = graph.node_key("https://ex.com", "h1")
    key_about = graph.node_key("https://ex.com/about", "h2")
    return graph.connect(
        source_key=key_home, target_key=key_about, action="click", element_signature="sig"
    )


def sample_snapshots() -> tuple[PageSnapshot, ...]:
    return (
        PageSnapshot(
            url="https://ex.com/",
            title="Home",
            captured_at=NOW,
            elements=[
                ElementRecord(
                    element_id="e1", tag="a", role="link", name="About", selectors=["css=a"]
                ),
                ElementRecord(
                    element_id="e2",
                    tag="button",
                    role="button",
                    name="Sign up",
                    selectors=["css=button"],
                ),
            ],
        ),
    )


def sample_report(findings: bool = True) -> QaReport:
    if not findings:
        return QaReport(run_id="run_report")
    items = (
        QaFinding(
            kind="http_error",
            severity=Severity.CRITICAL,
            title="Failed request",
            detail="GET /api -> 500",
            url="https://ex.com/",
            dedupe_key="k1",
        ),
        QaFinding(
            kind="missing_label",
            severity=Severity.MAJOR,
            title="No label",
            detail="textbox has no name",
            url="https://ex.com/",
            dedupe_key="k2",
        ),
    )
    return QaReport(
        run_id="run_report",
        findings=items,
        counts=SeverityCounts(critical=1, major=1),
    )


def sample_inputs(findings: bool = True) -> ReportInputs:
    return ReportInputs(
        run_result=RunResult(
            run_id="run_report",
            stop_reason=StopReason.FRONTIER_EXHAUSTED,
            steps=5,
            pages_visited=2,
            findings=2 if findings else 0,
            tokens=1234,
            cost_usd=0.0021,
            started_at=NOW,
            finished_at=NOW,
        ),
        page_graph=sample_graph(),
        qa_report=sample_report(findings),
        snapshots=sample_snapshots(),
    )
