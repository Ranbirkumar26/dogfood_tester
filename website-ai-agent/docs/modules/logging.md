# Module: logging

Structured, redacted logging on stdlib `logging`. Rich console for humans, JSON lines for machines.

## Model

- Events, not strings: `log.info("step_executed", step_id="step_0003", outcome="success")`.
- Correlation IDs (run_id, step) bind via contextvars and stamp every event automatically:

```python
from website_agent.logging import bind_run_context, configure_logging, get_logger

configure_logging(settings.logging)
log = get_logger("executor")

with bind_run_context(run_id=run_id):
    with bind_run_context(step="step_0003"):
        log.info("action_done", action="click", element="e3")
```

JSON sink output:

```json
{"ts": "2026-07-20T12:00:00+00:00", "level": "INFO", "component": "executor",
 "event": "action_done", "run_id": "run_...", "step": "step_0003",
 "fields": {"action": "click", "element": "e3"}}
```

## Redaction (design D12)

`RedactionFilter` sits on the package logger itself, so every handler receives already-masked records. Masked shapes: `key=value` assignments for secret-named keys (api_key, token, password, secret, authorization), bearer credentials, `sk-...` API keys. `redact_text` is exported for artifact writers to apply the same masking at file-write time.

Patterns are precision-first: ordinary URLs, element IDs, and selectors must never be mangled. Extend patterns with a test in both directions (masked and untouched).

## Rules

- One `configure_logging` call at process start (CLI/API entry); safe to call again, last call wins.
- Only the `website_agent.*` logger namespace is touched; `propagate=False`, so embedding never hijacks a host app's logging.
- Never pass secrets as field values expecting redaction to save you; redaction is the last line, not a license.
- Component names are dotted paths under the package: `get_logger("browser.session")`.
