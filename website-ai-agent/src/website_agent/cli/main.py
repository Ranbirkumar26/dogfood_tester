"""Typer CLI: the command surface over AgentRunner and the reporting artifacts.

Design rationale (docs/architecture/components.md, rule 5): the CLI is a thin adapter. It
parses arguments, builds a RunSpec, calls the shared AgentRunner, and renders the result with
Rich; no business logic lives here. Commands that produce a run are async under the hood and
wrapped with asyncio.run. Read-only commands (graph, report, docs, list) touch only artifacts
and the run registry, so they work without a browser or a key.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from website_agent.agent.graph import render_graph_mermaid
from website_agent.agent.runner import AgentRunner, RunSpec
from website_agent.config.settings import load_settings
from website_agent.core.types import GoalMode, Severity
from website_agent.logging import configure_logging
from website_agent.state.models import Budgets, GoalSpec, RunPolicy, RunResult

app = typer.Typer(
    name="website-agent",
    help="Autonomous website exploration and QA agent.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()

_UrlArg = Annotated[str, typer.Argument(help="Start URL to explore.")]
_ConfigOpt = Annotated[Path | None, typer.Option("--config", help="TOML config file.")]


def _budgets(max_steps: int | None, max_usd: float | None, defaults: Budgets) -> Budgets:
    return defaults.model_copy(
        update={k: v for k, v in (("max_steps", max_steps), ("max_usd", max_usd)) if v is not None}
    )


def _run(
    url: str,
    mode: GoalMode,
    config: Path | None,
    max_steps: int | None,
    max_usd: float | None,
    same_domain: bool,
) -> RunResult:
    settings = load_settings(config_file=config)
    configure_logging(settings.logging)
    default_budgets = Budgets(
        max_steps=settings.budgets.max_steps,
        max_tokens=settings.budgets.max_tokens,
        max_usd=settings.budgets.max_usd,
        max_wall_seconds=settings.budgets.max_wall_seconds,
        max_consecutive_failures=settings.budgets.max_consecutive_failures,
    )
    from urllib.parse import urlsplit

    allowed = frozenset({urlsplit(url).netloc.lower()}) if same_domain else frozenset()
    spec = RunSpec(
        goal=GoalSpec(mode=mode, start_url=url),
        policy=RunPolicy(allowed_domains=allowed),
        budgets=_budgets(max_steps, max_usd, default_budgets),
    )
    runner = AgentRunner(settings)
    try:
        with console.status(f"Exploring {url} ..."):
            return asyncio.run(runner.run(spec))
    finally:
        runner.close()


def _render_result(result: RunResult) -> None:
    table = Table(title=f"Run {result.run_id}", show_header=False)
    table.add_row("Stop reason", result.stop_reason.value)
    table.add_row("Steps", str(result.steps))
    table.add_row("Pages visited", str(result.pages_visited))
    table.add_row("Findings", str(result.findings))
    table.add_row("Tokens", str(result.tokens))
    table.add_row("Cost", f"${result.cost_usd:.4f}")
    console.print(table)
    console.print(f"Reports written under [bold]reports/{result.run_id}/output/[/bold]")


@app.command()
def run(
    url: _UrlArg,
    config: _ConfigOpt = None,
    max_steps: Annotated[int | None, typer.Option(help="Override the step budget.")] = None,
    max_usd: Annotated[float | None, typer.Option(help="Override the USD budget.")] = None,
    same_domain: Annotated[
        bool, typer.Option(help="Restrict navigation to the start URL's domain.")
    ] = True,
) -> None:
    """Explore a website and produce QA reports and documentation."""
    _render_result(_run(url, GoalMode.EXPLORE, config, max_steps, max_usd, same_domain))


@app.command(name="test")
def run_test(
    url: _UrlArg,
    config: _ConfigOpt = None,
    max_steps: Annotated[int | None, typer.Option(help="Override the step budget.")] = None,
    max_usd: Annotated[float | None, typer.Option(help="Override the USD budget.")] = None,
) -> None:
    """Explore in test mode: exercise forms and probe validation."""
    _render_result(_run(url, GoalMode.TEST, config, max_steps, max_usd, same_domain=True))


@app.command()
def docs(
    url: _UrlArg,
    config: _ConfigOpt = None,
    max_steps: Annotated[int | None, typer.Option(help="Override the step budget.")] = None,
) -> None:
    """Explore in document mode: generate site documentation breadth-first."""
    _render_result(_run(url, GoalMode.DOCUMENT, config, max_steps, None, same_domain=True))


@app.command(name="list")
def list_runs(config: _ConfigOpt = None) -> None:
    """List recorded runs from the run registry."""
    settings = load_settings(config_file=config)
    runner = AgentRunner(settings)
    try:
        runs = runner.list_runs()
    finally:
        runner.close()
    if not runs:
        console.print("No runs recorded yet.")
        return
    columns = ("run_id", "status", "stop_reason", "steps", "cost_usd", "updated_at")
    table = Table(title="Runs")
    for column in columns:
        table.add_column(column)
    for row in runs:
        table.add_row(*(str(row.get(c, "")) for c in columns))
    console.print(table)


@app.command()
def report(
    run_id: Annotated[str, typer.Argument(help="Run id whose QA report to print.")],
    config: _ConfigOpt = None,
) -> None:
    """Print a run's QA report from its output directory."""
    settings = load_settings(config_file=config)
    path = settings.paths.reports_dir / run_id / "output" / "qa_report.md"
    if not path.is_file():
        console.print(f"[red]No report found at {path}[/red]")
        raise typer.Exit(code=1)
    console.print(path.read_text())


