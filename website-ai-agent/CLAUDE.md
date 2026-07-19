# website-ai-agent project notes

Read `docs/architecture/overview.md` first. Decisions D1..D14 there are binding; this file tracks process state, decisions made outside the architecture docs, and deferred features.

## Build process

18-phase spec from the project owner, strict order, approval gate after every phase. Each phase ends with the audit block: deliverables, files, remaining work, manual test checklist, automated test results, architecture validation, production readiness score. Never start phase N+1 without explicit approval of phase N.

Phase status: 1-3 done (architecture; foundation; browser tooling with real-chromium integration tests against tests/fixtures/sites/static-basic). 137 tests, 95 percent coverage, ruff plus mypy strict clean. Next: Phase 4 (LLM tooling) awaiting approval.

Dev commands: `.venv/bin/python -m pytest --cov`, `.venv/bin/ruff check .`, `.venv/bin/ruff format .`, `.venv/bin/mypy`. Python 3.13 venv at `.venv/`.

## Decision log

- 2026-07-19: Provider-agnostic LLM layer with OpenAI as documented default; any OpenAI-compatible endpoint (Ollama, Groq, OpenRouter, vLLM) supported. Owner decision via plan review. Free-tier-first constraint: dev and CI must run at zero API cost (replay cassettes plus local models).
- 2026-07-19: Package layout deviates from spec's flat src/ tree: installable src-layout `src/website_agent/`, `core/` consolidation, `llm/` and `qa/` additions. Rationale in overview.md D14 and folder-structure.md deviations table.
- 2026-07-20: LangChain proper not a dependency; LangGraph only (overview.md D4). Revisit only with a concrete component need.
- 2026-07-20: Memory is graph plus signature registry, deliberately not a vector store (data-flow.md s4).
- 2026-07-20: `bootstrap` and `finalize` nodes added around the spec's planner/executor/reviewer/decision loop (state-machine.md).

## Deferred features (owner's words to be captured when deferred; none yet)

- Semantic memory / vector recall behind the memory interface, only if Phase 6+ shows exact-match dedupe is insufficient (self-deferred, architectural).
- Multimodal vision checks default-on (kept off by default for cost; hooks live in `vision/`).
- Postgres checkpoint backend (SQLite chosen; interface will not preclude it).
- LLM-assisted triage of unmatched eval findings (never in gating path).

## Conventions

- No emojis, no em dashes anywhere in repo text. Professional tone.
- Secrets only via environment / .env (gitignored); redaction at write time for logs and artifacts.
- Every module ships with `docs/modules/<module>.md` in its implementation phase.
- Tests mirror package tree; no test touches the public internet.
