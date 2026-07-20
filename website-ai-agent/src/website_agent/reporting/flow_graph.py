"""User-flow graph rendering: PageGraph to Mermaid and DOT.

Design rationale: the page graph is already the navigation model (data-flow.md s4); rendering
it is a pure transform. Mermaid is the default because it renders inline on GitHub and in the
generated Markdown docs; DOT is offered for users who want Graphviz. Node and edge labels are
sanitized so page titles containing quotes or newlines cannot break the diagram grammar.
"""

from __future__ import annotations

import re

from website_agent.memory.graph import PageGraph

_MERMAID_UNSAFE = re.compile(r'["\n\r]')
_ID_SAFE = re.compile(r"[^A-Za-z0-9_]")


def _node_id(key: str, index: int) -> str:
    """Stable, grammar-safe node identifier for a graph key."""
    return f"n{index}_{_ID_SAFE.sub('_', key)[:24]}"


def _label(text: str, limit: int = 40) -> str:
    cleaned = _MERMAID_UNSAFE.sub(" ", text).strip()
    if len(cleaned) > limit:
        cleaned = cleaned[: limit - 1] + "…"
    return cleaned or "(untitled)"


def render_mermaid(graph: PageGraph) -> str:
    """Render the page graph as a Mermaid flowchart."""
    keys = {key: i for i, key in enumerate(sorted(graph.nodes))}
    lines = ["flowchart TD"]
    for key, index in keys.items():
        node = graph.nodes[key]
        label = f"{_label(node.title)}<br/>{_label(node.normalized_url, 50)}"
        lines.append(f'    {_node_id(key, index)}["{label}"]')
    for edge in graph.edges:
        if edge.source_key not in keys or edge.target_key not in keys:
            continue
        source = _node_id(edge.source_key, keys[edge.source_key])
        target = _node_id(edge.target_key, keys[edge.target_key])
        lines.append(f"    {source} -->|{_label(edge.action, 20)}| {target}")
    return "\n".join(lines)


def render_dot(graph: PageGraph) -> str:
    """Render the page graph as Graphviz DOT."""
    keys = {key: i for i, key in enumerate(sorted(graph.nodes))}
    lines = ["digraph userflow {", "  rankdir=TB;", "  node [shape=box];"]
    for key, index in keys.items():
        node = graph.nodes[key]
        label = f"{_label(node.title)}\\n{_label(node.normalized_url, 50)}"
        lines.append(f'  {_node_id(key, index)} [label="{label}"];')
    for edge in graph.edges:
        if edge.source_key not in keys or edge.target_key not in keys:
            continue
        source = _node_id(edge.source_key, keys[edge.source_key])
        target = _node_id(edge.target_key, keys[edge.target_key])
        lines.append(f'  {source} -> {target} [label="{_label(edge.action, 20)}"];')
    lines.append("}")
    return "\n".join(lines)
