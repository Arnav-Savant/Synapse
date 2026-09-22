"""Chat route. Thin: validate via schemas, call the service."""

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import chat_service

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, settings: Settings = Depends(get_settings)) -> ChatResponse:
    reply = await chat_service.ask(settings.knowledge_repo_path, body.message, body.concept_slug)
    return ChatResponse(reply=reply)
