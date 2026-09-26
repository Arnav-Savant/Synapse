"""Orchestrates `repositories/source_record_repo.py` and
`agents/naming_agent.py` for the sources API.

The real logic here: auto-filing a source's category via the naming agent
when the caller doesn't supply one, and auto-enqueuing that source's
processing job right after writing it — pasting content and having the
knowledge base update is meant to be one action, not two (see
docs/ARCHITECTURE.md §14.2: routes stay thin, services hold the logic).

This is the Postgres/DB-backed cutover of what used to write to the
filesystem `source/` directory (`repositories/source_repo.py`,
`claude_runner/naming.py`, `claude_runner/git_guard.py`) — a `Source` row
has no filename/path to collide on, so the old collision-avoidance and
git-commit-on-save logic this replaces no longer applies.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import naming_agent
from app.db.models import Job, Source
from app.jobs.queue import JobQueue
from app.repositories import source_record_repo
from app.services import job_service

logger = logging.getLogger(__name__)


async def list_sources(session: AsyncSession) -> list[Source]:
    return await source_record_repo.list_sources(session)


async def read_source(session: AsyncSession, source_id: str) -> Source:
    return await source_record_repo.read_source(session, source_id)


async def create_text_source(
    session: AsyncSession,
    session_factory,
    kuzu_conn,
    content: str,
    queue: JobQueue,
    category: str | None = None,
    topic_hint: str | None = None,
) -> tuple[Source, Job]:
    """`category` is optional — when it isn't given, the naming agent
    decides it by surveying categories already in use
    (`agents/naming_agent.suggest_source_location`), not a slugify
    heuristic. `session_factory` is threaded through separately from
    `session` because both `job_service.enqueue_processing` and the naming
    agent's `ClaudeCodeEngine` need to open their own sessions across a
    subprocess/worker-task boundary, not share this request's session.

    Returns the written source together with the processing job enqueued
    for it — saving and processing are one action from the caller's side.
    """
    if not category:
        category = await naming_agent.suggest_source_location(session, session_factory, content, topic_hint)

    source = await source_record_repo.write_source(session, content=content, category=category, topic_hint=topic_hint)
    job = await job_service.enqueue_processing(session_factory, kuzu_conn, source.id, queue)
    logger.info("source saved: id=%s category=%r (job %s enqueued)", source.id, category, job.id)
    return source, job
