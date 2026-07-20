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
| 5 | State management | Pending |
| 6 | Planner | Pending |
| 7 | Executor | Pending |
| 8 | Reviewer | Pending |
| 9 | LangGraph orchestration | Pending |
| 10 | QA engine | Pending |
| 11 | Documentation engine | Pending |
| 12 | Evaluation harness | Pending |
| 13 | CLI | Pending |
| 14 | FastAPI server | Pending |
| 15 | Docker | Pending |
| 16 | CI/CD | Pending |
| 17 | Open source preparation | Pending |
| 18 | Final audit | Pending |

## Design

The complete architecture lives in [`docs/architecture/`](docs/architecture/), starting with the [overview](docs/architecture/overview.md). Core shape:

```
bootstrap -> planner -> executor -> reviewer -> decide -> (loop | finalize)
```

A LangGraph state machine with durable checkpoints drives a plan-execute-review loop over a wrapped Playwright session. Element addressing uses the accessibility tree with synthesized stable selectors; the model can only act on elements that actually exist. Budgets (steps, tokens, dollars, wall-clock) are enforced by a deterministic router, and every run is resumable from its last checkpoint.

## Safety posture

Domain-allowlisted navigation, a destructive-action policy (safe-explore by default), secret redaction in all logs and reports, and no CAPTCHA or bot-detection circumvention. Intended targets: your own sites, staging environments, and the bundled fixture sites.

## License

MIT (LICENSE file lands in Phase 17 packaging pass).
