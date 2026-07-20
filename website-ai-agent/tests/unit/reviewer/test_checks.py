"""Deterministic reviewer checks: mechanical expectations and QA-candidate extraction."""

from __future__ import annotations

from datetime import UTC, datetime

from website_agent.browser.models import (
    ConsoleEvent,
    DialogRecord,
    DownloadRecord,
    NetworkEvent,
    ObservationBundle,
)
from website_agent.core.types import RiskClass, Severity
from website_agent.executor.models import ExecutionResult
from website_agent.planner.models import (
    ActionType,
    Expectation,
    ExpectationKind,
    PlanStep,
)
from website_agent.reviewer.checks import check_mechanical, extract_qa_candidates, is_mechanical

NOW = datetime(2026, 7, 20, tzinfo=UTC)


def _result(
    *,
    ok: bool = True,
    action: str = "click",
    url_before: str = "https://ex.com/a",
    url_after: str = "https://ex.com/a",
    console: list[ConsoleEvent] | None = None,
    network: list[NetworkEvent] | None = None,
    dialogs: list[DialogRecord] | None = None,
    downloads: list[DownloadRecord] | None = None,
) -> ExecutionResult:
    return ExecutionResult(
        step_id="step_0001",
        action=action,
        element_id="e1",
        ok=ok,
        url_before=url_before,
        url_after=url_after,
        navigated=url_before != url_after,
        observations=ObservationBundle(
            step_id="step_0001",
            console=console or [],
            network=network or [],
            dialogs=dialogs or [],
            downloads=downloads or [],
        ),
        at=NOW,
    )


def _step(kind: ExpectationKind) -> PlanStep:
    return PlanStep(
        step_id="step_0001",
        action=ActionType.CLICK,
        element_id="e1",
        element_signature="sig",
        label="click",
        risk=RiskClass.SAFE,
        expectation=Expectation(kind=kind),
    )


def test_is_mechanical() -> None:
    assert is_mechanical(ExpectationKind.URL_CHANGE)
    assert is_mechanical(ExpectationKind.DIALOG)
    assert not is_mechanical(ExpectationKind.VALIDATION_ERROR)
    assert not is_mechanical(ExpectationKind.CONTENT_CHANGE)


def test_url_change_expectation() -> None:
    changed = _result(url_after="https://ex.com/b")
    unchanged = _result()
    assert check_mechanical(_step(ExpectationKind.URL_CHANGE), changed)
    assert not check_mechanical(_step(ExpectationKind.URL_CHANGE), unchanged)


def test_dialog_expectation() -> None:
    with_dialog = _result(
        dialogs=[DialogRecord(kind="alert", message="hi", action="dismissed", at=NOW)]
    )
    assert check_mechanical(_step(ExpectationKind.DIALOG), with_dialog)
    assert not check_mechanical(_step(ExpectationKind.DIALOG), _result())


def test_download_expectation() -> None:
    with_download = _result(
        downloads=[DownloadRecord(suggested_name="f.txt", source_url=None, relpath="d/f", at=NOW)]
    )
    assert check_mechanical(_step(ExpectationKind.DOWNLOAD), with_download)


def test_no_change_expectation() -> None:
    assert check_mechanical(_step(ExpectationKind.NO_CHANGE), _result())
    assert not check_mechanical(
        _step(ExpectationKind.NO_CHANGE), _result(url_after="https://ex.com/b")
    )


def test_console_errors_become_candidates() -> None:
    result = _result(
        console=[
            ConsoleEvent(level="error", text="TypeError: undefined is not a function", at=NOW),
            ConsoleEvent(level="log", text="ignored", at=NOW),
        ]
    )
    candidates = extract_qa_candidates(result)
    console = [c for c in candidates if c.kind == "console_error"]
    assert len(console) == 1
    assert console[0].severity is Severity.MAJOR


def test_http_errors_severity_by_status() -> None:
    result = _result(
        network=[
            NetworkEvent(method="GET", url="/missing", status=404, ok=False, at=NOW),
            NetworkEvent(method="POST", url="/api", status=500, ok=False, at=NOW),
        ]
    )
    http = {c.detail.split()[1]: c for c in extract_qa_candidates(result) if c.kind == "http_error"}
    assert http["/missing"].severity is Severity.MAJOR
    assert http["/api"].severity is Severity.CRITICAL


def test_dead_action_candidate_for_inert_click() -> None:
    result = _result(action="click")  # ok, no url change, no dialog, no download
    dead = [c for c in extract_qa_candidates(result) if c.kind == "dead_action"]
    assert len(dead) == 1
    assert dead[0].severity is Severity.MINOR


def test_no_dead_action_when_click_navigates() -> None:
    result = _result(action="click", url_after="https://ex.com/b")
    assert not [c for c in extract_qa_candidates(result) if c.kind == "dead_action"]
