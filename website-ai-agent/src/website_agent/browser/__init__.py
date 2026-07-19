"""Browser capability layer: Playwright behind one facade (designs D5, D6).

Public surface: BrowserManager builds BrowserSessions; sessions expose actions,
snapshots, and observation draining. Nothing above this layer imports Playwright.
"""

from website_agent.browser.extraction import build_inventory, extract_snapshot
from website_agent.browser.manager import BrowserManager
from website_agent.browser.models import (
    ConsoleEvent,
    DialogRecord,
    DownloadRecord,
    ElementRecord,
    NetworkEvent,
    ObservationBundle,
    PageSnapshot,
    PopupRecord,
)
from website_agent.browser.observers import ConsoleObserver, NetworkObserver
from website_agent.browser.screenshots import ScreenshotManager
from website_agent.browser.session import BrowserSession, ElementUnavailableError

__all__ = [
    "BrowserManager",
    "BrowserSession",
    "ConsoleEvent",
    "ConsoleObserver",
    "DialogRecord",
    "DownloadRecord",
    "ElementRecord",
    "ElementUnavailableError",
    "NetworkEvent",
    "NetworkObserver",
    "ObservationBundle",
    "PageSnapshot",
    "PopupRecord",
    "ScreenshotManager",
    "build_inventory",
    "extract_snapshot",
]
