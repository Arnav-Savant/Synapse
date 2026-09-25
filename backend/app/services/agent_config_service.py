"""Orchestrates `repositories/agent_config_repo.py` for the agent-config API.

Validation lives here, not in the repository (which only knows how to read/
write rows) or the route (which stays thin per docs/ARCHITECTURE.md §14.2) —
this is the one layer that knows both the engine-specific validation rules
(spec §11.5) and the repository it delegates the actual write to.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_env_var
from app.db.models import AgentConfig
from app.repositories import agent_config_repo

_ENGINES = ("claude_code", "litellm")
_CLAUDE_CODE_EFFORTS = ("low", "medium", "high", "xhigh", "max")


class AgentConfigValidationError(ValueError):
    """A PUT /api/agent-configs/{role} request failed validation (spec §11.5)."""


async def list_configs(session: AsyncSession) -> list[AgentConfig]:
    return await agent_config_repo.list_agent_configs(session)


async def update_config(
    session: AsyncSession,
    agent_role: str,
    *,
    engine: str,
    model: str,
    effort: str,
    provider: str | None,
    env_key_name: str | None,
) -> AgentConfig:
    _validate(engine=engine, effort=effort, env_key_name=env_key_name)

    return await agent_config_repo.update_agent_config(
        session,
        agent_role=agent_role,
        engine=engine,
        model=model,
        effort=effort,
        provider=provider,
        env_key_name=env_key_name,
    )


def _validate(*, engine: str, effort: str, env_key_name: str | None) -> None:
    if engine not in _ENGINES:
        raise AgentConfigValidationError(f"engine must be one of {_ENGINES}, got {engine!r}")

    if engine == "claude_code":
        if effort not in _CLAUDE_CODE_EFFORTS:
            raise AgentConfigValidationError(
                f"effort must be one of {_CLAUDE_CODE_EFFORTS} for engine 'claude_code', got {effort!r}"
            )
        return

    # engine == "litellm"
    if not env_key_name:
        raise AgentConfigValidationError("env_key_name is required for engine 'litellm'")
    if get_env_var(env_key_name) is None:
        raise AgentConfigValidationError(f"{env_key_name} not set — add it to .env and restart the backend")
