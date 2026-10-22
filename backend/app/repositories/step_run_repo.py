"""Step-run repository: the lean audit and cost trail per job. Prompts and outputs are never stored."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import StepRun


async def record(
    session: AsyncSession,
    *,
    job_id: str,
    step: str,
    agent_role: str | None,
    attempt: int,
    status: str,
    cost_usd: float,
    error: str | None = None,
) -> StepRun:
    now = datetime.now(timezone.utc)
    run = StepRun(
        job_id=job_id, step=step, agent_role=agent_role, attempt=attempt, status=status,
        cost_usd=cost_usd, started_at=now, finished_at=now, error=error,
    )
    session.add(run)
    await session.commit()
    return run


async def list_for_job(session: AsyncSession, job_id: str) -> list[StepRun]:
    result = await session.execute(select(StepRun).where(StepRun.job_id == job_id).order_by(StepRun.started_at))
    return list(result.scalars().all())
