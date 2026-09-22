"""Build the derived graph ({nodes, edges}) from parsed knowledge concepts.

Pure function — no I/O; `services/graph_service.py` does the file reading
via `repositories/knowledge_repo.py` and this module's `frontmatter.parse`.
See docs/ARCHITECTURE.md §4.1/§4.2 for the relationship taxonomy and the
frontmatter-vs-wikilink dedup rule this implements.
"""

from dataclasses import dataclass

from app.knowledge.frontmatter import ParsedConcept
from app.knowledge.wikilinks import extract_links

# Inverse labels for display only — never stored, always derived (§4.1).
# Symmetric types (contrasts-with, related-to) aren't in this map; their
# inverse is themselves.
_INVERSE_LABELS = {
    "subtopic-of": "has-subtopic",
    "prerequisite-of": "depends-on",
    "example-of": "has-example",
    "used-in": "uses",
}


@dataclass(frozen=True)
class GraphNode:
    id: str
    title: str
    aliases: list[str]
    domains: list[str]
    status: str


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    type: str
    inverse_type: str
    note: str | None
    implicit: bool


@dataclass(frozen=True)
class Graph:
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    warnings: list[str]


def build_graph(concepts: list[ParsedConcept]) -> Graph:
    known_ids = {c.id for c in concepts}
    nodes = [
        GraphNode(id=c.id, title=c.title, aliases=c.aliases, domains=c.domains, status=c.status)
        for c in concepts
    ]

    edges: list[GraphEdge] = []
    warnings: list[str] = []
    # Unordered pairs already connected by a frontmatter-declared
    # relationship (in either direction) — an implicit wikilink edge for a
    # pair that's already connected is a duplicate, not new information.
    connected_pairs: set[frozenset[str]] = set()

    for concept in concepts:
        for rel in concept.relationships:
            if rel.target not in known_ids:
                warnings.append(
                    f"{concept.id}: relationship '{rel.type}' points at unknown concept '{rel.target}'"
                )
                continue
            edges.append(
                GraphEdge(
                    source=concept.id,
                    target=rel.target,
                    type=rel.type,
                    inverse_type=_INVERSE_LABELS.get(rel.type, rel.type),
                    note=rel.note,
                    implicit=False,
                )
            )
            connected_pairs.add(frozenset((concept.id, rel.target)))

    for concept in concepts:
        for linked_slug in extract_links(concept.body):
            if linked_slug == concept.id:
                continue
            if linked_slug not in known_ids:
                warnings.append(f"{concept.id}: [[{linked_slug}]] does not match any known concept")
                continue
            pair = frozenset((concept.id, linked_slug))
            if pair in connected_pairs:
                continue
            connected_pairs.add(pair)
            edges.append(
                GraphEdge(
                    source=concept.id,
                    target=linked_slug,
                    type="related-to",
                    inverse_type="related-to",
                    note=None,
                    implicit=True,
                )
            )

    return Graph(nodes=nodes, edges=edges, warnings=warnings)
