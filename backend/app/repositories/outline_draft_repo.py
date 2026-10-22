"""Outline draft repository: one row per job, overwritten on every re-plan, deleted when the job ends."""

from datetime import datetime, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import OutlineDraft
from app.schemas.outline import Outline


async def save(session: AsyncSession, job_id: str, tree: Outline, feedback: str | None) -> None:
    row = await session.get(OutlineDraft, job_id)
    if row is None:
        row = OutlineDraft(job_id=job_id)
        session.add(row)
    row.tree = tree.model_dump(mode="json")
    row.feedback = feedback
    row.updated_at = datetime.now(timezone.utc)
    await session.commit()


async def get(session: AsyncSession, job_id: str) -> Outline | None:
    row = await session.get(OutlineDraft, job_id)
    if row is not None:
        await session.refresh(row)
    return Outline.model_validate(row.tree) if row is not None else None


async def delete_for_job(session: AsyncSession, job_id: str) -> None:
    await session.execute(delete(OutlineDraft).where(OutlineDraft.job_id == job_id))
    await session.commit()
