# Website AI Agent

Autonomous website exploration and QA agent. Point it at a URL; it operates a real browser to explore pages, click and fill its way through workflows, watch the console and network, detect functional bugs and accessibility issues, and produce QA reports, user-flow graphs, and generated documentation.

Built on Python, LangGraph, and Playwright, with a provider-agnostic LLM layer (OpenAI-compatible: OpenAI, Ollama, Groq, OpenRouter, vLLM). Local models make development and CI free; paid APIs are opt-in.

## Status

Pre-release. Architecture phase complete; implementation in progress.

| Phase | Scope | Status |
|---|---|---|
| 1 | Architecture and design | Done |
| 2 | Foundation (config, logging, errors, DI) | Done |
| 3 | Browser tooling | Done |
| 4 | LLM tooling | Done |
| 5 | State management | Done |
| 6 | Planner | Done |
| 7 | Executor | Done |
| 8 | Reviewer | Done |
| 9 | LangGraph orchestration | Done |
| 10 | QA engine | Done |
| 11 | Documentation engine | Done |
| 12 | Evaluation harness | Done |
| 13 | CLI | Done |
| 14 | FastAPI server | Done |
| 15 | Docker | Done |
| 16 | CI/CD | Pending |
| 17 | Open source preparation | Pending |
| 18 | Final audit | Pending |

## Design

The complete architecture lives in [`docs/architecture/`](docs/architecture/), starting with the [overview](docs/architecture/overview.md). Core shape:

```
bootstrap -> planner -> executor -> reviewer -> decide -> (loop | finalize)
```

A LangGraph state machine with durable checkpoints drives a plan-execute-review loop over a wrapped Playwright session. Element addressing uses the accessibility tree with synthesized stable selectors; the model can only act on elements that actually exist. Budgets (steps, tokens, dollars, wall-clock) are enforced by a deterministic router, and every run is resumable from its last checkpoint.

## Quickstart

```bash
pip install -e ".[dev]"
playwright install chromium
website-agent run https://example.com --max-steps 40   # reports land in reports/<run_id>/output/
website-agent graph                                     # print the agent's state machine
```

Point `WA_LLM__BASE_URL` at a local model (Ollama, vLLM) for zero-cost runs, or set `WA_LLM__API_KEY` for a hosted provider. Docker usage: [`docs/guides/docker.md`](docs/guides/docker.md).

## Safety posture

Domain-allowlisted navigation, a destructive-action policy (safe-explore by default), secret redaction in all logs and reports, and no CAPTCHA or bot-detection circumvention. Intended targets: your own sites, staging environments, and the bundled fixture sites.

## License

MIT (LICENSE file lands in Phase 17 packaging pass).
