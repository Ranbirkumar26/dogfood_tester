"""Snapshot-to-prompt rendering: the token-bounded inventory view the planner reads.

Design rationale (docs/architecture/data-flow.md, section 2): the prompt-facing rendering
is bounded and salience-ordered so a pathological page cannot blow the context window. This
lives with the planner (the consumer) rather than the browser layer so presentation stays a
role concern, not a capability concern. Only stable, human-meaningful fields are rendered;
the ephemeral element id is included because the model references elements by it only
indirectly (candidates carry ids), and it aids debugging of recorded prompts.
"""

from __future__ import annotations

from website_agent.browser.models import PageSnapshot

_DEFAULT_LIMIT = 60


def render_inventory(snapshot: PageSnapshot, *, limit: int = _DEFAULT_LIMIT) -> str:
    """Compact one-line-per-element inventory, salience-ordered, capped at ``limit``.

    In-viewport visible elements come first, then other visible, then hidden; a trailing
    marker notes truncation so the planner knows the view is partial.
    """
    ordered = sorted(
        (e for e in snapshot.elements if not e.disabled),
        key=lambda e: (not (e.visible and e.in_viewport), not e.visible),
    )
    shown = ordered[:limit]
    lines = [f"[{snapshot.title}] {snapshot.url}"]
    for element in shown:
        parts = [f"{element.element_id}:", element.role]
        if element.name:
            parts.append(f'"{element.name}"')
        if element.input_type:
            parts.append(f"type={element.input_type}")
        if not element.visible:
            parts.append("(hidden)")
        lines.append(" ".join(parts))
    if len(ordered) > limit or snapshot.truncated:
        lines.append(f"... ({len(ordered) - len(shown)} more elements not shown)")
    return "\n".join(lines)
