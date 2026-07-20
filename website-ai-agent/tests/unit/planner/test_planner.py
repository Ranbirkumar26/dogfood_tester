"""Planner pipeline: dedupe, policy filter, LLM scoring, deterministic re-rank."""

from __future__ import annotations

from datetime import UTC, datetime

from website_agent.browser.models import ElementRecord, PageSnapshot
from website_agent.config.settings import LlmSettings
from website_agent.core.clock import FixedClock
from website_agent.core.types import GoalMode, RiskClass
from website_agent.llm.ledger import TokenLedger
from website_agent.llm.manager import ModelManager
from website_agent.llm.pricing import PriceTable
from website_agent.llm.rate_limit import AsyncRateLimiter
from website_agent.memory.service import MemoryService
from website_agent.planner.models import ActionType, PlannerScoring
from website_agent.planner.planner import Planner
from website_agent.planner.render import render_inventory
from website_agent.prompts.manager import PromptManager
from website_agent.state.models import GoalSpec, RunPolicy

NOW = datetime(2026, 7, 20, tzinfo=UTC)


class ScriptedModel:
    """Stand-in ModelManager.complete that returns a fixed PlannerScoring."""

    def __init__(self, scoring: PlannerScoring) -> None:
        self._scoring = scoring
        self.calls: list[tuple[str, object]] = []

    async def complete(self, role: str, prompt: object, schema: type) -> object:
        self.calls.append((role, prompt))
        return self._scoring


def _el(eid: str, name: str, *, tag: str = "a", role: str = "link", **kw: object) -> ElementRecord:
    base: dict[str, object] = {
        "element_id": eid,
        "tag": tag,
        "role": role,
        "name": name,
        "selectors": [f"css=#{eid}"],
    }
    base.update(kw)
    return ElementRecord(**base)  # type: ignore[arg-type]


def _snapshot(elements: list[ElementRecord]) -> PageSnapshot:
    return PageSnapshot(url="https://ex.com/", title="Home", captured_at=NOW, elements=elements)


def _planner(model: object) -> Planner:
    return Planner(model, PromptManager())  # type: ignore[arg-type]


def _scoring(*entries: tuple[int, float]) -> PlannerScoring:
    from website_agent.planner.models import ExpectationKind, ScoredCandidate

    return PlannerScoring(
        scored=tuple(
            ScoredCandidate(
                index=i, goal_relevance=rel, expectation_kind=ExpectationKind.URL_CHANGE
            )
            for i, rel in entries
        ),
        rationale="test strategy",
    )


async def test_plan_orders_steps_by_priority() -> None:
    snapshot = _snapshot(
        [
            _el("e1", "Home", href="https://ex.com/"),
            _el("e2", "Pricing", href="https://ex.com/pricing"),
        ]
    )
    # Candidate 2 (Pricing) scored more relevant than candidate 1 (Home).
    model = ScriptedModel(_scoring((1, 0.2), (2, 0.9)))
    plan = await _planner(model).plan(
        goal=GoalSpec(mode=GoalMode.EXPLORE, start_url="https://ex.com/"),
        policy=RunPolicy(),
        memory=MemoryService(),
        snapshot=snapshot,
        snapshot_render=render_inventory(snapshot),
    )
    assert len(plan.steps) == 2
    assert plan.steps[0].label.endswith("'Pricing'")
    assert plan.steps[0].priority > plan.steps[1].priority
    assert plan.steps[0].step_id == "step_0001"  # ids follow final order
    assert plan.rationale == "test strategy"


async def test_plan_excludes_deduped_actions() -> None:
    snapshot = _snapshot([_el("e1", "Pricing", href="https://ex.com/pricing")])
    memory = MemoryService()
    element_sig = snapshot.elements[0].signature
    memory.record_action(
        url="https://ex.com/", element_signature=element_sig, action="click", success=True
    )
    model = ScriptedModel(_scoring((1, 0.9)))
    plan = await _planner(model).plan(
        goal=GoalSpec(mode=GoalMode.EXPLORE, start_url="https://ex.com/"),
        policy=RunPolicy(),
        memory=memory,
        snapshot=snapshot,
        snapshot_render="inv",
    )
    assert plan.is_empty
    assert not model.calls  # no LLM call when nothing survives dedupe


async def test_plan_filters_destructive_under_safe_policy() -> None:
    snapshot = _snapshot([_el("e1", "Delete account", tag="button", role="button")])
    model = ScriptedModel(_scoring((1, 0.9)))
    plan = await _planner(model).plan(
        goal=GoalSpec(mode=GoalMode.EXPLORE, start_url="https://ex.com/"),
        policy=RunPolicy(allow_destructive=False),
        memory=MemoryService(),
        snapshot=snapshot,
        snapshot_render="inv",
    )
    assert plan.is_empty


async def test_plan_respects_domain_allowlist() -> None:
    snapshot = _snapshot(
        [
            _el("e1", "Internal", href="https://ex.com/page"),
            _el("e2", "External", href="https://evil.com/page"),
        ]
    )
    model = ScriptedModel(_scoring((1, 0.5)))  # only candidate 1 survives to be scored
    plan = await _planner(model).plan(
        goal=GoalSpec(mode=GoalMode.EXPLORE, start_url="https://ex.com/"),
        policy=RunPolicy(allowed_domains=frozenset({"ex.com"})),
        memory=MemoryService(),
        snapshot=snapshot,
        snapshot_render="inv",
    )
    assert len(plan.steps) == 1
    assert plan.steps[0].target_url == "https://ex.com/page"


