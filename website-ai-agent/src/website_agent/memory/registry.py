"""ActionRegistry: normalized action signatures for duplicate avoidance.

Design rationale (docs/architecture/planner.md, section 4): the planner must not re-propose
actions it has already tried. A signature hashes the normalized URL pattern, the element
signature (role + name + author ids, not the ephemeral eN id), the action type, and an
input class, so dedupe survives re-snapshots and minor DOM shifts. In test mode the same
element with a different input class (valid vs malformed email) is a distinct, valuable
action, which the input_class component preserves. Serializable and run-scoped.
"""

from __future__ import annotations

import hashlib

from pydantic import BaseModel, ConfigDict, Field

from website_agent.memory.graph import PageGraph, normalize_url


def action_signature(
    *,
    url: str,
    element_signature: str | None,
    action: str,
    input_class: str = "",
) -> str:
    """Stable signature for one action attempt (see module docstring)."""
    basis = "|".join((normalize_url(url), element_signature or "", action, input_class))
    return hashlib.sha256(basis.encode()).hexdigest()[:16]


class ActionRegistry(BaseModel):
    """Set of seen action signatures with failure tracking.

    Frozen and copy-on-write like PageGraph so it can live in run state; the memory
    service holds the live instance during a run.
    """

    model_config = ConfigDict(frozen=True)

    seen: frozenset[str] = frozenset()
    failed: frozenset[str] = frozenset()

    def record(self, signature: str, *, success: bool) -> ActionRegistry:
        """Return a registry with this signature marked seen (and failed if unsuccessful)."""
        seen = self.seen | {signature}
        failed = self.failed if success else self.failed | {signature}
        return self.model_copy(update={"seen": seen, "failed": failed})

    def has_seen(self, signature: str) -> bool:
        """Whether this action signature has been attempted."""
        return signature in self.seen

    def has_failed(self, signature: str) -> bool:
        """Whether this action signature has failed at least once (planner penalty input)."""
        return signature in self.failed

    @property
    def count(self) -> int:
        """Distinct actions attempted."""
        return len(self.seen)


class MemoryState(BaseModel):
    """The two memory structures together; one serializable unit for checkpoints."""

    model_config = ConfigDict(frozen=True)

    page_graph: PageGraph = Field(default_factory=PageGraph)
    registry: ActionRegistry = Field(default_factory=ActionRegistry)
