"""Job repository: async Postgres reads/writes for `jobs` rows.

Each write commits immediately: workflow activities call these from many
places and the dashboard reads the rows, so every status change must be
durable and visible right away.
"""

import logging
import uuid
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Job

logger = logging.getLogger(__name__)

STATUSES = ("queued", "running", "awaiting_owner", "completed", "failed", "cancelled")
TERMINAL_STATUSES = ("completed", "failed", "cancelled")
STEPS = (
    "classify", "outline", "overlap", "outline_gate", "research", "write",
    "references", "related", "validate", "draft_gate", "commit",
)


class JobNotFoundError(LookupError):
    """No Job exists for the given id."""


async def create_job(
    session: AsyncSession, *, input_kind: str, input_text: str, domain_choice: str, profile_snapshot: dict
) -> Job:
    """The workflow id is the job id, so the two can always be matched."""
    job_id = str(uuid.uuid4())
    job = Job(
        id=job_id, workflow_id=job_id, input_kind=input_kind, input_text=input_text,
        domain_choice=domain_choice, profile_snapshot=profile_snapshot, status="queued",
    )
    session.add(job)
    await session.commit()
    logger.info("job %s created: %s input, domain choice %r, %d characters", job_id[:8], input_kind, domain_choice, len(input_text))
    return job


async def get_job(session: AsyncSession, job_id: str) -> Job:
    job = await session.get(Job, job_id)
    if job is None:
        raise JobNotFoundError(f"no job with id {job_id!r}")
    await session.refresh(job)  # a long-lived session may hold a stale copy
    return job


async def set_status(
    session: AsyncSession,
    job_id: str,
    *,
    status: str,
    current_step: str | None = None,
    awaiting_owner: bool | None = None,
    error: str | None = None,
) -> Job:
    """Fields left as None are not changed; `error=""` clears a previous error."""
    if status not in STATUSES:
        raise ValueError(f"unknown job status {status!r}")
    job = await get_job(session, job_id)
    job.status = status
    if current_step is not None:
        job.current_step = current_step
    if awaiting_owner is not None:
        job.awaiting_owner = awaiting_owner
    if error is not None:
        job.error = error or None
    await session.commit()
    return job


async def set_resolved_domains(
    session: AsyncSession, job_id: str, domains: list[str], classifier_confidence: float | None = None
) -> None:
    job = await get_job(session, job_id)
    job.resolved_domains = list(domains)
    job.classifier_confidence = classifier_confidence
    await session.commit()


async def add_cost(session: AsyncSession, job_id: str, usd: float) -> None:
    """Atomic in the database, so parallel activities never lose each other's cost."""
    await session.execute(update(Job).where(Job.id == job_id).values(total_cost_usd=Job.total_cost_usd + Decimal(str(usd))))
    await session.commit()


async def list_jobs(session: AsyncSession, statuses: list[str] | None = None) -> list[Job]:
    stmt = select(Job).order_by(Job.created_at.desc())
    if statuses:
        stmt = stmt.where(Job.status.in_(statuses))
    return list((await session.execute(stmt)).scalars().all())
