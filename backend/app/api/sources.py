"""Source file routes. Thin: validate via schemas, call the service."""

from fastapi import APIRouter, Depends, UploadFile

from app.core.config import Settings, get_settings
from app.schemas.sources import CreateSourceRequest, SourceFileListResponse, SourceFileOut
from app.services import source_service

router = APIRouter()


@router.get("/sources", response_model=SourceFileListResponse)
def list_sources(settings: Settings = Depends(get_settings)) -> SourceFileListResponse:
    sources = source_service.list_sources(settings.knowledge_repo_path)
    return SourceFileListResponse(sources=[SourceFileOut(**vars(s)) for s in sources])


@router.post("/sources", response_model=SourceFileOut, status_code=201)
def create_source(
    body: CreateSourceRequest, settings: Settings = Depends(get_settings)
) -> SourceFileOut:
    source = source_service.create_text_source(
        settings.knowledge_repo_path, body.category, body.filename, body.content
    )
    return SourceFileOut(**vars(source))


@router.post("/sources/upload", response_model=SourceFileOut, status_code=201)
async def upload_source(
    file: UploadFile, settings: Settings = Depends(get_settings)
) -> SourceFileOut:
    data = await file.read()
    source = source_service.upload_binary_source(settings.knowledge_repo_path, file.filename, data)
    return SourceFileOut(**vars(source))
