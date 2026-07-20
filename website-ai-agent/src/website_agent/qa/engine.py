"""QA engine: run the detector pipeline, dedupe across detectors, rank by severity.

Design rationale: the engine is pure composition over the detectors (all deterministic), so a
run's QA outcome is reproducible from its recorded evidence: ``website-agent report --from-run``
can re-derive findings without re-exploring. Findings are deduplicated by their stable key
(the same defect surfaced by two detectors collapses to one) and sorted most-severe-first for
reports and the CI gate.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from website_agent.core.types import Severity
from website_agent.logging import get_logger
from website_agent.qa.detectors import ALL_DETECTORS
from website_agent.qa.models import QaContext, QaFinding, QaReport, SeverityCounts

log = get_logger("qa.engine")

Detector = Callable[[QaContext], list[QaFinding]]


class QaEngine:
    """Runs detectors over a QaContext and aggregates a QaReport."""

    def __init__(self, detectors: Sequence[Detector] = ALL_DETECTORS) -> None:
        self._detectors = tuple(detectors)

    def analyze(self, context: QaContext) -> QaReport:
        """Detect, deduplicate, count, and rank findings for a run."""
        by_key: dict[str, QaFinding] = {}
        for detector in self._detectors:
            for finding in detector(context):
                # First writer wins; detectors are ordered so the most specific runs first.
                by_key.setdefault(finding.dedupe_key, finding)

        findings = sorted(by_key.values(), key=lambda f: f.sort_key)
        report = QaReport(
            run_id=context.run_id,
            findings=tuple(findings),
            counts=_count(findings),
        )
        log.info(
            "qa_analysis_complete",
            run_id=context.run_id,
            findings=report.counts.total,
            blocking=report.has_blocking_issues,
        )
        return report


def _count(findings: Sequence[QaFinding]) -> SeverityCounts:
    tally = dict.fromkeys(Severity, 0)
    for finding in findings:
        tally[finding.severity] += 1
    return SeverityCounts(
        blocker=tally[Severity.BLOCKER],
        critical=tally[Severity.CRITICAL],
        major=tally[Severity.MAJOR],
        minor=tally[Severity.MINOR],
        info=tally[Severity.INFO],
    )
