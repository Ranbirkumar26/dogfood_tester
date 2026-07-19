"""Screenshot manager: sequencing, tag sanitization, graceful failure."""

from __future__ import annotations

from pathlib import Path

import pytest

from website_agent.browser.screenshots import ScreenshotManager
from website_agent.core.artifacts import FileArtifactStore
from website_agent.core.clock import FixedClock

PNG_BYTES = b"\x89PNG\r\n\x1a\nfake"


class FakePage:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    async def screenshot(self) -> bytes:
        if self.fail:
            raise RuntimeError("page crashed mid-capture")
        return PNG_BYTES


@pytest.fixture
def store(tmp_path: Path, fixed_clock: FixedClock) -> FileArtifactStore:
    return FileArtifactStore(tmp_path, "run_shots", fixed_clock)


async def test_capture_sequences_and_persists(store: FileArtifactStore) -> None:
    manager = ScreenshotManager(store)
    first = await manager.capture(FakePage(), "step_0001")
    second = await manager.capture(FakePage(), "step_0002")
    assert first is not None
    assert second is not None
    assert first.relpath == "screenshots/s0001_step_0001.png"
    assert second.relpath == "screenshots/s0002_step_0002.png"
    assert store.path_for(first).read_bytes() == PNG_BYTES
    assert manager.count == 2


async def test_capture_sanitizes_hostile_tags(store: FileArtifactStore) -> None:
    manager = ScreenshotManager(store)
    ref = await manager.capture(FakePage(), "../etc/passwd step?")
    assert ref is not None
    # Dots are allowed characters; separators collapse to dashes, so no path segment
    # can ever be ".." and the store's safe-name check accepts the result.
    assert ref.relpath == "screenshots/s0001_..-etc-passwd-step.png"


async def test_capture_failure_returns_none_and_keeps_counting(store: FileArtifactStore) -> None:
    manager = ScreenshotManager(store)
    assert await manager.capture(FakePage(fail=True), "step_0001") is None
    ok = await manager.capture(FakePage(), "step_0002")
    assert ok is not None
    assert ok.relpath == "screenshots/s0002_step_0002.png"
    assert manager.count == 2
