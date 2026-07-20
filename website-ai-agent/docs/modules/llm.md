# Module: llm

Layer 2 capability: provider-agnostic model access. One thin abstraction over the OpenAI wire protocol serves every provider users realistically run (designs D3, D13).

## Components

| File | Provides |
|---|---|
| `manager.py` | `ModelManager`: the single entry point for every model call. Structured (`complete`) and plain (`complete_text`, `stream_text`) completions; the full pipeline rate-limit to transport to accounting to parse to repair |
| `pricing.py` | `PriceTable`: USD/million-token pricing with longest-prefix matching; unknown models price at zero (local models are free) with a one-time warning |
| `ledger.py` | `TokenLedger`: append-only usage accounting, grand totals and per-role attribution; feeds budgets (D10) and the eval harness |
| `rate_limit.py` | `AsyncRateLimiter`: client-side sliding-window request limiting; injected clock and sleep for deterministic tests |
| `recorder.py` | `CassetteStore` + `request_key`: record/replay of model responses for keyless, cost-free, deterministic CI (D13) |

## Provider configuration

Any OpenAI-compatible endpoint via `WA_LLM__BASE_URL`:

| Provider | base_url | Cost |
|---|---|---|
| OpenAI (default) | `https://api.openai.com/v1` | paid |
| Ollama | `http://localhost:11434/v1` | free, local |
| Groq | `https://api.groq.com/openai/v1` | free tier |
| OpenRouter | `https://openrouter.ai/api/v1` | mixed |
| vLLM / LM Studio | local URL | free, local |

## Structured output

`complete(role, prompt, schema)` returns a validated Pydantic instance. Provider-side schema enforcement is not relied upon (support varies across OpenAI-compatible servers): the schema is stated in the prompt, `json_object` mode is requested when configured, and the pipeline validates then does one bounded repair reprompt. Two failures raise `OutputParseError` (failure class F4). Parsing tolerates code fences and surrounding prose.

## Record / replay (design D13)

Three modes via `WA_LLM__MODE`:

- `live` (default): real calls, no cassettes.
- `record`: real calls, responses saved to `WA_LLM__CASSETTE_DIR/<key>.json`.
- `replay`: no provider client at all, responses served from cassettes; a miss (prompt, model, or schema changed) raises a `StateError` naming the key.

The cassette key hashes role, model, messages, and schema name, so any prompt or schema drift invalidates cassettes loudly instead of silently replaying stale behavior. CI and the default test suite run keyless.

## Retries and errors

Provider failures are classified by `map_openai_error` into the taxonomy: 429/timeout/5xx are transient (F3, retried under `LLM_TRANSIENT_POLICY` with `retry-after` honored); auth and other 4xx are terminal. Streaming is live/record only (replaying faked latency has no value).

## Usage

```python
ledger = TokenLedger(PriceTable(), clock)
limiter = AsyncRateLimiter(settings.llm.requests_per_minute, clock)
manager = ModelManager(settings.llm, ledger, limiter)

plan = await manager.complete("planner", rendered_prompt, Plan)
print(ledger.by_role())  # per-role tokens and cost
```
