"""Knowledge file routes. Thin: validate via schemas, call the service."""

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.schemas.knowledge import KnowledgeDetailResponse, KnowledgeListResponse
from app.services import knowledge_service

router = APIRouter()


@router.get("/knowledge", response_model=KnowledgeListResponse)
def list_knowledge(settings: Settings = Depends(get_settings)) -> KnowledgeListResponse:
    slugs = knowledge_service.list_knowledge(settings.knowledge_repo_path)
    return KnowledgeListResponse(slugs=slugs)


@router.get("/knowledge/{slug}", response_model=KnowledgeDetailResponse)
def get_knowledge(slug: str, settings: Settings = Depends(get_settings)) -> KnowledgeDetailResponse:
    content = knowledge_service.read_knowledge(settings.knowledge_repo_path, slug)
    return KnowledgeDetailResponse(slug=slug, content=content)
