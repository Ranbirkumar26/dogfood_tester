# Module: executor

Layer 3 role: runs one plan step against the browser and returns a structured result. The only role allowed to touch the tool layer (docs/architecture/components.md, rule 3).

## Contract

```python
result = await Executor(clock).execute(step, session, memory)
```

`execute(step, session, memory) -> ExecutionResult`. It:

1. dispatches the step's action to the matching `BrowserSession` tool call,
2. settles the page and re-snapshots (for actions that can change the page),
3. captures a screenshot and drains the step's observation window,
4. records the action in memory (for planner dedupe) and the visited page in the graph,
5. returns an `ExecutionResult` with the mechanical outcome.

## The executor decides mechanics, not truth

It is deliberately LLM-free: the plan step already carries the element, input, and target, so execution is a deterministic dispatch (fast, cheap, exhaustively testable). It reports only what happened; whether that matched the step's expectation is the reviewer's judgement (design D2). `ExecutionResult` therefore carries no verdict, just the tool outcome, before/after URLs, the post-step snapshot, the observation bundle, and a screenshot reference.

## Never raises on step failure

Every browser failure is caught and classified into `failure_kind` (`element_unavailable`, `browser`, `browser_fatal`, `policy`), producing a result with `ok=False` rather than an exception. The loop must keep control so the reviewer and router always run (docs/architecture/failure-recovery.md). Evidence (screenshot, observations) is captured even on failure. A failed action is still recorded in memory so the planner penalizes it next pass.

## Graceful degradation

A post-step snapshot or settle failure after a successful action does not fail the step: the result is still `ok`, with `snapshot_after=None` and a logged warning. Screenshots that fail to capture yield `screenshot=None`.

## Tested

Unit tests drive a fake session (dispatch, every failure class, memory recording, degradation). Integration tests (`pytest -m integration`) run the real executor against the local fixture site: click, fill, and navigation with observation capture.
