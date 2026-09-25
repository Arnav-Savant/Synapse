from datetime import datetime

from pydantic import BaseModel


class AgentConfigOut(BaseModel):
    agent_role: str
    engine: str
    provider: str | None
    model: str
    effort: str
    env_key_name: str | None
    updated_at: datetime


class AgentConfigListResponse(BaseModel):
    configs: list[AgentConfigOut]


class UpdateAgentConfigRequest(BaseModel):
    engine: str
    model: str
    effort: str
    provider: str | None = None
    env_key_name: str | None = None
