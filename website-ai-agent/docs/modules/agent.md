# Module: agent

Layer 4 orchestration: the LangGraph state machine that drives the plan-execute-review loop, plus the run lifecycle (designs D1, D10, D11).

## Components

| File | Provides |
|---|---|
| `graph.py` | `build_graph`: compiles the LangGraph `StateGraph` from the nodes |
| `graph_state.py` | `GraphState`: the orchestration state (embeds the durable `AgentState` plus transient per-loop fields) |
| `nodes.py` | `GraphNodes` (bootstrap, planner, executor, reviewer, decide, finalize) and `GraphDeps` (injected, non-serializable handles) |
| `decide.py` | the pure `decide` router (design D11): verdict + budgets + loop to next edge |
| `loop_detector.py` | state-signature loop detection and branch poisoning |
| `runner.py` | `AgentRunner`: assembles dependencies, drives the graph, persists the outcome |

## The loop

```
bootstrap -> planner -> executor -> reviewer -> decide -+-> planner   (continue / replan)
                ^                                        +-> executor  (retry / next step)
                |                                        +-> finalize  (done / budget / stop)
                +----------------------------------------+
```

`bootstrap` navigates and takes the first snapshot; `planner` produces a queue; `executor` runs the head step (or re-runs it on a retry); `reviewer` judges it and updates the loop signal; `decide` syncs counters from the ledger and routes; `finalize` builds the `RunResult`. A plan that comes back empty routes straight to `finalize` (frontier exhausted).

## decide is pure and safety-critical (D11)

Routing enforces budgets and stop conditions, so it is a pure function, LLM-free, and unit-tested to 100 percent across every edge. Budgets are checked before the verdict, so an exhausted budget (steps, tokens, USD, wall-clock, consecutive failures) always finalizes regardless of what the reviewer wanted (design D10). An interrupt outranks everything.

## State, dependencies, and durability

`GraphState` (Layer 4) may hold the Layer 3 role outputs `AgentState` cannot import. Non-serializable handles (browser session, live memory service, role objects) live in `GraphDeps`, injected into the nodes and never checkpointed, so checkpoints stay clean. LangGraph checkpoints `GraphState` per node; the `AgentRunner` also persists the final `AgentState` to the SQLite `CheckpointStore` and records the run in the registry. The LangGraph recursion limit is set above the step budget, so budgets, not the framework, stop a run.

## Visualization

The compiled graph exports Mermaid via `app.get_graph().draw_mermaid()` (surfaced by `website-agent graph` in Phase 13), so the shipped diagram is generated from code.

## Tested

`decide` and the loop detector: exhaustive pure unit tests. Nodes: unit-tested with a fake session and a schema-routed fake model. The whole graph: an end-to-end integration test (`pytest -m integration`) runs the real loop over the local fixture site with the LLM replaced by a scripted model, so it is keyless and deterministic.
