# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) from 1.0 onward.

## [Unreleased]

### Added

- Foundation: layered configuration, structured logging with secret redaction, exception
  hierarchy mapped to a failure taxonomy, dependency-injection container, retry policies,
  clock and ID utilities, and an artifact store.
- Browser layer: a Playwright facade with page-snapshot extraction (stable element IDs and
  synthesized selectors), console and network observers, screenshots, downloads, tabs,
  popups, dialogs, and storage-state authentication.
- LLM layer: a provider-agnostic model manager over the OpenAI-compatible protocol with
  structured outputs and repair, a token and cost ledger, rate limiting, and record/replay
  cassettes for keyless tests.
- State and memory: a serializable run state with budgets, SQLite checkpointing with resume,
  a page graph with template collapse, and an action registry for dedupe.
- Roles: a planner (candidate generation plus hybrid scoring), an executor (deterministic
  tool dispatch), and a reviewer (expectation-versus-observed truth authority).
- Orchestration: a LangGraph plan-execute-review loop with a pure decision router, loop
  detection, budgets, and a run runner.
- QA engine: a deterministic detector pipeline producing severity-ranked findings.
- Reporting: QA reports, generated site documentation, user-flow graphs, and JSON/CSV exports.
- Evaluation harness: ground-truth matching and metric collectors with report writers.
- Interfaces: a Typer CLI and a FastAPI server.
- Packaging and CI: Docker image and compose, GitHub Actions for lint, type, tests, coverage,
  Docker build, and tag-driven publishing.

This is the initial pre-release; interfaces may change before 1.0.
