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
