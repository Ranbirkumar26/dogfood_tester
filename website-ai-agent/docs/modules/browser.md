# Module: browser

Layer 2 capability: everything Playwright, behind one facade. Nothing above this layer imports Playwright types (design D5).

## Components

| File | Provides |
|---|---|
| `manager.py` | `BrowserManager`: driver + Chromium lifecycle, context creation (viewport, storage state, HTTP basic auth, timeouts), relaunch-once policy for crashed browsers (F2) |
| `session.py` | `BrowserSession`: actions (goto, click, fill, select_option, press_key, scroll, wait_for_load, go_back), snapshot cache, element-ID resolution, tabs/popups, downloads, dialogs, cookies, storage state, observation draining |
| `extraction.py` | In-page JS extraction script plus `build_inventory` / `extract_snapshot`: interactive-element inventory with stable IDs and synthesized selectors (design D6) |
| `models.py` | `PageSnapshot`, `ElementRecord` (with dedupe `signature`), `ObservationBundle`, console/network/download/dialog/popup records |
| `observers.py` | `ConsoleObserver`, `NetworkObserver`: buffer continuously, drain per step window; never raise into the event loop |
| `screenshots.py` | `ScreenshotManager`: sequenced PNG artifacts; capture failure degrades, never fails a step |
| `errors_map.py` | `map_playwright_error`: every Playwright exception classified into the failure taxonomy (F1 transient / F2 fatal) before leaving the layer |

## Key behaviors

- **Element addressing**: `snapshot()` assigns e1..eN and per-element candidate selectors (testid > id > role+name > structural CSS path). Actions take element IDs; `_resolve` tries candidates in order and requires a unique match. Unknown IDs raise `ElementUnavailableError` before touching the browser.
- **Retries**: every action runs under `BROWSER_TRANSIENT_POLICY` (2 attempts, jittered backoff) with the selector re-resolved per attempt. Fatal errors and non-browser errors are never retried here.
- **Observation windows**: observers buffer console/network continuously; `drain_observations(step_id)` returns an `ObservationBundle` with exactly the events since the previous drain, plus downloads, dialogs, and popups.
- **Dialogs**: auto-dismissed (beforeunload auto-accepted) and recorded; an unhandled dialog would block the event loop.
- **Auth**: storage state (path or dict) and HTTP credentials go in at context creation; `save_storage_state()` persists cookies + localStorage to `state/storage_state.json` for resume.
- **Snapshot invalidation**: navigation, go_back, and tab switches clear the cached snapshot; acting without a fresh snapshot raises.

## Usage

```python
async with BrowserManager(settings.browser) as manager:
    session = await manager.new_session(clock, store)
    await session.goto("http://127.0.0.1:8000/")
    snapshot = await session.snapshot()
    await session.click(snapshot.elements[0].element_id)
    bundle = session.drain_observations("step_0001")
    await session.close()
```

## Testing

Unit tests fake the page surface (extraction, observers, screenshots, error mapping). Integration tests (`pytest -m integration`) run real headless Chromium against `tests/fixtures/sites/static-basic` served on 127.0.0.1; no test touches the public internet.
