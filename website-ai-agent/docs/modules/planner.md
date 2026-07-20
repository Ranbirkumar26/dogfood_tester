# Module: planner

Layer 3 role: turns "what the agent can see and remembers" into "what to do next, in what order". The only component that decides intent (docs/architecture/planner.md).

## Pipeline

```
generate (deterministic) -> dedupe (registry) -> policy filter (D12) -> LLM score -> deterministic re-rank
```

| File | Provides |
|---|---|
| `candidates.py` | `generate_candidates` (afforded actions from the inventory + frontier navigations), `classify_risk` (safe/mutating/destructive from accessible name and kind) |
| `scoring.py` | `ScoringWeights`, `weights_for(mode)`, `compute_priority`, `coverage_gain` |
| `planner.py` | `Planner.plan(...)`: the orchestrated pipeline |
| `render.py` | `render_inventory`: token-bounded, salience-ordered inventory text for the prompt |
| `models.py` | `Plan`, `PlanStep`, `Expectation`, `InputSpec`, `ActionCandidate`, `PlannerScoring` (LLM output schema) |

## Why candidates come from code

The LLM never proposes elements (design D6): it scores a numbered shortlist that was generated deterministically from the inventory, and supplies each chosen step an expectation and (for fills) an input class and value. This kills selector hallucination at the source and keeps the model call small. Every `PlanStep` carries a falsifiable `Expectation`, the reviewer's comparison anchor (design D2); a step without one is invalid by schema.

## Value estimation is hybrid

Priority combines an LLM `goal_relevance` (semantic) with structural scores computed in code: novelty, coverage gain (links > inputs > scroll), depth penalty, and a failure penalty for signatures that failed before. Weights differ by goal mode (`weights_for`): explore favors novelty and coverage, test favors relevance (forms and edge cases), document favors breadth. The final re-rank is pure Python, so ordering is reproducible given fixed LLM scores, and weights are eval-harness tunables (Phase 12).

## Safety and dedupe

- **Policy filter** drops off-allowlist navigations and disallowed risk classes before scoring (D12), so a destructive action is never even offered to the model under safe-explore.
- **Dedupe** drops candidates whose action signature is already in the registry, so the planner does not re-propose tried actions. Test mode exempts fills so a form can be re-submitted with different input classes.

## Prompt

`prompts/templates/planner.md` ships with the package. Rendering is strict (missing/unused variables error). Cassette keys include the template version, so a prompt edit invalidates stale recordings (design D13).
