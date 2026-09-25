import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.postgres_connection import postgres_connection
from app.db.models import AgentConfig, Base
from app.repositories.agent_config_repo import (
    AgentConfigNotFoundError,
    get_agent_config,
    list_agent_configs,
    update_agent_config,
)


@pytest.fixture
async def db_session():
    """Local duplicate of `tests/db/conftest.py`'s fixture — this test file
    lives outside `tests/db/`, and per the assignment's own guidance it's
    simpler to duplicate the fixture than to reach across directories."""
    engine = postgres_connection.get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_agent_config_happy_path(db_session: AsyncSession):
    db_session.add(
        AgentConfig(
            agent_role="text_agent",
            engine="claude_code",
            provider=None,
            model="claude-sonnet-5",
            effort="medium",
            env_key_name=None,
        )
    )
    await db_session.flush()

    config = await get_agent_config(db_session, "text_agent")

    assert config.agent_role == "text_agent"
    assert config.model == "claude-sonnet-5"
    assert config.effort == "medium"


@pytest.mark.asyncio
async def test_get_agent_config_not_found_raises(db_session: AsyncSession):
    with pytest.raises(AgentConfigNotFoundError):
        await get_agent_config(db_session, "does-not-exist")


@pytest.mark.asyncio
async def test_list_agent_configs_returns_all_rows(db_session: AsyncSession):
    db_session.add_all(
        [
            AgentConfig(agent_role="orchestrator", engine="claude_code", model="claude-sonnet-5", effort="medium"),
            AgentConfig(agent_role="text_agent", engine="claude_code", model="claude-sonnet-5", effort="medium"),
            AgentConfig(agent_role="graph_agent", engine="claude_code", model="claude-sonnet-5", effort="medium"),
            AgentConfig(agent_role="validation_agent", engine="claude_code", model="claude-opus-5-5", effort="medium"),
            AgentConfig(agent_role="naming", engine="claude_code", model="claude-haiku-4-5-20251001", effort="medium"),
            AgentConfig(agent_role="chat", engine="claude_code", model="claude-sonnet-5", effort="medium"),
        ]
    )
    await db_session.flush()

    configs = await list_agent_configs(db_session)

    assert {c.agent_role for c in configs} == {
        "orchestrator",
        "text_agent",
        "graph_agent",
        "validation_agent",
        "naming",
        "chat",
    }


@pytest.mark.asyncio
async def test_update_agent_config_full_field_update_reflected_on_reread(db_session: AsyncSession):
    db_session.add(
        AgentConfig(
            agent_role="chat",
            engine="claude_code",
            provider=None,
            model="claude-sonnet-5",
            effort="medium",
            env_key_name=None,
        )
    )
    await db_session.flush()

    await update_agent_config(
        db_session,
        agent_role="chat",
        engine="litellm",
        model="gpt-5",
        effort="high",
        provider="openai",
        env_key_name="OPENAI_API_KEY",
    )

    reread = await get_agent_config(db_session, "chat")
    assert reread.engine == "litellm"
    assert reread.model == "gpt-5"
    assert reread.effort == "high"
    assert reread.provider == "openai"
    assert reread.env_key_name == "OPENAI_API_KEY"


@pytest.mark.asyncio
async def test_update_agent_config_clears_provider_and_env_key_name_for_claude_code(db_session: AsyncSession):
    db_session.add(
        AgentConfig(
            agent_role="naming",
            engine="litellm",
            provider="openai",
            model="gpt-5",
            effort="high",
            env_key_name="OPENAI_API_KEY",
        )
    )
    await db_session.flush()

    await update_agent_config(
        db_session,
        agent_role="naming",
        engine="claude_code",
        model="claude-haiku-4-5-20251001",
        effort="low",
        provider=None,
        env_key_name=None,
    )

    reread = await get_agent_config(db_session, "naming")
    assert reread.engine == "claude_code"
    assert reread.provider is None
    assert reread.env_key_name is None


@pytest.mark.asyncio
async def test_update_agent_config_not_found_raises(db_session: AsyncSession):
    with pytest.raises(AgentConfigNotFoundError):
        await update_agent_config(
            db_session,
            agent_role="does-not-exist",
            engine="claude_code",
            model="claude-sonnet-5",
            effort="medium",
        )
