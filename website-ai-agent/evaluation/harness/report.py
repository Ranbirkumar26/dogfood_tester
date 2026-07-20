"""Evaluation report writers: JSON, Markdown, CSV, and a self-contained HTML dashboard.

Design rationale (docs/architecture/evaluation.md, section 6): CI consumes JSON for threshold
gates, humans read the Markdown summary and the HTML dashboard, and CSV feeds spreadsheets and
history plots. The dashboard is a single self-contained file (no external assets) so it can be
published as a CI artifact and opened anywhere. All writers are pure functions from results to
strings.
"""

from __future__ import annotations

import csv
import io
import json

from evaluation.harness.models import ScenarioResult


def render_json(results: list[ScenarioResult]) -> str:
    """Machine-readable results for the CI gate."""
    return json.dumps(
        {"scenarios": [r.model_dump(mode="json") for r in results]}, indent=2, sort_keys=True
    )


def render_markdown(results: list[ScenarioResult]) -> str:
    """Human summary table of all scenarios."""
    passed = sum(1 for r in results if r.passed)
    lines = [
        "# Evaluation Report",
        "",
        f"{passed}/{len(results)} scenarios passed.",
        "",
        "| Scenario | Pass | Coverage | Recall | Precision | Cost | Steps |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        m = r.metrics
        mark = "yes" if r.passed else "NO"
        lines.append(
            f"| {r.scenario} | {mark} | {m.page_coverage:.2f} | {m.bug_recall:.2f} | "
            f"{m.bug_precision:.2f} | ${m.cost_usd:.4f} | {m.steps} |"
        )
    lines.append("")
    for r in results:
        if r.failures:
            lines.append(f"- {r.scenario}: {'; '.join(r.failures)}")
    return "\n".join(lines)


def render_csv(results: list[ScenarioResult]) -> str:
    """One row per scenario with the full metric set."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "scenario",
            "site",
            "passed",
            "page_coverage",
            "element_coverage",
            "navigation_success_rate",
            "retry_rate",
            "loop_frequency",
            "bug_precision",
            "bug_recall",
            "matched",
            "false_positives",
            "missed",
            "tokens",
            "cost_usd",
            "llm_calls",
            "screenshots",
            "wall_seconds",
            "steps",
        ]
    )
    for r in results:
        m = r.metrics
        writer.writerow(
            [
                r.scenario,
                r.site,
                r.passed,
                f"{m.page_coverage:.4f}",
                f"{m.element_coverage:.4f}",
                f"{m.navigation_success_rate:.4f}",
                f"{m.retry_rate:.4f}",
                f"{m.loop_frequency:.4f}",
                f"{m.bug_precision:.4f}",
                f"{m.bug_recall:.4f}",
                m.matched_defects,
                m.false_positives,
                m.missed_defects,
                m.tokens,
                f"{m.cost_usd:.6f}",
                m.llm_calls,
                m.screenshots,
                f"{m.wall_seconds:.2f}",
                m.steps,
            ]
        )
    return buffer.getvalue()


def render_dashboard(results: list[ScenarioResult]) -> str:
    """Single self-contained HTML dashboard (no external assets)."""
    passed = sum(1 for r in results if r.passed)
    rows = "\n".join(
        f"<tr class='{'ok' if r.passed else 'bad'}'>"
        f"<td>{_esc(r.scenario)}</td><td>{'PASS' if r.passed else 'FAIL'}</td>"
        f"<td>{r.metrics.page_coverage:.2f}</td><td>{r.metrics.bug_recall:.2f}</td>"
        f"<td>{r.metrics.bug_precision:.2f}</td><td>${r.metrics.cost_usd:.4f}</td>"
        f"<td>{r.metrics.steps}</td></tr>"
        for r in results
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Evaluation Dashboard</title>
<style>
body{{font-family:system-ui,sans-serif;margin:2rem;color:#1a1a1a}}
h1{{font-size:1.4rem}} table{{border-collapse:collapse;width:100%;margin-top:1rem}}
th,td{{border:1px solid #ddd;padding:.5rem .75rem;text-align:left}}
td{{font-variant-numeric:tabular-nums}}
th{{background:#f5f5f5}} tr.ok td:nth-child(2){{color:#0a7d33;font-weight:600}}
tr.bad td:nth-child(2){{color:#c0271b;font-weight:600}}
.summary{{font-size:1.1rem;margin-top:.5rem}}
</style></head><body>
<h1>Evaluation Dashboard</h1>
<div class="summary">{passed}/{len(results)} scenarios passed</div>
<table><thead><tr><th>Scenario</th><th>Result</th><th>Coverage</th><th>Recall</th>
<th>Precision</th><th>Cost</th><th>Steps</th></tr></thead>
<tbody>
{rows}
</tbody></table>
</body></html>
"""


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )
