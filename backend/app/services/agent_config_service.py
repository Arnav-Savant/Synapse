"""Orchestrates `repositories/agent_config_repo.py` for the agent-config API.

Validation lives here, not in the repository (which only knows how to read/
write rows) or the route (which stays thin per docs/ARCHITECTURE.md §14.2).
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentConfig
from app.repositories import agent_config_repo
from app.schemas.agent_config import ModelOption

_EFFORTS = ("low", "medium", "high", "xhigh", "max")

# The values `claude --model` accepts for the current model family: a pinned full ID, or an alias that
# follows the newest release (https://code.claude.com/docs/en/model-config). The CLI has no command that
# lists them. Every model here supports all five effort levels.
AVAILABLE_MODELS: tuple[ModelOption, ...] = (
    ModelOption(id="claude-fable-5-1", label="Fable 5.1", group="pinned"),
    ModelOption(id="claude-opus-5-5", label="Opus 5.5", group="pinned"),
    ModelOption(id="claude-sonnet-5-5", label="Sonnet 5.5", group="pinned"),
    ModelOption(id="claude-haiku-5-5", label="Haiku 5.5", group="pinned"),
    ModelOption(id="fable", label="Fable (latest)", group="latest"),
    ModelOption(id="opus", label="Opus (latest)", group="latest"),
    ModelOption(id="sonnet", label="Sonnet (latest)", group="latest"),
    ModelOption(id="haiku", label="Haiku (latest)", group="latest"),
)


class AgentConfigValidationError(ValueError):
    """A PUT /api/agent-configs/{role} request failed validation."""


def list_models() -> list[ModelOption]:
    return list(AVAILABLE_MODELS)


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
    if model.strip() not in {m.id for m in AVAILABLE_MODELS}:
        choices = ", ".join(m.id for m in AVAILABLE_MODELS)
        raise AgentConfigValidationError(f"unknown model {model.strip()!r}; choose one of: {choices}")

    return await agent_config_repo.update_agent_config(
        session, agent_role=agent_role, model=model.strip(), effort=effort, params=params
    )
