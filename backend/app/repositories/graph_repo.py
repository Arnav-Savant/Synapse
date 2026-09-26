"""Graph (Kùzu) repository: read/topology surface only.

Plain, stateless functions over an explicit `kuzu.Connection` — the same
repository pattern as `knowledge_repo.py`/`source_repo.py`, just backed by
the embedded graph database instead of the filesystem (see
`docs/superpowers/specs/2026-09-24-multi-agent-architecture-design.md` §9.3
for the storage design this implements).

Write functions (`add_relationship` etc.) land in a later, sequential task
in this same file — nothing here should be assumed final/exhaustive.
"""

import logging
from dataclasses import dataclass

import kuzu

from app.db.kuzu_db import HIERARCHY_MAX_DEPTH

logger = logging.getLogger(__name__)

HIERARCHICAL_TYPES = {"subtopic-of", "prerequisite-of"}
SYMMETRIC_TYPES = {"contrasts-with", "related-to"}
DIRECTIONAL_NOT_HIERARCHICAL_TYPES = frozenset({"example-of", "used-in"})
# A second, minimal copy of docs/ARCHITECTURE.md §4.2's fixed taxonomy —
# deliberately NOT imported from app/knowledge/graph.py's own type-handling
# (that module is private to the old filesystem pipeline, untouched and
# still serving live traffic until Phase 4 retires it). This is an
# intentional, documented duplication, not an accidental one.
ALL_RELATIONSHIP_TYPES = frozenset(HIERARCHICAL_TYPES) | SYMMETRIC_TYPES | DIRECTIONAL_NOT_HIERARCHICAL_TYPES


class ConceptNotFoundInGraphError(LookupError):
    """A concept_id referenced in a graph operation has no corresponding
    Concept node in Kùzu."""


class CyclicRelationshipError(ValueError):
    """Adding a hierarchical-type relationship would close a cycle in the
    same-type subgraph."""


class DuplicateRelationshipError(ValueError):
    """An identical (source, target, type) relationship already exists
    (committed, or pending under the same job)."""


class SymmetricRelationshipConflictError(ValueError):
    """A symmetric-type relationship already exists between these two
    concepts, in either direction."""


class RelationshipNotFoundError(LookupError):
    """No relationship matches the given (source_id, target_id, type)."""


class InvalidGraphInputError(ValueError):
    """A graph operation was called with locally-invalid input (unknown
    relationship type, self-loop, blank justification, out-of-range depth)
    — rejected before any Kùzu query runs. Kept as its own type (not a bare
    ValueError) so the MCP tool-binding layer can translate an exact, closed
    set of domain exceptions into agent-visible tool errors without a
    blanket `except ValueError` that could also swallow an unrelated bug."""


@dataclass(frozen=True)
class RelationshipRecord:
    source_id: str
    target_id: str
    type: str
    note: str
    justification: str
    confidence: float | None
    status: str
    job_id: str | None


@dataclass(frozen=True)
class NeighborNode:
    id: str
    title: str
    category: str


@dataclass(frozen=True)
class GraphNeighborhood:
    center_id: str
    nodes: list[NeighborNode]
    edges: list[RelationshipRecord]


def _rows(result: kuzu.QueryResult):
    while result.has_next():
        yield result.get_next()


def _row_to_relationship(row: list) -> RelationshipRecord:
    source_id, target_id, rel_type, note, justification, confidence, status, job_id = row
    return RelationshipRecord(
        source_id=source_id,
        target_id=target_id,
        type=rel_type,
        note=note,
        justification=justification,
        confidence=confidence,
        status=status,
        job_id=job_id,
    )


