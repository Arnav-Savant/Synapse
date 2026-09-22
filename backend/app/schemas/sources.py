from pydantic import BaseModel, Field


class SourceFileOut(BaseModel):
    category: str
    filename: str
    relative_path: str
    size_bytes: int


class SourceFileListResponse(BaseModel):
    sources: list[SourceFileOut]


class CreateSourceRequest(BaseModel):
    content: str = Field(min_length=1)
    # All optional: leave category/filename unset to have Claude Code file
    # this automatically (docs/PLAN.md ingestion flow); topic_hint is an
    # optional nudge, used whether or not category/filename are given.
    category: str | None = None
    filename: str | None = None
    topic_hint: str | None = None


class SourceContentResponse(BaseModel):
    relative_path: str
    content: str


class CreateSourceResponse(BaseModel):
    source: SourceFileOut
    job_id: str
