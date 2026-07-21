# Module: qa

Layer 3: the deterministic QA engine. Turns a run's accumulated evidence into confirmed, severity-ranked findings (Phase 10, overview.md D14).

## Components

| File | Provides |
|---|---|
| `models.py` | `QaFinding` (confirmed defect with severity and a stable dedupe key), `QaContext` (whole-run evidence), `QaReport` + `SeverityCounts` |
| `detectors.py` | pure detector functions and the `ALL_DETECTORS` pipeline |
| `engine.py` | `QaEngine.analyze(context) -> QaReport`: composition, cross-detector dedupe, severity ranking |

## Detectors

Two families, all pure functions over `QaContext`:

- **Candidate promotion**: `detect_from_candidates` turns the reviewer's per-step `QaCandidate`s (console errors, HTTP errors, dead actions, unexpected redirects, missing validation, slow requests) into findings, deduplicated across the whole run by kind and location, so a console error firing on every page is one finding.
- **Snapshot analysis**: structural defects the per-step reviewer cannot see: `detect_missing_labels` (interactive controls with no accessible name, a real accessibility defect), `detect_duplicate_ids` (repeated author ids, invalid HTML), `detect_empty_pages` (visited pages with nothing interactive, possible dead navigation).

Severity is assigned uniformly in the detectors: HTTP 5xx is critical; 4xx, console errors, missing labels, unexpected redirects, and missing validation are major; duplicate ids, slow requests, and dead ends are minor. Every finding carries a stable `dedupe_key` so the same defect collapses to one across steps, pages, and detectors.

## Determinism

The engine is pure composition over deterministic detectors, so a run's QA outcome is reproducible from its recorded evidence: a future `website-agent report --from-run` can re-derive findings without re-exploring. `analyze` deduplicates by key, counts by severity, and sorts most-severe-first for reports and the CI gate (`has_blocking_issues`).

## Wiring

The graph accumulates distinct visited page snapshots (deduped by content hash) during the run. The `finalize` node builds a `QaContext` from the accumulated reviewer candidates plus those snapshots, runs `QaEngine`, persists `qa/findings.json` to the run's artifact directory, and sets `RunResult.findings` from the report. Rendering to Markdown/HTML is the reporting engine (Phase 11).

## Tested

Each detector has isolated unit tests; the engine has composition, dedupe, ranking, and JSON round-trip tests. An integration test runs the engine over a real snapshot of the fixture contact page and confirms the unlabeled input is flagged.
