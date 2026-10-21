"""FastAPI application entrypoint: app construction and route registration only.

Route modules live under `app/api/`; this file wires them together,
configures CORS and maps domain exceptions raised by the repository layer to
HTTP responses centrally. No business logic should be added here.
"""

import contextlib
import logging
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.agent_config import router as agent_config_router
from app.api.health import router as health_router
from app.core.config import get_server_config
from app.core.logging_config import configure_logging
from app.core.postgres_connection import postgres_connection
from app.db.seed import seed_default_agent_configs
from app.engines.claude_code_engine import ClaudeCodeEngineError
from app.repositories.agent_config_repo import AgentConfigNotFoundError
from app.services.agent_config_service import AgentConfigValidationError

configure_logging()
logger = logging.getLogger(__name__)

settings = get_server_config()

_BACKEND_DIR = Path(__file__).resolve().parent.parent  # app/main.py -> app/ -> backend/
_ALEMBIC_INI = _BACKEND_DIR / "alembic.ini"


def _run_migrations() -> None:
    logger.info("running database migrations (alembic upgrade head)")
    subprocess.run(
        ["alembic", "-c", str(_ALEMBIC_INI), "upgrade", "head"],
        check=True,
        cwd=_BACKEND_DIR,
    )
    logger.info("database migrations up to date")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("backend starting up")
    _run_migrations()

    async for session in postgres_connection.get_session():
        await seed_default_agent_configs(session)
    logger.info("default agent_configs seeded")

    logger.info("backend ready")
    yield

    logger.info("backend shutting down")


app = FastAPI(title="Synapse Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ClaudeCodeEngineError)
async def handle_claude_code_engine_error(request: Request, exc: ClaudeCodeEngineError) -> JSONResponse:
    logger.error("claude_code engine invocation failed: %s", exc)
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(AgentConfigNotFoundError)
async def handle_agent_config_not_found(request: Request, exc: AgentConfigNotFoundError) -> JSONResponse:
    logger.info("agent config not found: %s", exc)
    return JSONResponse(status_code=404, content={"detail": f"agent config not found: {exc}"})


@app.exception_handler(AgentConfigValidationError)
async def handle_agent_config_validation_error(request: Request, exc: AgentConfigValidationError) -> JSONResponse:
    logger.warning("agent config validation error: %s", exc)
    return JSONResponse(status_code=400, content={"detail": str(exc)})


app.include_router(health_router, prefix="/api")
app.include_router(agent_config_router, prefix="/api")
