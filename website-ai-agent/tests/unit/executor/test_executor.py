"""Executor: action dispatch, failure classification, memory recording, evidence capture."""

from __future__ import annotations

from typing import cast

from tests.unit.executor._fakes import FakeSession, make_snapshot

from website_agent.browser.session import BrowserSession, ElementUnavailableError
from website_agent.core.clock import FixedClock
from website_agent.core.errors import BrowserFatalError, BrowserTransientError, PolicyViolationError
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


def _step(
    action: ActionType,
    *,
    element_id: str | None = "e1",
    element_signature: str | None = "sig",
    target_url: str | None = None,
    input_spec: InputSpec | None = None,
) -> PlanStep:
    return PlanStep(
        step_id="step_0001",
        action=action,
        element_id=element_id,
        element_signature=element_signature,
        label=f"{action.value}",
        risk=RiskClass.SAFE,
        input_spec=input_spec,
        expectation=Expectation(kind=ExpectationKind.URL_CHANGE),
        target_url=target_url,
    )


def _executor(clock: FixedClock) -> Executor:
    return Executor(clock)


def _as_session(fake: FakeSession) -> BrowserSession:
    return cast(BrowserSession, fake)


async def test_click_success_records_and_captures(fixed_clock: FixedClock) -> None:
    session = FakeSession(navigate_to="https://ex.com/next", snapshot=make_snapshot())
    memory = MemoryService()
    result = await _executor(fixed_clock).execute(
        _step(ActionType.CLICK), _as_session(session), memory
    )
    assert result.ok
    assert result.navigated
    assert result.url_after == "https://ex.com/next"
    assert result.snapshot_after is not None
    assert result.screenshot is not None
    assert "click:e1" in session.calls
    # Action recorded for dedupe; visited page recorded in the graph.
    assert memory.registry.count == 1
    assert memory.graph.page_count == 1


async def test_fill_passes_input_value(fixed_clock: FixedClock) -> None:
    session = FakeSession(snapshot=make_snapshot())
    result = await _executor(fixed_clock).execute(
        _step(ActionType.FILL, input_spec=InputSpec(input_class="valid_email", value="a@b.com")),
        _as_session(session),
        MemoryService(),
    )
    assert result.ok
    assert "fill:e1:a@b.com" in session.calls


async def test_navigate_uses_target_url(fixed_clock: FixedClock) -> None:
    session = FakeSession(snapshot=make_snapshot())
    result = await _executor(fixed_clock).execute(
        _step(ActionType.NAVIGATE, element_id=None, target_url="https://ex.com/deep"),
        _as_session(session),
        MemoryService(),
    )
    assert result.ok
    assert result.url_after == "https://ex.com/deep"
    assert "goto:https://ex.com/deep" in session.calls


async def test_element_unavailable_is_classified_not_raised(fixed_clock: FixedClock) -> None:
    session = FakeSession(fail={"click": ElementUnavailableError("gone")})
    memory = MemoryService()
    result = await _executor(fixed_clock).execute(
        _step(ActionType.CLICK), _as_session(session), memory
    )
    assert not result.ok
    assert result.failure_kind == "element_unavailable"
    assert result.snapshot_after is None
    assert result.screenshot is not None  # evidence still captured on failure
    # Failed action still recorded so the planner penalizes it.
    assert memory.registry.has_failed(next(iter(memory.registry.failed)))


async def test_browser_transient_failure_is_classified(fixed_clock: FixedClock) -> None:
    session = FakeSession(fail={"click": BrowserTransientError("detached")})
    result = await _executor(fixed_clock).execute(
        _step(ActionType.CLICK), _as_session(session), MemoryService()
    )
    assert not result.ok
    assert result.failure_kind == "browser"


