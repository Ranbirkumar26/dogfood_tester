"""Evaluation data models: ground truth, scenarios, evidence, metrics, results.

Design rationale (docs/architecture/evaluation.md): metrics are only meaningful against
labeled ground truth, so a fixture site ships a YAML file of planted defects and expected
coverage. The collectors are pure functions over an EvalEvidence bundle assembled from a
finished run, so scoring is reproducible and can be re-run over any past run directory
without re-exploring. Thresholds gate on the minimum across repeats, never the mean, so a
lucky run cannot mask a flaky regression.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from website_agent.core.types import GoalMode, Severity


class Defect(BaseModel):
    """One planted defect in a fixture site's ground truth."""

    model_config = ConfigDict(frozen=True)

    id: str
    kind: str  # aligns 1:1 with QA-engine finding kinds
    location: str  # normalized URL or path where the defect lives
    severity: Severity = Severity.MAJOR
    notes: str = ""


class GroundTruth(BaseModel):
    """Labeled truth for a fixture site."""

    model_config = ConfigDict(frozen=True)

    site: str
    defects: tuple[Defect, ...] = ()
    expected_reachable_pages: int = 0
    expected_interactive_elements: int = 0


class SuccessCriteria(BaseModel):
    """Thresholds a scenario must meet to count as a pass (gate on the minimum)."""

    model_config = ConfigDict(frozen=True)

    min_page_coverage: float = 0.0
    min_bug_recall: float = 0.0
    min_bug_precision: float = 0.0


class Scenario(BaseModel):
    """A named evaluation scenario over a fixture site."""

    model_config = ConfigDict(frozen=True)

    name: str
    site: str
    mode: GoalMode = GoalMode.EXPLORE
    max_steps: int = 60
    max_usd: float = 0.5
    max_wall_seconds: int = 900
    success: SuccessCriteria = Field(default_factory=SuccessCriteria)


class ActionOutcome(BaseModel):
    """The minimal per-step record the metrics need (from the run's action history)."""

    model_config = ConfigDict(frozen=True)

    action: str
    success: bool
    navigated: bool
    retried: bool = False
    looped: bool = False


class FoundDefect(BaseModel):
    """A QA finding reduced to what matters for matching against ground truth."""

    model_config = ConfigDict(frozen=True)

    kind: str
    location: str
    severity: Severity


class EvalEvidence(BaseModel):
    """Everything the collectors read, assembled from one finished run."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    reached_pages: frozenset[str] = frozenset()
    exercised_elements: int = 0
    findings: tuple[FoundDefect, ...] = ()
    outcomes: tuple[ActionOutcome, ...] = ()
    tokens: int = 0
    cost_usd: float = 0.0
    llm_calls: int = 0
    screenshots: int = 0
    wall_seconds: float = 0.0


class Metrics(BaseModel):
    """The computed metric set for one run (docs/architecture/evaluation.md, section 3)."""

    model_config = ConfigDict(frozen=True)

    page_coverage: float
    element_coverage: float
    navigation_success_rate: float
    retry_rate: float
    loop_frequency: float
    bug_precision: float
    bug_recall: float
    matched_defects: int
    false_positives: int
    missed_defects: int
    tokens: int
    cost_usd: float
    llm_calls: int
    screenshots: int
    wall_seconds: float
    steps: int


class ScenarioResult(BaseModel):
    """The scored outcome of running one scenario."""

    model_config = ConfigDict(frozen=True)

    scenario: str
    site: str
    passed: bool
    metrics: Metrics
    failures: tuple[str, ...] = ()  # which thresholds were missed
