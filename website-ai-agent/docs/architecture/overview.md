# System Architecture Overview

Status: Implemented architecture, kept as the binding design contract
Audience: contributors and reviewers. Every structural decision in this codebase traces back to a numbered decision (D1..D14) in this document.

## 1. What this system is

An autonomous website agent that, given a starting URL and a goal (explore, test, document), operates a real browser to:

- crawl and understand page structure,
- plan and execute interactions (click, type, navigate, submit),
- observe consequences (DOM changes, console errors, network failures, screenshots),
- detect functional bugs and accessibility issues,
- and emit machine-readable and human-readable outputs: QA reports, user-flow graphs, and generated documentation.

It is a closed-loop agent, not a script runner: it decides what to do next based on what it has seen.

## 2. Non-goals

- Not a load-testing or security-scanning tool (no fuzzing, no auth brute force).
- Not a pixel-perfect visual regression tool (visual checks are heuristic, in `vision/`).
- No mass crawling of third-party sites. Domain scoping is enforced (D12).
- No CAPTCHA bypass or bot-detection evasion. If a site blocks automation, the agent reports it and stops.

## 3. High-level architecture

Five layers, strict downward dependencies. Nothing in a lower layer imports from a higher one.

```
Layer 5  Interfaces      cli/  api/
Layer 4  Orchestration   agent/  (LangGraph graph, run lifecycle)
Layer 3  Roles           planner/  executor/  reviewer/  qa/
Layer 2  Capabilities    browser/  tools/  vision/  memory/  state/  prompts/  reporting/
Layer 1  Foundation      config/  logging/  errors, types, DI
```

- **Foundation** owns configuration, structured logging, the exception hierarchy, shared type definitions, and a minimal dependency injection container.
- **Capabilities** are deterministic, LLM-free services: browser control, observation capture, persistence, prompt templating, report rendering. Everything here is unit-testable without a model.
- **Roles** are the three LLM-driven actors plus the deterministic QA engine. Each role has one job and a typed input/output contract.
- **Orchestration** wires roles into a LangGraph state machine with checkpointing, interrupts, and budget enforcement.
- **Interfaces** are thin adapters (Typer CLI, FastAPI server) over one shared `AgentRunner` service. No business logic lives in an interface.

See `components.md` for the component diagram and `folder-structure.md` for the physical layout.

## 4. The core loop

```
bootstrap -> planner -> executor -> reviewer -> decide -+-> planner   (continue / replan)
                ^                                       +-> executor  (retry)
                |                                       +-> finalize  (done / budget / stopped)
                +---------------------------------------+
```

- **Planner** turns the current page snapshot plus memory into a prioritized task queue.
- **Executor** performs exactly one plan step via typed browser tools and returns an `ExecutionResult` with observations.
- **Reviewer** compares expected outcome against observed outcome and issues a `ReviewVerdict` (success, retry, replan, stop) with reasons.
- **decide** is a deterministic router (no LLM) that maps verdict plus budgets plus loop detection onto the next edge.

Full node and edge semantics: `state-machine.md`. Timing and message detail: `sequences.md`.

## 5. Design decisions

Each decision lists the choice, the reason, and the rejected alternative. These are binding for implementation phases; changing one requires updating this document.

### D1. LangGraph for orchestration

**Choice**: The control loop is a LangGraph `StateGraph` with a persistent checkpointer.
**Why**: The problem is literally a stateful graph with conditional edges, interrupts, and resume-from-checkpoint. LangGraph provides durable execution, per-thread state, `interrupt`/`Command` semantics, and graph visualization out of the box. Hand-rolling this (a while-loop with a state dict) rebuilds the hard parts (checkpointing, resumability, replay) with none of the ecosystem benefit.
**Rejected**: plain asyncio loop (no durable state), CrewAI/AutoGen (opinionated multi-agent chat abstractions, wrong shape for a tight plan-execute-review loop).

### D2. Plan-Execute-Review as three separate roles

**Choice**: Three LLM roles with disjoint responsibilities and separate prompts, never merged into one "do everything" agent call.
**Why**: (a) Hallucination containment: the reviewer only trusts observations, not the executor's claims, so a failed click cannot silently become "success". (b) Each role gets a small, focused context window slice, which cuts tokens and improves output quality. (c) Roles are independently promptable, testable, and evaluatable (the eval harness scores planner and reviewer separately).
**Rejected**: single ReAct agent (cheaper per step but unauditable, loop-prone, and untestable in isolation).

