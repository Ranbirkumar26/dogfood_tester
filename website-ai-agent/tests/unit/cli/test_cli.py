"""CLI commands: argument wiring, rendering, and read-only artifact commands."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from website_agent.core.types import StopReason
from website_agent.state.models import RunResult

runner = CliRunner()

NOW = datetime(2026, 7, 20, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Run each CLI test in an isolated cwd so reports/ and the registry are scoped.
    monkeypatch.chdir(tmp_path)


def _result() -> RunResult:
    return RunResult(
        run_id="run_cli_0001",
        stop_reason=StopReason.FRONTIER_EXHAUSTED,
        steps=7,
        pages_visited=3,
        findings=2,
        tokens=500,
        cost_usd=0.0012,
        started_at=NOW,
        finished_at=NOW,
    )


def test_graph_command_prints_mermaid() -> None:
    from website_agent.cli.main import app

    result = runner.invoke(app, ["graph"])
    assert result.exit_code == 0
    assert "bootstrap" in result.stdout
    assert "planner" in result.stdout


def test_run_command_invokes_runner_and_renders(monkeypatch: pytest.MonkeyPatch) -> None:
    from website_agent.agent import runner as runner_module
    from website_agent.cli.main import app

    captured = {}

    class FakeRunner:
        def __init__(self, settings: object, **kw: object) -> None:
            captured["built"] = True

        async def run(self, spec: object) -> RunResult:
            captured["spec"] = spec
            return _result()

        def close(self) -> None:
            captured["closed"] = True

    monkeypatch.setattr("website_agent.cli.main.AgentRunner", FakeRunner)
    del runner_module  # imported only to assert the module path exists

    result = runner.invoke(app, ["run", "https://ex.com/", "--max-steps", "5"])
    assert result.exit_code == 0, result.stdout
    assert "run_cli_0001" in result.stdout
    assert "Frontier" in result.stdout or "frontier_exhausted" in result.stdout
    assert captured["closed"] is True
    # The step budget override reached the spec.
    assert captured["spec"].budgets.max_steps == 5
    # same_domain default restricts to the start domain.
    assert "ex.com" in captured["spec"].policy.allowed_domains


def test_test_command_uses_test_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from website_agent.cli.main import app
    from website_agent.core.types import GoalMode

    captured = {}

    class FakeRunner:
        def __init__(self, settings: object, **kw: object) -> None: ...

        async def run(self, spec: object) -> RunResult:
            captured["mode"] = spec.goal.mode
            return _result()

        def close(self) -> None: ...

    monkeypatch.setattr("website_agent.cli.main.AgentRunner", FakeRunner)
    result = runner.invoke(app, ["test", "https://ex.com/"])
    assert result.exit_code == 0
    assert captured["mode"] is GoalMode.TEST


def test_resume_command_calls_runner_resume(monkeypatch: pytest.MonkeyPatch) -> None:
    from website_agent.cli.main import app

    captured = {}

    class FakeRunner:
        def __init__(self, settings: object, **kw: object) -> None: ...

        async def resume(self, run_id: str) -> RunResult:
            captured["run_id"] = run_id
            return _result()

        def close(self) -> None:
            captured["closed"] = True

    monkeypatch.setattr("website_agent.cli.main.AgentRunner", FakeRunner)
    result = runner.invoke(app, ["resume", "run_abc123"])
    assert result.exit_code == 0, result.stdout
    assert captured["run_id"] == "run_abc123"
    assert captured["closed"] is True
    assert "run_cli_0001" in result.stdout


def test_docs_command_uses_document_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from website_agent.cli.main import app
    from website_agent.core.types import GoalMode

    captured = {}

    class FakeRunner:
        def __init__(self, settings: object, **kw: object) -> None: ...

        async def run(self, spec: object) -> RunResult:
            captured["mode"] = spec.goal.mode
            return _result()

        def close(self) -> None: ...

    monkeypatch.setattr("website_agent.cli.main.AgentRunner", FakeRunner)
    result = runner.invoke(app, ["docs", "https://ex.com/"])
    assert result.exit_code == 0
    assert captured["mode"] is GoalMode.DOCUMENT


def test_list_command_renders_registry_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    from website_agent.cli.main import app

    class FakeRunner:
        def __init__(self, settings: object, **kw: object) -> None: ...

        def list_runs(self) -> list[dict[str, object]]:
            return [
                {
                    "run_id": "run_a",
                    "status": "finished",
                    "stop_reason": "goal_met",
                    "steps": 9,
                    "cost_usd": 0.01,
                    "updated_at": "2026-07-20",
                }
            ]

        def close(self) -> None: ...

    monkeypatch.setattr("website_agent.cli.main.AgentRunner", FakeRunner)
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "run_a" in result.stdout
    assert "finished" in result.stdout


def test_summary_command_errors_when_missing() -> None:
    from website_agent.cli.main import app

    result = runner.invoke(app, ["summary", "absent"])
    assert result.exit_code == 1
    assert "No report.json" in result.stdout


def test_report_command_prints_saved_markdown(tmp_path: Path) -> None:
    from website_agent.cli.main import app

    out = tmp_path / "reports" / "run_x" / "output"
    out.mkdir(parents=True)
    (out / "qa_report.md").write_text("# QA Report: run_x\n\nNo issues detected.")
    result = runner.invoke(app, ["report", "run_x"])
    assert result.exit_code == 0
    assert "QA Report: run_x" in result.stdout


def test_report_command_errors_when_missing() -> None:
    from website_agent.cli.main import app

    result = runner.invoke(app, ["report", "absent"])
    assert result.exit_code == 1
    assert "No report" in result.stdout


def test_evaluate_command_scores_a_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from website_agent.agent.runner import RunArtifacts
    from website_agent.cli.main import app
    from website_agent.core.types import Severity
    from website_agent.llm.ledger import LedgerTotals
    from website_agent.memory.graph import PageGraph
    from website_agent.qa.models import QaFinding, QaReport, SeverityCounts

    graph = PageGraph().visit(
        url="https://demo.local/", title="Home", content_hash="h", interactive=2
    )

    class FakeRunner:
        def __init__(self, settings: object, **kw: object) -> None: ...

        async def run_collecting(self, spec: object) -> RunArtifacts:
            return RunArtifacts(
                run_result=_result(),
                qa_report=QaReport(
                    run_id="run_cli_0001",
                    findings=(
                        QaFinding(
                            kind="console_error",
                            severity=Severity.MAJOR,
                            title="t",
                            detail="err",
                            url="https://demo.local/",
                            dedupe_key="k",
                        ),
                    ),
                    counts=SeverityCounts(major=1),
                ),
                page_graph=graph,
                action_history=(),
                ledger_totals=LedgerTotals(
                    calls=0, prompt_tokens=0, completion_tokens=0, cost_usd=0.0
                ),
                screenshots=0,
                wall_seconds=1.0,
            )

        def close(self) -> None: ...

    monkeypatch.setattr("website_agent.cli.main.AgentRunner", FakeRunner)

    scenario = tmp_path / "scenario.yaml"
    scenario.write_text(
        "name: demo\nsite: demo\nmode: explore\nsuccess:\n"
        "  min_page_coverage: 0.0\n  min_bug_recall: 0.0\n  min_bug_precision: 0.0\n"
    )
    ground_truth = tmp_path / "gt.yaml"
    ground_truth.write_text(
        "site: demo\nexpected_reachable_pages: 1\nexpected_interactive_elements: 2\n"
        "defects:\n  - id: GT-1\n    kind: console_error\n    location: '/'\n"
    )
    out = tmp_path / "evalout"
    result = runner.invoke(
        app,
        [
            "evaluate",
            "https://demo.local",
            "--scenario",
            str(scenario),
            "--ground-truth",
            str(ground_truth),
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert (out / "eval_result.json").is_file()
    assert (out / "dashboard.html").is_file()
    assert "scenarios passed" in result.stdout


def test_summary_command_reads_report_json(tmp_path: Path) -> None:
    from website_agent.cli.main import app

    out = tmp_path / "reports" / "run_y" / "output"
    out.mkdir(parents=True)
    (out / "report.json").write_text(json.dumps({"qa": {"counts": {"critical": 2, "major": 1}}}))
    result = runner.invoke(app, ["summary", "run_y"])
    assert result.exit_code == 0
    assert "critical" in result.stdout
    assert "2" in result.stdout


def test_list_command_empty() -> None:
    from website_agent.cli.main import app

    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "No runs recorded" in result.stdout


def test_no_args_shows_help() -> None:
    from website_agent.cli.main import app

    result = runner.invoke(app, [])
    # no_args_is_help prints usage and exits non-zero by convention (like argparse).
    assert result.exit_code == 2
    assert "run" in result.stdout
    assert "graph" in result.stdout


def test_help_lists_all_commands() -> None:
    from website_agent.cli.main import app

    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("run", "test", "resume", "docs", "report", "graph", "list", "summary"):
        assert command in result.stdout
