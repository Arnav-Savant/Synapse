"""Job round repository: async Postgres reads/writes for `job_rounds` rows.

Plain, stateless functions taking an explicit `AsyncSession` argument —
matches the `concept_repo.py`/`agent_config_repo.py` pattern.
`create_job_round` commits immediately per this codebase's established
convention (see `concept_repo.py`'s `create_concept`/`update_concept`
docstrings): each agent round runs in its own subprocess, so a write has to
survive past that round exiting for the trace to be readable afterwards.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import JobRound

logger = logging.getLogger(__name__)


async def create_job_round(
    session: AsyncSession,
    *,
    job_id: str,
    round_number: int,
    agent_type: str,
    prompt_delta: str | None,
    output_summary: str | None,
    structured_output_json: dict | None,
    cost_usd: float | None,
) -> JobRound:
    """Plain insert + commit — matches concept_repo.py's 'commit immediately'
    convention (a subprocess-per-round means the write must survive past
    that round exiting)."""
    round_ = JobRound(
        job_id=job_id,
        round_number=round_number,
        agent_type=agent_type,
        prompt_delta=prompt_delta,
        output_summary=output_summary,
        structured_output_json=structured_output_json,
        cost_usd=cost_usd,
    )
    session.add(round_)
    await session.commit()
    logger.info("job round created: job=%s round=%s agent=%s", job_id, round_number, agent_type)
    return round_


async def list_job_rounds(session: AsyncSession, job_id: str) -> list[JobRound]:
    """Ordered by round_number ascending — the trace record for a job."""
    result = await session.execute(
        select(JobRound).where(JobRound.job_id == job_id).order_by(JobRound.round_number.asc())
    )
    return list(result.scalars().all())
