"""Reporting engine: writes all outputs, degrades on a failing renderer."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.unit.reporting._inputs import sample_inputs

from website_agent.core.artifacts import FileArtifactStore
from website_agent.core.clock import FixedClock
from website_agent.reporting.engine import ReportingEngine


@pytest.fixture
def store(tmp_path: Path, fixed_clock: FixedClock) -> FileArtifactStore:
    return FileArtifactStore(tmp_path, "run_report", fixed_clock)


def test_generate_writes_all_outputs(store: FileArtifactStore) -> None:
    written = ReportingEngine(store).generate(sample_inputs())
    expected = {
        "qa_report.md",
        "documentation.md",
        "flow.mmd",
        "flow.dot",
        "report.json",
        "findings.csv",
    }
    assert set(written) == expected
    for name in expected:
        assert store.path_for(written[name]).is_file()
    assert "# QA Report" in store.path_for(written["qa_report.md"]).read_text()


def test_one_failing_output_does_not_lose_the_rest(store: FileArtifactStore) -> None:
    engine = ReportingEngine(store)
    original = store.save_text
    calls = {"n": 0}

    def flaky(kind: str, name: str, text: str):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if name == "flow.dot":
            raise OSError("disk full")
        return original(kind, name, text)

    store.save_text = flaky  # type: ignore[method-assign]
    written = engine.generate(sample_inputs())
    assert "flow.dot" not in written
    assert "qa_report.md" in written  # others still produced
