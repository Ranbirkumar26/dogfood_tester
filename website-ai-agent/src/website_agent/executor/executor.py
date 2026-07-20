"""Executor: run one plan step via the browser tool layer, return a structured result.

Design rationale: the executor decides mechanics, not intent (the planner decides intent,
the reviewer decides truth). It is the only role allowed to touch the tool layer
(docs/architecture/components.md, rule 3). It is deliberately LLM-free: the plan step
already carries everything needed to act, so execution is a deterministic dispatch, which
keeps it fast, cheap, and exhaustively testable. Every browser failure is caught and turned
into a failed ExecutionResult with the failure classified; the executor never raises into
the graph, so the reviewer and router always get to run
(docs/architecture/failure-recovery.md). Each executed action is recorded in memory so the
planner's dedupe sees it on the next pass.
"""

from __future__ import annotations

from website_agent.browser.session import BrowserSession, ElementUnavailableError
from website_agent.core.clock import Clock
from website_agent.core.errors import BrowserError, PolicyViolationError
from website_agent.executor.models import ExecutionResult
from website_agent.logging import get_logger
from website_agent.memory.service import MemoryService
from website_agent.planner.models import ActionType, PlanStep

log = get_logger("executor")

# Actions after which the page may have changed and a fresh snapshot is worth taking.
_SNAPSHOT_AFTER = {
    ActionType.CLICK,
    ActionType.NAVIGATE,
    ActionType.GO_BACK,
    ActionType.SELECT,
}


class Executor:
    """Executes a single PlanStep against a BrowserSession."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    async def execute(
        self, step: PlanStep, session: BrowserSession, memory: MemoryService
    ) -> ExecutionResult:
        """Run ``step`` and return its mechanical outcome (never raises on step failure)."""
        url_before = session.page.url
        input_class = step.input_spec.input_class if step.input_spec else ""

        ok, failure_kind, detail = await self._dispatch(step, session)

        if ok and step.action in _SNAPSHOT_AFTER:
            # Let the page settle before re-extracting; a failed settle degrades to
            # whatever is present rather than failing the (successful) action.
            await self._settle(session)

        snapshot_after = await self._safe_snapshot(session) if ok else None
        url_after = session.page.url
        screenshot = await session.screenshots.capture(session.page, step.step_id)
        observations = session.drain_observations(step.step_id)

        memory.record_action(
            url=url_before,
            element_signature=step.element_signature,
            action=step.action.value,
            input_class=input_class,
            success=ok,
        )
        if ok and snapshot_after is not None:
            memory.observe_page(snapshot_after)

        result = ExecutionResult(
            step_id=step.step_id,
            action=step.action.value,
            element_id=step.element_id,
            ok=ok,
            failure_kind=failure_kind,
            detail=detail,
            url_before=url_before,
            url_after=url_after,
            navigated=url_before != url_after,
            snapshot_after=snapshot_after,
            observations=observations,
            screenshot=screenshot,
            at=self._clock.now(),
        )
        log.info(
            "step_executed",
            step_id=step.step_id,
            action=step.action.value,
            ok=ok,
            failure_kind=failure_kind,
            navigated=result.navigated,
        )
        return result

    async def _dispatch(
        self, step: PlanStep, session: BrowserSession
    ) -> tuple[bool, str | None, str]:
        """Invoke the tool for the step's action; classify any failure."""
        try:
            await self._invoke(step, session)
        except ElementUnavailableError as exc:
            return False, "element_unavailable", str(exc)
        except PolicyViolationError as exc:
            return False, "policy", str(exc)
        except BrowserError as exc:
            # Transient and fatal browser errors both surface here after the session's
            # own in-tool retries are exhausted; the reviewer/router decides what next.
            kind = "browser_fatal" if type(exc).__name__ == "BrowserFatalError" else "browser"
            return False, kind, str(exc)
        return True, None, ""

    async def _invoke(self, step: PlanStep, session: BrowserSession) -> None:
        """Map a PlanStep action onto the corresponding session tool call."""
        action = step.action
        if action is ActionType.CLICK:
            await session.click(_require_element(step))
        elif action is ActionType.FILL:
            value = step.input_spec.value if step.input_spec else ""
            await session.fill(_require_element(step), value)
        elif action is ActionType.SELECT:
            value = step.input_spec.value if step.input_spec else ""
            await session.select_option(_require_element(step), value)
        elif action is ActionType.NAVIGATE:
            await session.goto(_require_target(step))
        elif action is ActionType.GO_BACK:
            await session.go_back()
        elif action is ActionType.SCROLL:
            await session.scroll(600)

    async def _settle(self, session: BrowserSession) -> None:
        try:
            await session.wait_for_load("networkidle")
        except BrowserError:
            log.debug("settle_skipped", reason="load state wait failed; continuing")

    async def _safe_snapshot(self, session: BrowserSession):  # type: ignore[no-untyped-def]
        try:
            return await session.snapshot()
        except BrowserError as exc:
            log.warning("post_step_snapshot_failed", reason=str(exc))
            return None


def _require_element(step: PlanStep) -> str:
    if step.element_id is None:
        raise ElementUnavailableError(
            "step requires an element id but has none", context={"step_id": step.step_id}
        )
    return step.element_id


def _require_target(step: PlanStep) -> str:
    if step.target_url is None:
        raise ElementUnavailableError(
            "navigate step requires a target url but has none",
            context={"step_id": step.step_id},
        )
    return step.target_url
