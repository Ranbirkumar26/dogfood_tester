# Failure Recovery and Retry Strategy

Every failure in this system belongs to exactly one class, and every class has one owner and one policy. "Retry" is never generic: what gets retried, by whom, how many times, and with what backoff is fixed here and implemented once in `core/` retry policies.

## 1. Failure taxonomy

| Class | Examples | Owner | Policy |
|---|---|---|---|
| **F1 Browser-transient** | element detached, click intercepted, navigation timeout, target closed | Tool layer | retry in place: 2 attempts, exponential backoff 0.5s base, jitter; re-resolve selector between attempts |
| **F2 Browser-fatal** | browser process crash, context destroyed | BrowserManager | relaunch session once per run, rehydrate (section 4); second crash = fatal |
| **F3 LLM-transient** | 429, 5xx, connection reset, timeout | ModelManager | retry: 3 attempts, exponential backoff 1s base with jitter, honor Retry-After; provider-level rate limiter in front |
| **F4 LLM-output** | schema validation failure, truncated JSON | ModelManager | 1 repair reprompt with error appended; then raise typed parse error, step fails as F5 |
| **F5 Step-semantic** | action ran but wrong outcome; expected nav absent; new console errors | Reviewer + decide | verdict RETRY (max 2 attempts per step, fresh snapshot each) then REPLAN |
| **F6 Plan-level** | step impossible, element gone, section dead-ends | Planner via REPLAN | replan with failure feedback; failed signature recorded so the action is not re-proposed |
| **F7 Run-level** | loop detected, budget exhausted, allowlist exhausted, user stop | decide router | graceful finalize with partial results, never an exception |
| **F8 Fatal** | invalid config, unreachable start URL, storage-state auth rejected, second F2 | AgentRunner | fail fast at bootstrap or finalize with `stop_reason=fatal_error`; clear operator message |

Classification is structural: each layer raises typed exceptions from the `AgentError` hierarchy (`BrowserTransientError`, `ModelRateLimitError`, `OutputParseError`, ...), so the owner is determined by type, never by string matching.

## 2. Retry policies (implemented once, in core)

```
policy browser_transient: attempts=2, backoff=exp(base=0.5s, cap=4s, jitter=full)
policy llm_transient:     attempts=3, backoff=exp(base=1s, cap=30s, jitter=full), respect Retry-After
policy llm_repair:        attempts=1 (repair reprompt), no backoff
policy step_retry:        attempts=2 (decide-enforced), fresh snapshot mandatory
```

Rules:

- Backoff with full jitter everywhere (thundering-herd hygiene even for one agent; matters when API server runs concurrent runs).
- Retry budgets nest but never multiply unboundedly: worst case per step = F1(2) x F5(2) tool attempts plus F3(3) per LLM call, all bounded, all counted in `counters`.
- Every retry emits a structured log event with class, attempt, and cause; retry counts are eval-harness metrics.
- No retry on F8, on policy violations (D12), or on 4xx client errors other than 429 (a 400 will not become a 200 by insisting).

## 3. Loop detection

Failure mode unique to autonomous agents: everything "succeeds" while the run goes nowhere.

- **State signature** = hash(normalized URL, inventory hash, last action signature). Ring buffer of recent signatures in state.
- Same signature seen `loop_warn` times (default 3): planner receives an explicit loop warning in feedback.
- Seen `loop_limit` times (default 5): decide forces one replan with the looping branch marked poisoned; if the signature recurs after that, finalize with `stop_reason=loop_limit`.
- Reviewer independently flags semantic loops (e.g., pagination that never advances) as REPLAN with reason, feeding the same counters.

## 4. Crash recovery and resume protocol

Checkpoint after every node (D8) makes any crash recoverable to the last node boundary.

Resume steps (`AgentRunner.resume(run_id)`):

1. Load latest checkpoint for `thread_id=run_id`; verify state schema version.
2. Launch fresh browser session; restore `storage_state.json` from the run's artifact dir (cookies, localStorage, auth survive).
3. Navigate to `current_snapshot.url`; extract fresh snapshot.
4. Compare fresh snapshot hash to checkpointed hash:
   - match: resume graph at the pending node;
   - drift: resume with forced-replan flag (stale plan steps may reference dead elements).
5. Budgets resume from checkpointed counters: a crash never resets spend (D10).

Non-resumable cases: corrupt checkpoint (reported, run marked failed), storage state rejected by the site (F8, operator must re-auth).

## 5. Graceful degradation

- Screenshot capture failure never fails a step: observation marked `screenshot: unavailable`, run continues.
- One observer failing (e.g., network capture detaches) degrades that signal for the step and raises a run-level warning; QA report marks affected detectors as reduced-confidence.
- Reporting failures at finalize retry once, then write a minimal JSON report; a run that explored successfully must never end with zero output.

## 6. Timeouts

| Scope | Default | Enforced by |
|---|---|---|
| Single browser action | 10s | Playwright timeout via tool layer |
| Page navigation | 30s | BrowserSession |
| LLM call | 60s | ModelManager |
| Node execution (soft) | 120s | AgentRunner watchdog; timeout = step failure (F5), not a hung graph |
| Whole run wall-clock | budget (`max_wall_seconds`) | decide router |

All defaults live in config (Phase 2), overridable per run.
