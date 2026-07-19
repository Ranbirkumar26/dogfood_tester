"""BrowserManager: Playwright and browser process lifecycle.

Design rationale: exactly one component owns launching, relaunching, and stopping the
browser. The relaunch-once policy implements failure class F2
(docs/architecture/failure-recovery.md): a crashed browser gets one fresh process per run;
a second crash escalates to FatalError because a repeatedly dying browser signals an
environment problem retries will not fix. Sessions are created here so context options
(viewport, storage state, HTTP credentials, timeouts) are applied uniformly.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from playwright.async_api import Browser, Playwright, async_playwright

from website_agent.browser.errors_map import map_playwright_error
from website_agent.browser.session import BrowserSession
from website_agent.config.settings import BrowserSettings
from website_agent.core.artifacts import ArtifactStore
from website_agent.core.clock import Clock
from website_agent.core.errors import FatalError
from website_agent.logging import get_logger

log = get_logger("browser.manager")


class BrowserManager:
    """Owns the Playwright driver and one Chromium process; builds sessions on it."""

    def __init__(self, settings: BrowserSettings) -> None:
        self._settings = settings
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._relaunches = 0

    async def __aenter__(self) -> BrowserManager:
        await self.start()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.stop()

    async def start(self) -> None:
        """Start the driver and launch Chromium. Idempotent while running."""
        if self._browser is not None and self._browser.is_connected():
            return
        try:
            if self._playwright is None:
                self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=self._settings.headless)
        except Exception as exc:
            raise FatalError(
                "browser launch failed; is chromium installed? (playwright install chromium)",
                context={"detail": str(exc)},
            ) from exc
        log.info("browser_started", headless=self._settings.headless)

    async def stop(self) -> None:
        """Close the browser and stop the driver. Safe to call twice."""
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception as exc:  # noqa: BLE001 - closing a dead browser is fine
                log.warning("browser_close_failed", reason=str(exc))
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
        log.info("browser_stopped")

    async def relaunch(self) -> None:
        """Replace a crashed browser process, once per run (failure class F2).

        Raises:
            FatalError: on the second relaunch request in this manager's lifetime.
        """
        if self._relaunches >= 1:
            raise FatalError(
                "browser crashed twice; giving up", context={"relaunches": self._relaunches}
            )
        self._relaunches += 1
        log.warning("browser_relaunching", relaunch=self._relaunches)
        if self._browser is not None:
            with contextlib.suppress(Exception):  # it is likely already dead
                await self._browser.close()
            self._browser = None
        await self.start()

    async def new_session(
        self,
        clock: Clock,
        store: ArtifactStore,
        *,
        storage_state: Path | dict[str, Any] | None = None,
        http_credentials: dict[str, str] | None = None,
    ) -> BrowserSession:
        """Create a session on a fresh context.

        Args:
            clock: time source for observations and artifacts.
            store: the run's artifact store.
            storage_state: Playwright storage state (path or dict) for authenticated
                sessions and resume (design D12: credentials never pass through prompts).
            http_credentials: HTTP basic auth, e.g. ``{"username": ..., "password": ...}``.
        """
        if self._browser is None or not self._browser.is_connected():
            raise FatalError("browser not started; call start() first")
        try:
            context = await self._browser.new_context(
                viewport={
                    "width": self._settings.viewport_width,
                    "height": self._settings.viewport_height,
                },
                storage_state=storage_state,  # type: ignore[arg-type]
                http_credentials=http_credentials,  # type: ignore[arg-type]
            )
            context.set_default_timeout(self._settings.action_timeout_ms)
            context.set_default_navigation_timeout(self._settings.nav_timeout_ms)
        except Exception as exc:
            raise map_playwright_error(exc, action="new_context") from exc
        session = await BrowserSession.create(context, self._settings, clock, store)
        log.info("session_created", authenticated=storage_state is not None)
        return session
