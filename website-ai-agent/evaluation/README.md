# Evaluation harness

Dev tooling that scores agent runs against labeled ground truth. Not shipped in the wheel (design D14, D9). It imports the installed `website_agent` package and drives the same `AgentRunner` the CLI and API use, so measurements reflect shipping behavior.

## Layout

| Path | Contents |
|---|---|
| `harness/models.py` | `GroundTruth`, `Defect`, `Scenario`, `EvalEvidence`, `Metrics`, `ScenarioResult` |
| `harness/ground_truth.py` | YAML loading and mechanical finding-to-defect matching |
| `harness/metrics.py` | pure metric collectors |
| `harness/scoring.py` | threshold gating to a pass/fail result |
| `harness/evidence.py` | reduce a finished run to the flat evidence bundle |
| `harness/report.py` | JSON, Markdown, CSV, and self-contained HTML dashboard writers |
| `scenarios/*.yaml` | scenario definitions (site, budgets, success thresholds) |
| `ground_truth/*.yaml` | labeled defects and expected coverage per fixture site |

## Bundled scenarios

| Site | Focus |
|---|---|
| `static-basic` | baseline navigation, console error, HTTP error, missing label |
| `forms-basic` | form validation and form-control accessibility |
| `defects-basic` | console/network defects, duplicate ids, redirect handling |
| `spa-basic` | client-side state changes, modals, hash navigation |
| `maze-basic` | cyclic navigation and dead-end detection |

## Metrics

Page and element coverage, navigation success rate, retry rate, loop frequency (per 100 steps), bug precision and recall (against ground truth), plus tokens, cost, LLM calls, screenshots, wall-clock, and steps. All are pure functions over `EvalEvidence`, so scores are reproducible and can be recomputed over any past run without re-exploring.

## Ground-truth matching

Mechanical, no LLM in the metric path (design D9): a finding matches a defect when their kind agrees and their locations agree under URL normalization (with path-suffix tolerance, since ground-truth locations are often paths and findings are full URLs). Unmatched findings are false positives; unmatched defects are misses. Both are reported explicitly so a regression is triageable.

## Determinism and cost

Scenarios run in replay or scripted-model mode at zero API cost; thresholds gate on the minimum across repeats, never the mean, so a lucky run cannot mask a flaky regression. The `kind` values in ground truth align 1:1 with QA-engine finding kinds.

## Outputs

`eval_result.json` (CI gate), `report.md` (human summary), `metrics.csv` (spreadsheets and history), `dashboard.html` (single self-contained file, publishable as a CI artifact).
