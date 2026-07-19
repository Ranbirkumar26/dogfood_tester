# Repository Folder Structure

Physical layout of the repository. Layer rules from `overview.md` section 3 apply: a directory may import only from directories in the same or lower layers.

## Full tree

```
website-ai-agent/
|-- README.md                     Project front page: vision, quickstart, status
|-- LICENSE                       MIT
|-- CONTRIBUTING.md               Dev setup, style, PR process (Phase 17)
|-- SECURITY.md                   Reporting policy, scope, safety posture (Phase 17)
|-- CHANGELOG.md                  Keep-a-Changelog format
|-- pyproject.toml                Package metadata, deps, ruff/mypy/pytest config
|-- requirements.txt              Pinned lock-style export for non-pip-tools users
|-- Dockerfile                    Playwright-python base, non-root, headless (Phase 15)
|-- docker-compose.yml            Agent service plus fixture-site service (Phase 15)
|-- .env.example                  Every env var, documented, no real values
|-- .gitignore
|
|-- .github/
|   |-- workflows/
|   |   |-- ci.yml                Lint, typecheck, tests, coverage, Docker build (Phase 16)
|   |   |-- release.yml           Tag-driven package publish (Phase 16)
|   |-- ISSUE_TEMPLATE/           Bug, feature, question templates (Phase 17)
|   |-- PULL_REQUEST_TEMPLATE.md  (Phase 17)
|
|-- docs/
|   |-- architecture/             This design set (Phase 1)
|   |-- modules/                  One README per src module, added with its phase
|   |-- guides/                   User-facing how-tos (Phase 17)
|
|-- examples/                     Runnable example scripts and configs, one dir each
|
|-- tests/
|   |-- unit/                     Mirrors src/website_agent/ package tree
|   |-- integration/              Headless browser against local fixture sites
|   |-- fixtures/
|   |   |-- sites/                Static HTML fixture sites served locally
|   |   |-- cassettes/            Recorded LLM responses for replay mode (D13)
|   |-- conftest.py
|
|-- evaluation/                   Dev tooling, not shipped in the wheel (D14)
|   |-- harness/                  Runner, metric collectors, report writers
|   |-- scenarios/                YAML scenario definitions
|   |-- ground_truth/             Labeled defects per fixture site (D9)
|
|-- reports/                      Runtime output, gitignored except .gitkeep
|   |-- <run_id>/                 Screenshots, logs, snapshots, generated reports
|
|-- src/
    |-- website_agent/
        |-- __init__.py           Version, public API surface
        |-- py.typed
        |
        |-- config/               Layer 1. Settings models, layered loading, defaults
        |-- logging/              Layer 1. Structured logger, Rich + JSON sinks, redaction
        |-- core/                 Layer 1. Exception hierarchy, shared types, DI container,
        |                         retry policies, clock and ID Protocols
        |
        |-- browser/              Layer 2. BrowserManager, BrowserSession, extractors
        |                         (DOM, a11y tree), observers (console, network),
        |                         screenshots, downloads, tabs, popups, auth, storage state
        |-- tools/                Layer 2. Typed tool layer over browser/: the only API
        |                         the executor may call. Tool registry and schemas
        |-- vision/               Layer 2. Screenshot annotation and heuristic visual
        |                         checks; optional multimodal hooks, off by default
        |-- memory/               Layer 2. PageGraph (visited pages and navigation edges),
        |                         ActionRegistry (action signatures for dedupe)
        |-- state/                Layer 2. RunState models, budgets, checkpoint store
        |                         adapters, serialization, resume support
        |-- prompts/              Layer 2. PromptManager, versioned templates per role,
        |                         rendering with strict variable checking
        |-- llm/                  Layer 2. ModelManager, provider config, structured
        |                         output parsing, token ledger, price table,
        |                         rate limiting, record/replay (D3, D13)
        |-- reporting/            Layer 2. Report models, renderers (Markdown, JSON, CSV),
        |                         flow-graph builder (Mermaid/DOT), docs generator engine
        |
        |-- planner/              Layer 3. Page analysis to prioritized task queue
        |-- executor/             Layer 3. One plan step to ExecutionResult via tools/
        |-- reviewer/             Layer 3. Expected vs observed to ReviewVerdict
        |-- qa/                   Layer 3. Deterministic detector pipeline: broken links,
        |                         HTTP errors, console errors, a11y, forms, redirects,
        |                         performance; severity model (spec addition, see D14)
        |
        |-- agent/                Layer 4. LangGraph graph assembly, decide router,
        |                         AgentRunner (run lifecycle, budgets, interrupts)
        |
        |-- api/                  Layer 5. FastAPI app, routes, schemas, progress streaming
        |-- cli/                  Layer 5. Typer app: run, test, evaluate, docs, report, graph
```

## Deviations from the spec's literal tree

| Spec item | Here | Reason |
|---|---|---|
| flat `src/agent`, `src/planner`, ... | nested under `src/website_agent/` | Installable src-layout package (D14) |
| `src/logging` sibling dirs for errors/types | `core/` consolidates exceptions, types, DI, retry | These are one cohesive foundation unit; fifteen two-file dirs is worse maintenance |
| no `qa/` directory | `qa/` added | Phase 10 QA engine needs a home; folding it into `reporting/` would mix detection with rendering |
| `prompts/` | kept, holds manager plus template assets | Templates ship inside the wheel so the installed CLI works standalone |
| LLM tooling implied under `tools/` | `llm/` dedicated | `tools/` is browser tools per Phase 3/7; conflating LLM plumbing with agent tools obscures both |

`vision/` is retained from the spec with a narrow charter (screenshot annotation, heuristic visual checks, optional multimodal hook) so it does not become a junk drawer.

## Naming and placement rules

- Tests mirror the package: `tests/unit/browser/test_session.py` tests `src/website_agent/browser/session.py`.
- Every `src/website_agent/<module>/` gets `docs/modules/<module>.md` in the phase that implements it.
- Runtime output only ever lands under `reports/<run_id>/`; nothing else writes outside the repo or temp dirs.
- Module `__init__.py` files export the module's public surface; everything else is private by convention.
