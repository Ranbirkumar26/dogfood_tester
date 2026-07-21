"""Browser-layer data models: page snapshots, element inventory, observations.

Design rationale: the PageSnapshot is the single source of truth about the current page
(docs/architecture/data-flow.md, section 2). Elements carry short stable IDs (e1..eN) plus
an ordered list of candidate selectors synthesized at extraction time; the LLM only ever
sees IDs, and the session resolves IDs back to live locators (design D6). Signatures hash
role/name/testid rather than the ephemeral ID so memory dedupe survives re-snapshots.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from urllib.parse import urldefrag

from pydantic import BaseModel, ConfigDict, Field


class ElementRecord(BaseModel):
    """One interactive element in the inventory."""

    model_config = ConfigDict(frozen=True)

    element_id: str
    tag: str
    role: str
    name: str = ""
    testid: str | None = None
    dom_id: str | None = None
    input_type: str | None = None
    href: str | None = None
    disabled: bool = False
    visible: bool = True
    in_viewport: bool = True
    editable: bool = False
    selectors: list[str] = Field(min_length=1)
    rect: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)

    @property
    def signature(self) -> str:
        """Stable identity across re-snapshots: role, name, and author-assigned ids.

        Deliberately excludes element_id (ephemeral) and CSS path (layout-sensitive);
        used by ActionRegistry dedupe (docs/architecture/planner.md, section 4).
        """
        basis = "|".join(
            (self.role, self.name.strip().lower(), self.testid or "", self.dom_id or "")
        )
        return hashlib.sha256(basis.encode()).hexdigest()[:12]


class PageSnapshot(BaseModel):
    """What the page is right now: identity, inventory, and a drift-detection hash."""

    model_config = ConfigDict(frozen=True)

    url: str
    title: str
    captured_at: datetime
    elements: list[ElementRecord]
    truncated: bool = False
    viewport: tuple[int, int] = (0, 0)

    @property
    def snapshot_hash(self) -> str:
        """Content-class hash: normalized URL plus the multiset of element signatures.

        Stable under element reordering and re-snapshot; changes when the page's
        interactive surface changes. Used for loop detection and resume drift checks.
        """
        url_no_fragment, _ = urldefrag(self.url)
        signature_part = ",".join(sorted(e.signature for e in self.elements))
        return hashlib.sha256(f"{url_no_fragment}#{signature_part}".encode()).hexdigest()[:16]

    def element(self, element_id: str) -> ElementRecord | None:
        """Inventory lookup by ID; None when the ID is not in this snapshot."""
        for record in self.elements:
            if record.element_id == element_id:
                return record
        return None


class ConsoleEvent(BaseModel):
    """One console message or uncaught page error."""

    model_config = ConfigDict(frozen=True)

    level: str  # debug | log | info | warning | error | pageerror
    text: str
    url: str | None = None
    at: datetime


class NetworkEvent(BaseModel):
    """One finished or failed request. status is None for transport-level failures."""

    model_config = ConfigDict(frozen=True)

    method: str
    url: str
    status: int | None
    ok: bool
    resource_type: str | None = None
    failure: str | None = None
    duration_ms: float | None = None
    at: datetime


class DownloadRecord(BaseModel):
    """A file the page pushed at us, persisted into the run's artifact directory."""

    model_config = ConfigDict(frozen=True)

    suggested_name: str
    source_url: str | None
    relpath: str
    at: datetime


class DialogRecord(BaseModel):
    """A JS dialog (alert/confirm/prompt/beforeunload) that was auto-handled."""

    model_config = ConfigDict(frozen=True)

    kind: str
    message: str
    action: str  # dismissed | accepted
    at: datetime


class PopupRecord(BaseModel):
    """A new page/tab the site opened; index points into the session's page list."""

    model_config = ConfigDict(frozen=True)

    url: str
    page_index: int
    at: datetime


class ObservationBundle(BaseModel):
    """Everything observed during one step window; the reviewer's evidence (design D2)."""

    model_config = ConfigDict(frozen=True)

    step_id: str
    console: list[ConsoleEvent] = Field(default_factory=list)
    network: list[NetworkEvent] = Field(default_factory=list)
    downloads: list[DownloadRecord] = Field(default_factory=list)
    dialogs: list[DialogRecord] = Field(default_factory=list)
    popups: list[PopupRecord] = Field(default_factory=list)

    @property
    def console_errors(self) -> list[ConsoleEvent]:
        """Console events at error severity, the primary bug signal for QA."""
        return [e for e in self.console if e.level in ("error", "pageerror")]

    @property
    def failed_requests(self) -> list[NetworkEvent]:
        """Requests that failed at transport level or returned status >= 400."""
        return [e for e in self.network if not e.ok]
