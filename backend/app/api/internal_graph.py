"""Internal (loopback-only) graph routes.

Deliberately mounted outside `/api` (see `main.py`) to signal "plumbing for
the MCP server subprocess, not for the frontend". Every real agent
invocation runs as a separate OS subprocess (see
`app/mcp_server/entrypoint.py`), and Kùzu is single-process-exclusive — a
second `kuzu.Connection` onto the same database file from that subprocess
crashes outright. These six routes are the loopback-HTTP path
`app/mcp_server/graph_backend.py`'s `RemoteGraphBackend` uses instead of
opening its own `kuzu.Connection`, so the subprocess never touches the
Kùzu file directly; only this already-running backend process does.

Exactly the six `graph_repo` operations `mcp_server/server.py`'s tool
builders touch — no general-purpose Cypher proxy (see
`docs/superpowers/specs/2026-09-24-multi-agent-architecture-design.md`
§10.1: scoped, purpose-built tools, not a generic passthrough).

Thin, like every other route module here: validate via schemas, call the
repository, convert dataclasses to schemas. Plain `def` (not `async def`),
matching `app/api/graph.py`'s existing precedent — Starlette runs sync
`def` routes in a threadpool automatically, and Kùzu's driver has no async
API.
"""

import kuzu
from fastapi import APIRouter, Depends

from app.db.kuzu_db import get_kuzu_connection
from app.repositories import graph_repo
from app.schemas.graph import (
    AddRelationshipRequest,
    EnsureNodeRequest,
    GraphEdgeOut,
    GraphNeighborhoodOut,
    GraphNodeOut,
    RelationshipListOut,
    RemoveRelationshipRequest,
    UpdateRelationshipRequest,
)

router = APIRouter()


def get_kuzu_conn() -> kuzu.Connection:
    return get_kuzu_connection()


@router.get("/neighborhood/{concept_id}", response_model=GraphNeighborhoodOut)
def get_graph_neighborhood(
    concept_id: str,
    depth: int = 1,
    job_id: str | None = None,
    conn: kuzu.Connection = Depends(get_kuzu_conn),
) -> GraphNeighborhoodOut:
    neighborhood = graph_repo.get_graph_neighborhood(conn, concept_id, depth, job_id=job_id)
    return GraphNeighborhoodOut(
        center_id=neighborhood.center_id,
        nodes=[GraphNodeOut(**vars(n)) for n in neighborhood.nodes],
        edges=[GraphEdgeOut(**vars(e)) for e in neighborhood.edges],
    )


@router.get("/relationships/{concept_id}", response_model=RelationshipListOut)
def search_relationships(
    concept_id: str,
    job_id: str | None = None,
    conn: kuzu.Connection = Depends(get_kuzu_conn),
) -> RelationshipListOut:
    relationships = graph_repo.search_relationships(conn, concept_id, job_id=job_id)
    return RelationshipListOut(relationships=[GraphEdgeOut(**vars(r)) for r in relationships])


@router.post("/nodes", status_code=204)
def ensure_node(body: EnsureNodeRequest, conn: kuzu.Connection = Depends(get_kuzu_conn)) -> None:
    graph_repo.ensure_node(conn, body.id, body.title, body.category)


@router.post("/relationships", response_model=GraphEdgeOut)
def add_relationship(
    body: AddRelationshipRequest, conn: kuzu.Connection = Depends(get_kuzu_conn)
) -> GraphEdgeOut:
    record = graph_repo.add_relationship(
        conn,
        source_id=body.source_id,
        target_id=body.target_id,
        type=body.type,
        justification=body.justification,
        note=body.note,
        confidence=body.confidence,
        job_id=body.job_id,
    )
    return GraphEdgeOut(**vars(record))


@router.patch("/relationships", response_model=GraphEdgeOut)
def update_relationship(
    body: UpdateRelationshipRequest, conn: kuzu.Connection = Depends(get_kuzu_conn)
) -> GraphEdgeOut:
    record = graph_repo.update_relationship(
        conn,
        source_id=body.source_id,
        target_id=body.target_id,
        type=body.type,
        job_id=body.job_id,
        note=body.note,
        justification=body.justification,
        confidence=body.confidence,
    )
    return GraphEdgeOut(**vars(record))


@router.delete("/relationships", status_code=204)
def remove_relationship(
    body: RemoveRelationshipRequest, conn: kuzu.Connection = Depends(get_kuzu_conn)
) -> None:
    graph_repo.remove_relationship(
        conn, source_id=body.source_id, target_id=body.target_id, type=body.type, job_id=body.job_id
    )
