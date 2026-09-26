from datetime import datetime

from pydantic import BaseModel


class ProcessSourceRequest(BaseModel):
    source_id: str


class JobOut(BaseModel):
    id: str
    source_id: str
    status: str
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class JobListResponse(BaseModel):
    jobs: list[JobOut]
