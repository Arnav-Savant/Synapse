import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentConfig, Job, JobRound


@pytest.mark.asyncio
async def test_job_round_roundtrip(db_session: AsyncSession):
    job = Job(source_id="src-1", status="running")
    db_session.add(job)
    await db_session.flush()

    round_ = JobRound(
        job_id=job.id,
        round_number=1,
        agent_type="text",
        prompt_delta=None,
        output_summary="created 1 concept",
        structured_output_json=None,
        cost_usd=0.01,
    )
    db_session.add(round_)
    await db_session.commit()

    assert round_.id is not None
    assert round_.job_id == job.id


@pytest.mark.asyncio
async def test_agent_config_defaults(db_session: AsyncSession):
    cfg = AgentConfig(agent_role="text_agent", engine="claude_code", model="claude-sonnet-5", effort="medium")
    db_session.add(cfg)
    await db_session.commit()
    assert cfg.provider is None
    assert cfg.env_key_name is None
