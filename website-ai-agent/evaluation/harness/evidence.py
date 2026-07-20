"""Assemble EvalEvidence from a finished run's state and reporting inputs.

Design rationale: the collectors are pure over EvalEvidence, so this adapter is the one place
that knows how to reduce a run (its RunResult, QA report, page graph, action history, and
ledger totals) into the flat evidence bundle. Keeping it separate means the same evidence can
be reconstructed from persisted artifacts by ``evaluate --from-run`` without a live run.
"""

from __future__ import annotations

from evaluation.harness.models import ActionOutcome, EvalEvidence, FoundDefect
from website_agent.llm.ledger import LedgerTotals
from website_agent.memory.graph import PageGraph
from website_agent.qa.models import QaReport
from website_agent.state.models import ActionRecord, RunResult


def build_evidence(
    *,
    run_result: RunResult,
    page_graph: PageGraph,
    qa_report: QaReport,
    action_history: tuple[ActionRecord, ...],
    ledger_totals: LedgerTotals,
    screenshots: int,
    wall_seconds: float,
) -> EvalEvidence:
    """Reduce a finished run to the flat evidence the metric collectors consume."""
    outcomes = tuple(
        ActionOutcome(
            action=record.action,
            success=record.success,
            navigated=record.url_before != record.url_after,
        )
        for record in action_history
    )
    findings = tuple(
        FoundDefect(kind=f.kind, location=f.url, severity=f.severity) for f in qa_report.findings
    )
    exercised = sum(1 for o in outcomes if o.success)
    return EvalEvidence(
        run_id=run_result.run_id,
        reached_pages=frozenset(n.normalized_url for n in page_graph.nodes.values()),
        exercised_elements=exercised,
        findings=findings,
        outcomes=outcomes,
        tokens=ledger_totals.total_tokens,
        cost_usd=ledger_totals.cost_usd,
        llm_calls=ledger_totals.calls,
        screenshots=screenshots,
        wall_seconds=wall_seconds,
    )
