# Module: state

Layer 2 capability: the serializable heart of a run plus its durable persistence (designs D8, D10).

## Components

| File | Provides |
|---|---|
| `agent_state.py` | `AgentState`: the whole run in one frozen Pydantic object; nodes evolve it via `with_updates` / `append_action`. `STATE_SCHEMA_VERSION` guards resume |
| `models.py` | `GoalSpec`, `RunPolicy` (risk-class gate, D12), `Budgets` (hard stops, D10), `Counters`, `ActionRecord`, `LoopSignal`, `RunResult` |
| `store.py` | `CheckpointStore`: SQLite checkpoints keyed by (run_id, step) plus a run registry; `load_latest` for resume with a schema-version check |

## AgentState

Carries only small structured data and `ArtifactRef` pointers, never binaries (D8), so checkpoints stay small and fast. It holds the current `PageSnapshot` so resume can verify drift, the `MemoryState` (page graph + action registry), append-only `action_history`, budgets, counters, loop signal, and the terminal `stop_reason`. Deliberately free of LangGraph imports so it serializes and tests standalone; Phase 9 wraps it in a `StateGraph`.

State is frozen: nodes produce a new state with `with_updates(**changes)` rather than mutating, so every transition is explicit and auditable.

## Persistence and resume

`CheckpointStore` writes a checkpoint on every step and upserts a run-registry row (status, stop_reason, steps, cost). `load_latest(run_id)` rehydrates the most recent checkpoint; a schema-version mismatch raises `StateError` rather than deserializing wrong-shaped state. Budgets and counters live in the checkpoint, so a resumed run cannot exceed its original budget by crashing (D10). The store is the source of truth for the run list the CLI and API read; Phase 9 adds LangGraph's own `SqliteSaver` for in-graph checkpointing alongside it.

## Budgets (design D10)

Every run carries explicit `Budgets`: max steps, tokens, USD, wall-clock seconds, consecutive failures. `max_usd` may be zero (free local models). The Phase 9 decide router reads `Counters` against `Budgets` to stop by construction.
