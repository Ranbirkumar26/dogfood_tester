# Sequence Diagrams

Three sequences cover the system's temporal behavior: the happy-path explore loop, in-run failure recovery, and crash resume. Participants map 1:1 to components in `components.md`.

## 1. Explore loop (happy path)

One full cycle: plan, execute two steps, review, continue.

```mermaid
sequenceDiagram
    autonumber
    participant R as AgentRunner
    participant G as StateGraph
    participant P as Planner
    participant X as Executor
    participant T as ToolLayer
    participant B as BrowserSession
    participant V as Reviewer
    participant D as decide
    participant M as ModelManager

    R->>G: run(goal, policy, budgets)
    G->>B: bootstrap: launch, auth, goto(start_url)
    B-->>G: PageSnapshot#35;1 (inventory e1..eN)

    G->>P: plan(snapshot, memory, goal)
    P->>M: complete(planner prompt, Plan schema)
    M-->>P: Plan (prioritized PlanSteps with expectations)
    P-->>G: state.plan

    G->>X: execute(step 1: click e12)
    X->>T: click(element_id=e12)
    T->>B: resolve e12 to selector, act, auto-wait
    B-->>T: nav event, console(0), network(2xx), screenshot ref
    T-->>X: ToolResult + ObservationBundle
    X->>B: re-extract snapshot
    B-->>X: PageSnapshot#35;2
    X-->>G: ExecutionResult(step 1)

    G->>V: review(step 1 expectation vs result)
    V->>M: complete(reviewer prompt, Verdict schema)
    M-->>V: SUCCESS (expected nav occurred, no errors)
    V-->>G: ReviewVerdict

    G->>D: decide(state)
    D-->>G: edge=executor (queue non-empty, budgets OK)
    G->>X: execute(step 2: fill form e7...)
    Note over G,D: loop continues until frontier empty or budget stop
```

## 2. Failure recovery (element gone stale, retry then replan)

Shows the taxonomy in action: one browser-level retry inside the tool layer, then a step-level RETRY, then escalation to REPLAN. Policies: `failure-recovery.md`.

```mermaid
sequenceDiagram
    autonumber
    participant G as StateGraph
    participant X as Executor
    participant T as ToolLayer
    participant B as BrowserSession
    participant V as Reviewer
    participant D as decide
    participant P as Planner

    G->>X: execute(step: click e9)
    X->>T: click(e9)
    T->>B: act
    B--xT: TimeoutError (element detached)
    Note over T,B: browser-level retry: backoff, re-resolve selector
    T->>B: act (attempt 2)
    B--xT: TimeoutError again
    T-->>X: ToolResult(failure=element_unavailable)
    X-->>G: ExecutionResult(failed, observations)

    G->>V: review(step, result)
    V-->>G: ReviewVerdict(RETRY, reason=transient_element)
    G->>D: decide(state)
    D-->>G: edge=executor (attempt 2 of max 2)

    G->>X: execute(step, attempt 2, fresh snapshot first)
    X->>B: re-extract snapshot
    B-->>X: PageSnapshot (e9 no longer present)
    X-->>G: ExecutionResult(failed, element_not_in_inventory)
    G->>V: review
    V-->>G: ReviewVerdict(REPLAN, reason=page_changed)
    G->>D: decide(state)
    D-->>G: edge=planner (step marked failed)
    G->>P: plan(fresh snapshot, memory incl. failed action signature)
    P-->>G: new Plan (dead action excluded via ActionRegistry)
```

## 3. Crash resume

Process dies mid-run; user resumes. Checkpoint semantics: `state-machine.md`; rehydration protocol: `failure-recovery.md`.

```mermaid
sequenceDiagram
    autonumber
    participant U as CLI user
    participant R as AgentRunner
    participant C as CheckpointStore
    participant B as BrowserSession
    participant G as StateGraph
    participant P as Planner

    Note over R: process killed after step 14 checkpoint
    U->>R: website-agent run --resume run_abc123
    R->>C: load latest checkpoint(thread_id=run_abc123)
    C-->>R: AgentState (step 14, plan queue, memory refs)
    R->>B: new session, restore storage_state.json
    B-->>R: session ready (cookies, localStorage applied)
    R->>B: goto(state.current_snapshot.url)
    B-->>R: fresh PageSnapshot
    R->>R: compare snapshot hash vs checkpointed hash
    alt hash matches
        R->>G: resume at pending node
    else page drifted
        R->>G: resume with forced-replan flag
        G->>P: plan(fresh snapshot, full memory)
    end
    Note over G: run continues; budgets include pre-crash spend
```

Budget counters (tokens, USD, steps, wall-clock) persist in the checkpoint, so a resumed run cannot exceed its original budget by crashing (D10).
