import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.postgres_connection import postgres_connection
from app.db.models import AgentConfig, Base
from app.repositories.agent_config_repo import AgentConfigNotFoundError, get_agent_config
from app.services.agent_config_service import AgentConfigValidationError, list_configs, update_config

_ROLES_USED = ("chat", "text_agent", "naming")


@pytest.fixture
async def db_session():
    """Adapted from `tests/test_agent_config_repo.py`'s fixture: ensures the
    schema exists (idempotent `create_all`, harmless whether or not Alembic
    already migrated it) but deliberately does NOT `Base.metadata.drop_all()`
    at teardown — this file is required (Task 3.8's regression bundle) to
    run in the same pytest session as `test_agent_config_api.py`, whose
    `TestClient`-triggered `lifespan` relies on Alembic's migrations having
    already run against the real dev Postgres DB; a `drop_all` here would
    leave tables missing while Alembic still believes it's at head
    (confirmed empirically), breaking every test afterward in the same
    session. Row-scoped cleanup of just the roles this file uses is enough
    isolation without that side effect — done both before and after each
    test, so a prior run that errored out mid-test (leaving a row
    uncommitted-cleanup) can't poison the next one either."""
    engine = postgres_connection.get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(delete(AgentConfig).where(AgentConfig.agent_role.in_(_ROLES_USED)))
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.execute(delete(AgentConfig).where(AgentConfig.agent_role.in_(_ROLES_USED)))
    await engine.dispose()


async def _seed(db_session: AsyncSession, **overrides) -> None:
    fields = {
        "agent_role": "chat",
        "engine": "claude_code",
        "provider": None,
        "model": "claude-sonnet-5",
        "effort": "medium",
        "env_key_name": None,
    }
    fields.update(overrides)
    db_session.add(AgentConfig(**fields))
    await db_session.flush()


@pytest.mark.asyncio
async def test_update_config_rejects_unknown_engine(db_session: AsyncSession):
    await _seed(db_session)

    with pytest.raises(AgentConfigValidationError):
        await update_config(
            db_session, "chat", engine="ollama", model="llama3", effort="medium", provider=None, env_key_name=None
        )


@pytest.mark.asyncio
async def test_update_config_rejects_invalid_claude_code_effort(db_session: AsyncSession):
    await _seed(db_session)

    with pytest.raises(AgentConfigValidationError):
        await update_config(
            db_session,
            "chat",
            engine="claude_code",
            model="claude-sonnet-5",
            effort="ultra",
            provider=None,
            env_key_name=None,
        )


@pytest.mark.asyncio
async def test_update_config_rejects_litellm_without_env_key_name(db_session: AsyncSession):
    await _seed(db_session)

    with pytest.raises(AgentConfigValidationError):
        await update_config(
            db_session, "chat", engine="litellm", model="gpt-5", effort="high", provider="openai", env_key_name=None
        )


@pytest.mark.asyncio
async def test_update_config_rejects_litellm_with_unset_env_var(db_session: AsyncSession, monkeypatch):
    await _seed(db_session)
    monkeypatch.delenv("SOME_UNSET_API_KEY", raising=False)

    with pytest.raises(AgentConfigValidationError, match="SOME_UNSET_API_KEY"):
        await update_config(
            db_session,
            "chat",
            engine="litellm",
            model="gpt-5",
            effort="high",
            provider="openai",
            env_key_name="SOME_UNSET_API_KEY",
        )


@pytest.mark.asyncio
async def test_update_config_accepts_litellm_with_set_env_var(db_session: AsyncSession, monkeypatch):
    await _seed(db_session)
    monkeypatch.setenv("SOME_SET_API_KEY", "sk-test-value")

    config = await update_config(
        db_session,
        "chat",
        engine="litellm",
        model="gpt-5",
        effort="high",
        provider="openai",
        env_key_name="SOME_SET_API_KEY",
    )

    assert config.engine == "litellm"
    assert config.env_key_name == "SOME_SET_API_KEY"


@pytest.mark.asyncio
async def test_update_config_accepts_valid_claude_code_and_reflected_on_reread(db_session: AsyncSession):
    await _seed(db_session)

    await update_config(
        db_session, "chat", engine="claude_code", model="claude-opus-5-5", effort="high", provider=None, env_key_name=None
    )

    reread = await get_agent_config(db_session, "chat")
    assert reread.engine == "claude_code"
    assert reread.model == "claude-opus-5-5"
    assert reread.effort == "high"


@pytest.mark.asyncio
async def test_update_config_unknown_agent_role_propagates_not_found(db_session: AsyncSession):
    with pytest.raises(AgentConfigNotFoundError):
        await update_config(
            db_session,
            "does-not-exist",
            engine="claude_code",
            model="claude-sonnet-5",
            effort="medium",
            provider=None,
            env_key_name=None,
        )


@pytest.mark.asyncio
async def test_list_configs_passthrough(db_session: AsyncSession):
    await _seed(db_session, agent_role="text_agent")
    await _seed(db_session, agent_role="naming")

    configs = await list_configs(db_session)

    # Subset, not equality: this table is real, shared Postgres state that
    # other test files' seeded roles (e.g. orchestrator) may also be
    # sitting in — list_configs is a passthrough over all rows (see
    # agent_config_repo.list_agent_configs' own docstring), so the
    # meaningful assertion is "includes what this test seeded", not
    # "contains only what this test seeded".
    assert {"text_agent", "naming"} <= {c.agent_role for c in configs}
