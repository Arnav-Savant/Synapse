"""Source routes. Thin: validate via schemas, call the service."""

import contextlib

import kuzu
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.postgres_connection import postgres_connection
from app.db.kuzu_db import get_kuzu_connection
from app.db.models import Source
from app.jobs.queue import JobQueue, get_job_queue
from app.schemas.sources import (
    CreateSourceRequest,
    CreateSourceResponse,
    SourceListResponse,
    SourceOut,
)
from app.services import source_service

router = APIRouter()


def get_kuzu_conn() -> kuzu.Connection:
    return get_kuzu_connection()


@router.get("/sources", response_model=SourceListResponse)
async def list_sources(session: AsyncSession = Depends(postgres_connection.get_session)) -> SourceListResponse:
    sources = await source_service.list_sources(session)
    return SourceListResponse(sources=[_to_source_out(s) for s in sources])


@router.post("/sources", response_model=CreateSourceResponse, status_code=201)
async def create_source(
    body: CreateSourceRequest,
    session: AsyncSession = Depends(postgres_connection.get_session),
    kuzu_conn: kuzu.Connection = Depends(get_kuzu_conn),
    queue: JobQueue = Depends(get_job_queue),
) -> CreateSourceResponse:
    # The queued processing job (and the naming agent's ClaudeCodeEngine
    # call, when category isn't given) each need to open their own sessions
    # over a lifetime independent of this request, so a factory is handed
    # down alongside the per-request `session` — same idiom `api/jobs.py`'s
    # `process_source` and `api/chat.py`'s `chat` route use.
    session_factory = contextlib.asynccontextmanager(postgres_connection.get_session)
    source, job = await source_service.create_text_source(
        session,
        session_factory,
        kuzu_conn,
        body.content,
        queue,
        category=body.category,
        topic_hint=body.topic_hint,
    )
    return CreateSourceResponse(source=_to_source_out(source), job_id=job.id)


@router.get("/sources/{source_id}", response_model=SourceOut)
async def get_source(
    source_id: str, session: AsyncSession = Depends(postgres_connection.get_session)
) -> SourceOut:
    source = await source_service.read_source(session, source_id)
    return _to_source_out(source)


def _to_source_out(source: Source) -> SourceOut:
    return SourceOut(
        id=source.id,
        content=source.content,
        category=source.category,
        topic_hint=source.topic_hint,
        uploaded_at=source.uploaded_at,
    )
