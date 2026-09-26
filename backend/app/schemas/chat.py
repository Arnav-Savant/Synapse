from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    concept_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
