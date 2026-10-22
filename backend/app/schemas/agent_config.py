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


class ModelOption(BaseModel):
    id: str  # what is passed to `claude --model`
    label: str
    group: str  # "pinned" is a fixed version; "latest" is an alias that follows the newest release


class ModelListResponse(BaseModel):
    models: list[ModelOption]
