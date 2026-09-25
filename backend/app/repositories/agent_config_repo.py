"""Agent config repository: async Postgres reads/writes for `agent_configs`
rows.

Plain, stateless functions taking an explicit `AsyncSession` argument —
matches the `concept_repo.py`/`source_record_repo.py` pattern. The role
roster (orchestrator, text_agent, graph_agent, validation_agent, naming,
chat) is fixed by `db/seed.py`'s seeding; `update_agent_config` never
inserts a new role, only updates one that already exists, and commits
immediately per this codebase's established convention (see
`concept_repo.py`'s `create_concept`/`update_concept` docstrings) so the
write is durable before the request/subprocess that made it exits.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentConfig

logger = logging.getLogger(__name__)


class AgentConfigNotFoundError(LookupError):
    """No AgentConfig row exists for the given agent_role."""


async def get_agent_config(session: AsyncSession, agent_role: str) -> AgentConfig:
    """Raises AgentConfigNotFoundError if no row matches."""
    result = await session.execute(select(AgentConfig).where(AgentConfig.agent_role == agent_role))
    config = result.scalars().first()
    if config is None:
        raise AgentConfigNotFoundError(agent_role)
    return config


async def list_agent_configs(session: AsyncSession) -> list[AgentConfig]:
    """All rows — the 6 seeded roles (orchestrator, text_agent, graph_agent,
    validation_agent, naming, chat) plus any that might exist beyond those."""
    result = await session.execute(select(AgentConfig))
    return list(result.scalars().all())


async def update_agent_config(
    session: AsyncSession,
    *,
    agent_role: str,
    engine: str,
    model: str,
    effort: str,
    provider: str | None = None,
    env_key_name: str | None = None,
) -> AgentConfig:
    """Updates the existing row — never inserts (the role roster is fixed
    by db/seed.py's seeding). Every field is always provided by the caller
    (the API layer always sends a complete UpdateAgentConfigRequest), so
    unlike concept_repo.update_concept this has no partial/None-means-
    unchanged semantics: provider=None/env_key_name=None genuinely clears
    those fields (the claude_code case). Raises AgentConfigNotFoundError if
    agent_role doesn't already exist. Commits the write for the same reason
    as concept_repo.py's create_concept/update_concept — see this module's
    docstring."""
    result = await session.execute(select(AgentConfig).where(AgentConfig.agent_role == agent_role))
    config = result.scalars().first()
    if config is None:
        raise AgentConfigNotFoundError(agent_role)

    config.engine = engine
    config.model = model
    config.effort = effort
    config.provider = provider
    config.env_key_name = env_key_name

    await session.commit()
    logger.info("agent config updated: role=%s engine=%s model=%s", agent_role, engine, model)
    return config
