"""Graph route. Thin: call the service, convert dataclasses to schemas."""

from fastapi import APIRouter, Depends

from app.core.config import ServerConfig, get_server_config
from app.schemas.graph import GraphEdgeOut, GraphNodeOut, GraphResponse
from app.services import graph_service

router = APIRouter()


@router.get("/graph", response_model=GraphResponse)
def get_graph(settings: ServerConfig = Depends(get_server_config)) -> GraphResponse:
    graph = graph_service.get_graph(settings.knowledge_repo_path)
    return GraphResponse(
        nodes=[GraphNodeOut(**vars(n)) for n in graph.nodes],
        edges=[GraphEdgeOut(**vars(e)) for e in graph.edges],
        warnings=graph.warnings,
    )
