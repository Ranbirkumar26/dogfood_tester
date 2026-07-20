"""Metric collectors: pure functions from evidence and ground truth to Metrics.

Design rationale (docs/architecture/evaluation.md, section 3): every metric is a pure
computation over recorded evidence, so scores are reproducible and unit-testable without a
browser or a model. Rates are defined to be well-behaved at zero (no steps, no findings) so a
trivial run scores 0, not NaN. Precision and recall follow the standard definitions over the
mechanical match against ground truth.
"""

from __future__ import annotations

from evaluation.harness.ground_truth import MatchResult, match_findings
from evaluation.harness.models import EvalEvidence, GroundTruth, Metrics


def _safe_ratio(numerator: float, denominator: float) -> float:
    """numerator/denominator, or 0.0 when the denominator is zero."""
    return numerator / denominator if denominator else 0.0


def compute_metrics(evidence: EvalEvidence, truth: GroundTruth) -> Metrics:
    """Score one run's evidence against a fixture site's ground truth."""
    match = match_findings(truth.defects, evidence.findings)
    steps = len(evidence.outcomes)

    return Metrics(
        page_coverage=_safe_ratio(len(evidence.reached_pages), truth.expected_reachable_pages),
        element_coverage=_safe_ratio(
            evidence.exercised_elements, truth.expected_interactive_elements
        ),
        navigation_success_rate=_navigation_success(evidence),
        retry_rate=_safe_ratio(sum(o.retried for o in evidence.outcomes), steps),
        loop_frequency=_safe_ratio(sum(o.looped for o in evidence.outcomes) * 100, steps),
        bug_precision=_precision(match),
        bug_recall=_recall(match, truth),
        matched_defects=len(match.matched),
        false_positives=len(match.false_positives),
        missed_defects=len(match.missed),
        tokens=evidence.tokens,
        cost_usd=evidence.cost_usd,
        llm_calls=evidence.llm_calls,
        screenshots=evidence.screenshots,
        wall_seconds=evidence.wall_seconds,
        steps=steps,
    )


def _navigation_success(evidence: EvalEvidence) -> float:
    attempts = [o for o in evidence.outcomes if o.action in ("navigate", "click", "go_back")]
    if not attempts:
        return 0.0
    succeeded = sum(1 for o in attempts if o.success)
    return succeeded / len(attempts)


def _precision(match: MatchResult) -> float:
    total_findings = len(match.matched) + len(match.false_positives)
    return _safe_ratio(len(match.matched), total_findings)


def _recall(match: MatchResult, truth: GroundTruth) -> float:
    return _safe_ratio(len(match.matched), len(truth.defects))
