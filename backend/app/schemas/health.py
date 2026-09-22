from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    knowledge_repo_path: str
    knowledge_repo_exists: bool
