from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentConfig

_DEFAULTS = {
    "orchestrator": "claude-sonnet-5",
    "text_agent": "claude-sonnet-5",
    "graph_agent": "claude-sonnet-5",
    "validation_agent": "claude-opus-5-5",
    "naming": "claude-haiku-4-5-20251001",
    "chat": "claude-sonnet-5",
}


async def seed_default_agent_configs(session: AsyncSession) -> None:
    result = await session.execute(select(AgentConfig.agent_role))
    existing = {row[0] for row in result.all()}
    for role, model in _DEFAULTS.items():
        if role in existing:
            continue
        session.add(AgentConfig(agent_role=role, engine="claude_code", model=model, effort="medium"))
    await session.commit()
