"""Fake browser session for executor unit tests (no real Playwright)."""

from __future__ import annotations

from datetime import UTC, datetime

from website_agent.browser.models import ObservationBundle, PageSnapshot
from website_agent.browser.session import ElementUnavailableError
from website_agent.core.errors import BrowserTransientError
from website_agent.core.types import ArtifactRef

NOW = datetime(2026, 7, 20, tzinfo=UTC)


class FakeScreenshots:
    def __init__(self) -> None:
        self.count = 0

    async def capture(self, page: object, tag: str) -> ArtifactRef:
        self.count += 1
        return ArtifactRef(
            kind="screenshots",
            name=f"{tag}.png",
            relpath=f"screenshots/{tag}.png",
            size_bytes=10,
            created_at=NOW,
        )


class FakePage:
    def __init__(self, url: str) -> None:
        self.url = url


class FakeSession:
    """Implements only the surface the executor uses; scriptable failures per action."""

    def __init__(
        self,
        url: str = "https://ex.com/",
        *,
        snapshot: PageSnapshot | None = None,
        fail: dict[str, Exception] | None = None,
        navigate_to: str | None = None,
    ) -> None:
        self._page = FakePage(url)
        self._snapshot = snapshot
        self._fail = fail or {}
        self._navigate_to = navigate_to
        self.screenshots = FakeScreenshots()
        self.calls: list[str] = []
        self._drained = False

    @property
    def page(self) -> FakePage:
        return self._page

    def _maybe_fail(self, action: str) -> None:
        if action in self._fail:
            raise self._fail[action]

    async def click(self, element_id: str) -> None:
        self.calls.append(f"click:{element_id}")
        self._maybe_fail("click")
        if self._navigate_to:
            self._page.url = self._navigate_to

    async def fill(self, element_id: str, value: str) -> None:
        self.calls.append(f"fill:{element_id}:{value}")
        self._maybe_fail("fill")

    async def select_option(self, element_id: str, value: str) -> None:
        self.calls.append(f"select:{element_id}:{value}")
        self._maybe_fail("select")

    async def goto(self, url: str) -> int | None:
        self.calls.append(f"goto:{url}")
        self._maybe_fail("goto")
        self._page.url = url
        return 200

    async def go_back(self) -> None:
        self.calls.append("go_back")
        self._maybe_fail("go_back")

    async def scroll(self, delta_y: int) -> None:
        self.calls.append(f"scroll:{delta_y}")
        self._maybe_fail("scroll")

    async def wait_for_load(self, state: str = "load") -> None:
        self.calls.append(f"wait:{state}")
        self._maybe_fail("wait")

    async def snapshot(self) -> PageSnapshot:
        self.calls.append("snapshot")
        self._maybe_fail("snapshot")
        if self._snapshot is None:
            raise BrowserTransientError("no snapshot configured")
        return self._snapshot.model_copy(update={"url": self._page.url})

    def drain_observations(self, step_id: str) -> ObservationBundle:
        self._drained = True
        return ObservationBundle(step_id=step_id)


def make_snapshot(url: str = "https://ex.com/next") -> PageSnapshot:
    from website_agent.browser.models import ElementRecord

    return PageSnapshot(
        url=url,
        title="Next",
        captured_at=NOW,
        elements=[ElementRecord(element_id="e1", tag="a", role="link", selectors=["css=a"])],
    )


__all__ = ["ElementUnavailableError", "FakeSession", "make_snapshot"]