### D3. Provider-agnostic LLM layer, OpenAI-compatible protocol

**Choice**: One thin `ModelManager` over the `openai` Python SDK with a configurable `base_url`. Default configuration targets OpenAI; the same code path serves Ollama, Groq, OpenRouter, vLLM, LM Studio, or any OpenAI-compatible endpoint.
**Why**: The OpenAI wire protocol is the de-facto standard; one dependency covers every provider users realistically run, including free local models for development and CI. Cost control is a project constraint: contributors must be able to develop and run the eval smoke suite at zero API cost.
**Rejected**: LiteLLM (large dependency surface for a protocol we need one dialect of), LangChain chat model classes (adds an abstraction layer we would immediately wrap anyway; LangGraph does not require them).

### D4. LangChain usage is minimal and justified per-import

**Choice**: LangGraph is a core dependency. LangChain proper is not, unless a concrete phase demonstrates a component that would otherwise be rebuilt (none currently identified).
**Why**: The spec says "LangChain only where beneficial". Our model layer (D3), prompt manager, and parsers are deliberately owned in-repo because they are small, load-bearing, and must support token accounting and replay (D13).

### D5. Async Playwright, single wrapped session abstraction

**Choice**: Playwright's async API behind a `BrowserSession` facade owning: one browser context, page lifecycle, console and network capture, screenshot store, downloads, popups, storage state.
**Why**: LangGraph nodes are async; console/network observers are push-based and need a running event loop; Playwright auto-waiting removes a whole class of flaky interactions. A single facade means roles and tools never touch Playwright types directly, which keeps the browser layer swappable and mockable in tests.
**Rejected**: Selenium (weaker auto-wait, no first-class network capture), sync Playwright (blocks the graph), raw CDP (reimplements Playwright).

### D6. Element addressing by accessibility tree plus synthesized stable selectors

**Choice**: Each observed page yields a `PageSnapshot` containing a compact interactive-element inventory. Elements get short stable IDs (e1, e2, ...) with a synthesized selector chosen by priority: `data-testid` > `id` > ARIA role+name > text anchor > structural CSS path. The LLM only ever references element IDs; the executor resolves IDs to selectors.
**Why**: (a) LLMs must never invent selectors; inventing is the top cause of ghost actions in browser agents. (b) The accessibility tree is simultaneously the interaction map and the input to accessibility auditing, so one extraction serves two subsystems. (c) Compact inventories cost 10 to 50x fewer tokens than raw DOM dumps.
**Rejected**: pixel-coordinate vision control (fragile, resolution-dependent, expensive multimodal calls per step), raw HTML in prompts (token blowup, selector hallucination).

### D7. Pydantic v2 at every boundary

**Choice**: All LLM outputs, config, tool inputs/outputs, state, and report models are Pydantic models. LLM structured output uses JSON schema derived from these models, with a repair-reprompt fallback for models lacking native structured output.
**Why**: One schema source of truth feeds prompts, validation, serialization, checkpoints, and docs. Parse failures become typed, retryable errors instead of silent corruption.

### D8. SQLite for durable state, filesystem for artifacts

**Choice**: LangGraph `SqliteSaver` for checkpoints; a per-run artifact directory (`reports/<run_id>/`) for screenshots, HAR-like network logs, extracted snapshots, and generated reports; a small SQLite index of runs.
**Why**: Zero-infrastructure persistence suits an open-source tool that must work on a laptop and in CI. Artifacts are large binaries and belong on disk, not in a database. Postgres would be an operational tax with no current benefit; the state layer's interface will not preclude adding it later.

### D9. Deterministic evaluation against fixture sites with seeded defects

**Choice**: The eval harness runs the agent against local fixture sites (static pages plus a small FastAPI app) containing a labeled ground truth of planted bugs, broken links, a11y violations, and dead ends. Metrics: coverage, bug precision/recall, task completion, retry rate, loop frequency, latency, tokens, cost.
**Why**: Live third-party sites make precision/recall unmeasurable and CI nondeterministic. Ground truth turns "the agent seems good" into numbers that can gate regressions.

### D10. Budgets and hard stops are first-class state

**Choice**: Every run carries explicit budgets: max steps, max tokens, max USD, max wall-clock, max consecutive failures. The `decide` router enforces them; exhaustion produces a normal finalized run with partial results, never a crash.
**Why**: Autonomous browser agents fail open (loop forever, spend unbounded money) unless bounded by construction. Budgets in state also make cost visible in every report (project constraint: cost transparency).

