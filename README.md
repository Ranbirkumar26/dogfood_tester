# Website AI Agent

Public repository: [Ranbirkumar26/dogfood_tester](https://github.com/Ranbirkumar26/dogfood_tester)

This repository contains a production-grade autonomous Website AI Agent in the
[`website-ai-agent/`](website-ai-agent/) folder.

The agent opens a real Chromium browser, explores websites, plans and executes safe UI
actions, watches console and network activity, detects QA and accessibility issues, captures
screenshots, and writes reports that humans and machines can read.

For the full long-form guide, see:

- [website-ai-agent/README.md](website-ai-agent/README.md)
- [website-ai-agent/docs/FINAL_AUDIT.md](website-ai-agent/docs/FINAL_AUDIT.md)
- [website-ai-agent/docs/architecture/overview.md](website-ai-agent/docs/architecture/overview.md)

## What This Agent Can Do

- Explore a website with Playwright and Chromium.
- Understand visible interactive elements from DOM and accessibility snapshots.
- Use an LLM to plan safe next actions.
- Click buttons and links.
- Fill forms and select options.
- Navigate multi-page workflows.
- Detect console errors and failed network requests.
- Detect broken links, HTTP errors, dead clicks, duplicate ids, missing labels, missing
  validation, unexpected redirects, slow requests, and dead navigation.
- Capture screenshots.
- Build user-flow graphs.
- Generate QA reports, JSON exports, CSV exports, and generated documentation.
- Resume interrupted runs from durable checkpoints.
- Run through a CLI, FastAPI server, Docker, or the Python package.

## Repository Layout

```text
dogfood_tester/
  README.md                    This top-level guide
  website-ai-agent/            Main project
    README.md                  Full detailed user guide
    src/website_agent/         Python package
    tests/                     Unit and integration tests
    evaluation/                Evaluation scenarios and ground truth
    docs/                      Architecture and module docs
    examples/                  Example outputs
    reports/                   Runtime output directory
```

The installable Python package is named `website_agent`.

The CLI command is:

```bash
website-agent
```

## Installation From Scratch

### 1. Clone The Repository

```bash
git clone https://github.com/Ranbirkumar26/dogfood_tester.git
cd dogfood_tester/website-ai-agent
```

### 2. Create A Virtual Environment

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

### 3. Install Dependencies

```bash
pip install -e ".[dev]"
playwright install chromium
```

### 4. Verify The CLI

```bash
website-agent --help
website-agent graph
```

`website-agent graph` does not need an API key. It prints the LangGraph state machine.

## Installing As A System Command

If you want `website-agent` available globally on your machine, install it with `pipx`:

```bash
pipx install /path/to/dogfood_tester/website-ai-agent
```

Then call it from anywhere:

```bash
website-agent --help
```

On this machine it has already been installed as:

```text
/Users/tarry/.local/bin/website-agent
```

## Configure An LLM

The agent needs an OpenAI-compatible chat completions API for planning and semantic review.

You can use:

- OpenAI
- Ollama
- vLLM
- LM Studio
- OpenRouter
- Groq
- Any compatible provider

### OpenAI

```bash
export WA_LLM__BASE_URL="https://api.openai.com/v1"
export WA_LLM__API_KEY="your_api_key_here"
export WA_LLM__MODEL="gpt-4o-mini"
```

### Local Ollama

```bash
export WA_LLM__BASE_URL="http://localhost:11434/v1"
export WA_LLM__API_KEY="not-needed"
export WA_LLM__MODEL="your-local-model"
```

### `.env` File

You can also create a `.env` file:

```bash
cd website-ai-agent
cp .env.example .env
```

Then edit `.env` with your provider settings.

## First Safe Run

Start with a local fixture site:

```bash
cd website-ai-agent
python -m http.server 8008 --directory tests/fixtures/sites/static-basic
```

In another terminal:

```bash
cd dogfood_tester/website-ai-agent
source .venv/bin/activate
website-agent run http://127.0.0.1:8008/index.html --max-steps 20 --max-usd 0
```

For a real site you own:

```bash
website-agent run https://your-staging-site.com --max-steps 40 --max-usd 0.25
```

Reports are written under:

```text
reports/<run_id>/output/
```

## Main CLI Commands

General exploration and QA:

```bash
website-agent run https://example.com --max-steps 40 --max-usd 0.25
```

Form and validation-focused testing:

```bash
website-agent test https://example.com --max-steps 50 --max-usd 0.50
```

Documentation-focused exploration:

```bash
website-agent docs https://example.com --max-steps 60
```

List previous runs:

```bash
website-agent list
```

Print a QA report:

```bash
website-agent report <run_id>
```

Print a findings summary:

```bash
website-agent summary <run_id>
```

Resume an interrupted run:

```bash
website-agent resume <run_id>
```

Print the graph:

```bash
website-agent graph
```

## Reports

Each run writes artifacts to:

```text
website-ai-agent/reports/<run_id>/
```

Important files:

| File | Purpose |
|---|---|
| `output/qa_report.md` | Human-readable QA report |
| `output/report.json` | Machine-readable full report |
| `output/findings.csv` | Spreadsheet-friendly findings |
| `output/flow_graph.mmd` | Mermaid user-flow graph |
| `qa/findings.json` | Raw QA findings |
| `screenshots/` | Captured screenshots |
| `state/storage_state.json` | Browser storage state |

Common finding kinds:

| Finding | Meaning |
|---|---|
| `console_error` | JavaScript console error |
| `http_error` | Failed request or HTTP status 400 and above |
| `dead_action` | Click had no observable effect |
| `missing_label` | Form control lacks an accessible name |
| `duplicate_id` | Duplicate DOM id |
| `dead_navigation` | Page exposes no interactive elements |
| `unexpected_redirect` | Navigation ended at the wrong URL |
| `missing_validation` | Invalid input was accepted without expected validation |
| `slow_request` | Request crossed the slow-request threshold |

## API Server

Start the FastAPI server:

```bash
cd website-ai-agent
python -m website_agent.api
```

Open Swagger UI:

```text
http://127.0.0.1:8000/docs
```

Start a run:

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

Fetch report:

```bash
curl http://127.0.0.1:8000/runs/<run_id>/report
```

## Docker

Build the image:

```bash
cd website-ai-agent
docker build -t website-ai-agent .
```

Run the CLI:

```bash
docker run --rm --env-file .env -v wa_reports:/data/reports \
  website-ai-agent run https://example.com --max-steps 40
```

Run the API:

```bash
docker compose up api
```

For Ollama running on the host machine from Docker, use:

```text
WA_LLM__BASE_URL=http://host.docker.internal:11434/v1
```

## Evaluation Harness

Bundled fixtures:

| Fixture | Focus |
|---|---|
| `static-basic` | Navigation, console error, HTTP error, missing label |
| `forms-basic` | Form validation and accessible labels |
| `defects-basic` | Console/network defects, duplicate ids, redirects |
| `spa-basic` | Client-side state, modals, hash navigation |
| `maze-basic` | Cyclic navigation and dead-end detection |

Example:

```bash
cd website-ai-agent
python -m http.server 8008 --directory tests/fixtures/sites/static-basic

website-agent evaluate http://127.0.0.1:8008/index.html \
  --scenario evaluation/scenarios/explore-static-basic.yaml \
  --ground-truth evaluation/ground_truth/static-basic.yaml \
  --out reports/eval/static-basic
```

## Safety Rules

This agent controls a real browser. Use it responsibly.

- Run it only on sites you own or have permission to test.
- Start with staging, local, or fixture sites.
- Use small `--max-steps` and `--max-usd` budgets first.
- Do not use real payment, deletion, or irreversible workflows.
- Keep API keys in environment variables or `.env`.
- Review reports before creating bug tickets.
- Keep same-domain restrictions enabled unless you know why you need otherwise.

The default policy is safe-explore and avoids destructive-looking actions.

## Troubleshooting

### `website-agent: command not found`

Install the package or activate the virtual environment:

```bash
cd website-ai-agent
source .venv/bin/activate
pip install -e ".[dev]"
```

### `ModuleNotFoundError: website_agent`

Refresh the editable install:

```bash
cd website-ai-agent
pip install -e ".[dev]"
```

### Browser missing

```bash
playwright install chromium
```

### Provider authentication failed

Check:

```bash
echo "$WA_LLM__BASE_URL"
echo "$WA_LLM__MODEL"
```

Confirm `WA_LLM__API_KEY` is set, but do not print it in a shared terminal.

### Local model works outside Docker but not inside Docker

Use:

```text
WA_LLM__BASE_URL=http://host.docker.internal:11434/v1
```

## Development Checks

```bash
cd website-ai-agent
ruff check .
ruff format --check .
mypy
pytest --cov --cov-fail-under=90
```

Current verified state:

- 399 tests passing.
- 97.31 percent coverage.
- Strict mypy clean.
- Ruff clean.

## License

[MIT](website-ai-agent/LICENSE)
