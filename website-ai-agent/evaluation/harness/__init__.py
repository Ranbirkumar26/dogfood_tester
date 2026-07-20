"""Evaluation harness: ground truth, metrics, scoring, and report writers."""

from evaluation.harness.evidence import build_evidence
from evaluation.harness.ground_truth import (
    MatchResult,
    load_ground_truth,
    load_scenario,
    match_findings,
)
from evaluation.harness.metrics import compute_metrics
from evaluation.harness.models import (
    ActionOutcome,
    Defect,
    EvalEvidence,
    FoundDefect,
    GroundTruth,
    Metrics,
    Scenario,
    ScenarioResult,
    SuccessCriteria,
)
from evaluation.harness.report import (
    render_csv,
    render_dashboard,
    render_json,
    render_markdown,
)
from evaluation.harness.scoring import score

__all__ = [
    "ActionOutcome",
    "Defect",
    "EvalEvidence",
    "FoundDefect",
    "GroundTruth",
    "MatchResult",
    "Metrics",
    "Scenario",
    "ScenarioResult",
    "SuccessCriteria",
    "build_evidence",
    "compute_metrics",
    "load_ground_truth",
    "load_scenario",
    "match_findings",
    "render_csv",
    "render_dashboard",
    "render_json",
    "render_markdown",
    "score",
]