### D11. Deterministic decision router, LLM-free

**Choice**: The `decide` node is pure Python: verdict plus counters plus loop detector in, next edge out.
**Why**: Routing is safety-critical (it enforces budgets and stop conditions) and must be unit-testable to 100 percent coverage. An LLM router can be talked out of stopping.

### D12. Safety posture: domain allowlist, destructive-action policy, secret redaction

**Choice**: (a) Navigation is restricted to an allowlisted domain set derived from the start URL unless explicitly widened. (b) Actions classified destructive (form submits that mutate state, payments, deletions, logouts) require an explicit run-level policy flag; default policy is safe-explore. (c) Log and report pipelines redact values matching secret patterns and never persist credential form values. Credentials for authenticated testing enter only via environment or storage-state file, never prompts or reports.
**Why**: An autonomous clicker on the open web is a liability without fences. These are product features, not afterthoughts: QA teams need to trust the tool on staging environments.

### D13. Record/replay mode for LLM calls

**Choice**: `ModelManager` supports record and replay of model responses keyed by (role, prompt hash). CI and most tests run in replay mode with committed cassettes; live mode is opt-in.
**Why**: Deterministic CI without API keys or cost; contributors without any key can run the full test suite. Also enables offline debugging of a recorded run.

### D14. src-layout installable package

**Choice**: Code lives in `src/website_agent/` with the spec's component directories nested inside the package, with three adjustments: `core/` consolidates the foundation units (errors, types, DI, retry), `llm/` gets a dedicated module (the spec implies it under tooling; conflating it with browser `tools/` obscures both), and `qa/` is added for the Phase 10 QA engine, which the spec's directory list omits. Top-level `evaluation/` holds the harness as dev tooling, importing the installed package.
**Why**: src-layout is the packaging best practice (prevents accidental import of the working tree, makes editable installs and wheels behave identically). Deviation from the spec's literal flat tree is intentional and flagged in the Phase 1 audit.

## 6. Cross-cutting concerns

- **Configuration**: `pydantic-settings`, layered: defaults < config file < environment < CLI/API overrides. `.env` for local development. Secrets only via environment. See Phase 2.
- **Logging**: structured events with run_id and step correlation IDs. Two sinks: Rich console renderer for humans, JSON lines for machines. Log level and format configurable.
- **Error handling**: single exception hierarchy rooted at `AgentError`, split along the retry taxonomy in `failure-recovery.md`. No bare excepts; every catch either handles, retries by policy, or annotates and re-raises.
- **Typing**: full type hints, mypy in CI, Protocols/ABCs for every seam a test needs to fake (model client, browser session, clock, artifact store).
- **Testing**: pytest plus pytest-asyncio. Unit tests fake the seams; integration tests run headless Playwright against local fixture sites; no test touches the public internet.
- **Cost accounting**: every model call passes through a token ledger with a static price table per model; totals land in state, logs, and every report.

## 7. Primary risks and mitigations

| Risk | Mitigation |
|---|---|
| LLM selector or action hallucination | D6 element IDs; executor rejects IDs not in current inventory; reviewer cross-checks observations |
| Infinite exploration loops | State-signature loop detector plus budgets (D10), replan-on-loop verdict |
| Flaky browser automation | Playwright auto-wait, bounded retries with re-snapshot, failure taxonomy in `failure-recovery.md` |
| Unbounded API cost | Budgets (D10), token ledger, replay mode (D13), free local-model path (D3) |
| Non-deterministic CI | Fixture sites (D9), cassette replay (D13) |
| Harm to real sites | Allowlist and destructive-action policy (D12) |

## 8. Document map

| Document | Contents |
|---|---|
| `folder-structure.md` | Full repository tree and per-directory contracts |
| `components.md` | Component diagram, responsibilities, dependency rules |
| `state-machine.md` | LangGraph nodes, state schema, edge conditions |
| `sequences.md` | Sequence diagrams: explore loop, failure recovery, resume |
| `data-flow.md` | Data, tool, and memory flow between layers |
| `failure-recovery.md` | Failure taxonomy, retry policies, checkpoint/resume protocol |
| `planner.md` | Planner internals: inference, scoring, dedupe, replanning |
| `evaluation.md` | Metrics, ground truth format, harness design, reports |
