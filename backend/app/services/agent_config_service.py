"""Orchestrates `repositories/agent_config_repo.py` for the agent-config API.

Validation lives here, not in the repository (which only knows how to read/
write rows) or the route (which stays thin per docs/ARCHITECTURE.md §14.2).
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentConfig
from app.repositories import agent_config_repo

_EFFORTS = ("low", "medium", "high", "xhigh", "max")


class AgentConfigValidationError(ValueError):
    """A PUT /api/agent-configs/{role} request failed validation."""


async def list_configs(session: AsyncSession) -> list[AgentConfig]:
    return await agent_config_repo.list_agent_configs(session)


async def update_config(
    session: AsyncSession,
    agent_role: str,
    *,
    model: str,
    effort: str,
    params: dict,
) -> AgentConfig:
    if effort not in _EFFORTS:
        raise AgentConfigValidationError(f"effort must be one of {_EFFORTS}, got {effort!r}")
    if not model.strip():
        raise AgentConfigValidationError("model must not be empty")

    return await agent_config_repo.update_agent_config(
        session, agent_role=agent_role, model=model.strip(), effort=effort, params=params
    )
