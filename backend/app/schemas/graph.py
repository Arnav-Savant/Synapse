from pydantic import BaseModel


class GraphNodeOut(BaseModel):
    id: str
    title: str
    category: str


class GraphEdgeOut(BaseModel):
    source_id: str
    target_id: str
    type: str
    note: str
    justification: str
    confidence: float | None
    status: str
    job_id: str | None


class GraphResponse(BaseModel):
    nodes: list[GraphNodeOut]
    edges: list[GraphEdgeOut]


# --- Internal (loopback-only) request/response models -----------------------
#
# Used by app/api/internal_graph.py, the six `/internal/graph/*` routes that
# `app/mcp_server/graph_backend.py`'s `RemoteGraphBackend` calls from the MCP
# server subprocess. Mirror `app/repositories/graph_repo.py`'s dataclass/
# parameter shapes closely enough that `RemoteGraphBackend` can reconstruct
# the exact same dataclasses from the JSON response.


class GraphNeighborhoodOut(BaseModel):
    center_id: str
    nodes: list[GraphNodeOut]
    edges: list[GraphEdgeOut]


class RelationshipListOut(BaseModel):
    relationships: list[GraphEdgeOut]


class EnsureNodeRequest(BaseModel):
    id: str
    title: str
    category: str


class AddRelationshipRequest(BaseModel):
    source_id: str
    target_id: str
    type: str
    justification: str
    note: str = ""
    confidence: float | None = None
    job_id: str


class UpdateRelationshipRequest(BaseModel):
    source_id: str
    target_id: str
    type: str
    job_id: str
    note: str | None = None
    justification: str | None = None
    confidence: float | None = None


class RemoveRelationshipRequest(BaseModel):
    source_id: str
    target_id: str
    type: str
    job_id: str