async def test_browser_fatal_failure_is_flagged(fixed_clock: FixedClock) -> None:
    session = FakeSession(fail={"goto": BrowserFatalError("crashed")})
    result = await _executor(fixed_clock).execute(
        _step(ActionType.NAVIGATE, element_id=None, target_url="https://ex.com/x"),
        _as_session(session),
        MemoryService(),
    )
    assert not result.ok
    assert result.failure_kind == "browser_fatal"


async def test_policy_violation_is_classified(fixed_clock: FixedClock) -> None:
    session = FakeSession(fail={"click": PolicyViolationError("off allowlist")})
    result = await _executor(fixed_clock).execute(
        _step(ActionType.CLICK), _as_session(session), MemoryService()
    )
    assert not result.ok
    assert result.failure_kind == "policy"


async def test_click_without_element_id_fails_gracefully(fixed_clock: FixedClock) -> None:
    session = FakeSession()
    result = await _executor(fixed_clock).execute(
        _step(ActionType.CLICK, element_id=None), _as_session(session), MemoryService()
    )
    assert not result.ok
    assert result.failure_kind == "element_unavailable"


async def test_navigate_without_target_fails_gracefully(fixed_clock: FixedClock) -> None:
    session = FakeSession()
    result = await _executor(fixed_clock).execute(
        _step(ActionType.NAVIGATE, element_id=None, target_url=None),
        _as_session(session),
        MemoryService(),
    )
    assert not result.ok
    assert result.failure_kind == "element_unavailable"
    assert "url" in result.detail


async def test_snapshot_failure_after_success_degrades(fixed_clock: FixedClock) -> None:
    # Click succeeds but the post-step snapshot raises: result is still ok, snapshot None.
    session = FakeSession(fail={"snapshot": BrowserTransientError("extract failed")})
    result = await _executor(fixed_clock).execute(
        _step(ActionType.CLICK), _as_session(session), MemoryService()
    )
    assert result.ok
    assert result.snapshot_after is None


async def test_settle_failure_does_not_fail_step(fixed_clock: FixedClock) -> None:
    session = FakeSession(
        fail={"wait": BrowserTransientError("idle timeout")}, snapshot=make_snapshot()
    )
    result = await _executor(fixed_clock).execute(
        _step(ActionType.CLICK), _as_session(session), MemoryService()
    )
    assert result.ok  # settle is best-effort


async def test_scroll_does_not_require_snapshot(fixed_clock: FixedClock) -> None:
    session = FakeSession()
    result = await _executor(fixed_clock).execute(
        _step(ActionType.SCROLL, element_id=None, element_signature=None),
        _as_session(session),
        MemoryService(),
    )
    assert result.ok
    assert result.snapshot_after is None  # scroll is not in the re-snapshot set
    assert "scroll:600" in session.calls


async def test_select_passes_value(fixed_clock: FixedClock) -> None:
    session = FakeSession(snapshot=make_snapshot())
    result = await _executor(fixed_clock).execute(
        _step(ActionType.SELECT, input_spec=InputSpec(input_class="option", value="bugs")),
        _as_session(session),
        MemoryService(),
    )
    assert result.ok
    assert "select:e1:bugs" in session.calls


async def test_go_back_executes(fixed_clock: FixedClock) -> None:
    session = FakeSession(snapshot=make_snapshot())
    result = await _executor(fixed_clock).execute(
        _step(ActionType.GO_BACK, element_id=None, element_signature=None),
        _as_session(session),
        MemoryService(),
    )
    assert result.ok
    assert "go_back" in session.calls


async def test_url_changed_property_reflects_navigation(fixed_clock: FixedClock) -> None:
    session = FakeSession(navigate_to="https://ex.com/next", snapshot=make_snapshot())
    result = await _executor(fixed_clock).execute(
        _step(ActionType.CLICK), _as_session(session), MemoryService()
    )
    assert result.url_changed is True

    still = FakeSession(snapshot=make_snapshot())
    same = await _executor(fixed_clock).execute(
        _step(ActionType.CLICK), _as_session(still), MemoryService()
    )
    assert same.url_changed is False
