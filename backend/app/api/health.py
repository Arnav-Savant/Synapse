"""Health check route.

Thin by design: no business logic lives here, just enough to prove the
backend is up and pointed at a real knowledge repo path. There's no
dedicated service for this (nothing to orchestrate) — see
docs/ARCHITECTURE.md §14.3 on not adding abstraction where a plain function
is enough. Later phases add their own route modules under `api/` rather
than growing this one.
"""

from fastapi import APIRouter, Depends

from app.core.config import ServerConfig, get_server_config
from app.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health(settings: ServerConfig = Depends(get_server_config)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        knowledge_repo_path=str(settings.knowledge_repo_path),
        knowledge_repo_exists=settings.knowledge_repo_path.is_dir(),
    )
