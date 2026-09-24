"""Knowledge file routes. Thin: validate via schemas, call the service."""

from fastapi import APIRouter, Depends

from app.core.config import ServerConfig, get_server_config
from app.knowledge import frontmatter
from app.knowledge.frontmatter import ParsedConcept
from app.schemas.knowledge import (
    KnowledgeDetailResponse,
    KnowledgeListResponse,
    RelationshipOut,
    UpdateKnowledgeRequest,
)
from app.services import knowledge_service

router = APIRouter()


@router.get("/knowledge", response_model=KnowledgeListResponse)
def list_knowledge(settings: ServerConfig = Depends(get_server_config)) -> KnowledgeListResponse:
    slugs = knowledge_service.list_knowledge(settings.knowledge_repo_path)
    return KnowledgeListResponse(slugs=slugs)


@router.get("/knowledge/{slug}", response_model=KnowledgeDetailResponse)
def get_knowledge(slug: str, settings: ServerConfig = Depends(get_server_config)) -> KnowledgeDetailResponse:
    parsed, raw = knowledge_service.read_knowledge(settings.knowledge_repo_path, slug)
    return _to_response(slug, parsed, raw)


@router.put("/knowledge/{slug}", response_model=KnowledgeDetailResponse)
def update_knowledge(
    slug: str, body: UpdateKnowledgeRequest, settings: ServerConfig = Depends(get_server_config)
) -> KnowledgeDetailResponse:
    serialized = knowledge_service.update_knowledge(settings.knowledge_repo_path, slug, body.content)
    parsed = frontmatter.parse(serialized)
    return _to_response(slug, parsed, serialized)


def _to_response(slug: str, parsed: ParsedConcept, raw: str) -> KnowledgeDetailResponse:
    return KnowledgeDetailResponse(
        slug=slug,
        title=parsed.title,
        aliases=parsed.aliases,
        domains=parsed.domains,
        status=parsed.status,
        created=parsed.created,
        updated=parsed.updated,
        sources=parsed.sources,
        relationships=[RelationshipOut(type=r.type, target=r.target, note=r.note) for r in parsed.relationships],
        body=parsed.body,
        raw_content=raw,
    )
