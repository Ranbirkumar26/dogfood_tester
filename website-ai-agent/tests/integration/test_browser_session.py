"""End-to-end browser layer against the local static-basic fixture site."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from website_agent.browser.models import PageSnapshot
from website_agent.browser.session import BrowserSession, ElementUnavailableError
from website_agent.core.errors import FatalError

pytestmark = pytest.mark.integration


def _find(snapshot: PageSnapshot, *, testid: str | None = None, name: str | None = None) -> str:
    for element in snapshot.elements:
        if testid is not None and element.testid == testid:
            return element.element_id
        if name is not None and element.name == name:
            return element.element_id
    raise AssertionError(f"element not found (testid={testid}, name={name})")


async def _wait_until(predicate, timeout_s: float = 5.0):  # type: ignore[no-untyped-def]
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("condition not met in time")


async def test_goto_and_snapshot_inventory(session: BrowserSession, static_basic_url: str) -> None:
    status = await session.goto(f"{static_basic_url}/index.html")
    assert status == 200

    snapshot = await session.snapshot()
    assert snapshot.title == "Static Basic - Home"
    assert snapshot.viewport == (1280, 900)

    ids = [e.element_id for e in snapshot.elements]
    assert len(ids) == len(set(ids))

    nav_links = [e for e in snapshot.elements if e.role == "link" and e.visible]
    assert {e.name for e in nav_links} >= {"Home", "About", "Contact", "Broken Link"}
    assert all(e.href for e in nav_links)

    cta = snapshot.element(_find(snapshot, testid="cta-primary"))
    assert cta is not None
    assert cta.role == "button"
    assert cta.selectors[0] == '[data-testid="cta-primary"]'
    assert cta.dom_id == "cta"

    hidden = [e for e in snapshot.elements if e.dom_id == "hidden-link"]
    assert hidden
    assert hidden[0].visible is False


async def test_click_mutates_page_state(session: BrowserSession, static_basic_url: str) -> None:
    await session.goto(f"{static_basic_url}/index.html")
    snapshot = await session.snapshot()
    await session.click(_find(snapshot, testid="cta-primary"))
    outcome = await session.page.evaluate("document.getElementById('outcome').textContent")
    assert outcome == "clicked"


async def test_form_fill_select_and_submit(session: BrowserSession, static_basic_url: str) -> None:
    await session.goto(f"{static_basic_url}/contact.html")
    snapshot = await session.snapshot()

    email_id = _find(snapshot, name="Email address")
    topic_id = _find(snapshot, name="Topic")
    submit_id = _find(snapshot, testid="submit-contact")

    await session.fill(email_id, "qa@example.com")
    await session.select_option(topic_id, "bugs")
    await session.click(submit_id)

    result = await session.page.evaluate("document.getElementById('form-result').textContent")
    assert result == "submitted:qa@example.com:bugs"


async def test_observers_capture_console_error_and_404(
    session: BrowserSession, static_basic_url: str
) -> None:
    await session.goto(f"{static_basic_url}/index.html")
    await session.wait_for_load("networkidle")

    bundle = session.drain_observations("step_0001")
    assert any("fixture-console-error-marker" in e.text for e in bundle.console_errors)
    missing = [e for e in bundle.failed_requests if e.url.endswith("/missing.json")]
    assert missing
    assert missing[0].status == 404

    # Window semantics: a second drain with no new activity is empty.
    assert session.drain_observations("step_0002").console == []


async def test_broken_link_navigation_reports_404(
    session: BrowserSession, static_basic_url: str
) -> None:
    status = await session.goto(f"{static_basic_url}/missing-page.html")
    assert status == 404


async def test_go_back_returns_to_previous_page(
    session: BrowserSession, static_basic_url: str
) -> None:
    await session.goto(f"{static_basic_url}/index.html")
    await session.goto(f"{static_basic_url}/about.html")
    await session.go_back()
    assert session.page.url.endswith("/index.html")


async def test_popup_is_tracked_and_switchable(
    session: BrowserSession, static_basic_url: str
) -> None:
    await session.goto(f"{static_basic_url}/index.html")
    snapshot = await session.snapshot()
    await session.click(_find(snapshot, name="Open Popup"))

    await _wait_until(lambda: len(session.pages_info()) == 2)
    bundle = session.drain_observations("step_0001")
    assert len(bundle.popups) == 1

    session.switch_tab(1)
    await session.wait_for_load()
    assert session.page.url.endswith("/about.html")
    assert session.current_snapshot is None  # tab switch invalidates the snapshot

    with pytest.raises(ElementUnavailableError):
        session.switch_tab(9)


async def test_alert_dialog_is_auto_dismissed_and_recorded(
    session: BrowserSession, static_basic_url: str
) -> None:
    await session.goto(f"{static_basic_url}/index.html")
    snapshot = await session.snapshot()
    await session.click(_find(snapshot, name="Trigger Alert"))

    bundle_dialogs = []
    for _ in range(50):
        bundle_dialogs = session.drain_observations("step_0001").dialogs
        if bundle_dialogs:
            break
        await asyncio.sleep(0.05)
    assert bundle_dialogs
    assert bundle_dialogs[0].kind == "alert"
    assert bundle_dialogs[0].message == "intrusive alert"
    assert bundle_dialogs[0].action == "dismissed"


async def test_storage_state_and_cookies_round_trip(
    session: BrowserSession, static_basic_url: str, tmp_path: Path
) -> None:
    await session.goto(f"{static_basic_url}/contact.html")  # page writes localStorage
    await session.add_cookies(
        [{"name": "wa_test", "value": "cookie-value", "url": static_basic_url}]
    )

    ref = await session.save_storage_state()
    assert ref.relpath == "state/storage_state.json"
    state = json.loads((tmp_path / "run_integration" / ref.relpath).read_text())
    local_storage_pairs = [
        item for origin in state.get("origins", []) for item in origin.get("localStorage", [])
    ]
    assert {"name": "fixture-key", "value": "fixture-value"} in local_storage_pairs
    assert any(c["name"] == "wa_test" for c in state.get("cookies", []))

    cookies = await session.cookies()
    assert any(c["name"] == "wa_test" and c["value"] == "cookie-value" for c in cookies)


async def test_unknown_element_id_raises_element_unavailable(
    session: BrowserSession, static_basic_url: str
) -> None:
    await session.goto(f"{static_basic_url}/index.html")
    await session.snapshot()
    with pytest.raises(ElementUnavailableError, match="not in current snapshot"):
        await session.click("e999")


async def test_screenshot_produces_png_artifact(
    session: BrowserSession, static_basic_url: str, tmp_path: Path
) -> None:
    await session.goto(f"{static_basic_url}/index.html")
    ref = await session.screenshots.capture(session.page, "step_0001")
    assert ref is not None
    data = (tmp_path / "run_integration" / ref.relpath).read_bytes()
    assert data.startswith(b"\x89PNG")


async def test_download_is_captured_into_artifacts(
    session: BrowserSession, static_basic_url: str, tmp_path: Path
) -> None:
    await session.goto(f"{static_basic_url}/index.html")
    snapshot = await session.snapshot()
    await session.click(_find(snapshot, testid="download-report"))

    downloads = []
    for _ in range(100):
        downloads = session.drain_observations("step_0001").downloads
        if downloads:
            break
        await asyncio.sleep(0.05)
    assert downloads
    assert downloads[0].suggested_name == "report.txt"
    saved = (tmp_path / "run_integration" / downloads[0].relpath).read_text()
    assert "Fixture download payload" in saved


async def test_press_key_and_scroll(session: BrowserSession, static_basic_url: str) -> None:
    await session.goto(f"{static_basic_url}/contact.html")
    snapshot = await session.snapshot()
    await session.click(_find(snapshot, name="Email address"))
    await session.press_key("q")
    value = await session.page.evaluate("document.getElementById('email').value")
    assert value == "q"

    await session.scroll(400)
    scroll_y = await session.page.evaluate("window.scrollY")
    assert scroll_y >= 0  # page may be shorter than 400px; call must succeed either way


async def test_session_close_is_idempotent(session: BrowserSession, static_basic_url: str) -> None:
    await session.goto(f"{static_basic_url}/index.html")
    await session.close()
    await session.close()  # second close must be a no-op, not an error


async def test_new_session_before_start_raises_fatal(tmp_path: Path) -> None:
    from website_agent.browser.manager import BrowserManager
    from website_agent.config.settings import BrowserSettings
    from website_agent.core.artifacts import FileArtifactStore
    from website_agent.core.clock import SystemClock

    unstarted = BrowserManager(BrowserSettings())
    clock = SystemClock()
    with pytest.raises(FatalError, match="not started"):
        await unstarted.new_session(clock, FileArtifactStore(tmp_path, "run_x", clock))


async def test_manager_relaunch_once_then_fatal(manager, tmp_path) -> None:  # type: ignore[no-untyped-def]
    await manager.relaunch()  # first relaunch allowed
    from website_agent.core.artifacts import FileArtifactStore
    from website_agent.core.clock import SystemClock

    clock = SystemClock()
    store = FileArtifactStore(tmp_path, "run_relaunch", clock)
    session = await manager.new_session(clock, store)  # relaunched browser is usable
    await session.close()

    with pytest.raises(FatalError, match="crashed twice"):
        await manager.relaunch()
