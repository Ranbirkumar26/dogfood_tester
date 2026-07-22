# Agent Handoff Guide

This file is for future LLM agents working on this repository.

Public repo: https://github.com/Ranbirkumar26/dogfood_tester

Main project folder:

```text
website-ai-agent/
```

Start with these files:

1. `README.md` at the repository root for top-level usage.
2. `website-ai-agent/README.md` for the full user guide.
3. `website-ai-agent/docs/architecture/overview.md` for binding design decisions.
4. `website-ai-agent/docs/FINAL_AUDIT.md` for current engineering status.
5. `website-ai-agent/CLAUDE.md` for build history and local process notes.

## Project Summary

Website AI Agent is an autonomous website QA agent. It uses Python, LangGraph, Playwright,
Pydantic, FastAPI, Typer, Rich, Pytest, Docker, and GitHub Actions.

The agent opens a real Chromium browser, explores a site, plans actions with an LLM,
executes actions through typed browser tools, reviews observed results, detects defects,
and writes reports.

The Python package is:

```text
website_agent
```

The CLI command is:

```bash
website-agent
```

## Architecture In One Screen

Core loop:

```text
bootstrap -> planner -> executor -> reviewer -> decide -> planner/executor/finalize
```

Layering:

```text
Interfaces:     cli/, api/
Orchestration:  agent/
Roles:          planner/, executor/, reviewer/, qa/
Capabilities:   browser/, memory/, state/, prompts/, reporting/
Foundation:     config/, logging/, core/
```

Important invariant:

The LLM must not invent raw browser selectors. It can only reference element IDs extracted
from the current page inventory. The executor resolves those IDs to live Playwright
locators and rejects missing elements.

## Commands

Run from:

```bash
cd /Users/tarry/Desktop/dogfood_tester/website-ai-agent
```

Install:

```bash
pip install -e ".[dev]"
playwright install chromium
```

Quality gate:

```bash
ruff check .
ruff format --check .
mypy
pytest --cov --cov-fail-under=90
```

Current verified state:

- 399 tests passing.
- 97.31 percent coverage.
- Ruff clean.
- Strict mypy clean.

## Runtime Configuration

Environment prefix:

```text
WA_
```

Common settings:

```text
WA_LLM__BASE_URL
WA_LLM__API_KEY
WA_LLM__MODEL
WA_BUDGETS__MAX_STEPS
WA_BUDGETS__MAX_USD
WA_PATHS__REPORTS_DIR
```

Never commit real secrets or `.env`.

## Vulnerability And Risk Map

Treat this project as a real browser automation tool with real side effects.

### Real Browser Side Effects

Risk:

The agent can click UI, fill forms, trigger requests, download files, and navigate real
sites.

Controls:

- Default policy is safe-explore.
- Destructive-looking actions are risk-classified and blocked by default.
- Use only authorized sites, local fixtures, or staging.
- Keep step and cost budgets small on first runs.

Do not weaken `RunPolicy`, `RiskClass`, candidate filtering, or budget checks without
updating tests and docs.

### Prompt Injection From Web Pages

Risk:

The page under test can contain text that tries to manipulate the LLM.

Controls:

- The model sees compact inventories and structured prompts, not unconstrained browser
  control.
- The model references observed element IDs, not raw selectors.
- The deterministic executor rejects nonexistent element IDs.
- The reviewer checks reality from browser observations.

Do not let the model call Playwright directly.

### Selector Hallucination

Risk:

LLMs often invent CSS selectors or click targets.

Controls:

- Element IDs are generated from actual browser extraction.
- `BrowserSession` resolves IDs against the current snapshot.
- Missing elements become structured failures and route to replan/retry.

Do not add a planner path that accepts arbitrary selectors from the model.

### Secret Leakage

Risk:

Credentials, API keys, cookies, or user-entered values can leak into logs, prompts, reports,
or artifacts.

Controls:

- Secrets come from environment or storage state, not prompts.
- Logging has redaction.
- Reports and artifacts should not persist credential values.
- `.env` is ignored.

When adding new logs or artifacts, check that secret values are not written.

### Cross-Domain Navigation

Risk:

An autonomous browser could wander away from the intended site.

Controls:

- CLI defaults to same-domain navigation.
- Planner policy filters off-allowlist target URLs.

Do not loosen domain filtering casually.

### Cost And Infinite Loops

Risk:

Autonomous agents can loop or spend unbounded model tokens.

Controls:

- Budgets are first-class state: steps, tokens, USD, wall-clock, consecutive failures.
- The `decide` router is deterministic and LLM-free.
- Loop detection and branch poisoning exist in `agent/loop_detector.py`.

Do not move budget enforcement into the LLM.

### Artifact And API Path Traversal

Risk:

Report downloads and artifact paths could expose local files if path validation is weakened.

Controls:

- API validates run IDs and artifact names.
- `ArtifactRef` rejects absolute paths and `..`.

Keep path validation strict.

### Download Handling

Risk:

Websites can trigger downloads.

Controls:

- Downloads are saved as artifacts.
- Downloads are not executed.
- Filenames are sanitized.

Do not auto-open or execute downloaded files.

### Persistence And Scaling

Risk:

SQLite checkpointing is not a multi-worker production backend.

Current limitation:

- Single-worker operation is intentional.
- Postgres checkpoint backend is future work.

Do not advertise horizontal scaling until that backend exists.

### Evaluation Limitations

Risk:

Rule-based QA detectors do not catch every visual, semantic, security, or performance issue.

Current limitation:

- Vision checks are heuristic and off by default.
- Accessible-name extraction is pragmatic, not a full ARIA implementation.
- Live-model prompt regression cassettes are not committed yet.

Keep claims honest in README and docs.

## Where To Make Changes

Common tasks:

| Task | Start Here |
|---|---|
| CLI behavior | `website-ai-agent/src/website_agent/cli/main.py` |
| API behavior | `website-ai-agent/src/website_agent/api/` |
| Browser actions | `website-ai-agent/src/website_agent/browser/session.py` |
| Page extraction | `website-ai-agent/src/website_agent/browser/extraction.py` |
| Planning | `website-ai-agent/src/website_agent/planner/` |
| Execution | `website-ai-agent/src/website_agent/executor/` |
| Review logic | `website-ai-agent/src/website_agent/reviewer/` |
| QA findings | `website-ai-agent/src/website_agent/qa/` |
| Reports | `website-ai-agent/src/website_agent/reporting/` |
| State and resume | `website-ai-agent/src/website_agent/state/`, `agent/runner.py` |
| Evaluation | `website-ai-agent/evaluation/` |
| Architecture docs | `website-ai-agent/docs/architecture/` |

## Test Rules

- No test should touch the public internet.
- Integration tests use local fixture servers.
- Unit tests fake seams instead of patching internals.
- Add tests for every detector, router, state, prompt, API, or browser contract change.
- Keep `pytest --cov --cov-fail-under=90` green.

## Current Local Note

`website-ai-agent/scripts/make_task_excel.py` is an optional task-tracking helper. It is not
part of the package runtime.

