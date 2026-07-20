# Module: reviewer

Layer 3 role: the truth authority. Compares a step's expectation against observed reality and issues the router decision (design D2, docs/architecture/state-machine.md).

## Contract

```python
verdict = await Reviewer(model, prompts).review(step, result, loop_repeats=n, branch_poisoned=b)
```

Returns a `ReviewVerdict` with a `decision` (SUCCESS / RETRY / REPLAN / STOP), `expectation_met`, human reasons, extracted `qa_candidates`, and `is_loop` / `hallucination_suspected` flags.

## Never trusts the executor

The reviewer reasons from observations only, never from a claim of success (design D2). A failed click cannot become "success". The LLM judgement prompt is fed the observed evidence (URLs, navigation, console errors, failed requests, post-step title) and the step's expectation, never a success flag.

## Layered decision pipeline

Cheapest guard that settles the outcome wins, so the LLM is called only when genuinely needed:

1. **Execution failed** to `RETRY` (transient browser), `REPLAN` (element gone / policy), or `STOP` (fatal), by failure class.
2. **Loop detected** (`loop_repeats >= loop_limit`) to `REPLAN`, or `STOP` once the branch is already poisoned.
3. **Mechanical expectation** (url_change, dialog, download, no_change) decided directly from observations, no LLM.
4. **Semantic expectation** (validation_error, content_change, new_elements) judged by one LLM call.

## QA candidates are LLM-independent

`extract_qa_candidates` turns observations into candidate defects in pure Python on every path: console errors (major), HTTP failures (critical for 5xx, major otherwise), and dead actions (a click that produced no observable change). So the bug signal never depends on the verdict path or the model. These feed the Phase 10 QA engine for confirmation and severity finalization.

## Prompt

`prompts/templates/reviewer.md` ships with the package; content-hash versioned so edits invalidate stale cassettes (design D13).
