# Examples

## Sample run output

[`sample-run/`](sample-run/) contains real output from exploring the bundled `static-basic`
fixture site (URLs normalized to `demo.local` for a stable sample):

- [`qa_report.md`](sample-run/qa_report.md): the QA report. The agent found the seeded console
  errors, the 404 responses (a broken link and a missing fetch), and a form input with no
  accessible name.
- [`flow.mmd`](sample-run/flow.mmd): the user-flow graph in Mermaid.

To reproduce against your own site:

```bash
website-agent run https://your-site.example --max-steps 40
# outputs land in reports/<run_id>/output/
```

## Running against a local model (free)

```bash
export WA_LLM__BASE_URL=http://localhost:11434/v1   # Ollama
export WA_LLM__MODEL=llama3.1:8b
website-agent run https://your-site.example
```

The agent runs at zero API cost against any OpenAI-compatible local endpoint.
