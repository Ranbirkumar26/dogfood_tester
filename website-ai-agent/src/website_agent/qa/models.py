"""QA engine data models: findings, the analysis context, the aggregated report.

Design rationale (docs/architecture/overview.md D14, folder-structure.md): the QA engine is a
deterministic detector pipeline, so its output is fully typed and reproducible. A QaFinding
is the confirmed, severity-assigned defect (versus the reviewer's pre-confirmation
QaCandidate); findings carry a stable dedupe key so the same defect seen on many steps
collapses to one. The QaContext is the whole-run evidence a detector reads; assembling it in
one place keeps detectors pure functions over data, independently testable without a browser
or a model.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from website_agent.browser.models import PageSnapshot
from website_agent.core.types import Severity
from website_agent.reviewer.models import QaCandidate


class QaFinding(BaseModel):
    """A confirmed defect with a severity and a stable identity."""

    model_config = ConfigDict(frozen=True)

    kind: str
    severity: Severity
    title: str
    detail: str
    url: str
    dedupe_key: str  # findings with the same key are the same defect across steps/pages

    @property
    def sort_key(self) -> tuple[int, str]:
        """Order most severe first, then by kind for a stable listing."""
        return (self.severity.rank, self.kind)


class QaContext(BaseModel):
    """Whole-run evidence the detectors read."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    candidates: tuple[QaCandidate, ...] = ()
    snapshots: tuple[PageSnapshot, ...] = ()  # distinct visited pages


class SeverityCounts(BaseModel):
    """Finding counts per severity, for report headlines and eval."""

    model_config = ConfigDict(frozen=True)

    blocker: int = 0
    critical: int = 0
    major: int = 0
    minor: int = 0
    info: int = 0

    @property
    def total(self) -> int:
        """All findings across severities."""
        return self.blocker + self.critical + self.major + self.minor + self.info


class QaReport(BaseModel):
    """The aggregated QA result for a run."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    findings: tuple[QaFinding, ...] = Field(default_factory=tuple)
    counts: SeverityCounts = Field(default_factory=SeverityCounts)

    @property
    def has_blocking_issues(self) -> bool:
        """Whether any blocker or critical finding exists (CI gate signal)."""
        return self.counts.blocker > 0 or self.counts.critical > 0
