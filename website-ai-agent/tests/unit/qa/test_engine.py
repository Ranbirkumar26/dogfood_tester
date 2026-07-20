"""QA engine: detector composition, cross-detector dedupe, severity ranking, counts."""

from __future__ import annotations

from datetime import UTC, datetime

from website_agent.browser.models import ElementRecord, PageSnapshot
from website_agent.core.types import Severity
from website_agent.qa.engine import QaEngine
from website_agent.qa.models import QaContext, QaFinding
from website_agent.reviewer.models import QaCandidate

NOW = datetime(2026, 7, 20, tzinfo=UTC)


def _snap(elements: list[ElementRecord]) -> PageSnapshot:
    return PageSnapshot(url="https://ex.com/", title="T", captured_at=NOW, elements=elements)


def test_analyze_ranks_findings_most_severe_first() -> None:
    ctx = QaContext(
        run_id="r",
        candidates=(
            QaCandidate(
                kind="http_error",
                severity=Severity.CRITICAL,
                detail="500",
                url="https://ex.com/",
                step_id="s",
            ),
            QaCandidate(
                kind="console_error",
                severity=Severity.MAJOR,
                detail="err",
                url="https://ex.com/",
                step_id="s",
            ),
        ),
        snapshots=(
            _snap(
                [
                    ElementRecord(
                        element_id="e1",
                        tag="input",
                        role="textbox",
                        name="",
                        dom_id="dup",
                        selectors=["css=#e1"],
                    ),
                    ElementRecord(
                        element_id="e2",
                        tag="input",
                        role="textbox",
                        name="",
                        dom_id="dup",
                        selectors=["css=#e2"],
                    ),
                ]
            ),
        ),
    )
    report = QaEngine().analyze(ctx)
    severities = [f.severity for f in report.findings]
    assert severities == sorted(severities, key=lambda s: s.rank)
    assert report.findings[0].severity is Severity.CRITICAL


def test_counts_and_blocking_flag() -> None:
    ctx = QaContext(
        run_id="r",
        candidates=(
            QaCandidate(
                kind="http_error", severity=Severity.CRITICAL, detail="500", url="u", step_id="s"
            ),
            QaCandidate(
                kind="console_error", severity=Severity.MAJOR, detail="e", url="u", step_id="s"
            ),
        ),
    )
    report = QaEngine().analyze(ctx)
    assert report.counts.critical == 1
    assert report.counts.major == 1
    assert report.counts.total == 2
    assert report.has_blocking_issues is True


def test_no_findings_is_clean_report() -> None:
    report = QaEngine().analyze(QaContext(run_id="r"))
    assert report.counts.total == 0
    assert report.has_blocking_issues is False
    assert report.findings == ()


def test_dedupe_across_detectors_by_key() -> None:
    # Two detectors that would emit the same dedupe key collapse to one finding.
    shared = QaFinding(
        kind="x", severity=Severity.MINOR, title="t", detail="d", url="u", dedupe_key="same"
    )
    engine = QaEngine(detectors=[lambda _ctx: [shared], lambda _ctx: [shared]])
    report = engine.analyze(QaContext(run_id="r"))
    assert report.counts.total == 1


def test_report_round_trips_through_json() -> None:
    ctx = QaContext(
        run_id="r",
        candidates=(
            QaCandidate(
                kind="console_error", severity=Severity.MAJOR, detail="e", url="u", step_id="s"
            ),
        ),
    )
    report = QaEngine().analyze(ctx)
    restored = report.__class__.model_validate_json(report.model_dump_json())
    assert restored == report
