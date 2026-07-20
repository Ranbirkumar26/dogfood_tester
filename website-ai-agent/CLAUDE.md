# website-ai-agent project notes

Read `docs/architecture/overview.md` first. Decisions D1..D14 there are binding; this file tracks process state, decisions made outside the architecture docs, and deferred features.

## Build process

18-phase spec from the project owner, strict order, approval gate after every phase. Each phase ends with the audit block: deliverables, files, remaining work, manual test checklist, automated test results, architecture validation, production readiness score. Never start phase N+1 without explicit approval of phase N.

Phase status: 1-7 done (architecture; foundation; browser; LLM; state+memory; planner: deterministic candidate-generate/dedupe/policy-filter, hybrid LLM+structural scoring, reproducible re-rank, ships planner.md prompt; executor: LLM-free deterministic dispatch to tool layer, classifies failures without raising, captures screenshot+observations, records to memory). 263 tests, 96 percent coverage, ruff plus mypy strict clean. Committing and pushing to GitHub after each phase (standing order). Next: Phase 8 (reviewer).

Dev commands: `.venv/bin/python -m pytest --cov`, `.venv/bin/ruff check .`, `.venv/bin/ruff format .`, `.venv/bin/mypy`. Python 3.13 venv at `.venv/`.

## Decision log

- 2026-07-19: Provider-agnostic LLM layer with OpenAI as documented default; any OpenAI-compatible endpoint (Ollama, Groq, OpenRouter, vLLM) supported. Owner decision via plan review. Free-tier-first constraint: dev and CI must run at zero API cost (replay cassettes plus local models).
- 2026-07-19: Package layout deviates from spec's flat src/ tree: installable src-layout `src/website_agent/`, `core/` consolidation, `llm/` and `qa/` additions. Rationale in overview.md D14 and folder-structure.md deviations table.
- 2026-07-20: LangChain proper not a dependency; LangGraph only (overview.md D4). Revisit only with a concrete component need.
- 2026-07-20: Memory is graph plus signature registry, deliberately not a vector store (data-flow.md s4).
- 2026-07-20: `bootstrap` and `finalize` nodes added around the spec's planner/executor/reviewer/decision loop (state-machine.md).
- 2026-07-20: Prompt templates use `$var` (string.Template); `PromptManager.render(name, variables_dict)` takes a mapping not kwargs, so a template variable may be named `name`. Strict rendering: missing and unused variables both raise ConfigError.
- 2026-07-20: Structured LLM output does not depend on provider-side schema enforcement (varies across OpenAI-compatible servers): schema in prompt + json_object mode + validate + one repair reprompt. Cassette keys hash role/model/messages/schema so drift fails loudly.
- 2026-07-20: pytest uses `--import-mode=importlib` + `pythonpath=["."]` so same-basename test modules coexist and shared test helpers import as `tests.unit.<pkg>._fakes`. Editable install `.pth` goes stale after dependency changes; `.venv/bin/pip install -e ".[dev]"` fixes ModuleNotFoundError: website_agent.

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
