"""FastAPI endpoints: run lifecycle, status, reports, artifacts, validation."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from website_agent.api.app import create_app
from website_agent.api.service import AgentService
from website_agent.config.settings import PathSettings, Settings
from website_agent.state.models import RunResult


class FakeRunner:
    """Stand-in AgentRunner: records the run in an in-memory registry synchronously."""

    _registry: list[dict[str, object]] = []

    def __init__(self, settings: object) -> None: ...

    async def run(self, spec: object) -> RunResult:
        FakeRunner._registry.insert(
            0,
            {
                "run_id": "run_api_0001",
                "status": "finished",
                "stop_reason": "frontier_exhausted",
                "steps": 4,
                "cost_usd": 0.0,
                "updated_at": "2026-07-20",
            },
        )
        from datetime import UTC, datetime

        from website_agent.core.types import StopReason

        return RunResult(
            run_id="run_api_0001",
            stop_reason=StopReason.FRONTIER_EXHAUSTED,
            steps=4,
            pages_visited=2,
            findings=0,
            tokens=0,
            cost_usd=0.0,
            started_at=datetime(2026, 7, 20, tzinfo=UTC),
            finished_at=datetime(2026, 7, 20, tzinfo=UTC),
        )

    def list_runs(self) -> list[dict[str, object]]:
        return list(FakeRunner._registry)

    def close(self) -> None: ...


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    FakeRunner._registry = []
    settings = Settings(
        paths=PathSettings(
            reports_dir=tmp_path / "reports", checkpoint_db=tmp_path / "reports" / "cp.sqlite3"
        )
    )
    service = AgentService(settings, runner_factory=lambda: FakeRunner(settings))  # type: ignore[arg-type]
    app = create_app(settings=settings, service=service)
    return TestClient(app)


def test_health() -> None:
    settings = Settings()
    client = TestClient(
        create_app(settings=settings, service=AgentService(settings, lambda: FakeRunner(settings)))
    )  # type: ignore[arg-type]
    assert client.get("/health").json() == {"status": "ok"}


def test_start_run_returns_202_and_run_id(client: TestClient) -> None:
    response = client.post("/runs", json={"url": "https://ex.com/", "max_steps": 5})
    assert response.status_code == 202
    body = response.json()
    assert body["run_id"].startswith("run_")
    assert body["status"] == "running"


def test_run_completes_and_appears_in_list(client: TestClient) -> None:
    client.post("/runs", json={"url": "https://ex.com/"})
    # The background task runs on the TestClient's event loop between requests.
    for _ in range(50):
        runs = client.get("/runs").json()["runs"]
        if runs:
            break
    assert any(r["run_id"] == "run_api_0001" for r in client.get("/runs").json()["runs"])


def test_status_unknown_run_is_404(client: TestClient) -> None:
    assert client.get("/runs/nope").status_code == 404


def test_status_reports_finished_run(client: TestClient) -> None:
    client.post("/runs", json={"url": "https://ex.com/"})
    for _ in range(50):
        if client.get("/runs").json()["runs"]:
            break
    status = client.get("/runs/run_api_0001").json()
    assert status["status"] == "finished"
    assert status["steps"] == 4


def test_report_available_after_writing(client: TestClient, tmp_path: Path) -> None:
    out = tmp_path / "reports" / "run_x" / "output"
    out.mkdir(parents=True)
    (out / "qa_report.md").write_text("# QA Report: run_x")
    response = client.get("/runs/run_x/report")
    assert response.status_code == 200
    assert "QA Report: run_x" in response.text


def test_report_missing_is_404(client: TestClient) -> None:
    assert client.get("/runs/absent/report").status_code == 404


def test_artifact_download(client: TestClient, tmp_path: Path) -> None:
    out = tmp_path / "reports" / "run_y" / "output"
    out.mkdir(parents=True)
    (out / "findings.csv").write_text("severity,kind\ncritical,http_error\n")
    response = client.get("/runs/run_y/artifacts/findings.csv")
    assert response.status_code == 200
    assert "http_error" in response.text


def test_artifact_rejects_traversal(client: TestClient) -> None:
    assert client.get("/runs/run_y/artifacts/..%2f..%2fetc").status_code in (400, 404)


def test_invalid_run_id_rejected(client: TestClient) -> None:
    assert client.get("/runs/bad%2Fid/report").status_code in (400, 404)


def test_openapi_schema_is_served(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert schema["info"]["title"] == "Website AI Agent"
    assert "/runs" in schema["paths"]


def test_artifact_invalid_name_is_400(client: TestClient) -> None:
    # A syntactically invalid but route-matching artifact name hits our validation.
    assert client.get("/runs/run_z/artifacts/bad$name").status_code == 400


async def test_service_start_launches_background_task() -> None:
    settings = Settings()
    service = AgentService(settings, runner_factory=lambda: FakeRunner(settings))  # type: ignore[arg-type]
    from website_agent.api.schemas import StartRunRequest

    run_id = service.start(StartRunRequest(url="https://ex.com/"))
    assert run_id.startswith("run_")
    # A just-started run with no registry row yet still reports as running.
    assert service.status(run_id) is not None
    # Let the background task run to completion.
    await asyncio.sleep(0.05)
    assert service.active_count() == 0
    service.close()


async def test_service_survives_a_failing_run() -> None:
    settings = Settings()

    class BoomRunner:
        def __init__(self, settings: object) -> None: ...

        async def run(self, spec: object) -> None:
            raise RuntimeError("run blew up")

        def list_runs(self) -> list[dict[str, object]]:
            return []

        def close(self) -> None: ...

    service = AgentService(settings, runner_factory=lambda: BoomRunner(settings))  # type: ignore[arg-type]
    from website_agent.api.schemas import StartRunRequest

    service.start(StartRunRequest(url="https://ex.com/"))
    await asyncio.sleep(0.05)
    # A failed run is logged and cleaned up, not propagated; the server stays healthy.
    assert service.active_count() == 0
    service.close()
