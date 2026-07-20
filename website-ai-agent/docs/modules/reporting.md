# Module: reporting

Layer 2: the documentation engine. Renders a finished run's evidence into human and machine outputs (Phase 11).

## Components

| File | Provides |
|---|---|
| `inputs.py` | `ReportInputs`: the immutable evidence bundle (run result, page graph, QA report, snapshots, action history) |
| `flow_graph.py` | `render_mermaid`, `render_dot`: the user-flow graph from the page graph |
| `markdown.py` | `render_qa_report` (findings and metrics), `render_site_docs` (navigation tree, feature inventory, flow) |
| `exports.py` | `render_json` (full typed report), `render_findings_csv` |
| `engine.py` | `ReportingEngine.generate`: renders everything and persists it to `output/` |

## Outputs

`ReportingEngine.generate` writes six artifacts under the run's `output/` directory: `qa_report.md`, `documentation.md`, `flow.mmd`, `flow.dot`, `report.json`, `findings.csv`.

## Pure renderers, reproducible

Every renderer is a pure function from `ReportInputs` to a string, so a run's documentation is fully reproducible from its recorded evidence: `website-agent report --from-run` (Phase 13) can rebuild all outputs without re-exploring. The engine's only side effect is writing; a failure to render one output is logged and skipped, so a run always ends with as much documentation as could be produced.

## Generated site documentation

The docs the agent produces about the site under test are factual and structural: the navigation tree (pages and their link counts), a feature inventory (distinct interactive controls across visited pages, most common first), and the user-flow Mermaid graph. It documents the site as observed; it does not editorialize. Labels are sanitized so page titles with quotes or newlines cannot break diagram or table grammar. No emojis or em dashes, per project convention.

## Wiring

The `AgentRunner` calls the reporting engine after the graph completes, building `ReportInputs` from the final graph state (run result, QA report, visited snapshots, action history) and the page graph, then generating all outputs. QA `findings.json` is written earlier by the `finalize` node; reporting adds the rendered views.

## Tested

Each renderer has isolated unit tests (content, sanitization, escaping, empty cases); the engine has a full-write test and a degradation test. The end-to-end agent integration test exercises report generation over a real run.
