# Module: cli

Layer 5 interface: the Typer command surface. A thin adapter over `AgentRunner` and the reporting artifacts (docs/architecture/components.md, rule 5); no business logic here.

## Commands

| Command | Does |
|---|---|
| `website-agent run <url>` | Explore a site (explore mode); prints a run summary and writes reports |
| `website-agent test <url>` | Explore in test mode: exercise forms, probe validation |
| `website-agent docs <url>` | Explore in document mode: breadth-first for documentation |
| `website-agent report <run_id>` | Print a run's QA report Markdown from its output directory |
| `website-agent summary <run_id>` | Print a run's findings counts from report.json |
| `website-agent list` | List recorded runs from the registry |
| `website-agent graph` | Print the plan-execute-review graph as Mermaid |
| `website-agent evaluate <url> --scenario ... --ground-truth ...` | Run a scenario against a site and score it against labeled ground truth (source checkout only) |

`evaluate` uses `AgentRunner.run_collecting`, which returns a `RunArtifacts` bundle (run result, QA report, page graph, action history, ledger totals, screenshots, wall time) that the evaluation harness reduces to evidence and scores. The harness is dev tooling and ships only in a source checkout, so `evaluate` imports it lazily and errors cleanly when unavailable.

Common options: `--config <toml>`, `--max-steps`, `--max-usd`, `--same-domain/--no-same-domain` (run defaults to restricting navigation to the start URL's domain, design D12).

## Design

Commands that produce a run build a `RunSpec`, call the shared `AgentRunner`, and render the `RunResult` with Rich. The async run is wrapped in `asyncio.run`. Read-only commands (`graph`, `report`, `summary`, `list`) touch only artifacts and the run registry, so they work without a browser or an API key: `graph` in particular renders the topology from a deps-free graph build, so it never launches Chromium.

## Entry point

Installed as the `website-agent` console script (`[project.scripts]`). `no_args_is_help` prints usage when invoked bare.

## Tested

Every command is unit-tested with Typer's `CliRunner`; run-producing commands use a fake `AgentRunner` so the tests are fast and keyless. The `graph` command is tested end-to-end, and the installed console script is smoke-tested.
