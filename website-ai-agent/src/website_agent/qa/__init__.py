"""QA engine: deterministic detector pipeline producing severity-ranked findings (Phase 10)."""

from website_agent.qa.detectors import (
    ALL_DETECTORS,
    detect_duplicate_ids,
    detect_empty_pages,
    detect_from_candidates,
    detect_missing_labels,
)
from website_agent.qa.engine import QaEngine
from website_agent.qa.models import QaContext, QaFinding, QaReport, SeverityCounts

__all__ = [
    "ALL_DETECTORS",
    "QaContext",
    "QaEngine",
    "QaFinding",
    "QaReport",
    "SeverityCounts",
    "detect_duplicate_ids",
    "detect_empty_pages",
    "detect_from_candidates",
    "detect_missing_labels",
]
