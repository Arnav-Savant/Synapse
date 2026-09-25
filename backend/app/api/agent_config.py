"""Agent config routes. Thin: validate via schemas, call the service."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.postgres_connection import postgres_connection
from app.schemas.agent_config import AgentConfigListResponse, AgentConfigOut, UpdateAgentConfigRequest
from app.services import agent_config_service

router = APIRouter()


@router.get("/agent-configs", response_model=AgentConfigListResponse)
async def list_agent_configs(
    session: AsyncSession = Depends(postgres_connection.get_session),
) -> AgentConfigListResponse:
    configs = await agent_config_service.list_configs(session)
    return AgentConfigListResponse(configs=[AgentConfigOut.model_validate(c, from_attributes=True) for c in configs])


@router.put("/agent-configs/{agent_role}", response_model=AgentConfigOut)
async def update_agent_config(
    agent_role: str,
    body: UpdateAgentConfigRequest,
    session: AsyncSession = Depends(postgres_connection.get_session),
) -> AgentConfigOut:
    config = await agent_config_service.update_config(
        session,
        agent_role,
        engine=body.engine,
        model=body.model,
        effort=body.effort,
        provider=body.provider,
        env_key_name=body.env_key_name,
    )
    return AgentConfigOut.model_validate(config, from_attributes=True)
