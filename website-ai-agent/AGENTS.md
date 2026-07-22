# Agent Handoff Guide For `website-ai-agent`

Read this first if you are an LLM agent working inside this folder.

Full context:

- `../AGENTS.md`
- `README.md`
- `docs/architecture/overview.md`
- `docs/FINAL_AUDIT.md`
- `CLAUDE.md`

## Project

This is the main Python project for Website AI Agent.

Package:

```text
website_agent
```

CLI:

```bash
website-agent
```

Core loop:

```text
bootstrap -> planner -> executor -> reviewer -> decide -> planner/executor/finalize
```

## Non-Negotiable Architecture Rules

- The LLM never controls Playwright directly.
- The planner may only reference observed element IDs.
- The executor is the only layer that mutates browser state.
- The reviewer judges from observations, not executor claims.
- The deterministic `decide` router enforces budgets, retries, loops, and stop reasons.
- Browser observations and artifacts must not leak secrets.
- Tests must not touch the public internet.

## Commands

```bash
pip install -e ".[dev]"
playwright install chromium
ruff check .
ruff format --check .
mypy
pytest --cov --cov-fail-under=90
```

Run:

```bash
website-agent run https://example.com --max-steps 20 --max-usd 0.25
```

API:

```bash
python -m website_agent.api
```

## Vulnerability Checklist

Before changing behavior, check these risks:

- Real browser actions can mutate real sites.
- Webpage text can attempt prompt injection.
- LLMs can hallucinate actions or selectors.
- Secrets can leak through logs, prompts, reports, screenshots, or storage state.
- Cross-domain navigation can leave the authorized target.
- Missing budgets can cause loops or excessive API spend.
- Artifact APIs can become path traversal bugs if validation is loosened.
- Downloaded files must never be executed.
- SQLite persistence is not a multi-worker backend.
- Rule-based QA detectors are not a full security scanner.

Keep mitigations in place:

- `RunPolicy`
- `RiskClass`
- same-domain defaults
- element-ID-only actions
- redaction
- strict artifact path validation
- deterministic budget router
- local fixture tests

## Main Folders

```text
src/website_agent/agent/       LangGraph graph and runner
src/website_agent/browser/     Playwright facade and observations
src/website_agent/planner/     Candidate generation and planning
src/website_agent/executor/    Browser action dispatch
src/website_agent/reviewer/    Expected-vs-observed review
src/website_agent/qa/          Deterministic QA detectors
src/website_agent/reporting/   Report renderers
src/website_agent/api/         FastAPI server
src/website_agent/cli/         Typer CLI
evaluation/                    Scenario scoring and ground truth
tests/                         Unit and integration tests
docs/                          Architecture and module docs
```

## Current Verified State

- 399 tests passing.
- 97.31 percent coverage.
- `ruff check` clean.
- `ruff format --check` clean.
- `mypy --strict` clean.