def ensure_node(conn: kuzu.Connection, concept_id: str, title: str, category: str) -> None:
    """Idempotent upsert of the thin Concept node. Called by the (later)
    MCP tool-binding layer immediately after a Postgres get_concept_metadata
    read, keeping Kùzu nodes in sync only via that path (spec §9.3) — this
    function itself doesn't know about Postgres, it just upserts what it's
    given.

    Installed kuzu (0.11.3, confirmed) supports `MERGE ... ON CREATE SET ...
    ON MATCH SET ...` directly, so no MATCH-then-conditional-CREATE fallback
    is needed.
    """
    conn.execute(
        "MERGE (c:Concept {id: $id}) "
        "ON CREATE SET c.title = $title, c.category = $category "
        "ON MATCH SET c.title = $title, c.category = $category",
        {"id": concept_id, "title": title, "category": category},
    )
    logger.info("concept node upserted in graph: id=%s", concept_id)


def get_graph_neighborhood(
    conn: kuzu.Connection, concept_id: str, depth: int = 1, job_id: str | None = None
) -> GraphNeighborhood:
    """Nodes + edges within `depth` hops of concept_id. Raises
    ConceptNotFoundInGraphError if concept_id itself has no node.

    Edges are scoped to `status = 'committed' OR rel.job_id = $job_id` — the
    same shape already used by `_directional_duplicate_exists`/
    `_symmetric_conflict_exists`/`would_create_cycle` — so a caller sees
    every committed edge plus only its own job's in-flight pending edges,
    never another (possibly crashed/orphaned) job's pending edges.
    `job_id=None` (the default) confirmed empirically to behave as
    committed-only: Kùzu treats a bound Python `None` as SQL NULL, so
    `rel.job_id = $job_id` evaluates to NULL (falsy) rather than matching
    anything, including other NULL job_ids — no conditional query text is
    needed for the `job_id is None` case.

    `depth` controls a Cypher variable-length path bound, which Kùzu does
    not accept as a query parameter (confirmed empirically — only a literal
    integer is valid there), so it's validated as a non-negative int and
    interpolated into the query text rather than bound as `$depth`; every
    other value in this function goes through parameter binding.
    """
    if not isinstance(depth, int) or isinstance(depth, bool) or depth < 0:
        raise InvalidGraphInputError(f"depth must be a non-negative int, got {depth!r}")
    if depth > 5:
        # Depth becomes an LLM-controlled MCP tool parameter once the Graph
        # Agent is wired up (spec §6.2) — bounded here so an agent request
        # can't trigger an unbounded traversal at that trust boundary. 5 is
        # a reasonable default for topology reasoning at this project's
        # "hundreds of nodes" scale; revisit if a real use case needs more.
        raise InvalidGraphInputError(f"depth must be <= 5, got {depth}")

    center_result = conn.execute(
        "MATCH (c:Concept {id: $id}) RETURN c.id, c.title, c.category", {"id": concept_id}
    )
    if not center_result.has_next():
        raise ConceptNotFoundInGraphError(concept_id)
    center_id, center_title, center_category = center_result.get_next()

    nodes_by_id = {center_id: NeighborNode(id=center_id, title=center_title, category=center_category)}

    if depth > 0:
        neighbor_result = conn.execute(
            f"MATCH (start:Concept {{id: $id}})-[e:RELATES_TO*1..{depth}]-(nbr:Concept) "
            "RETURN DISTINCT nbr.id, nbr.title, nbr.category",
            {"id": concept_id},
        )
        for nbr_id, nbr_title, nbr_category in _rows(neighbor_result):
            nodes_by_id.setdefault(nbr_id, NeighborNode(id=nbr_id, title=nbr_title, category=nbr_category))

    edges: list[RelationshipRecord] = []
    node_ids = list(nodes_by_id.keys())
    if len(node_ids) > 1:
        edge_result = conn.execute(
            "MATCH (a:Concept)-[rel:RELATES_TO]->(b:Concept) "
            "WHERE a.id IN $ids AND b.id IN $ids "
            "AND (rel.status = 'committed' OR rel.job_id = $job_id) "
            "RETURN a.id, b.id, rel.type, rel.note, rel.justification, rel.confidence, rel.status, rel.job_id",
            {"ids": node_ids, "job_id": job_id},
        )
        edges = [_row_to_relationship(row) for row in _rows(edge_result)]

    logger.info(
        "graph neighborhood computed: center=%s depth=%d nodes=%d edges=%d",
        concept_id,
        depth,
        len(node_ids),
        len(edges),
    )
    return GraphNeighborhood(center_id=concept_id, nodes=list(nodes_by_id.values()), edges=edges)


