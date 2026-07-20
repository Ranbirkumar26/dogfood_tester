# Module: api

Layer 5 interface: the FastAPI REST server. A thin surface over `AgentService`; handlers validate, call the service, and translate to HTTP (docs/architecture/components.md, rule 5).

## Endpoints

| Method | Path | Does |
|---|---|---|
| GET | `/health` | Liveness check |
| POST | `/runs` | Start an exploration run (body: url, mode, same_domain, budgets); returns 202 with a run id |
| GET | `/runs` | List recorded runs |
| GET | `/runs/{run_id}` | Run status from the registry |
| GET | `/runs/{run_id}/report` | The run's QA report Markdown |
| GET | `/runs/{run_id}/artifacts/{name}` | Download an output artifact |
| GET | `/docs`, `/openapi.json` | Swagger UI and schema (FastAPI built-in) |

## Background execution

A run takes minutes, so `POST /runs` returns immediately (202) and the `AgentService` launches the run as a tracked asyncio task. Callers poll `GET /runs/{run_id}`; status comes from the persisted run registry, which the graph updates every step. A run that is accepted but has no checkpoint yet reports as `running`. A failed run is logged and cleaned up, never propagated, so one bad run cannot crash the server.

## Safety

Artifact and report reads validate the run id and artifact name against a strict pattern before building any path, so traversal (`../`) and unexpected characters are rejected with 400 before touching the filesystem. `same_domain` defaults to true on start, restricting navigation to the target's domain (design D12).

## Running

`python -m website_agent.api` (host and port via `WA_API_HOST` / `WA_API_PORT`), or embed `create_app()` in any ASGI server. `create_app` accepts an injected settings object and service, which is how the tests drive the whole API with a fake runner and no browser.

## Tested

Every endpoint is unit-tested with FastAPI's `TestClient` and a fake runner: run lifecycle, status, reports, artifact download, validation rejections, background-task completion, and resilience to a failing run. The OpenAPI schema is asserted to serve.
