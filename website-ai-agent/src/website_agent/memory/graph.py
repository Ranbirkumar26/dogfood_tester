"""PageGraph: visited pages and the actions that connect them.

Design rationale (docs/architecture/data-flow.md, section 4): the graph is the planner's
frontier source and the flow-graph/docs report source. Nodes key on a normalized URL plus
a content-class hash so structurally identical template pages (/product/1, /product/2)
collapse into one node, giving coverage without combinatorial blow-up. Deliberately not a
vector store: exploration needs exact dedupe and graph traversal, not similarity search.
The graph is run-scoped, serializable, and rebuilt from state on resume.
"""

from __future__ import annotations

import re
from urllib.parse import urldefrag, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field

# Path segments that look like identifiers collapse to {id} so template pages share a node.
_ID_SEGMENT = re.compile(r"^(?:\d+|[0-9a-f]{8,}|[0-9a-fA-F-]{16,})$")


def normalize_url(url: str, *, keep_query: bool = False) -> str:
    """Canonical URL for graph and dedupe keys.

    Drops the fragment, lowercases scheme/host, strips a trailing slash, and replaces
    id-like path segments with ``{id}``. Query is dropped by default (most query variation
    is navigational noise) but can be kept where it is semantically load-bearing.
    """
    url, _ = urldefrag(url)
    parts = urlsplit(url)
    segments = [("{id}" if _ID_SEGMENT.match(seg) else seg) for seg in parts.path.split("/")]
    path = "/".join(segments).rstrip("/")  # bare root and trailing slashes both normalize away
    query = parts.query if keep_query else ""
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


class PageNode(BaseModel):
    """One page-class in the graph."""

    model_config = ConfigDict(frozen=True)

    key: str  # normalized_url#content_hash
    normalized_url: str
    title: str
    content_hash: str
    visit_count: int = 1
    interactive_elements: int = 0


class PageEdge(BaseModel):
    """A navigation caused by an action, from one page-class to another."""

    model_config = ConfigDict(frozen=True)

    source_key: str
    target_key: str
    action: str
    element_signature: str | None = None


class PageGraph(BaseModel):
    """Serializable graph of discovered pages and transitions.

    Mutation returns updated copies via the ``record_*`` helpers so the graph can live
    inside frozen-by-convention run state; the memory service owns a mutable instance
    during a run and serializes it into checkpoints.
    """

    model_config = ConfigDict(frozen=True)

    nodes: dict[str, PageNode] = Field(default_factory=dict)
    edges: list[PageEdge] = Field(default_factory=list)

    @staticmethod
    def node_key(normalized_url: str, content_hash: str) -> str:
        """Compose a node key from a normalized URL and a content-class hash."""
        return f"{normalized_url}#{content_hash}"

    def visit(self, *, url: str, title: str, content_hash: str, interactive: int) -> PageGraph:
        """Return a graph with this page recorded (visit count incremented if seen)."""
        normalized = normalize_url(url)
        key = self.node_key(normalized, content_hash)
        nodes = dict(self.nodes)
        existing = nodes.get(key)
        if existing is None:
            nodes[key] = PageNode(
                key=key,
                normalized_url=normalized,
                title=title,
                content_hash=content_hash,
                interactive_elements=interactive,
            )
        else:
            nodes[key] = existing.model_copy(update={"visit_count": existing.visit_count + 1})
        return self.model_copy(update={"nodes": nodes})

    def connect(
        self, *, source_key: str, target_key: str, action: str, element_signature: str | None
    ) -> PageGraph:
        """Return a graph with a transition edge added (deduplicated)."""
        edge = PageEdge(
            source_key=source_key,
            target_key=target_key,
            action=action,
            element_signature=element_signature,
        )
        if edge in self.edges:
            return self
        return self.model_copy(update={"edges": [*self.edges, edge]})

    def is_visited(self, url: str, content_hash: str) -> bool:
        """Whether this exact page-class has been visited."""
        return self.node_key(normalize_url(url), content_hash) in self.nodes

    def visited_url_classes(self) -> set[str]:
        """Distinct normalized URLs seen, regardless of content hash (frontier dedupe)."""
        return {node.normalized_url for node in self.nodes.values()}

    @property
    def page_count(self) -> int:
        """Number of distinct page-classes discovered."""
        return len(self.nodes)
