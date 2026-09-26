from pydantic import BaseModel


class KnowledgeSummary(BaseModel):
    id: str
    title: str
    category: str


class KnowledgeListResponse(BaseModel):
    concepts: list[KnowledgeSummary]


class RelationshipOut(BaseModel):
    source_id: str
    target_id: str
    type: str
    note: str | None = None


class KnowledgeDetailResponse(BaseModel):
    id: str
    title: str
    category: str
    metadata: dict
    body: str
    relationships: list[RelationshipOut]


class UpdateKnowledgeRequest(BaseModel):
    body: str
    metadata: dict
