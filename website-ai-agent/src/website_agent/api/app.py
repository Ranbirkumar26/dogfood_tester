"""FastAPI application: REST surface over the AgentService.

Design rationale: handlers are thin (docs/architecture/components.md, rule 5). They validate
input via the schema models, call the service, and translate outcomes to HTTP. Long runs
execute in the background (the service owns the tasks) and callers poll status, so no request
blocks for minutes. Report and artifact reads serve files from the run's output directory with
path-traversal protection. Swagger UI is served at /docs by FastAPI.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse

from website_agent.api.schemas import RunAccepted, RunList, RunStatus, StartRunRequest
from website_agent.api.service import AgentService
from website_agent.config.settings import Settings, load_settings

_ARTIFACT_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


def create_app(settings: Settings | None = None, service: AgentService | None = None) -> FastAPI:
    """Build the FastAPI app. Inject a service for tests; otherwise one is built from settings."""
    resolved_settings = settings or load_settings()
    agent_service = service or AgentService(resolved_settings)

    app = FastAPI(
        title="Website AI Agent",
        version="0.1.0",
        summary="Autonomous website exploration and QA agent.",
    )

    # Handlers close over agent_service and resolved_settings directly: both are already in
    # scope here, so FastAPI dependency injection would add ceremony without benefit.

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/runs", response_model=RunAccepted, status_code=202)
    async def start_run(request: StartRunRequest) -> RunAccepted:
        # Async so the service can schedule the background run on the event loop.
        run_id = agent_service.start(request)
        return RunAccepted(run_id=run_id, status="running")

    @app.get("/runs", response_model=RunList)
    def list_runs() -> RunList:
        return RunList(runs=agent_service.list_runs())

    @app.get("/runs/{run_id}", response_model=RunStatus)
    def run_status(run_id: str) -> RunStatus:
        status = agent_service.status(run_id)
        if status is None:
            raise HTTPException(status_code=404, detail="run not found")
        return status

    @app.get("/runs/{run_id}/report", response_class=PlainTextResponse)
    def run_report(run_id: str) -> PlainTextResponse:
        path = _run_output(resolved_settings, run_id) / "qa_report.md"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="report not available")
        return PlainTextResponse(path.read_text())

    @app.get("/runs/{run_id}/artifacts/{name}")
    def run_artifact(run_id: str, name: str) -> FileResponse:
        if not _ARTIFACT_NAME.match(name):
            raise HTTPException(status_code=400, detail="invalid artifact name")
        path = _run_output(resolved_settings, run_id) / name
        if not path.is_file():
            raise HTTPException(status_code=404, detail="artifact not found")
        return FileResponse(path)

    return app


def _run_output(settings: Settings, run_id: str) -> Path:
    if not _ARTIFACT_NAME.match(run_id):
        raise HTTPException(status_code=400, detail="invalid run id")
    return settings.paths.reports_dir / run_id / "output"
