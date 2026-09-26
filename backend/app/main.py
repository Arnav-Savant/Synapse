"""FastAPI application entrypoint: app construction and route registration only.

Route modules live under `app/api/`; this file wires them together,
configures CORS, maps domain exceptions raised by the repository layer to
HTTP responses centrally, and starts the job queue worker on startup. No
business logic should be added here.
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
from app.api.chat import router as chat_router
from app.api.graph import router as graph_router
from app.api.health import router as health_router
from app.api.internal_graph import router as internal_graph_router
from app.api.jobs import router as jobs_router
from app.api.knowledge import router as knowledge_router
from app.api.sources import router as sources_router
from app.agents.naming_agent import NamingAgentError
from app.core.config import get_server_config
from app.core.logging_config import configure_logging
from app.core.postgres_connection import postgres_connection
from app.db.kuzu_db import get_kuzu_connection
from app.db.seed import seed_default_agent_configs
from app.engines.claude_code_engine import ClaudeCodeEngineError
from app.jobs.queue import JobQueue
from app.jobs.reconciliation import reconcile_orphaned_running_jobs
from app.repositories import graph_repo
from app.repositories.agent_config_repo import AgentConfigNotFoundError
from app.repositories.concept_repo import ConceptNotFoundError
from app.repositories.source_record_repo import SourceRecordNotFoundError
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

    session_factory = contextlib.asynccontextmanager(postgres_connection.get_session)
    kuzu_conn = get_kuzu_connection()
    reconciled_ids = await reconcile_orphaned_running_jobs(session_factory, kuzu_conn)
    if reconciled_ids:
        logger.warning("reconciled %d orphaned running job(s): %s", len(reconciled_ids), reconciled_ids)

    queue = JobQueue()
    queue.start()
    app.state.job_queue = queue
    logger.info("job queue started, backend ready")
    yield

    logger.info("backend shutting down")
    await queue.stop()


app = FastAPI(title="Synapse Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ConceptNotFoundError)
async def handle_concept_not_found(request: Request, exc: ConceptNotFoundError) -> JSONResponse:
    logger.info("concept not found: %s", exc)
    return JSONResponse(status_code=404, content={"detail": f"concept not found: {exc}"})


@app.exception_handler(SourceRecordNotFoundError)
async def handle_source_record_not_found(request: Request, exc: SourceRecordNotFoundError) -> JSONResponse:
    logger.info("source record not found: %s", exc)
    return JSONResponse(status_code=404, content={"detail": f"source record not found: {exc}"})


@app.exception_handler(ClaudeCodeEngineError)
async def handle_claude_code_engine_error(request: Request, exc: ClaudeCodeEngineError) -> JSONResponse:
    logger.error("claude_code engine invocation failed: %s", exc)
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(NamingAgentError)
async def handle_naming_agent_error(request: Request, exc: NamingAgentError) -> JSONResponse:
    logger.error("source auto-naming failed: %s", exc)
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(AgentConfigNotFoundError)
async def handle_agent_config_not_found(request: Request, exc: AgentConfigNotFoundError) -> JSONResponse:
    logger.info("agent config not found: %s", exc)
    return JSONResponse(status_code=404, content={"detail": f"agent config not found: {exc}"})


@app.exception_handler(AgentConfigValidationError)
async def handle_agent_config_validation_error(request: Request, exc: AgentConfigValidationError) -> JSONResponse:
    logger.warning("agent config validation error: %s", exc)
    return JSONResponse(status_code=400, content={"detail": str(exc)})


def _graph_error_response(status_code: int, exc: Exception) -> JSONResponse:
    # Unlike the `/api/*` handlers above (whose only consumer is the
    # frontend, which just displays `detail`), these six back
    # `/internal/graph/*` — `app.mcp_server.graph_backend.RemoteGraphBackend`
    # is the sole consumer, and it must reconstruct the *exact* exception
    # type raised in-process (see that module's `_raise_for_error_response`),
    # so the exception class name rides along as `error`.
    return JSONResponse(status_code=status_code, content={"error": type(exc).__name__, "detail": str(exc)})


@app.exception_handler(graph_repo.ConceptNotFoundInGraphError)
async def handle_concept_not_found_in_graph(request: Request, exc: graph_repo.ConceptNotFoundInGraphError) -> JSONResponse:
    logger.info("concept not found in graph: %s", exc)
    return _graph_error_response(404, exc)


@app.exception_handler(graph_repo.RelationshipNotFoundError)
async def handle_relationship_not_found(request: Request, exc: graph_repo.RelationshipNotFoundError) -> JSONResponse:
    logger.info("relationship not found: %s", exc)
    return _graph_error_response(404, exc)


@app.exception_handler(graph_repo.CyclicRelationshipError)
async def handle_cyclic_relationship(request: Request, exc: graph_repo.CyclicRelationshipError) -> JSONResponse:
    logger.info("cyclic relationship rejected: %s", exc)
    return _graph_error_response(409, exc)


@app.exception_handler(graph_repo.DuplicateRelationshipError)
async def handle_duplicate_relationship(request: Request, exc: graph_repo.DuplicateRelationshipError) -> JSONResponse:
    logger.info("duplicate relationship rejected: %s", exc)
    return _graph_error_response(409, exc)


@app.exception_handler(graph_repo.SymmetricRelationshipConflictError)
async def handle_symmetric_relationship_conflict(
    request: Request, exc: graph_repo.SymmetricRelationshipConflictError
) -> JSONResponse:
    logger.info("symmetric relationship conflict rejected: %s", exc)
    return _graph_error_response(409, exc)


@app.exception_handler(graph_repo.InvalidGraphInputError)
async def handle_invalid_graph_input(request: Request, exc: graph_repo.InvalidGraphInputError) -> JSONResponse:
    logger.info("invalid graph input rejected: %s", exc)
    return _graph_error_response(400, exc)


app.include_router(health_router, prefix="/api")
app.include_router(sources_router, prefix="/api")
app.include_router(knowledge_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")
app.include_router(graph_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(agent_config_router, prefix="/api")
app.include_router(internal_graph_router, prefix="/internal/graph")
