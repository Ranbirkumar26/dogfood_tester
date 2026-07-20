"""Planner: page snapshot plus memory to a prioritized, deduplicated task queue.

Design rationale (docs/architecture/planner.md): the planner is the only component that
decides intent. The pipeline is generate (deterministic) -> dedupe (registry) -> policy
filter (D12) -> LLM score -> deterministic re-rank. Candidates come from code so the model
can never reference an element that is not in the inventory (design D6); the model scores a
pre-filtered shortlist and supplies expectations, which keeps the expensive call small and
kills selector hallucination. The re-rank is pure Python so ordering is reproducible.
"""

from __future__ import annotations

from website_agent.browser.models import PageSnapshot
from website_agent.core.ids import generate_step_id
from website_agent.core.types import GoalMode
from website_agent.llm.manager import ModelManager
from website_agent.logging import get_logger
from website_agent.memory.registry import action_signature
from website_agent.memory.service import MemoryService
from website_agent.planner.candidates import generate_candidates
from website_agent.planner.models import (
    ActionCandidate,
    Expectation,
    InputSpec,
    Plan,
    PlannerScoring,
    PlanStep,
    ScoredCandidate,
    ValueEstimate,
)
from website_agent.planner.scoring import (
    compute_priority,
    coverage_gain,
    weights_for,
)
from website_agent.prompts.manager import PromptManager
from website_agent.state.models import GoalSpec, RunPolicy

log = get_logger("planner")

_MAX_SHORTLIST = 30  # candidates sent to the LLM per pass; bounds prompt cost


