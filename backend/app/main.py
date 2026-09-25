"""FastAPI application entrypoint: app construction and route registration only.

Route modules live under `app/api/`; this file wires them together,
configures CORS, maps domain exceptions raised by the repository layer to
HTTP responses centrally, and starts the job queue worker on startup. No
business logic should be added here.
"""

import logging
import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.chat import router as chat_router
from app.api.graph import router as graph_router
from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.api.knowledge import router as knowledge_router
from app.api.sources import router as sources_router
from app.claude_runner.chat_engine import ChatEngineError
from app.claude_runner.naming import NamingError
from app.core.config import get_server_config
from app.core.logging_config import configure_logging
from app.core.postgres_connection import postgres_connection
from app.db.seed import seed_default_agent_configs
from app.jobs import store as job_store
from app.jobs.queue import JobQueue
from app.knowledge.frontmatter import FrontmatterError
from app.repositories.knowledge_repo import KnowledgeFileNotFoundError
from app.repositories.paths import PathTraversalError
from app.repositories.source_repo import SourceFileNotFoundError

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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("backend starting up")
    _run_migrations()

    async for session in postgres_connection.get_session():
        await seed_default_agent_configs(session)
    logger.info("default agent_configs seeded")

    job_store.reconcile_orphaned_running_jobs(settings.knowledge_repo_path)

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


@app.exception_handler(PathTraversalError)
async def handle_path_traversal(request: Request, exc: PathTraversalError) -> JSONResponse:
    logger.warning("path traversal attempt blocked: %s", exc)
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(KnowledgeFileNotFoundError)
async def handle_knowledge_not_found(request: Request, exc: KnowledgeFileNotFoundError) -> JSONResponse:
    logger.info("knowledge concept not found: %s", exc)
    return JSONResponse(status_code=404, content={"detail": f"knowledge concept not found: {exc}"})


@app.exception_handler(SourceFileNotFoundError)
async def handle_source_not_found(request: Request, exc: SourceFileNotFoundError) -> JSONResponse:
    logger.info("source file not found: %s", exc)
    return JSONResponse(status_code=404, content={"detail": f"source file not found: {exc}"})


@app.exception_handler(FrontmatterError)
async def handle_frontmatter_error(request: Request, exc: FrontmatterError) -> JSONResponse:
    logger.warning("frontmatter parse/write error: %s", exc)
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(ChatEngineError)
async def handle_chat_engine_error(request: Request, exc: ChatEngineError) -> JSONResponse:
    logger.error("chat engine invocation failed: %s", exc)
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(NamingError)
async def handle_naming_error(request: Request, exc: NamingError) -> JSONResponse:
    logger.error("source auto-naming failed: %s", exc)
    return JSONResponse(status_code=502, content={"detail": str(exc)})


app.include_router(health_router, prefix="/api")
app.include_router(sources_router, prefix="/api")
app.include_router(knowledge_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")
app.include_router(graph_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
