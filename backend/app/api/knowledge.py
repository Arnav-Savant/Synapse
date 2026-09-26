"""Knowledge routes. Thin: validate via schemas, call the service."""

import kuzu
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.postgres_connection import postgres_connection
from app.db.kuzu_db import get_kuzu_connection
from app.db.models import Concept
from app.repositories.graph_repo import RelationshipRecord
from app.schemas.knowledge import (
    KnowledgeDetailResponse,
    KnowledgeListResponse,
    KnowledgeSummary,
    RelationshipOut,
    UpdateKnowledgeRequest,
)
from app.services import knowledge_service

router = APIRouter()


def get_kuzu_conn() -> kuzu.Connection:
    return get_kuzu_connection()


@router.get("/knowledge", response_model=KnowledgeListResponse)
async def list_knowledge(session: AsyncSession = Depends(postgres_connection.get_session)) -> KnowledgeListResponse:
    concepts = await knowledge_service.list_knowledge(session)
    return KnowledgeListResponse(
        concepts=[KnowledgeSummary(id=c.id, title=c.title, category=c.category) for c in concepts]
    )


@router.get("/knowledge/{concept_id}", response_model=KnowledgeDetailResponse)
async def get_knowledge(
    concept_id: str,
    session: AsyncSession = Depends(postgres_connection.get_session),
    kuzu_conn: kuzu.Connection = Depends(get_kuzu_conn),
) -> KnowledgeDetailResponse:
    concept, relationships = await knowledge_service.read_knowledge(session, kuzu_conn, concept_id)
    return _to_response(concept, relationships)


@router.put("/knowledge/{concept_id}", response_model=KnowledgeDetailResponse)
async def update_knowledge(
    concept_id: str,
    body: UpdateKnowledgeRequest,
    session: AsyncSession = Depends(postgres_connection.get_session),
    kuzu_conn: kuzu.Connection = Depends(get_kuzu_conn),
) -> KnowledgeDetailResponse:
    concept, relationships = await knowledge_service.update_knowledge(
        session,
        kuzu_conn,
        concept_id=concept_id,
        body=body.body,
        metadata=body.metadata,
    )
    return _to_response(concept, relationships)


def _to_response(concept: Concept, relationships: list[RelationshipRecord]) -> KnowledgeDetailResponse:
    return KnowledgeDetailResponse(
        id=concept.id,
        title=concept.title,
        category=concept.category,
        metadata=concept.metadata_,
        body=concept.body,
        relationships=[
            RelationshipOut(source_id=r.source_id, target_id=r.target_id, type=r.type, note=r.note)
            for r in relationships
        ],
    )
