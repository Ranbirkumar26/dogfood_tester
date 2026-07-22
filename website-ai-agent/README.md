# Website AI Agent

![CI](https://github.com/Ranbirkumar26/dogfood_tester/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Coverage](https://img.shields.io/badge/coverage-~97%25-brightgreen)
![Type checked: mypy strict](https://img.shields.io/badge/mypy-strict-blue)

Autonomous website exploration and QA agent. Give it a URL and a goal, and it will use a
real Chromium browser to explore the site, click and fill UI, watch console and network
events, detect common defects, capture screenshots, build user-flow graphs, and write
human-readable plus machine-readable reports.

The project is open source under the MIT license and the GitHub repository is public:
[Ranbirkumar26/dogfood_tester](https://github.com/Ranbirkumar26/dogfood_tester).

## What It Does

Website AI Agent is built for QA engineers, developers, founders, and maintainers who want
an automated browser agent that can inspect a website the way a careful tester would.

It can:

- Explore a website with a real Playwright browser.
- Understand visible interactive elements through DOM and accessibility snapshots.
- Plan safe actions with an LLM.
- Click links and buttons.
- Fill forms and select options.
- Navigate multi-page workflows.
- Capture screenshots and browser observations.
- Watch JavaScript console errors.
- Watch failed and slow network requests.
- Detect broken links, HTTP failures, dead clicks, missing labels, duplicate ids,
  unexpected redirects, missing validation, dead navigation, and related QA signals.
- Generate Markdown, JSON, CSV, and graph outputs.
- Resume interrupted runs from durable checkpoints.
- Run from a CLI, a FastAPI server, or Docker.

It intentionally does not:

- Bypass CAPTCHA or bot-protection.
- Perform security fuzzing or brute force attacks.
- Crawl random third-party websites without permission.
- Click destructive actions by default.
- Replace manual QA, accessibility audits, or load testing.

Use it on your own websites, local apps, staging environments, or systems where you have
explicit permission.

## Current Status

Pre-release, feature-complete through the core build.

All 18 original build phases are implemented:

| Phase | Scope | Status |
|---|---|---|
| 1 | Architecture and design | Done |
| 2 | Foundation: config, logging, errors, DI | Done |
| 3 | Browser tooling | Done |
| 4 | LLM tooling | Done |
| 5 | State and memory | Done |
| 6 | Planner | Done |
| 7 | Executor | Done |
| 8 | Reviewer | Done |
| 9 | LangGraph orchestration | Done |
| 10 | QA engine | Done |
| 11 | Documentation/reporting engine | Done |
| 12 | Evaluation harness | Done |
| 13 | CLI | Done |
| 14 | FastAPI server | Done |
| 15 | Docker | Done |
| 16 | CI/CD | Done |
| 17 | Open-source prep | Done |
| 18 | Final audit | Done |

Local verification at the latest audit:

- 399 tests passing.
- 97.31 percent coverage.
- `ruff check` clean.
- `ruff format --check` clean.
- `mypy --strict` clean.

See [docs/FINAL_AUDIT.md](docs/FINAL_AUDIT.md) for the engineering audit.

## How It Works

The core loop is:

```text
bootstrap -> planner -> executor -> reviewer -> decide -> planner or executor or finalize
```

- **Browser layer** observes the real page: URL, title, DOM, accessibility-derived element
  inventory, console logs, network events, screenshots, downloads, popups, and storage
  state.
- **Planner** decides which action is worth trying next.
- **Executor** performs exactly one typed browser action.
- **Reviewer** checks whether the observed outcome matched the expectation.
- **Decision router** enforces budgets, retries, loop detection, and stop conditions.
- **Reporting engine** writes QA reports, generated docs, flow graphs, and exports.

The model never invents raw selectors. It only references element IDs extracted from the
current page. The executor resolves those IDs back to live browser locators and rejects
anything that is not present.

Architecture docs start here: [docs/architecture/overview.md](docs/architecture/overview.md).

For future LLM coding agents, read [AGENTS.md](AGENTS.md) and the repository-root
[AGENTS.md](../AGENTS.md). They summarize architecture boundaries, commands, safety
rules, and the vulnerability/risk map.

## Quick Start For Beginners

This section assumes you have never run the project before.

### 1. Install System Requirements

You need:

- Python 3.11, 3.12, or 3.13.
- Git.
- A terminal.
- An LLM provider:
  - OpenAI or another hosted OpenAI-compatible API, or
  - a local OpenAI-compatible server such as Ollama or vLLM.

### 2. Clone The Public Repo

```bash
git clone https://github.com/Ranbirkumar26/dogfood_tester.git
cd dogfood_tester/website-ai-agent
```

### 3. Create A Virtual Environment

macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

### 4. Install The Project

For normal use from a source checkout:

```bash
pip install -e ".[dev]"
```

Install Chromium for Playwright:

```bash
playwright install chromium
```

Check that the CLI is available:

```bash
website-agent --help
website-agent graph
```

`website-agent graph` does not need an API key. It prints the LangGraph state machine.

## Configure An LLM

The agent needs an LLM for planning and semantic review. The LLM must be reachable through
the OpenAI-compatible chat completions API.

Configuration can be provided through environment variables or a `.env` file.

Start from the example file:

```bash
cp .env.example .env
```

### Option A: OpenAI

```bash
export WA_LLM__BASE_URL="https://api.openai.com/v1"
export WA_LLM__API_KEY="your_api_key_here"
export WA_LLM__MODEL="gpt-4o-mini"
```

Then run:

```bash
website-agent run https://example.com --max-steps 20 --max-usd 0.25
```

### Option B: Local Model With Ollama

Run an OpenAI-compatible local model server, then point the agent at it:

```bash
export WA_LLM__BASE_URL="http://localhost:11434/v1"
export WA_LLM__API_KEY="not-needed"
export WA_LLM__MODEL="your-local-model"
```

Then run:

```bash
website-agent run https://example.com --max-steps 20 --max-usd 0
```

Unknown local model names are priced at zero by the built-in cost ledger. The model still
needs to follow JSON instructions well enough for structured outputs.

### Option C: Other OpenAI-Compatible Providers

Set:

```bash
export WA_LLM__BASE_URL="https://provider.example.com/openai/v1"
export WA_LLM__API_KEY="provider_key_here"
export WA_LLM__MODEL="provider-model-name"
```

Examples of compatible deployments include Groq, OpenRouter, vLLM, LM Studio, and hosted
OpenAI-compatible gateways. Check the provider's own base URL and model name.

## Your First Safe Run

Start with a site you own or a local fixture. For a fully local website:

```bash
python -m http.server 8008 --directory tests/fixtures/sites/static-basic
```

In a second terminal:

```bash
cd dogfood_tester/website-ai-agent
source .venv/bin/activate
website-agent run http://127.0.0.1:8008/index.html --max-steps 20 --max-usd 0
```

If you use a hosted paid model, use a small USD budget:

```bash
website-agent run http://127.0.0.1:8008/index.html --max-steps 20 --max-usd 0.10
```

Reports are written to:

```text
reports/<run_id>/output/
```

To see recent runs:

```bash
website-agent list
```

To print a Markdown QA report:

```bash
website-agent report <run_id>
```

To print a compact severity summary:

```bash
website-agent summary <run_id>
```

## CLI Commands

### `website-agent run`

General exploration and QA.

```bash
website-agent run https://staging.example.com --max-steps 40 --max-usd 0.25
```

Use this first for most sites.

### `website-agent test`

Form and validation oriented mode.

```bash
website-agent test https://staging.example.com --max-steps 50 --max-usd 0.50
```

This mode prioritizes forms and edge cases. Use it on staging, not production, unless the
target app is safe to interact with.

### `website-agent docs`

Documentation-oriented exploration.

```bash
website-agent docs https://docs.example.com --max-steps 60
```

Use this when you want navigation trees, feature inventories, and generated site docs.

### `website-agent resume`

Resume an interrupted run from its checkpoint:

```bash
website-agent resume <run_id>
```

### `website-agent list`

List saved runs:

```bash
website-agent list
```

### `website-agent report`

Print the QA report:

```bash
website-agent report <run_id>
```

### `website-agent summary`

Print a severity count summary from `report.json`:

```bash
website-agent summary <run_id>
```

### `website-agent graph`

Print the LangGraph state machine as Mermaid:

```bash
website-agent graph
```

### `website-agent evaluate`

Run a fixture scenario and score it against ground truth:

```bash
python -m http.server 8008 --directory tests/fixtures/sites/static-basic

website-agent evaluate http://127.0.0.1:8008/index.html \
  --scenario evaluation/scenarios/explore-static-basic.yaml \
  --ground-truth evaluation/ground_truth/static-basic.yaml \
  --out reports/eval/static-basic
```

Evaluation outputs include JSON, Markdown, and a self-contained HTML dashboard.

## Understanding Reports

Each run writes a folder under:

```text
reports/<run_id>/
```

Important output files:

| File | Purpose |
|---|---|
| `output/qa_report.md` | Human-readable QA report |
| `output/report.json` | Full machine-readable report |
| `output/findings.csv` | Spreadsheet-friendly findings export |
| `output/flow_graph.mmd` | Mermaid user-flow graph |
| `qa/findings.json` | Raw QA findings from the detector pipeline |
| `screenshots/` | Screenshots captured during execution |
| `state/storage_state.json` | Browser storage state saved at finalize |

Common finding types:

| Finding | Meaning |
|---|---|
| `console_error` | JavaScript console error or page error |
| `http_error` | Failed request or HTTP status 400 and above |
| `dead_action` | Click succeeded mechanically but had no observable effect |
| `missing_label` | Form control has no accessible name |
| `duplicate_id` | Page has repeated author-assigned ids |
| `dead_navigation` | Visited page exposes no interactive elements |
| `unexpected_redirect` | Navigation ended somewhere other than the expected target |
| `missing_validation` | Invalid input flow did not show expected validation feedback |
| `slow_request` | Request exceeded the built-in slow-request threshold |

Severity levels:

| Severity | Meaning |
|---|---|
| `blocker` | Run or core workflow is blocked |
| `critical` | Serious server or workflow failure |
| `major` | User-visible defect or important accessibility issue |
| `minor` | Lower-risk issue or quality concern |
| `info` | Informational signal |

## Running The API Server

Start the FastAPI server:

```bash
python -m website_agent.api
```

Defaults:

```text
Host: 127.0.0.1
Port: 8000
Swagger UI: http://127.0.0.1:8000/docs
```

Override host and port:

```bash
export WA_API_HOST="0.0.0.0"
export WA_API_PORT="8000"
python -m website_agent.api
```

Start a run with curl:

```bash
curl -X POST http://127.0.0.1:8000/runs \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "mode": "explore",
    "same_domain": true,
    "max_steps": 20,
    "max_usd": 0.25
  }'
```

Check status:

```bash
curl http://127.0.0.1:8000/runs/<run_id>
```

Fetch the Markdown report:

```bash
curl http://127.0.0.1:8000/runs/<run_id>/report
```

## Running With Docker

Build:

```bash
docker build -t website-ai-agent .
```

Create `.env`:

```bash
cp .env.example .env
```

For Ollama running on your host machine, use this in `.env`:

```text
WA_LLM__BASE_URL=http://host.docker.internal:11434/v1
WA_LLM__API_KEY=not-needed
WA_LLM__MODEL=your-local-model
```

Run CLI:

```bash
docker run --rm --env-file .env -v wa_reports:/data/reports \
  website-ai-agent run https://example.com --max-steps 40
```

Run API:

```bash
docker compose up api
```

Swagger UI:

```text
http://localhost:8000/docs
```

More Docker details: [docs/guides/docker.md](docs/guides/docker.md).

## Configuration Reference

All config uses the `WA_` prefix and double underscores for nesting.

Common variables:

| Variable | Example | Meaning |
|---|---|---|
| `WA_LLM__BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible API base URL |
| `WA_LLM__API_KEY` | `sk-...` | Provider API key |
| `WA_LLM__MODEL` | `gpt-4o-mini` | Model name |
| `WA_LLM__MODE` | `live` | `live`, `record`, or `replay` |
| `WA_LLM__CASSETTE_DIR` | `tests/fixtures/cassettes` | Record/replay cassette path |
| `WA_BROWSER__HEADLESS` | `true` | Run Chromium headlessly |
| `WA_BUDGETS__MAX_STEPS` | `100` | Default step budget |
| `WA_BUDGETS__MAX_USD` | `1.00` | Default cost budget |
| `WA_BUDGETS__MAX_WALL_SECONDS` | `1800` | Default wall-clock budget |
| `WA_LOGGING__FORMAT` | `rich` | `rich` or `json` logs |
| `WA_PATHS__REPORTS_DIR` | `reports` | Run artifact directory |

Full example: [.env.example](.env.example).

## Safety And Responsible Use

This project controls a real browser. Treat it like an automated tester with hands.

Recommended rules:

1. Start on local fixtures or staging.
2. Use `--max-steps` and `--max-usd` on every first run.
3. Keep `same_domain` enabled unless you intentionally need cross-domain navigation.
4. Do not run against third-party sites without permission.
5. Do not use production accounts with real payment, deletion, or irreversible workflows.
6. Review reports before turning findings into tickets.
7. Keep API keys in `.env` or environment variables, not in code or prompts.

The default run policy is safe-explore. Destructive-looking actions are blocked unless a
future run policy explicitly permits them.

See [SECURITY.md](SECURITY.md) for the full security posture.

## Tips For Better Results

- Prefer staging URLs with realistic data but no irreversible side effects.
- Give the agent a small budget first, then increase once reports look sane.
- Start with `website-agent run`, then use `website-agent test` for forms.
- Use accessible labels in your app. The agent relies heavily on accessibility metadata,
  and your users benefit too.
- Use stable attributes such as `data-testid` on important controls.
- Keep pages deterministic during tests. Random modals and rotating experiments make
  automated exploration harder to interpret.
- Investigate console and network findings first. They are usually high-signal.
- Save the entire `reports/<run_id>/` folder when filing issues. It contains screenshots,
  evidence, and machine-readable exports.
- Use local models for cheap iteration, then a stronger hosted model for important runs.
- Run the bundled fixture scenarios before changing planner, reviewer, browser, or QA code.

## Troubleshooting

### `website-agent: command not found`

You are probably outside the virtual environment or the package is not installed:

```bash
source .venv/bin/activate
pip install -e ".[dev]"
```

### `ModuleNotFoundError: website_agent`

Refresh the editable install:

```bash
pip install -e ".[dev]"
```

### Playwright browser is missing

Install Chromium:

```bash
playwright install chromium
```

### The run stops immediately because of budget

Increase step or cost budget:

```bash
website-agent run https://example.com --max-steps 50 --max-usd 0.50
```

For local models priced at zero, `--max-usd 0` is fine. For known paid models, use a
positive budget.

### Hosted provider returns authentication errors

Check:

```bash
echo "$WA_LLM__BASE_URL"
echo "$WA_LLM__MODEL"
```

Do not print your API key in a shared terminal. Confirm that `WA_LLM__API_KEY` is set.

### Local Ollama works on host but not in Docker

Inside Docker, use:

```text
WA_LLM__BASE_URL=http://host.docker.internal:11434/v1
```

### The agent misses an element

Check whether the element is visible, enabled, and has an accessible role/name. Adding a
stable label or `data-testid` often improves extraction and planning.

### The agent refuses to leave the starting domain

That is the default safety posture. The CLI restricts navigation to the start domain unless
you disable same-domain mode in the API or CLI path that supports it.

## Development

Run all checks:

```bash
ruff check .
ruff format --check .
mypy
pytest --cov --cov-fail-under=90
```

Run tests:

```bash
pytest
```

Run only unit tests:

```bash
pytest tests/unit
```

Run integration tests:

```bash
pytest tests/integration
```

The integration suite uses local fixture sites and does not touch the public internet.

## Evaluation Fixtures

Bundled scenarios live in [evaluation/scenarios](evaluation/scenarios), with matching
ground truth in [evaluation/ground_truth](evaluation/ground_truth).

Current fixtures:

| Fixture | Focus |
|---|---|
| `static-basic` | Navigation, console error, HTTP error, missing label |
| `forms-basic` | Form validation and accessible labels |
| `defects-basic` | Console/network defects, duplicate ids, redirect handling |
| `spa-basic` | Client-side state, modals, hash navigation |
| `maze-basic` | Cyclic navigation and dead-end detection |

Use these fixtures when changing browser extraction, planning, reviewing, QA detectors, or
reporting.

## Project Layout

```text
website-ai-agent/
  src/website_agent/
    agent/       LangGraph orchestration and runner
    api/         FastAPI application
    browser/     Playwright session, extraction, screenshots, observers
    cli/         Typer CLI
    config/      Settings and environment loading
    core/        Errors, retry, IDs, artifacts, shared types
    executor/    Deterministic browser action execution
    llm/         Provider abstraction, structured outputs, cost ledger
    logging/     Rich and JSON structured logging
    memory/      Page graph and action registry
    planner/     Candidate generation, scoring, planning
    prompts/     Prompt templates and rendering
    qa/          Deterministic QA detector pipeline
    reporting/   Markdown, JSON, CSV, graph rendering
    reviewer/    Expected-vs-observed judgement
    state/       Run state and checkpoint registry
  tests/
  evaluation/
  docs/
  examples/
  reports/
```

## Public Interfaces

The project exposes:

- CLI: `website-agent`.
- Python package: `website_agent`.
- API server: `python -m website_agent.api`.
- Docker image built from `Dockerfile`.
- Evaluation harness from a source checkout.

## Roadmap

- Semantic memory or vector recall behind the memory interface.
- Multimodal visual QA checks.
- Postgres checkpoint backend for multi-worker deployments.
- Larger load benchmarks.
- Authenticated-flow fixture recipes.
- More live-model replay cassettes for prompt regression testing.

## Known Limitations

- Accessible-name extraction is pragmatic, not a full ARIA specification implementation.
- QA detectors are deterministic and rule-based, so subtle visual bugs may be missed.
- SQLite persistence is single-worker oriented.
- Evaluation ground truth is provided for bundled fixtures; your own site needs its own
  ground-truth file for precision and recall metrics.
- Prompt quality against live models is not fully gated until real model cassettes are
  recorded and committed.

## Contributing

Contributions are welcome. Start with:

- [CONTRIBUTING.md](CONTRIBUTING.md)
- [SECURITY.md](SECURITY.md)
- [docs/architecture/overview.md](docs/architecture/overview.md)
- [docs/FINAL_AUDIT.md](docs/FINAL_AUDIT.md)

Before opening a pull request:

```bash
ruff check .
ruff format --check .
mypy
pytest --cov --cov-fail-under=90
```

## License

[MIT](LICENSE)
