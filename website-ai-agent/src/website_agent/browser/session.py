"""BrowserSession: the single facade over a Playwright context.

Design rationale (design D5): roles and tools never touch Playwright types; this facade
owns pages, observers, downloads, dialogs, popups, storage state, and the element-ID to
locator resolution that makes hallucinated selectors impossible (design D6). Every action
runs under the browser-transient retry policy with selectors re-resolved per attempt, and
every Playwright exception is classified into the failure taxonomy before it escapes.
Dialogs are auto-dismissed and recorded: an unhandled dialog would block the event loop,
and the record preserves the signal for the reviewer and QA.
"""

from __future__ import annotations

import pathlib
import re
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from playwright.async_api import BrowserContext, Locator, Page

from website_agent.browser.errors_map import map_playwright_error
from website_agent.browser.extraction import extract_snapshot
from website_agent.browser.models import (
    DialogRecord,
    DownloadRecord,
    ObservationBundle,
    PageSnapshot,
    PopupRecord,
)
from website_agent.browser.observers import ConsoleObserver, NetworkObserver
from website_agent.browser.screenshots import ScreenshotManager
from website_agent.config.settings import BrowserSettings
from website_agent.core.artifacts import ArtifactStore
from website_agent.core.clock import Clock
from website_agent.core.errors import BrowserTransientError
from website_agent.core.retry import BROWSER_TRANSIENT_POLICY, RetryPolicy, retry_async
from website_agent.core.types import ArtifactRef
from website_agent.logging import get_logger

T = TypeVar("T")

log = get_logger("browser.session")

_FILENAME_SANITIZER = re.compile(r"[^A-Za-z0-9._-]+")


class ElementUnavailableError(BrowserTransientError):
    """Element ID absent from the current snapshot or no candidate selector resolved
    uniquely. Transient by design: a fresh snapshot plus replan usually recovers."""


