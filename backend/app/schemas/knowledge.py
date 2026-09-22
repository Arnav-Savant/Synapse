from pydantic import BaseModel


class KnowledgeListResponse(BaseModel):
    slugs: list[str]


class KnowledgeDetailResponse(BaseModel):
    slug: str
    content: str
