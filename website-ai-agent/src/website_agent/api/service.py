"""AgentService: background run execution and status for the API.

Design rationale: HTTP handlers must return immediately, but a run takes minutes, so the
service launches each run as a tracked asyncio task and reports status from the persisted run
registry (which the graph updates every step). This is the one component the API layer holds;
handlers stay thin (docs/architecture/components.md, rule 5). The service is constructed with a
runner factory so tests can inject a fake runner and drive the whole API without a browser.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from urllib.parse import urlsplit

from website_agent.agent.runner import AgentRunner, RunSpec
from website_agent.api.schemas import RunStatus, StartRunRequest
from website_agent.config.settings import Settings
from website_agent.core.clock import SystemClock
from website_agent.core.ids import generate_run_id
from website_agent.logging import get_logger
from website_agent.state.models import Budgets, GoalSpec, RunPolicy

log = get_logger("api.service")

RunnerFactory = Callable[[], AgentRunner]


class AgentService:
    """Starts runs in the background and reports their status."""

    def __init__(self, settings: Settings, runner_factory: RunnerFactory | None = None) -> None:
        self._settings = settings
        self._runner_factory = runner_factory or (lambda: AgentRunner(settings))
        self._registry_runner = self._runner_factory()
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def start(self, request: StartRunRequest) -> str:
        """Launch a run in the background; returns its run id immediately."""
        run_id = generate_run_id(SystemClock())
        spec = self._build_spec(request)
        self._tasks[run_id] = asyncio.create_task(self._execute(run_id, spec))
        log.info("api_run_started", run_id=run_id, url=request.url, mode=request.mode.value)
        return run_id

    async def _execute(self, run_id: str, spec: RunSpec) -> None:
        runner = self._runner_factory()
        try:
            await runner.run(spec)
        except Exception as exc:  # noqa: BLE001 - a failed run must not crash the server
            log.error("api_run_failed", run_id=run_id, reason=str(exc), exc_info=True)
        finally:
            runner.close()
            self._tasks.pop(run_id, None)

    def status(self, run_id: str) -> RunStatus | None:
        """Current status of a run from the registry, or None if unknown."""
        for row in self._registry_runner.list_runs():
            if row["run_id"] == run_id:
                return _to_status(row)
        # A just-started run may not have its first checkpoint yet; report it as running.
        if run_id in self._tasks:
            return RunStatus(run_id=run_id, status="running")
        return None

    def list_runs(self) -> list[RunStatus]:
        """All recorded runs, newest first."""
        return [_to_status(row) for row in self._registry_runner.list_runs()]

    def active_count(self) -> int:
        """Number of runs currently executing (diagnostics)."""
        return len(self._tasks)

    def close(self) -> None:
        """Release the registry runner's resources."""
        self._registry_runner.close()

    def _build_spec(self, request: StartRunRequest) -> RunSpec:
        b = self._settings.budgets
        budgets = Budgets(
            max_steps=request.max_steps or b.max_steps,
            max_tokens=b.max_tokens,
            max_usd=request.max_usd if request.max_usd is not None else b.max_usd,
            max_wall_seconds=b.max_wall_seconds,
            max_consecutive_failures=b.max_consecutive_failures,
        )
        allowed = (
            frozenset({urlsplit(request.url).netloc.lower()})
            if request.same_domain
            else frozenset()
        )
        return RunSpec(
            goal=GoalSpec(mode=request.mode, start_url=request.url),
            policy=RunPolicy(allowed_domains=allowed),
            budgets=budgets,
        )


def _to_status(row: dict[str, object]) -> RunStatus:
    return RunStatus(
        run_id=str(row["run_id"]),
        status=str(row["status"]),
        stop_reason=(str(row["stop_reason"]) if row.get("stop_reason") else None),
        steps=int(str(row.get("steps", 0) or 0)),
        cost_usd=float(str(row.get("cost_usd", 0.0) or 0.0)),
        updated_at=(str(row["updated_at"]) if row.get("updated_at") else None),
    )
