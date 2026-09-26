"""Job repository: async Postgres reads/writes for `jobs` rows.

Plain, stateless functions taking an explicit `AsyncSession` argument —
matches the `agent_config_repo.py`/`concept_repo.py` pattern.
`create_job`/`save_job` commit immediately, same convention as
`concept_repo.py`'s `create_concept`/`update_concept`: a write has to be
durable before the in-process job queue's worker task (a separate
`async with session_factory()` call, not the same session) can see it.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Job

logger = logging.getLogger(__name__)


async def create_job(session: AsyncSession, *, source_id: str) -> Job:
    """Always inserts status='queued'. Commits immediately per this
    module's docstring."""
    job = Job(source_id=source_id, status="queued")
    session.add(job)
    await session.commit()
    logger.info("job created: id=%s source_id=%s", job.id, source_id)
    return job


async def get_job(session: AsyncSession, job_id: str) -> Job | None:
    """Read-only. Returns None rather than raising when missing — callers
    (job_service's worker) treat a missing job as a mirror of the old
    filesystem store's same-shaped guard, not an exceptional condition."""
    result = await session.execute(select(Job).where(Job.id == job_id))
    return result.scalars().first()


async def save_job(session: AsyncSession, job: Job) -> Job:
    """Persists in-place mutations already made to an already-loaded, still
    session-attached Job row (status/error transitions). Commits
    immediately per this module's docstring."""
    await session.commit()
    logger.info("job saved: id=%s status=%s", job.id, job.status)
    return job


async def list_jobs(session: AsyncSession) -> list[Job]:
    """All rows, most recently created first."""
    result = await session.execute(select(Job).order_by(Job.created_at.desc()))
    return list(result.scalars().all())
