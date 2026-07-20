"""Page graph: URL normalization, template collapse, node/edge dedupe."""

from __future__ import annotations

import pytest

from website_agent.memory.graph import PageGraph, normalize_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://Ex.com/About/", "https://ex.com/About"),
        ("https://ex.com/page#section", "https://ex.com/page"),
        ("https://ex.com/product/123", "https://ex.com/product/{id}"),
        ("https://ex.com/u/deadbeefcafe1234", "https://ex.com/u/{id}"),
        ("https://ex.com/a?q=1", "https://ex.com/a"),
        ("https://ex.com/", "https://ex.com"),
    ],
)
def test_normalize_url(raw: str, expected: str) -> None:
    assert normalize_url(raw) == expected


def test_normalize_keeps_query_when_asked() -> None:
    assert normalize_url("https://ex.com/a?q=1", keep_query=True) == "https://ex.com/a?q=1"


def test_template_pages_collapse_to_one_node() -> None:
    graph = PageGraph()
    graph = graph.visit(url="https://ex.com/product/1", title="P1", content_hash="h", interactive=5)
    graph = graph.visit(url="https://ex.com/product/2", title="P2", content_hash="h", interactive=5)
    assert graph.page_count == 1
    node = next(iter(graph.nodes.values()))
    assert node.visit_count == 2
    assert node.normalized_url == "https://ex.com/product/{id}"


def test_different_content_hash_makes_distinct_nodes() -> None:
    graph = PageGraph()
    graph = graph.visit(url="https://ex.com/p", title="A", content_hash="h1", interactive=1)
    graph = graph.visit(url="https://ex.com/p", title="B", content_hash="h2", interactive=2)
    assert graph.page_count == 2


def test_is_visited_and_url_classes() -> None:
    graph = PageGraph().visit(url="https://ex.com/a", title="A", content_hash="h", interactive=0)
    assert graph.is_visited("https://ex.com/a", "h")
    assert not graph.is_visited("https://ex.com/a", "other")
    assert graph.visited_url_classes() == {"https://ex.com/a"}


def test_edges_are_deduplicated() -> None:
    graph = PageGraph()
    graph = graph.visit(url="https://ex.com/a", title="A", content_hash="h1", interactive=0)
    graph = graph.visit(url="https://ex.com/b", title="B", content_hash="h2", interactive=0)
    key_a = graph.node_key("https://ex.com/a", "h1")
    key_b = graph.node_key("https://ex.com/b", "h2")
    graph = graph.connect(source_key=key_a, target_key=key_b, action="click", element_signature="s")
    graph = graph.connect(source_key=key_a, target_key=key_b, action="click", element_signature="s")
    assert len(graph.edges) == 1


def test_graph_round_trips_through_json() -> None:
    graph = PageGraph()
    graph = graph.visit(url="https://ex.com/a", title="A", content_hash="h1", interactive=3)
    key_a = graph.node_key("https://ex.com/a", "h1")
    graph = graph.connect(source_key=key_a, target_key=key_a, action="self", element_signature=None)
    restored = PageGraph.model_validate_json(graph.model_dump_json())
    assert restored == graph
    assert restored.page_count == 1
