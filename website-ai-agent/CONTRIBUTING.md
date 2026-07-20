# Contributing

Thanks for your interest in improving website-ai-agent. This guide covers setup, the quality bar, and how work is organized.

## Development setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
```

Run the checks the way CI does:

```bash
ruff check .            # lint
ruff format --check .   # formatting
mypy                    # strict type check (src and evaluation)
pytest --cov            # unit + real-browser integration tests
```

Integration tests (`pytest -m integration`) drive real headless Chromium against a local fixture server; no test touches the public internet, and no API key is required (tests use scripted models).

## Quality bar

Every change is expected to keep the build green:

- ruff lint and format clean, mypy strict clean.
- Tests pass; new behavior comes with tests. Coverage is gated at 90 percent in CI (currently ~97).
- No secrets in code, commits, or logs. Configuration goes through settings and the environment.
- No emojis or em dashes in code, docs, or commit messages.

## Architecture

Read [`docs/architecture/overview.md`](docs/architecture/overview.md) first. The decisions there (D1..D14) are binding; changing one means updating that document. The layered dependency rule (interfaces to foundation, downward only) is enforced in review. Each module has a one-page doc under [`docs/modules/`](docs/modules/).

## Commit and PR conventions

- Small, focused commits with imperative subjects that explain the why.
- Open a PR against `main`; fill in the template. CI must pass.
- Prompt or schema changes invalidate LLM cassettes by design; re-record if you touch them.

## Reporting bugs and requesting features

Use the issue templates. For anything security-related, follow [`SECURITY.md`](SECURITY.md) instead of opening a public issue.
