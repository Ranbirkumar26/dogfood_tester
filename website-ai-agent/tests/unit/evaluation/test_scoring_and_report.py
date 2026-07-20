"""Threshold scoring, report writers, and YAML loading."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from evaluation.harness.ground_truth import load_ground_truth, load_scenario
from evaluation.harness.models import Metrics, Scenario, ScenarioResult, SuccessCriteria
from evaluation.harness.report import (
    render_csv,
    render_dashboard,
    render_json,
    render_markdown,
)
from evaluation.harness.scoring import score

_ROOT = Path(__file__).parents[3]


def _metrics(**over: float) -> Metrics:
    base: dict[str, float] = {
        "page_coverage": 0.9,
        "element_coverage": 0.8,
        "navigation_success_rate": 1.0,
        "retry_rate": 0.1,
        "loop_frequency": 0.0,
        "bug_precision": 0.9,
        "bug_recall": 0.8,
        "matched_defects": 4,
        "false_positives": 0,
        "missed_defects": 1,
        "tokens": 1000,
        "cost_usd": 0.0,
        "llm_calls": 10,
        "screenshots": 5,
        "wall_seconds": 12.0,
        "steps": 20,
    }
    base.update(over)
    return Metrics(**base)  # type: ignore[arg-type]


def _scenario(**crit: float) -> Scenario:
    return Scenario(name="s", site="site", success=SuccessCriteria(**crit))  # type: ignore[arg-type]


def test_score_passes_when_all_thresholds_met() -> None:
    result = score(_scenario(min_page_coverage=0.6, min_bug_recall=0.5), _metrics())
    assert result.passed
    assert result.failures == ()


def test_score_fails_and_explains_missed_thresholds() -> None:
    result = score(
        _scenario(min_page_coverage=0.95, min_bug_recall=0.9), _metrics(page_coverage=0.5)
    )
    assert not result.passed
    assert any("page_coverage" in f for f in result.failures)
    assert any("bug_recall" in f for f in result.failures)


def test_score_fails_on_precision_threshold() -> None:
    result = score(_scenario(min_bug_precision=0.9), _metrics(bug_precision=0.4))
    assert not result.passed
    assert any("bug_precision" in f for f in result.failures)


def _results() -> list[ScenarioResult]:
    return [
        score(_scenario(min_page_coverage=0.6), _metrics()),
        score(_scenario(min_bug_recall=0.99), _metrics(bug_recall=0.2)),
    ]


def test_json_report_is_valid() -> None:
    payload = json.loads(render_json(_results()))
    assert len(payload["scenarios"]) == 2


def test_markdown_report_summarizes_pass_fail() -> None:
    md = render_markdown(_results())
    assert "1/2 scenarios passed" in md
    assert "| s |" in md


def test_csv_report_has_header_and_rows() -> None:
    rows = list(csv.reader(io.StringIO(render_csv(_results()))))
    assert rows[0][0] == "scenario"
    assert len(rows) == 3  # header + 2


def test_dashboard_is_self_contained_html() -> None:
    html = render_dashboard(_results())
    assert html.startswith("<!doctype html>")
    assert "http" not in html.split("<style>")[0]  # no external asset links in head
    assert "1/2 scenarios passed" in html


def test_dashboard_escapes_scenario_names() -> None:
    result = score(Scenario(name="<script>", site="s", success=SuccessCriteria()), _metrics())
    html = render_dashboard([result])
    assert "<script>" not in html.split("<body>")[1]
    assert "&lt;script&gt;" in html


def test_load_committed_ground_truth_and_scenario() -> None:
    truth = load_ground_truth(_ROOT / "evaluation" / "ground_truth" / "static-basic.yaml")
    assert truth.site == "static-basic"
    assert len(truth.defects) == 3
    scenario = load_scenario(_ROOT / "evaluation" / "scenarios" / "explore-static-basic.yaml")
    assert scenario.name == "explore-static-basic"
    assert scenario.success.min_page_coverage == 0.6
