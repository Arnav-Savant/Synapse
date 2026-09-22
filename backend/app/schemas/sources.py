from pydantic import BaseModel, Field


class SourceFileOut(BaseModel):
    category: str
    filename: str
    relative_path: str
    size_bytes: int


class SourceFileListResponse(BaseModel):
    sources: list[SourceFileOut]


class CreateSourceRequest(BaseModel):
    category: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    content: str


class SourceContentResponse(BaseModel):
    relative_path: str
    content: str
