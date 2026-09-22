from pydantic import BaseModel


class KnowledgeListResponse(BaseModel):
    slugs: list[str]


class RelationshipOut(BaseModel):
    type: str
    target: str
    note: str | None = None


class KnowledgeDetailResponse(BaseModel):
    slug: str
    title: str
    aliases: list[str]
    domains: list[str]
    status: str
    created: str | None
    updated: str | None
    sources: list[str]
    relationships: list[RelationshipOut]
    body: str
    raw_content: str


class UpdateKnowledgeRequest(BaseModel):
    content: str
