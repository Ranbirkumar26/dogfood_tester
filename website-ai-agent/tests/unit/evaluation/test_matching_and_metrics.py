"""Ground-truth matching and metric collectors."""

from __future__ import annotations

from evaluation.harness.evidence import build_evidence
from evaluation.harness.ground_truth import match_findings
from evaluation.harness.metrics import compute_metrics
from evaluation.harness.models import (
    ActionOutcome,
    Defect,
    EvalEvidence,
    FoundDefect,
    GroundTruth,
)

from website_agent.core.types import Severity


def _defect(kind: str, location: str) -> Defect:
    return Defect(id=f"d-{kind}", kind=kind, location=location, severity=Severity.MAJOR)


def _finding(kind: str, location: str) -> FoundDefect:
    return FoundDefect(kind=kind, location=location, severity=Severity.MAJOR)


# --------------------------------------------------------------------- matching


def test_match_on_kind_and_normalized_location() -> None:
    defects = (_defect("http_error", "/pricing"),)
    findings = (_finding("http_error", "https://ex.com/pricing"),)  # full URL vs path
    result = match_findings(defects, findings)
    assert len(result.matched) == 1
    assert not result.false_positives
    assert not result.missed


def test_exact_normalized_location_matches() -> None:
    # Both sides already normalize to the same value: the equality fast-path.
    result = match_findings(
        (_defect("http_error", "https://ex.com/a"),),
        (_finding("http_error", "https://ex.com/a"),),
    )
    assert len(result.matched) == 1


def test_wrong_kind_does_not_match() -> None:
    result = match_findings((_defect("http_error", "/x"),), (_finding("console_error", "/x"),))
    assert not result.matched
    assert len(result.missed) == 1
    assert len(result.false_positives) == 1


def test_each_finding_matches_at_most_one_defect() -> None:
    defects = (_defect("http_error", "/a"), _defect("http_error", "/a"))
    findings = (_finding("http_error", "https://ex.com/a"),)  # only one finding
    result = match_findings(defects, findings)
    assert len(result.matched) == 1
    assert len(result.missed) == 1  # second identical defect unmatched


# ---------------------------------------------------------------------- metrics


def _truth() -> GroundTruth:
    return GroundTruth(
        site="s",
        defects=(_defect("http_error", "/a"), _defect("console_error", "/b")),
        expected_reachable_pages=4,
        expected_interactive_elements=10,
    )


def test_precision_recall_and_coverage() -> None:
    evidence = EvalEvidence(
        run_id="r",
        reached_pages=frozenset({"https://ex.com/a", "https://ex.com/b"}),
        exercised_elements=5,
        findings=(
            _finding("http_error", "https://ex.com/a"),  # true positive
            _finding("console_error", "https://ex.com/z"),  # false positive (wrong place)
        ),
        outcomes=(
            ActionOutcome(action="click", success=True, navigated=True),
            ActionOutcome(action="click", success=False, navigated=False, retried=True),
        ),
        tokens=100,
        cost_usd=0.0,
    )
    metrics = compute_metrics(evidence, _truth())
    assert metrics.page_coverage == 0.5  # 2 of 4
    assert metrics.element_coverage == 0.5  # 5 of 10
    assert metrics.matched_defects == 1
    assert metrics.false_positives == 1
    assert metrics.missed_defects == 1
    assert metrics.bug_precision == 0.5  # 1 of 2 findings
    assert metrics.bug_recall == 0.5  # 1 of 2 defects
    assert metrics.navigation_success_rate == 0.5  # 1 of 2 nav-ish actions
    assert metrics.retry_rate == 0.5  # 1 of 2 steps retried


def test_rates_are_zero_safe_on_empty_run() -> None:
    metrics = compute_metrics(EvalEvidence(run_id="r"), GroundTruth(site="s"))
    for value in (
        metrics.page_coverage,
        metrics.bug_precision,
        metrics.bug_recall,
        metrics.retry_rate,
        metrics.navigation_success_rate,
        metrics.loop_frequency,
    ):
        assert value == 0.0


def test_loop_frequency_per_hundred_steps() -> None:
    evidence = EvalEvidence(
        run_id="r",
        outcomes=tuple(
            ActionOutcome(action="click", success=True, navigated=False, looped=(i == 0))
            for i in range(4)
        ),
    )
    metrics = compute_metrics(evidence, GroundTruth(site="s"))
    assert metrics.loop_frequency == 25.0  # 1 loop in 4 steps -> 25 per 100


def test_build_evidence_reduces_a_run() -> None:
    from datetime import UTC, datetime

    from website_agent.core.types import StopReason
    from website_agent.llm.ledger import LedgerTotals
    from website_agent.memory.graph import PageGraph
    from website_agent.qa.models import QaFinding, QaReport, SeverityCounts
    from website_agent.state.models import ActionRecord, RunResult

    now = datetime(2026, 7, 20, tzinfo=UTC)
    graph = PageGraph().visit(url="https://ex.com/a", title="A", content_hash="h", interactive=2)
    evidence = build_evidence(
        run_result=RunResult(
            run_id="r",
            stop_reason=StopReason.GOAL_MET,
            steps=2,
            pages_visited=1,
            findings=1,
            tokens=50,
            cost_usd=0.0,
            started_at=now,
            finished_at=now,
        ),
        page_graph=graph,
        qa_report=QaReport(
            run_id="r",
            findings=(
                QaFinding(
                    kind="http_error",
                    severity=Severity.CRITICAL,
                    title="t",
                    detail="500",
                    url="https://ex.com/a",
                    dedupe_key="k",
                ),
            ),
            counts=SeverityCounts(critical=1),
        ),
        action_history=(
            ActionRecord(
                step_id="step_0001",
                action="click",
                element_id="e1",
                element_signature="s",
                url_before="https://ex.com/",
                url_after="https://ex.com/a",
                success=True,
                at=now,
            ),
        ),
        ledger_totals=LedgerTotals(calls=2, prompt_tokens=40, completion_tokens=10, cost_usd=0.0),
        screenshots=3,
        wall_seconds=1.5,
    )
    assert evidence.reached_pages == frozenset({"https://ex.com/a"})
    assert evidence.exercised_elements == 1
    assert evidence.llm_calls == 2
    assert evidence.tokens == 50
    assert len(evidence.findings) == 1
