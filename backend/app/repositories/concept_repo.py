"""Concept repository: async Postgres reads/writes for `concepts` rows.

Plain, stateless functions taking an explicit `AsyncSession` argument —
matches the `knowledge_repo.py`/`source_repo.py`/`paths.py` pattern for
filesystem repositories (docs/ARCHITECTURE.md §6/§14.2), applied here to the
Postgres-backed concept store (`app/db/models.py`). `create_concept`/
`update_concept` commit immediately: the staging model (spec §10.2) treats
`commit_job()`/`rollback_job()` as a status-flip/delete over already-durable
rows, not a SQL transaction boundary, and each agent round runs in its own
subprocess against its own `SynapseMcpServer` instance — a write has to
survive past that process exiting for a later round or another agent's
subprocess to see it via `search_concepts`.
"""

import logging
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Concept

logger = logging.getLogger(__name__)


class ConceptNotFoundError(LookupError):
    """No concept exists for the given id."""


@dataclass(frozen=True)
class ConceptMetadata:
    id: str
    title: str
    category: str


async def get_concept(session: AsyncSession, concept_id: str) -> Concept:
    """Full row incl. body — Text Agent's merge-decision read, Validation
    Agent's cross-check read."""
    result = await session.execute(select(Concept).where(Concept.id == concept_id))
    concept = result.scalars().first()
    if concept is None:
        raise ConceptNotFoundError(concept_id)
    return concept


async def get_concept_metadata(session: AsyncSession, concept_id: str) -> ConceptMetadata:
    """Postgres-only read of (id, title, category) — deliberately excludes
    body (spec §6.2 information-asymmetry with Graph Agent)."""
    result = await session.execute(
        select(Concept.id, Concept.title, Concept.category).where(Concept.id == concept_id)
    )
    row = result.first()
    if row is None:
        raise ConceptNotFoundError(concept_id)
    return ConceptMetadata(id=row.id, title=row.title, category=row.category)


async def search_concepts(
    session: AsyncSession, query: str, *, job_id: str | None = None, limit: int = 10
) -> list[ConceptMetadata]:
    """Matches status='committed' concepts, plus this job's own
    status='pending' concepts when `job_id` is given (so a per-topic dedup
    check sees concepts already created earlier in the same job, not just
    prior committed state). Case-insensitive substring match against title
    and `metadata_["aliases"]`, done in Python after a bounded fetch —
    consistent with this codebase's existing "hundreds of concepts, full
    scan is fine" scale assumption (`app/knowledge/graph.py` already does a
    full-corpus scan-on-read), not a new performance assumption.
    """
    visibility = Concept.status == "committed"
    if job_id is not None:
        visibility = or_(visibility, (Concept.status == "pending") & (Concept.job_id == job_id))

    result = await session.execute(
        select(Concept.id, Concept.title, Concept.category, Concept.metadata_).where(visibility)
    )
    needle = query.strip().lower()

    matches: list[ConceptMetadata] = []
    for row in result.all():
        aliases = (row.metadata_ or {}).get("aliases", [])
        title_match = needle in row.title.lower()
        alias_match = any(needle in alias.lower() for alias in aliases)
        if title_match or alias_match:
            matches.append(ConceptMetadata(id=row.id, title=row.title, category=row.category))
        if len(matches) >= limit:
            break

    return matches


async def create_concept(
    session: AsyncSession, *, title: str, category: str, body: str, metadata: dict, job_id: str
) -> Concept:
    """Always inserts status='pending', job_id=job_id. No dedup check here
    — that's the caller's (Text Agent's) judgment; this function trusts the
    decision already made."""
    concept = Concept(
        title=title,
        category=category,
        body=body,
        metadata_=metadata,
        status="pending",
        job_id=job_id,
    )
    session.add(concept)
    await session.commit()
    logger.info("concept created: id=%s title=%r job=%s", concept.id, title, job_id)
    return concept


async def update_concept(
    session: AsyncSession,
    *,
    concept_id: str,
    job_id: str,
    body: str | None = None,
    metadata: dict | None = None,
) -> Concept:
    """Partial update — None means 'leave as-is', preserving what's there.
    Re-stages an already-committed concept touched by a new job: sets
    status='pending', job_id=job_id."""
    result = await session.execute(select(Concept).where(Concept.id == concept_id))
    concept = result.scalars().first()
    if concept is None:
        raise ConceptNotFoundError(concept_id)

    if body is not None:
        concept.body = body
    if metadata is not None:
        concept.metadata_ = metadata
    concept.status = "pending"
    concept.job_id = job_id

    await session.commit()
    logger.info("concept %s re-staged as pending for job %s", concept_id, job_id)
    return concept