def search_relationships(
    conn: kuzu.Connection, concept_id: str, job_id: str | None = None
) -> list[RelationshipRecord]:
    """All relationships touching concept_id, either direction.

    Same `status = 'committed' OR rel.job_id = $job_id` scoping as
    `get_graph_neighborhood` (see its docstring for the empirically-confirmed
    `job_id=None` behavior) — committed edges plus only the caller's own
    job's pending edges.
    """
    result = conn.execute(
        "MATCH (a:Concept)-[rel:RELATES_TO]->(b:Concept) "
        "WHERE (a.id = $id OR b.id = $id) "
        "AND (rel.status = 'committed' OR rel.job_id = $job_id) "
        "RETURN a.id, b.id, rel.type, rel.note, rel.justification, rel.confidence, rel.status, rel.job_id",
        {"id": concept_id, "job_id": job_id},
    )
    return [_row_to_relationship(row) for row in _rows(result)]


def would_create_cycle(conn: kuzu.Connection, source_id: str, target_id: str, edge_type: str, job_id: str) -> bool:
    """True iff adding source_id -[edge_type]-> target_id would create a
    cycle in the subgraph restricted to edge_type. Only meaningful for
    edge_type in HIERARCHICAL_TYPES — callers should only invoke this for
    those types. A path already existing from target_id back to source_id
    (via only same-type edges, pending-this-job + committed) means adding
    the proposed edge would close a cycle.

    `HIERARCHY_MAX_DEPTH` is interpolated into the query text rather than
    bound as `$param` — Kùzu's parser rejects a bound parameter for the
    variable-length path bound (confirmed empirically, consistent with
    `get_graph_neighborhood`'s `depth` handling). It is a module constant,
    never user input, so this is not a SQL/Cypher-injection risk.
    """
    query = (
        "MATCH p = (t:Concept {id: $target_id})"
        f"-[:RELATES_TO* SHORTEST 1..{HIERARCHY_MAX_DEPTH} (r, n | WHERE r.type = $edge_type "
        "AND (r.status = 'committed' OR r.job_id = $job_id))]->"
        "(s:Concept {id: $source_id}) "
        "RETURN length(p) LIMIT 1"
    )
    result = conn.execute(
        query,
        {"target_id": target_id, "source_id": source_id, "edge_type": edge_type, "job_id": job_id},
    )
    return result.has_next()


def _find_missing_concepts(conn: kuzu.Connection, source_id: str, target_id: str) -> set[str]:
    """Returns the subset of {source_id, target_id} that has no Concept node."""
    result = conn.execute(
        "MATCH (n:Concept) WHERE n.id IN [$source_id, $target_id] RETURN n.id",
        {"source_id": source_id, "target_id": target_id},
    )
    found_ids = {row[0] for row in _rows(result)}
    return {source_id, target_id} - found_ids


def _directional_duplicate_exists(conn: kuzu.Connection, source_id: str, target_id: str, edge_type: str, job_id: str) -> bool:
    result = conn.execute(
        "MATCH (a:Concept {id: $source_id})-[r:RELATES_TO]->(b:Concept {id: $target_id}) "
        "WHERE r.type = $edge_type AND (r.status = 'committed' OR r.job_id = $job_id) "
        "RETURN count(r)",
        {"source_id": source_id, "target_id": target_id, "edge_type": edge_type, "job_id": job_id},
    )
    return result.get_next()[0] > 0


def _symmetric_conflict_exists(conn: kuzu.Connection, source_id: str, target_id: str, edge_type: str, job_id: str) -> bool:
    result = conn.execute(
        "MATCH (a:Concept {id: $source_id})-[r:RELATES_TO]-(b:Concept {id: $target_id}) "
        "WHERE r.type = $edge_type AND (r.status = 'committed' OR r.job_id = $job_id) "
        "RETURN count(r)",
        {"source_id": source_id, "target_id": target_id, "edge_type": edge_type, "job_id": job_id},
    )
    return result.get_next()[0] > 0


