"""Ground-truth loading and finding-to-defect matching.

Design rationale: matching is mechanical (design D9, no LLM-as-judge in the metric path): a
finding matches a defect when their kind agrees and their locations agree under URL
normalization, with a per-kind tolerance. Unmatched findings are false positives; unmatched
defects are misses. Both are reported explicitly so a regression is triageable, not just a
number that moved.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from evaluation.harness.models import Defect, FoundDefect, GroundTruth, Scenario
from website_agent.memory.graph import normalize_url


def load_ground_truth(path: Path) -> GroundTruth:
    """Load a fixture site's labeled defects from YAML."""
    data = yaml.safe_load(path.read_text())
    return GroundTruth.model_validate(data)


def load_scenario(path: Path) -> Scenario:
    """Load a scenario definition from YAML."""
    data = yaml.safe_load(path.read_text())
    return Scenario.model_validate(data)


def _same_location(a: str, b: str) -> bool:
    """Whether two locations refer to the same place under URL normalization.

    Ground-truth locations are often paths (``/pricing``); findings carry full URLs. Compare
    on the normalized path suffix so host and scheme differences do not defeat a match.
    """
    na, nb = normalize_url(a), normalize_url(b)
    if na == nb:
        return True
    # Fall back to path-suffix comparison for path-only ground-truth locations.
    return na.endswith(b) or nb.endswith(a)


class MatchResult:
    """The outcome of matching findings against ground-truth defects."""

    def __init__(
        self,
        matched: list[tuple[Defect, FoundDefect]],
        false_positives: list[FoundDefect],
        missed: list[Defect],
    ) -> None:
        self.matched = matched
        self.false_positives = false_positives
        self.missed = missed


def match_findings(defects: tuple[Defect, ...], findings: tuple[FoundDefect, ...]) -> MatchResult:
    """Match findings to defects by kind and location; each pairs at most once."""
    remaining = list(findings)
    matched: list[tuple[Defect, FoundDefect]] = []
    missed: list[Defect] = []

    for defect in defects:
        hit = None
        for finding in remaining:
            if finding.kind == defect.kind and _same_location(finding.location, defect.location):
                hit = finding
                break
        if hit is not None:
            matched.append((defect, hit))
            remaining.remove(hit)
        else:
            missed.append(defect)

    return MatchResult(matched=matched, false_positives=remaining, missed=missed)
