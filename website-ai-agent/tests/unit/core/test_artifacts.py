"""File artifact store: placement, references, safety."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from website_agent.core.artifacts import FileArtifactStore
from website_agent.core.clock import FixedClock
from website_agent.core.errors import AgentError


@pytest.fixture
def store(tmp_path: Path, fixed_clock: FixedClock) -> FileArtifactStore:
    return FileArtifactStore(tmp_path, "run_test_000001", fixed_clock)


def test_creates_run_directory(tmp_path: Path, store: FileArtifactStore) -> None:
    assert store.run_dir == tmp_path / "run_test_000001"
    assert store.run_dir.is_dir()


def test_bytes_round_trip_with_reference(store: FileArtifactStore) -> None:
    ref = store.save_bytes("screenshots", "step_0001.png", b"\x89PNG-fake")
    assert ref.kind == "screenshots"
    assert ref.relpath == "screenshots/step_0001.png"
    assert ref.size_bytes == 9
    assert store.path_for(ref).read_bytes() == b"\x89PNG-fake"


def test_text_and_json_round_trip(store: FileArtifactStore) -> None:
    text_ref = store.save_text("console", "events.jsonl", "line1\nline2")
    assert store.path_for(text_ref).read_text() == "line1\nline2"

    json_ref = store.save_json("qa", "findings.json", {"b": 1, "a": [1, 2]})
    loaded = json.loads(store.path_for(json_ref).read_text())
    assert loaded == {"a": [1, 2], "b": 1}


def test_json_serializes_non_json_types_via_str(store: FileArtifactStore) -> None:
    ref = store.save_json("meta", "run.json", {"path": Path("/x/y")})
    assert json.loads(store.path_for(ref).read_text()) == {"path": "/x/y"}


@pytest.mark.parametrize(
    ("kind", "name"),
    [
        ("../escape", "f.txt"),
        ("ok", "../../etc/passwd"),
        ("ok", "a/b.txt"),
        ("with space", "f.txt"),
        ("ok", ""),
    ],
)
def test_rejects_unsafe_path_segments(store: FileArtifactStore, kind: str, name: str) -> None:
    with pytest.raises(AgentError, match="unsafe artifact path segment"):
        store.save_text(kind, name, "data")


def test_artifacts_never_land_outside_run_dir(store: FileArtifactStore) -> None:
    ref = store.save_text("snapshots", "s1.json", "{}")
    resolved = store.path_for(ref).resolve()
    assert resolved.is_relative_to(store.run_dir.resolve())