def add_relationship(
    conn: kuzu.Connection,
    *,
    source_id: str,
    target_id: str,
    type: str,  # noqa: A002 — shadows builtin `type`, but this is the exact agent-facing tool parameter name from the spec; use `edge_type` internally
    justification: str,
    note: str = "",
    confidence: float | None = None,
    job_id: str,
) -> RelationshipRecord:
    """Validate and create a pending RELATES_TO edge (spec §9.3 Layer 2/1
    checks). Raises (in check order): InvalidGraphInputError (unknown type,
    self-loop, blank justification), ConceptNotFoundInGraphError (dangling endpoint),
    CyclicRelationshipError (hierarchical types only),
    SymmetricRelationshipConflictError (symmetric types only),
    DuplicateRelationshipError (directional, non-hierarchy-enforced types).
    """
    edge_type = type

    if edge_type not in ALL_RELATIONSHIP_TYPES:
        raise InvalidGraphInputError(f"unknown relationship type: {edge_type!r}")
    if source_id == target_id:
        raise InvalidGraphInputError(f"self-loop relationship is not allowed: {source_id!r}")
    if not justification or not justification.strip():
        raise InvalidGraphInputError("justification is required and cannot be blank")

    missing = _find_missing_concepts(conn, source_id, target_id)
    if missing:
        raise ConceptNotFoundInGraphError(f"concept(s) not found in graph: {sorted(missing)}")

    if edge_type in HIERARCHICAL_TYPES and would_create_cycle(conn, source_id, target_id, edge_type, job_id):
        raise CyclicRelationshipError(
            f"adding {source_id!r} -[{edge_type}]-> {target_id!r} would create a cycle"
        )

    if edge_type in SYMMETRIC_TYPES:
        if _symmetric_conflict_exists(conn, source_id, target_id, edge_type, job_id):
            raise SymmetricRelationshipConflictError(
                f"symmetric relationship {edge_type!r} already exists between "
                f"{source_id!r} and {target_id!r}"
            )
    elif _directional_duplicate_exists(conn, source_id, target_id, edge_type, job_id):
        raise DuplicateRelationshipError(
            f"relationship {edge_type!r} from {source_id!r} to {target_id!r} already exists"
        )

    conn.execute(
        "MATCH (a:Concept {id: $source_id}), (b:Concept {id: $target_id}) "
        "CREATE (a)-[:RELATES_TO {type: $edge_type, note: $note, justification: $justification, "
        "confidence: $confidence, status: 'pending', job_id: $job_id, "
        "created_at: current_timestamp()}]->(b)",
        {
            "source_id": source_id,
            "target_id": target_id,
            "edge_type": edge_type,
            "note": note,
            "justification": justification,
            "confidence": confidence,
            "job_id": job_id,
        },
    )
    logger.info(
        "relationship added: %s -[%s]-> %s (job=%s, status=pending)", source_id, edge_type, target_id, job_id
    )
    return RelationshipRecord(
        source_id=source_id,
        target_id=target_id,
        type=edge_type,
        note=note,
        justification=justification,
        confidence=confidence,
        status="pending",
        job_id=job_id,
    )


def _get_relationship(conn: kuzu.Connection, source_id: str, target_id: str, edge_type: str) -> RelationshipRecord | None:
    result = conn.execute(
        "MATCH (a:Concept {id: $source_id})-[r:RELATES_TO]->(b:Concept {id: $target_id}) "
        "WHERE r.type = $edge_type "
        "RETURN a.id, b.id, r.type, r.note, r.justification, r.confidence, r.status, r.job_id",
        {"source_id": source_id, "target_id": target_id, "edge_type": edge_type},
    )
    if not result.has_next():
        return None
    return _row_to_relationship(result.get_next())


