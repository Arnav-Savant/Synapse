"""Owns the derived graph's in-memory cache.

Recomputed from `knowledge/*.md` on first request after a miss, invalidated
explicitly whenever the underlying knowledge repo could have changed (a
processing job completes — `job_service.py` — or a manual save in Phase 5).
Cheap at "hundreds of nodes" scale (docs/ARCHITECTURE.md §6), so no
incremental indexing. A malformed knowledge file is skipped with a warning
rather than failing the whole graph, consistent with the "surface as
warnings, don't crash" rule for broken relationship targets.
"""

from pathlib import Path

from app.knowledge import frontmatter
from app.knowledge.graph import Graph, build_graph
from app.repositories import knowledge_repo

_cache: dict[Path, Graph] = {}


def get_graph(knowledge_repo_path: Path) -> Graph:
    if knowledge_repo_path not in _cache:
        _cache[knowledge_repo_path] = _build(knowledge_repo_path)
    return _cache[knowledge_repo_path]


def invalidate(knowledge_repo_path: Path) -> None:
    _cache.pop(knowledge_repo_path, None)


def _build(knowledge_repo_path: Path) -> Graph:
    concepts = []
    parse_warnings = []

    for slug in knowledge_repo.list_knowledge_slugs(knowledge_repo_path):
        raw = knowledge_repo.read_knowledge(knowledge_repo_path, slug)
        try:
            concepts.append(frontmatter.parse(raw))
        except frontmatter.FrontmatterError as exc:
            parse_warnings.append(f"{slug}: could not parse frontmatter ({exc})")

    graph = build_graph(concepts)
    return Graph(nodes=graph.nodes, edges=graph.edges, warnings=[*parse_warnings, *graph.warnings])
