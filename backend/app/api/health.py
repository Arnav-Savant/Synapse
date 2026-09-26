"""Health check route.

Thin by design: no business logic lives here, just enough to prove the
backend is up. There's no dedicated service for this (nothing to
orchestrate) — see docs/ARCHITECTURE.md §14.3 on not adding abstraction
where a plain function is enough. Later phases add their own route modules
under `api/` rather than growing this one.
"""

from fastapi import APIRouter

from app.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")