async def test_plan_penalizes_previously_failed_actions() -> None:
    snapshot = _snapshot(
        [
            _el("e1", "Alpha", href="https://ex.com/a"),
            _el("e2", "Beta", href="https://ex.com/b"),
        ]
    )
    memory = MemoryService()
    from website_agent.memory.registry import action_signature

    # Beta previously failed; even with equal LLM relevance it should rank below Alpha.
    failed_sig = action_signature(
        url="https://ex.com/", element_signature=snapshot.elements[1].signature, action="click"
    )
    memory._state = memory._state.model_copy(
        update={"registry": memory.registry.record(failed_sig, success=False)}
    )
    model = ScriptedModel(_scoring((1, 0.5), (2, 0.5)))
    plan = await _planner(model).plan(
        goal=GoalSpec(mode=GoalMode.EXPLORE, start_url="https://ex.com/"),
        policy=RunPolicy(),
        memory=memory,
        snapshot=snapshot,
        snapshot_render="inv",
    )
    assert plan.steps[0].label.endswith("'Alpha'")


async def test_plan_horizon_caps_queue_length() -> None:
    elements = [_el(f"e{i}", f"Link{i}", href=f"https://ex.com/{i}") for i in range(1, 11)]
    snapshot = _snapshot(elements)
    model = ScriptedModel(_scoring(*[(i, 0.5) for i in range(1, 11)]))
    planner = Planner(model, PromptManager(), plan_horizon=3)  # type: ignore[arg-type]
    plan = await planner.plan(
        goal=GoalSpec(mode=GoalMode.EXPLORE, start_url="https://ex.com/"),
        policy=RunPolicy(),
        memory=MemoryService(),
        snapshot=snapshot,
        snapshot_render="inv",
    )
    assert len(plan.steps) == 3


async def test_plan_builds_input_spec_for_fills() -> None:
    from website_agent.planner.models import ExpectationKind, ScoredCandidate

    field = _el("e1", "Email", tag="input", role="textbox", input_type="email", editable=True)
    snapshot = _snapshot([field])
    scoring = PlannerScoring(
        scored=(
            ScoredCandidate(
                index=1,
                goal_relevance=0.9,
                expectation_kind=ExpectationKind.VALIDATION_ERROR,
                input_class="malformed_email",
                input_value="not-an-email",
            ),
        )
    )
    plan = await _planner(ScriptedModel(scoring)).plan(
        goal=GoalSpec(mode=GoalMode.TEST, start_url="https://ex.com/"),
        policy=RunPolicy(),
        memory=MemoryService(),
        snapshot=snapshot,
        snapshot_render="inv",
    )
    step = plan.steps[0]
    assert step.action is ActionType.FILL
    assert step.input_spec is not None
    assert step.input_spec.input_class == "malformed_email"
    assert step.input_spec.value == "not-an-email"


async def test_plan_skips_candidates_the_model_omits() -> None:
    snapshot = _snapshot(
        [
            _el("e1", "Alpha", href="https://ex.com/a"),
            _el("e2", "Beta", href="https://ex.com/b"),
        ]
    )
    # Model scores only candidate 1; candidate 2 is omitted and must not be scheduled.
    model = ScriptedModel(_scoring((1, 0.7)))
    plan = await _planner(model).plan(
        goal=GoalSpec(mode=GoalMode.EXPLORE, start_url="https://ex.com/"),
        policy=RunPolicy(),
        memory=MemoryService(),
        snapshot=snapshot,
        snapshot_render="inv",
    )
    assert len(plan.steps) == 1
    assert plan.steps[0].label.endswith("'Alpha'")


def test_render_inventory_marks_truncation_and_shows_input_type() -> None:
    field = _el("e0", "Email", tag="input", role="textbox", input_type="email", editable=True)
    links = [_el(f"e{i}", f"Link{i}", role="button", tag="button") for i in range(1, 6)]
    rendered = render_inventory(_snapshot([field, *links]), limit=2)
    assert "more elements not shown" in rendered
    assert "type=email" in rendered


def test_plan_queue_helpers() -> None:
    from website_agent.planner.models import Expectation, ExpectationKind, Plan, PlanStep

    step = PlanStep(
        step_id="step_0001",
        action=ActionType.CLICK,
        element_id="e1",
        element_signature="s",
        label="click",
        risk=RiskClass.SAFE,
        expectation=Expectation(kind=ExpectationKind.URL_CHANGE),
    )
    plan = Plan(steps=(step,))
    assert plan.next_step() is step
    assert plan.without_first().is_empty
    assert Plan(steps=()).next_step() is None


def test_render_inventory_is_bounded_and_salient() -> None:
    visible = _el("e1", "Visible", role="button", tag="button")
    hidden = _el("e2", "Hidden", role="button", tag="button", visible=False, in_viewport=False)
    snapshot = _snapshot([hidden, visible])
    rendered = render_inventory(snapshot, limit=10)
    lines = rendered.splitlines()
    # Header first, then visible before hidden.
    assert lines[0].startswith("[Home]")
    assert lines.index('e1: button "Visible"') < lines.index('e2: button "Hidden" (hidden)')


def test_real_model_manager_wires_into_planner(fixed_clock: FixedClock) -> None:
    # Sanity: Planner accepts a real ModelManager instance (type wiring), no call made.
    settings = LlmSettings(model="m")
    manager = ModelManager(
        settings,
        TokenLedger(PriceTable(), fixed_clock),
        AsyncRateLimiter(0, fixed_clock),
        transport=object(),  # unused: no completion invoked in this test
    )
    planner = Planner(manager, PromptManager())
    assert planner is not None
