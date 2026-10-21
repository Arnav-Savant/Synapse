from datetime import datetime

from pydantic import BaseModel, Field


class DomainProfile(BaseModel):
    objective: str = ""
    depth_sections: list[str] = Field(default_factory=list)
    scope_include: str = ""
    scope_mention_only: str = ""
    style: str = ""


class DomainSummary(BaseModel):
    """What the Classifier sees for each domain."""

    slug: str
    name: str
    purpose: str


class DomainOut(BaseModel):
    slug: str
    name: str
    purpose: str
    vault_path: str
    profile: DomainProfile
    folder_existed: bool = False
    created_at: datetime
    updated_at: datetime


class DomainListResponse(BaseModel):
    domains: list[DomainOut]


class CreateDomainRequest(BaseModel):
    name: str
    purpose: str = ""
    profile: DomainProfile = Field(default_factory=DomainProfile)


class UpdateDomainRequest(BaseModel):
    name: str
    purpose: str = ""
    profile: DomainProfile = Field(default_factory=DomainProfile)