class BrowserSession:
    """One browser context: pages, actions, observation capture, state.

    Build via :meth:`create` (construction needs awaits). Close via :meth:`close`.
    """

    def __init__(
        self,
        context: BrowserContext,
        page: Page,
        settings: BrowserSettings,
        clock: Clock,
        store: ArtifactStore,
        screenshots: ScreenshotManager,
        retry_policy: RetryPolicy,
    ) -> None:
        self._context = context
        self._pages: list[Page] = [page]
        self._active_index = 0
        self._settings = settings
        self._clock = clock
        self._store = store
        self.screenshots = screenshots
        self._retry_policy = retry_policy
        self._snapshot: PageSnapshot | None = None
        self._console = ConsoleObserver(clock)
        self._network = NetworkObserver(clock)
        self._downloads: list[DownloadRecord] = []
        self._dialogs: list[DialogRecord] = []
        self._popups: list[PopupRecord] = []
        self._closed = False

        self._wire_page(page)
        context.on("page", self._on_new_page)

    @classmethod
    async def create(
        cls,
        context: BrowserContext,
        settings: BrowserSettings,
        clock: Clock,
        store: ArtifactStore,
        *,
        retry_policy: RetryPolicy = BROWSER_TRANSIENT_POLICY,
    ) -> BrowserSession:
        """Open the initial page and wire all capture on a fresh context."""
        page = await context.new_page()
        return cls(
            context=context,
            page=page,
            settings=settings,
            clock=clock,
            store=store,
            screenshots=ScreenshotManager(store),
            retry_policy=retry_policy,
        )

    # ------------------------------------------------------------------ pages

    @property
    def page(self) -> Page:
        """The active page. Falls back to the last open page if the active one closed."""
        self._prune_closed_pages()
        if not self._pages:
            raise BrowserTransientError("no open pages in session")
        return self._pages[self._active_index]

    @property
    def current_snapshot(self) -> PageSnapshot | None:
        """The most recent snapshot taken via :meth:`snapshot`, if any."""
        return self._snapshot

    def pages_info(self) -> list[tuple[int, str]]:
        """(index, url) for every open page; index feeds :meth:`switch_tab`."""
        self._prune_closed_pages()
        return [(i, p.url) for i, p in enumerate(self._pages)]

    def switch_tab(self, index: int) -> None:
        """Make the page at ``index`` active. Snapshot is invalidated: new page, new world."""
        self._prune_closed_pages()
        if not 0 <= index < len(self._pages):
            raise ElementUnavailableError(
                "no such tab", context={"index": index, "open_tabs": len(self._pages)}
            )
        self._active_index = index
        self._snapshot = None

    def _prune_closed_pages(self) -> None:
        before = self._pages[self._active_index] if self._pages else None
        self._pages = [p for p in self._pages if not p.is_closed()]
        if before in self._pages:
            self._active_index = self._pages.index(before)
        else:
            self._active_index = max(0, len(self._pages) - 1)

    def _on_new_page(self, page: Page) -> None:
        self._wire_page(page)
        self._pages.append(page)
        self._popups.append(
            PopupRecord(
                url=page.url or "about:blank",
                page_index=len(self._pages) - 1,
                at=self._clock.now(),
            )
        )
        log.info("popup_opened", page_index=len(self._pages) - 1)

    def _wire_page(self, page: Page) -> None:
        self._console.attach(page)
        self._network.attach(page)
        page.on("download", self._on_download)
        page.on("dialog", self._on_dialog)

    async def _on_download(self, download: Any) -> None:
        try:
            temp_path = await download.path()
            data = pathlib.Path(temp_path).read_bytes()
            name = _FILENAME_SANITIZER.sub("-", download.suggested_filename) or "download.bin"
            ref = self._store.save_bytes("downloads", name, data)
            self._downloads.append(
                DownloadRecord(
                    suggested_name=download.suggested_filename,
                    source_url=download.url,
                    relpath=ref.relpath,
                    at=self._clock.now(),
                )
            )
            log.info("download_saved", name=name, bytes=len(data))
        except Exception as exc:  # noqa: BLE001 - capture must not break the run
            log.warning("download_capture_failed", reason=str(exc))

    async def _on_dialog(self, dialog: Any) -> None:
        # beforeunload must be accepted to let navigation proceed; everything else is
        # dismissed so the page cannot park the agent behind a modal.
        action = "accepted" if dialog.type == "beforeunload" else "dismissed"
        try:
            if action == "accepted":
                await dialog.accept()
            else:
                await dialog.dismiss()
            self._dialogs.append(
                DialogRecord(
                    kind=dialog.type,
                    message=dialog.message,
                    action=action,
                    at=self._clock.now(),
                )
            )
            log.info("dialog_handled", kind=dialog.type, action=action)
        except Exception as exc:  # noqa: BLE001
            log.warning("dialog_handling_failed", reason=str(exc))

    # ---------------------------------------------------------------- actions

    async def goto(self, url: str) -> int | None:
        """Navigate the active page. Returns the main response status (None for
        same-document navigations). Invalidates the snapshot."""

        async def attempt() -> int | None:
            try:
                response = await self.page.goto(
                    url, timeout=self._settings.nav_timeout_ms, wait_until="load"
                )
            except Exception as exc:
                raise map_playwright_error(exc, action=f"goto {url}") from exc
            self._snapshot = None
            return response.status if response else None

        return await self._retrying("goto", attempt)

    async def go_back(self) -> None:
        """History back on the active page. Invalidates the snapshot."""

        async def attempt() -> None:
            try:
                await self.page.go_back(timeout=self._settings.nav_timeout_ms)
            except Exception as exc:
                raise map_playwright_error(exc, action="go_back") from exc
            self._snapshot = None

        await self._retrying("go_back", attempt)

    async def click(self, element_id: str) -> None:
        """Click an inventory element; selector re-resolved on every retry attempt."""
        await self._element_action(
            "click",
            element_id,
            lambda locator: locator.click(timeout=self._settings.action_timeout_ms),
        )

    async def fill(self, element_id: str, value: str) -> None:
        """Fill an editable inventory element with ``value``."""
        await self._element_action(
            "fill",
            element_id,
            lambda locator: locator.fill(value, timeout=self._settings.action_timeout_ms),
        )

    async def select_option(self, element_id: str, value: str) -> None:
        """Choose an option (by value or label) in a select-like element."""

        async def act(locator: Locator) -> None:
            await locator.select_option(value, timeout=self._settings.action_timeout_ms)

        await self._element_action("select_option", element_id, act)

    async def press_key(self, key: str) -> None:
        """Press a keyboard key (Playwright key syntax) on the active page."""

        async def attempt() -> None:
            try:
                await self.page.keyboard.press(key)
            except Exception as exc:
                raise map_playwright_error(exc, action=f"press {key}") from exc

        await self._retrying("press_key", attempt)

    async def scroll(self, delta_y: int) -> None:
        """Scroll the active page vertically by ``delta_y`` CSS pixels."""

        async def attempt() -> None:
            try:
                await self.page.evaluate(f"window.scrollBy(0, {int(delta_y)})")
            except Exception as exc:
                raise map_playwright_error(exc, action="scroll") from exc

        await self._retrying("scroll", attempt)

    async def wait_for_load(self, state: str = "load") -> None:
        """Wait for a load state: load, domcontentloaded, or networkidle."""

        async def attempt() -> None:
            try:
                await self.page.wait_for_load_state(
                    state,  # type: ignore[arg-type]
                    timeout=self._settings.nav_timeout_ms,
                )
            except Exception as exc:
                raise map_playwright_error(exc, action=f"wait_for_load {state}") from exc

        await self._retrying("wait_for_load", attempt)

    # ---------------------------------------------------- snapshot and evidence

    async def snapshot(self) -> PageSnapshot:
        """Extract and cache a fresh PageSnapshot of the active page."""

        async def attempt() -> PageSnapshot:
            try:
                return await extract_snapshot(self.page, self._clock)
            except Exception as exc:
                raise map_playwright_error(exc, action="snapshot") from exc

        self._snapshot = await self._retrying("snapshot", attempt)
        log.info(
            "snapshot_taken",
            url=self._snapshot.url,
            elements=len(self._snapshot.elements),
            truncated=self._snapshot.truncated,
        )
        return self._snapshot

    def drain_observations(self, step_id: str) -> ObservationBundle:
        """Everything observed since the previous drain, as one step-scoped bundle."""
        downloads, self._downloads = self._downloads, []
        dialogs, self._dialogs = self._dialogs, []
        popups, self._popups = self._popups, []
        return ObservationBundle(
            step_id=step_id,
            console=self._console.drain(),
            network=self._network.drain(),
            downloads=downloads,
            dialogs=dialogs,
            popups=popups,
        )

    # ----------------------------------------------------- auth and state

    async def save_storage_state(self) -> ArtifactRef:
        """Persist cookies plus localStorage to the run's artifact dir (resume/auth)."""
        state = await self._context.storage_state()
        return self._store.save_json("state", "storage_state.json", state)

    async def cookies(self) -> list[dict[str, Any]]:
        """All cookies visible to this context."""
        return [dict(c) for c in await self._context.cookies()]

    async def add_cookies(self, cookies: list[dict[str, Any]]) -> None:
        """Inject cookies (e.g. a pre-baked auth session) into the context."""
        await self._context.add_cookies(cookies)  # type: ignore[arg-type]

    async def close(self) -> None:
        """Close the context; safe to call twice."""
        if self._closed:
            return
        self._closed = True
        try:
            await self._context.close()
        except Exception as exc:  # noqa: BLE001 - closing a dead context is fine
            log.warning("context_close_failed", reason=str(exc))

    # ------------------------------------------------------------- internals

    async def _element_action(
        self,
        action: str,
        element_id: str,
        act: Callable[[Locator], Awaitable[None]],
    ) -> None:
        async def attempt() -> None:
            locator = await self._resolve(element_id)
            try:
                await act(locator)
            except Exception as exc:
                raise map_playwright_error(exc, action=f"{action} {element_id}") from exc

        await self._retrying(action, attempt)

    async def _resolve(self, element_id: str) -> Locator:
        """Element ID to a uniquely matching live locator, trying candidates in priority order."""
        if self._snapshot is None:
            raise ElementUnavailableError(
                "no snapshot taken yet", context={"element_id": element_id}
            )
        record = self._snapshot.element(element_id)
        if record is None:
            raise ElementUnavailableError(
                "element not in current snapshot", context={"element_id": element_id}
            )
        for selector in record.selectors:
            locator = self.page.locator(selector)
            try:
                count = await locator.count()
            except Exception as exc:
                raise map_playwright_error(exc, action=f"resolve {element_id}") from exc
            if count == 1:
                return locator
        raise ElementUnavailableError(
            "no candidate selector resolved uniquely",
            context={"element_id": element_id, "candidates": len(record.selectors)},
        )

    async def _retrying(self, action: str, attempt: Callable[[], Awaitable[T]]) -> T:
        def on_retry(exc: BaseException, attempt_number: int, delay: float) -> None:
            log.warning(
                "browser_retry",
                action=action,
                attempt=attempt_number,
                delay_s=round(delay, 2),
                reason=str(exc),
            )

        return await retry_async(
            attempt,
            policy=self._retry_policy,
            retry_on=(BrowserTransientError,),
            on_retry=on_retry,
        )
