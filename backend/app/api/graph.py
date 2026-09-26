"""Graph route. Thin: call the service, convert dataclasses to schemas."""

import kuzu
from fastapi import APIRouter, Depends

from app.db.kuzu_db import get_kuzu_connection
from app.schemas.graph import GraphEdgeOut, GraphNodeOut, GraphResponse
from app.services import graph_service

router = APIRouter()


def get_kuzu_conn() -> kuzu.Connection:
    return get_kuzu_connection()


@router.get("/graph", response_model=GraphResponse)
def get_graph(conn: kuzu.Connection = Depends(get_kuzu_conn)) -> GraphResponse:
    graph = graph_service.get_graph(conn)
    return GraphResponse(
        nodes=[GraphNodeOut(**vars(n)) for n in graph.nodes],
        edges=[GraphEdgeOut(**vars(e)) for e in graph.edges],
    )
