from datetime import datetime

from pydantic import BaseModel, Field


class CreateChatRequest(BaseModel):
    domain_slugs: list[str] = Field(min_length=1)


class AskRequest(BaseModel):
    text: str


class CitationOut(BaseModel):
    ref: int
    domain: str
    title: str
    heading: str


class MessageOut(BaseModel):
    id: str
    position: int
    role: str
    kind: str
    text: str
    status: str
    step: str | None
    citations: list[CitationOut]
    gaps: list[str]
    flags: list[str]
    error: str | None
    cost_usd: float
    created_at: datetime


class ChatSummaryOut(BaseModel):
    id: str
    title: str
    domain_slugs: list[str]
    updated_at: datetime
    pending: bool


class ChatDetailOut(ChatSummaryOut):
    messages: list[MessageOut]
    total_cost_usd: float


class ChatListResponse(BaseModel):
    chats: list[ChatSummaryOut]
