# Module: config

Layered application settings on pydantic-settings. One frozen `Settings` object per process, loaded through `load_settings`.

## Precedence (highest first)

1. Explicit overrides (`load_settings(llm={"model": ...})`) from CLI flags or tests
2. Environment variables (`WA_` prefix, `__` nesting: `WA_LLM__API_KEY`)
3. `.env` file in the working directory
4. Optional TOML config file (`load_settings(config_file=Path("wa.toml"))`)
5. Coded defaults

## Sections

| Section | Model | Covers |
|---|---|---|
| `llm` | `LlmSettings` | base_url (OpenAI-compatible endpoint, design D3), api_key (`SecretStr`), model, temperature, max_output_tokens, request timeout |
| `browser` | `BrowserSettings` | headless, action/navigation timeouts, viewport |
| `budgets` | `BudgetSettings` | run hard stops: steps, tokens, USD, wall seconds, consecutive failures (design D10) |
| `logging` | `LoggingSettings` | level, format (`rich` or `json`) |
| `paths` | `PathSettings` | reports dir, checkpoint DB path |

All documented with live examples in `.env.example`.

## Rules

- Never construct `Settings()` directly; always `load_settings` so layering is uniform.
- Settings are process-wide static configuration. Per-run variation (budgets for one run, goal, policy) is run state, set at run creation with settings as defaults.
- Secrets are `SecretStr`: `repr` masks them; call `.get_secret_value()` only at the provider boundary.
- Validation failures raise `ConfigError` with detail in `context`, so interfaces render clean operator messages.
