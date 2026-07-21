"""Detectors: pure functions from run evidence to findings.

Design rationale: each detector is a pure function over the QaContext, so it is unit-testable
in isolation and the engine is just composition. Detectors fall in two families: those that
promote the reviewer's per-step candidates (console errors, HTTP errors, dead actions) into
confirmed findings, and those that analyze accumulated page snapshots for structural defects
the per-step reviewer cannot see (missing form labels, duplicate author ids). Severity is
assigned here, uniformly, so it is not scattered across the codebase. Every finding gets a
stable dedupe key so the same defect collapses to one across steps and pages.
"""

from __future__ import annotations

import hashlib

from website_agent.browser.models import PageSnapshot
from website_agent.core.types import Severity
from website_agent.qa.models import QaContext, QaFinding

# Interactive roles that require an accessible name to be usable with assistive tech.
_LABELLED_ROLES = {"textbox", "combobox", "listbox", "searchbox", "checkbox", "radio", "switch"}


def _key(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def detect_from_candidates(context: QaContext) -> list[QaFinding]:
    """Promote reviewer QA candidates to findings (console errors, HTTP errors, dead actions).

    The reviewer flags these per step; here they are deduplicated across the whole run by
    kind and location so a console error firing on every page is one finding, not twenty.
    """
    findings: list[QaFinding] = []
    seen: set[str] = set()
    for candidate in context.candidates:
        key = _key(candidate.kind, candidate.url, candidate.detail)
        if key in seen:
            continue
        seen.add(key)
        findings.append(
            QaFinding(
                kind=candidate.kind,
                severity=candidate.severity,
                title=_title_for(candidate.kind),
                detail=candidate.detail,
                url=candidate.url,
                dedupe_key=key,
            )
        )
    return findings


def detect_missing_labels(context: QaContext) -> list[QaFinding]:
    """Interactive form controls with no accessible name (an accessibility defect)."""
    findings: list[QaFinding] = []
    seen: set[str] = set()
    for snapshot in context.snapshots:
        for element in snapshot.elements:
            if element.role not in _LABELLED_ROLES or element.disabled or not element.visible:
                continue
            if element.name.strip():
                continue
            key = _key("missing_label", snapshot.url, element.signature)
            if key in seen:
                continue
            seen.add(key)
            findings.append(
                QaFinding(
                    kind="missing_label",
                    severity=Severity.MAJOR,
                    title="Form control without an accessible name",
                    detail=(
                        f"{element.role} ({element.tag}) has no label, aria-label, or "
                        "accessible text; screen readers cannot announce it"
                    ),
                    url=snapshot.url,
                    dedupe_key=key,
                )
            )
    return findings


def detect_duplicate_ids(context: QaContext) -> list[QaFinding]:
    """Repeated author-assigned ids on one page (invalid HTML; breaks selectors and labels)."""
    findings: list[QaFinding] = []
    for snapshot in context.snapshots:
        counts: dict[str, int] = {}
        for element in snapshot.elements:
            if element.dom_id:
                counts[element.dom_id] = counts.get(element.dom_id, 0) + 1
        for dom_id, count in sorted(counts.items()):
            if count < 2:
                continue
            key = _key("duplicate_id", snapshot.url, dom_id)
            findings.append(
                QaFinding(
                    kind="duplicate_id",
                    severity=Severity.MINOR,
                    title="Duplicate element id",
                    detail=f"id='{dom_id}' appears {count} times; ids must be unique per document",
                    url=snapshot.url,
                    dedupe_key=key,
                )
            )
    return findings


def detect_empty_pages(context: QaContext) -> list[QaFinding]:
    """Visited pages with no interactive elements at all (possible dead navigation)."""
    findings: list[QaFinding] = []
    for snapshot in context.snapshots:
        if _has_interactive(snapshot):
            continue
        key = _key("dead_navigation", snapshot.url)
        findings.append(
            QaFinding(
                kind="dead_navigation",
                severity=Severity.MINOR,
                title="Page with no interactive elements",
                detail="the page exposes nothing to click, fill, or navigate; it may be a dead end",
                url=snapshot.url,
                dedupe_key=key,
            )
        )
    return findings


def _has_interactive(snapshot: PageSnapshot) -> bool:
    return any(e.visible and not e.disabled for e in snapshot.elements)


def _title_for(kind: str) -> str:
    return {
        "console_error": "JavaScript console error",
        "http_error": "Failed network request",
        "dead_action": "Interaction with no observable effect",
        "unexpected_redirect": "Unexpected redirect",
        "missing_validation": "Missing form validation",
        "slow_request": "Slow network request",
    }.get(kind, kind.replace("_", " ").title())


# The default detector pipeline, in the order findings are gathered (severity re-sorts later).
ALL_DETECTORS = (
    detect_from_candidates,
    detect_missing_labels,
    detect_duplicate_ids,
    detect_empty_pages,
)
