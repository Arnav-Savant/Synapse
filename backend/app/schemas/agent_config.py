from datetime import datetime

from pydantic import BaseModel, Field


class AgentConfigOut(BaseModel):
    agent_role: str
    model: str
    effort: str
    params: dict
    updated_at: datetime


class AgentConfigListResponse(BaseModel):
    configs: list[AgentConfigOut]


class UpdateAgentConfigRequest(BaseModel):
    model: str
    effort: str
    params: dict = Field(default_factory=dict)
