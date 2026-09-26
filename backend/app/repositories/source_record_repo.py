"""Source record repository: the only module that reads/writes the
Postgres-backed `sources` table (a DB row, distinct from the
filesystem-backed `source/` directory owned by `source_repo.py` — see
docs/ARCHITECTURE.md §6 and the multi-agent architecture spec, Phase 2 Task
2.5, for why these are separate, unreconciled concepts for now).

`read_source`/`list_source_categories` are the only Source-record access
surface exposed to the Text Agent. `write_source` is an app-level operation
only (see its docstring) — never exposed as an agent MCP tool.
"""

import logging

from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Source

logger = logging.getLogger(__name__)


class SourceRecordNotFoundError(LookupError):
    """No Source row exists for the given id."""


async def read_source(session: AsyncSession, source_id: str) -> Source:
    """Read-only. Raises SourceRecordNotFoundError if no matching row exists."""
    result = await session.execute(select(Source).where(Source.id == source_id))
    source = result.scalar_one_or_none()
    if source is None:
        logger.warning("source record not found: id=%s", source_id)
        raise SourceRecordNotFoundError(source_id)
    return source


async def write_source(session: AsyncSession, *, content: str, category: str, topic_hint: str | None) -> Source:
    """App-level write only — never exposed as an agent MCP tool (matches
    spec §6.1's 'no agent tool may write source material' rule, applied by
    analogy; this is the human-facing "save a new source" path, not
    something an agent calls). Commits immediately, matching this file's
    established convention."""
    source = Source(content=content, category=category, topic_hint=topic_hint)
    session.add(source)
    await session.commit()
    logger.info("source record created: id=%s category=%r", source.id, category)
    return source


async def list_sources(session: AsyncSession) -> list[Source]:
    """Read-only, newest first — feeds the sources list view (replaces the
    old filesystem-glob-based `source_repo.list_sources`)."""
    result = await session.execute(select(Source).order_by(Source.uploaded_at.desc()))
    return list(result.scalars().all())


async def list_source_categories(session: AsyncSession) -> list[str]:
    """SELECT DISTINCT category FROM sources ORDER BY category — feeds the
    Naming agent's prompt (replaces the old filesystem-glob-based category
    survey). Excludes NULL categories from the result (a source with no
    category yet shouldn't show up as a suggested category name)."""
    result = await session.execute(
        select(distinct(Source.category)).where(Source.category.is_not(None)).order_by(Source.category)
    )
    return list(result.scalars().all())
