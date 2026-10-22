from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.outline import Outline

MAX_INPUT_CHARS = 200_000
CLASSIFIER_CONFIDENCE_THRESHOLD = 0.7


class StepRunOut(BaseModel):
    step: str
    agent_role: str | None
    attempt: int
    status: str
    cost_usd: float
    started_at: datetime
    finished_at: datetime | None
    error: str | None


class CreateJobRequest(BaseModel):
    input_kind: Literal["topic", "content"]
    text: str
    domain_choice: str = "auto"  # a domain slug, or "auto"


class JobOut(BaseModel):
    id: str
    title: str  # the first line of the input, shortened
    input_kind: str
    domain_choice: str
    resolved_domains: list[str]
    status: str
    current_step: str | None
    awaiting_owner: bool
    error: str | None
    total_cost_usd: float
    created_at: datetime
    updated_at: datetime


class JobListResponse(BaseModel):
    jobs: list[JobOut]


class JobDetail(JobOut):
    steps: list[StepRunOut]


class OutlineView(BaseModel):
    outline: Outline
    resolved_domains: list[str]
    classifier_confidence: float | None
    low_confidence: bool  # below the threshold: the owner should confirm the domain
    error: str | None  # why the last edit was rejected, if it was


class DraftView(BaseModel):
    node_key: str
    domain_slug: str
    title: str
    kind: str  # new | merge
    stage: str
    path: str | None
    parents: list[str]  # titles of the notes this one sits under
    body_md: str
    validator_flags: list[dict]
    diff: str | None  # merge drafts: unified diff against the file on disk now


class LinkAdditionView(BaseModel):
    note_title: str
    domain_slug: str
    section: str
    entry_title: str


class DraftsResponse(BaseModel):
    drafts: list[DraftView]
    link_additions: list[LinkAdditionView] = Field(default_factory=list)
