"""Processing job routes. Thin: validate via schemas, call the service."""

import contextlib

import kuzu
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.postgres_connection import postgres_connection
from app.db.kuzu_db import get_kuzu_connection
from app.jobs.queue import JobQueue, get_job_queue
from app.repositories import job_repo
from app.schemas.jobs import JobListResponse, JobOut, ProcessSourceRequest
from app.services import job_service

router = APIRouter()


def get_kuzu_conn() -> kuzu.Connection:
    return get_kuzu_connection()


@router.post("/jobs/process", response_model=JobOut, status_code=202)
async def process_source(
    body: ProcessSourceRequest,
    kuzu_conn: kuzu.Connection = Depends(get_kuzu_conn),
    queue: JobQueue = Depends(get_job_queue),
) -> JobOut:
    # A plain per-request `Depends(postgres_connection.get_session)` session
    # can't be handed to `enqueue_processing`: the queued job runs after this
    # request returns and needs to open its own sessions over its lifetime,
    # so it needs a factory instead — same idiom `api/chat.py` uses to hand
    # `ClaudeCodeEngine` a session factory.
    session_factory = contextlib.asynccontextmanager(postgres_connection.get_session)
    job = await job_service.enqueue_processing(session_factory, kuzu_conn, body.source_id, queue)
    return JobOut.model_validate(job, from_attributes=True)


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(
    job_id: str,
    session: AsyncSession = Depends(postgres_connection.get_session),
) -> JobOut:
    job = await job_repo.get_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
    return JobOut.model_validate(job, from_attributes=True)


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    session: AsyncSession = Depends(postgres_connection.get_session),
) -> JobListResponse:
    jobs = await job_repo.list_jobs(session)
    return JobListResponse(jobs=[JobOut.model_validate(j, from_attributes=True) for j in jobs])
