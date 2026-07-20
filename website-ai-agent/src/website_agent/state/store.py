"""Checkpoint store: durable AgentState persistence with resume.

Design rationale (design D8): SQLite gives zero-infrastructure durability that works on a
laptop and in CI. This is the project's own checkpoint store used for the run index and
for state save/load in tests and the runner; Phase 9 additionally wires LangGraph's
SqliteSaver for in-graph checkpointing, and this store remains the source of truth for the
run registry (list, status, totals) the CLI and API read. Checkpoints are keyed by
(run_id, step) so the full history is inspectable and resume can pick the latest. Schema
version is checked on load so an incompatible checkpoint fails loudly rather than
deserializing into wrong-shaped state.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from website_agent.core.errors import StateError
from website_agent.logging import get_logger
from website_agent.state.agent_state import STATE_SCHEMA_VERSION, AgentState

log = get_logger("state.store")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS checkpoints (
    run_id TEXT NOT NULL,
    step INTEGER NOT NULL,
    schema_version INTEGER NOT NULL,
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (run_id, step)
);
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    stop_reason TEXT,
    steps INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class CheckpointStore:
    """SQLite-backed AgentState checkpoints plus a run registry."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def save(self, state: AgentState) -> None:
        """Persist a checkpoint at the state's current step and upsert the run row."""
        self._conn.execute(
            "INSERT OR REPLACE INTO checkpoints "
            "(run_id, step, schema_version, state_json) VALUES (?, ?, ?, ?)",
            (
                state.run_id,
                state.counters.steps,
                state.schema_version,
                state.model_dump_json(),
            ),
        )
        status = "finished" if state.stop_reason is not None else "running"
        self._conn.execute(
            "INSERT INTO runs (run_id, status, stop_reason, steps, cost_usd, updated_at) "
            "VALUES (?, ?, ?, ?, ?, datetime('now')) "
            "ON CONFLICT(run_id) DO UPDATE SET "
            "status=excluded.status, stop_reason=excluded.stop_reason, "
            "steps=excluded.steps, cost_usd=excluded.cost_usd, updated_at=datetime('now')",
            (
                state.run_id,
                status,
                state.stop_reason.value if state.stop_reason else None,
                state.counters.steps,
                state.counters.usd,
            ),
        )
        self._conn.commit()

    def load_latest(self, run_id: str) -> AgentState:
        """Most recent checkpoint for a run.

        Raises:
            StateError: no checkpoint for the run, or a schema-version mismatch.
        """
        row = self._conn.execute(
            "SELECT schema_version, state_json FROM checkpoints "
            "WHERE run_id = ? ORDER BY step DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        if row is None:
            raise StateError("no checkpoint for run", context={"run_id": run_id})
        version, state_json = row
        if version != STATE_SCHEMA_VERSION:
            raise StateError(
                "checkpoint schema version mismatch; cannot resume",
                context={"run_id": run_id, "found": version, "expected": STATE_SCHEMA_VERSION},
            )
        return AgentState.model_validate_json(state_json)

    def list_runs(self) -> list[dict[str, object]]:
        """Run registry rows, newest first (for CLI/API listing)."""
        cursor = self._conn.execute(
            "SELECT run_id, status, stop_reason, steps, cost_usd, updated_at "
            "FROM runs ORDER BY updated_at DESC"
        )
        columns = [c[0] for c in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]

    def checkpoint_count(self, run_id: str) -> int:
        """How many checkpoints exist for a run (diagnostics and tests)."""
        count = self._conn.execute(
            "SELECT COUNT(*) FROM checkpoints WHERE run_id = ?", (run_id,)
        ).fetchone()[0]
        return int(count)

    def close(self) -> None:
        """Close the database connection. Safe to call twice."""
        self._conn.close()

    def __enter__(self) -> CheckpointStore:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
