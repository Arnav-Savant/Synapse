from datetime import datetime

from pydantic import BaseModel, Field, model_validator


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


class ProfileAnswers(BaseModel):
    """What the owner typed into the domain form (or pasted) for "Draft with Claude"."""

    name: str = ""
    purpose: str = ""
    objective: str = ""
    depth_sections: list[str] = Field(default_factory=list)
    scope_include: str = ""
    scope_mention_only: str = ""
    style: str = ""
    pasted_prompt: str | None = None

    @model_validator(mode="after")
    def _something_to_work_from(self) -> "ProfileAnswers":
        typed = [self.name, self.purpose, self.objective, self.scope_include, self.scope_mention_only, self.style, self.pasted_prompt or ""]
        if not any(t.strip() for t in typed) and not any(s.strip() for s in self.depth_sections):
            raise ValueError("fill in at least one field or paste a prompt to draft from")
        return self
