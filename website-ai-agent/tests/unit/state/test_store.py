"""Checkpoint store: save/load, resume-latest, run registry, schema-version guard."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from website_agent.browser.models import ElementRecord, PageSnapshot
from website_agent.core.errors import StateError
from website_agent.core.types import GoalMode, StopReason
from website_agent.state.agent_state import AgentState
from website_agent.state.models import Budgets, Counters, GoalSpec, RunPolicy
from website_agent.state.store import CheckpointStore

NOW = datetime(2026, 7, 20, tzinfo=UTC)


def _state(run_id: str = "run_test", steps: int = 0, stop: StopReason | None = None) -> AgentState:
    snapshot = PageSnapshot(
        url="https://ex.com/",
        title="Home",
        captured_at=NOW,
        elements=[ElementRecord(element_id="e1", tag="a", role="link", selectors=["css=a"])],
    )
    return AgentState(
        run_id=run_id,
        goal=GoalSpec(mode=GoalMode.EXPLORE, start_url="https://ex.com/"),
        policy=RunPolicy(),
        budgets=Budgets(
            max_steps=50,
            max_tokens=1000,
            max_usd=1.0,
            max_wall_seconds=600,
            max_consecutive_failures=3,
        ),
        counters=Counters(steps=steps, usd=0.02),
        current_snapshot=snapshot,
        stop_reason=stop,
    )


@pytest.fixture
def store(tmp_path: Path) -> CheckpointStore:
    with CheckpointStore(tmp_path / "checkpoints.sqlite3") as store:
        yield store


def test_save_and_load_latest_round_trip(store: CheckpointStore) -> None:
    store.save(_state(steps=1))
    store.save(_state(steps=2))
    loaded = store.load_latest("run_test")
    assert loaded.counters.steps == 2
    assert loaded.current_snapshot is not None
    assert loaded.current_snapshot.url == "https://ex.com/"
    assert store.checkpoint_count("run_test") == 2


def test_full_state_survives_serialization(store: CheckpointStore) -> None:
    original = _state(steps=5)
    store.save(original)
    assert store.load_latest("run_test") == original


def test_load_missing_run_raises(store: CheckpointStore) -> None:
    with pytest.raises(StateError, match="no checkpoint"):
        store.load_latest("absent")


def test_run_registry_tracks_status_and_totals(store: CheckpointStore) -> None:
    store.save(_state(run_id="run_a", steps=3))
    store.save(_state(run_id="run_b", steps=7, stop=StopReason.GOAL_MET))
    runs = {r["run_id"]: r for r in store.list_runs()}
    assert runs["run_a"]["status"] == "running"
    assert runs["run_b"]["status"] == "finished"
    assert runs["run_b"]["stop_reason"] == "goal_met"
    assert runs["run_b"]["steps"] == 7


def test_schema_version_mismatch_is_rejected(tmp_path: Path) -> None:
    db = tmp_path / "cp.sqlite3"
    with CheckpointStore(db) as store:
        store.save(_state(steps=1))
        # Simulate a checkpoint written by a future, incompatible schema version.
        store._conn.execute("UPDATE checkpoints SET schema_version = 999 WHERE run_id = 'run_test'")
        store._conn.commit()
        with pytest.raises(StateError, match="schema version mismatch"):
            store.load_latest("run_test")


def test_reopening_db_preserves_checkpoints(tmp_path: Path) -> None:
    db = tmp_path / "cp.sqlite3"
    with CheckpointStore(db) as store:
        store.save(_state(steps=4))
    # A new process (new store on the same file) can resume: durability on disk.
    with CheckpointStore(db) as reopened:
        assert reopened.load_latest("run_test").counters.steps == 4
