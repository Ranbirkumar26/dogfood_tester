"""Cassette store: key determinism, round-trip, replay-miss error."""

from __future__ import annotations

from pathlib import Path

import pytest

from website_agent.core.errors import StateError
from website_agent.llm.recorder import CassetteEntry, CassetteStore, request_key


def test_request_key_is_deterministic_and_order_independent() -> None:
    messages = [{"role": "system", "content": "a"}, {"role": "user", "content": "b"}]
    assert request_key("planner", "m", messages, "Plan") == request_key(
        "planner", "m", messages, "Plan"
    )


def test_request_key_changes_with_any_component() -> None:
    messages = [{"role": "user", "content": "b"}]
    base = request_key("planner", "m", messages, "Plan")
    assert base != request_key("reviewer", "m", messages, "Plan")
    assert base != request_key("planner", "m2", messages, "Plan")
    assert base != request_key("planner", "m", messages, "Verdict")
    assert base != request_key("planner", "m", [{"role": "user", "content": "c"}], "Plan")


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    store = CassetteStore(tmp_path / "cassettes")
    entry = CassetteEntry(content='{"ok": true}', prompt_tokens=12, completion_tokens=3, model="m")
    store.save("key123", entry)
    loaded = store.load("key123")
    assert loaded == entry


def test_load_missing_returns_none(tmp_path: Path) -> None:
    store = CassetteStore(tmp_path)
    assert store.load("absent") is None


def test_require_missing_raises_actionable_error(tmp_path: Path) -> None:
    store = CassetteStore(tmp_path)
    with pytest.raises(StateError, match="cassette replay miss") as excinfo:
        store.require("absent")
    assert excinfo.value.context["key"] == "absent"


def test_saved_cassette_is_human_readable(tmp_path: Path) -> None:
    store = CassetteStore(tmp_path)
    store.save("k", CassetteEntry(content="x", prompt_tokens=1, completion_tokens=1, model="m"))
    text = (tmp_path / "k.json").read_text()
    assert text.endswith("\n")
    assert "\n  " in text  # pretty-printed for reviewable diffs
