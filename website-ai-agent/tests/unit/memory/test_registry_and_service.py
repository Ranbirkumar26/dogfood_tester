"""Action registry signatures and the MemoryService live wrapper."""

from __future__ import annotations

from datetime import UTC, datetime

from website_agent.browser.models import ElementRecord, PageSnapshot
from website_agent.memory.registry import ActionRegistry, MemoryState, action_signature
from website_agent.memory.service import MemoryService

NOW = datetime(2026, 7, 20, tzinfo=UTC)


def test_signature_stable_across_equivalent_urls() -> None:
    a = action_signature(url="https://ex.com/p/1", element_signature="sig", action="click")
    b = action_signature(url="https://ex.com/p/2", element_signature="sig", action="click")
    assert a == b  # template-collapsed URLs share signatures


def test_signature_distinguishes_input_class() -> None:
    valid = action_signature(
        url="https://ex.com", element_signature="s", action="fill", input_class="valid_email"
    )
    invalid = action_signature(
        url="https://ex.com", element_signature="s", action="fill", input_class="malformed_email"
    )
    assert valid != invalid


def test_registry_records_seen_and_failed() -> None:
    registry = ActionRegistry()
    registry = registry.record("sig1", success=True)
    registry = registry.record("sig2", success=False)
    assert registry.has_seen("sig1")
    assert registry.has_seen("sig2")
    assert not registry.has_failed("sig1")
    assert registry.has_failed("sig2")
    assert registry.count == 2


def _snapshot(url: str, content: str = "a") -> PageSnapshot:
    element = ElementRecord(
        element_id="e1", tag="a", role="link", name=content, selectors=["css=a"]
    )
    return PageSnapshot(url=url, title="T", captured_at=NOW, elements=[element])


def test_service_observe_page_records_and_returns_key() -> None:
    service = MemoryService()
    key = service.observe_page(_snapshot("https://ex.com/a"))
    assert service.graph.page_count == 1
    assert key in service.graph.nodes


def test_service_observe_transition_adds_edge() -> None:
    service = MemoryService()
    source_key = service.observe_page(_snapshot("https://ex.com/a", content="home"))
    service.observe_transition(
        source_key=source_key,
        target_snapshot=_snapshot("https://ex.com/b", content="about"),
        action="click",
        element_signature="sig",
    )
    assert service.graph.page_count == 2
    assert len(service.graph.edges) == 1
    assert service.graph.edges[0].source_key == source_key


def test_service_records_and_dedupes_actions() -> None:
    service = MemoryService()
    assert not service.has_seen_action(url="https://ex.com", element_signature="s", action="click")
    service.record_action(url="https://ex.com", element_signature="s", action="click", success=True)
    assert service.has_seen_action(url="https://ex.com", element_signature="s", action="click")


def test_service_round_trips_through_memory_state() -> None:
    service = MemoryService()
    service.observe_page(_snapshot("https://ex.com/a"))
    service.record_action(
        url="https://ex.com/a", element_signature="s", action="click", success=False
    )

    serialized = service.state.model_dump_json()
    restored_state = MemoryState.model_validate_json(serialized)
    resumed = MemoryService(restored_state)

    assert resumed.graph.page_count == 1
    assert resumed.registry.has_failed(
        action_signature(url="https://ex.com/a", element_signature="s", action="click")
    )
