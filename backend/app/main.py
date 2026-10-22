"""FastAPI application entrypoint: app construction and route registration only.

Route modules live under `app/api/`; this file wires them together,
configures CORS and maps domain exceptions raised by the repository layer to
HTTP responses centrally. No business logic should be added here.
"""

import asyncio
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
from app.api.jobs import router as jobs_router
from app.api.notes import router as notes_router
from app.api.domains import router as domains_router
from app.core.config import REPO_ROOT, ConfigError, get_server_config, validate_vaults_root
from app.core.logging_config import configure_logging
from app.core.postgres_connection import postgres_connection
from app.db.seed import seed_default_agent_configs, seed_default_domains
from app.engines.claude_code_engine import ClaudeCodeEngineError
from app.engines.factory import build_engine
from app.repositories.agent_config_repo import AgentConfigNotFoundError
from app.repositories.domain_repo import DomainExistsError, DomainNotFoundError
from app.repositories.job_repo import JobNotFoundError
from app.repositories.note_draft_repo import NoteDraftNotFoundError
from app.repositories.note_index_repo import NoteNotFoundError
from app.services.job_service import InputTooLargeError, InvalidJobInputError, JobStartError, JobStateError, reconcile_job_rows
from app.services.note_delete_service import DeleteSelectionError
from app.services.note_service import ConfirmationRequiredError
from app.vault.paths import VaultPathError
from app.services.reconcile_service import reconcile_all
from app.workflows.client import TemporalUnavailableError, ensure_admission_started, get_client
from app.workflows.worker import run_worker
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

    try:
        client = await get_client(settings)
    except TemporalUnavailableError as exc:
        logger.critical("startup aborted: %s", exc)
        raise
    app.state.temporal_client = client
    await ensure_admission_started(client)
    try:
        async for session in postgres_connection.get_session():
            lost = await reconcile_job_rows(session, client)
        if lost:
            logger.warning("%d job(s) had lost their workflow and were marked failed", lost)
    except Exception:
        logger.exception("startup check of running jobs failed; continuing without it")
    worker_task = run_worker(
        client, session_factory=contextlib.asynccontextmanager(postgres_connection.get_session), engine=build_engine()
    )

    logger.info("backend ready")
    yield

    logger.info("backend shutting down")
    worker_task.cancel()
    await asyncio.gather(worker_task, return_exceptions=True)


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
app.add_exception_handler(JobNotFoundError, _json_handler(404, "job not found"))
app.add_exception_handler(NoteNotFoundError, _json_handler(404, "note not found"))
app.add_exception_handler(NoteDraftNotFoundError, _json_handler(404, "draft not found"))
app.add_exception_handler(InvalidJobInputError, _json_handler(400, "invalid job input"))
app.add_exception_handler(DeleteSelectionError, _json_handler(400, "invalid delete selection"))
app.add_exception_handler(VaultPathError, _json_handler(400, "path outside the vault"))
app.add_exception_handler(InputTooLargeError, _json_handler(413, "input too large"))
app.add_exception_handler(JobStateError, _json_handler(409, "job in the wrong state"))
app.add_exception_handler(ConfirmationRequiredError, _json_handler(409, "confirmation required"))
app.add_exception_handler(JobStartError, _json_handler(503, "job could not start", logger.error))
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
app.include_router(jobs_router, prefix="/api")
app.include_router(notes_router, prefix="/api")
