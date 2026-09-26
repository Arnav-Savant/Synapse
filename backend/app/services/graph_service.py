"""Owns the derived graph's in-memory cache.

Recomputed from Kùzu (`graph_repo.get_full_graph`) on first request after a
miss, invalidated explicitly whenever the underlying graph could have
changed (a processing job commits — `orchestrator/graph.py`'s `commit`
node, or a manual knowledge edit). Cheap at "hundreds of nodes" scale
(docs/ARCHITECTURE.md §6), so no incremental indexing.

Exactly one Kùzu database backs the whole app, so the cache is a single
module-level entry rather than the old filesystem model's per-repo-path
dict.
"""

import kuzu

from app.repositories.graph_repo import GraphNeighborhood, get_full_graph

_cached_graph: GraphNeighborhood | None = None


def get_graph(kuzu_conn: kuzu.Connection) -> GraphNeighborhood:
    global _cached_graph
    if _cached_graph is None:
        _cached_graph = get_full_graph(kuzu_conn)
    return _cached_graph


def invalidate() -> None:
    global _cached_graph
    _cached_graph = None