@app.command()
def graph() -> None:
    """Print the agent's plan-execute-review graph as Mermaid."""
    console.print(render_graph_mermaid())


@app.command()
def evaluate(
    base_url: Annotated[str, typer.Argument(help="Base URL of the site to evaluate.")],
    scenario: Annotated[Path, typer.Option("--scenario", help="Scenario YAML file.")],
    ground_truth: Annotated[Path, typer.Option("--ground-truth", help="Ground-truth YAML file.")],
    config: _ConfigOpt = None,
    out: Annotated[Path, typer.Option("--out", help="Directory for eval outputs.")] = Path(
        "reports/eval"
    ),
) -> None:
    """Run a scenario against a site and score it against labeled ground truth.

    Requires the evaluation harness, which ships only in a source checkout (not the wheel).
    """
    try:
        from evaluation.harness import (
            build_evidence,
            compute_metrics,
            load_ground_truth,
            load_scenario,
            render_dashboard,
            render_json,
            render_markdown,
            score,
        )
    except ModuleNotFoundError:
        console.print(
            "[red]The evaluation harness is not available; run from a source checkout.[/red]"
        )
        raise typer.Exit(code=1) from None

    scenario_def = load_scenario(scenario)
    truth = load_ground_truth(ground_truth)
    settings = load_settings(config_file=config)
    configure_logging(settings.logging)

    spec = RunSpec(
        goal=GoalSpec(mode=scenario_def.mode, start_url=base_url),
        policy=RunPolicy(),
        budgets=_scenario_budgets(scenario_def, settings),
    )
    runner = AgentRunner(settings)
    try:
        with console.status(f"Evaluating {base_url} ..."):
            artifacts = asyncio.run(runner.run_collecting(spec))
    finally:
        runner.close()

    evidence = build_evidence(
        run_result=artifacts.run_result,
        page_graph=artifacts.page_graph,
        qa_report=artifacts.qa_report,
        action_history=artifacts.action_history,
        ledger_totals=artifacts.ledger_totals,
        screenshots=artifacts.screenshots,
        wall_seconds=artifacts.wall_seconds,
    )
    result = score(scenario_def, compute_metrics(evidence, truth))

    out.mkdir(parents=True, exist_ok=True)
    (out / "eval_result.json").write_text(render_json([result]))
    (out / "report.md").write_text(render_markdown([result]))
    (out / "dashboard.html").write_text(render_dashboard([result]))

    console.print(render_markdown([result]))
    if not result.passed:
        raise typer.Exit(code=1)


def _scenario_budgets(scenario: object, settings: object) -> Budgets:
    return Budgets(
        max_steps=scenario.max_steps,  # type: ignore[attr-defined]
        max_tokens=settings.budgets.max_tokens,  # type: ignore[attr-defined]
        max_usd=scenario.max_usd,  # type: ignore[attr-defined]
        max_wall_seconds=scenario.max_wall_seconds,  # type: ignore[attr-defined]
        max_consecutive_failures=settings.budgets.max_consecutive_failures,  # type: ignore[attr-defined]
    )


@app.command()
def summary(
    run_id: Annotated[str, typer.Argument(help="Run id to summarize.")],
    config: _ConfigOpt = None,
) -> None:
    """Print a run's machine-readable findings summary from report.json."""
    settings = load_settings(config_file=config)
    path = settings.paths.reports_dir / run_id / "output" / "report.json"
    if not path.is_file():
        console.print(f"[red]No report.json found at {path}[/red]")
        raise typer.Exit(code=1)
    payload = json.loads(path.read_text())
    counts = payload["qa"]["counts"]
    table = Table(title=f"Findings: {run_id}", show_header=False)
    for severity in Severity:
        table.add_row(severity.value, str(counts.get(severity.value, 0)))
    console.print(table)


if __name__ == "__main__":  # pragma: no cover - module entry point
    app()