def update_relationship(
    conn: kuzu.Connection,
    *,
    source_id: str,
    target_id: str,
    type: str,  # noqa: A002
    job_id: str,
    note: str | None = None,
    justification: str | None = None,
    confidence: float | None = None,
) -> RelationshipRecord:
    """Partial update of the edge identified by (source_id, target_id, type)
    — that tuple is unique among pending/committed edges by construction of
    add_relationship's Check 3/4. `None` fields are left as-is.
    """
    edge_type = type
    existing = _get_relationship(conn, source_id, target_id, edge_type)
    if existing is None:
        raise RelationshipNotFoundError(
            f"no relationship {edge_type!r} from {source_id!r} to {target_id!r}"
        )

    new_note = existing.note if note is None else note
    new_justification = existing.justification if justification is None else justification
    new_confidence = existing.confidence if confidence is None else confidence

    conn.execute(
        "MATCH (a:Concept {id: $source_id})-[r:RELATES_TO]->(b:Concept {id: $target_id}) "
        "WHERE r.type = $edge_type "
        "SET r.note = $note, r.justification = $justification, r.confidence = $confidence",
        {
            "source_id": source_id,
            "target_id": target_id,
            "edge_type": edge_type,
            "note": new_note,
            "justification": new_justification,
            "confidence": new_confidence,
        },
    )
    logger.info("relationship updated: %s -[%s]-> %s (job=%s)", source_id, edge_type, target_id, job_id)
    return RelationshipRecord(
        source_id=source_id,
        target_id=target_id,
        type=edge_type,
        note=new_note,
        justification=new_justification,
        confidence=new_confidence,
        status=existing.status,
        job_id=existing.job_id,
    )


def remove_relationship(conn: kuzu.Connection, *, source_id: str, target_id: str, type: str, job_id: str) -> None:
    """Deletes the edge identified by (source_id, target_id, type). Raises
    RelationshipNotFoundError if nothing matches."""
    edge_type = type
    if _get_relationship(conn, source_id, target_id, edge_type) is None:
        raise RelationshipNotFoundError(
            f"no relationship {edge_type!r} from {source_id!r} to {target_id!r}"
        )

    conn.execute(
        "MATCH (a:Concept {id: $source_id})-[r:RELATES_TO]->(b:Concept {id: $target_id}) "
        "WHERE r.type = $edge_type "
        "DELETE r",
        {"source_id": source_id, "target_id": target_id, "edge_type": edge_type},
    )
    logger.info("relationship removed: %s -[%s]-> %s (job=%s)", source_id, edge_type, target_id, job_id)


def get_full_graph(conn: kuzu.Connection) -> GraphNeighborhood:
    """All Concept nodes + all committed RELATES_TO edges, no depth bound —
    the "render everything" read for the graph visualization UI,
    deliberately distinct from get_graph_neighborhood's bounded,
    agent-scoped read.

    Concept nodes carry no `status` property (see `_SCHEMA_STATEMENTS` in
    `app/db/kuzu_db.py` and spec §9.3 — pending/committed is tracked per
    *relationship*, not per concept), so "committed" filtering applies only
    to edges here; every node currently in the graph is returned. Reuses the
    GraphNeighborhood dataclass shape; `center_id=""` is the sentinel for
    "no single center" since a full-graph view has none.
    """
    node_result = conn.execute("MATCH (c:Concept) RETURN c.id, c.title, c.category")
    nodes = [NeighborNode(id=row[0], title=row[1], category=row[2]) for row in _rows(node_result)]

    edge_result = conn.execute(
        "MATCH (a:Concept)-[rel:RELATES_TO]->(b:Concept) "
        "WHERE rel.status = 'committed' "
        "RETURN a.id, b.id, rel.type, rel.note, rel.justification, rel.confidence, rel.status, rel.job_id"
    )
    edges = [_row_to_relationship(row) for row in _rows(edge_result)]

    logger.info("full graph computed: nodes=%d edges=%d", len(nodes), len(edges))
    return GraphNeighborhood(center_id="", nodes=nodes, edges=edges)
