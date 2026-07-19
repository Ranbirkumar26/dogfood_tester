"""Screenshot capture into the run's artifact directory.

Design rationale: screenshots are evidence (reviewer, QA report, docs), so naming must be
deterministic and sortable: a monotonically increasing sequence number plus a caller tag.
Capture failure never fails a step (graceful degradation): callers get None and the run
continues with the screenshot marked unavailable.
"""

from __future__ import annotations

import re
from typing import Any

from website_agent.core.artifacts import ArtifactStore
from website_agent.core.types import ArtifactRef
from website_agent.logging import get_logger

log = get_logger("browser.screenshots")

_TAG_SANITIZER = re.compile(r"[^A-Za-z0-9._-]+")


class ScreenshotManager:
    """Captures page screenshots as sequenced PNG artifacts under ``screenshots/``."""

    def __init__(self, store: ArtifactStore) -> None:
        self._store = store
        self._counter = 0

    async def capture(self, page: Any, tag: str) -> ArtifactRef | None:
        """Screenshot the page's current viewport.

        Args:
            page: Playwright page (anything with an async ``screenshot()`` returning bytes).
            tag: short label folded into the filename, e.g. a step ID or "finding".

        Returns:
            The stored artifact reference, or None when capture failed; failure is
            logged and never raised (screenshots are evidence, not preconditions).
        """
        self._counter += 1
        safe_tag = _TAG_SANITIZER.sub("-", tag).strip("-") or "shot"
        name = f"s{self._counter:04d}_{safe_tag}.png"
        try:
            data = await page.screenshot()
            return self._store.save_bytes("screenshots", name, data)
        except Exception as exc:  # noqa: BLE001 - degrade, never fail the step
            log.warning("screenshot_unavailable", tag=tag, reason=str(exc))
            return None

    @property
    def count(self) -> int:
        """Capture attempts so far (successful or not); an eval-harness metric."""
        return self._counter
