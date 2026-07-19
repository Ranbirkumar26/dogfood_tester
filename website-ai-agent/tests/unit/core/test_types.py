"""Shared vocabulary types: severity ordering, artifact path safety, enum stability."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from website_agent.core.types import ArtifactRef, GoalMode, RiskClass, Severity, StopReason


def test_severity_rank_orders_most_severe_first() -> None:
    ranked = sorted(Severity, key=lambda s: s.rank)
    assert ranked == [
        Severity.BLOCKER,
        Severity.CRITICAL,
        Severity.MAJOR,
        Severity.MINOR,
        Severity.INFO,
    ]


def test_enums_serialize_as_plain_strings() -> None:
    # These values appear in reports, config, and prompts; they are a public contract.
    assert GoalMode.EXPLORE.value == "explore"
    assert RiskClass.DESTRUCTIVE.value == "destructive"
    assert StopReason.BUDGET_USD.value == "budget_usd"
    assert f"{Severity.MAJOR}" == "major"


def _ref(relpath: str) -> ArtifactRef:
    return ArtifactRef(
        kind="screenshots",
        name="step_0001.png",
        relpath=relpath,
        size_bytes=10,
        created_at=datetime(2026, 7, 20, tzinfo=UTC),
    )


def test_artifact_ref_accepts_relative_paths() -> None:
    assert _ref("screenshots/step_0001.png").relpath == "screenshots/step_0001.png"


@pytest.mark.parametrize(
    "bad",
    ["/etc/passwd", "\\windows\\path", "../outside.png", "a/../../b.png"],
)
def test_artifact_ref_rejects_absolute_and_traversal_paths(bad: str) -> None:
    with pytest.raises(ValidationError):
        _ref(bad)


def test_artifact_ref_is_frozen() -> None:
    ref = _ref("screenshots/x.png")
    with pytest.raises(ValidationError):
        ref.relpath = "other.png"  # type: ignore[misc]
