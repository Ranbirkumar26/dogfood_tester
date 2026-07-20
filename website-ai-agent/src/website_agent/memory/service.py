"""MemoryService: live wrapper that evolves MemoryState during a run.

Design rationale: the graph and registry are frozen copy-on-write structures so they
serialize cleanly into checkpoints, but the run loop wants a mutable owner it can feed
observations to. MemoryService holds the current MemoryState, applies updates from
executed steps, and hands back the immutable snapshot for checkpointing. On resume it is
reconstructed from the checkpointed MemoryState, so no history is lost.
"""

from __future__ import annotations

from website_agent.browser.models import PageSnapshot
from website_agent.memory.graph import PageGraph, normalize_url
from website_agent.memory.registry import ActionRegistry, MemoryState, action_signature


class MemoryService:
    """Mutable owner of run memory; produces immutable MemoryState for checkpoints."""

    def __init__(self, state: MemoryState | None = None) -> None:
        self._state = state or MemoryState()

    @property
    def state(self) -> MemoryState:
        """Current immutable memory snapshot, ready to embed in a checkpoint."""
        return self._state

    @property
    def graph(self) -> PageGraph:
        """The current page graph."""
        return self._state.page_graph

    @property
    def registry(self) -> ActionRegistry:
        """The current action registry."""
        return self._state.registry

    def observe_page(self, snapshot: PageSnapshot) -> str:
        """Record a visited page from a snapshot; returns the graph node key."""
        graph = self._state.page_graph.visit(
            url=snapshot.url,
            title=snapshot.title,
            content_hash=snapshot.snapshot_hash,
            interactive=len(snapshot.elements),
        )
        self._state = self._state.model_copy(update={"page_graph": graph})
        return graph.node_key(normalize_url(snapshot.url), snapshot.snapshot_hash)

    def observe_transition(
        self,
        *,
        source_key: str,
        target_snapshot: PageSnapshot,
        action: str,
        element_signature: str | None,
    ) -> None:
        """Record that an action navigated from source to the target snapshot's page."""
        target_key = self.observe_page(target_snapshot)
        graph = self._state.page_graph.connect(
            source_key=source_key,
            target_key=target_key,
            action=action,
            element_signature=element_signature,
        )
        self._state = self._state.model_copy(update={"page_graph": graph})

    def record_action(
        self,
        *,
        url: str,
        element_signature: str | None,
        action: str,
        input_class: str = "",
        success: bool,
    ) -> str:
        """Record an attempted action in the registry; returns its signature."""
        signature = action_signature(
            url=url,
            element_signature=element_signature,
            action=action,
            input_class=input_class,
        )
        registry = self._state.registry.record(signature, success=success)
        self._state = self._state.model_copy(update={"registry": registry})
        return signature

    def has_seen_action(
        self, *, url: str, element_signature: str | None, action: str, input_class: str = ""
    ) -> bool:
        """Whether an equivalent action was already attempted (planner dedupe)."""
        signature = action_signature(
            url=url,
            element_signature=element_signature,
            action=action,
            input_class=input_class,
        )
        return self._state.registry.has_seen(signature)
