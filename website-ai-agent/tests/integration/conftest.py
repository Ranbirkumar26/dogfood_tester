"""Integration fixtures: local fixture-site server plus a real headless browser session.

No test in this directory may touch the public internet (design D9); everything runs
against 127.0.0.1.
"""

from __future__ import annotations

import threading
from collections.abc import AsyncIterator, Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from website_agent.browser.manager import BrowserManager
from website_agent.browser.session import BrowserSession
from website_agent.config.settings import BrowserSettings
from website_agent.core.artifacts import FileArtifactStore
from website_agent.core.clock import SystemClock

FIXTURE_SITES = Path(__file__).parent.parent / "fixtures" / "sites"


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass  # request logging would drown pytest output


def _serve(directory: Path) -> Iterator[str]:
    handler = partial(_QuietHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.fixture(scope="session")
def static_basic_url() -> Iterator[str]:
    yield from _serve(FIXTURE_SITES / "static-basic")


@pytest.fixture
def browser_settings() -> BrowserSettings:
    # Tight timeouts keep failing integration tests fast without flaking healthy ones.
    return BrowserSettings(headless=True, action_timeout_ms=5_000, nav_timeout_ms=10_000)


@pytest.fixture
async def manager(browser_settings: BrowserSettings) -> AsyncIterator[BrowserManager]:
    async with BrowserManager(browser_settings) as mgr:
        yield mgr


@pytest.fixture
async def session(manager: BrowserManager, tmp_path: Path) -> AsyncIterator[BrowserSession]:
    clock = SystemClock()
    store = FileArtifactStore(tmp_path, "run_integration", clock)
    browser_session = await manager.new_session(clock, store)
    yield browser_session
    await browser_session.close()
