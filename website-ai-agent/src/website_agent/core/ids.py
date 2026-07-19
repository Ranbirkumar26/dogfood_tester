"""Run and step identifier generation.

Design rationale: run IDs are also directory names and checkpoint thread IDs, so they must
be filesystem-safe, sortable by creation time, and collision-resistant across concurrent
runs on one machine. Timestamp prefix gives sortability; a random suffix gives uniqueness
without coordination.
"""

from __future__ import annotations

import secrets

from website_agent.core.clock import Clock


def generate_run_id(clock: Clock) -> str:
    """New run identifier, e.g. ``run_20260720_143512_a3f9c1``.

    Sortable by start time; 3 random bytes make same-second collisions negligible.
    """
    stamp = clock.now().strftime("%Y%m%d_%H%M%S")
    return f"run_{stamp}_{secrets.token_hex(3)}"


def generate_step_id(index: int) -> str:
    """Step identifier from its 1-based position in the run, e.g. ``step_0042``.

    Zero-padded so lexicographic order equals execution order in listings.
    """
    if index < 1:
        raise ValueError(f"step index must be >= 1, got {index}")
    return f"step_{index:04d}"
