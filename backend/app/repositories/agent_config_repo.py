"""Agent config repository: async Postgres reads/writes for `agent_configs`
rows.

Plain, stateless functions taking an explicit `AsyncSession` argument —
the repository pattern used across `repositories/`. The role roster (the ten
agent roles) is fixed by `db/seed.py`'s seeding; `update_agent_config` never
inserts a new role, only updates one that already exists, and commits
immediately so the write is durable before the request that made it exits.
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
    """All rows, ordered by role name."""
    result = await session.execute(select(AgentConfig).order_by(AgentConfig.agent_role))
    return list(result.scalars().all())


async def update_agent_config(
    session: AsyncSession,
    *,
    agent_role: str,
    model: str,
    effort: str,
    params: dict,
) -> AgentConfig:
    """Updates the existing row — never inserts. Every field is always
    provided by the caller (the API layer always sends a complete request),
    so there are no partial/None-means-unchanged semantics. Raises
    AgentConfigNotFoundError if agent_role doesn't already exist."""
    result = await session.execute(select(AgentConfig).where(AgentConfig.agent_role == agent_role))
    config = result.scalars().first()
    if config is None:
        raise AgentConfigNotFoundError(agent_role)

    config.model = model
    config.effort = effort
    config.params = params

    await session.commit()
    logger.info("agent %r now uses model %s at effort %s", agent_role, model, effort)
    return config
