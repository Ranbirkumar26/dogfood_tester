# Module: core

Foundation layer (Layer 1). Exception hierarchy, shared vocabulary types, dependency injection, retry policies, time, IDs, and artifact storage. LLM-free, browser-free, framework-free by rule; everything above imports from here.

## Contents

| File | Provides |
|---|---|
| `errors.py` | `AgentError` hierarchy mapped 1:1 to the failure taxonomy (F1..F8); `retryable` class markers; structured `context` dicts |
| `types.py` | `GoalMode`, `RiskClass`, `Severity` (with `rank`), `StopReason`, `ArtifactRef` (traversal-safe artifact pointer) |
| `clock.py` | `Clock` protocol, `SystemClock`, `FixedClock` (deterministic tests) |
| `ids.py` | `generate_run_id` (sortable, filesystem-safe), `generate_step_id` |
| `retry.py` | `RetryPolicy`, `retry_async` (full jitter, `retry_after` support, injectable sleep/rng), presets `BROWSER_TRANSIENT_POLICY`, `LLM_TRANSIENT_POLICY`, `LLM_REPAIR_POLICY` |
| `di.py` | `Container`: type-keyed providers, singleton caching, cycle detection, scoped test overrides |
| `artifacts.py` | `ArtifactStore` ABC, `FileArtifactStore` writing under `reports/<run_id>/` |

## Usage

```python
from website_agent.core import (
    Container, SystemClock, FileArtifactStore, generate_run_id,
    retry_async, LLM_TRANSIENT_POLICY, ModelTransientError,
)

clock = SystemClock()
run_id = generate_run_id(clock)
store = FileArtifactStore(Path("reports"), run_id, clock)

result = await retry_async(
    call_provider,
    policy=LLM_TRANSIENT_POLICY,
    retry_on=(ModelTransientError,),
    on_retry=lambda exc, attempt, delay: log.warning("llm_retry", attempt=attempt),
)
```

## Rules

- Raise only `AgentError` subclasses from package code; pick the type by failure class, never encode the class in the message.
- Never put secrets in `context` dicts; they flow to logs and reports.
- All retries in the system go through `retry_async` with a named policy; no ad hoc retry loops.
- Components take `Clock`, never call `datetime.now()` directly.

Design references: docs/architecture/overview.md (D7, D8, D10, D11), docs/architecture/failure-recovery.md.
