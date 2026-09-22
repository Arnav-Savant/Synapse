"""Source file routes. Thin: validate via schemas, call the service."""

from fastapi import APIRouter, Depends, UploadFile

from app.core.config import Settings, get_settings
from app.jobs.queue import JobQueue, get_job_queue
from app.schemas.sources import (
    CreateSourceRequest,
    CreateSourceResponse,
    SourceContentResponse,
    SourceFileListResponse,
    SourceFileOut,
)
from app.services import source_service

router = APIRouter()


@router.get("/sources", response_model=SourceFileListResponse)
def list_sources(settings: Settings = Depends(get_settings)) -> SourceFileListResponse:
    sources = source_service.list_sources(settings.knowledge_repo_path)
    return SourceFileListResponse(sources=[SourceFileOut(**vars(s)) for s in sources])


@router.post("/sources", response_model=CreateSourceResponse, status_code=201)
async def create_source(
    body: CreateSourceRequest,
    settings: Settings = Depends(get_settings),
    queue: JobQueue = Depends(get_job_queue),
) -> CreateSourceResponse:
    source, job = await source_service.create_text_source(
        settings.knowledge_repo_path,
        body.content,
        queue,
        category=body.category,
        filename=body.filename,
        topic_hint=body.topic_hint,
    )
    return CreateSourceResponse(source=SourceFileOut(**vars(source)), job_id=job.id)


@router.post("/sources/upload", response_model=SourceFileOut, status_code=201)
async def upload_source(
    file: UploadFile, settings: Settings = Depends(get_settings)
) -> SourceFileOut:
    data = await file.read()
    source = source_service.upload_binary_source(settings.knowledge_repo_path, file.filename, data)
    return SourceFileOut(**vars(source))


@router.get("/sources/{relative_path:path}", response_model=SourceContentResponse)
def get_source_content(
    relative_path: str, settings: Settings = Depends(get_settings)
) -> SourceContentResponse:
    content = source_service.read_source(settings.knowledge_repo_path, relative_path)
    return SourceContentResponse(relative_path=relative_path, content=content)
