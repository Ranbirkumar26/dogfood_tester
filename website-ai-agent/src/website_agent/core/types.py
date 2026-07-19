"""Cross-phase vocabulary: enums and small value objects shared by multiple layers.

Design rationale: these names appear in state, reports, config, and prompts, so they are
defined exactly once here. Types owned by a single subsystem (PageSnapshot, Plan, verdicts)
live with that subsystem and land in their own phase; putting them here would invert the
layer dependencies.
"""

from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class GoalMode(enum.StrEnum):
    """What the run is trying to achieve; planner weights differ per mode."""

    EXPLORE = "explore"
    TEST = "test"
    DOCUMENT = "document"


class RiskClass(enum.StrEnum):
    """Side-effect classification of an action, input to the policy gate (design D12)."""

    SAFE = "safe"
    MUTATING = "mutating"
    DESTRUCTIVE = "destructive"


class Severity(enum.StrEnum):
    """QA finding severity. Order matters for report sorting and eval scoring."""

    BLOCKER = "blocker"
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    INFO = "info"

    @property
    def rank(self) -> int:
        """Numeric rank, 0 = most severe. Use for sorting, never compare strings."""
        return _SEVERITY_ORDER[self]


_SEVERITY_ORDER: dict[Severity, int] = {
    Severity.BLOCKER: 0,
    Severity.CRITICAL: 1,
    Severity.MAJOR: 2,
    Severity.MINOR: 3,
    Severity.INFO: 4,
}


class StopReason(enum.StrEnum):
    """Why a run finalized. Every terminal path maps to exactly one value."""

    GOAL_MET = "goal_met"
    FRONTIER_EXHAUSTED = "frontier_exhausted"
    BUDGET_STEPS = "budget_steps"
    BUDGET_TOKENS = "budget_tokens"
    BUDGET_USD = "budget_usd"
    BUDGET_WALL_CLOCK = "budget_wall_clock"
    BUDGET_FAILURES = "budget_failures"
    LOOP_LIMIT = "loop_limit"
    FATAL_ERROR = "fatal_error"
    USER_STOP = "user_stop"


class ArtifactRef(BaseModel):
    """Pointer to a file in the run's artifact directory.

    State and reports carry these instead of file contents (design D8). ``relpath``
    is always relative to the run directory so runs stay relocatable.
    """

    model_config = ConfigDict(frozen=True)

    kind: str
    name: str
    relpath: str
    size_bytes: int
    created_at: datetime

    @field_validator("relpath")
    @classmethod
    def _must_stay_inside_run_dir(cls, value: str) -> str:
        # Escaping the run directory would let a crafted name overwrite arbitrary files
        # when artifacts are copied or served by the API.
        if value.startswith(("/", "\\")) or ".." in value.split("/"):
            raise ValueError(f"artifact relpath must be relative and traversal-free: {value!r}")
        return value
