"""Markdown renderers: QA report and generated site documentation.

Design rationale: the docs the agent produces about the site under test are derived entirely
from recorded evidence (the page graph, snapshots, QA findings), so these are pure functions
from ReportInputs to Markdown strings. No emojis or em dashes in output, per project
convention. The generated documentation is deliberately factual and structural (what pages
exist, what they link to, what interactive features they expose): it documents the site as
observed, it does not editorialize.
"""

from __future__ import annotations

from collections import Counter

from website_agent.browser.models import PageSnapshot
from website_agent.reporting.flow_graph import render_mermaid
from website_agent.reporting.inputs import ReportInputs


def _pipe(text: str) -> str:
    """Escape a value for use inside a Markdown table cell."""
    return text.replace("|", "\\|").replace("\n", " ")


def render_qa_report(inputs: ReportInputs) -> str:
    """Human-readable QA report for a run."""
    report = inputs.qa_report
    result = inputs.run_result
    counts = report.counts
    lines = [
        f"# QA Report: {result.run_id}",
        "",
        f"- Stop reason: `{result.stop_reason.value}`",
        f"- Steps: {result.steps}",
        f"- Pages visited: {result.pages_visited}",
        f"- Findings: {counts.total}",
        f"- Tokens: {result.tokens}",
        f"- Cost: ${result.cost_usd:.4f}",
        "",
        "## Findings by severity",
        "",
        "| Severity | Count |",
        "|---|---|",
        f"| Blocker | {counts.blocker} |",
        f"| Critical | {counts.critical} |",
        f"| Major | {counts.major} |",
        f"| Minor | {counts.minor} |",
        f"| Info | {counts.info} |",
        "",
    ]
    if report.findings:
        lines += ["## Findings", "", "| Severity | Kind | Page | Detail |", "|---|---|---|---|"]
        for finding in report.findings:
            lines.append(
                f"| {finding.severity.value} | {finding.kind} | "
                f"{_pipe(finding.url)} | {_pipe(finding.detail)} |"
            )
        lines.append("")
    else:
        lines += ["No issues detected.", ""]
    return "\n".join(lines)


def render_site_docs(inputs: ReportInputs) -> str:
    """Generated documentation of the site under test: navigation, features, flow."""
    graph = inputs.page_graph
    lines = [
        f"# Site Documentation: {inputs.run_result.run_id}",
        "",
        f"Generated from an autonomous exploration of {graph.page_count} distinct pages.",
        "",
        "## Navigation tree",
        "",
    ]
    for node in sorted(graph.nodes.values(), key=lambda n: n.normalized_url):
        lines.append(
            f"- [{_inline(node.title)}]({node.normalized_url}) "
            f"({node.interactive_elements} interactive elements)"
        )
    lines += ["", "## Feature inventory", ""]
    features = _feature_inventory(inputs.snapshots)
    if features:
        lines += ["| Feature | Occurrences |", "|---|---|"]
        for feature, count in features:
            lines.append(f"| {_pipe(feature)} | {count} |")
    else:
        lines.append("No interactive features were catalogued.")
    lines += ["", "## User flow", "", "```mermaid", render_mermaid(graph), "```", ""]
    return "\n".join(lines)


def _inline(text: str) -> str:
    return text.replace("[", "(").replace("]", ")").replace("\n", " ") or "(untitled)"


def _feature_inventory(snapshots: tuple[PageSnapshot, ...]) -> list[tuple[str, int]]:
    """Distinct interactive features across all visited pages, most common first."""
    tally: Counter[str] = Counter()
    for snapshot in snapshots:
        seen_on_page: set[str] = set()
        for element in snapshot.elements:
            if not element.visible or element.disabled:
                continue
            name = element.name.strip() or element.role
            feature = f"{element.role}: {name}"
            if feature not in seen_on_page:
                seen_on_page.add(feature)
                tally[feature] += 1
    return tally.most_common(50)
