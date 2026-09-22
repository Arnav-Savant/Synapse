from pydantic import BaseModel


class GraphNodeOut(BaseModel):
    id: str
    title: str
    aliases: list[str]
    domains: list[str]
    status: str


class GraphEdgeOut(BaseModel):
    source: str
    target: str
    type: str
    inverse_type: str
    note: str | None = None
    implicit: bool


class GraphResponse(BaseModel):
    nodes: list[GraphNodeOut]
    edges: list[GraphEdgeOut]
    warnings: list[str]
