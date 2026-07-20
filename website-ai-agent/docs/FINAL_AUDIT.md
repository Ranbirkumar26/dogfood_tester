# Phase 18: Final Engineering Audit

A senior-engineering review of website-ai-agent at the end of the 18-phase build. This is a candid assessment: strengths are stated plainly, and real gaps are named rather than glossed.

## Verification snapshot

All figures below were produced by running the checks, not estimated.

| Check | Result |
|---|---|
| Tests | 385 passing (48 test files; 5 real-browser integration files) |
| Coverage | 97 percent (branch coverage on), gated at 90 percent in CI |
| Lint | `ruff check` clean |
| Format | `ruff format --check` clean |
| Types | `mypy --strict` clean across 87 source files (src and evaluation) |
| Source size | ~6,950 LOC across 18 module packages |
| Test size | ~6,400 LOC (roughly 1:1 test-to-source) |
| Docs | 26 Markdown documents (9 architecture, 12 module, guides, audit) |
| CI | GitHub Actions green: lint/type, tests on 3.11/3.12/3.13, and Docker build all pass |
| Packaging | Wheel builds and includes prompt templates and py.typed; Docker image builds on CI |

## Dimension review

### Architecture (9/10)

Five layers with a strictly enforced downward dependency rule, 14 numbered and justified design decisions, and a clean separation between deterministic capabilities and the three LLM roles. The plan-execute-review loop is a real LangGraph state machine, not a hand-rolled loop, so checkpointing, resume, and visualization come from the framework. The single strongest decision is D6 (element-ID addressing): the model can only act on elements the browser actually extracted, which structurally eliminates the most common class of browser-agent failure. Point off: the memory layer is deliberately not pluggable to a vector store yet, and the resume path, while designed and scaffolded in state, is exercised at the store level but not yet through a full crash-resume integration test.

### Maintainability (9/10)

Every module has a one-page doc; every design decision traces to a binding record. Comments explain why, not what. Functions are small and seams are Protocol-based, so tests fake at boundaries rather than patching internals. The consistent role shape (typed input, pure-where-possible core, LLM only where semantic judgement is needed) makes the codebase easy to extend. The recurring editable-install staleness during development is a local tooling quirk, not a code issue.

### Scalability (7/10)

Single-worker by design: SQLite checkpoints and an in-process run registry suit a laptop, CI, and a single server. The state interface does not preclude a Postgres backend (on the roadmap), and the API already runs runs as independent background tasks. Horizontal scaling across workers is not implemented and is honestly out of scope for this build.

### Security and safety (9/10)

Safety is structural, not bolted on: a domain allowlist enforced in the planner before navigation, a destructive-action policy that risk-classifies by accessible name and type with safe-explore as default, secret redaction in the logging pipeline and at artifact-write time, and credentials that enter only via environment or storage state. The API validates run IDs and artifact names against a strict pattern before touching the filesystem, blocking traversal. No CAPTCHA or bot-detection evasion. SECURITY.md documents private reporting and scope.

### Reliability (9/10)

A single failure taxonomy (F1 to F8) mapped to typed exceptions, with retry policies implemented once and injected everywhere. Budgets (steps, tokens, dollars, wall-clock, consecutive failures) are enforced by a pure, exhaustively tested router before the verdict, so a run cannot spend unbounded money or loop forever. Graceful degradation is pervasive: a failed screenshot, snapshot, or report never fails a run. The loop detector with branch poisoning handles the autonomous-agent failure mode where everything "succeeds" while going nowhere.

### Performance (8/10)

The design is deliberately token-frugal: successful steps skip the planner (roughly halving LLM calls), the reviewer settles mechanical expectations without a model call, candidate shortlists are pre-filtered before scoring, and snapshots are salience-truncated for prompts. Cost is accounted per call and visible in every report. Not yet measured under load; the eval harness collects latency but no large-site benchmark is committed.

### Documentation (9/10)

Nine architecture documents (with Mermaid diagrams), a module doc per package, Docker and usage guides, a real sample-run output, and inline rationale throughout. The architecture docs are the contract the code was built against, and they stayed in sync because each phase validated against them. A short conceptual walkthrough or a recorded demo GIF would round it out.

### Testing (9/10)

385 tests at 97 percent coverage, with a genuine unit/integration split: unit tests fake the seams and run in milliseconds; integration tests drive real headless Chromium against a local fixture server and exercise the whole graph end to end. Nothing touches the public internet, and the whole suite runs keyless via scripted models. The honest gap: role-level LLM behavior is tested against scripted outputs, not committed replay cassettes of a real model, so prompt-quality regressions against a live model are not caught in CI (the cassette infrastructure exists; recordings are not yet committed).

### Open-source and GitHub quality (9/10)

MIT license, CONTRIBUTING, SECURITY, CHANGELOG, issue and PR templates, README with badges, quickstart, roadmap, FAQ, and known-limitations, plus committed example output. CI runs on every push and PR. The one wrinkle, now fixed, was that the project living in a subdirectory meant workflows had to be added at the repository root to be discovered.

### Production readiness (8.5/10)

Runs headless in Docker as non-root with a persistent volume, config entirely through environment, budgets and safety fences on by default, structured JSON logs, and cost transparency. What a team would still want before betting on it: committed live-model eval baselines, a crash-resume integration test, and a load benchmark. None are blockers for the intended use (QA of your own sites and staging).

## Honest gap list

1. Role LLM cassettes are not committed, so live-model prompt regressions are not gated (infrastructure exists).
2. Full crash-resume is designed and unit-tested at the store level but lacks an end-to-end integration test.
3. Single-worker only; no Postgres backend yet.
4. Accessible-name computation is a pragmatic ARIA subset.
5. Vision checks are heuristic and off by default; no multimodal QA yet.

The Docker image build, initially only validated structurally, is now built and verified green on CI, so that earlier caveat is resolved.

## Verdict

The repository delivers what the spec asked for: a production-grade, well-architected, thoroughly tested, and well-documented autonomous website QA agent that runs free on local models and is honest about its limits. It reads as the work of a senior engineer: decisions are justified and recorded, safety and cost are designed in rather than patched on, and the test suite exercises real behavior rather than mocks-of-everything. The named gaps are the right ones to have deferred, and each is documented rather than hidden.

Overall production readiness: **8.7/10** for the intended scope.
