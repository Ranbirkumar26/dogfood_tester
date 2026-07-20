# Module: memory

Layer 2 capability: run memory as a page graph and an action registry (docs/architecture/data-flow.md, section 4). Deliberately not a vector store: exploration needs exact dedupe and graph traversal, not similarity search.

## Components

| File | Provides |
|---|---|
| `graph.py` | `PageGraph` (nodes = page-classes, edges = navigations), `normalize_url` |
| `registry.py` | `ActionRegistry` (seen/failed signatures), `action_signature`, `MemoryState` (both structures, one serializable unit) |
| `service.py` | `MemoryService`: mutable live owner that evolves `MemoryState` from observations and hands back immutable snapshots for checkpointing |

## URL normalization and template collapse

`normalize_url` drops the fragment, lowercases scheme/host, strips trailing slashes, drops the query by default, and replaces id-like path segments with `{id}`. So `/product/1` and `/product/2` collapse to one page-class node, giving coverage without combinatorial blow-up. Distinct content hashes at the same URL still make distinct nodes (a page that changed materially).

## Action signatures (planner dedupe)

`action_signature` hashes the normalized URL, the element signature (role + name + author ids, not the ephemeral eN id), the action type, and an input class. Because it uses the stable element signature, dedupe survives re-snapshots and minor DOM shifts. The input class keeps "fill with valid email" and "fill with malformed email" distinct, which matters in test mode.

## Lifecycle

`MemoryService` holds the live `MemoryState` during a run: `observe_page` and `observe_transition` grow the graph; `record_action` / `has_seen_action` drive dedupe. Its `.state` is the immutable snapshot embedded in each checkpoint. On resume it is reconstructed from the checkpointed `MemoryState`, losing no history. The frozen copy-on-write structures serialize cleanly and round-trip through JSON.
