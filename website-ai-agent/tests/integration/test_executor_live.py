"""Executor against a real browser session on the local fixture site."""

from __future__ import annotations

import pytest

from website_agent.browser.session import BrowserSession
from website_agent.core.clock import SystemClock
from website_agent.core.types import RiskClass
from website_agent.executor.executor import Executor
from website_agent.memory.service import MemoryService
from website_agent.planner.models import (
    ActionType,
    Expectation,
    ExpectationKind,
    InputSpec,
    PlanStep,
)

pytestmark = pytest.mark.integration


def _step(action: ActionType, element_id: str | None, **kw: object) -> PlanStep:
    return PlanStep(
        step_id="step_0001",
        action=action,
        element_id=element_id,
        element_signature="sig",
        label=action.value,
        risk=RiskClass.SAFE,
        expectation=Expectation(kind=ExpectationKind.CONTENT_CHANGE),
        **kw,  # type: ignore[arg-type]
    )


def _find(snapshot: object, testid: str) -> str:
    for element in snapshot.elements:  # type: ignore[attr-defined]
        if element.testid == testid:
            return element.element_id
    raise AssertionError(f"no element with testid={testid}")


async def test_executor_clicks_real_element(session: BrowserSession, static_basic_url: str) -> None:
    await session.goto(f"{static_basic_url}/index.html")
    snapshot = await session.snapshot()
    memory = MemoryService()
    memory.observe_page(snapshot)

    step = _step(ActionType.CLICK, _find(snapshot, "cta-primary"))
    result = await Executor(SystemClock()).execute(step, session, memory)

    assert result.ok
    assert result.screenshot is not None
    assert memory.registry.count == 1


async def test_executor_fills_and_reports_observations(
    session: BrowserSession, static_basic_url: str
) -> None:
    await session.goto(f"{static_basic_url}/contact.html")
    snapshot = await session.snapshot()
    memory = MemoryService()

    email_id = next(e.element_id for e in snapshot.elements if e.name == "Email address")
    step = _step(
        ActionType.FILL,
        email_id,
        input_spec=InputSpec(input_class="valid_email", value="qa@example.com"),
    )
    result = await Executor(SystemClock()).execute(step, session, memory)

    assert result.ok
    value = await session.page.evaluate("document.getElementById('email').value")
    assert value == "qa@example.com"


async def test_executor_navigation_records_transition(
    session: BrowserSession, static_basic_url: str
) -> None:
    await session.goto(f"{static_basic_url}/index.html")
    memory = MemoryService()
    step = _step(ActionType.NAVIGATE, None, target_url=f"{static_basic_url}/about.html")
    result = await Executor(SystemClock()).execute(step, session, memory)

    assert result.ok
    assert result.navigated
    assert result.url_after.endswith("/about.html")
    assert result.snapshot_after is not None
    assert result.snapshot_after.title == "Static Basic - About"
