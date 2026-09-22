"""Processing job routes. Thin: validate via schemas, call the service."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import Settings, get_settings
from app.jobs import store
from app.jobs.queue import JobQueue, get_job_queue
from app.schemas.jobs import JobListResponse, JobOut, ProcessSourceRequest
from app.services import job_service

router = APIRouter()


@router.post("/jobs/process", response_model=JobOut, status_code=202)
async def process_source(
    body: ProcessSourceRequest,
    settings: Settings = Depends(get_settings),
    queue: JobQueue = Depends(get_job_queue),
) -> JobOut:
    job = await job_service.enqueue_processing(
        settings.knowledge_repo_path, body.source_relative_path, queue
    )
    return JobOut(**asdict(job))


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, settings: Settings = Depends(get_settings)) -> JobOut:
    job = store.load_job(settings.knowledge_repo_path, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
    return JobOut(**asdict(job))


@router.get("/jobs", response_model=JobListResponse)
def list_jobs(settings: Settings = Depends(get_settings)) -> JobListResponse:
    jobs = store.list_jobs(settings.knowledge_repo_path)
    return JobListResponse(jobs=[JobOut(**asdict(j)) for j in jobs])
