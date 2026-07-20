"""Candidate generation and risk classification."""

from __future__ import annotations

from datetime import UTC, datetime

from website_agent.browser.models import ElementRecord, PageSnapshot
from website_agent.core.types import RiskClass
from website_agent.planner.candidates import classify_risk, generate_candidates
from website_agent.planner.models import ActionType

NOW = datetime(2026, 7, 20, tzinfo=UTC)


def _el(**kw: object) -> ElementRecord:
    base: dict[str, object] = {
        "element_id": "e1",
        "tag": "button",
        "role": "button",
        "name": "Go",
        "selectors": ["css=button"],
    }
    base.update(kw)
    return ElementRecord(**base)  # type: ignore[arg-type]


def _snap(elements: list[ElementRecord], url: str = "https://ex.com/") -> PageSnapshot:
    return PageSnapshot(url=url, title="T", captured_at=NOW, elements=elements)


def test_link_becomes_click_candidate_with_target() -> None:
    link = _el(tag="a", role="link", name="Pricing", href="https://ex.com/pricing")
    [candidate] = generate_candidates(_snap([link]))
    assert candidate.action is ActionType.CLICK
    assert candidate.target_url == "https://ex.com/pricing"
    assert candidate.element_signature == link.signature


def test_text_input_becomes_fill_candidate() -> None:
    field = _el(tag="input", role="textbox", name="Email", input_type="email", editable=True)
    [candidate] = generate_candidates(_snap([field]))
    assert candidate.action is ActionType.FILL
    assert candidate.risk is RiskClass.SAFE  # typing is safe


def test_select_becomes_select_candidate() -> None:
    dropdown = _el(tag="select", role="combobox", name="Topic", editable=True)
    [candidate] = generate_candidates(_snap([dropdown]))
    assert candidate.action is ActionType.SELECT


def test_disabled_and_hidden_elements_are_skipped() -> None:
    disabled = _el(element_id="e1", disabled=True)
    hidden = _el(element_id="e2", visible=False)
    assert generate_candidates(_snap([disabled, hidden])) == []


def test_frontier_urls_become_navigate_candidates() -> None:
    candidates = generate_candidates(_snap([]), frontier_urls=["https://ex.com/deep"])
    assert len(candidates) == 1
    assert candidates[0].action is ActionType.NAVIGATE
    assert candidates[0].target_url == "https://ex.com/deep"


def test_checkbox_input_becomes_click_not_fill() -> None:
    checkbox = _el(
        element_id="e1",
        tag="input",
        role="checkbox",
        name="Agree",
        input_type="checkbox",
        editable=True,
    )
    [candidate] = generate_candidates(_snap([checkbox]))
    assert candidate.action is ActionType.CLICK


def test_contenteditable_falls_through_to_click() -> None:
    editable_div = _el(element_id="e1", tag="div", role="textbox", name="Note", editable=False)
    [candidate] = generate_candidates(_snap([editable_div]))
    assert candidate.action is ActionType.CLICK


def test_risk_classification() -> None:
    assert (
        classify_risk(name="Delete account", tag="button", input_type=None, action=ActionType.CLICK)
        is RiskClass.DESTRUCTIVE
    )
    assert (
        classify_risk(name="Log out", tag="a", input_type=None, action=ActionType.CLICK)
        is RiskClass.DESTRUCTIVE
    )
    assert (
        classify_risk(name="Submit order", tag="button", input_type=None, action=ActionType.CLICK)
        is RiskClass.MUTATING
    )
    assert (
        classify_risk(name="", tag="input", input_type="submit", action=ActionType.CLICK)
        is RiskClass.MUTATING
    )
    assert (
        classify_risk(name="Learn more", tag="a", input_type=None, action=ActionType.CLICK)
        is RiskClass.SAFE
    )
    # Filling a field named "Delete" is still just typing until submitted... but a
    # destructive name dominates, which is the safe direction to err.
    assert (
        classify_risk(name="Delete", tag="input", input_type="text", action=ActionType.FILL)
        is RiskClass.DESTRUCTIVE
    )