class Planner:
    """Produces a Plan from the current snapshot, memory, goal, and policy."""

    def __init__(
        self,
        model: ModelManager,
        prompts: PromptManager,
        *,
        plan_horizon: int = 8,
    ) -> None:
        self._model = model
        self._prompts = prompts
        self._horizon = plan_horizon

    async def plan(
        self,
        *,
        goal: GoalSpec,
        policy: RunPolicy,
        memory: MemoryService,
        snapshot: PageSnapshot,
        snapshot_render: str,
        frontier_urls: list[str] | None = None,
        feedback: str = "",
    ) -> Plan:
        """Run the planning pipeline and return a prioritized task queue.

        Args:
            snapshot: the current page snapshot (source of candidates, design D6).
            snapshot_render: token-bounded textual inventory for the prompt (the caller
                owns rendering so the planner stays free of presentation concerns).
            frontier_urls: discovered-but-unvisited navigation targets to also consider.
            feedback: reviewer feedback when routed here via REPLAN; empty otherwise.
        """
        current_url = snapshot.url
        candidates = generate_candidates(snapshot, frontier_urls=frontier_urls)
        candidates = self._dedupe(candidates, memory, current_url, goal.mode)
        candidates = self._policy_filter(candidates, policy)

        if not candidates:
            log.info("planner_no_candidates", url=current_url)
            return Plan(steps=(), rationale="no actionable, novel, policy-permitted candidates")

        shortlist = candidates[:_MAX_SHORTLIST]
        scoring = await self._score(goal, shortlist, current_url, snapshot_render, feedback)
        steps = self._rerank(goal.mode, shortlist, scoring, memory, current_url)
        plan = Plan(steps=tuple(steps[: self._horizon]), rationale=scoring.rationale)
        log.info(
            "planner_produced_plan",
            candidates=len(candidates),
            scored=len(scoring.scored),
            steps=len(plan.steps),
        )
        return plan

    # ------------------------------------------------------------- pipeline

    def _dedupe(
        self,
        candidates: list[ActionCandidate],
        memory: MemoryService,
        current_url: str,
        mode: GoalMode,
    ) -> list[ActionCandidate]:
        """Drop candidates already attempted, unless the goal mode wants a re-visit."""
        kept: list[ActionCandidate] = []
        for candidate in candidates:
            seen = memory.has_seen_action(
                url=current_url,
                element_signature=candidate.element_signature,
                action=candidate.action.value,
            )
            # Test mode re-submits forms with new input classes, so fills are never deduped
            # away here; their input_class makes them distinct at execution time.
            if seen and not (mode is GoalMode.TEST and candidate.action.value == "fill"):
                continue
            kept.append(candidate)
        return kept

    def _policy_filter(
        self, candidates: list[ActionCandidate], policy: RunPolicy
    ) -> list[ActionCandidate]:
        """Drop candidates the policy forbids (off-allowlist, disallowed risk class)."""
        from urllib.parse import urlsplit

        kept: list[ActionCandidate] = []
        for candidate in candidates:
            if not policy.permits(candidate.risk):
                continue
            if candidate.target_url and policy.allowed_domains:
                host = urlsplit(candidate.target_url).netloc.lower()
                if host and host not in policy.allowed_domains:
                    continue
            kept.append(candidate)
        return kept

    async def _score(
        self,
        goal: GoalSpec,
        shortlist: list[ActionCandidate],
        current_url: str,
        snapshot_render: str,
        feedback: str,
    ) -> PlannerScoring:
        """Ask the model to score and annotate the candidate shortlist."""
        listing = "\n".join(
            f"{i}. [{c.action.value}] {c.label} (risk={c.risk.value})"
            for i, c in enumerate(shortlist, start=1)
        )
        prompt = self._prompts.render(
            "planner",
            {
                "goal_mode": goal.mode.value,
                "goal_description": goal.description or "(none)",
                "current_url": current_url,
                "inventory": snapshot_render,
                "candidates": listing,
                "feedback": feedback or "(none)",
            },
        )
        return await self._model.complete("planner", prompt, PlannerScoring)

    def _rerank(
        self,
        mode: GoalMode,
        shortlist: list[ActionCandidate],
        scoring: PlannerScoring,
        memory: MemoryService,
        current_url: str,
    ) -> list[PlanStep]:
        """Combine LLM relevance with structural scores into a reproducible ordering."""
        weights = weights_for(mode)
        by_index = {s.index: s for s in scoring.scored}
        steps: list[PlanStep] = []

        for position, candidate in enumerate(shortlist, start=1):
            scored = by_index.get(position)
            if scored is None:
                continue  # model omitted this candidate: treat as not worth scheduling
            value = self._value(candidate, scored, memory, current_url)
            steps.append(
                self._build_step(candidate, scored, value, compute_priority(value, weights))
            )

        # Stable sort by descending priority; ties keep candidate order for determinism.
        steps.sort(key=lambda s: s.priority, reverse=True)
        # Assign step ids in final execution order so ids sort with priority.
        return [
            step.model_copy(update={"step_id": generate_step_id(i)})
            for i, step in enumerate(steps, start=1)
        ]

    # -------------------------------------------------------------- helpers

    def _value(
        self,
        candidate: ActionCandidate,
        scored: ScoredCandidate,
        memory: MemoryService,
        current_url: str,
    ) -> ValueEstimate:
        already_failed = memory.registry.has_failed(
            action_signature(
                url=current_url,
                element_signature=candidate.element_signature,
                action=candidate.action.value,
            )
        )
        # A candidate with no stable element signature (e.g. a bare navigate) still counts
        # as novel here; page-level dedupe handles repeat visits.
        novelty = 1.0
        return ValueEstimate(
            goal_relevance=scored.goal_relevance,
            novelty=novelty,
            coverage_gain=coverage_gain(candidate.action),
            depth_penalty=0.0,
            failure_penalty=1.0 if already_failed else 0.0,
        )

    def _build_step(
        self,
        candidate: ActionCandidate,
        scored: ScoredCandidate,
        value: ValueEstimate,
        priority: float,
    ) -> PlanStep:
        input_spec = None
        if candidate.action.value == "fill" and scored.input_value:
            input_spec = InputSpec(
                input_class=scored.input_class or "text", value=scored.input_value
            )
        return PlanStep(
            step_id="pending",
            action=candidate.action,
            element_id=candidate.element_id,
            element_signature=candidate.element_signature,
            label=candidate.label,
            risk=candidate.risk,
            input_spec=input_spec,
            expectation=Expectation(kind=scored.expectation_kind, detail=scored.expectation_detail),
            target_url=candidate.target_url,
            priority=priority,
            value=value,
        )
