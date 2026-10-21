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

from app.agents.runner import AgentOutputError
from app.api.agent_config import router as agent_config_router
from app.api.health import router as health_router
from app.api.domains import router as domains_router
from app.core.config import REPO_ROOT, ConfigError, get_server_config, validate_vaults_root
from app.core.logging_config import configure_logging
from app.core.postgres_connection import postgres_connection
from app.db.seed import seed_default_agent_configs, seed_default_domains
from app.engines.claude_code_engine import ClaudeCodeEngineError
from app.repositories.agent_config_repo import AgentConfigNotFoundError
from app.repositories.domain_repo import DomainExistsError, DomainNotFoundError
from app.services.reconcile_service import reconcile_all
from app.services.agent_config_service import AgentConfigValidationError
from app.services.domain_service import DomainInUseError, InvalidDomainError, VaultFolderError

configure_logging()
logger = logging.getLogger(__name__)

settings = get_server_config()

_BACKEND_DIR = Path(__file__).resolve().parent.parent  # app/main.py -> app/ -> backend/
_ALEMBIC_INI = _BACKEND_DIR / "alembic.ini"


def _run_migrations() -> None:
    logger.info("running database migrations (alembic upgrade head)")
    try:
        subprocess.run(
            ["alembic", "-c", str(_ALEMBIC_INI), "upgrade", "head"],
            check=True,
            cwd=_BACKEND_DIR,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        logger.critical("database migration failed (is Postgres up? `docker compose up -d postgres`): %s", exc)
        raise
    logger.info("database migrations up to date")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("backend starting up")
    try:
        validate_vaults_root(settings)
    except ConfigError as exc:
        logger.critical("startup aborted: %s", exc)
        raise
    logger.info("vaults root: %s", settings.vaults_root)
    if settings.vaults_root.resolve().is_relative_to(REPO_ROOT):
        logger.warning("VAULTS_ROOT is inside the repo — it must be gitignored; vaults are never committed")
    _run_migrations()

    async for session in postgres_connection.get_session():
        await seed_default_agent_configs(session)

    async for session in postgres_connection.get_session():
        await seed_default_domains(session, settings)

    try:
        async for session in postgres_connection.get_session():
            await reconcile_all(session)
    except Exception:
        # A reconcile problem must never keep the app from starting; the Notes page can re-run it.
        logger.exception("startup reconcile failed; continuing without it")

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


def _json_handler(status_code: int, label: str, level=logger.info):
    async def handler(request: Request, exc: Exception) -> JSONResponse:
        level("%s: %s", label, exc)
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})

    return handler


app.add_exception_handler(DomainNotFoundError, _json_handler(404, "domain not found"))
app.add_exception_handler(DomainExistsError, _json_handler(409, "domain already exists"))
app.add_exception_handler(DomainInUseError, _json_handler(409, "domain in use"))
app.add_exception_handler(InvalidDomainError, _json_handler(400, "invalid domain"))
app.add_exception_handler(AgentOutputError, _json_handler(502, "agent output unusable", logger.error))
app.add_exception_handler(VaultFolderError, _json_handler(500, "vault folder error", logger.error))


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # Last resort: log the full traceback server-side, never leak internals to the client.
    logger.exception("unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "internal server error — see backend logs"})


app.include_router(health_router, prefix="/api")
app.include_router(agent_config_router, prefix="/api")
app.include_router(domains_router, prefix="/api")
