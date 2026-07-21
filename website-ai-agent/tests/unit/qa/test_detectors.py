"""QA detectors: candidate promotion, accessibility, duplicate ids, dead pages."""

from __future__ import annotations

from datetime import UTC, datetime

from website_agent.browser.models import ElementRecord, PageSnapshot
from website_agent.core.types import Severity
from website_agent.qa.detectors import (
    detect_duplicate_ids,
    detect_empty_pages,
    detect_from_candidates,
    detect_missing_labels,
)
from website_agent.qa.models import QaContext
from website_agent.reviewer.models import QaCandidate

NOW = datetime(2026, 7, 20, tzinfo=UTC)


def _el(eid: str, role: str, name: str = "", **kw: object) -> ElementRecord:
    base: dict[str, object] = {
        "element_id": eid,
        "tag": "input",
        "role": role,
        "name": name,
        "selectors": [f"css=#{eid}"],
    }
    base.update(kw)
    return ElementRecord(**base)  # type: ignore[arg-type]


def _snap(elements: list[ElementRecord], url: str = "https://ex.com/") -> PageSnapshot:
    return PageSnapshot(url=url, title="T", captured_at=NOW, elements=elements)


def _candidate(
    kind: str, url: str, detail: str, severity: Severity = Severity.MAJOR
) -> QaCandidate:
    return QaCandidate(kind=kind, severity=severity, detail=detail, url=url, step_id="step_0001")


def test_candidate_promotion_dedupes_across_run() -> None:
    ctx = QaContext(
        run_id="r",
        candidates=(
            _candidate("console_error", "https://ex.com/a", "TypeError x"),
            _candidate("console_error", "https://ex.com/a", "TypeError x"),  # same defect
            _candidate("console_error", "https://ex.com/b", "TypeError x"),  # different page
        ),
    )
    findings = detect_from_candidates(ctx)
    assert len(findings) == 2  # collapsed the duplicate, kept the distinct page
    assert findings[0].title == "JavaScript console error"


def test_candidate_promotion_titles_new_finding_types() -> None:
    ctx = QaContext(
        run_id="r",
        candidates=(
            _candidate("unexpected_redirect", "https://ex.com/a", "ended at login"),
            _candidate("missing_validation", "https://ex.com/form", "invalid email accepted"),
            _candidate("slow_request", "https://ex.com/app", "GET /api took 3000ms"),
        ),
    )
    titles = {finding.kind: finding.title for finding in detect_from_candidates(ctx)}
    assert titles == {
        "unexpected_redirect": "Unexpected redirect",
        "missing_validation": "Missing form validation",
        "slow_request": "Slow network request",
    }


def test_missing_label_detected_for_unnamed_control() -> None:
    ctx = QaContext(
        run_id="r",
        snapshots=(
            _snap(
                [
                    _el("e1", "textbox", name=""),  # unnamed: a finding
                    _el("e2", "textbox", name="Email"),  # named: fine
                ]
            ),
        ),
    )
    findings = detect_missing_labels(ctx)
    assert len(findings) == 1
    assert findings[0].kind == "missing_label"
    assert findings[0].severity is Severity.MAJOR


def test_missing_label_ignores_non_form_roles_and_disabled() -> None:
    ctx = QaContext(
        run_id="r",
        snapshots=(
            _snap(
                [
                    _el("e1", "link", name=""),  # links do not need this check here
                    _el("e2", "textbox", name="", disabled=True),  # disabled: skip
                    _el("e3", "textbox", name="", visible=False),  # hidden: skip
                ]
            ),
        ),
    )
    assert detect_missing_labels(ctx) == []


def test_duplicate_ids_detected() -> None:
    ctx = QaContext(
        run_id="r",
        snapshots=(
            _snap(
                [
                    _el("e1", "textbox", dom_id="email"),
                    _el("e2", "textbox", dom_id="email"),  # duplicate id
                    _el("e3", "button", dom_id="submit"),  # unique
                ]
            ),
        ),
    )
    findings = detect_duplicate_ids(ctx)
    assert len(findings) == 1
    assert "email" in findings[0].detail
    assert findings[0].severity is Severity.MINOR


def test_empty_page_flagged_as_dead_navigation() -> None:
    ctx = QaContext(
        run_id="r",
        snapshots=(
            _snap([], url="https://ex.com/blank"),
            _snap([_el("e1", "button", name="Go")], url="https://ex.com/live"),
        ),
    )
    findings = detect_empty_pages(ctx)
    assert len(findings) == 1
    assert findings[0].url == "https://ex.com/blank"
    assert findings[0].kind == "dead_navigation"
