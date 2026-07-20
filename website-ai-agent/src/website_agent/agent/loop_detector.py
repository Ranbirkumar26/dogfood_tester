"""Loop detection: state-signature ring buffer and repeat counting.

Design rationale (docs/architecture/failure-recovery.md, section 3): the failure mode unique
to autonomous agents is that everything "succeeds" while the run goes nowhere. A state
signature hashes the normalized URL, the snapshot's content hash, and the last action
signature; when the same signature recurs enough times the router forces a replan, and once
a branch is poisoned a further recurrence stops the run. Pure functions over LoopSignal so
the logic is reproducible and exhaustively testable, independent of the graph framework.
"""

from __future__ import annotations

import hashlib

from website_agent.memory.graph import normalize_url
from website_agent.state.models import LoopSignal

_RING = 12  # signatures retained; long enough to catch multi-step cycles, short enough to be cheap


def state_signature(*, url: str, content_hash: str, last_action_signature: str | None) -> str:
    """Signature of the agent's situation after a step (loop-detector key)."""
    basis = "|".join((normalize_url(url), content_hash, last_action_signature or ""))
    return hashlib.sha256(basis.encode()).hexdigest()[:16]


def observe_signature(signal: LoopSignal, signature: str) -> tuple[LoopSignal, int]:
    """Record a new signature; return the updated signal and this signature's repeat count.

    The repeat count is how many times this exact signature already appears in the recent
    ring (before this observation): 0 means brand new, 1 means seen once before, and so on.
    """
    repeats = signal.recent.count(signature)
    recent = (*signal.recent, signature)[-_RING:]
    updated = signal.model_copy(update={"recent": recent, "repeats": repeats})
    return updated, repeats


def poison_branch(signal: LoopSignal, signature: str) -> LoopSignal:
    """Mark a signature's branch as poisoned (already force-replanned once)."""
    return signal.model_copy(update={"poisoned": signal.poisoned | {signature}})


def is_poisoned(signal: LoopSignal, signature: str) -> bool:
    """Whether this signature's branch has already been force-replanned."""
    return signature in signal.poisoned
