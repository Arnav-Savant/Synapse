from pydantic import BaseModel


class ProcessSourceRequest(BaseModel):
    source_relative_path: str


class JobOut(BaseModel):
    id: str
    source_relative_path: str
    status: str
    created_at: str
    updated_at: str
    result_summary: str | None = None
    error: str | None = None
    committed_files: list[str] = []
    cost_usd: float | None = None


class JobListResponse(BaseModel):
    jobs: list[JobOut]
