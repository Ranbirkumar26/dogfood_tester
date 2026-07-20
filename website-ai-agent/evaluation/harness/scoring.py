"""Threshold scoring: turn metrics plus success criteria into a pass/fail ScenarioResult.

Design rationale: gating is separate from measurement so it is trivially testable and the same
metrics can be re-scored under different criteria. A scenario passes only when every threshold
is met; each missed threshold is recorded in ``failures`` so a red run explains itself.
"""

from __future__ import annotations

from evaluation.harness.models import Metrics, Scenario, ScenarioResult


def score(scenario: Scenario, metrics: Metrics) -> ScenarioResult:
    """Evaluate ``metrics`` against ``scenario``'s success criteria."""
    criteria = scenario.success
    failures: list[str] = []

    if metrics.page_coverage < criteria.min_page_coverage:
        failures.append(
            f"page_coverage {metrics.page_coverage:.2f} < {criteria.min_page_coverage:.2f}"
        )
    if metrics.bug_recall < criteria.min_bug_recall:
        failures.append(f"bug_recall {metrics.bug_recall:.2f} < {criteria.min_bug_recall:.2f}")
    if metrics.bug_precision < criteria.min_bug_precision:
        failures.append(
            f"bug_precision {metrics.bug_precision:.2f} < {criteria.min_bug_precision:.2f}"
        )

    return ScenarioResult(
        scenario=scenario.name,
        site=scenario.site,
        passed=not failures,
        metrics=metrics,
        failures=tuple(failures),
    )
