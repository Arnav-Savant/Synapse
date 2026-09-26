from datetime import datetime

from pydantic import BaseModel, Field


class SourceOut(BaseModel):
    id: str
    content: str
    category: str | None
    topic_hint: str | None
    uploaded_at: datetime


class SourceListResponse(BaseModel):
    sources: list[SourceOut]


class CreateSourceRequest(BaseModel):
    content: str = Field(min_length=1)
    # Optional: leave category unset to have the naming agent file this
    # automatically; topic_hint is an optional nudge, used whether or not
    # category is given. There's no filename concept under the DB model.
    category: str | None = None
    topic_hint: str | None = None


class CreateSourceResponse(BaseModel):
    source: SourceOut
    job_id: str
