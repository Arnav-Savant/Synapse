import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentConfig
from app.db.seed import seed_default_agent_configs

ROLES = {"orchestrator", "text_agent", "graph_agent", "validation_agent", "naming", "chat"}


@pytest.mark.asyncio
async def test_seed_creates_six_defaults(db_session: AsyncSession):
    await seed_default_agent_configs(db_session)
    result = await db_session.execute(select(AgentConfig))
    rows = result.scalars().all()
    assert {row.agent_role for row in rows} == ROLES
    assert all(row.engine == "claude_code" for row in rows)


@pytest.mark.asyncio
async def test_seed_is_idempotent(db_session: AsyncSession):
    await seed_default_agent_configs(db_session)
    await seed_default_agent_configs(db_session)
    result = await db_session.execute(select(AgentConfig))
    assert len(result.scalars().all()) == 6
