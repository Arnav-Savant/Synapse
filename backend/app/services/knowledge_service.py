"""Orchestrates `repositories/concept_repo.py`/`repositories/graph_repo.py`
for the Knowledge API.

Read path: list committed concepts (Postgres), read a full concept row
(Postgres, including body) plus its relationships (Kùzu, read-only).
Write path: a direct human edit — `concept_repo.update_concept_content`
(NOT the agent-facing `update_concept` tool: no job/agent semantics, no
re-staging to `pending`, sets `status='committed'` directly) — then
invalidate the derived graph cache.
"""

import kuzu
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Concept
from app.repositories import concept_repo, graph_repo
from app.repositories.concept_repo import ConceptMetadata
from app.repositories.graph_repo import RelationshipRecord
from app.services import graph_service


async def list_knowledge(session: AsyncSession) -> list[ConceptMetadata]:
    return await concept_repo.list_committed_concepts(session)


async def read_knowledge(
    session: AsyncSession, kuzu_conn: kuzu.Connection, concept_id: str
) -> tuple[Concept, list[RelationshipRecord]]:
    concept = await concept_repo.get_concept(session, concept_id)
    relationships = graph_repo.search_relationships(kuzu_conn, concept_id)
    return concept, relationships


async def update_knowledge(
    session: AsyncSession,
    kuzu_conn: kuzu.Connection,
    *,
    concept_id: str,
    body: str,
    metadata: dict,
) -> tuple[Concept, list[RelationshipRecord]]:
    concept = await concept_repo.update_concept_content(session, concept_id=concept_id, body=body, metadata=metadata)
    graph_service.invalidate()
    relationships = graph_repo.search_relationships(kuzu_conn, concept_id)
    return concept, relationships
